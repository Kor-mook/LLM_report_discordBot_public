param(
    [int]$Tail = 100,
    [switch]$NoWait
)

$ErrorActionPreference = "Stop"

try {
    $utf8 = [System.Text.UTF8Encoding]::new($false)
    [Console]::OutputEncoding = $utf8
    $OutputEncoding = $utf8
}
catch {
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$logPath = Join-Path $scriptDir "logs\llm_report_bot.log"

if (-not (Test-Path -LiteralPath $logPath)) {
    New-Item -ItemType File -Path $logPath -Force | Out-Null
}

function Write-ColoredLogLine {
    param([string]$Line)

    if ($Line -match "\[CRITICAL\]") {
        Write-Host $Line -ForegroundColor Red
        return
    }
    if ($Line -match "\[ERROR\]") {
        Write-Host $Line -ForegroundColor Red
        return
    }
    if ($Line -match "\[WARNING\]") {
        Write-Host $Line -ForegroundColor DarkYellow
        return
    }
    if ($Line -match "\[INFO\]") {
        Write-Host $Line -ForegroundColor Gray
        return
    }

    Write-Host $Line
}

Write-Host "[LLM_report_bot] Live logs. Close this window to stop viewing logs." -ForegroundColor Cyan
Write-Host "[LLM_report_bot] File: $logPath" -ForegroundColor DarkGray
Write-Host "[LLM_report_bot] Colors: ERROR/CRITICAL=red, WARNING=orange, INFO=gray" -ForegroundColor DarkGray
Write-Host ""

$contentArgs = @{
    LiteralPath = $logPath
    Tail = $Tail
    Encoding = "UTF8"
}

if (-not $NoWait) {
    $contentArgs["Wait"] = $true
}

Get-Content @contentArgs | ForEach-Object {
    Write-ColoredLogLine $_
}
