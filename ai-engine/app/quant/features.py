"""Indicadores técnicos cruzados com o macro do dia, sem olhar o futuro."""

from __future__ import annotations

import numpy as np
import pandas as pd

FEATURES: tuple[str, ...] = (
    "ret_1",
    "sma20_gap",
    "sma50_gap",
    "median_gap",
    "rsi",
    "macd_hist",
    "bb_pct",
    "bb_width",
    "atr_pct",
    "usd_chg",
    "eur_chg",
    "brent_chg",
    "gold_chg",
)

MACRO_COLUMNS: tuple[str, ...] = ("usd", "eur", "brent", "gold")


def sma(close: pd.Series, window: int) -> pd.Series:
    return close.rolling(window, min_periods=window).mean()


def rolling_median(close: pd.Series, window: int) -> pd.Series:
    return close.rolling(window, min_periods=window).median()


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    alpha = 1.0 / window
    avg_gain = gain.ewm(alpha=alpha, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=alpha, min_periods=window, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def macd_histogram(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.Series:
    line = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    return line - line.ewm(span=signal, adjust=False).mean()


def bollinger(close: pd.Series, window: int = 20, n_std: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = sma(close, window)
    spread = close.rolling(window, min_periods=window).std(ddof=0)
    upper = mid + n_std * spread
    lower = mid - n_std * spread
    width = (upper - lower) / mid.replace(0.0, np.nan)
    span = (upper - lower).replace(0.0, np.nan)
    percent = (close - lower) / span
    return percent, width, mid


def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    previous = close.shift(1)
    true_range = pd.concat(
        [(high - low).abs(), (high - previous).abs(), (low - previous).abs()],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1.0 / window, min_periods=window, adjust=False).mean()


def _log_change(series: pd.Series) -> pd.Series:
    positive = series.where(series > 0)
    return np.log(positive / positive.shift(1))


def build_matrix(ohlc: pd.DataFrame, macro: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por pregão. O alvo é o log-retorno do pregão seguinte.

    O macro entra com merge_asof para trás: o pregão de hoje só vê a última
    leitura macro já publicada. A última linha fica com alvo ausente e serve
    de inferência.
    """
    prices = ohlc.copy()
    prices["date"] = pd.to_datetime(prices["date"]).dt.tz_localize(None)
    prices = prices.sort_values("date").drop_duplicates("date", keep="last")
    context = macro.copy()
    context["date"] = pd.to_datetime(context["date"]).dt.tz_localize(None)
    context = context.sort_values("date").drop_duplicates("date", keep="last")
    missing = [name for name in MACRO_COLUMNS if name not in context.columns]
    if missing:
        raise ValueError(f"Macro sem as colunas {', '.join(missing)}.")

    # Cada série entra sozinha. Um buraco no dólar não apaga o ouro do mesmo dia,
    # e o pregão só herda a última leitura já publicada.
    frame = prices
    for name in MACRO_COLUMNS:
        column = context[["date", name]].dropna().sort_values("date")
        frame = pd.merge_asof(frame, column, on="date", direction="backward")
    close = frame["close"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    frame["ret_1"] = _log_change(close)
    frame["sma20_gap"] = close / sma(close, 20) - 1.0
    frame["sma50_gap"] = close / sma(close, 50) - 1.0
    frame["median_gap"] = close / rolling_median(close, 20) - 1.0
    frame["rsi"] = rsi(close) / 100.0
    frame["macd_hist"] = macd_histogram(close) / close.replace(0.0, np.nan)
    percent, width, _mid = bollinger(close)
    frame["bb_pct"] = percent
    frame["bb_width"] = width
    frame["atr_pct"] = atr(high, low, close) / close.replace(0.0, np.nan)
    frame["atr"] = atr(high, low, close)
    for name in MACRO_COLUMNS:
        frame[f"{name}_chg"] = _log_change(frame[name].astype(float))
    frame["alvo"] = _log_change(close).shift(-1)
    # ret_1 already is today's change; alvo must be tomorrow's, so recompute explicitly.
    frame["alvo"] = np.log(close.shift(-1) / close.where(close > 0))

    ready = frame[list(FEATURES)].notna().all(axis=1)
    frame = frame.loc[ready].reset_index(drop=True)
    if frame.empty:
        return frame
    last = frame.iloc[[-1]]
    body = frame.iloc[:-1].dropna(subset=["alvo"])
    return pd.concat([body, last], ignore_index=True)
