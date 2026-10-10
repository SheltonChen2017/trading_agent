"""Pure terminal-spelling successor; executed v1/v2 evidence stays unchanged."""
from __future__ import annotations

from . import matched_audit as base, matched_audit_v2 as previous


def audit_result(result_response, logs_response, order_pages, source_receipt, candidate_config):
    """Retain v2 checks and admit only QC's concrete ``Completed.`` spelling.

    Original result/log/order inventories and their source bindings pass to
    v2 unchanged. Only its terminal-spelling diagnostic can be removed, after
    the same completed/progress/error guards pass. Every other diagnostic,
    including adapter refusal and unexplained delisting, remains binding.
    This parser correction is not new execution or canonical acceptance.
    """
    evidence = previous.audit_result(result_response, logs_response, order_pages,
                                     source_receipt, candidate_config)
    result = (result_response["backtest"] if type(result_response) is dict
              and result_response.get("success") is True
              and type(result_response.get("backtest")) is dict else {})
    if (type(result.get("status")) is str and result["status"] == "Completed."
            and result.get("completed") is True
            and base._number(result.get("progress", "0")) == 1
            and result.get("error") is None):
        prior_reasons = evidence["diagnostic_reasons"]
        terminal_reason = "backtest_not_successfully_completed"
        evidence["diagnostic_reasons"] = [reason for reason in prior_reasons
                                          if reason != terminal_reason]
        evidence["meaningful_execution"] = (evidence["meaningful_execution"]
                                            or prior_reasons == [terminal_reason])
    evidence["previous_audit_schema"] = evidence["schema"]
    evidence["schema"] = "tpr-qc-matched-audit-v3"
    return evidence
