from __future__ import annotations

import json
import locale
import math
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9 fallback
    ZoneInfo = None  # type: ignore[assignment]

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - reported clearly at runtime
    load_dotenv = None  # type: ignore[assignment]


SCRIPT_DIR = Path(__file__).resolve().parent
ALERT_STATE_PATH = SCRIPT_DIR / ".alert_state.json"

LANGUAGE_ENV = "AI_USAGE_LANGUAGE"
TIMEZONE_ENV = "AI_USAGE_TIMEZONE"
CLAUDE_PLAN_ENV = "CLAUDE_PLAN"
CLAUDE_5H_TOKEN_LIMIT_ENV = "CLAUDE_5H_TOKEN_LIMIT"
DEFAULT_CLAUDE_PLAN_KEY = "pro"
CLAUDE_CODE_TURN_TOKEN_ESTIMATE = 140_000
CLAUDE_CACHE_READ_WEIGHT = 0.10
CLAUDE_CACHE_CREATION_WEIGHT = 2.0
CLAUDE_OUTPUT_WEIGHT = 5.0

MESSAGES: dict[str, dict[str, str]] = {
    "ko": {
        "report_title": "AI 사용량 리포트",
        "footer_note": (
            "Codex 퍼센티지는 최신 rate_limits 이벤트 기준입니다. "
            "Claude Code 퍼센티지는 캐시 토큰을 할인 반영한 5시간 환산 토큰 추정치입니다. "
            "정확한 Claude 사용률은 Claude 앱 /usage에서 확인하세요."
        ),
        "dry_run": "테스트 출력",
        "unknown": "알 수 없음",
        "no_data": "데이터 없음",
        "expired_data": "데이터 만료됨",
        "no_usage_name": "사용량 데이터 없음",
        "no_usage_value": "이 PC에서 Claude Code / Codex CLI 로그를 찾지 못했습니다.",
        "no_usage_console": "사용량 데이터 없음: Claude Code / Codex CLI 로그를 찾지 못했습니다.",
        "codex_quota": "Codex 할당량",
        "claude_code": "Claude Code",
        "plan_line": "요금제: {plan}",
        "plan_line_default": "요금제: {plan} (기본 추정값)",
        "plan_line_estimated": "요금제: {plan} (추정 기준)",
        "codex_5h": "5시간 창: {value}",
        "codex_weekly": "주간 창: {value}",
        "remaining": "{percent} 남음",
        "reset_unknown": "재설정 알 수 없음",
        "reset_in_minutes": "{minutes}분 후 재설정",
        "reset_at": "{time} 재설정",
        "claude_5h_estimate": "5시간 추정: {percent} 남음 (환산 {used} / 약 {limit} 토큰 사용)",
        "claude_5h_no_limit": "5시간 추정: 토큰 한계값 없음 (환산 {used} 토큰 사용)",
        "claude_today": "오늘: {tokens} 토큰",
        "claude_all": "전체: {tokens} 토큰",
        "claude_exact_usage": "정확한 사용률: Claude 앱 /usage에서 확인",
        "command_not_allowed": "이 위치에서는 !usage 명령을 사용할 수 없습니다.",
        "command_error": "명령 처리 중 오류가 발생했습니다. 봇 로그를 확인하세요.",
        "work_summary_unknown": "작업 요약을 찾지 못했습니다.",
        "work_monitor_disabled": "작업 감시가 비활성화되어 있습니다.",
        "work_status_idle": "대기중입니다.",
        "work_status_active": "작업중입니다.",
        "work_status_active_line": "- {provider}: {duration}째 작업중",
        "work_status_active_line_with_summary": "- {provider}: {duration}째 작업중\n  요약: {summary}",
        "work_status_last_completed": "마지막 완료: {provider}, {ago} 전",
        "work_status_last_completed_with_summary": "마지막 완료: {provider}, {ago} 전\n요약: {summary}",
        "work_completed_title": "LLM 작업 완료",
        "work_failed_title": "LLM 작업 실패",
        "work_completed_provider": "도구",
        "work_completed_duration": "작업 시간",
        "work_completed_tokens": "작업 토큰",
        "work_completed_summary": "요약",
        "work_completed_content": "✅ LLM 작업 완료: {summary}",
        "work_completed_content_safe": "✅ LLM 작업 완료",
        "work_failed_content_safe": "⚠️ LLM 작업 실패",
        "tray_status_running": "상태: 봇 실행 중",
        "tray_status_stopped": "상태: 봇 중지됨",
        "tray_start_bot": "봇 시작",
        "tray_stop_bot": "봇 중지",
        "tray_restart_bot": "봇 재시작",
        "tray_open_logs": "로그 열기",
        "tray_startup_toggle": "Windows 시작 시 실행",
        "tray_quit": "종료",
        "tray_bot_started": "봇을 시작했습니다.",
        "tray_bot_already_running": "봇이 이미 실행 중입니다.",
        "tray_bot_stopped": "봇을 중지했습니다.",
        "tray_bot_already_stopped": "실행 중인 봇이 없습니다.",
        "tray_bot_restarted": "봇을 재시작했습니다.",
        "tray_startup_enabled": "Windows 시작 시 자동 실행을 켰습니다.",
        "tray_startup_disabled": "Windows 시작 시 자동 실행을 껐습니다.",
        "tray_startup_failed": "시작프로그램 설정을 바꾸지 못했습니다. 로그를 확인하세요.",
        "alert_window_primary": "5시간",
        "alert_window_secondary": "주간",
        "alert_window_fallback": "Codex",
        "alert_exhausted": "⚠️ Codex {windows} 할당량 소진",
        "requests_missing": "requests가 설치되어 있지 않습니다. 실행: python -m pip install -r requirements.txt",
        "webhook_http_error": "HTTP {status_code} 응답 오류",
        "webhook_connection_error": "연결 오류",
        "webhook_timeout": "시간 초과",
        "webhook_send_error": "전송 오류",
        "truncated": "\n... 생략됨",
    },
    "en": {
        "report_title": "AI Usage Report",
        "footer_note": (
            "Codex percentages come from the latest rate_limits event. "
            "Claude Code percentages are 5-hour weighted-token estimates with discounted cache tokens. "
            "Check exact Claude usage in the Claude app with /usage."
        ),
        "dry_run": "Dry run",
        "unknown": "Unknown",
        "no_data": "No data",
        "expired_data": "Expired data",
        "no_usage_name": "No usage data",
        "no_usage_value": "No local Claude Code / Codex CLI logs were found on this PC.",
        "no_usage_console": "No usage data: no local Claude Code / Codex CLI logs were found.",
        "codex_quota": "Codex quota",
        "claude_code": "Claude Code",
        "plan_line": "Plan: {plan}",
        "plan_line_default": "Plan: {plan} (default estimate)",
        "plan_line_estimated": "Plan: {plan} (estimate basis)",
        "codex_5h": "5-hour window: {value}",
        "codex_weekly": "Weekly window: {value}",
        "remaining": "{percent} remaining",
        "reset_unknown": "Reset unknown",
        "reset_in_minutes": "resets in {minutes} min",
        "reset_at": "resets {time}",
        "claude_5h_estimate": "5h estimate: {percent} remaining ({used} / ~{limit} weighted tokens used)",
        "claude_5h_no_limit": "5h estimate: no token limit configured ({used} weighted tokens used)",
        "claude_today": "Today: {tokens} tokens",
        "claude_all": "All time: {tokens} tokens",
        "claude_exact_usage": "Exact usage: check /usage in the Claude app",
        "command_not_allowed": "The !usage command is not allowed here.",
        "command_error": "An error occurred while handling the command. Check the bot logs.",
        "work_summary_unknown": "No work summary was found.",
        "work_monitor_disabled": "Work monitoring is disabled.",
        "work_status_idle": "Idle.",
        "work_status_active": "Working.",
        "work_status_active_line": "- {provider}: working for {duration}",
        "work_status_active_line_with_summary": "- {provider}: working for {duration}\n  Summary: {summary}",
        "work_status_last_completed": "Last completed: {provider}, {ago} ago",
        "work_status_last_completed_with_summary": "Last completed: {provider}, {ago} ago\nSummary: {summary}",
        "work_completed_title": "LLM Work Completed",
        "work_failed_title": "LLM Work Failed",
        "work_completed_provider": "Tool",
        "work_completed_duration": "Duration",
        "work_completed_tokens": "Task tokens",
        "work_completed_summary": "Summary",
        "work_completed_content": "✅ LLM work completed: {summary}",
        "work_completed_content_safe": "✅ LLM work completed",
        "work_failed_content_safe": "⚠️ LLM work failed",
        "tray_status_running": "Status: bot running",
        "tray_status_stopped": "Status: bot stopped",
        "tray_start_bot": "Start bot",
        "tray_stop_bot": "Stop bot",
        "tray_restart_bot": "Restart bot",
        "tray_open_logs": "Open logs",
        "tray_startup_toggle": "Run at Windows sign-in",
        "tray_quit": "Quit",
        "tray_bot_started": "Bot started.",
        "tray_bot_already_running": "Bot is already running.",
        "tray_bot_stopped": "Bot stopped.",
        "tray_bot_already_stopped": "No bot is running.",
        "tray_bot_restarted": "Bot restarted.",
        "tray_startup_enabled": "Run at sign-in enabled.",
        "tray_startup_disabled": "Run at sign-in disabled.",
        "tray_startup_failed": "Could not update the startup setting. Check the logs.",
        "alert_window_primary": "5-hour",
        "alert_window_secondary": "weekly",
        "alert_window_fallback": "Codex",
        "alert_exhausted": "⚠️ Codex {windows} quota exhausted",
        "requests_missing": "requests is not installed. Run: python -m pip install -r requirements.txt",
        "webhook_http_error": "HTTP {status_code} response error",
        "webhook_connection_error": "connection error",
        "webhook_timeout": "timeout",
        "webhook_send_error": "send error",
        "truncated": "\n... truncated",
    },
}


