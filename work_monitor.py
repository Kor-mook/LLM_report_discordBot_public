from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import llm_report_core
import work_events


WORK_MONITOR_ENABLED_ENV = "WORK_MONITOR_ENABLED"
WORK_MONITOR_INTERVAL_SECONDS_ENV = "WORK_MONITOR_INTERVAL_SECONDS"
WORK_IDLE_SECONDS_ENV = "WORK_IDLE_SECONDS"
WORK_LOOKBACK_HOURS_ENV = "WORK_LOOKBACK_HOURS"
WORK_MAX_FILES_PER_PROVIDER_ENV = "WORK_MAX_FILES_PER_PROVIDER"
WORK_SUMMARY_MAX_CHARS_ENV = "WORK_SUMMARY_MAX_CHARS"
WORK_INCLUDE_SUMMARY_ENV = "WORK_INCLUDE_SUMMARY"
WORK_COMPLETION_COOLDOWN_SECONDS_ENV = "WORK_COMPLETION_COOLDOWN_SECONDS"
WORK_PROVIDER_COMPLETION_COOLDOWN_SECONDS_ENV = "WORK_PROVIDER_COMPLETION_COOLDOWN_SECONDS"

DEFAULT_INTERVAL_SECONDS = 30
DEFAULT_IDLE_SECONDS = 600
DEFAULT_LOOKBACK_HOURS = 24
DEFAULT_MAX_FILES_PER_PROVIDER = 40
DEFAULT_SUMMARY_MAX_CHARS = 180
DEFAULT_COMPLETION_COOLDOWN_SECONDS = 3600
DEFAULT_PROVIDER_COMPLETION_COOLDOWN_SECONDS = 300

GENERIC_SUMMARY_LINES = {
    "done",
    "done.",
    "completed",
    "completed.",
    "완료",
    "완료.",
    "완료했습니다",
    "완료했습니다.",
    "수정 완료했습니다",
    "수정 완료했습니다.",
    "작업 완료했습니다",
    "작업 완료했습니다.",
    "변경 요약",
    "change summary",
    "summary",
}


@dataclass(frozen=True)
class MonitorConfig:
    enabled: bool
    interval_seconds: int
    idle_seconds: int
    lookback_hours: int
    max_files_per_provider: int
    summary_max_chars: int
    include_summary: bool
    completion_cooldown_seconds: int
    provider_completion_cooldown_seconds: int


@dataclass
class WorkSnapshot:
    key: str
    provider: str
    session_id: str
    source_path: Path
    started_at: datetime
    last_activity_at: datetime
    summary: str
    token_total: int | None = None


@dataclass
class ActiveWork:
    key: str
    provider: str
    session_id: str
    source_path: str
    started_at: datetime
    last_activity_at: datetime
    summary: str
    token_total: int | None = None
    notified: bool = False


@dataclass(frozen=True)
class CompletedWork:
    provider: str
    session_id: str
    started_at: datetime
    completed_at: datetime
    duration_seconds: int
    summary: str
    token_total: int | None = None
    outcome: str = "completed"


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    try:
        value = int(os.getenv(name, "").strip())
    except ValueError:
        return default
    return max(minimum, value)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "no", "off"}


def load_config() -> MonitorConfig:
    return MonitorConfig(
        enabled=_env_bool(WORK_MONITOR_ENABLED_ENV, True),
        interval_seconds=_env_int(
            WORK_MONITOR_INTERVAL_SECONDS_ENV,
            DEFAULT_INTERVAL_SECONDS,
            minimum=5,
        ),
        idle_seconds=_env_int(WORK_IDLE_SECONDS_ENV, DEFAULT_IDLE_SECONDS, minimum=30),
        lookback_hours=_env_int(
            WORK_LOOKBACK_HOURS_ENV,
            DEFAULT_LOOKBACK_HOURS,
            minimum=1,
        ),
        max_files_per_provider=_env_int(
            WORK_MAX_FILES_PER_PROVIDER_ENV,
            DEFAULT_MAX_FILES_PER_PROVIDER,
            minimum=1,
        ),
        summary_max_chars=_env_int(
            WORK_SUMMARY_MAX_CHARS_ENV,
            DEFAULT_SUMMARY_MAX_CHARS,
            minimum=40,
        ),
        include_summary=_env_bool(WORK_INCLUDE_SUMMARY_ENV, False),
        completion_cooldown_seconds=_env_int(
            WORK_COMPLETION_COOLDOWN_SECONDS_ENV,
            DEFAULT_COMPLETION_COOLDOWN_SECONDS,
            minimum=0,
        ),
        provider_completion_cooldown_seconds=_env_int(
            WORK_PROVIDER_COMPLETION_COOLDOWN_SECONDS_ENV,
            DEFAULT_PROVIDER_COMPLETION_COOLDOWN_SECONDS,
            minimum=0,
        ),
    )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_timestamp(value: Any) -> datetime | None:
    parsed = llm_report_core.parse_timestamp(value)
    if parsed is None:
        return None
    return _as_utc(parsed)


