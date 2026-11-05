"""Pure private monthly source normalization; never input or fitness admission.

The caller authenticates historical/global controls and holds protected files.
This layer proves one complete original table/month panel, not its identity,
currency, class, listing, rights, availability, or empirical admissibility.
"""
from __future__ import annotations

from collections import defaultdict
import dataclasses
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import json
import re

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf.contracts import parse_utc_timestamp
import research.short_interest_etf.native_market_input_protocol as inputs

CAPTURE_PROTOCOL_SHA256 = "b95ecfeefdc8b0bd01a7cb9fd1ea7b250e777356a2db8f7a026810899e7582b1"
SCHEMA = "si-native-monthly-market-qualification-v1"
MAXIMUM_REPORT_BYTES = 256 * 1024 ** 2
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\Z")


class MonthlyMarketQualificationError(ValueError):
    """Fixed safe reasons never interpolate source values or exception text."""


def _require(value, code):
    if not value:
        raise MonthlyMarketQualificationError("REFUSED: " + code)


def _clock(value):
    try:
        _require(type(value) is str, "exact_UTC_clock_required")
        return parse_utc_timestamp(value, "source_clock")
    except (TypeError, ValueError):
        raise MonthlyMarketQualificationError("REFUSED: exact_UTC_clock_required") from None


def _authority():
    return {"source_only": True, "latest_revised_only": True,
        "source_admitted": False, "data_or_fitness_admitted": False,
        "native_identity_admitted": False, "share_class_admitted": False,
        "USD_currency_admitted": False, "same_class_denominator_admitted": False,
        "historical_availability_verified": False, "point_in_time_data": False,
        "actual_input_execution_admitted": False, "ready_for_backtesting": False,
        "outcome_access_authorized": False, "outcome_looks": 0, "allocated_alpha": 0,
        "qc_authorized": False, "qc_attempts": 0, "trading_authority": False}


def qualification_policy():
    return {"schema": SCHEMA + "-policy", "capture_protocol_sha256": CAPTURE_PROTOCOL_SHA256,
        "scope": "one_complete_original_table_month_no_ticker_filter_or_source_fitness_claim",
        "raw_OHLC": "adjusted_OHLC_times_closeunadj_divided_by_close",
        "raw_volume": "volume_times_close_divided_by_closeunadj_exact_no_rounding",
        "daily_cap": "issuer_USD_millions_times_1000000_never_class_shares_or_currency_proof",
        "numbers": "exact_JSON_int_not_bool_or_monthly_NumberToken_max128chars_abs_adjusted_exponent30",
        "duplicates": "all_identifiable_same_table_ticker_date_peers_quarantined_across_pages",
        "lastupdated": "source_revision_metadata_only_not_public_availability",
        "consumer": "private_source_only_exact_master_daily_class_CIK_USD_proofs_deferred",
        "authority": _authority()}


_PAGE_FIELDS = ("page_number", "attempt", "request_json", "request_sha256", "raw",
    "source_file_sha256", "started_at", "received_at", "http_status", "content_type")


@dataclasses.dataclass(frozen=True, slots=True)
class CapturedMonthlyMarketPage:
    page_number: int
    attempt: int
    request_json: str = dataclasses.field(repr=False)
    request_sha256: str
    raw: bytes = dataclasses.field(repr=False)
    source_file_sha256: str
    started_at: str
    received_at: str
    http_status: int = 200
    content_type: str = dataclasses.field(default="application/json", repr=False)
    _anchor: tuple = dataclasses.field(init=False, repr=False)
    _identity: tuple = dataclasses.field(init=False, repr=False)

    def __post_init__(self):
        # Re-running post-init must verify, never re-anchor reflected mutation.
        if hasattr(self, "_anchor"):
            self._guard()
            return
        _require(type(self) is CapturedMonthlyMarketPage, "exact_monthly_capture_required")
        _require(type(self.page_number) is int and 0 <= self.page_number < 64
            and type(self.attempt) is int and 1 <= self.attempt <= 7168,
            "bounded_exact_page_and_attempt_required")
        _require(type(self.request_json) is str and len(self.request_json) <= 4096
            and type(self.request_sha256) is str and _SHA.fullmatch(self.request_sha256)
            and type(self.source_file_sha256) is str and _SHA.fullmatch(self.source_file_sha256)
            and type(self.raw) is bytes and len(self.raw) <= 8 * 1024 ** 2
            and hash_bytes(self.raw) == self.source_file_sha256,
            "original_request_and_raw_bytes_required")
        _require(type(self.http_status) is int and self.http_status == 200
            and type(self.content_type) is str and len(self.content_type) <= 256
            and self.content_type.split(";", 1)[0].strip().lower() == "application/json",
            "successful_JSON_receipt_required")
        _require(_clock(self.started_at) <= _clock(self.received_at), "page_receipt_chronology")
        parts = tuple(getattr(self, name) for name in _PAGE_FIELDS)
        object.__setattr__(self, "_anchor", parts)
        object.__setattr__(self, "_identity", parts)

    def _guard(self):
        _require(type(self) is CapturedMonthlyMarketPage and type(self._anchor) is tuple
            and len(self._anchor) == len(_PAGE_FIELDS) and self._anchor is self._identity
            and all(getattr(self, name) is value for name, value in zip(_PAGE_FIELDS, self._anchor)),
            "sealed_monthly_capture_changed")


