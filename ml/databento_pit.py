"""Databento point-in-time evidence capture for ML-LR-1.

This module advances the external-data half of ML-LR-1 without pretending
that one vendor response completes it.  It captures two evidence families:

* ``EQUS.SUMMARY`` statistics, whose ``ts_recv`` is the capture-server time
  at which an official preliminary OHLCV summary reached Databento; and
* Databento reference responses for point-in-time security identity and
  corporate-action adjustment factors.

Neither snapshot is wired into the model runtime.  In particular, listing
status is not index/strategy membership and raw statistics are unadjusted.
The prerequisite report therefore keeps ``point_in_time_data`` hardcoded
False until a separately reviewed vintage-adjustment builder and an explicit
historical-universe source exist.
"""
from __future__ import annotations

import dataclasses
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Mapping, Protocol, Sequence

import pandas as pd

from ml.availability import (
    UniverseMembershipRecord,
    hash_feature_value,
)
from ml.contracts import freeze_json
from ml.databento_source import (
    DEFAULT_DATASET,
    DEFAULT_STYPE_IN,
    DailyBarsRequest,
    DatabentoSnapshotRetainedError,
    DatabentoSourceError,
    HistoricalClient,
    create_historical_client,
    databento_source_version,
    download_and_preserve_dbn,
    write_immutable_bytes,
)
from ml.hashing import canonical_json, hash_bytes, hash_payload
from ml.shadow import trading_sessions

STATISTICS_SCHEMA = "statistics"
STATISTICS_SOURCE_ID = "databento_equities_summary_statistics"
REFERENCE_SOURCE_ID = "databento_reference"
PIT_SNAPSHOT_SCHEMA_VERSION = "1"
_EASTERN = "America/New_York"
_STAT_FEATURES = MappingProxyType(
    {1: "open", 4: "low", 5: "high", 6: "volume", 11: "close"}
)
_PRICE_FEATURES = frozenset({"open", "high", "low", "close"})
_REFERENCE_KINDS = frozenset({"security_master", "adjustment_factors"})
_SUMMARY_WINDOWS_ET = MappingProxyType(
    {
        1: ("16:05:00", "16:30:00"),
        2: ("16:50:00", "17:15:00"),
    }
)


class _ReferenceSecurityMaster(Protocol):
    def get_range(self, **kwargs: Any) -> pd.DataFrame: ...


class _ReferenceAdjustmentFactors(Protocol):
    def get_range(self, **kwargs: Any) -> pd.DataFrame: ...


class ReferenceClient(Protocol):
    security_master: _ReferenceSecurityMaster
    adjustment_factors: _ReferenceAdjustmentFactors


def _canonical_observed_at(value: str | None) -> str:
    candidate = value or datetime.now(timezone.utc).isoformat()
    if not isinstance(candidate, str):
        raise DatabentoSourceError("observed_at must be a timezone-aware timestamp")
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DatabentoSourceError(
            "observed_at must be a timezone-aware timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DatabentoSourceError("observed_at must be timezone-aware")
    return parsed.astimezone(timezone.utc).isoformat()


def _timestamp(value: Any, name: str) -> pd.Timestamp:
    try:
        result = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise DatabentoSourceError(f"{name} must be a timestamp") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise DatabentoSourceError(f"{name} must be timezone-aware")
    return result.tz_convert("UTC")


def _utc_iso(value: Any, name: str) -> str:
    return _timestamp(value, name).isoformat()


def _positive_cost_cap(value: Any) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) <= 0
    ):
        raise DatabentoSourceError("max_cost_usd must be positive and finite")
    return float(value)


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


@dataclasses.dataclass(frozen=True)
class StatisticsRequest:
    tickers: tuple[str, ...]
    start: str
    end: str
    summary_flag: int
    dataset: str = DEFAULT_DATASET
    schema: str = STATISTICS_SCHEMA
    stype_in: str = DEFAULT_STYPE_IN

    def __post_init__(self) -> None:
        # Reuse the already-reviewed ticker/date/vendor validation. Schema is
        # intentionally checked separately because DailyBarsRequest is fixed
        # to ohlcv-1d.
        validated = DailyBarsRequest(
            tickers=self.tickers,
            start=self.start,
            end=self.end,
            dataset=self.dataset,
            stype_in=self.stype_in,
        )
        if self.schema != STATISTICS_SCHEMA:
            raise DatabentoSourceError(
                f"statistics adapter only supports schema {STATISTICS_SCHEMA!r}"
            )
        start_date = date.fromisoformat(self.start)
        if date.fromisoformat(self.end) != start_date + timedelta(days=1):
            raise DatabentoSourceError(
                "statistics requests must cover exactly one calendar day"
            )
        if start_date not in trading_sessions(start_date, start_date):
            raise DatabentoSourceError(
                "statistics request.start must be an NYSE trading session"
            )
        if (
            isinstance(self.summary_flag, bool)
            or self.summary_flag not in _SUMMARY_WINDOWS_ET
        ):
            raise DatabentoSourceError("summary_flag must be 1 or 2")
        object.__setattr__(self, "tickers", validated.tickers)

    @property
    def query_start(self) -> str:
        start_time, _ = _SUMMARY_WINDOWS_ET[self.summary_flag]
        return pd.Timestamp(
            f"{self.start}T{start_time}", tz=_EASTERN
        ).isoformat()

    @property
    def query_end(self) -> str:
        _, end_time = _SUMMARY_WINDOWS_ET[self.summary_flag]
        return pd.Timestamp(
            f"{self.start}T{end_time}", tz=_EASTERN
        ).isoformat()

    @property
    def request_hash(self) -> str:
        return hash_payload(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "schema": self.schema,
            "stype_in": self.stype_in,
            "tickers": list(self.tickers),
            "start": self.start,
            "end": self.end,
            "summary_flag": self.summary_flag,
            "query_start": self.query_start,
            "query_end": self.query_end,
        }

    def api_kwargs(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "schema": self.schema,
            "stype_in": self.stype_in,
            "symbols": list(self.tickers),
            "start": self.query_start,
            "end": self.query_end,
        }


