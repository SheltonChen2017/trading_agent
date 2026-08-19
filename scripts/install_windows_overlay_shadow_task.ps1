[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$PythonPath,

    [Parameter(Mandatory = $true)]
    [string]$DatabasePath,

    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$ConfigPath,

    [string]$RepositoryPath,

    [string]$TaskPrefix = "TradingAgent-Overlay-Shadow",

    [string]$RunAsUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name,

    [ValidateSet("Interactive", "S4U")]
    [string]$TaskLogonType = "S4U",

    [datetime]$ObserveLocalTime = [datetime]::MinValue,

    [datetime]$MatureLocalTime = [datetime]::MinValue,

    [datetime]$SufficiencyLocalTime = [datetime]::MinValue,

    [string]$SufficiencyOutputPath
)

# SHW-4 scheduler (design doc section 4; deferred from SHW-2 by SHW2-004).
# The observation CADENCE is monthly; the TRIGGERS are daily because the
# native ScheduledTasks cmdlets have no monthly parameter set and the
# runner is idempotent by construction: `observe` exits "up to date" on
# every day that is not a fresh completed month-end, and a machine that
# was off records gap refusal rows at the next run. Registers three
# tasks (observe / mature / sufficiency) and NEVER touches the
# TradingAgent-Paper-* or TradingAgent-ML-Shadow-* tasks.

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
            "Registering these scheduled tasks requires elevation. Re-run this " +
            "installer from a PowerShell session started with 'Run as " +
            "Administrator'."
        )
    }
    # A Microsoft Store execution alias is a zero-byte reparse point that a
    # scheduled task cannot launch (same silent-failure hazard the ML shadow
    # installer guards against).
    $item = Get-Item -LiteralPath $InterpreterPath -Force
    $isReparse = [bool]($item.Attributes -band [IO.FileAttributes]::ReparsePoint)
    if ($isReparse -or $item.Length -eq 0) {
        throw (
            "$InterpreterPath is a Microsoft Store app execution alias " +
            "(zero-byte reparse point), not a real interpreter. Point " +
            "-PythonPath at a real python.exe and re-run."
        )
    }
}

