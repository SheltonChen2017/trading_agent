"""Separate TPR-DEV-RAWREV-v1 stock-only development proxy; no source opener.

Raw new/prior minus one is not a comparable-horizon canonical target signal.
Unknown horizon/share-basis and current-snapshot/restatement risks remain
explicit. Supplied source/calendar inventories are not authenticated here.
Only flat in-memory native-schema projections are consumed; real identifiers
are never relabelled SYNTHETIC. No I/O, price/outcome join, authority issuance,
order engine, operator state or canonical gate is reachable from this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import re

SCHEMA = "TPR-DEV-RAWREV-v1"
MAX_ROWS = 100_000
MAX_SESSIONS = 10_000
_RATING = {"benzinga_id", "benzinga_firm_id", "ticker", "date", "last_updated", "currency",
           "price_target_action", "price_target", "previous_price_target"}
_IDENTITY = {"ticker", "security_id", "permaticker", "figi", "category", "exchange", "isdelisted"}
_ACTION = {"ticker", "date", "action"}
_SESSION = {"session_date", "open_utc"}
_EXCHANGES = {"NYSE": "XNYS", "NASDAQ": "XNAS", "NYSEMKT": "XASE",
              "XNYS": "XNYS", "XNAS": "XNAS", "XASE": "XASE"}


class RawRevisionError(ValueError):
    """Fixed framing refusal, never source values or account details."""


@dataclass(frozen=True)
class RawRevisionEvent:
    benzinga_id: str | int
    benzinga_firm_id: str | int
    ticker: str
    security_id: str | int
    permaticker: str | int
    figi: str
    exchange: str
    issued_date: str
    last_updated_utc: str
    capture_utc: str
    eligible_open_utc: str
    eligible_session_index: int
    price_target: str
    previous_price_target: str
    raw_revision_ratio: str
    later_touch: bool
    horizon_status: str = "unknown-not-comparable"
    raw_share_basis_unproven: bool = True
    historical_identity_proven: bool = False


@dataclass(frozen=True)
class RawRevisionDisposition:
    benzinga_id: str | int | None
    ticker: str | None
    reason: str
    occurrences: int


@dataclass(frozen=True)
class RawRevisionResult:
    events: tuple[RawRevisionEvent, ...]
    dispositions: tuple[RawRevisionDisposition, ...]
    input_rows: int
    duplicate_rows: int
    refusal_counts: tuple[tuple[str, int], ...]
    cutoff_utc: str
    capture_utc: str
    view: str
    schema: str = SCHEMA
    mode: str = "accepted-risk-raw-revision-development-proxy"
    non_pristine_current_snapshot: bool = True
    point_in_time_data: bool = False
    canonical_admission: bool = False
    outcome_access: bool = False
    quantconnect: bool = False
    trading: bool = False
    source_inventory_authenticated: bool = False
    calendar_authenticated: bool = False


def _fail(reason):
    raise RawRevisionError(reason)


def _schema(value, keys):
    if (type(value) is not dict or len(value) != len(keys)
            or any(type(key) is not str for key in value) or set(value) != keys):
        _fail("invalid closed raw-revision schema")


def _signature(row):
    result = []
    for key in sorted(row):
        value = row[key]
        if type(value) is str and len(value) <= 256:
            rendered = value
        elif value is None or type(value) in (bool, int) and (type(value) is bool or value.bit_length() <= 128):
            rendered = str(value)
        elif type(value) is Decimal:
            rendered = str(value)
            if len(rendered) > 256:
                _fail("source primitive resource bound")
        elif type(value) is float:
            # Native floats remain invalid targets, but can retain a named
            # per-record disposition without evaluating caller callbacks.
            rendered = value.hex()
        else:
            _fail("invalid flat source primitive")
        result.append((key, type(value).__name__, rendered))
    return tuple(result)


def _rows(value, keys, maximum=MAX_ROWS):
    if type(value) not in (tuple, list) or len(value) > maximum:
        _fail("invalid bounded raw-revision inventory")
    result = []
    for row in value:
        _schema(row, keys)
        _signature(row)
        result.append(dict(row))
    return tuple(result)


def _native_id(value):
    if type(value) is int:
        return 0 < value < 10**30
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:\-]{0,127}", value) is not None


def _ticker(value):
    return type(value) is str and re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,31}", value) is not None


def _day(value):
    if type(value) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        _fail("invalid source session date")
    try:
        return date.fromisoformat(value)
    except ValueError:
        _fail("invalid source session date")


def _utc(value):
    if type(value) is not str or len(value) > 64:
        _fail("invalid source UTC clock")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError
        return stamp.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        _fail("invalid source UTC clock")


def _calendar(value):
    rows = _rows(value, _SESSION, MAX_SESSIONS)
    result = []
    for row in rows:
        day, opened = _day(row["session_date"]), _utc(row["open_utc"])
        if opened.date() != day or (result and (day <= result[-1][0] or opened <= result[-1][1])):
            _fail("invalid ordered session calendar")
        result.append((day, opened))
    return tuple(result)


def _number(value):
    if type(value) is str:
        if len(value) > 96 or re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value) is None:
            return None, "invalid_positive_target"
        try:
            number = Decimal(value)
        except InvalidOperation:
            return None, "invalid_positive_target"
    elif type(value) is Decimal:
        number = value
    elif type(value) is int:
        number = Decimal(value)
    else:
        return None, "invalid_positive_target"
    if not number.is_finite() or number <= 0:
        return None, "invalid_positive_target"
    digits = number.as_tuple()
    if len(digits.digits) > 64 or not -32 <= digits.exponent <= 32 or number.copy_abs() > Decimal(10**24):
        return None, "target_resource_bound"
    return number, None


def _number_text(number):
    value = format(number, "f")
    return value.rstrip("0").rstrip(".") if "." in value else value


def _ratio(new, previous):
    value = Fraction(new) / Fraction(previous) - 1
    return str(value.numerator) if value.denominator == 1 else str(value.numerator) + "/" + str(value.denominator)


def _identity_reason(row):
    if (not _native_id(row["security_id"]) or not _native_id(row["permaticker"])
            or type(row["figi"]) is not str or re.fullmatch(r"[A-Z0-9]{12}", row["figi"]) is None
            or type(row["isdelisted"]) is not bool):
        return "invalid_snapshot_identity"
    if type(row["category"]) is not str or row["category"] != "Domestic Common Stock":
        return "not_domestic_common_stock"
    if type(row["exchange"]) is not str or row["exchange"] not in _EXCHANGES:
        return "unsupported_exchange"
    if row["isdelisted"]:
        return "current_snapshot_delisted"
    return None


def _identity_map(rows):
    groups, keys = {}, {}
    for row in rows:
        if not _ticker(row["ticker"]):
            _fail("invalid snapshot ticker")
        groups.setdefault(row["ticker"], {})[_signature(row)] = row
        for field in ("security_id", "permaticker", "figi"):
            if _native_id(row[field]):
                key = (field, type(row[field]).__name__, str(row[field]))
                keys.setdefault(key, set()).add(row["ticker"])
    ambiguous = set()
    for symbols in keys.values():
        if len(symbols) > 1:
            ambiguous.update(symbols)
    return groups, ambiguous


def _action_exclusions(rows, cutoff):
    exclusions = set()
    for row in rows:
        if not _ticker(row["ticker"]):
            _fail("invalid action ticker")
        day = _day(row["date"])
        if day > cutoff.date():
            continue
        # With no prior-target date or adjustment-vintage proof, any supplied
        # action at/before this cutoff is a basis/identity ambiguity. Unknown
        # actions are not harmless; no split factor or repair is invented.
        exclusions.add(row["ticker"])
    return exclusions


def normalize_raw_revisions(ratings, identities, actions, sessions, *, cutoff_utc, capture_utc,
                            view="censored", action_inventory_complete):
    """Normalize the explicitly separate, unknown-horizon stock-only proxy.

    Native IDs/types and original eligibility are retained. Censored excludes
    touches beyond the supplied cutoff; current admits/discloses later touches
    without claiming earlier payload recovery. Both views are non-PIT. Only
    use this as-of result at its own cutoff, not as a hindsight earlier bundle.
    The second supplied exchange open strictly after issued UTC date is the
    frozen conservative timing policy. Actual calendar/source authentication
    and whole-run corporate-action/outcome admission remain outside this API.
    """
    if type(view) is not str or view not in ("current", "censored"):
        _fail("invalid raw-revision view")
    if type(action_inventory_complete) is not bool:
        _fail("invalid action-inventory completeness")
    cutoff, capture = _utc(cutoff_utc), _utc(capture_utc)
    if cutoff > capture:
        _fail("cutoff exceeds source capture")
    rows = _rows(ratings, _RATING)
    mapping, ambiguous = _identity_map(_rows(identities, _IDENTITY))
    exclusions = _action_exclusions(_rows(actions, _ACTION), cutoff)
    axis = _calendar(sessions)
    groups = {}
    for row in rows:
        native = row["benzinga_id"]
        if not _native_id(native):
            _fail("invalid native event identity")
        key = (type(native).__name__, str(native))
        groups.setdefault(key, []).append(row)
    events, dispositions, counts = [], [], {}
    duplicates = 0
    for key in sorted(groups):
        group = groups[key]
        duplicates += len(group) - 1
        row = min(group, key=_signature)
        reason = None
        if len({_signature(item) for item in group}) != 1:
            reason = "conflicting_native_event_id"
        elif not _ticker(row["ticker"]):
            reason = "invalid_rating_ticker"
        elif not _native_id(row["benzinga_firm_id"]):
            reason = "invalid_firm_id"
        try:
            issued = _day(row["date"])
        except RawRevisionError:
            issued = None
            reason = reason or "invalid_issued_date"
        try:
            touched = _utc(row["last_updated"])
        except RawRevisionError:
            touched = None
            reason = reason or "invalid_touch_clock"
        if reason is None:
            if issued > cutoff.date():
                reason = "issued_after_cutoff"
            elif touched.date() < issued:
                reason = "touch_precedes_issue_date"
            elif touched > capture:
                reason = "touch_after_capture"
            elif view == "censored" and touched > cutoff:
                reason = "later_touch_censored"
        if reason is None and row["currency"] != "USD":
            reason = "unsupported_currency"
        new, new_reason = _number(row["price_target"])
        previous, prior_reason = _number(row["previous_price_target"])
        if reason is None:
            action = row["price_target_action"]
            if action in ("sets", "announces"):
                reason = "initiation_not_revision"
            elif action == "withdraws":
                reason = "withdrawal_not_revision"
            elif type(action) is not str or action not in ("raises", "lowers", "maintains"):
                reason = "unsupported_target_action"
            elif new_reason or prior_reason:
                reason = new_reason or prior_reason
            elif (new > previous) - (new < previous) != {"raises": 1, "lowers": -1, "maintains": 0}[action]:
                reason = "action_direction_conflict"
        identity = None
        if reason is None:
            candidates = mapping.get(row["ticker"], {})
            if not candidates:
                reason = "missing_snapshot_identity"
            elif len(candidates) != 1 or row["ticker"] in ambiguous:
                reason = "ambiguous_snapshot_identity"
            else:
                identity = next(iter(candidates.values()))
                reason = _identity_reason(identity)
        if reason is None:
            if not action_inventory_complete:
                reason = "action_inventory_incomplete"
            elif row["ticker"] in exclusions:
                reason = "corporate_action_ambiguity"
        eligible = None
        if reason is None:
            if not axis or axis[0][0] > issued:
                reason = "calendar_anchor_missing"
            else:
                later = tuple((index, opened) for index, (day, opened) in enumerate(axis) if day > issued)
                if len(later) < 2:
                    reason = "insufficient_calendar"
                else:
                    index, eligible = later[1]
                    if eligible > cutoff:
                        reason = "not_yet_eligible"
        if reason is None:
            events.append(RawRevisionEvent(
                row["benzinga_id"], row["benzinga_firm_id"], row["ticker"], identity["security_id"],
                identity["permaticker"], identity["figi"], _EXCHANGES[identity["exchange"]], issued.isoformat(),
                touched.isoformat(), capture.isoformat(), eligible.isoformat(), index,
                _number_text(new), _number_text(previous), _ratio(new, previous), touched > cutoff))
            reason = "accepted_proxy_revision"
        else:
            counts[reason] = counts.get(reason, 0) + len(group)
        dispositions.append(RawRevisionDisposition(row["benzinga_id"],
                            row["ticker"] if _ticker(row["ticker"]) else None, reason, len(group)))
    return RawRevisionResult(tuple(events), tuple(dispositions), len(rows), duplicates,
                             tuple(sorted(counts.items())), cutoff.isoformat(), capture.isoformat(), view)
