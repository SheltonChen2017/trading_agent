"""Behavioral tests for the 74-firm owner-adjudication candidate bridge."""
from __future__ import annotations

import ast
import copy
import dataclasses
import json
import os
import weakref
from pathlib import Path

import pytest

from research.analyst_revisions_v2 import firm_ontology as firm_module
from research.analyst_revisions_v2.canonical import canonical_json_bytes, sha256_bytes
from research.analyst_revisions_v2.firm_ontology import (
    load_reviewed_firm_rating_ontology,
)
from research.analyst_revisions_v2_qc import (
    firm_ontology_candidate_builder as builder,
)
from research.analyst_revisions_v2_qc import production_evidence_composer as composer
from research.analyst_revisions_v2_qc.firm_ontology_candidate_builder import (
    FirmOntologyCandidateBundle,
    FirmOntologyCandidateError,
    FirmOntologyCandidateRefusalReason,
    build_firm_ontology_candidate_bundle,
    require_firm_ontology_candidate_bundle,
)
from research.analyst_revisions_v2_qc.physical_firm_ontology_review_packet import (
    _build_physical_firm_ontology_review_packet_for_test,
    iter_physical_firm_owner_adjudication_template,
)
from tests.analyst_revisions_v2.test_physical_firm_ontology_review_packet import (
    _c1,
    _diagnostic_ratings,
    _rating,
)


REVIEWED_AT = "2026-09-14T12:00:00.000000Z"
AVAILABLE_AT = "2012-12-31T12:00:00.000000Z"


@pytest.fixture(scope="module")
def review_packet(tmp_path_factory):
    root = tmp_path_factory.mktemp("firm-candidate-packet")
    ratings = [
        _rating(
            f"rating-{ordinal:03d}",
            firm_id=f"firm-{ordinal:03d}",
            firm_name=f"Firm {ordinal:03d}",
            action="upgrades",
            rating="Buy",
            previous_rating="Hold",
        )
        for ordinal in range(74)
    ]
    return _build_physical_firm_ontology_review_packet_for_test(
        accepted_risk_archive=_c1(root, ratings),
        output_root=root / "review",
    )


def _mapping(firm_id: str, label: str, rank: int) -> dict[str, object]:
    return {
        "valid_from": "2013-01-02",
        "valid_to": None,
        "raw_label": label,
        "ordered_rank": rank,
        "source_evidence_id": f"scale-{firm_id}-{rank}",
        "source_evidence_sha256": sha256_bytes(
            canonical_json_bytes(["scale", firm_id, label, rank])
        ),
        "available_at": AVAILABLE_AT,
        "valid_to_available_at": None,
    }


def _owner_rows(packet) -> list[dict[str, object]]:
    rows = copy.deepcopy(list(iter_physical_firm_owner_adjudication_template(packet)))
    for row in rows:
        firm_id = row["provider_firm_id"]
        row["owner_adjudication"] = {
            "review_status": builder.OWNER_ADJUDICATION_STATUS,
            "reviewer": "Owner Reviewer",
            "reviewed_at": REVIEWED_AT,
            "canonical_firm_name": row["observed_firm_names"][0],
            "validity_intervals": [
                {"valid_from": "2013-01-02", "valid_to": None}
            ],
            "ordered_scale": [
                _mapping(firm_id, "Sell", 1),
                _mapping(firm_id, "Hold", 2),
                _mapping(firm_id, "Buy", 3),
            ],
            "scope": "company_relative",
            "alias_mappings": [],
            "notes": "Owner supplied each judgment and evidence field explicitly.",
        }
    return rows


def _write_owner(path: Path, rows: list[dict[str, object]]) -> Path:
    path.write_bytes(b"".join(canonical_json_bytes(row) for row in rows))
    path.chmod(0o600)
    return path


def _reason(exc_info) -> FirmOntologyCandidateRefusalReason:
    assert type(exc_info.value) is FirmOntologyCandidateError
    return exc_info.value.reason


def _refresh_test_bundle_authority(candidate: FirmOntologyCandidateBundle) -> None:
    """Expose content verifiers beneath the independent mint-authentication guard."""

    authority = builder._BUNDLE_AUTHORITIES[id(candidate)]
    builder._BUNDLE_AUTHORITIES[id(candidate)] = (
        authority[0],
        builder._bundle_fingerprint(candidate),
        os.getpid(),
    )


