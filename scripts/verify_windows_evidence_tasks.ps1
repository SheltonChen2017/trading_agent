[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RunAsUser,

    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$PythonPath,

    [Parameter(Mandatory = $true)]
    [string]$DatabasePath,

    # Mirror the installers' path/cadence inputs so verification can compare
    # the installed task definition with the exact contract that was planned.
    # Defaults preserve the existing invocation surface used by the generated
    # operational-host wrapper.
    [string]$RepositoryPath,

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

    [string]$OperationalAlertsJsonlPath = "",

    [string]$MlAlertsJsonlPath = "",

    [string]$MonitoringOutputPath = "",

    [string]$SupervisorOutputPath = "",

    [ValidateRange(5, 60)]
    [int]$OperationsCycleMinutes = 10,

    [ValidateRange(1, 60)]
    [int]$LongRunningHealMinutes = 5,

    [ValidateRange(5, 60)]
    [int]$SupervisorIntervalMinutes = 15,

    [datetime]$PaperObservationLocalTime = [datetime]::MinValue,

    [datetime]$PredictionLocalTime = [datetime]::MinValue,

    [datetime]$MaturityLocalTime = [datetime]::MinValue,

    [datetime]$MonitoringLocalTime = [datetime]::MinValue,

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
$repository = if ([string]::IsNullOrWhiteSpace($RepositoryPath)) {
    Split-Path -Parent $PSScriptRoot
}
else {
    (Resolve-Path -LiteralPath $RepositoryPath).Path
}
$repository = (Resolve-Path -LiteralPath $repository).Path
$assistantScript = Join-Path $repository "scripts\run_personal_assistant.py"
$watchdogScript = Join-Path $repository "scripts\run_operations_watchdog.py"
$shadowScript = Join-Path $repository "scripts\run_ml_shadow.py"
$supervisorScript = Join-Path $repository "scripts\run_ml_evidence_supervisor.py"
$operationalAlerts = if ([string]::IsNullOrWhiteSpace($OperationalAlertsJsonlPath)) {
    Join-Path $repository "data\alerts.jsonl"
}
else {
    [IO.Path]::GetFullPath($OperationalAlertsJsonlPath)
}
$mlAlerts = if ([string]::IsNullOrWhiteSpace($MlAlertsJsonlPath)) {
    Join-Path $repository "data\alerts.jsonl"
}
else {
    [IO.Path]::GetFullPath($MlAlertsJsonlPath)
}
$monitoringOutput = if ([string]::IsNullOrWhiteSpace($MonitoringOutputPath)) {
    Join-Path $repository "artifacts\ml-shadow-monitoring.json"
}
else {
    [IO.Path]::GetFullPath($MonitoringOutputPath)
}
$supervisorOutput = if ([string]::IsNullOrWhiteSpace($SupervisorOutputPath)) {
    Join-Path $repository "artifacts\ml-evidence-supervisor.json"
}
else {
    [IO.Path]::GetFullPath($SupervisorOutputPath)
}
$resolvedPolicy = ""
$resolvedConfig = ""
$resolvedArtifacts = ""

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

function Get-PropertyValue {
    param(
        [AllowNull()][object]$InputObject,
        [Parameter(Mandatory = $true)][string]$Name
    )
    if ($null -eq $InputObject) {
        return $null
    }
    $property = $InputObject.PSObject.Properties[$Name]
    if ($null -eq $property) {
        return $null
    }
    return $property.Value
}

function Get-ComparablePath {
    param([Parameter(Mandatory = $true)][string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw "path is empty"
    }
    $full = [IO.Path]::GetFullPath($Path)
    $root = [IO.Path]::GetPathRoot($full)
    if (-not [StringComparer]::OrdinalIgnoreCase.Equals($full, $root)) {
        $full = $full.TrimEnd([char[]]@('\', '/'))
    }
    return $full
}

function Test-PathEqual {
    param(
        [AllowNull()][object]$Actual,
        [Parameter(Mandatory = $true)][string]$Expected
    )
    try {
        $actualPath = Get-ComparablePath -Path ([string]$Actual)
        $expectedPath = Get-ComparablePath -Path $Expected
        return [StringComparer]::OrdinalIgnoreCase.Equals($actualPath, $expectedPath)
    }
    catch {
        return $false
    }
}

function Test-AccountIdentity {
    param([AllowNull()][object]$Actual)
    $actualName = [string]$Actual
    if ([string]::IsNullOrWhiteSpace($actualName)) {
        return $false
    }
    if ($actualName -eq $RunAsUser) {
        return $true
    }
    if (-not $expectedRunAsSid) {
        return $false
    }
    $actualSid = Resolve-AccountSid -AccountName $actualName
    return ($null -ne $actualSid) -and ($actualSid -eq $expectedRunAsSid)
}

function Get-CimClassName {
    param([AllowNull()][object]$InputObject)
    $cimClass = Get-PropertyValue -InputObject $InputObject -Name "CimClass"
    return [string](Get-PropertyValue -InputObject $cimClass -Name "CimClassName")
}

function Get-TriggerClassName {
    param([AllowNull()][object]$Trigger)
    return Get-CimClassName -InputObject $Trigger
}

function Test-BooleanTrue {
    param([AllowNull()][object]$Value)
    return ($Value -is [bool]) -and [bool]$Value
}

function Test-IsoDuration {
    param(
        [AllowNull()][object]$Value,
        [Parameter(Mandatory = $true)][timespan]$Expected
    )
    try {
        if ($Value -is [timespan]) {
            return ([timespan]$Value) -eq $Expected
        }
        return [Xml.XmlConvert]::ToTimeSpan([string]$Value) -eq $Expected
    }
    catch {
        return $false
    }
}

function Get-ParsedStartBoundary {
    param([AllowNull()][object]$Value)
    try {
        return [datetime]::Parse(
            [string]$Value,
            [Globalization.CultureInfo]::InvariantCulture,
            [Globalization.DateTimeStyles]::AllowWhiteSpaces
        )
    }
    catch {
        return $null
    }
}

function Test-RepeatingTimeTrigger {
    param(
        [Parameter(Mandatory = $true)][object]$Trigger,
        [Parameter(Mandatory = $true)][int]$IntervalMinutes
    )
    $failures = [Collections.Generic.List[string]]::new()
    if ((Get-TriggerClassName -Trigger $Trigger) -ne "MSFT_TaskTimeTrigger") {
        $failures.Add("type")
    }
    if (-not (Test-BooleanTrue (Get-PropertyValue -InputObject $Trigger -Name "Enabled"))) {
        $failures.Add("disabled")
    }
    $repetition = Get-PropertyValue -InputObject $Trigger -Name "Repetition"
    if ($null -eq $repetition) {
        $failures.Add("missing_repetition")
    }
    else {
        if (-not (Test-IsoDuration `
            -Value (Get-PropertyValue -InputObject $repetition -Name "Interval") `
            -Expected (New-TimeSpan -Minutes $IntervalMinutes))) {
            $failures.Add("interval")
        }
        if (-not (Test-IsoDuration `
            -Value (Get-PropertyValue -InputObject $repetition -Name "Duration") `
            -Expected (New-TimeSpan -Days 3650))) {
            $failures.Add("duration")
        }
    }
    $start = Get-ParsedStartBoundary (
        Get-PropertyValue -InputObject $Trigger -Name "StartBoundary"
    )
    if ($null -eq $start) {
        $failures.Add("start_boundary")
    }
    else {
        $now = Get-Date
        # Both installers set repeating boundaries to install-time + 1 minute.
        # A future or expired anchor is not the installed cadence even if its
        # repetition metadata happens to look right.
        if ($start -gt $now.AddMinutes(10)) {
            $failures.Add("future_start")
        }
        try {
            if ($start.AddDays(3650) -le $now) {
                $failures.Add("expired")
            }
        }
        catch {
            $failures.Add("invalid_duration_window")
        }
    }
    return [PSCustomObject]@{
        Ok = $failures.Count -eq 0
        Detail = if ($failures.Count -eq 0) { "matched" } else { $failures -join "," }
    }
}

function Test-WeeklyTrigger {
    param(
        [Parameter(Mandatory = $true)][object]$Trigger,
        [Parameter(Mandatory = $true)][datetime]$ExpectedLocalTime
    )
    $failures = [Collections.Generic.List[string]]::new()
    if ((Get-TriggerClassName -Trigger $Trigger) -ne "MSFT_TaskWeeklyTrigger") {
        $failures.Add("type")
    }
    if (-not (Test-BooleanTrue (Get-PropertyValue -InputObject $Trigger -Name "Enabled"))) {
        $failures.Add("disabled")
    }
    try {
        if ([int](Get-PropertyValue -InputObject $Trigger -Name "WeeksInterval") -ne 1) {
            $failures.Add("weeks_interval")
        }
    }
    catch {
        $failures.Add("weeks_interval")
    }
    try {
        # Task Scheduler bit mask: Monday=2 through Friday=32 -> 62.
        if ([int](Get-PropertyValue -InputObject $Trigger -Name "DaysOfWeek") -ne 62) {
            $failures.Add("days_of_week")
        }
    }
    catch {
        $failures.Add("days_of_week")
    }
    $start = Get-ParsedStartBoundary (
        Get-PropertyValue -InputObject $Trigger -Name "StartBoundary"
    )
    if ($null -eq $start) {
        $failures.Add("start_boundary")
    }
    else {
        if ($start.TimeOfDay -ne $ExpectedLocalTime.TimeOfDay) {
            $failures.Add("local_time")
        }
        if ($start.Date -gt (Get-Date).Date.AddDays(1)) {
            $failures.Add("future_start")
        }
    }
    return [PSCustomObject]@{
        Ok = $failures.Count -eq 0
        Detail = if ($failures.Count -eq 0) { "matched" } else { $failures -join "," }
    }
}

function Test-TaskTriggerContract {
    param(
        [AllowNull()][object[]]$Triggers,
        [Parameter(Mandatory = $true)][object]$Contract
    )
    $actual = @($Triggers)
    if ($Contract.TriggerMode -eq "repeating") {
        if ($actual.Count -ne 1) {
            return [PSCustomObject]@{ Ok = $false; Detail = "expected 1 repeating trigger; got $($actual.Count)" }
        }
        return Test-RepeatingTimeTrigger `
            -Trigger $actual[0] `
            -IntervalMinutes $Contract.IntervalMinutes
    }
    if ($Contract.TriggerMode -eq "weekly") {
        if ($actual.Count -ne 1) {
            return [PSCustomObject]@{ Ok = $false; Detail = "expected 1 weekly trigger; got $($actual.Count)" }
        }
        return Test-WeeklyTrigger `
            -Trigger $actual[0] `
            -ExpectedLocalTime $Contract.ExpectedLocalTime
    }
    if ($Contract.TriggerMode -eq "long_running") {
        if ($actual.Count -ne 2) {
            return [PSCustomObject]@{ Ok = $false; Detail = "expected 2 long-running triggers; got $($actual.Count)" }
        }
        $timeTriggers = @($actual | Where-Object {
            (Get-TriggerClassName -Trigger $_) -eq "MSFT_TaskTimeTrigger"
        })
        $baseClass = if ($ExpectedTaskLogonType -eq "S4U") {
            "MSFT_TaskBootTrigger"
        }
        else {
            "MSFT_TaskLogonTrigger"
        }
        $baseTriggers = @($actual | Where-Object {
            (Get-TriggerClassName -Trigger $_) -eq $baseClass
        })
        if ($timeTriggers.Count -ne 1 -or $baseTriggers.Count -ne 1) {
            return [PSCustomObject]@{
                Ok = $false
                Detail = "expected one $baseClass and one MSFT_TaskTimeTrigger"
            }
        }
        $repeating = Test-RepeatingTimeTrigger `
            -Trigger $timeTriggers[0] `
            -IntervalMinutes $Contract.IntervalMinutes
        $baseEnabled = Test-BooleanTrue (
            Get-PropertyValue -InputObject $baseTriggers[0] -Name "Enabled"
        )
        $baseIdentityOk = $true
        if ($ExpectedTaskLogonType -eq "Interactive") {
            $baseIdentityOk = Test-AccountIdentity (
                Get-PropertyValue -InputObject $baseTriggers[0] -Name "UserId"
            )
        }
        $ok = $repeating.Ok -and $baseEnabled -and $baseIdentityOk
        return [PSCustomObject]@{
            Ok = $ok
            Detail = if ($ok) {
                "matched"
            }
            else {
                "repeating=$($repeating.Detail), base_enabled=$baseEnabled, base_identity=$baseIdentityOk"
            }
        }
    }
    return [PSCustomObject]@{ Ok = $false; Detail = "unknown trigger contract" }
}

function Test-TaskSettingsContract {
    param(
        [AllowNull()][object]$Settings,
        [Parameter(Mandatory = $true)][object]$Contract
    )
    $failures = [Collections.Generic.List[string]]::new()
    if (-not (Test-BooleanTrue (
        Get-PropertyValue -InputObject $Settings -Name "Enabled"
    ))) {
        $failures.Add("enabled")
    }
    if (-not (Test-BooleanTrue (
        Get-PropertyValue -InputObject $Settings -Name "StartWhenAvailable"
    ))) {
        $failures.Add("start_when_available")
    }
    if ([string](Get-PropertyValue -InputObject $Settings -Name "MultipleInstances") -ne "IgnoreNew") {
        $failures.Add("multiple_instances")
    }
    try {
        if ([int](Get-PropertyValue -InputObject $Settings -Name "RestartCount") -ne $Contract.RestartCount) {
            $failures.Add("restart_count")
        }
    }
    catch {
        $failures.Add("restart_count")
    }
    if (-not (Test-IsoDuration `
        -Value (Get-PropertyValue -InputObject $Settings -Name "RestartInterval") `
        -Expected (New-TimeSpan -Minutes $Contract.RestartIntervalMinutes))) {
        $failures.Add("restart_interval")
    }
    if (-not (Test-IsoDuration `
        -Value (Get-PropertyValue -InputObject $Settings -Name "ExecutionTimeLimit") `
        -Expected (New-TimeSpan -Minutes $Contract.ExecutionTimeLimitMinutes))) {
        $failures.Add("execution_time_limit")
    }
    $disallowOnBattery = Get-PropertyValue `
        -InputObject $Settings `
        -Name "DisallowStartIfOnBatteries"
    if (
        $disallowOnBattery -isnot [bool] -or
        [bool]$disallowOnBattery -ne [bool]$Contract.ExpectedDisallowStartIfOnBatteries
    ) {
        $failures.Add("battery_start")
    }
    $stopOnBattery = Get-PropertyValue `
        -InputObject $Settings `
        -Name "StopIfGoingOnBatteries"
    if (
        $stopOnBattery -isnot [bool] -or
        [bool]$stopOnBattery -ne [bool]$Contract.ExpectedStopIfGoingOnBatteries
    ) {
        $failures.Add("battery_stop")
    }
    return [PSCustomObject]@{
        Ok = $failures.Count -eq 0
        Detail = if ($failures.Count -eq 0) { "matched" } else { $failures -join "," }
    }
}

if ($PaperObservationLocalTime -eq [datetime]::MinValue) {
    $PaperObservationLocalTime = Convert-EasternClockToLocal -Hour 16 -Minute 30
}
if ($PredictionLocalTime -eq [datetime]::MinValue) {
    $PredictionLocalTime = Convert-EasternClockToLocal -Hour 16 -Minute 30
}
if ($MaturityLocalTime -eq [datetime]::MinValue) {
    $MaturityLocalTime = Convert-EasternClockToLocal -Hour 17 -Minute 0
}
if ($MonitoringLocalTime -eq [datetime]::MinValue) {
    $MonitoringLocalTime = Convert-EasternClockToLocal -Hour 17 -Minute 15
}

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
    # Windows PowerShell promotes native stderr to an ErrorRecord. Under the
    # script-wide Stop preference that would terminate verification before
    # the JSON report can record a failed check. Capture the command while
    # temporarily allowing its exit/output to be inspected fail-closed.
    $priorErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $policyIdentityOutput = @(
            & $resolvedPython @policyIdentityArguments 2>&1
        )
        $policyIdentityExit = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $priorErrorActionPreference
    }
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
$requiredTaskScripts = @($assistantScript, $watchdogScript)
if ($verifyMl) {
    $requiredTaskScripts += @($shadowScript, $supervisorScript)
}
foreach ($requiredTaskScript in $requiredTaskScripts) {
    Add-Check `
        -Name "task_script:$([IO.Path]::GetFileName($requiredTaskScript))" `
        -Ok (Test-Path -LiteralPath $requiredTaskScript -PathType Leaf) `
        -Detail $requiredTaskScript
}
if ($verifyMl) {
    # Resolve-Path throws on absence; report a failed check instead so the
    # JSON report stays the single verification surface.
    $configOk = Test-Path -LiteralPath $ConfigPath -PathType Leaf
    $artifactsOk = Test-Path -LiteralPath $ArtifactPath -PathType Container
    if ($configOk) {
        $resolvedConfig = (Resolve-Path -LiteralPath $ConfigPath).Path
    }
    if ($artifactsOk) {
        $resolvedArtifacts = (Resolve-Path -LiteralPath $ArtifactPath).Path
    }
    Add-Check -Name "config_path" -Ok $configOk -Detail $(
        if ($configOk) { $resolvedConfig } else { "$ConfigPath (missing)" }
    )
    Add-Check -Name "artifact_path" -Ok $artifactsOk -Detail $(
        if ($artifactsOk) { $resolvedArtifacts } else { "$ArtifactPath (missing)" }
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

# Build the exact action strings from the same canonical inputs and ordering as
# the installers. Task Scheduler preserves Exec.Arguments verbatim; ordinal
# equality therefore rejects missing, duplicated, reordered, or extra switches
# without executing or reparsing the installed command line.
$assistantArgument = Quote-TaskArgument $assistantScript
$watchdogArgument = Quote-TaskArgument $watchdogScript
$databaseArgument = Quote-TaskArgument $database
$policyArgument = Quote-TaskArgument $resolvedPolicy
$operationalAlertsArgument = Quote-TaskArgument $operationalAlerts
$operationalCommands = [ordered]@{
    OperationsCycle = "$assistantArgument --database $databaseArgument --policy $policyArgument operations-cycle --cancel-stale --alerts-jsonl $operationalAlertsArgument"
    OrderMonitor = "$assistantArgument --database $databaseArgument --policy $policyArgument monitor-orders --cancel-stale --poll-seconds 30"
    Watchdog = "$watchdogArgument --database $databaseArgument --policy $policyArgument --interval-seconds 60 --alerts-jsonl $operationalAlertsArgument"
    PaperObservation = "$assistantArgument --database $databaseArgument --policy $policyArgument paper-observation --cancel-stale --alerts-jsonl $operationalAlertsArgument"
}
$assistantInputsOk = $policyIdentityOk -and (
    Test-Path -LiteralPath $assistantScript -PathType Leaf
)
$watchdogInputsOk = $policyIdentityOk -and (
    Test-Path -LiteralPath $watchdogScript -PathType Leaf
)

$expectedTaskContracts = [ordered]@{}
$expectedTaskContracts[$operationalTasks[0]] = [PSCustomObject]@{
    Arguments = $operationalCommands.OperationsCycle
    TriggerMode = "repeating"
    IntervalMinutes = $OperationsCycleMinutes
    ExpectedLocalTime = [datetime]::MinValue
    InputsOk = $assistantInputsOk
    RestartCount = 3
    RestartIntervalMinutes = 1
    ExecutionTimeLimitMinutes = 8
    ExpectedDisallowStartIfOnBatteries = $false
    ExpectedStopIfGoingOnBatteries = $false
}
$expectedTaskContracts[$operationalTasks[1]] = [PSCustomObject]@{
    Arguments = $operationalCommands.OrderMonitor
    TriggerMode = "long_running"
    IntervalMinutes = $LongRunningHealMinutes
    ExpectedLocalTime = [datetime]::MinValue
    InputsOk = $assistantInputsOk
    RestartCount = 10
    RestartIntervalMinutes = 1
    ExecutionTimeLimitMinutes = 0
    ExpectedDisallowStartIfOnBatteries = $false
    ExpectedStopIfGoingOnBatteries = $false
}
$expectedTaskContracts[$operationalTasks[2]] = [PSCustomObject]@{
    Arguments = $operationalCommands.Watchdog
    TriggerMode = "long_running"
    IntervalMinutes = $LongRunningHealMinutes
    ExpectedLocalTime = [datetime]::MinValue
    InputsOk = $watchdogInputsOk
    RestartCount = 10
    RestartIntervalMinutes = 1
    ExecutionTimeLimitMinutes = 0
    ExpectedDisallowStartIfOnBatteries = $false
    ExpectedStopIfGoingOnBatteries = $false
}
$expectedTaskContracts[$operationalTasks[3]] = [PSCustomObject]@{
    Arguments = $operationalCommands.PaperObservation
    TriggerMode = "weekly"
    IntervalMinutes = 0
    ExpectedLocalTime = $PaperObservationLocalTime
    InputsOk = $assistantInputsOk
    RestartCount = 3
    RestartIntervalMinutes = 1
    ExecutionTimeLimitMinutes = 8
    ExpectedDisallowStartIfOnBatteries = $false
    ExpectedStopIfGoingOnBatteries = $false
}

if ($verifyMl) {
    $shadowArgument = Quote-TaskArgument $shadowScript
    $supervisorArgument = Quote-TaskArgument $supervisorScript
    $configArgument = Quote-TaskArgument $resolvedConfig
    $artifactArgument = Quote-TaskArgument $resolvedArtifacts
    $mlAlertsArgument = Quote-TaskArgument $mlAlerts
    $monitoringArgument = Quote-TaskArgument $monitoringOutput
    $supervisorOutputArgument = Quote-TaskArgument $supervisorOutput
    $credentialArguments = ($RequiredCredentialNames | ForEach-Object {
        "--required-credential " + (Quote-TaskArgument $_)
    }) -join " "
    $commonMlArguments = "$shadowArgument --database $databaseArgument --config $configArgument --artifact-dir $artifactArgument --alerts-jsonl $mlAlertsArgument"
    # Keep the installer's deliberate final interpolation exactly, including
    # its trailing space when RequiredCredentialNames is an empty array.
    $mlSupervisorArguments = "$supervisorArgument --database $databaseArgument --config $configArgument --artifact-dir $artifactArgument --alerts-jsonl $mlAlertsArgument --output $supervisorOutputArgument $credentialArguments"
    $mlInputsOk = $configOk -and $artifactsOk -and `
        (Test-Path -LiteralPath $shadowScript -PathType Leaf) -and `
        (Test-Path -LiteralPath $supervisorScript -PathType Leaf)
    $expectedTaskContracts[$mlTasks[0]] = [PSCustomObject]@{
        Arguments = "$commonMlArguments predict"
        TriggerMode = "weekly"
        IntervalMinutes = 0
        ExpectedLocalTime = $PredictionLocalTime
        InputsOk = $mlInputsOk
        RestartCount = 3
        RestartIntervalMinutes = 5
        ExecutionTimeLimitMinutes = 30
        ExpectedDisallowStartIfOnBatteries = $true
        ExpectedStopIfGoingOnBatteries = $true
    }
    $expectedTaskContracts[$mlTasks[1]] = [PSCustomObject]@{
        Arguments = "$commonMlArguments mature"
        TriggerMode = "weekly"
        IntervalMinutes = 0
        ExpectedLocalTime = $MaturityLocalTime
        InputsOk = $mlInputsOk
        RestartCount = 3
        RestartIntervalMinutes = 5
        ExecutionTimeLimitMinutes = 30
        ExpectedDisallowStartIfOnBatteries = $true
        ExpectedStopIfGoingOnBatteries = $true
    }
    $expectedTaskContracts[$mlTasks[2]] = [PSCustomObject]@{
        Arguments = "$commonMlArguments monitor --output $monitoringArgument"
        TriggerMode = "weekly"
        IntervalMinutes = 0
        ExpectedLocalTime = $MonitoringLocalTime
        InputsOk = $mlInputsOk
        RestartCount = 3
        RestartIntervalMinutes = 5
        ExecutionTimeLimitMinutes = 30
        ExpectedDisallowStartIfOnBatteries = $true
        ExpectedStopIfGoingOnBatteries = $true
    }
    $expectedTaskContracts[$mlTasks[3]] = [PSCustomObject]@{
        Arguments = $mlSupervisorArguments
        TriggerMode = "repeating"
        IntervalMinutes = $SupervisorIntervalMinutes
        ExpectedLocalTime = [datetime]::MinValue
        InputsOk = $mlInputsOk
        RestartCount = 3
        RestartIntervalMinutes = 5
        ExecutionTimeLimitMinutes = 30
        ExpectedDisallowStartIfOnBatteries = $true
        ExpectedStopIfGoingOnBatteries = $true
    }
}

foreach ($taskName in $expectedTasks) {
    $contract = $expectedTaskContracts[$taskName]
    $escapedTaskName = [WildcardPattern]::Escape($taskName)
    $taskCandidates = @()
    $taskLookupError = $null
    try {
        $taskCandidates = @(
            Get-ScheduledTask `
                -TaskName $escapedTaskName `
                -ErrorAction SilentlyContinue
        )
        $taskMatches = @($taskCandidates | Where-Object {
            [StringComparer]::OrdinalIgnoreCase.Equals(
                [string](Get-PropertyValue -InputObject $_ -Name "TaskName"),
                $taskName
            ) -and
            [string](Get-PropertyValue -InputObject $_ -Name "TaskPath") -eq "\"
        })
    }
    catch {
        $taskMatches = @()
        $taskLookupError = $_.Exception.Message
    }
    if ($taskMatches.Count -ne 1) {
        $taskLookupDetail = if ($taskMatches.Count -gt 1) {
            "ambiguous: found $($taskMatches.Count) exact root tasks"
        }
        elseif ($taskLookupError) {
            "lookup failed: $taskLookupError"
        }
        elseif ($taskCandidates.Count -gt 0) {
            "not installed as the exact root task (wrong name or TaskPath)"
        }
        else {
            "not installed"
        }
        Add-Check -Name "task:$taskName" -Ok $false -Detail $taskLookupDetail
        if ($operationalTasks -contains $taskName) {
            Add-Check -Name "task_policy:$taskName" -Ok $false -Detail (
                "task is not installed; policy identity cannot be verified"
            )
        }
        continue
    }
    $task = $taskMatches[0]
    try {
        $info = Get-ScheduledTaskInfo -InputObject $task
        if (@($info).Count -ne 1) {
            throw "expected one task-info result; got $(@($info).Count)"
        }
        $info = @($info)[0]
        $taskInfoOk = $true
        $taskInfoDetail = "matched"
    }
    catch {
        $info = $null
        $taskInfoOk = $false
        $taskInfoDetail = $_.Exception.Message
    }

    $principal = Get-PropertyValue -InputObject $task -Name "Principal"
    $principalUser = Get-PropertyValue -InputObject $principal -Name "UserId"
    $principalUserMatches = Test-AccountIdentity $principalUser
    $runLevel = [string](Get-PropertyValue -InputObject $principal -Name "RunLevel")
    $logonType = [string](Get-PropertyValue -InputObject $principal -Name "LogonType")
    $principalOk = $principalUserMatches -and `
        $runLevel -eq "Limited" -and `
        $logonType -eq $ExpectedTaskLogonType

    $taskPath = [string](Get-PropertyValue -InputObject $task -Name "TaskPath")
    $taskPathOk = $taskPath -eq "\"
    $settings = Get-PropertyValue -InputObject $task -Name "Settings"
    $enabledOk = Test-BooleanTrue (
        Get-PropertyValue -InputObject $settings -Name "Enabled"
    )
    $settingsResult = Test-TaskSettingsContract `
        -Settings $settings `
        -Contract $contract
    $settingsOk = [bool]$settingsResult.Ok
    $state = [string](Get-PropertyValue -InputObject $task -Name "State")
    $stateOk = $enabledOk -and (
        $state -eq "Ready" -or $state -eq "Running" -or $state -eq "Queued"
    )

    $actions = @(Get-PropertyValue -InputObject $task -Name "Actions")
    $actionCountOk = $actions.Count -eq 1
    $actionTypeOk = $false
    $executeOk = $false
    $workingDirectoryOk = $false
    $argumentsOk = $false
    $actualArguments = ""
    if ($actionCountOk) {
        $actionTypeOk = (Get-CimClassName -InputObject $actions[0]) -eq "MSFT_TaskExecAction"
        $executeOk = Test-PathEqual `
            -Actual (Get-PropertyValue -InputObject $actions[0] -Name "Execute") `
            -Expected $resolvedPython
        $workingDirectoryOk = Test-PathEqual `
            -Actual (Get-PropertyValue -InputObject $actions[0] -Name "WorkingDirectory") `
            -Expected $repository
        $actualArguments = [string](
            Get-PropertyValue -InputObject $actions[0] -Name "Arguments"
        )
        $argumentsOk = [bool]$contract.InputsOk -and `
            [StringComparer]::Ordinal.Equals(
                $actualArguments,
                [string]$contract.Arguments
            )
    }
    $triggers = @(Get-PropertyValue -InputObject $task -Name "Triggers")
    $triggerResult = Test-TaskTriggerContract `
        -Triggers $triggers `
        -Contract $contract
    $triggerOk = [bool]$triggerResult.Ok

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
                        Test-PathEqual -Actual $taskPolicyPath -Expected $resolvedPolicy
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
    $lastTaskResult = Get-PropertyValue -InputObject $info -Name "LastTaskResult"
    $lastRunTime = Get-PropertyValue -InputObject $info -Name "LastRunTime"
    $nextRunTime = Get-PropertyValue -InputObject $info -Name "NextRunTime"
    try {
        $lastRunDate = [datetime]$lastRunTime
        $neverRunTime = $lastRunDate -eq [datetime]::MinValue -or `
            $lastRunDate.Year -lt 2000
    }
    catch {
        $neverRunTime = $false
    }
    # Treat only the scheduler's consistent never-run pair as benign. An
    # impossible/corrupt combination such as a sentinel date plus exit 1
    # remains a failure.
    $neverRun = $neverRunTime -and $lastTaskResult -eq 267011
    # A healthy long-runner with a repeating self-heal trigger can show
    # LastTaskResult=0x800710E0 (already running / ignored start) after a
    # heal tick. Process identity is State=Running; requiring 267009 alone
    # false-fails the verifier while OrderMonitor/Watchdog are alive.
    $currentlyRunning = $state -eq "Running"
    $lastResultOk = $taskInfoOk -and (
        $lastTaskResult -eq 0 -or `
        $lastTaskResult -eq 267009 -or `
        $currentlyRunning -or ($neverRun -and -not $RequireTaskRun)
    )

    $contractFailures = [Collections.Generic.List[string]]::new()
    if (-not $taskPathOk) { $contractFailures.Add("task_path") }
    if (-not $enabledOk) { $contractFailures.Add("enabled") }
    if (-not $stateOk) { $contractFailures.Add("state") }
    if (-not $settingsOk) { $contractFailures.Add("settings:$($settingsResult.Detail)") }
    if (-not $principalOk) { $contractFailures.Add("principal") }
    if (-not $actionCountOk) { $contractFailures.Add("action_count") }
    if (-not $actionTypeOk) { $contractFailures.Add("action_type") }
    if (-not $executeOk) { $contractFailures.Add("execute") }
    if (-not $workingDirectoryOk) { $contractFailures.Add("working_directory") }
    if (-not $argumentsOk) { $contractFailures.Add("arguments") }
    if (-not $triggerOk) { $contractFailures.Add("triggers:$($triggerResult.Detail)") }
    if (-not $taskInfoOk) { $contractFailures.Add("task_info:$taskInfoDetail") }
    if (-not $lastResultOk) { $contractFailures.Add("last_result") }
    $taskOk = $contractFailures.Count -eq 0
    Add-Check -Name "task:$taskName" -Ok $taskOk -Detail (
        "contract_failures=[$($contractFailures -join ',')], " +
        "state=$state, enabled=$enabledOk, path=$taskPath, user=$principalUser, " +
        "run_level=$runLevel, logon_type=$logonType, actions=$($actions.Count), " +
        "action_type=$actionTypeOk, execute=$executeOk, working_directory=$workingDirectoryOk, " +
        "arguments=$argumentsOk, triggers=$($triggerResult.Detail), " +
        "settings=$($settingsResult.Detail), " +
        "last_result=$lastTaskResult, last_run=$lastRunTime, next_run=$nextRunTime"
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
    $priorErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $heartbeatOutput = @(& $resolvedPython @heartbeatArguments 2>&1)
        $heartbeatExit = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $priorErrorActionPreference
    }
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
