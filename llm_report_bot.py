from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Iterable

import llm_report_core
import work_monitor

LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_FILE = LOG_DIR / "llm_report_bot.log"
DEFAULT_BOT_NAME = "Your_LLM_Bot"
BOT_MUTEX_NAME = "Local\\LLM_report_bot"
ERROR_ALREADY_EXISTS = 183


LINE_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def claim_bot_instance() -> tuple[int | None, bool]:
    if os.name != "nt":
        return None, True
    try:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        handle = kernel32.CreateMutexW(None, False, BOT_MUTEX_NAME)
        if not handle:
            return None, True
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return None, False
        return int(handle), True
    except OSError:
        return None, True


def release_bot_instance(handle: int | None) -> None:
    if handle is None or os.name != "nt":
        return
    try:
        import ctypes

        ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(handle)
    except OSError:
        pass


def _enable_windows_ansi() -> None:
    """Enable ANSI colors in Windows cmd when possible."""
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        kernel32.SetConsoleMode(handle, 7)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING included
    except Exception:
        pass


class _VoiceWarningFilter(logging.Filter):
    """Hide harmless voice-support warnings from discord.py."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "voice will NOT be supported" not in record.getMessage()


class _ColorFormatter(logging.Formatter):
    """Color warning and error messages in the console."""

    COLORS = {
        logging.WARNING: "\033[33m",
        logging.ERROR: "\033[31m",
        logging.CRITICAL: "\033[1;31m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        color = self.COLORS.get(record.levelno)
        return f"{color}{text}{self.RESET}" if color else text


def setup_logging() -> logging.Logger:
    """Configure console and rotating file logs once."""
    root = logging.getLogger()
    if getattr(root, "_llm_report_bot_configured", False):
        return logging.getLogger("llm_report_bot")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _enable_windows_ansi()
    voice_filter = _VoiceWarningFilter()

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(_ColorFormatter(LINE_FMT))
    console.addFilter(voice_filter)

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(LINE_FMT))
    file_handler.addFilter(voice_filter)

    root.setLevel(logging.INFO)
    root.addHandler(console)
    root.addHandler(file_handler)
    root._llm_report_bot_configured = True  # type: ignore[attr-defined]
    return logging.getLogger("llm_report_bot")


def parse_id_set(value: str | None) -> set[int]:
    if not value:
        return set()

    ids: set[int] = set()
    for part in value.split(","):
        text = part.strip()
        if not text:
            continue
        if not text.isascii() or not text.isdigit() or int(text) <= 0:
            raise ValueError("Discord IDs must be positive integers.")
        ids.add(int(text))
    return ids


def is_allowed(
    *,
    user_id: int,
    channel_id: int,
    allowed_user_ids: set[int],
    allowed_channel_ids: set[int],
) -> bool:
    user_ok = user_id in allowed_user_ids
    channel_ok = not allowed_channel_ids or channel_id in allowed_channel_ids
    return user_ok and channel_ok


def format_command_help(commands: Iterable[tuple[str, str]]) -> str:
    lines = ["사용 가능한 명령어"]
    for name, description in sorted(commands):
        lines.append(f"`/{name}` — {description}")
    return "\n".join(lines)


def _enabled_label(enabled: bool) -> str:
    return "켜짐" if enabled else "꺼짐"


def _access_scope_label(count: int, unit: str) -> str:
    return "모두 허용" if count == 0 else f"{count}{unit}만 허용"


def _work_webhook_label(
    *,
    usage_webhook_configured: bool,
    dedicated_work_webhook_configured: bool,
) -> str:
    if dedicated_work_webhook_configured:
        return "전용 웹훅 사용"
    if usage_webhook_configured:
        return "사용량 웹훅 공유"
    return "미설정 (완료 알림 전송 안 함)"


def format_bot_status(
    *,
    config: work_monitor.MonitorConfig,
    uptime_seconds: int,
    active_work_count: int,
    last_completed_provider: str | None,
) -> str:
    lines = [
        "LLM 봇 상태",
        f"- 가동 시간: {work_monitor.format_duration(uptime_seconds)}",
        f"- 작업 감시: {_enabled_label(config.enabled)}",
        f"- 진행 중인 작업: {active_work_count}개",
        f"- 완료 알림 요약: {_enabled_label(config.include_summary)}",
    ]
    if last_completed_provider:
        lines.append(f"- 마지막 완료 도구: {last_completed_provider}")
    return "\n".join(lines)


def format_safe_settings(
    config: work_monitor.MonitorConfig,
    *,
    usage_webhook_configured: bool,
    dedicated_work_webhook_configured: bool,
    allowed_user_count: int,
    allowed_channel_count: int,
    resume_queue_enabled: bool,
) -> str:
    report_timezone = llm_report_core.get_report_timezone()
    timezone_name = getattr(report_timezone, "key", None) or str(report_timezone)
    claude_plan, plan_is_default = llm_report_core.configured_claude_plan()
    plan_name = (
        llm_report_core.claude_plan_display(claude_plan)
        if claude_plan.key != "custom"
        else "사용자 지정"
    )
    if plan_is_default:
        plan_name += " (기본값)"
    claude_token_limit = llm_report_core.configured_claude_token_limit(claude_plan)
    token_limit_label = (
        f"{claude_token_limit:,} 토큰" if claude_token_limit else "미설정"
    )

    return "\n".join(
        [
            "LLM 봇 설정",
            "",
            "**보고서**",
            f"- 언어: {llm_report_core.detect_report_language()}",
            f"- 시간대: {timezone_name}",
            f"- Claude 추정 기준: {plan_name} / {token_limit_label}",
            "",
            "**작업 감시**",
            f"- 상태: {_enabled_label(config.enabled)}",
            f"- 확인 주기: {work_monitor.format_duration(config.interval_seconds)}",
            f"- 완료 판정: {work_monitor.format_duration(config.idle_seconds)} 동안 활동 없음",
            (
                f"- 로그 탐색: 최근 {config.lookback_hours}시간 / "
                f"도구별 최대 {config.max_files_per_provider}개 파일"
            ),
            (
                f"- 완료 알림 요약: {_enabled_label(config.include_summary)} / "
                f"최대 {config.summary_max_chars}자"
            ),
            (
                "- 재알림 제한: 세션 "
                f"{work_monitor.format_duration(config.completion_cooldown_seconds)} / "
                "도구 "
                f"{work_monitor.format_duration(config.provider_completion_cooldown_seconds)}"
            ),
            "",
            "**Discord 전송**",
            (
                "- 사용량·할당량 웹훅: "
                + ("설정됨 (5분마다 경보 확인)" if usage_webhook_configured else "미설정")
            ),
            "- 작업 완료 웹훅: "
            + _work_webhook_label(
                usage_webhook_configured=usage_webhook_configured,
                dedicated_work_webhook_configured=dedicated_work_webhook_configured,
            ),
            "",
            "**접근·자동화**",
            "- 허용 사용자: "
            + (_access_scope_label(allowed_user_count, '명') if allowed_user_count else "모두 차단 (허용 사용자 미설정)"),
            f"- 허용 채널: {_access_scope_label(allowed_channel_count, '개')}",
            f"- 복구 큐: {_enabled_label(resume_queue_enabled)}",
            "",
            "※ 봇 토큰, 웹훅 URL, 실제 ID와 파일 경로 값만 숨깁니다.",
        ]
    )


def windows_to_check() -> Iterable[str]:
    return ("primary", "secondary")


def find_newly_exhausted_windows(
    snapshot: llm_report_core.UsageSnapshot,
    state: dict[str, bool],
) -> tuple[list[str], bool]:
    exhausted: list[str] = []
    changed = False

    for window in windows_to_check():
        remaining = llm_report_core.get_codex_remaining_percent(snapshot.codex, window)
        if remaining is None:
            continue

        if remaining <= 0:
            if not state.get(window, False):
                exhausted.append(window)
            continue

        if state.get(window, False):
            state[window] = False
            changed = True

    return exhausted, changed


async def send_alert_webhook(webhook_url: str, header: str, snapshot) -> None:
    await asyncio.to_thread(
        lambda: llm_report_core.send_webhook(
            webhook_url,
            llm_report_core.build_report_embeds(snapshot),
            content=header,
        )
    )


def main() -> int:
    logger = setup_logging()
    logger.info("llm_report_bot 시작 - 로그 파일: %s", LOG_FILE)

    llm_report_core.load_environment()

    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    webhook_url = os.getenv("DISCORD_USAGE_WEBHOOK_URL", "").strip()
    dedicated_work_webhook_url = os.getenv("DISCORD_WORK_WEBHOOK_URL", "").strip()
    work_webhook_url = dedicated_work_webhook_url or webhook_url
    bot_name = os.getenv("DISCORD_BOT_NAME", DEFAULT_BOT_NAME).strip() or DEFAULT_BOT_NAME
    try:
        allowed_user_ids = parse_id_set(os.getenv("DISCORD_ALLOWED_USER_IDS"))
        allowed_channel_ids = parse_id_set(os.getenv("DISCORD_ALLOWED_CHANNEL_IDS"))
    except ValueError:
        logger.error("Discord 허용 사용자·채널 ID에는 양의 정수만 입력하세요.")
        return 1
    if not allowed_user_ids:
        logger.error("DISCORD_ALLOWED_USER_IDS에 명령을 허용할 사용자 ID를 설정하세요.")
        return 1
    monitor = work_monitor.WorkMonitor()
    bot_started_at = time.monotonic()

    if not token:
        logger.error(
            "DISCORD_BOT_TOKEN이 설정되어 있지 않습니다. .env 파일에 봇 토큰을 설정하세요."
        )
        return 1

    try:
        import discord
        from discord.ext import commands, tasks
    except ImportError:
        logger.error(
            "discord.py가 설치되어 있지 않습니다. 실행: python -m pip install -r requirements.txt"
        )
        return 1

    instance_handle, is_primary_instance = claim_bot_instance()
    if not is_primary_instance:
        logger.warning("Another LLM_report_bot instance is already running; exiting.")
        return 0

    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(
        command_prefix=commands.when_mentioned,
        intents=intents,
        activity=discord.Game(name=f"{bot_name} | /usage /work /help"),
    )
    commands_synced = False

    @bot.event
    async def on_ready():
        nonlocal commands_synced
        if not commands_synced:
            try:
                for guild in bot.guilds:
                    bot.tree.copy_global_to(guild=guild)
                    await bot.tree.sync(guild=guild)
                await bot.tree.sync()
            except Exception:
                logger.exception("Discord slash command synchronization failed.")
            else:
                commands_synced = True
                logger.info("Discord slash commands synchronized.")
        logger.info("%s Discord 봇이 로그인했습니다. (%s)", bot_name, bot.user)
        if webhook_url:
            if not quota_alert_loop.is_running():
                quota_alert_loop.start()
                logger.info("자동 경보 루프 시작 (5분 주기).")
        else:
            logger.warning(
                "DISCORD_USAGE_WEBHOOK_URL이 없어 자동 경보 전송은 비활성화됩니다."
            )
        if monitor.config.enabled and not work_monitor_loop.is_running():
            monitor.seed()
            work_monitor_loop.start()
            logger.info(
                "작업 감시 루프 시작 (%s초 주기, %s초 idle 기준).",
                monitor.config.interval_seconds,
                monitor.config.idle_seconds,
            )

    @bot.event
    async def on_command_error(ctx, error):
        # Ignore unregistered commands quietly.
        if isinstance(error, commands.CommandNotFound):
            return
        logger.exception("명령 처리 오류: %s", error)
        try:
            await ctx.reply(
                llm_report_core.translate("command_error"),
                mention_author=False,
            )
        except Exception:
            logger.exception("오류 응답 전송 실패")

    async def interaction_is_allowed(interaction: discord.Interaction) -> bool:
        if is_allowed(
            user_id=interaction.user.id,
            channel_id=interaction.channel_id or 0,
            allowed_user_ids=allowed_user_ids,
            allowed_channel_ids=allowed_channel_ids,
        ):
            return True
        await interaction.response.send_message(
            llm_report_core.translate("command_not_allowed"),
            ephemeral=True,
        )
        return False

    @bot.tree.command(name="usage", description="AI 사용량 리포트를 표시합니다.")
    async def usage_command(interaction: discord.Interaction):
        if not await interaction_is_allowed(interaction):
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        snapshot = await asyncio.to_thread(llm_report_core.collect_usage)
        embeds = [
            discord.Embed.from_dict(embed)
            for embed in llm_report_core.build_report_embeds(snapshot)
        ]
        await interaction.followup.send(embeds=embeds)
        logger.info("/usage response -> channel %s (user %s)", interaction.channel_id, interaction.user)

    @bot.tree.command(name="work", description="현재 LLM 작업 상태를 표시합니다.")
    async def work_command(interaction: discord.Interaction):
        if not await interaction_is_allowed(interaction):
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        if monitor.config.enabled:
            await asyncio.to_thread(monitor.poll)
        await interaction.followup.send(
            work_monitor.format_work_status(monitor, include_summary=False),
        )
        logger.info("/work response -> channel %s (user %s)", interaction.channel_id, interaction.user)

    @bot.tree.command(name="help", description="사용 가능한 LLM 봇 명령어를 표시합니다.")
    async def help_command(interaction: discord.Interaction):
        if not await interaction_is_allowed(interaction):
            return
        await interaction.response.send_message(
            format_command_help(
                (command.name, command.description) for command in bot.tree.get_commands()
            ),
            ephemeral=True,
        )

    @bot.tree.command(name="status", description="LLM 봇과 작업 감시 상태를 표시합니다.")
    async def status_command(interaction: discord.Interaction):
        if not await interaction_is_allowed(interaction):
            return
        monitor_status = monitor.status()
        last_completed = monitor_status["last_completed"]
        await interaction.response.send_message(
            format_bot_status(
                config=monitor.config,
                uptime_seconds=round(time.monotonic() - bot_started_at),
                active_work_count=len(monitor_status["active"]),
                last_completed_provider=(
                    last_completed.provider if last_completed is not None else None
                ),
            ),
            ephemeral=True,
        )

    @bot.tree.command(name="settings", description="민감정보를 제외한 LLM 봇 설정을 표시합니다.")
    async def settings_command(interaction: discord.Interaction):
        if not await interaction_is_allowed(interaction):
            return
        await interaction.response.send_message(
            format_safe_settings(
                monitor.config,
                usage_webhook_configured=bool(webhook_url),
                dedicated_work_webhook_configured=bool(dedicated_work_webhook_url),
                allowed_user_count=len(allowed_user_ids),
                allowed_channel_count=len(allowed_channel_ids),
                resume_queue_enabled=(
                    os.getenv("RESUME_QUEUE_ENABLED", "0").strip().lower()
                    in {"1", "true", "yes", "on"}
                ),
            ),
            ephemeral=True,
        )

    @tasks.loop(minutes=5)
    async def quota_alert_loop():
        if not webhook_url:
            return
        try:
            snapshot = llm_report_core.collect_usage()
            state = llm_report_core.load_alert_state()
            exhausted, changed = find_newly_exhausted_windows(snapshot, state)

            if exhausted:
                header = llm_report_core.build_alert_header(exhausted)
                try:
                    await send_alert_webhook(webhook_url, header, snapshot)
                except Exception as exc:
                    logger.error(
                        "Codex 할당량 경보 전송 오류: %s",
                        llm_report_core.safe_webhook_error(exc),
                    )
                else:
                    for window in exhausted:
                        state[window] = True
                    changed = True
                    logger.info("Codex 할당량 경보 전송: %s", header)

            if changed:
                llm_report_core.save_alert_state(state)
        except Exception:
            # Keep the loop alive even when one cycle fails.
            logger.exception("자동 경보 점검 중 오류 (루프는 계속됩니다)")

    @quota_alert_loop.error
    async def quota_alert_loop_error(error):
        logger.exception("자동 경보 루프 오류, 재시작 시도: %s", error)
        if not quota_alert_loop.is_running():
            quota_alert_loop.restart()

    @quota_alert_loop.before_loop
    async def before_quota_alert_loop():
        await bot.wait_until_ready()

    @tasks.loop(seconds=monitor.config.interval_seconds)
    async def work_monitor_loop():
        if not monitor.config.enabled:
            return
        try:
            completed_items = await asyncio.to_thread(monitor.poll)
            for item in completed_items:
                logger.info("LLM 작업 결과 감지: %s / %s", item.provider, item.outcome)
                if not work_webhook_url:
                    logger.warning(
                        "DISCORD_WORK_WEBHOOK_URL 또는 DISCORD_USAGE_WEBHOOK_URL이 없어 작업 완료 알림은 생략됩니다."
                    )
                    continue
                try:
                    await asyncio.to_thread(
                        llm_report_core.send_webhook,
                        work_webhook_url,
                        [
                            work_monitor.build_completion_embed(
                                item,
                                include_summary=monitor.config.include_summary,
                            )
                        ],
                        content=llm_report_core.translate(
                            (
                                "work_completed_content"
                                if monitor.config.include_summary
                                else "work_completed_content_safe"
                            )
                            if item.outcome == "completed"
                            else "work_failed_content_safe",
                            summary=item.summary,
                        ),
                    )
                except Exception as exc:
                    logger.error(
                        "작업 완료 알림 전송 오류: %s",
                        llm_report_core.safe_webhook_error(exc),
                    )
        except Exception:
            logger.exception("작업 감시 중 오류 (루프는 계속됩니다)")

    @work_monitor_loop.error
    async def work_monitor_loop_error(error):
        logger.exception("작업 감시 루프 오류, 재시작 시도: %s", error)
        if not work_monitor_loop.is_running():
            work_monitor_loop.restart()

    @work_monitor_loop.before_loop
    async def before_work_monitor_loop():
        await bot.wait_until_ready()

    try:
        bot.run(token, log_handler=None)  # setup_logging() handles logging centrally
    except discord.LoginFailure:
        logger.error("Discord 봇 토큰이 올바르지 않습니다.")
        return 1
    except Exception:
        logger.exception("Discord 봇 실행에 실패했습니다.")
        return 1

    release_bot_instance(instance_handle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
