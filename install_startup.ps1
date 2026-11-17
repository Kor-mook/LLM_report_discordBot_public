$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$launcher = Join-Path $scriptDir "start_llm_report_tray_hidden.vbs"
$startupDir = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupDir "LLM_report_bot.lnk"
$legacyShortcutPath = Join-Path $startupDir "Your_LLM_Bot.lnk"

if (-not (Test-Path -LiteralPath $launcher)) {
    throw "Hidden launcher not found: $launcher"
}

if (Test-Path -LiteralPath $legacyShortcutPath) {
    Remove-Item -LiteralPath $legacyShortcutPath
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $env:SystemRoot "System32\wscript.exe"
$shortcut.Arguments = '"' + $launcher + '"'
$shortcut.WorkingDirectory = $scriptDir
$shortcut.Description = "LLM_report_bot tray manager"
$shortcut.Save()

Write-Host "Startup shortcut installed: $shortcutPath"
