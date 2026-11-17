from __future__ import annotations

import argparse
import os
import sys

import llm_report_core


def configure_standard_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Claude Code와 Codex 사용량을 집계합니다."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Discord 웹훅으로 보내지 않고 콘솔에 요약을 출력합니다.",
    )
    parser.add_argument(
        "--period",
        choices=("today", "7d", "all"),
        default=None,
        help=(
            "이전 자동화 호환성을 위해 남겨둔 옵션입니다. 현재 리포트는 "
            "Claude Code의 5시간 추정 잔여량과 오늘/전체 토큰을 표시합니다."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_standard_streams()
    args = build_arg_parser().parse_args(argv)
    llm_report_core.selected_periods(args.period)

    llm_report_core.load_environment()
    webhook_url = os.getenv("DISCORD_USAGE_WEBHOOK_URL", "").strip()

    if not args.dry_run and not webhook_url:
        print(
            "오류: DISCORD_USAGE_WEBHOOK_URL이 설정되어 있지 않습니다. "
            ".env.example을 복사해 .env를 만들거나 환경 변수를 설정하세요.",
            file=sys.stderr,
        )
        return 1

    snapshot = llm_report_core.collect_usage()

    if args.dry_run:
        print(llm_report_core.build_report_text(snapshot, dry_run=True))
        return 0

    try:
        llm_report_core.send_webhook(webhook_url, llm_report_core.build_report_embeds(snapshot))
    except Exception as exc:
        print(
            f"Discord 웹훅 전송 오류: {llm_report_core.safe_webhook_error(exc)}",
            file=sys.stderr,
        )
        return 1

    print("AI 사용량 리포트를 전송했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
