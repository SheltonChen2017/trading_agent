"""Pure unqualified metrics with explicitly unknown native monetary fields.

The five original evidence objects are hash-bound before decoding or order
inventory interpretation. No fee/currency is inferred from a runtime summary,
an engine-looking tag, a headline statistic or a prior diagnostic. Original
accounting, sixty valuations and observed-only coverage remain separate from
native API fee completeness. No I/O, evidence repair, CLI or pair delta.
"""
from __future__ import annotations

import re

from . import cap_tilt_diagnostic as original, cap_tilt_diagnostic_v2 as observed
from . import cap_native_order_diagnostic as native_orders

cap, accounting = original.cap, original.accounting
AuditError = cap.AuditError
_refuse, _digest, _number, _text = cap._refuse, cap._digest, cap._number, cap._text


def diagnose_result(result_response, logs_response, order_pages, source_receipt, candidate_config):
    """Report intact native unknowns without granting any execution gate."""
    config_hash = cap._config(candidate_config)
    if type(order_pages) is not list:
        _refuse("order page list required")
    reasons = ["frozen_execution_unqualified", "strict_audit_refused_or_not_admitted"]
    sources = cap._source(source_receipt, candidate_config, config_hash, result_response, logs_response, order_pages, reasons)
    if any(reason in {"source_verification_missing", "evidence_binding_missing"} for reason in reasons):
        _refuse("complete original source and evidence binding required")
    if (type(result_response) is not dict or result_response.get("success") is not True
            or type(result_response.get("backtest")) is not dict):
        _refuse("original native backtest response required")
    native = result_response["backtest"]
    if native.get("backtestId") != source_receipt["backtest_id"]:
        _refuse("foreign native backtest identity")
    if (type(native.get("projectId")) is not int or native["projectId"] <= 0
            or native["projectId"] != source_receipt["project_id"]):
        _refuse("foreign or missing native project identity")
    status = native.get("status")
    terminal = status if type(status) is str and re.fullmatch(r"[A-Za-z][A-Za-z ._-]{0,63}", status) else None
    complete = (native.get("completed") is True and _number(native.get("progress", "0")) == 1
        and "error" in native and native["error"] is None and status in ("Completed", "Completed."))
    if not complete:
        reasons.append("backtest_not_successfully_completed")
    stats = native.get("statistics") if type(native.get("statistics")) is dict else {}
    decoded_logs, transport_mode = original._decoded_logs(logs_response)
    summary, nav_rows, coverage_rows = accounting._logs(decoded_logs, reasons)
    counts, flags, ambient, events = original._summary(summary, candidate_config, config_hash, reasons)
    # The helper interprets the unchanged native evidence, including explicitly
    # unreported monetary fields. The original summary is not repaired/rebound.
    inventory = native_orders.orders(order_pages, source_receipt, summary, stats, candidate_config, reasons)
    orders, partition = inventory["orders"], inventory["native_order_partition"]
    metrics = accounting._nav(nav_rows, summary, stats, reasons)
    coverage = cap._coverage(coverage_rows, candidate_config, summary, reasons)
    mark_hash = cap._prior_mark_inputs(coverage_rows)
    days, observed_marks = observed._observed_prior_mark_inputs(coverage_rows)
    missing = tuple(day for day in cap.DECISIONS if day not in days)
    if ((missing and mark_hash is not None) or (not missing and mark_hash != observed_marks)):
        _refuse("complete and observed prior mark paths inconsistent")
    paths = {}
    for etf in cap.ETFS:
        group = coverage[etf]
        paths[etf] = (None if group is None else {
            "observed_decision_count": group["observed_decisions"],
            **{name + "_sequence_sha256": group[name + "_sequence_sha256"] for name in observed._PATHS}})
    if metrics is not None:
        metrics["absolute_fill_notional_turnover_initial_nav"] = (None if orders["fill_notional"] is None else
            _text(_number(orders["fill_notional"]) / cap.INITIAL))
        metrics["observed_usd_fill_notional_turnover_initial_nav"] = (None if orders["observed_usd_fill_notional"] is None else
            _text(_number(orders["observed_usd_fill_notional"]) / cap.INITIAL))
        metrics["max_name_exposure"] = _text(_number(summary["max_name_exposure"]))
        metrics["name_soft_cap_breaches"] = summary["name_soft_cap_breaches"]
        metrics["drawdown_sampling_reconciled"] = False
    return {"schema": "tpr-qc-cap-tilt-diagnostic-v3", "study_id": cap.STUDY,
        "candidate_id": candidate_config["candidate_id"], "arm": candidate_config["arm"], "cost": candidate_config["cost"],
        "project_id": source_receipt["project_id"], "compile_id": source_receipt["compile_id"],
        "backtest_id": source_receipt["backtest_id"], "config_sha256": config_hash, "freeze_sha256": cap.FREEZE_SHA256,
        "packet_sha256": cap.PACKET_SHA256 if candidate_config["arm"] == "tpr_on" else None,
        "source_hashes": sources, "source_receipt_sha256": _digest(source_receipt),
        "evidence_hashes": {"result": _digest(result_response), "logs": _digest(logs_response),
            "order_pages": [_digest(page) for page in order_pages]}, "original_summary_sha256": _digest(summary),
        "aggregate_log_transport": transport_mode, "decoded_logs_sha256": _digest(decoded_logs),
        "terminal_status": terminal, "native_successfully_completed": complete,
        "native_error_field_present": "error" in native, "native_error_is_none": "error" in native and native["error"] is None,
        "runtime_reported_execution_flags": flags, "original_summary_counts": counts,
        "original_summary_filled_counter_includes_all_native_callbacks": True,
        "runtime_reported_accounting": {
            "fees": _text(_number(summary["fees"])),
            "max_cash_ledger_residual": _text(_number(summary["max_cash_ledger_residual"])),
            "max_nav_ledger_residual": _text(_number(summary["max_nav_ledger_residual"])),
            "provenance": "Unchanged hash-bound runtime SUMMARY; residuals are runtime ledger checks, not observed values for absent native API fees or monetary units.",
            "attests_unreported_native_fee_or_currency": False},
        "native_fee_provenance": inventory["fee_provenance"],
        "delisting_observer_qualified": False, "delisting_observer_ambient_check": ambient, "delisting_events": events,
        "orders": orders, "native_order_partition": partition, "metrics": metrics if complete else None,
        "coverage_by_sleeve": coverage, "prior_mark_input_sequence_sha256": mark_hash,
        "valuation_observations": len(nav_rows), "decision_coverage_observations": len(coverage_rows),
        "valuation_sessions_sha256": _digest([row.get("session") for row in nav_rows]),
        "observed_decision_dates": list(days), "missing_frozen_decision_dates": list(missing),
        "observed_coverage_sessions_sha256": _digest(list(days)),
        "observed_prior_mark_input_sequence_sha256": observed_marks,
        "observed_prior_mark_decision_count": len(days), "complete_frozen_decision_coverage": not missing,
        "observed_coverage_input_paths_by_sleeve": paths,
        "coverage_provenance": "Only explicitly observed logged decisions; missing dates are not reconstructed or zero inputs. Complete-14 prior-mark hash is None for partial coverage. Observed-subset hashes do not attest native input tapes or historical publication availability. Full 60-day NAV/order metrics remain unqualified; no pair delta or alpha claim.",
        "diagnostic_reasons": sorted(set(reasons)), "classification": "unqualified_exploratory_diagnostic",
        "meaningful_execution": False, "original_no_delisting_meaningful_execution": False,
        "development_execution_qualified": False, "strategy_accepted": False, "canonical_admission": False,
        "matched_comparison_qualified": False, "confirmatory_alpha": "0", "independent_sleeve_pnl_observed": False,
        "difference_metrics": {}, "numerical_convention": "Unchanged exact rational observed native quantities/NAV; original runtime residuals mandatory. Unreported native fees/currencies remain unknown, not zero/USD/QCC; runtime/native headline claims are distinct from API-observed values. Statistical floats only in inherited metrics; Sharpe risk-free zero; partial 2025; all execution discrepancies remain diagnostic."}
