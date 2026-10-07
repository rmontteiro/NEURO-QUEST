import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from app.quant.job import record_failure, run_forecast
from app.quant.model import TrainConfig


def _livros() -> dict:
    rng = np.random.default_rng(5)
    n = 220
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    close = 40 * np.exp(np.cumsum(rng.normal(0.0, 0.01, n)))
    ohlc = pd.DataFrame(
        {
            "date": dates,
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
        }
    )
    level = 20 + np.cumsum(rng.normal(0.0, 0.05, n))
    macro = pd.DataFrame(
        {"date": dates, "usd": level + 100, "eur": level + 90, "brent": level + 70, "gold": level + 200}
    )
    return {
        "ativos": [{"symbol": "BTCUSDT", "classe": "cripto", "fonte_preco": "binance", "ohlc": ohlc}],
        "macro": macro,
        "fonte_macro": "fred",
        "fonte_ouro": "binance:PAXGUSDT",
        "nota_ouro": "série LBMA encerrada",
    }


class JobTests(unittest.TestCase):
    def test_busy_host_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["FORECAST_PATH"] = str(Path(tmp) / "forecasts.json")
            with patch("app.quant.job.host_is_idle", return_value=False):
                result = run_forecast(livros=_livros())
            self.assertEqual(result["status"], "adiado")
            self.assertFalse(Path(os.environ["FORECAST_PATH"]).exists())

    def test_failure_is_stored_until_a_forecast_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["FORECAST_PATH"] = str(Path(tmp) / "forecasts.json")
            result = record_failure("Binance sem histórico")
            self.assertEqual(result["status"], "erro")
            self.assertEqual(result["ativos"], [])
            self.assertTrue(Path(os.environ["FORECAST_PATH"]).is_file())

    def test_forced_run_writes_the_book(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "forecasts.json"
            os.environ["FORECAST_PATH"] = str(path)
            config = TrainConfig(hidden_sizes=(4,), learning_rates=(1e-2,), folds=2, max_epochs=3, patience=2)
            with patch("app.quant.job.host_is_idle", return_value=False):
                result = run_forecast(force=True, livros=_livros(), config=config)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["ativos"][0]["ativo"], "BTCUSDT")
            self.assertEqual(result["validacao"], "TimeSeriesSplit")
            self.assertIn("Não é ordem", result["aviso"])
            self.assertTrue(path.is_file())


if __name__ == "__main__":
    unittest.main()
