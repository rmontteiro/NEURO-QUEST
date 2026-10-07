"""Lê a carteira, pede os números ao motor e propõe quatro ordens."""

from __future__ import annotations

import os
from typing import Any

import httpx

from app.db import list_positions

STABLES = frozenset({"USDC", "USDT", "DAI", "USDS", "USDE", "FDUSD", "PYUSD"})

BASE_TOKENS = {
    "ETH": "0x4200000000000000000000000000000000000006",
    "WETH": "0x4200000000000000000000000000000000000006",
    "USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
}
TOKEN_DECIMALS = {"ETH": 18, "WETH": 18, "USDC": 6}

SOLANA_MINTS = {
    "SOL": "So11111111111111111111111111111111111111112",
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
}


def engine_url() -> str:
    return os.environ.get("AI_ENGINE_URL", "http://127.0.0.1:8092").rstrip("/")


def _priced(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in positions:
        value = float(row["amount"]) * float(row["price_usd"])
        if value > 0:
            rows.append({**row, "value": value})
    rows.sort(key=lambda item: item["value"], reverse=True)
    return rows


def contingencia(positions: list[dict[str, Any]]) -> dict[str, Any]:
    rows = _priced(positions)
    total = sum(row["value"] for row in rows)
    if total <= 0:
        return {
            "total_usd": 0.0,
            "priced_count": 0,
            "concentration": {
                "hhi": 0.0,
                "effective_assets": 0.0,
                "top_weight": 0.0,
                "top_symbol": None,
                "stable_weight": 0.0,
                "band": "vazia",
            },
        }
    weights = [row["value"] / total for row in rows]
    hhi = sum(weight * weight for weight in weights)
    if hhi >= 0.50:
        band = "alta"
    elif hhi >= 0.25:
        band = "moderada"
    else:
        band = "contida"
    stable = sum(row["value"] for row in rows if str(row["symbol"]).upper() in STABLES)
    return {
        "total_usd": round(total, 2),
        "priced_count": len(rows),
        "concentration": {
            "hhi": round(hhi, 4),
            "effective_assets": round(1.0 / hhi, 2) if hhi else 0.0,
            "top_weight": round(weights[0], 4),
            "top_symbol": rows[0]["symbol"],
            "stable_weight": round(stable / total, 4),
            "band": band,
        },
    }


def _qty(value: float) -> float:
    return float(f"{value:.8f}")


def propose(positions: list[dict[str, Any]], analysis: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _priced(positions)
    if not rows:
        return []
    top = rows[0]
    total = float(analysis.get("total_usd") or sum(row["value"] for row in rows))
    venda_amt = _qty(float(top["amount"]) * 0.10) or _qty(float(top["amount"]))
    concentration = analysis.get("concentration") or {}
    stable_weight = float(concentration.get("stable_weight") or 0.0)

    orders: list[dict[str, Any]] = [
        {
            "tipo": "venda",
            "simbolo": top["symbol"],
            "simbolo_par": "USDC",
            "rede": top["chain"],
            "quantidade": venda_amt,
            "preco_usd": float(top["price_usd"]),
            "gatilho_usd": None,
        }
    ]

    if stable_weight < 0.08 or len(rows) == 1:
        orders.append(
            {
                "tipo": "compra",
                "simbolo": "USDC",
                "simbolo_par": top["symbol"],
                "rede": top["chain"],
                "quantidade": _qty(max(total * 0.02, 1.0)),
                "preco_usd": 1.0,
                "gatilho_usd": None,
            }
        )
    else:
        small = next((row for row in reversed(rows) if row["symbol"] != top["symbol"]), rows[-1])
        orders.append(
            {
                "tipo": "compra",
                "simbolo": small["symbol"],
                "simbolo_par": "USDC",
                "rede": small["chain"],
                "quantidade": _qty(float(small["amount"]) * 0.05) or _qty(float(small["amount"])),
                "preco_usd": float(small["price_usd"]),
                "gatilho_usd": None,
            }
        )

    orders.append(
        {
            "tipo": "stop",
            "simbolo": top["symbol"],
            "simbolo_par": None,
            "rede": top["chain"],
            "quantidade": venda_amt,
            "preco_usd": float(top["price_usd"]),
            "gatilho_usd": _qty(float(top["price_usd"]) * 0.85),
        }
    )

    same_chain = [row for row in rows[1:] if row["chain"] == top["chain"]]
    partner = same_chain[0] if same_chain else (rows[1] if len(rows) > 1 else None)
    if partner is None:
        par_symbol = "USDC"
        pool_amt = venda_amt
        pool_chain = top["chain"]
    else:
        par_symbol = partner["symbol"]
        pool_chain = top["chain"]
        pool_amt = _qty(min(float(top["amount"]), float(partner["amount"])) * 0.02) or venda_amt
    orders.append(
        {
            "tipo": "pool",
            "simbolo": top["symbol"],
            "simbolo_par": par_symbol,
            "rede": pool_chain,
            "quantidade": pool_amt,
            "preco_usd": float(top["price_usd"]),
            "gatilho_usd": None,
        }
    )
    for order in orders:
        order["mint_solana"] = SOLANA_MINTS.get(order["simbolo"])
        order["token_base"] = BASE_TOKENS.get(order["simbolo"])
        order["token_par_base"] = BASE_TOKENS.get(order["simbolo_par"] or "")
    return orders


def mission_lines(orders: list[dict[str, Any]]) -> list[str]:
    lines = []
    for order in orders:
        gatilho = order.get("gatilho_usd")
        gatilho_txt = f", gatilho {gatilho:.2f}" if gatilho else ""
        par = f"/{order['simbolo_par']}" if order.get("simbolo_par") else ""
        lines.append(
            f"{order['tipo']} {order['simbolo']}{par} "
            f"quantidade {order['quantidade']:.8f} ao preço lançado {order['preco_usd']:.2f}{gatilho_txt}"
        )
    return lines


async def load_snapshot() -> dict[str, Any]:
    positions = list_positions()
    fonte_numeros = "motor"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(
                f"{engine_url()}/analyze",
                json={
                    "positions": [
                        {
                            "symbol": row["symbol"],
                            "name": row["name"],
                            "chain": row["chain"],
                            "amount": row["amount"],
                            "price_usd": row["price_usd"],
                        }
                        for row in positions
                    ]
                },
            )
            response.raise_for_status()
            analysis = response.json()
    except httpx.HTTPError:
        analysis = contingencia(positions)
        fonte_numeros = "contingencia"
    orders = propose(positions, analysis)
    concentration = analysis.get("concentration") or {}
    priced = _priced(positions)
    booked = sum(row["value"] for row in priced)
    carteira = [
        {"simbolo": str(row["symbol"]).upper(), "peso": round(row["value"] / booked, 4)}
        for row in priced
        if booked > 0
    ]
    return {
        "posicoes": len(positions),
        "total_usd": analysis.get("total_usd", 0.0),
        "fonte_numeros": fonte_numeros,
        "concentracao": concentration,
        "carteira": carteira,
        "ordens": orders,
        "missoes": mission_lines(orders),
    }
