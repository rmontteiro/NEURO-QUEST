"""Leitura quantitativa da carteira.

Não consulta preço de mercado e não chama um modelo de linguagem.
O cálculo usa apenas quantidade e preço lançados pelo operador.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

STABLE_SYMBOLS = frozenset({"USDC", "USDT", "DAI", "USDS", "USDE", "FDUSD", "PYUSD"})


def _band(hhi: float) -> str:
    if hhi >= 0.50:
        return "alta"
    if hhi >= 0.25:
        return "moderada"
    return "contida"


def analyze(positions: list[dict[str, Any]]) -> dict[str, Any]:
    if not positions:
        return {
            "total_usd": 0.0,
            "priced_count": 0,
            "unpriced_count": 0,
            "holdings": [],
            "chains": [],
            "concentration": {
                "hhi": 0.0,
                "effective_assets": 0.0,
                "top_weight": 0.0,
                "top_symbol": None,
                "stable_weight": 0.0,
                "band": "vazia",
            },
            "notes": ["Nenhuma posição lançada. A leitura começa quando a carteira tem quantidade e preço."],
        }

    frame = pd.DataFrame(positions)
    frame["symbol"] = frame["symbol"].astype(str).str.strip().str.upper()
    frame["chain"] = frame["chain"].astype(str).str.strip().str.lower()
    if "name" not in frame.columns:
        frame["name"] = frame["symbol"]
    frame["name"] = frame["name"].fillna(frame["symbol"]).astype(str)
    frame["amount"] = pd.to_numeric(frame["amount"], errors="coerce")
    frame["price_usd"] = pd.to_numeric(frame["price_usd"], errors="coerce")
    frame = frame.dropna(subset=["amount", "price_usd"])
    frame["value_usd"] = frame["amount"] * frame["price_usd"]

    unpriced = frame[frame["value_usd"] <= 0]
    priced = frame[frame["value_usd"] > 0].copy()
    total = float(priced["value_usd"].sum()) if not priced.empty else 0.0

    if priced.empty or total <= 0 or not math.isfinite(total):
        return {
            "total_usd": 0.0,
            "priced_count": 0,
            "unpriced_count": int(len(frame)),
            "holdings": [],
            "chains": [],
            "concentration": {
                "hhi": 0.0,
                "effective_assets": 0.0,
                "top_weight": 0.0,
                "top_symbol": None,
                "stable_weight": 0.0,
                "band": "vazia",
            },
            "notes": ["As posições estão sem preço. Lance um preço em USD para calcular peso e concentração."],
        }

    weights = priced["value_usd"].to_numpy(dtype=np.float64) / total
    priced["weight"] = weights
    hhi = float(np.square(weights).sum())
    effective = float(1.0 / hhi) if hhi > 0 else 0.0
    top_idx = int(np.argmax(weights))
    top_weight = float(weights[top_idx])
    top_symbol = str(priced.iloc[top_idx]["symbol"])

    stable_mask = priced["symbol"].astype(str).str.upper().isin(STABLE_SYMBOLS)
    stable_weight = float(priced.loc[stable_mask, "weight"].sum()) if stable_mask.any() else 0.0

    chains = (
        priced.groupby("chain", as_index=False)["value_usd"]
        .sum()
        .sort_values("value_usd", ascending=False)
    )
    chains["weight"] = chains["value_usd"] / total
    top_chain = str(chains.iloc[0]["chain"])
    top_chain_weight = float(chains.iloc[0]["weight"])

    holdings = (
        priced.sort_values("value_usd", ascending=False)[["symbol", "name", "chain", "value_usd", "weight"]]
        .assign(value_usd=lambda df: df["value_usd"].astype(float), weight=lambda df: df["weight"].astype(float))
        .to_dict(orient="records")
    )
    chain_rows = [
        {"chain": str(row.chain), "value_usd": float(row.value_usd), "weight": float(row.weight)}
        for row in chains.itertuples(index=False)
    ]

    notes: list[str] = []
    band = _band(hhi)
    if band == "alta":
        notes.append(
            f"{top_symbol} sozinho pesa {top_weight:.0%} da carteira. "
            "Um movimento nesse ativo redefine o resultado inteiro."
        )
    elif band == "moderada":
        notes.append(
            f"A concentração é moderada: o índice HHI está em {hhi:.2f} "
            f"e {top_symbol} é o maior peso ({top_weight:.0%})."
        )
    else:
        notes.append(
            f"Nenhum ativo domina a carteira. Os ativos efetivos, pelo inverso do HHI, são {effective:.1f}."
        )

    if top_chain_weight >= 0.80:
        notes.append(
            f"A rede {top_chain} concentra {top_chain_weight:.0%} do valor. "
            "Uma parada ou uma falha nessa rede atinge quase toda a posição."
        )
    elif top_chain_weight >= 0.60:
        notes.append(
            f"A rede {top_chain} ainda leva {top_chain_weight:.0%} do valor. "
            "Vale saber o que acontece com a carteira se essa rede ficar indisponível."
        )

    if stable_weight < 0.08:
        notes.append("Quase não há caixa estável. Uma saída em dólar exige vender o ativo volátil.")
    elif stable_weight > 0.70:
        notes.append("A maior parte do valor está em caixa estável. O risco de preço é baixo e a exposição também.")

    if len(unpriced) > 0:
        notes.append(
            f"{len(unpriced)} posição(ões) sem preço ficaram fora do peso. O total acima ignora esses lançamentos."
        )

    return {
        "total_usd": round(total, 2),
        "priced_count": int(len(priced)),
        "unpriced_count": int(len(unpriced)),
        "holdings": holdings,
        "chains": chain_rows,
        "concentration": {
            "hhi": round(hhi, 4),
            "effective_assets": round(effective, 2),
            "top_weight": round(top_weight, 4),
            "top_symbol": top_symbol,
            "stable_weight": round(stable_weight, 4),
            "band": band,
        },
        "notes": notes,
    }
