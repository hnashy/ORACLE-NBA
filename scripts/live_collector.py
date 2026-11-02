#!/usr/bin/env python3
"""
ORACLE-NBA Live Collector (Path A) — PAPER TRADING ONLY
=======================================================
Secrets (env only — never hardcode):
  ODDS_API_KEY          required
  TELEGRAM_BOT_TOKEN    optional until alerts
  TELEGRAM_CHAT_ID      optional until alerts

Windows: T-6h / T-1h / T-10m (±12 min). Sparse pulls only.
Model: Elo rebuilt from data/processed/games_clean.csv (home-court +100).
Edge at T-10m vs de-vigged market; Telegram only if |edge| >= 3% and not --dry-run.
"""

from __future__ import annotations

import csv
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    requests = None  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "data" / "live_collection"
LOG_DIR.mkdir(parents=True, exist_ok=True)
MASTER_LOG = LOG_DIR / "master_log.csv"
GAMES_CLEAN = ROOT / "data" / "processed" / "games_clean.csv"

ODDS_API_BASE = "https://api.the-odds-api.com/v4"
SPORT = "basketball_nba"
REGIONS = "us"
MARKETS = "h2h,totals"
ODDS_FORMAT = "american"

WINDOWS = {
    "T-6h": timedelta(hours=6),
    "T-1h": timedelta(hours=1),
    "T-10m": timedelta(minutes=10),
}
WINDOW_TOLERANCE = timedelta(minutes=12)
EDGE_THRESHOLD = 0.03
ELO_K = 20.0
ELO_HCA = 100.0  # home-court advantage in Elo points
ELO_DEFAULT = 1500.0

CSV_FIELDS = [
    "game_id",
    "timestamp_utc_capture",
    "tipoff_time_utc",
    "window_label",
    "home_team",
    "away_team",
    "bookmaker",
    "ml_home_odds",
    "ml_away_odds",
    "total_line",
    "over_odds",
    "under_odds",
    "credits_remaining",
    "elo_home_p",
    "market_home_p_devig",
    "edge_home",
]


def require_env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        print(
            f"[FATAL] Missing required environment variable: {name}\n"
            f"  Set it in GitHub Secrets / shell before run.\n"
            f"  Example: export {name}=...",
            file=sys.stderr,
        )
        sys.exit(2)
    return val


def optional_env(name: str) -> str:
    return os.environ.get(name, "").strip()


_ELO_CACHE: dict[str, float] | None = None
_TEAM_ALIASES = {
    "LA Clippers": "Los Angeles Clippers",
    "LA Lakers": "Los Angeles Lakers",
    "NY Knicks": "New York Knicks",
    "GS Warriors": "Golden State Warriors",
    "SA Spurs": "San Antonio Spurs",
    "NO Pelicans": "New Orleans Pelicans",
    "UT Jazz": "Utah Jazz",
    "PHX Suns": "Phoenix Suns",
    "PHO Suns": "Phoenix Suns",
}


def _norm_team(name: str) -> str:
    n = (name or "").strip()
    return _TEAM_ALIASES.get(n, n)


def _elo_expected(ra: float, rb: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))


def build_elo_ratings(path: Path = GAMES_CLEAN) -> dict[str, float]:
    global _ELO_CACHE
    if _ELO_CACHE is not None:
        return _ELO_CACHE
    if not path.exists():
        print(f"[WARN] games_clean not found at {path}; Elo defaults to {ELO_DEFAULT}")
        _ELO_CACHE = {}
        return _ELO_CACHE

    import pandas as pd

    df = pd.read_csv(path)
    df = df.dropna(subset=["gh", "ga"])
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df = df.sort_values("date")
    ratings: dict[str, float] = {}

    def get(t: str) -> float:
        return ratings.get(t, ELO_DEFAULT)

    for _, r in df.iterrows():
        h, a = str(r["h"]), str(r["a"])
        rh, ra = get(h), get(a)
        eh = _elo_expected(rh + ELO_HCA, ra)
        if r["gh"] > r["ga"]:
            sh, sa = 1.0, 0.0
        elif r["gh"] < r["ga"]:
            sh, sa = 0.0, 1.0
        else:
            sh, sa = 0.5, 0.5
        ratings[h] = rh + ELO_K * (sh - eh)
        ratings[a] = ra + ELO_K * ((1.0 - sh) - (1.0 - eh))

    _ELO_CACHE = ratings
    print(f"[elo] loaded {len(ratings)} teams from {path.name}")
    return ratings


