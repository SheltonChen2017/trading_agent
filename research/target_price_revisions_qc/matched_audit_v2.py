"""Pure warm-up/custody audit successor; executed v1 audit stays unchanged."""
from __future__ import annotations

from . import matched_audit as base


def audit_result(result_response, logs_response, order_pages, source_receipt, candidate_config):
    """Retain every v1 reconciliation and additionally require v2 runtime proof.

    Metadata claims do not independently attest subscription custody; they are
    required runtime evidence in addition to the original source/order/NAV
    checks. Missing evidence stays unknown rather than becoming a zero count.
    """
    evidence = base.audit_result(result_response, logs_response, order_pages,
                                 source_receipt, candidate_config)
    summary, _, _ = base._logs(logs_response, [])
    summary = summary if summary is not None else {}
    extra_reasons = []
    warmup_validated = summary.get("warmup_finished_minute_validated") is True
    if not warmup_validated:
        extra_reasons.append("warmup_minute_subscription_validation_missing")
    observed = summary.get("observed_action_custody_symbols")
    positive_custody = type(observed) is int and observed > 0
    if not positive_custody:
        extra_reasons.append("observed_action_custody_missing")
    if summary.get("meaningful_execution") is not True:
        extra_reasons.append("successor_adapter_reports_diagnostic")
    evidence["base_audit_schema"] = evidence["schema"]
    evidence["schema"] = "tpr-qc-matched-audit-v2"
    evidence["warmup_finished_minute_validated"] = warmup_validated
    evidence["observed_action_custody_symbols"] = observed if type(observed) is int and observed >= 0 else None
    evidence["diagnostic_reasons"] = sorted(set(evidence["diagnostic_reasons"] + extra_reasons))
    evidence["meaningful_execution"] = evidence["meaningful_execution"] and not extra_reasons
    return evidence
