from __future__ import annotations

import ast
import json
import os
import shutil
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
    assert "$task.Principal.LogonType -eq $ExpectedTaskLogonType" in verifier
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


@pytest.mark.skipif(
    os.name != "nt",
    reason="The verifier targets Windows PowerShell and Task Scheduler.",
)
def test_windows_verifier_accepts_a_freshly_installed_never_run_task(tmp_path):
    """Field failure 2026-08-05 (first install on the operational host):
    Task Scheduler stores the principal UserId in SHORT form while the
    operator passes DOMAIN\\name, reports LastTaskResult 267011
    (SCHED_S_TASK_HAS_NOT_RUN) for a fresh task, and uses 1999-11-30 (not
    DateTime.MinValue) as the never-ran sentinel. The submitted verifier
    failed every correctly installed task on all three. This harness stubs
    ONE present task exactly as the field reported it -- short-form user,
    267011, 1999 sentinel -- using the real current user's two name forms
    so the SID normalization genuinely resolves, and requires the overall
    report to pass. A completed run's genuine nonzero exit must still
    fail (second stub)."""
    powershell = shutil.which("powershell")
    assert powershell is not None, "Windows validation requires powershell.exe"

    database = tmp_path / "paper.db"
    database.touch()
    verifier = (
        Path(__file__).resolve().parent.parent
        / "scripts"
        / "verify_windows_evidence_tasks.ps1"
    )

    def ps_quote(value) -> str:
        return "'" + str(value).replace("'", "''") + "'"

    short_user = os.environ["USERNAME"]
    full_user = f"{os.environ.get('USERDOMAIN', short_user)}\\{short_user}"

    def harness_script(last_task_result: int) -> str:
        return "\n".join(
            (
                "$ErrorActionPreference = 'Stop'",
                "function Get-ScheduledTask {",
                "    [CmdletBinding()]",
                "    param([string]$TaskName)",
                "    return [PSCustomObject]@{",
                "        TaskName = $TaskName",
                "        State = 'Ready'",
                "        Principal = [PSCustomObject]@{",
                f"            UserId = {ps_quote(short_user)}",
                "            RunLevel = 'Limited'",
                "            LogonType = 'Interactive'",
                "        }",
                "        Actions = @([PSCustomObject]@{",
                f"            Execute = {ps_quote(sys.executable)}",
                "        })",
                "    }",
                "}",
                "function Get-ScheduledTaskInfo {",
                "    [CmdletBinding()]",
                "    param([string]$TaskName)",
                "    return [PSCustomObject]@{",
                f"        LastTaskResult = {last_task_result}",
                "        LastRunTime = [datetime]'1999-11-30'",
                "        NextRunTime = $null",
                "    }",
                "}",
                (
                    f"& {ps_quote(verifier)} "
                    f"-RunAsUser {ps_quote(full_user)} "
                    f"-PythonPath {ps_quote(sys.executable)} "
                    f"-DatabasePath {ps_quote(database)} "
                    "-RequiredCredentialNames @() "
                    "-Scope operational"
                ),
                "exit $LASTEXITCODE",
            )
        )

    def run_harness(last_task_result: int):
        harness = tmp_path / f"run-verifier-{last_task_result}.ps1"
        harness.write_text(harness_script(last_task_result), encoding="utf-8")
        result = subprocess.run(
            [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result, json.loads(result.stdout)

    # 267011 = not yet run: a fresh, correctly installed task must PASS.
    result, report = run_harness(267011)
    assert result.returncode == 0, result.stdout
    assert report["Ok"] is True
    assert report["FailedCheckCount"] == 0

    # A post-start verification must NOT accept the same never-ran state.
    # Credential Guard exposed exactly this failure direction: requesting a
    # start can return without error while the task remains at 267011.
    harness = tmp_path / "run-verifier-require-task-run.ps1"
    harness.write_text(
        harness_script(267011).replace(
            "-Scope operational", "-Scope operational -RequireTaskRun"
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
    report = json.loads(result.stdout)
    assert result.returncode == 1
    assert report["Ok"] is False
    assert report["RequireTaskRun"] is True

    # An inconsistent sentinel date plus a genuine error code must fail
    # closed; only the exact 1999/267011 never-run pair is tolerated.
    result, report = run_harness(1)
    assert result.returncode == 1
    assert report["Ok"] is False

    # A completed run's genuine nonzero exit (e.g. 1) must still FAIL --
    # this second shape uses a real run date so only the exit code decides.
    harness = tmp_path / "run-verifier-real-failure.ps1"
    harness.write_text(
        harness_script(1).replace(
            "[datetime]'1999-11-30'", "[datetime]'2026-08-05'"
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
    report = json.loads(result.stdout)
    assert result.returncode == 1
    assert report["Ok"] is False


def test_windows_operational_verifier_executes_without_ml_paths(tmp_path):
    """Exercise the real PowerShell scope instead of only inspecting source.

    Scheduler cmdlets are replaced with read-only no-task stubs so this test
    verifies parameter binding, conditional expressions, JSON reporting, and
    fail-closed task absence without touching the host scheduler.
    """
    powershell = shutil.which("powershell")
    assert powershell is not None, "Windows validation requires powershell.exe"

    database = tmp_path / "paper.db"
    database.touch()
    verifier = (
        Path(__file__).resolve().parent.parent
        / "scripts"
        / "verify_windows_evidence_tasks.ps1"
    )

    def ps_quote(value: str | Path) -> str:
        return "'" + str(value).replace("'", "''") + "'"

    harness = tmp_path / "run-verifier.ps1"
    harness.write_text(
        "\n".join(
            (
                "$ErrorActionPreference = 'Stop'",
                "function Get-ScheduledTask {",
                "    [CmdletBinding()]",
                "    param([string]$TaskName)",
                "    return $null",
                "}",
                "function Get-ScheduledTaskInfo { throw 'unexpected task-info call' }",
                (
                    f"& {ps_quote(verifier)} "
                    f"-RunAsUser 'REVIEW\\verifier' "
                    f"-PythonPath {ps_quote(sys.executable)} "
                    f"-DatabasePath {ps_quote(database)} "
                    "-RequiredCredentialNames @() "
                    "-Scope operational"
                ),
                "exit $LASTEXITCODE",
            )
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1, result.stderr
    report = json.loads(result.stdout)
    assert report["Scope"] == "operational"
    assert report["Ok"] is False
    assert report["ProductionAuthoritative"] is False
    assert report["FailedCheckCount"] == 4
    assert [item["Name"] for item in report["Checks"] if item["Name"].startswith("task:")] == [
        "task:TradingAgent-Paper-OperationsCycle",
        "task:TradingAgent-Paper-OrderMonitor",
        "task:TradingAgent-Paper-Watchdog",
        "task:TradingAgent-Paper-PaperObservation",
    ]
    assert [item["Name"] for item in report["SkippedChecks"]] == [
        "config_path",
        "artifact_path",
        "task:TradingAgent-ML-Shadow-Predict",
        "task:TradingAgent-ML-Shadow-Mature",
        "task:TradingAgent-ML-Shadow-Monitor",
        "task:TradingAgent-ML-Shadow-Supervisor",
    ]