@dataclass(frozen=True)
class ClaudePlan:
    key: str
    display_ko: str
    display_en: str
    five_hour_token_limit: int | None


# Anthropic publishes message guidance rather than exact token caps. These
# defaults use a /usage calibration: 54% of a Claude Pro 5-hour window was
# approximately 3.4M weighted tokens. Cache writes use 2.0x because that best
# matches the Claude Code cost breakdown for 1-hour cache creation.
CLAUDE_PLANS: dict[str, ClaudePlan] = {
    "free": ClaudePlan("free", "Free", "Free", 1_260_000),
    "pro": ClaudePlan("pro", "Pro", "Pro", 6_300_000),
    "max_5x": ClaudePlan("max_5x", "Max 5x", "Max 5x", 31_500_000),
    "max_20x": ClaudePlan("max_20x", "Max 20x", "Max 20x", 126_000_000),
    "team": ClaudePlan("team", "Team", "Team", None),
    "enterprise": ClaudePlan("enterprise", "Enterprise", "Enterprise", None),
    "unknown": ClaudePlan("unknown", "알 수 없음", "Unknown", None),
}

CLAUDE_PLAN_ALIASES = {
    "free": "free",
    "claude_free": "free",
    "pro": "pro",
    "claude_pro": "pro",
    "max": "max_5x",
    "max5": "max_5x",
    "max_5": "max_5x",
    "max_5x": "max_5x",
    "max-5x": "max_5x",
    "max 5x": "max_5x",
    "max20": "max_20x",
    "max_20": "max_20x",
    "max_20x": "max_20x",
    "max-20x": "max_20x",
    "max 20x": "max_20x",
    "team": "team",
    "enterprise": "enterprise",
    "unknown": "unknown",
    "none": "unknown",
}


