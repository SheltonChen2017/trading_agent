"""Synthetic unreported native monetary fields; no private data/cloud I/O."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from research.target_price_revisions_qc import cap_tilt_diagnostic_v3 as d
from tests.target_price_revisions_qc.test_qc_cap_tilt_diagnostic_v2 import partial_fixture, MISSING
from tests.target_price_revisions_qc.test_qc_cap_tilt_diagnostic import diagnostic_fixture
from tests.target_price_revisions_qc.test_qc_cap_tilt_audit import fixture, rebind, change_log

FALSE_GATES = ("meaningful_execution", "original_no_delisting_meaningful_execution", "development_execution_qualified",
    "strategy_accepted", "canonical_admission", "matched_comparison_qualified", "independent_sleeve_pnl_observed",
    "delisting_observer_qualified")


def unreported_fixture(*, encoded=False, arm="tpr_on"):
    args = partial_fixture(encoded=encoded, arm=arm)
    engine = args[2][0]["orders"][1]
    engine.update(priceCurrency="")
    event = engine["events"][0]
    event.pop("orderFeeAmount")
    event.pop("orderFeeCurrency")
    event["fillPriceCurrency"] = ""
    event["isAssignment"] = False
    return rebind(args)


@pytest.mark.parametrize("encoded", [False, True])
@pytest.mark.parametrize("arm", ["tpr_on", "tpr_off"])
def test_absent_native_fee_units_are_unknown_not_summary_or_headline_reconstruction(encoded, arm):
    args = unreported_fixture(encoded=encoded, arm=arm)
    before = deepcopy(args)
    with pytest.raises(d.AuditError):
        d.observed.diagnose_result(*args)
    result = d.diagnose_result(*args)
    assert args == before and result["schema"] == "tpr-qc-cap-tilt-diagnostic-v3"
    assert result["native_successfully_completed"] is True
    assert result["orders"]["orders"] == 2 and result["orders"]["fill_events"] == 2
    assert result["orders"]["filled_shares"] == "20"
    assert result["orders"]["fees"] is None and result["orders"]["fill_notional"] is None
    assert result["orders"]["observed_fees"] == "0.1"
    assert result["orders"]["api_unreported_fee_events"] == 1
    assert result["orders"]["native_fee_fields_missing_fill_events"] == 1
    assert result["orders"]["native_fee_complete"] is False
    assert result["orders"]["observed_usd_fill_notional"] == "1000"
    assert result["orders"]["native_fill_currency_unknown_fill_events"] == 1
    assert result["orders"]["native_usd_notional_complete"] is False
    engine = result["native_order_partition"]["engine_tagged_delisting_market"]
    assert engine["orders"] == 1 and engine["filled_shares"] == "10"
    assert engine["fees"] is None and engine["observed_fees"] == "0"
    assert engine["api_unreported_fee_events"] == 1
    assert engine["native_fill_currency_unknown_fill_events"] == 1
    assert engine["zero_fee_qcc_fill_events"] == 0 and engine["zero_fee_usd_fill_events"] == 0
    assert result["native_order_partition"]["engine_tag_is_not_independent_custody_proof"] is True
    assert result["original_summary_counts"]["submitted_orders"] == 1
    assert result["original_summary_counts"]["submitted_shares"] == 10
    assert result["original_summary_counts"]["fill_events"] == 2
    assert result["original_summary_counts"]["filled_shares"] == 20
    runtime = result["runtime_reported_accounting"]
    assert runtime["fees"] == "0.1" and runtime["max_cash_ledger_residual"] == "0"
    assert runtime["max_nav_ledger_residual"] == "0"
    assert runtime["attests_unreported_native_fee_or_currency"] is False
    provenance = result["native_fee_provenance"]
    assert provenance["api_unreported_fee_events"] == 1
    assert provenance["all_native_fee_total_known"] is False and provenance["all_native_fee_total"] is None
    assert provenance["api_reported_usd_fee_subtotal"] == "0.1"
    assert provenance["original_summary_fee_claim"] == "0.1"
    assert provenance["original_qc_statistic_fee_claim"] == "0.1"
    assert provenance["unreported_fee_zero_attested"] is False
    assert provenance["unreported_fee_currency_attested"] is False
    assert result["metrics"]["return_pct"] == "0.59"
    assert result["metrics"]["daily_return_observations"] == 60
    assert result["metrics"]["absolute_fill_notional_turnover_initial_nav"] is None
    assert result["metrics"]["observed_usd_fill_notional_turnover_initial_nav"] == "0.01"
    assert result["valuation_observations"] == 60 and result["decision_coverage_observations"] == 13
    assert result["missing_frozen_decision_dates"] == [MISSING]
    assert result["observed_decision_dates"] == [day for day in d.cap.DECISIONS if day != MISSING]
    assert result["prior_mark_input_sequence_sha256"] is None
    assert result["observed_prior_mark_decision_count"] == 13
    for etf in d.cap.ETFS:
        assert result["observed_coverage_input_paths_by_sleeve"][etf]["observed_decision_count"] == 13
    assert all(result[flag] is False for flag in FALSE_GATES)
    assert result["difference_metrics"] == {} and result["confirmatory_alpha"] == "0"
    assert result["evidence_hashes"] == args[3]["evidence_hashes"]
    decoded, _ = d.original._decoded_logs(args[1])
    summary, _, _ = d.accounting._logs(decoded, [])
    assert result["original_summary_sha256"] == d._digest(summary)
    assert "SYNTHETIC_PRIVATE_TICKER" not in json.dumps(result)


@pytest.mark.parametrize("encoded", [False, True])
@pytest.mark.parametrize("arm", ["tpr_on", "tpr_off"])
def test_known_native_values_keep_original_metrics_calendar_and_observed_paths(encoded, arm):
    args = partial_fixture(encoded=encoded, arm=arm)
    base = d.observed.diagnose_result(*args)
    result = d.diagnose_result(*args)
    for key in base["metrics"]:
        assert result["metrics"][key] == base["metrics"][key]
    for key in ("original_summary_counts", "original_summary_sha256", "coverage_by_sleeve", "source_hashes",
        "evidence_hashes", "valuation_sessions_sha256", "observed_decision_dates", "missing_frozen_decision_dates",
        "observed_prior_mark_input_sequence_sha256", "observed_coverage_input_paths_by_sleeve"):
        assert result[key] == base[key]
    for key in base["orders"]:
        assert result["orders"][key] == base["orders"][key]
    assert result["orders"]["fees"] == "0.1" and result["orders"]["native_fee_complete"] is True
    assert result["orders"]["api_unreported_fee_events"] == 0
    assert result["orders"]["fill_notional"] == "2000"
    assert all(result[flag] is False for flag in FALSE_GATES)


def test_complete_coverage_keeps_complete_and_observed_mark_paths_equal():
    result = d.diagnose_result(*diagnostic_fixture())
    assert result["observed_decision_dates"] == list(d.cap.DECISIONS)
    assert result["missing_frozen_decision_dates"] == []
    assert result["prior_mark_input_sequence_sha256"] == result["observed_prior_mark_input_sequence_sha256"]
    assert result["observed_prior_mark_decision_count"] == 14
    assert result["metrics"]["daily_return_observations"] == 60
    assert all(result[flag] is False for flag in FALSE_GATES)


def test_original_five_objects_source_binding_precedes_decode_inventory_and_original_nav(monkeypatch):
    args = unreported_fixture(encoded=True)
    before = deepcopy(args)
    events = []
    source, decode, parse, orders, nav = d.cap._source, d.original._decoded_logs, d.accounting._logs, d.native_orders.orders, d.accounting._nav
    parsed_summary = []
    def bound(receipt, config, config_hash, result, logs, pages, reasons):
        assert all(left is right for left, right in zip((result, logs, pages, receipt, config), args))
        events.append("source")
        return source(receipt, config, config_hash, result, logs, pages, reasons)
    def decoded(logs):
        assert events == ["source"] and logs is args[1]
        events.append("decode")
        return decode(logs)
    def parsed(logs, reasons):
        assert events == ["source", "decode"] and logs is not args[1]
        result = parse(logs, reasons)
        parsed_summary.append(result[0])
        events.append("parse")
        return result
    def counted(pages, receipt, summary, stats, config, reasons):
        assert events == ["source", "decode", "parse"]
        assert pages is args[2] and receipt is args[3] and config is args[4]
        assert summary is parsed_summary[0]
        events.append("inventory")
        return orders(pages, receipt, summary, stats, config, reasons)
    def valued(rows, summary, stats, reasons):
        assert events == ["source", "decode", "parse", "inventory"] and summary is parsed_summary[0]
        events.append("nav")
        return nav(rows, summary, stats, reasons)
    monkeypatch.setattr(d.cap, "_source", bound)
    monkeypatch.setattr(d.original, "_decoded_logs", decoded)
    monkeypatch.setattr(d.accounting, "_logs", parsed)
    monkeypatch.setattr(d.native_orders, "orders", counted)
    monkeypatch.setattr(d.accounting, "_nav", valued)
    monkeypatch.setattr(d.original, "diagnose_result", lambda *unused: pytest.fail("catch-repair reporter called"))
    monkeypatch.setattr(d.original, "_partition", lambda *unused: pytest.fail("strict legacy partition called"))
    result = d.diagnose_result(*args)
    assert events == ["source", "decode", "parse", "inventory", "nav"] and args == before
    assert result["orders"]["fees"] is None and result["metrics"] is not None


@pytest.mark.parametrize("object_index", [0, 1, 2])
def test_original_evidence_changes_refuse_before_decode_or_native_inventory(object_index, monkeypatch):
    args = unreported_fixture(encoded=True)
    if object_index == 0:
        args[0]["backtest"]["status"] = "Completed"
    elif object_index == 1:
        args[1]["logs"].append("synthetic changed original wire")
    else:
        args[2][0]["orders"][1]["quantity"] = -11
    monkeypatch.setattr(d.original, "_decoded_logs", lambda *unused: pytest.fail("decode before hash binding"))
    monkeypatch.setattr(d.native_orders, "orders", lambda *unused: pytest.fail("inventory before hash binding"))
    with pytest.raises(d.AuditError, match="mixed result"):
        d.diagnose_result(*args)


@pytest.mark.parametrize("field", ["evidence_hashes", "source_hashes", "exact_cloud_readback", "build_success", "compile_id"])
def test_missing_source_or_evidence_proof_refuses_without_reporter_repair(field):
    args = unreported_fixture()
    args[3].pop(field)
    before = deepcopy(args)
    with pytest.raises(d.AuditError, match="source and evidence"):
        d.diagnose_result(*args)
    assert args == before


@pytest.mark.parametrize("field,value", [("projectId", True), ("projectId", 987), ("backtestId", "foreign")])
def test_unknown_or_foreign_native_identity_refuses(field, value):
    args = unreported_fixture()
    args[0]["backtest"][field] = value
    rebind(args)
    with pytest.raises(d.AuditError, match="foreign"):
        d.diagnose_result(*args)


@pytest.mark.parametrize("change", [{"status": "Runtime Error"}, {"status": "Completed.extra"}, {"completed": False},
    {"error": "SYNTHETIC_PRIVATE_ERROR"}, {"error": False}, {"progress": "0.99"}, {"error": "missing"}])
def test_unknown_terminal_state_never_yields_completed_metrics(change):
    args = unreported_fixture()
    if change == {"error": "missing"}:
        args[0]["backtest"].pop("error")
    else:
        args[0]["backtest"].update(change)
    rebind(args)
    result = d.diagnose_result(*args)
    assert result["native_successfully_completed"] is False and result["metrics"] is None
    assert all(result[flag] is False for flag in FALSE_GATES)
    assert "SYNTHETIC_PRIVATE_ERROR" not in json.dumps(result)


@pytest.mark.parametrize("field,value", [("filled_shares", -1), ("fees", "NaN"),
    ("native_final_delisting_compatibility_exceptions", True), ("max_cash_ledger_residual", "-0.01"),
    ("meaningful_execution", 0), ("canonical_admission", True), ("config_sha256", "b" * 64)])
def test_original_summary_invalid_types_identity_or_authority_still_refuse(field, value):
    args = unreported_fixture()
    change_log(args, "MATCHED_SUMMARY ", lambda row: row.update({field: value}))
    with pytest.raises(d.AuditError):
        d.diagnose_result(*args)


@pytest.mark.parametrize("field", ["fees", "max_cash_ledger_residual", "max_nav_ledger_residual", "filled_shares"])
def test_missing_original_runtime_accounting_is_not_invented(field):
    args = unreported_fixture()
    change_log(args, "MATCHED_SUMMARY ", lambda row: row.pop(field))
    with pytest.raises(d.AuditError, match="complete original"):
        d.diagnose_result(*args)


@pytest.mark.parametrize("fault", ["empty", "duplicate", "reorder", "outside", "prior", "hash"])
def test_observed_subset_invalid_or_missing_rows_are_never_reconstructed(fault):
    args = unreported_fixture()
    positions = [i for i, line in enumerate(args[1]["logs"]) if line.startswith("MATCHED_COVERAGE ")]
    if fault == "empty":
        args[1]["logs"] = [line for line in args[1]["logs"] if not line.startswith("MATCHED_COVERAGE ")]
    elif fault == "duplicate":
        args[1]["logs"].append(args[1]["logs"][positions[0]])
    elif fault == "reorder":
        args[1]["logs"][positions[0]], args[1]["logs"][positions[1]] = args[1]["logs"][positions[1]], args[1]["logs"][positions[0]]
    else:
        update = {"outside": {"session": "2025-01-03"}, "prior": {"prior_mark_session": "2025-01-02"},
            "hash": {"prior_mark_inputs_sha256": None}}[fault]
        change_log(args, "MATCHED_COVERAGE ", lambda row: row.update(update))
    args[1]["length"] = len(args[1]["logs"])
    rebind(args)
    before = deepcopy(args)
    with pytest.raises(d.AuditError):
        d.diagnose_result(*args)
    assert args == before


@pytest.mark.parametrize("fault", ["count", "session", "residual"])
def test_full_sixty_nav_calendar_and_original_residuals_remain_mandatory(fault):
    args = unreported_fixture()
    if fault == "count":
        position = next(i for i, line in enumerate(args[1]["logs"]) if line.startswith("MATCHED_NAV "))
        args[1]["logs"].pop(position)
        args[1]["length"] -= 1
    elif fault == "session":
        change_log(args, "MATCHED_NAV ", lambda row: row.update(session="2025-01-01"))
    else:
        change_log(args, "MATCHED_SUMMARY ", lambda row: row.update(max_nav_ledger_residual="0.02"))
    rebind(args)
    result = d.diagnose_result(*args)
    if fault == "residual":
        assert "daily_and_summary_accounting_mismatch" in result["diagnostic_reasons"]
    else:
        assert result["metrics"] is None
    assert all(result[flag] is False for flag in FALSE_GATES)


def test_even_true_runtime_claims_do_not_turn_any_reporter_gate_true():
    args = fixture()
    args[2][0]["orders"][0]["tag"] = "TPRM:" + "a" * 20
    change_log(args, "MATCHED_SUMMARY ", lambda row: row.update(native_final_delisting_compatibility_exceptions=0))
    result = d.diagnose_result(*args)
    assert result["runtime_reported_execution_flags"]["development_execution_qualified"] is True
    assert result["delisting_observer_ambient_check"] is True
    assert all(result[flag] is False for flag in FALSE_GATES)


@pytest.mark.parametrize("claim", ["runtime", "headline"])
def test_disagreeing_fee_claims_remain_claims_not_missing_native_fee_values(claim):
    args = unreported_fixture()
    if claim == "runtime":
        change_log(args, "MATCHED_SUMMARY ", lambda row: row.update(fees="7.25"))
    else:
        args[0]["backtest"]["statistics"]["Total Fees"] = "$7.25"
        rebind(args)
    result = d.diagnose_result(*args)
    assert result["orders"]["fees"] is None and result["orders"]["observed_fees"] == "0.1"
    assert result["native_fee_provenance"]["all_native_fee_total"] is None
    key = "original_summary_fee_claim" if claim == "runtime" else "original_qc_statistic_fee_claim"
    assert result["native_fee_provenance"][key] == "7.25"
    reason = "known_strategy_fees_and_summary_mismatch_or_unknown" if claim == "runtime" else "known_strategy_fees_and_statistic_mismatch_or_unknown"
    assert reason in result["diagnostic_reasons"]
    assert result["metrics"]["daily_return_observations"] == 60
    assert all(result[flag] is False for flag in FALSE_GATES)


def test_reporter_calls_do_not_mutate_reused_auditor_or_reporter_globals():
    modules = (d.cap, d.accounting, d.original, d.observed)
    before = [{key: value for key, value in vars(module).items() if not key.startswith("__")} for module in modules]
    d.diagnose_result(*unreported_fixture(encoded=True))
    after = [{key: value for key, value in vars(module).items() if not key.startswith("__")} for module in modules]
    assert after == before


def test_old_reporters_auditor_and_bound_inputs_are_not_edited_or_monkeypatched():
    package = Path(d.__file__).parent
    for name, expected in (("cap_tilt_diagnostic.py", "a1a12f1163dccc85c927ca5e1d8fb5fa0f0cf79b12ccd6abeb94d4fb6e0a1633"),
        ("cap_tilt_diagnostic_v2.py", "b185a01531fbdb8526d25ef98e053d2d88912da69a12a94885c1662145255a40"),
        ("cap_tilt_audit.py", "5f78a9af2d4bbe9da1939788ccd56a0c7a1804b511928ea577a646c0a0d07c5b")):
        assert hashlib.sha256((package / name).read_bytes()).hexdigest() == expected
    assert not hasattr(d, "main") and not hasattr(d, "analyze_pair")
