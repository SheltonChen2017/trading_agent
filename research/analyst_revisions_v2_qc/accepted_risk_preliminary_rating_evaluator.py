"""Bounded aggregate-only accepted-risk ARV2 preliminary evaluation."""
import dataclasses
import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from decimal import (
    Context,
    Decimal,
    InvalidOperation,
    ROUND_HALF_EVEN,
    localcontext,
)
from enum import Enum
from fractions import Fraction
from types import MappingProxyType
from typing import Any

try:
    import accepted_risk_preliminary_rating_policy as _policy
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_preliminary_rating_policy as _policy,
    )

class PreliminaryRatingEvaluationError(ValueError):
    pass


_Error = PreliminaryRatingEvaluationError


CONTRACT_ID = _policy.CONTRACT_ID
MANIFEST_SCHEMA = _policy.MANIFEST_SCHEMA
SESSION_SCHEMA = _policy.SESSION_SCHEMA
MEMBERSHIP_SCHEMA = _policy.MEMBERSHIP_SCHEMA
CONTRIBUTION_SCHEMA = _policy.CONTRIBUTION_SCHEMA
SUMMARY_SCHEMA = _policy.SUMMARY_SCHEMA
CELL_SCHEMA = _policy.CELL_SCHEMA
HISTORY_REQUEST_SCHEMA = _policy.HISTORY_REQUEST_SCHEMA
HISTORY_OBSERVATION_SCHEMA = _policy.HISTORY_OBSERVATION_SCHEMA
HISTORY_OBSERVATION = _policy.HISTORY_OBSERVATION
Q_DATA_POLICY_ID = _policy.Q_DATA_POLICY_ID
RATING_HISTORY_START_SESSION = _policy.RATING_HISTORY_START_SESSION
SOURCE_VIEW_IDS = _policy.SOURCE_VIEW_IDS
HORIZONS = _policy.HORIZONS
_PRIMARY_WINDOW = MappingProxyType(_policy.primary_window_record())
_DESCRIPTIVE_WINDOW = MappingProxyType(_policy.descriptive_window_record())
PRIMARY_WINDOW = _PRIMARY_WINDOW
DESCRIPTIVE_WINDOW = _DESCRIPTIVE_WINDOW
_WINDOWS = (_PRIMARY_WINDOW, _DESCRIPTIVE_WINDOW)
WINDOWS = _WINDOWS
SCORE_ARMS = ("firm_specific", "global_comparator")
MAX_SECURITY_COUNT = 25_000
MAX_CONTRIBUTION_COUNT = 2_000_000
MAX_SESSION_COUNT = 4_000
MAX_HISTORY_BATCH_SECURITY_COUNT = 64
MAX_SCORING_SESSIONS_PER_CALLBACK = 5
MAX_SIGNAL_SEED_CONTRIBUTIONS_PER_CALLBACK = 20_000
MAX_HISTORY_OBSERVATION_COUNT = 50_000_000
MAX_HISTORY_MATRIX_SLOT_COUNT = 10_000_000
MAX_CANONICAL_PRICE_TEXT_LENGTH = 64
MAX_BACKTEST_RUNTIME_HOURS = 12
HALF_LIFE_SESSIONS = 20
MINIMUM_TOTAL_NAMES = 20
MINIMUM_ACTIVE_NAMES = 5
MAD_SCALE = Decimal("1.4826")
SCORE_CLIP = Decimal("4")
NUMERICAL_ZERO = Decimal("1e-18")
MINIMUM_IC_ROWS = 20
_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,511}\Z")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_DECIMAL_TEXT = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
_SOURCE_LINEAGE_FIELDS = _policy.SOURCE_LINEAGE_FIELDS
_ACCEPTED_RISK_DISCLOSURES = MappingProxyType(
    _policy.accepted_risk_disclosures_record()
)
ACCEPTED_RISK_DISCLOSURES = _ACCEPTED_RISK_DISCLOSURES
OMITTED_FORMAL_COMPONENTS = _policy.OMITTED_FORMAL_COMPONENTS


def _cell_summary_statistic_name(
    source_view_id: str,
    score_arm: str,
    horizon_sessions: int,
    window_id: str,
) -> str:
    return "ARV2_IC_{}_{}_H{}_{}".format(
        "CUR" if source_view_id == SOURCE_VIEW_IDS[0] else "CEN",
        "FIRM" if score_arm == "firm_specific" else "GLOBAL",
        horizon_sessions,
        "2020_2025" if window_id == _PRIMARY_WINDOW["window_id"] else "2021_2025",
    )


EVALUATOR_CUSTOM_SUMMARY_STATISTIC_NAMES = tuple(sorted((
    "ARV2_PRELIMINARY_META",
    *(
        _cell_summary_statistic_name(
            source_view_id,
            score_arm,
            horizon,
            window["window_id"],
        )
        for window in _WINDOWS
        for source_view_id in SOURCE_VIEW_IDS
        for score_arm in SCORE_ARMS
        for horizon in HORIZONS
    ),
)))

def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise _Error("value is not canonical JSON") from exc


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _stream_sha256(records: Sequence[Mapping[str, object]]) -> str:
    digest = hashlib.sha256()
    for record in records:
        digest.update(_canonical_bytes(record))
        digest.update(b"\n")
    return digest.hexdigest()


def _exact_record(
    value: object, fields: tuple[str, ...], name: str
) -> dict[str, object]:
    if (
        type(value) is not dict
        or any(type(key) is not str for key in value)
        or set(value) != set(fields)
    ):
        raise _Error(f"{name} fields changed")
    return value


def _literal(value: object, expected: object, name: str) -> None:
    if type(value) is not type(expected):
        raise _Error(f"{name} changed type")
    if type(expected) is dict:
        if any(type(key) is not str for key in value) or set(value) != set(expected):
            raise _Error(f"{name} changed fields")
        for key in expected:
            _literal(value[key], expected[key], name)
    elif type(expected) is list:
        if len(value) != len(expected):
            raise _Error(f"{name} changed length")
        for actual, wanted in zip(value, expected, strict=True):
            _literal(actual, wanted, name)
    elif value != expected:
        raise _Error(f"{name} changed value")


def _string(value: object, name: str, *, safe: bool = True) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise _Error(f"{name} must be an exact string")
    if safe and _SAFE_ID.fullmatch(value) is None:
        raise _Error(f"{name} is not a safe identifier")
    return value


def _hash(value: object, name: str) -> str:
    if type(value) is not str or _HEX_64.fullmatch(value) is None:
        raise _Error(f"{name} must be SHA-256")
    return value


def _count(value: object, name: str, *, maximum: int | None = None) -> int:
    if type(value) is not int or value < 0 or (
        maximum is not None and value > maximum
    ):
        raise _Error(f"{name} is outside its exact bound")
    return value


