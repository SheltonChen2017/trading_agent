[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$PythonPath,

    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$ConfigPath,

    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory,

    [string]$RepositoryPath,

    [string]$TaskName = "TradingAgent-StrongBuy-Capture",

    [string]$RunAsUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name,

    # Interactive: Credential Guard on this domain-joined host blocks S4U
    # task logons SILENTLY (proven live 2026-08-19 by the overlay tasks;
    # see OPERATIONAL_FACTS). Enforced repo-wide by
    # tests/test_operational_task_resilience.py.
    [ValidateSet("Interactive", "S4U")]
    [string]$TaskLogonType = "Interactive",

    [datetime]$CaptureLocalTime = [datetime]::MinValue
)

# SBR-1 scheduler (capture preregistration section 3). The capture
# CADENCE is monthly; the TRIGGER is daily-weekday because the native
# cmdlets have no monthly parameter set and the runtime is idempotent:
# it exits "up to date" whenever the month's snapshot already exists,
# and a machine that was off on the first weekday captures late with an
# honest timestamp. Registers ONE task and never touches the
# TradingAgent-Paper-*, TradingAgent-ML-Shadow-*, or
# TradingAgent-Overlay-Shadow-* families.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-InstallerPreconditions {
    param(
        [Parameter(Mandatory = $true)][string]$InterpreterPath,
        [switch]$SkipElevationCheck
    )
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (
        -not $SkipElevationCheck -and
        -not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    ) {
        throw (
            "Registering this scheduled task requires elevation. Re-run " +
            "from a PowerShell session started with 'Run as Administrator'."
        )
    }
    $item = Get-Item -LiteralPath $InterpreterPath -Force
    $isReparse = [bool]($item.Attributes -band [IO.FileAttributes]::ReparsePoint)
    if ($isReparse -or $item.Length -eq 0) {
        throw (
            "$InterpreterPath is a Microsoft Store app execution alias " +
            "(zero-byte reparse point), not a real interpreter."
        )
    }
}

function Quote-TaskArgument {
    param([Parameter(Mandatory = $true)][string]$Value)
    return '"' + $Value.Replace('"', '\"') + '"'
}

function Convert-EasternClockToLocal {
    param(
        [Parameter(Mandatory = $true)][int]$Hour,
        [Parameter(Mandatory = $true)][int]$Minute
    )
    $eastern = [TimeZoneInfo]::FindSystemTimeZoneById("Eastern Standard Time")
    $easternClock = [datetime]::SpecifyKind(
        [datetime]::Today.AddHours($Hour).AddMinutes($Minute),
        [DateTimeKind]::Unspecified
    )
    return [TimeZoneInfo]::ConvertTimeToUtc($easternClock, $eastern).ToLocalTime()
}

# The protected-family guarantee is enforced, not left as convention
# (SHW4-004 lesson).
$forbiddenPrefixes = @(
    "TradingAgent-Paper", "TradingAgent-ML-Shadow", "TradingAgent-Overlay-Shadow"
)
foreach ($forbidden in $forbiddenPrefixes) {
    if ($TaskName -like "$forbidden*") {
        throw (
            "TaskName '$TaskName' collides with the protected " +
            "'$forbidden*' task family; refusing."
        )
    }
}

if (-not $RepositoryPath) {
    $RepositoryPath = Split-Path -Parent $PSScriptRoot
}
$resolvedRepository = (Resolve-Path -LiteralPath $RepositoryPath).Path
$resolvedPython = (Resolve-Path -LiteralPath $PythonPath).Path
Assert-InstallerPreconditions `
    -InterpreterPath $resolvedPython `
    -SkipElevationCheck:$WhatIfPreference
$resolvedConfig = (Resolve-Path -LiteralPath $ConfigPath).Path
$outputDir = [IO.Path]::GetFullPath($OutputDirectory)
$captureScript = Join-Path $resolvedRepository "scripts\capture_analyst_ratings.py"
if (-not (Test-Path -LiteralPath $captureScript -PathType Leaf)) {
    throw "Required script does not exist: $captureScript"
}

# 17:15 ET per the frozen capture spec — clear of the 16:30 paper capture
# and before the 17:45+ overlay chain, so the cadences never contend.
if ($CaptureLocalTime -eq [datetime]::MinValue) {
    $CaptureLocalTime = Convert-EasternClockToLocal -Hour 17 -Minute 15
}

$arguments = @(
    Quote-TaskArgument $captureScript
    "--config"
    Quote-TaskArgument $resolvedConfig
    "--output-dir"
    Quote-TaskArgument $outputDir
    "capture"
) -join " "

if ($WhatIfPreference) {
    Write-Host "WhatIf: would register $TaskName -> $resolvedPython $arguments at $($CaptureLocalTime.ToShortTimeString()) (Mon-Fri, $TaskLogonType)"
    return
}

$action = New-ScheduledTaskAction `
    -Execute $resolvedPython `
    -Argument $arguments `
    -WorkingDirectory $resolvedRepository
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
    -At $CaptureLocalTime
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$principal = New-ScheduledTaskPrincipal `
    -UserId $RunAsUser `
    -LogonType $TaskLogonType `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Force | Out-Null

$live = Get-ScheduledTask -TaskName $TaskName
[PSCustomObject]@{
    TaskName = $TaskName
    State = $live.State
    LogonType = $live.Principal.LogonType
    RunAsUser = $live.Principal.UserId
    Config = $resolvedConfig
    OutputDirectory = $outputDir
    LocalTime = $CaptureLocalTime.ToShortTimeString()
}
