from __future__ import annotations

import dataclasses
import json

import pytest

from research.analyst_revisions_v2.canonical import (
    CanonicalEvidenceError,
    canonical_json_bytes,
    sha256_bytes,
)
from research.analyst_revisions_v2.contracts import (
    AvailabilityQuality,
    CanonicalSourceEvent,
    DataAvailabilityQuality,
    EventContractError,
    EventState,
    RevisionKind,
    materialize_events_as_of,
    validate_revision_lineage,
)
from research.analyst_revisions_v2.normalization import (
    NormalizationContractError,
    NormalizationProvenance,
    NormalizationRefusal,
    NormalizationResult,
    RefusalReason,
)
from research.analyst_revisions_v2.snapshot import (
    INCOMPLETE_DIAGNOSTIC_STATUS,
    IncompleteDiagnosticSnapshot,
    SnapshotVerificationError,
    VerifiedSnapshot,
    load_snapshot,
    load_verified_snapshot,
    revalidate_verified_snapshot,
)

from ._helpers import (
    CODE_HASH,
    COMMIT,
    CONFIG_HASH,
    EVIDENCE_HASH,
    FIXED_VERIFIED_AT,
    event_for,
    historical_event_for,
    raw_row,
    read_manifest,
    refusal_for,
    result_for,
    verified_snapshot,
    write_manifest,
    write_snapshot,
)


def test_complete_snapshot_authenticates_every_raw_locator(tmp_path):
    root = write_snapshot(
        tmp_path / "snapshot",
        rows_by_year={
            2019: [raw_row(2019, "a")],
            2020: [raw_row(2020, "b"), raw_row(2020, "c")],
        },
        pages_per_year=2,
    )
    snapshot = load_verified_snapshot(root, verified_at=FIXED_VERIFIED_AT)

    assert type(snapshot) is VerifiedSnapshot
    assert snapshot.source_row_count == 3
    assert [partition.year for partition in snapshot.partitions] == [2019, 2020]
    assert len(set(snapshot.source_locators)) == 3
    for row in snapshot.rows:
        page_line = (
            root / row.locator.page_filename
        ).read_bytes().splitlines()[row.locator.row_offset]
        assert row.locator.raw_row_sha256 == sha256_bytes(page_line)
        assert row.locator.snapshot_manifest_sha256 == snapshot.manifest_sha256
        assert row.parsed_record()["event_year"] == row.locator.partition_year
    with pytest.raises(dataclasses.FrozenInstanceError):
        snapshot.rows[0].locator.row_offset = 99


def test_verified_snapshot_cannot_be_replaced_or_token_cloned(tmp_path):
    snapshot = verified_snapshot(tmp_path / "snapshot")
    with pytest.raises(TypeError):
        dataclasses.replace(snapshot, source_row_count=0)

    clone = object.__new__(VerifiedSnapshot)
    for field in dataclasses.fields(snapshot):
        object.__setattr__(clone, field.name, getattr(snapshot, field.name))
    with pytest.raises(SnapshotVerificationError, match="loader-authenticated"):
        revalidate_verified_snapshot(clone)
    with pytest.raises(SnapshotVerificationError, match="loader-authenticated"):
        NormalizationProvenance.create(
            snapshot=clone,
            normalizer_config_sha256=CONFIG_HASH,
            normalizer_code_sha256=CODE_HASH,
            evidence_epoch_id="epoch-1",
            build_recipe_id="recipe-1",
            producing_commit=COMMIT,
        )


