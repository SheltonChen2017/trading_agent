"""SI-2A PIT lifecycle, classification, and stock-readiness contracts."""
from __future__ import annotations

import copy
import json
from dataclasses import fields, replace
from pathlib import Path

import pytest

import research.short_interest_etf.dataset as dataset_module
import research.short_interest_etf.pit_eligibility as pit_eligibility_module
from data.hashing import hash_payload
from research.short_interest_etf.contracts import DenominatorKind
from research.short_interest_etf.dataset import (
    build_identity,
    build_vintage,
    load_synthetic_fixture,
)
from research.short_interest_etf.pit_eligibility import (
    CorporateActionIssue,
    PitReferenceBundle,
    PitReferenceError,
    REFUSAL_AMBIGUOUS_CLASSIFICATION,
    REFUSAL_AMBIGUOUS_LIFECYCLE,
    REFUSAL_IDENTITY_NOT_VALID,
    REFUSAL_MISSING_CLASSIFICATION,
    REFUSAL_MISSING_LIFECYCLE,
    REFUSAL_MISSING_PRIOR,
    REFUSAL_NOT_LISTED,
    REFUSAL_STALE_ADV,
    REFUSAL_SUPERSEDED,
    REFUSAL_UNAUDITED_FLOAT,
    REFUSAL_UNRESOLVED_ACTION_PREFIX,
    SectorClassificationObservation,
    build_stock_data_readiness,
    load_synthetic_pit_reference,
    reference_fixture_body_sha256,
)

SOURCE_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "short_interest_etf"
    / "official_style_v1.json"
)
REFERENCE_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "short_interest_etf"
    / "pit_reference_v1.json"
)


def _vintage():
    return load_synthetic_fixture(SOURCE_FIXTURE)


def _references():
    return load_synthetic_pit_reference(REFERENCE_FIXTURE)


def test_reference_manifest_schema_rejects_string_subclass_equality_spoofing():
    manifest = _references().manifest

    class ForgedSchema(str):
        def __eq__(self, other):
            return True

        def __ne__(self, other):
            return False

    with pytest.raises(PitReferenceError, match="schema_version"):
        replace(manifest, schema_version=ForgedSchema("9.9"))


def _reference_bundle(bundle, *, lifecycles=None, classifications=None):
    lifecycle_rows = tuple(
        bundle.lifecycles if lifecycles is None else lifecycles
    )
    classification_rows = tuple(
        bundle.classifications if classifications is None else classifications
    )
    canonical_lifecycles = tuple(
        sorted(
            lifecycle_rows,
            key=lambda item: (
                item.security_id,
                item.effective_date,
                item.available_at,
                item.record_id,
            ),
        )
    )
    canonical_classifications = tuple(
        sorted(
            classification_rows,
            key=lambda item: (
                item.security_id,
                item.valid_from,
                item.available_at,
                item.record_id,
            ),
        )
    )
    manifest = replace(
        bundle.manifest,
        lifecycle_record_count=len(lifecycle_rows),
        classification_record_count=len(classification_rows),
        source_body_sha256=reference_fixture_body_sha256(
            [item.to_payload() for item in canonical_lifecycles],
            [item.to_payload() for item in canonical_classifications],
        ),
    )
    return PitReferenceBundle(manifest, lifecycle_rows, classification_rows)


def _vintage_with_second(second):
    vintage = _vintage()
    return build_vintage(
        vintage.manifest,
        vintage.release_calendar,
        (vintage.snapshots[0], second),
        vintage.refusals,
    )


