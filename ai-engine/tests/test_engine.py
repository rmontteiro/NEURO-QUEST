import unittest

from app.engine import analyze


class AnalyzeTests(unittest.TestCase):
    def test_empty(self) -> None:
        result = analyze([])
        self.assertEqual(result["concentration"]["band"], "vazia")
        self.assertEqual(result["total_usd"], 0.0)

    def test_single_asset_is_high_concentration(self) -> None:
        result = analyze(
            [
                {
                    "symbol": "eth",
                    "name": "Ether",
                    "chain": "Ethereum",
                    "amount": 2,
                    "price_usd": 1000,
                }
            ]
        )
        self.assertEqual(result["concentration"]["band"], "alta")
        self.assertEqual(result["concentration"]["top_symbol"], "ETH")
        self.assertAlmostEqual(result["concentration"]["hhi"], 1.0)
        self.assertEqual(result["chains"][0]["chain"], "ethereum")
        self.assertAlmostEqual(result["total_usd"], 2000.0)

    def test_equal_basket_is_contained(self) -> None:
        positions = [
            {"symbol": f"A{i}", "name": f"Ativo {i}", "chain": "base" if i % 2 else "ethereum", "amount": 1, "price_usd": 100}
            for i in range(8)
        ]
        result = analyze(positions)
        self.assertEqual(result["concentration"]["band"], "contida")
        self.assertAlmostEqual(result["concentration"]["effective_assets"], 8.0, places=2)

    def test_unpriced_positions_are_excluded_from_weights(self) -> None:
        result = analyze(
            [
                {"symbol": "USDC", "name": "USD Coin", "chain": "ethereum", "amount": 100, "price_usd": 1},
                {"symbol": "AIR", "name": "Airdrop", "chain": "base", "amount": 10, "price_usd": 0},
            ]
        )
        self.assertEqual(result["unpriced_count"], 1)
        self.assertEqual(result["priced_count"], 1)
        self.assertAlmostEqual(result["concentration"]["stable_weight"], 1.0)


if __name__ == "__main__":
    unittest.main()
