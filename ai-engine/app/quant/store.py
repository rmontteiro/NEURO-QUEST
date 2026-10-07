"""Última previsão em disco. A leitura HTTP não treina."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def forecast_path() -> Path:
    return Path(os.environ.get("FORECAST_PATH", "data/forecasts.json"))


def load_forecast() -> dict[str, Any] | None:
    path = forecast_path()
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_forecast(document: dict[str, Any]) -> None:
    path = forecast_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
