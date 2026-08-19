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

    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Container })]
    [string]$ArtifactPath,

    [string]$RepositoryPath,

    [string]$TaskPrefix = "TradingAgent-ML-Shadow",

    [string]$RunAsUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name,

    # Interactive: Credential Guard on domain-joined Windows 11 blocks S4U
    # task logons SILENTLY (occurrence consumed, no run attempt, no error;
    # proven live 2026-08-19 by the overlay tasks). The setup wrapper always
    # passed Interactive explicitly; the default must not be a trap for a
    # direct invocation.
    [ValidateSet("Interactive", "S4U")]
    [string]$TaskLogonType = "Interactive",

    [ValidateRange(5, 60)]
    [int]$SupervisorIntervalMinutes = 15,

    [string[]]$RequiredCredentialNames = @("APCA_API_KEY_ID", "APCA_API_SECRET_KEY"),

    [datetime]$PredictionLocalTime = [datetime]::MinValue,

    [datetime]$MaturityLocalTime = [datetime]::MinValue,

    [datetime]$MonitoringLocalTime = [datetime]::MinValue,

    [string]$MonitoringOutputPath,

    [string]$AlertsJsonlPath,

    [string]$SupervisorOutputPath
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
$resolvedConfig = (Resolve-Path -LiteralPath $ConfigPath).Path
$resolvedArtifacts = (Resolve-Path -LiteralPath $ArtifactPath).Path
$database = [IO.Path]::GetFullPath($DatabasePath)
$monitoringOutput = if ($MonitoringOutputPath) {
    [IO.Path]::GetFullPath($MonitoringOutputPath)
}
else {
    Join-Path $resolvedRepository "artifacts\ml-shadow-monitoring.json"
}
$alerts = if ($AlertsJsonlPath) {
    [IO.Path]::GetFullPath($AlertsJsonlPath)
}
else {
    Join-Path $resolvedRepository "data\alerts.jsonl"
}
$supervisorOutput = if ($SupervisorOutputPath) {
    [IO.Path]::GetFullPath($SupervisorOutputPath)
}
else {
    Join-Path $resolvedRepository "artifacts\ml-evidence-supervisor.json"
}
$shadowScript = Join-Path $resolvedRepository "scripts\run_ml_shadow.py"
$supervisorScript = Join-Path $resolvedRepository "scripts\run_ml_evidence_supervisor.py"
foreach ($requiredPath in @($shadowScript, $supervisorScript)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required script does not exist: $requiredPath"
    }
}

# Defaults are expressed in Eastern market time and converted to the
# machine's local timezone. 16:30 ET is after both the normal 16:00 close
# and the 13:00 half-day close. US Eastern/Pacific DST transitions align;
# callers in a timezone with different DST rules can override these times.
if ($PredictionLocalTime -eq [datetime]::MinValue) {
    $PredictionLocalTime = Convert-EasternClockToLocal -Hour 16 -Minute 30
}
if ($MaturityLocalTime -eq [datetime]::MinValue) {
    $MaturityLocalTime = Convert-EasternClockToLocal -Hour 17 -Minute 0
}
if ($MonitoringLocalTime -eq [datetime]::MinValue) {
    $MonitoringLocalTime = Convert-EasternClockToLocal -Hour 17 -Minute 15
}

$scriptArgument = Quote-TaskArgument $shadowScript
$databaseArgument = Quote-TaskArgument $database
$configArgument = Quote-TaskArgument $resolvedConfig
$artifactArgument = Quote-TaskArgument $resolvedArtifacts
$alertsArgument = Quote-TaskArgument $alerts
$monitoringArgument = Quote-TaskArgument $monitoringOutput
$supervisorArgument = Quote-TaskArgument $supervisorScript
$supervisorOutputArgument = Quote-TaskArgument $supervisorOutput
$credentialArguments = ($RequiredCredentialNames | ForEach-Object {
    "--required-credential " + (Quote-TaskArgument $_)
}) -join " "
$commonArguments = "$scriptArgument --database $databaseArgument --config $configArgument --artifact-dir $artifactArgument --alerts-jsonl $alertsArgument"
$supervisorArguments = "$supervisorArgument --database $databaseArgument --config $configArgument --artifact-dir $artifactArgument --alerts-jsonl $alertsArgument --output $supervisorOutputArgument $credentialArguments"