def load_model_prob(home_team: str, away_team: str, tip: str | None = None) -> float | None:
    """Home-win probability from current Elo ratings (+ home-court)."""
    ratings = build_elo_ratings()
    h = _norm_team(home_team)
    a = _norm_team(away_team)
    rh = ratings.get(h, ELO_DEFAULT)
    ra = ratings.get(a, ELO_DEFAULT)
    p = _elo_expected(rh + ELO_HCA, ra)
    return float(p)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def american_to_implied(odds: float | int | None) -> float | None:
    if odds is None:
        return None
    o = float(odds)
    if o > 0:
        return 100.0 / (o + 100.0)
    return abs(o) / (abs(o) + 100.0)


def devig_two_way(p_home: float, p_away: float) -> tuple[float, float]:
    s = p_home + p_away
    if s <= 0:
        return p_home, p_away
    return p_home / s, p_away / s


def ensure_log_header() -> None:
    if not MASTER_LOG.exists():
        with MASTER_LOG.open("w", newline="") as f:
            csv.DictWriter(f, fieldnames=CSV_FIELDS).writeheader()


def append_rows(rows: list[dict[str, Any]]) -> None:
    ensure_log_header()
    with MASTER_LOG.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        for r in rows:
            w.writerow({k: r.get(k) for k in CSV_FIELDS})


