"""Pure paired Alpaca/FirstRate inputs for an explicitly assumed local model.

This is neither the Massive nor QC source contract. One reported Alpaca clock
stays one clock; no participant/SIP timestamp, sequence or qualified source is
manufactured. Unknown conditions remain literal and can enter the separate
model only through an explicit, hash-bound assumption. No fetching or fills.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from decimal import Decimal
import re
from zoneinfo import ZoneInfo

from data.financial_primitives import (
    decimal_text, exact_decimal_add, exact_decimal_multiply, exact_decimal_subtract,
)
from data.hashing import hash_bytes, hash_payload
from research.guidance_revision_drift.firstrate import ReconciledRow, regular_minute
from research.guidance_revision_drift.historical_market import HistoricalMinute, instant_ns
from research.guidance_revision_drift.input_contracts import (
    InputError, amount, decode_object, digest, identifier,
)
from research.guidance_revision_drift.research_reference import CalendarSession

MAX_PAGE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_PAGES = 128
MAX_QUOTES = 400_000
_MINUTE = 60_000_000_000
_QUOTE_KEYS = frozenset({'t', 'bx', 'bp', 'bs', 'ap', 'as', 'ax', 'c', 'z'})
_CLOCK = re.compile(r'([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})(?:\.([0-9]{1,9}))?Z')
_NY = ZoneInfo('America/New_York')


def _gates() -> dict:
    return {'point_in_time_data': False, 'source_execution_qualified': False,
            'source_completeness_verified': False, 'historical_availability_verified': False,
            'reference_mapping_verified': False, 'calendar_verified': False,
            'source_rights_verified': False, 'native_execution_verified': False,
            'execution_authority': False, 'backtest_ready': False}


def _clock_ns(value: object) -> int:
    matched = _CLOCK.fullmatch(value) if type(value) is str else None
    if matched is None:
        raise InputError('explicit Alpaca UTC nanosecond clock required')
    try:
        whole = datetime.fromisoformat(matched[1]).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise InputError('invalid Alpaca quote clock') from exc
    return instant_ns(whole) + int((matched[2] or '').ljust(9, '0'))


def _scope(security_id, symbol, role, session, capture_start_ns, capture_end_ns,
           allow_unknown_conditions, assumption_sha256):
    identifier(security_id)
    identifier(symbol)
    if type(role) is not str or role not in {'stock', 'benchmark'}:
        raise InputError('explicit stock or benchmark role required')
    if (role == 'benchmark') != (symbol == 'SPY'):
        raise InputError('SPY must have the explicit benchmark role')
    if type(session) is not CalendarSession:
        raise InputError('exact supplied CalendarSession required')
    session.__post_init__()
    if not date(2013, 1, 1) <= session.session_date < date(2026, 9, 1):
        raise InputError('unprotected exploratory market session required')
    if (type(capture_start_ns) is not int or type(capture_end_ns) is not int
            or not instant_ns(session.open_utc) <= capture_start_ns < capture_end_ns
            <= instant_ns(session.close_utc)):
        raise InputError('explicit nonempty in-session inclusive capture bounds required')
    if type(allow_unknown_conditions) is not bool:
        raise InputError('strict exploratory condition choice required')
    if allow_unknown_conditions:
        digest(assumption_sha256)
    elif assumption_sha256 is not None:
        raise InputError('condition assumption anchor without model choice')


def _raw_number(value):
    if type(value) not in (int, Decimal):
        raise InputError('provider numeric JSON lexeme required')
    return amount(value, nonnegative=True)


def _size(value):
    if type(value) is not int or not 0 <= value <= 10**12:
        raise InputError('bounded exact raw quote size required')
    return value


@dataclass(frozen=True, slots=True)
class ExploratoryQuote:
    security_id: str
    symbol: str
    source_page_sha256: str
    timestamp_ns: int
    bid: Decimal
    ask: Decimal
    bid_size_raw: int
    ask_size_raw: int
    raw_size_unit: str
    bid_exchange: str
    ask_exchange: str
    conditions: tuple[str, ...]
    tape: str
    unknown_condition_assumption_sha256: str | None

    def __post_init__(self):
        identifier(self.security_id)
        identifier(self.symbol)
        digest(self.source_page_sha256)
        if (type(self.timestamp_ns) is not int or not
                instant_ns(datetime(2013, 1, 1, tzinfo=timezone.utc)) <= self.timestamp_ns <
                instant_ns(datetime(2026, 9, 1, tzinfo=timezone.utc))):
            raise InputError('bounded exact exploratory quote clock required')
        for value in (self.bid, self.ask):
            if type(value) is not Decimal:
                raise InputError('exact exploratory quote Decimal required')
            amount(value, nonnegative=True)
        _size(self.bid_size_raw)
        _size(self.ask_size_raw)
        if type(self.raw_size_unit) is not str or self.raw_size_unit not in {'shares', 'round_lots'}:
            raise InputError('explicit raw quote size unit required')
        if (type(self.conditions) is not tuple or len(self.conditions) > 2
                or any(type(flag) is not str or len(flag) != 1 or not 32 <= ord(flag) <= 126
                       for flag in self.conditions)):
            raise InputError('immutable literal quote conditions required')
        if type(self.tape) is not str or self.tape not in {'A', 'B', 'C'}:
            raise InputError('explicit stock quote tape required')
        for venue in (self.bid_exchange, self.ask_exchange):
            if type(venue) is not str or re.fullmatch(r'[A-Z ]', venue) is None:
                raise InputError('bounded exploratory quote exchange required')
        if self.unknown_condition_assumption_sha256 is not None:
            digest(self.unknown_condition_assumption_sha256)
            if '?' not in self.conditions:
                raise InputError('quote assumption anchor requires literal unknown condition')

    @property
    def unknown_condition_assumed(self) -> bool:
        return '?' in self.conditions and self.unknown_condition_assumption_sha256 is not None

    def projection(self) -> dict:
        self.__post_init__()
        return {'security_id': self.security_id, 'symbol': self.symbol,
            'source_page_sha256': self.source_page_sha256, 'timestamp_ns': self.timestamp_ns,
            'clock_kind': 'Alpaca_reported_quote_timestamp',
            'participant_timestamp_ns': None, 'sip_timestamp_ns': None, 'sequence_number': None,
            'bid': decimal_text(self.bid), 'ask': decimal_text(self.ask),
            'bid_size_raw': self.bid_size_raw, 'ask_size_raw': self.ask_size_raw,
            'raw_size_unit': self.raw_size_unit, 'bid_exchange': self.bid_exchange,
            'ask_exchange': self.ask_exchange, 'conditions': list(self.conditions), 'tape': self.tape,
            'unknown_condition_assumed': self.unknown_condition_assumed,
            'condition_model_assumption_sha256': self.unknown_condition_assumption_sha256,
            'original_condition_recovered': False, **_gates()}

    def _state(self) -> tuple:
        # Source-page identity cannot turn duplicate states into extra liquidity.
        return (self.timestamp_ns, self.bid, self.ask, self.bid_size_raw, self.ask_size_raw,
                self.raw_size_unit, self.bid_exchange, self.ask_exchange, self.conditions, self.tape)


def _decode_pages(batch):
    _scope(batch.security_id, batch.symbol, batch.role, batch.session,
           batch.capture_start_ns, batch.capture_end_ns,
           batch.allow_unknown_conditions, batch.assumption_sha256)
    pages = batch.raw_pages
    if (type(pages) is not tuple or not 1 <= len(pages) <= MAX_PAGES
            or any(type(page) is not bytes or not page or len(page) > MAX_PAGE_BYTES for page in pages)
            or sum(map(len, pages)) > MAX_TOTAL_BYTES):
        raise InputError('bounded immutable Alpaca page inventory required')
    start, end = batch.capture_start_ns, batch.capture_end_ns
    unit = 'shares' if batch.session.session_date >= date(2025, 11, 3) else 'round_lots'
    quotes, previous, tokens = [], start, set()
    for index, raw in enumerate(pages):
        body = decode_object(raw, MAX_PAGE_BYTES, provider_numbers=True)
        if set(body) not in ({'symbol', 'quotes', 'next_page_token'},
                             {'symbol', 'quotes', 'next_page_token', 'currency'}):
            raise InputError('unexpected Alpaca page envelope')
        if body['symbol'] != batch.symbol or ('currency' in body and body['currency'] != 'USD'):
            raise InputError('Alpaca response symbol or currency mismatch')
        rows, token = body['quotes'], body['next_page_token']
        if type(rows) is not list or len(rows) > 10_000 or len(quotes) + len(rows) > MAX_QUOTES:
            raise InputError('bounded Alpaca quote list required')
        if token is not None:
            if (type(token) is not str or not 1 <= len(token) <= 4096 or token in tokens
                    or any(ord(char) < 33 or ord(char) > 126 for char in token)):
                raise InputError('bounded unique pagination token required')
            tokens.add(token)
        if (index == len(pages) - 1) != (token is None):
            raise InputError('declared Alpaca page chain is incomplete or inconsistent')
        source = hash_bytes(raw)
        for row in rows:
            if type(row) is not dict or set(row) != _QUOTE_KEYS:
                raise InputError('exact Alpaca paired quote properties required')
            stamp = _clock_ns(row['t'])
            if not start <= stamp <= end or stamp < previous:
                raise InputError('Alpaca clocks must be nondecreasing inside captured request interval')
            previous = stamp
            flags = row['c']
            if (type(flags) is not list or len(flags) > 2
                    or any(type(flag) is not str or len(flag) != 1
                           or not 32 <= ord(flag) <= 126 for flag in flags)):
                raise InputError('bounded per-side Alpaca condition strings required')
            if type(row['z']) is not str or row['z'] not in {'A', 'B', 'C'}:
                raise InputError('explicit regular-session stock tape required')
            for exchange in ('bx', 'ax'):
                if type(row[exchange]) is not str or re.fullmatch(r'[A-Z ]', row[exchange]) is None:
                    raise InputError('bounded Alpaca exchange code required')
            quotes.append(ExploratoryQuote(batch.security_id, batch.symbol, source, stamp,
                _raw_number(row['bp']), _raw_number(row['ap']), _size(row['bs']), _size(row['as']),
                unit, row['bx'], row['ax'], tuple(flags), row['z'],
                batch.assumption_sha256 if '?' in flags and batch.allow_unknown_conditions else None))
    return tuple(quotes)


@dataclass(frozen=True, slots=True)
class AlpacaQuoteBatch:
    raw_pages: tuple[bytes, ...] = field(repr=False)
    security_id: str
    symbol: str
    role: str
    session: CalendarSession
    capture_start_ns: int
    capture_end_ns: int
    allow_unknown_conditions: bool = False
    assumption_sha256: str | None = None

    def __post_init__(self):
        _decode_pages(self)

    @property
    def quotes(self) -> tuple[ExploratoryQuote, ...]:
        return _decode_pages(self)

    @property
    def sha256(self) -> str:
        self.__post_init__()
        return hash_payload({'schema': 'gdr.exploratory-alpaca-paired.v1',
            'security_id': self.security_id, 'symbol': self.symbol, 'role': self.role,
            'date': self.session.session_date.isoformat(),
            'session_open_utc': self.session.open_utc.isoformat(),
            'session_close_utc': self.session.close_utc.isoformat(),
            'capture_start_ns': self.capture_start_ns, 'capture_end_ns': self.capture_end_ns,
            'capture_interval_semantics': 'requested_start_and_end_inclusive',
            'page_sha256s': [hash_bytes(raw) for raw in self.raw_pages],
            'allow_unknown_conditions': self.allow_unknown_conditions,
            'assumption_sha256': self.assumption_sha256})

    def projection(self) -> dict:
        quotes = self.quotes
        return {'schema': 'gdr.exploratory-alpaca-paired-summary.v1', 'sha256': self.sha256,
            'security_id': self.security_id, 'symbol': self.symbol, 'role': self.role,
            'session_date': self.session.session_date.isoformat(), 'pages': len(self.raw_pages),
            'capture_start_ns': self.capture_start_ns, 'capture_end_ns': self.capture_end_ns,
            'capture_interval_semantics': 'requested_start_and_end_inclusive',
            'first_returned_quote_ns': quotes[0].timestamp_ns if quotes else None,
            'last_returned_quote_ns': quotes[-1].timestamp_ns if quotes else None,
            'quotes': len(quotes), 'unknown_condition_rows': sum('?' in q.conditions for q in quotes),
            'condition_assumption_rows': sum(q.unknown_condition_assumed for q in quotes),
            'declared_page_chain_complete_only': True, 'assumption_sha256': self.assumption_sha256,
            **_gates()}

    def quote_at(self, at: datetime, *, after: datetime | None = None,
                 entry_spread: bool = False) -> ExploratoryQuote:
        _scope(self.security_id, self.symbol, self.role, self.session,
               self.capture_start_ns, self.capture_end_ns,
               self.allow_unknown_conditions, self.assumption_sha256)
        at_ns = instant_ns(at)
        if type(entry_spread) is not bool:
            raise InputError('strict entry-spread choice required')
        if not instant_ns(self.session.open_utc) <= at_ns <= instant_ns(self.session.close_utc):
            raise InputError('quote selection outside supplied session')
        if not self.capture_start_ns <= at_ns <= self.capture_end_ns:
            raise InputError('quote selection outside captured request interval')
        after_ns = instant_ns(after) if after is not None else None
        if after_ns is not None and not instant_ns(self.session.open_utc) <= after_ns < at_ns:
            raise InputError('strict earlier in-session submission required')
        eligible = [quote for quote in self.quotes if quote.timestamp_ns <= at_ns]
        if not eligible:
            raise InputError('no observed quote at or before model instant')
        latest = eligible[-1].timestamp_ns
        group = [quote for quote in eligible if quote.timestamp_ns == latest]
        if len({quote._state() for quote in group}) != 1:
            raise InputError('ambiguous equal-clock quote states require later refresh')
        quote = group[-1]
        if at_ns - latest > _MINUTE or (after_ns is not None and latest <= after_ns):
            raise InputError('latest quote is stale or not subsequent')
        if (quote.bid <= 0 or quote.ask <= 0 or quote.bid > quote.ask
                or not quote.bid_size_raw or not quote.ask_size_raw
                or quote.bid_exchange == ' ' or quote.ask_exchange == ' '):
            raise InputError('latest quote is nonpositive crossed or absent')
        allowed = {'R', '?'} if self.allow_unknown_conditions else {'R'}
        if not quote.conditions or not set(quote.conditions) <= allowed:
            raise InputError('latest source condition is not permitted by exploratory model')
        if entry_spread and exact_decimal_multiply(exact_decimal_subtract(quote.ask, quote.bid), Decimal(2)) > (
                exact_decimal_multiply(exact_decimal_add(quote.ask, quote.bid), Decimal('0.005'))):
            raise InputError('entry quote spread exceeds unchanged proposed limit')
        return quote

    def decision_quote(self, at: datetime) -> ExploratoryQuote:
        instant_ns(at)
        if at.astimezone(_NY).time() != time(10):
            raise InputError('entry decision must be at 10:00 New York')
        return self.quote_at(at, entry_spread=True)


def decode_alpaca_quote_pages(pages: tuple[bytes, ...], *, security_id: str, symbol: str,
                             role: str, session: CalendarSession,
                             capture_start_ns: int, capture_end_ns: int,
                             allow_unknown_conditions: bool = False,
                             assumption_sha256: str | None = None) -> AlpacaQuoteBatch:
    return AlpacaQuoteBatch(pages, security_id, symbol, role, session, capture_start_ns, capture_end_ns,
                           allow_unknown_conditions, assumption_sha256)


@dataclass(frozen=True, slots=True)
class ExploratoryExecutionInput:
    quote: ExploratoryQuote
    minute: HistoricalMinute
    submitted_at_ns: int
    callback_at_ns: int

    def projection(self) -> dict:
        return {'quote': self.quote.projection(), 'minute': self.minute.projection(),
            'submitted_at_ns': self.submitted_at_ns, 'callback_at_ns': self.callback_at_ns,
            'minute_participation_cap_shares': self.minute.volume // 100,
            'volume_model': 'completed_post_submission_minute_volume_proxy', **_gates()}


@dataclass(frozen=True, slots=True)
class ExploratoryMarketBatch:
    quote_batch: AlpacaQuoteBatch
    minute_rows: tuple[ReconciledRow, ...] = field(repr=False)

    def __post_init__(self):
        if type(self.quote_batch) is not AlpacaQuoteBatch:
            raise InputError('exact exploratory paired-quote batch required')
        self.quote_batch.__post_init__()
        if type(self.minute_rows) is not tuple or not 1 <= len(self.minute_rows) <= 390:
            raise InputError('bounded immutable FirstRate minute inventory required')
        previous = None
        for row in self.minute_rows:
            minute = regular_minute(row, session=self.session, security_id=self.security_id)
            if minute.symbol != self.symbol or (previous is not None and minute.start_timestamp_ns <= previous):
                raise InputError('matching ordered unique FirstRate minutes required')
            previous = minute.start_timestamp_ns

    @property
    def security_id(self):
        return self.quote_batch.security_id

    @property
    def symbol(self):
        return self.quote_batch.symbol

    @property
    def role(self):
        return self.quote_batch.role

    @property
    def session(self):
        return self.quote_batch.session

    @property
    def quotes(self):
        return self.quote_batch.quotes

    @property
    def minutes(self) -> tuple[HistoricalMinute, ...]:
        self.__post_init__()
        return tuple(regular_minute(row, session=self.session, security_id=self.security_id)
                     for row in self.minute_rows)

    @property
    def sha256(self):
        self.__post_init__()
        return hash_payload({'schema': 'gdr.exploratory-market.v1', 'quotes_sha256': self.quote_batch.sha256,
            'minutes': [row.projection(include_values=True) for row in self.minute_rows]})

    def projection(self) -> dict:
        return {'schema': 'gdr.exploratory-market-summary.v1', 'sha256': self.sha256,
            'quotes': self.quote_batch.projection(), 'minutes': len(self.minutes), **_gates()}

    def quote_at(self, at: datetime, *, after: datetime | None = None,
                 entry_spread: bool = False) -> ExploratoryQuote:
        return self.quote_batch.quote_at(at, after=after, entry_spread=entry_spread)

    def decision_quote(self, at: datetime) -> ExploratoryQuote:
        return self.quote_batch.decision_quote(at)

    def subsequent_minute(self, *, submitted_at: datetime, callback_at: datetime,
                          decision_quote: ExploratoryQuote | None = None) -> ExploratoryExecutionInput:
        submitted, callback = instant_ns(submitted_at), instant_ns(callback_at)
        if callback <= submitted:
            raise InputError('execution callback must follow submission')
        matches = [minute for minute in self.minutes if minute.end_timestamp_ns == callback]
        if len(matches) != 1 or matches[0].start_timestamp_ns < submitted:
            raise InputError('no wholly subsequent complete execution minute')
        if decision_quote is not None:
            if (type(decision_quote) is not ExploratoryQuote or decision_quote not in self.quotes
                    or decision_quote.timestamp_ns > submitted):
                raise InputError('decision quote not in supplied source before submission')
        quote = self.quote_at(callback_at, after=submitted_at)
        if quote.timestamp_ns < matches[0].start_timestamp_ns:
            raise InputError('execution quote predates completed execution minute')
        return ExploratoryExecutionInput(quote, matches[0], submitted, callback)


def attach_first_rate_minutes(quotes: AlpacaQuoteBatch,
                              rows: tuple[ReconciledRow, ...]) -> ExploratoryMarketBatch:
    return ExploratoryMarketBatch(quotes, rows)