def _positive_count(value: object, name: str, *, maximum: int) -> int:
    result = _count(value, name, maximum=maximum)
    if result == 0:
        raise _Error(f"{name} must be positive")
    return result


def _date(value: object, name: str) -> str:
    text = _string(value, name, safe=False)
    if _DATE.fullmatch(text) is None:
        raise _Error(f"{name} is not ISO date text")
    try:
        from datetime import date

        if date.fromisoformat(text).isoformat() != text:
            raise ValueError
    except ValueError as exc:
        raise _Error(f"{name} is not an ISO date") from exc
    return text


def _decimal(value: object, name: str, *, positive: bool = False) -> Decimal:
    if type(value) is not str or _DECIMAL_TEXT.fullmatch(value) is None:
        raise _Error(f"{name} is not canonical Decimal text")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise _Error(f"{name} is not a Decimal") from exc
    if not result.is_finite() or format(result, "f") != value:
        raise _Error(f"{name} is not canonical Decimal text")
    if positive and result <= 0:
        raise _Error(f"{name} must be positive")
    return result


def _decimal_text(value: Decimal) -> str:
    return "0" if value == 0 else format(value, "f")


def _context() -> Context:
    return Context(
        prec=50,
        rounding=ROUND_HALF_EVEN,
        Emin=-999999,
        Emax=999999,
        capitals=1,
        clamp=0,
    )


def _stable_sum(values: Iterable[Decimal]) -> Decimal:
    ordered = sorted(tuple(values), key=lambda value: (abs(value), value))
    with localcontext(_context()):
        return sum(ordered, Decimal(0))


