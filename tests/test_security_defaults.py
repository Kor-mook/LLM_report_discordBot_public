from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

import llm_report_bot
import llm_report_core
import resume_worker


class AccessControlTests(unittest.TestCase):
    def check(self, users, channels, *, user=1, channel=10):
        return llm_report_bot.is_allowed(user_id=user, channel_id=channel,
                                        allowed_user_ids=users, allowed_channel_ids=channels)

    def test_empty_user_allowlist_denies_access(self):
        self.assertFalse(self.check(set(), set()))
        self.assertFalse(self.check(set(), {10}))

    def test_only_listed_users_are_allowed(self):
        self.assertTrue(self.check({1}, set()))
        self.assertFalse(self.check({2}, set()))

    def test_channel_restriction_also_applies(self):
        self.assertTrue(self.check({1}, {10}))
        self.assertFalse(self.check({1}, {20}))

    def test_invalid_id_lists_are_rejected(self):
        for value in ('abc', '1,abc', '0', '-1', '1.5', '１２３'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                llm_report_bot.parse_id_set(value)
        self.assertEqual(llm_report_bot.parse_id_set('1, 2, ,1'), {1, 2})

    def test_missing_allowlist_stops_before_discord_login(self):
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(llm_report_core, 'load_environment'),
            mock.patch.object(llm_report_bot, 'setup_logging'),
            mock.patch.object(llm_report_bot, 'claim_bot_instance') as claim,
        ):
            self.assertEqual(llm_report_bot.main(), 1)
        claim.assert_not_called()


class OutboundDataTests(unittest.TestCase):
    def test_webhook_cannot_trigger_mentions(self):
        response = mock.Mock()
        post = mock.Mock(return_value=response)
        # No real requests dependency is imported and no HTTP request is sent.
        with mock.patch.dict(sys.modules, {'requests': SimpleNamespace(post=post)}):
            llm_report_core.send_webhook('https://example.invalid/webhook', [],
                                         content='@everyone synthetic message')
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['allowed_mentions'], {'parse': []})
        self.assertEqual(post.call_args.kwargs['timeout'], 30)
        response.raise_for_status.assert_called_once()

    def test_resume_queue_does_not_execute_by_default(self):
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(resume_worker.resume_queue, 'take_due_tasks') as take,
            mock.patch.object(resume_worker.subprocess, 'Popen') as launch,
        ):
            resume_worker.ResumeWorker().poll()
        take.assert_not_called()
        launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
