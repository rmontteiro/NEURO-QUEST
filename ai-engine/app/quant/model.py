"""MLP com retropropagação. O ajuste escolhe tamanho e taxa no treino cronológico."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.quant.features import FEATURES

LIMIAR_VOL = 0.25
ATR_STOP = 1.5
ATR_TAKE = 2.5


@dataclass(frozen=True)
class TrainConfig:
    hidden_sizes: tuple[int, ...] = (8, 16)
    learning_rates: tuple[float, ...] = (1e-3, 3e-3)
    folds: int = 3
    max_epochs: int = 30
    patience: int = 6
    seed: int = 7


def split_bounds(n_labeled: int) -> tuple[int, int]:
    """80% iniciais para treino, 20% finais para teste. Sem embaralhar."""
    if n_labeled < 40:
        raise ValueError("Histórico curto demais para o corte 80/20.")
    cut = int(n_labeled * 0.8)
    if cut < 30 or n_labeled - cut < 8:
        raise ValueError("Histórico curto demais para treino e teste.")
    return cut, n_labeled


def _torch():
    import torch

    torch.set_num_threads(1)
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass
    return torch


def _fit_mse(x_fit, y_fit, x_val, y_val, hidden: int, lr: float, epochs: int, seed: int) -> float:
    torch = _torch()
    import torch.nn.functional as functional

    scale = float(np.std(y_fit)) or 1.0
    torch.manual_seed(seed)
    model = torch.nn.Sequential(
        torch.nn.Linear(x_fit.shape[1], hidden),
        torch.nn.ReLU(),
        torch.nn.Linear(hidden, 1),
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    xt = torch.tensor(x_fit, dtype=torch.float32)
    yt = torch.tensor(y_fit / scale, dtype=torch.float32)
    xv = torch.tensor(x_val, dtype=torch.float32)
    yv = torch.tensor(y_val, dtype=torch.float32)
    model.train()
    for _ in range(epochs):
        optimizer.zero_grad()
        loss = functional.mse_loss(model(xt).squeeze(-1), yt)
        loss.backward()
        optimizer.step()
    model.eval()
    with torch.no_grad():
        predicted = model(xv).squeeze(-1).cpu().numpy() * scale
    return float(np.mean((predicted - y_val) ** 2))


def _train_final(x_fit, y_fit, x_watch, y_watch, hidden: int, lr: float, config: TrainConfig):
    torch = _torch()
    import torch.nn.functional as functional

    scale = float(np.std(y_fit)) or 1.0
    torch.manual_seed(config.seed)
    model = torch.nn.Sequential(
        torch.nn.Linear(x_fit.shape[1], hidden),
        torch.nn.ReLU(),
        torch.nn.Linear(hidden, 1),
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, factor=0.5, patience=2)
    xt = torch.tensor(x_fit, dtype=torch.float32)
    yt = torch.tensor(y_fit / scale, dtype=torch.float32)
    xw = torch.tensor(x_watch, dtype=torch.float32)
    yw = torch.tensor(y_watch / scale, dtype=torch.float32)
    best_state = {key: value.detach().clone() for key, value in model.state_dict().items()}
    best_val = float("inf")
    wait = 0
    epochs_ran = 0
    for epoch in range(config.max_epochs):
        model.train()
        optimizer.zero_grad()
        loss = functional.mse_loss(model(xt).squeeze(-1), yt)
        loss.backward()
        optimizer.step()
        model.eval()
        with torch.no_grad():
            watched = float(functional.mse_loss(model(xw).squeeze(-1), yw).item())
        scheduler.step(watched)
        epochs_ran = epoch + 1
        if watched < best_val - 1e-8:
            best_val = watched
            best_state = {key: value.detach().clone() for key, value in model.state_dict().items()}
            wait = 0
        else:
            wait += 1
            if wait >= config.patience:
                break
    model.load_state_dict(best_state)
    model.eval()
    return model, epochs_ran, scale


def _predict(model, rows: np.ndarray) -> np.ndarray:
    torch = _torch()
    with torch.no_grad():
        values = model(torch.tensor(rows, dtype=torch.float32)).squeeze(-1).cpu().numpy()
    return np.atleast_1d(values).astype(float)


def _levels(price: float, atr_value: float, direction: str) -> tuple[float, float]:
    atr_value = float(atr_value) if np.isfinite(atr_value) and atr_value > 0 else price * 0.01
    if direction == "alta":
        stop = price - max(atr_value * ATR_STOP, price * 0.005)
        take = price + max(atr_value * ATR_TAKE, price * 0.008)
    elif direction == "baixa":
        stop = price + max(atr_value * ATR_STOP, price * 0.005)
        take = price - max(atr_value * ATR_TAKE, price * 0.008)
    else:
        band = max(atr_value, price * 0.005)
        stop = price - band
        take = price + band
    return round(max(stop, price * 0.01), 8), round(max(take, price * 0.01), 8)


def train_and_forecast(frame: pd.DataFrame, config: TrainConfig | None = None) -> dict:
    """Treina no primeiro 80% e mede no 20% seguinte. A última linha é o pregão vivo."""
    chosen = config or TrainConfig()
    if frame.empty or frame["alvo"].iloc[:-1].isna().any():
        raise ValueError("Matriz sem alvo utilizável.")
    labeled = frame.iloc[:-1].reset_index(drop=True)
    live = frame.iloc[-1]
    cut, total = split_bounds(len(labeled))
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.preprocessing import StandardScaler

    values = labeled.loc[:, list(FEATURES)].to_numpy(dtype=float)
    target = labeled["alvo"].to_numpy(dtype=float)
    scaler = StandardScaler()
    train_x = scaler.fit_transform(values[:cut])
    train_y = target[:cut]
    folds = min(chosen.folds, max(2, len(train_x) // 30))
    splitter = TimeSeriesSplit(n_splits=folds)
    search: list[dict[str, float | int]] = []
    best: tuple[float, int, float] | None = None
    cv_epochs = max(3, chosen.max_epochs // 2)
    for hidden in chosen.hidden_sizes:
        for lr in chosen.learning_rates:
            scores: list[float] = []
            for train_idx, val_idx in splitter.split(train_x):
                if train_idx.max() >= cut:
                    raise RuntimeError("A validação cruzada saiu da janela de treino.")
                score = _fit_mse(
                    train_x[train_idx],
                    train_y[train_idx],
                    train_x[val_idx],
                    train_y[val_idx],
                    hidden,
                    lr,
                    cv_epochs,
                    chosen.seed,
                )
                scores.append(score)
            mean_score = float(np.mean(scores))
            search.append({"hidden": hidden, "lr": lr, "mse_cv": round(mean_score, 8)})
            if best is None or mean_score < best[0]:
                best = (mean_score, hidden, lr)
    assert best is not None
    _mse, hidden, lr = best
    watch = max(8, int(len(train_x) * 0.15))
    model, epochs_ran, scale = _train_final(
        train_x[:-watch],
        train_y[:-watch],
        train_x[-watch:],
        train_y[-watch:],
        hidden,
        lr,
        chosen,
    )
    test_x = scaler.transform(values[cut:])
    test_pred = _predict(model, test_x) * scale
    test_y = target[cut:]
    mask = test_y != 0
    if mask.any():
        accuracy = float(np.mean(np.sign(test_pred[mask]) == np.sign(test_y[mask])))
    else:
        accuracy = 0.5
    mse = float(np.mean((test_pred - test_y) ** 2))
    live_x = scaler.transform(frame.loc[[frame.index[-1]], list(FEATURES)].to_numpy(dtype=float))
    predicted = float(_predict(model, live_x)[0]) * scale
    vol = float(np.std(target[-20:])) if len(target) >= 5 else float(np.std(target))
    vol = max(vol, 1e-6)
    if abs(predicted) < LIMIAR_VOL * vol:
        direction = "lateral"
    elif predicted > 0:
        direction = "alta"
    else:
        direction = "baixa"
    magnitude = min(1.0, abs(predicted) / vol)
    # A confiança nasce da taxa de acerto do sinal no teste, não do tamanho cru da saída.
    skill = float(np.clip(accuracy, 0.05, 0.95))
    if direction == "lateral":
        confidence = skill * (1.0 - 0.35 * magnitude)
    else:
        confidence = skill * (0.65 + 0.35 * magnitude)
    confidence = float(np.clip(confidence, 0.05, 0.95))
    price = float(live["close"])
    stop, take = _levels(price, float(live["atr"]), direction)
    if not all(np.isfinite(number) for number in (predicted, confidence, price, stop, take, mse)):
        raise ValueError("A rede devolveu um número inválido.")
    return {
        "direcao": direction,
        "confianca": round(confidence, 4),
        "preco_referencia": round(price, 8),
        "stop_loss": stop,
        "take_profit": take,
        "retorno_previsto": round(predicted, 8),
        "horizonte": "1d",
        "modelo": "mlp-backprop",
        "ajuste": {
            "hidden": hidden,
            "lr": lr,
            "epocas": epochs_ran,
            "folds": folds,
            "mse_cv": round(best[0], 8),
            "mse_teste": round(mse, 8),
            "acuracia_sinal_teste": round(accuracy, 4),
            "n_treino": cut,
            "n_teste": total - cut,
            "busca": search,
        },
    }
