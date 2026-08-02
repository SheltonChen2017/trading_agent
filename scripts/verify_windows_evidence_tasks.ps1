[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RunAsUser,

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

    [string]$OperationalTaskPrefix = "TradingAgent-Paper",

    [string]$MlTaskPrefix = "TradingAgent-ML-Shadow",

    [ValidateSet("Interactive", "S4U")]
    [string]$ExpectedTaskLogonType = "S4U",

    [string[]]$RequiredCredentialNames = @("APCA_API_KEY_ID", "APCA_API_SECRET_KEY")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$resolvedPython = (Resolve-Path -LiteralPath $PythonPath).Path
$resolvedConfig = (Resolve-Path -LiteralPath $ConfigPath).Path
$resolvedArtifacts = (Resolve-Path -LiteralPath $ArtifactPath).Path
$database = [IO.Path]::GetFullPath($DatabasePath)
$currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name

$expectedTasks = @(
    "$OperationalTaskPrefix-OperationsCycle",
    "$OperationalTaskPrefix-OrderMonitor",
    "$OperationalTaskPrefix-Watchdog",
    "$OperationalTaskPrefix-PaperObservation",
    "$MlTaskPrefix-Predict",
    "$MlTaskPrefix-Mature",
    "$MlTaskPrefix-Monitor",
    "$MlTaskPrefix-Supervisor"
)

$checks = [Collections.Generic.List[object]]::new()
function Add-Check {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][bool]$Ok,
        [Parameter(Mandatory = $true)][string]$Detail
    )
    $checks.Add([PSCustomObject]@{ Name = $Name; Ok = $Ok; Detail = $Detail })
}

Add-Check -Name "python_path" -Ok (Test-Path -LiteralPath $resolvedPython -PathType Leaf) -Detail $resolvedPython
Add-Check -Name "database_path" -Ok (Test-Path -LiteralPath $database -PathType Leaf) -Detail $database
Add-Check -Name "config_path" -Ok (Test-Path -LiteralPath $resolvedConfig -PathType Leaf) -Detail $resolvedConfig
Add-Check -Name "artifact_path" -Ok (Test-Path -LiteralPath $resolvedArtifacts -PathType Container) -Detail $resolvedArtifacts

foreach ($credentialName in $RequiredCredentialNames) {
    $processValue = [Environment]::GetEnvironmentVariable($credentialName, "Process")
    $userValue = [Environment]::GetEnvironmentVariable($credentialName, "User")
    $machineValue = [Environment]::GetEnvironmentVariable($credentialName, "Machine")
    $runningAsTaskUser = $currentUser -eq $RunAsUser
    $processPresent = -not [string]::IsNullOrWhiteSpace($processValue)
    $userPresent = -not [string]::IsNullOrWhiteSpace($userValue)
    $machinePresent = -not [string]::IsNullOrWhiteSpace($machineValue)
    $targetContextPresent = $runningAsTaskUser -and ($processPresent -or $userPresent)
    $present = $machinePresent -or $targetContextPresent
    Add-Check -Name "credential:$credentialName" -Ok $present -Detail (
        if ($machinePresent) {
            "present in machine scope; value not displayed"
        } elseif ($targetContextPresent) {
            "present while running as target task user; value not displayed"
        } elseif ($runningAsTaskUser) {
            "missing"
        } else {
            "not verifiable: rerun as $RunAsUser or configure machine scope"
        }
    )
}

foreach ($taskName in $expectedTasks) {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($null -eq $task) {
        Add-Check -Name "task:$taskName" -Ok $false -Detail "not installed"
        continue
    }
    $info = Get-ScheduledTaskInfo -TaskName $taskName
    $principalOk = $task.Principal.UserId -eq $RunAsUser -and `
        $task.Principal.RunLevel -eq "Limited" -and `
        $task.Principal.LogonType -eq $ExpectedTaskLogonType
    $actions = @($task.Actions)
    $pythonOk = $actions.Count -eq 1 -and `
        $actions[0].Execute -eq $resolvedPython
    $neverRun = $info.LastRunTime -eq [datetime]::MinValue
    $lastResultOk = $info.LastTaskResult -eq 0 -or $neverRun
    Add-Check -Name "task:$taskName" -Ok (
        $principalOk -and $pythonOk -and $lastResultOk
    ) -Detail (
        "state=$($task.State), user=$($task.Principal.UserId), " +
        "run_level=$($task.Principal.RunLevel), logon_type=$($task.Principal.LogonType), " +
        "last_result=$($info.LastTaskResult), " +
        "last_run=$($info.LastRunTime), next_run=$($info.NextRunTime)"
    )
}

$failed = @($checks | Where-Object { -not $_.Ok })
$report = [PSCustomObject]@{
    CheckedAt = [datetime]::UtcNow.ToString("o")
    Ok = $failed.Count -eq 0
    RunAsUser = $RunAsUser
    CurrentUser = $currentUser
    ExpectedTaskLogonType = $ExpectedTaskLogonType
    Checks = $checks
    FailedCheckCount = $failed.Count
    ProductionAuthoritative = $false
}
$report | ConvertTo-Json -Depth 6
if ($failed.Count -gt 0) {
    exit 1
}