def test_complete_owner_file_renders_deterministic_loader_compatible_candidates(
    review_packet, tmp_path: Path, monkeypatch
) -> None:
    owner_path = _write_owner(tmp_path / "owner.jsonl", _owner_rows(review_packet))
    first = build_firm_ontology_candidate_bundle(
        review_packet=review_packet,
        owner_adjudication_path=owner_path,
    )
    second = build_firm_ontology_candidate_bundle(
        review_packet=review_packet,
        owner_adjudication_path=owner_path,
    )

    assert first == second
    assert first.firm_count == 74
    assert first.ontology_entry_count == 74 * 3
    assert first.bundle_id.startswith("arv2-firm-candidate-bundle-")
    assert first.owner_adjudication_sha256 == sha256_bytes(
        first.owner_adjudication_bytes
    )
    assert first.owner_adjudication_byte_count == len(
        first.owner_adjudication_bytes
    )
    assert first.independently_reviewed is False
    assert first.production_authority is False
    assert all(
        getattr(first, name) is False
        for name in (
            "provider_access",
            "quantconnect_access",
            "outcome_access",
            "deployment",
            "orders",
            "trading",
        )
    )

    ontology_path = tmp_path / "ontology.json"
    ontology_path.write_bytes(first.ontology_bytes)
    ontology_path.chmod(0o600)
    ontology = load_reviewed_firm_rating_ontology(ontology_path)
    assert ontology.ontology_id == first.ontology_id
    assert ontology.payload_sha256 == first.ontology_sha256
    assert len(ontology.entries) == 222
    assert ontology.status == "reviewed"

    availability_path = tmp_path / "availability.json"
    availability_path.write_bytes(first.availability_bytes)
    availability_path.chmod(0o600)
    pending = json.loads(first.availability_review_candidate_bytes)
    assert pending["status"] == builder.PENDING_REVIEW_STATUS
    assert pending["receipt_id"] is None
    assert pending["receipt_sha256"] is None
    assert pending["complete_ontology_entry_census_verified"] is False
    assert pending["historical_availability_verified_from_external_source_evidence"] is False

    # A test-only reviewer projection demonstrates exact loader compatibility.
    # The production builder deliberately has no function that performs this
    # promotion or makes these independent-review assertions.
    pending.update(
        {
            "status": composer.FIRM_AVAILABILITY_REVIEW_STATUS,
            "complete_ontology_entry_census_verified": True,
            "historical_availability_verified_from_external_source_evidence": True,
            "no_review_time_or_valid_from_imputation_verified": True,
        }
    )
    seed = dict(pending)
    seed["receipt_id"] = None
    seed["receipt_sha256"] = None
    digest = sha256_bytes(canonical_json_bytes(seed))
    pending["receipt_id"] = f"arv2-firm-availability-review-{digest[:24]}"
    pending["receipt_sha256"] = digest
    review_path = tmp_path / "availability-review.json"
    review_path.write_bytes(canonical_json_bytes(pending))
    review_path.chmod(0o600)
    monkeypatch.setattr(
        firm_module,
        "require_registered_production_firm_ontology",
        lambda value: value,
    )
    availability = composer.load_reviewed_firm_ontology_availability(
        ontology=ontology,
        availability_path=availability_path,
        review_path=review_path,
    )
    assert availability.ontology_id == ontology.ontology_id
    assert len(availability.entries) == 222

    registry = json.loads(first.registry_candidate_bytes)
    assert registry["candidate_id"] == first.registry_candidate_id
    assert registry["candidate_sha256"] == first.registry_candidate_sha256
    assert registry["status"] == builder.PENDING_REVIEW_STATUS
    assert registry["entry"]["review_commit"] is None
    assert registry["entry"]["reviewed_by"] is None
    assert registry["entry"]["reviewed_at"] is None
    registry_seed = dict(registry)
    registry_seed["candidate_id"] = None
    registry_seed["candidate_sha256"] = None
    assert registry["candidate_sha256"] == sha256_bytes(
        canonical_json_bytes(registry_seed)
    )
    assert registry["candidate_id"] == (
        f"arv2-firm-registry-candidate-{registry['candidate_sha256'][:24]}"
    )

    coverage = json.loads(first.coverage_diagnostic_bytes)
    assert coverage["reviewed_firm_count"] == 74
    assert coverage["ontology_entry_count"] == 222
    assert coverage["all_selected_firms_present_once"] is True
    assert coverage["all_observed_dates_and_labels_covered"] is True
    assert coverage["independently_reviewed"] is False
    coverage_seed = dict(coverage)
    coverage_seed["diagnostic_id"] = None
    coverage_seed["diagnostic_sha256"] = None
    assert coverage["diagnostic_sha256"] == sha256_bytes(
        canonical_json_bytes(coverage_seed)
    )


def test_packet_with_fewer_than_74_selected_firms_is_named_refusal(
    tmp_path: Path,
) -> None:
    c1 = _c1(tmp_path, _diagnostic_ratings())
    packet = _build_physical_firm_ontology_review_packet_for_test(
        accepted_risk_archive=c1,
        output_root=tmp_path / "review",
    )
    placeholder = tmp_path / "placeholder.jsonl"
    placeholder.write_bytes(b"{}\n")
    placeholder.chmod(0o600)
    with pytest.raises(FirmOntologyCandidateError) as exc_info:
        build_firm_ontology_candidate_bundle(
            review_packet=packet,
            owner_adjudication_path=placeholder,
        )
    assert _reason(exc_info) is FirmOntologyCandidateRefusalReason.PACKET_CENSUS_NOT_74


def test_candidate_bundle_forgery_and_post_build_mutation_are_refused(
    review_packet, tmp_path: Path
) -> None:
    owner_path = _write_owner(tmp_path / "owner.jsonl", _owner_rows(review_packet))
    candidate = build_firm_ontology_candidate_bundle(
        review_packet=review_packet, owner_adjudication_path=owner_path
    )
    assert require_firm_ontology_candidate_bundle(candidate) is candidate

    forged = FirmOntologyCandidateBundle(
        **{
            field.name: getattr(candidate, field.name)
            for field in dataclasses.fields(candidate)
        }
    )
    with pytest.raises(FirmOntologyCandidateError) as exc_info:
        require_firm_ontology_candidate_bundle(forged)
    assert _reason(exc_info) is FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED

    object.__setattr__(candidate, "ontology_sha256", "f" * 64)
    with pytest.raises(FirmOntologyCandidateError) as exc_info:
        require_firm_ontology_candidate_bundle(candidate)
    assert _reason(exc_info) is FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED


