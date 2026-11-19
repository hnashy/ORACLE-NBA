#!/usr/bin/env python3
"""
ORACLE-NBA Injury Impact Module (free sources only)
====================================================
Fetches current NBA injuries from ESPN public site API (no key).
Applies temporary Elo penalties for Out/Doubtful stars.
Falls back to raw Elo if fetch fails.

Penalties (initial, tunable):
  Tier-1 star Out/Doubtful: -20 Elo
  Tier-2 role star Out/Doubtful: -5 Elo
  Questionable / Day-To-Day: ignored for v1 (too noisy)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    requests = None  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = ROOT / "data" / "injuries" / "latest_injuries.json"
STAR_PATH = ROOT / "config" / "star_tiers.json"

ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
USER_AGENT = "ORACLE-NBA-injury-adjuster/1.0 (paper research; contact: local)"

PENALTY_TIER1 = 20.0
PENALTY_TIER2 = 5.0
ACTIVE_STATUSES = {"out", "doubtful"}

TEAM_ALIASES = {
    "LA Clippers": "Los Angeles Clippers",
    "LA Lakers": "Los Angeles Lakers",
    "NY Knicks": "New York Knicks",
}


def _norm_team(name: str) -> str:
    n = (name or "").strip()
    return TEAM_ALIASES.get(n, n)


def load_star_tiers() -> tuple[set[str], set[str]]:
    if STAR_PATH.exists():
        data = json.loads(STAR_PATH.read_text())
        t1 = {str(x).strip() for x in data.get("tier1", [])}
        t2 = {str(x).strip() for x in data.get("tier2", [])}
        return t1, t2
    return set(), set()


def fetch_espn_injuries() -> dict[str, list[dict[str, Any]]]:
    if requests is None:
        raise RuntimeError("requests not installed")
    r = requests.get(
        ESPN_URL,
        timeout=25,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    r.raise_for_status()
    payload = r.json()
    out: dict[str, list[dict[str, Any]]] = {}
    for team_block in payload.get("injuries") or []:
        team = _norm_team(team_block.get("displayName") or "")
        rows = []
        for inj in team_block.get("injuries") or []:
            ath = inj.get("athlete") or {}
            player = ath.get("displayName") or f"{ath.get('firstName','')} {ath.get('lastName','')}".strip()
            status = (inj.get("status") or "").strip()
            rows.append(
                {
                    "player": player,
                    "status": status,
                    "status_norm": status.lower().replace(" ", "-"),
                    "short_comment": inj.get("shortComment") or "",
                    "date": inj.get("date") or "",
                }
            )
        if team:
            out[team] = rows
    return out


def save_cache(by_team: dict[str, list[dict[str, Any]]]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": ESPN_URL,
        "teams": by_team,
    }
    CACHE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False))


def load_cache() -> dict[str, list[dict[str, Any]]] | None:
    if not CACHE_PATH.exists():
        return None
    try:
        data = json.loads(CACHE_PATH.read_text())
        return data.get("teams") or {}
    except Exception:
        return None


def get_injuries(*, force_refresh: bool = False) -> dict[str, list[dict[str, Any]]]:
    try:
        by_team = fetch_espn_injuries()
        save_cache(by_team)
        print(f"[injury] ESPN OK teams={len(by_team)} cached→{CACHE_PATH.name}")
        return by_team
    except Exception as e:
        print(f"[injury] ESPN fetch failed: {e}")
        cached = load_cache()
        if cached is not None:
            print(f"[injury] using cache ({CACHE_PATH.name})")
            return cached
        print("[injury] no cache — zero penalties")
        return {}


def team_absence_penalty(
    team: str,
    by_team: dict[str, list[dict[str, Any]]],
    tier1: set[str],
    tier2: set[str],
) -> tuple[float, list[str]]:
    team = _norm_team(team)
    rows = by_team.get(team) or []
    if not rows:
        for k, v in by_team.items():
            if team.lower() in k.lower() or k.lower() in team.lower():
                rows = v
                break
    pen = 0.0
    reasons: list[str] = []
    seen = set()
    for row in rows:
        st = (row.get("status_norm") or row.get("status") or "").lower().replace(" ", "-")
        if st not in ACTIVE_STATUSES and "out" not in st and "doubtful" not in st:
            continue
        player = (row.get("player") or "").strip()
        if not player or player in seen:
            continue
        seen.add(player)
        if player in tier1:
            pen += PENALTY_TIER1
            reasons.append(f"{player} Out/T1(-{PENALTY_TIER1:.0f})")
        elif player in tier2:
            pen += PENALTY_TIER2
            reasons.append(f"{player} Out/T2(-{PENALTY_TIER2:.0f})")
    return pen, reasons


def adjust_ratings_for_matchup(
    ratings: dict[str, float],
    home_team: str,
    away_team: str,
    by_team: dict[str, list[dict[str, Any]]] | None = None,
) -> tuple[float, float, dict[str, Any]]:
    tier1, tier2 = load_star_tiers()
    if by_team is None:
        by_team = get_injuries()
    h = _norm_team(home_team)
    a = _norm_team(away_team)
    rh = float(ratings.get(h, 1500.0))
    ra = float(ratings.get(a, 1500.0))
    ph, rh_reasons = team_absence_penalty(h, by_team, tier1, tier2)
    pa, ra_reasons = team_absence_penalty(a, by_team, tier1, tier2)
    meta = {
        "home_penalty": ph,
        "away_penalty": pa,
        "home_reasons": rh_reasons,
        "away_reasons": ra_reasons,
        "injury_applied": bool(by_team),
    }
    return rh - ph, ra - pa, meta


def adjusted_home_win_prob(
    ratings: dict[str, float],
    home_team: str,
    away_team: str,
    *,
    hca: float = 100.0,
    by_team: dict[str, list[dict[str, Any]]] | None = None,
) -> tuple[float, dict[str, Any]]:
    rh, ra, meta = adjust_ratings_for_matchup(ratings, home_team, away_team, by_team)
    p = 1.0 / (1.0 + 10 ** ((ra - (rh + hca)) / 400.0))
    meta["adj_home_elo"] = rh
    meta["adj_away_elo"] = ra
    meta["p_home"] = p
    return float(p), meta


BACKTEST_INJURIES: dict[str, dict[str, list[dict[str, Any]]]] = {
    "2026-11-03": {
        "Los Angeles Clippers": [
            {"player": "Bradley Beal", "status": "Out", "status_norm": "out"},
            {"player": "Brandon Ingram", "status": "Out", "status_norm": "out"},
            {"player": "Rui Hachimura", "status": "Out", "status_norm": "out"},
            {"player": "Derrick Jones Jr.", "status": "Out", "status_norm": "out"},
        ],
        "Toronto Raptors": [
            {"player": "Kawhi Leonard", "status": "Out", "status_norm": "out"},
        ],
    },
    "2026-11-05": {},
    "2026-11-08": {},
    "2026-11-10": {
        "New Orleans Pelicans": [
            {"player": "Zion Williamson", "status": "Out", "status_norm": "out"},
            {"player": "Trey Murphy III", "status": "Out", "status_norm": "out"},
            {"player": "Dejounte Murray", "status": "Out", "status_norm": "out"},
        ],
    },
    "2026-11-14": {
        "Golden State Warriors": [
            {"player": "Stephen Curry", "status": "Out", "status_norm": "out"},
        ],
    },
    "2026-11-19": {
        "Golden State Warriors": [
            {"player": "Stephen Curry", "status": "Out", "status_norm": "out"},
            {"player": "Jimmy Butler", "status": "Out", "status_norm": "out"},
            {"player": "Moses Moody", "status": "Out", "status_norm": "out"},
            {"player": "Kristaps Porzingis", "status": "Out", "status_norm": "out"},
            {"player": "Draymond Green", "status": "Out", "status_norm": "out"},
            {"player": "Brandon Williams", "status": "Out", "status_norm": "out"},
        ],
        "Oklahoma City Thunder": [
            {"player": "Chet Holmgren", "status": "Out", "status_norm": "out"},
            {"player": "Jalen Williams", "status": "Out", "status_norm": "out"},
            {"player": "Cason Wallace", "status": "Out", "status_norm": "out"},
        ],
        "New Orleans Pelicans": [
            {"player": "Trey Murphy III", "status": "Out", "status_norm": "out"},
            {"player": "Dejounte Murray", "status": "Out", "status_norm": "out"},
            {"player": "Trendon Watford", "status": "Out", "status_norm": "out"},
        ],
    },
}


def backtest_injuries_for_date(date_yyyy_mm_dd: str) -> dict[str, list[dict[str, Any]]]:
    return BACKTEST_INJURIES.get(date_yyyy_mm_dd, {})


if __name__ == "__main__":
    by = get_injuries(force_refresh=True)
    n = sum(len(v) for v in by.values())
    print(f"players listed: {n}")
    for team in ("Golden State Warriors", "Oklahoma City Thunder", "Los Angeles Clippers"):
        pen, reasons = team_absence_penalty(team, by, *load_star_tiers())
        print(f"  {team}: penalty={pen} {reasons[:5]}")
