from __future__ import annotations

import argparse
from datetime import timedelta
from pathlib import Path
import sys

import resume_queue


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Queue a locally registered LLM command for automatic resume."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    enqueue = subparsers.add_parser("enqueue")
    enqueue.add_argument("--provider", required=True)
    enqueue.add_argument("--session-id", required=True)
    enqueue.add_argument("--cwd", default=str(Path.cwd()))
    timing = enqueue.add_mutually_exclusive_group(required=True)
    timing.add_argument("--resume-at", help="ISO 8601 time with timezone")
    timing.add_argument(
        "--after-minutes",
        type=int,
        help="Resume after this many minutes",
    )
    timing.add_argument(
        "--when-codex-recovers",
        action="store_true",
        help="Use the latest exhausted Codex quota reset time",
    )
    enqueue.add_argument("resume_command", nargs=argparse.REMAINDER)

    subparsers.add_parser("list")
    cancel = subparsers.add_parser("cancel")
    cancel.add_argument("task_id")
    return parser


def resolve_resume_at(args) -> object:
    if args.resume_at:
        return resume_queue.parse_datetime(args.resume_at)
    if args.after_minutes is not None:
        if args.after_minutes < 1:
            raise ValueError("--after-minutes must be at least 1")
        return resume_queue.utc_now() + timedelta(minutes=args.after_minutes)
    value = resume_queue.get_codex_recovery_time()
    if value is None:
        raise ValueError("No exhausted Codex quota with a reset time was found")
    return value


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "list":
        for task in resume_queue.load_tasks():
            print(
                f"{task.task_id} {task.status} {task.provider} "
                f"resume_at={task.resume_at.isoformat()}"
            )
        return 0

    if args.command == "cancel":
        task = resume_queue.cancel_task(args.task_id)
        if task is None:
            print("Task not found", file=sys.stderr)
            return 1
        print(f"Cancelled {task.task_id}")
        return 0

    command = list(args.resume_command)
    if command and command[0] == "--":
        command.pop(0)
    try:
        task = resume_queue.enqueue_task(
            provider=args.provider,
            session_id=args.session_id,
            command=command,
            cwd=args.cwd,
            resume_at=resolve_resume_at(args),
        )
    except (OSError, ValueError) as exc:
        print(f"Queue error: {exc}", file=sys.stderr)
        return 1

    print(f"Queued {task.task_id} for {task.resume_at.isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
