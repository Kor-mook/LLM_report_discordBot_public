from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

import resume_worker
import startup
import llm_report_core


SCRIPT_DIR = Path(__file__).resolve().parent
LOG_DIR = SCRIPT_DIR / "logs"
LOG_FILE = LOG_DIR / "llm_report_bot.log"
TRAY_LOG_FILE = LOG_DIR / "llm_report_tray.log"
PID_FILE = LOG_DIR / "llm_report_bot.pid"
TRAY_PID_FILE = LOG_DIR / "llm_report_tray.pid"
BOT_SCRIPT = SCRIPT_DIR / "llm_report_bot.py"
TAIL_LOGS_SCRIPT = SCRIPT_DIR / "tail_llm_report_logs.bat"
BOT_SCRIPT_NAME = "llm_report_bot.py"
TRAY_SCRIPT_NAME = "llm_report_tray.py"


logger = logging.getLogger("llm_report_tray")


def configure_logging() -> None:
    """Keep tray startup failures visible when launched through pythonw/VBS."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if logger.handlers:
        return
    handler = logging.FileHandler(TRAY_LOG_FILE, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def resume_queue_interval_seconds() -> int:
    try:
        value = int(os.getenv("RESUME_QUEUE_INTERVAL_SECONDS", "60"))
    except ValueError:
        return 60
    return max(15, value)


def python_for_background() -> str:
    candidates = [
        SCRIPT_DIR / ".venv" / "Scripts" / "pythonw.exe",
        SCRIPT_DIR / ".venv" / "Scripts" / "python.exe",
    ]
    executable = Path(sys.executable)
    if executable.name.lower() == "python.exe":
        candidates.append(executable.with_name("pythonw.exe"))
    candidates.append(executable)

    for candidate in candidates:
        if isinstance(candidate, Path) and candidate.exists():
            return str(candidate)
    return "pythonw.exe"


def _read_pid_file(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _read_pid() -> int | None:
    return _read_pid_file(PID_FILE)


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            process_query_limited_information = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                process_query_limited_information,
                False,
                pid,
            )
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _pid_command_line(pid: int) -> str:
    if os.name != "nt":
        return ""
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                f"(Get-CimInstance Win32_Process -Filter \"ProcessId = {pid}\").CommandLine",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return ""
    return (result.stdout or "").strip()


def _pid_matches_script(pid: int, script_name: str) -> bool:
    if not _pid_is_running(pid):
        return False
    if os.name != "nt":
        return True
    return script_name.lower() in _pid_command_line(pid).lower()


def _claim_tray_instance() -> bool:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    current_pid = os.getpid()
    existing_pid = _read_pid_file(TRAY_PID_FILE)
    if (
        existing_pid is not None
        and existing_pid != current_pid
        and _pid_matches_script(existing_pid, TRAY_SCRIPT_NAME)
    ):
        logger.info("A tray manager is already running (PID %s).", existing_pid)
        return False
    if existing_pid is not None and existing_pid != current_pid:
        logger.warning("Removing stale tray PID file for PID %s.", existing_pid)
    TRAY_PID_FILE.write_text(f"{current_pid}\n", encoding="utf-8")
    return True


def _release_tray_instance() -> None:
    current_pid = os.getpid()
    existing_pid = _read_pid_file(TRAY_PID_FILE)
    if existing_pid == current_pid:
        TRAY_PID_FILE.unlink(missing_ok=True)


class BotSupervisor:
    def __init__(self) -> None:
        self.process: subprocess.Popen[bytes] | None = None

    def is_running(self) -> bool:
        if self.process is not None and self.process.poll() is None:
            return True
        pid = _read_pid()
        if pid is not None and _pid_matches_script(pid, BOT_SCRIPT_NAME):
            return True
        PID_FILE.unlink(missing_ok=True)
        return False

    def start(self) -> bool:
        if self.is_running():
            return False

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        environment = os.environ.copy()
        environment["PYTHONUTF8"] = "1"
        self.process = subprocess.Popen(
            [python_for_background(), "-B", str(BOT_SCRIPT)],
            cwd=SCRIPT_DIR,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        PID_FILE.write_text(f"{self.process.pid}\n", encoding="utf-8")
        return True

    def stop(self) -> bool:
        pid = self.process.pid if self.process is not None else _read_pid()
        if pid is None or not _pid_matches_script(pid, BOT_SCRIPT_NAME):
            PID_FILE.unlink(missing_ok=True)
            return False

        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.process.kill()
        elif os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            os.kill(pid, 15)

        PID_FILE.unlink(missing_ok=True)
        self.process = None
        return True

    def restart(self) -> None:
        self.stop()
        self.start()


def create_tray_icon_image():
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    drawing = ImageDraw.Draw(image)
    drawing.rounded_rectangle(
        (4, 4, 60, 60),
        radius=12,
        fill=(22, 30, 46, 255),
        outline=(255, 255, 255, 255),
        width=3,
    )
    drawing.rectangle((9, 9, 55, 24), fill=(73, 196, 255, 255))
    drawing.ellipse((44, 44, 57, 57), fill=(57, 255, 136, 255))

    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 22)
    except OSError:
        font = ImageFont.load_default()

    label = "AI"
    bbox = drawing.textbbox((0, 0), label, font=font)
    x = (64 - (bbox[2] - bbox[0])) // 2
    y = 26
    drawing.text((x, y), label, font=font, fill=(255, 255, 255, 255))
    return image


def main() -> int:
    configure_logging()
    llm_report_core.load_environment()

    if not _claim_tray_instance():
        return 0

    try:
        import pystray
    except ImportError:
        _release_tray_instance()
        logger.error("pystray is not installed. Run python -m pip install -r requirements.txt")
        return 1

    supervisor = BotSupervisor()
    worker = resume_worker.ResumeWorker()
    worker_stop_event = threading.Event()

    def resume_loop() -> None:
        while not worker_stop_event.is_set():
            try:
                worker.poll()
            except Exception:
                pass
            worker_stop_event.wait(resume_queue_interval_seconds())

    worker_thread = threading.Thread(target=resume_loop, daemon=True)

    def status_label(_: object) -> str:
        key = "tray_status_running" if supervisor.is_running() else "tray_status_stopped"
        return llm_report_core.translate(key)

    def notify(icon, message_key: str) -> None:
        icon.notify(llm_report_core.translate(message_key), startup.APP_NAME)
        icon.update_menu()

    def start_bot(icon, _: object) -> None:
        changed = supervisor.start()
        notify(icon, "tray_bot_started" if changed else "tray_bot_already_running")

    def stop_bot(icon, _: object) -> None:
        changed = supervisor.stop()
        notify(icon, "tray_bot_stopped" if changed else "tray_bot_already_stopped")

    def restart_bot(icon, _: object) -> None:
        supervisor.restart()
        notify(icon, "tray_bot_restarted")

    def open_logs(icon, _: object) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        LOG_FILE.touch(exist_ok=True)
        if os.name == "nt" and TAIL_LOGS_SCRIPT.exists():
            os.startfile(TAIL_LOGS_SCRIPT)  # type: ignore[attr-defined]
            return
        os.startfile(LOG_FILE)  # type: ignore[attr-defined]

    def toggle_startup(icon, _: object) -> None:
        try:
            if startup.is_startup_enabled():
                startup.uninstall_startup_shortcut()
                notify(icon, "tray_startup_disabled")
            else:
                startup.install_startup_shortcut()
                notify(icon, "tray_startup_enabled")
        except Exception:
            notify(icon, "tray_startup_failed")

    def quit_app(icon, _: object) -> None:
        worker_stop_event.set()
        worker.stop()
        supervisor.stop()
        icon.stop()

    def setup_icon(icon) -> None:
        icon.visible = True
        logger.info("System-tray icon is visible (PID %s).", os.getpid())
        changed = supervisor.start()
        notify(icon, "tray_bot_started" if changed else "tray_bot_already_running")

    menu = pystray.Menu(
        pystray.MenuItem(status_label, None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(llm_report_core.translate("tray_start_bot"), start_bot),
        pystray.MenuItem(llm_report_core.translate("tray_stop_bot"), stop_bot),
        pystray.MenuItem(llm_report_core.translate("tray_restart_bot"), restart_bot),
        pystray.MenuItem(llm_report_core.translate("tray_open_logs"), open_logs, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            llm_report_core.translate("tray_startup_toggle"),
            toggle_startup,
            checked=lambda _: startup.is_startup_enabled(),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(llm_report_core.translate("tray_quit"), quit_app),
    )
    try:
        icon = pystray.Icon(startup.APP_NAME, create_tray_icon_image(), startup.APP_NAME, menu)
        worker_thread.start()
        logger.info("Starting tray manager (PID %s).", os.getpid())
        icon.run(setup=setup_icon)
        return 0
    except Exception:
        logger.exception("Tray manager stopped because the icon could not be created or run.")
        return 1
    finally:
        worker_stop_event.set()
        worker.stop()
        supervisor.stop()
        _release_tray_instance()


if __name__ == "__main__":
    raise SystemExit(main())
