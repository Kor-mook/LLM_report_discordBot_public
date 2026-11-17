@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title LLM_report_bot live logs
if not exist "logs\llm_report_bot.log" type nul > "logs\llm_report_bot.log"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tail_llm_report_logs.ps1"