@dataclasses.dataclass(frozen=True)
class StatisticsValueRecord:
    as_of_session: str
    ticker: str
    instrument_id: int
    publisher_id: int
    channel_id: int
    feature_name: str
    value: float | int
    event_at: str
    reference_at: str | None
    available_at: str
    summary_flag: int
    sequence: int
    revision_id: str

    def __post_init__(self) -> None:
        if self.feature_name not in {*_PRICE_FEATURES, "volume"}:
            raise DatabentoSourceError("unsupported statistics feature_name")
        DailyBarsRequest(
            tickers=(self.ticker,),
            start=self.as_of_session,
            end=(date.fromisoformat(self.as_of_session) + timedelta(days=1)).isoformat(),
        )
        event = _timestamp(self.event_at, "event_at")
        if self.reference_at is not None:
            _timestamp(self.reference_at, "reference_at")
        available = _timestamp(self.available_at, "available_at")
        if event > available:
            raise DatabentoSourceError("statistics event_at must not exceed available_at")
        if isinstance(self.summary_flag, bool) or self.summary_flag not in (1, 2):
            raise DatabentoSourceError("summary_flag must be 1 or 2")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int):
            raise DatabentoSourceError("sequence must be an integer")
        for name in ("instrument_id", "publisher_id"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise DatabentoSourceError(f"{name} must be a positive integer")
        if (
            isinstance(self.channel_id, bool)
            or not isinstance(self.channel_id, int)
            or self.channel_id < 0
        ):
            raise DatabentoSourceError("channel_id must be a non-negative integer")
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise DatabentoSourceError("statistics value must be numeric")
        if not math.isfinite(float(self.value)) or float(self.value) <= 0:
            raise DatabentoSourceError("statistics value must be positive and finite")
        if not _is_sha256(self.revision_id):
            raise DatabentoSourceError("revision_id must be a SHA-256 digest")

    @property
    def raw_value_hash(self) -> str:
        return hash_feature_value(self.value)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class NormalizedStatistics:
    records: tuple[StatisticsValueRecord, ...]
    refusals: tuple[Mapping[str, str], ...]
    invalid_cohorts: tuple[tuple[str, str, int], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "records", tuple(self.records))
        object.__setattr__(
            self,
            "refusals",
            tuple(MappingProxyType(dict(item)) for item in self.refusals),
        )
        object.__setattr__(
            self,
            "invalid_cohorts",
            tuple(sorted(set(tuple(item) for item in self.invalid_cohorts))),
        )


@dataclasses.dataclass(frozen=True)
class CompleteStatisticsCohort:
    """One internally coherent preliminary OHLCV summary.

    This deliberately is *not* a FeatureAvailabilityRecord. The captured
    values are unadjusted. Only a future vintage-correct adjustment builder
    may transform this evidence into feature lineage after binding the
    appropriate security identity and adjustment-factor vintage.
    """

    as_of_session: str
    ticker: str
    summary_flag: int
    available_at: str
    observed_at: str
    cohort_id: str
    records: tuple[StatisticsValueRecord, ...]

    def __post_init__(self) -> None:
        records = tuple(self.records)
        if len(records) != len(_STAT_FEATURES):
            raise DatabentoSourceError("statistics cohort must contain five records")
        if {record.feature_name for record in records} != set(_STAT_FEATURES.values()):
            raise DatabentoSourceError("statistics cohort must contain complete OHLCV")
        if any(
            record.as_of_session != self.as_of_session
            or record.ticker != self.ticker
            or record.summary_flag != self.summary_flag
            for record in records
        ):
            raise DatabentoSourceError("statistics cohort records disagree on identity")
        if len(
            {
                (record.instrument_id, record.publisher_id)
                for record in records
            }
        ) != 1:
            raise DatabentoSourceError(
                "statistics cohort mixes instrument or publisher identities"
            )
        available = _timestamp(self.available_at, "available_at")
        observed = _timestamp(self.observed_at, "observed_at")
        if available != max(
            _timestamp(record.available_at, "record.available_at")
            for record in records
        ):
            raise DatabentoSourceError(
                "cohort available_at must equal the latest record receipt time"
            )
        if available > observed:
            raise DatabentoSourceError("cohort cannot be observed before it was received")
        values = {record.feature_name: float(record.value) for record in records}
        if values["high"] < max(
            values["open"], values["low"], values["close"]
        ) or values["low"] > min(
            values["open"], values["high"], values["close"]
        ):
            raise DatabentoSourceError(
                "statistics cohort contains internally inconsistent OHLC values"
            )
        if not _is_sha256(self.cohort_id):
            raise DatabentoSourceError("cohort_id must be a SHA-256 digest")
        object.__setattr__(self, "records", records)

    def to_dict(self) -> dict[str, Any]:
        payload = dataclasses.asdict(self)
        payload["records"] = [record.to_dict() for record in self.records]
        return payload


@dataclasses.dataclass(frozen=True)
class StatisticsSnapshot:
    normalized: NormalizedStatistics
    manifest: Mapping[str, Any]
    raw_path: Path
    manifest_path: Path

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "manifest", freeze_json(dict(self.manifest), path="manifest")
        )