def test_synthetic_pit_fixture_is_authenticated_and_order_invariant(tmp_path):
    bundle = _references()
    assert bundle.manifest.reference_dataset_id == (
        "synthetic-si-pit-reference-2024-03-02"
    )
    assert len(bundle.lifecycles) == 2
    assert len(bundle.classifications) == 1
    assert bundle.manifest.sha256 == hash_payload(bundle.manifest.to_payload())
    assert bundle.sha256 == hash_payload(bundle.to_payload())
    assert bundle.lifecycles[0].record_id == hash_payload(
        bundle.lifecycles[0].to_payload()
    )
    assert bundle.classifications[0].record_id == hash_payload(
        bundle.classifications[0].to_payload()
    )

    reordered = _reference_bundle(
        bundle,
        lifecycles=tuple(reversed(bundle.lifecycles)),
        classifications=tuple(reversed(bundle.classifications)),
    )
    assert reordered == bundle
    assert reordered.sha256 == bundle.sha256

    extra_classification = replace(
        bundle.classifications[0],
        security_id="sec-synth-other",
        sector_code="HEALTHCARE",
        industry_code="BIOTECH",
        raw_record_sha256="41" * 32,
    )
    two_classifications = _reference_bundle(
        bundle,
        classifications=(bundle.classifications[0], extra_classification),
    )
    reversed_classifications = _reference_bundle(
        bundle,
        classifications=(extra_classification, bundle.classifications[0]),
    )
    assert reversed_classifications == two_classifications
    assert reversed_classifications.sha256 == two_classifications.sha256

    fixture = json.loads(REFERENCE_FIXTURE.read_text(encoding="utf-8"))
    fixture["lifecycle_rows"].reverse()
    reordered_path = tmp_path / "reordered-reference.json"
    reordered_path.write_text(json.dumps(fixture), encoding="utf-8")
    assert load_synthetic_pit_reference(reordered_path) == bundle


def test_every_source_snapshot_receives_an_explicit_readiness_disposition():
    vintage = _vintage()
    references = _references()
    readiness = build_stock_data_readiness(vintage, references)
    assert len(readiness) == 2
    assert readiness[0].settlement_date == "2024-01-12"
    assert readiness[0].ready is False
    assert readiness[0].refusal_reasons == (REFUSAL_MISSING_PRIOR,)
    assert readiness[1].settlement_date == "2024-01-31"
    assert readiness[1].ready is True
    assert readiness[1].refusal_reasons == ()
    assert readiness[1].taxonomy_id == "SYNTHETIC_SECTOR_V1"
    assert readiness[1].sector_code == "TECHNOLOGY"
    assert readiness[1].industry_code == "SOFTWARE"
    assert len({item.sha256 for item in readiness}) == 2
    assert [item.sha256 for item in readiness] == [
        "de3f033099330258e7b29b58c49092fe4e2094d719da453ef027fa96a5c756ee",
        "9a7bb2278cc49b7354a8808c6589075ed09893605227e2a21e1de947106dd272",
    ]
    assert [item.event_id for item in readiness] == [
        item.event_id for item in vintage.snapshots
    ]
    assert [item.security_id for item in readiness] == [
        item.security.security_id for item in vintage.snapshots
    ]
    assert all(
        item.reference_bundle_sha256 == references.sha256 for item in readiness
    )
    assert all(
        item.source_vintage_sha256 == build_identity(vintage)["content_hash"]
        for item in readiness
    )
    for source, disposition in zip(vintage.snapshots, readiness, strict=True):
        assert disposition.settlement_date == source.settlement_date
        assert disposition.security_identity_sha256 == hash_payload(
            source.security.to_payload()
        )
        assert disposition.denominator_sha256 == hash_payload(
            source.denominator.to_payload()
        )
        assert disposition.volume_basis_sha256 == hash_payload(
            source.volume_basis.to_payload()
        )
        assert disposition.lifecycle_record_id == references.lifecycles[0].record_id
        assert (
            disposition.classification_record_id
            == references.classifications[0].record_id
        )
    assert all(item.sha256 == hash_payload(item.to_payload()) for item in readiness)


