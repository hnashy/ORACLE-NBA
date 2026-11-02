#!/usr/bin/env python3
"""
ORACLE-NBA Post-Match Review (Path A companion)
===============================================
Structural audit only — NO ROI / PnL / bankroll math.

Reads data/live_collection/master_log.csv, joins final scores
(The Odds API scores endpoint), and writes:

  reports/live_reviews/review_YYYY-MM-DD.md

Focus:
  - Window completeness (T-6h / T-1h / T-10m)
  - T-10m edge signals → theoretical Win/Loss/Push vs final score
  - Price movement T-6h → T-10m (home de-vig + total line)
  - Confidence flag on |Δ total|: stable <1, moderate 1–3, volatile >3
  - Alias / team-name quality flags
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    requests = None  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
MASTER_LOG = ROOT / "data" / "live_collection" / "master_log.csv"
REPORT_DIR = ROOT / "reports" / "live_reviews"
ALIASES_PATH = ROOT / "config" / "team_aliases.json"

ODDS_API_BASE = "https://api.the-odds-api.com/v4"
SPORT = "basketball_nba"
EDGE_THRESHOLD = 0.03
WINDOWS = ("T-6h", "T-1h", "T-10m")


def require_env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        print(f"[FATAL] Missing env {name}", file=sys.stderr)
        sys.exit(2)
    return val


def load_aliases() -> dict[str, str]:
    if not ALIASES_PATH.exists():
        return {}
    import json

    return {str(k): str(v) for k, v in json.loads(ALIASES_PATH.read_text()).items()}


def load_master_log(path: Path = MASTER_LOG) -> list[dict[str, str]]:
    if not path.exists():
        print(f"[WARN] No master_log at {path}")
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def group_by_game(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    g: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        gid = r.get("game_id") or ""
        if gid:
            g[gid].append(r)
    return g


def consensus_home_p(rows: list[dict[str, str]]) -> float | None:
    """Mean de-vig home prob across books in this row set (already stored)."""
    vals = []
    for r in rows:
        v = r.get("market_home_p_devig")
        if v not in (None, ""):
            try:
                vals.append(float(v))
            except ValueError:
                pass
    if not vals:
        return None
    return sum(vals) / len(vals)


def consensus_total_line(rows: list[dict[str, str]]) -> float | None:
    """Mean total_line across books for a window."""
    vals = []
    for r in rows:
        v = r.get("total_line")
        if v not in (None, ""):
            try:
                vals.append(float(v))
            except ValueError:
                pass
    if not vals:
        return None
    return sum(vals) / len(vals)


def confidence_flag(delta_total: float | None) -> str:
    """
    Stable if |Δ total| < 1, volatile if |Δ total| > 3, else moderate.
    Based on T-6h → T-10m total line movement (points).
    """
    if delta_total is None:
        return "n/a"
    a = abs(delta_total)
    if a < 1.0:
        return "stable"
    if a > 3.0:
        return "volatile"
    return "moderate"


def elo_home_p(rows: list[dict[str, str]]) -> float | None:
    vals = []
    for r in rows:
        v = r.get("elo_home_p")
        if v not in (None, ""):
            try:
                vals.append(float(v))
            except ValueError:
                pass
    if not vals:
        return None
    return sum(vals) / len(vals)


def window_rows(rows: list[dict[str, str]], label: str) -> list[dict[str, str]]:
    return [r for r in rows if r.get("window_label") == label]


def fetch_scores(api_key: str, days_from: int = 3) -> list[dict]:
    """Completed + live NBA scores from The Odds API."""
    if requests is None:
        raise RuntimeError("requests not installed")
    url = f"{ODDS_API_BASE}/sports/{SPORT}/scores"
    params = {"apiKey": api_key, "daysFrom": days_from, "dateFormat": "iso"}
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def score_index(scores: list[dict]) -> dict[str, dict]:
    """Map game id → score payload."""
    out = {}
    for s in scores:
        gid = s.get("id")
        if gid:
            out[gid] = s
    return out


def parse_final_score(score_obj: dict | None) -> tuple[int | None, int | None, bool]:
    """Return (home_score, away_score, completed)."""
    if not score_obj:
        return None, None, False
    completed = bool(score_obj.get("completed"))
    scores = score_obj.get("scores") or []
    home_name = score_obj.get("home_team")
    away_name = score_obj.get("away_team")
    hs = as_ = None
    for sc in scores:
        name = sc.get("name")
        try:
            pts = int(sc.get("score"))
        except (TypeError, ValueError):
            continue
        if name == home_name:
            hs = pts
        elif name == away_name:
            as_ = pts
    return hs, as_, completed


def signal_outcome(
    edge: float | None,
    home_score: int | None,
    away_score: int | None,
) -> str:
    """
    Theoretical paper outcome for a HOME-edge signal at T-10m.
    edge > 0 → model leaned HOME; edge < 0 → AWAY.
    """
    if edge is None or home_score is None or away_score is None:
        return "n/a"
    if abs(edge) < EDGE_THRESHOLD:
        return "no_signal"
    if home_score == away_score:
        return "push"
    home_won = home_score > away_score
    model_home = edge > 0
    if model_home == home_won:
        return "win"
    return "loss"


def alias_flags(home: str, away: str, aliases: dict[str, str]) -> list[str]:
    flags = []
    for t in (home, away):
        if not t:
            flags.append("empty_team_name")
            continue
        if t not in aliases.values() and t not in aliases:
            flags.append(f"unmapped:{t}")
    return flags


def build_game_summary(
    gid: str,
    rows: list[dict[str, str]],
    score_obj: dict | None,
    aliases: dict[str, str],
) -> dict[str, Any]:
    home = rows[0].get("home_team", "")
    away = rows[0].get("away_team", "")
    tip = rows[0].get("tipoff_time_utc", "")
    present = {w: bool(window_rows(rows, w)) for w in WINDOWS}
    p6 = consensus_home_p(window_rows(rows, "T-6h"))
    p1 = consensus_home_p(window_rows(rows, "T-1h"))
    p10 = consensus_home_p(window_rows(rows, "T-10m"))
    tot6 = consensus_total_line(window_rows(rows, "T-6h"))
    tot10 = consensus_total_line(window_rows(rows, "T-10m"))
    e10 = None
    elo10 = elo_home_p(window_rows(rows, "T-10m"))
    if elo10 is not None and p10 is not None:
        e10 = elo10 - p10
    if e10 is None:
        for r in window_rows(rows, "T-10m"):
            try:
                e10 = float(r.get("edge_home") or "")
                break
            except ValueError:
                pass

    hs, as_, completed = parse_final_score(score_obj)
    outcome = signal_outcome(e10, hs, as_) if present["T-10m"] else "n/a"
    move_6_to_10 = None
    if p6 is not None and p10 is not None:
        move_6_to_10 = p10 - p6
    total_move = None
    if tot6 is not None and tot10 is not None:
        total_move = tot10 - tot6
    conf = confidence_flag(total_move)

    return {
        "game_id": gid,
        "home_team": home,
        "away_team": away,
        "tipoff_time_utc": tip,
        "windows": present,
        "windows_complete": all(present.values()),
        "p_home_t6h": p6,
        "p_home_t1h": p1,
        "p_home_t10m": p10,
        "elo_home_t10m": elo10,
        "edge_t10m": e10,
        "move_6h_to_10m": move_6_to_10,
        "total_t6h": tot6,
        "total_t10m": tot10,
        "total_move_6h_to_10m": total_move,
        "confidence_flag": conf,
        "home_score": hs,
        "away_score": as_,
        "completed": completed,
        "signal_outcome": outcome,
        "alias_flags": alias_flags(home, away, aliases),
        "n_rows": len(rows),
    }


def fmt_pct(x: float | None) -> str:
    if x is None:
        return "—"
    return f"{x * 100:.1f}%"


def fmt_edge(x: float | None) -> str:
    if x is None:
        return "—"
    return f"{x * 100:+.1f}%"


def render_markdown(summaries: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    day = meta.get("report_date", "")
    lines: list[str] = []
    lines.append(f"# Live Collection Review — {day}")
    lines.append("")
    lines.append("> Structural audit only. No ROI / PnL. Paper signals at T-10m.")
    lines.append("")
    lines.append("## Session summary")
    lines.append("")
    lines.append(f"- Generated (UTC): `{meta.get('generated_at')}`")
    lines.append(f"- Master log rows: **{meta.get('n_log_rows')}**")
    lines.append(f"- Distinct games: **{meta.get('n_games')}**")
    lines.append(f"- Scores fetched: **{meta.get('n_scores')}** (API daysFrom={meta.get('days_from')})")
    lines.append(f"- Credits remaining (last header if any): `{meta.get('credits_remaining', 'n/a')}`")
    lines.append("")
    complete = sum(1 for s in summaries if s["windows_complete"])
    has_t10 = sum(1 for s in summaries if s["windows"]["T-10m"])
    finished = sum(1 for s in summaries if s["completed"])
    lines.append(f"- Games with all 3 windows (T-6h/T-1h/T-10m): **{complete}**")
    lines.append(f"- Games with T-10m snapshot: **{has_t10}**")
    lines.append(f"- Games completed (final score available): **{finished}**")
    lines.append("")

    lines.append("## T-10m edge signals (|edge| ≥ 3%)")
    lines.append("")
    signals = [
        s
        for s in summaries
        if s.get("edge_t10m") is not None and abs(s["edge_t10m"]) >= EDGE_THRESHOLD
    ]
    if not signals:
        lines.append("_No T-10m signals above threshold in this log._")
    else:
        lines.append(
            "| Match | Tip (UTC) | Elo p(H) | Mkt p(H) | Edge | Δ Total | Conf | Score | Paper |"
        )
        lines.append("|---|---|---:|---:|---:|---:|---|---|---|")
        for s in signals:
            match = f"{s['away_team']} @ {s['home_team']}"
            score = (
                f"{s['home_score']}-{s['away_score']}"
                if s["home_score"] is not None
                else "—"
            )
            dt = s.get("total_move_6h_to_10m")
            dt_s = "—" if dt is None else f"{dt:+.1f}"
            lines.append(
                f"| {match} | {s['tipoff_time_utc']} | "
                f"{fmt_pct(s['elo_home_t10m'])} | {fmt_pct(s['p_home_t10m'])} | "
                f"{fmt_edge(s['edge_t10m'])} | {dt_s} | `{s.get('confidence_flag', 'n/a')}` | "
                f"{score} | `{s['signal_outcome']}` |"
            )
    lines.append("")

    lines.append("## Price movement (T-6h → T-10m)")
    lines.append("")
    lines.append(
        "Confidence: `stable` if |Δ total| < 1 pt · `moderate` 1–3 · `volatile` > 3."
    )
    lines.append("")
    moved = [
        s
        for s in summaries
        if s.get("move_6h_to_10m") is not None or s.get("total_move_6h_to_10m") is not None
    ]
    if not moved:
        lines.append("_Insufficient paired windows._")
    else:
        lines.append(
            "| Match | p(H) T-6h | p(H) T-10m | Δ p(H) | Total T-6h | Total T-10m | Δ Total | Conf |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
        for s in moved:
            match = f"{s['away_team']} @ {s['home_team']}"
            dt = s.get("total_move_6h_to_10m")
            dt_s = "—" if dt is None else f"{dt:+.1f}"
            t6 = s.get("total_t6h")
            t10 = s.get("total_t10m")
            t6s = "—" if t6 is None else f"{t6:.1f}"
            t10s = "—" if t10 is None else f"{t10:.1f}"
            lines.append(
                f"| {match} | {fmt_pct(s['p_home_t6h'])} | "
                f"{fmt_pct(s['p_home_t10m'])} | {fmt_edge(s['move_6h_to_10m'])} | "
                f"{t6s} | {t10s} | {dt_s} | `{s.get('confidence_flag', 'n/a')}` |"
            )
    lines.append("")

    lines.append("## Window coverage by game")
    lines.append("")
    lines.append("| Match | T-6h | T-1h | T-10m | Complete | Final |")
    lines.append("|---|:---:|:---:|:---:|:---:|---|")
    for s in summaries:
        match = f"{s['away_team']} @ {s['home_team']}"

        def mark(b: bool) -> str:
            return "✓" if b else "·"

        final = (
            f"{s['home_score']}-{s['away_score']}"
            if s["completed"] and s["home_score"] is not None
            else ("live/pending" if not s["completed"] else "—")
        )
        lines.append(
            f"| {match} | {mark(s['windows']['T-6h'])} | "
            f"{mark(s['windows']['T-1h'])} | {mark(s['windows']['T-10m'])} | "
            f"{mark(s['windows_complete'])} | {final} |"
        )
    lines.append("")

    lines.append("## Quality alerts")
    lines.append("")
    alerts = []
    for s in summaries:
        if s["alias_flags"]:
            alerts.append(f"- Alias: {s['away_team']} @ {s['home_team']} → {s['alias_flags']}")
        if not s["completed"] and s["windows"]["T-10m"]:
            try:
                tip = datetime.fromisoformat(
                    (s["tipoff_time_utc"] or "").replace("Z", "+00:00")
                )
                if tip < datetime.now(timezone.utc) - timedelta(hours=4):
                    alerts.append(
                        f"- Missing final score (>4h after tip): "
                        f"{s['away_team']} @ {s['home_team']} ({s['game_id'][:8]}…)"
                    )
            except ValueError:
                pass
    if not alerts:
        lines.append("_None._")
    else:
        lines.extend(alerts)
    lines.append("")
    lines.append("---")
    lines.append("_Generated by `scripts/post_match_review.py`. Paper trading documentation only._")
    lines.append("")
    return "\n".join(lines)


def run(days_from: int = 3, report_date: str | None = None) -> Path:
    api_key = require_env("ODDS_API_KEY")
    aliases = load_aliases()
    rows = load_master_log()
    games = group_by_game(rows)
    scores = fetch_scores(api_key, days_from=days_from)
    idx = score_index(scores)

    summaries = [
        build_game_summary(gid, grows, idx.get(gid), aliases)
        for gid, grows in sorted(
            games.items(), key=lambda x: x[1][0].get("tipoff_time_utc") or ""
        )
    ]

    day = report_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    meta = {
        "report_date": day,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_log_rows": len(rows),
        "n_games": len(games),
        "n_scores": len(scores),
        "days_from": days_from,
        "credits_remaining": (rows[-1].get("credits_remaining") if rows else "n/a"),
    }
    md = render_markdown(summaries, meta)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / f"review_{day}.md"
    out.write_text(md, encoding="utf-8")
    print(
        f"[ok] wrote {out} games={len(summaries)} signals="
        f"{sum(1 for s in summaries if s.get('edge_t10m') and abs(s['edge_t10m']) >= EDGE_THRESHOLD)}"
    )
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="ORACLE-NBA post-match structural review")
    ap.add_argument("--days-from", type=int, default=3, help="Odds API scores lookback")
    ap.add_argument("--date", type=str, default=None, help="Report date YYYY-MM-DD")
    args = ap.parse_args()
    run(days_from=args.days_from, report_date=args.date)


if __name__ == "__main__":
    main()
