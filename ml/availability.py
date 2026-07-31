"""ML-LR-1: point-in-time lineage and historical universe membership
(live-readiness plan section 7).

This module supplies the contracts needed to remove the project's largest
research blocker once an authoritative source is configured.  The existing
yfinance path must still report `point_in_time_data=False`: its adjusted
closes can be rewritten retroactively and it cannot prove when each value
first became knowable.

Three timestamps, deliberately distinct (plan 7.2 / strategy doc 3.4):

  * ``event_at``     -- when the underlying event actually occurred;
  * ``available_at`` -- when this application could FIRST have known it;
  * ``observed_at``  -- when this pipeline actually retrieved/recorded it.

Only ``available_at`` may gate a decision. Using ``observed_at`` would let a
backfill run today certify that last year's dataset was point-in-time, and
using ``event_at`` would assume instantaneous, free knowledge of every
corporate action. The ordering ``event_at <= available_at <= observed_at``
is enforced, not assumed.

The hard rule from plan 7.4: an adapter that cannot obtain real availability
timestamps must say so and leave the dataset exploratory. It must NEVER
synthesize them from download time -- that would manufacture exactly the
false confidence this milestone exists to prevent.
"""
from __future__ import annotations

import contextlib
import dataclasses
import json
import math
from datetime import date, datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence

from ml.contracts import (
    ContractError,
    _check_required_str as _contract_check_required_str,
    _check_sha256 as _contract_check_sha256,
    _parse_timestamp as _contract_parse_timestamp,
)
from ml.hashing import canonical_json, hash_bytes

SCHEMA_VERSION = "1.0"
_SUPPORTED_SCHEMA_VERSIONS = frozenset({SCHEMA_VERSION})

# Plan 7.4: the existing yfinance path must identify itself honestly.
RETROACTIVELY_ADJUSTED_SOURCE_ID = "yfinance_retroactively_adjusted"


class AvailabilityError(ContractError):
    """Lineage data cannot support a point-in-time claim."""


@contextlib.contextmanager
def _as_availability_error():
    """Reused ml/contracts.py helpers raise the PARENT ContractError; since
    AvailabilityError is a subclass, `except AvailabilityError` would miss
    them. Same translation rationale as ml/experiment_contracts.py."""
    try:
        yield
    except AvailabilityError:
        raise
    except ContractError as exc:
        raise AvailabilityError(str(exc)) from exc


def _check_required_str(value: Any, name: str) -> None:
    with _as_availability_error():
        _contract_check_required_str(value, name)


def _check_sha256(value: Any, name: str) -> None:
    with _as_availability_error():
        _contract_check_sha256(value, name)


def _parse_timestamp(value: Any, name: str) -> datetime:
    with _as_availability_error():
        return _contract_parse_timestamp(value, name)


def _parse_session(value: Any, name: str) -> date:
    if not isinstance(value, str):
        raise AvailabilityError(f"{name} must use canonical YYYY-MM-DD format")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise AvailabilityError(f"{name} must use canonical YYYY-MM-DD format") from exc
    if parsed.isoformat() != value:
        raise AvailabilityError(f"{name} must use canonical YYYY-MM-DD format")
    return parsed


def _check_schema_version(schema_version: str) -> None:
    if schema_version not in _SUPPORTED_SCHEMA_VERSIONS:
        raise AvailabilityError(
            f"unknown schema_version {schema_version!r}; "
            f"supported: {sorted(_SUPPORTED_SCHEMA_VERSIONS)}"
        )


def hash_feature_value(value: Any) -> str:
    """Canonical digest used to bind a lineage record to its actual value."""
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        raise AvailabilityError("feature values used for lineage must be finite")
    if value is not None and not isinstance(value, (str, bool, int, float)):
        raise AvailabilityError(
            "feature values used for lineage must be JSON scalar values"
        )
    return hash_bytes(canonical_json(value).encode("utf-8"))