def _recent_files(root: Path, pattern: str, config: MonitorConfig) -> list[Path]:
    if not root.exists():
        return []

    cutoff = utc_now().timestamp() - (config.lookback_hours * 60 * 60)
    files: list[Path] = []
    for path in root.glob(pattern):
        try:
            if path.stat().st_mtime >= cutoff:
                files.append(path)
        except OSError:
            continue

    files.sort(key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True)
    return files[: config.max_files_per_provider]


def _content_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            return value["text"]
        if isinstance(value.get("content"), str):
            return value["content"]
        return ""
    if isinstance(value, list):
        parts = [_content_text(item) for item in value]
        return "\n".join(part for part in parts if part)
    return ""


def _is_codex_subagent_source(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() == "subagent"
    return isinstance(value, dict) and "subagent" in value


def _clean_line(line: str) -> str:
    line = line.strip()
    line = re.sub(r"^#{1,6}\s*", "", line)
    line = re.sub(r"^[-*]\s+", "", line)
    line = line.strip("`*_ \t")
    return line.strip()


def summarize_text(text: str, *, max_chars: int) -> str:
    text = text.replace("\r", "\n")
    lines: list[str] = []
    in_code_block = False
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        line = _clean_line(stripped)
        if not line:
            continue

        key = line.lower().rstrip(":")
        if key in GENERIC_SUMMARY_LINES:
            continue
        lines.append(line)

    if not lines:
        fallback = re.sub(r"\s+", " ", text).strip()
        if not fallback:
            fallback = llm_report_core.translate("work_summary_unknown")
        return truncate_summary(fallback, max_chars)

    return truncate_summary(lines[0], max_chars)


def truncate_summary(value: str, max_chars: int) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1].rstrip() + "…"


def _new_snapshot(
    *,
    provider: str,
    source_path: Path,
    session_id: str,
    timestamp: datetime,
) -> WorkSnapshot:
    key = f"{provider}:{session_id}"
    return WorkSnapshot(
        key=key,
        provider=provider,
        session_id=session_id,
        source_path=source_path,
        started_at=timestamp,
        last_activity_at=timestamp,
        summary="",
    )


def _update_snapshot(
    snapshot: WorkSnapshot,
    *,
    timestamp: datetime,
    summary: str | None = None,
    idle_seconds: int | None = None,
    reset_started_on_idle: bool = True,
) -> None:
    if timestamp < snapshot.last_activity_at:
        return
    if (
        reset_started_on_idle
        and idle_seconds is not None
        and timestamp > snapshot.last_activity_at
        and (timestamp - snapshot.last_activity_at).total_seconds() >= idle_seconds
    ):
        snapshot.started_at = timestamp
    elif timestamp < snapshot.started_at:
        snapshot.started_at = timestamp
    if timestamp >= snapshot.last_activity_at:
        snapshot.last_activity_at = timestamp
    if summary:
        snapshot.summary = summary


