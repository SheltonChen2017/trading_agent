"""Immutable-vintage, linkage, revision, and refusal tests for SI-1 fixtures."""
from __future__ import annotations

import json
from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import research.short_interest_etf.dataset as dataset_module
from research.short_interest_etf.contracts import recompute_days_to_cover
from research.short_interest_etf.dataset import (
    ShortInterestDatasetError,
    ShortInterestVintage,
    build_identity,
    build_vintage,
    load_synthetic_fixture,
    load_vintage,
    visible_source_snapshots_as_of,
    write_vintage,
)
from research.short_interest_etf.normalize import SnapshotRefusal

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "short_interest_etf"
    / "official_style_v1.json"
)


def _vintage():
    return load_synthetic_fixture(FIXTURE)


def _manifest(vintage, *, accepted: int, refused: int = 0, retrieved_at=None):
    total = accepted + refused
    return replace(
        vintage.manifest,
        requested_record_count=total,
        input_row_count=total,
        accepted_record_count=accepted,
        refusal_count=refused,
        retrieved_at=retrieved_at or vintage.manifest.retrieved_at,
    )


def _with_correction():
    vintage = _vintage()
    original = vintage.snapshots[1]
    correction = replace(
        original,
        source_record_id="synthetic-si-2024-01-31-r2",
        current_short_shares=1250,
        recomputed_days_to_cover=recompute_days_to_cover(
            1250, original.volume_basis.average_daily_share_volume
        ),
        revision_id="r2",
        revision_published_at="2024-02-14T22:00:00Z",
        observed_at="2024-02-14T22:00:00Z",
        supersedes_event_id=original.event_id,
        raw_record_sha256="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    return build_vintage(
        _manifest(
            vintage,
            accepted=3,
            retrieved_at="2024-02-14T22:00:00Z",
        ),
        vintage.release_calendar,
        (*vintage.snapshots, correction),
    )


def _with_prior_correction_visible_at_current_revision():
    vintage = _vintage()
    prior = vintage.snapshots[0]
    current = vintage.snapshots[1]
    corrected_prior = replace(
        prior,
        source_record_id="synthetic-si-2024-01-12-r2",
        current_short_shares=1050,
        recomputed_days_to_cover=recompute_days_to_cover(
            1050, prior.volume_basis.average_daily_share_volume
        ),
        revision_id="r2",
        revision_published_at=current.revision_published_at,
        observed_at=current.revision_published_at,
        supersedes_event_id=prior.event_id,
        raw_record_sha256="ab" * 32,
    )
    current = replace(current, previous_short_shares=1050)
    return build_vintage(
        _manifest(vintage, accepted=3),
        vintage.release_calendar,
        (prior, corrected_prior, current),
    )


def _with_second_security():
    vintage = _vintage()
    second_security_id = "sec-synth-002"
    second_snapshots = []
    for snapshot in vintage.snapshots:
        second_security = replace(
            snapshot.security,
            security_id=second_security_id,
            vendor_security_id="vendor-synth-002",
            ticker="SYN2",
            raw_record_sha256="1a" * 32,
        )
        second_snapshots.append(
            replace(
                snapshot,
                source_record_id=f"{snapshot.source_record_id}-sec2",
                security=second_security,
                volume_basis=replace(
                    snapshot.volume_basis,
                    security_id=second_security_id,
                    raw_record_sha256="1b" * 32,
                ),
                denominator=replace(
                    snapshot.denominator,
                    security_id=second_security_id,
                    raw_record_sha256="1c" * 32,
                ),
                raw_record_sha256="1d" * 32,
            )
        )
    snapshots = (*vintage.snapshots, *second_snapshots)
    return build_vintage(
        replace(
            vintage.manifest,
            requested_record_count=len(snapshots),
            input_row_count=len(snapshots),
            accepted_record_count=len(snapshots),
        ),
        vintage.release_calendar,
        snapshots,
        vintage.refusals,
    )