@dataclasses.dataclass(frozen=True)
class FeatureAvailabilityRecord:
    """When one (session, ticker, feature) value became knowable."""

    as_of_session: str
    ticker: str
    feature_name: str
    event_at: str
    available_at: str
    observed_at: str
    source_id: str
    source_version: str
    revision_id: str
    raw_value_hash: str
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        with _as_availability_error():
            self._validate()

    def _validate(self) -> None:
        _check_schema_version(self.schema_version)
        for name in (
            "ticker", "feature_name", "source_id", "source_version", "revision_id",
        ):
            _check_required_str(getattr(self, name), name)
        if self.ticker != self.ticker.upper():
            raise AvailabilityError("ticker must be canonical uppercase")
        _parse_session(self.as_of_session, "as_of_session")
        _check_sha256(self.raw_value_hash, "raw_value_hash")

        event_at = _parse_timestamp(self.event_at, "event_at")
        available_at = _parse_timestamp(self.available_at, "available_at")
        observed_at = _parse_timestamp(self.observed_at, "observed_at")
        if event_at > available_at:
            raise AvailabilityError(
                "event_at must not be after available_at: an event cannot become "
                "knowable before it happens"
            )
        if available_at > observed_at:
            raise AvailabilityError(
                "available_at must not be after observed_at: this pipeline cannot "
                "have recorded a value before it was knowable"
            )

    @property
    def identity(self) -> tuple[str, str, str, str]:
        """One value per (session, ticker, feature, revision). The revision is
        part of the identity so a later restatement is a NEW record rather
        than an overwrite of what was historically visible."""
        return (self.as_of_session, self.ticker, self.feature_name, self.revision_id)

    def is_available_by(self, cutoff: datetime) -> bool:
        if not isinstance(cutoff, datetime) or cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise AvailabilityError("cutoff must be a timezone-aware datetime")
        return _parse_timestamp(self.available_at, "available_at") <= cutoff

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FeatureAvailabilityRecord":
        return _load(cls, payload)


@dataclasses.dataclass(frozen=True)
class UniverseMembershipRecord:
    """When a ticker was a member of a universe, and when that was knowable.

    `announced_at` and `available_at` are separate from `effective_from` for
    the reason index reconstitutions are a classic backtest trap: an index
    change is typically announced days BEFORE it takes effect, so a naive
    backtest that uses effective_from as the knowledge date is both too late
    (ignoring the announcement drift) and, if it uses today's membership
    list, catastrophically too early.
    """

    universe_id: str
    ticker: str
    effective_from: str
    effective_to: str | None
    announced_at: str
    available_at: str
    source_id: str
    source_version: str
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        with _as_availability_error():
            self._validate()

    def _validate(self) -> None:
        _check_schema_version(self.schema_version)
        for name in ("universe_id", "ticker", "source_id", "source_version"):
            _check_required_str(getattr(self, name), name)
        if self.ticker != self.ticker.upper():
            raise AvailabilityError("ticker must be canonical uppercase")
        effective_from = _parse_session(self.effective_from, "effective_from")
        if self.effective_to is not None:
            effective_to = _parse_session(self.effective_to, "effective_to")
            if effective_to < effective_from:
                raise AvailabilityError("effective_to must not precede effective_from")
        announced_at = _parse_timestamp(self.announced_at, "announced_at")
        available_at = _parse_timestamp(self.available_at, "available_at")
        if announced_at > available_at:
            raise AvailabilityError("announced_at must not be after available_at")

    def covers_session(self, session: str) -> bool:
        target = _parse_session(session, "session")
        if target < _parse_session(self.effective_from, "effective_from"):
            return False
        if self.effective_to is None:
            return True
        return target <= _parse_session(self.effective_to, "effective_to")

    def is_known_by_session(self, session: str, *, cutoff_hour_utc: int = 0) -> bool:
        """Whether this membership fact was knowable BEFORE `session` opened.

        Compares against the START of the session day in UTC rather than its
        end: a membership change announced during a session was not usable to
        select that session's universe without look-ahead.
        """
        target = _parse_session(session, "session")
        if isinstance(cutoff_hour_utc, bool) or not isinstance(cutoff_hour_utc, int):
            raise AvailabilityError("cutoff_hour_utc must be an integer from 0 through 23")
        if not 0 <= cutoff_hour_utc <= 23:
            raise AvailabilityError("cutoff_hour_utc must be an integer from 0 through 23")
        session_start = datetime(
            target.year, target.month, target.day, cutoff_hour_utc,
            tzinfo=timezone.utc,
        )
        return self.is_known_by(session_start)

    def is_known_by(self, cutoff: datetime) -> bool:
        """Whether this membership fact was available by an exact cutoff."""
        if not isinstance(cutoff, datetime) or cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise AvailabilityError("cutoff must be a timezone-aware datetime")
        return _parse_timestamp(self.available_at, "available_at") <= cutoff

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "UniverseMembershipRecord":
        return _load(cls, payload)