function Get-InstalledTaskExact {
    param([Parameter(Mandatory = $true)][string]$Name)
    $escapedName = [WildcardPattern]::Escape($Name)
    return @(
        Get-ScheduledTask -TaskName $escapedName -ErrorAction SilentlyContinue
    ) | Where-Object { $_.TaskName -eq $Name }
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

if (-not $RepositoryPath) {
    $RepositoryPath = Split-Path -Parent $PSScriptRoot
}
$resolvedRepository = (Resolve-Path -LiteralPath $RepositoryPath).Path
$resolvedPython = (Resolve-Path -LiteralPath $PythonPath).Path
Assert-InstallerPreconditions `
    -InterpreterPath $resolvedPython `
    -SkipElevationCheck:$WhatIfPreference
$resolvedConfig = (Resolve-Path -LiteralPath $ConfigPath).Path
$database = [IO.Path]::GetFullPath($DatabasePath)
$sufficiencyOutput = if ($SufficiencyOutputPath) {
    [IO.Path]::GetFullPath($SufficiencyOutputPath)
}
else {
    Join-Path $resolvedRepository "artifacts\overlay-shadow-sufficiency.json"
}
$runnerScript = Join-Path $resolvedRepository "scripts\run_overlay_shadow.py"
if (-not (Test-Path -LiteralPath $runnerScript -PathType Leaf)) {
    throw "Required script does not exist: $runnerScript"
}

# 17:45 / 17:55 / 18:05 Eastern: after the paper capture (16:30 window on
# this host) and the ML shadow chain (16:30-17:15 ET defaults), so the
# cadences never contend for the interpreter or the network at once.
if ($ObserveLocalTime -eq [datetime]::MinValue) {
    $ObserveLocalTime = Convert-EasternClockToLocal -Hour 17 -Minute 45
}
if ($MatureLocalTime -eq [datetime]::MinValue) {
    $MatureLocalTime = Convert-EasternClockToLocal -Hour 17 -Minute 55
}
if ($SufficiencyLocalTime -eq [datetime]::MinValue) {
    $SufficiencyLocalTime = Convert-EasternClockToLocal -Hour 18 -Minute 5
}

$scriptArgument = Quote-TaskArgument $runnerScript
$databaseArgument = Quote-TaskArgument $database
$configArgument = Quote-TaskArgument $resolvedConfig
$sufficiencyArgument = Quote-TaskArgument $sufficiencyOutput
$commonArguments = "$scriptArgument --database $databaseArgument --config $configArgument"

if ($WhatIfPreference) {
    @(
        @{ Name = "$TaskPrefix-Observe"; Command = "$commonArguments observe" },
        @{ Name = "$TaskPrefix-Mature"; Command = "$commonArguments mature" },
        @{ Name = "$TaskPrefix-Sufficiency"; Command = "$commonArguments sufficiency --output $sufficiencyArgument" }
    ) | ForEach-Object {
        [PSCustomObject]@{
            TaskName = $_.Name
            Status = "planned (WhatIf)"
            Execute = $resolvedPython
            Arguments = $_.Command
            WorkingDirectory = $resolvedRepository
            RunAsUser = $RunAsUser
            RunLevel = "Limited"
            LogonType = $TaskLogonType
            Database = $database
            Config = $resolvedConfig
            SufficiencyOutput = $sufficiencyOutput
        }
    }
    return
}

$observeAction = New-ScheduledTaskAction `
    -Execute $resolvedPython `
    -Argument "$commonArguments observe" `
    -WorkingDirectory $resolvedRepository
$matureAction = New-ScheduledTaskAction `
    -Execute $resolvedPython `
    -Argument "$commonArguments mature" `
    -WorkingDirectory $resolvedRepository
$sufficiencyAction = New-ScheduledTaskAction `
    -Execute $resolvedPython `
    -Argument "$commonArguments sufficiency --output $sufficiencyArgument" `
    -WorkingDirectory $resolvedRepository

$observeTrigger = New-ScheduledTaskTrigger `
    -Weekly -WeeksInterval 1 `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
    -At $ObserveLocalTime
$matureTrigger = New-ScheduledTaskTrigger `
    -Weekly -WeeksInterval 1 `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
    -At $MatureLocalTime
$sufficiencyTrigger = New-ScheduledTaskTrigger `
    -Weekly -WeeksInterval 1 `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
    -At $SufficiencyLocalTime

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$principal = New-ScheduledTaskPrincipal `
    -UserId $RunAsUser `
    -LogonType $TaskLogonType `
    -RunLevel Limited

$tasks = @(
    @{
        Name = "$TaskPrefix-Observe"
        Description = "Overlay shadow monthly observation (idempotent; no-ops until a fresh completed month-end). Observation only; no order authority."
        Action = $observeAction
        Trigger = $observeTrigger
    },
    @{
        Name = "$TaskPrefix-Mature"
        Description = "Attach adjacent-month overlay outcomes exactly once."
        Action = $matureAction
        Trigger = $matureTrigger
    },
    @{
        Name = "$TaskPrefix-Sufficiency"
        Description = "Write the counts-only overlay sufficiency report (no statistic at any count)."
        Action = $sufficiencyAction
        Trigger = $sufficiencyTrigger
    }
)

$attempted = $false
$failedTasks = New-Object System.Collections.Generic.List[string]
foreach ($task in $tasks) {
    if ($PSCmdlet.ShouldProcess($task.Name, "Register or replace scheduled task")) {
        $attempted = $true
        $registrationErrors = @()
        Register-ScheduledTask `
            -TaskName $task.Name `
            -Description $task.Description `
            -Action $task.Action `
            -Trigger $task.Trigger `
            -Settings $settings `
            -Principal $principal `
            -Force `
            -ErrorAction SilentlyContinue `
            -ErrorVariable registrationErrors | Out-Null
        $live = Get-InstalledTaskExact -Name $task.Name
        if (@($registrationErrors).Count -gt 0 -or -not $live) {
            $detail = if (@($registrationErrors).Count -gt 0) {
                (@($registrationErrors) | ForEach-Object { $_.Exception.Message }) -join "; "
            }
            else {
                "task was not present after registration"
            }
            $failedTasks.Add("$($task.Name): $detail")
        }
    }
}

if ($failedTasks.Count -gt 0) {
    throw (
        "Failed to register or replace: " + ($failedTasks -join ", ") + ". " +
        "Verify the elevated session, RunAsUser, TaskLogonType, and Task " +
        "Scheduler service, then retry."
    )
}

$tasks | ForEach-Object {
    $live = if ($attempted) { Get-InstalledTaskExact -Name $_.Name } else { $null }
    [PSCustomObject]@{
        TaskName = $_.Name
        Status = if ($attempted) { "registered" } else { "planned (WhatIf)" }
        State = if ($live) { $live.State } else { $null }
        RunAsUser = if ($live) { $live.Principal.UserId } else { $RunAsUser }
        RunLevel = if ($live) { $live.Principal.RunLevel } else { "Limited" }
        Database = $database
        Config = $resolvedConfig
        SufficiencyOutput = $sufficiencyOutput
        MultipleInstances = "IgnoreNew"
        ExecutionTimeLimitMinutes = 30
    }
}
