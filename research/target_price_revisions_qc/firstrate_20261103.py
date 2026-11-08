"""Bounded supplied-byte FirstRate diagnostics; no source opener or admission.

This independent dataset is not a native QC mark, a SID map, a PIT witness or
the frozen study's signal/universe input. Parsing never grants those statuses.
Prices remain unadjusted. Missing bars are retained as gaps, never filled.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import csv
import hashlib
import io
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from data.financial_primitives import to_decimal

MAX_BYTES = 32 * 1024 * 1024
MAX_ROWS = 500_000
MAX_MEMBERS = 50_000
MAX_CALENDAR_DATES = 10_000
_INTERVAL = {"minute": "1min", "daily": "1day"}
_HEADERS = (("datetime", "open", "high", "low", "close", "volume"),
            ("date", "open", "high", "low", "close", "volume"))
# Public fund fact, not a guessed historical ticker/SID mapping. The anomaly
# quarantines supplied ETF history; it does not discard its pre-inception rows.
REMX_INCEPTION = date(2010, 10, 27)
REMX_INCEPTION_SOURCE = "https://www.vaneck.com/us/en/investments/rare-earth-strategic-metals-etf-remx/overview/"
REQUIRED_INPUT_EVIDENCE = (
    "analyst_target_revision_events_with_firm_ids_and_availability_times",
    "historical_etf_constituent_membership",
    "as_of_market_caps_and_insurance_classifications",
    "historical_permanent_security_id_and_ticker_binding",
    "split_dividend_and_delisting_semantics_and_complete_action_history",
    "point_in_time_availability_and_source_rights",
    "native_qc_raw_identity_mark_and_action_custody",
)


class FirstRateRefusal(ValueError):
    """A fixed error body with a non-sensitive reason code."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__("bounded FirstRate input refused")


def _fail(reason):
    raise FirstRateRefusal(reason) from None


def _symbol(value):
    if (type(value) is not str or
            re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,31}", value) is None or ".." in value):
        _fail("symbol")
    return value


def expected_member_name(symbol, timeframe, *, adjustment="unadjusted"):
    """Only the exact flat unadjusted provider member convention is supported."""
    _symbol(symbol)
    if type(timeframe) is not str or timeframe not in _INTERVAL:
        _fail("timeframe")
    if adjustment != "unadjusted" or type(adjustment) is not str:
        _fail("adjustment")
    return symbol + "_full_" + _INTERVAL[timeframe] + "_UNADJUSTED.txt"


def select_member(member_names, *, symbol, timeframe, adjustment="unadjusted"):
    """Select one exact member; no prefix matching, path cleanup or extraction."""
    expected = expected_member_name(symbol, timeframe, adjustment=adjustment)
    if type(member_names) not in (tuple, list) or not 0 < len(member_names) <= MAX_MEMBERS:
        _fail("catalog_bound")
    seen = set()
    for name in member_names:
        if (type(name) is not str or not 0 < len(name) <= 160 or
                re.fullmatch(r"[A-Za-z0-9_.-]+", name) is None or
                name.startswith(".") or ".." in name or name in seen):
            _fail("unsafe_or_duplicate_member")
        seen.add(name)
    if expected not in seen:
        _fail("member_missing")
    return expected


def _calendar_date(value):
    if type(value) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        _fail("date")
    try:
        result = date.fromisoformat(value)
    except ValueError:
        _fail("date")
    if not 1900 <= result.year <= 2099:
        _fail("date")
    return result


def _new_york_clock(naive):
    try:
        zone = ZoneInfo("America/New_York")
    except ZoneInfoNotFoundError:
        _fail("timezone_unavailable")
    first, second = naive.replace(tzinfo=zone, fold=0), naive.replace(tzinfo=zone, fold=1)
    roundtrip = first.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)
    if roundtrip != naive or first.utcoffset() != second.utcoffset():
        _fail("ambiguous_or_nonexistent_clock")
    return first


def _interval(value, timeframe):
    if timeframe == "daily":
        if len(value) == 10:
            day = _calendar_date(value)
        elif re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2} 00:00:00", value):
            day = _calendar_date(value[:10])
        else:
            _fail("daily_label")
        start = _new_york_clock(datetime.combine(day, time()))
        end = _new_york_clock(datetime.combine(day + timedelta(days=1), time()))
    else:
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:00", value) is None:
            _fail("minute_clock")
        _calendar_date(value[:10])
        try:
            naive = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            _fail("minute_clock")
        start = _new_york_clock(naive)
        end = (start.astimezone(timezone.utc) + timedelta(minutes=1)).astimezone(start.tzinfo)
    return start, end


def _price(text):
    if type(text) is not str or re.fullmatch(r"(?:0|[1-9][0-9]{0,15})(?:\.[0-9]{1,12})?", text) is None:
        _fail("price")
    try:
        value = to_decimal(text)
    except ValueError:
        _fail("price")
    if value <= 0:
        _fail("price")
    return value


