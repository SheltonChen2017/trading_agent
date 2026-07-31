"""ML-LR-1: point-in-time lineage and historical universe membership
(live-readiness plan section 7).

This module removes the project's largest research blocker. Today
`ml/datasets.py` must always report `point_in_time_data=False` because
nothing can prove WHEN each feature value became knowable. That is not
pedantry: yfinance's adjusted closes are rewritten retroactively whenever a
split or dividend is announced, so a "2024-03-01 close" fetched today is not
the number anyone could have seen on 2024-03-01.

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
from datetime import date, datetime
from typing import Any, Mapping, Protocol, Sequence

from ml.contracts import ContractError, _check_required_str, _check_sha256, _parse_timestamp

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
        available_at = _parse_timestamp(self.available_at, "available_at")
        session_start = datetime(
            target.year, target.month, target.day, cutoff_hour_utc,
            tzinfo=available_at.tzinfo,
        )
        return available_at <= session_start

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "point_in_time_data": self.point_in_time_data,
            "survivorship_bias_free": self.survivorship_bias_free,
            "checked_feature_columns": list(self.checked_feature_columns),
            "covered_feature_columns": list(self.covered_feature_columns),
            "missing_lineage_columns": list(self.missing_lineage_columns),
            "failures": list(self.failures),
        }


def evaluate_point_in_time_coverage(
    *,
    feature_keys: Sequence[tuple[str, str]],
    feature_columns: Sequence[str],
    availability: Sequence[FeatureAvailabilityRecord],
    universe: Sequence[UniverseMembershipRecord],
    universe_id: str,
    decision_cutoffs: Mapping[str, str],
    derived_columns: Mapping[str, Sequence[str]] = {},
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

    # --- duplicate identity ------------------------------------------------
    identities = [record.identity for record in availability]
    if len(identities) != len(set(identities)):
        failures.append("duplicate_feature_availability_identity")

    # --- availability vs decision cutoff -----------------------------------
    parsed_cutoffs = {
        session: _parse_timestamp(value, f"decision_cutoffs[{session}]")
        for session, value in decision_cutoffs.items()
    }
    for record in availability:
        cutoff = parsed_cutoffs.get(record.as_of_session)
        if cutoff is None:
            failures.append(f"missing_decision_cutoff:{record.as_of_session}")
            continue
        if not record.is_available_by(cutoff):
            failures.append(
                f"availability_after_cutoff:{record.as_of_session}:{record.ticker}"
                f":{record.feature_name}"
            )

    # --- per-key column coverage -------------------------------------------
    covered_by_key: dict[tuple[str, str], set[str]] = {}
    for record in availability:
        cutoff = parsed_cutoffs.get(record.as_of_session)
        if cutoff is not None and record.is_available_by(cutoff):
            covered_by_key.setdefault(
                (record.as_of_session, record.ticker), set()
            ).add(record.feature_name)

    checked = tuple(feature_columns)
    covered: list[str] = []
    missing: list[str] = []
    for column in checked:
        inputs = tuple(derived_columns.get(column, (column,)))
        if not inputs:
            missing.append(column)
            continue
        if all(
            all(source in covered_by_key.get(key, set()) for source in inputs)
            for key in feature_keys
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

        # Overlapping intervals for one ticker make membership ambiguous.
        for ticker, records in by_ticker.items():
            ordered = sorted(records, key=lambda r: r.effective_from)
            for earlier, later in zip(ordered, ordered[1:]):
                earlier_end = earlier.effective_to
                if earlier_end is None or later.effective_from <= earlier_end:
                    failures.append(f"overlapping_universe_interval:{ticker}")
                    survivorship_bias_free = False
                    break

        for session, ticker in feature_keys:
            records = by_ticker.get(ticker, ())
            if not any(
                record.covers_session(session) and record.is_known_by_session(session)
                for record in records
            ):
                failures.append(f"ticker_not_eligible:{session}:{ticker}")
                survivorship_bias_free = False

    ordered_failures = tuple(dict.fromkeys(failures))
    return CoverageResult(
        point_in_time_data=not ordered_failures,
        survivorship_bias_free=survivorship_bias_free and not ordered_failures,
        checked_feature_columns=checked,
        covered_feature_columns=tuple(covered),
        missing_lineage_columns=tuple(missing),
        failures=ordered_failures,
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
    visible = [record for record in records if record.is_available_by(cutoff)]
    if not visible:
        return None
    return max(visible, key=lambda r: (_parse_timestamp(r.available_at, "available_at"), r.revision_id))
