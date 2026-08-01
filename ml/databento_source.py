"""Auditable Databento daily-bar ingestion for ML research.

The adapter deliberately separates three claims that are easy to conflate:

* Databento ``EQUS.SUMMARY`` is an authoritative source of unadjusted,
  consolidated end-of-day US-equity bars.
* A downloaded DBN file can be preserved and hash-bound as an immutable raw
  snapshot.
* The OHLCV-1d record itself does *not* carry the per-record publication or
  receive timestamp required by :mod:`ml.availability`.

Consequently this module never turns ``point_in_time_data`` on.  A later
adapter may do so only after binding the values to receipt-timestamped
``statistics`` records and point-in-time adjustment/security-master data.
That fail-closed distinction keeps a paid data source from being treated as
look-ahead-safe merely because it is reputable.
"""
from __future__ import annotations

import dataclasses
import math
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence

import pandas as pd

from ml.availability import (
    FeatureAvailabilityRecord,
    UniverseMembershipRecord,
)
from ml.hashing import canonical_json, hash_bytes, hash_payload

DATABENTO_API_KEY_ENV = "DATABENTO_API_KEY"
DEFAULT_DATASET = "EQUS.SUMMARY"
DEFAULT_SCHEMA = "ohlcv-1d"
DEFAULT_STYPE_IN = "raw_symbol"
SOURCE_ID = "databento_equities_summary"
SNAPSHOT_SCHEMA_VERSION = "1"
_REQUIRED_BAR_COLUMNS = ("open", "high", "low", "close", "volume", "symbol")


class DatabentoSourceError(ValueError):
    """A Databento request or returned snapshot is unsafe to use."""


class _MetadataClient(Protocol):
    def get_cost(self, **kwargs: Any) -> float: ...

    def list_datasets(self) -> Sequence[str]: ...


class _TimeseriesClient(Protocol):
    def get_range(self, **kwargs: Any) -> Any: ...


class HistoricalClient(Protocol):
    metadata: _MetadataClient
    timeseries: _TimeseriesClient


