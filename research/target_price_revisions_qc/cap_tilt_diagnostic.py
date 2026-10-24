"""Pure, permanently unqualified metrics for intact cap/tilt QC evidence.

Native final-delisting Market fills can exceed strategy MOO submissions. This
diagnostic preserves those original counters and every frozen discrepancy;
it neither changes the strict auditor nor treats Market/zero-fee/QCC fills as
the frozen MOO economics. No I/O, CLI, admission, cloud import or pair delta.
"""
from __future__ import annotations

from fractions import Fraction
import re

from . import cap_tilt_audit as cap, cap_log_transport as transport

accounting = cap.accounting
AuditError = cap.AuditError
_refuse, _digest, _number, _text = cap._refuse, cap._digest, cap._number, cap._text

_COUNTS = {"decisions", "refused_decisions", "submitted_orders", "fill_events", "requested_shares",
    "submitted_shares", "filled_shares", "valuation_days", "position_ledger_mismatches", "risk_breaches",
    "observed_action_custody_symbols", "registered_universe_contexts", "cap_callback_count", "cap_snapshot_count",
    "isolated_benchmark_internal_config_max", "name_soft_cap_breaches", "native_final_delisting_compatibility_exceptions"}
_FLAGS = {"meaningful_execution", "original_no_delisting_meaningful_execution", "development_execution_qualified"}
_RESIDUALS = {"max_cash_ledger_residual", "max_nav_ledger_residual"}


def _decoded_logs(response):
    """Original plain logs, or a verified derivative; never repair truncation."""
    lines = response.get("logs") if type(response) is dict else None
    compressed = (type(lines) is list and any(type(line) is str and "MATCHED_Z" in line for line in lines))
    if not compressed:
        return response, "plain"
    try:
        return transport.decode_logs(response), "lossless_zlib_base64"
    except transport.TransportError:
        _refuse("aggregate log transport refused")


def _summary(summary, config, config_hash, reasons):
    expected = {"study_id": cap.STUDY, "candidate_id": config["candidate_id"], "arm": config["arm"],
        "cost": config["cost"], "config_sha256": config_hash, "freeze_sha256": cap.FREEZE_SHA256,
        "packet_sha256": cap.PACKET_SHA256 if config["arm"] == "tpr_on" else None,
        "canonical_admission": False, "independent_sleeve_pnl_observed": False}
    if (type(summary) is not dict or any(key not in summary or summary[key] != value or
            type(value) is bool and type(summary[key]) is not bool for key, value in expected.items())):
        _refuse("diagnostic summary identity or authority mismatch")
    required = _COUNTS | _FLAGS | _RESIDUALS | {"fees", "last_valuation_session", "reason_counts",
        "sleeve_selected_decisions", "delisting_audit", "warmup_finished_minute_validated", "max_name_exposure"}
    if not required.issubset(summary):
        _refuse("complete original diagnostic summary required")
    counts = {key: cap._count(summary[key]) for key in sorted(_COUNTS)}
    if any(type(summary[key]) is not bool for key in _FLAGS) or type(summary["warmup_finished_minute_validated"]) is not bool:
        _refuse("exact original runtime flags required")
    flags = {key: summary[key] for key in sorted(_FLAGS)}
    if flags["meaningful_execution"] != flags["original_no_delisting_meaningful_execution"]:
        _refuse("original strict runtime gate was relabelled")
    residuals = {key: _number(summary[key]) for key in _RESIDUALS}
    fees, exposure = _number(summary["fees"]), _number(summary["max_name_exposure"])
    if any(value < 0 for value in (*residuals.values(), fees, exposure)):
        _refuse("negative original accounting or exposure value")
    if (any(value > cap.PENNY for value in residuals.values()) or counts["position_ledger_mismatches"]
            or counts["risk_breaches"]):
        reasons.append("summary_accounting_or_risk_failure")
    if (counts["decisions"] != 14 or counts["refused_decisions"] != 0 or counts["valuation_days"] != 60
            or summary["last_valuation_session"] != cap.END.isoformat()):
        reasons.append("summary_execution_incomplete")
    if not counts["requested_shares"] >= counts["submitted_shares"] >= counts["filled_shares"]:
        reasons.append("original_strict_summary_share_ordering_refused")
    if summary["warmup_finished_minute_validated"] is not True:
        reasons.append("warmup_minute_subscription_validation_missing")
    if counts["observed_action_custody_symbols"] <= 0:
        reasons.append("observed_action_custody_missing")
    if counts["registered_universe_contexts"] != 7:
        reasons.append("native_cap_or_etf_context_inventory_incomplete")
    if not 0 < counts["cap_snapshot_count"] <= counts["cap_callback_count"]:
        reasons.append("native_cap_callback_evidence_missing_or_inconsistent")
    if counts["isolated_benchmark_internal_config_max"] > 1:
        reasons.append("isolated_benchmark_subscription_inventory_invalid")
    inventory = summary["reason_counts"]
    if (type(inventory) is not dict or len(inventory) > 1000
            or any(type(key) is not str or not 0 < len(key) <= 128 for key in inventory)):
        _refuse("bounded original reason count inventory required")
    values = {key: cap._count(value) for key, value in inventory.items()}
    events = values.get("delisting_event", 0)
    try:
        ambient = cap.observer.validate_audit(summary["delisting_audit"], events)
    except cap.observer.CapObserverError:
        _refuse("native delisting observer aggregate inconsistent")
    if not ambient:
        reasons.append("delisting_observation_unknown_or_nonambient")
    if events and flags["original_no_delisting_meaningful_execution"]:
        _refuse("strict runtime gate contradicts native delisting")
    failures = {"missing_mark", "missing_action_custody", "unpriced_held_nav", "missing_prior_close_nav",
        "qc_invalid_order", "qc_canceled_order", "delisting_target_refused"}
    if any(value and (key in failures or key.startswith("missing_") or
            "delist" in key.lower() and key != "delisting_event") for key, value in values.items()):
        reasons.append("execution_input_or_order_failure")
    if not all(flags.values()):
        reasons.append("original_runtime_reports_diagnostic")
    return counts, flags, ambient, events


