import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.wallet_sync import USDC_SOL, saldos_solana


class ParserTests(unittest.TestCase):
    def test_native_sol_and_usdc_are_kept(self) -> None:
        rows = saldos_solana(
            386_530_939,
            [
                {
                    "account": {
                        "data": {
                            "parsed": {
                                "info": {
                                    "mint": USDC_SOL,
                                    "tokenAmount": {"uiAmountString": "4.354782"},
                                }
                            }
                        }
                    }
                },
                {
                    "account": {
                        "data": {
                            "parsed": {
                                "info": {
                                    "mint": "MintDesconhecida111111111111111111111111111",
                                    "tokenAmount": {"uiAmountString": "999"},
                                }
                            }
                        }
                    }
                },
            ],
        )
        book = {row["symbol"]: row["amount"] for row in rows}
        self.assertAlmostEqual(book["SOL"], 0.386530939)
        self.assertAlmostEqual(book["USDC"], 4.354782)
        self.assertNotIn("MintDesconhecida111111111111111111111111111", book)

    def test_zero_balance_is_left_out(self) -> None:
        self.assertEqual(saldos_solana(0, []), [])


class SyncTests(unittest.TestCase):
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

    def test_sync_replaces_solana_and_keeps_other_chains(self) -> None:
        self.client.delete("/positions")
        self.client.post(
            "/positions",
            json={"symbol": "SOL", "name": "Solana", "chain": "solana", "amount": 9, "price_usd": 100},
        )
        self.client.post(
            "/positions",
            json={"symbol": "ETH", "name": "Ether", "chain": "ethereum", "amount": 1, "price_usd": 3000},
        )
        chave = "Fu2gwoYjDfTZTJ9kDPPcHNgcfWTkknPsGkaoyRijfVKP"
        lidas = [
            {"symbol": "SOL", "name": "Solana", "amount": 0.34787275, "price_usd": 113.0},
            {"symbol": "USDC", "name": "USD Coin", "amount": 4.354782, "price_usd": 1.0},
        ]
        with patch("app.wallet_sync.ler_solana", new=AsyncMock(return_value=lidas)):
            response = self.client.post("/carteira/sincronizar", json={"solana": chave})
            again = self.client.post("/carteira/sincronizar", json={})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["atualizado"])
        book = {(row["symbol"], row["chain"]): row["amount"] for row in body["positions"]}
        self.assertEqual(book[("SOL", "solana")], 0.34787275)
        self.assertEqual(book[("USDC", "solana")], 4.354782)
        self.assertEqual(book[("ETH", "ethereum")], 1)
        self.assertTrue(again.json()["atualizado"])

    def test_failed_read_keeps_the_book(self) -> None:
        self.client.delete("/positions")
        self.client.post(
            "/positions",
            json={"symbol": "SOL", "name": "Solana", "chain": "solana", "amount": 1.5, "price_usd": 100},
        )
        with patch("app.wallet_sync.ler_solana", new=AsyncMock(side_effect=ValueError("A rede Solana não respondeu."))):
            response = self.client.post(
                "/carteira/sincronizar",
                json={"solana": "Fu2gwoYjDfTZTJ9kDPPcHNgcfWTkknPsGkaoyRijfVKP"},
            )
        self.assertFalse(response.json()["atualizado"])
        listed = self.client.get("/positions").json()["positions"]
        self.assertEqual(listed[0]["amount"], 1.5)


if __name__ == "__main__":
    unittest.main()
