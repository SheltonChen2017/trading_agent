"""No-order diagnostic for a *claimed* common forward predecision input.

Caller-supplied hash pins and pre-cutoff clock fields check internal input
consistency; they cannot authenticate independent origin, vendor publication
time or crosswalk authority. A valid diagnostic is never decision-ready or
paper authority.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, time, timezone
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from zoneinfo import ZoneInfo

from research.analyst_revisions_v2 import forward_data_quality as vendor_quality
from research.analyst_revisions_v2.canonical import (
    CanonicalEvidenceError, parse_date, require_sha256, strict_json_loads,
)

from . import six_universe_forward_construction_policy as construction_policy


class ForwardPredecisionError(ValueError):
    """A supplied byte pin, clock, exact identity or safety gate refused."""


SCHEMA = "arv2-six-forward-predecision-diagnostic-v1"
MAPPING_SCHEMA = "arv2-six-forward-claimed-crosswalk-v1"
PRICE_SCHEMA = "arv2-six-forward-reference-price-diagnostic-v1"
MAX_INPUT_BYTES = 8_000_000
ETFS = ("SPY", "QQQ", "SOXX", "XLV", "REMX", "XLE")
SOURCES = ("FUNDAMENTALS",) + ETFS
NEW_YORK = ZoneInfo("America/New_York")
_REFUSALS = (
    "VENDOR_PUBLICATION_AVAILABILITY_UNPROVEN",
    "CROSSWALK_INDEPENDENT_REVIEW_UNPROVEN",
    "REFERENCE_PRICE_PROVENANCE_UNPROVEN",
    "PRICE_FRESHNESS_UNPROVEN",
)


@dataclass(frozen=True, slots=True)
class ArmInputBinding:
    candidate_id: str
    common_input_sha256: str


@dataclass(frozen=True, slots=True)
class PredecisionDiagnostic:
    schema: str
    decision_session: str
    common_input_sha256: str
    arms: tuple[ArmInputBinding, ArmInputBinding, ArmInputBinding]
    refusal_codes: tuple[str, ...]
    decision_ready: bool = False
    order_or_outcome_access: bool = False


def _refuse(code):
    raise ForwardPredecisionError(code)


def _keys(value, expected, code):
    if type(value) is not dict or set(value) != set(expected):
        _refuse(code)


def _pinned_json(payload, expected_sha256, name):
    try:
        require_sha256(expected_sha256, name + " SHA-256")
    except CanonicalEvidenceError as exc:
        raise ForwardPredecisionError(name + "_SHA256_INVALID") from exc
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_INPUT_BYTES:
        _refuse(name + "_BYTES_INVALID")
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        _refuse(name + "_SHA256_MISMATCH")
    try:
        value = strict_json_loads(payload.decode("ascii"), name)
        canonical = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("ascii")
    except (UnicodeError, TypeError, ValueError) as exc:
        raise ForwardPredecisionError(name + "_JSON_INVALID") from exc
    if payload != canonical:
        _refuse(name + "_NONCANONICAL")
    return value


def _instant(value, code):
    if type(value) is not str:
        _refuse(code)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        _refuse(code)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _refuse(code)
    return parsed.astimezone(timezone.utc)


def _session_date(value, code):
    try:
        return parse_date(value, code)
    except CanonicalEvidenceError as exc:
        raise ForwardPredecisionError(code) from exc


def _positive(value, code):
    if type(value) is not str:
        _refuse(code)
    # The QC snapshot producer emits fixed-point text. Bound its scale before
    # Fraction conversion so a tiny exponent cannot allocate an enormous
    # denominator from a short, caller-supplied JSON string.
    parts = value.split(".")
    if (len(value) > 128 or len(parts) > 2
            or any(not part or not part.isascii() or not part.isdigit() for part in parts)):
        _refuse(code)
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        _refuse(code)
    if not parsed.is_finite() or parsed <= 0:
        _refuse(code)
    return parsed


def _pairs(value, code):
    if type(value) is not list:
        _refuse(code)
    result = {}
    for pair in value:
        if (type(pair) is not list or len(pair) != 2 or type(pair[0]) is not str
                or not pair[0] or pair[0] in result):
            _refuse(code)
        result[pair[0]] = _positive(pair[1], code)
    return result


def _qc_snapshot(value, session, cutoff):
    _keys(value, {
        "schema", "decision_session", "qc_decision_time_ny", "capture_time_utc",
        "naive_qc_times_interpreted_as", "qc_callback_is_vendor_availability_time",
        "point_in_time_vendor_availability_proven", "decision_ready",
        "order_and_outcome_access", "qcom_exact_sid_status",
        "superseded_degenerate_callback_count_by_source",
        "superseded_degenerate_callback_count", "sources",
    }, "QC_SNAPSHOT_SHAPE_CHANGED")
    if (value["schema"] != "arv2-fresh-six-universe-input-snapshot-v1"
            or value["decision_session"] != session
            or value["naive_qc_times_interpreted_as"] != "America/New_York"
            or value["qc_callback_is_vendor_availability_time"] is not False
            or value["point_in_time_vendor_availability_proven"] is not False
            or value["decision_ready"] is not False
            or value["order_and_outcome_access"] is not False):
        _refuse("QC_SNAPSHOT_AUTHORITY_CHANGED")
    if _instant(value["qc_decision_time_ny"], "QC_DECISION_CLOCK_INVALID") != cutoff:
        _refuse("QC_DECISION_CLOCK_CHANGED")
    # This is the backtest artifact's acquisition time, which may be later
    # than the decision. Parse it, but never use it as vendor availability.
    _instant(value["capture_time_utc"], "QC_CAPTURE_CLOCK_INVALID")
    sources = value["sources"]
    if type(sources) is not dict or set(sources) != set(SOURCES):
        _refuse("QC_SOURCE_CENSUS_CHANGED")
    counts = value["superseded_degenerate_callback_count_by_source"]
    if (type(counts) is not dict or set(counts) != set(SOURCES)
            or any(type(count) is not int or count < 0 for count in counts.values())
            or type(value["superseded_degenerate_callback_count"]) is not int
            or value["superseded_degenerate_callback_count"] != sum(counts.values())):
        _refuse("QC_SUPERSEDED_CALLBACK_CENSUS_CHANGED")
    caps = {}
    members = {}
    displayed_qcom = set()
    for source in SOURCES:
        row = sources[source]
        if type(row) is not dict or row.get("collection_status") != "valid" or row.get("degenerate_reason") is not None:
            _refuse("QC_SOURCE_INVALID_OR_DEGENERATE")
        common = {
            "qc_source_end_time_ny", "qc_callback_time_ny", "collection_status",
            "degenerate_reason", "diagnostic_raw_end_time_calendar_lag_days",
            "source_row_count",
        }
        specific = ({"null_market_cap_count", "nonpositive_market_cap_count",
                     "invalid_market_cap_count", "positive_market_caps"}
                    if source == "FUNDAMENTALS" else
                    {"positive_constituents", "display_qcom_sids"})
        _keys(row, common | specific, "QC_SOURCE_SHAPE_CHANGED")
        if (type(row["source_row_count"]) is not int
                or not 1 <= row["source_row_count"] <= 25_000
                or type(row["diagnostic_raw_end_time_calendar_lag_days"]) is not int
                or row["diagnostic_raw_end_time_calendar_lag_days"] < 0):
            _refuse("QC_SOURCE_CENSUS_INVALID")
        callback = _instant(row["qc_callback_time_ny"], "QC_CALLBACK_CLOCK_INVALID")
        source_end = _instant(row["qc_source_end_time_ny"], "QC_SOURCE_END_CLOCK_INVALID")
        if callback >= cutoff or source_end >= cutoff:
            _refuse("QC_SOURCE_NOT_PREDECISION")
        if source_end > callback:
            _refuse("QC_SOURCE_END_FOLLOWS_CALLBACK")
        actual_lag = (
            _session_date(session, "DECISION_SESSION_INVALID")
            - source_end.astimezone(NEW_YORK).date()
        ).days
        if (row["diagnostic_raw_end_time_calendar_lag_days"] != actual_lag
                or not 0 <= actual_lag <= (4 if source == "FUNDAMENTALS" else 10)):
            _refuse("QC_DIAGNOSTIC_SOURCE_AGE_CHANGED")
        if source == "FUNDAMENTALS":
            caps = _pairs(row.get("positive_market_caps"), "QC_CAP_ROWS_INVALID")
            if not caps:
                _refuse("QC_VALID_FUNDAMENTALS_HAVE_NO_POSITIVE_CAP")
            other_counts = (
                row["null_market_cap_count"], row["nonpositive_market_cap_count"],
                row["invalid_market_cap_count"],
            )
            if (any(type(count) is not int or count < 0 for count in other_counts)
                    or row["source_row_count"] != len(caps) + sum(other_counts)):
                _refuse("QC_FUNDAMENTAL_ROW_CENSUS_CHANGED")
        else:
            members[source] = _pairs(row.get("positive_constituents"), "QC_MEMBER_ROWS_INVALID")
            hints = row.get("display_qcom_sids")
            if type(hints) is not list or any(type(sid) is not str or not sid for sid in hints):
                _refuse("QC_QCOM_HINTS_INVALID")
            if row["source_row_count"] < len(members[source]):
                _refuse("QC_MEMBER_ROW_CENSUS_CHANGED")
            if row["source_row_count"] > len(members[source]):
                _refuse("ETF_UNWEIGHTED_CONSTITUENT_ROWS_UNRESOLVED")
            displayed_qcom.update(hints)
            total = sum((Fraction(weight) for weight in members[source].values()), Fraction(0))
            if not Fraction(95, 100) <= total <= Fraction(105, 100):
                _refuse("ETF_TOTAL_REPORTED_WEIGHT_INVALID")
    qcom_status = (
        "not_observed" if not displayed_qcom else
        "conflicting_display_sids" if len(displayed_qcom) > 1 else
        "joined" if displayed_qcom <= caps.keys() else
        "unmatched_positive_cap"
    )
    if value["qcom_exact_sid_status"] != qcom_status:
        _refuse("QC_QCOM_STATUS_CHANGED")
    return caps, members, displayed_qcom


def _crosswalk(value, session, cutoff, qc_sha256, vendor_sha256):
    _keys(value, {
        "schema", "decision_session", "qc_snapshot_sha256",
        "vendor_receipt_sha256", "qcom_qc_sid", "rows",
    }, "CROSSWALK_SHAPE_CHANGED")
    if (value["schema"] != MAPPING_SCHEMA or value["decision_session"] != session
            or value["qc_snapshot_sha256"] != qc_sha256
            or value["vendor_receipt_sha256"] != vendor_sha256):
        _refuse("CROSSWALK_INPUT_BINDING_CHANGED")
    qcom = value["qcom_qc_sid"]
    if qcom is not None and (type(qcom) is not str or not qcom):
        _refuse("QCOM_EXACT_SID_INVALID")
    rows = value["rows"]
    if type(rows) is not list:
        _refuse("CROSSWALK_ROWS_INVALID")
    by_sid = {}
    vendors = set()
    for row in rows:
        _keys(row, {"vendor_security_id", "qc_sid", "valid_from_session",
                    "valid_to_session", "available_at_utc"}, "CROSSWALK_ROW_SHAPE_CHANGED")
        vendor = row["vendor_security_id"]
        sid = row["qc_sid"]
        if (type(vendor) is not str or not vendor or vendor in vendors
                or type(sid) is not str or not sid or sid in by_sid):
            _refuse("CROSSWALK_AMBIGUOUS_EXACT_IDENTITY")
        vendors.add(vendor)
        start = _session_date(row["valid_from_session"], "CROSSWALK_DATE_INVALID")
        end = None if row["valid_to_session"] is None else _session_date(
            row["valid_to_session"], "CROSSWALK_DATE_INVALID")
        decision_date = _session_date(session, "DECISION_SESSION_INVALID")
        if start > decision_date or (end is not None and end <= decision_date):
            _refuse("CROSSWALK_NOT_VALID_AS_OF_DECISION")
        if _instant(row["available_at_utc"], "CROSSWALK_CLOCK_INVALID") >= cutoff:
            _refuse("CROSSWALK_NOT_AVAILABLE_BY_DECISION")
        by_sid[sid] = vendor
    return by_sid, qcom


def _prices(value, session, cutoff, qc_sha256):
    _keys(value, {"schema", "decision_session", "qc_snapshot_sha256",
                  "source_time_utc", "positive_reference_prices"}, "PRICE_SHAPE_CHANGED")
    if (value["schema"] != PRICE_SCHEMA or value["decision_session"] != session
            or value["qc_snapshot_sha256"] != qc_sha256):
        _refuse("PRICE_INPUT_BINDING_CHANGED")
    if _instant(value["source_time_utc"], "PRICE_CLOCK_INVALID") >= cutoff:
        _refuse("PRICE_NOT_PREDECISION")
    return _pairs(value["positive_reference_prices"], "PRICE_ROWS_INVALID")


def build_predecision_diagnostic(
    *, decision_session, qc_snapshot_bytes, qc_snapshot_sha256,
    vendor_receipt_bytes, vendor_receipt_sha256, crosswalk_bytes,
    crosswalk_sha256, reference_price_bytes, reference_price_sha256,
):
    """Validate supplied private-input claims; never promote them to an order.

    The supplied mapping/price timestamps are *claims*. Hashing and cutoff
    checks do not independently establish their origin or first availability.
    """
    if type(decision_session) is not str:
        _refuse("DECISION_SESSION_INVALID")
    session_date = _session_date(decision_session, "DECISION_SESSION_INVALID")
    if session_date.isoformat() != decision_session:
        _refuse("DECISION_SESSION_NONCANONICAL")
    cutoff = datetime.combine(session_date, time(9, 20), NEW_YORK).astimezone(timezone.utc)
    policy = construction_policy.load_policy()
    qc = _pinned_json(qc_snapshot_bytes, qc_snapshot_sha256, "QC_SNAPSHOT")
    caps, members, displayed_qcom = _qc_snapshot(qc, decision_session, cutoff)
    try:
        vendor = vendor_quality._require_receipt(vendor_receipt_bytes, vendor_receipt_sha256)
    except (ValueError, TypeError) as exc:
        raise ForwardPredecisionError("VENDOR_RECEIPT_INVALID") from exc
    if (vendor["first_event_date"] != decision_session
            or vendor["last_event_date"] != decision_session
            or vendor["capture_transport"] != vendor_quality.PRODUCTION_TRANSPORT):
        _refuse("VENDOR_RECEIPT_SESSION_OR_TRANSPORT_CHANGED")
    start_of_day = datetime.combine(session_date, time(0, 0), NEW_YORK).astimezone(timezone.utc)
    if (_instant(vendor["capture_started_at"], "VENDOR_CAPTURE_CLOCK_INVALID") < start_of_day
            or _instant(vendor["capture_completed_at"], "VENDOR_CAPTURE_CLOCK_INVALID") >= cutoff):
        _refuse("VENDOR_CAPTURE_NOT_PREDECISION")
    crosswalk = _pinned_json(crosswalk_bytes, crosswalk_sha256, "CROSSWALK")
    by_sid, qcom = _crosswalk(
        crosswalk, decision_session, cutoff, qc_snapshot_sha256, vendor_receipt_sha256,
    )
    prices = _prices(
        _pinned_json(reference_price_bytes, reference_price_sha256, "PRICE"),
        decision_session, cutoff, qc_snapshot_sha256,
    )
    for etf in ETFS:
        weights = members[etf]
        total = sum((Fraction(weight) for weight in weights.values()), Fraction(0))
        mapped = sum((Fraction(weight) for sid, weight in weights.items() if sid in by_sid), Fraction(0))
        if mapped * 100 < total * 99:
            _refuse("ETF_EXACT_IDENTITY_WEIGHT_BELOW_99_PERCENT")
    if displayed_qcom or qcom is not None:
        if qcom is None or displayed_qcom != {qcom} or qcom not in by_sid:
            _refuse("QCOM_EXACT_IDENTITY_UNRESOLVED")
        if qcom not in caps or qcom not in prices or not any(qcom in members[etf] for etf in ETFS):
            _refuse("QCOM_CAP_WEIGHT_OR_REFERENCE_PRICE_UNAVAILABLE")
    body = {
        "schema": SCHEMA,
        "decision_session": decision_session,
        "construction_policy_sha256": construction_policy.FROZEN_POLICY_SHA256,
        "qc_snapshot_sha256": qc_snapshot_sha256,
        "vendor_receipt_sha256": vendor_receipt_sha256,
        "crosswalk_sha256": crosswalk_sha256,
        "reference_price_sha256": reference_price_sha256,
    }
    common = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()
    ids = (policy["signal_semantics"]["control"]["forward_candidate_id"],) + tuple(
        arm["forward_candidate_id"] for arm in policy["signal_semantics"]["arms"]
    )
    if ids != ("ARV2_FORWARD_AR_OFF", "ARV2_FORWARD_AR_100", "ARV2_FORWARD_AR_200"):
        _refuse("FORWARD_ARM_CENSUS_CHANGED")
    return PredecisionDiagnostic(
        schema=SCHEMA,
        decision_session=decision_session,
        common_input_sha256=common,
        arms=tuple(ArmInputBinding(candidate_id, common) for candidate_id in ids),
        refusal_codes=_REFUSALS,
    )


__all__ = [
    "ArmInputBinding", "ForwardPredecisionError", "PredecisionDiagnostic",
    "build_predecision_diagnostic",
]
