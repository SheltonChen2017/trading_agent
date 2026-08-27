[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RunAsUser,

    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$PythonPath,

    [Parameter(Mandatory = $true)]
    [string]$DatabasePath,

    # Optional highest-precedence override. When omitted, resolve through the
    # same environment -> personal -> committed-default chain as runtime.
    [string]$PolicyPath,

    # Required for the full eight-task verification (Scope "all"); with
    # Scope "operational" the ML shadow config/artifact checks are skipped
    # explicitly, so these may be omitted. Existence is validated at run
    # time per scope rather than by ValidateScript so an operational-only
    # host without any shadow artifact can still verify its four tasks.
    [string]$ConfigPath = "",

    [string]$ArtifactPath = "",

    [string]$OperationalTaskPrefix = "TradingAgent-Paper",

    [string]$MlTaskPrefix = "TradingAgent-ML-Shadow",

    # Interactive is the only logon type that actually runs on this host
    # (Credential Guard silently kills S4U); a defaults-run verification
    # must therefore expect Interactive, or it would fail correctly
    # registered tasks and pass S4U misregistrations.
    [ValidateSet("Interactive", "S4U")]
    [string]$ExpectedTaskLogonType = "Interactive",

    # Installation verification may accept a correctly registered task that
    # has not run yet. Post-start verification must not: Credential Guard can
    # make Start-ScheduledTask return while an S4U task remains at the
    # never-ran sentinel. Callers that start tasks before verifying must pass
    # this switch so that state fails closed.
    [switch]$RequireTaskRun,

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
$repository = Split-Path -Parent $PSScriptRoot
$assistantScript = Join-Path $repository "scripts\run_personal_assistant.py"
$resolvedPolicy = ""

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

$policyPathOk = $false
$policyPathDetail = "policy identity could not be resolved"
$policyIdentityOk = $false
$policyFingerprint = ""
$policyIdentityDetail = "required script is missing: $assistantScript"
if (Test-Path -LiteralPath $assistantScript -PathType Leaf) {
    $policyIdentityArguments = @($assistantScript)
    if (-not [string]::IsNullOrWhiteSpace($PolicyPath)) {
        $policyIdentityArguments += @("--policy", $PolicyPath.Trim())
    }
    $policyIdentityArguments += "policy-identity"
    $policyIdentityOutput = @(
        & $resolvedPython @policyIdentityArguments 2>&1
    )
    $policyIdentityExit = $LASTEXITCODE
    if ($policyIdentityExit -eq 0) {
        try {
            $policyIdentity = ($policyIdentityOutput -join [Environment]::NewLine) |
                ConvertFrom-Json
            $identityPath = [string]$policyIdentity.policy_path
            $policyFingerprint = [string]$policyIdentity.policy_fingerprint
            $policyPathOk = (
                -not [string]::IsNullOrWhiteSpace($identityPath) -and
                (Test-Path -LiteralPath $identityPath -PathType Leaf)
            )
            if ($policyPathOk) {
                $resolvedPolicy = (Resolve-Path -LiteralPath $identityPath).Path
                $policyPathOk = $identityPath -eq $resolvedPolicy
            }
            $policyPathDetail = if ($policyPathOk) {
                $resolvedPolicy
            }
            else {
                "policy identity returned an unreadable or noncanonical path: $identityPath"
            }
            $policyIdentityOk = (
                $policyPathOk -and
                -not [string]::IsNullOrWhiteSpace($policyFingerprint) -and
                $identityPath -eq $resolvedPolicy
            )
            $policyIdentityDetail = (
                "path=$($policyIdentity.policy_path), " +
                "fingerprint=$policyFingerprint"
            )
        }
        catch {
            $policyIdentityDetail = (
                "policy identity output was invalid JSON: " +
                $_.Exception.Message
            )
        }
    }
    else {
        $policyIdentityDetail = (
            "policy identity command failed with exit ${policyIdentityExit}: " +
            ($policyIdentityOutput -join [Environment]::NewLine)
        )
        $policyPathDetail = $policyIdentityDetail
    }
}
Add-Check -Name "policy_path" -Ok $policyPathOk -Detail $policyPathDetail
Add-Check -Name "policy_identity" -Ok $policyIdentityOk -Detail $policyIdentityDetail

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
        if ($operationalTasks -contains $taskName) {
            Add-Check -Name "task_policy:$taskName" -Ok $false -Detail (
                "task is not installed; policy identity cannot be verified"
            )
        }
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
    if ($operationalTasks -contains $taskName) {
        $taskPolicyOk = $false
        $taskPolicyDetail = "task must have exactly one action with one --policy path"
        if ($actions.Count -eq 1) {
            $matches = [regex]::Matches(
                [string]$actions[0].Arguments,
                '(?:^|\s)--policy\s+"([^"]+)"'
            )
            if ($matches.Count -eq 1) {
                $taskPolicyPath = $matches[0].Groups[1].Value
                if (Test-Path -LiteralPath $taskPolicyPath -PathType Leaf) {
                    $taskPolicyPath = (Resolve-Path -LiteralPath $taskPolicyPath).Path
                    $taskPolicyOk = $policyIdentityOk -and (
                        $taskPolicyPath -eq $resolvedPolicy
                    )
                    $taskPolicyDetail = (
                        "path=$taskPolicyPath, expected=$resolvedPolicy, " +
                        "fingerprint=$policyFingerprint"
                    )
                }
                else {
                    $taskPolicyDetail = (
                        "task policy path does not exist or is unreadable: " +
                        $taskPolicyPath
                    )
                }
            }
        }
        Add-Check -Name "task_policy:$taskName" -Ok $taskPolicyOk -Detail $taskPolicyDetail
    }
    # Task Scheduler's "never ran" sentinel is 1999-11-30, not
    # [datetime]::MinValue, and a not-yet-run task reports LastTaskResult
    # 267011 (SCHED_S_TASK_HAS_NOT_RUN); a currently running task reports
    # 267009 (SCHED_S_TASK_RUNNING). All three misreported freshly
    # installed or in-flight tasks as failures on the first field run
    # (2026-08-05). A genuine nonzero exit from a completed run still
    # fails.
    $neverRunTime = $info.LastRunTime -eq [datetime]::MinValue -or `
        $info.LastRunTime.Year -lt 2000
    # Treat only the scheduler's consistent never-run pair as benign. An
    # impossible/corrupt combination such as a sentinel date plus exit 1
    # remains a failure.
    $neverRun = $neverRunTime -and $info.LastTaskResult -eq 267011
    # A healthy long-runner with a repeating self-heal trigger can show
    # LastTaskResult=0x800710E0 (already running / ignored start) after a
    # heal tick. Process identity is State=Running; requiring 267009 alone
    # false-fails the verifier while OrderMonitor/Watchdog are alive.
    $currentlyRunning = $task.State -eq "Running"
    $lastResultOk = $info.LastTaskResult -eq 0 -or `
        $info.LastTaskResult -eq 267009 -or `
        $currentlyRunning -or ($neverRun -and -not $RequireTaskRun)
    Add-Check -Name "task:$taskName" -Ok (
        $principalOk -and $pythonOk -and $lastResultOk
    ) -Detail (
        "state=$($task.State), user=$($task.Principal.UserId), " +
        "run_level=$($task.Principal.RunLevel), logon_type=$($task.Principal.LogonType), " +
        "last_result=$($info.LastTaskResult), " +
        "last_run=$($info.LastRunTime), next_run=$($info.NextRunTime)"
    )
}

$heartbeatReport = $null
$heartbeatCheckOk = $false
$heartbeatCheckDetail = "policy identity or database path was not usable"
if (
    $policyIdentityOk -and
    (Test-Path -LiteralPath $database -PathType Leaf) -and
    (Test-Path -LiteralPath $assistantScript -PathType Leaf)
) {
    $heartbeatArguments = @(
        $assistantScript,
        "--database", $database,
        "--policy", $resolvedPolicy,
        "verify-operational-policy-heartbeats"
    )
    if ($RequireTaskRun) {
        $heartbeatArguments += "--require-all"
    }
    $heartbeatOutput = @(& $resolvedPython @heartbeatArguments 2>&1)
    $heartbeatExit = $LASTEXITCODE
    try {
        $heartbeatReport = ($heartbeatOutput -join [Environment]::NewLine) |
            ConvertFrom-Json
        $heartbeatCheckOk = $heartbeatExit -eq 0 -and [bool]$heartbeatReport.ok
        $heartbeatStatuses = @(
            $heartbeatReport.checks.psobject.Properties | ForEach-Object {
                "$($_.Name)=$($_.Value.status)"
            }
        ) -join ", "
        $heartbeatCheckDetail = (
            "expected_fingerprint=$policyFingerprint, " +
            "degraded=$($heartbeatReport.degraded), " +
            "statuses=[$heartbeatStatuses], exit=$heartbeatExit"
        )
    }
    catch {
        $heartbeatCheckDetail = (
            "heartbeat verification output was invalid JSON (exit " +
            "$heartbeatExit): " + ($heartbeatOutput -join [Environment]::NewLine)
        )
    }
}
Add-Check -Name "operational_policy_heartbeats" -Ok $heartbeatCheckOk -Detail $heartbeatCheckDetail

$failed = @($checks | Where-Object { -not $_.Ok })
$report = [PSCustomObject]@{
    CheckedAt = [datetime]::UtcNow.ToString("o")
    Ok = $failed.Count -eq 0
    Scope = $Scope
    RunAsUser = $RunAsUser
    CurrentUser = $currentUser
    ExpectedTaskLogonType = $ExpectedTaskLogonType
    RequireTaskRun = [bool]$RequireTaskRun
    PolicyPath = $resolvedPolicy
    PolicyFingerprint = $policyFingerprint
    PolicyHeartbeatReport = $heartbeatReport
    Checks = $checks
    SkippedChecks = $skippedChecks
    FailedCheckCount = $failed.Count
    ProductionAuthoritative = $false
}
$report | ConvertTo-Json -Depth 6
if ($failed.Count -gt 0) {
    exit 1
}