def estimate_statistics_cost(
    request: StatisticsRequest, *, client: HistoricalClient | None = None
) -> float:
    active_client = client or create_historical_client()
    try:
        value = float(active_client.metadata.get_cost(**request.api_kwargs()))
    except Exception as exc:
        raise DatabentoSourceError(
            f"Databento statistics cost estimate failed: {type(exc).__name__}: {exc}"
        ) from exc
    if not math.isfinite(value) or value < 0:
        raise DatabentoSourceError("Databento returned an invalid statistics cost")
    return value


def _statistics_refusal(
    *, ticker: str, session: str, reason: str
) -> dict[str, str]:
    return {"ticker": ticker, "session": session, "reason": reason}


def normalize_statistics_frame(
    raw: pd.DataFrame, request: StatisticsRequest
) -> NormalizedStatistics:
    if not isinstance(raw, pd.DataFrame) or raw.empty:
        raise DatabentoSourceError("Databento returned no statistics records")
    required = {
        "ts_event",
        "ts_ref",
        "symbol",
        "publisher_id",
        "instrument_id",
        "stat_type",
        "stat_flags",
        "sequence",
        "channel_id",
        "update_action",
        "price",
        "quantity",
    }
    missing = sorted(required - set(raw.columns))
    if missing:
        raise DatabentoSourceError(
            f"Databento statistics are missing required columns: {missing}"
        )
    if "ts_recv" in raw.columns:
        receive_values = raw["ts_recv"]
    elif isinstance(raw.index, pd.DatetimeIndex):
        receive_values = pd.Series(raw.index, index=raw.index)
    else:
        raise DatabentoSourceError(
            "Databento statistics require ts_recv as a column or DatetimeIndex"
        )

    requested = set(request.tickers)
    # Databento's end is exclusive; trading_sessions() accepts an inclusive
    # end. Keeping that distinction explicit prevents a vendor over-return on
    # request.end from being mistaken for in-window evidence.
    start_date = date.fromisoformat(request.start)
    end_exclusive = date.fromisoformat(request.end)
    sessions = set(trading_sessions(start_date, end_exclusive - timedelta(days=1)))
    query_start = _timestamp(request.query_start, "request.query_start")
    query_end = _timestamp(request.query_end, "request.query_end")
    records: list[StatisticsValueRecord] = []
    refusals: list[Mapping[str, str]] = []
    invalid_cohorts: set[tuple[str, str, int]] = set()
    identities: set[tuple[int, int, int, int]] = set()
    for position, (_, row) in enumerate(raw.iterrows()):
        ticker = str(row["symbol"])
        if ticker not in requested:
            raise DatabentoSourceError(
                f"Databento statistics returned unrequested symbol {ticker!r}"
            )
        try:
            stat_type = int(row["stat_type"])
        except (TypeError, ValueError, OverflowError) as exc:
            raise DatabentoSourceError(
                f"statistics[{position}].stat_type is invalid"
            ) from exc
        feature_name = _STAT_FEATURES.get(stat_type)
        if feature_name is None:
            # Other official statistics are valid vendor data but irrelevant
            # to the OHLCV evidence this adapter owns.
            continue
        try:
            summary_flag = int(row["stat_flags"])
        except (TypeError, ValueError, OverflowError) as exc:
            raise DatabentoSourceError(
                f"statistics[{position}].stat_flags is invalid"
            ) from exc
        if summary_flag != request.summary_flag:
            # The final summary and the other preliminary vintage are outside
            # this immutable request's pinned summary-vintage contract.
            continue
        event = _timestamp(row["ts_event"], f"statistics[{position}].ts_event")
        receive = _timestamp(
            receive_values.iloc[position], f"statistics[{position}].ts_recv"
        )
        if receive < query_start or receive >= query_end:
            raise DatabentoSourceError(
                "Databento returned statistics outside the requested receive window"
            )
        session = event.tz_convert(_EASTERN).date()
        session_text = session.isoformat()
        if session < start_date or session >= end_exclusive:
            raise DatabentoSourceError(
                "Databento returned statistics outside the requested window"
            )
        if session not in sessions:
            raise DatabentoSourceError(
                "Databento returned statistics outside an NYSE session"
            )
        try:
            sequence = int(row["sequence"])
            update_action = int(row["update_action"])
            publisher_id = int(row["publisher_id"])
            instrument_id = int(row["instrument_id"])
            channel_id = int(row["channel_id"])
        except (TypeError, ValueError, OverflowError) as exc:
            raise DatabentoSourceError(
                f"statistics[{position}] has an invalid enum or sequence"
            ) from exc
        if (
            sequence < 0
            or publisher_id <= 0
            or instrument_id <= 0
            or channel_id < 0
        ):
            raise DatabentoSourceError(
                f"statistics[{position}] has an invalid identity or sequence"
            )
        cohort_key = (session_text, ticker, summary_flag)
        reason: str | None = None
        if event > receive:
            reason = "ts_event is after ts_recv"
        elif update_action != 1:
            # A DELETE can invalidate an earlier NEW. Until the adjustment
            # builder reconstructs deletion/replacement state, refuse the
            # whole preliminary cohort instead of falling back to stale data.
            reason = "statistics cohort contains a delete observation"
        raw_value = row["price"] if feature_name in _PRICE_FEATURES else row["quantity"]
        try:
            numeric = float(raw_value)
        except (TypeError, ValueError, OverflowError):
            numeric = math.nan
        if reason is None and (not math.isfinite(numeric) or numeric <= 0):
            reason = f"non-positive or non-finite {feature_name}"
        if reason is not None:
            invalid_cohorts.add(cohort_key)
            refusals.append(
                _statistics_refusal(
                    ticker=ticker, session=session_text, reason=reason
                )
            )
            continue
        value: float | int
        if feature_name == "volume":
            if numeric % 1 != 0:
                invalid_cohorts.add(cohort_key)
                refusals.append(
                    _statistics_refusal(
                        ticker=ticker,
                        session=session_text,
                        reason="non-integral volume",
                    )
                )
                continue
            value = int(numeric)
        else:
            value = numeric
        reference_at: str | None
        try:
            missing_reference = pd.isna(row["ts_ref"])
        except (TypeError, ValueError):
            missing_reference = False
        reference_at = (
            None
            if missing_reference
            else _utc_iso(row["ts_ref"], f"statistics[{position}].ts_ref")
        )
        identity = (publisher_id, instrument_id, channel_id, sequence)
        if identity in identities:
            raise DatabentoSourceError(
                "Databento returned duplicate statistics sequence identity"
            )
        identities.add(identity)
        revision_id = hash_payload(
            {
                "ticker": ticker,
                "publisher_id": publisher_id,
                "instrument_id": instrument_id,
                "channel_id": channel_id,
                "session": session_text,
                "feature_name": feature_name,
                "summary_flag": summary_flag,
                "sequence": sequence,
                "available_at": receive.isoformat(),
                "reference_at": reference_at,
                "value": value,
            }
        )
        records.append(
            StatisticsValueRecord(
                as_of_session=session_text,
                ticker=ticker,
                instrument_id=instrument_id,
                publisher_id=publisher_id,
                channel_id=channel_id,
                feature_name=feature_name,
                value=value,
                event_at=event.isoformat(),
                reference_at=reference_at,
                available_at=receive.isoformat(),
                summary_flag=summary_flag,
                sequence=sequence,
                revision_id=revision_id,
            )
        )
    if not records:
        raise DatabentoSourceError(
            "Databento statistics contained no usable preliminary OHLCV records"
        )
    ordered = tuple(
        sorted(
            records,
            key=lambda item: (
                item.as_of_session,
                item.ticker,
                item.summary_flag,
                item.feature_name,
                item.available_at,
                item.sequence,
            ),
        )
    )
    return NormalizedStatistics(
        records=ordered,
        refusals=tuple(refusals),
        invalid_cohorts=tuple(invalid_cohorts),
    )


