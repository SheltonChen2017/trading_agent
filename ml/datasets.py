"""Point-in-time dataset assembly and immutable persistence (strategy doc
section 6.1).

Features and labels are kept as two SEPARATE frames and joined only by
`join_for_evaluation()` -- doc 6.4: "Keep labels separate from features and
join only during research evaluation." Nothing in this module merges them
automatically.

Storage: immutable, content-hashed CSV-gzip artifacts plus a JSON
DatasetManifest, kept outside the production SQLite database (doc 6.1).
CSV-gzip rather than Parquet -- the doc requires pinning a Parquet engine
explicitly before using it ("do not rely on an undeclared optional
dependency"), and none is pinned in requirements.txt yet; adding one is a
one-line follow-up, not blocking, if a real dataset's size later demands it.

`point_in_time_data` is never assumed true: ml/features.py's own windowing never looks
ahead (tests/test_ml_features.py's
test_point_in_time_correctness_prefix_is_unaffected_by_appending_future_rows
proves that), but the *source* prices this module is handed may still come
from data/market_data.py's yfinance pipeline, which
docs/ML_IMPLEMENTATION_STRATEGY.md section 3.4 and every other research
entry point in this repo (scripts/run_portfolio_research_report.py) already
flag `point_in_time_data=False` -- auto-adjusted closes retroactively
reflect splits/dividends announced after the fact. Until a per-feature
event/availability/observation lineage sidecar exists, this builder refuses
to claim `point_in_time_data=True` rather than trusting an unauditable flag.
"""
from __future__ import annotations

import gzip
import io
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from ml.contracts import DatasetManifest
from ml.hashing import canonical_json, hash_bytes
from ml.labels import LabelRow

REQUIRED_KEY_COLUMNS = ("as_of_session", "ticker")
_SAFE_DATASET_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class DatasetError(ValueError):
    """Feature/label data cannot support an immutable dataset."""


def _require_safe_dataset_id(dataset_id: str) -> None:
    """Keep an identifier from becoming a path when artifact names are built."""
    if not isinstance(dataset_id, str) or not _SAFE_DATASET_ID.fullmatch(dataset_id):
        raise DatasetError(
            "dataset_id must be 1-128 characters using only letters, numbers, "
            "periods, underscores, and hyphens, and must start with a letter or number"
        )


def _require_unique_key(frame: pd.DataFrame, name: str) -> None:
    missing = [c for c in REQUIRED_KEY_COLUMNS if c not in frame.columns]
    if missing:
        raise DatasetError(f"{name} is missing key column(s): {missing}")
    if frame.empty:
        raise DatasetError(f"{name} has no rows")
    if frame[list(REQUIRED_KEY_COLUMNS)].isna().any().any():
        raise DatasetError(f"{name} has a missing as_of_session or ticker")
    tickers = frame["ticker"]
    if not tickers.map(lambda value: isinstance(value, str) and bool(value.strip())).all():
        raise DatasetError(f"{name} ticker values must be non-empty strings")
    sessions = pd.to_datetime(frame["as_of_session"], format="%Y-%m-%d", errors="coerce")
    if sessions.isna().any():
        raise DatasetError(f"{name} has an invalid as_of_session; expected YYYY-MM-DD")
    canonical_sessions = sessions.dt.strftime("%Y-%m-%d")
    if not canonical_sessions.equals(frame["as_of_session"]):
        raise DatasetError(f"{name} as_of_session values must use canonical YYYY-MM-DD format")
    if frame.duplicated(list(REQUIRED_KEY_COLUMNS)).any():
        raise DatasetError(f"{name} has duplicate (as_of_session, ticker) rows")


def _require_sorted_key(frame: pd.DataFrame, name: str) -> None:
    expected = frame.sort_values(list(REQUIRED_KEY_COLUMNS), kind="stable").index
    if not expected.equals(frame.index):
        raise DatasetError(f"{name} rows must be sorted by as_of_session and ticker")


