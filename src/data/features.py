"""
Feature engineering for ORACLE-NBA.

Builds:
- Adaptive Elo + Net Rating probabilities (calibrated)
- LSTM sequence tensors (last N games per team)
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

import numpy as np

K = 28
HFA = 100
BASE = 1500
ELO_HL = 120
MARGIN_CAP = 22
SIGMA = 11.8
B2B_PEN = 2.0
ELO_TO_PTS = 22.5
CAL_A = 0.85
NET_WEIGHT = 0.38
WINDOW = 12
SEQ_LEN = 10
FEATURE_DIM = 6


def decay(r: float, days: float, hl: float = ELO_HL) -> float:
    if not days or days <= 0:
        return r
    k = np.exp(-np.log(2) * days / hl)
    return float(r * k + BASE * (1 - k))


def elo_expect(rh: float, ra: float, hfa: float = HFA) -> float:
    return 1.0 / (1.0 + 10 ** (-((rh + hfa) - ra) / 400))


def margin_mult(gd: float) -> float:
    g = min(abs(gd), MARGIN_CAP)
    return float(np.log(max(g, 1) + 1) / np.log(2) * 0.7 + 0.6)


def normal_cdf(x: float) -> float:
    t = 1 / (1 + 0.2316419 * abs(x))
    d = 0.3989423 * np.exp(-x * x / 2)
    p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))))
    return float(1 - p if x > 0 else p)


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def calibrate(p: float) -> float:
    eps = 1e-6
    pp = clamp(p, eps, 1 - eps)
    logit = float(np.log(pp / (1 - pp)))
    return clamp(1 / (1 + np.exp(-(CAL_A * logit))), 0.02, 0.98)


def build_sequence(team: str, as_of_ts: float, hist: Dict, seq_len: int = SEQ_LEN) -> np.ndarray:
    rows = []
    for g in reversed(hist.get(team, [])):
        if g["ts"] >= as_of_ts:
            continue
        rows.append(
            [
                g["margin"],
                g["pts_for"],
                g["pts_against"],
                g["rest"],
                g["b2b"],
                1.0 if g["is_home"] else 0.0,
            ]
        )
        if len(rows) >= seq_len:
            break
    rows = list(reversed(rows))
    while len(rows) < seq_len:
        rows.insert(0, [0.0] * FEATURE_DIM)
    return np.asarray(rows[-seq_len:], dtype=np.float32)


def walk_features(games: List[dict], warmup: int = 400) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Walk-forward feature build (no look-ahead).
    Returns X (N, 2*SEQ_LEN, F), y home-win, elo_p calibrated P(home).
    """
    elo = defaultdict(lambda: {"r": BASE, "last": None, "games": 0, "net": 0.0, "recent": []})
    team_hist: Dict[str, list] = defaultdict(list)
    X_list, y_list, elo_p_list = [], [], []

    for i, g in enumerate(games):
        h, a = g["h"], g["a"]
        eh, ea = elo[h], elo[a]
        dh = (g["ts"] - eh["last"]) / 86400 if eh["last"] else 0
        da = (g["ts"] - ea["last"]) / 86400 if ea["last"] else 0
        rh, ra = decay(eh["r"], dh), decay(ea["r"], da)

        rest = 0.0
        if g.get("hB2B"):
            rest -= B2B_PEN * 0.55
        if g.get("aB2B"):
            rest += B2B_PEN * 0.55
        if g.get("hRest") is not None and g.get("aRest") is not None:
            rest += max(-2.8, min(2.8, ((g["hRest"] or 0) - (g["aRest"] or 0)) * 0.65))

        elo_m = ((rh + HFA) - ra) / ELO_TO_PTS + rest
        net_m = ((eh["net"] or 0) - (ea["net"] or 0)) * 0.92 + 1.1
        raw = (1 - NET_WEIGHT) * elo_m + NET_WEIGHT * net_m
        ph_elo = calibrate(normal_cdf(raw / SIGMA))

        seq_h = build_sequence(h, g["ts"], team_hist)
        seq_a = build_sequence(a, g["ts"], team_hist)
        X_seq = np.concatenate([seq_h, seq_a], axis=0)
        actual = 1.0 if g["gh"] > g["ga"] else 0.0

        if i >= warmup:
            X_list.append(X_seq)
            y_list.append(actual)
            elo_p_list.append(ph_elo)

        e = elo_expect(rh, ra)
        res = 1.0 if g["gh"] > g["ga"] else 0.0
        gd = g["gh"] - g["ga"]
        delta = K * margin_mult(gd) * (res - e)
        eh["r"] = rh + delta
        eh["last"] = g["ts"]
        eh["games"] += 1
        ea["r"] = ra - delta
        ea["last"] = g["ts"]
        ea["games"] += 1
        eh["recent"].append(gd)
        ea["recent"].append(-gd)
        if len(eh["recent"]) > WINDOW:
            eh["recent"].pop(0)
        if len(ea["recent"]) > WINDOW:
            ea["recent"].pop(0)
        eh["net"] = sum(eh["recent"]) / len(eh["recent"])
        ea["net"] = sum(ea["recent"]) / len(ea["recent"])

        h_rest = float(g["hRest"]) if g.get("hRest") is not None else 2.0
        a_rest = float(g["aRest"]) if g.get("aRest") is not None else 2.0
        team_hist[h].append(
            {
                "ts": g["ts"],
                "margin": gd,
                "pts_for": g["gh"],
                "pts_against": g["ga"],
                "rest": h_rest,
                "b2b": 1.0 if g.get("hB2B") else 0.0,
                "is_home": True,
            }
        )
        team_hist[a].append(
            {
                "ts": g["ts"],
                "margin": -gd,
                "pts_for": g["ga"],
                "pts_against": g["gh"],
                "rest": a_rest,
                "b2b": 1.0 if g.get("aB2B") else 0.0,
                "is_home": False,
            }
        )

    return np.stack(X_list), np.array(y_list, dtype=np.float32), np.array(elo_p_list, dtype=np.float32)