def _partition(pages, native_orders, summary, reasons):
    """Describe native tags, not independent proof of engine/custody authority."""
    names = ("strategy_tagged_moo", "engine_tagged_delisting_market", "unclassified")
    if native_orders["orders"] is None:
        return {"inventory_complete": False, **{name: None for name in names}}
    groups = {name: {"orders": 0, "fill_events": 0, "submitted_shares": Fraction(0),
        "filled_shares": Fraction(0), "fees": Fraction(0), "zero_fee_qcc_fill_events": 0,
        "zero_fee_usd_fill_events": 0, "other_fee_or_currency_fill_events": 0} for name in names}
    for page in pages:
        if type(page) is not dict or page.get("success") is not True:
            continue
        for order in page["orders"]:
            raw_usd = (type(order.get("priceAdjustmentMode")) is int
                and order["priceAdjustmentMode"] == 0 and order.get("priceCurrency") == "USD")
            tag = order.get("tag")
            if (type(order.get("type")) is int and order["type"] == 4 and raw_usd and type(tag) is str
                    and re.fullmatch(r"TPRM:[0-9a-f]{20}", tag) is not None):
                name = "strategy_tagged_moo"
            elif type(order.get("type")) is int and order["type"] == 0 and raw_usd and tag == "Liquidate from delisting":
                name = "engine_tagged_delisting_market"
            else:
                name = "unclassified"
            group = groups[name]
            group["orders"] += 1
            quantity = _number(order["quantity"])
            group["submitted_shares"] += abs(quantity)
            filled = Fraction(0)
            for event in order["events"]:
                if event.get("status") not in ("filled", "partiallyFilled", "partially_filled", 2, 3):
                    continue
                amount, fee = _number(event["fillQuantity"]), _number(event["orderFeeAmount"])
                filled += amount
                group["fill_events"] += 1
                group["filled_shares"] += abs(amount)
                group["fees"] += fee
                currency = event.get("orderFeeCurrency")
                if fee == 0 and currency == "QCC":
                    group["zero_fee_qcc_fill_events"] += 1
                elif fee == 0 and currency == "USD":
                    group["zero_fee_usd_fill_events"] += 1
                else:
                    group["other_fee_or_currency_fill_events"] += 1
                if name == "engine_tagged_delisting_market" and (fee != 0 or amount >= 0):
                    reasons.append("engine_tagged_market_economics_not_final_zero_fee_close")
            if name == "engine_tagged_delisting_market" and (quantity >= 0 or filled != quantity or order.get("status") != 3):
                reasons.append("engine_tagged_market_not_full_negative_close")
    strategy, engine = groups["strategy_tagged_moo"], groups["engine_tagged_delisting_market"]
    if groups["unclassified"]["orders"]:
        reasons.append("unclassified_native_orders")
    if (strategy["orders"] != summary["submitted_orders"] or strategy["submitted_shares"] != summary["submitted_shares"]
            or strategy["filled_shares"] > strategy["submitted_shares"]):
        reasons.append("strategy_tagged_moo_summary_mismatch")
    if (native_orders["fill_events"] != summary["fill_events"]
            or _number(native_orders["filled_shares"]) != summary["filled_shares"]
            or _number(native_orders["fees"]) != _number(summary["fees"])):
        reasons.append("all_native_fill_summary_mismatch")
    if engine["fill_events"] != summary["native_final_delisting_compatibility_exceptions"]:
        reasons.append("native_final_compatibility_count_mismatch")
    incomplete = {"order_inventory_loading_or_failed", "order_inventory_incomplete", "order_page_boundary_missing"}
    return {"inventory_complete": not any(reason in incomplete for reason in reasons),
        **{name: {key: _text(value) if isinstance(value, Fraction) else value for key, value in group.items()}
           for name, group in groups.items()}, "engine_tag_is_not_independent_custody_proof": True}