@dataclass
class ClaudeTotals:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    def add(self, other: "ClaudeTotals") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_creation_input_tokens += other.cache_creation_input_tokens
        self.cache_read_input_tokens += other.cache_read_input_tokens

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
        )

    @property
    def weighted_quota_tokens(self) -> int:
        return round(
            self.input_tokens
            + (self.output_tokens * CLAUDE_OUTPUT_WEIGHT)
            + (self.cache_creation_input_tokens * CLAUDE_CACHE_CREATION_WEIGHT)
            + (self.cache_read_input_tokens * CLAUDE_CACHE_READ_WEIGHT)
        )


@dataclass
class ClaudeAggregate:
    periods: dict[str, ClaudeTotals] = field(
        default_factory=lambda: {
            "5h": ClaudeTotals(),
            "today": ClaudeTotals(),
            "7d": ClaudeTotals(),
            "all": ClaudeTotals(),
        }
    )
    by_model: dict[str, dict[str, ClaudeTotals]] = field(
        default_factory=lambda: {"5h": {}, "today": {}, "7d": {}, "all": {}}
    )
    files_seen: int = 0
    usage_events: int = 0


@dataclass
class CodexTotals:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0
    total_tokens: int = 0

    def add(self, other: "CodexTotals") -> None:
        self.input_tokens += other.input_tokens
        self.cached_input_tokens += other.cached_input_tokens
        self.output_tokens += other.output_tokens
        self.reasoning_output_tokens += other.reasoning_output_tokens
        self.total_tokens += other.total_tokens