def test_every_snapshot_consumer_reloads_bound_manifest_and_pages(tmp_path):
    root = tmp_path / "snapshot"
    snapshot = verified_snapshot(root)
    page = root / snapshot.partitions[0].pages[0].filename
    page.write_bytes(page.read_bytes() + b"{}\n")
    with pytest.raises(SnapshotVerificationError, match="changed|mismatch"):
        NormalizationProvenance.create(
            snapshot=snapshot,
            normalizer_config_sha256=CONFIG_HASH,
            normalizer_code_sha256=CODE_HASH,
            evidence_epoch_id="epoch-1",
            build_recipe_id="recipe-1",
            producing_commit=COMMIT,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "string_boolean",
        "missing_requested_year",
        "reversed_years",
        "wrong_partition_key",
        "unknown_manifest_key",
    ],
)
def test_snapshot_manifest_is_exact_and_complete(tmp_path, mutation):
    root = write_snapshot(
        tmp_path / mutation,
        rows_by_year={2020: [raw_row(2020, "a")]},
    )
    manifest = read_manifest(root)
    if mutation == "string_boolean":
        manifest["complete"] = "true"
    elif mutation == "missing_requested_year":
        manifest["requested_last_year"] = 2021
    elif mutation == "reversed_years":
        manifest["requested_first_year"] = 2021
    elif mutation == "wrong_partition_key":
        manifest["partition_key"] = "year"
    else:
        manifest["unexpected"] = "not allowed"
    write_manifest(root, manifest)

    with pytest.raises(CanonicalEvidenceError):
        load_snapshot(root, verified_at=FIXED_VERIFIED_AT)


@pytest.mark.parametrize(
    "mutation",
    [
        "page_gap",
        "wrong_row_year",
        "page_count",
        "partition_count",
        "total_count",
        "page_hash",
        "unreferenced_page",
    ],
)
def test_snapshot_page_inventory_hashes_and_counts_are_fail_closed(tmp_path, mutation):
    root = write_snapshot(
        tmp_path / mutation,
        rows_by_year={2020: [raw_row(2020, "a")]},
    )
    manifest = read_manifest(root)
    page = manifest["partitions"][0]["pages"][0]
    page_path = root / page["filename"]
    if mutation == "page_gap":
        page["page_number"] = 2
    elif mutation == "wrong_row_year":
        payload = canonical_json_bytes(raw_row(2021, "a"))
        page_path.write_bytes(payload)
        page["sha256"] = sha256_bytes(payload)
    elif mutation == "page_count":
        page["row_count"] = 2
    elif mutation == "partition_count":
        manifest["partitions"][0]["row_count"] = 2
    elif mutation == "total_count":
        manifest["source_row_count"] = 2
    elif mutation == "page_hash":
        page_path.write_bytes(page_path.read_bytes() + canonical_json_bytes(raw_row(2020, "b")))
    else:
        extra = root / "pages" / "year=2020" / "unreferenced.jsonl"
        extra.write_bytes(canonical_json_bytes(raw_row(2020, "extra")))
    write_manifest(root, manifest)

    with pytest.raises(CanonicalEvidenceError):
        load_snapshot(root, verified_at=FIXED_VERIFIED_AT)


def test_snapshot_rejects_noncanonical_and_duplicate_key_json(tmp_path):
    root = write_snapshot(
        tmp_path / "whitespace",
        rows_by_year={2020: [raw_row(2020, "a")]},
    )
    manifest = read_manifest(root)
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    with pytest.raises(CanonicalEvidenceError, match="canonical"):
        load_snapshot(root, verified_at=FIXED_VERIFIED_AT)

    duplicate_root = tmp_path / "duplicate"
    duplicate_root.mkdir()
    (duplicate_root / "manifest.json").write_bytes(
        b'{"schema":"one","schema":"two"}\n'
    )
    with pytest.raises(CanonicalEvidenceError, match="duplicate JSON key"):
        load_snapshot(duplicate_root, verified_at=FIXED_VERIFIED_AT)


def test_snapshot_rejects_nonfinite_nonstandard_json_number(tmp_path):
    root = write_snapshot(
        tmp_path / "overflow",
        rows_by_year={2020: [raw_row(2020, "a")]},
    )
    manifest = read_manifest(root)
    page = manifest["partitions"][0]["pages"][0]
    payload = b'{"event_year":2020,"value":NaN}\n'
    (root / page["filename"]).write_bytes(payload)
    page["sha256"] = sha256_bytes(payload)
    write_manifest(root, manifest)
    with pytest.raises(CanonicalEvidenceError, match="non-finite"):
        load_snapshot(root, verified_at=FIXED_VERIFIED_AT)


