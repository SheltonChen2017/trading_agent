"""Synthetic intact-evidence diagnostics; no private inputs or cloud I/O."""
from copy import deepcopy
from datetime import datetime
import json

import pytest

from research.target_price_revisions_qc import cap_tilt_diagnostic as d
from tests.target_price_revisions_qc.test_qc_cap_tilt_audit import fixture, change_log, rebind, observation


def diagnostic_fixture(arm="tpr_on"):
    args = fixture(arm)
    strategy = args[2][0]["orders"][0]
    strategy["tag"] = "TPRM:" + "a" * 20
    stamp = datetime(2025, 3, 7, 16, tzinfo=d.cap.NY)
    engine = {"id": 2, "status": 3, "type": 0, "priceAdjustmentMode": 0, "priceCurrency": "USD",
        "quantity": -10, "tag": "Liquidate from delisting", "createdTime": stamp.isoformat(),
        "events": [{"orderId": 2, "orderEventId": 2, "status": "filled", "fillQuantity": -10,
            "fillPrice": "100", "fillPriceCurrency": "USD", "orderFeeAmount": "0",
            "orderFeeCurrency": "QCC", "time": int(stamp.timestamp())}]}
    args[2][0].update(length=2, orders=[strategy, engine])
    args[0]["backtest"]["statistics"]["Total Orders"] = "2"
    def update(summary):
        summary.update(fill_events=2, filled_shares=20, meaningful_execution=False,
            original_no_delisting_meaningful_execution=False, development_execution_qualified=False,
            native_final_delisting_compatibility_exceptions=1)
        summary["reason_counts"] = {"delisting_event": 1}
        summary["delisting_audit"] = d.cap.observer.record_event(d.cap.observer.empty_audit(),
            observation(type="final", held_before=True, held_after=False, ever_filled=True,
                        ever_ordered=True, native_ticket=True))
    change_log(args, "MATCHED_SUMMARY ", update)
    return rebind(args)


@pytest.mark.parametrize("arm", ["tpr_on", "tpr_off"])
def test_native_extra_market_fill_reports_metrics_without_relaxing_any_gate(arm):
    args = diagnostic_fixture(arm)
    before = deepcopy(args)
    with pytest.raises(d.AuditError, match="share accounting order"):
        d.cap.audit_result(*args)
    result = d.diagnose_result(*args)
    assert args == before
    assert result["native_successfully_completed"] is True
    assert result["classification"] == "unqualified_exploratory_diagnostic"
    assert result["original_summary_counts"]["requested_shares"] == 12
    assert result["original_summary_counts"]["submitted_shares"] == 10
    assert result["original_summary_counts"]["filled_shares"] == 20
    assert result["native_order_partition"]["strategy_tagged_moo"]["filled_shares"] == "10"
    assert result["native_order_partition"]["engine_tagged_delisting_market"]["filled_shares"] == "10"
    assert result["native_order_partition"]["engine_tagged_delisting_market"]["fees"] == "0"
    assert result["native_order_partition"]["engine_tagged_delisting_market"]["zero_fee_qcc_fill_events"] == 1
    assert result["native_order_partition"]["engine_tagged_delisting_market"]["zero_fee_usd_fill_events"] == 0
    assert result["metrics"]["return_pct"] == "0.59"
    assert result["metrics"]["risk_free_daily"] == "0"
    assert result["valuation_observations"] == 60 and result["decision_coverage_observations"] == 14
    assert {"non_moo_raw_usd_order", "native_fee_schedule_mismatch", "non_usd_native_fill",
        "order_clock_outside_frozen_schedule", "fill_clock_outside_frozen_schedule",
        "original_strict_summary_share_ordering_refused", "delisting_observation_unknown_or_nonambient"} <= set(result["diagnostic_reasons"])
    for flag in ("meaningful_execution", "original_no_delisting_meaningful_execution", "development_execution_qualified",
                 "strategy_accepted", "canonical_admission", "matched_comparison_qualified", "independent_sleeve_pnl_observed"):
        assert result[flag] is False
    assert result["difference_metrics"] == {} and result["confirmatory_alpha"] == "0"
    assert result["evidence_hashes"] == args[3]["evidence_hashes"]
    assert result["original_summary_sha256"] == d._digest(d.accounting._logs(args[1], [])[0])
    assert "SYNTHETIC_PRIVATE_TICKER" not in json.dumps(result)


@pytest.mark.parametrize("field,value", [("canonical_admission", True), ("canonical_admission", 0),
    ("independent_sleeve_pnl_observed", True), ("meaningful_execution", 0),
    ("original_no_delisting_meaningful_execution", True), ("native_final_delisting_compatibility_exceptions", True),
    ("native_final_delisting_compatibility_exceptions", -1), ("filled_shares", -1),
    ("max_cash_ledger_residual", "-0.01"), ("max_nav_ledger_residual", "NaN"), ("fees", "-1"),
    ("candidate_id", "foreign"), ("config_sha256", "b" * 64)])
