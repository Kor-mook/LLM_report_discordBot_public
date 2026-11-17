from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import llm_report_core


SCRIPT_DIR = Path(__file__).resolve().parent
QUEUE_PATH = SCRIPT_DIR / "logs" / "resume_queue.json"
VALID_STATUSES = {"paused", "launching", "running", "completed", "failed", "cancelled"}


@dataclass
class ResumeTask:
    task_id: str
    provider: str
    session_id: str
    command: list[str]
    cwd: str
    resume_at: datetime
    status: str
    created_at: datetime
    updated_at: datetime
    attempts: int = 0
    last_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "provider": self.provider,
            "session_id": self.session_id,
            "command": self.command,
            "cwd": self.cwd,
            "resume_at": self.resume_at.isoformat(),
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "attempts": self.attempts,
            "last_error": self.last_error,
        }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_datetime(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _task_from_dict(value: Any) -> ResumeTask | None:
    if not isinstance(value, dict):
        return None
    try:
        task = ResumeTask(
            task_id=str(value["task_id"]),
            provider=str(value["provider"]),
            session_id=str(value["session_id"]),
            command=[str(item) for item in value["command"]],
            cwd=str(value["cwd"]),
            resume_at=parse_datetime(str(value["resume_at"])),
            status=str(value["status"]),
            created_at=parse_datetime(str(value["created_at"])),
            updated_at=parse_datetime(str(value["updated_at"])),
            attempts=int(value.get("attempts", 0)),
            last_error=str(value.get("last_error", "")),
        )
    except (KeyError, TypeError, ValueError):
        return None
    if not task.task_id or not task.provider or not task.session_id or not task.command:
        return None
    if task.status not in VALID_STATUSES:
        return None
    return task


def load_tasks(path: Path = QUEUE_PATH) -> list[ResumeTask]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(raw, list):
        return []
    return [task for item in raw if (task := _task_from_dict(item)) is not None]


def save_tasks(tasks: list[ResumeTask], path: Path = QUEUE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps([task.to_dict() for task in tasks], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def is_enabled() -> bool:
    return os.getenv("RESUME_QUEUE_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}


def get_codex_recovery_time() -> datetime | None:
    llm_report_core.load_environment()
    aggregate = llm_report_core.aggregate_codex()
    limits = aggregate.latest_rate_limits or {}
    if not isinstance(limits, dict):
        return None

    reset_times: list[datetime] = []
    for window in ("primary", "secondary"):
        limit = limits.get(window)
        if not isinstance(limit, dict):
            continue
        remaining = llm_report_core.remaining_percent_from_limit(limit)
        if remaining is None or remaining > 0:
            continue
        reset_at = llm_report_core.parse_timestamp(limit.get("resets_at"))
        if reset_at is not None:
            reset_times.append(reset_at.astimezone(timezone.utc))

    if not reset_times:
        return None
    return max(reset_times)


def enqueue_task(
    *,
    provider: str,
    session_id: str,
    command: list[str],
    cwd: str,
    resume_at: datetime,
    path: Path = QUEUE_PATH,
) -> ResumeTask:
    normalized_provider = provider.strip()
    normalized_session_id = session_id.strip()
    normalized_command = [part.strip() for part in command if part.strip()]
    if not normalized_provider:
        raise ValueError("provider is required")
    if not normalized_session_id:
        raise ValueError("session_id is required")
    if not normalized_command:
        raise ValueError("resume command is required")

    now = utc_now()
    task = ResumeTask(
        task_id=uuid.uuid4().hex,
        provider=normalized_provider,
        session_id=normalized_session_id,
        command=normalized_command,
        cwd=str(Path(cwd).resolve()),
        resume_at=resume_at.astimezone(timezone.utc),
        status="paused",
        created_at=now,
        updated_at=now,
    )
    tasks = load_tasks(path)
    tasks.append(task)
    save_tasks(tasks, path)
    return task


def take_due_tasks(
    *,
    now: datetime | None = None,
    path: Path = QUEUE_PATH,
) -> list[ResumeTask]:
    current = (now or utc_now()).astimezone(timezone.utc)
    tasks = load_tasks(path)
    due: list[ResumeTask] = []
    for task in tasks:
        if task.status != "paused" or task.resume_at > current:
            continue
        task.status = "launching"
        task.updated_at = current
        task.attempts += 1
        due.append(task)
    if due:
        save_tasks(tasks, path)
    return due


def update_task(
    task_id: str,
    *,
    status: str,
    last_error: str = "",
    path: Path = QUEUE_PATH,
) -> ResumeTask | None:
    if status not in VALID_STATUSES:
        raise ValueError(f"Unsupported status: {status}")
    tasks = load_tasks(path)
    for task in tasks:
        if task.task_id != task_id:
            continue
        task.status = status
        task.last_error = last_error.strip()
        task.updated_at = utc_now()
        save_tasks(tasks, path)
        return task
    return None


def cancel_task(task_id: str, path: Path = QUEUE_PATH) -> ResumeTask | None:
    return update_task(task_id, status="cancelled", path=path)
