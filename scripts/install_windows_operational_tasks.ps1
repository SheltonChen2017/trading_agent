[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$PythonPath,

    [Parameter(Mandatory = $true)]
    [string]$DatabasePath,

    [string]$RepositoryPath,

    [string]$TaskPrefix = "TradingAgent-Paper",

    [string]$RunAsUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name,

    # Interactive: Credential Guard on domain-joined Windows 11 blocks S4U
    # task logons SILENTLY (occurrence consumed, no run attempt, no error;
    # proven live 2026-08-19 by the overlay tasks). The setup wrapper always
    # passed Interactive explicitly; the default must not be a trap for a
    # direct invocation.
    [ValidateSet("Interactive", "S4U")]
    [string]$TaskLogonType = "Interactive",

    [ValidateRange(5, 60)]
    [int]$OperationsCycleMinutes = 10,

    # How often the long-running tasks re-check that they are still alive.
    [ValidateRange(1, 60)]
    [int]$LongRunningHealMinutes = 5,

    [datetime]$PaperObservationLocalTime = [datetime]::MinValue,

    [string]$AlertsJsonlPath
)

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
            "Administrator'. Checked up front so the failure is one clear " +
            "message rather than one 'Access is denied' per task."
        )
    }
    # Test-Path -PathType Leaf returns true for a Microsoft Store app execution
    # alias, which is a zero-byte reparse point rather than an executable. Such
    # an alias resolves only inside an interactive session with the package
    # registered, so a scheduled task pointed at one can fail to launch while
    # the task itself looks perfectly healthy -- the silent-failure mode this
    # whole pipeline exists to avoid.
    $item = Get-Item -LiteralPath $InterpreterPath -Force
    $isReparse = [bool]($item.Attributes -band [IO.FileAttributes]::ReparsePoint)
    if ($isReparse -or $item.Length -eq 0) {
        throw (
            "$InterpreterPath is a Microsoft Store app execution alias " +
            "(zero-byte reparse point), not a real interpreter. A scheduled " +
            "task cannot rely on it. Install Python from python.org, or point " +
            "-PythonPath at a virtual environment's Scripts\python.exe, and " +
            "re-run."
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
$database = [IO.Path]::GetFullPath($DatabasePath)
$alerts = if ($AlertsJsonlPath) {
    [IO.Path]::GetFullPath($AlertsJsonlPath)
}
else {
    Join-Path $resolvedRepository "data\alerts.jsonl"
}
$assistantScript = Join-Path $resolvedRepository "scripts\run_personal_assistant.py"
$watchdogScript = Join-Path $resolvedRepository "scripts\run_operations_watchdog.py"
foreach ($requiredPath in @($assistantScript, $watchdogScript)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required script does not exist: $requiredPath"
    }
}

# The evidence capture is defined by the NYSE clock, not by the host's wall
# clock. 16:30 Eastern is after both the normal 16:00 close and 13:00 half-day
# close; TimeZoneInfo applies the date's Eastern and local DST rules.
if ($PaperObservationLocalTime -eq [datetime]::MinValue) {
    $PaperObservationLocalTime = Convert-EasternClockToLocal -Hour 16 -Minute 30
}

$databaseArgument = Quote-TaskArgument $database
$alertsArgument = Quote-TaskArgument $alerts
$assistantArgument = Quote-TaskArgument $assistantScript
$watchdogArgument = Quote-TaskArgument $watchdogScript

# ScheduledTasks object construction can itself require access to the local
# Task Scheduler CIM provider.  A non-elevated operator must still be able to
# inspect a -WhatIf plan, so return a data-only preview before invoking any
# New-ScheduledTask* cmdlet.
if ($WhatIfPreference) {
    @(
        @{ Name = "$TaskPrefix-OperationsCycle"; Command = "$assistantArgument --database $databaseArgument operations-cycle --cancel-stale --alerts-jsonl $alertsArgument" },
        @{ Name = "$TaskPrefix-OrderMonitor"; Command = "$assistantArgument --database $databaseArgument monitor-orders --cancel-stale --poll-seconds 30" },
        @{ Name = "$TaskPrefix-Watchdog"; Command = "$watchdogArgument --database $databaseArgument --interval-seconds 60 --alerts-jsonl $alertsArgument" },
        @{ Name = "$TaskPrefix-PaperObservation"; Command = "$assistantArgument --database $databaseArgument paper-observation --cancel-stale --alerts-jsonl $alertsArgument" }
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
            AlertsJsonl = $alerts
        }
    }
    return
}

$cycleAction = New-ScheduledTaskAction `
    -Execute $resolvedPython `
    -Argument "$assistantArgument --database $databaseArgument operations-cycle --cancel-stale --alerts-jsonl $alertsArgument" `
    -WorkingDirectory $resolvedRepository
$monitorAction = New-ScheduledTaskAction `
    -Execute $resolvedPython `
    -Argument "$assistantArgument --database $databaseArgument monitor-orders --cancel-stale --poll-seconds 30" `
    -WorkingDirectory $resolvedRepository
