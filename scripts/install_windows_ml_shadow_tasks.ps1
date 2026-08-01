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

    [datetime]$PredictionLocalTime = [datetime]::MinValue,

    [datetime]$MaturityLocalTime = [datetime]::MinValue,

    [datetime]$MonitoringLocalTime = [datetime]::MinValue,

    [string]$MonitoringOutputPath,

    [string]$AlertsJsonlPath
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
$shadowScript = Join-Path $resolvedRepository "scripts\run_ml_shadow.py"
if (-not (Test-Path -LiteralPath $shadowScript -PathType Leaf)) {
    throw "Required script does not exist: $shadowScript"
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
$commonArguments = "$scriptArgument --database $databaseArgument --config $configArgument --artifact-dir $artifactArgument --alerts-jsonl $alertsArgument"

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

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

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
            -Force | Out-Null
    }
}

$tasks | ForEach-Object {
    [PSCustomObject]@{
        TaskName = $_.Name
        CurrentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        Database = $database
        Config = $resolvedConfig
        Artifacts = $resolvedArtifacts
        AlertsJsonl = $alerts
        MultipleInstances = "IgnoreNew"
        ExecutionTimeLimitMinutes = 30
        RestartCount = 3
    }
}