def collect_codex_snapshots(config: MonitorConfig) -> dict[str, WorkSnapshot]:
    base_dir = Path.home() / ".codex" / "sessions"
    snapshots: dict[str, WorkSnapshot] = {}

    for path in _recent_files(base_dir, "**/rollout-*.jsonl", config):
        session_id = path.stem.replace("rollout-", "")
        current: WorkSnapshot | None = None
        is_subagent_session = False

        for _, obj in llm_report_core.read_jsonl(path):
            if not isinstance(obj, dict):
                continue

            timestamp = _parse_timestamp(obj.get("timestamp"))
            if timestamp is None:
                continue

            if obj.get("type") == "session_meta":
                payload = obj.get("payload")
                if isinstance(payload, dict):
                    if payload.get("id"):
                        session_id = str(payload["id"])
                    if _is_codex_subagent_source(payload.get("source")):
                        is_subagent_session = True
                        break
                continue

            current = current or _new_snapshot(
                provider="Codex",
                source_path=path,
                session_id=session_id,
                timestamp=timestamp,
            )

            payload = obj.get("payload")
            summary: str | None = None
            if (
                obj.get("type") == "event_msg"
                and isinstance(payload, dict)
                and payload.get("type") == "token_count"
            ):
                info = payload.get("info")
                usage = info.get("total_token_usage") if isinstance(info, dict) else None
                if isinstance(usage, dict):
                    total = llm_report_core.codex_totals_from_usage(usage).total_tokens
                    current.token_total = max(current.token_total or 0, total)
            if obj.get("type") == "response_item" and isinstance(payload, dict):
                if payload.get("type") == "message" and payload.get("role") == "assistant":
                    text = _content_text(payload.get("content"))
                    summary = summarize_text(text, max_chars=config.summary_max_chars)
            elif obj.get("type") == "event_msg" and isinstance(payload, dict):
                if payload.get("type") in {"agent_message", "assistant_message"}:
                    text = _content_text(payload.get("message") or payload.get("text"))
                    summary = summarize_text(text, max_chars=config.summary_max_chars)

            _update_snapshot(
                current,
                timestamp=timestamp,
                summary=summary,
                idle_seconds=config.idle_seconds,
            )

        if current is not None and not is_subagent_session:
            _store_snapshot(snapshots, current)

    return snapshots


def collect_claude_snapshots(config: MonitorConfig) -> dict[str, WorkSnapshot]:
    base_dir = Path.home() / ".claude" / "projects"
    snapshots: dict[str, WorkSnapshot] = {}

    for path in _recent_files(base_dir, "**/*.jsonl", config):
        session_id = path.stem
        current: WorkSnapshot | None = None

        for _, obj in llm_report_core.read_jsonl(path):
            if not isinstance(obj, dict):
                continue

            timestamp = _parse_timestamp(obj.get("timestamp"))
            if timestamp is None:
                continue

            if obj.get("sessionId"):
                session_id = str(obj["sessionId"])

            event_type = obj.get("type")
            message = obj.get("message")
            has_session_event = bool(obj.get("sessionId"))
            if not has_session_event and not isinstance(message, dict):
                continue

            current = current or _new_snapshot(
                provider="Claude Code",
                source_path=path,
                session_id=session_id,
                timestamp=timestamp,
            )

            summary: str | None = None
            if event_type == "assistant" and isinstance(message, dict):
                text = _content_text(message.get("content"))
                summary = summarize_text(text, max_chars=config.summary_max_chars)
            elif isinstance(message, dict) and message.get("role") == "assistant":
                text = _content_text(message.get("content"))
                summary = summarize_text(text, max_chars=config.summary_max_chars)

            is_user_prompt = (
                event_type == "user"
                and "toolUseResult" not in obj
                and not obj.get("isMeta")
            )
            _update_snapshot(
                current,
                timestamp=timestamp,
                summary=summary,
                idle_seconds=config.idle_seconds,
                reset_started_on_idle=is_user_prompt,
            )

        if current is not None:
            _store_snapshot(snapshots, current)

    return snapshots


def collect_work_snapshots(config: MonitorConfig) -> dict[str, WorkSnapshot]:
    snapshots = collect_codex_snapshots(config)
    snapshots.update(collect_claude_snapshots(config))
    return snapshots


def _active_from_snapshot(snapshot: WorkSnapshot) -> ActiveWork:
    return ActiveWork(
        key=snapshot.key,
        provider=snapshot.provider,
        session_id=snapshot.session_id,
        source_path=str(snapshot.source_path),
        started_at=snapshot.started_at,
        last_activity_at=snapshot.last_activity_at,
        summary=snapshot.summary or llm_report_core.translate("work_summary_unknown"),
        token_total=snapshot.token_total,
    )


