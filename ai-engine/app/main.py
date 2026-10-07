from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field, field_validator

from app.engine import analyze
from app.quant.job import AVISO, start_scheduler
from app.quant.store import load_forecast


@asynccontextmanager
async def lifespan(_app: FastAPI):
    scheduler = start_scheduler()
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Lastro — motor de leitura", version="1.1.0", lifespan=lifespan)


class PositionIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=12)
    name: str = Field(default="", max_length=64)
    chain: str = Field(min_length=1, max_length=32)
    amount: float = Field(gt=0)
    price_usd: float = Field(ge=0)

    @field_validator("symbol")
    @classmethod
    def upper_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("chain")
    @classmethod
    def lower_chain(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("amount", "price_usd")
    @classmethod
    def finite(cls, value: float) -> float:
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("número inválido")
        return value


class AnalyzeIn(BaseModel):
    positions: list[PositionIn] = Field(default_factory=list)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ai-engine"}


@app.post("/analyze")
def analyze_route(body: AnalyzeIn) -> dict[str, Any]:
    payload = [item.model_dump() for item in body.positions]
    return analyze(payload)


@app.get("/forecasts")
def forecasts() -> dict[str, Any]:
    document = load_forecast()
    if document is None:
        return {
            "status": "vazio",
            "ativos": [],
            "aviso": AVISO,
            "mensagem": "O turno ocioso ainda não gravou uma previsão.",
        }
    return document


@app.post("/forecasts/run")
def forecasts_run() -> dict[str, Any]:
    from app.quant.job import run_forecast

    return run_forecast(force=False)
