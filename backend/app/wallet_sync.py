"""Lê SOL e stablecoins na Solana e grava o saldo no lugar do lançamento manual."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx
from solders.pubkey import Pubkey

from app.db import list_positions, meta_get, meta_set, replace_chain

SOLANA_RPCS = (
    "https://api.mainnet-beta.solana.com",
    "https://solana-rpc.publicnode.com",
)
PRECO_URLS = (
    "https://api.binance.com/api/v3/ticker/price",
    "https://data-api.binance.vision/api/v3/ticker/price",
)

USDC_SOL = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT_SOL = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
CATALOGO = {
    USDC_SOL: ("USDC", "USD Coin"),
    USDT_SOL: ("USDT", "Tether"),
}
PARES = {"SOL": "SOLUSDT", "ETH": "ETHUSDT", "WBTC": "BTCUSDT", "AAVE": "AAVEUSDT"}
CHAVE_SOLANA = "carteira_solana"


def saldos_solana(lamports: int, contas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Monta as posições a partir do saldo nativo e das contas SPL conhecidas."""
    linhas: dict[str, Decimal] = {}
    sol = Decimal(lamports) / Decimal(10**9)
    if sol > 0:
        linhas["SOL"] = sol
    for conta in contas:
        info = (
            ((conta.get("account") or {}).get("data") or {}).get("parsed") or {}
        ).get("info") or {}
        mint = str(info.get("mint") or "")
        if mint not in CATALOGO:
            continue
        symbol = CATALOGO[mint][0]
        bruto = (info.get("tokenAmount") or {}).get("uiAmountString")
        if bruto in (None, ""):
            continue
        amount = Decimal(str(bruto))
        if amount <= 0:
            continue
        linhas[symbol] = linhas.get(symbol, Decimal(0)) + amount
    nomes = {"SOL": "Solana", **{item[0]: item[1] for item in CATALOGO.values()}}
    return [
        {"symbol": symbol, "name": nomes[symbol], "amount": float(amount)}
        for symbol, amount in linhas.items()
        if amount > 0
    ]


def _preco_anterior(symbol: str, chain: str) -> float | None:
    for row in list_positions():
        if str(row["symbol"]).upper() == symbol and str(row["chain"]).lower() == chain:
            if float(row["price_usd"]) > 0:
                return float(row["price_usd"])
    return None


async def _rpc(client: httpx.AsyncClient, method: str, params: list[Any]) -> Any:
    ultimo = "A rede Solana não respondeu."
    for url in SOLANA_RPCS:
        try:
            response = await client.post(url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        except httpx.HTTPError:
            continue
        if response.status_code >= 400:
            ultimo = "A rede Solana recusou a leitura."
            continue
        body = response.json()
        if body.get("error"):
            ultimo = "A rede Solana recusou a leitura."
            continue
        return body.get("result")
    raise ValueError(ultimo)


async def _preco_mercado(client: httpx.AsyncClient, symbol: str) -> float | None:
    if symbol in {"USDC", "USDT"}:
        return 1.0
    par = PARES.get(symbol)
    if par is None:
        return _preco_anterior(symbol, "solana")
    for url in PRECO_URLS:
        try:
            response = await client.get(url, params={"symbol": par})
        except httpx.HTTPError:
            continue
        if response.status_code != 200:
            continue
        raw = response.json().get("price")
        try:
            price = float(raw)
        except (TypeError, ValueError):
            continue
        if price > 0:
            return price
    return _preco_anterior(symbol, "solana")


async def ler_solana(pubkey: str) -> list[dict[str, Any]]:
    try:
        Pubkey.from_string(pubkey)
    except Exception as exc:
        raise ValueError("A chave Solana da Phantom não é válida.") from exc
    async with httpx.AsyncClient(timeout=20.0) as client:
        saldo = await _rpc(client, "getBalance", [pubkey, {"commitment": "confirmed"}])
        lamports = int((saldo or {}).get("value") or 0)
        contas: list[dict[str, Any]] = []
        for programa in (
            "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
            "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
        ):
            resposta = await _rpc(
                client,
                "getTokenAccountsByOwner",
                [pubkey, {"programId": programa}, {"encoding": "jsonParsed", "commitment": "confirmed"}],
            )
            contas.extend((resposta or {}).get("value") or [])
        linhas = saldos_solana(lamports, contas)
        for linha in linhas:
            preco = await _preco_mercado(client, linha["symbol"])
            if preco is None:
                raise ValueError(f"Sem preço de mercado para {linha['symbol']}. A mesa manteve o lançamento anterior.")
            linha["price_usd"] = preco
    return linhas


async def sincronizar_solana(pubkey: str | None) -> dict[str, Any]:
    chave = (pubkey or "").strip() or meta_get(CHAVE_SOLANA)
    if not chave:
        return {
            "atualizado": False,
            "solana": None,
            "aviso": "Ligue a Phantom uma vez. Depois a mesa relê SOL e USDC sozinha.",
        }
    linhas = await ler_solana(chave)
    meta_set(CHAVE_SOLANA, chave)
    replace_chain("solana", linhas)
    rows = [row for row in list_positions() if str(row["chain"]).lower() == "solana"]
    total = sum(row["amount"] * row["price_usd"] for row in list_positions())
    return {
        "atualizado": True,
        "solana": chave,
        "aviso": None,
        "lidas": [
            {"symbol": row["symbol"], "chain": row["chain"], "amount": row["amount"], "price_usd": row["price_usd"]}
            for row in rows
        ],
        "positions": list_positions(),
        "total_usd": round(total, 2),
    }