def select_complete_statistics_cohorts(
    normalized: NormalizedStatistics,
    *,
    decision_cutoffs: Mapping[str, str],
    observed_at: str,
) -> tuple[CompleteStatisticsCohort, ...]:
    """Select the latest complete preliminary summary visible by each cutoff.

    The cohort's availability is its maximum ``ts_recv``. This prevents a
    caller from treating an early open as though the complete OHLCV state was
    knowable before its latest field arrived. The returned type is raw
    evidence, never production-shaped feature lineage.
    """
    observed = _timestamp(observed_at, "observed_at")
    grouped: dict[tuple[str, str, int], list[StatisticsValueRecord]] = {}
    for record in normalized.records:
        grouped.setdefault(
            (record.as_of_session, record.ticker, record.summary_flag), []
        ).append(record)
    by_key: dict[tuple[str, str], list[tuple[pd.Timestamp, int, list[StatisticsValueRecord]]]] = {}
    required = {*_PRICE_FEATURES, "volume"}
    invalid_cohorts = set(normalized.invalid_cohorts)
    for (session, ticker, flag), values in grouped.items():
        if (session, ticker, flag) in invalid_cohorts:
            continue
        cutoff_text = decision_cutoffs.get(session)
        if cutoff_text is None:
            continue
        cutoff = _timestamp(cutoff_text, f"decision_cutoffs[{session}]")
        visible = [
            record
            for record in values
            if _timestamp(record.available_at, "available_at") <= cutoff
        ]
        latest_by_feature: dict[str, StatisticsValueRecord] = {}
        for record in visible:
            prior = latest_by_feature.get(record.feature_name)
            if prior is None or (
                record.available_at,
                record.sequence,
                record.revision_id,
            ) > (prior.available_at, prior.sequence, prior.revision_id):
                latest_by_feature[record.feature_name] = record
        if set(latest_by_feature) != required:
            continue
        cohort = list(latest_by_feature.values())
        cohort_available = max(
            _timestamp(record.available_at, "available_at") for record in cohort
        )
        by_key.setdefault((session, ticker), []).append(
            (cohort_available, flag, cohort)
        )

    result: list[CompleteStatisticsCohort] = []
    for (session, ticker), candidates in sorted(by_key.items()):
        cohort_available, flag, cohort = max(candidates, key=lambda item: (item[0], item[1]))
        if cohort_available > observed:
            raise DatabentoSourceError(
                "observed_at precedes a selected statistics receive timestamp"
            )
        cohort_id = hash_payload(
            {
                "session": session,
                "ticker": ticker,
                "summary_flag": flag,
                "available_at": cohort_available.isoformat(),
                "revisions": sorted(record.revision_id for record in cohort),
            }
        )
        result.append(
            CompleteStatisticsCohort(
                as_of_session=session,
                ticker=ticker,
                summary_flag=flag,
                available_at=cohort_available.isoformat(),
                observed_at=observed.isoformat(),
                cohort_id=cohort_id,
                records=tuple(sorted(cohort, key=lambda item: item.feature_name)),
            )
        )
    return tuple(result)