@dataclass
class CodexAggregate:
    totals: CodexTotals = field(default_factory=CodexTotals)
    files_seen: int = 0
    sessions_counted: int = 0
    token_events: int = 0
    latest_rate_limits: dict[str, Any] | None = None
    latest_rate_limit_sort_key: tuple[float, int, int] | None = None


@dataclass
class UsageSnapshot:
    claude: ClaudeAggregate
    codex: CodexAggregate
    now_local: datetime


def load_environment() -> None:
    if load_dotenv is not None:
        load_dotenv(SCRIPT_DIR / ".env", encoding="utf-8")


def _normalize_env_value(value: str) -> str:
    return value.strip().lower().replace("-", "_")


def detect_report_language() -> str:
    configured = _normalize_env_value(os.getenv(LANGUAGE_ENV, ""))
    if configured in {"ko", "kr", "korean"}:
        return "ko"
    if configured in {"en", "english"}:
        return "en"

    locale_candidates = [
        os.getenv("LC_ALL", ""),
        os.getenv("LC_MESSAGES", ""),
        os.getenv("LANG", ""),
    ]
    try:
        locale_candidates.append(locale.getlocale()[0] or "")
    except (TypeError, ValueError):
        pass
    try:
        locale_candidates.append(locale.getdefaultlocale()[0] or "")
    except (TypeError, ValueError):
        pass

    timezone_name = datetime.now().astimezone().tzname() or ""
    locale_candidates.append(timezone_name)

    for candidate in locale_candidates:
        lowered = candidate.lower()
        if (
            lowered.startswith("ko")
            or "korean" in lowered
            or "korea" in lowered
            or "seoul" in lowered
            or "대한민국" in lowered
            or "한국" in lowered
            or lowered == "kst"
        ):
            return "ko"

    return "en"


def translate(key: str, **kwargs: Any) -> str:
    lang = detect_report_language()
    template = MESSAGES.get(lang, MESSAGES["en"]).get(key, MESSAGES["en"].get(key, key))
    return template.format(**kwargs) if kwargs else template


def get_report_timezone():
    configured = os.getenv(TIMEZONE_ENV, "").strip()
    if configured and configured.lower() != "auto" and ZoneInfo is not None:
        try:
            return ZoneInfo(configured)
        except Exception:
            pass

    return datetime.now().astimezone().tzinfo or timezone.utc


def safe_int(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_timestamp(value: Any) -> datetime | None:
    report_tz = get_report_timezone()
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).astimezone(
                report_tz
            )
        except (OSError, OverflowError, ValueError):
            return None

    if not isinstance(value, str) or not value.strip():
        return None

    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"

    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(report_tz)


def format_number(value: int) -> str:
    return f"{value:,}"