def test_zero_row_complete_snapshot_is_not_verified(tmp_path):
    root = write_snapshot(
        tmp_path / "empty",
        rows_by_year={2020: []},
        complete=True,
    )
    with pytest.raises(SnapshotVerificationError, match="zero rows"):
        load_verified_snapshot(root, verified_at=FIXED_VERIFIED_AT)


def test_incomplete_snapshot_is_a_diagnostic_type_never_publishable(tmp_path):
    root = write_snapshot(
        tmp_path / "diagnostic",
        rows_by_year={2020: [raw_row(2020, "a")]},
        complete=False,
    )
    diagnostic = load_snapshot(root, verified_at=FIXED_VERIFIED_AT)
    assert type(diagnostic) is IncompleteDiagnosticSnapshot
    assert diagnostic.status == INCOMPLETE_DIAGNOSTIC_STATUS
    with pytest.raises(SnapshotVerificationError, match="not publishable"):
        load_verified_snapshot(root, verified_at=FIXED_VERIFIED_AT)
    with pytest.raises(NormalizationContractError, match="VerifiedSnapshot"):
        NormalizationProvenance.create(
            snapshot=diagnostic,
            normalizer_config_sha256=CONFIG_HASH,
            normalizer_code_sha256=CODE_HASH,
            evidence_epoch_id="epoch-1",
            build_recipe_id="recipe-1",
            producing_commit=COMMIT,
        )


def test_non_authoritative_event_contract_replays_revision_states(tmp_path):
    snapshot = verified_snapshot(tmp_path / "snapshot", row_count=3)
    original = event_for(snapshot.source_locators[0])
    correction = event_for(
        snapshot.source_locators[1],
        event_version_id="version-1",
        revision_sequence=1,
        supersedes_event_version_id="version-0",
        revision_kind=RevisionKind.CORRECTION,
        event_state=EventState.ACTIVE_CORRECTED,
        public_at="2020-01-03T15:00:00.000000Z",
        available_at="2020-01-03T15:00:00.000000Z",
        ingested_at="2020-01-03T15:01:00.000000Z",
        raw_rating="Strong Buy",
    )
    withdrawal = event_for(
        snapshot.source_locators[2],
        event_version_id="version-2",
        revision_sequence=2,
        supersedes_event_version_id="version-1",
        revision_kind=RevisionKind.WITHDRAWAL,
        event_state=EventState.WITHDRAWN,
        public_at="2020-01-06T15:00:00.000000Z",
        available_at="2020-01-06T15:00:00.000000Z",
        ingested_at="2020-01-06T15:01:00.000000Z",
        normalized_rating=None,
        raw_rating="Withdrawn",
    )
    events = (original, correction, withdrawal)
    validate_revision_lineage(events)
    assert materialize_events_as_of(
        events, as_of="2020-01-02T16:00:00.000000Z"
    ) == ()
    assert materialize_events_as_of(
        events, as_of="2020-01-03T16:00:00.000000Z"
    ) == (original,)
    assert materialize_events_as_of(
        events, as_of="2020-01-06T16:00:00.000000Z"
    ) == (correction,)
    assert materialize_events_as_of(
        events, as_of="2020-01-07T16:00:00.000000Z"
    ) == ()


