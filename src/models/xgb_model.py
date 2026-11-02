"""
Walk-forward XGBoost for NBA win probability.

Expanded tabular features (40):
- Core: Elo, Net Rating, rest, B2B
- Form: L5/L10 win rate, margin L5, streaks
- Schedule density: games in last 7 days
- Off/Def proxies: rolling pts for/against
- Home/away splits
- Season progress, Elo momentum
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
    "h_form5",
    "a_form5",
    "form5_diff",
    "h_form10",
    "a_form10",
    "form10_diff",
    "h_margin5",
    "a_margin5",
    "margin5_diff",
    "h_streak",
    "a_streak",
    "h_games7d",
    "a_games7d",
    "density_diff",
    "h_off",
    "a_off",
    "h_def",
    "a_def",
    "off_diff",
    "def_edge",
    "h_home_wr",
    "a_away_wr",
    "season_progress",
    "elo_mom_h",
    "elo_mom_a",
    "elo_mom_diff",
]

DEFAULT_PARAMS = dict(
    objective="binary:logistic",
    eval_metric="logloss",
    max_depth=4,
    learning_rate=0.04,
    subsample=0.85,
    colsample_bytree=0.75,
    reg_lambda=3.0,
    reg_alpha=0.8,
    min_child_weight=25,
)


def train_xgb(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: Optional[np.ndarray] = None,
    y_val: Optional[np.ndarray] = None,
    params: Optional[dict] = None,
    num_boost_round: int = 400,
    early_stopping_rounds: int = 30,
) -> "xgb.Booster":
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


def predict_proba(model: "xgb.Booster", X: np.ndarray, shrink: float = 0.08) -> np.ndarray:
    d = xgb.DMatrix(X, feature_names=FEAT_NAMES)
    p = model.predict(d)
    p = (1.0 - shrink) * p + shrink * 0.5
    return np.clip(p, 0.02, 0.98)


def walk_forward_xgb(
    X: np.ndarray,
    y: np.ndarray,
    min_train: int = 600,
    block: int = 250,
) -> Tuple[np.ndarray, List]:
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