def test_bundle_creator_pid_guard_is_an_isolated_refusal(
    review_packet, tmp_path: Path, monkeypatch
) -> None:
    owner_path = _write_owner(tmp_path / "owner-pid.jsonl", _owner_rows(review_packet))
    candidate = build_firm_ontology_candidate_bundle(
        review_packet=review_packet, owner_adjudication_path=owner_path
    )
    monkeypatch.setattr(builder, "_BUNDLE_AUTHORITY_PID", os.getpid() + 1)

    with pytest.raises(FirmOntologyCandidateError, match="another process") as exc_info:
        require_firm_ontology_candidate_bundle(candidate)
    assert _reason(exc_info) is FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED


def test_bundle_content_address_is_independently_recomputed(
    review_packet, tmp_path: Path
) -> None:
    candidate = build_firm_ontology_candidate_bundle(
        review_packet=review_packet,
        owner_adjudication_path=_write_owner(
            tmp_path / "owner-bundle-address.jsonl", _owner_rows(review_packet)
        ),
    )
    object.__setattr__(candidate, "bundle_sha256", "f" * 64)
    _refresh_test_bundle_authority(candidate)

    with pytest.raises(FirmOntologyCandidateError, match="bundle content address"):
        require_firm_ontology_candidate_bundle(candidate)


def test_ontology_semantic_address_and_packet_lineage_are_recomputed(
    review_packet, tmp_path: Path
) -> None:
    candidate = build_firm_ontology_candidate_bundle(
        review_packet=review_packet,
        owner_adjudication_path=_write_owner(
            tmp_path / "owner-ontology-address.jsonl", _owner_rows(review_packet)
        ),
    )
    object.__setattr__(candidate, "packet_sha256", "f" * 64)
    _refresh_test_bundle_authority(candidate)

    with pytest.raises(FirmOntologyCandidateError, match="semantic address or lineage"):
        require_firm_ontology_candidate_bundle(candidate)


def test_availability_ontology_cross_binding_is_recomputed(
    review_packet, tmp_path: Path
) -> None:
    candidate = build_firm_ontology_candidate_bundle(
        review_packet=review_packet,
        owner_adjudication_path=_write_owner(
            tmp_path / "owner-availability-binding.jsonl", _owner_rows(review_packet)
        ),
    )
    availability = json.loads(candidate.availability_bytes)
    availability["ontology_sha256"] = "f" * 64
    availability_bytes = canonical_json_bytes(availability)
    availability_sha = sha256_bytes(availability_bytes)
    object.__setattr__(candidate, "availability_bytes", availability_bytes)
    object.__setattr__(candidate, "availability_sha256", availability_sha)
    object.__setattr__(
        candidate,
        "availability_id",
        f"arv2-firm-availability-{availability_sha[:24]}",
    )
    _refresh_test_bundle_authority(candidate)

    with pytest.raises(FirmOntologyCandidateError, match="ontology binding"):
        require_firm_ontology_candidate_bundle(candidate)


def test_pending_availability_review_cross_binding_is_recomputed(
    review_packet, tmp_path: Path
) -> None:
    candidate = build_firm_ontology_candidate_bundle(
        review_packet=review_packet,
        owner_adjudication_path=_write_owner(
            tmp_path / "owner-review-binding.jsonl", _owner_rows(review_packet)
        ),
    )
    review = json.loads(candidate.availability_review_candidate_bytes)
    review["entry_count"] += 1
    review_bytes = canonical_json_bytes(review)
    object.__setattr__(candidate, "availability_review_candidate_bytes", review_bytes)
    object.__setattr__(
        candidate,
        "availability_review_candidate_sha256",
        sha256_bytes(review_bytes),
    )
    _refresh_test_bundle_authority(candidate)

    with pytest.raises(FirmOntologyCandidateError, match="review candidate binding"):
        require_firm_ontology_candidate_bundle(candidate)


def test_registry_candidate_content_address_is_recomputed(
    review_packet, tmp_path: Path
) -> None:
    candidate = build_firm_ontology_candidate_bundle(
        review_packet=review_packet,
        owner_adjudication_path=_write_owner(
            tmp_path / "owner-registry-address.jsonl", _owner_rows(review_packet)
        ),
    )
    registry = json.loads(candidate.registry_candidate_bytes)
    registry["candidate_sha256"] = "f" * 64
    object.__setattr__(
        candidate, "registry_candidate_bytes", canonical_json_bytes(registry)
    )
    object.__setattr__(candidate, "registry_candidate_sha256", "f" * 64)
    _refresh_test_bundle_authority(candidate)

    with pytest.raises(FirmOntologyCandidateError, match="registry candidate content"):
        require_firm_ontology_candidate_bundle(candidate)


def test_coverage_diagnostic_content_address_is_recomputed(
    review_packet, tmp_path: Path
) -> None:
    candidate = build_firm_ontology_candidate_bundle(
        review_packet=review_packet,
        owner_adjudication_path=_write_owner(
            tmp_path / "owner-coverage-address.jsonl", _owner_rows(review_packet)
        ),
    )
    coverage = json.loads(candidate.coverage_diagnostic_bytes)
    coverage["diagnostic_sha256"] = "f" * 64
    object.__setattr__(
        candidate, "coverage_diagnostic_bytes", canonical_json_bytes(coverage)
    )
    object.__setattr__(candidate, "coverage_diagnostic_sha256", "f" * 64)
    _refresh_test_bundle_authority(candidate)

    with pytest.raises(FirmOntologyCandidateError, match="diagnostic content address"):
        require_firm_ontology_candidate_bundle(candidate)


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX fork is unavailable")
def test_bundle_registry_and_lock_reset_after_fork(
    review_packet, tmp_path: Path
) -> None:
    owner_path = _write_owner(tmp_path / "owner-fork.jsonl", _owner_rows(review_packet))
    candidate = build_firm_ontology_candidate_bundle(
        review_packet=review_packet, owner_adjudication_path=owner_path
    )
    read_descriptor, write_descriptor = os.pipe()
    child = os.fork()
    if child == 0:
        os.close(read_descriptor)
        reset = (
            builder._BUNDLE_AUTHORITY_PID == os.getpid()
            and builder._BUNDLE_AUTHORITIES == {}
        )
        try:
            require_firm_ontology_candidate_bundle(candidate)
        except FirmOntologyCandidateError:
            refused = True
        else:
            refused = False
        os.write(write_descriptor, b"ok" if reset and refused else b"bad")
        os.close(write_descriptor)
        os._exit(0)
    os.close(write_descriptor)
    try:
        result = os.read(read_descriptor, 3)
    finally:
        os.close(read_descriptor)
    waited, status = os.waitpid(child, 0)
    assert waited == child and os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
    assert result == b"ok"
    assert require_firm_ontology_candidate_bundle(candidate) is candidate


