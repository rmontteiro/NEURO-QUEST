from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import httpx

from app.agents import PERSONAS, narrate
from app.council import BASE_TOKENS, SOLANA_MINTS, load_snapshot
from app.router_defi import (
    build_route,
    classificar_falha,
    ordem_limite,
    validar_ordem_publicada,
)
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


class RouteIn(BaseModel):
    pagador_solana: str | None = None
    pagador_ethereum: str | None = None
    blockhash: str | None = None


class PublicarIn(BaseModel):
    pagador: str = Field(min_length=42, max_length=42)
    assinatura: str = Field(min_length=10, max_length=200)
    ordem: dict[str, Any]


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


@router.post("/rota-missao")
async def rota_missao(body: RouteIn) -> dict[str, Any]:
    snapshot = await load_snapshot()
    try:
        return build_route(
            snapshot["ordens"],
            pagador_solana=body.pagador_solana,
            pagador_ethereum=body.pagador_ethereum,
            blockhash=body.blockhash,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=classificar_falha(str(exc))) from exc


@router.post("/rota-missao/publicar")
async def publicar_limite(body: PublicarIn) -> dict[str, Any]:
    snapshot = await load_snapshot()
    stop = next((order for order in snapshot["ordens"] if order["tipo"] == "stop"), None)
    if stop is None:
        raise HTTPException(status_code=422, detail="A missão não tem ordem de stop.")
    try:
        expected = ordem_limite(stop, body.pagador)
        validar_ordem_publicada(body.ordem, expected)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    payload = {
        **body.ordem,
        "signingScheme": "eip712",
        "signature": body.assinatura,
        "from": body.pagador,
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post("https://api.cow.fi/mainnet/api/v1/orders", json=payload)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=classificar_falha(str(exc))) from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=422, detail=classificar_falha(response.text))
    return {"order_id": response.text.strip('"'), "protocolo": "CoW Protocol"}
