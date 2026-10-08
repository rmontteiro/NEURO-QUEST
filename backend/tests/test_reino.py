import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from solders.keypair import Keypair


class ReinoTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["DATA_PATH"] = str(Path(self._tmp.name) / "lastro.db")
        os.environ["AI_ENGINE_URL"] = "http://127.0.0.1:9"
        os.environ["GEMINI_API_KEY"] = ""
        os.environ.pop("GOOGLE_API_KEY", None)
        from app import db, main

        db.DATA_PATH = Path(os.environ["DATA_PATH"])
        self._client = TestClient(main.app)
        self.client = self._client.__enter__()

    def tearDown(self) -> None:
        self._client.__exit__(None, None, None)
        self._tmp.cleanup()

    def test_three_personas_without_gemini(self) -> None:
        ceo = self.client.get("/status-reino")
        cio = self.client.get("/missoes-ativas")
        cco = self.client.get("/analise-risco")
        self.assertEqual(ceo.status_code, 200)
        self.assertEqual(cio.status_code, 200)
        self.assertEqual(cco.status_code, 200)
        self.assertIn("carteira lançada", ceo.json()["fala"])
        self.assertIn("venda ETH", cio.json()["fala"])
        self.assertIn("HHI", cco.json()["fala"])
        for response in (ceo, cio, cco):
            body = response.json()
            self.assertEqual(body["fonte"], "cronica-local")
            self.assertEqual(body["fonte_numeros"], "contingencia")
            self.assertEqual(
                [order["tipo"] for order in body["dados"]["ordens"]],
                ["venda", "compra", "stop", "pool"],
            )
            self.assertGreaterEqual(len(body["dados"]["carteira"]), 1)
            self.assertIn("peso", body["dados"]["carteira"][0])

    def test_unsigned_bundle_route(self) -> None:
        response = self.client.post(
            "/transacao-nao-assinada",
            json={
                "pagador_solana": str(Keypair().pubkey()),
                "pagador_base": "0x0000000000000000000000000000000000000001",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertFalse(body["move_tokens"])
        self.assertIsNotNone(body["solana"]["serialized_base64"])
        self.assertEqual(body["base"]["transacao"]["chainId"], "0x2105")

    def test_rejects_a_bundle_without_payer(self) -> None:
        response = self.client.post("/transacao-nao-assinada", json={})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