class _RetentionMarker:
    pass


def test_high_cardinality_evidence_selection_is_bounded_and_exhaustive() -> None:
    selected_ids = tuple(f"firm-{ordinal:06d}" for ordinal in range(74))
    selected_set = frozenset(selected_ids)
    references: list[weakref.ReferenceType[_RetentionMarker]] = []
    live = 0
    peak = 0
    exhausted = False

    def collected(_reference) -> None:
        nonlocal live
        live -= 1

    def rows():
        nonlocal exhausted, live, peak
        for ordinal in range(10_000):
            firm_id = f"firm-{ordinal:06d}"
            if firm_id in selected_set:
                yield {"provider_firm_id": firm_id}
                continue
            marker = _RetentionMarker()
            live += 1
            references.append(weakref.ref(marker, collected))
            peak = max(peak, live)
            if peak > 2:
                raise AssertionError("unselected firm evidence accumulated in memory")
            yield {"provider_firm_id": firm_id, "retention_marker": marker}
            marker = None
        exhausted = True

    selected = builder._select_authenticated_evidence_rows(
        rows(), selected_ids=selected_ids, expected_row_count=10_000
    )

    assert exhausted is True
    assert tuple(selected) == selected_ids
    assert peak <= 2
    assert live == 0


def test_candidate_builder_routes_packet_census_through_bounded_selector(
    review_packet, tmp_path: Path, monkeypatch
) -> None:
    observed: list[tuple[int, int]] = []
    original = builder._select_authenticated_evidence_rows

    def selector(rows, *, selected_ids, expected_row_count):
        selected = original(
            rows,
            selected_ids=selected_ids,
            expected_row_count=expected_row_count,
        )
        observed.append((expected_row_count, len(selected)))
        return selected

    monkeypatch.setattr(builder, "_select_authenticated_evidence_rows", selector)
    owner_path = _write_owner(
        tmp_path / "owner-selector.jsonl", _owner_rows(review_packet)
    )
    build_firm_ontology_candidate_bundle(
        review_packet=review_packet, owner_adjudication_path=owner_path
    )

    assert observed == [(review_packet.firm_count, 74)]


def test_evidence_selector_refuses_duplicate_identity() -> None:
    rows = (
        {"provider_firm_id": "firm-001"},
        {"provider_firm_id": "firm-001"},
    )
    with pytest.raises(FirmOntologyCandidateError, match="duplicated or out of order"):
        builder._select_authenticated_evidence_rows(
            rows, selected_ids=("firm-001",), expected_row_count=2
        )


def test_evidence_selector_refuses_out_of_order_identity() -> None:
    rows = (
        {"provider_firm_id": "firm-002"},
        {"provider_firm_id": "firm-001"},
    )
    with pytest.raises(FirmOntologyCandidateError, match="duplicated or out of order"):
        builder._select_authenticated_evidence_rows(
            rows, selected_ids=("firm-001",), expected_row_count=2
        )


def test_evidence_selector_refuses_missing_selected_identity_after_exhaustion() -> None:
    rows = (
        {"provider_firm_id": "firm-001"},
        {"provider_firm_id": "firm-002"},
    )
    with pytest.raises(FirmOntologyCandidateError, match="complete authenticated"):
        builder._select_authenticated_evidence_rows(
            rows, selected_ids=("firm-003",), expected_row_count=2
        )


def test_evidence_selector_refuses_short_and_long_census() -> None:
    with pytest.raises(FirmOntologyCandidateError, match="complete authenticated"):
        builder._select_authenticated_evidence_rows(
            ({"provider_firm_id": "firm-001"},),
            selected_ids=("firm-001",),
            expected_row_count=2,
        )
    with pytest.raises(FirmOntologyCandidateError, match="census or row type"):
        builder._select_authenticated_evidence_rows(
            (
                {"provider_firm_id": "firm-001"},
                {"provider_firm_id": "firm-002"},
            ),
            selected_ids=("firm-001",),
            expected_row_count=1,
        )

def test_forged_packet_with_copied_fields_never_acquires_builder_authority(
    review_packet, tmp_path: Path
) -> None:
    forged = object.__new__(type(review_packet))
    for field in dataclasses.fields(review_packet):
        object.__setattr__(forged, field.name, getattr(review_packet, field.name))
    owner_path = _write_owner(tmp_path / "forged.jsonl", _owner_rows(review_packet))
    with pytest.raises(FirmOntologyCandidateError) as exc_info:
        build_firm_ontology_candidate_bundle(
            review_packet=forged, owner_adjudication_path=owner_path
        )
    assert _reason(exc_info) is FirmOntologyCandidateRefusalReason.PACKET_AUTHENTICATION_FAILED