def fetch_statistics_snapshot(
    request: StatisticsRequest,
    *,
    directory: Path,
    max_cost_usd: float,
    client: HistoricalClient | None = None,
    observed_at: str | None = None,
) -> StatisticsSnapshot:
    cap = _positive_cost_cap(max_cost_usd)
    active_client = client or create_historical_client()
    estimate = estimate_statistics_cost(request, client=active_client)
    if estimate > cap:
        raise DatabentoSourceError(
            f"estimated request cost ${estimate:.6f} exceeds max_cost_usd "
            f"${cap:.6f}; no data was downloaded"
        )
    naming_instant = _canonical_observed_at(observed_at)
    stamp = datetime.fromisoformat(naming_instant).strftime("%Y%m%dT%H%M%S%fZ")
    stem = f"databento-equs-statistics-{stamp}-{request.request_hash[:12]}"
    directory = Path(directory)
    raw_path = directory / f"{stem}.dbn"
    manifest_path = directory / f"{stem}.manifest.json"
    download = download_and_preserve_dbn(
        api_kwargs=request.api_kwargs(),
        directory=directory,
        stem=stem,
        raw_path=raw_path,
        manifest_path=manifest_path,
        client=active_client,
    )
    # With no injected replay timestamp, observation occurs only after the
    # response has actually been downloaded and preserved.
    observed = (
        naming_instant
        if observed_at is not None
        else _canonical_observed_at(None)
    )
    base_manifest = {
        "schema_version": PIT_SNAPSHOT_SCHEMA_VERSION,
        "source_id": STATISTICS_SOURCE_ID,
        "source_version": databento_source_version(),
        "request": request.to_dict(),
        "request_hash": request.request_hash,
        "observed_at": observed,
        "estimated_cost_usd": estimate,
        "raw_filename": raw_path.name,
        "raw_sha256": hash_bytes(download.raw_bytes),
        "exact_receive_timestamps": True,
        "adjustment_status": "unadjusted",
        "point_in_time_data": False,
        "provides_point_in_time_lineage": False,
    }
    try:
        if download.materialization_error is not None:
            raise download.materialization_error
        if download.frame is None:
            raise DatabentoSourceError("statistics DBN was not materialized")
        normalized = normalize_statistics_frame(download.frame, request)
        if any(
            _timestamp(record.available_at, "statistics.available_at")
            > _timestamp(observed, "observed_at")
            for record in normalized.records
        ):
            raise DatabentoSourceError(
                "statistics response contains a record received after observed_at"
            )
    except Exception as exc:
        reason = (
            exc
            if isinstance(exc, DatabentoSourceError)
            else DatabentoSourceError(
                f"Databento statistics validation failed: {type(exc).__name__}: {exc}"
            )
        )
        rejected = dict(base_manifest)
        rejected.update(
            {
                "validation_status": "rejected",
                "rejection_reason": str(reason),
                "record_count": 0,
                "refusal_count": 0,
                "refusals": [],
                "invalid_cohort_count": 0,
                "invalid_cohorts": [],
                "normalized_sha256": None,
                "blockers": [
                    "unadjusted_statistics",
                    "missing_point_in_time_adjustment_application",
                    "missing_historical_universe_membership",
                ],
            }
        )
        try:
            write_immutable_bytes(
                manifest_path, canonical_json(rejected).encode("utf-8")
            )
        except Exception as manifest_exc:
            raise DatabentoSnapshotRetainedError(
                f"{reason} — paid statistics DBN retained at {raw_path}, but "
                f"the rejection manifest could not be written: {manifest_exc}",
                raw_path=raw_path,
                manifest_path=manifest_path,
            ) from manifest_exc
        raise DatabentoSnapshotRetainedError(
            f"{reason} — paid statistics DBN retained at {raw_path}",
            raw_path=raw_path,
            manifest_path=manifest_path,
        ) from reason
    material = [record.to_dict() for record in normalized.records]
    manifest = dict(base_manifest)
    invalid_cohorts = [
        {"session": session, "ticker": ticker, "summary_flag": flag}
        for session, ticker, flag in normalized.invalid_cohorts
    ]
    manifest.update(
        {
            "validation_status": (
                "accepted_with_refusals" if normalized.refusals else "accepted"
            ),
            "rejection_reason": None,
            "record_count": len(material),
            "refusal_count": len(normalized.refusals),
            "refusals": [dict(item) for item in normalized.refusals],
            "invalid_cohort_count": len(invalid_cohorts),
            "invalid_cohorts": invalid_cohorts,
            "normalized_sha256": hash_bytes(
                canonical_json(material).encode("utf-8")
            ),
            "blockers": [
                "unadjusted_statistics",
                "missing_point_in_time_adjustment_application",
                "missing_historical_universe_membership",
            ],
        }
    )
    try:
        write_immutable_bytes(manifest_path, canonical_json(manifest).encode("utf-8"))
    except Exception as exc:
        raise DatabentoSnapshotRetainedError(
            f"paid statistics DBN retained at {raw_path}, but its manifest "
            f"could not be written: {type(exc).__name__}: {exc}",
            raw_path=raw_path,
            manifest_path=manifest_path,
        ) from exc
    return StatisticsSnapshot(
        normalized=normalized,
        manifest=manifest,
        raw_path=raw_path,
        manifest_path=manifest_path,
    )


