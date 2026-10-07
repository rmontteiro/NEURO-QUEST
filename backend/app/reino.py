from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agents import PERSONAS, narrate
from app.council import BASE_TOKENS, SOLANA_MINTS, load_snapshot
from app.txbuild import build_bundle

router = APIRouter()


class OrderIn(BaseModel):
    tipo: Literal["compra", "venda", "stop", "pool"]
    simbolo: str = Field(min_length=1, max_length=12)
    simbolo_par: str | None = Field(default=None, max_length=12)
    rede: str = Field(min_length=1, max_length=32)
    quantidade: float = Field(gt=0, le=1_000_000_000)
    preco_usd: float = Field(ge=0, le=100_000_000)
    gatilho_usd: float | None = Field(default=None, ge=0, le=100_000_000)


class TxIn(BaseModel):
    pagador_solana: str | None = None
    pagador_base: str | None = None
    blockhash: str | None = None
    ordens: list[OrderIn] | None = None


def _speech(persona: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    profile = PERSONAS[persona]
    spoken = narrate(persona, snapshot)
    return {
        "agente": profile["agente"],
        "cargo": profile["cargo"],
        "fala": spoken["fala"],
        "fonte": spoken["fonte"],
        "aviso": spoken["aviso"],
        "fonte_numeros": snapshot["fonte_numeros"],
        "dados": snapshot,
    }


def _normalize(order: OrderIn) -> dict[str, Any]:
    symbol = order.simbolo.strip().upper()
    pair = order.simbolo_par.strip().upper() if order.simbolo_par else None
    return {
        "tipo": order.tipo,
        "simbolo": symbol,
        "simbolo_par": pair,
        "rede": order.rede.strip().lower(),
        "quantidade": order.quantidade,
        "preco_usd": order.preco_usd,
        "gatilho_usd": order.gatilho_usd,
        "mint_solana": SOLANA_MINTS.get(symbol),
        "token_base": BASE_TOKENS.get(symbol),
        "token_par_base": BASE_TOKENS.get(pair or ""),
    }


@router.get("/status-reino")
async def status_reino() -> dict[str, Any]:
    snapshot = await load_snapshot()
    return await asyncio.to_thread(_speech, "ceo", snapshot)


@router.get("/missoes-ativas")
async def missoes_ativas() -> dict[str, Any]:
    snapshot = await load_snapshot()
    return await asyncio.to_thread(_speech, "cio", snapshot)


@router.get("/analise-risco")
async def analise_risco() -> dict[str, Any]:
    snapshot = await load_snapshot()
    return await asyncio.to_thread(_speech, "cco", snapshot)


@router.post("/transacao-nao-assinada")
async def transacao_nao_assinada(body: TxIn) -> dict[str, Any]:
    if body.ordens is None:
        snapshot = await load_snapshot()
        orders = snapshot["ordens"]
    else:
        orders = [_normalize(order) for order in body.ordens]
    try:
        return build_bundle(orders, body.pagador_solana, body.pagador_base, body.blockhash)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