@pytest.mark.parametrize("mutation", ["omitted", "duplicate", "reordered"])
def test_owner_firm_census_must_match_all_74_exactly(
    review_packet, tmp_path: Path, mutation: str
) -> None:
    rows = _owner_rows(review_packet)
    if mutation == "omitted":
        rows.pop()
    elif mutation == "duplicate":
        rows[-1] = copy.deepcopy(rows[-2])
    else:
        rows[0], rows[1] = rows[1], rows[0]
    path = _write_owner(tmp_path / f"{mutation}.jsonl", rows)
    with pytest.raises(FirmOntologyCandidateError) as exc_info:
        build_firm_ontology_candidate_bundle(
            review_packet=review_packet, owner_adjudication_path=path
        )
    assert _reason(exc_info) is FirmOntologyCandidateRefusalReason.ADJUDICATION_CENSUS_CHANGED


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ranking_ordinal", 999),
        ("predeclared_2021_2025_volume_count", 999),
        ("observed_firm_names", ["Invented Firm"]),
        ("ontology_authority_created", True),
        ("availability_authority_created", True),
        ("production_authority", True),
    ],
)
def test_packet_derived_outer_fields_cannot_be_changed(
    review_packet, tmp_path: Path, field: str, value: object
) -> None:
    rows = _owner_rows(review_packet)
    rows[0][field] = value
    path = _write_owner(tmp_path / f"outer-{field}.jsonl", rows)
    with pytest.raises(FirmOntologyCandidateError) as exc_info:
        build_firm_ontology_candidate_bundle(
            review_packet=review_packet, owner_adjudication_path=path
        )
    assert _reason(exc_info) is FirmOntologyCandidateRefusalReason.TEMPLATE_BINDING_CHANGED


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("review_status", "draft"),
        ("reviewer", None),
        ("reviewed_at", "2026-09-14"),
        ("canonical_firm_name", ""),
        ("notes", 7),
    ],
)
def test_review_status_reviewer_time_name_and_notes_are_explicit(
    review_packet, tmp_path: Path, field: str, value: object
) -> None:
    rows = _owner_rows(review_packet)
    rows[0]["owner_adjudication"][field] = value
    path = _write_owner(tmp_path / f"review-{field}.jsonl", rows)
    with pytest.raises(FirmOntologyCandidateError) as exc_info:
        build_firm_ontology_candidate_bundle(
            review_packet=review_packet, owner_adjudication_path=path
        )
    assert _reason(exc_info) is FirmOntologyCandidateRefusalReason.REVIEW_INCOMPLETE


def test_validity_intervals_must_be_contiguous_and_cover_observed_dates(
    review_packet, tmp_path: Path
) -> None:
    rows = _owner_rows(review_packet)
    rows[0]["owner_adjudication"]["validity_intervals"] = [
        {"valid_from": "2013-01-02", "valid_to": "2020-01-01"},
        {"valid_from": "2020-01-02", "valid_to": None},
    ]
    path = _write_owner(tmp_path / "interval-gap.jsonl", rows)
    with pytest.raises(FirmOntologyCandidateError) as exc_info:
        build_firm_ontology_candidate_bundle(
            review_packet=review_packet, owner_adjudication_path=path
        )
    assert _reason(exc_info) is FirmOntologyCandidateRefusalReason.VALIDITY_INTERVALS_INVALID

    rows = _owner_rows(review_packet)
    adjudication = rows[0]["owner_adjudication"]
    adjudication["validity_intervals"] = [
        {"valid_from": "2022-01-01", "valid_to": None}
    ]
    for mapping in adjudication["ordered_scale"]:
        mapping["valid_from"] = "2022-01-01"
    path = _write_owner(tmp_path / "date-uncovered.jsonl", rows)
    with pytest.raises(FirmOntologyCandidateError) as exc_info:
        build_firm_ontology_candidate_bundle(
            review_packet=review_packet, owner_adjudication_path=path
        )
    assert _reason(exc_info) is FirmOntologyCandidateRefusalReason.OBSERVED_DATE_UNCOVERED


def test_multiple_contiguous_scales_and_aliases_are_preserved_explicitly(
    review_packet, tmp_path: Path
) -> None:
    rows = _owner_rows(review_packet)
    adjudication = rows[0]["owner_adjudication"]
    adjudication["validity_intervals"] = [
        {"valid_from": "2013-01-02", "valid_to": "2020-01-01"},
        {"valid_from": "2020-01-01", "valid_to": None},
    ]
    open_scale = adjudication["ordered_scale"]
    closed_scale = copy.deepcopy(open_scale)
    for item in closed_scale:
        item["valid_to"] = "2020-01-01"
        item["valid_to_available_at"] = "2020-01-02T12:00:00.000000Z"
        item["source_evidence_id"] += "-closed"
    for item in open_scale:
        item["valid_from"] = "2020-01-01"
        item["source_evidence_id"] += "-open"
    alias = copy.deepcopy(open_scale[1])
    alias["raw_label"] = "Market Perform"
    alias["source_evidence_id"] += "-alias"
    alias["source_evidence_sha256"] = sha256_bytes(
        canonical_json_bytes(["explicit-alias", rows[0]["provider_firm_id"]])
    )
    adjudication["ordered_scale"] = closed_scale + open_scale
    adjudication["alias_mappings"] = [alias]
    path = _write_owner(tmp_path / "multiple-intervals.jsonl", rows)

    candidate = build_firm_ontology_candidate_bundle(
        review_packet=review_packet, owner_adjudication_path=path
    )
    ontology = json.loads(candidate.ontology_bytes)
    first_firm = [
        item
        for item in ontology["entries"]
        if item["provider_firm_id"] == rows[0]["provider_firm_id"]
    ]
    assert len(first_firm) == 7
    assert [
        item for item in first_firm if item["mapping_quality"] == "reviewed_alias"
    ][0]["raw_label"] == "Market Perform"
    assert {item["valid_from"] for item in first_firm} == {
        "2013-01-02",
        "2020-01-01",
    }