def _canonical_date(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise DatabentoSourceError(f"{name} must use canonical YYYY-MM-DD format")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise DatabentoSourceError(
            f"{name} must use canonical YYYY-MM-DD format"
        ) from exc
    if parsed.isoformat() != value:
        raise DatabentoSourceError(f"{name} must use canonical YYYY-MM-DD format")
    return value


def _canonical_ticker(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or value != value.upper()
        or not all(character.isalnum() or character in ".-" for character in value)
    ):
        raise DatabentoSourceError(
            f"{name} must be a canonical uppercase ticker"
        )
    return value


def _aware_timestamp(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise DatabentoSourceError(f"{name} must be a timezone-aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DatabentoSourceError(
            f"{name} must be a timezone-aware ISO timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DatabentoSourceError(f"{name} must be a timezone-aware ISO timestamp")
    return parsed.astimezone(timezone.utc).isoformat()


@dataclasses.dataclass(frozen=True)
class DailyBarsRequest:
    """One tightly-scoped, cost-estimable historical request."""

    tickers: tuple[str, ...]
    start: str
    end: str
    dataset: str = DEFAULT_DATASET
    schema: str = DEFAULT_SCHEMA
    stype_in: str = DEFAULT_STYPE_IN

    def __post_init__(self) -> None:
        if not isinstance(self.tickers, tuple) or not self.tickers:
            raise DatabentoSourceError("tickers must contain at least one ticker")
        tickers = tuple(
            _canonical_ticker(value, f"tickers[{index}]")
            for index, value in enumerate(self.tickers)
        )
        if len(set(tickers)) != len(tickers):
            raise DatabentoSourceError("tickers must not contain duplicates")
        start = _canonical_date(self.start, "start")
        end = _canonical_date(self.end, "end")
        if date.fromisoformat(end) <= date.fromisoformat(start):
            raise DatabentoSourceError("end must be after start (Databento end is exclusive)")
        if self.dataset != DEFAULT_DATASET:
            raise DatabentoSourceError(
                f"daily-bar adapter only supports dataset {DEFAULT_DATASET!r}"
            )
        if self.schema != DEFAULT_SCHEMA:
            raise DatabentoSourceError(
                f"daily-bar adapter only supports schema {DEFAULT_SCHEMA!r}"
            )
        if self.stype_in != DEFAULT_STYPE_IN:
            raise DatabentoSourceError(
                f"daily-bar adapter only supports stype_in {DEFAULT_STYPE_IN!r}"
            )
        object.__setattr__(self, "tickers", tickers)

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
        }

    def api_kwargs(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "schema": self.schema,
            "stype_in": self.stype_in,
            "symbols": list(self.tickers),
            "start": self.start,
            "end": self.end,
        }


@dataclasses.dataclass(frozen=True)
class DailyBarsSnapshot:
    frames: Mapping[str, pd.DataFrame]
    manifest: Mapping[str, Any]
    raw_path: Path
    manifest_path: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "frames", MappingProxyType(dict(self.frames)))
        object.__setattr__(self, "manifest", MappingProxyType(dict(self.manifest)))


def databento_is_configured(environ: Mapping[str, str] | None = None) -> bool:
    source = os.environ if environ is None else environ
    value = source.get(DATABENTO_API_KEY_ENV, "")
    return bool(value.strip())


def create_historical_client() -> HistoricalClient:
    """Create the official client without copying the key into arguments/logs."""
    if not databento_is_configured():
        raise DatabentoSourceError(
            f"{DATABENTO_API_KEY_ENV} is not configured in this process"
        )
    try:
        import databento as db
    except ImportError as exc:
        raise DatabentoSourceError(
            "databento package is not installed; install requirements.txt"
        ) from exc
    # The official client reads DATABENTO_API_KEY itself.  Passing no key also
    # reduces the chance of a future exception rendering a credential.
    return db.Historical()


def estimate_daily_bars_cost(
    request: DailyBarsRequest, *, client: HistoricalClient | None = None
) -> float:
    active_client = client or create_historical_client()
    try:
        value = float(active_client.metadata.get_cost(**request.api_kwargs()))
    except Exception as exc:
        raise DatabentoSourceError(
            f"Databento cost estimate failed: {type(exc).__name__}: {exc}"
        ) from exc
    if not math.isfinite(value) or value < 0:
        raise DatabentoSourceError("Databento returned an invalid cost estimate")
    return value


def _normalize_daily_frame(
    raw: pd.DataFrame, request: DailyBarsRequest
) -> dict[str, pd.DataFrame]:
    if not isinstance(raw, pd.DataFrame) or raw.empty:
        raise DatabentoSourceError("Databento returned no daily bars")
    missing = [name for name in _REQUIRED_BAR_COLUMNS if name not in raw.columns]
    if missing:
        raise DatabentoSourceError(
            f"Databento daily bars are missing required columns: {missing}"
        )
    if not isinstance(raw.index, pd.DatetimeIndex):
        raise DatabentoSourceError("Databento daily bars require a DatetimeIndex")
    if raw.index.hasnans:
        raise DatabentoSourceError("Databento daily bars contain a missing timestamp")

    working = raw.loc[:, list(_REQUIRED_BAR_COLUMNS)].copy()
    utc_index = pd.to_datetime(working.index, utc=True, errors="coerce")
    if utc_index.hasnans:
        raise DatabentoSourceError("Databento daily bars contain an invalid timestamp")
    # EQUS.SUMMARY OHLCV-1d uses UTC-date interval starts.  Removing the
    # timezone produces the normalized trading-session index expected by the
    # feature code without changing the represented calendar date.
    working.index = utc_index.tz_convert("UTC").tz_localize(None).normalize()
    working["symbol"] = working["symbol"].astype(str)

    unknown = sorted(set(working["symbol"]) - set(request.tickers))
    if unknown:
        raise DatabentoSourceError(
            f"Databento returned unrequested symbols: {unknown}"
        )

    frames: dict[str, pd.DataFrame] = {}
    for ticker in request.tickers:
        frame = working.loc[working["symbol"] == ticker].drop(columns="symbol")
        if frame.empty:
            raise DatabentoSourceError(f"Databento omitted requested ticker {ticker!r}")
        if frame.index.has_duplicates:
            raise DatabentoSourceError(
                f"Databento returned duplicate daily bars for {ticker!r}"
            )
        frame = frame.sort_index()
        if frame.index[0].date() < date.fromisoformat(request.start):
            raise DatabentoSourceError("Databento returned a bar before request.start")
        if frame.index[-1].date() >= date.fromisoformat(request.end):
            raise DatabentoSourceError(
                "Databento returned a bar at or after exclusive request.end"
            )
        for column in ("open", "high", "low", "close", "volume"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        numeric = frame.loc[:, ["open", "high", "low", "close", "volume"]]
        finite = numeric.apply(lambda column: column.map(math.isfinite)).all().all()
        if not finite or (numeric <= 0).any().any():
            raise DatabentoSourceError(
                f"Databento returned non-positive or non-finite bars for {ticker!r}"
            )
        if (
            (frame["high"] < frame[["open", "low", "close"]].max(axis=1)).any()
            or (frame["low"] > frame[["open", "high", "close"]].min(axis=1)).any()
        ):
            raise DatabentoSourceError(
                f"Databento returned internally inconsistent OHLC values for {ticker!r}"
            )
        volumes = frame["volume"]
        if ((volumes % 1) != 0).any():
            raise DatabentoSourceError(
                f"Databento returned non-integral volume for {ticker!r}"
            )
        frame["volume"] = volumes.astype("int64")
        frames[ticker] = frame
    return frames


def normalize_daily_bars(
    store_or_frame: Any, request: DailyBarsRequest
) -> dict[str, pd.DataFrame]:
    """Normalize an official ``DBNStore`` (or a test DataFrame) into frames."""
    if isinstance(store_or_frame, pd.DataFrame):
        raw = store_or_frame
    else:
        converter = getattr(store_or_frame, "to_df", None)
        if not callable(converter):
            raise DatabentoSourceError("Databento response cannot be converted to pandas")
        try:
            raw = converter(price_type="float", pretty_ts=True, map_symbols=True)
        except Exception as exc:
            raise DatabentoSourceError(
                f"Databento DBN conversion failed: {type(exc).__name__}: {exc}"
            ) from exc
    return _normalize_daily_frame(raw, request)


def _normalized_material(frames: Mapping[str, pd.DataFrame]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ticker in sorted(frames):
        for session, row in frames[ticker].sort_index().iterrows():
            rows.append(
                {
                    "ticker": ticker,
                    "session": session.date().isoformat(),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": int(row["volume"]),
                }
            )
    return rows


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise DatabentoSourceError(f"refusing to overwrite immutable snapshot {path}")
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            raise DatabentoSourceError(
                f"refusing to overwrite immutable snapshot {path}"
            )
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def fetch_daily_bars_snapshot(
    request: DailyBarsRequest,
    *,
    directory: Path,
    max_cost_usd: float,
    client: HistoricalClient | None = None,
    observed_at: str | None = None,
) -> DailyBarsSnapshot:
    """Estimate, cap, download, validate, and immutably preserve one request."""
    if (
        isinstance(max_cost_usd, bool)
        or not isinstance(max_cost_usd, (int, float))
        or not math.isfinite(float(max_cost_usd))
        or float(max_cost_usd) <= 0
    ):
        raise DatabentoSourceError("max_cost_usd must be positive and finite")
    active_client = client or create_historical_client()
    estimate = estimate_daily_bars_cost(request, client=active_client)
    if estimate > float(max_cost_usd):
        raise DatabentoSourceError(
            f"estimated request cost ${estimate:.6f} exceeds "
            f"max_cost_usd ${float(max_cost_usd):.6f}; no data was downloaded"
        )

    observed = _aware_timestamp(
        observed_at or datetime.now(timezone.utc).isoformat(), "observed_at"
    )
    stamp = datetime.fromisoformat(observed).strftime("%Y%m%dT%H%M%S%fZ")
    stem = f"databento-equs-summary-{stamp}-{request.request_hash[:12]}"
    directory = Path(directory)
    raw_path = directory / f"{stem}.dbn"
    manifest_path = directory / f"{stem}.manifest.json"
    if raw_path.exists() or manifest_path.exists():
        raise DatabentoSourceError("refusing to overwrite an immutable snapshot")
    directory.mkdir(parents=True, exist_ok=True)

    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=directory, prefix=f".{stem}.", suffix=".dbn.tmp"
    )
    os.close(file_descriptor)
    temporary_raw = Path(temporary_name)
    # The Databento client requires a non-existent destination path.
    temporary_raw.unlink()
    try:
        try:
            store = active_client.timeseries.get_range(
                **request.api_kwargs(), path=temporary_raw
            )
        except Exception as exc:
            raise DatabentoSourceError(
                f"Databento download failed: {type(exc).__name__}: {exc}"
            ) from exc
        if not temporary_raw.is_file() or temporary_raw.stat().st_size <= 0:
            raise DatabentoSourceError("Databento did not write a non-empty DBN snapshot")
        frames = normalize_daily_bars(store, request)
        raw_bytes = temporary_raw.read_bytes()
        normalized = _normalized_material(frames)
        manifest = {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "source_id": SOURCE_ID,
            "source_version": "databento-python-0.81.0",
            "request": request.to_dict(),
            "request_hash": request.request_hash,
            "observed_at": observed,
            "estimated_cost_usd": estimate,
            "raw_filename": raw_path.name,
            "raw_sha256": hash_bytes(raw_bytes),
            "normalized_sha256": hash_bytes(
                canonical_json(normalized).encode("utf-8")
            ),
            "row_count": len(normalized),
            "session_count": len({row["session"] for row in normalized}),
            "point_in_time_data": False,
            "provides_point_in_time_lineage": False,
            "adjustment_status": "unadjusted",
            "limitation": (
                "EQUS.SUMMARY OHLCV-1d records identify the UTC aggregation "
                "interval but do not carry the per-record receipt/publication "
                "timestamp required for historical availability lineage. The "
                "bars are also unadjusted. Receipt-timestamped statistics plus "
                "point-in-time adjustment and security-master evidence are "
                "required before this snapshot can pass the promotion gate."
            ),
        }
        manifest_bytes = canonical_json(manifest).encode("utf-8")
        if raw_path.exists() or manifest_path.exists():
            raise DatabentoSourceError("refusing to overwrite an immutable snapshot")
        os.replace(temporary_raw, raw_path)
        try:
            _atomic_write(manifest_path, manifest_bytes)
        except BaseException:
            raw_path.unlink(missing_ok=True)
            raise
        return DailyBarsSnapshot(
            frames=frames,
            manifest=manifest,
            raw_path=raw_path,
            manifest_path=manifest_path,
        )
    finally:
        temporary_raw.unlink(missing_ok=True)


class DatabentoDailyBarsSource:
    """Honest ``PointInTimeSource`` facade for OHLCV-only snapshots.

    Returning no lineage is intentional.  ``EQUS.SUMMARY`` is useful real
    market data, but its OHLCV record cannot alone satisfy the exact
    ``available_at`` and historical-universe contracts.
    """

    source_id = SOURCE_ID
    provides_point_in_time_lineage = False

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
            "source_version": "databento-python-0.81.0",
            "dataset": DEFAULT_DATASET,
            "schema": DEFAULT_SCHEMA,
            "provides_point_in_time_lineage": "false",
            "adjustment_status": "unadjusted",
            "limitation": (
                "OHLCV-1d alone lacks per-record receipt/publication timestamps "
                "and point-in-time corporate-action/universe sidecars."
            ),
        }
