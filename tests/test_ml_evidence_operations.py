from __future__ import annotations

import ast
import copy
import json
import os
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from ml.evidence_operations import (
    EvidenceOperationsError,
    EvidenceOperationsPolicy,
    build_evidence_operations_report,
    expected_completed_sessions,
)
from ml.shadow import session_close_instant


NOW = datetime(2026, 3, 2, 23, 0, tzinfo=timezone.utc)


def _healthy_inputs():
    policy = EvidenceOperationsPolicy(
        lookback_sessions=5,
        post_close_grace_minutes=60,
        maximum_worker_heartbeat_age_hours=26,
        maximum_supervisor_heartbeat_age_minutes=30,
        maximum_backup_age_hours=24,
        maximum_restore_drill_age_days=30,
    )
    sessions = expected_completed_sessions(
        now=NOW,
        epoch_started_at="2026-02-20T20:00:00+00:00",
        lookback_sessions=policy.lookback_sessions,
        post_close_grace_minutes=policy.post_close_grace_minutes,
    )
    observations = [
        {
            "session_date": session,
            "observation_id": f"obs-{session}",
        }
        for session in sessions
    ]
    captures = [
        {
            "session_date": session,
            "observation_id": f"obs-{session}",
            "position_count": 0,
        }
        for session in sessions
    ]
    runs = [
        {
            "run_id": f"run-{session}",
            "scheduled_for": session_close_instant(session).isoformat(),
            "status": "completed",
            "prediction_count": 1,
        }
        for session in sessions
    ]
    predictions = [
        {
            "prediction_id": (
                "pred-matured" if index == len(sessions) - 1 else f"pred-{session}"
            ),
            "subject_key": "AAPL",
            "shadow_run_id": f"run-{session}",
            "available": index == len(sessions) - 1,
            "target_available_at": (
                (NOW - timedelta(days=1)).isoformat()
                if index == len(sessions) - 1
                else (NOW + timedelta(days=30)).isoformat()
            ),
        }
        for index, session in enumerate(sessions)
    ]
    inputs = dict(
        now=NOW,
        policy=policy,
        database_integrity=["ok"],
        runtime_artifact_integrity=["ok"],
        required_credentials={
            "APCA_API_KEY_ID": True,
            "APCA_API_SECRET_KEY": True,
        },
        paper_epoch={
            "status": "active",
            "evidence_epoch": "paper-v1",
            "started_at": "2026-02-20T20:00:00+00:00",
        },
        paper_observations=observations,
        portfolio_captures=captures,
        ml_epoch={
            "status": "active",
            "evidence_epoch": "ml-v1",
            "started_at": "2026-02-20T20:00:00+00:00",
        },
        ml_runs=runs,
        expected_subjects=["AAPL"],
        predictions=predictions,
        outcomes=[{"prediction_id": "pred-matured"}],
        worker_heartbeats={
            name: {"at": (NOW - timedelta(minutes=5)).isoformat(), "ok": True}
            for name in ("predict", "mature", "monitor")
        },
        operations_heartbeat={
            "at": (NOW - timedelta(minutes=5)).isoformat(),
            "healthy": True,
        },
        backup_state={
            "completed_at": (NOW - timedelta(hours=2)).isoformat(),
            "integrity": ["ok"],
        },
        restore_drill_state={
            "completed_at": (NOW - timedelta(days=2)).isoformat(),
            "passed": True,
        },
    )
    return inputs, sessions


def _checks(report):
    return {check["name"]: check for check in report["checks"]}


def test_complete_evidence_operations_report_is_healthy_and_cash_only_is_complete():
    inputs, sessions = _healthy_inputs()
    report = build_evidence_operations_report(**inputs)
    assert report["healthy"] is True
    assert report["paper_expected_sessions"] == list(sessions)
    assert report["production_authoritative"] is False
    assert _checks(report)["portfolio_capture_manifest_completeness"]["ok"] is True


def test_missed_paper_observation_and_incomplete_capture_are_distinct_failures():
    inputs, sessions = _healthy_inputs()
    inputs["paper_observations"] = inputs["paper_observations"][:-1]
    report = build_evidence_operations_report(**inputs)
    checks = _checks(report)
    assert checks["paper_observation_session_coverage"]["ok"] is False
    assert sessions[-1] in checks["paper_observation_session_coverage"]["evidence"]["missing_sessions"]

    inputs, sessions = _healthy_inputs()
    inputs["portfolio_captures"] = inputs["portfolio_captures"][:-1]
    report = build_evidence_operations_report(**inputs)
    checks = _checks(report)
    assert checks["paper_observation_session_coverage"]["ok"] is True
    assert checks["portfolio_capture_manifest_completeness"]["ok"] is False
    assert checks["portfolio_capture_manifest_completeness"]["evidence"]["incomplete_captures"][0]["session_date"] == sessions[-1]