@pytest.mark.parametrize("mutation", ["missing_rank", "duplicate_rank", "alias_rank"])
def test_each_interval_has_one_complete_contiguous_ordered_scale(
    review_packet, tmp_path: Path, mutation: str
) -> None:
    rows = _owner_rows(review_packet)
    adjudication = rows[0]["owner_adjudication"]
    if mutation == "missing_rank":
        adjudication["ordered_scale"].pop(1)
    elif mutation == "duplicate_rank":
        adjudication["ordered_scale"][2]["ordered_rank"] = 2
    else:
        alias = _mapping(rows[0]["provider_firm_id"], "Market Perform", 4)
        alias["source_evidence_id"] += "-alias"
        adjudication["alias_mappings"] = [alias]
    path = _write_owner(tmp_path / f"scale-{mutation}.jsonl", rows)
    with pytest.raises(FirmOntologyCandidateError) as exc_info:
        build_firm_ontology_candidate_bundle(
            review_packet=review_packet, owner_adjudication_path=path
        )
    assert _reason(exc_info) is FirmOntologyCandidateRefusalReason.SCALE_INCOMPLETE


def test_scope_alias_and_evidence_are_explicit_and_nonduplicative(
    review_packet, tmp_path: Path
) -> None:
    rows = _owner_rows(review_packet)
    rows[0]["owner_adjudication"]["scope"] = "global_guess"
    path = _write_owner(tmp_path / "scope.jsonl", rows)
    with pytest.raises(FirmOntologyCandidateError) as exc_info:
        build_firm_ontology_candidate_bundle(
            review_packet=review_packet, owner_adjudication_path=path
        )
    assert _reason(exc_info) is FirmOntologyCandidateRefusalReason.SCOPE_INVALID

    rows = _owner_rows(review_packet)
    adjudication = rows[0]["owner_adjudication"]
    alias = copy.deepcopy(adjudication["ordered_scale"][1])
    alias["source_evidence_id"] += "-alias"
    adjudication["alias_mappings"] = [alias]
    path = _write_owner(tmp_path / "duplicate-alias.jsonl", rows)
    with pytest.raises(FirmOntologyCandidateError) as exc_info:
        build_firm_ontology_candidate_bundle(
            review_packet=review_packet, owner_adjudication_path=path
        )
    assert _reason(exc_info) is FirmOntologyCandidateRefusalReason.DUPLICATE_MAPPING

    rows = _owner_rows(review_packet)
    rows[0]["owner_adjudication"]["ordered_scale"][0][
        "source_evidence_sha256"
    ] = "not-a-hash"
    path = _write_owner(tmp_path / "evidence.jsonl", rows)
    with pytest.raises(FirmOntologyCandidateError) as exc_info:
        build_firm_ontology_candidate_bundle(
            review_packet=review_packet, owner_adjudication_path=path
        )
    assert _reason(exc_info) is FirmOntologyCandidateRefusalReason.EVIDENCE_INVALID

    rows = _owner_rows(review_packet)
    rows[0]["owner_adjudication"]["ordered_scale"][0]["available_at"] = (
        "2026-09-15T12:00:00.000000Z"
    )
    path = _write_owner(tmp_path / "future-evidence.jsonl", rows)
    with pytest.raises(FirmOntologyCandidateError) as exc_info:
        build_firm_ontology_candidate_bundle(
            review_packet=review_packet, owner_adjudication_path=path
        )
    assert _reason(exc_info) is FirmOntologyCandidateRefusalReason.EVIDENCE_INVALID

    rows = _owner_rows(review_packet)
    first = rows[0]["owner_adjudication"]["ordered_scale"][0]
    second = rows[1]["owner_adjudication"]["ordered_scale"][0]
    second["source_evidence_id"] = first["source_evidence_id"]
    path = _write_owner(tmp_path / "conflicting-evidence-id.jsonl", rows)
    with pytest.raises(FirmOntologyCandidateError) as exc_info:
        build_firm_ontology_candidate_bundle(
            review_packet=review_packet, owner_adjudication_path=path
        )
    assert _reason(exc_info) is FirmOntologyCandidateRefusalReason.EVIDENCE_INVALID


def test_every_observed_label_requires_an_explicit_mapping(
    review_packet, tmp_path: Path
) -> None:
    rows = _owner_rows(review_packet)
    scale = rows[0]["owner_adjudication"]["ordered_scale"]
    scale[1]["raw_label"] = "Neutral"
    path = _write_owner(tmp_path / "unmapped.jsonl", rows)
    with pytest.raises(FirmOntologyCandidateError) as exc_info:
        build_firm_ontology_candidate_bundle(
            review_packet=review_packet, owner_adjudication_path=path
        )
    assert _reason(exc_info) is FirmOntologyCandidateRefusalReason.OBSERVED_LABEL_UNMAPPED