# Build a data-only preview before touching the Task Scheduler CIM provider.
# New-ScheduledTaskAction can be access-denied for a non-elevated user even
# though -WhatIf must remain a safe, useful preflight.
if ($WhatIfPreference) {
    @(
        @{ Name = "$TaskPrefix-Predict"; Command = "$commonArguments predict" },
        @{ Name = "$TaskPrefix-Mature"; Command = "$commonArguments mature" },
        @{ Name = "$TaskPrefix-Monitor"; Command = "$commonArguments monitor --output $monitoringArgument" },
        @{ Name = "$TaskPrefix-Supervisor"; Command = $supervisorArguments }
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
            Artifacts = $resolvedArtifacts
            AlertsJsonl = $alerts
            SupervisorOutput = $supervisorOutput
        }
    }
    return
}

$predictAction = New-ScheduledTaskAction `
    -Execute $resolvedPython `
    -Argument "$commonArguments predict" `
    -WorkingDirectory $resolvedRepository
$matureAction = New-ScheduledTaskAction `
    -Execute $resolvedPython `
    -Argument "$commonArguments mature" `
    -WorkingDirectory $resolvedRepository
$monitorAction = New-ScheduledTaskAction `
    -Execute $resolvedPython `
    -Argument "$commonArguments monitor --output $monitoringArgument" `
    -WorkingDirectory $resolvedRepository
$supervisorAction = New-ScheduledTaskAction `
    -Execute $resolvedPython `
    -Argument $supervisorArguments `
    -WorkingDirectory $resolvedRepository

$predictionTrigger = New-ScheduledTaskTrigger `
    -Weekly -WeeksInterval 1 `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
    -At $PredictionLocalTime
$maturityTrigger = New-ScheduledTaskTrigger `
    -Weekly -WeeksInterval 1 `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
    -At $MaturityLocalTime
$monitoringTrigger = New-ScheduledTaskTrigger `
    -Weekly -WeeksInterval 1 `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
    -At $MonitoringLocalTime
$supervisorTrigger = New-ScheduledTaskTrigger `
    -Once `
    -At ((Get-Date).AddMinutes(1)) `
    -RepetitionInterval (New-TimeSpan -Minutes $SupervisorIntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

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
        Name = "$TaskPrefix-Predict"
        Description = "Generate non-authoritative volatility observations after finalized market data."
        Action = $predictAction
        Trigger = $predictionTrigger
    },
    @{
        Name = "$TaskPrefix-Mature"
        Description = "Attach exactly-once realized outcomes after their exchange-calendar target close."
        Action = $matureAction
        Trigger = $maturityTrigger
    },
    @{
        Name = "$TaskPrefix-Monitor"
        Description = "Write a read-only monitoring report scoped to one ML evidence epoch."
        Action = $monitorAction
        Trigger = $monitoringTrigger
    },
    @{
        Name = "$TaskPrefix-Supervisor"
        Description = "Independently alert on missing paper captures, ML runs/outcomes, heartbeats, credentials, and recovery evidence."
        Action = $supervisorAction
        Trigger = $supervisorTrigger
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
        "Scheduler service, then retry."
    )
}

$summary = {
    param($name, $status, $live)
    [PSCustomObject]@{
        TaskName = $name
        Status = $status
        State = if ($live) { $live.State } else { $null }
        RunAsUser = if ($live) { $live.Principal.UserId } else { $RunAsUser }
        RunLevel = if ($live) { $live.Principal.RunLevel } else { "Limited" }
        LogonType = if ($live) { $live.Principal.LogonType } else { $TaskLogonType }
        Database = $database
        Config = $resolvedConfig
        Artifacts = $resolvedArtifacts
        AlertsJsonl = $alerts
        SupervisorOutput = $supervisorOutput
        MultipleInstances = "IgnoreNew"
        ExecutionTimeLimitMinutes = 30
        RestartCount = 3
    }
}

$tasks | ForEach-Object {
    if (-not $attempted) {
        & $summary $_.Name "planned (WhatIf)" $null
    }
    else {
        & $summary $_.Name "registered" (Get-InstalledTaskExact -Name $_.Name)
    }
}