def format_percent_value(value: float | None) -> str:
    if value is None:
        return translate("unknown")
    return f"{value:.1f}%"


def format_report_timestamp(value: datetime) -> str:
    dt = value.astimezone(get_report_timezone())
    if detect_report_language() == "ko":
        ampm = "오전" if dt.hour < 12 else "오후"
        hour = dt.hour % 12
        if hour == 0:
            hour = 12
        return f"{dt.month}/{dt.day} {ampm} {hour}:{dt.minute:02d}"

    hour = dt.hour % 12
    if hour == 0:
        hour = 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{dt.month}/{dt.day} {hour}:{dt.minute:02d} {ampm}"


def format_clock_time(value: datetime) -> str:
    dt = value.astimezone(get_report_timezone())
    return f"{dt.month}/{dt.day} {dt.hour:02d}:{dt.minute:02d}"


def format_report_title(now_local: datetime) -> str:
    return f"{translate('report_title')} • {format_report_timestamp(now_local)}"


def format_reset_at(value: Any, now_local: datetime) -> str:
    dt = parse_timestamp(value)
    if dt is None:
        return translate("reset_unknown")

    seconds = (dt - now_local).total_seconds()
    if seconds <= 60 * 60:
        minutes = max(0, math.ceil(seconds / 60))
        return translate("reset_in_minutes", minutes=minutes)

    return translate("reset_at", time=format_clock_time(dt))


def remaining_percent_from_limit(limit: Any) -> float | None:
    if not isinstance(limit, dict):
        return None

    used = safe_float(limit.get("used_percent"))
    if used is None:
        return None
    return max(0.0, 100.0 - used)


def get_codex_limit(codex: CodexAggregate, window: str) -> Any:
    rate_limits = codex.latest_rate_limits or {}
    if not isinstance(rate_limits, dict):
        return None
    return rate_limits.get(window)


def codex_limit_is_stale(limit: Any, now_local: datetime) -> bool:
    if not isinstance(limit, dict):
        return False

    reset_at = parse_timestamp(limit.get("resets_at"))
    if reset_at is None:
        return False

    if now_local.tzinfo is None:
        now_local = now_local.replace(tzinfo=get_report_timezone())
    return reset_at <= now_local.astimezone(reset_at.tzinfo)


def get_codex_remaining_percent(
    codex: CodexAggregate,
    window: str,
    now_local: datetime | None = None,
) -> float | None:
    limit = get_codex_limit(codex, window)
    if now_local is not None and codex_limit_is_stale(limit, now_local):
        return None
    return remaining_percent_from_limit(limit)


def add_claude_period(
    aggregate: ClaudeAggregate,
    period: str,
    model: str,
    totals: ClaudeTotals,
) -> None:
    aggregate.periods[period].add(totals)
    model_totals = aggregate.by_model[period].setdefault(model, ClaudeTotals())
    model_totals.add(totals)


def read_jsonl(path: Path):
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, start=1):
                text = line.strip()
                if not text:
                    continue
                try:
                    yield line_number, json.loads(text)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return


def aggregate_claude(now_local: datetime) -> ClaudeAggregate:
    aggregate = ClaudeAggregate()
    base_dir = Path.home() / ".claude" / "projects"
    today = now_local.date()
    seven_day_start = today - timedelta(days=6)
    five_hour_start = now_local - timedelta(hours=5)

    files = sorted(base_dir.glob("**/*.jsonl")) if base_dir.exists() else []
    aggregate.files_seen = len(files)

    for path in files:
        for _, obj in read_jsonl(path):
            if not isinstance(obj, dict):
                continue

            message = obj.get("message")
            if not isinstance(message, dict) or "usage" not in message:
                continue

            usage = message.get("usage")
            if not isinstance(usage, dict):
                continue

            totals = ClaudeTotals(
                input_tokens=safe_int(usage.get("input_tokens")),
                output_tokens=safe_int(usage.get("output_tokens")),
                cache_creation_input_tokens=safe_int(
                    usage.get("cache_creation_input_tokens")
                ),
                cache_read_input_tokens=safe_int(usage.get("cache_read_input_tokens")),
            )
            model = str(message.get("model") or "unknown")
            aggregate.usage_events += 1

            add_claude_period(aggregate, "all", model, totals)

            timestamp = parse_timestamp(obj.get("timestamp"))
            if timestamp is None:
                continue

            bucket_date = timestamp.date()
            if five_hour_start <= timestamp <= now_local:
                add_claude_period(aggregate, "5h", model, totals)
            if bucket_date == today:
                add_claude_period(aggregate, "today", model, totals)
            if seven_day_start <= bucket_date <= today:
                add_claude_period(aggregate, "7d", model, totals)

    return aggregate