@pytest.mark.parametrize("mutation", ["public", "symlink", "noncanonical"])
def test_owner_file_is_private_regular_and_canonical(
    review_packet, tmp_path: Path, mutation: str
) -> None:
    rows = _owner_rows(review_packet)
    real = _write_owner(tmp_path / f"real-{mutation}.jsonl", rows)
    path = real
    if mutation == "public":
        real.chmod(0o644)
    elif mutation == "symlink":
        path = tmp_path / "alias.jsonl"
        path.symlink_to(real)
    else:
        real.write_bytes(real.read_bytes() + b" ")
    with pytest.raises(FirmOntologyCandidateError) as exc_info:
        build_firm_ontology_candidate_bundle(
            review_packet=review_packet, owner_adjudication_path=path
        )
    assert _reason(exc_info) is FirmOntologyCandidateRefusalReason.ADJUDICATION_FILE_INVALID


def test_owner_stream_total_byte_boundary_is_exact(
    review_packet, tmp_path: Path, monkeypatch
) -> None:
    path = _write_owner(tmp_path / "owner-total-boundary.jsonl", _owner_rows(review_packet))
    payload = path.read_bytes()
    monkeypatch.setattr(builder, "MAX_OWNER_ADJUDICATION_BYTES", len(payload))
    observed, rows = builder._read_owner_file(path)
    assert observed == payload
    assert len(rows) == 74

    monkeypatch.setattr(builder, "MAX_OWNER_ADJUDICATION_BYTES", len(payload) - 1)
    with pytest.raises(FirmOntologyCandidateError) as exc_info:
        builder._read_owner_file(path)
    assert _reason(exc_info) is FirmOntologyCandidateRefusalReason.ADJUDICATION_FILE_INVALID


def test_owner_stream_row_byte_boundary_is_exact(
    review_packet, tmp_path: Path, monkeypatch
) -> None:
    path = _write_owner(tmp_path / "owner-row-boundary.jsonl", _owner_rows(review_packet))
    maximum_row = max(len(line) for line in path.read_bytes().splitlines(keepends=True))
    monkeypatch.setattr(builder, "MAX_OWNER_ADJUDICATION_ROW_BYTES", maximum_row)
    _payload, rows = builder._read_owner_file(path)
    assert len(rows) == 74

    monkeypatch.setattr(builder, "MAX_OWNER_ADJUDICATION_ROW_BYTES", maximum_row - 1)
    with pytest.raises(FirmOntologyCandidateError) as exc_info:
        builder._read_owner_file(path)
    assert _reason(exc_info) is FirmOntologyCandidateRefusalReason.ADJUDICATION_FILE_INVALID


def test_validity_interval_ceiling_has_exact_boundary(monkeypatch) -> None:
    intervals = [
        {"valid_from": "2013-01-02", "valid_to": "2020-01-01"},
        {"valid_from": "2020-01-01", "valid_to": None},
    ]
    monkeypatch.setattr(builder, "MAX_VALIDITY_INTERVALS_PER_FIRM", 2)
    assert len(builder._validated_intervals(intervals)) == 2

    monkeypatch.setattr(builder, "MAX_VALIDITY_INTERVALS_PER_FIRM", 1)
    with pytest.raises(FirmOntologyCandidateError) as exc_info:
        builder._validated_intervals(intervals)
    assert _reason(exc_info) is FirmOntologyCandidateRefusalReason.CANDIDATE_CAPACITY_EXCEEDED


def test_primary_mapping_ceiling_has_exact_boundary(
    review_packet, tmp_path: Path, monkeypatch
) -> None:
    owner_path = _write_owner(
        tmp_path / "owner-primary-cap.jsonl", _owner_rows(review_packet)
    )
    monkeypatch.setattr(builder, "MAX_PRIMARY_MAPPINGS_PER_FIRM", 3)
    build_firm_ontology_candidate_bundle(
        review_packet=review_packet, owner_adjudication_path=owner_path
    )

    monkeypatch.setattr(builder, "MAX_PRIMARY_MAPPINGS_PER_FIRM", 2)
    with pytest.raises(FirmOntologyCandidateError) as exc_info:
        build_firm_ontology_candidate_bundle(
            review_packet=review_packet, owner_adjudication_path=owner_path
        )
    assert _reason(exc_info) is FirmOntologyCandidateRefusalReason.CANDIDATE_CAPACITY_EXCEEDED


def test_alias_mapping_ceiling_has_exact_boundary(
    review_packet, tmp_path: Path, monkeypatch
) -> None:
    rows = _owner_rows(review_packet)
    firm_id = rows[0]["provider_firm_id"]
    alias = _mapping(firm_id, "Neutral", 2)
    alias["source_evidence_id"] = f"alias-{firm_id}"
    alias["source_evidence_sha256"] = sha256_bytes(
        canonical_json_bytes(["alias", firm_id, "Neutral", 2])
    )
    rows[0]["owner_adjudication"]["alias_mappings"] = [alias]
    owner_path = _write_owner(tmp_path / "owner-alias-cap.jsonl", rows)
    monkeypatch.setattr(builder, "MAX_ALIAS_MAPPINGS_PER_FIRM", 1)
    build_firm_ontology_candidate_bundle(
        review_packet=review_packet, owner_adjudication_path=owner_path
    )

    monkeypatch.setattr(builder, "MAX_ALIAS_MAPPINGS_PER_FIRM", 0)
    with pytest.raises(FirmOntologyCandidateError) as exc_info:
        build_firm_ontology_candidate_bundle(
            review_packet=review_packet, owner_adjudication_path=owner_path
        )
    assert _reason(exc_info) is FirmOntologyCandidateRefusalReason.CANDIDATE_CAPACITY_EXCEEDED


