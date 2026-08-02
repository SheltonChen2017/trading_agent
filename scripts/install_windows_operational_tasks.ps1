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

    [ValidateSet("Interactive", "S4U")]
    [string]$TaskLogonType = "S4U",

    [ValidateRange(5, 60)]
    [int]$OperationsCycleMinutes = 10,

    [datetime]$PaperObservationLocalTime = [datetime]::Today.AddHours(16).AddMinutes(30),

    [string]$AlertsJsonlPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-InstallerPreconditions {
    param(
        [Parameter(Mandatory = $true)][string]$InterpreterPath
    )
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw (
            "Registering an S4U scheduled task requires elevation. Re-run this " +
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

function Quote-TaskArgument {
    param([Parameter(Mandatory = $true)][string]$Value)
    return '"' + $Value.Replace('"', '\"') + '"'
}

if (-not $RepositoryPath) {
    $RepositoryPath = Split-Path -Parent $PSScriptRoot
}
$resolvedRepository = (Resolve-Path -LiteralPath $RepositoryPath).Path
$resolvedPython = (Resolve-Path -LiteralPath $PythonPath).Path
Assert-InstallerPreconditions -InterpreterPath $resolvedPython
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
$longRunningTrigger = if ($TaskLogonType -eq "S4U") {
    New-ScheduledTaskTrigger -AtStartup
}
else {
    New-ScheduledTaskTrigger -AtLogOn -User $RunAsUser
}
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
        Register-ScheduledTask `
            -TaskName $task.Name `
            -Description $task.Description `
            -Action $task.Action `
            -Trigger $task.Trigger `
            -Settings $task.Settings `
            -Principal $principal `
            -Force `
            -ErrorAction SilentlyContinue | Out-Null
        # Register-ScheduledTask is a CIM cmdlet, and CIM errors do not honour
        # $ErrorActionPreference = "Stop". Without reading the task back, an
        # unelevated run prints four "Access is denied" lines and then a full
        # success table -- the operator believes evidence collection is live
        # and it is collecting nothing. Confirm, never assume.
        if (-not (Get-ScheduledTask -TaskName $task.Name -ErrorAction SilentlyContinue)) {
            $failedTasks.Add($task.Name)
        }
    }
}

if ($failedTasks.Count -gt 0) {
    throw (
        "Failed to register: " + ($failedTasks -join ", ") + ". " +
        "Registering an S4U scheduled task requires an elevated PowerShell " +
        "session; re-run this installer as Administrator. No summary is " +
        "printed for tasks that do not exist."
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
    $live = Get-ScheduledTask -TaskName $_.Name
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
