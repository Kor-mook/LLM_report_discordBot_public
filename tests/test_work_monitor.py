from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import work_monitor


class CodexSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = work_monitor.MonitorConfig(
            enabled=True,
            interval_seconds=30,
            idle_seconds=600,
            lookback_hours=24,
            max_files_per_provider=40,
            summary_max_chars=180,
            include_summary=True,
            completion_cooldown_seconds=3600,
            provider_completion_cooldown_seconds=300,
        )

    def _write_session(
        self,
        sessions_dir: Path,
        session_id: str,
        source: object,
    ) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        events = [
            {
                "timestamp": timestamp,
                "type": "session_meta",
                "payload": {"id": session_id, "source": source},
            },
            {
                "timestamp": timestamp,
                "type": "event_msg",
                "payload": {"type": "agent_message", "message": "Finished work"},
            },
        ]
        path = sessions_dir / f"rollout-{session_id}.jsonl"
        path.write_text(
            "".join(json.dumps(event) + "\n" for event in events),
            encoding="utf-8",
        )

    def test_collects_main_session_and_ignores_subagents(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            sessions_dir = home / ".codex" / "sessions" / "2026" / "07" / "15"
            sessions_dir.mkdir(parents=True)
            self._write_session(sessions_dir, "main-session", "vscode")
            self._write_session(
                sessions_dir,
                "worker-session",
                {
                    "subagent": {
                        "thread_spawn": {
                            "parent_thread_id": "main-session",
                            "depth": 1,
                            "agent_path": "/root/worker",
                        }
                    }
                },
            )
            self._write_session(
                sessions_dir,
                "guardian-session",
                {"subagent": {"other": "guardian"}},
            )

            with mock.patch.object(work_monitor.Path, "home", return_value=home):
                snapshots = work_monitor.collect_codex_snapshots(self.config)

        self.assertEqual(set(snapshots), {"Codex:main-session"})


class MonitorConfigTests(unittest.TestCase):
    def test_completion_summary_is_disabled_by_default(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertFalse(work_monitor.load_config().include_summary)

    def test_completion_summary_requires_explicit_opt_in(self) -> None:
        with mock.patch.dict("os.environ", {"WORK_INCLUDE_SUMMARY": "1"}, clear=True):
            self.assertTrue(work_monitor.load_config().include_summary)

    def test_completion_summary_can_be_disabled(self) -> None:
        with mock.patch.dict("os.environ", {"WORK_INCLUDE_SUMMARY": "0"}, clear=True):
            self.assertFalse(work_monitor.load_config().include_summary)


if __name__ == "__main__":
    unittest.main()