def _number(value, *, positive=False):
    if type(value) is int:
        _require(abs(value) <= 10 ** 30, "numeric_bound")
        amount = Fraction(value)
    else:
        _require(type(value) is inputs.NumberToken and len(value) <= 128
            and _NUMBER.fullmatch(value) is not None, "exact_lexical_JSON_number_required")
        try:
            decimal = Decimal(value)
        except InvalidOperation:
            raise MonthlyMarketQualificationError("REFUSED: exact_lexical_JSON_number_required") from None
        _require(decimal.is_finite() and abs(decimal.adjusted()) <= 30, "numeric_bound")
        amount = Fraction(decimal)
    _require(amount > 0 if positive else amount >= 0, "positive_or_nonnegative_number_required")
    return amount


def _rational(amount):
    return {"numerator": amount.numerator, "denominator": amount.denominator}


def _normalize(table, row):
    if table == "daily":
        return {"ticker": row["ticker"], "session": row["date"],
            "issuer_market_cap_USD": _rational(_number(row["marketcap"]) * 1000000),
            "provider_units": "USD_millions", "same_class_shares": None}
    values = {key: _number(row[key], positive=key != "volume")
        for key in ("open", "high", "low", "close", "volume", "closeunadj")}
    _require(values["low"] <= min(values["open"], values["close"])
        <= max(values["open"], values["close"]) <= values["high"], "OHLC_order_invalid")
    ratio = values["closeunadj"] / values["close"]
    return {"ticker": row["ticker"], "session": row["date"],
        **{"raw_" + key: _rational(values[key] * ratio) for key in ("open", "high", "low", "close")},
        "raw_volume": _rational(values["volume"] / ratio)}


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class MonthlyMarketQualification:
    _pages: tuple = dataclasses.field(repr=False)
    _json: str = dataclasses.field(repr=False)
    _sha256: str = dataclasses.field(repr=False)
    _anchor: tuple = dataclasses.field(repr=False)
    _identity: tuple = dataclasses.field(repr=False)

    def __init__(self):
        raise MonthlyMarketQualificationError("REFUSED: monthly_qualification_factory_required")

    def _guard(self):
        _require(type(self) is MonthlyMarketQualification and type(self._anchor) is tuple
            and len(self._anchor) == 3 and self._anchor is self._identity
            and all(getattr(self, name) is value for name, value in zip(
                ("_pages", "_json", "_sha256"), self._anchor)), "sealed_monthly_qualification_changed")
        for page in self._pages:
            page._guard()

    def to_bytes(self):
        """PRIVATE: includes licensed normalized rows and original provenance."""
        self._guard()
        return self._json.encode()

    def to_payload(self):
        """PRIVATE detached payload; callers cannot mutate the sealed report."""
        return json.loads(self.to_bytes())

    @property
    def sha256(self):
        self._guard()
        return self._sha256

    def public_summary(self):
        """Operational scope only, not coverage/refusal counts or source fitness."""
        self._guard()
        return {"schema": SCHEMA, "pages": len(self._pages), "attempts": len(self._pages),
            "authority": _authority()}