def test_late_and_equal_time_revisions_never_leak_early(tmp_path):
    snapshot = verified_snapshot(tmp_path / "snapshot", row_count=2)
    original = event_for(snapshot.source_locators[0])
    correction = event_for(
        snapshot.source_locators[1],
        event_version_id="version-1",
        revision_sequence=1,
        supersedes_event_version_id="version-0",
        revision_kind=RevisionKind.CORRECTION,
        event_state=EventState.ACTIVE_CORRECTED,
        public_at="2020-02-01T15:00:00.000000Z",
        available_at="2020-02-01T15:00:00.000000Z",
        ingested_at="2020-02-01T15:00:00.000000Z",
    )
    validate_revision_lineage((original, correction))
    assert materialize_events_as_of(
        (original, correction), as_of="2020-01-31T23:59:59.999999Z"
    ) == (original,)

    equal_time = event_for(
        snapshot.source_locators[1],
        event_version_id="version-1",
        revision_sequence=1,
        supersedes_event_version_id="version-0",
        revision_kind=RevisionKind.CORRECTION,
        event_state=EventState.ACTIVE_CORRECTED,
        public_at=original.public_at,
        available_at=original.available_at,
        ingested_at=original.ingested_at,
    )
    validate_revision_lineage((original, equal_time))
    assert materialize_events_as_of(
        (original, equal_time), as_of="2020-01-03T16:00:00.000000Z"
    ) == (equal_time,)


@pytest.mark.parametrize(
    "public_date,first_session,first_open,eligible_session,eligible_open",
    [
        (
            "2020-01-07",
            "2020-01-08",
            "2020-01-08T14:30:00.000000Z",
            "2020-01-09",
            "2020-01-09T14:30:00.000000Z",
        ),
        (
            "2020-01-10",
            "2020-01-13",
            "2020-01-13T14:30:00.000000Z",
            "2020-01-14",
            "2020-01-14T14:30:00.000000Z",
        ),
        (
            "2020-07-03",
            "2020-07-06",
            "2020-07-06T13:30:00.000000Z",
            "2020-07-07",
            "2020-07-07T13:30:00.000000Z",
        ),
    ],
)
def test_date_only_tuesday_friday_and_holiday_use_literal_two_session_delay(
    tmp_path,
    public_date,
    first_session,
    first_open,
    eligible_session,
    eligible_open,
):
    snapshot = verified_snapshot(tmp_path / "snapshot")
    event = event_for(
        snapshot.source_locators[0],
        public_at=None,
        public_date=public_date,
        available_at=f"{public_date}T23:00:00.000000Z",
        ingested_at=f"{public_date}T23:01:00.000000Z",
    )
    assert event.public_at is None
    assert event.public_date == public_date
    assert event.eligibility_quality is AvailabilityQuality.DATE_ONLY_TWO_SESSION_DELAY
    assert event.eligible_session == eligible_session
    assert event.eligible_at == eligible_open
    assert materialize_events_as_of((event,), as_of=first_open) == ()
    assert materialize_events_as_of((event,), as_of=eligible_open) == (event,)

    with pytest.raises(EventContractError, match="does not match"):
        dataclasses.replace(
            event,
            eligible_session=first_session,
            eligible_at=first_open,
        )


def test_absence_never_synthesizes_a_tombstone(tmp_path):
    snapshot = verified_snapshot(tmp_path / "snapshot")
    original = event_for(snapshot.source_locators[0])
    assert materialize_events_as_of(
        (original,), as_of="2030-01-01T00:00:00.000000Z"
    ) == (original,)


def test_non_authoritative_event_contract_keeps_security_identities_distinct(tmp_path):
    snapshot = verified_snapshot(tmp_path / "snapshot", row_count=3)
    first = event_for(snapshot.source_locators[0], provider_event_id="event-a")
    second = event_for(
        snapshot.source_locators[1],
        provider_event_id="event-b",
        issuer_id="issuer-2",
        security_id="security-2",
        share_class_id="share-class-2",
        historical_ticker="AAA",
    )
    third = event_for(
        snapshot.source_locators[2],
        provider_event_id="event-c",
        event_version_id="version-c",
        issuer_id="issuer-1",
        security_id="security-3",
        share_class_id="share-class-3",
        historical_ticker="AAB",
    )
    events = (first, second, third)
    assert {event.security_id for event in events} == {
        "security-1",
        "security-2",
        "security-3",
    }
    assert first.event_version_id == second.event_version_id