@dataclasses.dataclass(frozen=True)
class ReferenceRequest:
    kind: Literal["security_master", "adjustment_factors"]
    tickers: tuple[str, ...]
    start: str
    end: str
    stype_in: str = DEFAULT_STYPE_IN
    country: str = "US"

    def __post_init__(self) -> None:
        if self.kind not in _REFERENCE_KINDS:
            raise DatabentoSourceError(
                f"reference kind must be one of {sorted(_REFERENCE_KINDS)}"
            )
        validated = DailyBarsRequest(
            tickers=self.tickers, start=self.start, end=self.end
        )
        if self.stype_in != DEFAULT_STYPE_IN:
            raise DatabentoSourceError("reference adapter only supports raw_symbol")
        if self.country != "US":
            raise DatabentoSourceError("reference adapter currently supports US only")
        object.__setattr__(self, "tickers", validated.tickers)

    @property
    def request_hash(self) -> str:
        return hash_payload(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "tickers": list(self.tickers),
            "start": self.start,
            "end": self.end,
            "stype_in": self.stype_in,
            "country": self.country,
        }

    def api_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "symbols": list(self.tickers),
            "stype_in": self.stype_in,
            "countries": [self.country],
            "start": self.start,
            "end": self.end,
        }
        if self.kind == "security_master":
            kwargs["index"] = "ts_effective"
        return kwargs


@dataclasses.dataclass(frozen=True)
class ReferenceSnapshot:
    records: tuple[Mapping[str, Any], ...]
    manifest: Mapping[str, Any]
    data_path: Path
    manifest_path: Path

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "records",
            tuple(freeze_json(dict(item), path="reference_record") for item in self.records),
        )
        object.__setattr__(
            self, "manifest", freeze_json(dict(self.manifest), path="manifest")
        )


def create_reference_client() -> ReferenceClient:
    try:
        import databento as db
    except ImportError as exc:
        raise DatabentoSourceError(
            "databento package is not installed; install requirements.txt"
        ) from exc
    try:
        return db.Reference()
    except Exception as exc:
        raise DatabentoSourceError(
            f"Databento reference client creation failed: {type(exc).__name__}: {exc}"
        ) from exc


def _json_scalar(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (pd.Timestamp, datetime)):
        return _utc_iso(value, "reference timestamp")
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float):
        if not math.isfinite(value):
            raise DatabentoSourceError("reference response contains infinity")
        return value
    if isinstance(value, (str, bool, int)):
        return value
    raise DatabentoSourceError(
        f"unsupported reference value type {type(value).__name__}"
    )


def canonical_reference_records(
    frame: pd.DataFrame, request: ReferenceRequest
) -> tuple[dict[str, Any], ...]:
    if not isinstance(frame, pd.DataFrame):
        raise DatabentoSourceError("Databento reference response must be a DataFrame")
    working = frame.copy()
    index_name = "ts_effective" if request.kind == "security_master" else "ex_date"
    if index_name not in working.columns:
        if working.index.name != index_name:
            raise DatabentoSourceError(
                f"{request.kind} response must be indexed by {index_name}"
            )
        working = working.reset_index()
    required = (
        {
            "ts_effective",
            "ts_record",
            "ts_created",
            "listing_id",
            "security_id",
            "listing_status",
            "operating_mic",
            "symbol",
        }
        if request.kind == "security_master"
        else {
            "ex_date",
            "ts_created",
            "event_id",
            "security_id",
            "status",
            "factor",
            "reason",
            "option",
            "operating_mic",
            "symbol",
        }
    )
    missing = sorted(required - set(working.columns))
    if missing:
        raise DatabentoSourceError(
            f"{request.kind} response is missing required columns: {missing}"
        )
    records: list[dict[str, Any]] = []
    for position, row in working.iterrows():
        record: dict[str, Any] = {}
        for column, value in row.items():
            name = str(column)
            if name == "ex_date":
                # The API models ex_date as a date, not an instant. Pandas may
                # materialize it as datetime64[ns], which must not trigger an
                # invented timezone or midnight availability timestamp.
                try:
                    if pd.isna(value):
                        raise ValueError
                    parsed_date = pd.Timestamp(value).date()
                except (TypeError, ValueError) as exc:
                    raise DatabentoSourceError(
                        f"adjustment_factors[{position}].ex_date is invalid"
                    ) from exc
                record[name] = parsed_date.isoformat()
            else:
                record[name] = _json_scalar(value)
        symbol = record.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            raise DatabentoSourceError(
                f"{request.kind}[{position}].symbol is missing"
            )
        if symbol not in request.tickers:
            raise DatabentoSourceError(
                f"{request.kind} returned unrequested symbol {symbol!r}"
            )
        for timestamp_name in (
            ("ts_effective", "ts_record", "ts_created")
            if request.kind == "security_master"
            else ("ts_created",)
        ):
            value = record.get(timestamp_name)
            if value is None:
                raise DatabentoSourceError(
                    f"{request.kind}[{position}].{timestamp_name} is missing"
                )
            _timestamp(value, f"{request.kind}[{position}].{timestamp_name}")
        if request.kind == "security_master":
            scope_date = _timestamp(
                record["ts_effective"],
                f"security_master[{position}].ts_effective",
            ).date()
        else:
            scope_date = date.fromisoformat(str(record["ex_date"]))
        if not (
            date.fromisoformat(request.start)
            <= scope_date
            < date.fromisoformat(request.end)
        ):
            raise DatabentoSourceError(
                f"{request.kind} returned a record outside the requested window"
            )
        if request.kind == "adjustment_factors":
            factor = record.get("factor")
            if isinstance(factor, bool) or not isinstance(factor, (int, float)):
                raise DatabentoSourceError("adjustment factor must be numeric")
            if not math.isfinite(float(factor)) or float(factor) <= 0:
                raise DatabentoSourceError("adjustment factor must be positive and finite")
            if record.get("status") not in {"A", "P", "R"}:
                raise DatabentoSourceError("adjustment status must be A, P, or R")
            option = record.get("option")
            reason = record.get("reason")
            if (
                isinstance(option, bool)
                or not isinstance(option, int)
                or not 1 <= option <= 9
            ):
                raise DatabentoSourceError("adjustment option must be 1 through 9")
            if isinstance(reason, bool) or not isinstance(reason, int) or reason <= 0:
                raise DatabentoSourceError("adjustment reason must be a positive integer")
        for identity_name in ("security_id", "operating_mic"):
            if record.get(identity_name) in (None, ""):
                raise DatabentoSourceError(
                    f"{request.kind}[{position}].{identity_name} is missing"
                )
        identity_name = (
            "listing_id" if request.kind == "security_master" else "event_id"
        )
        if record.get(identity_name) in (None, ""):
            raise DatabentoSourceError(
                f"{request.kind}[{position}].{identity_name} is missing"
            )
        if request.kind == "security_master" and record.get("listing_status") in (
            None,
            "",
        ):
            raise DatabentoSourceError(
                f"security_master[{position}].listing_status is missing"
            )
        records.append(record)
    if request.kind == "security_master" and not records:
        raise DatabentoSourceError("security_master response contained no records")
    return tuple(sorted(records, key=canonical_json))


