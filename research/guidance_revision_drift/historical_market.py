"""Pure normalization/slicing of a bounded Massive-shaped historical projection.

No API client, SDK, file access, historical availability certification, or order
engine is present. Supplied request/completeness/reference metadata is a claim,
not evidence that a subscription, source, calendar or security mapping is valid.
The accepted SYN-only runtime is deliberately not imported or changed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from data.financial_primitives import (
    decimal_text, exact_decimal_add, exact_decimal_multiply, exact_decimal_subtract,
)
from data.hashing import hash_bytes
from research.guidance_revision_drift.input_contracts import (
    InputError, amount, canonical_bytes, day, decode_object, identifier, keys, utc,
)


SCHEMA = "gdr.historical-market.v1"
MAX_BYTES = 1_048_576
MAX_QUOTES = 4096
MAX_MINUTES = 390
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_NY = ZoneInfo("America/New_York")
_SECOND = 1_000_000_000
_MINUTE = 60 * _SECOND
_ENVELOPE = frozenset({"schema", "provider", "security_id", "symbol", "role", "session_date",
    "session_open_utc", "session_close_utc", "adjusted", "fill_forward",
    "quotes_complete", "minutes_complete", "quotes", "minutes"})
_QUOTE = frozenset({"bid_price", "ask_price", "bid_size", "ask_size", "sip_timestamp",
                    "participant_timestamp", "sequence_number", "conditions"})
_BAR = frozenset({"o", "h", "l", "c", "v", "t"})


def _integer(value: object, *, maximum: int = 10**21) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise InputError("bounded nonnegative exact market integer required")
    return value


def instant_ns(value: datetime) -> int:
    """Exact UTC microsecond-to-nanosecond conversion, never float timestamp()."""
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise InputError("aware UTC market instant required")
    elapsed = value - _EPOCH
    return ((elapsed.days * 86400 + elapsed.seconds) * _SECOND + elapsed.microseconds * 1000)


@dataclass(frozen=True, slots=True)
class HistoricalQuote:
    security_id: str
    symbol: str
    source_sha256: str
    sip_timestamp_ns: int
    participant_timestamp_ns: int
    sequence_number: int
    bid: Decimal
    ask: Decimal
    bid_size: int
    ask_size: int
    conditions: tuple[int, ...]

    def projection(self) -> dict:
        return {"security_id": self.security_id, "symbol": self.symbol,
            "source_sha256": self.source_sha256, "sip_timestamp_ns": self.sip_timestamp_ns,
            "participant_timestamp_ns": self.participant_timestamp_ns,
            "sequence_number": self.sequence_number, "bid": decimal_text(self.bid),
            "ask": decimal_text(self.ask), "bid_size": self.bid_size, "ask_size": self.ask_size,
            "conditions": list(self.conditions)}


@dataclass(frozen=True, slots=True)
class HistoricalMinute:
    security_id: str
    symbol: str
    source_sha256: str
    start_timestamp_ns: int
    end_timestamp_ns: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    def projection(self) -> dict:
        return {"security_id": self.security_id, "symbol": self.symbol,
            "source_sha256": self.source_sha256, "start_timestamp_ns": self.start_timestamp_ns,
            "end_timestamp_ns": self.end_timestamp_ns, "open": decimal_text(self.open),
            "high": decimal_text(self.high), "low": decimal_text(self.low),
            "close": decimal_text(self.close), "volume_shares": self.volume,
            "normalization": "Raw", "fill_forward": False}


@dataclass(frozen=True, slots=True)
class HistoricalExecutionInput:
    quote: HistoricalQuote
    minute: HistoricalMinute
    submitted_at_ns: int
    callback_at_ns: int

    def projection(self) -> dict:
        return {"quote": self.quote.projection(), "minute": self.minute.projection(),
            "submitted_at_ns": self.submitted_at_ns, "callback_at_ns": self.callback_at_ns,
            "minute_participation_cap_shares": self.minute.volume // 100,
            "volume_model": "completed_post_submission_minute_volume_proxy",
            "point_in_time_data": False, "execution_authority": False,
            "coverage_verified": False, "native_execution_evidence": False}


def _quote(row: object, security: str, symbol: str, source: str,
           session_start: int, session_end: int) -> HistoricalQuote:
    row = keys(row, _QUOTE)
    sip = _integer(row["sip_timestamp"])
    participant = _integer(row["participant_timestamp"])
    if not session_start <= sip <= session_end:
        raise InputError("quote SIP instant outside supplied regular session")
    conditions = row["conditions"]
    if type(conditions) is not list or len(conditions) > 16:
        raise InputError("bounded quote-condition list required")
    checked = tuple(_integer(item, maximum=10000) for item in conditions)
    if len(set(checked)) != len(checked):
        raise InputError("duplicate quote condition")
    # Keep economically invalid latest quotes so the selector refuses them,
    # rather than silently reaching back to an earlier convenient valid quote.
    return HistoricalQuote(security, symbol, source, sip, participant,
        _integer(row["sequence_number"]), amount(row["bid_price"]), amount(row["ask_price"]),
        _integer(row["bid_size"], maximum=10**12), _integer(row["ask_size"], maximum=10**12), checked)


def _minute(row: object, security: str, symbol: str, source: str,
            session_start: int, session_end: int) -> HistoricalMinute:
    row = keys(row, _BAR)
    start = _integer(row["t"]) * 1_000_000  # Massive aggregate t is START milliseconds.
    end = start + _MINUTE
    if start % _MINUTE or not session_start <= start < end <= session_end:
        raise InputError("complete aligned regular-session minute required")
    opening, high, low, close = (amount(row[key], positive=True) for key in ("o", "h", "l", "c"))
    if not low <= min(opening, close) <= max(opening, close) <= high:
        raise InputError("inconsistent raw minute OHLC range")
    volume = amount(row["v"], nonnegative=True)
    if volume != volume.to_integral_value() or volume > 10**12:
        raise InputError("bounded integral reported share volume required")
    return HistoricalMinute(security, symbol, source, start, end, opening, high, low, close, int(volume))


def _decode(raw: bytes) -> tuple[dict, tuple[HistoricalQuote, ...], tuple[HistoricalMinute, ...]]:
    body = keys(decode_object(raw, MAX_BYTES, provider_numbers=True), _ENVELOPE)
    if body["schema"] != SCHEMA or body["provider"] != "massive":
        raise InputError("explicit historical market projection schema required")
    security, symbol = identifier(body["security_id"]), identifier(body["symbol"])
    if type(body["role"]) is not str or body["role"] not in {"stock", "benchmark"}:
        raise InputError("explicit stock or benchmark role required")
    if body["role"] == "benchmark" and symbol != "SPY":
        raise InputError("benchmark projection must explicitly identify SPY")
    session_day = day(body["session_date"])
    opening, close = utc(body["session_open_utc"]), utc(body["session_close_utc"])
    local_open, local_close = opening.astimezone(_NY), close.astimezone(_NY)
    if (session_day.weekday() >= 5 or local_open.date() != session_day or local_close.date() != session_day
            or local_open.time() != time(9, 30) or local_close.time() not in {time(13), time(16)}
            or opening >= close):
        raise InputError("supplied regular-session bounds are inconsistent")
    if (body["adjusted"] is not False or body["fill_forward"] is not False
            or body["quotes_complete"] is not True or body["minutes_complete"] is not True):
        raise InputError("explicit raw non-filled and supplied-complete projection required")
    quotes, minutes = body["quotes"], body["minutes"]
    if type(quotes) is not list or not 1 <= len(quotes) <= MAX_QUOTES:
        raise InputError("bounded nonempty quote projection required")
    if type(minutes) is not list or not 1 <= len(minutes) <= MAX_MINUTES:
        raise InputError("bounded nonempty minute projection required")
    source = hash_bytes(raw)
    start, end = instant_ns(opening), instant_ns(close)
    unique_quotes = {}
    for row in quotes:
        value = _quote(row, security, symbol, source, start, end)
        identity = (value.sip_timestamp_ns, value.sequence_number)
        previous = unique_quotes.get(identity)
        if previous is not None and previous != value:
            raise InputError("conflicting quote identity")
        unique_quotes[identity] = value
    unique_minutes = {}
    for row in minutes:
        value = _minute(row, security, symbol, source, start, end)
        previous = unique_minutes.get(value.start_timestamp_ns)
        if previous is not None and previous != value:
            raise InputError("conflicting minute identity")
        unique_minutes[value.start_timestamp_ns] = value
    return (body, tuple(unique_quotes[key] for key in sorted(unique_quotes)),
            tuple(unique_minutes[key] for key in sorted(unique_minutes)))


def _usable_quote(quote: HistoricalQuote, as_of_ns: int, *, entry_spread: bool) -> HistoricalQuote:
    if (quote.sip_timestamp_ns > as_of_ns or as_of_ns - quote.sip_timestamp_ns > _MINUTE
            or quote.participant_timestamp_ns > quote.sip_timestamp_ns
            or as_of_ns - quote.participant_timestamp_ns > _MINUTE):
        raise InputError("latest quote is future or stale")
    if quote.bid <= 0 or quote.ask <= 0 or quote.bid > quote.ask:
        raise InputError("latest quote is nonpositive or crossed")
    if not quote.bid_size or not quote.ask_size or quote.conditions:
        raise InputError("latest quote size or condition is not executable under this narrow model")
    if entry_spread and exact_decimal_multiply(exact_decimal_subtract(quote.ask, quote.bid), Decimal("2")) > (
            exact_decimal_multiply(exact_decimal_add(quote.ask, quote.bid), Decimal("0.005"))):
        raise InputError("entry quote spread exceeds proposed limit")
    return quote


@dataclass(frozen=True, slots=True)
class HistoricalMarketBatch:
    """Immutable caller-supplied raw bytes; no provenance or readiness assertion."""
    raw_bytes: bytes

    def __post_init__(self) -> None:
        _decode(self.raw_bytes)

    @classmethod
    def from_bytes(cls, raw: bytes) -> HistoricalMarketBatch:
        return cls(raw)

    @property
    def sha256(self) -> str:
        _decode(self.raw_bytes)
        return hash_bytes(self.raw_bytes)

    @property
    def security_id(self) -> str:
        return _decode(self.raw_bytes)[0]["security_id"]

    @property
    def symbol(self) -> str:
        return _decode(self.raw_bytes)[0]["symbol"]

    @property
    def role(self) -> str:
        return _decode(self.raw_bytes)[0]["role"]

    @property
    def session_date(self) -> date:
        return day(_decode(self.raw_bytes)[0]["session_date"])

    @property
    def session_open_utc(self) -> datetime:
        return utc(_decode(self.raw_bytes)[0]["session_open_utc"])

    @property
    def session_close_utc(self) -> datetime:
        return utc(_decode(self.raw_bytes)[0]["session_close_utc"])

    def projection(self) -> dict:
        body, quotes, minutes = _decode(self.raw_bytes)
        return {"schema": "gdr.historical-market-normalized.v1", "provider": body["provider"],
            "security_id": body["security_id"], "symbol": body["symbol"], "role": body["role"],
            "session_date": body["session_date"], "source_sha256": self.sha256,
            "session_open_utc": body["session_open_utc"], "session_close_utc": body["session_close_utc"],
            "normalization": "Raw", "fill_forward": False,
            "quotes": [quote.projection() for quote in quotes],
            "minutes": [minute.projection() for minute in minutes],
            "quote_duplicates": len(body["quotes"]) - len(quotes),
            "minute_duplicates": len(body["minutes"]) - len(minutes),
            "supplied_completeness_only": True, "coverage_verified": False,
            "reference_mapping_verified": False, "calendar_verified": False,
            "point_in_time_data": False, "historical_availability_verified": False,
            "execution_authority": False, "native_execution_evidence": False}

    def canonical_projection(self) -> bytes:
        return canonical_bytes(self.projection())

    def _latest(self, at: datetime, *, entry_spread: bool) -> HistoricalQuote:
        body, quotes, _ = _decode(self.raw_bytes)
        at_ns = instant_ns(at)
        if not instant_ns(utc(body["session_open_utc"])) <= at_ns <= instant_ns(utc(body["session_close_utc"])):
            raise InputError("market decision outside supplied regular session")
        eligible = [quote for quote in quotes if quote.sip_timestamp_ns <= at_ns]
        if not eligible:
            raise InputError("no quote at or before market instant")
        return _usable_quote(eligible[-1], at_ns, entry_spread=entry_spread)

    def decision_quote(self, at: datetime) -> HistoricalQuote:
        """At 10:00 NY select latest then validate, never a valid-quote fallback."""
        instant_ns(at)
        if at.astimezone(_NY).time() != time(10):
            raise InputError("entry decision must be at 10:00 New York")
        return self._latest(at, entry_spread=True)

    def subsequent_minute(self, *, submitted_at: datetime, callback_at: datetime,
                          decision_quote: HistoricalQuote | None = None) -> HistoricalExecutionInput:
        """Slice a wholly post-submission completed volume interval and later quote.

        The quote is observed by the callback and volume is a minute cap proxy,
        not evidence that individual trades executed at the selected quote.
        This returns no fill, price impact, settlement policy or actual order.
        """
        submitted, callback = instant_ns(submitted_at), instant_ns(callback_at)
        body, quotes, minutes = _decode(self.raw_bytes)
        if callback <= submitted:
            raise InputError("execution callback must follow submission")
        matches = [minute for minute in minutes if minute.end_timestamp_ns == callback]
        if len(matches) != 1 or matches[0].start_timestamp_ns < submitted:
            raise InputError("no wholly subsequent complete execution minute")
        minute = matches[0]
        if decision_quote is not None:
            if (type(decision_quote) is not HistoricalQuote or decision_quote not in quotes
                    or decision_quote.sip_timestamp_ns > submitted):
                raise InputError("decision quote does not belong to this source before submission")
        quote = self._latest(callback_at, entry_spread=False)
        if (quote.sip_timestamp_ns <= submitted or quote.sip_timestamp_ns < minute.start_timestamp_ns
                or quote == decision_quote):
            raise InputError("execution cannot reuse decision or pre-submission quote")
        return HistoricalExecutionInput(quote, minute, submitted, callback)
