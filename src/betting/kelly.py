"""
Kelly Criterion sizing with fractional Kelly and hard bankroll caps.
"""

from __future__ import annotations


def kelly_fraction(fair_prob: float, decimal_odds: float) -> float:
    """
    Full Kelly for a binary bet at decimal odds.
    f* = (p * b - q) / b  where b = decimal_odds - 1, q = 1 - p
    """
    if decimal_odds <= 1.0 or fair_prob <= 0.0 or fair_prob >= 1.0:
        return 0.0
    b = decimal_odds - 1.0
    q = 1.0 - fair_prob
    f = (fair_prob * b - q) / b
    return max(0.0, f)


def fractional_kelly(
    fair_prob: float,
    decimal_odds: float,
    fraction: float = 0.25,
    max_pct: float = 0.015,
) -> float:
    """
    Recommended stake as fraction of bankroll.
    - fraction: 0.25 = quarter Kelly (default, conservative)
    - max_pct: hard cap (default 1.5% of bankroll)
    """
    full = kelly_fraction(fair_prob, decimal_odds)
    sized = full * fraction
    return min(sized, max_pct)


def stake_amount(bankroll: float, fair_prob: float, decimal_odds: float,
                 fraction: float = 0.25, max_pct: float = 0.015) -> float:
    """Absolute stake in currency units."""
    return bankroll * fractional_kelly(fair_prob, decimal_odds, fraction, max_pct)