def codex_totals_from_usage(usage: dict[str, Any]) -> CodexTotals:
    return CodexTotals(
        input_tokens=safe_int(usage.get("input_tokens")),
        cached_input_tokens=safe_int(usage.get("cached_input_tokens")),
        output_tokens=safe_int(usage.get("output_tokens")),
        reasoning_output_tokens=safe_int(usage.get("reasoning_output_tokens")),
        total_tokens=safe_int(usage.get("total_tokens")),
    )


def token_event_sort_key(
    obj: dict[str, Any],
    path: Path,
    file_index: int,
    line_number: int,
) -> tuple[float, int, int]:
    timestamp = (
        parse_timestamp(obj.get("timestamp"))
        or parse_timestamp(obj.get("created_at"))
        or parse_timestamp(obj.get("time"))
    )
    if timestamp is not None:
        return (timestamp.timestamp(), file_index, line_number)

    try:
        return (path.stat().st_mtime, file_index, line_number)
    except OSError:
        return (0.0, file_index, line_number)


def aggregate_codex() -> CodexAggregate:
    aggregate = CodexAggregate()
    base_dir = Path.home() / ".codex" / "sessions"
    files = sorted(base_dir.glob("**/rollout-*.jsonl")) if base_dir.exists() else []
    aggregate.files_seen = len(files)

    for file_index, path in enumerate(files):
        last_session_totals: CodexTotals | None = None

        for line_number, obj in read_jsonl(path):
            if not isinstance(obj, dict):
                continue

            payload = obj.get("payload")
            if (
                obj.get("type") != "event_msg"
                or not isinstance(payload, dict)
                or payload.get("type") != "token_count"
            ):
                continue

            rate_limits = payload.get("rate_limits")
            if isinstance(rate_limits, dict):
                sort_key = token_event_sort_key(obj, path, file_index, line_number)
                if (
                    aggregate.latest_rate_limit_sort_key is None
                    or sort_key > aggregate.latest_rate_limit_sort_key
                ):
                    aggregate.latest_rate_limit_sort_key = sort_key
                    aggregate.latest_rate_limits = rate_limits

            info = payload.get("info")
            if not isinstance(info, dict):
                continue
            usage = info.get("total_token_usage")
            if not isinstance(usage, dict):
                continue

            aggregate.token_events += 1
            last_session_totals = codex_totals_from_usage(usage)

        if last_session_totals is not None:
            aggregate.sessions_counted += 1
            aggregate.totals.add(last_session_totals)

    return aggregate


def collect_usage(now_local: datetime | None = None) -> UsageSnapshot:
    report_tz = get_report_timezone()
    if now_local is None:
        now_local = datetime.now(timezone.utc).astimezone(report_tz)
    else:
        now_local = now_local.astimezone(report_tz)
    return UsageSnapshot(
        claude=aggregate_claude(now_local),
        codex=aggregate_codex(),
        now_local=now_local,
    )


def selected_periods(period: str | None) -> list[str]:
    if period is not None:
        return [period]
    return ["today", "7d", "all"]


def configured_claude_plan() -> tuple[ClaudePlan, bool]:
    raw = os.getenv(CLAUDE_PLAN_ENV, "").strip()
    defaulted = not raw
    normalized = _normalize_env_value(raw) if raw else DEFAULT_CLAUDE_PLAN_KEY
    plan_key = CLAUDE_PLAN_ALIASES.get(normalized, normalized)

    if plan_key in CLAUDE_PLANS:
        return CLAUDE_PLANS[plan_key], defaulted

    custom_name = raw.strip() or plan_key
    return ClaudePlan("custom", custom_name, custom_name, None), defaulted


