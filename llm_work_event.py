from __future__ import annotations

import argparse
import sys

import work_events


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Record a local LLM work lifecycle event for LLM_report_bot."
    )
    parser.add_argument("event", choices=sorted(work_events.VALID_EVENT_TYPES))
    parser.add_argument("--provider", required=True, help="Provider name, such as Gemini or Grok")
    parser.add_argument("--session-id", required=True, help="Provider-specific work or session ID")
    parser.add_argument(
        "--summary",
        default="",
        help="Optional one-line completion summary stored locally.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        event = work_events.append_event(
            args.event,
            provider=args.provider,
            session_id=args.session_id,
            summary=args.summary,
        )
    except (OSError, ValueError) as exc:
        print(f"Work event error: {exc}", file=sys.stderr)
        return 1

    print(
        f"Recorded {event.event_type}: {event.provider} / {event.session_id}",
        file=sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