def _load(contract_type: type[Any], payload: Mapping[str, Any]) -> Any:
    name = contract_type.__name__
    if not isinstance(payload, Mapping):
        raise AvailabilityError(f"{name} payload must be a JSON object")
    fields = {field.name for field in dataclasses.fields(contract_type)}
    unknown = set(payload) - fields
    if unknown:
        raise AvailabilityError(f"{name} payload has unknown fields: {sorted(unknown, key=str)}")
    try:
        return contract_type(**{k: v for k, v in payload.items() if k in fields})
    except TypeError as exc:
        raise AvailabilityError(f"{name} payload missing required field(s): {exc}") from exc


class PointInTimeSource(Protocol):
    """Plan 7.4: a small protocol rather than a hard-coded vendor."""

    source_id: str
    provides_point_in_time_lineage: bool

    def feature_records(
        self, *, tickers: Sequence[str], start_session: str, end_session: str
    ) -> Sequence[FeatureAvailabilityRecord]: ...

    def universe_membership(
        self, *, universe_id: str, start_session: str, end_session: str
    ) -> Sequence[UniverseMembershipRecord]: ...

    def source_manifest(self) -> Mapping[str, str]: ...


class RetroactivelyAdjustedSource:
    """The honest description of this project's current yfinance path.

    Deliberately returns NOTHING rather than fabricating lineage. Plan 7.4:
    "It must never synthesize historical availability or universe
    membership." Returning empty sequences (instead of records stamped with
    download time) is what keeps datasets built from this source correctly
    classified as exploratory -- a synthesized `available_at` would let them
    silently pass the point-in-time gate while being no more trustworthy.
    """

    source_id = RETROACTIVELY_ADJUSTED_SOURCE_ID
    provides_point_in_time_lineage = False

    def __init__(self, *, source_version: str = "yfinance-1.5.2") -> None:
        self.source_version = source_version

    def feature_records(
        self, *, tickers: Sequence[str], start_session: str, end_session: str
    ) -> Sequence[FeatureAvailabilityRecord]:
        return ()

    def universe_membership(
        self, *, universe_id: str, start_session: str, end_session: str
    ) -> Sequence[UniverseMembershipRecord]:
        return ()

    def source_manifest(self) -> Mapping[str, str]:
        return {
            "source_id": self.source_id,
            "source_version": self.source_version,
            "provides_point_in_time_lineage": "false",
            "limitation": (
                "Prices are retroactively split/dividend adjusted and carry no "
                "historical availability or index-membership record. Datasets "
                "built from this source remain exploratory and promotion-blocked."
            ),
        }


