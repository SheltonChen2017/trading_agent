"""Tests for ml/datasets.py -- unique-key enforcement, the
features/labels-stay-separate rule, and hash-verified atomic persistence."""
from __future__ import annotations

import pandas as pd
import pytest

from ml.datasets import (
    DatasetError,
    assemble_dataset_frames,
    build_dataset_manifest,
    join_for_evaluation,
    load_dataset,
    save_dataset,
)
from ml.labels import LabelRow


def _features_frame(ticker: str, sessions: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": [ticker] * len(sessions),
            "as_of_session": sessions,
            "return_1d_pct": [0.1 * i for i in range(len(sessions))],
        }
    )


def _label_rows(ticker: str, sessions: list[str], label_version: str) -> tuple[LabelRow, ...]:
    return tuple(
        LabelRow(
            ticker=ticker,
            as_of_session=session,
            label_version=label_version,
            entry_session=session,
            entry_price=100.0,
            exit_session=session,
            exit_price=101.0,
            value=1.0,
            components={"raw_return_pct": 1.0},
        )
        for session in sessions
    )


def _sessions(n: int) -> list[str]:
    return [f"2026-01-{day:02d}" for day in range(1, n + 1)]


def test_assemble_dataset_frames_basic_success():
    sessions = _sessions(5)
    features_by_ticker = {
        "AAA": _features_frame("AAA", sessions),
        "BBB": _features_frame("BBB", sessions),
    }
    labels_by_ticker = {
        "AAA": _label_rows("AAA", sessions, "forward_excess_return_20d_next_open_v1"),
        "BBB": _label_rows("BBB", sessions, "forward_excess_return_20d_next_open_v1"),
    }

    features_df, labels_df = assemble_dataset_frames(features_by_ticker, labels_by_ticker)

    assert len(features_df) == 10
    assert len(labels_df) == 10
    assert set(features_df["ticker"]) == {"AAA", "BBB"}


def test_assemble_dataset_frames_rejects_duplicate_feature_key():
    sessions = _sessions(3)
    dup = pd.concat([_features_frame("AAA", sessions), _features_frame("AAA", sessions[:1])])
    with pytest.raises(DatasetError, match="duplicate"):
        assemble_dataset_frames(
            {"AAA": dup},
            {"AAA": _label_rows("AAA", sessions, "v1")},
        )


def test_assemble_dataset_frames_rejects_duplicate_label_key_within_one_version():
    sessions = _sessions(3)
    rows = _label_rows("AAA", sessions, "v1") + _label_rows("AAA", sessions[:1], "v1")
    with pytest.raises(DatasetError, match="duplicate"):
        assemble_dataset_frames(
            {"AAA": _features_frame("AAA", sessions)},
            {"AAA": rows},
        )


def test_assemble_dataset_frames_allows_two_label_versions_for_the_same_session():
    sessions = _sessions(3)
    rows = _label_rows("AAA", sessions, "v1") + _label_rows("AAA", sessions, "v2")
    features_df, labels_df = assemble_dataset_frames(
        {"AAA": _features_frame("AAA", sessions)},
        {"AAA": rows},
    )
    assert set(labels_df["label_version"]) == {"v1", "v2"}


def test_assemble_dataset_frames_rejects_empty_inputs():
    with pytest.raises(DatasetError, match="no feature frames"):
        assemble_dataset_frames({}, {"AAA": _label_rows("AAA", _sessions(1), "v1")})
    with pytest.raises(DatasetError, match="no label rows"):
        assemble_dataset_frames({"AAA": _features_frame("AAA", _sessions(1))}, {})


def test_join_for_evaluation_joins_by_as_of_session_and_ticker():
    sessions = _sessions(3)
    features_df, labels_df = assemble_dataset_frames(
        {"AAA": _features_frame("AAA", sessions)},
        {"AAA": _label_rows("AAA", sessions, "v1")},
    )
    joined = join_for_evaluation(features_df, labels_df, label_version="v1")
    assert len(joined) == 3
    assert "label_value" in joined.columns
    assert "label_version" not in joined.columns or "label_label_version" in joined.columns


def test_join_for_evaluation_rejects_unknown_label_version():
    sessions = _sessions(3)
    features_df, labels_df = assemble_dataset_frames(
        {"AAA": _features_frame("AAA", sessions)},
        {"AAA": _label_rows("AAA", sessions, "v1")},
    )
    with pytest.raises(DatasetError, match="no label rows"):
        join_for_evaluation(features_df, labels_df, label_version="does-not-exist")


def _manifest_kwargs(features_df, labels_df, **overrides):
    kwargs = dict(
        features_df=features_df,
        labels_df=labels_df,
        dataset_id="ds-test-1",
        created_at="2026-07-31T00:00:00+00:00",
        task="volatility_forecast",
        feature_set_version="fs-v1",
        label_version="v1",
        source_descriptions=("synthetic test fixture",),
        point_in_time_data=False,
        universe_definition="fixed:test",
        entry_timing="next_open",
        target_horizon_sessions=5,
        embargo_sessions=5,
        transaction_cost_bps=5.0,
        tax_assumptions="none",
        git_commit="0" * 40,
    )
    kwargs.update(overrides)
    return kwargs


