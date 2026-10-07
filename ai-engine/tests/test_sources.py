import unittest

import pandas as pd

from app.quant.sources import fred_csv_to_series, gold_source, klines_to_frame


class SourceTests(unittest.TestCase):
    def test_klines_become_daily_ohlc(self) -> None:
        frame = klines_to_frame(
            [[1_700_000_000_000, "100", "110", "90", "105", "1", 0, "0", 0, "0", "0", "0"]]
        )
        self.assertEqual(len(frame), 1)
        self.assertEqual(float(frame.iloc[0]["close"]), 105.0)
        self.assertEqual(float(frame.iloc[0]["low"]), 90.0)

    def test_fred_csv_drops_missing_dots(self) -> None:
        text = "observation_date,DTWEXBGS\n2024-01-02,120.1\n2024-01-03,.\n2024-01-04,120.4\n"
        series = fred_csv_to_series(text, "usd")
        self.assertEqual(len(series), 2)
        self.assertAlmostEqual(float(series.iloc[0]), 120.1)
        self.assertAlmostEqual(float(series.iloc[1]), 120.4)

    def test_stale_lbma_gold_falls_back(self) -> None:
        old = pd.Series([1800.0, 1810.0], index=pd.to_datetime(["2022-01-03", "2022-01-04"]))
        self.assertEqual(gold_source(old, pd.Timestamp("2026-10-07")), "binance")
        recent = pd.Series([2400.0], index=pd.to_datetime(["2026-10-01"]))
        self.assertEqual(gold_source(recent, pd.Timestamp("2026-10-07")), "fred")
        self.assertEqual(gold_source(pd.Series(dtype=float), pd.Timestamp("2026-10-07")), "binance")


if __name__ == "__main__":
    unittest.main()
