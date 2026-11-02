"""
Expected Value and odds utilities.

Convert book odds → implied probabilities (de-vig),
compare to model fair probabilities, compute EV and edge.
"""

from __future__ import annotations

from typing import Tuple


def american_to_decimal(odds: float) -> float:
    if odds >= 0:
        return 1.0 + odds / 100.0
    return 1.0 + 100.0 / abs(odds)


def decimal_to_american(decimal: float) -> float:
    if decimal >= 2.0:
        return (decimal - 1.0) * 100.0
    return -100.0 / (decimal - 1.0)


def decimal_to_implied(dec: float) -> float:
    return 1.0 / dec


def american_to_implied(odds: float) -> float:
    return decimal_to_implied(american_to_decimal(odds))


def fair_prob_to_american(p: float) -> float:
    p = max(0.01, min(0.99, p))
    if p >= 0.5:
        return -100.0 * p / (1.0 - p)
    return 100.0 * (1.0 - p) / p


def devig_two_way(
    odds_a: float,
    odds_b: float,
    method: str = "multiplicative",
) -> Tuple[float, float]:
    """
    Remove vig from a two-outcome market (American odds).
    Returns fair probabilities (sum to 1).
    """
    p_a = american_to_implied(odds_a)
    p_b = american_to_implied(odds_b)
    total = p_a + p_b
    if method == "multiplicative":
        return p_a / total, p_b / total
    overround = total - 1.0
    return p_a - overround / 2, p_b - overround / 2


def apply_vig_to_fair(
    p_home_fair: float,
    vig: float = 0.045,
) -> Tuple[float, float, float, float]:
    """
    Build book decimal odds from fair home probability with multiplicative vig.
    Returns (dec_home, dec_away, implied_home, implied_away).
    """
    p_h = max(0.02, min(0.98, p_home_fair))
    p_a = 1.0 - p_h
    over = 1.0 + vig
    imp_h = p_h * over
    imp_a = p_a * over
    return 1.0 / imp_h, 1.0 / imp_a, imp_h, imp_a


def expected_value(fair_prob: float, decimal_odds: float) -> float:
    """EV per unit stake: p * decimal - 1."""
    return fair_prob * decimal_odds - 1.0


def edge(fair_prob: float, market_prob: float) -> float:
    """Model probability minus market implied probability."""
    return fair_prob - market_prob


def is_positive_ev(fair_prob: float, decimal_odds: float, min_ev: float = 0.02) -> bool:
    return expected_value(fair_prob, decimal_odds) >= min_ev