def test_original_summary_identity_types_authority_and_accounting_still_refuse(field, value):
    args = diagnostic_fixture()
    change_log(args, "MATCHED_SUMMARY ", lambda row: row.update({field: value}))
    with pytest.raises(d.AuditError):
        d.diagnose_result(*args)


@pytest.mark.parametrize("field", ["max_cash_ledger_residual", "max_nav_ledger_residual",
    "native_final_delisting_compatibility_exceptions", "development_execution_qualified", "filled_shares"])
def test_missing_original_summary_inputs_are_not_invented(field):
    args = diagnostic_fixture()
    change_log(args, "MATCHED_SUMMARY ", lambda row: row.pop(field))
    with pytest.raises(d.AuditError, match="complete original"):
        d.diagnose_result(*args)


@pytest.mark.parametrize("object_index", [0, 1, 2])
def test_hash_binding_refuses_changed_original_evidence(object_index):
    args = diagnostic_fixture()
    if object_index == 0:
        args[0]["backtest"]["status"] = "Completed"
    elif object_index == 1:
        args[1]["logs"].append("synthetic extra original line")
    else:
        args[2][0]["orders"][1]["tag"] = "foreign"
    with pytest.raises(d.AuditError, match="mixed result"):
        d.diagnose_result(*args)


@pytest.mark.parametrize("field", ["evidence_hashes", "source_hashes", "exact_cloud_readback", "build_success", "compile_id"])
def test_missing_source_or_evidence_proof_cannot_emit_metrics(field):
    args = diagnostic_fixture()
    args[3].pop(field)
    with pytest.raises(d.AuditError, match="source and evidence"):
        d.diagnose_result(*args)


@pytest.mark.parametrize("field,value", [("backtestId", "foreign"), ("projectId", 987)])
def test_foreign_native_result_is_not_a_diagnostic_for_this_run(field, value):
    args = diagnostic_fixture()
    args[0]["backtest"][field] = value
    rebind(args)
    with pytest.raises(d.AuditError, match="foreign"):
        d.diagnose_result(*args)


@pytest.mark.parametrize("update", [{"completed": False}, {"progress": "0.99"}, {"error": "SYNTHETIC_PRIVATE_ERROR"},
    {"status": "Completed.extra"}, {"status": "Runtime Error"}])
def test_unsuccessful_status_never_reports_completed_metrics_or_acceptance(update):
    args = diagnostic_fixture()
    args[0]["backtest"].update(update)
    rebind(args)
    result = d.diagnose_result(*args)
    assert result["native_successfully_completed"] is False and result["metrics"] is None
    assert result["development_execution_qualified"] is False
    assert "backtest_not_successfully_completed" in result["diagnostic_reasons"]
    assert "SYNTHETIC_PRIVATE_ERROR" not in json.dumps(result)


@pytest.mark.parametrize("group,field,value,reason", [
    ("summary", "submitted_orders", 2, "strategy_tagged_moo_summary_mismatch"),
    ("summary", "fill_events", 1, "all_native_fill_summary_mismatch"),
    ("summary", "filled_shares", 19, "all_native_fill_summary_mismatch"),
    ("summary", "fees", "0", "all_native_fill_summary_mismatch"),
    ("summary", "native_final_delisting_compatibility_exceptions", 0, "native_final_compatibility_count_mismatch"),
    ("order", "tag", "prefix Liquidate from delisting", "unclassified_native_orders"),
    ("order", "type", 4, "unclassified_native_orders"),
    ("order", "type", False, "unclassified_native_orders"),
    ("order", "priceAdjustmentMode", 1, "unclassified_native_orders"),
    ("order", "priceAdjustmentMode", False, "unclassified_native_orders"),
    ("fill", "orderFeeAmount", "0.10", "engine_tagged_market_economics_not_final_zero_fee_close")])
def test_native_partition_mismatches_remain_visible_not_corrected(group, field, value, reason):
    args = diagnostic_fixture()
    if group == "summary":
        change_log(args, "MATCHED_SUMMARY ", lambda row: row.update({field: value}))
    elif group == "order":
        args[2][0]["orders"][1][field] = value
    else:
        args[2][0]["orders"][1]["events"][0][field] = value
    rebind(args)
    result = d.diagnose_result(*args)
    assert reason in result["diagnostic_reasons"]
    assert result["development_execution_qualified"] is False


