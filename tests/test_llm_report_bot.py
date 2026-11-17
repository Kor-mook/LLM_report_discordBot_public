from __future__ import annotations

import unittest
from datetime import timezone
from unittest import mock

import llm_report_bot
import work_monitor


class CommandHelpTests(unittest.TestCase):
    def test_formats_commands_in_name_order(self) -> None:
        result = llm_report_bot.format_command_help(
            [
                ("usage", "Show usage."),
                ("help", "Show commands."),
                ("work", "Show work status."),
            ]
        )
        self.assertEqual(
            result.splitlines()[1:],
            [
                "`/help` — Show commands.",
                "`/usage` — Show usage.",
                "`/work` — Show work status.",
            ],
        )


class SafeCommandOutputTests(unittest.TestCase):
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

    def test_status_excludes_work_summary(self) -> None:
        result = llm_report_bot.format_bot_status(
            config=self.config,
            uptime_seconds=61,
            active_work_count=2,
            last_completed_provider="Codex",
        )

        self.assertIn("가동 시간: 1분", result)
        self.assertIn("진행 중인 작업: 2개", result)
        self.assertIn("마지막 완료 도구: Codex", result)
        self.assertNotIn("비밀 작업 요약", result)

    def test_settings_shows_useful_values_without_sensitive_details(self) -> None:
        with (
            mock.patch.object(llm_report_bot.llm_report_core, "detect_report_language", return_value="ko"),
            mock.patch.object(llm_report_bot.llm_report_core, "get_report_timezone", return_value=timezone.utc),
            mock.patch.object(
                llm_report_bot.llm_report_core,
                "configured_claude_plan",
                return_value=(llm_report_bot.llm_report_core.CLAUDE_PLANS["pro"], False),
            ),
        ):
            result = llm_report_bot.format_safe_settings(
                self.config,
                usage_webhook_configured=True,
                dedicated_work_webhook_configured=False,
                allowed_user_count=2,
                allowed_channel_count=3,
                resume_queue_enabled=False,
            )

        self.assertIn("언어: ko", result)
        self.assertIn("시간대: UTC", result)
        self.assertIn("Claude 추정 기준: Pro / 6,300,000 토큰", result)
        self.assertIn("확인 주기: 30초", result)
        self.assertIn("완료 판정: 10분 동안 활동 없음", result)
        self.assertIn("로그 탐색: 최근 24시간 / 도구별 최대 40개 파일", result)
        self.assertIn("완료 알림 요약: 켜짐 / 최대 180자", result)
        self.assertIn("재알림 제한: 세션 1시간 / 도구 5분", result)
        self.assertIn("사용량·할당량 웹훅: 설정됨", result)
        self.assertIn("작업 완료 웹훅: 사용량 웹훅 공유", result)
        self.assertIn("허용 사용자: 2명만 허용", result)
        self.assertIn("허용 채널: 3개만 허용", result)
        self.assertIn("복구 큐: 꺼짐", result)
        self.assertIn("봇 토큰, 웹훅 URL, 실제 ID와 파일 경로 값만 숨깁니다.", result)

    def test_settings_calls_out_unrestricted_access_and_missing_webhooks(self) -> None:
        with (
            mock.patch.object(llm_report_bot.llm_report_core, "detect_report_language", return_value="ko"),
            mock.patch.object(llm_report_bot.llm_report_core, "get_report_timezone", return_value=timezone.utc),
            mock.patch.object(
                llm_report_bot.llm_report_core,
                "configured_claude_plan",
                return_value=(llm_report_bot.llm_report_core.CLAUDE_PLANS["pro"], True),
            ),
        ):
            result = llm_report_bot.format_safe_settings(
                self.config,
                usage_webhook_configured=False,
                dedicated_work_webhook_configured=False,
                allowed_user_count=0,
                allowed_channel_count=0,
                resume_queue_enabled=True,
            )

        self.assertIn("Claude 추정 기준: Pro (기본값)", result)
        self.assertIn("사용량·할당량 웹훅: 미설정", result)
        self.assertIn("작업 완료 웹훅: 미설정 (완료 알림 전송 안 함)", result)
        self.assertIn("허용 사용자: 모두 차단 (허용 사용자 미설정)", result)
        self.assertIn("허용 채널: 모두 허용", result)
        self.assertIn("복구 큐: 켜짐", result)

if __name__ == "__main__":
    unittest.main()
