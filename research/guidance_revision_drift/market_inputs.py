"""Strict, caller-supplied synthetic market inputs; no fetching or PIT claim.

The NYSE schedule is an explicit common execution calendar, not an assertion
that the reference listing exchange was historically verified. Hashes bind
invented input bytes and that schedule, not a vendor entitlement or receipt.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
import re

from data.hashing import canonical_json, hash_bytes
from research.guidance_revision_drift.events import (
    _date, _identifier, _keys, _text, _utc, decode_fixture_object,
)
from research.guidance_revision_drift.simulation import Minute, Quote, _money
from research.guidance_revision_drift.timing import NY, PinnedSchedule, decision_cutoff


class MarketInputError(ValueError):
    """Malformed, misaligned, stale, or unavailable synthetic market input."""


def input_clock(value: object) -> datetime:
    clock = _utc(value)
    if clock.year not in (2024, 2025):
        raise MarketInputError("only invented 2024/2025 inputs are supported")
    return clock


def input_decimal(value: object, *, zero: bool = False) -> Decimal:
    if type(value) is not str or len(value) > 100:
        raise MarketInputError("bounded decimal text required")
    # Decimal accepts scientific notation/whitespace; the input contract does not.
    if re.fullmatch(r"(?:0|[1-9]\d*)(?:\.\d+)?", value) is None:
        raise MarketInputError("nonnegative plain decimal text required")
    return _money(Decimal(value), "input amount", zero=zero)


def calendar_session(schedule: PinnedSchedule, calendar_sha256: str, session_date: date):
    if type(schedule) is not PinnedSchedule:
        raise MarketInputError("exact pinned synthetic calendar required")
    schedule.validate()
    if schedule.sha256 != calendar_sha256:
        raise MarketInputError("calendar content identity mismatch")
    return schedule.sessions[schedule.index(session_date)]


@dataclass(frozen=True, slots=True)
class PreparedMarketInput:
    security_id: str
    issuer_id: str
    sector: str
    quote: Quote
    minute: Minute
    input_sha256: str
    calendar_sha256: str


@dataclass(frozen=True, slots=True)
class SyntheticMarketInput:
    """Immutable paired raw quote/trade plus dated reference and provenance.

    ``amount``-bearing JSON fields use exact decimal strings. No missing value
    is defaulted, forward-filled, adjusted, or fetched. Call ``prepare`` at
    the actual synthetic decision/callback instant, not a backdated instant.
    """

    canonical_bytes: bytes

    def __post_init__(self):
        try:
            body = decode_fixture_object(self.canonical_bytes, 32768)
            _keys(body, frozenset(("schema", "source_id", "calendar_sha256", "session_date",
                                  "received_at", "validated_at", "reference", "quote", "trade")), "market input")
            if body["schema"] != "gdr.synthetic.market-input.v1":
                raise MarketInputError("explicit synthetic market schema required")
            _identifier(body["source_id"])
            if type(body["calendar_sha256"]) is not str or len(body["calendar_sha256"]) != 64 or any(
                    c not in "0123456789abcdef" for c in body["calendar_sha256"]):
                raise MarketInputError("calendar hash required")
            _date(body["session_date"])
            received, validated = (input_clock(body[key]) for key in ("received_at", "validated_at"))
            if validated < received:
                raise MarketInputError("validation precedes receipt")
            reference = _keys(body["reference"], frozenset(("security_id", "issuer_id", "exchange",
                "instrument_type", "primary", "sector", "valid_from", "valid_through", "available_at")), "reference")
            _identifier(reference["security_id"]), _identifier(reference["issuer_id"])
            if reference["exchange"] not in ("NYSE", "NASDAQ", "NYSE_AMERICAN"):
                raise MarketInputError("unsupported listing exchange")
            expected_type = "ETF" if reference["issuer_id"] == "SYN-SPY" else "COMMON_STOCK"
            if reference["instrument_type"] != expected_type or reference["primary"] is not True:
                raise MarketInputError("primary common-share or explicit SYN-SPY ETF reference required")
            _text(reference["sector"], "sector")
            if _date(reference["valid_from"]) > _date(reference["valid_through"]):
                raise MarketInputError("inverted mapping validity")
            input_clock(reference["available_at"])
            intervals = []
            for name, extra in (("quote", ("bid", "ask")), ("trade", ("volume",))):
                row = _keys(body[name], frozenset(("security_id", "start_utc", "end_utc", "normalization",
                                                   "fill_forward", *extra)), name)
                if row["security_id"] != reference["security_id"]:
                    raise MarketInputError("market/reference security identity mismatch")
                if row["normalization"] != "Raw" or row["fill_forward"] is not False:
                    raise MarketInputError("raw non-fill-forward inputs required")
                start, end = input_clock(row["start_utc"]), input_clock(row["end_utc"])
                if end - start != timedelta(minutes=1) or end.second or end.microsecond:
                    raise MarketInputError("aligned complete one-minute interval required")
                if end > received:
                    raise MarketInputError("receipt precedes completed minute")
                intervals.append((start, end))
            if intervals[0] != intervals[1]:
                raise MarketInputError("quote/trade intervals differ")
            if input_decimal(body["quote"]["bid"]) > input_decimal(body["quote"]["ask"]):
                raise MarketInputError("crossed raw quote")
            volume = body["trade"]["volume"]
            if type(volume) is not int or not 0 <= volume <= 10**12:
                raise MarketInputError("bounded integer trade volume required")
            if canonical_json(body).encode() != self.canonical_bytes:
                raise MarketInputError("canonical market bytes required")
        except ValueError as exc:
            raise MarketInputError(str(exc)) from exc

    @classmethod
    def from_dict(cls, body: dict) -> SyntheticMarketInput:
        return cls(canonical_json(body).encode())

    @classmethod
    def from_bytes(cls, raw: bytes) -> SyntheticMarketInput:
        return cls.from_dict(decode_fixture_object(raw, 32768))

    def to_dict(self) -> dict:
        self.__post_init__()
        return decode_fixture_object(self.canonical_bytes, 32768)

    @property
    def sha256(self) -> str:
        self.__post_init__()
        return hash_bytes(self.canonical_bytes)

    def _validated_quote(self, schedule: PinnedSchedule, as_of: datetime):
        body = self.to_dict()
        if type(as_of) is not datetime or as_of.tzinfo is None or as_of.utcoffset() != timedelta(0):
            raise MarketInputError("aware UTC as-of required")
        day = _date(body["session_date"])
        session = calendar_session(schedule, body["calendar_sha256"], day)
        end = input_clock(body["quote"]["end_utc"])
        if not session.open_utc < end <= session.close_utc or as_of.astimezone(NY).date() != day:
            raise MarketInputError("market minute is outside its regular session")
        if not session.open_utc <= as_of <= session.close_utc:
            raise MarketInputError("as-of is outside regular session")
        if end > as_of or as_of - end > timedelta(seconds=60):
            raise MarketInputError("quote/trade minute is future or stale")
        if input_clock(body["validated_at"]) > as_of:
            raise MarketInputError("input was unavailable as of callback")
        ref = body["reference"]
        if not _date(ref["valid_from"]) <= day <= _date(ref["valid_through"]):
            raise MarketInputError("missing dated mapping for session")
        if input_clock(ref["available_at"]) > decision_cutoff(schedule, day):
            raise MarketInputError("reference mapping unavailable at preceding-session cutoff")
        quote = Quote(end, input_decimal(body["quote"]["bid"]), input_decimal(body["quote"]["ask"]))
        return body, quote

    def quote_at(self, schedule: PinnedSchedule, *, as_of: datetime) -> Quote:
        """Latest completed raw quote, at most 60 seconds old; no fill authority."""
        return self._validated_quote(schedule, as_of)[1]

    def prepare(self, schedule: PinnedSchedule, *, as_of: datetime,
                adv20: Decimal, settlement_session: date) -> PreparedMarketInput:
        """Prepare an on-time minute callback; never backdate a delayed receipt.

        Delayed but fresh quotes may still be inspected via ``quote_at``. Their
        old volume/price interval cannot become a retroactive execution minute.
        """
        body, quote = self._validated_quote(schedule, as_of)
        if quote.at != as_of:
            raise MarketInputError("delayed market minute cannot be backdated into an execution")
        day = _date(body["session_date"])
        ref = body["reference"]
        if type(settlement_session) is not date or settlement_session < day:
            raise MarketInputError("known nonpast settlement session required")
        schedule.index(settlement_session)
        _money(adv20, "decision-pinned adv20")
        minute = Minute(ref["issuer_id"], quote.at, quote.bid, quote.ask, body["trade"]["volume"],
                        adv20, settlement_session)
        return PreparedMarketInput(ref["security_id"], ref["issuer_id"], ref["sector"], quote, minute,
                                   self.sha256, schedule.sha256)
