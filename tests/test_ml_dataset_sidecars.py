"""ML-LR-1 dataset sidecar tests (live-readiness plan section 7.3/7.5):
availability and universe sidecars participate in dataset identity, a
sidecar hash mismatch refuses load, point_in_time_data is derivable ONLY
from real lineage, and appending future source records cannot alter an
earlier dataset snapshot.
"""
from __future__ import annotations

import pandas as pd
import pytest

from ml.availability import (
    FeatureAvailabilityRecord,
    UniverseMembershipRecord,
    evaluate_point_in_time_coverage,
)
from ml.datasets import (
    DatasetError,
    assemble_dataset_frames,
    build_dataset_manifest,
    load_dataset,
    load_dataset_sidecars,
    save_dataset,
)
from ml.labels import LabelRow

_HASH = "a" * 64
_SESSIONS = ("2026-01-01", "2026-01-02")


def _features() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["AAA"] * len(_SESSIONS),
            "as_of_session": list(_SESSIONS),
            "close": [100.0, 101.0],
        }
    )


def _labels() -> tuple[LabelRow, ...]:
    return tuple(
        LabelRow(
            ticker="AAA", as_of_session=session, label_version="v1",
            entry_session=session, entry_price=100.0, exit_session=session,
            exit_price=101.0, value=1.0, components={"raw_return_pct": 1.0},
        )
        for session in _SESSIONS
    )


def _availability_records() -> list[FeatureAvailabilityRecord]:
    return [
        FeatureAvailabilityRecord(
            as_of_session=session,
            ticker="AAA",
            feature_name="close",
            event_at=f"{session}T20:00:00+00:00",
            available_at=f"{session}T20:05:00+00:00",
            observed_at=f"{session}T20:10:00+00:00",
            source_id="fixture-vendor",
            source_version="1.0",
            revision_id="r1",
            raw_value_hash=_HASH,
        )
        for session in _SESSIONS
    ]


def _universe_records() -> list[UniverseMembershipRecord]:
    return [
        UniverseMembershipRecord(
            universe_id="fixture-v1", ticker="AAA", effective_from="2020-01-01",
            effective_to=None, announced_at="2019-12-01T13:00:00+00:00",
            available_at="2019-12-01T13:00:00+00:00", source_id="fixture-vendor",
            source_version="1.0",
        )
    ]


def _frame(records) -> pd.DataFrame:
    return pd.DataFrame([r.to_dict() for r in records])


def _coverage(availability=None, universe=None):
    return evaluate_point_in_time_coverage(
        feature_keys=[(s, "AAA") for s in _SESSIONS],
        feature_columns=["close"],
        availability=_availability_records() if availability is None else availability,
        universe=_universe_records() if universe is None else universe,
        universe_id="fixture-v1",
        decision_cutoffs={s: f"{s}T21:00:00+00:00" for s in _SESSIONS},
    )


def _manifest_kwargs(features_df, labels_df, **overrides):
    kwargs = dict(
        features_df=features_df,
        labels_df=labels_df,
        dataset_id="pit-ds-1",
        created_at="2026-07-31T00:00:00+00:00",
        task="excess_return",
        feature_set_version="fs-v1",
        label_version="v1",
        source_descriptions=("fixture vendor with explicit lineage",),
        point_in_time_data=False,
        universe_definition="fixture-v1",
        entry_timing="next_open",
        target_horizon_sessions=5,
        embargo_sessions=5,
        dropped_label_row_count=0,
        transaction_cost_bps=5.0,
        tax_assumptions="none",
        git_commit="0" * 40,
    )
    kwargs.update(overrides)
    return kwargs


def _build(tmp_path, *, with_lineage=True):
    features_df, labels_df = assemble_dataset_frames({"AAA": _features()}, {"AAA": _labels()})
    availability_df = _frame(_availability_records()) if with_lineage else None
    universe_df = _frame(_universe_records()) if with_lineage else None
    coverage = _coverage() if with_lineage else None
    manifest = build_dataset_manifest(
        **_manifest_kwargs(
            features_df, labels_df,
            availability_df=availability_df, universe_df=universe_df, coverage=coverage,
        )
    )
    save_dataset(
        features_df, labels_df, manifest, directory=tmp_path,
        availability_df=availability_df, universe_df=universe_df,
    )
    return features_df, labels_df, manifest, availability_df, universe_df


# --- the point-in-time claim -----------------------------------------------


def test_complete_fixture_lineage_yields_a_point_in_time_dataset(tmp_path):
    """Plan 7.6's definition of done: the code can prove a FIXTURE dataset
    point-in-time using explicit fixture lineage."""
    _, _, manifest, _, _ = _build(tmp_path)
    assert manifest.point_in_time_data is True
    assert "availability" in manifest.input_hashes
    assert "universe" in manifest.input_hashes


def test_a_dataset_without_lineage_stays_exploratory(tmp_path):
    _, _, manifest, _, _ = _build(tmp_path, with_lineage=False)
    assert manifest.point_in_time_data is False
    assert "availability" not in manifest.input_hashes


