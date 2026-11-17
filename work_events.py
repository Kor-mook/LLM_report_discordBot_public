from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
EVENT_LOG_PATH = SCRIPT_DIR / "logs" / "work_events.jsonl"
VALID_EVENT_TYPES = {"start", "heartbeat", "complete", "failed"}


@dataclass(frozen=True)
class WorkEvent:
    event_type: str
    provider: str
    session_id: str
    timestamp: datetime
    summary: str
    raw: dict[str, Any]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_event(value: Any) -> WorkEvent | None:
    if not isinstance(value, dict):
        return None
    event_type = str(value.get("event") or "").strip().lower()
    provider = str(value.get("provider") or "").strip()
    session_id = str(value.get("session_id") or "").strip()
    timestamp = _parse_timestamp(value.get("timestamp"))
    if (
        event_type not in VALID_EVENT_TYPES
        or not provider
        or not session_id
        or timestamp is None
    ):
        return None
    return WorkEvent(
        event_type=event_type,
        provider=provider,
        session_id=session_id,
        timestamp=timestamp,
        summary=str(value.get("summary") or "").strip(),
        raw=value,
    )


def append_event(
    event_type: str,
    *,
    provider: str,
    session_id: str,
    summary: str = "",
    path: Path = EVENT_LOG_PATH,
) -> WorkEvent:
    normalized_type = event_type.strip().lower()
    normalized_provider = provider.strip()
    normalized_session_id = session_id.strip()
    if normalized_type not in VALID_EVENT_TYPES:
        raise ValueError(f"Unsupported event type: {event_type}")
    if not normalized_provider:
        raise ValueError("provider is required")
    if not normalized_session_id:
        raise ValueError("session_id is required")

    now = utc_now()
    payload = {
        "version": 1,
        "event": normalized_type,
        "provider": normalized_provider,
        "session_id": normalized_session_id,
        "timestamp": now.isoformat(),
        "summary": summary.strip(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    parsed = _parse_event(payload)
    if parsed is None:  # pragma: no cover - validated above
        raise RuntimeError("Could not create work event")
    return parsed


def read_events(path: Path = EVENT_LOG_PATH) -> list[WorkEvent]:
    events: list[WorkEvent] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    parsed = _parse_event(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if parsed is not None:
                    events.append(parsed)
    except OSError:
        return events
    return events


class EventLogWatcher:
    def __init__(self, path: Path = EVENT_LOG_PATH) -> None:
        self.path = path
        self.position = 0

    def seed(self) -> list[WorkEvent]:
        events = read_events(self.path)
        try:
            self.position = self.path.stat().st_size
        except OSError:
            self.position = 0
        return events

    def poll(self) -> list[WorkEvent]:
        try:
            size = self.path.stat().st_size
        except OSError:
            return []
        if size < self.position:
            self.position = 0

        events: list[WorkEvent] = []
        try:
            with self.path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(self.position)
                for line in handle:
                    try:
                        parsed = _parse_event(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                    if parsed is not None:
                        events.append(parsed)
                self.position = handle.tell()
        except OSError:
            return []
        return events