@pytest.mark.parametrize("fault,reason", [("summary", "daily_and_summary_accounting_mismatch"),
    ("daily", "daily_accounting_failure"), ("risk", "daily_unlevered_risk_failure"),
    ("nav_count", "valuation_schedule_incomplete_or_wrong"), ("coverage", "coverage_schedule_incomplete_or_wrong")])
def test_nav_residual_schedule_risk_and_coverage_proofs_are_not_dropped(fault, reason):
    args = diagnostic_fixture()
    if fault == "summary":
        change_log(args, "MATCHED_SUMMARY ", lambda row: row.update(max_cash_ledger_residual="0.02"))
    elif fault == "daily":
        change_log(args, "MATCHED_NAV ", lambda row: row.update(cash_ledger_residual="0.02"))
    elif fault == "risk":
        change_log(args, "MATCHED_NAV ", lambda row: row.update(risk_within_unlevered_account=False))
    else:
        prefix = "MATCHED_NAV " if fault == "nav_count" else "MATCHED_COVERAGE "
        index = next(i for i, line in enumerate(args[1]["logs"]) if prefix in line)
        args[1]["logs"].pop(index)
        args[1]["length"] -= 1
    rebind(args)
    result = d.diagnose_result(*args)
    assert reason in result["diagnostic_reasons"]
    assert result["matched_comparison_qualified"] is False
    assert result["difference_metrics"] == {}
    if fault == "nav_count":
        assert result["metrics"] is None


def test_diagnostic_has_no_cli_or_io_and_does_not_mutate_accounting_globals(monkeypatch):
    import importlib
    original = {name: value for name, value in vars(d.accounting).items() if not name.startswith("__")}
    monkeypatch.setattr(d.cap, "_summary", lambda *args: pytest.fail("strict summary called with altered counters"))
    args = diagnostic_fixture()
    result = d.diagnose_result(*args)
    assert result["metrics"] is not None
    importlib.reload(d)
    assert {name: value for name, value in vars(d.accounting).items() if not name.startswith("__")} == original
    assert not hasattr(d, "main") and not hasattr(d, "analyze_pair")


def test_native_boolean_project_identity_is_not_an_exact_integer_identity():
    args = diagnostic_fixture()
    args[0]["backtest"]["projectId"] = True
    args[3]["project_id"] = 1
    rebind(args)
    with pytest.raises(d.AuditError, match="project identity"):
        d.diagnose_result(*args)


def test_even_an_ambient_runtime_claim_never_turns_a_diagnostic_gate_true():
    args = fixture()
    args[2][0]["orders"][0]["tag"] = "TPRM:" + "a" * 20
    change_log(args, "MATCHED_SUMMARY ", lambda row: row.update(native_final_delisting_compatibility_exceptions=0))
    result = d.diagnose_result(*args)
    assert result["runtime_reported_execution_flags"]["meaningful_execution"] is True
    assert result["runtime_reported_execution_flags"]["development_execution_qualified"] is True
    assert result["delisting_observer_qualified"] is False
    assert result["delisting_observer_ambient_check"] is True
    assert result["development_execution_qualified"] is False
    assert result["original_no_delisting_meaningful_execution"] is False
    assert result["strategy_accepted"] is False and result["matched_comparison_qualified"] is False


def test_missing_native_error_field_is_unknown_not_known_none():
    args = diagnostic_fixture()
    args[0]["backtest"].pop("error")
    rebind(args)
    result = d.diagnose_result(*args)
    assert result["native_error_field_present"] is False and result["native_error_is_none"] is False
    assert result["native_successfully_completed"] is False and result["metrics"] is None


def test_order_tally_omits_only_the_legacy_summary_comparison_nav_keeps_original(monkeypatch):
    args = diagnostic_fixture()
    summary, nav_rows, coverage_rows = d.accounting._logs(args[1], [])
    before = deepcopy(summary)
    original_orders, original_nav = d.accounting._orders, d.accounting._nav
    monkeypatch.setattr(d.accounting, "_logs", lambda logs, reasons: (summary, nav_rows, coverage_rows))
    def orders(pages, receipt, supplied_summary, stats, config, reasons):
        assert pages is args[2] and receipt is args[3] and config is args[4]
        assert supplied_summary is None
        return original_orders(pages, receipt, supplied_summary, stats, config, reasons)
    def nav(rows, supplied_summary, stats, reasons):
        assert rows is nav_rows and supplied_summary is summary
        return original_nav(rows, supplied_summary, stats, reasons)
    monkeypatch.setattr(d.accounting, "_orders", orders)
    monkeypatch.setattr(d.accounting, "_nav", nav)
    result = d.diagnose_result(*args)
    assert summary == before
    assert result["original_summary_sha256"] == d._digest(summary)
    assert result["original_summary_counts"]["filled_shares"] == 20


