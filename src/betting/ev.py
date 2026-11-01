"""
Expected Value and odds utilities.

Convert book odds → implied probabilities (de-vig),
compare to model fair probabilities, compute EV and edge.
"""

from __future__ import annotations

from typing import Tuple


def american_to_decimal(odds: float) -> float:
    if odds >= 100:
        return 1.0 + odds / 100.0
    if odds <= -100:
        return 1.0 + 100.0 / abs(odds)
    raise ValueError(f"Invalid American odds: {odds}")


def decimal_to_implied(dec: float) -> float:
    return 1.0 / dec


def american_to_implied(odds: float) -> float:
    return decimal_to_implied(american_to_decimal(odds))


def devig_two_way(odds_a: float, odds_b: float, method: str = "multiplicative") -> Tuple[float, float]:
    """
    Remove vig from a two-outcome market.
    Returns fair probabilities (sum to 1).
    """
    p_a = american_to_implied(odds_a)
    p_b = american_to_implied(odds_b)
    total = p_a + p_b
    if method == "multiplicative":
        return p_a / total, p_b / total
    # additive (simple)
    overround = total - 1.0
    return p_a - overround / 2, p_b - overround / 2


def expected_value(fair_prob: float, decimal_odds: float) -> float:
    """
    EV per unit stake.
    EV = fair_prob * (decimal_odds - 1) - (1 - fair_prob)
    """
    return fair_prob * (decimal_odds - 1.0) - (1.0 - fair_prob)


def edge(fair_prob: float, market_prob: float) -> float:
    """Absolute edge: fair - market."""
    return fair_prob - market_prob


def is_positive_ev(fair_prob: float, decimal_odds: float, min_ev: float = 0.02) -> bool:
    return expected_value(fair_prob, decimal_odds) >= min_ev
