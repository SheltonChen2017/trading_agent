"""Synthetic terminal parser proofs only; no retained rows or cloud operations."""
from copy import deepcopy
import hashlib
from pathlib import Path

import pytest

from research.target_price_revisions_qc import matched_audit as base, matched_audit_v2 as previous, matched_audit_v3 as audit
from tests.target_price_revisions_qc.test_qc_matched_audit import change_log, rebind
from tests.target_price_revisions_qc.test_qc_matched_audit_v2 import successor_fixture

ROOT = Path(__file__).resolve().parents[2]
TERMINAL_REASON = "backtest_not_successfully_completed"


def terminal_fixture(arm="tpr_on", cost="baseline", **kwargs):
    args = successor_fixture(arm, cost, **kwargs)
    args[0]["backtest"]["status"] = "Completed."
    return rebind(args)


@pytest.mark.parametrize("arm,cost", [(arm, cost) for arm in ("tpr_on", "tpr_off", "etf_basket") for cost in ("baseline", "adverse")])
def test_concrete_completed_dot_correction_retains_all_original_evidence(arm, cost):
    args = terminal_fixture(arm, cost)
    before = deepcopy(args)
    original = previous.audit_result(*args)
    assert original["meaningful_execution"] is False
    assert original["diagnostic_reasons"] == [TERMINAL_REASON]
    result = audit.audit_result(*args)
    assert result["meaningful_execution"] is True
    assert result["diagnostic_reasons"] == []
    assert result["terminal_status"] == "Completed."
    assert result["schema"] == "tpr-qc-matched-audit-v3"
    assert result["previous_audit_schema"] == "tpr-qc-matched-audit-v2"
    assert result["base_audit_schema"] == "tpr-qc-matched-audit-v1"
    assert result["canonical_admission"] is False
    assert result["independent_sleeve_pnl_observed"] is False
    for key in original:
        if key not in ("schema", "meaningful_execution", "diagnostic_reasons"):
            assert result[key] == original[key]
    assert args == before


@pytest.mark.parametrize("status", ["Completed", "completed", "completed.", "Completed..", "Completed. ", " Completed.", "COMPLETED.", "Completed. Runtime Error", "CompletedDiagnostic", "Runtime Error", None])
def test_only_concrete_completed_dot_extends_existing_terminal_spellings(status):
    args = terminal_fixture()
    args[0]["backtest"]["status"] = status
    rebind(args)
    original = previous.audit_result(*args)
    result = audit.audit_result(*args)
    assert result["meaningful_execution"] == original["meaningful_execution"]
    assert result["diagnostic_reasons"] == original["diagnostic_reasons"]
    assert result["terminal_status"] == status


@pytest.mark.parametrize("key,value", [("completed", False), ("completed", None), ("completed", 1), ("completed", "true"), ("progress", 0), ("progress", "0.999"), ("progress", 2), ("error", ""), ("error", False), ("error", 0), ("error", "runtime failure")])
def test_completed_dot_keeps_all_original_completion_guards(key, value):
    args = terminal_fixture()
    args[0]["backtest"][key] = value
    rebind(args)
    result = audit.audit_result(*args)
    assert result["meaningful_execution"] is False
    assert TERMINAL_REASON in result["diagnostic_reasons"]


@pytest.mark.parametrize("field,value,reason", [("warmup_finished_minute_validated", False, "warmup_minute_subscription_validation_missing"), ("observed_action_custody_symbols", 0, "observed_action_custody_missing"), ("meaningful_execution", False, "adapter_reports_diagnostic"), ("reason_counts", {"delisting_event": 4}, "execution_input_or_order_failure")])
def test_correct_terminal_status_never_erases_other_runtime_diagnostics(field, value, reason):
    args = terminal_fixture()
    change_log(args, "MATCHED_SUMMARY ", lambda row: row.update({field: value}))
    original = previous.audit_result(*args)
    result = audit.audit_result(*args)
    assert reason in result["diagnostic_reasons"]
    assert result["meaningful_execution"] is False
    assert result["diagnostic_reasons"] == sorted(set(original["diagnostic_reasons"]) - {TERMINAL_REASON})


def test_delisting_and_adapter_false_remain_open_together_with_valid_counts():
    args = terminal_fixture()
    change_log(args, "MATCHED_SUMMARY ", lambda row: row.update(meaningful_execution=False, reason_counts={"delisting_event": 4}))
    result = audit.audit_result(*args)
    assert result["orders"]["filled_orders"] > 0
    assert result["decision_coverage_observations"] == 14
    assert result["valuation_observations"] == 60
    assert result["diagnostic_reasons"] == ["adapter_reports_diagnostic", "execution_input_or_order_failure", "successor_adapter_reports_diagnostic"]
    assert result["meaningful_execution"] is False