def test_non_authoritative_event_contract_preserves_stable_firm_identity(tmp_path):
    snapshot = verified_snapshot(tmp_path / "snapshot", row_count=2)
    first = event_for(snapshot.source_locators[0], provider_event_id="event-a")
    renamed = dataclasses.replace(
        event_for(snapshot.source_locators[1], provider_event_id="event-b"),
        raw_firm_name="Broker One Capital",
    )
    assert first.raw_firm_name != renamed.raw_firm_name
    assert first.provider_firm_id == renamed.provider_firm_id
    assert first.institution_id == renamed.institution_id


@pytest.mark.parametrize(
    "replacement,match",
    [
        ({"available_at": "2020-01-02T14:59:59.000000Z"}, "public_at"),
        ({"identity_mapping_available_at": "2020-01-03T00:00:00.000000Z"}, "available"),
        ({"ticker_valid_from": "2020-01-03"}, "validity"),
        ({"revision_kind": "original"}, "RevisionKind"),
        ({"availability_quality": DataAvailabilityQuality.CAPTURE_UPPER_BOUND}, "capture_upper_bound"),
    ],
)
def test_event_time_enum_and_mapping_contracts_are_strict(tmp_path, replacement, match):
    snapshot = verified_snapshot(tmp_path / "snapshot")
    event = event_for(snapshot.source_locators[0])
    with pytest.raises(EventContractError, match=match):
        dataclasses.replace(event, **replacement)


def test_event_round_trip_rejects_field_loss_and_unknown_fields(tmp_path):
    snapshot = verified_snapshot(tmp_path / "snapshot")
    event = event_for(snapshot.source_locators[0])
    assert CanonicalSourceEvent.from_record(event.to_record()) == event
    record = event.to_record()
    record["legacy_ticker"] = record["historical_ticker"]
    with pytest.raises(CanonicalEvidenceError, match="keys are not exact"):
        CanonicalSourceEvent.from_record(record)
    with pytest.raises(CanonicalEvidenceError, match="trimmed non-control"):
        dataclasses.replace(event, raw_firm_name="\ud800")


@pytest.mark.parametrize("case", ["gap", "wrong_supersedes", "terminal_successor"])
def test_revision_lineage_rejects_ambiguous_or_impossible_chains(tmp_path, case):
    snapshot = verified_snapshot(
        tmp_path / "snapshot", row_count=3 if case == "terminal_successor" else 2
    )
    first = event_for(snapshot.source_locators[0])
    if case == "gap":
        second = event_for(
            snapshot.source_locators[1],
            event_version_id="version-2",
            revision_sequence=2,
            supersedes_event_version_id="version-0",
            revision_kind=RevisionKind.CORRECTION,
            event_state=EventState.ACTIVE_CORRECTED,
        )
    elif case == "wrong_supersedes":
        second = event_for(
            snapshot.source_locators[1],
            event_version_id="version-1",
            revision_sequence=1,
            supersedes_event_version_id="unrelated-version",
            revision_kind=RevisionKind.CORRECTION,
            event_state=EventState.ACTIVE_CORRECTED,
        )
    else:
        terminal = event_for(
            snapshot.source_locators[1],
            event_version_id="version-1",
            revision_sequence=1,
            supersedes_event_version_id="version-0",
            revision_kind=RevisionKind.TOMBSTONE,
            event_state=EventState.TOMBSTONE,
            normalized_rating=None,
            raw_rating="Deleted",
        )
        second = event_for(
            snapshot.source_locators[2],
            event_version_id="version-2",
            revision_sequence=2,
            supersedes_event_version_id="version-1",
            revision_kind=RevisionKind.CORRECTION,
            event_state=EventState.ACTIVE_CORRECTED,
        )
        with pytest.raises(EventContractError, match="terminal"):
            validate_revision_lineage((first, terminal, second))
        return
    with pytest.raises(EventContractError):
        validate_revision_lineage((first, second))