def test_identity_is_deterministic_under_input_reordering():
    vintage = _vintage()
    reordered = build_vintage(
        vintage.manifest,
        tuple(reversed(vintage.release_calendar)),
        tuple(reversed(vintage.snapshots)),
    )
    assert reordered == vintage
    assert build_identity(reordered) == build_identity(vintage)


def test_indexed_prior_validation_preserves_fixture_identity_and_exact_time_visibility():
    assert build_identity(_vintage())["content_hash"] == (
        "10651715ecb06a2fb4d703efe9ae8008f41b8d83d8b0e7c148600d7887657df5"
    )

    corrected = _with_prior_correction_visible_at_current_revision()
    current = next(
        item for item in corrected.snapshots if item.settlement_date == "2024-01-31"
    )
    assert current.previous_short_shares == 1050

    stale_link = replace(current, previous_short_shares=1000)
    with pytest.raises(ShortInterestDatasetError, match="previous_short_shares"):
        build_vintage(
            corrected.manifest,
            corrected.release_calendar,
            tuple(
                stale_link if item.event_id == current.event_id else item
                for item in corrected.snapshots
            ),
        )


def test_prior_link_validation_builds_one_index_without_settlement_scans(
    monkeypatch,
):
    vintage = _with_second_security()
    real_builder = dataset_module._build_prior_revision_index
    real_group_builder = dataset_module._group_prior_revisions
    real_settlement_builder = dataset_module._build_settlement_ordinal
    real_identity = dataset_module._snapshot_prior_identity
    real_latest = dataset_module._latest_visible_prior
    build_passes = []
    group_work = []
    settlement_builds = []
    prior_index_gets = []
    settlement_ordinal_gets = []
    identity_calls = []
    latest_calls = []
    indexed_snapshot_proxies = []

    class CountingSequence:
        def __init__(self, rows):
            self.rows = tuple(rows)
            self.passes = 0
            self.item_reads = 0

        def __iter__(self):
            self.passes += 1
            for row in self.rows:
                self.item_reads += 1
                yield row

        def __len__(self):
            return len(self.rows)

        def __getitem__(self, index):
            result = self.rows[index]
            self.item_reads += len(result) if isinstance(index, slice) else 1
            return result

    class CountedSettlement:
        hash_calls = 0
        equality_calls = 0

        def __init__(self, value):
            self.value = value

        def __hash__(self):
            type(self).hash_calls += 1
            return hash(self.value)

        def __eq__(self, other):
            type(self).equality_calls += 1
            if isinstance(other, CountedSettlement):
                other = other.value
            return self.value == other

        def __str__(self):
            raise AssertionError("settlement keys were laundered to base strings")

    class CountedSettlementSequence(tuple):
        def __new__(cls, rows):
            return super().__new__(cls, rows)

        def __init__(self, _rows):
            self.passes = 0
            self.iterated_items = 0
            self.indexed_reads = 0

        def __iter__(self):
            self.passes += 1
            for row in tuple.__iter__(self):
                self.iterated_items += 1
                yield row

        def __getitem__(self, index):
            result = tuple.__getitem__(self, index)
            self.indexed_reads += len(result) if isinstance(index, slice) else 1
            return result

        def index(self, *_args, **_kwargs):
            raise AssertionError("release settlements were scanned per snapshot")

    class CountingSnapshotProxy:
        def __init__(self, snapshot):
            self.snapshot = snapshot
            self.attribute_reads = 0

        def __getattr__(self, name):
            self.attribute_reads += 1
            return getattr(self.snapshot, name)

    class CountingIdentity:
        hash_calls = 0
        equality_calls = 0

        def __init__(self, value):
            self.value = value

        def __hash__(self):
            type(self).hash_calls += 1
            return hash(self.value)

        def __eq__(self, other):
            type(self).equality_calls += 1
            if isinstance(other, CountingIdentity):
                other = other.value
            return self.value == other

        def __iter__(self):
            raise AssertionError("prior identities were laundered to base tuples")

    class GetOnlyMapping:
        def __init__(self, values, get_calls):
            self.values = values
            self.get_calls = get_calls

        def get(self, key, default=None):
            self.get_calls.append(key)
            return self.values.get(key, default)

    class ItemsOnlyMapping:
        def __init__(self, values):
            self.values = values
            self.items_calls = 0

        def items(self):
            self.items_calls += 1
            return self.values.items()

    def counted_builder(snapshots):
        counted = CountingSequence(snapshots)
        proxies = tuple(CountingSnapshotProxy(item) for item in counted)
        indexed_snapshot_proxies.extend(proxies)
        result = real_builder(proxies)
        build_passes.append((counted.passes, counted.item_reads))
        return GetOnlyMapping(result, prior_index_gets)

    def counted_group_builder(snapshots):
        counted = CountingSequence(snapshots)
        result = ItemsOnlyMapping(real_group_builder(counted))
        group_work.append((counted.passes, counted.item_reads, result))
        return result

    def counted_settlement_builder(release_settlements):
        settlement_builds.append(release_settlements)
        result = real_settlement_builder(release_settlements)
        assert type(result) is dict
        return GetOnlyMapping(
            result,
            settlement_ordinal_gets,
        )

    def counted_identity(snapshot):
        identity_calls.append(snapshot.event_id)
        return CountingIdentity(real_identity(snapshot))

    def counted_latest(series, cutoff):
        latest_calls.append((series, cutoff))
        return real_latest(series, cutoff)

    monkeypatch.setattr(
        dataset_module,
        "_build_prior_revision_index",
        counted_builder,
    )
    monkeypatch.setattr(
        dataset_module,
        "_snapshot_prior_identity",
        counted_identity,
    )
    monkeypatch.setattr(
        dataset_module,
        "_group_prior_revisions",
        counted_group_builder,
    )
    monkeypatch.setattr(
        dataset_module,
        "_build_settlement_ordinal",
        counted_settlement_builder,
    )
    monkeypatch.setattr(
        dataset_module,
        "_latest_visible_prior",
        counted_latest,
    )
    expected_event_ids = {item.event_id for item in vintage.snapshots}
    expected_prior_queries = sum(
        item.settlement_date != vintage.manifest.settlement_start
        for item in vintage.snapshots
    )
    snapshot_rows = CountingSequence(vintage.snapshots)
    object.__setattr__(vintage, "snapshots", snapshot_rows)
    settlements = CountedSettlementSequence(
        CountedSettlement(item.settlement_date)
        for item in vintage.release_calendar
    )
    vintage._validate_prior_links(
        datetime.fromisoformat(vintage.manifest.settlement_start).date(),
        settlements,
    )
    assert build_passes == [(1, len(vintage.snapshots))]
    assert len(group_work) == 1
    assert group_work[0][:2] == (1, len(vintage.snapshots))
    assert group_work[0][2].items_calls == 1
    assert len(settlement_builds) == 1
    assert settlement_builds[0] is settlements
    assert len(identity_calls) == len(vintage.snapshots)
    assert set(identity_calls) == expected_event_ids
    assert len(latest_calls) == expected_prior_queries
    assert all(series is not None for series, _cutoff in latest_calls)
    assert len(prior_index_gets) == expected_prior_queries
    assert len(settlement_ordinal_gets) == len(vintage.snapshots)
    assert CountingIdentity.equality_calls <= len(vintage.snapshots)
    assert CountingIdentity.hash_calls <= 4 * len(vintage.snapshots)
    assert len(indexed_snapshot_proxies) == len(vintage.snapshots)
    assert sum(item.attribute_reads for item in indexed_snapshot_proxies) <= (
        6 * len(vintage.snapshots)
    )
    # One-pass materialization and the current two-pass traversal are both
    # linear; pin the complexity ceiling without freezing implementation shape.
    assert 0 < snapshot_rows.passes <= 2
    assert snapshot_rows.item_reads <= 2 * len(snapshot_rows)
    assert settlements.passes == 1
    assert settlements.iterated_items == len(settlements)
    assert settlements.indexed_reads <= len(vintage.snapshots)
    assert CountedSettlement.hash_calls <= len(settlements)
    assert CountedSettlement.equality_calls <= 2 * len(vintage.snapshots)