def test_manifest_and_save_load_round_trip(tmp_path):
    sessions = _sessions(6)
    features_df, labels_df = assemble_dataset_frames(
        {"AAA": _features_frame("AAA", sessions)},
        {"AAA": _label_rows("AAA", sessions, "v1")},
    )
    manifest = build_dataset_manifest(**_manifest_kwargs(features_df, labels_df))

    paths = save_dataset(features_df, labels_df, manifest, directory=tmp_path)
    assert all(p for p in paths.values())

    loaded_features, loaded_labels, loaded_manifest = load_dataset(tmp_path, "ds-test-1")

    assert loaded_manifest == manifest
    pd.testing.assert_frame_equal(loaded_features, features_df)
    # "components" is a dict column -- CSV round-tripping stringifies it
    # (documented in ml/datasets.py's _serialize_frame_to_csv_gz docstring
    # as the reason hashes are computed on raw bytes, not a reloaded
    # DataFrame). Every other column must still match exactly.
    non_lossy_columns = [c for c in labels_df.columns if c != "components"]
    pd.testing.assert_frame_equal(
        loaded_labels[non_lossy_columns].astype(
            {"entry_price": float, "exit_price": float, "value": float}
        ),
        labels_df[non_lossy_columns],
    )
    import ast

    assert (
        loaded_labels["components"].apply(ast.literal_eval).tolist()
        == labels_df["components"].tolist()
    )


def test_save_dataset_refuses_stale_manifest(tmp_path):
    sessions = _sessions(6)
    features_df, labels_df = assemble_dataset_frames(
        {"AAA": _features_frame("AAA", sessions)},
        {"AAA": _label_rows("AAA", sessions, "v1")},
    )
    manifest = build_dataset_manifest(**_manifest_kwargs(features_df, labels_df))

    mutated_features = features_df.copy()
    mutated_features.loc[0, "return_1d_pct"] = 999.0

    with pytest.raises(DatasetError, match="does not match the frames"):
        save_dataset(mutated_features, labels_df, manifest, directory=tmp_path)


def test_load_dataset_refuses_tampered_file_on_disk(tmp_path):
    sessions = _sessions(6)
    features_df, labels_df = assemble_dataset_frames(
        {"AAA": _features_frame("AAA", sessions)},
        {"AAA": _label_rows("AAA", sessions, "v1")},
    )
    manifest = build_dataset_manifest(**_manifest_kwargs(features_df, labels_df))
    save_dataset(features_df, labels_df, manifest, directory=tmp_path)

    (tmp_path / "ds-test-1.features.csv.gz").write_bytes(b"tampered")

    with pytest.raises(DatasetError, match="does not match its manifest"):
        load_dataset(tmp_path, "ds-test-1")


def test_save_dataset_refuses_to_overwrite_with_different_content(tmp_path):
    sessions = _sessions(6)
    features_df, labels_df = assemble_dataset_frames(
        {"AAA": _features_frame("AAA", sessions)},
        {"AAA": _label_rows("AAA", sessions, "v1")},
    )
    manifest = build_dataset_manifest(**_manifest_kwargs(features_df, labels_df))
    save_dataset(features_df, labels_df, manifest, directory=tmp_path)

    other_sessions = _sessions(6)
    other_features, other_labels = assemble_dataset_frames(
        {"BBB": _features_frame("BBB", other_sessions)},
        {"BBB": _label_rows("BBB", other_sessions, "v1")},
    )
    other_manifest = build_dataset_manifest(
        **_manifest_kwargs(other_features, other_labels, dataset_id="ds-test-1")
    )

    with pytest.raises(DatasetError, match="refusing to overwrite"):
        save_dataset(other_features, other_labels, other_manifest, directory=tmp_path)


def test_multiple_datasets_coexist_in_one_directory(tmp_path):
    sessions = _sessions(6)
    features_df, labels_df = assemble_dataset_frames(
        {"AAA": _features_frame("AAA", sessions)},
        {"AAA": _label_rows("AAA", sessions, "v1")},
    )
    manifest_1 = build_dataset_manifest(**_manifest_kwargs(features_df, labels_df, dataset_id="ds-1"))
    manifest_2 = build_dataset_manifest(**_manifest_kwargs(features_df, labels_df, dataset_id="ds-2"))

    save_dataset(features_df, labels_df, manifest_1, directory=tmp_path)
    save_dataset(features_df, labels_df, manifest_2, directory=tmp_path)

    _, _, loaded_1 = load_dataset(tmp_path, "ds-1")
    _, _, loaded_2 = load_dataset(tmp_path, "ds-2")
    assert loaded_1.dataset_id == "ds-1"
    assert loaded_2.dataset_id == "ds-2"
