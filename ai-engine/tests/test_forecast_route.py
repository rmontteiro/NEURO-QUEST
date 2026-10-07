import os
import tempfile
import unittest
from pathlib import Path

os.environ["QUANT_SCHEDULER"] = "0"

from app.main import app, forecasts
from app.quant.job import start_scheduler
from app.quant.store import save_forecast


class ForecastRouteTests(unittest.TestCase):
    def test_scheduler_stays_off_in_tests(self) -> None:
        self.assertIsNone(start_scheduler())
        paths = {getattr(route, "path", "") for route in app.routes}
        self.assertIn("/forecasts", paths)
        self.assertIn("/analyze", paths)

    def test_missing_file_is_the_empty_turn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["FORECAST_PATH"] = str(Path(tmp) / "forecasts.json")
            body = forecasts()
        self.assertEqual(body["status"], "vazio")
        self.assertEqual(body["ativos"], [])
        self.assertIn("turno ocioso", body["mensagem"])

    def test_saved_book_is_served_without_training(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["FORECAST_PATH"] = str(Path(tmp) / "forecasts.json")
            save_forecast(
                {
                    "status": "ok",
                    "ativos": [{"ativo": "ETHUSDT", "direcao": "alta", "confianca": 0.5}],
                    "aviso": "estudo",
                }
            )
            body = forecasts()
        self.assertEqual(body["ativos"][0]["ativo"], "ETHUSDT")


if __name__ == "__main__":
    unittest.main()