def test_latest_visible_prior_lookup_is_inclusive_and_logarithmic():
    row_count = 4096
    first = datetime(2024, 1, 1, tzinfo=timezone.utc)
    revision_times = tuple(
        first + timedelta(seconds=index) for index in range(row_count)
    )

    class RandomAccessOnlySequence:
        def __init__(self, rows):
            self.rows = tuple(rows)
            self.item_reads = 0

        def __len__(self):
            return len(self.rows)

        def __getitem__(self, index):
            result = self.rows[index]
            self.item_reads += len(result) if isinstance(index, slice) else 1
            return result

        def __iter__(self):
            raise AssertionError("latest-visible lookup scanned revision history")

    counted_times = RandomAccessOnlySequence(revision_times)
    counted_snapshots = RandomAccessOnlySequence(range(row_count))
    series = dataset_module._PriorRevisionSeries(
        revision_times=counted_times,
        snapshots=counted_snapshots,
    )
    assert dataset_module._latest_visible_prior(series, revision_times[-1]) == (
        row_count - 1
    )
    assert counted_times.item_reads <= 16
    assert counted_snapshots.item_reads <= 1

    midpoint = row_count // 2
    counted_times.item_reads = 0
    counted_snapshots.item_reads = 0
    assert dataset_module._latest_visible_prior(
        series,
        revision_times[midpoint],
    ) == midpoint
    assert counted_times.item_reads <= 16
    assert counted_snapshots.item_reads <= 1

    counted_times.item_reads = 0
    counted_snapshots.item_reads = 0
    assert dataset_module._latest_visible_prior(
        series,
        first - timedelta(seconds=1),
    ) is None
    assert counted_times.item_reads <= 16
    assert counted_snapshots.item_reads == 0


