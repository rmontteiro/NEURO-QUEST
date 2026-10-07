"""Histórico: Binance para cripto e ouro tokenizado; FRED para macro e o Nasdaq."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from io import StringIO
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

BINANCE_HOSTS: tuple[str, ...] = (
    "https://api.binance.com",
    "https://data-api.binance.vision",
)
CRYPTO: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
FRED_MACRO: dict[str, str] = {
    "usd": "DTWEXBGS",
    "eur": "DEXUSEU",
    "brent": "DCOILBRENTEU",
}
FRED_GOLD = "GOLDAMGBD228NLBM"
FRED_EQUITY = "NASDAQCOM"
GOLD_BINANCE = "PAXGUSDT"
GOLD_NOTE = (
    "A série LBMA GOLDAMGBD228NLBM saiu do FRED em janeiro de 2022. "
    "O ouro entra pelo PAXGUSDT da Binance."
)
HISTORY_DAYS = 730
USER_AGENT = "lastro-quant/1.0"


class MarketDataError(RuntimeError):
    pass


def klines_to_frame(rows: list[list[Any]]) -> pd.DataFrame:
    records = []
    for row in rows:
        records.append(
            {
                "date": pd.to_datetime(int(row[0]), unit="ms"),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
            }
        )
    frame = pd.DataFrame.from_records(records)
    if frame.empty:
        return frame
    return frame.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)


def fred_csv_to_series(text: str, name: str) -> pd.Series:
    frame = pd.read_csv(StringIO(text))
    if frame.shape[1] < 2:
        raise MarketDataError(f"CSV do FRED sem valor para {name}.")
    dates = pd.to_datetime(frame.iloc[:, 0], errors="coerce")
    values = pd.to_numeric(frame.iloc[:, 1], errors="coerce")
    series = pd.Series(values.to_numpy(), index=dates, name=name).dropna()
    series = series[series.index.notna()]
    return series.sort_index()


def fred_json_to_series(payload: dict[str, Any], name: str) -> pd.Series:
    rows = payload.get("observations") or []
    dates = []
    values = []
    for row in rows:
        dates.append(pd.to_datetime(row.get("date"), errors="coerce"))
        values.append(pd.to_numeric(row.get("value"), errors="coerce"))
    series = pd.Series(values, index=dates, name=name).dropna()
    series = series[series.index.notna()]
    return series.sort_index()


def gold_source(fred_gold: pd.Series | None, asof: pd.Timestamp, stale_days: int = 30) -> str:
    """Devolve 'fred' só quando a série oficial tem leitura recente."""
    if fred_gold is None or fred_gold.dropna().empty:
        return "binance"
    last = pd.Timestamp(fred_gold.dropna().index.max())
    if last < pd.Timestamp(asof) - pd.Timedelta(days=stale_days):
        return "binance"
    return "fred"


def _get(url: str, timeout: float = 20.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/csv"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise MarketDataError(f"HTTP {exc.code} em {url}") from exc
    except urllib.error.URLError as exc:
        raise MarketDataError(f"Sem resposta de {url}") from exc


def fetch_klines(symbol: str, start: datetime) -> pd.DataFrame:
    start_ms = int(start.timestamp() * 1000)
    query = f"/api/v3/klines?symbol={symbol}&interval=1d&startTime={start_ms}&limit=1000"
    errors: list[str] = []
    for host in BINANCE_HOSTS:
        try:
            payload = json.loads(_get(host + query))
        except (MarketDataError, json.JSONDecodeError) as exc:
            errors.append(str(exc))
            continue
        frame = klines_to_frame(payload if isinstance(payload, list) else [])
        if not frame.empty:
            return frame
        errors.append(f"{host} devolveu klines vazias para {symbol}")
    raise MarketDataError(f"Binance sem histórico de {symbol}: {'; '.join(errors)}")


def fetch_fred(series_id: str, start: datetime) -> pd.Series:
    start_day = start.date().isoformat()
    api_key = os.environ.get("FRED_API_KEY", "").strip()
    if api_key:
        url = (
            "https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={series_id}&api_key={api_key}&file_type=json"
            f"&observation_start={start_day}"
        )
        try:
            series = fred_json_to_series(json.loads(_get(url)), series_id)
            if not series.empty:
                return series
        except (MarketDataError, json.JSONDecodeError):
            pass
    csv_url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    try:
        text = _get(csv_url).decode("utf-8", errors="replace")
        series = fred_csv_to_series(text, series_id)
    except MarketDataError as exc:
        raise MarketDataError(f"FRED sem a série {series_id}.") from exc
    series = series[series.index >= pd.Timestamp(start_day)]
    if series.empty:
        raise MarketDataError(f"FRED sem observações recentes de {series_id}.")
    return series


def _close_frame(series: pd.Series) -> pd.DataFrame:
    values = series.dropna().astype(float)
    values = values[values > 0]
    return pd.DataFrame(
        {
            "date": values.index,
            "open": values.to_numpy(),
            "high": values.to_numpy(),
            "low": values.to_numpy(),
            "close": values.to_numpy(),
        }
    )


def _macro_frame(columns: dict[str, pd.Series]) -> pd.DataFrame:
    frame = pd.DataFrame(columns).sort_index()
    frame.index.name = "date"
    frame = frame.reset_index()
    return frame


def load_market(now: datetime | None = None) -> dict[str, Any]:
    clock = now or datetime.now(timezone.utc)
    start = clock - timedelta(days=HISTORY_DAYS)
    ativos: list[dict[str, Any]] = []
    for symbol in CRYPTO:
        ativos.append(
            {
                "symbol": symbol,
                "classe": "cripto",
                "fonte_preco": "binance",
                "ohlc": fetch_klines(symbol, start),
            }
        )
    equity = fetch_fred(FRED_EQUITY, start)
    ativos.append(
        {
            "symbol": FRED_EQUITY,
            "classe": "indice_acao",
            "fonte_preco": "fred",
            "ohlc": _close_frame(equity),
        }
    )
    columns = {name: fetch_fred(series_id, start) for name, series_id in FRED_MACRO.items()}
    try:
        fred_gold = fetch_fred(FRED_GOLD, start - timedelta(days=3650))
    except MarketDataError:
        fred_gold = pd.Series(dtype=float)
    asof = pd.Timestamp(clock.date())
    source = gold_source(fred_gold, asof)
    note = ""
    if source == "fred":
        columns["gold"] = fred_gold
        fonte_ouro = f"fred:{FRED_GOLD}"
    else:
        paxg = fetch_klines(GOLD_BINANCE, start).set_index("date")["close"]
        paxg.name = "gold"
        columns["gold"] = paxg
        fonte_ouro = f"binance:{GOLD_BINANCE}"
        note = GOLD_NOTE
    return {
        "ativos": ativos,
        "macro": _macro_frame(columns),
        "fonte_ouro": fonte_ouro,
        "nota_ouro": note,
        "fonte_macro": "fred",
    }
