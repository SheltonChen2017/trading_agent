# Launches the personal trading assistant from the DEVELOPMENT checkout
# against a DISPOSABLE database, so unreleased code can be tried without
# touching the operator database that holds the active evidence epoch.
#
# Why this script exists rather than a documented command: the operator
# database lives at data\trading_assistant.db INSIDE this development folder,
# and that same path is the app's fallback when TRADING_ASSISTANT_DB is unset.
# Launching the development app without setting it therefore opens the LIVE
# operator database and applies whatever migrations this tree carries. There
# is no warning when that happens, so the safe path is a script that cannot
# forget.
$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$developmentDatabase = Join-Path $repositoryRoot "data\dev_scratch.db"
$operatorDatabase = Join-Path $repositoryRoot "data\trading_assistant.db"

if ($developmentDatabase -eq $operatorDatabase) {
    throw "Refusing to launch: the development database resolved to the operator database path."
}

$env:TRADING_ASSISTANT_DB = $developmentDatabase

# Alpaca credentials are loaded so quote-driven and position-driven features
# are actually exercisable. Read-only use is safe. Submitting an order is NOT:
# the paper ACCOUNT is shared with the operational runtime, so an approved
# order from development code would appear in the active epoch's broker
# record even though this database is separate.
foreach ($credentialName in @("APCA_API_KEY_ID", "APCA_API_SECRET_KEY", "ANTHROPIC_API_KEY")) {
    $currentValue = [Environment]::GetEnvironmentVariable($credentialName, "User")
    if (-not [string]::IsNullOrWhiteSpace($currentValue)) {
        Set-Item -Path "Env:$credentialName" -Value $currentValue
    }
}

Set-Location $repositoryRoot
Write-Host "DEVELOPMENT app -- not the frozen operational runtime." -ForegroundColor Yellow
Write-Host "Checkout:           " (git rev-parse --short HEAD) "|" (git rev-parse --abbrev-ref HEAD)
Write-Host "Scratch database:   $env:TRADING_ASSISTANT_DB"
Write-Host "Operator database:  $operatorDatabase (NOT opened)"
Write-Host "Credentials:        loaded fresh from user scope (values not shown)"
Write-Host "Do NOT approve/submit orders here: the paper account is shared with the active epoch." -ForegroundColor Yellow

& "$repositoryRoot\.venv\Scripts\python.exe" -m streamlit run scripts\personal_assistant_ui.py
