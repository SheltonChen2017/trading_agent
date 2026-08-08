# Bootstrap the model-2 operational setup on a Windows machine.
#
# Creates (idempotently):
#   1. the pinned OPERATIONAL checkout (a separate clone that stays on the
#      frozen evidence-epoch commit while development continues elsewhere);
#   2. the dedicated task-interpreter VENV with the exact pinned
#      requirements (a real python.exe -- scheduled tasks cannot launch the
#      Microsoft Store's zero-byte app-execution aliases, and the Store's
#      versioned install path breaks on auto-updates mid-epoch);
#   3. the app LAUNCHER (outside every repo, so no worktree is dirtied):
#      starts Streamlit from the operational checkout against the single
#      operator database; and
#   4. the ELEVATED INSTALL wrapper the owner runs once as Administrator to
#      register, start, and verify the four operational scheduled tasks.
#
# Non-elevated. Run from any checkout of this repository:
#
#   pwsh -NoProfile -File scripts\setup_operational_host.ps1
#
# ============================ EVIDENCE WARNING ============================
# A paper evidence epoch binds ONE operational host, ONE frozen commit, and
# ONE operator database. Running this script on a second computer prepares
# that machine; it must NOT run the scheduled cadence there while another
# host's epoch is active -- two hosts collecting into (or beside) one epoch
# corrupts the evidence. Use a second setup only to (a) develop with the
# same launcher conventions, or (b) deliberately MOVE the operational host,
# which requires closing the epoch first (`paper-epoch-close`) and moving
# or re-bootstrapping the operator database on the new host.
# ==========================================================================
#
# Machine facts this script cannot carry for you:
#   - Alpaca PAPER credentials (APCA_API_KEY_ID / APCA_API_SECRET_KEY) must
#     exist as user-scope environment variables on the new machine; they
#     are never stored in the repository.
#   - assistant/my_policy.json is machine-local (gitignored); copy it into
#     the operational checkout yourself if you use a custom policy.
#   - Credential Guard (standard on domain-joined Windows 11) blocks S4U
#     task logons, so the elevated wrapper installs with -TaskLogonType
#     Interactive: tasks run while the owner is logged on (a locked screen
#     counts). Verified on the first operational host, 2026-08-05.

