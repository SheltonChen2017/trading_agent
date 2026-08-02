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

    [ValidateSet("Interactive", "S4U")]
    [string]$TaskLogonType = "S4U",

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

foreach ($task in $tasks) {
    if ($PSCmdlet.ShouldProcess($task.Name, "Register or replace scheduled task")) {
        Register-ScheduledTask `
            -TaskName $task.Name `
            -Description $task.Description `
            -Action $task.Action `
            -Trigger $task.Trigger `
            -Settings $settings `
            -Principal $principal `
            -Force | Out-Null
    }
}

$tasks | ForEach-Object {
    [PSCustomObject]@{
        TaskName = $_.Name
        RunAsUser = $RunAsUser
        RunLevel = "Limited"
        LogonType = $TaskLogonType
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