def test_readiness_builds_each_canonical_index_once_and_uses_no_legacy_scans(
    monkeypatch,
):
    cohort_calls = []
    execution_calls = []
    reference_calls = []
    real_cohort_builder = dataset_module.snapshot_execution_cohort
    real_execution_builder = (
        pit_eligibility_module._snapshot_execution_selection_index
    )
    real_reference_builder = (
        pit_eligibility_module._build_reference_selection_index
    )

    def counted_cohort_builder(snapshot, release):
        cohort_calls.append((snapshot, release))
        return real_cohort_builder(snapshot, release)

    def counted_execution_builder(vintage):
        execution_calls.append(vintage)
        return real_execution_builder(vintage)

    def counted_reference_builder(vintage, references, execution_index):
        reference_calls.append((vintage, references, execution_index))
        return real_reference_builder(vintage, references, execution_index)

    def forbidden_legacy_scan(*_args, **_kwargs):
        raise AssertionError("legacy per-cutoff source scan was called")

    monkeypatch.setattr(
        dataset_module,
        "snapshot_execution_cohort",
        counted_cohort_builder,
    )
    monkeypatch.setattr(
        pit_eligibility_module,
        "_snapshot_execution_selection_index",
        counted_execution_builder,
    )
    monkeypatch.setattr(
        pit_eligibility_module,
        "_build_reference_selection_index",
        counted_reference_builder,
    )
    monkeypatch.setattr(
        dataset_module,
        "visible_source_snapshots_as_of",
        forbidden_legacy_scan,
    )
    monkeypatch.setattr(
        dataset_module,
        "delta_eligible_snapshots_as_of",
        forbidden_legacy_scan,
    )
    monkeypatch.setattr(
        pit_eligibility_module,
        "visible_source_snapshots_as_of",
        forbidden_legacy_scan,
        raising=False,
    )
    monkeypatch.setattr(
        pit_eligibility_module,
        "delta_eligible_snapshots_as_of",
        forbidden_legacy_scan,
        raising=False,
    )
    monkeypatch.setattr(
        pit_eligibility_module,
        "_select_lifecycle",
        forbidden_legacy_scan,
        raising=False,
    )
    monkeypatch.setattr(
        pit_eligibility_module,
        "_select_classification",
        forbidden_legacy_scan,
        raising=False,
    )

    vintage = _vintage()
    references = _references()
    readiness = build_stock_data_readiness(vintage, references)

    assert len(readiness) == len(vintage.snapshots)
    assert len(cohort_calls) == len(vintage.snapshots)
    assert {item[0].event_id for item in cohort_calls} == {
        item.event_id for item in vintage.snapshots
    }
    assert execution_calls == [vintage]
    assert len(reference_calls) == 1
    assert reference_calls[0][:2] == (vintage, references)
    assert set(reference_calls[0][2]) == {
        item.event_id for item in vintage.snapshots
    }


def test_reference_indices_include_exact_open_and_valid_to_boundaries():
    bundle = _references()
    execution_open = "2024-02-13T14:30:00Z"
    lifecycle = replace(
        bundle.lifecycles[0],
        effective_date="2024-02-13",
        available_at=execution_open,
        observed_at=execution_open,
        raw_record_sha256="62" * 32,
    )
    classification = replace(
        bundle.classifications[0],
        valid_from="2024-02-13",
        valid_to="2024-02-13",
        available_at=execution_open,
        observed_at=execution_open,
        raw_record_sha256="63" * 32,
    )
    boundary_bundle = _reference_bundle(
        bundle,
        lifecycles=(lifecycle,),
        classifications=(classification,),
    )

    result = build_stock_data_readiness(_vintage(), boundary_bundle)[1]

    assert result.execution_at == execution_open
    assert result.ready is True
    assert result.lifecycle_record_id == lifecycle.record_id
    assert result.classification_record_id == classification.record_id


def test_readiness_refusals_reject_tuple_subclass_equality_spoofing():
    readiness = build_stock_data_readiness(_vintage(), _references())[0]

    class ForgedReasons(tuple):
        def __eq__(self, other):
            return True

        def __ne__(self, other):
            return False

    with pytest.raises(PitReferenceError, match="exact tuple"):
        replace(
            readiness,
            refusal_reasons=ForgedReasons((REFUSAL_SUPERSEDED,)),
        )


def test_pit_reference_containers_must_be_exact_tuples():
    bundle = _references()

    class TupleSubclass(tuple):
        pass

    with pytest.raises(PitReferenceError, match="unresolved_actions"):
        replace(
            bundle.lifecycles[0],
            unresolved_actions=TupleSubclass(
                bundle.lifecycles[0].unresolved_actions
            ),
        )
    with pytest.raises(PitReferenceError, match="lifecycles"):
        replace(bundle, lifecycles=TupleSubclass(bundle.lifecycles))
    with pytest.raises(PitReferenceError, match="classifications"):
        replace(
            bundle,
            classifications=TupleSubclass(bundle.classifications),
        )


