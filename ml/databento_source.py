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
from ml.contracts import _freeze_json
from ml.hashing import canonical_json, hash_bytes, hash_payload
from ml.shadow import trading_sessions

DATABENTO_API_KEY_ENV = "DATABENTO_API_KEY"
DEFAULT_DATASET = "EQUS.SUMMARY"
DEFAULT_SCHEMA = "ohlcv-1d"
DEFAULT_STYPE_IN = "raw_symbol"
SOURCE_ID = "databento_equities_summary"
SNAPSHOT_SCHEMA_VERSION = "2"
_REQUIRED_BAR_COLUMNS = ("open", "high", "low", "close", "volume", "symbol")


class DatabentoSourceError(ValueError):
    """A Databento request or returned snapshot is unsafe to use."""


class DatabentoSnapshotRetainedError(DatabentoSourceError):
    """Validation rejected a snapshot that was already downloaded and paid for.

    Distinct from the base error so a caller can tell "nothing was purchased"
    apart from "the bytes are on disk and re-downloading would bill again".
    """

    def __init__(self, message: str, *, raw_path: Path, manifest_path: Path) -> None:
        super().__init__(message)
        self.raw_path = raw_path
        self.manifest_path = manifest_path


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
    refusals: tuple[Mapping[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "frames", MappingProxyType(dict(self.frames)))
        object.__setattr__(
            self, "manifest", _freeze_json(dict(self.manifest), path="manifest")
        )
        object.__setattr__(
            self,
            "refusals",
            tuple(MappingProxyType(dict(item)) for item in self.refusals),
        )


def databento_source_version() -> str:
    """The client version that actually produced a snapshot.

    Derived rather than hard-coded: a manifest is immutable and hash-bound,
    so a stale literal would permanently assert a provenance that never
    happened. When the package is absent the snapshot did not come from the
    real client, and the manifest says exactly that instead of naming a
    version nothing here can confirm.
    """
    try:
        import databento
    except ImportError:
        return "databento-python-not-installed"
    version = getattr(databento, "__version__", None)
    if not isinstance(version, str) or not version.strip():
        return "databento-python-unknown-version"
    return f"databento-python-{version.strip()}"


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


@dataclasses.dataclass(frozen=True)
class NormalizedBars:
    """Accepted bars plus every row this adapter refused, and why.

    Refusals are returned rather than raised because a legitimate market
    condition -- a halted name with no volume, a ticker that had not listed
    yet, a delisted ticker with no bars in the window -- must not discard an
    entire paid multi-ticker download.  Structural problems (a response that
    is not what was requested) still raise, because salvaging those would be
    guessing.
    """

    frames: Mapping[str, pd.DataFrame]
    refusals: tuple[Mapping[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "frames", MappingProxyType(dict(self.frames)))
        object.__setattr__(
            self,
            "refusals",
            tuple(MappingProxyType(dict(item)) for item in self.refusals),
        )


def _refusal(ticker: str, session: str, reason: str) -> dict[str, str]:
    return {"ticker": ticker, "session": session, "reason": reason}


def _normalize_daily_frame(
    raw: pd.DataFrame, request: DailyBarsRequest
) -> NormalizedBars:
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

    # Resolved once for the whole request rather than per row: the NYSE
    # calendar is the authority on what a US-equity daily bar may be dated,
    # and a bar dated outside it is the signature of a timestamp-convention
    # error in the block above, not of bad market data.
    sessions = set(
        trading_sessions(
            date.fromisoformat(request.start),
            date.fromisoformat(request.end),
        )
    )

    frames: dict[str, pd.DataFrame] = {}
    refusals: list[Mapping[str, str]] = []
    for ticker in request.tickers:
        frame = working.loc[working["symbol"] == ticker].drop(columns="symbol")
        if frame.empty:
            # A ticker can legitimately have no bars in the window: it had not
            # listed yet, or it was already delisted. Refusing the request
            # would make survivorship-aware universes impossible to fetch.
            refusals.append(
                _refusal(ticker, "", "no bars returned for this ticker in the window")
            )
            continue
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

        keep: list[bool] = []
        for timestamp, row in frame.iterrows():
            session = timestamp.date()
            session_text = session.isoformat()
            reason: str | None = None
            prices = [row["open"], row["high"], row["low"], row["close"]]
            volume = row["volume"]
            if session not in sessions:
                reason = "bar is not dated on an NYSE trading session"
            elif any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                for value in prices
            ):
                reason = "non-finite price"
            elif any(float(value) <= 0 for value in prices):
                # Zero is invalid for a price but valid for volume, so the two
                # are deliberately not checked together.
                reason = "non-positive price"
            elif (
                not isinstance(volume, (int, float))
                or isinstance(volume, bool)
                or not math.isfinite(float(volume))
            ):
                reason = "non-finite volume"
            elif float(volume) < 0:
                reason = "negative volume"
            elif float(volume) == 0:
                reason = "zero volume"
            elif float(volume) % 1 != 0:
                reason = "non-integral volume"
            elif float(row["high"]) < max(
                float(row["open"]), float(row["low"]), float(row["close"])
            ) or float(row["low"]) > min(
                float(row["open"]), float(row["high"]), float(row["close"])
            ):
                reason = "internally inconsistent OHLC values"
            if reason is None:
                keep.append(True)
            else:
                keep.append(False)
                refusals.append(_refusal(ticker, session_text, reason))

        frame = frame.loc[pd.Series(keep, index=frame.index)]
        if frame.empty:
            refusals.append(
                _refusal(ticker, "", "every returned bar for this ticker was refused")
            )
            continue
        frame["volume"] = frame["volume"].astype("int64")
        frames[ticker] = frame

    if not frames:
        raise DatabentoSourceError(
            "no requested ticker produced a usable bar; refusals: "
            f"{[dict(item) for item in refusals[:10]]}"
        )
    return NormalizedBars(frames=frames, refusals=tuple(refusals))


def _materialize_frame(store_or_frame: Any) -> pd.DataFrame:
    """Read the response into pandas.

    Separate from validation because a file-backed ``DBNStore`` holds its
    source path open: the frame must be materialized while the temporary
    file still exists, but validation must happen only after that file has
    been moved to its permanent, already-paid-for location.
    """
    if isinstance(store_or_frame, pd.DataFrame):
        return store_or_frame
    converter = getattr(store_or_frame, "to_df", None)
    if not callable(converter):
        raise DatabentoSourceError("Databento response cannot be converted to pandas")
    try:
        return converter(price_type="float", pretty_ts=True, map_symbols=True)
    except Exception as exc:
        raise DatabentoSourceError(
            f"Databento DBN conversion failed: {type(exc).__name__}: {exc}"
        ) from exc


def normalize_daily_bars(
    store_or_frame: Any, request: DailyBarsRequest
) -> NormalizedBars:
    """Normalize an official ``DBNStore`` (or a test DataFrame) into frames."""
    return _normalize_daily_frame(_materialize_frame(store_or_frame), request)


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


def _close_dbn_store(store: Any) -> None:
    """Release a file-backed DBNStore before moving its source on Windows.

    Databento 0.81.0 exposes the underlying reader but does not give DBNStore
    a close method or context-manager protocol.  ``get_range(path=...)``
    returns a store whose FileDataSource keeps that path open after ``to_df``.
    Closing the data-source reader is therefore required before an atomic
    rename (and before best-effort cleanup on an error path).
    """
    if store is None:
        return
    data_source = getattr(store, "_data_source", None)
    reader = getattr(data_source, "reader", None)
    close = getattr(reader, "close", None)
    if callable(close):
        close()


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
    store = None
    downloaded_artifact_exists = False
    raw_preserved = False
    raw_frame: pd.DataFrame | None = None
    materialization_error: DatabentoSourceError | None = None
    try:
        try:
            store = active_client.timeseries.get_range(
                **request.api_kwargs(), path=temporary_raw
            )
        except Exception as exc:
            downloaded_artifact_exists = (
                temporary_raw.is_file() and temporary_raw.stat().st_size > 0
            )
            raise DatabentoSourceError(
                f"Databento download failed: {type(exc).__name__}: {exc}"
            ) from exc
        downloaded_artifact_exists = temporary_raw.is_file()
        if not temporary_raw.is_file() or temporary_raw.stat().st_size <= 0:
            raise DatabentoSourceError("Databento did not write a non-empty DBN snapshot")
        raw_bytes = temporary_raw.read_bytes()
        if raw_path.exists() or manifest_path.exists():
            raise DatabentoSourceError("refusing to overwrite an immutable snapshot")
        # The download is billable and has already been paid for. Preserve its
        # exact bytes BEFORE even converting DBN to pandas: a client/API/parser
        # mismatch is itself one of the failures for which the operator must
        # not have to purchase the same response again. Copying through the
        # atomic writer avoids renaming Databento's still-open file on Windows.
        _atomic_write(raw_path, raw_bytes)
        raw_preserved = True
        try:
            raw_frame = _materialize_frame(store)
        except DatabentoSourceError as exc:
            materialization_error = exc
    except Exception as exc:
        if downloaded_artifact_exists and not raw_preserved and temporary_raw.exists():
            # Even a local persistence failure must not silently destroy bytes
            # that may already have been billed. The temporary name is surfaced
            # explicitly so an operator can recover it without re-downloading.
            raise DatabentoSnapshotRetainedError(
                f"{exc} — downloaded bytes could not be copied to the permanent "
                f"snapshot path, so they were retained at {temporary_raw}",
                raw_path=temporary_raw,
                manifest_path=manifest_path,
            ) from exc
        raise
    finally:
        try:
            _close_dbn_store(store)
        finally:
            if not downloaded_artifact_exists or raw_preserved:
                temporary_raw.unlink(missing_ok=True)

    base_manifest = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "source_id": SOURCE_ID,
        "source_version": databento_source_version(),
        "request": request.to_dict(),
        "request_hash": request.request_hash,
        "observed_at": observed,
        "estimated_cost_usd": estimate,
        "raw_filename": raw_path.name,
        "raw_sha256": hash_bytes(raw_bytes),
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

    try:
        if materialization_error is not None:
            raise materialization_error
        if raw_frame is None:
            raise DatabentoSourceError("Databento response was not materialized")
        normalized_bars = _normalize_daily_frame(raw_frame, request)
    except Exception as exc:
        rejection_reason = (
            exc
            if isinstance(exc, DatabentoSourceError)
            else DatabentoSourceError(
                f"Databento normalization failed: {type(exc).__name__}: {exc}"
            )
        )
        # A retained snapshot with no manifest would be an unlabeled artifact
        # nobody could later classify, so the rejection is recorded next to it.
        rejection = dict(base_manifest)
        rejection.update(
            {
                "validation_status": "rejected",
                "rejection_reason": str(rejection_reason),
                "normalized_sha256": None,
                "row_count": 0,
                "session_count": 0,
                "refusals": [],
                "refusal_count": 0,
                "non_session_refusal_count": 0,
                "underfilled": True,
            }
        )
        try:
            _atomic_write(manifest_path, canonical_json(rejection).encode("utf-8"))
        except Exception as manifest_exc:
            raise DatabentoSnapshotRetainedError(
                f"{rejection_reason} — the paid raw snapshot was retained at "
                f"{raw_path}, but its rejection manifest could not be written: "
                f"{type(manifest_exc).__name__}: {manifest_exc}",
                raw_path=raw_path,
                manifest_path=manifest_path,
            ) from manifest_exc
        raise DatabentoSnapshotRetainedError(
            f"{rejection_reason} — the paid raw snapshot was retained at {raw_path} and does "
            f"not need to be downloaded again; its rejection manifest is "
            f"{manifest_path}",
            raw_path=raw_path,
            manifest_path=manifest_path,
        ) from rejection_reason

    normalized = _normalized_material(normalized_bars.frames)
    refusals = [dict(item) for item in normalized_bars.refusals]
    manifest = dict(base_manifest)
    manifest.update(
        {
            "validation_status": (
                "accepted_with_refusals" if refusals else "accepted"
            ),
            "rejection_reason": None,
            "normalized_sha256": hash_bytes(canonical_json(normalized).encode("utf-8")),
            "row_count": len(normalized),
            "session_count": len({row["session"] for row in normalized}),
            "refusals": refusals,
            "refusal_count": len(refusals),
            "underfilled": bool(refusals),
            # A large count here means the timestamp convention above is wrong,
            # not that the market data is bad. It is surfaced separately so a
            # systematic off-by-one session shift is visible rather than buried.
            "non_session_refusal_count": sum(
                1
                for item in refusals
                if item["reason"] == "bar is not dated on an NYSE trading session"
            ),
        }
    )
    try:
        _atomic_write(manifest_path, canonical_json(manifest).encode("utf-8"))
    except Exception as exc:
        raise DatabentoSnapshotRetainedError(
            f"validated paid snapshot was retained at {raw_path}, but its "
            f"manifest could not be written: {type(exc).__name__}: {exc}",
            raw_path=raw_path,
            manifest_path=manifest_path,
        ) from exc
    return DailyBarsSnapshot(
        frames=normalized_bars.frames,
        manifest=manifest,
        raw_path=raw_path,
        manifest_path=manifest_path,
        refusals=normalized_bars.refusals,
    )


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
            "source_version": databento_source_version(),
            "dataset": DEFAULT_DATASET,
            "schema": DEFAULT_SCHEMA,
            "provides_point_in_time_lineage": "false",
            "adjustment_status": "unadjusted",
            "limitation": (
                "OHLCV-1d alone lacks per-record receipt/publication timestamps "
                "and point-in-time corporate-action/universe sidecars."
            ),
        }