def fetch_reference_snapshot(
    request: ReferenceRequest,
    *,
    directory: Path,
    acknowledge_reference_subscription: bool,
    client: ReferenceClient | None = None,
    observed_at: str | None = None,
) -> ReferenceSnapshot:
    if acknowledge_reference_subscription is not True:
        raise DatabentoSourceError(
            "reference request requires explicit subscription acknowledgement"
        )
    active_client = client or create_reference_client()
    naming_instant = _canonical_observed_at(observed_at)
    try:
        service = getattr(active_client, request.kind)
        frame = service.get_range(**request.api_kwargs())
    except Exception as exc:
        raise DatabentoSourceError(
            f"Databento {request.kind} request failed: {type(exc).__name__}: {exc}"
        ) from exc
    observed = (
        naming_instant
        if observed_at is not None
        else _canonical_observed_at(None)
    )
    records = canonical_reference_records(frame, request)
    if any(
        _timestamp(record["ts_created"], "reference.ts_created")
        > _timestamp(observed, "observed_at")
        for record in records
    ):
        raise DatabentoSourceError(
            "reference response contains a record created after observed_at"
        )
    payload = {
        "schema_version": PIT_SNAPSHOT_SCHEMA_VERSION,
        "kind": request.kind,
        "request": request.to_dict(),
        "records": list(records),
    }
    data_bytes = canonical_json(payload).encode("utf-8")
    stamp = datetime.fromisoformat(naming_instant).strftime("%Y%m%dT%H%M%S%fZ")
    stem = f"databento-{request.kind.replace('_', '-')}-{stamp}-{request.request_hash[:12]}"
    directory = Path(directory)
    data_path = directory / f"{stem}.reference.json"
    manifest_path = directory / f"{stem}.manifest.json"
    write_immutable_bytes(data_path, data_bytes)
    manifest = {
        "schema_version": PIT_SNAPSHOT_SCHEMA_VERSION,
        "source_id": REFERENCE_SOURCE_ID,
        "source_version": databento_source_version(),
        "kind": request.kind,
        "request": request.to_dict(),
        "request_hash": request.request_hash,
        "observed_at": observed,
        "data_filename": data_path.name,
        "data_sha256": hash_bytes(data_bytes),
        "row_count": len(records),
        "validation_status": "accepted",
        "point_in_time_reference": True,
        "point_in_time_data": False,
        "provides_point_in_time_lineage": False,
        "limitation": (
            "Reference evidence does not itself apply vintage-correct adjustments "
            "or establish historical strategy/index membership."
        ),
    }
    try:
        write_immutable_bytes(manifest_path, canonical_json(manifest).encode("utf-8"))
    except Exception as exc:
        raise DatabentoSnapshotRetainedError(
            f"licensed reference snapshot retained at {data_path}, but its "
            f"manifest could not be written: {type(exc).__name__}: {exc}",
            raw_path=data_path,
            manifest_path=manifest_path,
        ) from exc
    return ReferenceSnapshot(
        records=records,
        manifest=manifest,
        data_path=data_path,
        manifest_path=manifest_path,
    )


@dataclasses.dataclass(frozen=True)
class DatabentoPITPrerequisiteReport:
    capture_prerequisites_complete: bool
    failures: tuple[str, ...]
    statistics_request_hash: str | None
    security_master_request_hash: str | None
    adjustment_factors_request_hash: str | None
    historical_universe_record_count: int

    @property
    def point_in_time_data(self) -> bool:
        # Capture readiness is not dataset authority. A future reviewed
        # vintage-adjustment/dataset builder must derive that claim through
        # evaluate_point_in_time_coverage().
        return False

    def to_dict(self) -> dict[str, Any]:
        payload = dataclasses.asdict(self)
        payload["point_in_time_data"] = False
        return payload