def test_revision_superseded_before_first_open_has_a_distinct_disposition():
    vintage = _vintage()
    original = vintage.snapshots[1]
    correction = replace(
        original,
        source_record_id="synthetic-si-2024-01-31-r2-before-open",
        revision_id="r2",
        revision_published_at="2024-02-13T13:00:00Z",
        observed_at="2024-02-13T13:00:00Z",
        supersedes_event_id=original.event_id,
        raw_record_sha256="9" * 64,
    )
    manifest = replace(
        vintage.manifest,
        requested_record_count=3,
        input_row_count=3,
        accepted_record_count=3,
    )
    corrected_vintage = build_vintage(
        manifest,
        vintage.release_calendar,
        (*vintage.snapshots, correction),
    )
    dispositions = {
        item.event_id: item
        for item in build_stock_data_readiness(corrected_vintage, _references())
    }
    assert dispositions[original.event_id].refusal_reasons == (
        REFUSAL_SUPERSEDED,
    )
    assert dispositions[correction.event_id].ready is True


def test_later_delisting_is_retained_without_backfilling_earlier_eligibility():
    bundle = _references()
    assert any(item.status.value == "delisted" for item in bundle.lifecycles)
    readiness = build_stock_data_readiness(_vintage(), bundle)
    assert readiness[1].ready is True
    assert REFUSAL_NOT_LISTED not in readiness[1].refusal_reasons


def test_security_already_delisted_at_execution_is_named_not_silently_dropped():
    bundle = _references()
    delisted = replace(
        bundle.lifecycles[1],
        effective_date="2024-02-01",
        available_at="2024-02-01T22:00:00Z",
        observed_at="2024-02-01T22:00:00Z",
        raw_record_sha256="d" * 64,
    )
    changed = _reference_bundle(
        bundle, lifecycles=(bundle.lifecycles[0], delisted)
    )
    result = build_stock_data_readiness(_vintage(), changed)[1]
    assert result.ready is False
    assert REFUSAL_NOT_LISTED in result.refusal_reasons


@pytest.mark.parametrize(
    ("issue", "raw_record_sha256"),
    [
        (CorporateActionIssue.MERGER, "5" * 64),
        (CorporateActionIssue.SHARE_CLASS, "6" * 64),
        (CorporateActionIssue.SPLIT, "7" * 64),
        (CorporateActionIssue.TICKER_CHANGE, "8" * 64),
    ],
)
def test_every_unresolved_corporate_action_fails_closed_with_exact_reason(
    issue, raw_record_sha256
):
    bundle = _references()
    active = replace(
        bundle.lifecycles[0],
        unresolved_actions=(issue,),
        raw_record_sha256=raw_record_sha256,
    )
    changed = _reference_bundle(
        bundle, lifecycles=(active, bundle.lifecycles[1])
    )
    result = build_stock_data_readiness(_vintage(), changed)[1]
    assert result.ready is False
    assert (
        f"{REFUSAL_UNRESOLVED_ACTION_PREFIX}{issue.value}"
        in result.refusal_reasons
    )


@pytest.mark.parametrize(
    "changes",
    [
        {
            "security_id": "sec-synth-other",
            "raw_record_sha256": "51" * 32,
        },
        {
            "effective_date": "2024-02-14",
            "raw_record_sha256": "52" * 32,
        },
        {
            "available_at": "2024-02-14T22:00:00Z",
            "observed_at": "2024-02-14T22:00:00Z",
            "raw_record_sha256": "53" * 32,
        },
    ],
)
def test_lifecycle_selection_requires_stable_id_effective_date_and_availability(
    changes,
):
    bundle = _references()
    changed_active = replace(bundle.lifecycles[0], **changes)
    changed = _reference_bundle(
        bundle, lifecycles=(changed_active, bundle.lifecycles[1])
    )
    result = build_stock_data_readiness(_vintage(), changed)[1]
    assert result.ready is False
    assert REFUSAL_MISSING_LIFECYCLE in result.refusal_reasons
    assert result.lifecycle_record_id is None