def _require_single_label_version(
    labels_df: pd.DataFrame, expected_version: str, *, name: str
) -> None:
    if "label_version" not in labels_df.columns:
        raise DatasetError(f"{name} is missing label_version")
    versions = labels_df["label_version"]
    if versions.isna().any() or not versions.map(
        lambda value: isinstance(value, str) and bool(value.strip())
    ).all():
        raise DatasetError(f"{name} has a missing or invalid label_version")
    actual_versions = set(versions)
    if actual_versions != {expected_version}:
        raise DatasetError(
            f"{name} must contain exactly the requested label_version; "
            f"expected {expected_version!r}, found {sorted(actual_versions)!r}"
        )


def _require_label_keys_covered(
    features_df: pd.DataFrame, labels_df: pd.DataFrame, name: str
) -> None:
    feature_keys = pd.MultiIndex.from_frame(features_df[list(REQUIRED_KEY_COLUMNS)])
    label_keys = pd.MultiIndex.from_frame(labels_df[list(REQUIRED_KEY_COLUMNS)])
    missing = label_keys.difference(feature_keys)
    if len(missing):
        sample = tuple(missing[0])
        raise DatasetError(f"{name} has no matching feature row for key {sample!r}")


def assemble_dataset_frames(
    features_by_ticker: Mapping[str, pd.DataFrame],
    labels_by_ticker: Mapping[str, Sequence[LabelRow]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Concatenate per-ticker feature/label output into two frames, each
    enforcing the unique (as_of_session, ticker) key on its own -- does not
    join features to labels (see module docstring)."""
    if not features_by_ticker:
        raise DatasetError("no feature frames supplied")
    if not labels_by_ticker:
        raise DatasetError("no label rows supplied")

    for ticker, frame in features_by_ticker.items():
        _require_unique_key(frame, f"features[{ticker}]")
        if set(frame["ticker"]) != {ticker}:
            raise DatasetError(
                f"features[{ticker}] contains a ticker value that does not match its mapping key"
            )
        if not frame["as_of_session"].is_monotonic_increasing:
            raise DatasetError(f"features[{ticker}] sessions are not sorted ascending")
    features_df = pd.concat(list(features_by_ticker.values()), ignore_index=True)
    _require_unique_key(features_df, "features")

    label_records: list[dict[str, Any]] = []
    for ticker, rows in labels_by_ticker.items():
        for row in rows:
            if not isinstance(row, LabelRow):
                raise DatasetError(f"labels[{ticker}] contains a non-LabelRow value")
            if row.ticker != ticker:
                raise DatasetError(
                    f"labels[{ticker}] contains ticker {row.ticker!r}, which does not match its mapping key"
                )
            label_records.append(row.to_dict())
    if not label_records:
        raise DatasetError("labels_by_ticker contained no label rows")
    labels_df = pd.DataFrame.from_records(label_records)
    if "label_version" not in labels_df.columns:
        raise DatasetError("label rows are missing label_version")
    for label_version, group in labels_df.groupby("label_version"):
        _require_unique_key(group, f"labels[{label_version}]")
        _require_label_keys_covered(features_df, group, f"labels[{label_version}]")

    return (
        features_df.sort_values(["as_of_session", "ticker"]).reset_index(drop=True),
        labels_df.sort_values(["as_of_session", "ticker"]).reset_index(drop=True),
    )


def join_for_evaluation(
    features_df: pd.DataFrame, labels_df: pd.DataFrame, *, label_version: str
) -> pd.DataFrame:
    """Explicit, evaluation-time-only join by (as_of_session, ticker) for
    exactly one label version. Never called automatically by this module."""
    _require_unique_key(features_df, "features")
    if "label_version" not in labels_df.columns:
        raise DatasetError("labels is missing label_version")
    subset = labels_df[labels_df["label_version"] == label_version]
    if subset.empty:
        raise DatasetError(f"no label rows found for label_version={label_version!r}")
    _require_unique_key(subset, f"labels[{label_version}]")
    renamed = subset.add_prefix("label_").rename(
        columns={"label_as_of_session": "as_of_session", "label_ticker": "ticker"}
    )
    merged = features_df.merge(renamed, on=["as_of_session", "ticker"], how="inner")
    if merged.empty:
        raise DatasetError(
            f"joining features to label_version={label_version!r} produced zero rows"
        )
    return merged.sort_values(["as_of_session", "ticker"]).reset_index(drop=True)


def _serialize_frame_to_csv_gz(frame: pd.DataFrame) -> bytes:
    """The one serialization this module ever hashes or persists -- both
    build_dataset_manifest() and save_dataset() call this SAME function, so
    a manifest's recorded hash always matches the bytes actually written.
    Hashing an intermediate in-memory representation (e.g. a DataFrame's
    own .to_json()) instead would silently diverge from the on-disk CSV.gz
    bytes: CSV round-tripping is lossy for dict-typed columns (LabelRow's
    `components`) and can upcast integer dtypes that contained NaN, so a
    hash computed before serialization would almost never match a hash
    recomputed after reloading."""
    # mtime=0 is essential on the repository's supported Python 3.12/3.13
    # runtimes, where gzip.compress() otherwise embeds the current wall-clock
    # time. Without it, an unchanged frame can receive a different content
    # hash whenever manifest construction and saving cross a one-second
    # boundary. Keep this explicit even on interpreters that may later adopt
    # a reproducible default, and if this moves to gzip.GzipFile/gzip.open,
    # preserve the same zero-mtime requirement there as well.
    return gzip.compress(frame.to_csv(index=False).encode("utf-8"), mtime=0)


def _expected_dataset_hash(input_hashes: Mapping[str, str]) -> str:
    return hash_bytes(canonical_json(dict(input_hashes)).encode("utf-8"))


def _validate_manifest_frames(
    features_df: pd.DataFrame,
    labels_df: pd.DataFrame,
    manifest: DatasetManifest,
) -> None:
    _require_safe_dataset_id(manifest.dataset_id)
    _require_unique_key(features_df, "features")
    _require_sorted_key(features_df, "features")
    _require_single_label_version(
        labels_df, manifest.label_version, name="labels"
    )
    _require_unique_key(labels_df, f"labels[{manifest.label_version}]")
    _require_sorted_key(labels_df, f"labels[{manifest.label_version}]")
    _require_label_keys_covered(
        features_df, labels_df, f"labels[{manifest.label_version}]"
    )
    sessions = features_df["as_of_session"]
    expected_metadata = {
        "row_count": len(features_df),
        "distinct_session_count": int(sessions.nunique()),
        "ticker_count": int(features_df["ticker"].nunique()),
        "actual_start_date": str(sessions.min()),
        "actual_end_date": str(sessions.max()),
    }
    for field, expected in expected_metadata.items():
        actual = getattr(manifest, field)
        if actual != expected:
            raise DatasetError(
                f"manifest.{field}={actual!r} does not match features ({expected!r})"
            )
    expected_dataset_hash = _expected_dataset_hash(manifest.input_hashes)
    if manifest.dataset_hash != expected_dataset_hash:
        raise DatasetError("manifest.dataset_hash does not match manifest.input_hashes")


def build_dataset_manifest(
    features_df: pd.DataFrame,
    labels_df: pd.DataFrame,
    *,
    dataset_id: str,
    created_at: str,
    task: str,
    feature_set_version: str,
    label_version: str,
    source_descriptions: Sequence[str],
    point_in_time_data: bool,
    universe_definition: str,
    entry_timing: str,
    target_horizon_sessions: int,
    embargo_sessions: int,
    dropped_label_row_count: int,
    transaction_cost_bps: float,
    tax_assumptions: str,
    git_commit: str,
    availability_df: pd.DataFrame | None = None,
    universe_df: pd.DataFrame | None = None,
    coverage: Any = None,
) -> DatasetManifest:
    """Build the DatasetManifest describing `features_df`/`labels_df` as
    they exist right now -- callers must construct this immediately before
    persisting, not lazily, so `dataset_hash` cannot drift from the frames
    it claims to describe.

    `point_in_time_data` cannot be passed as True (ML-LR-1, plan 7.3: "The
    caller must not be able to set `point_in_time_data=True` directly").
    The only way to reach True is to supply a `coverage` result produced by
    ml/availability.py's `evaluate_point_in_time_coverage()`, which DERIVES
    it from actual lineage and returns the failures when it cannot.
    """
    _require_safe_dataset_id(dataset_id)
    if point_in_time_data:
        raise DatasetError(
            "point_in_time_data cannot be asserted by the caller; supply a "
            "coverage result from ml.availability.evaluate_point_in_time_coverage() "
            "so the claim is derived from real event_at/available_at/observed_at "
            "lineage"
        )
    _require_unique_key(features_df, "features")
    _require_sorted_key(features_df, "features")
    _require_single_label_version(labels_df, label_version, name="labels")
    _require_unique_key(labels_df, f"labels[{label_version}]")
    _require_sorted_key(labels_df, f"labels[{label_version}]")
    _require_label_keys_covered(features_df, labels_df, f"labels[{label_version}]")

    derived_point_in_time = False
    if coverage is not None:
        derived_point_in_time = bool(getattr(coverage, "point_in_time_data", False))
        if derived_point_in_time and (availability_df is None or universe_df is None):
            # A point-in-time claim must be reproducible from persisted
            # sidecars, not merely from a coverage object the caller
            # computed in memory and could have fabricated.
            raise DatasetError(
                "a point-in-time dataset must persist its availability and "
                "universe sidecars"
            )

    sessions = features_df["as_of_session"]
    input_hashes = {
        "features": hash_bytes(_serialize_frame_to_csv_gz(features_df)),
        "labels": hash_bytes(_serialize_frame_to_csv_gz(labels_df)),
    }
    # Sidecars participate in dataset identity (plan 7.3: "Dataset identity
    # must change if any sidecar changes"), so swapping lineage under a
    # dataset produces a different dataset_hash rather than a silent
    # re-interpretation of the same one.
    if availability_df is not None:
        input_hashes["availability"] = hash_bytes(
            _serialize_frame_to_csv_gz(availability_df)
        )
    if universe_df is not None:
        input_hashes["universe"] = hash_bytes(_serialize_frame_to_csv_gz(universe_df))
    dataset_hash = _expected_dataset_hash(input_hashes)
    point_in_time_data = derived_point_in_time
    return DatasetManifest(
        dataset_id=dataset_id,
        created_at=created_at,
        task=task,
        feature_set_version=feature_set_version,
        label_version=label_version,
        source_descriptions=tuple(source_descriptions),
        point_in_time_data=point_in_time_data,
        requested_start_date=str(sessions.min()),
        requested_end_date=str(sessions.max()),
        actual_start_date=str(sessions.min()),
        actual_end_date=str(sessions.max()),
        row_count=len(features_df),
        distinct_session_count=sessions.nunique(),
        ticker_count=features_df["ticker"].nunique(),
        universe_definition=universe_definition,
        entry_timing=entry_timing,
        target_horizon_sessions=target_horizon_sessions,
        embargo_sessions=embargo_sessions,
        dropped_label_row_count=dropped_label_row_count,
        transaction_cost_bps=transaction_cost_bps,
        tax_assumptions=tax_assumptions,
        input_hashes=input_hashes,
        dataset_hash=dataset_hash,
        git_commit=git_commit,
    )


def _atomic_write_bytes(directory: Path, filename: str, data: bytes) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / filename
    if destination.exists():
        if destination.read_bytes() == data:
            return
        raise DatasetError(f"refusing to overwrite immutable dataset file {destination}")
    fd, tmp_name = tempfile.mkstemp(dir=directory, prefix=f".{filename}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if destination.exists():
            if destination.read_bytes() == data:
                tmp_path.unlink(missing_ok=True)
                return
            raise DatasetError(f"refusing to overwrite immutable dataset file {destination}")
        os.replace(tmp_path, destination)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def _preflight_immutable_writes(
    directory: Path, payloads: Mapping[str, bytes]
) -> None:
    """Refuse the whole save before writing any member if one conflicts."""
    for filename, data in payloads.items():
        destination = directory / filename
        if destination.exists() and destination.read_bytes() != data:
            raise DatasetError(f"refusing to overwrite immutable dataset file {destination}")


def save_dataset(
    features_df: pd.DataFrame,
    labels_df: pd.DataFrame,
    manifest: DatasetManifest,
    *,
    directory: Path,
    availability_df: pd.DataFrame | None = None,
    universe_df: pd.DataFrame | None = None,
) -> dict[str, str]:
    """Atomically write features.csv.gz, labels.csv.gz, the optional
    availability/universe sidecars, and manifest.json into `directory`, all
    named after `manifest.dataset_id` so a directory can hold more than one
    dataset. Returns every file path written."""
    directory = Path(directory)
    _validate_manifest_frames(features_df, labels_df, manifest)
    features_bytes = _serialize_frame_to_csv_gz(features_df)
    labels_bytes = _serialize_frame_to_csv_gz(labels_df)
    actual_hashes = {
        "features": hash_bytes(features_bytes),
        "labels": hash_bytes(labels_bytes),
    }
    sidecar_bytes: dict[str, bytes] = {}
    for name, frame in (("availability", availability_df), ("universe", universe_df)):
        if frame is None:
            continue
        data = _serialize_frame_to_csv_gz(frame)
        sidecar_bytes[name] = data
        actual_hashes[name] = hash_bytes(data)
    if manifest.point_in_time_data and set(sidecar_bytes) != {"availability", "universe"}:
        raise DatasetError(
            "a point-in-time dataset must be saved with both its availability "
            "and universe sidecars"
        )
    if actual_hashes != dict(manifest.input_hashes):
        raise DatasetError(
            "manifest.input_hashes does not match the frames being saved -- "
            "did the frames change after build_dataset_manifest() was called? "
            "Build the manifest immediately before saving, from the exact "
            "frames being persisted."
        )
    expected_dataset_hash = _expected_dataset_hash(actual_hashes)
    if manifest.dataset_hash != expected_dataset_hash:
        raise DatasetError("manifest.dataset_hash does not match the frames being saved")
    manifest_bytes = canonical_json(manifest.to_dict()).encode("utf-8")

    features_name = f"{manifest.dataset_id}.features.csv.gz"
    labels_name = f"{manifest.dataset_id}.labels.csv.gz"
    manifest_name = f"{manifest.dataset_id}.manifest.json"

    payloads = {
        features_name: features_bytes,
        labels_name: labels_bytes,
        manifest_name: manifest_bytes,
    }
    written = {
        "features": str(directory / features_name),
        "labels": str(directory / labels_name),
        "manifest": str(directory / manifest_name),
    }
    for name, data in sidecar_bytes.items():
        filename = f"{manifest.dataset_id}.{name}.csv.gz"
        payloads[filename] = data
        written[name] = str(directory / filename)
    _preflight_immutable_writes(directory, payloads)
    for filename, data in payloads.items():
        _atomic_write_bytes(directory, filename, data)
    return written


def load_dataset(
    directory: Path, dataset_id: str
) -> tuple[pd.DataFrame, pd.DataFrame, DatasetManifest]:
    """Load a dataset previously written by save_dataset(), verifying the
    on-disk frames still hash to what the manifest claims before returning
    them -- a silently edited CSV must not be trusted."""
    directory = Path(directory)
    _require_safe_dataset_id(dataset_id)
    manifest_path = directory / f"{dataset_id}.manifest.json"
    features_path = directory / f"{dataset_id}.features.csv.gz"
    labels_path = directory / f"{dataset_id}.labels.csv.gz"

    manifest = DatasetManifest.from_dict(
        json.loads(manifest_path.read_text(encoding="utf-8"))
    )
    if manifest.dataset_id != dataset_id:
        raise DatasetError(
            f"manifest dataset_id {manifest.dataset_id!r} does not match requested {dataset_id!r}"
        )
    features_bytes = features_path.read_bytes()
    labels_bytes = labels_path.read_bytes()

    # Hash the RAW bytes before parsing -- same ordering as
    # ml/artifacts.py's load_model_artifact(): verify identity/integrity on
    # bytes first, only then hand them to a parser. A CSV round-trip is
    # lossy (dict columns, integer-vs-float dtypes), so hashing a
    # reloaded DataFrame instead would essentially never match the hash
    # recorded from the DataFrame that was originally serialized.
    actual_hashes = {
        "features": hash_bytes(features_bytes),
        "labels": hash_bytes(labels_bytes),
    }
    # Sidecars are verified on exactly the same footing as the primary
    # frames: a dataset whose availability lineage was edited after the fact
    # is no more trustworthy than one whose features were.
    # Read and HASH every sidecar first; parse none of them yet. Parsing
    # inside this loop would hand a tampered file to gzip/pandas before the
    # hash comparison below could reject it -- the caller would then see a
    # BadGzipFile traceback instead of the accurate "does not match its
    # manifest" refusal, and integrity checking would depend on the
    # corruption happening to be unparseable. Same bytes-before-parser
    # ordering this function already documents for the primary frames.
    sidecar_bytes: dict[str, bytes] = {}
    for name in ("availability", "universe"):
        if name not in manifest.input_hashes:
            continue
        path = directory / f"{dataset_id}.{name}.csv.gz"
        if not path.exists():
            raise DatasetError(
                f"dataset {dataset_id!r} manifest records a {name} sidecar that is "
                "missing on disk -- refusing to load"
            )
        data = path.read_bytes()
        sidecar_bytes[name] = data
        actual_hashes[name] = hash_bytes(data)
    if actual_hashes != dict(manifest.input_hashes):
        raise DatasetError(
            f"dataset {dataset_id!r} on disk does not match its manifest's "
            "recorded content hashes -- refusing to load"
        )
    if manifest.dataset_hash != _expected_dataset_hash(actual_hashes):
        raise DatasetError(
            f"dataset {dataset_id!r} manifest has an inconsistent dataset_hash -- refusing to load"
        )
    if manifest.point_in_time_data and set(sidecar_bytes) != {"availability", "universe"}:
        raise DatasetError(
            f"dataset {dataset_id!r} claims point_in_time_data but is missing "
            "availability/universe lineage -- refusing to load"
        )

    features_df = pd.read_csv(io.StringIO(gzip.decompress(features_bytes).decode("utf-8")))
    labels_df = pd.read_csv(io.StringIO(gzip.decompress(labels_bytes).decode("utf-8")))
    _validate_manifest_frames(features_df, labels_df, manifest)
    return features_df, labels_df, manifest


def load_dataset_sidecars(
    directory: Path, dataset_id: str
) -> dict[str, pd.DataFrame]:
    """Load the availability/universe sidecars, hash-verified against the
    manifest. Separate from load_dataset() so existing three-tuple callers
    keep working unchanged."""
    directory = Path(directory)
    _require_safe_dataset_id(dataset_id)
    manifest = DatasetManifest.from_dict(
        json.loads((directory / f"{dataset_id}.manifest.json").read_text(encoding="utf-8"))
    )
    frames: dict[str, pd.DataFrame] = {}
    for name in ("availability", "universe"):
        expected = manifest.input_hashes.get(name)
        if expected is None:
            continue
        data = (directory / f"{dataset_id}.{name}.csv.gz").read_bytes()
        if hash_bytes(data) != expected:
            raise DatasetError(
                f"{name} sidecar for {dataset_id!r} does not match its recorded hash"
            )
        frames[name] = pd.read_csv(io.StringIO(gzip.decompress(data).decode("utf-8")))
    return frames
