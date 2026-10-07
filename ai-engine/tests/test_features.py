import unittest

import numpy as np
import pandas as pd

from app.quant.features import FEATURES, build_matrix, rsi, sma


def _walk(n: int = 120, seed: int = 4) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    close = 100 * np.exp(np.cumsum(rng.normal(0.0, 0.01, n)))
    high = close * 1.01
    low = close * 0.99
    ohlc = pd.DataFrame({"date": dates, "open": close, "high": high, "low": low, "close": close})
    level = 50 + np.cumsum(rng.normal(0.0, 0.2, n))
    macro = pd.DataFrame(
        {
            "date": dates,
            "usd": level + 100,
            "eur": level + 80,
            "brent": level + 60,
            "gold": np.full(n, 10.0),
        }
    )
    return ohlc, macro


class FeatureTests(unittest.TestCase):
    def test_sma_20_matches_the_first_window(self) -> None:
        close = pd.Series(np.arange(1, 41, dtype=float))
        self.assertAlmostEqual(float(sma(close, 20).iloc[19]), float(close.iloc[:20].mean()))

    def test_rsi_stays_inside_zero_and_hundred(self) -> None:
        close = pd.Series(_walk()[0]["close"])
        values = rsi(close).dropna()
        self.assertGreater(len(values), 10)
        self.assertTrue(((values >= 0) & (values <= 100)).all())

    def test_target_is_the_next_day_and_not_a_feature(self) -> None:
        ohlc, macro = _walk()
        frame = build_matrix(ohlc, macro)
        self.assertNotIn("alvo", FEATURES)
        self.assertGreater(len(frame), 20)
        self.assertTrue(pd.isna(frame["alvo"].iloc[-1]))
        for index in range(len(frame) - 1):
            expected = float(np.log(frame["close"].iloc[index + 1] / frame["close"].iloc[index]))
            self.assertAlmostEqual(float(frame["alvo"].iloc[index]), expected, places=8)

    def test_macro_holds_the_last_print_across_a_gap(self) -> None:
        ohlc, macro = _walk(n=80)
        gap = macro["date"].iloc[60]
        macro = macro.loc[macro["date"] != gap].reset_index(drop=True)
        frame = build_matrix(ohlc, macro)
        held = frame.loc[frame["date"] == gap]
        self.assertEqual(len(held), 1)
        self.assertTrue(np.isfinite(float(held["usd_chg"].iloc[0])))

    def test_macro_does_not_look_ahead(self) -> None:
        ohlc, macro = _walk()
        macro.loc[macro.index[-1], "gold"] = 1000.0
        frame = build_matrix(ohlc, macro)
        self.assertAlmostEqual(float(frame["gold_chg"].iloc[-2]), 0.0, places=8)
        self.assertGreater(abs(float(frame["gold_chg"].iloc[-1])), 1.0)


if __name__ == "__main__":
    unittest.main()
