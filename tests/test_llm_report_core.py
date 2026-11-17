from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import llm_report_core


class AggregateCodexTests(unittest.TestCase):
    def test_keeps_rate_limits_when_token_usage_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            sessions_dir = home / ".codex" / "sessions" / "2026" / "01" / "01"
            sessions_dir.mkdir(parents=True)
            rate_limits = {
                "plan_type": "pro",
                "primary": {"used_percent": 25, "resets_at": 2_000_000_000},
                "secondary": {"used_percent": 50, "resets_at": 2_000_100_000},
            }
            event = {
                "timestamp": "2026-01-01T00:00:00Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": None,
                    "rate_limits": rate_limits,
                },
            }
            (sessions_dir / "rollout-test.jsonl").write_text(
                json.dumps(event) + "\n",
                encoding="utf-8",
            )

            with mock.patch.object(llm_report_core.Path, "home", return_value=home):
                aggregate = llm_report_core.aggregate_codex()

        self.assertEqual(aggregate.latest_rate_limits, rate_limits)
        self.assertEqual(aggregate.token_events, 0)
        self.assertTrue(llm_report_core.codex_present(aggregate))


class CodexRateLimitExpiryTests(unittest.TestCase):
    def test_expired_window_is_not_returned_as_remaining_quota(self) -> None:
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        limit = {"used_percent": 100, "resets_at": int(now.timestamp())}
        aggregate = llm_report_core.CodexAggregate(
            latest_rate_limits={"primary": limit}
        )

        with mock.patch.dict(
            os.environ,
            {
                llm_report_core.LANGUAGE_ENV: "en",
                llm_report_core.TIMEZONE_ENV: "UTC",
            },
        ):
            self.assertIsNone(
                llm_report_core.get_codex_remaining_percent(
                    aggregate,
                    "primary",
                    now_local=now,
                )
            )
            self.assertEqual(
                llm_report_core.format_codex_rate_limit(limit, now),
                "Expired data",
            )

    def test_expired_window_uses_korean_message(self) -> None:
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        limit = {
            "used_percent": 100,
            "resets_at": int((now - timedelta(seconds=1)).timestamp()),
        }

        with mock.patch.dict(
            os.environ,
            {
                llm_report_core.LANGUAGE_ENV: "ko",
                llm_report_core.TIMEZONE_ENV: "UTC",
            },
        ):
            self.assertEqual(
                llm_report_core.format_codex_rate_limit(limit, now),
                "데이터 만료됨",
            )

    def test_future_window_still_returns_remaining_quota(self) -> None:
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        limit = {
            "used_percent": 25,
            "resets_at": int((now + timedelta(hours=1)).timestamp()),
        }
        aggregate = llm_report_core.CodexAggregate(
            latest_rate_limits={"primary": limit}
        )

        with mock.patch.dict(
            os.environ,
            {
                llm_report_core.LANGUAGE_ENV: "en",
                llm_report_core.TIMEZONE_ENV: "UTC",
            },
        ):
            self.assertEqual(
                llm_report_core.get_codex_remaining_percent(
                    aggregate,
                    "primary",
                    now_local=now,
                ),
                75.0,
            )
            self.assertIn(
                "75.0% remaining",
                llm_report_core.format_codex_rate_limit(limit, now),
            )


class AlertStatePersistenceTests(unittest.TestCase):
    def test_save_alert_state_replaces_from_unique_sibling_temp_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / ".alert_state.json"
            path.write_text('{"primary": true}\n', encoding="utf-8")
            real_replace = os.replace

            with mock.patch.object(
                llm_report_core.os,
                "replace",
                wraps=real_replace,
            ) as replace_mock:
                llm_report_core.save_alert_state(
                    {"primary": False, "secondary": True},
                    path,
                )

            source, destination = replace_mock.call_args.args
            source_path = Path(source)
            self.assertEqual(source_path.parent, path.parent)
            self.assertNotEqual(source_path, path)
            self.assertEqual(Path(destination), path)
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                {"primary": False, "secondary": True},
            )
            self.assertEqual(
                [item for item in path.parent.iterdir() if item != path],
                [],
            )

    def test_save_alert_state_preserves_old_file_when_replace_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / ".alert_state.json"
            original = '{"primary": true, "secondary": false}\n'
            path.write_text(original, encoding="utf-8")

            with mock.patch.object(
                llm_report_core.os,
                "replace",
                side_effect=OSError("replace failed"),
            ):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    llm_report_core.save_alert_state(
                        {"primary": False, "secondary": True},
                        path,
                    )

            self.assertEqual(path.read_text(encoding="utf-8"), original)
            self.assertEqual(
                [item for item in path.parent.iterdir() if item != path],
                [],
            )


if __name__ == "__main__":
    unittest.main()
