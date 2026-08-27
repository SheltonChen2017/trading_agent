"""Independent-review coverage for the GR-3 operational drill runner."""
from __future__ import annotations

import subprocess
import sqlite3
from pathlib import Path

import pytest

import assistant.paper_evidence as paper_evidence
import assistant.storage as storage
import scripts.run_fault_drill as runner


def _fake_pytest(
    monkeypatch: pytest.MonkeyPatch,
    *,
    xml: str,
    returncode: int = 0,
) -> None:
    def run(command, **_kwargs):
        junit_path = Path(command[command.index("--junitxml") + 1])
        junit_path.write_text(xml, encoding="utf-8")
        return subprocess.CompletedProcess(
            command,
            returncode,
            stdout="synthetic pytest stdout",
            stderr="synthetic pytest stderr",
        )

    monkeypatch.setattr(runner.subprocess, "run", run)


def test_skipped_fault_case_is_not_reported_as_passed(monkeypatch):
    _fake_pytest(
        monkeypatch,
        xml=(
            "<testsuites><testsuite>"
            '<testcase name="test_fault"><skipped message="not runnable" />'
            "</testcase></testsuite></testsuites>"
        ),
    )

    outcomes = runner._run_fault_matrix()

    assert outcomes["test_fault"]["passed"] is False
    assert "skipped" in outcomes["test_fault"]["detail"].lower()


def test_nonzero_pytest_exit_cannot_produce_a_passing_matrix(monkeypatch):
    _fake_pytest(
        monkeypatch,
        returncode=1,
        xml=(
            "<testsuites><testsuite>"
            '<testcase name="test_fault" />'
            "</testsuite></testsuites>"
        ),
    )

    with pytest.raises(RuntimeError, match="exit code 1"):
        runner._run_fault_matrix()


@pytest.mark.parametrize("report_commit", ["unknown", "b" * 40])
def test_active_epoch_refuses_unknown_or_mismatched_runtime_lineage(
    monkeypatch,
    tmp_path,
    report_commit,
):
    calls = []

    class FakeStore:
        def get_active_paper_evidence_epoch(self):
            return {
                "evidence_epoch": "paper-epoch-1",
                "lineage": {"code_commit": "a" * 40},
            }

    monkeypatch.setattr(storage, "AssistantStore", lambda _path: FakeStore())
    monkeypatch.setattr(
        paper_evidence,
        "record_operational_drill",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {"drill_id": "bad"},
    )
    report = {
        "code_commit": report_commit,
        "report_sha256": "c" * 64,
        "faults": [
            {"fault_id": fault_id, "requirement": fault_id, "passed": True}
            for fault_id in ("F1", "F2", "F3", "F4", "F9")
        ],
    }

    with pytest.raises(RuntimeError, match="active evidence epoch"):
        runner.record_drills(
            report,
            tmp_path / "operator.db",
            "reviewer",
            "fault-report.json",
        )

    assert calls == []


def test_matching_active_epoch_lineage_records_all_supported_drill_types(
    monkeypatch,
    tmp_path,
):
    calls = []

    class FakeStore:
        def get_active_paper_evidence_epoch(self):
            return {
                "evidence_epoch": "paper-epoch-1",
                "lineage": {"code_commit": "a" * 40},
            }

    monkeypatch.setattr(storage, "AssistantStore", lambda _path: FakeStore())

    def record(_store, **kwargs):
        calls.append(kwargs)
        return {"drill_id": f"drill-{kwargs['drill_type']}"}

    monkeypatch.setattr(paper_evidence, "record_operational_drill", record)
    report = {
        "code_commit": "a" * 40,
        "report_sha256": "c" * 64,
        "faults": [
            {"fault_id": fault_id, "requirement": fault_id, "passed": True}
            for fault_id in ("F1", "F2", "F3", "F4", "F9")
        ],
    }

    recorded = runner.record_drills(
        report,
        tmp_path / "operator.db",
        "reviewer",
        "fault-report.json",
    )

    assert [row["drill_type"] for row in recorded] == [
        "ambiguous_submission",
        "kill_switch",
        "restart_recovery",
    ]
    assert len(calls) == 3


def test_atomic_report_write_removes_temporary_file_on_publish_failure(
    monkeypatch,
    tmp_path,
):
    output = tmp_path / "fault-report.json"

    def fail_link(_source, _destination):
        raise OSError("injected publish failure")

    monkeypatch.setattr(runner.os, "link", fail_link)

    with pytest.raises(OSError, match="injected publish failure"):
        runner._write_report_atomically(output, {"passed": True})

    assert not output.exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_reconciliation_alert_failure_preserves_local_and_runtime_halt(tmp_path):
    store = storage.AssistantStore(tmp_path / "halt.db")
    store.set_kill_switch(False, reason="review baseline")
    with store._connect() as connection:
        connection.execute(
            """
            CREATE TRIGGER inject_alert_failure
            BEFORE INSERT ON operational_alerts
            BEGIN
                SELECT RAISE(ABORT, 'injected alert failure');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="injected alert failure"):
        store.activate_reconciliation_halt(
            proposal_id="p-review",
            reason="identity mismatch",
        )

    # Diagnostic persistence may fail, but containment must survive in both
    # the local database fallback and the runtime-global stop.
    assert store.get_kill_switch()["active"] is True
    assert storage.get_runtime_emergency_stop(store.path)["active"] is True
    assert store.list_operational_alerts() == []
