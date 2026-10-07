import unittest

import numpy as np
import pandas as pd

from app.quant.features import build_matrix
from app.quant.model import TrainConfig, split_bounds, train_and_forecast


def _book() -> pd.DataFrame:
    rng = np.random.default_rng(3)
    n = 220
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    close = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.012, n)))
    ohlc = pd.DataFrame(
        {
            "date": dates,
            "open": close,
            "high": close * (1 + rng.uniform(0.001, 0.01, n)),
            "low": close * (1 - rng.uniform(0.001, 0.01, n)),
            "close": close,
        }
    )
    level = 100 * np.exp(np.cumsum(rng.normal(0.0, 0.004, n)))
    macro = pd.DataFrame(
        {
            "date": dates,
            "usd": level,
            "eur": level * 1.08,
            "brent": level * 0.7,
            "gold": level * 18,
        }
    )
    return build_matrix(ohlc, macro)


class ModelTests(unittest.TestCase):
    def test_split_is_the_first_eighty_percent(self) -> None:
        self.assertEqual(split_bounds(100), (80, 100))

    def test_network_emits_a_finite_plan(self) -> None:
        frame = _book()
        config = TrainConfig(
            hidden_sizes=(4,),
            learning_rates=(1e-2,),
            folds=2,
            max_epochs=4,
            patience=2,
            seed=7,
        )
        result = train_and_forecast(frame, config)
        labeled = len(frame) - 1
        self.assertEqual(result["ajuste"]["n_treino"], int(labeled * 0.8))
        self.assertEqual(result["ajuste"]["n_teste"], labeled - result["ajuste"]["n_treino"])
        self.assertGreaterEqual(result["ajuste"]["epocas"], 1)
        self.assertIn(result["direcao"], {"alta", "baixa", "lateral"})
        self.assertGreater(result["confianca"], 0)
        self.assertLessEqual(result["confianca"], 0.95)
        price = result["preco_referencia"]
        if result["direcao"] == "baixa":
            self.assertGreater(result["stop_loss"], price)
            self.assertLess(result["take_profit"], price)
        else:
            self.assertLess(result["stop_loss"], price)
            self.assertGreater(result["take_profit"], price)
        for key in ("preco_referencia", "stop_loss", "take_profit", "retorno_previsto"):
            self.assertTrue(np.isfinite(result[key]))


if __name__ == "__main__":
    unittest.main()
