"""Synthetic successor evidence only; executed audit and sources stay frozen."""
from copy import deepcopy
import hashlib
from pathlib import Path

import pytest

from research.target_price_revisions_qc import matched_audit as base, matched_audit_v2 as audit
from tests.target_price_revisions_qc.test_qc_matched_audit import fixture, change_log

ROOT = Path(__file__).resolve().parents[2]
V1_HASH = "8a1bd842777f698ee42f00494e6a9f1d95a8e497c0dcea3b09f8ccd3308fb795"


def successor_fixture(*args, **kwargs):
    return change_log(fixture(*args, **kwargs), "MATCHED_SUMMARY ",
        lambda row: row.update(warmup_finished_minute_validated=True, observed_action_custody_symbols=6))


def test_executed_v1_audit_remains_immutable_and_has_snapshot_sequence_binding():
    source = ROOT / "research/target_price_revisions_qc/matched_audit.py"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == V1_HASH
    assert "membership_snapshot_sequence_sha256" in source.read_text()


@pytest.mark.parametrize("arm,cost", [(arm, cost) for arm in ("tpr_on", "tpr_off", "etf_basket") for cost in ("baseline", "adverse")])
def test_successor_retains_all_base_metrics_and_adds_runtime_requirements(arm, cost):
    args = successor_fixture(arm, cost)
    original = base.audit_result(*args)
    result = audit.audit_result(*args)
    assert original["meaningful_execution"] is True and result["meaningful_execution"] is True
    assert result["base_audit_schema"] == "tpr-qc-matched-audit-v1"
    assert result["schema"] == "tpr-qc-matched-audit-v2"
    assert result["warmup_finished_minute_validated"] is True
    assert result["observed_action_custody_symbols"] == 6
    for key in original:
        if key != "schema":
            assert result[key] == original[key]


@pytest.mark.parametrize("value", [False, None, 1, "true"])
def test_missing_or_untyped_warmup_validation_cannot_claim_success(value):
    args = successor_fixture()
    assert audit.audit_result(*args)["meaningful_execution"] is True
    change_log(args, "MATCHED_SUMMARY ", lambda row: row.update(warmup_finished_minute_validated=value))
    assert base.audit_result(*args)["meaningful_execution"] is True
    result = audit.audit_result(*args)
    assert result["meaningful_execution"] is False
    assert result["diagnostic_reasons"] == ["warmup_minute_subscription_validation_missing"]


@pytest.mark.parametrize("value", [0, None, -1, True, "6", 1.5])
def test_positive_observed_custody_must_be_present_and_typed(value):
    args = successor_fixture()
    assert audit.audit_result(*args)["meaningful_execution"] is True
    change_log(args, "MATCHED_SUMMARY ", lambda row: row.update(observed_action_custody_symbols=value))
    assert base.audit_result(*args)["meaningful_execution"] is True
    result = audit.audit_result(*args)
    assert result["meaningful_execution"] is False
    assert result["diagnostic_reasons"] == ["observed_action_custody_missing"]
    assert result["observed_action_custody_symbols"] == (0 if value == 0 and type(value) is int else None)


def test_adapter_diagnostic_is_explicit_even_with_good_source_counts_orders():
    args = successor_fixture()
    assert audit.audit_result(*args)["meaningful_execution"] is True
    change_log(args, "MATCHED_SUMMARY ", lambda row: row.update(meaningful_execution=False))
    result = audit.audit_result(*args)
    assert result["meaningful_execution"] is False
    assert "adapter_reports_diagnostic" in result["diagnostic_reasons"]
    assert "successor_adapter_reports_diagnostic" in result["diagnostic_reasons"]


def test_new_metadata_cannot_override_zero_trade_or_missing_coverage():
    args = successor_fixture(empty=True)
    change_log(args, "MATCHED_SUMMARY ", lambda row: row.update(meaningful_execution=True))
    result = audit.audit_result(*args)
    assert result["warmup_finished_minute_validated"] is True
    assert result["observed_action_custody_symbols"] == 6
    assert result["meaningful_execution"] is False
    assert "zero_trade_diagnostic" in result["diagnostic_reasons"]


def test_missing_summary_retains_unknown_custody_count():
    args = successor_fixture()
    from tests.target_price_revisions_qc.test_qc_matched_audit import rebind
    args[1]["logs"] = [line for line in args[1]["logs"] if "MATCHED_SUMMARY " not in line]
    args[1]["length"] = len(args[1]["logs"])
    rebind(args)
    result = audit.audit_result(*args)
    assert result["meaningful_execution"] is False
    assert result["observed_action_custody_symbols"] is None
    assert "summary_missing" in result["diagnostic_reasons"]


def test_input_evidence_is_not_mutated():
    args = successor_fixture()
    before = deepcopy(args)
    audit.audit_result(*args)
    assert args == before
