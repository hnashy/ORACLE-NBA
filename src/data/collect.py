"""
ORACLE-NBA data collection.

Primary: ESPN public scoreboard (no key).
Secondary: billmill parquet dumps (team_box, games).
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

import requests

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"


def fetch_espn_day(date_str: str) -> List[Dict]:
    """date_str = YYYYMMDD. Returns list of completed games."""
    url = (
        "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/"
        f"scoreboard?dates={date_str}&limit=50"
    )
    try:
        r = requests.get(url, timeout=12)
        if r.status_code != 200:
            return []
        data = r.json()
    except Exception:
        return []

    games = []
    for ev in data.get("events", []):
        status = (ev.get("status") or {}).get("type") or {}
        if not status.get("completed"):
            continue
        comp = (ev.get("competitions") or [{}])[0]
        comps = comp.get("competitors") or []
        if len(comps) < 2:
            continue
        home = away = None
        for c in comps:
            if c.get("homeAway") == "home":
                home = c
            else:
                away = c
        if not home or not away:
            continue
        try:
            gh = int(home.get("score") or 0)
            ga = int(away.get("score") or 0)
        except Exception:
            continue
        if gh == 0 and ga == 0:
            continue
        hname = (home.get("team") or {}).get("displayName") or "Home"
        aname = (away.get("team") or {}).get("displayName") or "Away"
        games.append(
            {
                "date": ev.get("date"),
                "h": hname,
                "a": aname,
                "gh": gh,
                "ga": ga,
            }
        )
    return games


def collect_espn_range(
    start: datetime,
    end: datetime,
    season: Optional[int] = None,
    sleep: float = 0.15,
) -> List[Dict]:
    games: List[Dict] = []
    d = start
    while d <= end:
        ds = d.strftime("%Y%m%d")
        day = fetch_espn_day(ds)
        for g in day:
            g["season"] = season
        games.extend(day)
        d += timedelta(days=1)
        time.sleep(sleep)
    return games


def add_rest_b2b(games: List[Dict]) -> List[Dict]:
    for g in games:
        try:
            g["ts"] = datetime.fromisoformat(g["date"].replace("Z", "+00:00")).timestamp()
        except Exception:
            g["ts"] = 0.0
    games = sorted(games, key=lambda x: x["ts"])
    last: Dict[str, float] = {}
    for g in games:
        prev_h = last.get(g["h"])
        prev_a = last.get(g["a"])
        g["hB2B"] = prev_h is not None and (g["ts"] - prev_h) < 36 * 3600
        g["aB2B"] = prev_a is not None and (g["ts"] - prev_a) < 36 * 3600
        g["hRest"] = (g["ts"] - prev_h) / 86400 if prev_h else None
        g["aRest"] = (g["ts"] - prev_a) / 86400 if prev_a else None
        last[g["h"]] = g["ts"]
        last[g["a"]] = g["ts"]
    return games


def dedupe(games: List[Dict]) -> List[Dict]:
    seen = set()
    out = []
    for g in games:
        k = ((g.get("date") or "")[:10], g["h"], g["a"])
        if k in seen:
            continue
        seen.add(k)
        out.append(g)
    return out


def save_json(games: List[Dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(games, f)


if __name__ == "__main__":
    # Example: last two seasons
    ranges = [
        (datetime(2024, 10, 22), datetime(2025, 4, 20), 2025),
        (datetime(2025, 10, 22), datetime(2026, 4, 20), 2026),
    ]
    all_g = []
    for start, end, season in ranges:
        print(f"Collecting season {season}...")
        batch = collect_espn_range(start, end, season=season)
        print(f"  {len(batch)} games")
        all_g.extend(batch)
    all_g = dedupe(add_rest_b2b(all_g))
    RAW.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    save_json(all_g, RAW / "espn_games_all.json")
    save_json(all_g, PROCESSED / "games_clean.json")
    print(f"Saved {len(all_g)} unique games")