def diagnose_result(result_response, logs_response, order_pages, source_receipt, candidate_config):
    """Interpret intact hash-bound inputs without granting any execution gate."""
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
    decoded_logs, transport_mode = _decoded_logs(logs_response)
    summary, nav_rows, coverage_rows = accounting._logs(decoded_logs, reasons)
    counts, flags, ambient, events = _summary(summary, candidate_config, config_hash, reasons)
    orders = accounting._orders(order_pages, source_receipt, None, stats, candidate_config, reasons)
    partition = _partition(order_pages, orders, summary, reasons)
    metrics = accounting._nav(nav_rows, summary, stats, reasons)
    coverage = cap._coverage(coverage_rows, candidate_config, summary, reasons)
    mark_hash = cap._prior_mark_inputs(coverage_rows)
    if metrics is not None:
        metrics["absolute_fill_notional_turnover_initial_nav"] = (None if orders["fill_notional"] is None else
            _text(_number(orders["fill_notional"]) / cap.INITIAL))
        metrics["max_name_exposure"] = _text(_number(summary["max_name_exposure"]))
        metrics["name_soft_cap_breaches"] = summary["name_soft_cap_breaches"]
        metrics["drawdown_sampling_reconciled"] = False
    return {"schema": "tpr-qc-cap-tilt-diagnostic-v1", "study_id": cap.STUDY,
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
        "delisting_observer_qualified": False, "delisting_observer_ambient_check": ambient, "delisting_events": events,
        "orders": orders, "native_order_partition": partition, "metrics": metrics if complete else None,
        "coverage_by_sleeve": coverage, "prior_mark_input_sequence_sha256": mark_hash,
        "valuation_observations": len(nav_rows), "decision_coverage_observations": len(coverage_rows),
        "valuation_sessions_sha256": _digest([row.get("session") for row in nav_rows]),
        "diagnostic_reasons": sorted(set(reasons)), "classification": "unqualified_exploratory_diagnostic",
        "meaningful_execution": False, "original_no_delisting_meaningful_execution": False,
        "development_execution_qualified": False, "strategy_accepted": False, "canonical_admission": False,
        "matched_comparison_qualified": False, "confirmatory_alpha": "0", "independent_sleeve_pnl_observed": False,
        "difference_metrics": {}, "numerical_convention": "Unchanged exact rational native orders/NAV; original residuals mandatory; statistical floats only in inherited metrics; Sharpe risk-free zero; partial 2025; native Market/zero-fee/QCC discrepancies remain diagnostic."}