def fetch_odds(api_key: str) -> tuple[list[dict], dict]:
    if requests is None:
        raise RuntimeError("requests package not installed")
    url = f"{ODDS_API_BASE}/sports/{SPORT}/odds"
    params = {
        "apiKey": api_key,
        "regions": REGIONS,
        "markets": MARKETS,
        "oddsFormat": ODDS_FORMAT,
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json(), dict(resp.headers)


def parse_event_rows(
    event: dict,
    capture_ts: datetime,
    window_label: str,
    credits: str,
    elo_p: float | None,
    mkt_p: float | None,
    edge: float | None,
) -> list[dict]:
    tip = event.get("commence_time")
    rows = []
    for bk in event.get("bookmakers") or []:
        ml_home = ml_away = total_line = over_o = under_o = None
        for market in bk.get("markets") or []:
            key = market.get("key")
            outcomes = market.get("outcomes") or []
            if key == "h2h":
                for o in outcomes:
                    if o.get("name") == event.get("home_team"):
                        ml_home = o.get("price")
                    elif o.get("name") == event.get("away_team"):
                        ml_away = o.get("price")
            elif key == "totals":
                for o in outcomes:
                    if o.get("name") == "Over":
                        total_line = o.get("point")
                        over_o = o.get("price")
                    elif o.get("name") == "Under":
                        under_o = o.get("price")
        rows.append(
            {
                "game_id": event.get("id"),
                "timestamp_utc_capture": capture_ts.isoformat(),
                "tipoff_time_utc": tip,
                "window_label": window_label,
                "home_team": event.get("home_team"),
                "away_team": event.get("away_team"),
                "bookmaker": bk.get("key"),
                "ml_home_odds": ml_home,
                "ml_away_odds": ml_away,
                "total_line": total_line,
                "over_odds": over_o,
                "under_odds": under_o,
                "credits_remaining": credits,
                "elo_home_p": None if elo_p is None else round(elo_p, 4),
                "market_home_p_devig": None if mkt_p is None else round(mkt_p, 4),
                "edge_home": None if edge is None else round(edge, 4),
            }
        )
    return rows


def active_window_label(tip_utc: datetime, now: datetime) -> str | None:
    for label, delta in WINDOWS.items():
        target = tip_utc - delta
        if abs(now - target) <= WINDOW_TOLERANCE:
            return label
    return None


def maybe_telegram_alert(
    summary: dict,
    edge: float,
    side: str,
    *,
    dry_run: bool,
) -> None:
    msg = (
        f"PAPER EDGE {side}\n"
        f"{summary.get('away_team')} @ {summary.get('home_team')}\n"
        f"edge={edge:.1%} window={summary.get('window_label')}\n"
        f"elo_p={summary.get('elo_home_p')} mkt_p={summary.get('market_home_p_devig')}\n"
        f"ml_home={summary.get('ml_home_odds')} total={summary.get('total_line')}\n"
        f"capture={summary.get('timestamp_utc_capture')}\n"
        f"(paper only — no real wager)"
    )
    if dry_run:
        print("[telegram DRY-RUN — not sent]\n" + msg)
        return

    token = optional_env("TELEGRAM_BOT_TOKEN")
    chat = optional_env("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[telegram skipped — TELEGRAM_BOT_TOKEN/CHAT_ID missing]")
        print(msg)
        return
    if requests is None:
        print("[telegram skipped — requests missing]")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": chat, "text": msg}, timeout=15)
        print(f"[telegram] status={r.status_code}")
    except Exception as e:
        print(f"[telegram error] {e}")


def consensus_devig_home(rows: list[dict]) -> float | None:
    imps = []
    for r in rows:
        ih = american_to_implied(r.get("ml_home_odds"))
        ia = american_to_implied(r.get("ml_away_odds"))
        if ih is not None and ia is not None:
            dh, _ = devig_two_way(ih, ia)
            imps.append(dh)
    if not imps:
        return None
    return sum(imps) / len(imps)


def run_once(api_key: str, dry_run: bool = False) -> dict:
    now = utcnow()
    build_elo_ratings()

    events, headers = fetch_odds(api_key)
    credits = headers.get("x-requests-remaining", "")
    used = headers.get("x-requests-used", "")
    print(
        f"[{now.isoformat()}] API OK events={len(events)} "
        f"credits_remaining={credits} used={used} dry_run={dry_run}"
    )

    all_rows: list[dict] = []
    games_in_window = 0
    signals = 0

    for ev in events:
        tip_s = ev.get("commence_time")
        if not tip_s:
            continue
        tip = datetime.fromisoformat(tip_s.replace("Z", "+00:00"))
        label = active_window_label(tip, now)
        if not label:
            continue
        games_in_window += 1

        elo_p = load_model_prob(ev.get("home_team", ""), ev.get("away_team", ""), tip_s)
        provisional = parse_event_rows(ev, now, label, str(credits), None, None, None)
        mkt_p = consensus_devig_home(provisional)
        edge = None if (elo_p is None or mkt_p is None) else (elo_p - mkt_p)

        rows = parse_event_rows(ev, now, label, str(credits), elo_p, mkt_p, edge)
        all_rows.extend(rows)

        print(
            f"  WINDOW {label} | {ev.get('away_team')} @ {ev.get('home_team')} "
            f"| tip={tip_s} | elo_p={elo_p and round(elo_p,3)} "
            f"| mkt_p={mkt_p and round(mkt_p,3)} | edge={edge and round(edge,3)}"
        )

        if label == "T-10m" and edge is not None and abs(edge) >= EDGE_THRESHOLD:
            side = "HOME" if edge > 0 else "AWAY"
            maybe_telegram_alert(rows[0], abs(edge), side, dry_run=dry_run)
            signals += 1

    if all_rows and not dry_run:
        append_rows(all_rows)
        print(f"wrote {len(all_rows)} rows → {MASTER_LOG}")
    else:
        print(
            f"no CSV write (dry_run={dry_run} or empty) "
            f"rows={len(all_rows)} games_in_window={games_in_window}"
        )

    return {
        "api_ok": True,
        "events_total": len(events),
        "games_in_window": games_in_window,
        "rows": len(all_rows),
        "signals": signals,
        "credits_remaining": credits,
        "dry_run": dry_run,
        "wrote_csv": bool(all_rows and not dry_run),
    }


def main() -> None:
    dry = "--dry-run" in sys.argv
    api_key = require_env("ODDS_API_KEY")
    if not dry:
        if not optional_env("TELEGRAM_BOT_TOKEN") or not optional_env("TELEGRAM_CHAT_ID"):
            print("[WARN] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — signals will log only")
    summary = run_once(api_key, dry_run=dry)
    print("[summary]", summary)


if __name__ == "__main__":
    main()