def test_zero_trade_completed_dot_is_still_diagnostic():
    args = terminal_fixture(empty=True)
    change_log(args, "MATCHED_SUMMARY ", lambda row: row.update(meaningful_execution=True))
    result = audit.audit_result(*args)
    assert result["meaningful_execution"] is False
    assert "zero_trade_diagnostic" in result["diagnostic_reasons"]


@pytest.mark.parametrize("key,value", [("build_success", False), ("exact_cloud_readback", False), ("source_hashes", {})])
def test_completed_dot_does_not_override_missing_source_verification(key, value):
    args = terminal_fixture()
    args[3][key] = value
    result = audit.audit_result(*args)
    assert result["meaningful_execution"] is False
    assert "source_verification_missing" in result["diagnostic_reasons"]


def test_original_status_bytes_must_match_original_result_evidence_hash():
    args = successor_fixture()
    args[0]["backtest"]["status"] = "Completed."
    with pytest.raises(base.AuditError, match="mixed result log or order evidence"):
        audit.audit_result(*args)


@pytest.mark.parametrize("progress", [True, False, "NaN", "Infinity", None])
def test_malformed_progress_keeps_original_refusal(progress):
    args = terminal_fixture()
    args[0]["backtest"]["progress"] = progress
    rebind(args)
    with pytest.raises(base.AuditError):
        previous.audit_result(*args)
    with pytest.raises(base.AuditError):
        audit.audit_result(*args)


def test_failed_result_response_cannot_be_recovered_by_status_only():
    args = terminal_fixture()
    args[0]["success"] = False
    rebind(args)
    result = audit.audit_result(*args)
    assert result["meaningful_execution"] is False
    assert "backtest_response_unavailable" in result["diagnostic_reasons"]


def test_status_correction_preserves_missing_coverage_diagnostic():
    args = terminal_fixture()
    args[1]["logs"] = [line for line in args[1]["logs"] if "MATCHED_COVERAGE " not in line]
    args[1]["length"] = len(args[1]["logs"])
    rebind(args)
    original = previous.audit_result(*args)
    result = audit.audit_result(*args)
    assert result["meaningful_execution"] is False
    assert result["diagnostic_reasons"] == sorted(set(original["diagnostic_reasons"]) - {TERMINAL_REASON})
    assert "coverage_schedule_incomplete_or_wrong" in result["diagnostic_reasons"]


@pytest.mark.parametrize("scope,key,value", [("result", "backtestId", "f" * 32), ("result", "projectId", 999), ("source", "config_sha256", "f" * 64), ("source", "packet_sha256", "f" * 64)])
def test_original_identity_mismatches_still_refuse(scope, key, value):
    args = terminal_fixture()
    (args[0]["backtest"] if scope == "result" else args[3])[key] = value
    rebind(args)
    with pytest.raises(base.AuditError):
        audit.audit_result(*args)


def test_previous_audit_receives_identical_input_objects_without_rebinding(monkeypatch):
    args = terminal_fixture()
    before = deepcopy(args)
    original = previous.audit_result
    observed = []

    def spy(*received):
        assert all(got is expected for got, expected in zip(received, args))
        assert list(received) == before
        observed.append(True)
        return original(*received)

    monkeypatch.setattr(previous, "audit_result", spy)
    assert audit.audit_result(*args)["meaningful_execution"] is True
    assert observed == [True]
    assert args == before


def test_pure_successor_needs_no_file_io(monkeypatch):
    args = terminal_fixture()

    def refuse_io(*args, **kwargs):
        raise AssertionError("audit attempted file I/O")

    monkeypatch.setattr("builtins.open", refuse_io)
    monkeypatch.setattr(Path, "open", refuse_io)
    assert audit.audit_result(*args)["meaningful_execution"] is True


def test_executed_auditors_remain_byte_identical():
    expected = {"matched_audit.py": "8a1bd842777f698ee42f00494e6a9f1d95a8e497c0dcea3b09f8ccd3308fb795", "matched_audit_v2.py": "81d8b5f8f6ae6f03b89f7a61731d52aa9690d5a23c7efa6f8a41ee9b86d98a77"}
    for name, digest in expected.items():
        assert hashlib.sha256((ROOT / "research/target_price_revisions_qc" / name).read_bytes()).hexdigest() == digest