def test_total_mapping_ceiling_has_exact_boundary(
    review_packet, tmp_path: Path, monkeypatch
) -> None:
    owner_path = _write_owner(
        tmp_path / "owner-total-mapping-cap.jsonl", _owner_rows(review_packet)
    )
    monkeypatch.setattr(builder, "MAX_MAPPINGS_PER_FIRM", 3)
    build_firm_ontology_candidate_bundle(
        review_packet=review_packet, owner_adjudication_path=owner_path
    )

    monkeypatch.setattr(builder, "MAX_MAPPINGS_PER_FIRM", 2)
    with pytest.raises(FirmOntologyCandidateError) as exc_info:
        build_firm_ontology_candidate_bundle(
            review_packet=review_packet, owner_adjudication_path=owner_path
        )
    assert _reason(exc_info) is FirmOntologyCandidateRefusalReason.CANDIDATE_CAPACITY_EXCEEDED


def test_total_entry_ceiling_has_exact_boundary(
    review_packet, tmp_path: Path, monkeypatch
) -> None:
    owner_path = _write_owner(
        tmp_path / "owner-entry-cap.jsonl", _owner_rows(review_packet)
    )
    monkeypatch.setattr(builder, "MAX_ONTOLOGY_ENTRY_COUNT", 222)
    build_firm_ontology_candidate_bundle(
        review_packet=review_packet, owner_adjudication_path=owner_path
    )

    monkeypatch.setattr(builder, "MAX_ONTOLOGY_ENTRY_COUNT", 221)
    with pytest.raises(FirmOntologyCandidateError) as exc_info:
        build_firm_ontology_candidate_bundle(
            review_packet=review_packet, owner_adjudication_path=owner_path
        )
    assert _reason(exc_info) is FirmOntologyCandidateRefusalReason.CANDIDATE_CAPACITY_EXCEEDED


def test_projected_output_byte_ceiling_has_exact_boundary(
    review_packet, tmp_path: Path, monkeypatch
) -> None:
    owner_path = _write_owner(
        tmp_path / "owner-projection-cap.jsonl", _owner_rows(review_packet)
    )
    baseline = build_firm_ontology_candidate_bundle(
        review_packet=review_packet, owner_adjudication_path=owner_path
    )
    ontology_entries = json.loads(baseline.ontology_bytes)["entries"]
    availability_entries = json.loads(baseline.availability_bytes)["entries"]
    exact_projection = max(
        2 + sum(len(canonical_json_bytes(item)) for item in ontology_entries),
        2 + sum(len(canonical_json_bytes(item)) for item in availability_entries),
    )
    monkeypatch.setattr(builder, "MAX_PROJECTED_ENTRY_BYTES", exact_projection)
    build_firm_ontology_candidate_bundle(
        review_packet=review_packet, owner_adjudication_path=owner_path
    )

    monkeypatch.setattr(builder, "MAX_PROJECTED_ENTRY_BYTES", exact_projection - 1)
    with pytest.raises(FirmOntologyCandidateError) as exc_info:
        build_firm_ontology_candidate_bundle(
            review_packet=review_packet, owner_adjudication_path=owner_path
        )
    assert _reason(exc_info) is FirmOntologyCandidateRefusalReason.CANDIDATE_CAPACITY_EXCEEDED


@pytest.mark.parametrize(
    ("owner", "name"),
    [
        ("canonical", "canonical_json_bytes"),
        ("canonical", "sha256_bytes"),
        ("canonical", "decode_utf8"),
        ("canonical", "strict_json_loads"),
        ("canonical", "parse_date"),
        ("canonical", "parse_utc_timestamp"),
        ("canonical", "require_identifier"),
        ("canonical", "require_int"),
        ("canonical", "require_sha256"),
        ("canonical", "require_text"),
        ("builder", "canonical_json_bytes"),
        ("builder", "sha256_bytes"),
        ("builder", "decode_utf8"),
        ("builder", "strict_json_loads"),
        ("builder", "parse_date"),
        ("builder", "parse_utc_timestamp"),
        ("builder", "require_identifier"),
        ("builder", "require_int"),
        ("builder", "require_sha256"),
        ("builder", "require_text"),
        ("builder", "_content_addressed_record"),
        ("builder", "_require_candidate_content_bindings"),
        ("ontology", "_validate_entry_set"),
        ("packet", "require_physical_firm_ontology_review_packet"),
        ("packet", "iter_physical_firm_owner_adjudication_template"),
        ("packet", "iter_physical_firm_ontology_review_rows"),
        ("composer", "FirmOntologyAvailabilityEntry"),
    ],
)
def test_each_pinned_dependency_rebinding_is_an_isolated_refusal(
    review_packet,
    tmp_path: Path,
    monkeypatch,
    owner: str,
    name: str,
) -> None:
    owner_rows = _owner_rows(review_packet)
    target = {
        "canonical": builder._canonical,
        "builder": builder,
        "ontology": builder._ontology,
        "packet": builder._packet,
        "composer": builder._composer,
    }[owner]
    monkeypatch.setattr(target, name, object())
    owner_path = _write_owner(
        tmp_path / f"dependency-{owner}-{name}.jsonl", owner_rows
    )
    with pytest.raises(FirmOntologyCandidateError) as exc_info:
        build_firm_ontology_candidate_bundle(
            review_packet=review_packet, owner_adjudication_path=owner_path
        )
    assert _reason(exc_info) is FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED


def test_module_has_no_network_outcome_or_action_surface() -> None:
    source = Path(builder.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert not any(
        imported == prefix or imported.startswith(prefix + ".")
        for imported in imports
        for prefix in ("requests", "urllib", "http", "socket", "quantconnect")
    )
    forbidden_calls = {
        "create_project",
        "compile_project",
        "backtest",
        "launch",
        "history",
        "add_equity",
        "submit_order",
    }
    assert not {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    } & forbidden_calls
    assert "independently_reviewed" not in {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("independently_reviewed_")
    }