def compressed_fixture():
    args = diagnostic_fixture()
    encoded = []
    for line in args[1]["logs"]:
        marker, payload = line.split(" ", 1)
        encoded.append(d.transport.encode_record(marker.removeprefix("MATCHED_"), json.loads(payload)))
    args[1]["logs"] = encoded
    args[1]["fixture_extra_metadata"] = {"retained": True}
    return rebind(args)


def test_compressed_derivative_keeps_original_wire_binding_and_exact_metrics():
    plain = diagnostic_fixture()
    encoded = compressed_fixture()
    before = deepcopy(encoded)
    plain_result, encoded_result = d.diagnose_result(*plain), d.diagnose_result(*encoded)
    assert encoded == before
    assert plain_result["aggregate_log_transport"] == "plain"
    assert encoded_result["aggregate_log_transport"] == "lossless_zlib_base64"
    assert encoded_result["evidence_hashes"] == encoded[3]["evidence_hashes"]
    assert encoded_result["evidence_hashes"]["logs"] == d._digest(encoded[1])
    assert encoded_result["decoded_logs_sha256"] != encoded_result["evidence_hashes"]["logs"]
    for key in ("metrics", "original_summary_counts", "original_summary_sha256", "coverage_by_sleeve",
                "prior_mark_input_sequence_sha256", "native_order_partition", "diagnostic_reasons"):
        assert encoded_result[key] == plain_result[key]
    assert encoded_result["development_execution_qualified"] is False


def test_original_wire_source_binding_precedes_decode_and_parser_receives_only_derivative(monkeypatch):
    args = compressed_fixture()
    events = []
    original_source, original_decode, original_logs = d.cap._source, d.transport.decode_logs, d.accounting._logs
    def source(receipt, config, config_hash, result, logs, pages, reasons):
        assert receipt is args[3] and logs is args[1] and pages is args[2] and result is args[0]
        events.append("source")
        return original_source(receipt, config, config_hash, result, logs, pages, reasons)
    def decode(logs):
        assert events == ["source"] and logs is args[1]
        events.append("decode")
        return original_decode(logs)
    def parse(logs, reasons):
        assert events == ["source", "decode"] and logs is not args[1]
        assert logs["fixture_extra_metadata"] == args[1]["fixture_extra_metadata"]
        events.append("parse")
        return original_logs(logs, reasons)
    monkeypatch.setattr(d.cap, "_source", source)
    monkeypatch.setattr(d.transport, "decode_logs", decode)
    monkeypatch.setattr(d.accounting, "_logs", parse)
    assert d.diagnose_result(*args)["metrics"] is not None
    assert events == ["source", "decode", "parse"]


def test_plain_mode_uses_the_unchanged_original_logs_without_codec(monkeypatch):
    args = diagnostic_fixture()
    original_logs = d.accounting._logs
    monkeypatch.setattr(d.transport, "decode_logs", lambda *unused: pytest.fail("codec invoked for plain evidence"))
    def parse(logs, reasons):
        assert logs is args[1]
        return original_logs(logs, reasons)
    monkeypatch.setattr(d.accounting, "_logs", parse)
    assert d.diagnose_result(*args)["aggregate_log_transport"] == "plain"


@pytest.mark.parametrize("fault", ["mixed", "duplicate", "hash", "bad_marker", "count"])
def test_invalid_encoded_log_transport_refuses_without_rebinding_or_repair(fault):
    args = compressed_fixture()
    if fault == "mixed":
        args[1]["logs"].append(diagnostic_fixture()[1]["logs"][0])
        args[1]["length"] += 1
    elif fault == "duplicate":
        args[1]["logs"].append(args[1]["logs"][0])
        args[1]["length"] += 1
    elif fault == "hash":
        pieces = args[1]["logs"][0].split(" ")
        pieces[2] = "0" * 64
        args[1]["logs"][0] = " ".join(pieces)
    elif fault == "bad_marker":
        args[1]["logs"][0] = "MATCHED_Z"
    else:
        args[1]["length"] -= 1
    rebind(args)
    before = deepcopy(args)
    with pytest.raises(d.AuditError, match="aggregate log transport"):
        d.diagnose_result(*args)
    assert args == before


@pytest.mark.parametrize("encoded", [False, True])
def test_missing_summary_cannot_be_reconstructed_after_native_log_truncation(encoded):
    args = compressed_fixture() if encoded else diagnostic_fixture()
    marker = "MATCHED_Z SUMMARY " if encoded else "MATCHED_SUMMARY "
    args[1]["logs"] = [line for line in args[1]["logs"] if not line.startswith(marker)]
    args[1]["length"] = len(args[1]["logs"])
    rebind(args)
    before = deepcopy(args)
    with pytest.raises(d.AuditError, match="summary identity"):
        d.diagnose_result(*args)
    assert args == before