@dataclasses.dataclass(frozen=True)
class CoverageResult:
    """Why a dataset may or may not claim point-in-time status."""

    point_in_time_data: bool
    survivorship_bias_free: bool
    checked_feature_columns: tuple[str, ...]
    covered_feature_columns: tuple[str, ...]
    missing_lineage_columns: tuple[str, ...]
    failures: tuple[str, ...]
    feature_keys: tuple[tuple[str, str], ...]
    universe_id: str
    decision_cutoffs: Mapping[str, str]
    derived_columns: Mapping[str, tuple[str, ...]]
    value_hashes: Mapping[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "point_in_time_data": self.point_in_time_data,
            "survivorship_bias_free": self.survivorship_bias_free,
            "checked_feature_columns": list(self.checked_feature_columns),
            "covered_feature_columns": list(self.covered_feature_columns),
            "missing_lineage_columns": list(self.missing_lineage_columns),
            "failures": list(self.failures),
            "feature_keys": [list(key) for key in self.feature_keys],
            "universe_id": self.universe_id,
            "decision_cutoffs": dict(self.decision_cutoffs),
            "derived_columns": {
                key: list(value) for key, value in self.derived_columns.items()
            },
            "value_hashes": dict(self.value_hashes),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CoverageResult":
        if not isinstance(payload, Mapping):
            raise AvailabilityError("CoverageResult payload must be a JSON object")
        fields = {field.name for field in dataclasses.fields(cls)}
        unknown = set(payload) - fields
        missing = fields - set(payload)
        if unknown or missing:
            raise AvailabilityError(
                f"CoverageResult fields mismatch; missing={sorted(missing)}, "
                f"unknown={sorted(unknown)}"
            )
        try:
            return cls(
                point_in_time_data=payload["point_in_time_data"],
                survivorship_bias_free=payload["survivorship_bias_free"],
                checked_feature_columns=tuple(payload["checked_feature_columns"]),
                covered_feature_columns=tuple(payload["covered_feature_columns"]),
                missing_lineage_columns=tuple(payload["missing_lineage_columns"]),
                failures=tuple(payload["failures"]),
                feature_keys=tuple(tuple(key) for key in payload["feature_keys"]),
                universe_id=payload["universe_id"],
                decision_cutoffs=dict(payload["decision_cutoffs"]),
                derived_columns={
                    key: tuple(value)
                    for key, value in payload["derived_columns"].items()
                },
                value_hashes=dict(payload["value_hashes"]),
            )
        except (TypeError, ValueError) as exc:
            raise AvailabilityError(f"CoverageResult has invalid field shapes: {exc}") from exc

    def __post_init__(self) -> None:
        if not isinstance(self.point_in_time_data, bool) or not isinstance(
            self.survivorship_bias_free, bool
        ):
            raise AvailabilityError("coverage flags must be booleans")
        _check_required_str(self.universe_id, "universe_id")
        string_fields: dict[str, tuple[str, ...]] = {}
        for name in (
            "checked_feature_columns",
            "covered_feature_columns",
            "missing_lineage_columns",
            "failures",
        ):
            value = getattr(self, name)
            if not isinstance(value, (list, tuple)):
                raise AvailabilityError(f"{name} must be a sequence of strings")
            items = tuple(value)
            for index, item in enumerate(items):
                _check_required_str(item, f"{name}[{index}]")
            string_fields[name] = items
        checked = string_fields["checked_feature_columns"]
        covered = string_fields["covered_feature_columns"]
        missing_lineage = string_fields["missing_lineage_columns"]
        failures = string_fields["failures"]
        if not checked or len(checked) != len(set(checked)):
            raise AvailabilityError(
                "checked_feature_columns must be non-empty and unique"
            )
        if set(covered) & set(missing_lineage) or set(covered) | set(missing_lineage) != set(checked):
            raise AvailabilityError(
                "covered_feature_columns and missing_lineage_columns must partition checked features"
            )
        if self.point_in_time_data != (not failures):
            raise AvailabilityError(
                "point_in_time_data must equal the absence of coverage failures"
            )
        if not isinstance(self.feature_keys, (list, tuple)) or not self.feature_keys:
            raise AvailabilityError("feature_keys must be a non-empty sequence")
        keys_list: list[tuple[str, str]] = []
        for index, key in enumerate(self.feature_keys):
            if not isinstance(key, (list, tuple)) or len(key) != 2:
                raise AvailabilityError(f"feature_keys[{index}] must contain session and ticker")
            session, ticker = key
            if not isinstance(session, str) or not isinstance(ticker, str):
                raise AvailabilityError(f"feature_keys[{index}] values must be strings")
            keys_list.append((session, ticker))
        keys = tuple(keys_list)
        if len(keys) != len(set(keys)):
            raise AvailabilityError("feature_keys must be unique")
        for session, ticker in keys:
            _parse_session(session, "feature_keys session")
            _check_required_str(ticker, "feature_keys ticker")
            if ticker != ticker.upper():
                raise AvailabilityError("feature_keys tickers must be canonical uppercase")
        if not isinstance(self.decision_cutoffs, Mapping):
            raise AvailabilityError("decision_cutoffs must be a mapping")
        cutoffs = dict(self.decision_cutoffs)
        for session, cutoff in cutoffs.items():
            _parse_session(session, "decision_cutoffs session")
            _parse_timestamp(cutoff, f"decision_cutoffs[{session}]")
        if not isinstance(self.derived_columns, Mapping):
            raise AvailabilityError("derived_columns must be a mapping")
        derived: dict[str, tuple[str, ...]] = {}
        for column, sources in self.derived_columns.items():
            _check_required_str(column, "derived_columns key")
            if not isinstance(sources, (list, tuple)):
                raise AvailabilityError(f"derived_columns[{column}] must be a sequence")
            derived[column] = tuple(sources)
            for source in derived[column]:
                _check_required_str(source, f"derived_columns[{column}]")
        if not isinstance(self.value_hashes, Mapping):
            raise AvailabilityError("value_hashes must be a mapping")
        value_hashes = dict(self.value_hashes)
        for key, digest in value_hashes.items():
            _check_required_str(key, "value_hashes key")
            _check_sha256(digest, f"value_hashes[{key}]")
        object.__setattr__(self, "feature_keys", keys)
        for name, value in string_fields.items():
            object.__setattr__(self, name, value)
        object.__setattr__(self, "decision_cutoffs", MappingProxyType(cutoffs))
        object.__setattr__(self, "derived_columns", MappingProxyType(derived))
        object.__setattr__(self, "value_hashes", MappingProxyType(value_hashes))


def _value_hash_key(session: str, ticker: str, feature_name: str) -> str:
    return canonical_json([session, ticker, feature_name])


def coverage_value_hashes(
    coverage: CoverageResult,
) -> dict[tuple[str, str, str], str]:
    """Decode persisted coverage hashes for deterministic re-validation."""
    decoded: dict[tuple[str, str, str], str] = {}
    for key, digest in coverage.value_hashes.items():
        try:
            parts = json.loads(key)
        except (TypeError, ValueError) as exc:
            raise AvailabilityError(f"invalid persisted value-hash key {key!r}") from exc
        if not isinstance(parts, list) or len(parts) != 3 or not all(
            isinstance(part, str) and part for part in parts
        ):
            raise AvailabilityError(f"invalid persisted value-hash key {key!r}")
        decoded[tuple(parts)] = digest
    return decoded


def evaluate_point_in_time_coverage(
    *,
    feature_keys: Sequence[tuple[str, str]],
    feature_columns: Sequence[str],
    availability: Sequence[FeatureAvailabilityRecord],
    universe: Sequence[UniverseMembershipRecord],
    universe_id: str,
    decision_cutoffs: Mapping[str, str],
    derived_columns: Mapping[str, Sequence[str]] | None = None,
    feature_values: Mapping[tuple[str, str, str], Any] | None = None,
    feature_value_hashes: Mapping[tuple[str, str, str], str] | None = None,
) -> CoverageResult:
    """Derive -- never assert -- whether a dataset is point-in-time.

    Plan 7.3: "`point_in_time_data=True` is derived only when all coverage
    checks pass. The caller must not be able to set `point_in_time_data=True`
    directly." This function is the ONLY place that may return True, and it
    returns the failures alongside so a False answer is explainable rather
    than mysterious.

    `derived_columns` maps a deterministically-derived feature to the source
    columns it was computed from; a derived column is covered when its whole
    input lineage is covered (plan 7.3: "deterministic derived features
    identify their complete input lineage").
    """
    failures: list[str] = []
    normalized_keys = tuple((str(session), str(ticker)) for session, ticker in feature_keys)
    if not normalized_keys:
        raise AvailabilityError("feature_keys must be non-empty")
    if len(normalized_keys) != len(set(normalized_keys)):
        raise AvailabilityError("feature_keys contains duplicates")
    checked = tuple(str(column) for column in feature_columns)
    if not checked or len(checked) != len(set(checked)):
        raise AvailabilityError("feature_columns must be non-empty and unique")
    _check_required_str(universe_id, "universe_id")
    normalized_derived = {
        str(column): tuple(str(source) for source in sources)
        for column, sources in (derived_columns or {}).items()
    }
    unknown_derived = set(normalized_derived) - set(checked)
    if unknown_derived:
        raise AvailabilityError(
            f"derived_columns contains columns absent from feature_columns: {sorted(unknown_derived)}"
        )

    def raw_inputs(column: str, trail: tuple[str, ...] = ()) -> tuple[str, ...]:
        if column in trail:
            raise AvailabilityError(
                f"derived_columns contains a cycle: {' -> '.join((*trail, column))}"
            )
        if column not in normalized_derived:
            return (column,)
        sources = normalized_derived[column]
        if not sources:
            raise AvailabilityError(f"derived column {column!r} has no input lineage")
        flattened: list[str] = []
        for source in sources:
            _check_required_str(source, f"derived_columns[{column}]")
            flattened.extend(raw_inputs(source, (*trail, column)))
        return tuple(dict.fromkeys(flattened))

    raw_by_column = {column: raw_inputs(column) for column in checked}
    required_raw = tuple(
        dict.fromkeys(
            source for column in checked for source in raw_by_column[column]
        )
    )
    key_set = set(normalized_keys)
    relevant_availability = [
        record
        for record in availability
        if (record.as_of_session, record.ticker) in key_set
        and record.feature_name in required_raw
    ]

    # --- availability vs decision cutoff -----------------------------------
    parsed_cutoffs = {
        session: _parse_timestamp(value, f"decision_cutoffs[{session}]")
        for session, value in decision_cutoffs.items()
    }
    for session in dict.fromkeys(session for session, _ in normalized_keys):
        if session not in parsed_cutoffs:
            failures.append(f"missing_decision_cutoff:{session}")

    # Duplicate records that arrived only after the historical cutoff cannot
    # alter the already-frozen prefix.  Visible duplicates remain an error.
    visible_identities = [
        record.identity
        for record in relevant_availability
        if record.as_of_session in parsed_cutoffs
        and record.is_available_by(parsed_cutoffs[record.as_of_session])
    ]
    if len(visible_identities) != len(set(visible_identities)):
        failures.append("duplicate_feature_availability_identity")

    # --- per-key column coverage -------------------------------------------
    records_by_value: dict[tuple[str, str, str], list[FeatureAvailabilityRecord]] = {}
    for record in relevant_availability:
        records_by_value.setdefault(
            (record.as_of_session, record.ticker, record.feature_name), []
        ).append(record)
    covered_by_key: dict[tuple[str, str], set[str]] = {}
    if feature_values is not None and feature_value_hashes is not None:
        raise AvailabilityError(
            "supply feature_values or feature_value_hashes, not both"
        )
    values = feature_values or {}
    supplied_hashes = feature_value_hashes or {}
    for key, digest in supplied_hashes.items():
        if not isinstance(key, tuple) or len(key) != 3:
            raise AvailabilityError("feature_value_hashes keys must be 3-tuples")
        _check_sha256(digest, f"feature_value_hashes[{key!r}]")
    selected_value_hashes: dict[str, str] = {}
    for session, ticker in normalized_keys:
        cutoff = parsed_cutoffs.get(session)
        if cutoff is None:
            continue
        for source in required_raw:
            candidates = records_by_value.get((session, ticker, source), ())
            visible = [record for record in candidates if record.is_available_by(cutoff)]
            if not visible:
                if candidates:
                    failures.append(f"availability_after_cutoff:{session}:{ticker}:{source}")
                continue
            newest_at = max(_parse_timestamp(record.available_at, "available_at") for record in visible)
            newest = [
                record
                for record in visible
                if _parse_timestamp(record.available_at, "available_at") == newest_at
            ]
            if len({record.raw_value_hash for record in newest}) != 1:
                failures.append(f"ambiguous_visible_revision:{session}:{ticker}:{source}")
                continue
            value_key = (session, ticker, source)
            if value_key in values:
                actual_value_hash = hash_feature_value(values[value_key])
            elif value_key in supplied_hashes:
                actual_value_hash = supplied_hashes[value_key]
            else:
                failures.append(f"missing_feature_value_binding:{session}:{ticker}:{source}")
                continue
            if actual_value_hash != newest[0].raw_value_hash:
                failures.append(f"feature_value_hash_mismatch:{session}:{ticker}:{source}")
                continue
            selected_value_hashes[
                _value_hash_key(session, ticker, source)
            ] = actual_value_hash
            covered_by_key.setdefault((session, ticker), set()).add(source)

    covered: list[str] = []
    missing: list[str] = []
    for column in checked:
        inputs = raw_by_column[column]
        if all(
            all(source in covered_by_key.get(key, set()) for source in inputs)
            for key in normalized_keys
        ):
            covered.append(column)
        else:
            missing.append(column)
    if missing:
        failures.append("missing_feature_lineage")

    # --- universe eligibility ----------------------------------------------
    survivorship_bias_free = True
    if not universe:
        survivorship_bias_free = False
        failures.append("no_universe_membership_records")
    else:
        by_ticker: dict[str, list[UniverseMembershipRecord]] = {}
        for record in universe:
            if record.universe_id != universe_id:
                continue
            by_ticker.setdefault(record.ticker, []).append(record)

        for session, ticker in normalized_keys:
            records = by_ticker.get(ticker, ())
            cutoff = parsed_cutoffs.get(session)
            eligible = [
                record
                for record in records
                if cutoff is not None
                and record.covers_session(session)
                and record.is_known_by(cutoff)
            ]
            if len(eligible) > 1:
                failures.append(f"overlapping_universe_interval:{session}:{ticker}")
                survivorship_bias_free = False
            elif not eligible:
                failures.append(f"ticker_not_eligible:{session}:{ticker}")
                survivorship_bias_free = False

    ordered_failures = tuple(dict.fromkeys(failures))
    return CoverageResult(
        point_in_time_data=not ordered_failures,
        survivorship_bias_free=survivorship_bias_free,
        checked_feature_columns=checked,
        covered_feature_columns=tuple(covered),
        missing_lineage_columns=tuple(missing),
        failures=ordered_failures,
        feature_keys=normalized_keys,
        universe_id=universe_id,
        decision_cutoffs=dict(decision_cutoffs),
        derived_columns=normalized_derived,
        value_hashes=selected_value_hashes,
    )


def latest_visible_revision(
    records: Sequence[FeatureAvailabilityRecord], *, cutoff: datetime
) -> FeatureAvailabilityRecord | None:
    """The revision that was actually visible at `cutoff`.

    Plan 7.5: "a later revision does not replace the historically visible
    value." Restatements are the whole reason `revision_id` is part of the
    record identity -- a fundamentals vendor revising Q3 revenue in Q4 must
    not retroactively change what a Q3-dated feature row contained. Selecting
    by the latest `available_at` that is still <= cutoff gives the historical
    answer; selecting by "most recent revision" would give today's answer.
    """
    if not isinstance(cutoff, datetime) or cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise AvailabilityError("cutoff must be a timezone-aware datetime")
    scopes = {
        (record.as_of_session, record.ticker, record.feature_name)
        for record in records
    }
    if len(scopes) > 1:
        raise AvailabilityError(
            "latest_visible_revision requires records for one session/ticker/feature"
        )
    visible = [record for record in records if record.is_available_by(cutoff)]
    if not visible:
        return None
    newest_at = max(_parse_timestamp(record.available_at, "available_at") for record in visible)
    newest = [
        record
        for record in visible
        if _parse_timestamp(record.available_at, "available_at") == newest_at
    ]
    if len({record.raw_value_hash for record in newest}) > 1:
        raise AvailabilityError(
            "multiple visible revisions have the same availability timestamp"
        )
    return max(newest, key=lambda record: record.revision_id)