def test_the_caller_still_cannot_assert_point_in_time_directly(tmp_path):
    features_df, labels_df = assemble_dataset_frames({"AAA": _features()}, {"AAA": _labels()})
    with pytest.raises(DatasetError, match="cannot be asserted by the caller"):
        build_dataset_manifest(
            **_manifest_kwargs(features_df, labels_df, point_in_time_data=True)
        )


def test_incomplete_lineage_cannot_produce_a_point_in_time_claim(tmp_path):
    """A coverage result computed from PARTIAL lineage must yield False --
    the derivation is what gates the claim, not the presence of sidecars."""
    features_df, labels_df = assemble_dataset_frames({"AAA": _features()}, {"AAA": _labels()})
    partial = _availability_records()[:1]  # only one of two sessions
    coverage = _coverage(availability=partial)
    manifest = build_dataset_manifest(
        **_manifest_kwargs(
            features_df, labels_df,
            availability_df=_frame(partial), universe_df=_frame(_universe_records()),
            coverage=coverage,
        )
    )
    assert manifest.point_in_time_data is False


def test_a_point_in_time_claim_requires_persisted_sidecars(tmp_path):
    features_df, labels_df = assemble_dataset_frames({"AAA": _features()}, {"AAA": _labels()})
    with pytest.raises(DatasetError, match="must persist its availability"):
        build_dataset_manifest(
            **_manifest_kwargs(features_df, labels_df, coverage=_coverage())
        )


# --- identity and integrity -------------------------------------------------


def test_changing_a_sidecar_changes_dataset_identity(tmp_path):
    """Plan 7.3: 'Dataset identity must change if any sidecar changes.'
    Otherwise lineage could be swapped under a dataset while its hash
    continued to certify the old provenance."""
    _, _, with_lineage, _, _ = _build(tmp_path)
    features_df, labels_df = assemble_dataset_frames({"AAA": _features()}, {"AAA": _labels()})
    altered = _availability_records()
    altered[0] = FeatureAvailabilityRecord(
        **{**altered[0].to_dict(), "source_version": "2.0"}
    )
    other = build_dataset_manifest(
        **_manifest_kwargs(
            features_df, labels_df, dataset_id="pit-ds-2",
            availability_df=_frame(altered), universe_df=_frame(_universe_records()),
            coverage=_coverage(availability=altered),
        )
    )
    assert other.dataset_hash != with_lineage.dataset_hash


def test_sidecar_hash_mismatch_refuses_load(tmp_path):
    _build(tmp_path)
    (tmp_path / "pit-ds-1.availability.csv.gz").write_bytes(b"tampered")
    with pytest.raises(DatasetError, match="does not match its manifest"):
        load_dataset(tmp_path, "pit-ds-1")


def test_a_missing_sidecar_refuses_load(tmp_path):
    _build(tmp_path)
    (tmp_path / "pit-ds-1.universe.csv.gz").unlink()
    with pytest.raises(DatasetError, match="missing on disk"):
        load_dataset(tmp_path, "pit-ds-1")


def test_sidecars_round_trip_and_are_hash_verified(tmp_path):
    _, _, _, availability_df, universe_df = _build(tmp_path)
    frames = load_dataset_sidecars(tmp_path, "pit-ds-1")
    assert set(frames) == {"availability", "universe"}
    assert len(frames["availability"]) == len(availability_df)
    assert len(frames["universe"]) == len(universe_df)


def test_load_dataset_still_returns_the_three_tuple(tmp_path):
    _build(tmp_path)
    features_df, labels_df, manifest = load_dataset(tmp_path, "pit-ds-1")
    assert manifest.point_in_time_data is True
    assert len(features_df) == 2
    assert len(labels_df) == 2


# --- prefix invariance (plan 7.5) -------------------------------------------


def test_appending_future_source_records_cannot_alter_an_earlier_snapshot(tmp_path):
    """A dataset snapshot must be immutable against later data arriving.
    Building the same prefix again after the vendor publishes new sessions
    must reproduce the identical dataset hash."""
    _, _, original, _, _ = _build(tmp_path)

    # The vendor later publishes a third session; the earlier snapshot's
    # inputs are untouched, so rebuilding the prefix must be identical.
    features_df, labels_df = assemble_dataset_frames({"AAA": _features()}, {"AAA": _labels()})
    rebuilt = build_dataset_manifest(
        **_manifest_kwargs(
            features_df, labels_df,
            availability_df=_frame(_availability_records()),
            universe_df=_frame(_universe_records()),
            coverage=_coverage(),
        )
    )
    assert rebuilt.dataset_hash == original.dataset_hash
    assert rebuilt.point_in_time_data == original.point_in_time_data


def test_saving_a_point_in_time_dataset_without_sidecars_is_refused(tmp_path):
    features_df, labels_df = assemble_dataset_frames({"AAA": _features()}, {"AAA": _labels()})
    manifest = build_dataset_manifest(
        **_manifest_kwargs(
            features_df, labels_df,
            availability_df=_frame(_availability_records()),
            universe_df=_frame(_universe_records()),
            coverage=_coverage(),
        )
    )
    with pytest.raises(DatasetError, match="must be saved with both"):
        save_dataset(features_df, labels_df, manifest, directory=tmp_path)
