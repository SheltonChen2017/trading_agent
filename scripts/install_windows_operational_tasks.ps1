[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$PythonPath,

    [Parameter(Mandatory = $true)]
    [string]$DatabasePath,

    [string]$RepositoryPath,

    [string]$TaskPrefix = "TradingAgent-Paper",

    [ValidateRange(5, 60)]
    [int]$OperationsCycleMinutes = 10,

    [datetime]$PaperObservationLocalTime = [datetime]::Today.AddHours(16).AddMinutes(30),

    [string]$AlertsJsonlPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Quote-TaskArgument {
    param([Parameter(Mandatory = $true)][string]$Value)
    return '"' + $Value.Replace('"', '\"') + '"'
}

if (-not $RepositoryPath) {
    $RepositoryPath = Split-Path -Parent $PSScriptRoot
}
$resolvedRepository = (Resolve-Path -LiteralPath $RepositoryPath).Path
$resolvedPython = (Resolve-Path -LiteralPath $PythonPath).Path
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

$databaseArgument = Quote-TaskArgument $database
$alertsArgument = Quote-TaskArgument $alerts
$assistantArgument = Quote-TaskArgument $assistantScript
$watchdogArgument = Quote-TaskArgument $watchdogScript

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
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn
$observationTrigger = New-ScheduledTaskTrigger `
    -Weekly `
    -WeeksInterval 1 `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
    -At $PaperObservationLocalTime

$shortSettings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 8)
$longSettings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 10 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

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
        Trigger = $logonTrigger
        Settings = $longSettings
    },
    @{
        Name = "$TaskPrefix-Watchdog"
        Description = "Continuously record operational heartbeats and durable alerts."
        Action = $watchdogAction
        Trigger = $logonTrigger
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

foreach ($task in $tasks) {
    if ($PSCmdlet.ShouldProcess($task.Name, "Register or replace scheduled task")) {
        Register-ScheduledTask `
            -TaskName $task.Name `
            -Description $task.Description `
            -Action $task.Action `
            -Trigger $task.Trigger `
            -Settings $task.Settings `
            -Force | Out-Null
    }
}

$tasks | ForEach-Object {
    [PSCustomObject]@{
        TaskName = $_.Name
        CurrentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        Database = $database
        AlertsJsonl = $alerts
    }
}
