from __future__ import annotations

import csv
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

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


class TelegramReviewWebhookTests(unittest.TestCase):
    def _telegram_success(self):
        response = Mock(status_code=200)
        response.json.return_value = {"ok": True, "result": {}}
        return response

    def test_review_copy_follows_confirmed_telegram_success(self) -> None:
        telegram_response = self._telegram_success()
        webhook_response = Mock(status_code=204)
        webhook_url = "https://review.example.invalid/hook-secret"
        with (
            patch.dict("os.environ", {
                "TELEGRAM_BOT_TOKEN": "test-token",
                "TELEGRAM_CHAT_ID": "test-chat",
                "TELEGRAM_REVIEW_WEBHOOK_URL": webhook_url,
            }),
            patch.object(live_collector.requests, "post", side_effect=[telegram_response, webhook_response]) as post,
        ):
            sent = live_collector.maybe_telegram_alert(
                {"home_team": "Home", "away_team": "Away"}, 0.04, "HOME", dry_run=False
            )

        self.assertTrue(sent)
        self.assertEqual(post.call_count, 2)
        self.assertEqual(
            post.call_args_list[1].kwargs["json"],
            {"source": "ORACLE-NBA", "text": post.call_args_list[0].kwargs["json"]["text"]},
        )

    def test_no_review_copy_when_telegram_does_not_confirm_success(self) -> None:
        telegram_response = self._telegram_success()
        telegram_response.json.return_value = {"ok": False, "description": "rejected"}
        with (
            patch.dict("os.environ", {
                "TELEGRAM_BOT_TOKEN": "test-token",
                "TELEGRAM_CHAT_ID": "test-chat",
                "TELEGRAM_REVIEW_WEBHOOK_URL": "https://review.example.invalid/hook-secret",
            }),
            patch.object(live_collector.requests, "post", return_value=telegram_response) as post,
        ):
            sent = live_collector.maybe_telegram_alert(
                {"home_team": "Home", "away_team": "Away"}, 0.04, "HOME", dry_run=False
            )

        self.assertTrue(sent)
        self.assertEqual(post.call_count, 1)

    def test_manual_send_keeps_http_success_without_review_secret(self) -> None:
        telegram_response = self._telegram_success()
        telegram_response.json.return_value = {"ok": False, "description": "not confirmed"}
        with (
            patch.dict("os.environ", {
                "TELEGRAM_BOT_TOKEN": "test-token",
                "TELEGRAM_CHAT_ID": "test-chat",
            }, clear=True),
            patch.object(live_collector.requests, "post", return_value=telegram_response) as post,
        ):
            sent = live_collector.maybe_telegram_alert(
                {"home_team": "Home", "away_team": "Away"}, 0.04, "HOME", dry_run=False
            )

        self.assertTrue(sent)
        self.assertEqual(post.call_count, 1)
        telegram_response.json.assert_not_called()

    def test_no_review_copy_when_telegram_http_request_fails(self) -> None:
        with (
            patch.dict("os.environ", {
                "TELEGRAM_BOT_TOKEN": "test-token",
                "TELEGRAM_CHAT_ID": "test-chat",
                "TELEGRAM_REVIEW_WEBHOOK_URL": "https://review.example.invalid/hook-secret",
            }),
            patch.object(
                live_collector.requests,
                "post",
                side_effect=live_collector.requests.HTTPError("Telegram request failed"),
            ) as post,
        ):
            sent = live_collector.maybe_telegram_alert(
                {"home_team": "Home", "away_team": "Away"}, 0.04, "HOME", dry_run=False
            )

        self.assertFalse(sent)
        self.assertEqual(post.call_count, 1)

    def test_webhook_failure_is_best_effort_and_does_not_log_url(self) -> None:
        telegram_response = self._telegram_success()
        webhook_url = "https://review.example.invalid/hook-secret"
        with (
            patch.dict("os.environ", {
                "TELEGRAM_BOT_TOKEN": "test-token",
                "TELEGRAM_CHAT_ID": "test-chat",
                "TELEGRAM_REVIEW_WEBHOOK_URL": webhook_url,
            }),
            patch.object(
                live_collector.requests,
                "post",
                side_effect=[telegram_response, RuntimeError(f"failed {webhook_url}")],
            ),
            patch("sys.stdout", new_callable=io.StringIO) as output,
        ):
            sent = live_collector.maybe_telegram_alert(
                {"home_team": "Home", "away_team": "Away"}, 0.04, "HOME", dry_run=False
            )

        self.assertTrue(sent)
        self.assertNotIn(webhook_url, output.getvalue())

    def test_dry_run_does_not_send_telegram_or_review_copy(self) -> None:
        with (
            patch.dict("os.environ", {
                "TELEGRAM_BOT_TOKEN": "test-token",
                "TELEGRAM_CHAT_ID": "test-chat",
                "TELEGRAM_REVIEW_WEBHOOK_URL": "https://review.example.invalid/hook-secret",
            }),
            patch.object(live_collector.requests, "post") as post,
        ):
            sent = live_collector.maybe_telegram_alert(
                {"home_team": "Home", "away_team": "Away"}, 0.04, "HOME", dry_run=True
            )

        self.assertFalse(sent)
        post.assert_not_called()


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
