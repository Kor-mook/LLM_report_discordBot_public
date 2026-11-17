@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1

if exist "%~dp0start_llm_report_tray_hidden.vbs" (
    start "" "%SystemRoot%\System32\wscript.exe" "%~dp0start_llm_report_tray_hidden.vbs"
    exit /b 0
)

echo [LLM_report_bot] Console-free tray launcher was not found.
echo [LLM_report_bot] Starting tray manager in this console instead.
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -B llm_report_tray.py %*
) else (
    python -B llm_report_tray.py %*
)