def qualify_monthly_market_panel(table, month, pages, *, retrieved_at):
    """Qualify one exhausted panel; global/historical custody remains external."""
    _require(hash_payload(inputs.market_input_protocol()) == CAPTURE_PROTOCOL_SHA256,
        "frozen_monthly_capture_protocol_changed")
    _require(type(table) is str and table in inputs.TABLES and type(month) is str
        and month in {item[0] for item in inputs.MONTHS}, "frozen_table_month_required")
    _require(type(pages) is tuple and 1 <= len(pages) <= 64
        and all(type(page) is CapturedMonthlyMarketPage for page in pages),
        "bounded_exact_panel_captures_required")
    retrieved = _clock(retrieved_at)
    records, origins, groups = [], [], defaultdict(list)
    previous_date, previous_receipt, previous_attempt, row_bytes = None, None, None, 0
    for number, page in enumerate(pages):
        page._guard()
        descriptor = inputs.page_request(table, month, number)
        _require(page.page_number == number and page.request_json == canonical_json(descriptor)
            and page.request_sha256 == hash_payload(descriptor), "exact_contiguous_panel_request_required")
        _require(previous_attempt is None or page.attempt == previous_attempt + 1,
            "contiguous_original_attempts_required")
        start, end = _clock(page.started_at), _clock(page.received_at)
        _require((previous_receipt is None or previous_receipt <= start) and end <= retrieved,
            "serial_panel_and_retrieval_chronology")
        try:
            rows = inputs.decode_page(page.raw)
            inspected, previous_date = inputs.inspect_page(rows, table=table, month=month, previous_date=previous_date)
        except (inputs.NativeMarketInputError, TypeError, ValueError, OverflowError):
            raise MonthlyMarketQualificationError("REFUSED: monthly_page_envelope_scope_or_order") from None
        if number + 1 < len(pages):
            _require(len(rows) == 10000, "only_full_page_may_have_successor")
        else:
            _require(len(rows) < 10000, "final_short_page_exhaustion_required")
        origins.append({"page_number": number, "attempt": page.attempt,
            "raw_path": f"attempt-{page.attempt:05d}.raw", "request_sha256": page.request_sha256,
            "source_file_sha256": page.source_file_sha256, "raw_bytes": len(page.raw),
            "started_at": page.started_at, "received_at": page.received_at,
            "http_status": page.http_status, "content_type": page.content_type, "row_count": len(rows)})
        for index, slot, reason in inspected:
            origin = {"page_number": number, "attempt": page.attempt, "row_index": index,
                "source_file_sha256": page.source_file_sha256}
            normalized, reasons = None, [] if reason is None else [reason]
            if reason is None:
                try:
                    normalized = _normalize(table, rows[index])
                except MonthlyMarketQualificationError:
                    reasons.append("financial_token_or_OHLC_refused")
            record = {"source_origin": origin,
                "identifiable_grouping_key": None if slot is None else {"table": table, "ticker": slot[0], "date": slot[1]},
                "lastupdated_revision_metadata": rows[index].get("lastupdated") if type(rows[index]) is dict else None,
                "normalized": normalized, "refusal_reasons": reasons}
            row_bytes += len(canonical_json(record).encode()) + 96
            _require(row_bytes <= MAXIMUM_REPORT_BYTES - 2 * 1024 ** 2, "bounded_private_panel_report_required")
            if slot is not None:
                groups[slot].append(len(records))
            records.append(record)
        previous_receipt, previous_attempt = end, page.attempt
    for indices in groups.values():
        if len(indices) > 1:
            for index in indices:
                records[index]["normalized"] = None
                records[index]["refusal_reasons"].append("all_identifiable_duplicate_peers_quarantined")
    for page in pages:
        page._guard()
    payload = {"schema": SCHEMA, "capture_protocol_sha256": CAPTURE_PROTOCOL_SHA256,
        "qualification_policy_sha256": hash_payload(qualification_policy()), "table": table, "month": month,
        "retrieved_at": retrieved_at, "page_origins": origins, "rows": records,
        "lastupdated_semantic": "revision_metadata_not_public_availability",
        "global_historical_controls_authenticated_by_this_layer": False,
        "publication_scope": "private_only_no_rows_or_fitness_conclusions", "authority": _authority()}
    raw = canonical_json(payload)
    _require(len(raw.encode()) <= MAXIMUM_REPORT_BYTES, "bounded_private_panel_report_required")
    value = object.__new__(MonthlyMarketQualification)
    parts = pages, raw, hash_bytes(raw.encode())
    for name, item in zip(("_pages", "_json", "_sha256"), parts):
        object.__setattr__(value, name, item)
    object.__setattr__(value, "_anchor", parts)
    object.__setattr__(value, "_identity", parts)
    value._guard()
    return value