def test_conflicting_lifecycle_events_are_ambiguous():
    bundle = _references()
    active = bundle.lifecycles[0]
    conflict = replace(
        active,
        status=bundle.lifecycles[1].status,
        source_version="2024.conflict",
        raw_record_sha256="54" * 32,
    )
    changed = _reference_bundle(
        bundle, lifecycles=(active, conflict, bundle.lifecycles[1])
    )
    result = build_stock_data_readiness(_vintage(), changed)[1]
    assert result.ready is False
    assert REFUSAL_AMBIGUOUS_LIFECYCLE in result.refusal_reasons
    assert result.lifecycle_record_id is None


def test_lifecycle_precedence_uses_effective_date_not_latest_availability():
    bundle = _references()
    newer_effective = replace(
        bundle.lifecycles[0],
        effective_date="2024-02-01",
        available_at="2024-02-01T22:00:00Z",
        observed_at="2024-02-01T22:00:00Z",
        raw_record_sha256="64" * 32,
    )
    older_effective_but_later_available = replace(
        bundle.lifecycles[0],
        effective_date="2024-01-15",
        available_at="2024-02-12T22:00:00Z",
        observed_at="2024-02-12T22:00:00Z",
        raw_record_sha256="65" * 32,
    )
    changed = _reference_bundle(
        bundle,
        lifecycles=(newer_effective, older_effective_but_later_available),
    )

    result = build_stock_data_readiness(_vintage(), changed)[1]

    assert result.ready is True
    assert result.lifecycle_record_id == newer_effective.record_id


def test_future_or_wrong_identity_classification_cannot_backfill_sector():
    bundle = _references()
    classification = bundle.classifications[0]
    future = replace(
        classification,
        available_at="2024-03-01T22:00:00Z",
        observed_at="2024-03-01T22:00:00Z",
        raw_record_sha256="f" * 64,
    )
    future_bundle = _reference_bundle(bundle, classifications=(future,))
    future_result = build_stock_data_readiness(_vintage(), future_bundle)[1]
    assert future_result.ready is False
    assert REFUSAL_MISSING_CLASSIFICATION in future_result.refusal_reasons

    wrong_identity = replace(
        classification,
        security_id="sec-synth-other",
        raw_record_sha256="1" * 64,
    )
    wrong_bundle = _reference_bundle(bundle, classifications=(wrong_identity,))
    wrong_result = build_stock_data_readiness(_vintage(), wrong_bundle)[1]
    assert wrong_result.ready is False
    assert REFUSAL_MISSING_CLASSIFICATION in wrong_result.refusal_reasons

    not_yet_valid = replace(
        classification,
        valid_from="2024-02-14",
        available_at="2024-02-01T22:00:00Z",
        observed_at="2024-02-01T22:00:00Z",
        raw_record_sha256="13" * 32,
    )
    not_yet_valid_bundle = _reference_bundle(
        bundle, classifications=(not_yet_valid,)
    )
    not_yet_valid_result = build_stock_data_readiness(
        _vintage(), not_yet_valid_bundle
    )[1]
    assert not_yet_valid_result.ready is False
    assert (
        REFUSAL_MISSING_CLASSIFICATION
        in not_yet_valid_result.refusal_reasons
    )


def test_sector_mapping_must_be_valid_at_execution_not_only_settlement():
    bundle = _references()
    expired_before_execution = replace(
        bundle.classifications[0],
        valid_to="2024-02-01",
        raw_record_sha256="12" * 32,
    )
    changed = _reference_bundle(
        bundle, classifications=(expired_before_execution,)
    )
    result = build_stock_data_readiness(_vintage(), changed)[1]
    assert result.execution_session == "2024-02-13"
    assert result.ready is False
    assert REFUSAL_MISSING_CLASSIFICATION in result.refusal_reasons


def test_conflicting_same_vintage_classifications_are_ambiguous():
    bundle = _references()
    original = bundle.classifications[0]
    conflict = replace(
        original,
        sector_code="INDUSTRIALS",
        industry_code="MACHINERY",
        source_version="2024.conflict",
        raw_record_sha256="2" * 64,
    )
    changed = _reference_bundle(
        bundle, classifications=(original, conflict)
    )
    result = build_stock_data_readiness(_vintage(), changed)[1]
    assert result.ready is False
    assert REFUSAL_AMBIGUOUS_CLASSIFICATION in result.refusal_reasons
    assert result.sector_code is None


