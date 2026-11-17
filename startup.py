from __future__ import annotations

import os
import subprocess
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
APP_NAME = "Your_LLM_Bot"
STARTUP_SHORTCUT_NAME = f"{APP_NAME}.lnk"


def startup_directory() -> Path:
    app_data = os.getenv("APPDATA", "").strip()
    if not app_data:
        raise RuntimeError("APPDATA is not available")
    return Path(app_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def startup_shortcut_path() -> Path:
    return startup_directory() / STARTUP_SHORTCUT_NAME


def hidden_launcher_path() -> Path:
    return SCRIPT_DIR / "start_llm_report_tray_hidden.vbs"


def is_startup_enabled() -> bool:
    try:
        return startup_shortcut_path().exists()
    except RuntimeError:
        return False


def install_startup_shortcut() -> None:
    if os.name != "nt":
        raise RuntimeError("Windows startup shortcuts are only supported on Windows")

    launcher = hidden_launcher_path()
    if not launcher.exists():
        raise RuntimeError(f"Hidden launcher not found: {launcher}")

    shortcut = startup_shortcut_path()
    shortcut.parent.mkdir(parents=True, exist_ok=True)
    system_root = os.getenv("SystemRoot", r"C:\Windows")
    wscript = Path(system_root) / "System32" / "wscript.exe"

    def quote(value: str) -> str:
        return value.replace("'", "''")

    command = (
        "$shell = New-Object -ComObject WScript.Shell; "
        f"$shortcut = $shell.CreateShortcut('{quote(str(shortcut))}'); "
        f"$shortcut.TargetPath = '{quote(str(wscript))}'; "
        f"$shortcut.Arguments = '" + '"' + f"{quote(str(launcher))}" + '"' + "'; "
        f"$shortcut.WorkingDirectory = '{quote(str(SCRIPT_DIR))}'; "
        f"$shortcut.Description = '{APP_NAME} tray manager'; "
        "$shortcut.Save()"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        check=False,
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "unknown PowerShell error").strip()
        raise RuntimeError(message)


def uninstall_startup_shortcut() -> None:
    try:
        startup_shortcut_path().unlink(missing_ok=True)
    except RuntimeError:
        return
