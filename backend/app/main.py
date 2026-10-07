from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.db import clear_positions, delete_position, init_db, insert_position, list_positions
from app.reino import router as reino_router

AI_ENGINE_URL = os.environ.get("AI_ENGINE_URL", "http://127.0.0.1:8092").rstrip("/")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Neuro-Quest Capital", version="1.1.0", lifespan=lifespan)
app.include_router(reino_router)


class PositionIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=12)
    name: str = Field(min_length=1, max_length=64)
    chain: str = Field(min_length=1, max_length=32)
    amount: float = Field(gt=0, le=1_000_000_000)
    price_usd: float = Field(ge=0, le=100_000_000)

    @field_validator("symbol")
    @classmethod
    def symbol_ok(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned.isalnum():
            raise ValueError("use apenas letras e números no símbolo")
        return cleaned

    @field_validator("name", "chain")
    @classmethod
    def strip_text(cls, value: str) -> str:
        cleaned = " ".join(value.strip().split())
        if not cleaned:
            raise ValueError("campo vazio")
        return cleaned

    @field_validator("chain")
    @classmethod
    def chain_lower(cls, value: str) -> str:
        return value.lower()

    @field_validator("amount", "price_usd")
    @classmethod
    def finite(cls, value: float) -> float:
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("número inválido")
        return value


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "backend"}


@app.get("/positions")
def positions() -> dict[str, Any]:
    rows = list_positions()
    total = sum(row["amount"] * row["price_usd"] for row in rows)
    return {"positions": rows, "total_usd": round(total, 2)}


@app.post("/positions", status_code=201)
def create_position(body: PositionIn) -> dict[str, Any]:
    return insert_position(body.symbol, body.name, body.chain, body.amount, body.price_usd)


@app.delete("/positions/{position_id}")
def remove_position(position_id: str) -> dict[str, bool]:
    if not delete_position(position_id):
        raise HTTPException(status_code=404, detail="Posição não encontrada.")
    return {"deleted": True}


@app.delete("/positions")
def remove_all() -> dict[str, int]:
    return {"deleted": clear_positions()}


@app.post("/analysis")
def analysis() -> dict[str, Any]:
    rows = list_positions()
    payload = [
        {
            "symbol": row["symbol"],
            "name": row["name"],
            "chain": row["chain"],
            "amount": row["amount"],
            "price_usd": row["price_usd"],
        }
        for row in rows
    ]
    try:
        with httpx.Client(timeout=8.0) as client:
            response = client.post(f"{AI_ENGINE_URL}/analyze", json={"positions": payload})
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail="O motor de leitura não respondeu. A lista da carteira continua disponível.",
        ) from exc
    return response.json()


@app.get("/previsoes")
def previsoes() -> dict[str, Any]:
    engine = os.environ.get("AI_ENGINE_URL", "http://127.0.0.1:8092").rstrip("/")
    try:
        with httpx.Client(timeout=8.0) as client:
            response = client.get(f"{engine}/forecasts")
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail="O motor quantitativo não respondeu. A mesa segue sem previsão nova.",
        ) from exc
    return response.json()
