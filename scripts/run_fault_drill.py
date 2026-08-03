"""GR-3 fault-injection drill harness.

Runs the complete adversarial fault matrix in ``tests/faults/`` (real
SQLite store, real execution entry points, scripted broker), maps each
plan-mandated fault to its observed outcome, writes an immutable
hash-stamped drill report artifact, and can additionally record the
producible promotion drill types (``ambiguous_submission``,
``restart_recovery``, ``kill_switch``) in a database's
``operational_drill_runs`` table.

Safety posture:

- By default this command records NOTHING durable: it runs the matrix in
  a disposable pytest environment (which itself pins
  ``TRADING_ASSISTANT_DB`` into a temp directory and strips brokerage
  credentials) and writes one JSON artifact.
- ``--record-database`` opts into writing drill rows. If that database
  has an ACTIVE paper evidence epoch, recording goes through
  ``assistant.paper_evidence.record_operational_drill`` and is bound to
  the epoch's lineage (promotion evidence). Without an active epoch the
  rows are written with ``evidence_epoch=NULL`` and are explicitly marked
  ``verification_only`` -- they prove the drills run, never that epoch
  evidence exists.
- A drill row is recorded with ``passed=False`` when its faults fail;
  failure is evidence too and must never be silently dropped.
- ``alert_delivery`` and ``backup_restore`` are deliberately NOT recorded
  here: backup_restore already has its own producer (the
  ``recovery-drill`` CLI) and alert_delivery cannot honestly pass until
  GR-5 ships a real delivery channel.

Usage:
    python scripts/run_fault_drill.py
    python scripts/run_fault_drill.py --output artifacts/fault-drill.json
    python scripts/run_fault_drill.py --record-database data/trading_assistant.db --operator "<name>"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

_REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPOSITORY_ROOT))

# One entry per plan row (archived GENERAL_READINESS_IMPLEMENTATION_PLAN
# section 8.2), plus the two 2026-08-02 isolation incidents the GR status
# doc earmarked for GR-3. The test names double as the drill inventory:
# if a listed test disappears or is renamed, the harness fails loudly
# rather than reporting a smaller matrix as complete.
FAULT_MATRIX: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "F1",
        "Broker times out after submit, before ack -> reconciler resolves; never a blind resubmit",
        ("test_f1_submit_timeout_resolves_by_lookup_never_resubmits",),
    ),
    (
        "F2",
        "Broker returns a duplicate order ID -> idempotent; one order, one journal entry",
        ("test_f2_duplicate_order_id_is_idempotent_one_order_one_journal",),
    ),
    (
        "F3",
        "Process killed mid-submission -> restart resolves the claim; no orphan",
        (
            "test_f3_pre_broker_crash_recovers_claim_and_frees_the_slot",
            "test_f3_crash_mid_reconciliation_recovers_to_retryable",
            "test_f3_restart_recovers_submitting_order_without_resubmit",
        ),
    ),
    (
        "F4",
        "Broker reports an order the ledger does not expect -> critical halt; refuse further submissions",
        (
            "test_f4_unexpected_order_halts_platform_and_blocks_new_submissions",
            "test_f4_submit_time_unexpected_order_also_alerts_and_halts",
        ),
    ),
    (
        "F5",
        "Ticker halted between approval and submit -> refuse; risk-reducing sells elsewhere still permitted",
        ("test_f5_halted_ticker_refused_but_other_risk_reducing_sell_proceeds",),
    ),
    (
        "F6",
        "Corporate action between snapshot and submit -> refuse on share-count mismatch",
        ("test_f6_share_count_mismatch_after_corporate_action_is_refused",),
    ),
    (
        "F7",
        "Clock skew / stale snapshot -> refuse on freshness",
        (
            "test_f7_stale_quote_is_refused",
            "test_f7_future_quote_timestamp_clock_skew_is_refused",
        ),
    ),
    (
        "F8",
        "Disk full during journal write -> transaction rolls back; no partial state",
        ("test_f8_disk_full_during_journal_rolls_back_and_keeps_the_truth",),
    ),
    (
        "F9",
        "Kill switch flips mid-flight -> no new submissions; in-flight resolves cleanly",
        ("test_f9_kill_switch_mid_flight_blocks_new_but_inflight_resolves",),
    ),
    (
        "F10",
        "Regression drill (2026-08-02): pytest must never touch the operator database",
        ("test_f10_tests_are_isolated_from_the_operator_database",),
    ),
    (
        "F11",
        "Regression drill (2026-08-02): no live brokerage credentials reach the suite",
        ("test_f11_no_live_broker_credentials_reach_the_suite",),
    ),
)

# Which faults substantiate which producible promotion drill type.
DRILL_TYPE_FAULTS: dict[str, tuple[str, ...]] = {
    "ambiguous_submission": ("F1", "F2"),
    "restart_recovery": ("F3",),
    "kill_switch": ("F4", "F9"),
}


def _run_fault_matrix() -> dict:
    """Run tests/faults/ once and return per-test outcomes from JUnit XML."""
    with tempfile.TemporaryDirectory(prefix="fault-drill-") as scratch:
        junit_path = Path(scratch) / "fault-matrix.xml"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "--basetemp",
                str(Path(scratch) / "basetemp"),
                "--junitxml",
                str(junit_path),
                "tests/faults/",
            ],
            cwd=_REPOSITORY_ROOT,
            capture_output=True,
            text=True,
        )
        if not junit_path.exists():
            raise RuntimeError(
                "fault matrix produced no JUnit report; pytest said:\n"
                + completed.stdout[-2000:]
                + completed.stderr[-2000:]
            )
        tree = ElementTree.parse(junit_path)
    outcomes: dict[str, dict] = {}
    for case in tree.iter("testcase"):
        name = case.attrib.get("name", "")
        failure_nodes = list(case.iter("failure")) + list(case.iter("error"))
        skipped_nodes = list(case.iter("skipped"))
        nonpassing_nodes = failure_nodes + skipped_nodes
        if skipped_nodes:
            message = skipped_nodes[0].attrib.get("message", "")
            detail = f"skipped: {message}" if message else "skipped"
        elif failure_nodes:
            detail = failure_nodes[0].attrib.get("message", "")[:500]
        else:
            detail = ""
        outcomes[name] = {
            "passed": not nonpassing_nodes,
            "detail": detail,
        }
    # Exit 1 is the ordinary "one or more tests failed" result and those
    # failures are useful drill evidence when JUnit captured them. Every
    # other non-zero code is a harness failure; exit 1 with no non-passing
    # case is also a session/teardown failure that the per-test inventory
    # cannot honestly explain.
    captured_failure = any(not result["passed"] for result in outcomes.values())
    if completed.returncode not in (0, 1) or (
        completed.returncode == 1 and not captured_failure
    ):
        raise RuntimeError(
            f"fault-matrix pytest exited with exit code {completed.returncode} "
            "without a complete per-test explanation; stdout/stderr tail:\n"
            + completed.stdout[-1000:]
            + completed.stderr[-1000:]
        )
    return outcomes


def _current_commit() -> dict:
    try:
        from assistant.runtime_identity import current_commit

        return {"code_commit": current_commit(), "commit_source": "git"}
    except Exception as exc:
        # Fail closed on lineage: an unknown commit is recorded AS unknown,
        # never guessed -- and such a report cannot be promotion evidence.
        return {"code_commit": "unknown", "commit_source": f"unavailable: {exc}"}


def build_drill_report() -> dict:
    outcomes = _run_fault_matrix()
    faults = []
    for fault_id, requirement, test_names in FAULT_MATRIX:
        tests = []
        for test_name in test_names:
            result = outcomes.get(test_name)
            if result is None:
                # A listed drill test that did not run is a FAILED drill,
                # not a smaller matrix.
                tests.append(
                    {"test": test_name, "passed": False, "detail": "test not collected"}
                )
            else:
                tests.append({"test": test_name, **result})
        faults.append(
            {
                "fault_id": fault_id,
                "requirement": requirement,
                "passed": all(t["passed"] for t in tests),
                "tests": tests,
            }
        )
    unexpected = sorted(
        set(outcomes)
        - {name for _, _, tests in FAULT_MATRIX for name in tests}
    )
    report = {
        "drill": "gr3_fault_matrix",
        "performed_at": datetime.now(timezone.utc).isoformat(),
        "passed": all(f["passed"] for f in faults) and not unexpected,
        "faults": faults,
        "unmapped_tests": unexpected,
        **_current_commit(),
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return report


def record_drills(report: dict, database: Path, operator: str, artifact: str) -> list[dict]:
    from assistant.paper_evidence import record_operational_drill
    from assistant.storage import AssistantStore

    store = AssistantStore(database)
    epoch = store.get_active_paper_evidence_epoch()
    if epoch is not None:
        report_commit = str(report.get("code_commit") or "")
        epoch_commit = str(epoch.get("lineage", {}).get("code_commit") or "")
        if report_commit == "unknown" or report_commit != epoch_commit:
            raise RuntimeError(
                "Refusing to record GR-3 drills into the active evidence epoch: "
                f"the drill runtime commit is {report_commit or 'missing'}, but "
                f"the epoch is bound to {epoch_commit or 'missing'}. Run the "
                "drill from the epoch's exact clean commit."
            )
    fault_by_id = {f["fault_id"]: f for f in report["faults"]}
    recorded = []
    for drill_type, fault_ids in sorted(DRILL_TYPE_FAULTS.items()):
        evidence = {
            "operator": operator,
            "artifact": artifact,
            "report_sha256": report["report_sha256"],
            "faults": {fid: fault_by_id[fid]["passed"] for fid in fault_ids},
            "requirements": {fid: fault_by_id[fid]["requirement"] for fid in fault_ids},
        }
        passed = all(fault_by_id[fid]["passed"] for fid in fault_ids)
        if epoch is not None:
            row = record_operational_drill(
                store, drill_type=drill_type, passed=passed, evidence=evidence
            )
        else:
            evidence["verification_only"] = True
            row = store.record_operational_drill(
                drill_type=drill_type,
                performed_at=datetime.now(timezone.utc).isoformat(),
                passed=passed,
                evidence_epoch=None,
                code_commit=report["code_commit"],
                evidence=evidence,
            )
        recorded.append({"drill_type": drill_type, "passed": passed, "drill_id": row.get("drill_id")})
    return recorded


def _write_report_atomically(output: Path, report: dict) -> None:
    """Create one complete report without exposing a partial JSON artifact."""
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(output)
    data = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output.parent,
        prefix=f".{output.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        # A same-filesystem hard link publishes the already-complete inode and
        # fails atomically if another process won the destination name. Unlike
        # os.replace(), it cannot overwrite an immutable report in the race
        # between an existence check and publication.
        os.link(temporary, output)
        temporary.unlink()
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the GR-3 fault-injection drill matrix.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the drill report JSON here (default: artifacts/fault-drill-<utc>.json).",
    )
    parser.add_argument(
        "--record-database",
        type=Path,
        help=(
            "Also record ambiguous_submission/restart_recovery/kill_switch drill rows "
            "in this database's operational_drill_runs table. Epoch-bound when an "
            "active paper evidence epoch exists; otherwise marked verification_only."
        ),
    )
    parser.add_argument(
        "--operator",
        help="Human operator name for recorded drill evidence (required with --record-database).",
    )
    args = parser.parse_args()
    if args.record_database is not None and not (args.operator or "").strip():
        raise SystemExit("--operator is required when recording drill evidence.")

    report = build_drill_report()

    output = args.output
    if output is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output = _REPOSITORY_ROOT / "artifacts" / f"fault-drill-{stamp}.json"
    try:
        _write_report_atomically(output, report)
    except FileExistsError:
        raise SystemExit(
            f"Refusing to overwrite an existing drill report: {output}"
        )
    report["artifact"] = str(output)

    if args.record_database is not None:
        report["recorded"] = record_drills(
            report, args.record_database, args.operator.strip(), str(output)
        )

    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
