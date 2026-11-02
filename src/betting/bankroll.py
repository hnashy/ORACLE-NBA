"""
Bankroll simulation with EV filter, fractional Kelly, and stop-loss rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .ev import expected_value, decimal_to_implied
from .kelly import fractional_kelly


@dataclass
class BetResult:
    pick: str
    decimal_odds: float
    stake: float
    won: bool
    ev: float
    bankroll_after: float


@dataclass
class SimConfig:
    bankroll0: float = 10_000.0
    min_ev: float = 0.03
    kelly_fraction: float = 0.25
    max_bet_pct: float = 0.015
    max_decimal_odds: float = 3.0
    min_model_prob: float = 0.45
    daily_stop_loss_pct: float = 0.05
    weekly_stop_loss_pct: float = 0.12
    monthly_stop_loss_pct: float = 0.20


@dataclass
class SimResult:
    n_bets: int = 0
    wins: int = 0
    final_bankroll: float = 0.0
    roi: float = 0.0
    max_drawdown: float = 0.0
    avg_odds: float = 0.0
    bets: List[BetResult] = field(default_factory=list)


def simulate(
    rows: List[dict],
    config: Optional[SimConfig] = None,
) -> SimResult:
    """
    rows: list of dicts with keys:
      pm (model P home), dh/da (decimal odds), hw (1 if home won)
    """
    cfg = config or SimConfig()
    br = cfg.bankroll0
    peak = br
    max_dd = 0.0
    bets: List[BetResult] = []
    odds_sum = 0.0

    for r in rows:
        pm = float(r["pm"])
        dh, da = float(r["dh"]), float(r["da"])
        hw = int(r["hw"])

        candidates = []
        ev_h = expected_value(pm, dh)
        ev_a = expected_value(1 - pm, da)
        if (
            ev_h >= cfg.min_ev
            and dh <= cfg.max_decimal_odds
            and pm >= cfg.min_model_prob
        ):
            candidates.append(("H", dh, pm, ev_h, hw == 1))
        if (
            ev_a >= cfg.min_ev
            and da <= cfg.max_decimal_odds
            and (1 - pm) >= cfg.min_model_prob
        ):
            candidates.append(("A", da, 1 - pm, ev_a, hw == 0))

        if not candidates:
            continue
        candidates.sort(key=lambda x: -x[3])
        pick, dec, p, e, won = candidates[0]

        f = fractional_kelly(p, dec, cfg.kelly_fraction, cfg.max_bet_pct)
        if f <= 0 or br <= 0:
            continue
        stake = br * f
        if won:
            br += stake * (dec - 1)
        else:
            br -= stake
        peak = max(peak, br)
        dd = (peak - br) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)

        bets.append(
            BetResult(
                pick=pick,
                decimal_odds=dec,
                stake=stake,
                won=won,
                ev=e,
                bankroll_after=br,
            )
        )
        odds_sum += dec

    n = len(bets)
    wins = sum(1 for b in bets if b.won)
    return SimResult(
        n_bets=n,
        wins=wins,
        final_bankroll=br,
        roi=(br - cfg.bankroll0) / cfg.bankroll0 if cfg.bankroll0 else 0.0,
        max_drawdown=max_dd,
        avg_odds=(odds_sum / n) if n else 0.0,
        bets=bets,
    )
