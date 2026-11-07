"""Bounded, pure QC quote-tick normalization, never a QC client or fill model.

Input is an explicit in-memory projection of RAW Tick.Quote / TradeBar fields.
Prices are already native Decimal price units (NOT the CSV integer x10000).
Each time_ny must carry the actual New York UTC offset and retains native
precision through .NET's 100ns ticks. No receipt, SIP, participant clock,
source sequence, NBBO certification or permission is inferred.

An observed-venue book is a structural diagnostic, not certified national BBO.
Unknown withdrawals/flags and ambiguous same-event-time updates refuse. The
existing Massive parser and SYN-only order/native engines remain unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal
from itertools import groupby
import re
from zoneinfo import ZoneInfo

from data.financial_primitives import (
    decimal_text, exact_decimal_add, exact_decimal_multiply, exact_decimal_subtract,
)
from data.hashing import hash_bytes
from research.guidance_revision_drift.historical_market import HistoricalMinute, instant_ns
from research.guidance_revision_drift.input_contracts import (
    InputError, amount, canonical_bytes, day, decode_object, digest, identifier, keys, utc,
)

SCHEMA = "gdr.qc-native-quotes.v1"
MAX_BYTES = 4_194_304
MAX_TICKS = 16_384
_MINUTE = 60_000_000_000
_NY = ZoneInfo("America/New_York")
# Native ExchangeCode values, not Tick.Exchange names or arbitrary SIP letters.
# Inspected https://github.com/QuantConnect/Lean/blob/master/Common/Exchange.cs
# defines these USA equity venues. This is not a complete historical registry
# or proof of this deployed binding's quote mapping/delivered subset. Broker
# routing objects and other markets are excluded; unknown codes require source
# qualification rather than a fabricated historical activity interval.
_EQUITY_EXCHANGE_CODES = frozenset({
    "A", "B", "C", "D", "I", "J", "K", "L", "M", "N", "P", "Q", "S",
    "W", "X", "Y", "Z", "BB", "IEX", "MM", "MP", "SIAC",
})
_NATIVE_CLOCK = re.compile(
    r"([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})"
    r"(?:\.([0-9]{1,7}))?([+-][0-9]{2}:[0-9]{2})")
_ENVELOPE = frozenset({"schema", "provider", "data_type", "security_id", "symbol", "role",
    "session_date", "session_open_utc", "session_close_utc", "normalization", "fill_forward",
    "ticks_complete", "minutes_complete", "ticks", "minutes"})
_TICK = frozenset({"time_ny", "bid_price", "ask_price", "bid_size", "ask_size",
                   "exchange", "sale_condition", "suspicious", "is_fill_forward"})
_BAR = frozenset({"time_ny", "end_time_ny", "open", "high", "low", "close", "volume",
                  "is_fill_forward"})


def _ny_clock_ns(value: object) -> int:
    """Retain 100ns native event times without Python datetime truncation.

    LEAN's Tick reader accepts fractional milliseconds. Its one-millisecond
    Slice buckets do not imply millisecond precision for each Tick.Time.
    https://github.com/QuantConnect/Lean/blob/master/Common/Data/Market/Tick.cs
    """
    matched = _NATIVE_CLOCK.fullmatch(value) if type(value) is str else None
    if matched is None:
        raise InputError("explicit offset New York tick clock required")
    try:
        at = datetime.fromisoformat(matched[1] + matched[3])
    except ValueError as exc:
        raise InputError("invalid native clock") from exc
    local = at.astimezone(_NY)
    if at.utcoffset() != local.utcoffset() or at.replace(tzinfo=None) != local.replace(tzinfo=None):
        raise InputError("native clock must match New York offset")
    fraction_ns = int((matched[2] or "").ljust(7, "0")) * 100
    return instant_ns(at.astimezone(timezone.utc)) + fraction_ns


def _shares(value: object) -> int:
    shares = amount(value)
    if shares != shares.to_integral_value() or not 0 <= shares <= 10**12:
        raise InputError("bounded integral native share count required")
    return int(shares)


def _exchange(value: object) -> str:
    if type(value) is not str or value not in _EQUITY_EXCHANGE_CODES:
        raise InputError("explicit native exchange code required")
    return value


def _gates() -> dict:
    return {"coverage_verified": False, "nbbo_verified": False, "point_in_time_data": False,
        "native_execution_evidence": False, "execution_authority": False,
        "historical_availability_verified": False, "calendar_verified": False,
        "reference_mapping_verified": False, "source_rights_verified": False,
        "backtest_ready": False}


@dataclass(frozen=True, slots=True)
class _Tick:
    at_ns: int
    exchange: str
    bid: Decimal
    ask: Decimal
    bid_size: int
    ask_size: int
    flags: int
    suspicious: bool
    fill_forward: bool


@dataclass(frozen=True, slots=True)
class QcNativeQuote:
    security_id: str
    symbol: str
    source_sha256: str
    as_of_ns: int
    observed_time_ns: int
    bid_updated_ns: int
    ask_updated_ns: int
    bid: Decimal
    ask: Decimal
    bid_size: int
    ask_size: int
    bid_exchange: str
    ask_exchange: str

    def __post_init__(self) -> None:
        identifier(self.security_id), identifier(self.symbol), digest(self.source_sha256)
        for stamp in (self.as_of_ns, self.observed_time_ns, self.bid_updated_ns, self.ask_updated_ns):
            if type(stamp) is not int or not 0 <= stamp <= 253402300799999999900:
                raise InputError("bounded exact native quote clock required")
        if (self.as_of_ns % 1000 or any(stamp % 100 for stamp in (
                self.observed_time_ns, self.bid_updated_ns, self.ask_updated_ns))
                or not max(self.bid_updated_ns, self.ask_updated_ns) <= self.observed_time_ns <= self.as_of_ns
                or self.as_of_ns - min(self.bid_updated_ns, self.ask_updated_ns) > _MINUTE):
            raise InputError("native quote side clocks are inconsistent or stale")
        for price in (self.bid, self.ask):
            if type(price) is not Decimal:
                raise InputError("exact native Decimal price required")
            amount(price, positive=True)
        if self.bid > self.ask:
            raise InputError("crossed native quote snapshot")
        for size in (self.bid_size, self.ask_size):
            if type(size) is not int or not 1 <= size <= 10**12:
                raise InputError("positive exact native share size required")
        _exchange(self.bid_exchange), _exchange(self.ask_exchange)

    def projection(self) -> dict:
        return {"schema": "gdr.qc-native-quote.v1", "security_id": self.security_id,
            "symbol": self.symbol, "source_sha256": self.source_sha256,
            "clock_kind": "qc_native_event_time", "as_of_ns": self.as_of_ns,
            "observed_time_ns": self.observed_time_ns, "bid_updated_ns": self.bid_updated_ns,
            "ask_updated_ns": self.ask_updated_ns, "bid": decimal_text(self.bid),
            "ask": decimal_text(self.ask), "bid_size": self.bid_size, "ask_size": self.ask_size,
            "bid_exchange": self.bid_exchange, "ask_exchange": self.ask_exchange,
            "book_model": "observed_venues_only_regular_flag_1",
            "size_model": "one_selected_venue_per_side_not_aggregated", **_gates()}


@dataclass(frozen=True, slots=True)
class QcNativeExecutionInput:
    quote: QcNativeQuote
    minute: HistoricalMinute
    submitted_at_ns: int
    callback_at_ns: int

    def projection(self) -> dict:
        return {"quote": self.quote.projection(), "minute": self.minute.projection(),
            "submitted_at_ns": self.submitted_at_ns, "callback_at_ns": self.callback_at_ns,
            "minute_participation_cap_shares": self.minute.volume // 100,
            "volume_model": "completed_post_submission_minute_volume_proxy", **_gates()}


def _decode(raw: bytes) -> tuple[dict, tuple[_Tick, ...], tuple[HistoricalMinute, ...]]:
    body = keys(decode_object(raw, MAX_BYTES, provider_numbers=True), _ENVELOPE)
    if (body["schema"] != SCHEMA or body["provider"] != "quantconnect"
            or body["data_type"] != "Tick.Quote"):
        raise InputError("explicit QC native quote-tick schema required")
    security, symbol = identifier(body["security_id"]), identifier(body["symbol"])
    if type(body["role"]) is not str or body["role"] not in {"stock", "benchmark"}:
        raise InputError("explicit stock or benchmark role required")
    if body["role"] == "benchmark" and symbol != "SPY":
        raise InputError("benchmark must explicitly identify SPY")
    session = day(body["session_date"])
    opening, closing = utc(body["session_open_utc"]), utc(body["session_close_utc"])
    local_open, local_close = opening.astimezone(_NY), closing.astimezone(_NY)
    if (session.weekday() >= 5 or local_open.date() != session or local_close.date() != session
            or local_open.time() != time(9, 30) or local_close.time() not in {time(13), time(16)}):
        raise InputError("native supplied regular-session bounds are inconsistent")
    if (body["normalization"] != "Raw" or body["fill_forward"] is not False
            or body["ticks_complete"] is not True or body["minutes_complete"] is not True):
        raise InputError("explicit raw non-filled and supplied-complete native projection required")
    rows, bars = body["ticks"], body["minutes"]
    if type(rows) is not list or not 1 <= len(rows) <= MAX_TICKS:
        raise InputError("bounded nonempty native tick projection required")
    if type(bars) is not list or not 1 <= len(bars) <= 390:
        raise InputError("bounded nonempty native minute projection required")
    start, end = instant_ns(opening), instant_ns(closing)
    ticks, last = [], start
    for row in rows:
        row = keys(row, _TICK)
        stamp = _ny_clock_ns(row["time_ny"])
        if not start <= stamp <= end or stamp < last:
            raise InputError("native ticks must be nondecreasing inside supplied regular session")
        last = stamp
        exchange = _exchange(row["exchange"])
        flags = row["sale_condition"]
        if type(flags) is not str or re.fullmatch(r"[0-9a-fA-F]{1,8}", flags) is None:
            raise InputError("explicit native hexadecimal quote condition required")
        if type(row["suspicious"]) is not bool or type(row["is_fill_forward"]) is not bool:
            raise InputError("strict native tick flags required")
        bid, ask = amount(row["bid_price"]), amount(row["ask_price"])
        bid_size, ask_size = _shares(row["bid_size"]), _shares(row["ask_size"])
        if (bid != 0 or bid_size != 0) and (ask != 0 or ask_size != 0):
            raise InputError("native equity quote must be one-sided, not a QuoteBar or healed pair")
        ticks.append(_Tick(stamp, exchange, bid, ask, bid_size, ask_size, int(flags, 16),
                           row["suspicious"], row["is_fill_forward"]))
    source, unique = hash_bytes(raw), {}
    for row in bars:
        row = keys(row, _BAR)
        begin, finish = (_ny_clock_ns(row[key]) for key in ("time_ny", "end_time_ny"))
        if (row["is_fill_forward"] is not False or begin % _MINUTE
                or finish - begin != _MINUTE or not start <= begin < finish <= end):
            raise InputError("raw unfilled aligned complete regular-session trade minute required")
        op, hi, lo, cl = (amount(row[key], positive=True) for key in ("open", "high", "low", "close"))
        if not lo <= min(op, cl) <= max(op, cl) <= hi:
            raise InputError("inconsistent native raw minute OHLC")
        minute = HistoricalMinute(security, symbol, source, begin, finish, op, hi, lo, cl, _shares(row["volume"]))
        if begin in unique and unique[begin] != minute:
            raise InputError("conflicting native minute identity")
        unique[begin] = minute
    return body, tuple(ticks), tuple(unique[key] for key in sorted(unique))


@dataclass(frozen=True, slots=True)
class QcNativeQuoteBatch:
    """Immutable bounded projection; completeness and source metadata are claims.

    No caller-supplied NBBO/rights/PIT approval fields exist. Importing this
    module neither installs an SDK nor enables the existing execution runners.
    """
    raw_bytes: bytes

    def __post_init__(self) -> None:
        _decode(self.raw_bytes)

    @classmethod
    def from_bytes(cls, raw: bytes) -> QcNativeQuoteBatch:
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
        body, ticks, minutes = _decode(self.raw_bytes)
        return {"schema": "gdr.qc-native-quote-batch-summary.v1", "provider": "quantconnect",
            "security_id": body["security_id"], "symbol": body["symbol"], "role": body["role"],
            "source_sha256": self.sha256, "session_date": body["session_date"],
            "tick_count": len(ticks), "minute_count": len(minutes),
            "normalization": "Raw", "declared_fill_forward": False,
            "flagged_fill_forward_ticks": sum(tick.fill_forward for tick in ticks),
            "flagged_suspicious_ticks": sum(tick.suspicious for tick in ticks),
            "supplied_completeness_only": True, **_gates()}

    def canonical_projection(self) -> bytes:
        return canonical_bytes(self.projection())

    def quote_at(self, at: datetime, *, entry_spread: bool = False) -> QcNativeQuote:
        if type(entry_spread) is not bool:
            raise InputError("strict entry spread option required")
        body, ticks, _ = _decode(self.raw_bytes)
        cutoff = instant_ns(at)
        if not instant_ns(utc(body["session_open_utc"])) <= cutoff <= instant_ns(utc(body["session_close_utc"])):
            raise InputError("native quote instant outside supplied regular session")
        # Each side is either its latest observation or explicitly unknown.
        # Consume complete equal-event-time groups atomically: no invented tie
        # order. A one-millisecond Slice can contain distinct 100ns event times.
        state, observed = {}, None
        for stamp, group in groupby(ticks, key=lambda row: row.at_ns):
            if stamp > cutoff:
                break
            observed = stamp
            updates, poison = {}, set()
            for tick in group:
                state.setdefault(tick.exchange, {"bid": None, "ask": None})
                has_bid = tick.bid != 0 or tick.bid_size != 0
                has_ask = tick.ask != 0 or tick.ask_size != 0
                # These flags describe participant state, not merely an absent
                # opposite side. Both sides must refresh after uncertainty.
                if tick.flags != 1 or tick.suspicious or tick.fill_forward or not (has_bid or has_ask):
                    poison.update(((tick.exchange, "bid"), (tick.exchange, "ask")))
                else:
                    side = "bid" if has_bid else "ask"
                    value = (tick.bid, tick.bid_size, stamp) if has_bid else (tick.ask, tick.ask_size, stamp)
                    updates.setdefault((tick.exchange, side), set()).add(value)
            for (exchange, side), values in updates.items():
                state[exchange][side] = next(iter(values)) if len(values) == 1 else None
            for exchange, side in poison:
                state[exchange][side] = None
        if observed is None:
            raise InputError("no native quote at or before market instant")
        bids, asks = [], []
        for exchange, sides in sorted(state.items()):
            bid, ask = sides["bid"], sides["ask"]
            if bid is None or ask is None:
                raise InputError("latest native venue side is missing or ambiguous")
            if any(price <= 0 or size <= 0 for price, size, _ in (bid, ask)):
                raise InputError("latest native side is nonpositive or has zero size")
            if any(cutoff - stamp > _MINUTE for _, _, stamp in (bid, ask)):
                raise InputError("latest native side is stale")
            if bid[0] > ask[0]:
                raise InputError("latest native venue is crossed")
            bids.append((*bid, exchange))
            asks.append((*ask, exchange))
        # Pick one venue's size; never sum displayed liquidity or refresh an
        # old side because the other side moved. Equal prices use oldest time.
        best_bid = max(row[0] for row in bids)
        bid = min((row for row in bids if row[0] == best_bid), key=lambda row: (row[2], row[3]))
        ask = min(asks, key=lambda row: (row[0], row[2], row[3]))
        if bid[0] > ask[0]:
            raise InputError("observed native venue BBO is crossed")
        if entry_spread and exact_decimal_multiply(exact_decimal_subtract(ask[0], bid[0]), amount("2")) > (
                exact_decimal_multiply(exact_decimal_add(ask[0], bid[0]), amount("0.005"))):
            raise InputError("entry quote spread exceeds proposed limit")
        return QcNativeQuote(body["security_id"], body["symbol"], hash_bytes(self.raw_bytes),
            cutoff, observed, bid[2], ask[2], bid[0], ask[0], bid[1], ask[1], bid[3], ask[3])

    def decision_quote(self, at: datetime) -> QcNativeQuote:
        instant_ns(at)
        if at.astimezone(_NY).time() != time(10):
            raise InputError("entry decision must be at 10:00 New York")
        return self.quote_at(at, entry_spread=True)

    def subsequent_minute(self, *, submitted_at: datetime, callback_at: datetime,
                          decision_quote: QcNativeQuote | None = None) -> QcNativeExecutionInput:
        submitted, callback = instant_ns(submitted_at), instant_ns(callback_at)
        body, _, minutes = _decode(self.raw_bytes)
        if callback <= submitted:
            raise InputError("execution callback must follow submission")
        if not instant_ns(utc(body["session_open_utc"])) <= submitted <= instant_ns(utc(body["session_close_utc"])):
            raise InputError("native submission outside supplied regular session")
        matches = [minute for minute in minutes if minute.end_timestamp_ns == callback]
        if len(matches) != 1 or matches[0].start_timestamp_ns < submitted:
            raise InputError("no wholly subsequent complete native execution minute")
        if decision_quote is not None:
            decision_at = datetime.combine(day(body["session_date"]), time(10), _NY).astimezone(timezone.utc)
            if type(decision_quote) is not QcNativeQuote:
                raise InputError("exact native decision quote required")
            decision_quote.__post_init__()
            if (decision_quote.as_of_ns != instant_ns(decision_at)
                    or decision_quote.as_of_ns > submitted
                    or decision_quote != self.decision_quote(decision_at)):
                raise InputError("decision quote does not belong to this native source before submission")
        quote = self.quote_at(callback_at)
        if min(quote.bid_updated_ns, quote.ask_updated_ns) <= submitted or min(
                quote.bid_updated_ns, quote.ask_updated_ns) < matches[0].start_timestamp_ns:
            raise InputError("execution cannot reuse decision or pre-submission native side")
        return QcNativeExecutionInput(quote, matches[0], submitted, callback)
