"""Turno ocioso: treina uma vez e grava o JSON. Não dispara ordem."""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.quant.features import build_matrix
from app.quant.model import TrainConfig, train_and_forecast
from app.quant.store import load_forecast, save_forecast

AVISO = "Previsão de estudo para o pregão seguinte. Não é ordem de execução e não move saldo."
_LOCK = threading.Lock()


def host_is_idle() -> bool:
    try:
        load1 = float(Path("/proc/loadavg").read_text(encoding="utf-8").split()[0])
    except OSError:
        return True
    processors = os.cpu_count() or 1
    ratio = float(os.environ.get("QUANT_IDLE_LOAD_RATIO", "0.5"))
    return load1 <= ratio * processors


def _stamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def forecast_book(livros: dict[str, Any], config: TrainConfig | None = None) -> dict[str, Any]:
    ativos = []
    for item in livros["ativos"]:
        matrix = build_matrix(item["ohlc"], livros["macro"])
        forecast = train_and_forecast(matrix, config)
        ativos.append(
            {
                "ativo": item["symbol"],
                "classe": item["classe"],
                "fonte_preco": item["fonte_preco"],
                **forecast,
            }
        )
    return {
        "status": "ok",
        "gerado_em": _stamp(),
        "horizonte": "1d",
        "aviso": AVISO,
        "split": {"treino": 0.8, "teste": 0.2, "corte": "cronologico"},
        "validacao": "TimeSeriesSplit",
        "fonte_macro": livros.get("fonte_macro", "fred"),
        "fonte_ouro": livros.get("fonte_ouro", ""),
        "nota_ouro": livros.get("nota_ouro", ""),
        "series_macro": ["DTWEXBGS", "DEXUSEU", "DCOILBRENTEU"],
        "ativos": ativos,
        "erro": None,
    }


def record_failure(message: str) -> dict[str, Any]:
    previous = load_forecast()
    if previous and previous.get("status") == "ok" and previous.get("ativos"):
        return {
            "status": "erro",
            "erro": message,
            "preservado": True,
            "gerado_em": previous.get("gerado_em"),
            "aviso": previous.get("aviso", AVISO),
            "ativos": previous.get("ativos", []),
        }
    document = {
        "status": "erro",
        "erro": message,
        "gerado_em": _stamp(),
        "aviso": AVISO,
        "ativos": [],
    }
    save_forecast(document)
    return document


def run_forecast(
    *,
    force: bool = False,
    livros: dict[str, Any] | None = None,
    config: TrainConfig | None = None,
) -> dict[str, Any]:
    if not _LOCK.acquire(blocking=False):
        return {
            "status": "em_andamento",
            "motivo": "Já existe um treino neste processo.",
            "ativos": [],
        }
    try:
        return _run_forecast(force=force, livros=livros, config=config)
    finally:
        _LOCK.release()


def _run_forecast(
    *,
    force: bool,
    livros: dict[str, Any] | None,
    config: TrainConfig | None,
) -> dict[str, Any]:
    if not force and not host_is_idle():
        return {
            "status": "adiado",
            "motivo": "A carga do host passou do limiar ocioso. O treino espera o próximo turno.",
            "ativos": [],
        }
    if livros is None:
        from app.quant.sources import MarketDataError, load_market

        try:
            livros = load_market()
        except (MarketDataError, OSError, ValueError) as exc:
            return record_failure(str(exc))
    try:
        document = forecast_book(livros, config)
    except (ValueError, RuntimeError) as exc:
        return record_failure(str(exc))
    save_forecast(document)
    return document


def start_scheduler():
    if os.environ.get("QUANT_SCHEDULER", "1") == "0":
        return None
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    hour = int(os.environ.get("QUANT_CRON_HOUR", "4"))
    minute = int(os.environ.get("QUANT_CRON_MINUTE", "30"))
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        run_forecast,
        CronTrigger(hour=hour, minute=minute, timezone="UTC"),
        id="quant-turno",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=1800,
        replace_existing=True,
    )
    scheduler.start()
    return scheduler


def main() -> None:
    force = os.environ.get("QUANT_FORCE", "0") == "1"
    document = run_forecast(force=force)
    print(__import__("json").dumps(document, ensure_ascii=False))


if __name__ == "__main__":
    main()
