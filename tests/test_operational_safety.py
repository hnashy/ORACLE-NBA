from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import injury_adjuster  # noqa: E402
import live_collector  # noqa: E402
import post_match_review  # noqa: E402


class InjuryCacheTests(unittest.TestCase):
    def _write_cache(self, path: Path, fetched_at: str | None) -> None:
        payload = {"teams": {"Boston Celtics": [{"player": "Example", "status": "Out"}]}}
        if fetched_at is not None:
            payload["fetched_at_utc"] = fetched_at
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_fresh_cache_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "injuries.json"
            fetched = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            self._write_cache(path, fetched)
            with patch.object(injury_adjuster, "CACHE_PATH", path):
                cached = injury_adjuster.load_cache()
        self.assertIn("Boston Celtics", cached or {})

    def test_stale_cache_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "injuries.json"
            fetched = (datetime.now(timezone.utc) - timedelta(hours=13)).isoformat()
            self._write_cache(path, fetched)
            with patch.object(injury_adjuster, "CACHE_PATH", path):
                self.assertIsNone(injury_adjuster.load_cache())

    def test_cache_without_timestamp_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "injuries.json"
            self._write_cache(path, None)
            with patch.object(injury_adjuster, "CACHE_PATH", path):
                self.assertIsNone(injury_adjuster.load_cache())

    def test_fetch_failure_does_not_use_stale_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "injuries.json"
            fetched = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
            self._write_cache(path, fetched)
            with (
                patch.object(injury_adjuster, "CACHE_PATH", path),
                patch.object(injury_adjuster, "fetch_espn_injuries", side_effect=OSError("offline")),
            ):
                self.assertEqual(injury_adjuster.get_injuries(force_refresh=True), {})


class TelegramDeduplicationTests(unittest.TestCase):
    def test_successful_alert_is_not_resent_on_next_run(self) -> None:
        now = datetime(2026, 11, 20, 4, 40, tzinfo=timezone.utc)
        event = {
            "id": "game-123",
            "commence_time": (now + timedelta(minutes=10)).isoformat(),
            "home_team": "Boston Celtics",
            "away_team": "New York Knicks",
            "bookmakers": [
                {
                    "key": "testbook",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "Boston Celtics", "price": -110},
                                {"name": "New York Knicks", "price": -110},
                            ],
                        }
                    ],
                }
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "master_log.csv"
            legacy_fields = live_collector.CSV_FIELDS[:-1]
            with log_path.open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=legacy_fields)
                writer.writeheader()
                writer.writerow({"game_id": "historical-game", "window_label": "T-6h"})
            with (
                patch.object(live_collector, "MASTER_LOG", log_path),
                patch.object(live_collector, "utcnow", return_value=now),
                patch.object(live_collector, "build_elo_ratings", return_value={}),
                patch.object(live_collector, "_get_injury_board", return_value={}),
                patch.object(live_collector, "fetch_odds", return_value=([event], {})),
                patch.object(live_collector, "load_model_prob", return_value=0.70),
                patch.object(live_collector, "maybe_telegram_alert", return_value=True) as send_alert,
            ):
                live_collector.run_once("test-key")
                live_collector.run_once("test-key")

            self.assertEqual(send_alert.call_count, 1)
            with log_path.open(newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                self.assertIn("telegram_alert_sent", reader.fieldnames or [])
            self.assertTrue(any(row.get("telegram_alert_sent") == "true" for row in rows))
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0]["game_id"], "historical-game")


class DaysFromValidationTests(unittest.TestCase):
    def test_run_rejects_values_outside_supported_range(self) -> None:
        for invalid in (0, 4, -1, True):
            with self.subTest(days_from=invalid), self.assertRaises(ValueError):
                post_match_review.run(days_from=invalid)

    def test_cli_rejects_unsupported_days_from(self) -> None:
        with patch.object(sys, "argv", ["post_match_review.py", "--days-from", "4"]):
            with self.assertRaises(SystemExit) as exc:
                post_match_review.main()
        self.assertEqual(exc.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
