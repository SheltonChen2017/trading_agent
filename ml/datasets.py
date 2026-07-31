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

`point_in_time_data` on the resulting DatasetManifest must be supplied by
the caller, not assumed true: ml/features.py's own windowing never looks
ahead (tests/test_ml_features.py's
test_point_in_time_correctness_prefix_is_unaffected_by_appending_future_rows
proves that), but the *source* prices this module is handed may still come
from data/market_data.py's yfinance pipeline, which
docs/ML_IMPLEMENTATION_STRATEGY.md section 3.4 and every other research
entry point in this repo (scripts/run_portfolio_research_report.py) already
flag `point_in_time_data=False` -- auto-adjusted closes retroactively
reflect splits/dividends announced after the fact. This module cannot see
where its input came from, so it does not guess.
"""
from __future__ import annotations

import gzip
import io
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from ml.contracts import DatasetManifest
from ml.hashing import canonical_json, hash_bytes
from ml.labels import LabelRow

REQUIRED_KEY_COLUMNS = ("as_of_session", "ticker")


class DatasetError(ValueError):
    """Feature/label data cannot support an immutable dataset."""


def _require_unique_key(frame: pd.DataFrame, name: str) -> None:
    missing = [c for c in REQUIRED_KEY_COLUMNS if c not in frame.columns]
    if missing:
        raise DatasetError(f"{name} is missing key column(s): {missing}")
    if frame.empty:
        raise DatasetError(f"{name} has no rows")
    key = list(zip(frame["as_of_session"], frame["ticker"]))
    if len(key) != len(set(key)):
        raise DatasetError(f"{name} has duplicate (as_of_session, ticker) rows")


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

    features_df = pd.concat(
        [frame for frame in features_by_ticker.values()], ignore_index=True
    )
    _require_unique_key(features_df, "features")

    label_records = [
        row.to_dict() for rows in labels_by_ticker.values() for row in rows
    ]
    if not label_records:
        raise DatasetError("labels_by_ticker contained no label rows")
    labels_df = pd.DataFrame.from_records(label_records)
    if "label_version" not in labels_df.columns:
        raise DatasetError("label rows are missing label_version")
    for label_version, group in labels_df.groupby("label_version"):
        _require_unique_key(group, f"labels[{label_version}]")

    return (
        features_df.sort_values(["as_of_session", "ticker"]).reset_index(drop=True),
        labels_df.sort_values(["as_of_session", "ticker"]).reset_index(drop=True),
    )


def join_for_evaluation(
    features_df: pd.DataFrame, labels_df: pd.DataFrame, *, label_version: str
) -> pd.DataFrame:
    """Explicit, evaluation-time-only join by (as_of_session, ticker) for
    exactly one label version. Never called automatically by this module."""
    subset = labels_df[labels_df["label_version"] == label_version]
    if subset.empty:
        raise DatasetError(f"no label rows found for label_version={label_version!r}")
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
    return gzip.compress(frame.to_csv(index=False).encode("utf-8"))


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
    transaction_cost_bps: float,
    tax_assumptions: str,
    git_commit: str,
) -> DatasetManifest:
    """Build the DatasetManifest describing `features_df`/`labels_df` as
    they exist right now -- callers must construct this immediately before
    persisting, not lazily, so `dataset_hash` cannot drift from the frames
    it claims to describe."""
    sessions = features_df["as_of_session"]
    input_hashes = {
        "features": hash_bytes(_serialize_frame_to_csv_gz(features_df)),
        "labels": hash_bytes(_serialize_frame_to_csv_gz(labels_df)),
    }
    dataset_hash = hash_bytes(canonical_json(input_hashes).encode("utf-8"))
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


def save_dataset(
    features_df: pd.DataFrame,
    labels_df: pd.DataFrame,
    manifest: DatasetManifest,
    *,
    directory: Path,
) -> dict[str, str]:
    """Atomically write features.csv.gz, labels.csv.gz, and manifest.json
    into `directory`, all named after `manifest.dataset_id` so a directory
    can hold more than one dataset. Returns the three file paths written."""
    directory = Path(directory)
    features_bytes = _serialize_frame_to_csv_gz(features_df)
    labels_bytes = _serialize_frame_to_csv_gz(labels_df)
    actual_hashes = {
        "features": hash_bytes(features_bytes),
        "labels": hash_bytes(labels_bytes),
    }
    if actual_hashes != dict(manifest.input_hashes):
        raise DatasetError(
            "manifest.input_hashes does not match the frames being saved -- "
            "did the frames change after build_dataset_manifest() was called? "
            "Build the manifest immediately before saving, from the exact "
            "frames being persisted."
        )
    manifest_bytes = canonical_json(manifest.to_dict()).encode("utf-8")

    features_name = f"{manifest.dataset_id}.features.csv.gz"
    labels_name = f"{manifest.dataset_id}.labels.csv.gz"
    manifest_name = f"{manifest.dataset_id}.manifest.json"

    _atomic_write_bytes(directory, features_name, features_bytes)
    _atomic_write_bytes(directory, labels_name, labels_bytes)
    _atomic_write_bytes(directory, manifest_name, manifest_bytes)
    return {
        "features": str(directory / features_name),
        "labels": str(directory / labels_name),
        "manifest": str(directory / manifest_name),
    }


def load_dataset(
    directory: Path, dataset_id: str
) -> tuple[pd.DataFrame, pd.DataFrame, DatasetManifest]:
    """Load a dataset previously written by save_dataset(), verifying the
    on-disk frames still hash to what the manifest claims before returning
    them -- a silently edited CSV must not be trusted."""
    directory = Path(directory)
    manifest_path = directory / f"{dataset_id}.manifest.json"
    features_path = directory / f"{dataset_id}.features.csv.gz"
    labels_path = directory / f"{dataset_id}.labels.csv.gz"

    manifest = DatasetManifest.from_dict(
        json.loads(manifest_path.read_text(encoding="utf-8"))
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
    if actual_hashes != dict(manifest.input_hashes):
        raise DatasetError(
            f"dataset {dataset_id!r} on disk does not match its manifest's "
            "recorded content hashes -- refusing to load"
        )

    features_df = pd.read_csv(io.StringIO(gzip.decompress(features_bytes).decode("utf-8")))
    labels_df = pd.read_csv(io.StringIO(gzip.decompress(labels_bytes).decode("utf-8")))
    return features_df, labels_df, manifest