def _store_snapshot(
    snapshots: dict[str, WorkSnapshot],
    snapshot: WorkSnapshot,
) -> None:
    existing = snapshots.get(snapshot.key)
    if existing is None:
        snapshots[snapshot.key] = snapshot
        return

    if snapshot.last_activity_at >= existing.last_activity_at:
        existing.started_at = snapshot.started_at
        existing.last_activity_at = snapshot.last_activity_at
        existing.source_path = snapshot.source_path
        if snapshot.summary:
            existing.summary = snapshot.summary
        if snapshot.token_total is not None:
            existing.token_total = max(existing.token_total or 0, snapshot.token_total)


class WorkMonitor:
    def __init__(self, config: MonitorConfig | None = None) -> None:
        self.config = config or load_config()
        self.started_at = utc_now()
        self.active: dict[str, ActiveWork] = {}
        self.last_completed: CompletedWork | None = None
        self.last_notified_by_key: dict[str, datetime] = {}
        self.last_notified_by_provider: dict[str, datetime] = {}
        self.event_watcher = work_events.EventLogWatcher()
        self._seeded = False

    def seed(self) -> None:
        now = utc_now()
        self._process_bridge_events(self.event_watcher.seed(), notify=False)
        snapshots = collect_work_snapshots(self.config)
        for snapshot in snapshots.values():
            if (now - snapshot.last_activity_at).total_seconds() < self.config.idle_seconds:
                self.active.setdefault(snapshot.key, _active_from_snapshot(snapshot))
        self._seeded = True

    def poll(self) -> list[CompletedWork]:
        if not self._seeded:
            self.seed()

        now = utc_now()
        completed = self._process_bridge_events(self.event_watcher.poll(), notify=True)
        snapshots = collect_work_snapshots(self.config)

        for snapshot in snapshots.values():
            active = self.active.get(snapshot.key)
            is_recent = (now - snapshot.last_activity_at).total_seconds() < self.config.idle_seconds
            is_new_for_monitor = snapshot.last_activity_at >= self.started_at
            if active is None:
                if is_recent and is_new_for_monitor:
                    self.active[snapshot.key] = _active_from_snapshot(snapshot)
                continue

            if snapshot.last_activity_at > active.last_activity_at:
                active.last_activity_at = snapshot.last_activity_at
                active.summary = snapshot.summary or active.summary
                if snapshot.started_at < active.started_at:
                    active.started_at = snapshot.started_at
            if snapshot.token_total is not None:
                active.token_total = max(active.token_total or 0, snapshot.token_total)

        for key, active in list(self.active.items()):
            idle_for = (now - active.last_activity_at).total_seconds()
            if idle_for < self.config.idle_seconds:
                continue

            completed_at = active.last_activity_at
            duration_seconds = max(0, round((completed_at - active.started_at).total_seconds()))
            item = CompletedWork(
                provider=active.provider,
                session_id=active.session_id,
                started_at=active.started_at,
                completed_at=completed_at,
                duration_seconds=duration_seconds,
                summary=active.summary or llm_report_core.translate("work_summary_unknown"),
                token_total=active.token_total,
                outcome="completed",
            )
            self.last_completed = item
            if self._should_notify_passive_completion(key, item):
                completed.append(item)
            del self.active[key]

        return completed

    def _should_notify_passive_completion(
        self,
        key: str,
        item: CompletedWork,
    ) -> bool:
        last_for_key = self.last_notified_by_key.get(key)
        if (
            last_for_key is not None
            and self.config.completion_cooldown_seconds > 0
            and (item.completed_at - last_for_key).total_seconds()
            < self.config.completion_cooldown_seconds
        ):
            return False

        last_for_provider = self.last_notified_by_provider.get(item.provider)
        if (
            last_for_provider is not None
            and self.config.provider_completion_cooldown_seconds > 0
            and (item.completed_at - last_for_provider).total_seconds()
            < self.config.provider_completion_cooldown_seconds
        ):
            return False

        self.last_notified_by_key[key] = item.completed_at
        self.last_notified_by_provider[item.provider] = item.completed_at
        return True

    def _process_bridge_events(
        self,
        events: list[work_events.WorkEvent],
        *,
        notify: bool,
    ) -> list[CompletedWork]:
        completed: list[CompletedWork] = []
        for event in events:
            key = f"{event.provider}:{event.session_id}"
            active = self.active.get(key)
            if event.event_type in {"start", "heartbeat"}:
                if active is None:
                    active = ActiveWork(
                        key=key,
                        provider=event.provider,
                        session_id=event.session_id,
                        source_path="local-event-bridge",
                        started_at=event.timestamp,
                        last_activity_at=event.timestamp,
                        summary=event.summary or llm_report_core.translate("work_summary_unknown"),
                    )
                    self.active[key] = active
                    continue

                active.started_at = min(active.started_at, event.timestamp)
                active.last_activity_at = max(active.last_activity_at, event.timestamp)
                if event.summary:
                    active.summary = truncate_summary(
                        event.summary,
                        self.config.summary_max_chars,
                    )
                continue

            if active is None:
                active = ActiveWork(
                    key=key,
                    provider=event.provider,
                    session_id=event.session_id,
                    source_path="local-event-bridge",
                    started_at=event.timestamp,
                    last_activity_at=event.timestamp,
                    summary=event.summary or llm_report_core.translate("work_summary_unknown"),
                )

            summary = event.summary or active.summary
            item = CompletedWork(
                provider=active.provider,
                session_id=active.session_id,
                started_at=active.started_at,
                completed_at=event.timestamp,
                duration_seconds=max(
                    0,
                    round((event.timestamp - active.started_at).total_seconds()),
                ),
                summary=truncate_summary(summary, self.config.summary_max_chars),
                token_total=active.token_total,
                outcome="failed" if event.event_type == "failed" else "completed",
            )
            self.last_completed = item
            self.active.pop(key, None)
            if notify:
                completed.append(item)

        return completed

    def status(self) -> dict[str, Any]:
        now = utc_now()
        active_items = sorted(self.active.values(), key=lambda item: item.started_at)
        return {
            "enabled": self.config.enabled,
            "active": active_items,
            "last_completed": self.last_completed,
            "now": now,
        }


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if llm_report_core.detect_report_language() == "ko":
        parts: list[str] = []
        if hours:
            parts.append(f"{hours}시간")
        if minutes:
            parts.append(f"{minutes}분")
        if not parts:
            parts.append(f"{secs}초")
        return " ".join(parts)

    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def format_work_status(monitor: WorkMonitor, *, include_summary: bool = False) -> str:
    status = monitor.status()
    if not status["enabled"]:
        return llm_report_core.translate("work_monitor_disabled")

    active_items: list[ActiveWork] = status["active"]
    now: datetime = status["now"]
    if active_items:
        lines = [llm_report_core.translate("work_status_active")]
        for item in active_items:
            elapsed = round((now - item.started_at).total_seconds())
            line_key = (
                "work_status_active_line_with_summary"
                if include_summary
                else "work_status_active_line"
            )
            lines.append(
                llm_report_core.translate(
                    line_key,
                    provider=item.provider,
                    duration=format_duration(elapsed),
                    summary=item.summary,
                )
            )
        return "\n".join(lines)

    last_completed: CompletedWork | None = status["last_completed"]
    if last_completed is None:
        return llm_report_core.translate("work_status_idle")

    elapsed = round((now - last_completed.completed_at).total_seconds())
    line_key = (
        "work_status_last_completed_with_summary"
        if include_summary
        else "work_status_last_completed"
    )
    return "\n".join(
        [
            llm_report_core.translate("work_status_idle"),
            llm_report_core.translate(
                line_key,
                provider=last_completed.provider,
                ago=format_duration(elapsed),
                summary=last_completed.summary,
            ),
        ]
    )


def build_completion_embed(
    item: CompletedWork,
    *,
    include_summary: bool = False,
) -> dict[str, Any]:
    fields = [
        {
            "name": llm_report_core.translate("work_completed_provider"),
            "value": item.provider,
            "inline": True,
        },
        {
            "name": llm_report_core.translate("work_completed_duration"),
            "value": format_duration(item.duration_seconds),
            "inline": True,
        },
    ]
    if item.token_total is not None:
        fields.append(
            {
                "name": llm_report_core.translate("work_completed_tokens"),
                "value": llm_report_core.format_number(item.token_total),
                "inline": True,
            }
        )
    if include_summary:
        fields.append(
            {
                "name": llm_report_core.translate("work_completed_summary"),
                "value": item.summary,
                "inline": False,
            }
        )

    return {
        "title": llm_report_core.translate(
            "work_failed_title" if item.outcome == "failed" else "work_completed_title"
        ),
        "color": 0xE74C3C if item.outcome == "failed" else 0x2ECC71,
        "fields": fields,
        "timestamp": item.completed_at.isoformat(),
    }