@dataclass(frozen=True)
class Bar:
    session_date: date
    local_start: datetime
    local_end: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    @property
    def utc_start(self):
        return self.local_start.astimezone(timezone.utc)

    @property
    def utc_end(self):
        return self.local_end.astimezone(timezone.utc)


@dataclass(frozen=True)
class ParsedOHLCV:
    symbol: str
    timeframe: str
    instrument_kind: str
    member_name: str
    source_sha256: str
    source_bytes: int
    bars: tuple[Bar, ...]
    pre_inception_rows: int


def parse_ohlcv(raw, *, expected_sha256, symbol, timeframe, member_name,
                adjustment="unadjusted", instrument_kind="stock"):
    """Validate an entire bounded supplied member without filtering its rows.

    Daily labels represent calendar-day intervals, not an asserted exchange
    close. Minute end times are one real minute after the source's start label.
    A matching SHA proves byte equality only, not origin, identity or rights.
    """
    expected = expected_member_name(symbol, timeframe, adjustment=adjustment)
    if member_name != expected or type(member_name) is not str:
        _fail("member_binding")
    if instrument_kind not in ("stock", "etf") or type(instrument_kind) is not str:
        _fail("instrument_kind")
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        _fail("byte_bound")
    if (type(expected_sha256) is not str or
            re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None or
            hashlib.sha256(raw).hexdigest() != expected_sha256):
        _fail("source_hash")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        _fail("encoding")
    if "\0" in text:
        _fail("encoding")
    bars, previous, pre_inception = [], None, 0
    try:
        for index, row in enumerate(csv.reader(io.StringIO(text, newline=""), strict=True)):
            if index == 0 and tuple(cell.casefold() for cell in row) in _HEADERS:
                continue
            if len(bars) >= MAX_ROWS:
                _fail("row_bound")
            if len(row) != 6 or any(len(cell) > 64 for cell in row):
                _fail("row_schema")
            start, end = _interval(row[0], timeframe)
            if previous is not None and start.astimezone(timezone.utc) <= previous:
                _fail("duplicate_or_out_of_order")
            opening, high, low, close = (_price(cell) for cell in row[1:5])
            if low > min(opening, close) or high < max(opening, close) or low > high:
                _fail("ohlc_geometry")
            if re.fullmatch(r"[1-9][0-9]{0,17}", row[5]) is None:
                _fail("volume")
            bar = Bar(start.date(), start, end, opening, high, low, close, int(row[5]))
            bars.append(bar)
            previous = bar.utc_start
            if symbol == "REMX" and instrument_kind == "etf" and bar.session_date < REMX_INCEPTION:
                pre_inception += 1
    except csv.Error:
        _fail("csv")
    if not bars:
        _fail("empty")
    return ParsedOHLCV(symbol, timeframe, instrument_kind, expected, expected_sha256,
                       len(raw), tuple(bars), pre_inception)


def diagnostic_report(dataset, *, expected_sessions=()):
    """Return date/schema evidence only; caller dates are not an admitted calendar."""
    if type(dataset) is not ParsedOHLCV:
        _fail("dataset")
    if type(expected_sessions) not in (tuple, list) or len(expected_sessions) > MAX_CALENDAR_DATES:
        _fail("calendar_bound")
    expected = tuple(_calendar_date(value) for value in expected_sessions)
    if tuple(sorted(set(expected))) != expected:
        _fail("calendar_order")
    observed = tuple(sorted({bar.session_date for bar in dataset.bars}))
    missing = tuple(day.isoformat() for day in expected if day not in observed)
    return {
        "schema": "tpr-firstrate-supplied-ohlcv-diagnostic-v1",
        "symbol": dataset.symbol, "timeframe": dataset.timeframe,
        "member_name": dataset.member_name,
        "source_sha256": dataset.source_sha256, "source_bytes": dataset.source_bytes,
        "rows": len(dataset.bars), "first_session": observed[0].isoformat(),
        "last_session": observed[-1].isoformat(), "observed_sessions": len(observed),
        "expected_sessions": len(expected), "missing_sessions": list(missing),
        "expected_calendar_authenticated": False,
        "source_timestamp_convention": "America/New_York period start",
        "daily_interval_is_native_close": False,
        "gap_fill_performed": False, "adjustment": "unadjusted",
        "pre_inception_rows": dataset.pre_inception_rows,
        "identity_status": "QUARANTINED_PRE_INCEPTION" if dataset.pre_inception_rows else "UNVERIFIED",
        "source_origin_authenticated": False, "permanent_sid_bound": False,
        "point_in_time_data": False, "source_rights_verified": False,
        "native_qc_mark": False, "source_inputs_admitted": False,
        "backtesting_ready": False, "financial_acceptance": False,
        "canonical_admission": False, "trading_authority": False,
        "required_input_evidence": list(REQUIRED_INPUT_EVIDENCE),
    }
