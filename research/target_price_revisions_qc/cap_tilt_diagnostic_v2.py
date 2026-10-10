"""Pure observed-coverage labels over the immutable unqualified reporter.

Full 60-day native NAV/order metrics keep their original accounting calendar.
A partial decision-coverage subset is never completed, renormalized, treated
as zero input, or used to make an execution/alpha gate true. No I/O or pair
delta. The original five evidence objects pass untouched to diagnostic v1.
"""
from __future__ import annotations

from . import cap_tilt_diagnostic as original

AuditError = original.AuditError
cap = original.cap
_PATHS = ("membership_snapshot", "cap_input", "selected_ids", "baseline_weights")


def _observed_prior_mark_inputs(rows):
    """Validate only the explicitly observed, ordered frozen-date subset."""
    if type(rows) is not list or not 1 <= len(rows) <= len(cap.DECISIONS):
        cap._refuse("nonempty bounded observed decision coverage required")
    days = tuple(row.get("session") if type(row) is dict else None for row in rows)
    if any(type(day) is not str or day not in cap.DECISIONS for day in days):
        cap._refuse("observed coverage session outside frozen decisions")
    if len(set(days)) != len(days):
        cap._refuse("duplicate observed decision coverage")
    if days != tuple(day for day in cap.DECISIONS if day in set(days)):
        cap._refuse("observed decision coverage order ambiguous")
    sequence = []
    for row, day in zip(rows, days):
        prior, _ = cap._prior_cutoff(day)
        if not cap._hash(row.get("prior_mark_inputs_sha256")):
            cap._refuse("observed selected-target prior mark input hash required")
        if row.get("prior_mark_session") != prior.isoformat():
            cap._refuse("observed prior mark source session outside frozen cutoff")
        sequence.append((day, row["prior_mark_session"], row["prior_mark_inputs_sha256"]))
    return days, cap._digest(sequence)


def diagnose_result(result_response, logs_response, order_pages, source_receipt, candidate_config):
    """Add truthful partial-coverage metadata; preserve every v1 gate/value."""
    evidence = original.diagnose_result(result_response, logs_response, order_pages, source_receipt, candidate_config)
    # Original source/evidence binding precedes decoding. No receipt or raw
    # response is rewritten; the same strict decoder creates only a derivative.
    decoded, _ = original._decoded_logs(logs_response)
    _, _, rows = original.accounting._logs(decoded, [])
    days, observed_marks = _observed_prior_mark_inputs(rows)
    missing = tuple(day for day in cap.DECISIONS if day not in days)
    complete_hash = evidence["prior_mark_input_sequence_sha256"]
    if ((missing and complete_hash is not None)
            or (not missing and complete_hash != observed_marks)):
        cap._refuse("complete and observed prior mark paths inconsistent")
    paths = {}
    for etf in cap.ETFS:
        group = evidence["coverage_by_sleeve"][etf]
        paths[etf] = (None if group is None else {
            "observed_decision_count": group["observed_decisions"],
            **{name + "_sequence_sha256": group[name + "_sequence_sha256"] for name in _PATHS}})
    return {**evidence, "schema": "tpr-qc-cap-tilt-diagnostic-v2",
        "observed_decision_dates": list(days), "missing_frozen_decision_dates": list(missing),
        "observed_coverage_sessions_sha256": cap._digest(list(days)),
        "observed_prior_mark_input_sequence_sha256": observed_marks,
        "observed_prior_mark_decision_count": len(days),
        "complete_frozen_decision_coverage": not missing,
        "observed_coverage_input_paths_by_sleeve": paths,
        "coverage_provenance": "Only explicitly observed logged decisions; missing dates are not reconstructed or zero inputs. Complete-14 prior-mark hash is None for partial coverage. Observed-subset hashes do not attest native input tapes or historical publication availability. Full 60-day NAV/order metrics remain unqualified; no pair delta or alpha claim."}