def claude_plan_display(plan: ClaudePlan) -> str:
    if detect_report_language() == "ko":
        return plan.display_ko
    return plan.display_en


def configured_claude_token_limit(plan: ClaudePlan) -> int | None:
    override = safe_int(os.getenv(CLAUDE_5H_TOKEN_LIMIT_ENV))
    if override > 0:
        return override
    return plan.five_hour_token_limit


def claude_remaining_percent(used_tokens: int, limit_tokens: int | None) -> float | None:
    if not limit_tokens or limit_tokens <= 0:
        return None
    return max(0.0, 100.0 - (used_tokens / limit_tokens * 100.0))


def format_claude_token_totals(aggregate: ClaudeAggregate) -> str:
    return "\n".join(claude_quota_lines(aggregate))


def format_codex_rate_limit(limit: Any, now_local: datetime) -> str:
    if not isinstance(limit, dict):
        return translate("no_data")
    if codex_limit_is_stale(limit, now_local):
        return translate("expired_data")

    remaining = remaining_percent_from_limit(limit)
    remaining_text = translate("remaining", percent=format_percent_value(remaining))
    reset_text = format_reset_at(limit.get("resets_at"), now_local)
    return f"{remaining_text}, {reset_text}"


def codex_quota_lines(aggregate: CodexAggregate, now_local: datetime) -> list[str]:
    rate_limits = aggregate.latest_rate_limits or {}
    plan_type = rate_limits.get("plan_type") if isinstance(rate_limits, dict) else None
    primary = rate_limits.get("primary") if isinstance(rate_limits, dict) else None
    secondary = rate_limits.get("secondary") if isinstance(rate_limits, dict) else None
    return [
        translate("plan_line", plan=plan_type or translate("unknown")),
        translate("codex_5h", value=format_codex_rate_limit(primary, now_local)),
        translate("codex_weekly", value=format_codex_rate_limit(secondary, now_local)),
    ]


def claude_quota_lines(aggregate: ClaudeAggregate) -> list[str]:
    plan, defaulted = configured_claude_plan()
    plan_display = claude_plan_display(plan)
    plan_key = "plan_line_default" if defaulted else "plan_line_estimated"
    limit = configured_claude_token_limit(plan)
    five_hour_tokens = aggregate.periods["5h"].weighted_quota_tokens
    remaining = claude_remaining_percent(five_hour_tokens, limit)

    lines = [translate(plan_key, plan=plan_display)]
    if limit:
        lines.append(
            translate(
                "claude_5h_estimate",
                percent=format_percent_value(remaining),
                used=format_number(five_hour_tokens),
                limit=format_number(limit),
            )
        )
    else:
        lines.append(
            translate(
                "claude_5h_no_limit",
                used=format_number(five_hour_tokens),
            )
        )

    today_tokens = aggregate.periods["today"].total_tokens
    all_tokens = aggregate.periods["all"].total_tokens
    lines.extend(
        [
            translate("claude_today", tokens=format_number(today_tokens)),
            translate("claude_all", tokens=format_number(all_tokens)),
            translate("claude_exact_usage"),
        ]
    )
    return lines


def format_codex_console(snapshot: UsageSnapshot) -> list[str]:
    return [
        translate("codex_quota"),
        *(f"  {line}" for line in codex_quota_lines(snapshot.codex, snapshot.now_local)),
    ]


def format_claude_console(snapshot: UsageSnapshot) -> list[str]:
    return [
        translate("claude_code"),
        *(f"  {line}" for line in claude_quota_lines(snapshot.claude)),
    ]


def truncate_for_embed(value: str, limit: int = 1024) -> str:
    if len(value) <= limit:
        return value
    suffix = translate("truncated")
    return value[: limit - len(suffix)].rstrip() + suffix