def test_manifest_subclass_cannot_serialize_facts_other_than_those_validated():
    vintage = _vintage()
    genuine = vintage.manifest

    class ManifestSubclass(type(genuine)):
        def to_payload(self):
            return {**super().to_payload(), "snapshot_name": "tampered-after-validation"}

    impostor = ManifestSubclass(
        **{field.name: getattr(genuine, field.name) for field in fields(genuine)}
    )
    assert impostor.snapshot_name == genuine.snapshot_name
    assert impostor.to_payload()["snapshot_name"] != genuine.snapshot_name

    with pytest.raises(ShortInterestDatasetError, match="exact CollectionManifest"):
        build_vintage(
            impostor,
            vintage.release_calendar,
            vintage.snapshots,
            vintage.refusals,
        )


def test_release_and_refusal_subclasses_cannot_cross_vintage_boundary():
    vintage = _vintage()
    genuine_release = vintage.release_calendar[0]

    class ReleaseSubclass(type(genuine_release)):
        pass

    release_impostor = ReleaseSubclass(
        **{
            field.name: getattr(genuine_release, field.name)
            for field in fields(genuine_release)
        }
    )
    with pytest.raises(ShortInterestDatasetError, match="exact ReleaseCalendarEntry"):
        build_vintage(
            vintage.manifest,
            (release_impostor, *vintage.release_calendar[1:]),
            vintage.snapshots,
        )

    genuine_refusal = SnapshotRefusal(
        source_record_id="synthetic-refusal",
        settlement_date=None,
        reason="synthetic_reason",
        detail="synthetic detail",
    )

    class RefusalSubclass(type(genuine_refusal)):
        pass

    refusal_impostor = RefusalSubclass(
        **{
            field.name: getattr(genuine_refusal, field.name)
            for field in fields(genuine_refusal)
        }
    )
    with pytest.raises(ShortInterestDatasetError, match="exact SnapshotRefusal"):
        build_vintage(
            _manifest(vintage, accepted=2, refused=1),
            vintage.release_calendar,
            vintage.snapshots,
            (refusal_impostor,),
        )


