"""Pure audit of fresh, owner-authorized cap-selected TPR-tilt QC evidence.

The original order/NAV reconciliation helpers are reused without changing
their source, globals or executed evidence. This distinct study has new
configuration, source inventory, coverage and delisting qualification. The
strict no-delisting gate remains separately visible; only a fresh, complete,
all-ambient observer can qualify development execution despite delisting.
Neither hashes nor runtime aggregate claims attest canonical custody, native
input tapes or historical publication availability. No I/O occurs here.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from fractions import Fraction
import re

from . import cap_observer as observer, matched_audit as accounting
from .cap_tilt_bundle import CANDIDATES, FREEZE_SHA256, PACKET_SHA256, STUDY


AuditError = accounting.AuditError
_refuse, _digest, _hash = accounting._refuse, accounting._digest, accounting._hash
_number, _text, _clock = accounting._number, accounting._text, accounting._clock
ETFS, DECISIONS, VALUATIONS = accounting.ETFS, accounting.DECISIONS, accounting.VALUATIONS
NY, INITIAL, PENNY, END = accounting.NY, accounting.INITIAL, accounting.PENNY, accounting.END
SOURCE_FILES = {"main.py", "proxy_core.py", "signal_packet.py", "matched_config.py", "cap_tilt.py", "cap_observer.py"}
CAP_STATES = {"available", "missing", "unknown", "invalid", "nonpositive"}
SCORE_STATES = {"nonzero", "zero", "missing", "unknown", "invalid"}
# Runtime display ratios use forty-eight-digit decimal text, and the reused
# audit formatter uses fifty digits; exact money still
# reconciles through the unchanged rational order/NAV helpers. This tolerance
# covers display of thirds, never an execution/accounting penny discrepancy.
DISPLAY_TOLERANCE = Fraction(1, 10**45)
_COVERAGE_KEYS = {
    "membership_available", "snapshot_hash", "member_count", "selected_count", "effective_utc", "received_utc",
    "etf_fallback", "cap_state_counts", "cap_input_hash", "cap_effective_utc", "cap_received_utc", "cap_asof_time",
    "selected_ids_hash", "baseline_weights_hash", "score_state_counts", "ranked_score_count", "baseline_weight",
    "target_weight", "cash_weight", "transferred_weight", "recipient_underfill", "aggregate_cap_blocked_capacity",
    "cap_binding_recipient_count",
}
_OPTIONAL_COVERAGE = {"unfilled_slots", "eligible_count", "transfer_count", "maximum_absolute_relative_change"}
_SEQUENCES = ("membership_snapshot", "cap_input", "selected_ids", "baseline_weights")


def _count(value, maximum=1000000):
    if type(value) is not int or not 0 <= value <= maximum:
        _refuse("bounded exact integer count required")
    return value


def _identifier(value):
    return (value if type(value) is str and re.fullmatch(r"[A-Za-z0-9_.-]{1,200}", value) else None)


def _config(config):
    keys = {"schema", "study_id", "freeze_sha256", "candidate_id", "arm", "cost", "slippage"}
    if type(config) is not dict or set(config) != keys:
        _refuse("closed cap/tilt configuration required")
    policy = (config["candidate_id"], config["arm"], config["cost"], config["slippage"])
    if (config["schema"] != "tpr-qc-cap-tilt-config-v1" or config["study_id"] != STUDY
            or config["freeze_sha256"] != FREEZE_SHA256 or policy not in CANDIDATES):
        _refuse("candidate outside frozen cap/tilt policy")
    return _digest(config)


def _source(receipt, config, config_hash, result, logs, pages, reasons):
    if type(receipt) is not dict:
        reasons.append("source_verification_missing")
        return {}
    expected_packet = PACKET_SHA256 if config["arm"] == "tpr_on" else None
    for key, expected in (("candidate_id", config["candidate_id"]), ("config_sha256", config_hash),
                          ("freeze_sha256", FREEZE_SHA256), ("packet_sha256", expected_packet)):
        if key not in receipt:
            reasons.append("source_verification_missing")
        elif receipt[key] != expected:
            _refuse("source and cap/tilt candidate identities differ")
    sources = receipt.get("source_hashes")
    hashes_valid = (type(sources) is dict and set(sources) == SOURCE_FILES
                    and all(_hash(value) for value in sources.values()))
    if not hashes_valid or receipt.get("exact_cloud_readback") is not True or receipt.get("build_success") is not True:
        reasons.append("source_verification_missing")
    if type(receipt.get("project_id")) is not int or receipt["project_id"] <= 0:
        reasons.append("source_verification_missing")
    for key in ("compile_id", "backtest_id"):
        value = receipt.get(key)
        if type(value) is not str or re.fullmatch(r"[A-Za-z0-9_.-]{1,200}", value) is None:
            reasons.append("source_verification_missing")
    expected_evidence = {"result": _digest(result), "logs": _digest(logs), "order_pages": [_digest(page) for page in pages]}
    if "evidence_hashes" not in receipt:
        reasons.append("evidence_binding_missing")
    elif receipt["evidence_hashes"] != expected_evidence:
        _refuse("mixed result log or order evidence")
    return dict(sources) if hashes_valid else {}


def _summary(summary, config, config_hash, reasons):
    if summary is None:
        return {"observer_qualified": False, "strict_claim": False, "development_claim": False, "delisting_events": None}
    expected = {"study_id": STUDY, "candidate_id": config["candidate_id"], "arm": config["arm"], "cost": config["cost"],
                "config_sha256": config_hash, "freeze_sha256": FREEZE_SHA256,
                "packet_sha256": PACKET_SHA256 if config["arm"] == "tpr_on" else None,
                "canonical_admission": False, "independent_sleeve_pnl_observed": False}
    if any(key not in summary or summary[key] != value or
           (type(value) is bool and type(summary[key]) is not bool) for key, value in expected.items()):
        _refuse("cap/tilt summary identity or authority mismatch")
    required = {"decisions", "refused_decisions", "submitted_orders", "fill_events", "requested_shares", "submitted_shares",
                "filled_shares", "fees", "valuation_days", "last_valuation_session", "reason_counts",
                "max_cash_ledger_residual", "max_nav_ledger_residual", "position_ledger_mismatches", "risk_breaches",
                "sleeve_selected_decisions", "meaningful_execution", "original_no_delisting_meaningful_execution",
                "development_execution_qualified", "delisting_audit", "warmup_finished_minute_validated",
                "observed_action_custody_symbols", "registered_universe_contexts", "cap_callback_count", "cap_snapshot_count",
                "isolated_benchmark_internal_config_max", "max_name_exposure", "name_soft_cap_breaches"}
    if not required.issubset(summary):
        reasons.append("summary_accounting_incomplete")
        return {"observer_qualified": False, "strict_claim": False, "development_claim": False, "delisting_events": None}
    for flag in ("meaningful_execution", "original_no_delisting_meaningful_execution", "development_execution_qualified"):
        if type(summary[flag]) is not bool:
            _refuse("exact adapter execution flags required")
    strict_claim = summary["original_no_delisting_meaningful_execution"]
    if summary["meaningful_execution"] != strict_claim:
        _refuse("strict old execution gate was relabelled")
    if (_count(summary["decisions"]) != 14 or _count(summary["refused_decisions"]) != 0
            or _count(summary["valuation_days"]) != 60 or summary["last_valuation_session"] != END.isoformat()):
        reasons.append("summary_execution_incomplete")
    residuals = [_number(summary[key]) for key in ("max_cash_ledger_residual", "max_nav_ledger_residual")]
    if any(value < 0 for value in residuals):
        _refuse("negative accounting residual")
    if (any(value > PENNY for value in residuals) or _count(summary["position_ledger_mismatches"]) != 0
            or _count(summary["risk_breaches"]) != 0):
        reasons.append("summary_accounting_or_risk_failure")
    requested, submitted, filled = (_count(summary[key]) for key in ("requested_shares", "submitted_shares", "filled_shares"))
    if not requested >= submitted >= filled:
        _refuse("share accounting order violated")
    if summary["warmup_finished_minute_validated"] is not True:
        reasons.append("warmup_minute_subscription_validation_missing")
    if _count(summary["observed_action_custody_symbols"], 4096) <= 0:
        reasons.append("observed_action_custody_missing")
    if _count(summary["registered_universe_contexts"], 4096) != 7:
        reasons.append("native_cap_or_etf_context_inventory_incomplete")
    callbacks, snapshots = (_count(summary[key], 10000) for key in ("cap_callback_count", "cap_snapshot_count"))
    if not 0 < snapshots <= callbacks:
        reasons.append("native_cap_callback_evidence_missing_or_inconsistent")
    if _count(summary["isolated_benchmark_internal_config_max"], 4096) > 1:
        reasons.append("isolated_benchmark_subscription_inventory_invalid")
    if _number(summary["max_name_exposure"]) < 0:
        _refuse("negative name exposure")
    _count(summary["name_soft_cap_breaches"])
    counts = summary["reason_counts"]
    if type(counts) is not dict or any(type(key) is not str or not 0 < len(key) <= 128 for key in counts):
        _refuse("invalid diagnostic reason inventory")
    for value in counts.values():
        _count(value)
    events = counts.get("delisting_event", 0)
    try:
        observer_qualified = observer.validate_audit(summary["delisting_audit"], events)
    except observer.CapObserverError:
        _refuse("native delisting observer aggregate inconsistent")
    if not observer_qualified:
        reasons.append("delisting_observation_unknown_or_nonambient")
    failures = {"missing_mark", "missing_action_custody", "unpriced_held_nav", "missing_prior_close_nav",
                "qc_invalid_order", "qc_canceled_order", "delisting_target_refused"}
    if any(value and (key in failures or key.startswith("missing_") or
                      ("delist" in key.lower() and key != "delisting_event")) for key, value in counts.items()):
        reasons.append("execution_input_or_order_failure")
    if events and not observer_qualified:
        reasons.append("execution_input_or_order_failure")
    if events and strict_claim:
        _refuse("strict no-delisting gate contradicts native event count")
    if not events and not strict_claim:
        reasons.append("adapter_reports_diagnostic")
    if summary["development_execution_qualified"] is not True:
        reasons.append("prospective_adapter_reports_diagnostic")
    return {"observer_qualified": observer_qualified, "strict_claim": strict_claim,
            "development_claim": summary["development_execution_qualified"], "delisting_events": events}


def _prior_cutoff(day):
    prior = date.fromisoformat(day) - timedelta(days=1)
    while prior.weekday() >= 5 or prior in accounting.HOLIDAYS or prior == date(2025, 1, 1):
        prior -= timedelta(days=1)
    return prior, datetime(prior.year, prior.month, prior.day, 18, tzinfo=NY).astimezone(timezone.utc)


def _prior_mark_inputs(rows):
    """Bind the common selected-target prior RAW price/volume input domain.

    The runtime hashes selected target SID -> prior close/volume or explicit
    unavailable states after its native custody/source-clock checks. Holdings-
    only exits are excluded from this common construction-input comparison.
    This scalar digest does not independently attest the native market tape.
    """
    sequence = []
    for row in rows:
        day = row.get("session")
        if day not in DECISIONS:
            continue
        prior, _ = _prior_cutoff(day)
        if not _hash(row.get("prior_mark_inputs_sha256")):
            _refuse("selected-target prior mark input hash required")
        if row.get("prior_mark_session") != prior.isoformat():
            _refuse("prior mark source session outside frozen cutoff")
        sequence.append((day, row["prior_mark_session"], row["prior_mark_inputs_sha256"]))
    return _digest(sequence) if tuple(row.get("session") for row in rows) == DECISIONS else None


def _coverage(rows, config, summary, reasons):
    if tuple(row.get("session") for row in rows) != DECISIONS:
        reasons.append("coverage_schedule_incomplete_or_wrong")
    output = {}
    for row in rows:
        if row.get("arm") != config["arm"]:
            _refuse("coverage belongs to a different arm")
        day = row.get("session")
        if day not in DECISIONS:
            continue
        reports = row.get("sleeves")
        if type(reports) is not dict or set(reports) != set(ETFS):
            reasons.append("sleeve_coverage_missing")
            continue
        slots, maximum_selected = 0, 0
        for etf in ETFS:
            report = reports[etf]
            if (type(report) is not dict or not _COVERAGE_KEYS.issubset(report)
                    or not set(report) <= _COVERAGE_KEYS | _OPTIONAL_COVERAGE):
                _refuse("closed cap/tilt sleeve coverage required")
            if report["membership_available"] is not True or report["etf_fallback"] is not False:
                reasons.append("stock_membership_unavailable_or_fallback")
                continue
            if any(not _hash(report[key]) for key in
                   ("snapshot_hash", "cap_input_hash", "selected_ids_hash", "baseline_weights_hash")):
                _refuse("native cap/membership/selection/baseline hashes required")
            members, selected = _count(report["member_count"], 4096), _count(report["selected_count"], 10)
            caps = report["cap_state_counts"]
            if type(caps) is not dict or set(caps) != CAP_STATES:
                _refuse("closed cap-state inventory required")
            cap_counts = {key: _count(caps[key], 4096) for key in sorted(CAP_STATES)}
            if sum(cap_counts.values()) != members or selected != min(10, cap_counts["available"]):
                reasons.append("cap_state_partition_or_selection_count_mismatch")
            scores = report["score_state_counts"]
            states = SCORE_STATES if config["arm"] == "tpr_on" else {"not_used"}
            if type(scores) is not dict or set(scores) != states:
                _refuse("closed standalone score-state inventory required")
            score_counts = {key: _count(scores[key], 10) for key in sorted(states)}
            ranked = _count(report["ranked_score_count"], 10)
            if sum(score_counts.values()) != selected or ranked != (score_counts["nonzero"] if config["arm"] == "tpr_on" else 0):
                reasons.append("selected_score_partition_or_rank_count_mismatch")
            prior, cutoff = _prior_cutoff(day)
            effective, received = (_clock(report[key]).astimezone(timezone.utc) for key in ("effective_utc", "received_utc"))
            if not (effective <= received <= cutoff and cutoff - timedelta(days=21) <= effective <= cutoff - timedelta(days=7)):
                reasons.append("membership_clock_outside_frozen_cutoff")
            cap_asof, cap_effective, cap_received = (_clock(report[key]).astimezone(timezone.utc)
                for key in ("cap_asof_time", "cap_effective_utc", "cap_received_utc"))
            if not (cap_asof <= cap_effective <= cap_received <= cutoff and cap_effective.astimezone(NY).date() == prior):
                reasons.append("cap_clock_outside_prior_session_cutoff")
            baseline, target, cash, moved, underfill, blocked = (_number(report[key]) for key in
                ("baseline_weight", "target_weight", "cash_weight", "transferred_weight", "recipient_underfill", "aggregate_cap_blocked_capacity"))
            expected_base = Fraction(selected, 60)
            if (any(value < 0 for value in (baseline, target, cash, moved, underfill, blocked))
                    or abs(baseline - expected_base) > DISPLAY_TOLERANCE
                    or abs(target - baseline) > DISPLAY_TOLERANCE
                    or abs(cash - (Fraction(1, 6) - baseline)) > DISPLAY_TOLERANCE
                    or target > Fraction(1, 6) + DISPLAY_TOLERANCE
                    or moved + underfill > baseline * Fraction(1, 5) + DISPLAY_TOLERANCE
                    or blocked > underfill + DISPLAY_TOLERANCE):
                reasons.append("sleeve_budget_or_transfer_conservation_failure")
            binding = _count(report["cap_binding_recipient_count"], 10)
            if binding > selected:
                _refuse("cap binding count exceeds selected identities")
            if config["arm"] == "tpr_off" and any(value != 0 for value in (moved, underfill, blocked, binding)):
                reasons.append("neutral_control_contains_tpr_transfer")
            if "eligible_count" in report and _count(report["eligible_count"], 4096) != cap_counts["available"]:
                reasons.append("cap_eligible_count_mismatch")
            if "unfilled_slots" in report and _count(report["unfilled_slots"], 10) != 10 - selected:
                reasons.append("fixed_slot_cash_count_mismatch")
            if "maximum_absolute_relative_change" in report:
                change = _number(report["maximum_absolute_relative_change"])
                limit = Fraction(1, 5) if config["arm"] == "tpr_on" else Fraction(0)
                if not 0 <= change <= limit + DISPLAY_TOLERANCE:
                    reasons.append("own_baseline_tilt_band_failure")
            transfers = _count(report["transfer_count"], 100) if "transfer_count" in report else None
            if config["arm"] == "tpr_off" and transfers not in (None, 0):
                reasons.append("neutral_control_contains_tpr_transfer")
            slots += selected
            maximum_selected = max(maximum_selected, selected)
            group = output.setdefault(etf, {"selected_counts": [], "member_counts": [], "cap_state_counts": {}, "score_state_counts": {},
                "transferred_weight": Fraction(0), "recipient_underfill": Fraction(0), "aggregate_cap_blocked_capacity": Fraction(0),
                "cap_binding_recipient_count": 0, "transfer_count": 0, "transfer_count_complete": True,
                **{name + "_sequence": [] for name in _SEQUENCES}})
            group["selected_counts"].append(selected)
            group["member_counts"].append(members)
            for key, values in (("cap_state_counts", cap_counts), ("score_state_counts", score_counts)):
                for state, count in values.items():
                    group[key][state] = group[key].get(state, 0) + count
            for key, value in (("transferred_weight", moved), ("recipient_underfill", underfill), ("aggregate_cap_blocked_capacity", blocked)):
                group[key] += value
            group["cap_binding_recipient_count"] += binding
            group["transfer_count_complete"] &= transfers is not None
            group["transfer_count"] += transfers if transfers is not None else 0
            group["membership_snapshot_sequence"].append((day, report["snapshot_hash"], report["effective_utc"], report["received_utc"]))
            group["cap_input_sequence"].append((day, report["cap_input_hash"], report["cap_asof_time"], report["cap_effective_utc"], report["cap_received_utc"]))
            group["selected_ids_sequence"].append((day, report["selected_ids_hash"], selected))
            group["baseline_weights_sequence"].append((day, report["baseline_weights_hash"], report["baseline_weight"], report["cash_weight"]))
        if all(key in row for key in ("consolidated_selected_count", "target_gross", "unallocated_target_cash")):
            consolidated = _count(row["consolidated_selected_count"], 60)
            gross, cash = _number(row["target_gross"]), _number(row["unallocated_target_cash"])
            if (not maximum_selected <= consolidated <= slots or abs(gross - Fraction(slots, 60)) > DISPLAY_TOLERANCE
                    or abs(cash - (1 - gross)) > DISPLAY_TOLERANCE):
                reasons.append("consolidated_fixed_slot_budget_mismatch")
        else:
            reasons.append("consolidated_fixed_slot_budget_missing")
    for etf in ETFS:
        if etf not in output:
            output[etf] = None
            continue
        group = output[etf]
        selected, members = group.pop("selected_counts"), group.pop("member_counts")
        for name in _SEQUENCES:
            group[name + "_sequence_sha256"] = _digest(group.pop(name + "_sequence"))
        group["observed_decisions"] = len(selected)
        group["selected_decisions"] = sum(value > 0 for value in selected)
        group["zero_selection_diagnostic"] = not any(selected)
        group["selected_min_mean_max"] = [min(selected), _text(Fraction(sum(selected), len(selected))), max(selected)]
        group["members_min_max"] = [min(members), max(members)]
        group["covered_subset_only"] = True
        group["historical_publication_availability_attested"] = False
        for key in ("transferred_weight", "recipient_underfill", "aggregate_cap_blocked_capacity"):
            group[key] = _text(group[key])
        complete_transfers = group.pop("transfer_count_complete")
        if not complete_transfers:
            group["transfer_count"] = None
        if summary is not None and "sleeve_selected_decisions" in summary:
            claimed = summary["sleeve_selected_decisions"]
            if type(claimed) is not dict or set(claimed) != set(ETFS):
                reasons.append("sleeve_summary_incomplete")
            elif _count(claimed[etf], 14) != group["selected_decisions"]:
                reasons.append("sleeve_selection_summary_mismatch")
    return output


def audit_result(result_response, logs_response, order_pages, source_receipt, candidate_config):
    """Audit new evidence only; all response inventories stay hash-bound intact."""
    config_hash = _config(candidate_config)
    if type(order_pages) is not list:
        _refuse("order page list required")
    reasons = []
    receipt = source_receipt if type(source_receipt) is dict else {}
    source_hashes = _source(source_receipt, candidate_config, config_hash, result_response, logs_response, order_pages, reasons)
    result, stats = {}, {}
    if (type(result_response) is not dict or result_response.get("success") is not True
            or type(result_response.get("backtest")) is not dict):
        reasons.append("backtest_response_unavailable")
    else:
        result = result_response["backtest"]
        stats = result.get("statistics") if type(result.get("statistics")) is dict else {}
        if receipt.get("backtest_id") in (None, ""):
            reasons.append("result_identity_unverified")
        elif result.get("backtestId") != receipt["backtest_id"]:
            _refuse("result belongs to a different backtest")
        if "projectId" in result and receipt.get("project_id") not in (None, "") and result["projectId"] != receipt["project_id"]:
            _refuse("result belongs to a different project")
        if (result.get("completed") is not True or _number(result.get("progress", "0")) != 1
                or "error" not in result or result["error"] is not None or result.get("status") not in ("Completed", "Completed.")):
            reasons.append("backtest_not_successfully_completed")
    summary, nav_rows, coverage_rows = accounting._logs(logs_response, reasons)
    summary_proof = _summary(summary, candidate_config, config_hash, reasons)
    orders = accounting._orders(order_pages, receipt, summary, stats, candidate_config, reasons)
    metrics = accounting._nav(nav_rows, summary, stats, reasons)
    mark_input_sequence = _prior_mark_inputs(coverage_rows)
    coverage = _coverage(coverage_rows, candidate_config, summary, reasons)
    development_qualified = not reasons
    strict_reasons = list(reasons)
    if summary_proof["delisting_events"]:
        strict_reasons.extend(("execution_input_or_order_failure", "adapter_reports_diagnostic"))
    if not summary_proof["strict_claim"]:
        strict_reasons.append("adapter_reports_diagnostic")
    strict_meaningful = not strict_reasons
    if metrics is not None:
        if orders["fill_notional"] is not None:
            metrics["absolute_fill_notional_turnover_initial_nav"] = _text(_number(orders["fill_notional"]) / INITIAL)
        headline = stats.get("Drawdown")
        if headline is not None:
            if type(headline) not in (str, int, float):
                _refuse("bounded native drawdown statistic required")
            _number(str(headline).removesuffix("%"))
        metrics["qc_headline_drawdown"] = headline
        metrics["drawdown_sampling_reconciled"] = False
        if summary is not None and "max_name_exposure" in summary:
            metrics["max_name_exposure"] = _text(_number(summary["max_name_exposure"]))
        metrics["name_soft_cap_breaches"] = summary.get("name_soft_cap_breaches") if summary is not None else None
    shortfall = None
    if summary is not None and all(key in summary for key in ("requested_shares", "submitted_shares")):
        shortfall = _count(summary["requested_shares"]) - _count(summary["submitted_shares"])
    terminal = result.get("status")
    terminal = terminal if type(terminal) is str and re.fullmatch(r"[A-Za-z][A-Za-z ._-]{0,63}", terminal) else None
    project_id = receipt.get("project_id")
    project_id = project_id if type(project_id) is int and project_id > 0 else None
    return {"schema": "tpr-qc-cap-tilt-audit-v1", "study_id": STUDY, "candidate_id": candidate_config["candidate_id"],
            "arm": candidate_config["arm"], "cost": candidate_config["cost"], "project_id": project_id,
            "compile_id": _identifier(receipt.get("compile_id")), "backtest_id": _identifier(receipt.get("backtest_id")), "config_sha256": config_hash,
            "freeze_sha256": FREEZE_SHA256, "packet_sha256": PACKET_SHA256 if candidate_config["arm"] == "tpr_on" else None,
            "source_hashes": source_hashes, "terminal_status": terminal, "meaningful_execution": strict_meaningful,
            "original_no_delisting_meaningful_execution": strict_meaningful, "development_execution_qualified": development_qualified,
            "delisting_observer_qualified": summary_proof["observer_qualified"], "delisting_events": summary_proof["delisting_events"],
            "diagnostic_reasons": sorted(set(reasons)), "original_diagnostic_reasons": sorted(set(strict_reasons)),
            "orders": orders, "metrics": metrics, "coverage_by_sleeve": coverage, "requested_minus_submitted_shares": shortfall,
            "prior_mark_input_sequence_sha256": mark_input_sequence,
            "valuation_observations": len(nav_rows), "decision_coverage_observations": len(coverage_rows),
            "canonical_admission": False, "independent_sleeve_pnl_observed": False,
            "numerical_convention": "Exact decimal-text rational money; 48-digit runtime/50-digit audit display ratios with 1e-45 display-only tolerance; floats only sqrt/exponent statistical metrics; 60 daily returns include initial100000; CAGR88 observed calendar days; Sharpe risk-free0; partial2025 only; QC drawdown sampling unreconciled."}


def analyze_operation(result_response, logs_response, order_pages, source_receipt, candidate_config):
    """Explicit pure alias; never fetches an operation or invokes its driver."""
    return audit_result(result_response, logs_response, order_pages, source_receipt, candidate_config)


def analyze_pair(tpr_on, tpr_off):
    """Compare qualified ON/OFF only after all four frozen input paths match."""
    reasons = []
    for evidence, arm in ((tpr_on, "tpr_on"), (tpr_off, "tpr_off")):
        policy = {"schema": "tpr-qc-cap-tilt-config-v1", "study_id": STUDY, "freeze_sha256": FREEZE_SHA256,
                  "candidate_id": next(row[0] for row in CANDIDATES if row[1] == arm),
                  "arm": arm, "cost": "baseline", "slippage": "0.001"}
        if (type(evidence) is not dict or evidence.get("schema") != "tpr-qc-cap-tilt-audit-v1"
                or evidence.get("study_id") != STUDY or evidence.get("freeze_sha256") != FREEZE_SHA256
                or evidence.get("arm") != arm or evidence.get("cost") != "baseline"
                or evidence.get("candidate_id") != policy["candidate_id"] or evidence.get("config_sha256") != _digest(policy)
                or evidence.get("canonical_admission") is not False or evidence.get("independent_sleeve_pnl_observed") is not False):
            _refuse("different study or unmatched comparison role")
        if evidence.get("development_execution_qualified") is not True:
            reasons.append(arm + "_execution_not_qualified")
        if evidence.get("valuation_observations") != 60 or evidence.get("decision_coverage_observations") != 14:
            reasons.append(arm + "_comparison_observations_incomplete")
    matching = True
    first_marks, second_marks = (evidence.get("prior_mark_input_sequence_sha256") for evidence in (tpr_on, tpr_off))
    if not _hash(first_marks) or first_marks != second_marks:
        reasons.append("unmatched_prior_mark_inputs")
        matching = False
    if any(type(evidence.get("coverage_by_sleeve")) is not dict for evidence in (tpr_on, tpr_off)):
        _refuse("explicit pair coverage inventory required")
    for etf in ETFS:
        first, second = (evidence.get("coverage_by_sleeve", {}).get(etf) for evidence in (tpr_on, tpr_off))
        if type(first) is not dict or type(second) is not dict or first.get("observed_decisions") != 14 or second.get("observed_decisions") != 14:
            reasons.append("comparison_coverage_incomplete_" + etf)
            matching = False
            continue
        for name in _SEQUENCES:
            key = name + "_sequence_sha256"
            if not _hash(first.get(key)) or first[key] != second.get(key):
                reasons.append("unmatched_" + name + "_" + etf)
                matching = False
    qualified = not reasons
    metrics = {}
    if qualified:
        if type(tpr_on.get("metrics")) is not dict or type(tpr_off.get("metrics")) is not dict:
            _refuse("qualified pair requires interpreted accounting metrics")
        for key in ("return_pct", "daily_drawdown_pct"):
            metrics[key + "_difference_percentage_points"] = _text(
                _number(tpr_on["metrics"][key]) - _number(tpr_off["metrics"][key]))
    return {"schema": "tpr-qc-cap-tilt-pair-audit-v1", "study_id": STUDY, "freeze_sha256": FREEZE_SHA256,
            "matched_inputs": matching, "matched_comparison_qualified": qualified, "diagnostic_reasons": sorted(set(reasons)),
            "tpr_on_backtest_id": tpr_on.get("backtest_id"), "tpr_off_backtest_id": tpr_off.get("backtest_id"),
            "matched_observation_count": 60 if qualified else None, "difference_metrics": metrics,
            "independent_sleeve_pnl_observed": False, "canonical_admission": False,
            "confirmatory_alpha": "0", "exploratory_adaptive_correlated_study": True}