$watchdogAction = New-ScheduledTaskAction `
    -Execute $resolvedPython `
    -Argument "$watchdogArgument --database $databaseArgument --interval-seconds 60 --alerts-jsonl $alertsArgument" `
    -WorkingDirectory $resolvedRepository
$observationAction = New-ScheduledTaskAction `
    -Execute $resolvedPython `
    -Argument "$assistantArgument --database $databaseArgument paper-observation --cancel-stale --alerts-jsonl $alertsArgument" `
    -WorkingDirectory $resolvedRepository

$cycleTrigger = New-ScheduledTaskTrigger `
    -Once `
    -At ((Get-Date).AddMinutes(1)) `
    -RepetitionInterval (New-TimeSpan -Minutes $OperationsCycleMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
# The startup/logon trigger fires exactly ONCE per boot or logon. On its
# own that makes a long-running task unrecoverable: the two console-hosted
# tasks were observed terminating with 0xC000013A (STATUS_CONTROL_C_EXIT)
# when their windows were closed, and nothing ever restarted them --
# RestartCount does not cover that exit, because Task Scheduler treats a
# console-close as the task being stopped rather than failing. Order-stream
# monitoring and the health heartbeat then stayed silently dead until
# somebody noticed by hand, and the Watchdog is precisely the component
# that would otherwise have raised the alarm.
#
# The repeating companion trigger below is the recovery path. It composes
# with MultipleInstances=IgnoreNew already set in $longSettings: a tick
# while the task is healthy does not start a second process. It can still
# update LastRunTime/LastTaskResult with an "already running" HRESULT, so
# verify_windows_evidence_tasks.ps1 treats State=Running as healthy even
# when the latest heal tick was refused. IgnoreNew is necessary but not
# sufficient: an orphaned console process can leave the scheduler free to
# start a second worker. Long-runners also take a process-level singleton
# lock in Python (assistant/process_singleton.py).
$selfHealTrigger = New-ScheduledTaskTrigger `
    -Once `
    -At ((Get-Date).AddMinutes(1)) `
    -RepetitionInterval (New-TimeSpan -Minutes $LongRunningHealMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$longRunningTrigger = if ($TaskLogonType -eq "S4U") {
    @((New-ScheduledTaskTrigger -AtStartup), $selfHealTrigger)
}
else {
    @((New-ScheduledTaskTrigger -AtLogOn -User $RunAsUser), $selfHealTrigger)
}
$observationTrigger = New-ScheduledTaskTrigger `
    -Weekly `
    -WeeksInterval 1 `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
    -At $PaperObservationLocalTime

# AllowStartIfOnBatteries / DontStopIfGoingOnBatteries are not conveniences.
# New-ScheduledTaskSettingsSet defaults BOTH battery guards to on, which on
# a laptop means unplugging the machine stops order monitoring, the health
# heartbeat, and the reconciliation cycle -- and the observation that makes
# a session count toward the evidence epoch simply never runs. An evidence
# gap caused by a power cable is indistinguishable, after the fact, from an
# evidence gap caused by a defect.
$shortSettings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 8)
$longSettings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 10 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal `
    -UserId $RunAsUser `
    -LogonType $TaskLogonType `
    -RunLevel Limited

$tasks = @(
    @{
        Name = "$TaskPrefix-OperationsCycle"
        Description = "Reconcile paper orders and ledger, verify backup cadence, and record operational health."
        Action = $cycleAction
        Trigger = $cycleTrigger
        Settings = $shortSettings
    },
    @{
        Name = "$TaskPrefix-OrderMonitor"
        Description = "Continuously reconcile Alpaca paper-order state with polling fallback."
        Action = $monitorAction
        Trigger = $longRunningTrigger
        Settings = $longSettings
    },
    @{
        Name = "$TaskPrefix-Watchdog"
        Description = "Continuously record operational heartbeats and durable alerts."
        Action = $watchdogAction
        Trigger = $longRunningTrigger
        Settings = $longSettings
    },
    @{
        Name = "$TaskPrefix-PaperObservation"
        Description = "Capture one immutable, reconciled paper NAV observation after each weekday close."
        Action = $observationAction
        Trigger = $observationTrigger
        Settings = $shortSettings
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
            -Settings $task.Settings `
            -Principal $principal `
            -Force `
            -ErrorAction SilentlyContinue `
            -ErrorVariable registrationErrors | Out-Null
        # Existence alone is not success: an older task may already have this
        # name while its replacement just failed. Capture the CIM error AND
        # read back the exact (non-wildcard) task name.
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
        "Scheduler service, then retry. No success summary is printed."
    )
}

if (-not $attempted) {
    # -WhatIf: describe the plan, and say so.
    $tasks | ForEach-Object {
        [PSCustomObject]@{
            TaskName = $_.Name
            Status = "planned (WhatIf)"
            RunAsUser = $RunAsUser
            RunLevel = "Limited"
            LogonType = $TaskLogonType
            Database = $database
            AlertsJsonl = $alerts
        }
    }
    return
}

# Report what the scheduler actually holds, not what we intended to create.
$tasks | ForEach-Object {
    $live = Get-InstalledTaskExact -Name $_.Name
    [PSCustomObject]@{
        TaskName = $live.TaskName
        Status = "registered"
        State = $live.State
        RunAsUser = $live.Principal.UserId
        RunLevel = $live.Principal.RunLevel
        LogonType = $live.Principal.LogonType
        Database = $database
        AlertsJsonl = $alerts
    }
}