def _mean(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        raise _Error("mean requires values")
    with localcontext(_context()):
        return +(_stable_sum(values) / Decimal(len(values)))


def _median(values: Iterable[Decimal]) -> Decimal:
    ordered = tuple(sorted(values))
    if not ordered:
        raise _Error("median requires values")
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    with localcontext(_context()):
        return +((ordered[middle - 1] + ordered[middle]) / Decimal(2))


def _decay(age: int) -> Decimal:
    _count(age, "contribution age")
    with localcontext(_context()):
        whole, remainder = divmod(age, HALF_LIFE_SESSIONS)
        weight = Decimal("0.5") ** whole
        if remainder:
            exponent = -Decimal(remainder) / Decimal(HALF_LIFE_SESSIONS)
            weight *= (exponent * Decimal(2).ln()).exp()
        return +weight


def _fraction_decimal(value: Fraction) -> Decimal:
    if type(value) is not Fraction:
        raise _Error("rating delta is not an exact Fraction")
    with localcontext(_context()):
        return +(Decimal(value.numerator) / Decimal(value.denominator))


def _effective_contributors(values: Iterable[Decimal]) -> Decimal:
    with localcontext(_context()):
        absolute = []
        for value in values:
            if type(value) is not Decimal or not value.is_finite():
                raise _Error("effective contributor mass is invalid")
            absolute.append(abs(value))
        total = _stable_sum(absolute)
        if total <= NUMERICAL_ZERO:
            return Decimal(0)
        positive = tuple(value for value in absolute if value > 0)
        squares = _stable_sum(value * value for value in positive)
        result = +((total * total) / squares)
        if not result.is_finite() or result <= 0:
            raise _Error("effective breadth violated bounds")
        return max(Decimal(1), min(Decimal(len(positive)), result))


def _stock_reliability(n_eff: Decimal, quality: Decimal) -> Decimal:
    if (
        type(n_eff) is not Decimal
        or type(quality) is not Decimal
        or n_eff < 0
        or not Decimal(0) <= quality <= Decimal(1)
    ):
        raise _Error("reliability inputs are invalid")
    with localcontext(_context()):
        return +((n_eff / (n_eff + Decimal(3))) * quality)


def _reliable_score(value: Decimal, reliability: Decimal) -> Decimal:
    with localcontext(_context()):
        return +(value * reliability)


def _positive_share(values: tuple[Decimal, ...]) -> Decimal:
    with localcontext(_context()):
        return +(Decimal(sum(value > 0 for value in values)) / Decimal(len(values)))


def _normalize_sector(
    raw: Mapping[str, Decimal], active: set[str], members: tuple[str, ...]
) -> dict[str, Decimal] | None:
    if len(members) < MINIMUM_TOTAL_NAMES or sum(
        item in active for item in members
    ) < MINIMUM_ACTIVE_NAMES:
        return None
    # Analyst events are sparse.  Estimate location and scale from the names
    # carrying a live signal; structural-zero names remain exact zero in the
    # returned cross-section and never manufacture dispersion.
    active_members = tuple(item for item in members if item in active)
    with localcontext(_context()):
        median = _median(raw[item] for item in active_members)
        mad = _median(abs(raw[item] - median) for item in active_members)
        if mad == 0:
            if min(raw[item] for item in members) == max(raw[item] for item in members):
                return {item: Decimal(0) for item in members}
            return None
        scale = +(MAD_SCALE * mad)
        return {
            item: (
                max(-SCORE_CLIP, min(SCORE_CLIP, +((raw[item] - median) / scale)))
                if item in active else Decimal(0)
            )
            for item in members
        }


def _average_ranks(values: tuple[Decimal, ...]) -> tuple[Fraction, ...]:
    ordered = sorted(range(len(values)), key=lambda index: (values[index], index))
    result = [Fraction(0) for _ in values]
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and values[ordered[end]] == values[ordered[start]]:
            end += 1
        rank = Fraction((start + 1) + end, 2)
        for position in range(start, end):
            result[ordered[position]] = rank
        start = end
    return tuple(result)


def _spearman(scores: tuple[Decimal, ...], outcomes: tuple[Decimal, ...]) -> Decimal:
    if len(scores) != len(outcomes) or len(scores) < 2:
        raise _Error("Spearman inputs are underfilled")
    left = _average_ranks(scores)
    right = _average_ranks(outcomes)
    left_mean = sum(left, Fraction(0)) / len(left)
    right_mean = sum(right, Fraction(0)) / len(right)
    numerator = sum(
        ((a - left_mean) * (b - right_mean) for a, b in zip(left, right, strict=True)),
        Fraction(0),
    )
    left_square = sum(((value - left_mean) ** 2 for value in left), Fraction(0))
    right_square = sum(((value - right_mean) ** 2 for value in right), Fraction(0))
    if left_square == 0 or right_square == 0:
        raise _Error("Spearman input is constant")
    with localcontext(_context()):
        decimal_numerator = Decimal(numerator.numerator) / Decimal(numerator.denominator)
        decimal_left = Decimal(left_square.numerator) / Decimal(left_square.denominator)
        decimal_right = Decimal(right_square.numerator) / Decimal(right_square.denominator)
        return +(decimal_numerator / (decimal_left * decimal_right).sqrt())


@dataclasses.dataclass(frozen=True)
class SecurityMembership:
    security_id: str
    first_session_index: int
    last_session_index_exclusive: int
    sector_id: str
    q_data: Decimal
    row_sha256: str


@dataclasses.dataclass(frozen=True)
class RatingContribution:
    source_view_id: str
    contribution_id: str
    security_id: str
    eligible_session_index: int
    institution_id: str
    common_event_id: str
    rating_action: str
    firm_delta: Fraction
    global_delta: Fraction
    source_row_sha256: str
    row_sha256: str


@dataclasses.dataclass(frozen=True)
class PreliminaryRatingInput:
    manifest_id: str
    manifest_sha256: str
    benchmark_security_id: str
    session_axis: tuple[str, ...]
    memberships: tuple[SecurityMembership, ...]
    contributions: tuple[RatingContribution, ...]
    source_lineage_sha256s: tuple[tuple[str, str], ...]
    history_batch_security_count: int
    scoring_sessions_per_callback: int
    signal_seed_contributions_per_callback: int


_SESSION_FIELDS = _policy.SESSION_FIELDS
_MEMBERSHIP_FIELDS = _policy.MEMBERSHIP_FIELDS
_CONTRIBUTION_FIELDS = _policy.CONTRIBUTION_FIELDS
_MANIFEST_FIELDS = _policy.MANIFEST_FIELDS


def build_membership_record(
    *,
    security_id: str,
    first_session_index: int,
    last_session_index_exclusive: int,
    sector_id: str,
) -> dict[str, object]:
    seed = {
        "schema": MEMBERSHIP_SCHEMA,
        "security_id": _string(security_id, "membership security"),
        "first_session_index": _count(first_session_index, "membership first"),
        "last_session_index_exclusive": _count(
            last_session_index_exclusive, "membership last"
        ),
        "sector_id": _string(sector_id, "membership sector"),
        "q_data": "1",
    }
    if seed["first_session_index"] >= seed["last_session_index_exclusive"]:
        raise _Error("membership interval is empty")
    return {**seed, "row_sha256": _sha256(seed)}


def build_contribution_record(
    *,
    source_view_id: str,
    security_id: str,
    eligible_session_index: int,
    institution_id: str,
    common_event_id: str,
    rating_action: str,
    firm_delta: Fraction,
    global_delta: Fraction,
    source_row_sha256: str,
) -> dict[str, object]:
    if type(firm_delta) is not Fraction or type(global_delta) is not Fraction:
        raise _Error("rating deltas must be exact Fractions")
    if rating_action not in ("upgrades", "downgrades"):
        raise _Error("rating action is not directional")
    expected_positive = rating_action == "upgrades"
    if firm_delta == 0 or (firm_delta > 0) != expected_positive:
        raise _Error("firm delta contradicts rating action")
    if global_delta != 0 and (global_delta > 0) != expected_positive:
        raise _Error("global delta contradicts rating action")
    seed = {
        "schema": CONTRIBUTION_SCHEMA,
        "source_view_id": _string(source_view_id, "source view"),
        "security_id": _string(security_id, "contribution security"),
        "eligible_session_index": _count(
            eligible_session_index, "eligible session index"
        ),
        "institution_id": _string(institution_id, "institution"),
        "common_event_id": _string(common_event_id, "common event"),
        "rating_action": _string(rating_action, "rating action"),
        "firm_delta_numerator": firm_delta.numerator,
        "firm_delta_denominator": firm_delta.denominator,
        "global_delta_numerator": global_delta.numerator,
        "global_delta_denominator": global_delta.denominator,
        "source_row_sha256": _hash(source_row_sha256, "source row hash"),
    }
    digest = _sha256(seed)
    return {
        **seed,
        "contribution_id": "arv2-preliminary-rating-contribution-" + digest[:24],
        "row_sha256": digest,
    }


def build_preliminary_rating_manifest(
    *,
    benchmark_security_id: str,
    session_axis_records: tuple[dict[str, object], ...],
    membership_records: tuple[dict[str, object], ...],
    contribution_records: tuple[dict[str, object], ...],
    source_lineage_sha256s: dict[str, str],
    history_batch_security_count: int = MAX_HISTORY_BATCH_SECURITY_COUNT,
    scoring_sessions_per_callback: int = MAX_SCORING_SESSIONS_PER_CALLBACK,
    signal_seed_contributions_per_callback: int = (
        MAX_SIGNAL_SEED_CONTRIBUTIONS_PER_CALLBACK
    ),
) -> dict[str, object]:
    if any(
        type(value) is not tuple
        for value in (
            session_axis_records,
            membership_records,
            contribution_records,
        )
    ):
        raise _Error("manifest shards must be exact tuples")
    lineage = _exact_record(
        source_lineage_sha256s,
        _SOURCE_LINEAGE_FIELDS,
        "source lineage",
    )
    canonical_lineage = {
        name: _hash(lineage[name], name) for name in _SOURCE_LINEAGE_FIELDS
    }
    semantic = {
        "schema": MANIFEST_SCHEMA,
        "contract_id": CONTRACT_ID,
        "source_view_ids": list(SOURCE_VIEW_IDS),
        "horizons": list(HORIZONS),
        "primary_window": dict(_PRIMARY_WINDOW),
        "descriptive_window": dict(_DESCRIPTIVE_WINDOW),
        "rating_history_start_session": RATING_HISTORY_START_SESSION,
        "history_observation": HISTORY_OBSERVATION,
        "benchmark_security_id": _string(
            benchmark_security_id, "benchmark security"
        ),
        "session_axis_count": len(session_axis_records),
        "session_axis_sha256": _stream_sha256(session_axis_records),
        "membership_row_count": len(membership_records),
        "membership_rows_sha256": _stream_sha256(membership_records),
        "contribution_row_count": len(contribution_records),
        "contribution_rows_sha256": _stream_sha256(contribution_records),
        "source_lineage_sha256s": canonical_lineage,
        "history_batch_security_count": _positive_count(
            history_batch_security_count,
            "history batch security count",
            maximum=MAX_HISTORY_BATCH_SECURITY_COUNT,
        ),
        "scoring_sessions_per_callback": _positive_count(
            scoring_sessions_per_callback,
            "scoring sessions per callback",
            maximum=MAX_SCORING_SESSIONS_PER_CALLBACK,
        ),
        "signal_seed_contributions_per_callback": _positive_count(
            signal_seed_contributions_per_callback,
            "signal seed contributions per callback",
            maximum=MAX_SIGNAL_SEED_CONTRIBUTIONS_PER_CALLBACK,
        ),
        "q_data_policy_id": Q_DATA_POLICY_ID,
        "maximum_backtest_runtime_hours": MAX_BACKTEST_RUNTIME_HOURS,
        "accepted_risk_disclosures": dict(_ACCEPTED_RISK_DISCLOSURES),
    }
    digest = _sha256(semantic)
    return {
        **semantic,
        "manifest_id": "arv2-preliminary-rating-manifest-" + digest[:24],
        "manifest_sha256": digest,
    }


def _parse_sessions(records: object) -> tuple[str, ...]:
    if type(records) is not tuple or len(records) > MAX_SESSION_COUNT:
        raise _Error("session records require a bounded tuple")
    sessions: list[str] = []
    for index, raw in enumerate(records):
        row = _exact_record(raw, _SESSION_FIELDS, "session record")
        _literal(row["schema"], SESSION_SCHEMA, "session schema")
        if _count(row["session_index"], "session index") != index:
            raise _Error("session record identity changed")
        sessions.append(_date(row["session"], "session"))
    result = tuple(sessions)
    if not result or result != tuple(sorted(set(result))):
        raise _Error("session axis is empty, duplicated, or unordered")
    if result[0] != RATING_HISTORY_START_SESSION:
        raise _Error("rating history does not start at frozen 2013 session")
    for boundary in (
        _PRIMARY_WINDOW["start_session"],
        _PRIMARY_WINDOW["end_session"],
        _DESCRIPTIVE_WINDOW["start_session"],
        _DESCRIPTIVE_WINDOW["end_session"],
    ):
        if boundary not in result:
            raise _Error("fixed result window escaped session axis")
    end = result.index(_PRIMARY_WINDOW["end_session"])
    if end + max(HORIZONS) >= len(result):
        raise _Error("session axis lacks H60 outcome maturity")
    return result


def _parse_memberships(
    records: object, session_count: int
) -> tuple[SecurityMembership, ...]:
    if type(records) is not tuple or not records or len(records) > MAX_SECURITY_COUNT:
        raise _Error("membership records require a bounded tuple")
    parsed: list[SecurityMembership] = []
    expected_order: list[tuple[object, ...]] = []
    intervals: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for raw in records:
        row = _exact_record(raw, _MEMBERSHIP_FIELDS, "membership record")
        _literal(row["schema"], MEMBERSHIP_SCHEMA, "membership schema")
        semantic = {key: row[key] for key in _MEMBERSHIP_FIELDS if key != "row_sha256"}
        if _hash(row["row_sha256"], "membership hash") != _sha256(semantic):
            raise _Error("membership hash is not content-derived")
        security = _string(row["security_id"], "membership security")
        first = _count(row["first_session_index"], "membership first", maximum=session_count)
        last = _count(row["last_session_index_exclusive"], "membership last", maximum=session_count)
        if first >= last:
            raise _Error("membership interval is empty")
        sector = _string(row["sector_id"], "membership sector")
        quality = _decimal(row["q_data"], "membership q_data")
        if quality != 1:
            raise _Error("preliminary q_data must be the disclosed uniform one")
        parsed.append(SecurityMembership(security, first, last, sector, quality, row["row_sha256"]))
        expected_order.append((security, first, last, sector))
        intervals[security].append((first, last))
    if expected_order != sorted(expected_order):
        raise _Error("membership rows are not canonically sorted")
    for values in intervals.values():
        ordered = sorted(values)
        if any(left[1] > right[0] for left, right in zip(ordered, ordered[1:])):
            raise _Error("membership intervals overlap")
    return tuple(parsed)


def _parse_contributions(
    records: object,
    *,
    session_count: int,
    security_ids: set[str],
) -> tuple[RatingContribution, ...]:
    if type(records) is not tuple or len(records) > MAX_CONTRIBUTION_COUNT:
        raise _Error("contribution records require a bounded tuple")
    parsed: list[RatingContribution] = []
    sort_keys: list[tuple[object, ...]] = []
    dedupe: set[tuple[str, int, str, str]] = set()
    for raw in records:
        row = _exact_record(raw, _CONTRIBUTION_FIELDS, "contribution record")
        _literal(row["schema"], CONTRIBUTION_SCHEMA, "contribution schema")
        semantic = {
            key: row[key]
            for key in _CONTRIBUTION_FIELDS
            if key not in ("contribution_id", "row_sha256")
        }
        digest = _sha256(semantic)
        if (
            _hash(row["row_sha256"], "contribution row hash") != digest
            or _string(row["contribution_id"], "contribution id")
            != "arv2-preliminary-rating-contribution-" + digest[:24]
        ):
            raise _Error("contribution identity is not content-derived")
        view = _string(row["source_view_id"], "source view")
        if view not in SOURCE_VIEW_IDS:
            raise _Error("source view changed")
        security = _string(row["security_id"], "contribution security")
        if security not in security_ids:
            raise _Error("contribution security lacks membership")
        position = _count(row["eligible_session_index"], "eligible session", maximum=session_count - 1)
        institution = _string(row["institution_id"], "institution")
        common_event = _string(row["common_event_id"], "common event")
        action = _string(row["rating_action"], "rating action")
        if action not in ("upgrades", "downgrades"):
            raise _Error("rating action is not directional")
        for name in (
            "firm_delta_numerator", "firm_delta_denominator",
            "global_delta_numerator", "global_delta_denominator",
        ):
            if type(row[name]) is not int:
                raise _Error(f"{name} must be an exact integer")
        if row["firm_delta_denominator"] <= 0 or row["global_delta_denominator"] <= 0:
            raise _Error("rating delta denominator must be positive")
        firm = Fraction(row["firm_delta_numerator"], row["firm_delta_denominator"])
        global_value = Fraction(row["global_delta_numerator"], row["global_delta_denominator"])
        expected_positive = action == "upgrades"
        if firm == 0 or (firm > 0) != expected_positive:
            raise _Error("firm delta contradicts rating action")
        if global_value != 0 and (global_value > 0) != expected_positive:
            raise _Error("global delta contradicts rating action")
        source_hash = _hash(row["source_row_sha256"], "contribution source row")
        key = (view, position, security, institution)
        if key in dedupe:
            raise _Error("institution/security/session contribution is duplicated")
        dedupe.add(key)
        item = RatingContribution(
            view, row["contribution_id"], security, position, institution,
            common_event, action, firm, global_value, source_hash, digest,
        )
        parsed.append(item)
        sort_keys.append((SOURCE_VIEW_IDS.index(view), position, security, institution, item.contribution_id))
    if sort_keys != sorted(sort_keys):
        raise _Error("contribution rows are not canonically sorted")
    if any(not any(row.source_view_id == view for row in parsed) for view in SOURCE_VIEW_IDS):
        raise _Error("one required source view has no rating contribution")
    return tuple(parsed)


def load_preliminary_rating_input(
    manifest_record: object,
    session_axis_records: object,
    membership_records: object,
    contribution_records: object,
) -> PreliminaryRatingInput:
    manifest = _exact_record(manifest_record, _MANIFEST_FIELDS, "preliminary manifest")
    for value, expected, name in (
        (manifest["schema"], MANIFEST_SCHEMA, "manifest schema"),
        (manifest["contract_id"], CONTRACT_ID, "contract id"),
        (manifest["source_view_ids"], list(SOURCE_VIEW_IDS), "source views"),
        (manifest["horizons"], list(HORIZONS), "horizons"),
        (manifest["primary_window"], dict(_PRIMARY_WINDOW), "primary window"),
        (manifest["descriptive_window"], dict(_DESCRIPTIVE_WINDOW), "descriptive window"),
        (manifest["rating_history_start_session"], RATING_HISTORY_START_SESSION, "history start"),
        (manifest["history_observation"], HISTORY_OBSERVATION, "history observation"),
        (manifest["q_data_policy_id"], Q_DATA_POLICY_ID, "q_data policy"),
        (manifest["maximum_backtest_runtime_hours"], MAX_BACKTEST_RUNTIME_HOURS, "runtime hours"),
        (
            manifest["accepted_risk_disclosures"],
            dict(_ACCEPTED_RISK_DISCLOSURES),
            "risk disclosures",
        ),
    ):
        _literal(value, expected, name)
    benchmark = _string(manifest["benchmark_security_id"], "benchmark security")
    sessions_raw = session_axis_records
    memberships_raw = membership_records
    contributions_raw = contribution_records
    sessions = _parse_sessions(sessions_raw)
    memberships = _parse_memberships(memberships_raw, len(sessions))
    security_ids = {item.security_id for item in memberships}
    if benchmark in security_ids:
        raise _Error("benchmark cannot be a scored security")
    contributions = _parse_contributions(
        contributions_raw, session_count=len(sessions), security_ids=security_ids
    )
    count_bindings = (
        ("session_axis_count", sessions_raw, MAX_SESSION_COUNT),
        ("membership_row_count", memberships_raw, MAX_SECURITY_COUNT),
        ("contribution_row_count", contributions_raw, MAX_CONTRIBUTION_COUNT),
    )
    for field, values, maximum in count_bindings:
        if _count(manifest[field], field, maximum=maximum) != len(values):
            raise _Error(f"{field} does not match its shard")
    for field, values in (
        ("session_axis_sha256", sessions_raw),
        ("membership_rows_sha256", memberships_raw),
        ("contribution_rows_sha256", contributions_raw),
    ):
        if _hash(manifest[field], field) != _stream_sha256(values):
            raise _Error(f"{field} does not authenticate its shard")
    lineage = _exact_record(
        manifest["source_lineage_sha256s"], _SOURCE_LINEAGE_FIELDS,
        "source lineage",
    )
    lineage_tuple = tuple((name, _hash(lineage[name], name)) for name in _SOURCE_LINEAGE_FIELDS)
    history_batch = _positive_count(
        manifest["history_batch_security_count"], "history batch security count",
        maximum=MAX_HISTORY_BATCH_SECURITY_COUNT,
    )
    scoring_batch = _positive_count(
        manifest["scoring_sessions_per_callback"], "scoring sessions per callback",
        maximum=MAX_SCORING_SESSIONS_PER_CALLBACK,
    )
    seed_batch = _positive_count(
        manifest["signal_seed_contributions_per_callback"],
        "signal seed contributions per callback",
        maximum=MAX_SIGNAL_SEED_CONTRIBUTIONS_PER_CALLBACK,
    )
    semantic = {key: manifest[key] for key in _MANIFEST_FIELDS if key not in ("manifest_id", "manifest_sha256")}
    digest = _sha256(semantic)
    if (
        _hash(manifest["manifest_sha256"], "manifest hash") != digest
        or _string(manifest["manifest_id"], "manifest id")
        != "arv2-preliminary-rating-manifest-" + digest[:24]
    ):
        raise _Error("manifest identity is not content-derived")
    return PreliminaryRatingInput(
        manifest["manifest_id"], digest, benchmark, sessions, memberships,
        contributions, lineage_tuple, history_batch, scoring_batch, seed_batch,
    )


class RuntimePhase(str, Enum):
    HISTORY = "history"
    SIGNAL_SEED = "signal_seed"
    SCORING = "scoring"
    COMPLETED = "completed"
    CLOSED = "closed"


@dataclasses.dataclass(frozen=True)
class TotalReturnHistoryRequest:
    schema: str
    request_index: int
    security_ids: tuple[str, ...]
    start_session: str
    end_session: str
    normalization_mode: str
    observation: str
    request_sha256: str


@dataclasses.dataclass(frozen=True)
class TotalReturnOpenObservation:
    schema: str
    security_id: str
    session: str
    adjusted_open: Decimal

    def __post_init__(self) -> None:
        if type(self.schema) is not str or self.schema != HISTORY_OBSERVATION_SCHEMA:
            raise _Error("history observation schema changed")
        _string(self.security_id, "history observation security")
        _date(self.session, "history observation session")
        if type(self.adjusted_open) is not Decimal or not self.adjusted_open.is_finite() or self.adjusted_open <= 0:
            raise _Error("adjusted open must be an exact positive Decimal")


@dataclasses.dataclass(frozen=True)
class PreliminaryCallbackProgress:
    phase: RuntimePhase
    callback_count: int
    completed_history_batches: int
    total_history_batches: int
    seeded_contribution_count: int
    total_prestart_contribution_count: int
    completed_scoring_session_count: int
    total_scoring_session_count: int


@dataclasses.dataclass
class _SignalState:
    raw_firm_unscaled: Decimal = Decimal(0)
    raw_global_unscaled: Decimal = Decimal(0)
    firm_institution_mass: dict[str, Decimal] = dataclasses.field(default_factory=dict)
    firm_catalyst_mass: dict[str, Decimal] = dataclasses.field(default_factory=dict)
    global_institution_mass: dict[str, Decimal] = dataclasses.field(default_factory=dict)
    global_catalyst_mass: dict[str, Decimal] = dataclasses.field(default_factory=dict)
    firm_n_eff: Decimal | None = None
    global_n_eff: Decimal | None = None


@dataclasses.dataclass
class _CellAccumulator:
    eligible_score_rows: int = 0
    accepted_outcome_pairs: int = 0
    missing_outcome_pairs: int = 0
    sector_refused_rows: int = 0
    valid_ic_dates: int = 0
    invalid_ic_dates: int = 0
    date_ics: list[Decimal] = dataclasses.field(default_factory=list)
    date_mean_excess_returns: list[Decimal] = dataclasses.field(default_factory=list)


HistoryLoader = Callable[[TotalReturnHistoryRequest], tuple[TotalReturnOpenObservation, ...]]


class PreliminaryRatingEvaluationRuntime:
    def __init__(
        self,
        value: PreliminaryRatingInput,
        *,
        scratch_directory: object | None = None,
    ) -> None:
        if type(value) is not PreliminaryRatingInput:
            raise _Error("runtime requires exact preliminary input")
        self._input = value
        self._phase = RuntimePhase.HISTORY
        self._callback_count = 0
        self._history_batch_index = 0
        self._seed_cursor = 0
        self._scoring_cursor = 0
        self._summary: dict[str, object] | None = None
        self._states: dict[str, dict[str, _SignalState]] = {
            view: {} for view in SOURCE_VIEW_IDS
        }
        self._cells: dict[tuple[str, str, int, str], _CellAccumulator] = {
            (view, arm, horizon, window["window_id"]): _CellAccumulator()
            for view in SOURCE_VIEW_IDS
            for arm in SCORE_ARMS
            for horizon in HORIZONS
            for window in _WINDOWS
        }
        self._evaluation_positions = tuple(
            index for index, session in enumerate(value.session_axis)
            if _PRIMARY_WINDOW["start_session"] <= session <= _PRIMARY_WINDOW["end_session"]
        )
        start = self._evaluation_positions[0]
        self._prestart_indices = tuple(
            index for index, row in enumerate(value.contributions)
            if row.eligible_session_index < start
        )
        self._live_contribution_indices: dict[int, tuple[int, ...]] = defaultdict(tuple)
        pending: dict[int, list[int]] = defaultdict(list)
        for index, row in enumerate(value.contributions):
            if row.eligible_session_index >= start:
                pending[row.eligible_session_index].append(index)
        self._live_contribution_indices = {
            key: tuple(indices) for key, indices in pending.items()
        }
        ids = (value.benchmark_security_id, *sorted({item.security_id for item in value.memberships}))
        size = value.history_batch_security_count
        self._history_batches = tuple(
            tuple(ids[index:index + size]) for index in range(0, len(ids), size)
        )
        history_start = value.session_axis.index(_PRIMARY_WINDOW["start_session"])
        history_end = (
            value.session_axis.index(_PRIMARY_WINDOW["end_session"]) + max(HORIZONS)
        )
        self._history_sessions = value.session_axis[history_start:history_end + 1]
        history_slot_count = len(ids) * len(self._history_sessions)
        if (
            history_slot_count > MAX_HISTORY_OBSERVATION_COUNT
            or history_slot_count > MAX_HISTORY_MATRIX_SLOT_COUNT
        ):
            raise _Error("history observation geometry exceeds reviewed bound")
        self._history_security_ids = ids
        self._history_security_positions = {
            security: index for index, security in enumerate(ids)
        }
        self._history_session_positions = {
            session: index for index, session in enumerate(self._history_sessions)
        }
        self._history_prices: list[list[str | None]] = [
            [None] * len(ids) for _session in self._history_sessions
        ]
        self._maximum_callback_count = (
            len(self._history_batches)
            + max(
                1,
                (len(self._prestart_indices) + value.signal_seed_contributions_per_callback - 1)
                // value.signal_seed_contributions_per_callback,
            )
            + (len(self._evaluation_positions) + value.scoring_sessions_per_callback - 1)
            // value.scoring_sessions_per_callback
        )

    @property
    def phase(self) -> RuntimePhase:
        return self._phase

    def _history_request(self, index: int) -> TotalReturnHistoryRequest:
        securities = self._history_batches[index]
        start = _PRIMARY_WINDOW["start_session"]
        end_position = self._input.session_axis.index(_PRIMARY_WINDOW["end_session"]) + max(HORIZONS)
        end = self._input.session_axis[end_position]
        seed = {
            "schema": HISTORY_REQUEST_SCHEMA,
            "request_index": index,
            "security_ids": list(securities),
            "start_session": start,
            "end_session": end,
            "normalization_mode": "total_return",
            "observation": "session_open",
        }
        return TotalReturnHistoryRequest(
            HISTORY_REQUEST_SCHEMA, index, securities, start, end,
            "total_return", "session_open", _sha256(seed),
        )

    def _accept_history(
        self,
        request: TotalReturnHistoryRequest,
        observations: object,
    ) -> None:
        if type(observations) is not tuple:
            raise _Error("history loader must return an exact tuple")
        maximum = len(request.security_ids) * (
            self._input.session_axis.index(request.end_session)
            - self._input.session_axis.index(request.start_session) + 1
        )
        if len(observations) > maximum:
            raise _Error("history loader exceeded request geometry")
        permitted_ids = set(request.security_ids)
        permitted_sessions = set(
            self._input.session_axis[
                self._input.session_axis.index(request.start_session):
                self._input.session_axis.index(request.end_session) + 1
            ]
        )
        rows: list[tuple[int, int, str]] = []
        seen: set[tuple[str, str]] = set()
        for item in observations:
            if type(item) is not TotalReturnOpenObservation:
                raise _Error("history loader returned the wrong record type")
            item.__post_init__()
            key = (item.security_id, item.session)
            if item.security_id not in permitted_ids or item.session not in permitted_sessions:
                raise _Error("history observation escaped its request")
            if key in seen:
                raise _Error("history observation is duplicated")
            seen.add(key)
            open_text = _decimal_text(item.adjusted_open)
            if len(open_text) > MAX_CANONICAL_PRICE_TEXT_LENGTH:
                raise _Error("adjusted open exceeds canonical-text bound")
            rows.append((
                self._history_session_positions[item.session],
                self._history_security_positions[item.security_id],
                open_text,
            ))
        if any(
            self._history_prices[session][security] is not None
            for session, security, _open_text in rows
        ):
            raise _Error("history cache slot is already occupied")
        for session, security, open_text in rows:
            self._history_prices[session][security] = open_text

    def _apply_contribution(self, item: RatingContribution) -> None:
        factor = _decay(item.eligible_session_index)
        with localcontext(_context()):
            firm = +(_fraction_decimal(item.firm_delta) / factor)
            global_value = +(_fraction_decimal(item.global_delta) / factor)
        state = self._states[item.source_view_id].setdefault(item.security_id, _SignalState())
        with localcontext(_context()):
            state.raw_firm_unscaled = +(state.raw_firm_unscaled + firm)
            state.raw_global_unscaled = +(state.raw_global_unscaled + global_value)
            for target, key, value in (
                (state.firm_institution_mass, item.institution_id, abs(firm)),
                (state.firm_catalyst_mass, item.common_event_id, abs(firm)),
                (state.global_institution_mass, item.institution_id, abs(global_value)),
                (state.global_catalyst_mass, item.common_event_id, abs(global_value)),
            ):
                target[key] = +(target.get(key, Decimal(0)) + value)
        state.firm_n_eff = None
        state.global_n_eff = None

    @staticmethod
    def _reliability(
        state: _SignalState, arm: str, quality: Decimal, factor: Decimal
    ) -> Decimal:
        if arm == "firm_specific":
            institution_map = state.firm_institution_mass
            catalyst_map = state.firm_catalyst_mass
            cached = state.firm_n_eff
        else:
            institution_map = state.global_institution_mass
            catalyst_map = state.global_catalyst_mass
            cached = state.global_n_eff
        with localcontext(_context()):
            total = +(_stable_sum(institution_map.values()) * factor)
        if total <= NUMERICAL_ZERO:
            return Decimal(0)
        if cached is None:
            cached = min(
                _effective_contributors(institution_map.values()),
                _effective_contributors(catalyst_map.values()),
            )
            if arm == "firm_specific":
                state.firm_n_eff = cached
            else:
                state.global_n_eff = cached
        n_eff = cached
        return _stock_reliability(n_eff, quality)

    def _prices(self, sessions: tuple[str, ...]) -> dict[tuple[str, str], Decimal]:
        result: dict[tuple[str, str], Decimal] = {}
        for session in sessions:
            position = self._history_session_positions.get(session)
            if position is None:
                raise _Error("history cache session escaped its reviewed matrix")
            for security, open_text in zip(
                self._history_security_ids,
                self._history_prices[position],
                strict=True,
            ):
                if open_text is not None:
                    result[(security, session)] = _decimal(
                        open_text, "cached adjusted open", positive=True
                    )
        return result

    def _score_cross_section(
        self, position: int
    ) -> tuple[
        tuple[SecurityMembership, ...],
        dict[tuple[str, str], dict[str, Decimal]],
        defaultdict[tuple[str, str], int],
    ]:
        """Build the unchanged R055 score cross-section for one session."""
        for index in self._live_contribution_indices.get(position, ()):
            self._apply_contribution(self._input.contributions[index])
        memberships = tuple(
            item for item in self._input.memberships
            if item.first_session_index <= position < item.last_session_index_exclusive
        )
        by_sector: dict[str, list[SecurityMembership]] = defaultdict(list)
        for item in memberships:
            by_sector[item.sector_id].append(item)
        scores: dict[tuple[str, str], dict[str, Decimal]] = {
            (view, arm): {} for view in SOURCE_VIEW_IDS for arm in SCORE_ARMS
        }
        sector_refused: dict[tuple[str, str], int] = defaultdict(int)
        for view in SOURCE_VIEW_IDS:
            states = self._states[view]
            decay_factor = _decay(position)
            for sector in sorted(by_sector):
                members = tuple(sorted(by_sector[sector], key=lambda item: item.security_id))
                ids = tuple(item.security_id for item in members)
                active = {security for security in ids if security in states}
                with localcontext(_context()):
                    raw_firm = {
                        security: +(
                            states.get(security, _SignalState()).raw_firm_unscaled
                            * decay_factor
                        )
                        for security in ids
                    }
                    raw_global = {
                        security: +(
                            states.get(security, _SignalState()).raw_global_unscaled
                            * decay_factor
                        )
                        for security in ids
                    }
                firm_z = _normalize_sector(raw_firm, active, ids)
                global_z = _normalize_sector(raw_global, active, ids)
                if firm_z is None or global_z is None:
                    for arm in SCORE_ARMS:
                        sector_refused[(view, arm)] += len(ids)
                    continue
                quality = {item.security_id: item.q_data for item in members}
                for security in ids:
                    if security not in active:
                        scores[(view, "firm_specific")][security] = Decimal(0)
                        scores[(view, "global_comparator")][security] = Decimal(0)
                        continue
                    state = states[security]
                    scores[(view, "firm_specific")][security] = _reliable_score(
                        firm_z[security],
                        self._reliability(
                            state, "firm_specific", quality[security], decay_factor
                        ),
                    )
                    scores[(view, "global_comparator")][security] = _reliable_score(
                        global_z[security],
                        self._reliability(
                            state, "global_comparator", quality[security], decay_factor
                        ),
                    )
        return memberships, scores, sector_refused

    def _score_session(self, position: int) -> None:
        _memberships, scores, sector_refused = self._score_cross_section(position)
        session = self._input.session_axis[position]
        outcome_sessions = tuple(
            self._input.session_axis[position + horizon] for horizon in HORIZONS
        )
        price_map = self._prices((session, *outcome_sessions))
        benchmark = self._input.benchmark_security_id
        for view in SOURCE_VIEW_IDS:
            for arm in SCORE_ARMS:
                arm_scores = scores[(view, arm)]
                for horizon, exit_session in zip(HORIZONS, outcome_sessions, strict=True):
                    pairs: list[tuple[Decimal, Decimal]] = []
                    missing = 0
                    benchmark_start = price_map.get((benchmark, session))
                    benchmark_end = price_map.get((benchmark, exit_session))
                    for security, score in sorted(arm_scores.items()):
                        start = price_map.get((security, session))
                        end = price_map.get((security, exit_session))
                        if None in (start, end, benchmark_start, benchmark_end):
                            missing += 1
                            continue
                        assert start is not None and end is not None
                        assert benchmark_start is not None and benchmark_end is not None
                        with localcontext(_context()):
                            excess = +((end / start - Decimal(1)) - (benchmark_end / benchmark_start - Decimal(1)))
                        pairs.append((score, excess))
                    for window in _WINDOWS:
                        if not (window["start_session"] <= session <= window["end_session"]):
                            continue
                        cell = self._cells[(view, arm, horizon, window["window_id"])]
                        cell.eligible_score_rows += len(arm_scores)
                        cell.accepted_outcome_pairs += len(pairs)
                        cell.missing_outcome_pairs += missing
                        cell.sector_refused_rows += sector_refused[(view, arm)]
                        if (
                            sector_refused[(view, arm)]
                            or len(pairs) < MINIMUM_IC_ROWS
                        ):
                            cell.invalid_ic_dates += 1
                            continue
                        try:
                            ic = _spearman(
                                tuple(item[0] for item in pairs),
                                tuple(item[1] for item in pairs),
                            )
                        except PreliminaryRatingEvaluationError:
                            cell.invalid_ic_dates += 1
                            continue
                        cell.valid_ic_dates += 1
                        cell.date_ics.append(ic)
                        cell.date_mean_excess_returns.append(
                            _mean(tuple(item[1] for item in pairs))
                        )

    def _progress(self) -> PreliminaryCallbackProgress:
        return PreliminaryCallbackProgress(
            self._phase,
            self._callback_count,
            self._history_batch_index,
            len(self._history_batches),
            self._seed_cursor,
            len(self._prestart_indices),
            self._scoring_cursor,
            len(self._evaluation_positions),
        )

    def run_callback(self, total_return_history_loader: HistoryLoader | None = None) -> PreliminaryCallbackProgress:
        if self._phase in (RuntimePhase.COMPLETED, RuntimePhase.CLOSED):
            return self._progress()
        self._callback_count += 1
        if self._callback_count > self._maximum_callback_count:
            self.abort()
            raise _Error("callback census exceeded deterministic plan")
        if self._phase is RuntimePhase.HISTORY:
            if not callable(total_return_history_loader):
                raise _Error("history phase requires a callable loader")
            request = self._history_request(self._history_batch_index)
            observations = total_return_history_loader(request)
            self._accept_history(request, observations)
            self._history_batch_index += 1
            if self._history_batch_index == len(self._history_batches):
                self._phase = RuntimePhase.SIGNAL_SEED
            return self._progress()
        if self._phase is RuntimePhase.SIGNAL_SEED:
            stop = min(
                len(self._prestart_indices),
                self._seed_cursor + self._input.signal_seed_contributions_per_callback,
            )
            for position in range(self._seed_cursor, stop):
                self._apply_contribution(
                    self._input.contributions[self._prestart_indices[position]]
                )
            self._seed_cursor = stop
            if stop == len(self._prestart_indices):
                self._phase = RuntimePhase.SCORING
            return self._progress()
        if self._phase is not RuntimePhase.SCORING:
            raise _Error("runtime phase is unknown")
        stop = min(
            len(self._evaluation_positions),
            self._scoring_cursor + self._input.scoring_sessions_per_callback,
        )
        for index in range(self._scoring_cursor, stop):
            self._score_session(self._evaluation_positions[index])
        self._scoring_cursor = stop
        if stop == len(self._evaluation_positions):
            self._summary = self._build_summary()
            self._phase = RuntimePhase.COMPLETED
            self._destroy_history_cache()
        return self._progress()

    def _cell_record(
        self, view: str, arm: str, horizon: int, window_id: str,
        cell: _CellAccumulator,
    ) -> dict[str, object]:
        ics = tuple(cell.date_ics)
        returns = tuple(cell.date_mean_excess_returns)
        return {
            "schema": CELL_SCHEMA,
            "source_view_id": view,
            "score_arm": arm,
            "horizon_sessions": horizon,
            "window_id": window_id,
            "status": (
                "PRELIMINARY_DESCRIPTIVE_AVAILABLE"
                if cell.valid_ic_dates >= 50
                else "INCONCLUSIVE_UNDERFILLED"
            ),
            "eligible_score_row_count": cell.eligible_score_rows,
            "accepted_outcome_pair_count": cell.accepted_outcome_pairs,
            "missing_outcome_pair_count": cell.missing_outcome_pairs,
            "sector_refused_row_count": cell.sector_refused_rows,
            "valid_ic_date_count": cell.valid_ic_dates,
            "invalid_ic_date_count": cell.invalid_ic_dates,
            "mean_daily_spearman_ic": None if not ics else _decimal_text(_mean(ics)),
            "median_daily_spearman_ic": None if not ics else _decimal_text(_median(ics)),
            "positive_ic_date_share": (
                None if not ics else _decimal_text(_positive_share(ics))
            ),
            "mean_of_daily_cross_section_mean_excess_returns": (
                None if not returns else _decimal_text(_mean(returns))
            ),
            "median_of_daily_cross_section_mean_excess_returns": (
                None if not returns else _decimal_text(_median(returns))
            ),
            "outcome_definition": HISTORY_OBSERVATION,
            "formal_accept_reject_disposition": None,
        }

    def _build_summary(self) -> dict[str, object]:
        cells = [
            self._cell_record(view, arm, horizon, window["window_id"], self._cells[(view, arm, horizon, window["window_id"])])
            for window in _WINDOWS
            for view in SOURCE_VIEW_IDS
            for arm in SCORE_ARMS
            for horizon in HORIZONS
        ]
        record = {
            "schema": SUMMARY_SCHEMA,
            "contract_id": CONTRACT_ID,
            "manifest_id": self._input.manifest_id,
            "manifest_sha256": self._input.manifest_sha256,
            "status": "PRELIMINARY_ACCEPTED_RISK_STOCK_IC_ONLY",
            "source_lineage_sha256s": dict(self._input.source_lineage_sha256s),
            "windows": [dict(item) for item in _WINDOWS],
            "source_view_ids": list(SOURCE_VIEW_IDS),
            "score_arms": list(SCORE_ARMS),
            "horizons": list(HORIZONS),
            "outcome_definition": HISTORY_OBSERVATION,
            "history_normalization_mode": "TOTAL_RETURN",
            "history_value_field": "open",
            "decay_state_method": (
                "sparse_positive_common_scale_mathematically_equivalent_"
                "not_byte_identical_to_formal_per_event_replay"
            ),
            "benchmark_role": "matching_SPY_open_to_open_total_return",
            "q_data_policy_id": Q_DATA_POLICY_ID,
            "input_security_count": len({item.security_id for item in self._input.memberships}),
            "input_contribution_count": len(self._input.contributions),
            "completed_callback_count": self._callback_count,
            "accepted_risk_disclosures": dict(_ACCEPTED_RISK_DISCLOSURES),
            "omitted_formal_components": list(OMITTED_FORMAL_COMPONENTS),
            "raw_provider_rows_in_summary": False,
            "raw_security_outcome_rows_in_summary": False,
            "raw_price_rows_in_summary": False,
            "formal_result": False,
            "alpha_claim_authorized": False,
            "cells": cells,
        }
        digest = _sha256(record)
        return {
            **record,
            "summary_id": "arv2-preliminary-rating-summary-" + digest[:24],
            "summary_sha256": digest,
        }

    def custom_summary_statistics(self) -> dict[str, str]:
        if self._phase is not RuntimePhase.COMPLETED or self._summary is None:
            raise _Error("preliminary summary is not complete")
        metadata = {key: value for key, value in self._summary.items() if key != "cells"}
        output = {
            "ARV2_PRELIMINARY_META": _canonical_bytes(metadata).decode("ascii")
        }
        for cell in self._summary["cells"]:
            key = _cell_summary_statistic_name(
                cell["source_view_id"],
                cell["score_arm"],
                cell["horizon_sessions"],
                cell["window_id"],
            )
            output[key] = _canonical_bytes(cell).decode("ascii")
        if tuple(sorted(output)) != EVALUATOR_CUSTOM_SUMMARY_STATISTIC_NAMES:
            raise _Error("custom summary statistic inventory changed")
        if any(len(key) > 64 or len(value) > 4_096 for key, value in output.items()):
            raise _Error("custom summary statistic exceeded compact bound")
        return dict(sorted(output.items()))

    def aggregate_summary(self) -> dict[str, object]:
        if self._phase is not RuntimePhase.COMPLETED or self._summary is None:
            raise _Error("preliminary summary is not complete")
        return json.loads(_canonical_bytes(self._summary).decode("ascii"))

    def _destroy_history_cache(self) -> None:
        self._history_prices = []
        self._history_security_positions = {}
        self._history_session_positions = {}
        self._history_security_ids = ()
        self._history_sessions = ()

    def abort(self) -> None:
        self._destroy_history_cache()
        self._phase = RuntimePhase.CLOSED

    def close(self) -> None:
        self._destroy_history_cache()
        self._phase = RuntimePhase.CLOSED
