$startupDir = [Environment]::GetFolderPath("Startup")
$shortcutPaths = @(
    (Join-Path $startupDir "LLM_report_bot.lnk"),
    (Join-Path $startupDir "Your_LLM_Bot.lnk")
)

$removed = $false
foreach ($shortcutPath in $shortcutPaths) {
    if (Test-Path -LiteralPath $shortcutPath) {
        Remove-Item -LiteralPath $shortcutPath
        Write-Host "Startup shortcut removed: $shortcutPath"
        $removed = $true
    }
}

if (-not $removed) {
    Write-Host "Startup shortcut was not installed."
}
