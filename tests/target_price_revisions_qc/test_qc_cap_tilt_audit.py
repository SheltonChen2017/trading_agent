"""Synthetic fresh-study accounting/coverage/delisting audit regressions."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from fractions import Fraction
import json
from pathlib import Path

import pytest

from research.target_price_revisions_qc import cap_tilt_audit as a, cap_observer as o


def config(arm="tpr_on"):
    row = next(row for row in a.CANDIDATES if row[1] == arm)
    return {"schema": "tpr-qc-cap-tilt-config-v1", "study_id": a.STUDY,
            "freeze_sha256": a.FREEZE_SHA256, "candidate_id": row[0],
            "arm": arm, "cost": "baseline", "slippage": "0.001"}


def rebind(args):
    result, logs, pages, receipt, _ = args
    receipt["evidence_hashes"] = {"result": a._digest(result), "logs": a._digest(logs),
                                  "order_pages": [a._digest(page) for page in pages]}
    return args


def change_log(args, prefix, transform, occurrence=0):
    positions = [index for index, line in enumerate(args[1]["logs"]) if prefix in line]
    index = positions[occurrence]
    row = json.loads(args[1]["logs"][index].split(prefix, 1)[1])
    transform(row)
    args[1]["logs"][index] = prefix + json.dumps(row)
    return rebind(args)


def observation(**updated):
    value = {"type": "warning", "phase": "evaluation", "receipt_window": "outside", "event_window": "outside",
             "held_before": False, "held_after": False, "ever_filled": False, "targeted": False, "open_order": False,
             "ever_ordered": False, "native_ticket": False, "history_unknown": False}
    value.update(updated)
    return value


def fixture(arm="tpr_on", *, empty=False):
    policy = config(arm)
    count = 0 if empty else 1
    summary = {"study_id": a.STUDY, "candidate_id": policy["candidate_id"], "arm": arm, "cost": "baseline",
        "config_sha256": a._digest(policy), "freeze_sha256": a.FREEZE_SHA256,
        "packet_sha256": a.PACKET_SHA256 if arm == "tpr_on" else None,
        "decisions": 14, "refused_decisions": 0, "submitted_orders": count, "fill_events": count,
        "requested_shares": count * 12, "submitted_shares": count * 10, "filled_shares": count * 10,
        "fees": "0.10" if count else "0", "valuation_days": 60, "last_valuation_session": "2025-03-31",
        "reason_counts": {}, "max_cash_ledger_residual": "0", "max_nav_ledger_residual": "0",
        "position_ledger_mismatches": 0, "risk_breaches": 0, "sleeve_selected_decisions": {etf: 14 for etf in a.ETFS},
        "meaningful_execution": not empty, "original_no_delisting_meaningful_execution": not empty,
        "development_execution_qualified": not empty, "delisting_audit": o.empty_audit(),
        "warmup_finished_minute_validated": True, "observed_action_custody_symbols": 12,
        "registered_universe_contexts": 7, "cap_callback_count": 60, "cap_snapshot_count": 60,
        "isolated_benchmark_internal_config_max": 1, "max_name_exposure": "0.01", "name_soft_cap_breaches": 0,
        "canonical_admission": False, "independent_sleeve_pnl_observed": False}
    lines = []
    for index, day in enumerate(a.VALUATIONS):
        nav = Fraction(100000 + (0 if empty else index * 10))
        cash = nav if empty else Fraction(90000)
        lines.append("MATCHED_NAV " + json.dumps({"session": day, "nav": str(int(nav)), "cash": str(int(cash)),
            "gross_exposure": a._text((nav - cash) / nav), "risk_within_unlevered_account": True,
            "max_name_exposure": "0" if empty else "0.01", "name_cap_is_prior_close_soft_target": True,
            "position_ledger_mismatches": 0, "cash_ledger_residual": "0", "nav_ledger_residual": "0"}))
    for day in a.DECISIONS:
        prior, cutoff = a._prior_cutoff(day)
        end_time = datetime(prior.year, prior.month, prior.day, tzinfo=a.NY).astimezone(timezone.utc)
        reports = {}
        for etf in a.ETFS:
            reports[etf] = {"membership_available": True, "snapshot_hash": a._digest(["SYNTHETIC", etf, day]),
                "member_count": 3, "selected_count": 2, "effective_utc": (cutoff - timedelta(days=8)).isoformat(),
                "received_utc": (cutoff - timedelta(days=1)).isoformat(), "etf_fallback": False,
                "cap_state_counts": {"available": 2, "missing": 1, "unknown": 0, "invalid": 0, "nonpositive": 0},
                "cap_input_hash": a._digest(["SYNTHETIC-CAPS", etf, day]),
                "cap_asof_time": (end_time - timedelta(days=1)).isoformat(), "cap_effective_utc": end_time.isoformat(),
                "cap_received_utc": (end_time + timedelta(minutes=1)).isoformat(),
                "selected_ids_hash": a._digest(["SYNTHETIC-SELECTED", etf, day]),
                "baseline_weights_hash": a._digest(["SYNTHETIC-BASE", etf, day]),
                "score_state_counts": ({"nonzero": 2, "zero": 0, "missing": 0, "unknown": 0, "invalid": 0}
                                        if arm == "tpr_on" else {"not_used": 2}),
                "ranked_score_count": 2 if arm == "tpr_on" else 0,
                "baseline_weight": a._text(Fraction(1, 30)), "target_weight": a._text(Fraction(1, 30)),
                "cash_weight": a._text(Fraction(2, 15)), "transferred_weight": "0.002" if arm == "tpr_on" else "0",
                "recipient_underfill": "0", "aggregate_cap_blocked_capacity": "0", "cap_binding_recipient_count": 0,
                "unfilled_slots": 8, "eligible_count": 2, "transfer_count": 1 if arm == "tpr_on" else 0,
                "maximum_absolute_relative_change": "0.12" if arm == "tpr_on" else "0"}
        lines.append("MATCHED_COVERAGE " + json.dumps({"session": day, "arm": arm, "sleeves": reports,
            "consolidated_selected_count": 12, "target_gross": "0.2", "unallocated_target_cash": "0.8",
            "prior_mark_inputs_sha256": a._digest(["SYNTHETIC-PRIOR-MARKS", day]), "prior_mark_session": prior.isoformat()}))
    lines.append("MATCHED_SUMMARY " + json.dumps(summary))
    result = {"success": True, "backtest": {"backtestId": "c" * 32, "projectId": 123, "completed": True,
        "progress": 1, "status": "Completed.", "error": None, "statistics": {"Total Orders": str(count),
            "Total Fees": "$0.10" if count else "$0", "Start Equity": "100000", "End Equity": "100000" if empty else "100590",
            "Drawdown": "1.00%"}}}
    fill = datetime(2025, 1, 2, 9, 30, tzinfo=a.NY)
    native = {"id": 1, "status": 3, "type": 4, "priceAdjustmentMode": 0, "priceCurrency": "USD", "quantity": 10,
              "createdTime": "2025-01-02T14:20:00Z", "debug_private_field": "SYNTHETIC_PRIVATE_TICKER",
              "events": [{"orderId": 1, "orderEventId": 1, "status": "filled", "fillQuantity": 10, "fillPrice": "100",
                          "fillPriceCurrency": "USD", "orderFeeAmount": "0.10", "orderFeeCurrency": "USD", "time": int(fill.timestamp())}]}
    pages = [{"success": True, "start": 0, "end": 99, "length": count, "orders": [] if empty else [native]}]
    receipt = {"candidate_id": policy["candidate_id"], "project_id": 123, "backtest_id": "c" * 32, "compile_id": "d" * 32,
               "config_sha256": a._digest(policy), "freeze_sha256": a.FREEZE_SHA256,
               "packet_sha256": a.PACKET_SHA256 if arm == "tpr_on" else None,
               "source_hashes": {name: "a" * 64 for name in a.SOURCE_FILES}, "exact_cloud_readback": True, "build_success": True}
    return rebind([result, {"success": True, "logs": lines, "length": len(lines)}, pages, receipt, policy])


@pytest.mark.parametrize("arm", ["tpr_on", "tpr_off"])
def test_fresh_run_reconciles_exact_accounting_and_explicit_limitations(arm):
    args = fixture(arm)
    original = deepcopy(args)
    evidence = a.audit_result(*args)
    assert args == original
    assert evidence["meaningful_execution"] is True
    assert evidence["development_execution_qualified"] is True
    assert evidence["original_no_delisting_meaningful_execution"] is True
    assert evidence["diagnostic_reasons"] == evidence["original_diagnostic_reasons"] == []
    assert evidence["orders"]["filled_orders"] == 1
    assert evidence["orders"]["fees"] == "0.1"
    assert evidence["metrics"]["return_pct"] == "0.59"
    assert evidence["metrics"]["daily_return_observations"] == 60
    assert evidence["metrics"]["cagr_elapsed_calendar_days"] == 88
    assert evidence["metrics"]["annual_result_is_partial"] is True
    assert evidence["metrics"]["risk_free_daily"] == "0"
    assert evidence["metrics"]["drawdown_sampling_reconciled"] is False
    assert evidence["metrics"]["qc_headline_drawdown"] == "1.00%"
    assert evidence["requested_minus_submitted_shares"] == 2
    assert evidence["canonical_admission"] is False and evidence["independent_sleeve_pnl_observed"] is False
    assert a._hash(evidence["prior_mark_input_sequence_sha256"])
    assert "SYNTHETIC_PRIVATE_TICKER" not in json.dumps(evidence)
    assert "fillPrice" not in json.dumps(evidence) and "orderEventId" not in json.dumps(evidence)
    for group in evidence["coverage_by_sleeve"].values():
        assert group["observed_decisions"] == group["selected_decisions"] == 14
        assert group["cap_state_counts"] == {"available": 28, "missing": 14, "unknown": 0, "invalid": 0, "nonpositive": 0}
        assert group["covered_subset_only"] is True
        assert group["historical_publication_availability_attested"] is False
    assert a.analyze_operation(*args) == evidence


@pytest.mark.parametrize("status,qualified", [("Completed", True), ("Completed.", True),
    ("completed", False), ("Completed..", False), (" Completed.", False), ("Running", False)])
def test_exact_terminal_spelling_is_not_completion_by_itself(status, qualified):
    args = fixture()
    args[0]["backtest"]["status"] = status
    rebind(args)
    assert a.audit_result(*args)["development_execution_qualified"] is qualified


@pytest.mark.parametrize("changed", [{"completed": False}, {"completed": 1}, {"progress": "0.99"},
    {"error": "Synthetic runtime error"}, {"error": ""}])
def test_completed_punctuation_cannot_override_native_terminal_failures(changed):
    args = fixture()
    args[0]["backtest"].update(changed)
    rebind(args)
    assert a.audit_result(*args)["development_execution_qualified"] is False


def test_absent_error_field_is_unknown_not_explicit_success():
    args = fixture()
    del args[0]["backtest"]["error"]
    rebind(args)
    assert a.audit_result(*args)["development_execution_qualified"] is False


def add_delisting(args, **observed):
    def update(summary):
        summary.update(reason_counts={"delisting_event": 1}, meaningful_execution=False,
                       original_no_delisting_meaningful_execution=False,
                       delisting_audit=o.record_event(o.empty_audit(), observation(**observed)))
    return change_log(args, "MATCHED_SUMMARY ", update)


def test_fresh_all_ambient_delisting_qualifies_only_new_development_gate():
    evidence = a.audit_result(*add_delisting(fixture()))
    assert evidence["delisting_events"] == 1
    assert evidence["delisting_observer_qualified"] is True
    assert evidence["development_execution_qualified"] is True
    assert evidence["meaningful_execution"] is evidence["original_no_delisting_meaningful_execution"] is False
    assert evidence["diagnostic_reasons"] == []
    assert set(evidence["original_diagnostic_reasons"]) == {"adapter_reports_diagnostic", "execution_input_or_order_failure"}


@pytest.mark.parametrize("changed", [{"held_before": True}, {"held_after": True}, {"ever_filled": True},
    {"targeted": True}, {"open_order": True}, {"ever_ordered": True}, {"native_ticket": True},
    {"receipt_window": "inside"}, {"event_window": "inside"}, {"type": "unknown"}, {"phase": "unknown"},
    {"held_before": None}, {"targeted": None}, {"native_ticket": None}, {"history_unknown": True},
    {"receipt_window": "unknown"}, {"event_window": "unknown"}])
def test_unknown_or_nonambient_event_never_qualifies_from_adapter_claim(changed):
    evidence = a.audit_result(*add_delisting(fixture(), **changed))
    assert evidence["development_execution_qualified"] is False
    assert evidence["delisting_observer_qualified"] is False
    assert "delisting_observation_unknown_or_nonambient" in evidence["diagnostic_reasons"]


@pytest.mark.parametrize("change", [
    lambda summary: summary["reason_counts"].update(delisting_event=2),
    lambda summary: summary["delisting_audit"].update(total=True),
    lambda summary: summary["delisting_audit"].update(unknown_total=0),
    lambda summary: summary["delisting_audit"].update(ever_ordered=1),
    lambda summary: summary.update(original_no_delisting_meaningful_execution=True, meaningful_execution=True),
])
def test_delisting_total_partition_and_old_gate_cannot_be_retagged(change):
    args = add_delisting(fixture())
    change_log(args, "MATCHED_SUMMARY ", change)
    with pytest.raises(a.AuditError):
        a.audit_result(*args)


@pytest.mark.parametrize("reason", ["missing_mark", "missing_action_custody", "unpriced_held_nav",
    "missing_prior_close_nav", "qc_invalid_order", "qc_canceled_order", "delisting_target_refused",
    "missing_lagged_membership_REMX", "missing_prior_session_cap_snapshot", "delist", "generic_delisting"])
def test_ambient_exception_never_removes_any_other_failure(reason):
    args = add_delisting(fixture())
    change_log(args, "MATCHED_SUMMARY ", lambda summary: summary["reason_counts"].update({reason: 1}))
    evidence = a.audit_result(*args)
    assert evidence["development_execution_qualified"] is False
    assert "execution_input_or_order_failure" in evidence["diagnostic_reasons"]


@pytest.mark.parametrize("update", [{"warmup_finished_minute_validated": False}, {"observed_action_custody_symbols": 0},
    {"registered_universe_contexts": 6}, {"cap_callback_count": 0}, {"cap_snapshot_count": 0},
    {"cap_snapshot_count": 61}, {"isolated_benchmark_internal_config_max": 2}, {"decisions": 13},
    {"refused_decisions": 1}, {"valuation_days": 59}, {"risk_breaches": 1},
    {"development_execution_qualified": False}, {"meaningful_execution": False, "original_no_delisting_meaningful_execution": False}])
def test_native_runtime_claims_and_existing_readiness_gates_remain_required(update):
    args = fixture()
    change_log(args, "MATCHED_SUMMARY ", lambda summary: summary.update(update))
    assert a.audit_result(*args)["development_execution_qualified"] is False


@pytest.mark.parametrize("key", ["decisions", "cap_callback_count", "cap_snapshot_count", "registered_universe_contexts",
                                  "original_no_delisting_meaningful_execution", "development_execution_qualified"])
def test_new_summary_flags_counts_refuse_boolean_or_integer_coercion(key):
    args = fixture()
    value = 1 if "execution" in key else True
    change_log(args, "MATCHED_SUMMARY ", lambda summary: summary.update({key: value}))
    with pytest.raises(a.AuditError):
        a.audit_result(*args)


@pytest.mark.parametrize("field", ["snapshot_hash", "cap_input_hash", "selected_ids_hash", "baseline_weights_hash"])
def test_each_source_selection_or_baseline_hash_is_required(field):
    args = fixture()
    change_log(args, "MATCHED_COVERAGE ", lambda row: row["sleeves"]["SPY"].update({field: None}))
    with pytest.raises(a.AuditError):
        a.audit_result(*args)


@pytest.mark.parametrize("value", [None, True, "", "a" * 63, "A" * 64, {"private_row": "private"}])
def test_prior_selected_target_mark_hash_is_required_and_closed(value):
    args = fixture()
    change_log(args, "MATCHED_COVERAGE ", lambda row: row.update(prior_mark_inputs_sha256=value))
    with pytest.raises(a.AuditError, match="prior mark input hash"):
        a.audit_result(*args)


def test_missing_prior_mark_hash_refuses_instead_of_matching_empty_inputs():
    args = fixture()
    change_log(args, "MATCHED_COVERAGE ", lambda row: row.pop("prior_mark_inputs_sha256"))
    with pytest.raises(a.AuditError, match="prior mark input hash"):
        a.audit_result(*args)


@pytest.mark.parametrize("value", [None, "2025-01-02", "2024-12-30", "2024-12-31T00:00:00Z"])
def test_prior_mark_session_must_equal_exact_previous_exchange_session(value):
    args = fixture()
    change_log(args, "MATCHED_COVERAGE ", lambda row: row.update(prior_mark_session=value))
    with pytest.raises(a.AuditError, match="prior mark source session"):
        a.audit_result(*args)


@pytest.mark.parametrize("target", ["member_partition", "selection_count", "rank_count", "score_partition", "budget",
    "cash", "transfer_band", "cap_underfill", "eligible_count", "unfilled_slots", "relative_band", "gross", "consolidated_count"])
def test_cap_selection_score_counts_and_exact_slot_budgets_are_binding(target):
    args = fixture()
    def update(row):
        report = row["sleeves"]["SPY"]
        if target == "member_partition": report["member_count"] = 4
        elif target == "selection_count": report["selected_count"] = 1
        elif target == "rank_count": report["ranked_score_count"] = 1
        elif target == "score_partition": report["score_state_counts"]["missing"] = 1
        elif target == "budget": report["target_weight"] = "0.034"
        elif target == "cash": report["cash_weight"] = "0.1"
        elif target == "transfer_band": report["transferred_weight"] = "0.008"
        elif target == "cap_underfill": report["aggregate_cap_blocked_capacity"] = "0.001"
        elif target == "eligible_count": report["eligible_count"] = 3
        elif target == "unfilled_slots": report["unfilled_slots"] = 7
        elif target == "relative_band": report["maximum_absolute_relative_change"] = "0.21"
        elif target == "gross": row["target_gross"] = "0.3"
        else: row["consolidated_selected_count"] = 1
    change_log(args, "MATCHED_COVERAGE ", update)
    assert a.audit_result(*args)["development_execution_qualified"] is False


@pytest.mark.parametrize("target", ["membership_future", "membership_reverse", "cap_current", "cap_stale",
    "cap_future_received", "cap_asof_future", "cap_reverse_received"])
def test_membership_and_cap_clocks_preserve_prior_cutoff_and_native_endtime_date(target):
    args = fixture()
    def update(row):
        report = row["sleeves"]["SPY"]
        if target == "membership_future": report["received_utc"] = "2025-01-02T14:30:00Z"
        elif target == "membership_reverse": report["received_utc"] = "2024-12-01T00:00:00Z"
        elif target == "cap_current": report["cap_effective_utc"] = report["cap_received_utc"] = "2025-01-02T05:00:00Z"
        elif target == "cap_stale": report["cap_effective_utc"] = report["cap_received_utc"] = "2024-12-30T05:00:00Z"
        elif target == "cap_future_received": report["cap_received_utc"] = "2025-01-02T14:30:00Z"
        elif target == "cap_asof_future": report["cap_asof_time"] = "2025-01-02T05:00:00Z"
        else: report["cap_received_utc"] = "2024-12-30T05:00:00Z"
    change_log(args, "MATCHED_COVERAGE ", update)
    assert a.audit_result(*args)["development_execution_qualified"] is False


@pytest.mark.parametrize("field", ["effective_utc", "received_utc", "cap_effective_utc", "cap_received_utc", "cap_asof_time"])
def test_unknown_or_naive_clock_is_never_fabricated(field):
    for bad in (None, "2024-12-31T00:00:00"):
        args = fixture()
        change_log(args, "MATCHED_COVERAGE ", lambda row: row["sleeves"]["SPY"].update({field: bad}))
        with pytest.raises(a.AuditError):
            a.audit_result(*args)


@pytest.mark.parametrize("target", ["counts", "ranking", "transfer", "underfill", "capblock", "binding", "relative"])
def test_neutral_control_removes_every_tpr_input_or_transfer_influence(target):
    args = fixture("tpr_off")
    def update(row):
        report = row["sleeves"]["SPY"]
        if target == "counts": report["score_state_counts"] = {"nonzero": 2}
        elif target == "ranking": report["ranked_score_count"] = 1
        elif target == "transfer": report["transferred_weight"] = "0.001"
        elif target == "underfill": report["recipient_underfill"] = "0.001"
        elif target == "capblock": report.update(recipient_underfill="0.001", aggregate_cap_blocked_capacity="0.001")
        elif target == "binding": report["cap_binding_recipient_count"] = 1
        else: report["maximum_absolute_relative_change"] = "0.1"
    change_log(args, "MATCHED_COVERAGE ", update)
    if target == "counts":
        with pytest.raises(a.AuditError): a.audit_result(*args)
    else:
        assert a.audit_result(*args)["development_execution_qualified"] is False


@pytest.mark.parametrize("target", ["source_missing", "cloud_unverified", "build_unverified", "zero_orders", "fee",
    "native_fee_stats", "native_order_stats", "accounting", "daily_risk", "schedule", "loading", "terminal"])
def test_all_existing_non_delisting_accounting_order_and_source_gates_survive(target):
    args = fixture(empty=target == "zero_orders")
    if target == "source_missing": args[3]["source_hashes"].pop("cap_observer.py")
    elif target == "cloud_unverified": args[3]["exact_cloud_readback"] = False
    elif target == "build_unverified": args[3]["build_success"] = False
    elif target == "fee": args[2][0]["orders"][0]["events"][0]["orderFeeAmount"] = "0"
    elif target == "native_fee_stats": args[0]["backtest"]["statistics"]["Total Fees"] = "$1"
    elif target == "native_order_stats": args[0]["backtest"]["statistics"]["Total Orders"] = "2"
    elif target == "accounting": change_log(args, "MATCHED_NAV ", lambda row: row.update(cash_ledger_residual="0.02"))
    elif target == "daily_risk": change_log(args, "MATCHED_NAV ", lambda row: row.update(risk_within_unlevered_account=False))
    elif target == "schedule": change_log(args, "MATCHED_NAV ", lambda row: row.update(session="2025-01-09"))
    elif target == "loading": args[2][0]["loading"] = True
    elif target == "terminal": args[0]["backtest"].update(completed=False, status="RuntimeError", error="synthetic")
    rebind(args)
    evidence = a.audit_result(*args)
    assert evidence["development_execution_qualified"] is False
    assert evidence["diagnostic_reasons"]


def test_native_fee_rule_survives_consistently_wrong_zero_cost_accounting():
    args = fixture()
    args[2][0]["orders"][0]["events"][0]["orderFeeAmount"] = "0"
    args[0]["backtest"]["statistics"]["Total Fees"] = "$0"
    change_log(args, "MATCHED_SUMMARY ", lambda summary: summary.update(fees="0"))
    evidence = a.audit_result(*rebind(args))
    assert evidence["development_execution_qualified"] is False
    assert evidence["diagnostic_reasons"] == ["native_fee_schedule_mismatch"]


def test_content_binding_rejects_native_outcome_change_before_parsing():
    args = fixture()
    args[0]["backtest"]["statistics"]["End Equity"] = "99999"
    with pytest.raises(a.AuditError, match="mixed result"):
        a.audit_result(*args)


def test_old_study_config_and_four_file_receipt_cannot_be_relabelled_success():
    from research.target_price_revisions_qc import matched_audit
    args = fixture()
    args[4]["schema"] = "tpr-qc-matched-config-v1"
    with pytest.raises(a.AuditError): a.audit_result(*args)
    args = fixture()
    args[3]["source_hashes"] = {name: "a" * 64 for name in matched_audit.SOURCE_FILES}
    rebind(args)
    assert a.audit_result(*args)["development_execution_qualified"] is False


def test_matched_pair_compares_membership_cap_selected_and_baseline_paths():
    on, off = a.audit_result(*fixture()), a.audit_result(*fixture("tpr_off"))
    pair = a.analyze_pair(on, off)
    assert pair["matched_comparison_qualified"] is pair["matched_inputs"] is True
    assert pair["matched_observation_count"] == 60
    assert pair["difference_metrics"] == {"return_pct_difference_percentage_points": "0", "daily_drawdown_pct_difference_percentage_points": "0"}
    assert pair["independent_sleeve_pnl_observed"] is pair["canonical_admission"] is False
    assert pair["confirmatory_alpha"] == "0"


@pytest.mark.parametrize("field", ["snapshot_hash", "cap_input_hash", "selected_ids_hash", "baseline_weights_hash"])
def test_each_unmatched_input_path_prevents_tilt_attribution(field):
    args = fixture("tpr_off")
    change_log(args, "MATCHED_COVERAGE ", lambda row: row["sleeves"]["REMX"].update({field: "f" * 64}))
    off = a.audit_result(*args)
    assert off["development_execution_qualified"] is True
    pair = a.analyze_pair(a.audit_result(*fixture()), off)
    assert pair["matched_inputs"] is pair["matched_comparison_qualified"] is False
    assert pair["matched_observation_count"] is None and pair["difference_metrics"] == {}


def test_native_prior_mark_input_change_prevents_attribution_despite_other_paths_matching():
    args = fixture("tpr_off")
    change_log(args, "MATCHED_COVERAGE ", lambda row: row.update(prior_mark_inputs_sha256="f" * 64))
    on, off = a.audit_result(*fixture()), a.audit_result(*args)
    assert on["development_execution_qualified"] is off["development_execution_qualified"] is True
    assert all(on["coverage_by_sleeve"][etf][name + "_sequence_sha256"] ==
               off["coverage_by_sleeve"][etf][name + "_sequence_sha256"]
               for etf in a.ETFS for name in a._SEQUENCES)
    pair = a.analyze_pair(on, off)
    assert pair["matched_comparison_qualified"] is pair["matched_inputs"] is False
    assert pair["difference_metrics"] == {} and pair["matched_observation_count"] is None
    assert pair["diagnostic_reasons"] == ["unmatched_prior_mark_inputs"]


def test_missing_audited_prior_mark_path_is_not_a_matching_absent_path():
    on, off = a.audit_result(*fixture()), a.audit_result(*fixture("tpr_off"))
    on["prior_mark_input_sequence_sha256"] = off["prior_mark_input_sequence_sha256"] = None
    pair = a.analyze_pair(on, off)
    assert pair["matched_comparison_qualified"] is pair["matched_inputs"] is False
    assert pair["difference_metrics"] == {}


def test_incomplete_coverage_has_no_fabricated_complete_mark_path():
    args = fixture()
    index = next(index for index, line in enumerate(args[1]["logs"]) if "MATCHED_COVERAGE " in line)
    args[1]["logs"].pop(index)
    args[1]["length"] -= 1
    evidence = a.audit_result(*rebind(args))
    assert evidence["development_execution_qualified"] is False
    assert evidence["prior_mark_input_sequence_sha256"] is None


def test_failed_run_cannot_become_qualified_by_matching_input_hashes():
    pair = a.analyze_pair(a.audit_result(*fixture(empty=True)), a.audit_result(*fixture("tpr_off")))
    assert pair["matched_inputs"] is True
    assert pair["matched_comparison_qualified"] is False
    assert pair["difference_metrics"] == {}


def test_pair_role_or_study_mismatch_is_refused():
    on, off = a.audit_result(*fixture()), a.audit_result(*fixture("tpr_off"))
    with pytest.raises(a.AuditError): a.analyze_pair(off, on)
    off["freeze_sha256"] = "f" * 64
    with pytest.raises(a.AuditError): a.analyze_pair(on, off)


@pytest.mark.parametrize("changed", [{"coverage_by_sleeve": None}, {"config_sha256": "f" * 64},
    {"canonical_admission": True}, {"independent_sleeve_pnl_observed": True}])
def test_pair_does_not_trust_corrupt_or_authority_relabelled_audit(changed):
    on, off = a.audit_result(*fixture()), a.audit_result(*fixture("tpr_off"))
    off.update(changed)
    with pytest.raises(a.AuditError):
        a.analyze_pair(on, off)


def test_native_metadata_shape_cannot_echo_unexpected_row_values():
    args = fixture()
    args[0]["backtest"]["status"] = {"PRIVATE_ROW": "secret-value"}
    args[3]["compile_id"] = {"PRIVATE_ROW": "secret-value"}
    rebind(args)
    evidence = a.audit_result(*args)
    assert evidence["terminal_status"] is evidence["compile_id"] is None
    assert "PRIVATE_ROW" not in json.dumps(evidence)
    args = fixture()
    args[0]["backtest"]["statistics"]["Drawdown"] = {"PRIVATE_ROW": "secret-value"}
    rebind(args)
    with pytest.raises(a.AuditError) as error:
        a.audit_result(*args)
    assert "PRIVATE_ROW" not in str(error.value)


def test_empty_evidence_stays_unknown_not_a_completed_zero_signal_study():
    evidence = a.audit_result({"success": False}, {"success": False}, [], {}, config())
    assert evidence["development_execution_qualified"] is False
    assert evidence["metrics"] is None
    assert all(group is None for group in evidence["coverage_by_sleeve"].values())


def test_audit_is_pure_and_does_not_read_private_source_or_network(monkeypatch):
    args = fixture()
    import builtins, socket
    def forbidden(*_args, **_kwargs): pytest.fail("pure audit performed I/O")
    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    assert a.audit_result(*args)["development_execution_qualified"] is True