def test_overlapping_classification_intervals_fail_closed():
    bundle = _references()
    original = bundle.classifications[0]
    overlap = replace(
        original,
        valid_from="2024-01-01",
        sector_code="INDUSTRIALS",
        industry_code="MACHINERY",
        source_version="2024.overlap",
        raw_record_sha256="23" * 32,
    )
    changed = _reference_bundle(
        bundle, classifications=(original, overlap)
    )
    result = build_stock_data_readiness(_vintage(), changed)[1]
    assert result.ready is False
    assert REFUSAL_AMBIGUOUS_CLASSIFICATION in result.refusal_reasons
    assert result.classification_record_id is None


def test_security_mapping_must_remain_valid_through_execution():
    vintage = _vintage()
    second = vintage.snapshots[1]
    expired_identity = replace(
        second.security,
        valid_to=second.settlement_date,
        raw_record_sha256="56" * 32,
    )
    expired_snapshot = replace(second, security=expired_identity)
    result = build_stock_data_readiness(
        _vintage_with_second(expired_snapshot), _references()
    )[1]
    assert result.ready is False
    assert REFUSAL_IDENTITY_NOT_VALID in result.refusal_reasons


def test_ticker_rename_preserves_readiness_only_through_stable_security_id():
    vintage = _vintage()
    second = vintage.snapshots[1]
    renamed_identity = replace(
        second.security,
        ticker="RENAMED",
        raw_record_sha256="57" * 32,
    )
    renamed_snapshot = replace(second, security=renamed_identity)
    result = build_stock_data_readiness(
        _vintage_with_second(renamed_snapshot), _references()
    )[1]
    assert result.ready is True
    assert result.security_id == second.security.security_id
    assert result.security_identity_sha256 == hash_payload(
        renamed_identity.to_payload()
    )


def test_unaudited_float_cannot_displace_canonical_shares_outstanding():
    vintage = _vintage()
    second = vintage.snapshots[1]
    float_snapshot = replace(
        second,
        denominator=replace(
            second.denominator,
            kind=DenominatorKind.POINT_IN_TIME_FLOAT,
            raw_record_sha256="3" * 64,
        ),
    )
    result = build_stock_data_readiness(
        _vintage_with_second(float_snapshot), _references()
    )[1]
    assert result.ready is False
    assert REFUSAL_UNAUDITED_FLOAT in result.refusal_reasons


def test_adv_window_must_end_on_the_short_interest_settlement_date():
    vintage = _vintage()
    second = vintage.snapshots[1]
    stale_snapshot = replace(
        second,
        volume_basis=replace(
            second.volume_basis,
            window_end_date="2024-01-30",
            raw_record_sha256="4" * 64,
        ),
    )
    result = build_stock_data_readiness(
        _vintage_with_second(stale_snapshot), _references()
    )[1]
    assert result.ready is False
    assert REFUSAL_STALE_ADV in result.refusal_reasons


def test_reference_fixture_body_and_unknown_fields_fail_closed(tmp_path):
    payload = json.loads(REFERENCE_FIXTURE.read_text(encoding="utf-8"))
    changed = copy.deepcopy(payload)
    changed["classification_rows"][0]["sector_code"] = "INDUSTRIALS"
    changed_path = tmp_path / "changed-reference.json"
    changed_path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(PitReferenceError, match="source_body_sha256"):
        load_synthetic_pit_reference(changed_path)

    unknown = copy.deepcopy(payload["classification_rows"][0])
    unknown["future_unreviewed_field"] = "unsafe"
    with pytest.raises(ValueError, match="unknown"):
        SectorClassificationObservation.from_payload(unknown)


def test_reference_counts_duplicates_and_retrieval_lineage_fail_closed():
    bundle = _references()
    with pytest.raises(PitReferenceError, match="lifecycle_record_count"):
        PitReferenceBundle(
            replace(
                bundle.manifest,
                lifecycle_record_count=bundle.manifest.lifecycle_record_count + 1,
            ),
            bundle.lifecycles,
            bundle.classifications,
        )
    with pytest.raises(PitReferenceError, match="duplicate immutable reference"):
        _reference_bundle(
            bundle,
            lifecycles=(*bundle.lifecycles, bundle.lifecycles[0]),
        )

    late_classification = replace(
        bundle.classifications[0],
        available_at="2024-03-03T22:00:00Z",
        observed_at="2024-03-03T22:00:00Z",
        raw_record_sha256="61" * 32,
    )
    with pytest.raises(PitReferenceError, match="after manifest retrieval"):
        _reference_bundle(bundle, classifications=(late_classification,))


