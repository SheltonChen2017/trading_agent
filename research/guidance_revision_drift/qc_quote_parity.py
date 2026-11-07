"""Offline comparison of QC-native and paired historical quote inputs.

This compares structural selections, not provider clocks, market coverage,
NBBO authenticity, fills or performance. Refusal on both inputs is observable
agreement, never usable-input parity. No SDK, network or order path is called.
"""
from __future__ import annotations

from datetime import datetime

from research.guidance_revision_drift.historical_market import (
    HistoricalMarketBatch, instant_ns,
)
from research.guidance_revision_drift.input_contracts import InputError
from research.guidance_revision_drift.qc_native_quotes import QcNativeQuoteBatch


def _quote_values(quote) -> tuple:
    # Native event/side clocks and Massive SIP/participant clocks stay distinct.
    # Only the economic fields shared by both input contracts are comparable.
    return quote.bid, quote.ask, quote.bid_size, quote.ask_size


def _minute_values(minute) -> tuple:
    return (minute.start_timestamp_ns, minute.end_timestamp_ns, minute.open,
            minute.high, minute.low, minute.close, minute.volume)


def _observe(batch, decision_at: datetime, submitted_at: datetime,
             callback_at: datetime) -> tuple:
    decision = None
    try:
        decision = batch.decision_quote(decision_at)
    except InputError:
        pass
    execution = None
    try:
        execution = batch.subsequent_minute(submitted_at=submitted_at,
            callback_at=callback_at, decision_quote=decision)
    except InputError:
        pass
    return decision, execution


def compare_native_quote_parity(native: QcNativeQuoteBatch,
                                massive: HistoricalMarketBatch, *,
                                decision_at: datetime, submitted_at: datetime,
                                callback_at: datetime) -> dict:
    """Compare exact supplied sources; return hashes, statuses and match flags.

    Both stages are checked independently, including the subsequent interval
    when the decision refuses. ``matched_refusals`` means at least one stage
    refused on both sources and every comparable stage matched; it is never
    usable-input parity. Successful comparison does not qualify a native
    source or admit it to the order runner. No source rows or prices are emitted.
    """
    if type(native) is not QcNativeQuoteBatch or type(massive) is not HistoricalMarketBatch:
        raise InputError("exact native and paired historical batches required")
    native = QcNativeQuoteBatch.from_bytes(native.raw_bytes)
    massive = HistoricalMarketBatch.from_bytes(massive.raw_bytes)
    identity = ("security_id", "symbol", "role", "session_date",
                "session_open_utc", "session_close_utc")
    if any(getattr(native, key) != getattr(massive, key) for key in identity):
        raise InputError("parity inputs must share the exact security and session")
    decision_ns, submitted_ns, callback_ns = (
        instant_ns(value) for value in (decision_at, submitted_at, callback_at))
    if not decision_ns <= submitted_ns < callback_ns:
        raise InputError("parity decision submission callback order required")

    native_decision, native_execution = _observe(native, decision_at, submitted_at, callback_at)
    massive_decision, massive_execution = _observe(massive, decision_at, submitted_at, callback_at)
    mismatches = []
    checks = {}
    for name, left, right in (("decision", native_decision, massive_decision),
                              ("execution", native_execution, massive_execution)):
        acceptance_match = (left is not None) == (right is not None)
        values_match = None
        if not acceptance_match:
            mismatches.append(name + "_acceptance")
        elif left is not None:
            values_match = (_quote_values(left if name == "decision" else left.quote)
                            == _quote_values(right if name == "decision" else right.quote))
            if not values_match:
                mismatches.append(name + "_quote_values")
        checks[name] = {"native_status": "accepted" if left is not None else "refused",
                        "paired_status": "accepted" if right is not None else "refused",
                        "acceptance_match": acceptance_match,
                        "quote_values_match": values_match}
    minute_match = capacity_match = None
    if native_execution is not None and massive_execution is not None:
        minute_match = _minute_values(native_execution.minute) == _minute_values(massive_execution.minute)
        capacity_match = (native_execution.minute.volume // 100
                          == massive_execution.minute.volume // 100)
        if not minute_match:
            mismatches.append("execution_minute_values")
        if not capacity_match:
            mismatches.append("execution_minute_capacity")
    usable = not mismatches and all(value is not None for value in (
        native_decision, massive_decision, native_execution, massive_execution))
    return {"schema": "gdr.qc-native-quote-parity.v1",
            "scope": "offline_structural_inputs_only",
            "status": "mismatch" if mismatches else (
                "matched_usable_inputs" if usable else "matched_refusals"),
            "native_source_sha256": native.sha256,
            "paired_source_sha256": massive.sha256,
            "decision_at_ns": decision_ns,
            "submitted_at_ns": submitted_ns,
            "callback_at_ns": callback_ns,
            "checks": checks, "execution_minute_values_match": minute_match,
            "execution_minute_capacity_match": capacity_match,
            "mismatches": mismatches, "usable_input_parity": usable,
            "clock_equivalence_verified": False, "nbbo_verified": False,
            "coverage_verified": False, "point_in_time_data": False,
            "native_execution_evidence": False, "backtest_ready": False,
            "execution_authority": False}