@pytest.mark.parametrize(
    "field_name",
    ["release_calendar", "snapshots", "refusals"],
)
def test_vintage_container_must_be_an_exact_tuple(field_name):
    vintage = _vintage()

    class TupleSubclass(tuple):
        pass

    with pytest.raises(ShortInterestDatasetError, match=field_name):
        ShortInterestVintage(
            manifest=vintage.manifest,
            release_calendar=(
                TupleSubclass(vintage.release_calendar)
                if field_name == "release_calendar"
                else vintage.release_calendar
            ),
            snapshots=(
                TupleSubclass(vintage.snapshots)
                if field_name == "snapshots"
                else vintage.snapshots
            ),
            refusals=(
                TupleSubclass(vintage.refusals)
                if field_name == "refusals"
                else vintage.refusals
            ),
        )


def test_immutable_write_exact_retry_and_authenticated_round_trip(tmp_path):
    vintage = _vintage()
    identity = write_vintage(vintage, tmp_path)
    assert write_vintage(vintage, tmp_path) == identity
    loaded = load_vintage(tmp_path / identity["dataset_id"])
    assert loaded == vintage
    assert build_identity(loaded) == identity


def test_existing_different_bytes_are_never_overwritten(tmp_path):
    vintage = _vintage()
    identity = write_vintage(vintage, tmp_path)
    dataset_dir = tmp_path / identity["dataset_id"]
    snapshots_path = dataset_dir / "snapshots.jsonl"
    snapshots_path.write_bytes(b"squatted immutable path\n")
    with pytest.raises(ShortInterestDatasetError, match="immutable vintage conflict"):
        write_vintage(vintage, tmp_path)
    assert snapshots_path.read_bytes() == b"squatted immutable path\n"