def test_missed_or_failed_ml_run_is_alertable_without_fabricating_prediction():
    inputs, sessions = _healthy_inputs()
    inputs["ml_runs"] = inputs["ml_runs"][:-1]
    report = build_evidence_operations_report(**inputs)
    check = _checks(report)["ml_prediction_run_coverage"]
    assert check["ok"] is False
    assert check["evidence"]["missed_sessions"] == [sessions[-1]]

    inputs, _ = _healthy_inputs()
    inputs["ml_runs"][0]["status"] = "failed"
    report = build_evidence_operations_report(**inputs)
    assert _checks(report)["ml_prediction_run_coverage"]["evidence"]["failed_run_ids"]

    inputs, _ = _healthy_inputs()
    inputs["ml_runs"][0]["status"] = "claimed"
    report = build_evidence_operations_report(**inputs)
    check = _checks(report)["ml_prediction_run_coverage"]
    assert check["ok"] is False
    assert check["evidence"]["noncompleted_run_ids"]


def test_matured_prediction_without_outcome_is_underfill_not_zero():
    inputs, _ = _healthy_inputs()
    inputs["outcomes"] = []
    report = build_evidence_operations_report(**inputs)
    check = _checks(report)["matured_prediction_outcomes"]
    assert check["ok"] is False
    assert check["evidence"]["prediction_ids"] == ["pred-matured"]


def test_completed_run_must_retain_each_configured_prediction_or_refusal():
    inputs, _ = _healthy_inputs()
    inputs["predictions"] = inputs["predictions"][1:]
    report = build_evidence_operations_report(**inputs)
    check = _checks(report)["ml_prediction_attempt_completeness"]
    assert check["ok"] is False
    assert check["evidence"]["incomplete_attempts"][0]["missing_subjects"] == [
        "AAPL"
    ]


def test_credentials_artifacts_heartbeats_and_recovery_fail_independently():
    inputs, _ = _healthy_inputs()
    inputs["required_credentials"]["APCA_API_SECRET_KEY"] = False
    inputs["runtime_artifact_integrity"] = ["artifact hash mismatch"]
    inputs["worker_heartbeats"]["predict"] = {
        "at": (NOW - timedelta(days=2)).isoformat(), "ok": True
    }
    inputs["operations_heartbeat"] = None
    inputs["backup_state"] = None
    inputs["restore_drill_state"] = None
    checks = _checks(build_evidence_operations_report(**inputs))
    for name in (
        "required_credentials",
        "runtime_artifact_integrity",
        "ml_predict_heartbeat",
        "operations_watchdog_heartbeat",
        "verified_database_backup",
        "backup_restore_drill",
    ):
        assert checks[name]["ok"] is False


def test_heartbeat_without_explicit_success_fails_closed():
    inputs, _ = _healthy_inputs()
    inputs["worker_heartbeats"]["predict"] = {
        "at": (NOW - timedelta(minutes=5)).isoformat(),
    }
    report = build_evidence_operations_report(**inputs)
    assert _checks(report)["ml_predict_heartbeat"]["ok"] is False


def test_epoch_started_after_close_does_not_expect_that_session():
    sessions = expected_completed_sessions(
        now=datetime(2026, 3, 3, 23, 0, tzinfo=timezone.utc),
        epoch_started_at="2026-03-02T22:00:00+00:00",
        lookback_sessions=5,
        post_close_grace_minutes=60,
    )
    assert "2026-03-02" not in sessions
    assert "2026-03-03" in sessions


def test_future_epoch_start_is_refused_even_on_same_calendar_date():
    with pytest.raises(EvidenceOperationsError, match="starts after"):
        expected_completed_sessions(
            now=datetime(2026, 3, 3, 20, 0, tzinfo=timezone.utc),
            epoch_started_at="2026-03-03T21:00:00+00:00",
            lookback_sessions=5,
            post_close_grace_minutes=60,
        )


def test_exchange_holiday_is_not_expected_evidence():
    sessions = expected_completed_sessions(
        now=datetime(2026, 11, 27, 22, 0, tzinfo=timezone.utc),
        epoch_started_at="2026-11-23T20:00:00+00:00",
        lookback_sessions=10,
        post_close_grace_minutes=30,
    )
    assert "2026-11-26" not in sessions
    assert "2026-11-27" in sessions