def test_normalization_has_exactly_one_disposition_per_source_row(tmp_path):
    snapshot = verified_snapshot(
        tmp_path / "snapshot", row_count=2, refusal_row_indices=frozenset({0, 1})
    )
    refusals = tuple(refusal_for(locator) for locator in snapshot.source_locators)
    result = result_for(snapshot, events=(), refusals=refusals)
    assert len(result.events) + len(result.refusals) == snapshot.source_row_count


def test_refusal_digest_and_type_cannot_be_fabricated_to_erase_a_row(tmp_path):
    snapshot = verified_snapshot(
        tmp_path / "snapshot", refusal_row_indices=frozenset({0})
    )
    locator = snapshot.source_locators[0]
    with pytest.raises(NormalizationContractError, match="deterministically bound"):
        NormalizationRefusal.create(
            source_locator=locator,
            reason=RefusalReason.MISSING_IDENTITY_MAPPING,
            evidence_sha256=EVIDENCE_HASH,
            normalizer_config_sha256=CONFIG_HASH,
            normalizer_code_sha256=CODE_HASH,
            producing_commit=COMMIT,
        )
    valid = refusal_for(locator)
    with pytest.raises(TypeError):
        dataclasses.replace(
            valid, reason=RefusalReason.MISSING_AVAILABILITY_EVIDENCE
        )
    wrong_reason = refusal_for(
        locator, reason=RefusalReason.MISSING_AVAILABILITY_EVIDENCE
    )
    with pytest.raises(NormalizationContractError, match="not applicable"):
        result_for(snapshot, events=(), refusals=(wrong_reason,))
    with pytest.raises(
        NormalizationContractError,
        match="accepted canonical events are zero-access",
    ):
        result_for(snapshot, events=(event_for(locator),), refusals=())

    accepted_snapshot = verified_snapshot(tmp_path / "accepted-snapshot")
    fabricated_erasure = refusal_for(accepted_snapshot.source_locators[0])
    with pytest.raises(NormalizationContractError, match="not applicable"):
        result_for(
            accepted_snapshot, events=(), refusals=(fabricated_erasure,)
        )


@pytest.mark.parametrize(
    "mutation",
    ("ids", "times", "mapping", "rating", "analyst", "revision"),
)
def test_arbitrary_canonical_event_fields_are_zero_access_without_raw_derivation(
    tmp_path, mutation
):
    snapshot = verified_snapshot(tmp_path / mutation)
    locator = snapshot.source_locators[0]
    if mutation == "ids":
        event = event_for(locator, provider_event_id="caller-selected-event")
    elif mutation == "times":
        event = event_for(locator, effective_at="2020-01-01T14:00:00.000000Z")
    elif mutation == "mapping":
        event = event_for(locator, issuer_id="caller-selected-issuer")
    elif mutation == "rating":
        event = event_for(locator, raw_rating="Caller Selected Rating")
    elif mutation == "analyst":
        event = dataclasses.replace(
            event_for(locator),
            provider_analyst_id="caller-provider-analyst",
            analyst_id="caller-analyst",
        )
    else:
        event = event_for(
            locator,
            event_version_id="caller-version-1",
            revision_sequence=1,
            supersedes_event_version_id="caller-version-0",
            revision_kind=RevisionKind.CORRECTION,
            event_state=EventState.ACTIVE_CORRECTED,
        )
    with pytest.raises(NormalizationContractError, match="zero-access"):
        result_for(snapshot, events=(event,))


def test_pre_2013_event_cannot_be_accepted_or_laundered_into_a_later_year(tmp_path):
    snapshot = verified_snapshot(tmp_path / "snapshot", event_year=2012)
    early_event = historical_event_for(
        snapshot.source_locators[0], event_year=2012
    )
    with pytest.raises(NormalizationContractError, match="zero-access"):
        result_for(snapshot, events=(early_event,))

    laundered_event = historical_event_for(
        snapshot.source_locators[0], event_year=2013
    )
    with pytest.raises(NormalizationContractError, match="zero-access"):
        result_for(snapshot, events=(laundered_event,))