def test_reference_contract_subclass_cannot_cross_bundle_boundary():
    bundle = _references()
    genuine_classification = bundle.classifications[0]

    class ClassificationSubclass(type(genuine_classification)):
        pass

    classification_impostor = ClassificationSubclass(
        **{
            field.name: getattr(genuine_classification, field.name)
            for field in fields(genuine_classification)
        }
    )
    with pytest.raises(PitReferenceError, match="exact SectorClassification"):
        PitReferenceBundle(
            bundle.manifest,
            bundle.lifecycles,
            (classification_impostor,),
        )

    genuine_lifecycle = bundle.lifecycles[0]

    class LifecycleSubclass(type(genuine_lifecycle)):
        pass

    lifecycle_impostor = LifecycleSubclass(
        **{
            field.name: getattr(genuine_lifecycle, field.name)
            for field in fields(genuine_lifecycle)
        }
    )
    with pytest.raises(PitReferenceError, match="exact SecurityLifecycle"):
        PitReferenceBundle(
            bundle.manifest,
            (lifecycle_impostor, bundle.lifecycles[1]),
            bundle.classifications,
        )

    genuine_manifest = bundle.manifest

    class ManifestSubclass(type(genuine_manifest)):
        pass

    manifest_impostor = ManifestSubclass(
        **{
            field.name: getattr(genuine_manifest, field.name)
            for field in fields(genuine_manifest)
        }
    )
    with pytest.raises(PitReferenceError, match="exact PitReferenceManifest"):
        PitReferenceBundle(
            manifest_impostor,
            bundle.lifecycles,
            bundle.classifications,
        )


def test_readiness_boundary_rejects_subclassed_inputs():
    vintage = _vintage()
    references = _references()

    class VintageSubclass(type(vintage)):
        pass

    vintage_impostor = VintageSubclass(
        **{field.name: getattr(vintage, field.name) for field in fields(vintage)}
    )
    with pytest.raises(PitReferenceError, match="exact ShortInterestVintage"):
        build_stock_data_readiness(vintage_impostor, references)

    class BundleSubclass(type(references)):
        pass

    bundle_impostor = BundleSubclass(
        **{
            field.name: getattr(references, field.name)
            for field in fields(references)
        }
    )
    with pytest.raises(PitReferenceError, match="exact PitReferenceBundle"):
        build_stock_data_readiness(vintage, bundle_impostor)


def test_readiness_contract_rejects_inconsistent_or_noncanonical_output():
    genuine = build_stock_data_readiness(_vintage(), _references())[1]
    with pytest.raises(PitReferenceError, match="lifecycle selection refusal"):
        replace(genuine, lifecycle_record_id=None)
    with pytest.raises(PitReferenceError, match="requires sector and industry"):
        replace(genuine, taxonomy_id=None)
    with pytest.raises(ValueError, match="canonical YYYY-MM-DD"):
        replace(genuine, execution_session="2024-2-13")
    with pytest.raises(PitReferenceError, match="must follow settlement_date"):
        replace(genuine, execution_session=genuine.settlement_date)
    with pytest.raises(PitReferenceError, match="XNYS session open"):
        replace(genuine, execution_at="2024-02-13T14:30:01Z")
    with pytest.raises(ValueError, match="64-character sha256"):
        replace(genuine, event_id="not-a-hash")
    with pytest.raises(PitReferenceError, match="source_vintage_sha256"):
        replace(
            genuine,
            source_dataset_id="short-interest-vintage-deadbeefdeadbeef",
        )
    with pytest.raises(PitReferenceError, match="unknown refusal"):
        replace(genuine, ready=False, refusal_reasons=("invented_reason",))
    with pytest.raises(PitReferenceError, match="canonical strings"):
        replace(genuine, ready=False, refusal_reasons=(" ",))
    with pytest.raises(PitReferenceError, match="canonical uppercase"):
        replace(genuine, sector_code="Technology")