[CmdletBinding()]
param(
    [string]$RepoUrl = "https://github.com/SheltonChen2017/trading_agent.git",

    [string]$OperationalPath = "C:\git\trading_agent_operational",

    [string]$VenvPath = "C:\git\trading_agent_venv",

    # The single operator database. Default matches the first operational
    # host's layout (the development checkout's data folder). On a NEW
    # operational host, point this wherever the (moved or freshly
    # bootstrapped) operator database lives; every component must use the
    # SAME path or the evidence splits.
    [string]$OperatorDatabasePath = "C:\git\customizedAgent\trading_agent\data\trading_assistant.db",

    [string]$LauncherPath = "C:\git\launch_trading_app.ps1",

    [string]$ElevatedInstallerPath = "C:\git\install_operational_tasks_elevated.ps1",

    # A real interpreter used only to create the dedicated venv. Override
    # this when `python` resolves to a Microsoft Store app-execution alias.
    [string]$BootstrapPythonPath = "python",

    # Account the scheduled tasks run as; defaults to the current user in
    # DOMAIN\name form (pass the FULL form -- Task Scheduler stores the
    # short form, but credential verification compares the full identity).
    [string]$RunAsUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-NativeSuccess {
    param([Parameter(Mandatory = $true)][string]$Operation)
    # Windows PowerShell 5.1 does not turn a native nonzero exit into a
    # terminating error when ErrorActionPreference is Stop.
    if ($LASTEXITCODE -ne 0) {
        throw "$Operation failed with exit code $LASTEXITCODE."
    }
}

Write-Host "== 1/4 Operational checkout: $OperationalPath =="
if (Test-Path -LiteralPath (Join-Path $OperationalPath ".git")) {
    git -C $OperationalPath fetch --prune origin
    Assert-NativeSuccess -Operation "git fetch in the operational checkout"
    Write-Host "(existing clone left on its current commit -- if an epoch is active, do NOT move it)"
} else {
    git clone $RepoUrl $OperationalPath
    Assert-NativeSuccess -Operation "operational checkout clone"
}
$operationalStatus = @(git -C $OperationalPath status --porcelain)
Assert-NativeSuccess -Operation "operational checkout cleanliness check"
if ($operationalStatus.Count -gt 0) {
    throw "Operational checkout is dirty; refusing to generate launch or scheduler wrappers."
}
git -C $OperationalPath status --short --branch
Assert-NativeSuccess -Operation "operational checkout status"

Write-Host "== 2/4 Task-interpreter venv: $VenvPath =="
$venvPython = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    $bootstrapCommand = Get-Command $BootstrapPythonPath -ErrorAction Stop
    $bootstrapPython = $bootstrapCommand.Source
    if ([string]::IsNullOrWhiteSpace($bootstrapPython)) {
        throw "BootstrapPythonPath did not resolve to an executable."
    }
    $bootstrapItem = Get-Item -LiteralPath $bootstrapPython
    if ($bootstrapItem.Length -eq 0 -or ($bootstrapItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw (
            "BootstrapPythonPath resolves to a Microsoft Store/app-execution " +
            "alias. Install a real Python interpreter or pass its full path."
        )
    }
    & $bootstrapPython -m venv $VenvPath
    Assert-NativeSuccess -Operation "task-interpreter venv creation"
}
$venvItem = Get-Item -LiteralPath $venvPython
if ($venvItem.Length -eq 0 -or ($venvItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw "The venv interpreter is a zero-byte/reparse alias; a real python.exe is required."
}
& $venvPython -m pip install --quiet -r (Join-Path $OperationalPath "requirements.txt")
Assert-NativeSuccess -Operation "pinned requirement installation"
& $venvPython -c "import pandas, streamlit, alpaca, yfinance, sklearn, pytest; print('venv imports OK')"
Assert-NativeSuccess -Operation "task-interpreter import probe"

Write-Host "== 3/4 Launcher: $LauncherPath =="
@"
# Launches the personal trading assistant from the OPERATIONAL checkout,
# which stays pinned to the frozen evidence-epoch commit while development
# continues separately (epoch model 2). Generated by
# scripts/setup_operational_host.ps1; regenerate rather than editing.
`$env:TRADING_ASSISTANT_DB = "$OperatorDatabasePath"
# Lift credentials from the USER-SCOPE REGISTRY at every launch.
# Windows processes inherit their parent's environment, so a long-lived
# shell hands the app whatever credentials existed when the shell started;
# after the owner rotated keys (2026-08-05), the app presented the revoked
# key and Alpaca answered "unauthorized". Reading the registry here makes
# each launch use the currently stored values without displaying or
# persisting them.
#
# ANTHROPIC_API_KEY belongs in this list for the same reason (2026-08-07):
# it was set at user scope, every check reported it configured, and the app
# still showed no AI features -- because the launcher only lifted the two
# Alpaca names, so the key never reached the process. A credential this
# script does not lift is invisible to the app no matter where it is stored.
`$UserScopeCredentialNames = @(
    "APCA_API_KEY_ID",
    "APCA_API_SECRET_KEY",
    "ANTHROPIC_API_KEY",
    "FINNHUB_API_KEY",
    "DATABENTO_API_KEY"
)
foreach (`$credentialName in `$UserScopeCredentialNames) {
    `$currentValue = [Environment]::GetEnvironmentVariable(`$credentialName, "User")
    if (-not [string]::IsNullOrWhiteSpace(`$currentValue)) {
        Set-Item -Path "Env:`$credentialName" -Value `$currentValue
    }
}
Set-Location "$OperationalPath"
Write-Host "Operational checkout:" (git rev-parse --short HEAD) "|" (git rev-parse --abbrev-ref HEAD)
Write-Host "Operator database:  `$env:TRADING_ASSISTANT_DB"
Write-Host "Credentials:        Supported provider keys loaded fresh from user scope (values not shown)"
& "$venvPython" -m streamlit run scripts\personal_assistant_ui.py
"@ | Set-Content -LiteralPath $LauncherPath -Encoding utf8

Write-Host "== 4/4 Elevated install wrapper: $ElevatedInstallerPath =="
@"
# Installs, starts, and verifies the FOUR operational scheduled tasks.
# RUN FROM AN ELEVATED POWERSHELL ("Run as Administrator"):
#   pwsh -NoProfile -File $ElevatedInstallerPath
# Interactive logon type: Credential Guard blocks S4U task logons on
# domain-joined Windows 11, so tasks run while $RunAsUser is logged on
# (a locked screen counts). Generated by scripts/setup_operational_host.ps1.
`$ErrorActionPreference = "Stop"
pwsh -NoProfile -File "$OperationalPath\scripts\install_windows_operational_tasks.ps1" ``
    -PythonPath "$venvPython" -DatabasePath "$OperatorDatabasePath" ``
    -RunAsUser "$RunAsUser" -TaskLogonType Interactive
if (`$LASTEXITCODE -ne 0) { throw "Installer failed with exit `$LASTEXITCODE" }
foreach (`$name in @(
    "TradingAgent-Paper-OperationsCycle",
    "TradingAgent-Paper-OrderMonitor",
    "TradingAgent-Paper-Watchdog",
    "TradingAgent-Paper-PaperObservation"
)) {
    Start-ScheduledTask -TaskName `$name
    Write-Host "started `$name"
}
Start-Sleep -Seconds 10
pwsh -NoProfile -File "$OperationalPath\scripts\verify_windows_evidence_tasks.ps1" ``
    -RunAsUser "$RunAsUser" -PythonPath "$venvPython" ``
    -DatabasePath "$OperatorDatabasePath" ``
    -Scope operational -ExpectedTaskLogonType Interactive -RequireTaskRun
if (`$LASTEXITCODE -ne 0) {
    throw "Verifier reported failures (exit `$LASTEXITCODE); do not proceed to epoch actions until it exits 0."
}
Write-Host "All four tasks installed, started, and verified."
"@ | Set-Content -LiteralPath $ElevatedInstallerPath -Encoding utf8

Write-Host ""
Write-Host "Setup complete. Remaining manual steps on this machine:"
Write-Host "  1. Ensure Alpaca PAPER credentials exist as user environment variables."
Write-Host "  2. Copy assistant\my_policy.json into $OperationalPath\assistant\ if you use one."
Write-Host "  3. Run $ElevatedInstallerPath from an elevated PowerShell (once)."
Write-Host "  4. Launch the app via $LauncherPath."
Write-Host "REMINDER: one active operational host per evidence epoch -- see the warning at the top of this script."