def test_pre_2013_row_requires_exact_named_refusal_and_2013_event_remains_zero_access(
    tmp_path,
):
    early_snapshot = verified_snapshot(
        tmp_path / "early-snapshot", event_year=2012
    )
    wrong_refusal = refusal_for(early_snapshot.source_locators[0])
    with pytest.raises(NormalizationContractError, match="provider-era refusal"):
        result_for(early_snapshot, events=(), refusals=(wrong_refusal,))

    named_refusal = refusal_for(
        early_snapshot.source_locators[0],
        reason=(
            RefusalReason.PROVIDER_BACKFILL_SEMANTICS_UNVERIFIED_PRE_2013
        ),
    )
    result = result_for(early_snapshot, events=(), refusals=(named_refusal,))
    assert result.refusals == (named_refusal,)

    boundary_snapshot = verified_snapshot(
        tmp_path / "boundary-snapshot", event_year=2013
    )
    boundary_event = historical_event_for(
        boundary_snapshot.source_locators[0], event_year=2013
    )
    with pytest.raises(NormalizationContractError, match="zero-access"):
        result_for(boundary_snapshot, events=(boundary_event,))
    bad_named_refusal = refusal_for(
        boundary_snapshot.source_locators[0],
        reason=(
            RefusalReason.PROVIDER_BACKFILL_SEMANTICS_UNVERIFIED_PRE_2013
        ),
    )
    with pytest.raises(NormalizationContractError, match="post-2013"):
        result_for(
            boundary_snapshot,
            events=(),
            refusals=(bad_named_refusal,),
        )


@pytest.mark.parametrize("case", ["dropped", "duplicate", "event_and_refusal", "extra"])
def test_normalization_rejects_dropped_duplicate_or_extra_rows(tmp_path, case):
    count = 1 if case == "event_and_refusal" else 2
    snapshot = verified_snapshot(
        tmp_path / "snapshot",
        row_count=count,
        refusal_row_indices=frozenset(range(count)),
    )
    first = refusal_for(snapshot.source_locators[0])
    events = ()
    refusals = (first,)
    if case == "duplicate":
        refusals = (first, first)
    elif case == "event_and_refusal":
        events = (event_for(snapshot.source_locators[0]),)
    elif case == "extra":
        extra_locator = dataclasses.replace(snapshot.source_locators[1], row_offset=99)
        refusals = (first, refusal_for(extra_locator))
    with pytest.raises(NormalizationContractError):
        result_for(snapshot, events=events, refusals=refusals)


def test_normalization_rejects_loose_lists_and_provenance_drift(tmp_path):
    snapshot = verified_snapshot(
        tmp_path / "snapshot", refusal_row_indices=frozenset({0})
    )
    refusal = refusal_for(snapshot.source_locators[0])
    valid = result_for(snapshot, events=(), refusals=(refusal,))
    with pytest.raises(NormalizationContractError, match="tuple"):
        NormalizationResult(
            snapshot=snapshot,
            events=[],
            refusals=(refusal,),
            provenance=valid.provenance,
        )

    drifted_refusal = refusal_for(
        snapshot.source_locators[0], config_hash="9" * 64
    )
    with pytest.raises(NormalizationContractError, match="provenance"):
        NormalizationResult(
            snapshot=snapshot,
            events=(),
            refusals=(drifted_refusal,),
            provenance=valid.provenance,
        )

    tampered = dataclasses.replace(valid.provenance, build_recipe_sha256="f" * 64)
    with pytest.raises(NormalizationContractError, match="recipe hash"):
        NormalizationResult(
            snapshot=snapshot,
            events=(),
            refusals=(refusal,),
            provenance=tampered,
        )
