import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["DATA_PATH"] = str(Path(self._tmp.name) / "lastro.db")
        os.environ["AI_ENGINE_URL"] = "http://127.0.0.1:9"
        from app import db, main

        db.DATA_PATH = Path(os.environ["DATA_PATH"])
        main.AI_ENGINE_URL = os.environ["AI_ENGINE_URL"]
        self._client = TestClient(main.app)
        self.client = self._client.__enter__()

    def tearDown(self) -> None:
        self._client.__exit__(None, None, None)
        self._tmp.cleanup()

    def test_seed_and_clear(self) -> None:
        listed = self.client.get("/positions")
        self.assertEqual(listed.status_code, 200)
        self.assertGreaterEqual(len(listed.json()["positions"]), 1)
        cleared = self.client.delete("/positions")
        self.assertEqual(cleared.status_code, 200)
        again = self.client.get("/positions")
        self.assertEqual(again.json()["positions"], [])
        self.assertEqual(again.json()["total_usd"], 0)

    def test_create_and_reject_bad_symbol(self) -> None:
        self.client.delete("/positions")
        created = self.client.post(
            "/positions",
            json={"symbol": "op", "name": "Optimism", "chain": "Optimism", "amount": 10, "price_usd": 1.5},
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["symbol"], "OP")
        self.assertEqual(created.json()["chain"], "optimism")
        rejected = self.client.post(
            "/positions",
            json={"symbol": "O P", "name": "Ruim", "chain": "base", "amount": 1, "price_usd": 1},
        )
        self.assertEqual(rejected.status_code, 422)

    def test_analysis_reports_unavailable_engine(self) -> None:
        response = self.client.post("/analysis")
        self.assertEqual(response.status_code, 503)

    def test_previsoes_reports_unavailable_engine(self) -> None:
        response = self.client.get("/previsoes")
        self.assertEqual(response.status_code, 503)
        self.assertIn("motor quantitativo", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
