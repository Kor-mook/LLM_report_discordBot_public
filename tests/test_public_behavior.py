from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import llm_report_tray
import work_monitor


class LogBasedCompletionTests(unittest.TestCase):
    def test_completion_uses_log_activity_without_counting_the_idle_wait(self) -> None:
        now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        started = now - timedelta(seconds=900)
        last_activity = now - timedelta(seconds=650)
        with mock.patch.dict(os.environ, {}, clear=True):
            config = work_monitor.load_config()
        monitor = work_monitor.WorkMonitor(config)
        monitor._seeded = True
        monitor.active['Codex:session'] = work_monitor.ActiveWork(
            key='Codex:session', provider='Codex', session_id='session',
            source_path='synthetic-session.jsonl', started_at=started,
            last_activity_at=last_activity, summary='Finished a synthetic task',
            token_total=321,
        )
        with (
            mock.patch.object(work_monitor, 'utc_now', return_value=now),
            mock.patch.object(work_monitor, 'collect_work_snapshots', return_value={}),
            mock.patch.object(monitor.event_watcher, 'poll', return_value=[]),
        ):
            completed = monitor.poll()
            self.assertEqual(monitor.poll(), [])
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0].completed_at, last_activity)
        self.assertEqual(completed[0].duration_seconds, 250)
        self.assertEqual(completed[0].token_total, 321)

    def test_codex_token_total_is_read_directly_from_a_synthetic_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            sessions = home / '.codex' / 'sessions'
            sessions.mkdir(parents=True)
            now = datetime.now(timezone.utc)
            events = [
                {'timestamp': now.isoformat(), 'type': 'session_meta',
                 'payload': {'id': 'sample-session', 'source': 'cli'}},
                {'timestamp': now.isoformat(), 'type': 'event_msg',
                 'payload': {'type': 'token_count', 'info': {'total_token_usage': {
                     'input_tokens': 10, 'output_tokens': 20, 'total_tokens': 30}}}},
                {'timestamp': (now + timedelta(seconds=2)).isoformat(),
                 'type': 'event_msg', 'payload': {
                     'type': 'agent_message', 'message': 'Synthetic completion'}},
            ]
            (sessions / 'rollout-sample.jsonl').write_text(
                '\n'.join(json.dumps(event) for event in events), encoding='utf-8')
            with (
                mock.patch.dict(os.environ, {}, clear=True),
                mock.patch.object(work_monitor.Path, 'home', return_value=home),
            ):
                snapshots = work_monitor.collect_codex_snapshots(work_monitor.load_config())
            item = snapshots['Codex:sample-session']
            self.assertEqual(item.token_total, 30)
            self.assertEqual(item.summary, 'Synthetic completion')


class TrayBehaviorTests(unittest.TestCase):
    def test_start_stop_restart_and_exit_remain_available(self) -> None:
        menu_items = []

        def make_item(text, action, **kwargs):
            item = SimpleNamespace(text=text, action=action, **kwargs)
            menu_items.append(item)
            return item

        def make_menu(*items):
            return items

        make_menu.SEPARATOR = object()
        icon = mock.MagicMock()
        fake_pystray = SimpleNamespace(Menu=make_menu, MenuItem=make_item,
                                       Icon=mock.Mock(return_value=icon))

        def run_icon(*, setup):
            setup(icon)
            actions = {item.text: item.action for item in menu_items}
            actions['tray_start_bot'](icon, None)
            actions['tray_stop_bot'](icon, None)
            actions['tray_restart_bot'](icon, None)
            actions['tray_quit'](icon, None)

        icon.run.side_effect = run_icon
        with (
            mock.patch.dict(sys.modules, {'pystray': fake_pystray}),
            mock.patch.object(llm_report_tray, 'configure_logging'),
            mock.patch.object(llm_report_tray.llm_report_core, 'load_environment'),
            mock.patch.object(llm_report_tray.llm_report_core, 'translate', side_effect=lambda key: key),
            mock.patch.object(llm_report_tray, '_claim_tray_instance', return_value=True),
            mock.patch.object(llm_report_tray, '_release_tray_instance'),
            mock.patch.object(llm_report_tray, 'create_tray_icon_image', return_value=None),
            mock.patch.object(llm_report_tray, 'BotSupervisor') as supervisor_class,
            mock.patch.object(llm_report_tray.resume_worker, 'ResumeWorker') as worker_class,
            mock.patch.object(llm_report_tray.threading, 'Thread') as thread_class,
        ):
            self.assertEqual(llm_report_tray.main(), 0)
        supervisor = supervisor_class.return_value
        self.assertEqual(supervisor.start.call_count, 2)
        supervisor.restart.assert_called_once()
        self.assertGreaterEqual(supervisor.stop.call_count, 2)
        worker_class.return_value.stop.assert_called()
        thread_class.return_value.start.assert_called_once()
        defaults = [item for item in menu_items if getattr(item, 'default', False)]
        self.assertEqual([item.text for item in defaults], ['tray_open_logs'])
        icon.stop.assert_called_once()


if __name__ == '__main__':
    unittest.main()