def evaluate_databento_pit_prerequisites(
    *,
    statistics_manifest: Mapping[str, Any] | None,
    security_master_manifest: Mapping[str, Any] | None,
    adjustment_factors_manifest: Mapping[str, Any] | None,
    historical_universe: Sequence[UniverseMembershipRecord],
    vintage_adjustment_application_complete: bool,
) -> DatabentoPITPrerequisiteReport:
    failures: list[str] = []

    def accepted(
        manifest: Mapping[str, Any] | None,
        kind: str,
        *,
        expected_source_id: str,
        expected_reference_kind: str | None = None,
    ) -> tuple[str | None, tuple[frozenset[str], date, date] | None]:
        if manifest is None:
            failures.append(f"missing_{kind}_snapshot")
            return None, None
        if manifest.get("source_id") != expected_source_id:
            failures.append(f"unexpected_{kind}_source")
        if expected_reference_kind is not None and (
            manifest.get("kind") != expected_reference_kind
        ):
            failures.append(f"unexpected_{kind}_kind")
        if manifest.get("validation_status") not in {
            "accepted",
            "accepted_with_refusals",
        }:
            failures.append(f"rejected_{kind}_snapshot")
        if manifest.get("point_in_time_data") is not False or (
            manifest.get("provides_point_in_time_lineage") is not False
        ):
            failures.append(f"unsafe_{kind}_authority_claim")
        request_hash = manifest.get("request_hash")
        if not _is_sha256(request_hash):
            failures.append(f"invalid_{kind}_request_hash")
            request_hash = None
        request = manifest.get("request")
        scope: tuple[frozenset[str], date, date] | None = None
        if isinstance(request, Mapping):
            tickers = request.get("tickers")
            try:
                if not isinstance(tickers, (list, tuple)):
                    raise ValueError
                symbols = frozenset(str(value) for value in tickers)
                start_text = request.get("start")
                end_text = request.get("end")
                if not isinstance(start_text, str) or not isinstance(end_text, str):
                    raise ValueError
                start = date.fromisoformat(start_text)
                end = date.fromisoformat(end_text)
                if (
                    not symbols
                    or any(
                        not symbol or symbol != symbol.upper()
                        for symbol in symbols
                    )
                    or end <= start
                ):
                    raise ValueError
                scope = (symbols, start, end)
            except (TypeError, ValueError):
                failures.append(f"invalid_{kind}_request_scope")
            if request_hash is not None and hash_payload(dict(request)) != request_hash:
                failures.append(f"mismatched_{kind}_request_hash")
        else:
            failures.append(f"invalid_{kind}_request_scope")
        return request_hash, scope

    statistics_hash, statistics_scope = accepted(
        statistics_manifest,
        "statistics",
        expected_source_id=STATISTICS_SOURCE_ID,
    )
    if statistics_manifest is not None and (
        statistics_manifest.get("exact_receive_timestamps") is not True
    ):
        failures.append("statistics_lack_exact_receive_timestamps")
    if statistics_manifest is not None and (
        not isinstance(statistics_manifest.get("record_count"), int)
        or statistics_manifest.get("record_count", 0) <= 0
    ):
        failures.append("statistics_have_no_records")
    if statistics_manifest is not None and (
        statistics_manifest.get("invalid_cohort_count") != 0
    ):
        failures.append("statistics_have_invalid_cohorts")
    security_hash, security_scope = accepted(
        security_master_manifest,
        "security_master",
        expected_source_id=REFERENCE_SOURCE_ID,
        expected_reference_kind="security_master",
    )
    if security_master_manifest is not None and (
        security_master_manifest.get("point_in_time_reference") is not True
    ):
        failures.append("security_master_not_point_in_time")
    adjustment_hash, adjustment_scope = accepted(
        adjustment_factors_manifest,
        "adjustment_factors",
        expected_source_id=REFERENCE_SOURCE_ID,
        expected_reference_kind="adjustment_factors",
    )
    if adjustment_factors_manifest is not None and (
        adjustment_factors_manifest.get("point_in_time_reference") is not True
    ):
        failures.append("adjustment_factors_not_point_in_time")
    if statistics_scope is not None:
        for kind, reference_scope in (
            ("security_master", security_scope),
            ("adjustment_factors", adjustment_scope),
        ):
            if reference_scope is None:
                continue
            reference_symbols, reference_start, reference_end = reference_scope
            statistics_symbols, statistics_start, statistics_end = statistics_scope
            if not (
                reference_symbols.issuperset(statistics_symbols)
                and reference_start <= statistics_start
                and reference_end >= statistics_end
            ):
                failures.append(f"{kind}_scope_does_not_cover_statistics")
    universe = tuple(historical_universe)
    if not universe:
        failures.append("missing_historical_universe_membership")
    elif not all(isinstance(record, UniverseMembershipRecord) for record in universe):
        failures.append("invalid_historical_universe_membership")
    if vintage_adjustment_application_complete is not True:
        failures.append("missing_vintage_adjustment_application")
    ordered = tuple(dict.fromkeys(failures))
    return DatabentoPITPrerequisiteReport(
        capture_prerequisites_complete=not ordered,
        failures=ordered,
        statistics_request_hash=statistics_hash,
        security_master_request_hash=security_hash,
        adjustment_factors_request_hash=adjustment_hash,
        historical_universe_record_count=len(universe),
    )