def test_writer_refuses_pre_squatted_unknown_sidecar(tmp_path):
    vintage = _vintage()
    identity = build_identity(vintage)
    target = tmp_path / identity["dataset_id"]
    target.mkdir()
    (target / "outcomes.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ShortInterestDatasetError, match="unauthorized files"):
        write_vintage(vintage, tmp_path)
    assert {item.name for item in target.iterdir()} == {"outcomes.json"}


def test_tampered_or_partial_vintage_refuses_on_load(tmp_path):
    vintage = _vintage()
    identity = write_vintage(vintage, tmp_path)
    dataset_dir = tmp_path / identity["dataset_id"]
    (dataset_dir / "release_calendar.jsonl").write_bytes(b"{}\n")
    with pytest.raises(ShortInterestDatasetError, match="does not match"):
        load_vintage(dataset_dir)

    other_root = tmp_path / "partial"
    other_identity = write_vintage(vintage, other_root)
    other_dir = other_root / other_identity["dataset_id"]
    (other_dir / "refusals.jsonl").unlink()
    with pytest.raises(ShortInterestDatasetError, match="file set mismatch"):
        load_vintage(other_dir)


def test_identity_reformat_and_unknown_sidecars_are_refused(tmp_path):
    vintage = _vintage()
    identity = write_vintage(vintage, tmp_path)
    dataset_dir = tmp_path / identity["dataset_id"]
    identity_path = dataset_dir / "dataset.json"
    parsed = json.loads(identity_path.read_text(encoding="utf-8"))
    identity_path.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
    with pytest.raises(ShortInterestDatasetError, match="not canonical"):
        load_vintage(dataset_dir)

    other_root = tmp_path / "sidecar"
    other_identity = write_vintage(vintage, other_root)
    other_dir = other_root / other_identity["dataset_id"]
    (other_dir / "outcomes.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ShortInterestDatasetError, match="unknown=.*outcomes"):
        load_vintage(other_dir)


def test_fixture_source_body_hash_detects_hand_edits(tmp_path):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["snapshot_rows"][0]["current_short_shares"] = 1001
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ShortInterestDatasetError, match="raw_artifact_sha256"):
        load_synthetic_fixture(path)


def test_missing_prior_snapshot_inside_manifest_window_is_refused():
    vintage = _vintage()
    with pytest.raises(ShortInterestDatasetError, match="missing prior snapshot"):
        build_vintage(
            _manifest(vintage, accepted=1),
            vintage.release_calendar,
            (vintage.snapshots[1],),
        )


def test_later_snapshot_cannot_fake_a_pre_window_warmup_link():
    vintage = _vintage()
    evasion = replace(
        vintage.snapshots[1],
        previous_settlement_date="2023-12-29",
        previous_short_shares=777,
    )
    with pytest.raises(ShortInterestDatasetError, match="immediately preceding"):
        build_vintage(
            vintage.manifest,
            vintage.release_calendar,
            (vintage.snapshots[0], evasion),
        )


def test_omitted_first_row_plus_backdated_prior_cannot_fake_warmup():
    vintage = _vintage()
    evasion = replace(
        vintage.snapshots[1],
        previous_settlement_date="2023-12-29",
        previous_short_shares=777,
    )
    with pytest.raises(ShortInterestDatasetError, match="release-calendar settlement"):
        build_vintage(
            _manifest(vintage, accepted=1),
            vintage.release_calendar,
            (evasion,),
        )


def test_omitted_intermediate_release_cycle_cannot_become_multi_period_delta():
    vintage = _vintage()
    middle_release = replace(
        vintage.release_calendar[0],
        settlement_date="2024-01-22",
        filing_deadline_date="2024-01-25",
        public_release_date="2024-01-29",
        public_release_at="2024-01-29T21:00:00Z",
        observed_at="2024-01-29T22:00:00Z",
    )
    with pytest.raises(
        ShortInterestDatasetError, match="release-calendar settlement"
    ):
        build_vintage(
            vintage.manifest,
            (*vintage.release_calendar, middle_release),
            vintage.snapshots,
        )


def test_ticker_reuse_cannot_merge_two_stable_security_histories():
    vintage = _vintage()
    first = vintage.snapshots[0]
    other_identity = replace(
        first.security,
        security_id="sec-synth-other",
        vendor_security_id="vendor-synth-other",
        raw_record_sha256="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    )
    wrong_prior = replace(
        first,
        security=other_identity,
        volume_basis=replace(
            first.volume_basis, security_id=other_identity.security_id
        ),
        denominator=replace(
            first.denominator, security_id=other_identity.security_id
        ),
    )
    assert wrong_prior.security.ticker == vintage.snapshots[1].security.ticker
    with pytest.raises(ShortInterestDatasetError, match="ticker is not a join key"):
        build_vintage(
            vintage.manifest,
            vintage.release_calendar,
            (wrong_prior, vintage.snapshots[1]),
        )


def test_ticker_rename_preserves_history_when_stable_identity_matches():
    vintage = _vintage()
    second = vintage.snapshots[1]
    renamed_identity = replace(
        second.security,
        ticker="NEW",
        raw_record_sha256="cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
    )
    renamed = replace(second, security=renamed_identity)
    rebuilt = build_vintage(
        vintage.manifest,
        vintage.release_calendar,
        (vintage.snapshots[0], renamed),
    )
    assert rebuilt.snapshots[1].security.security_id == "sec-synth-001"
    assert rebuilt.snapshots[1].security.ticker == "NEW"


def test_prior_share_value_must_match_latest_visible_prior_revision():
    vintage = _vintage()
    broken = replace(vintage.snapshots[1], previous_short_shares=999)
    with pytest.raises(ShortInterestDatasetError, match="previous_short_shares"):
        build_vintage(
            vintage.manifest,
            vintage.release_calendar,
            (vintage.snapshots[0], broken),
        )


def test_correction_is_append_only_and_as_of_selection_never_backdates_it():
    vintage = _with_correction()
    assert len(vintage.snapshots) == 3
    correction = next(item for item in vintage.snapshots if item.revision_id == "r2")
    original = next(
        item
        for item in vintage.snapshots
        if item.settlement_date == "2024-01-31" and item.revision_id == "r1"
    )
    assert correction.supersedes_event_id == original.event_id
    before_correction_open = visible_source_snapshots_as_of(
        vintage, datetime(2024, 2, 15, 14, 29, 59, tzinfo=timezone.utc)
    )
    at_correction_open = visible_source_snapshots_as_of(
        vintage, datetime(2024, 2, 15, 14, 30, tzinfo=timezone.utc)
    )
    assert next(
        item for item in before_correction_open if item.settlement_date == "2024-01-31"
    ).revision_id == "r1"
    assert next(
        item for item in at_correction_open if item.settlement_date == "2024-01-31"
    ).revision_id == "r2"


def test_revision_overwrite_or_same_time_conflict_is_refused():
    revised = _with_correction()
    correction = next(item for item in revised.snapshots if item.revision_id == "r2")
    first = revised.snapshots[0]
    with pytest.raises(ShortInterestDatasetError, match="first revision"):
        build_vintage(
            _manifest(revised, accepted=2),
            revised.release_calendar,
            (first, correction),
        )

    original = next(item for item in revised.snapshots if item.revision_id == "r1" and item.settlement_date == "2024-01-31")
    same_time = replace(
        correction,
        revision_published_at=original.revision_published_at,
        observed_at=original.observed_at,
    )
    with pytest.raises(ShortInterestDatasetError, match="same-time revisions"):
        build_vintage(
            revised.manifest,
            revised.release_calendar,
            (first, original, same_time),
        )


def test_duplicate_immutable_event_is_refused():
    vintage = _vintage()
    with pytest.raises(ShortInterestDatasetError, match="duplicate immutable event_id"):
        build_vintage(
            _manifest(vintage, accepted=3),
            vintage.release_calendar,
            (*vintage.snapshots, vintage.snapshots[1]),
        )


def test_named_refusals_are_hashed_into_dataset_identity():
    vintage = _vintage()
    refusal = SnapshotRefusal(
        source_record_id="bad-row",
        settlement_date=None,
        reason="invalid_snapshot_contract",
        detail="synthetic malformed row",
    )
    with_refusal = build_vintage(
        _manifest(vintage, accepted=2, refused=1),
        vintage.release_calendar,
        vintage.snapshots,
        (refusal,),
    )
    assert build_identity(with_refusal)["refusal_count"] == 1
    assert build_identity(with_refusal) != build_identity(vintage)


def test_vintage_subclass_cannot_cross_the_storage_or_as_of_boundary(tmp_path):
    """The vintage container itself must be the exact type at both boundaries.

    A subclass can override ``__post_init__`` and skip every canonicalisation
    and type check the genuine contract performs. ``_content`` would then hash
    whatever it was handed, publishing non-canonical bytes under a canonical
    dataset identity, and the as-of view would report snapshots the vintage
    never validated. Nested exact-type rules do not cover the container itself.
    """
    vintage = _vintage()

    class UnvalidatedVintage(type(vintage)):
        def __post_init__(self):  # deliberately skips the real contract
            return None

    impostor = UnvalidatedVintage(
        manifest=vintage.manifest,
        release_calendar=vintage.release_calendar,
        snapshots=tuple(reversed(vintage.snapshots)),
        refusals=vintage.refusals,
    )
    assert isinstance(impostor, type(vintage))
    assert type(impostor) is not type(vintage)

    with pytest.raises(ShortInterestDatasetError, match="exact ShortInterestVintage"):
        build_identity(impostor)
    with pytest.raises(ShortInterestDatasetError, match="exact ShortInterestVintage"):
        write_vintage(impostor, tmp_path / "vintage-out")
    with pytest.raises(ShortInterestDatasetError, match="exact ShortInterestVintage"):
        visible_source_snapshots_as_of(
            impostor, datetime(2024, 2, 14, 15, 0, tzinfo=timezone.utc)
        )
    assert not (tmp_path / "vintage-out").exists(), "refusal must precede any write"
