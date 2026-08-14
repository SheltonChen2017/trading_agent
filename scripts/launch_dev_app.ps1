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
param(
    # Explicit escape hatch for an owner-authorized PAPER-order test. This
    # does not bypass any persistent or inherited kill switch; it only stops
    # this launcher from adding its own development-only halt.
    [switch]$AllowPaperOrders
)

$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$developmentDatabase = Join-Path $repositoryRoot "data\dev_scratch.db"
$operatorDatabase = Join-Path $repositoryRoot "data\trading_assistant.db"

if ($developmentDatabase -eq $operatorDatabase) {
    throw "Refusing to launch: the development database resolved to the operator database path."
}

$env:TRADING_ASSISTANT_DB = $developmentDatabase

# A separate database is not enough isolation: the development and
# operational runtimes still use the same Alpaca paper account. Default to an
# execution halt so an approval click in unreleased code cannot contaminate
# the active epoch's broker record. Deliberate paper-order testing requires
# the explicit switch above and remains subject to every other kill switch.
if (-not $AllowPaperOrders) {
    $env:TRADING_ASSISTANT_KILL_SWITCH = "1"
}

# Reload every provider key the UI supports so a long-lived parent shell
# cannot hand the app a stale pre-rotation value. This mirrors the reviewed
# operational launcher contract; values are never printed or persisted.
$UserScopeCredentialNames = @(
    "APCA_API_KEY_ID",
    "APCA_API_SECRET_KEY",
    "ANTHROPIC_API_KEY",
    "FINNHUB_API_KEY",
    "DATABENTO_API_KEY"
)
foreach ($credentialName in $UserScopeCredentialNames) {
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
Write-Host "Credentials:        supported provider keys loaded fresh from user scope (values not shown)"
if ($AllowPaperOrders) {
    Write-Host "Order submission:   EXPLICITLY OPTED IN for the shared Alpaca paper account." -ForegroundColor Red
    Write-Host "                     Existing environment/persistent kill switches still apply." -ForegroundColor Yellow
} else {
    Write-Host "Order submission:   BLOCKED by the development environment kill switch." -ForegroundColor Green
    Write-Host "                     The paper account is shared with the active epoch." -ForegroundColor Yellow
}

& "$repositoryRoot\.venv\Scripts\python.exe" -m streamlit run scripts\personal_assistant_ui.py