def codex_embed_value(snapshot: UsageSnapshot) -> str:
    return truncate_for_embed("\n".join(codex_quota_lines(snapshot.codex, snapshot.now_local)))


def claude_embed_value(snapshot: UsageSnapshot) -> str:
    return truncate_for_embed("\n".join(claude_quota_lines(snapshot.claude)))


# 사용 중인 도구만 출력한다. 로컬 로그에서 실제 데이터가 잡힌 provider만 포함한다.
# 배포 대상 PC마다 설치 도구가 다르므로 자동 탐지한다. Claude Code/Codex CLI만
# 로컬에 토큰을 남기며, Gemini/Grok/데스크톱 앱은 사용량이 서버 측이라 표시할 수 없다.
def claude_present(aggregate: ClaudeAggregate) -> bool:
    return aggregate.usage_events > 0


def codex_present(aggregate: CodexAggregate) -> bool:
    return aggregate.token_events > 0 or aggregate.latest_rate_limits is not None


def build_report_embeds(snapshot: UsageSnapshot) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    if codex_present(snapshot.codex):
        fields.append(
            {"name": translate("codex_quota"), "value": codex_embed_value(snapshot), "inline": False}
        )
    if claude_present(snapshot.claude):
        fields.append(
            {"name": translate("claude_code"), "value": claude_embed_value(snapshot), "inline": False}
        )
    if not fields:
        fields.append(
            {
                "name": translate("no_usage_name"),
                "value": translate("no_usage_value"),
                "inline": False,
            }
        )
    return [
        {
            "title": format_report_title(snapshot.now_local),
            "color": 0x5865F2,
            "fields": fields,
            "footer": {"text": translate("footer_note")},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    ]


def build_report_text(snapshot: UsageSnapshot, *, dry_run: bool = False) -> str:
    lines = [format_report_title(snapshot.now_local)]
    if dry_run:
        lines.append(translate("dry_run"))

    sections: list[list[str]] = []
    if codex_present(snapshot.codex):
        sections.append(format_codex_console(snapshot))
    if claude_present(snapshot.claude):
        sections.append(format_claude_console(snapshot))
    if not sections:
        sections.append([translate("no_usage_console")])

    for section in sections:
        lines.append("")
        lines.extend(section)
    lines.extend(["", translate("footer_note")])
    return "\n".join(lines)


def build_alert_header(windows: list[str]) -> str:
    labels = {
        "primary": translate("alert_window_primary"),
        "secondary": translate("alert_window_secondary"),
    }
    selected = [labels[window] for window in windows if window in labels]
    if not selected:
        selected = [translate("alert_window_fallback")]
    return translate("alert_exhausted", windows="/".join(selected))


def send_webhook(
    webhook_url: str,
    embeds: list[dict[str, Any]],
    *,
    content: str | None = None,
) -> None:
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError(translate("requests_missing")) from exc

    payload: dict[str, Any] = {"embeds": embeds, "allowed_mentions": {"parse": []}}
    if content:
        payload["content"] = content
    response = requests.post(webhook_url, json=payload, timeout=30)
    response.raise_for_status()


def safe_webhook_error(exc: Exception) -> str:
    if isinstance(exc, RuntimeError):
        return str(exc)

    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code is not None:
        return translate("webhook_http_error", status_code=status_code)

    error_name = type(exc).__name__
    if error_name == "ConnectionError":
        return translate("webhook_connection_error")
    if error_name == "Timeout":
        return translate("webhook_timeout")

    return translate("webhook_send_error")


def load_alert_state(path: Path = ALERT_STATE_PATH) -> dict[str, bool]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(raw, dict):
        return {}
    return {key: bool(raw.get(key)) for key in ("primary", "secondary")}


def save_alert_state(state: dict[str, bool], path: Path = ALERT_STATE_PATH) -> None:
    normalized = {key: bool(state.get(key)) for key in ("primary", "secondary")}
    serialized = json.dumps(normalized, ensure_ascii=False, indent=2) + "\n"
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except OSError:
                pass
