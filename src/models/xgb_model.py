"""
Walk-forward XGBoost model for NBA win probability.

Tabular features: Elo diff, Net Rating, rest, B2B, games played, form.
Train only on past games; early stopping on a validation slice.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np

try:
    import xgboost as xgb
except ImportError as e:  # pragma: no cover
    raise ImportError("pip install xgboost") from e

FEAT_NAMES = [
    "elo_diff",
    "elo_home",
    "elo_away",
    "net_diff",
    "net_home",
    "net_away",
    "rest_diff",
    "h_rest",
    "a_rest",
    "h_b2b",
    "a_b2b",
    "h_games",
    "a_games",
    "elo_margin_pts",
    "form_h",
    "form_a",
]

DEFAULT_PARAMS = dict(
    objective="binary:logistic",
    eval_metric="logloss",
    max_depth=3,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    reg_lambda=2.0,
    reg_alpha=0.5,
    min_child_weight=20,
)


def train_xgb(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: Optional[np.ndarray] = None,
    y_val: Optional[np.ndarray] = None,
    params: Optional[dict] = None,
    num_boost_round: int = 300,
    early_stopping_rounds: int = 25,
) -> xgb.Booster:
    p = {**DEFAULT_PARAMS, **(params or {})}
    dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=FEAT_NAMES)
    evals = [(dtrain, "train")]
    if X_val is not None and y_val is not None and len(y_val) > 0:
        dval = xgb.DMatrix(X_val, label=y_val, feature_names=FEAT_NAMES)
        evals.append((dval, "val"))
    model = xgb.train(
        p,
        dtrain,
        num_boost_round=num_boost_round,
        evals=evals,
        early_stopping_rounds=early_stopping_rounds if X_val is not None else None,
        verbose_eval=False,
    )
    return model


def predict_proba(model: xgb.Booster, X: np.ndarray, shrink: float = 0.08) -> np.ndarray:
    """Predict P(home win) with mild shrink toward 0.5 for calibration."""
    d = xgb.DMatrix(X, feature_names=FEAT_NAMES)
    p = model.predict(d)
    p = (1.0 - shrink) * p + shrink * 0.5
    return np.clip(p, 0.02, 0.98)


def walk_forward_xgb(
    X: np.ndarray,
    y: np.ndarray,
    min_train: int = 600,
    block: int = 250,
) -> Tuple[np.ndarray, List[xgb.Booster]]:
    """
    Expanding-window walk-forward.
    Returns predictions aligned with X (nan before min_train) and list of models.
    """
    N = len(y)
    preds = np.full(N, np.nan)
    models = []
    for start in range(min_train, N, block):
        end = min(start + block, N)
        split = int(start * 0.85)
        model = train_xgb(X[:split], y[:split], X[split:start], y[split:start])
        models.append(model)
        preds[start:end] = predict_proba(model, X[start:end])
    return preds, models
