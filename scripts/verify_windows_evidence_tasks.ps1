[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RunAsUser,

    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$PythonPath,

    [Parameter(Mandatory = $true)]
    [string]$DatabasePath,

    # Required for the full eight-task verification (Scope "all"); with
    # Scope "operational" the ML shadow config/artifact checks are skipped
    # explicitly, so these may be omitted. Existence is validated at run
    # time per scope rather than by ValidateScript so an operational-only
    # host without any shadow artifact can still verify its four tasks.
    [string]$ConfigPath = "",

    [string]$ArtifactPath = "",

    [string]$OperationalTaskPrefix = "TradingAgent-Paper",

    [string]$MlTaskPrefix = "TradingAgent-ML-Shadow",

    [ValidateSet("Interactive", "S4U")]
    [string]$ExpectedTaskLogonType = "S4U",

    [string[]]$RequiredCredentialNames = @("APCA_API_KEY_ID", "APCA_API_SECRET_KEY"),

    # MANDREV-001 follow-up: Phase 5 mandates the four operational tasks;
    # the four ML shadow tasks are conditional on a reviewed shadow
    # configuration and the owner's decision to collect ML evidence.
    # "all" (default) preserves the original eight-task contract exactly.
    # "operational" verifies the four mandatory tasks and REPORTS the ML
    # task/config/artifact checks as skipped -- visibly, never silently --
    # so an intentional four-task installation has a valid fail-closed
    # success check instead of an unusable one.
    [ValidateSet("all", "operational")]
    [string]$Scope = "all"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$verifyMl = $Scope -eq "all"
if ($verifyMl) {
    if ([string]::IsNullOrWhiteSpace($ConfigPath) -or [string]::IsNullOrWhiteSpace($ArtifactPath)) {
        throw (
            "Scope 'all' verifies the ML shadow tasks and requires " +
            "-ConfigPath and -ArtifactPath. For an operational-only " +
            "installation pass -Scope operational instead."
        )
    }
}

$resolvedPython = (Resolve-Path -LiteralPath $PythonPath).Path
$database = [IO.Path]::GetFullPath($DatabasePath)
$currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name

function Resolve-AccountSid {
    # Task Scheduler stores the principal's UserId in short form
    # ("sheltonchen") while operators pass DOMAIN\name; comparing the two
    # as strings misreported every correctly installed task as a failed
    # check (first field run, 2026-08-05). Normalize both to SIDs; an
    # unresolvable name returns $null and the caller falls back to the
    # exact string comparison (fail-closed, never fail-open).
    param([Parameter(Mandatory = $true)][string]$AccountName)
    try {
        return (New-Object Security.Principal.NTAccount($AccountName)).Translate(
            [Security.Principal.SecurityIdentifier]
        ).Value
    } catch {
        return $null
    }
}
$expectedRunAsSid = Resolve-AccountSid -AccountName $RunAsUser

$operationalTasks = @(
    "$OperationalTaskPrefix-OperationsCycle",
    "$OperationalTaskPrefix-OrderMonitor",
    "$OperationalTaskPrefix-Watchdog",
    "$OperationalTaskPrefix-PaperObservation"
)
$mlTasks = @(
    "$MlTaskPrefix-Predict",
    "$MlTaskPrefix-Mature",
    "$MlTaskPrefix-Monitor",
    "$MlTaskPrefix-Supervisor"
)
$expectedTasks = if ($verifyMl) { $operationalTasks + $mlTasks } else { $operationalTasks }

$skippedChecks = [Collections.Generic.List[object]]::new()
if (-not $verifyMl) {
    foreach ($skippedName in (@("config_path", "artifact_path") + ($mlTasks | ForEach-Object { "task:$_" }))) {
        $skippedChecks.Add([PSCustomObject]@{
            Name = $skippedName
            Detail = "skipped: Scope=operational (ML shadow collection not requested for this installation)"
        })
    }
}

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
if ($verifyMl) {
    # Resolve-Path throws on absence; report a failed check instead so the
    # JSON report stays the single verification surface.
    $configOk = Test-Path -LiteralPath $ConfigPath -PathType Leaf
    $artifactsOk = Test-Path -LiteralPath $ArtifactPath -PathType Container
    Add-Check -Name "config_path" -Ok $configOk -Detail $(
        if ($configOk) { (Resolve-Path -LiteralPath $ConfigPath).Path } else { "$ConfigPath (missing)" }
    )
    Add-Check -Name "artifact_path" -Ok $artifactsOk -Detail $(
        if ($artifactsOk) { (Resolve-Path -LiteralPath $ArtifactPath).Path } else { "$ArtifactPath (missing)" }
    )
}

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
    # $( ... ) not ( ... ): a parenthesized `if` statement is a runtime
    # error in PowerShell ("the term 'if' is not recognized") -- this line
    # crashed every end-to-end run of this verifier before 2026-08-04; it
    # went unnoticed because the old mandatory ConfigPath ValidateScript
    # aborted even earlier on hosts without a shadow config.
    Add-Check -Name "credential:$credentialName" -Ok $present -Detail $(
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
    $principalUserMatches = $task.Principal.UserId -eq $RunAsUser
    if (-not $principalUserMatches -and $expectedRunAsSid) {
        $taskSid = Resolve-AccountSid -AccountName $task.Principal.UserId
        $principalUserMatches = ($null -ne $taskSid) -and ($taskSid -eq $expectedRunAsSid)
    }
    $principalOk = $principalUserMatches -and `
        $task.Principal.RunLevel -eq "Limited" -and `
        $task.Principal.LogonType -eq $ExpectedTaskLogonType
    $actions = @($task.Actions)
    $pythonOk = $actions.Count -eq 1 -and `
        $actions[0].Execute -eq $resolvedPython
    # Task Scheduler's "never ran" sentinel is 1999-11-30, not
    # [datetime]::MinValue, and a not-yet-run task reports LastTaskResult
    # 267011 (SCHED_S_TASK_HAS_NOT_RUN); a currently running task reports
    # 267009 (SCHED_S_TASK_RUNNING). All three misreported freshly
    # installed or in-flight tasks as failures on the first field run
    # (2026-08-05). A genuine nonzero exit from a completed run still
    # fails.
    $neverRun = $info.LastRunTime -eq [datetime]::MinValue -or `
        $info.LastRunTime.Year -lt 2000 -or `
        $info.LastTaskResult -eq 267011
    $currentlyRunning = $info.LastTaskResult -eq 267009
    $lastResultOk = $info.LastTaskResult -eq 0 -or $neverRun -or $currentlyRunning
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
    Scope = $Scope
    RunAsUser = $RunAsUser
    CurrentUser = $currentUser
    ExpectedTaskLogonType = $ExpectedTaskLogonType
    Checks = $checks
    SkippedChecks = $skippedChecks
    FailedCheckCount = $failed.Count
    ProductionAuthoritative = $false
}
$report | ConvertTo-Json -Depth 6
if ($failed.Count -gt 0) {
    exit 1
}
