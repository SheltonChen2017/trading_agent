"""Pure, date-quarantined FirstRate raw bars/actions and duplicate reconciliation.

No file/network access, calendar discovery, security mapping, quotes, cash
posting, source-rights certification or execution is performed. A row date is
checked before payload decoding or hashing. Hashes identify supplied eligible
bytes; they do not authenticate a provider, subscription or availability clock.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, DecimalException
from pathlib import PurePosixPath
import re
from zoneinfo import ZoneInfo

from data.financial_primitives import decimal_text
from data.hashing import hash_bytes, hash_payload
from research.guidance_revision_drift.historical_market import HistoricalMinute, instant_ns
from research.guidance_revision_drift.input_contracts import InputError, amount, digest, identifier
from research.guidance_revision_drift.research_reference import CalendarSession

START = date(2013, 1, 1)
STOP = date(2026, 9, 1)
MAX_LINE_BYTES = 4096
MAX_RECORDS = 100_000
NY = ZoneInfo("America/New_York")
KINDS = frozenset(("daily", "minute", "split", "dividend"))
Key = tuple[str, str, str]
_DATE = re.compile(rb"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_STAMP = re.compile(rb"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:00\Z")
_NUMBER = re.compile(rb"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\Z")



def _provider_amount(token: bytes) -> Decimal:
    """FirstRate CSV decimals may use scientific notation; never float decoding.

    Provider lexical syntax is separate from canonical normalized decimal text.
    Existing finite/precision/exponent limits and downstream sign/volume/OHLC
    checks remain authoritative after an exact Decimal construction.
    """
    if type(token) is not bytes or not 1 <= len(token) <= 128 or not _NUMBER.fullmatch(token):
        raise InputError("invalid_or_nonfinite_numeric")
    try:
        return amount(Decimal(token.decode("ascii")))
    except (DecimalException, InputError) as exc:
        raise InputError("invalid_or_nonfinite_numeric") from exc


def _member(value: object) -> str:
    if (type(value) is not str or not 1 <= len(value) <= 512 or "\\" in value
            or any(ord(char) < 32 or ord(char) > 126 for char in value)
            or PurePosixPath(value).is_absolute() or ".." in value.split("/")
            or any(part == "" for part in value.split("/"))):
        raise InputError("safe relative FirstRate member label required")
    return value


def _flags() -> dict:
    return {"provider": "firstrate", "normalization": "Raw", "fill_forward": False,
            "point_in_time_data": False, "coverage_verified": False,
            "calendar_verified": False, "reference_mapping_verified": False,
            "historical_availability_verified": False, "execution_authority": False,
            "native_execution_evidence": False}


@dataclass(frozen=True, slots=True, order=True)
class SourceRef:
    source_id: str
    member: str
    line_number: int
    line_sha256: str | None

    def __post_init__(self) -> None:
        identifier(self.source_id)
        _member(self.member)
        if type(self.line_number) is not int or not 1 <= self.line_number <= 100_000_000:
            raise InputError("bounded positive FirstRate line number required")
        if self.line_sha256 is not None:
            digest(self.line_sha256)

    def projection(self) -> dict:
        return {"source_id": self.source_id, "member": self.member,
                "line_number": self.line_number, "line_sha256": self.line_sha256}



def _minute_bounds(stamp: str) -> tuple[datetime, datetime]:
    """One checked conversion for parsed and manually constructed projections."""
    try:
        if type(stamp) is not str or not _STAMP.fullmatch(stamp.encode("ascii")):
            raise InputError("invalid_minute_timestamp")
        naive = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
    except (ValueError, UnicodeError) as exc:
        raise InputError("invalid_minute_timestamp") from exc
    earlier = naive.replace(tzinfo=NY, fold=0)
    later = naive.replace(tzinfo=NY, fold=1)
    if earlier.utcoffset() != later.utcoffset() or (
        earlier.astimezone(timezone.utc).astimezone(NY).replace(tzinfo=None) != naive
    ):
        raise InputError("ambiguous_or_nonexistent_local_minute")
    opening = earlier.astimezone(timezone.utc)
    return opening, opening + timedelta(minutes=1)


def _key(key: object) -> Key:
    if type(key) is not tuple or len(key) != 3:
        raise InputError("exact FirstRate row key required")
    identifier(key[0])
    if type(key[1]) is not str or key[1] not in KINDS or type(key[2]) is not str:
        raise InputError("FirstRate kind and timestamp required")
    try:
        observed = date.fromisoformat(key[2][:10])
        expected = _minute_bounds(key[2])[0] if key[1] == "minute" else observed
    except InputError:
        raise
    except ValueError as exc:
        raise InputError("invalid FirstRate row key timestamp") from exc
    if not START <= observed < STOP or (
        key[1] == "minute" and (len(key[2]) != 19 or expected.second)
    ) or (key[1] != "minute" and key[2] != observed.isoformat()):
        raise InputError("unprotected canonical FirstRate key required")
    return key


def _values(kind: str, values: object) -> tuple[Decimal, ...]:
    expected = 5 if kind in ("daily", "minute") else 1
    if type(values) is not tuple or len(values) != expected or any(type(x) is not Decimal for x in values):
        raise InputError("exact FirstRate decimal tuple required")
    if kind in ("daily", "minute"):
        opening, high, low, close = (amount(x, positive=True) for x in values[:4])
        volume = amount(values[4], nonnegative=True)
        if not low <= min(opening, close) <= max(opening, close) <= high:
            raise InputError("firstrate_invalid_ohlc_bounds")
        if volume != volume.to_integral_value() or volume > 10**12:
            raise InputError("firstrate_nonintegral_or_excessive_volume")
        if kind == "minute" and volume == 0:
            raise InputError("firstrate_zero_minute_volume")
    else:
        amount(values[0], positive=kind == "split", nonnegative=kind == "dividend")
    return values


@dataclass(frozen=True, slots=True)
class FirstRateLine:
    status: str
    key: Key | None
    values: tuple[Decimal, ...]
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    source: SourceRef
    session_date: date | None
    start_utc: datetime | None = None
    end_utc: datetime | None = None

    def __post_init__(self) -> None:
        if self.status not in ("accepted", "refused", "excluded") or type(self.source) is not SourceRef:
            raise InputError("exact FirstRate parsed record required")
        if type(self.values) is not tuple:
            raise InputError("immutable FirstRate value tuple required")
        _codes(self.reasons)
        _codes(self.warnings)
        self.source.__post_init__()
        if self.session_date is not None and type(self.session_date) is not date:
            raise InputError("exact FirstRate session date required")
        if self.key is not None:
            _key(self.key)
            if self.session_date != date.fromisoformat(self.key[2][:10]):
                raise InputError("FirstRate row date/key mismatch")
        if self.status == "accepted":
            if self.key is None or self.source.line_sha256 is None or self.reasons:
                raise InputError("accepted FirstRate row requires exact key and eligible-byte hash")
            _values(self.key[1], self.values)
            if self.key[1] in ("daily", "minute") and self.session_date.weekday() >= 5:
                raise InputError("weekend_bar_date")
            if self.key[1] == "minute" and (self.start_utc, self.end_utc) != _minute_bounds(self.key[2]):
                raise InputError("minute_conversion_mismatch")
        elif self.values or not self.reasons:
            raise InputError("FirstRate refusal/exclusion must not contain financial values")
        if self.status == "excluded" and (self.key is not None or self.source.line_sha256 is not None):
            raise InputError("excluded financial payload must not be hashed or keyed")

    def projection(self, *, include_values: bool = False) -> dict:
        if type(include_values) is not bool:
            raise InputError("exact projection choice required")
        result = {"status": self.status, "key": list(self.key) if self.key else None,
                  "reasons": list(self.reasons), "warnings": list(self.warnings),
                  "source": self.source.projection(),
                  "session_date": self.session_date.isoformat() if self.session_date else None}
        if include_values:
            result["values"] = [decimal_text(x) for x in self.values]
        return result | _flags()


def parse_line(raw: bytes, *, source_id: str, member: str, line_number: int,
               symbol: str, kind: str, start: date = START, stop: date = STOP) -> FirstRateLine:
    """Decode one supplied raw line. Excluded payloads are neither split nor hashed.

    ``symbol`` is an explicit source label, never an inferred permanent identity.
    These formats have no adjustment flag: callers must select UNADJUSTED source
    members and retain that inventory. This function cannot authenticate a file.
    """
    if type(kind) is not str or kind not in KINDS:
        raise InputError("explicit raw FirstRate kind required")
    identifier(symbol)
    source = SourceRef(source_id, member, line_number, None)
    if kind in ("daily", "minute"):
        period = "1day" if kind == "daily" else "1min"
        if PurePosixPath(member).name != f"{symbol}_full_{period}_UNADJUSTED.txt":
            raise InputError("explicit_matching_unadjusted_member_required")
    if type(start) is not date or type(stop) is not date or not START <= start < stop <= STOP:
        raise InputError("bounded unprotected FirstRate window required")
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_LINE_BYTES:
        raise InputError("bounded FirstRate line bytes required")
    if not raw.strip(b" \t\r\n"):
        return FirstRateLine("excluded", None, (), ("blank_nondata_line",), (), source, None)
    prefix = raw[:10]
    try:
        if not _DATE.fullmatch(prefix):
            raise ValueError
        observed = date.fromisoformat(prefix.decode("ascii"))
    except ValueError:
        return FirstRateLine("refused", None, (), ("invalid_date_prefix",), (), source, None)
    # This must precede hashing, decoding or splitting the financial payload.
    if observed < start or observed >= stop:
        code = "protected_date" if observed >= STOP else "outside_requested_window"
        return FirstRateLine("excluded", None, (), (code,), (), source, observed)
    source = SourceRef(source_id, member, line_number, hash_bytes(raw))
    stamp_length = 19 if kind == "minute" else 10
    stamp = raw[:stamp_length]
    key = (symbol, kind, stamp.decode("ascii", errors="replace"))
    opening = closing = None
    warnings = []
    try:
        if kind == "minute":
            if not _STAMP.fullmatch(stamp) or raw[stamp_length:stamp_length + 1] != b",":
                raise InputError("invalid_minute_timestamp")
            opening, closing = _minute_bounds(stamp.decode("ascii"))
        elif raw[10:11] != b",":
            raise InputError("invalid_date_delimiter")
        if kind in ("daily", "minute") and observed.weekday() >= 5:
            raise InputError("weekend_bar_date")
        if kind in ("split", "dividend") and observed.weekday() >= 5:
            warnings.append("action_effective_date_requires_reconciliation")
        fields = raw.rstrip(b"\r\n").split(b",")
        expected = 6 if kind in ("daily", "minute") else 2
        if len(fields) != expected or fields[0] != stamp:
            raise InputError("invalid_field_count_or_timestamp")
        try:
            values = tuple(_provider_amount(value) for value in fields[1:])
        except (UnicodeError, InputError) as exc:
            raise InputError("invalid_or_nonfinite_numeric") from exc
        _values(kind, values)
        if kind == "daily" and values[-1] == 0:
            warnings.append("zero_daily_volume_requires_reconciliation")
        if kind == "dividend" and values[0] == 0:
            warnings.append("zero_dividend_requires_reconciliation")
        if kind in ("split", "dividend"):
            warnings.append("action_identity_currency_availability_unverified")
        if kind == "dividend":
            warnings.append("dividend_payment_date_missing")
        return FirstRateLine("accepted", key, values, (), tuple(warnings), source,
                             observed, opening, closing)
    except (InputError, ValueError) as exc:
        # Error text is a controlled code, never provider financial values.
        code = str(exc) if isinstance(exc, InputError) else "invalid_minute_timestamp"
        code = code.replace(" ", "_")
        if re.fullmatch(r"[A-Za-z0-9_.:\-]{1,128}", code) is None:
            code = "invalid_firstrate_row"
        try:
            _key(key)
        except InputError:
            key = None  # Ambiguous malformed timestamp blocks the source set.
        return FirstRateLine("refused", key, (), (code,), (), source, observed)


def _codes(codes: object, *, nonempty: bool = False) -> None:
    if (type(codes) is not tuple or len(codes) > 32 or (nonempty and not codes)
            or any(type(code) is not str for code in codes)):
        raise InputError("bounded immutable FirstRate diagnostic tuple required")
    for code in codes:
        identifier(code)
    if len(set(codes)) != len(codes):
        raise InputError("unique FirstRate diagnostics required")


def _source_refs(sources: object) -> None:
    if type(sources) is not tuple or not 1 <= len(sources) <= MAX_RECORDS:
        raise InputError("bounded immutable FirstRate source tuple required")
    locations = set()
    for source in sources:
        if type(source) is not SourceRef or source.line_sha256 is None:
            raise InputError("eligible FirstRate source reference required")
        source.__post_init__()
        location = (source.source_id, source.member, source.line_number)
        if location in locations:
            raise InputError("duplicate FirstRate source-line location")
        locations.add(location)
    if tuple(sorted(sources)) != sources:
        raise InputError("ordered unique eligible source refs required")



@dataclass(frozen=True, slots=True)
class ReconciledRow:
    key: Key
    values: tuple[Decimal, ...]
    sources: tuple[SourceRef, ...]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        _key(self.key)
        _values(self.key[1], self.values)
        if self.key[1] in ("daily", "minute") and date.fromisoformat(self.key[2][:10]).weekday() >= 5:
            raise InputError("weekend_bar_date")
        _source_refs(self.sources)
        _codes(self.warnings)

    @property
    def source_sha256(self) -> str:
        return hash_payload([source.projection() for source in self.sources])

    def projection(self, *, include_values: bool = False) -> dict:
        if type(include_values) is not bool:
            raise InputError("exact projection choice required")
        result = {"key": list(self.key), "sources": [x.projection() for x in self.sources],
                  "source_sha256": self.source_sha256, "warnings": list(self.warnings)}
        if include_values:
            result["values"] = [decimal_text(x) for x in self.values]
        if self.key[1] in ("split", "dividend"):
            result |= {"date_role": "split_effective_date" if self.key[1] == "split" else "dividend_ex_date",
                       "security_id": None, "currency": None, "published_at": None,
                       "received_at": None, "validated_at": None,
                       "payment_date": None, "cash_posting_permitted": False}
        return result | _flags()


@dataclass(frozen=True, slots=True)
class QuarantinedRow:
    key: Key
    reasons: tuple[str, ...]
    sources: tuple[SourceRef, ...]

    def __post_init__(self) -> None:
        _key(self.key)
        _codes(self.reasons, nonempty=True)
        if tuple(sorted(self.reasons)) != self.reasons:
            raise InputError("ordered FirstRate quarantine diagnostics required")
        _source_refs(self.sources)

    def projection(self) -> dict:
        self.__post_init__()
        return {"key": list(self.key), "reasons": list(self.reasons),
                "sources": [x.projection() for x in self.sources]}


@dataclass(frozen=True, slots=True)
class Reconciliation:
    accepted: tuple[ReconciledRow, ...]
    quarantined: tuple[QuarantinedRow, ...]
    refusals: tuple[FirstRateLine, ...]
    excluded: tuple[FirstRateLine, ...]
    input_records: int

    def __post_init__(self) -> None:
        if type(self.input_records) is not int or not 0 <= self.input_records <= MAX_RECORDS:
            raise InputError("bounded exact FirstRate input count required")
        groups = (self.accepted, self.quarantined, self.refusals, self.excluded)
        expected_types = (ReconciledRow, QuarantinedRow, FirstRateLine, FirstRateLine)
        if any(type(group) is not tuple or len(group) > MAX_RECORDS for group in groups):
            raise InputError("immutable bounded FirstRate reconciliation tuples required")
        keys = set()
        locations = set()
        represented = 0
        for index, (group, expected) in enumerate(zip(groups, expected_types)):
            previous = None
            for row in group:
                if type(row) is not expected:
                    raise InputError("exact FirstRate reconciliation member required")
                row.__post_init__()
                if index < 2:
                    if row.key in keys:
                        raise InputError("duplicate_or_overlapping_firstrate_key")
                    keys.add(row.key)
                    ordering = row.key
                    sources = row.sources
                else:
                    if row.status != ("refused" if index == 2 else "excluded") or row.key is not None:
                        raise InputError("FirstRate refusal_or_exclusion_category_mismatch")
                    ordering = (row.source.source_id, row.source.member, row.source.line_number)
                    sources = (row.source,)
                if previous is not None and ordering <= previous:
                    raise InputError("ordered_unique_FirstRate_reconciliation_required")
                previous = ordering
                for source in sources:
                    location = (source.source_id, source.member, source.line_number)
                    if location in locations:
                        raise InputError("source_line_reused_across_FirstRate_groups")
                    locations.add(location)
                    represented += 1
        # Exact re-deliveries count as inputs but not additional source lines.
        if represented > self.input_records or (represented == 0 and self.input_records != 0):
            raise InputError("FirstRate_input_count_source_inventory_mismatch")

    def projection(self, *, include_values: bool = False) -> dict:
        self.__post_init__()
        if type(include_values) is not bool:
            raise InputError("exact projection choice required")
        return {"schema": "gdr.firstrate-reconciliation.v1", "input_records": self.input_records,
                "accepted": [x.projection(include_values=include_values) for x in self.accepted],
                "quarantined": [x.projection() for x in self.quarantined],
                "unkeyed_refusals": [x.projection() for x in self.refusals],
                "excluded": [x.projection() for x in self.excluded],
                "supplied_source_inventory_only": True,
                "source_set_has_unkeyed_refusal": bool(self.refusals),
                "backtest_ready": False} | _flags()

    def require(self, key: Key) -> ReconciledRow:
        """No convenient fallback when an unidentified bad row could share a key."""
        self.__post_init__()
        _key(key)
        if self.refusals:
            raise InputError("unkeyed_refusal_blocks_supplied_source_set")
        for row in self.quarantined:
            if row.key == key:
                raise InputError("quarantined_firstrate_key")
        for row in self.accepted:
            if row.key == key:
                return row
        raise InputError("missing_firstrate_key")


def reconcile_records(records: Iterable[FirstRateLine], *, max_records: int = MAX_RECORDS) -> Reconciliation:
    """Reconcile the *entire supplied* key domain without source precedence.

    Equal numeric duplicates retain every source line; any invalid/conflicting
    occurrence poisons its key. This cannot discover omitted archive copies.
    A caller must bind the complete selected inventory separately.
    """
    if type(max_records) is not int or not 1 <= max_records <= MAX_RECORDS:
        raise InputError("bounded FirstRate reconciliation budget required")
    groups = {}
    excluded = []
    refusals = []
    refs = {}
    count = 0
    for record in records:
        count += 1
        if count > max_records:
            raise InputError("FirstRate reconciliation record budget exceeded")
        if type(record) is not FirstRateLine:
            raise InputError("exact parsed FirstRate record required")
        record.__post_init__()
        location = (record.source.source_id, record.source.member, record.source.line_number)
        previous = refs.get(location)
        if previous is not None:
            if previous != record:
                raise InputError("conflicting_first_rate_source_line_identity")
            continue  # Exact delivery is idempotent, not another source line.
        refs[location] = record
        if record.status == "excluded":
            excluded.append(record)
        elif record.key is None:
            refusals.append(record)
        else:
            groups.setdefault(record.key, []).append(record)
    accepted = []
    quarantined = []
    for key, group in sorted(groups.items()):
        sources = tuple(sorted(x.source for x in group))
        reasons = {code for x in group for code in x.reasons}
        good = [x for x in group if x.status == "accepted"]
        if good and any(x.values != good[0].values for x in good[1:]):
            reasons.add("conflicting_numeric_values")
        if reasons:
            quarantined.append(QuarantinedRow(key, tuple(sorted(reasons)), sources))
        else:
            accepted.append(ReconciledRow(key, good[0].values, sources,
                              tuple(sorted({code for x in group for code in x.warnings}))))
    order = lambda x: (x.source.source_id, x.source.member, x.source.line_number)
    return Reconciliation(tuple(accepted), tuple(quarantined), tuple(sorted(refusals, key=order)),
                          tuple(sorted(excluded, key=order)), count)


def regular_minute(row: ReconciledRow, *, session: CalendarSession, security_id: str) -> HistoricalMinute:
    """Return a raw regular-minute projection, never a quote or executable fill.

    Session bounds and the security identifier are explicit external assertions;
    this does not authenticate them. No holiday/half-day is inferred from bars.
    """
    if type(row) is not ReconciledRow or type(session) is not CalendarSession:
        raise InputError("exact reconciled FirstRate row and supplied session required")
    row.__post_init__()
    session.__post_init__()
    identifier(security_id)
    if row.key[1] != "minute":
        raise InputError("FirstRate regular-minute source required")
    if row.warnings:
        raise InputError("FirstRate row warnings require reconciliation")
    start, end = _minute_bounds(row.key[2])
    if date.fromisoformat(row.key[2][:10]) != session.session_date or not session.open_utc <= start < end <= session.close_utc:
        raise InputError("FirstRate minute outside supplied regular session")
    o, high, low, close, volume = row.values
    return HistoricalMinute(security_id, row.key[0], row.source_sha256,
                            instant_ns(start), instant_ns(end), o, high, low, close, int(volume))