def test_supervisor_and_rules_have_no_execution_or_proposal_imports():
    for filename in ("ml/evidence_operations.py", "scripts/run_ml_evidence_supervisor.py"):
        tree = ast.parse(Path(filename).read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        assert not any(
            name.startswith((
                "execution", "assistant.execution_service", "assistant.proposals",
                "assistant.allocation_batch",
            ))
            for name in imported
        )


def test_windows_installers_use_limited_principals_and_schedule_supervisor():
    root = Path(__file__).resolve().parent.parent
    ml_installer = (root / "scripts/install_windows_ml_shadow_tasks.ps1").read_text(
        encoding="utf-8"
    )
    operational = (root / "scripts/install_windows_operational_tasks.ps1").read_text(
        encoding="utf-8"
    )
    verifier = (root / "scripts/verify_windows_evidence_tasks.ps1").read_text(
        encoding="utf-8"
    )
    assert "run_ml_evidence_supervisor.py" in ml_installer
    assert "$TaskPrefix-Supervisor" in ml_installer
    assert "RepetitionInterval" in ml_installer
    for source, first_action in (
        (ml_installer, "$predictAction = New-ScheduledTaskAction"),
        (operational, "$cycleAction = New-ScheduledTaskAction"),
    ):
        assert "New-ScheduledTaskPrincipal" in source
        assert "-RunLevel Limited" in source
        assert "-Principal $principal" in source
        assert "-SkipElevationCheck:$WhatIfPreference" in source
        assert "-ErrorVariable registrationErrors" in source
        assert "@($registrationErrors).Count -gt 0" in source
        assert "[WildcardPattern]::Escape($Name)" in source
        preview = source.index("if ($WhatIfPreference)")
        first_scheduler_object = source.index(first_action)
        assert preview < first_scheduler_object
        assert 'Status = "planned (WhatIf)"' in source[preview:first_scheduler_object]
        assert "Arguments = $_.Command" in source[preview:first_scheduler_object]
    assert "New-ScheduledTaskTrigger -AtStartup" in operational
    assert "New-ScheduledTaskTrigger -AtLogOn -User $RunAsUser" in operational
    assert "Get-ScheduledTask" in verifier
    assert "Get-ScheduledTaskInfo" in verifier
    assert "value not displayed" in verifier
    assert '$logonType -eq $ExpectedTaskLogonType' in verifier
    assert "not verifiable: rerun as $RunAsUser" in verifier
    assert "ProductionAuthoritative = $false" in verifier
    assert "[datetime]$PaperObservationLocalTime = [datetime]::MinValue" in operational
    assert "function Convert-EasternClockToLocal" in operational
    assert 'FindSystemTimeZoneById("Eastern Standard Time")' in operational
    assert "ConvertTimeToUtc($easternClock, $eastern).ToLocalTime()" in operational
    assert (
        "$PaperObservationLocalTime = Convert-EasternClockToLocal -Hour 16 -Minute 30"
        in operational
    )
    # MANDREV-001 follow-up: an operational-only (four-task) installation
    # must have a valid fail-closed success check. Scope "all" keeps the
    # original eight-task contract and still hard-requires the ML
    # config/artifact paths; scope "operational" must skip the ML checks
    # VISIBLY (a SkippedChecks report section), never silently.
    assert '[ValidateSet("all", "operational")]' in verifier
    assert "Scope 'all' verifies the ML shadow tasks and requires" in verifier
    assert "$expectedTasks = if ($verifyMl) { $operationalTasks + $mlTasks } else { $operationalTasks }" in verifier
    assert "SkippedChecks = $skippedChecks" in verifier
    assert "skipped: Scope=operational" in verifier
    # Statement-position `if` inside plain parentheses is a runtime error
    # in PowerShell; a conditional Detail must use the $( ... )
    # subexpression form. (Plain parentheses around ordinary expressions,
    # e.g. string concatenation, remain fine.) The bare `( if ...` form
    # crashed every end-to-end verifier run before 2026-08-04.
    import re as _re

    normalized = verifier.replace("\r\n", "\n")
    assert not _re.search(r"-(?:Detail|Ok) \(\s*\n\s*if\b", normalized), (
        "verifier uses a statement-position `if` inside plain parentheses; "
        "use the $( ... ) subexpression form"
    )
    assert "-Detail $(" in verifier


@pytest.mark.parametrize(
    ("day", "utc_hour"),
    [("2026-01-15", 21), ("2026-07-15", 20)],
)
@pytest.mark.parametrize(
    "host_zone",
    ["America/Los_Angeles", "America/New_York", "UTC", "Asia/Tokyo"],
)
def test_market_clock_conversion_is_after_close_across_host_zones_and_dst(
    day, utc_hour, host_zone
):
    eastern = ZoneInfo("America/New_York")
    market_clock = datetime.fromisoformat(f"{day}T16:30:00").replace(tzinfo=eastern)
    converted = market_clock.astimezone(ZoneInfo(host_zone))

    assert converted.astimezone(eastern).strftime("%H:%M") == "16:30"
    assert converted.astimezone(timezone.utc).hour == utc_hour
    assert (market_clock.hour, market_clock.minute) > (16, 0)


WINDOWS_VERIFIER_REASON = "The verifier targets Windows PowerShell and Task Scheduler."
REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
REAL_INTERPRETER_REASON = (
    "sys.executable is a Microsoft Store app execution alias, which the "
    "installer refuses by contract; run under a real interpreter to exercise "
    "the installer preview."
)


def _interpreter_is_store_alias() -> bool:
    """Return whether ``sys.executable`` is a Store app execution alias."""
    if os.name != "nt":
        return False
    try:
        status = os.lstat(sys.executable)
    except OSError:
        return False
    reparse = bool(
        getattr(status, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )
    return reparse or status.st_size == 0


def _ps_quote(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _task_quote(value: str | Path) -> str:
    escaped = str(value).replace('"', '\\"')
    return f'"{escaped}"'


def _cim(class_name: str) -> dict:
    return {"CimClassName": class_name}


def _time_trigger(minutes: int) -> dict:
    return {
        "CimClass": _cim("MSFT_TaskTimeTrigger"),
        "Enabled": True,
        "StartBoundary": (datetime.now() - timedelta(minutes=1)).isoformat(
            timespec="seconds"
        ),
        "Repetition": {"Interval": f"PT{minutes}M", "Duration": "P3650D"},
    }


def _weekly_trigger(hour: int, minute: int) -> dict:
    boundary = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
    return {
        "CimClass": _cim("MSFT_TaskWeeklyTrigger"),
        "Enabled": True,
        "StartBoundary": boundary.isoformat(timespec="seconds"),
        "WeeksInterval": 1,
        "DaysOfWeek": 62,
    }


def _logon_trigger(user: str) -> dict:
    return {
        "CimClass": _cim("MSFT_TaskLogonTrigger"),
        "Enabled": True,
        "UserId": user,
    }


def _settings(
    *, restart_count: int, restart_minutes: int, execution_minutes: int,
    battery_operation: bool,
) -> dict:
    settings = {
        "Enabled": True,
        "StartWhenAvailable": True,
        "MultipleInstances": "IgnoreNew",
        "RestartCount": restart_count,
        "RestartInterval": f"PT{restart_minutes}M",
        "ExecutionTimeLimit": (
            "PT0S" if execution_minutes == 0 else f"PT{execution_minutes}M"
        ),
        "DisallowStartIfOnBatteries": not battery_operation,
        "StopIfGoingOnBatteries": not battery_operation,
    }
    return settings


def _task(
    name: str,
    arguments: str,
    triggers: list[dict],
    *,
    user: str,
    settings: dict,
) -> dict:
    return {
        "TaskName": name,
        "TaskPath": "\\",
        "State": "Ready",
        "Principal": {
            "UserId": user,
            "RunLevel": "Limited",
            "LogonType": "Interactive",
        },
        "Actions": [
            {
                "CimClass": _cim("MSFT_TaskExecAction"),
                "Execute": str(Path(sys.executable).resolve()),
                "Arguments": arguments,
                "WorkingDirectory": str(REPOSITORY_ROOT),
            }
        ],
        "Triggers": triggers,
        "Settings": settings,
    }


def _windows_verifier_case(tmp_path: Path, scope: str = "operational") -> dict:
    from assistant.policy import DEFAULT_POLICY_PATH
    from assistant.storage import AssistantStore

    database = (tmp_path / "paper.db").resolve()
    AssistantStore(database)
    config = (tmp_path / "shadow.json").resolve()
    config.write_text("{}", encoding="utf-8")
    artifacts = (tmp_path / "shadow-artifacts").resolve()
    artifacts.mkdir()
    policy = DEFAULT_POLICY_PATH.resolve()
    python = Path(sys.executable).resolve()
    short_user = os.environ["USERNAME"]
    full_user = f"{os.environ.get('USERDOMAIN', short_user)}\\{short_user}"

    assistant = REPOSITORY_ROOT / "scripts" / "run_personal_assistant.py"
    watchdog = REPOSITORY_ROOT / "scripts" / "run_operations_watchdog.py"
    shadow = REPOSITORY_ROOT / "scripts" / "run_ml_shadow.py"
    supervisor = REPOSITORY_ROOT / "scripts" / "run_ml_evidence_supervisor.py"
    alerts = REPOSITORY_ROOT / "data" / "alerts.jsonl"
    monitoring = REPOSITORY_ROOT / "artifacts" / "ml-shadow-monitoring.json"
    supervisor_output = REPOSITORY_ROOT / "artifacts" / "ml-evidence-supervisor.json"

    assistant_arg = _task_quote(assistant)
    watchdog_arg = _task_quote(watchdog)
    database_arg = _task_quote(database)
    policy_arg = _task_quote(policy)
    alerts_arg = _task_quote(alerts)
    operational_commands = {
        "TradingAgent-Paper-OperationsCycle": (
            f"{assistant_arg} --database {database_arg} --policy {policy_arg} "
            f"operations-cycle --cancel-stale --alerts-jsonl {alerts_arg}"
        ),
        "TradingAgent-Paper-OrderMonitor": (
            f"{assistant_arg} --database {database_arg} --policy {policy_arg} "
            "monitor-orders --cancel-stale --poll-seconds 30"
        ),
        "TradingAgent-Paper-Watchdog": (
            f"{watchdog_arg} --database {database_arg} --policy {policy_arg} "
            f"--interval-seconds 60 --alerts-jsonl {alerts_arg}"
        ),
        "TradingAgent-Paper-PaperObservation": (
            f"{assistant_arg} --database {database_arg} --policy {policy_arg} "
            f"paper-observation --cancel-stale --alerts-jsonl {alerts_arg}"
        ),
    }
    short_settings = _settings(
        restart_count=3,
        restart_minutes=1,
        execution_minutes=8,
        battery_operation=True,
    )
    long_settings = _settings(
        restart_count=10,
        restart_minutes=1,
        execution_minutes=0,
        battery_operation=True,
    )
    tasks = [
        _task(
            "TradingAgent-Paper-OperationsCycle",
            operational_commands["TradingAgent-Paper-OperationsCycle"],
            [_time_trigger(10)],
            user=short_user,
            settings=copy.deepcopy(short_settings),
        ),
        _task(
            "TradingAgent-Paper-OrderMonitor",
            operational_commands["TradingAgent-Paper-OrderMonitor"],
            [_logon_trigger(short_user), _time_trigger(5)],
            user=short_user,
            settings=copy.deepcopy(long_settings),
        ),
        _task(
            "TradingAgent-Paper-Watchdog",
            operational_commands["TradingAgent-Paper-Watchdog"],
            [_logon_trigger(short_user), _time_trigger(5)],
            user=short_user,
            settings=copy.deepcopy(long_settings),
        ),
        _task(
            "TradingAgent-Paper-PaperObservation",
            operational_commands["TradingAgent-Paper-PaperObservation"],
            [_weekly_trigger(16, 30)],
            user=short_user,
            settings=copy.deepcopy(short_settings),
        ),
    ]

    ml_commands: dict[str, str] = {}
    if scope == "all":
        shadow_arg = _task_quote(shadow)
        supervisor_arg = _task_quote(supervisor)
        config_arg = _task_quote(config)
        artifacts_arg = _task_quote(artifacts)
        monitoring_arg = _task_quote(monitoring)
        supervisor_output_arg = _task_quote(supervisor_output)
        common = (
            f"{shadow_arg} --database {database_arg} --config {config_arg} "
            f"--artifact-dir {artifacts_arg} --alerts-jsonl {alerts_arg}"
        )
        ml_commands = {
            "TradingAgent-ML-Shadow-Predict": f"{common} predict",
            "TradingAgent-ML-Shadow-Mature": f"{common} mature",
            "TradingAgent-ML-Shadow-Monitor": (
                f"{common} monitor --output {monitoring_arg}"
            ),
            # The installer retains this trailing space for an empty credential list.
            "TradingAgent-ML-Shadow-Supervisor": (
                f"{supervisor_arg} --database {database_arg} --config {config_arg} "
                f"--artifact-dir {artifacts_arg} --alerts-jsonl {alerts_arg} "
                f"--output {supervisor_output_arg} "
            ),
        }
        ml_settings = _settings(
            restart_count=3,
            restart_minutes=5,
            execution_minutes=30,
            battery_operation=False,
        )
        for name, trigger in (
            ("TradingAgent-ML-Shadow-Predict", _weekly_trigger(16, 30)),
            ("TradingAgent-ML-Shadow-Mature", _weekly_trigger(17, 0)),
            ("TradingAgent-ML-Shadow-Monitor", _weekly_trigger(17, 15)),
            ("TradingAgent-ML-Shadow-Supervisor", _time_trigger(15)),
        ):
            tasks.append(
                _task(
                    name,
                    ml_commands[name],
                    [trigger],
                    user=short_user,
                    settings=copy.deepcopy(ml_settings),
                )
            )

    infos = {
        task["TaskName"]: {
            "LastTaskResult": 0,
            "LastRunTime": datetime.now().isoformat(timespec="seconds"),
            "NextRunTime": None,
        }
        for task in tasks
    }
    return {
        "fixture": {"Tasks": tasks, "Infos": infos},
        "database": database,
        "config": config,
        "artifacts": artifacts,
        "policy": policy,
        "python": python,
        "short_user": short_user,
        "full_user": full_user,
        "operational_commands": operational_commands,
        "ml_commands": ml_commands,
    }


def _task_by_name(case: dict, task_name: str) -> dict:
    return next(
        task for task in case["fixture"]["Tasks"] if task["TaskName"] == task_name
    )


def _run_windows_verifier(
    tmp_path: Path,
    case: dict,
    *,
    scope: str,
    require_task_run: bool = False,
) -> tuple[subprocess.CompletedProcess[str], dict]:
    powershell = shutil.which("powershell")
    assert powershell is not None, "Windows validation requires powershell.exe"
    fixture_path = tmp_path / "scheduled-task-fixture.json"
    fixture_path.write_text(json.dumps(case["fixture"]), encoding="utf-8")
    verifier = REPOSITORY_ROOT / "scripts" / "verify_windows_evidence_tasks.ps1"
    ml_arguments = ""
    if scope == "all":
        ml_arguments = (
            f" -ConfigPath {_ps_quote(case['config'])}"
            f" -ArtifactPath {_ps_quote(case['artifacts'])}"
        )
    require_argument = " -RequireTaskRun" if require_task_run else ""
    harness = tmp_path / "run-verifier.ps1"
    harness.write_text(
        "\n".join(
            (
                "$ErrorActionPreference = 'Stop'",
                (
                    "$global:VerifierFixture = Get-Content -Raw -LiteralPath "
                    f"{_ps_quote(fixture_path)} | ConvertFrom-Json"
                ),
                "function Get-ScheduledTask {",
                "    [CmdletBinding()]",
                "    param([string]$TaskName)",
                "    @($global:VerifierFixture.Tasks) | Where-Object { $_.TaskName -eq $TaskName }",
                "}",
                "function Get-ScheduledTaskInfo {",
                "    [CmdletBinding()]",
                "    param([Parameter(Mandatory = $true)][object]$InputObject)",
                "    $property = $global:VerifierFixture.Infos.PSObject.Properties[$InputObject.TaskName]",
                "    if ($null -ne $property) { return $property.Value }",
                "    return $null",
                "}",
                (
                    f"& {_ps_quote(verifier)}"
                    f" -RunAsUser {_ps_quote(case['full_user'])}"
                    f" -PythonPath {_ps_quote(case['python'])}"
                    f" -DatabasePath {_ps_quote(case['database'])}"
                    f" -RepositoryPath {_ps_quote(REPOSITORY_ROOT)}"
                    f" -PolicyPath {_ps_quote(case['policy'])}"
                    " -RequiredCredentialNames @()"
                    " -PaperObservationLocalTime '2000-01-01T16:30:00'"
                    " -PredictionLocalTime '2000-01-01T16:30:00'"
                    " -MaturityLocalTime '2000-01-01T17:00:00'"
                    " -MonitoringLocalTime '2000-01-01T17:15:00'"
                    f" -Scope {scope}{ml_arguments}{require_argument}"
                ),
                "exit $LASTEXITCODE",
            )
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.stdout, (
        f"verifier emitted no JSON (exit={result.returncode}): {result.stderr}"
    )
    return result, json.loads(result.stdout)


def _run_installer_preview(tmp_path: Path, case: dict, *, lane: str) -> list[dict]:
    powershell = shutil.which("powershell")
    assert powershell is not None, "Windows validation requires powershell.exe"
    if lane == "operational":
        installer = REPOSITORY_ROOT / "scripts" / "install_windows_operational_tasks.ps1"
        lane_arguments = (
            f" -PolicyPath {_ps_quote(case['policy'])}"
            " -PaperObservationLocalTime '2000-01-01T16:30:00'"
        )
    else:
        installer = REPOSITORY_ROOT / "scripts" / "install_windows_ml_shadow_tasks.ps1"
        lane_arguments = (
            f" -ConfigPath {_ps_quote(case['config'])}"
            f" -ArtifactPath {_ps_quote(case['artifacts'])}"
            " -RequiredCredentialNames @()"
            " -PredictionLocalTime '2000-01-01T16:30:00'"
            " -MaturityLocalTime '2000-01-01T17:00:00'"
            " -MonitoringLocalTime '2000-01-01T17:15:00'"
        )
    harness = tmp_path / f"preview-{lane}-installer.ps1"
    harness.write_text(
        "\n".join(
            (
                "$ErrorActionPreference = 'Stop'",
                (
                    f"$preview = @(& {_ps_quote(installer)}"
                    f" -PythonPath {_ps_quote(case['python'])}"
                    f" -DatabasePath {_ps_quote(case['database'])}"
                    f" -RepositoryPath {_ps_quote(REPOSITORY_ROOT)}"
                    f" -RunAsUser {_ps_quote(case['full_user'])}"
                    " -TaskLogonType Interactive"
                    f"{lane_arguments} -WhatIf)"
                ),
                "$preview | ConvertTo-Json -Depth 5",
            )
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout, result.stderr
    return json.loads(result.stdout)


def _task_checks(report: dict) -> dict[str, dict]:
    return {
        check["Name"].removeprefix("task:"): check
        for check in report["Checks"]
        if check["Name"].startswith("task:")
    }


@pytest.mark.skipif(os.name != "nt", reason=WINDOWS_VERIFIER_REASON)
@pytest.mark.skipif(_interpreter_is_store_alias(), reason=REAL_INTERPRETER_REASON)
def test_windows_verifier_green_actions_match_installer_whatif_previews(tmp_path):
    """Data-only installer previews are the source of truth for action strings.

    Neither preview reaches a ScheduledTasks cmdlet. This pins the behavioral
    fixtures (and therefore the verifier's green contract) to both installers,
    so future argument-order or default-path drift fails before deployment.
    """
    case = _windows_verifier_case(tmp_path, scope="all")
    expected = {
        task["TaskName"]: task["Actions"][0] for task in case["fixture"]["Tasks"]
    }
    previews = _run_installer_preview(tmp_path, case, lane="operational")
    previews += _run_installer_preview(tmp_path, case, lane="ml")
    assert len(previews) == 8
    for preview in previews:
        action = expected[preview["TaskName"]]
        assert preview["Execute"] == action["Execute"]
        assert preview["Arguments"] == action["Arguments"]
        assert preview["WorkingDirectory"] == action["WorkingDirectory"]


@pytest.mark.skipif(os.name != "nt", reason=WINDOWS_VERIFIER_REASON)
def test_windows_verifier_accepts_exact_operational_contract_and_queued_state(tmp_path):
    case = _windows_verifier_case(tmp_path)
    _task_by_name(case, "TradingAgent-Paper-OperationsCycle")["State"] = "Queued"
    result, report = _run_windows_verifier(tmp_path, case, scope="operational")
    assert result.returncode == 0, report
    assert report["Ok"] is True
    assert report["FailedCheckCount"] == 0
    assert len(_task_checks(report)) == 4
    assert all(check["Ok"] is True for check in _task_checks(report).values())


@pytest.mark.skipif(os.name != "nt", reason=WINDOWS_VERIFIER_REASON)
def test_windows_verifier_accepts_exact_all_eight_task_contract(tmp_path):
    case = _windows_verifier_case(tmp_path, scope="all")
    result, report = _run_windows_verifier(tmp_path, case, scope="all")
    assert result.returncode == 0, report
    assert report["Ok"] is True
    assert report["FailedCheckCount"] == 0
    assert len(_task_checks(report)) == 8
    assert all(check["Ok"] is True for check in _task_checks(report).values())


@pytest.mark.skipif(os.name != "nt", reason=WINDOWS_VERIFIER_REASON)
@pytest.mark.parametrize(
    ("scope", "mutation", "task_name", "detail_fragment"),
    [
        ("operational", "swapped_command", "TradingAgent-Paper-OperationsCycle", "arguments"),
        ("operational", "wrong_database", "TradingAgent-Paper-OperationsCycle", "arguments"),
        ("operational", "wrong_policy", "TradingAgent-Paper-OrderMonitor", "arguments"),
        ("operational", "missing_subcommand", "TradingAgent-Paper-Watchdog", "arguments"),
        ("operational", "working_directory", "TradingAgent-Paper-PaperObservation", "working_directory"),
        ("operational", "extra_action", "TradingAgent-Paper-OperationsCycle", "action_count"),
        ("operational", "wrong_action_type", "TradingAgent-Paper-OperationsCycle", "action_type"),
        ("operational", "wrong_interval", "TradingAgent-Paper-OperationsCycle", "interval"),
        ("operational", "missing_trigger", "TradingAgent-Paper-OrderMonitor", "expected 2"),
        ("operational", "wrong_weekdays", "TradingAgent-Paper-PaperObservation", "days_of_week"),
        ("operational", "disabled", "TradingAgent-Paper-Watchdog", "enabled"),
        ("operational", "wrong_task_path", "TradingAgent-Paper-OperationsCycle", "exact root"),
        ("operational", "multiple_instances", "TradingAgent-Paper-OrderMonitor", "multiple_instances"),
        ("operational", "start_when_available", "TradingAgent-Paper-OperationsCycle", "start_when_available"),
        ("operational", "restart_interval", "TradingAgent-Paper-Watchdog", "restart_interval"),
        ("operational", "battery_stop", "TradingAgent-Paper-PaperObservation", "battery_stop"),
        ("operational", "restart_count", "TradingAgent-Paper-Watchdog", "restart_count"),
        ("all", "wrong_config", "TradingAgent-ML-Shadow-Predict", "arguments"),
        ("all", "wrong_artifact", "TradingAgent-ML-Shadow-Mature", "arguments"),
        ("all", "wrong_output", "TradingAgent-ML-Shadow-Monitor", "arguments"),
        ("all", "extra_credential", "TradingAgent-ML-Shadow-Supervisor", "arguments"),
        ("all", "wrong_clock", "TradingAgent-ML-Shadow-Predict", "local_time"),
        ("all", "wrong_supervisor_interval", "TradingAgent-ML-Shadow-Supervisor", "interval"),
        ("all", "ml_execution_limit", "TradingAgent-ML-Shadow-Mature", "execution_time_limit"),
        ("all", "ml_battery_start", "TradingAgent-ML-Shadow-Predict", "battery_start"),
    ],
)
def test_windows_verifier_rejects_dangerous_one_field_task_mutations(
    tmp_path, scope, mutation, task_name, detail_fragment
):
    case = _windows_verifier_case(tmp_path, scope=scope)
    task = _task_by_name(case, task_name)
    action = task["Actions"][0]
    if mutation == "swapped_command":
        action["Arguments"] = case["operational_commands"][
            "TradingAgent-Paper-PaperObservation"
        ]
    elif mutation == "wrong_database":
        action["Arguments"] = action["Arguments"].replace(
            _task_quote(case["database"]), _task_quote(tmp_path / "other.db")
        )
    elif mutation == "wrong_policy":
        action["Arguments"] = action["Arguments"].replace(
            _task_quote(case["policy"]), _task_quote(tmp_path / "other-policy.json")
        )
    elif mutation == "missing_subcommand":
        action["Arguments"] = action["Arguments"].replace(" --interval-seconds 60", "")
    elif mutation == "working_directory":
        action["WorkingDirectory"] = str(tmp_path)
    elif mutation == "extra_action":
        task["Actions"].append(copy.deepcopy(action))
    elif mutation == "wrong_action_type":
        action["CimClass"] = _cim("MSFT_TaskComHandlerAction")
    elif mutation == "wrong_interval":
        task["Triggers"][0]["Repetition"]["Interval"] = "PT11M"
    elif mutation == "missing_trigger":
        task["Triggers"] = task["Triggers"][:1]
    elif mutation == "wrong_weekdays":
        task["Triggers"][0]["DaysOfWeek"] = 2
    elif mutation == "disabled":
        task["Settings"]["Enabled"] = False
        task["State"] = "Disabled"
    elif mutation == "wrong_task_path":
        task["TaskPath"] = "\\Other\\"
    elif mutation == "multiple_instances":
        task["Settings"]["MultipleInstances"] = "Parallel"
    elif mutation == "start_when_available":
        task["Settings"]["StartWhenAvailable"] = False
    elif mutation == "restart_interval":
        task["Settings"]["RestartInterval"] = "PT30M"
    elif mutation == "battery_stop":
        task["Settings"]["StopIfGoingOnBatteries"] = True
    elif mutation == "restart_count":
        task["Settings"]["RestartCount"] = 0
    elif mutation == "wrong_config":
        action["Arguments"] = action["Arguments"].replace(
            _task_quote(case["config"]), _task_quote(tmp_path / "other-shadow.json")
        )
    elif mutation == "wrong_artifact":
        action["Arguments"] = action["Arguments"].replace(
            _task_quote(case["artifacts"]), _task_quote(tmp_path / "other-artifacts")
        )
    elif mutation == "wrong_output":
        action["Arguments"] = action["Arguments"].replace(
            _task_quote(REPOSITORY_ROOT / "artifacts" / "ml-shadow-monitoring.json"),
            _task_quote(tmp_path / "other-monitoring.json"),
        )
    elif mutation == "extra_credential":
        action["Arguments"] += '--required-credential "UNEXPECTED_SECRET_NAME"'
    elif mutation == "wrong_clock":
        task["Triggers"][0]["StartBoundary"] = datetime.now().replace(
            hour=9, minute=30, second=0, microsecond=0
        ).isoformat(timespec="seconds")
    elif mutation == "wrong_supervisor_interval":
        task["Triggers"][0]["Repetition"]["Interval"] = "PT30M"
    elif mutation == "ml_execution_limit":
        task["Settings"]["ExecutionTimeLimit"] = "PT5M"
    elif mutation == "ml_battery_start":
        task["Settings"]["DisallowStartIfOnBatteries"] = False
    else:  # pragma: no cover - keeps additions fail-closed
        raise AssertionError(f"unknown mutation: {mutation}")

    result, report = _run_windows_verifier(tmp_path, case, scope=scope)
    assert result.returncode == 1
    assert report["Ok"] is False
    checks = _task_checks(report)
    assert checks[task_name]["Ok"] is False
    assert detail_fragment in checks[task_name]["Detail"]
    assert all(
        check["Ok"] is True for name, check in checks.items() if name != task_name
    )


@pytest.mark.skipif(os.name != "nt", reason=WINDOWS_VERIFIER_REASON)
def test_windows_verifier_preserves_never_run_and_completed_error_contract(tmp_path):
    case = _windows_verifier_case(tmp_path)
    for info in case["fixture"]["Infos"].values():
        info["LastTaskResult"] = 267011
        info["LastRunTime"] = "1999-11-30T00:00:00"

    result, report = _run_windows_verifier(tmp_path, case, scope="operational")
    assert result.returncode == 0, report
    assert all(check["Ok"] is True for check in _task_checks(report).values())

    result, report = _run_windows_verifier(
        tmp_path, case, scope="operational", require_task_run=True
    )
    assert result.returncode == 1
    assert report["RequireTaskRun"] is True
    assert all(check["Ok"] is False for check in _task_checks(report).values())

    # The sentinel date only permits the exact SCHED_S_TASK_HAS_NOT_RUN code.
    # Sentinel + genuine failure must remain a fail-closed inconsistency.
    for info in case["fixture"]["Infos"].values():
        info["LastTaskResult"] = 1
    result, report = _run_windows_verifier(tmp_path, case, scope="operational")
    assert result.returncode == 1
    assert all(check["Ok"] is False for check in _task_checks(report).values())

    for info in case["fixture"]["Infos"].values():
        info["LastTaskResult"] = 1
        info["LastRunTime"] = datetime.now().isoformat(timespec="seconds")
    result, report = _run_windows_verifier(tmp_path, case, scope="operational")
    assert result.returncode == 1
    assert all(check["Ok"] is False for check in _task_checks(report).values())


@pytest.mark.skipif(os.name != "nt", reason=WINDOWS_VERIFIER_REASON)
def test_windows_operational_verifier_executes_without_ml_paths(tmp_path):
    case = _windows_verifier_case(tmp_path)
    case["fixture"]["Tasks"] = []
    case["fixture"]["Infos"] = {}
    result, report = _run_windows_verifier(tmp_path, case, scope="operational")
    assert result.returncode == 1
    assert report["Scope"] == "operational"
    assert report["Ok"] is False
    assert report["ProductionAuthoritative"] is False
    assert report["FailedCheckCount"] == 8
    assert list(_task_checks(report)) == [
        "TradingAgent-Paper-OperationsCycle",
        "TradingAgent-Paper-OrderMonitor",
        "TradingAgent-Paper-Watchdog",
        "TradingAgent-Paper-PaperObservation",
    ]
    assert [
        item["Name"] for item in report["Checks"]
        if item["Name"].startswith("task_policy:")
    ] == [
        "task_policy:TradingAgent-Paper-OperationsCycle",
        "task_policy:TradingAgent-Paper-OrderMonitor",
        "task_policy:TradingAgent-Paper-Watchdog",
        "task_policy:TradingAgent-Paper-PaperObservation",
    ]
    assert [item["Name"] for item in report["SkippedChecks"]] == [
        "config_path",
        "artifact_path",
        "task:TradingAgent-ML-Shadow-Predict",
        "task:TradingAgent-ML-Shadow-Mature",
        "task:TradingAgent-ML-Shadow-Monitor",
        "task:TradingAgent-ML-Shadow-Supervisor",
    ]
