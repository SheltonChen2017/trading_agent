"""Synthetic missing-decision labels; no private inputs or outcome access."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from research.target_price_revisions_qc import cap_tilt_diagnostic_v2 as d
from tests.target_price_revisions_qc.test_qc_cap_tilt_diagnostic import diagnostic_fixture
from tests.target_price_revisions_qc.test_qc_cap_tilt_audit import rebind, change_log

MISSING = "2025-01-13"


def partial_fixture(*, encoded=False, arm="tpr_on"):
    args = diagnostic_fixture(arm)
    args[1]["logs"] = [line for line in args[1]["logs"] if not (
        line.startswith("MATCHED_COVERAGE ") and json.loads(line.split(" ", 1)[1])["session"] == MISSING)]
    args[1]["length"] = len(args[1]["logs"])
    def update(summary):
        summary["refused_decisions"] = 1
        summary["reason_counts"]["missing_prior_cap_snapshot"] = 1
        summary["sleeve_selected_decisions"] = {etf: 13 for etf in d.cap.ETFS}
    change_log(args, "MATCHED_SUMMARY ", update)
    if encoded:
        args[1]["logs"] = [d.original.transport.encode_record(line.split(" ", 1)[0].removeprefix("MATCHED_"),
            json.loads(line.split(" ", 1)[1])) for line in args[1]["logs"]]
    return rebind(args)


@pytest.mark.parametrize("encoded", [False, True])
@pytest.mark.parametrize("arm", ["tpr_on", "tpr_off"])
def test_full_nav_metrics_remain_unchanged_and_partial_coverage_is_never_completed(encoded, arm):
    args = partial_fixture(encoded=encoded, arm=arm)
    before = deepcopy(args)
    base = d.original.diagnose_result(*args)
    result = d.diagnose_result(*args)
    assert args == before
    assert result["schema"] == "tpr-qc-cap-tilt-diagnostic-v2"
    assert result["metrics"] == base["metrics"] and result["orders"] == base["orders"]
    assert result["metrics"]["daily_return_observations"] == 60
    assert result["metrics"]["return_pct"] == "0.59"
    assert result["valuation_observations"] == 60 and result["decision_coverage_observations"] == 13
    assert result["observed_decision_dates"] == [day for day in d.cap.DECISIONS if day != MISSING]
    assert result["missing_frozen_decision_dates"] == [MISSING]
    assert result["complete_frozen_decision_coverage"] is False
    assert result["prior_mark_input_sequence_sha256"] is None
    assert d.cap._hash(result["observed_prior_mark_input_sequence_sha256"])
    decoded, _ = d.original._decoded_logs(args[1])
    _, _, rows = d.original.accounting._logs(decoded, [])
    expected_marks = d.cap._digest([(row["session"], row["prior_mark_session"], row["prior_mark_inputs_sha256"]) for row in rows])
    assert result["observed_prior_mark_input_sequence_sha256"] == expected_marks
    assert result["observed_coverage_sessions_sha256"] == d.cap._digest(result["observed_decision_dates"])
    assert result["observed_prior_mark_decision_count"] == 13
    assert result["original_summary_counts"]["decisions"] == 14
    assert result["original_summary_counts"]["refused_decisions"] == 1
    assert {"coverage_schedule_incomplete_or_wrong", "summary_execution_incomplete",
            "execution_input_or_order_failure"} <= set(result["diagnostic_reasons"])
    for etf in d.cap.ETFS:
        paths = result["observed_coverage_input_paths_by_sleeve"][etf]
        assert paths["observed_decision_count"] == 13
        assert result["coverage_by_sleeve"][etf]["selected_decisions"] == 13
        for path in d._PATHS:
            assert paths[path + "_sequence_sha256"] == result["coverage_by_sleeve"][etf][path + "_sequence_sha256"]
    for flag in ("meaningful_execution", "original_no_delisting_meaningful_execution", "development_execution_qualified",
                 "strategy_accepted", "canonical_admission", "matched_comparison_qualified", "delisting_observer_qualified"):
        assert result[flag] is False
    assert result["difference_metrics"] == {} and result["confirmatory_alpha"] == "0"
    assert result["evidence_hashes"] == args[3]["evidence_hashes"]


def test_complete_coverage_has_equal_complete_and_observed_hashes_but_false_gates():
    result = d.diagnose_result(*diagnostic_fixture())
    assert result["observed_decision_dates"] == list(d.cap.DECISIONS)
    assert result["missing_frozen_decision_dates"] == []
    assert result["complete_frozen_decision_coverage"] is True
    assert result["prior_mark_input_sequence_sha256"] == result["observed_prior_mark_input_sequence_sha256"]
    assert result["observed_prior_mark_decision_count"] == 14
    assert result["development_execution_qualified"] is False


@pytest.mark.parametrize("fault", ["empty", "outside", "foreign_type", "duplicate", "reordered", "prior_session", "hash"])
def test_observed_subset_refuses_ambiguous_unknown_or_foreign_inputs(fault):
    _, _, rows = d.original.accounting._logs(partial_fixture()[1], [])
    rows = deepcopy(rows)
    if fault == "empty":
        rows = []
    elif fault == "outside":
        rows[0]["session"] = "2025-01-03"
    elif fault == "foreign_type":
        rows[0]["session"] = True
    elif fault == "duplicate":
        rows.append(deepcopy(rows[0]))
    elif fault == "reordered":
        rows[0], rows[1] = rows[1], rows[0]
    elif fault == "prior_session":
        rows[0]["prior_mark_session"] = rows[0]["session"]
    else:
        rows[0]["prior_mark_inputs_sha256"] = "invalid"
    with pytest.raises(d.AuditError):
        d._observed_prior_mark_inputs(rows)


@pytest.mark.parametrize("fault", ["empty", "outside", "duplicate", "reordered", "prior_session", "hash"])
def test_public_reporter_refuses_invalid_coverage_without_reconstructing_it(fault):
    args = partial_fixture()
    positions = [i for i, line in enumerate(args[1]["logs"]) if line.startswith("MATCHED_COVERAGE ")]
    if fault == "empty":
        args[1]["logs"] = [line for line in args[1]["logs"] if not line.startswith("MATCHED_COVERAGE ")]
    elif fault == "outside":
        change_log(args, "MATCHED_COVERAGE ", lambda row: row.update(session="2025-01-03"))
    elif fault == "duplicate":
        args[1]["logs"].append(args[1]["logs"][positions[0]])
    elif fault == "reordered":
        args[1]["logs"][positions[0]], args[1]["logs"][positions[1]] = args[1]["logs"][positions[1]], args[1]["logs"][positions[0]]
    elif fault == "prior_session":
        change_log(args, "MATCHED_COVERAGE ", lambda row: row.update(prior_mark_session=row["session"]))
    else:
        change_log(args, "MATCHED_COVERAGE ", lambda row: row.update(prior_mark_inputs_sha256=None))
    args[1]["length"] = len(args[1]["logs"])
    rebind(args)
    before = deepcopy(args)
    with pytest.raises(d.AuditError):
        d.diagnose_result(*args)
    assert args == before


def test_source_binding_and_original_five_object_identity_precede_observed_metadata(monkeypatch):
    args = partial_fixture(encoded=True)
    before = deepcopy(args)
    events = []
    original_diagnose, observed = d.original.diagnose_result, d._observed_prior_mark_inputs
    def diagnose(*supplied):
        assert all(value is actual for value, actual in zip(supplied, args))
        events.append("source_bound_v1")
        return original_diagnose(*supplied)
    def metadata(rows):
        assert events == ["source_bound_v1"]
        events.append("observed_metadata")
        return observed(rows)
    monkeypatch.setattr(d.original, "diagnose_result", diagnose)
    monkeypatch.setattr(d, "_observed_prior_mark_inputs", metadata)
    assert d.diagnose_result(*args)["metrics"] is not None
    assert events == ["source_bound_v1", "observed_metadata"] and args == before


def test_changed_raw_evidence_is_not_saved_by_a_valid_partial_subset():
    args = partial_fixture()
    args[0]["backtest"]["status"] = "Completed"
    with pytest.raises(d.AuditError, match="mixed result"):
        d.diagnose_result(*args)


def test_old_reporter_and_auditor_bytes_remain_immutable_and_no_pair_api_exists():
    package = Path(d.original.__file__).parent
    assert hashlib.sha256((package / "cap_tilt_diagnostic.py").read_bytes()).hexdigest() == "a1a12f1163dccc85c927ca5e1d8fb5fa0f0cf79b12ccd6abeb94d4fb6e0a1633"
    assert hashlib.sha256((package / "cap_tilt_audit.py").read_bytes()).hexdigest() == "5f78a9af2d4bbe9da1939788ccd56a0c7a1804b511928ea577a646c0a0d07c5b"
    assert not hasattr(d, "analyze_pair") and not hasattr(d, "main")
