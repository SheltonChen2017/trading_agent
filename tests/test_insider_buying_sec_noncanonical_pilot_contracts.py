from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.insider_buying.sec_noncanonical_pilot_contracts as pilot_module
import research.insider_buying as insider_package
from research.insider_buying.sec_noncanonical_pilot_contracts import (
    SEC_NONCANONICAL_PILOT_DERIVED_JSON_VERSION,
    SEC_NONCANONICAL_PILOT_DERIVED_PROFILE_VERSION,
    SEC_NONCANONICAL_PILOT_MAX_TOTAL_XML_BYTES,
    SEC_NONCANONICAL_PILOT_MAX_XML_SOURCE_BYTES,
    SEC_NONCANONICAL_PILOT_MAX_METADATA_SOURCE_BYTES,
    SEC_NONCANONICAL_PILOT_MAX_ZIP_BYTES,
    PilotAccessionCandidateIdentity,
    PilotArtifactKind,
    PilotCompatibilityOutcome,
    PilotDerivedFlatIb1cProjectionIdentity,
    PilotFieldDerivation,
    PilotFieldProvenance,
    PilotFieldTransform,
    PilotOperationalOutcome,
    PilotReasonCount,
    PilotResourceMeasurement,
    PilotStageIdentity,
    PilotVerbatimArtifactIdentity,
    PilotZeroAuthority,
    SecNoncanonicalPilotContractError,
    SecNoncanonicalPilotOperationalReport,
    build_sec_noncanonical_pilot_manifest,
)


MODULE_PATH = Path(pilot_module.__file__)
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _zip(period: str, *, suffix: str = "") -> PilotVerbatimArtifactIdentity:
    return PilotVerbatimArtifactIdentity(
        relative_path=f"quarters/{period}/submissions{suffix}.zip",
        kind=PilotArtifactKind.QUARTERLY_ZIP,
        period=period,
        sha256=SHA_A if not suffix else SHA_B,
        size_bytes=100,
        source_url=f"https://www.sec.gov/files/{period.lower()}_form345.zip",
        retrieved_at_utc="2026-09-24T12:00:00+00:00",
        capture_git_commit="d" * 40,
    )


def _accession(index: int) -> str:
    return f"{index:010d}-26-{index:06d}"


def _accession_artifacts(
    period: str,
    accession: str,
    *,
    form_type: str = "4",
    xml_size: int = 100,
    prefix: str = "",
) -> tuple[PilotVerbatimArtifactIdentity, PilotVerbatimArtifactIdentity]:
    stem = f"{prefix}{accession}"
    metadata = PilotVerbatimArtifactIdentity(
        relative_path=f"metadata/{period}/{stem}.sgml",
        kind=PilotArtifactKind.VERBATIM_METADATA,
        period=period,
        sha256=SHA_B,
        size_bytes=120,
        source_url=(
            f"https://www.sec.gov/Archives/edgar/data/1/"
            f"{accession.replace('-', '')}/full-submission.txt"
        ),
        retrieved_at_utc="2026-09-24T12:00:00+00:00",
        capture_git_commit="d" * 40,
        accession_number=accession,
        form_type=form_type,
    )
    xml = PilotVerbatimArtifactIdentity(
        relative_path=f"xml/{period}/{stem}.xml",
        kind=PilotArtifactKind.PRIMARY_FORM4_XML,
        period=period,
        sha256=SHA_C,
        size_bytes=xml_size,
        source_url=(
            f"https://www.sec.gov/Archives/edgar/data/1/"
            f"{accession.replace('-', '')}/form4.xml"
        ),
        retrieved_at_utc="2026-09-24T12:00:00+00:00",
        capture_git_commit="d" * 40,
        accession_number=accession,
        form_type=form_type,
    )
    return metadata, xml


def _field(
    name: str,
    value: str,
    metadata: PilotVerbatimArtifactIdentity,
    xml: PilotVerbatimArtifactIdentity,
) -> PilotFieldDerivation:
    if name == "primary_document_sha256":
        return PilotFieldDerivation(
            field_name=name,
            value=xml.sha256,
            parent_relative_path=xml.relative_path,
            parent_sha256=xml.sha256,
            transform=PilotFieldTransform.PRIMARY_XML_SHA256_EXACT_BYTES,
            provenance=PilotFieldProvenance.EXACT_XML_SHA256,
        )
    accession_digits = (metadata.accession_number or "").replace("-", "")
    month = {"Q1": "01", "Q2": "04", "Q3": "07", "Q4": "10"}[metadata.period[-2:]]
    filing_day = f"{metadata.period[:4]}-{month}-15"
    values = {
        "accession_number": metadata.accession_number or "",
        "accepted_at": f"{filing_day}T14:30:00-05:00",
        "filing_date": filing_day,
        "form_type": metadata.form_type or "",
        "primary_document_url": (
            f"https://www.sec.gov/Archives/edgar/data/1/{accession_digits}/form4.xml"
        ),
        "original_accession_number": value,
    }
    transforms = {
        "accession_number": PilotFieldTransform.ACCESSION_FROM_METADATA,
        "accepted_at": PilotFieldTransform.ACCEPTED_AT_FROM_METADATA,
        "filing_date": PilotFieldTransform.FILING_DATE_FROM_METADATA,
        "form_type": PilotFieldTransform.FORM_TYPE_FROM_METADATA,
        "primary_document_url": PilotFieldTransform.PRIMARY_DOCUMENT_URL_FROM_METADATA,
        "original_accession_number": PilotFieldTransform.ORIGINAL_ACCESSION_FROM_METADATA,
    }
    transform = transforms[name]
    source_backed = True
    if name == "original_accession_number" and not value:
        if metadata.form_type == "4":
            transform = PilotFieldTransform.EMPTY_ORIGINAL_FROM_FORM_TYPE
        else:
            transform = PilotFieldTransform.MISSING_ORIGINAL_UNAVAILABLE
            source_backed = False
    return PilotFieldDerivation(
        field_name=name,
        value=values[name],
        parent_relative_path=metadata.relative_path,
        parent_sha256=metadata.sha256,
        transform=transform,
        provenance=PilotFieldProvenance.SOURCE_FIELD,
        source_backed=source_backed,
    )


def _projection(
    period: str,
    accession: str,
    *,
    form_type: str = "4",
    include_link: bool = False,
    xml_size: int = 100,
    prefix: str = "",
) -> tuple[
    tuple[PilotVerbatimArtifactIdentity, PilotVerbatimArtifactIdentity],
    PilotDerivedFlatIb1cProjectionIdentity,
]:
    metadata, xml = _accession_artifacts(
        period,
        accession,
        form_type=form_type,
        xml_size=xml_size,
        prefix=prefix,
    )
    fields = [
        _field(name, "", metadata, xml)
        for name in (
            "primary_document_url",
            "form_type",
            "filing_date",
            "accepted_at",
            "primary_document_sha256",
            "accession_number",
        )
    ]
    fields.append(
        _field(
            "original_accession_number",
            _accession(900000) if include_link else "",
            metadata,
            xml,
        )
    )
    return (metadata, xml), PilotDerivedFlatIb1cProjectionIdentity(
        period=period,
        accession_number=accession,
        form_type=form_type,
        fields=fields,  # type: ignore[arg-type]
    )


def _candidate(
    period: str,
    accession: str,
    form_type: str,
    zip_sha256: str,
    artifacts: tuple[PilotVerbatimArtifactIdentity, ...] = (),
) -> PilotAccessionCandidateIdentity:
    metadata = next(
        (item for item in artifacts if item.kind is PilotArtifactKind.VERBATIM_METADATA),
        None,
    )
    xml = next(
        (item for item in artifacts if item.kind is PilotArtifactKind.PRIMARY_FORM4_XML),
        None,
    )
    month = {"Q1": "01", "Q2": "04", "Q3": "07", "Q4": "10"}[period[-2:]]
    return PilotAccessionCandidateIdentity(
        period=period,
        accession_number=accession,
        form_type=form_type,
        filing_date=f"{period[:4]}-{month}-15",
        issuer_cik="0000000001",
        quarterly_zip_sha256=zip_sha256,
        submission_row_sha256=("e" if accession.endswith("1") else "f") * 64,
        metadata_relative_path=metadata.relative_path if metadata else None,
        xml_relative_path=xml.relative_path if xml else None,
    )


def _manifest():
    artifacts_1, projection_1 = _projection("2026Q1", _accession(1))
    artifacts_2, projection_2 = _projection(
        "2026Q2",
        _accession(2),
        form_type="4/A",
    )
    zip_1 = _zip("2026Q1")
    zip_2 = _zip("2026Q2")
    return build_sec_noncanonical_pilot_manifest(
        periods=["2026Q1", "2026Q2"],
        candidates=[
            _candidate("2026Q1", _accession(1), "4", zip_1.sha256, artifacts_1),
            _candidate("2026Q2", _accession(2), "4/A", zip_2.sha256, artifacts_2),
        ],
        artifacts=[zip_2, *artifacts_2, zip_1, *artifacts_1],
        projections=[projection_2, projection_1],
    )


def _report(manifest=None) -> SecNoncanonicalPilotOperationalReport:
    manifest = manifest or _manifest()
    return SecNoncanonicalPilotOperationalReport.for_manifest(
        manifest,
        parser_git_commit="d" * 40,
        accepted_count=1,
        refused_count=0,
        quarantined_count=1,
        reason_counts=[
            PilotReasonCount(
                PilotOperationalOutcome.QUARANTINED,
                "form4a_missing_source_backed_original_accession_link",
                1,
            ),
            PilotReasonCount(PilotOperationalOutcome.ACCEPTED, "accepted", 1),
        ],
        compatibility=PilotCompatibilityOutcome.PARTIALLY_COMPATIBLE,
        compatibility_reasons=["form4a_link_unavailable"],
        stage_identities=[PilotStageIdentity("IB-1A", "ib1a-fixture", SHA_A)],
    )


def test_manifest_is_deterministic_listed_only_and_noncanonical() -> None:
    manifest = _manifest()
    assert manifest.periods == ("2026Q1", "2026Q2")
    assert manifest.external_listed_only is True
    assert manifest.discovery_authorized is False
    assert manifest.optional_early_quarter_included is False
    assert manifest.canonical_corpus is False
    assert manifest.manifest_id.endswith(manifest.semantic_sha256[:16])
    assert manifest.to_payload()["optional_early_quarter_policy"] == (
        "excluded-from-this-end-to-end-manifest-and-evaluated-separately"
    )


def test_input_order_is_canonical_and_caller_containers_are_copied() -> None:
    first = _manifest()
    artifacts = list(reversed(first.artifacts))
    candidates = list(reversed(first.candidates))
    projections = list(reversed(first.projections))
    periods = list(first.periods)
    second = build_sec_noncanonical_pilot_manifest(
        periods=periods,
        candidates=candidates,
        artifacts=artifacts,
        projections=projections,
    )
    before = second.to_payload()
    artifacts.clear()
    candidates.clear()
    projections.clear()
    periods.clear()
    assert second.to_payload() == before == first.to_payload()


@pytest.mark.parametrize(
    "periods",
    [
        ["2026Q1"],
        ["2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2"],
        ["2026Q2", "2026Q1"],
        ["2026Q1", "2026Q1"],
        ["2025Q4", "2026Q2"],
    ],
)
def test_period_count_order_duplicates_and_gaps_fail_closed(periods) -> None:
    manifest = _manifest()
    with pytest.raises(SecNoncanonicalPilotContractError):
        build_sec_noncanonical_pilot_manifest(
            periods=periods,
            candidates=manifest.candidates,
            artifacts=manifest.artifacts,
            projections=manifest.projections,
        )


def test_exactly_one_quarter_zip_per_period_is_required() -> None:
    manifest = _manifest()
    without_zip = [
        item
        for item in manifest.artifacts
        if not (
            item.kind is PilotArtifactKind.QUARTERLY_ZIP
            and item.period == "2026Q2"
        )
    ]
    with pytest.raises(SecNoncanonicalPilotContractError, match="exactly one"):
        build_sec_noncanonical_pilot_manifest(
            periods=manifest.periods,
            candidates=manifest.candidates,
            artifacts=without_zip,
            projections=manifest.projections,
        )
    with pytest.raises(SecNoncanonicalPilotContractError, match="exactly one"):
        build_sec_noncanonical_pilot_manifest(
            periods=manifest.periods,
            candidates=manifest.candidates,
            artifacts=[*manifest.artifacts, _zip("2026Q1", suffix="-copy")],
            projections=manifest.projections,
        )


@pytest.mark.parametrize(
    "path",
    ["../escape.xml", "/absolute.xml", "C:/absolute.xml", "a/../b.xml", "a\\b.xml"],
)
def test_artifact_paths_refuse_absolute_traversal_and_backslash(path: str) -> None:
    with pytest.raises(SecNoncanonicalPilotContractError):
        dataclasses.replace(_manifest().artifacts[0], relative_path=path)


def test_case_colliding_paths_fail_closed() -> None:
    manifest = _manifest()
    target = manifest.artifacts[0]
    collision = dataclasses.replace(target, relative_path=target.relative_path.upper())
    with pytest.raises(SecNoncanonicalPilotContractError, match="case-colliding"):
        build_sec_noncanonical_pilot_manifest(
            periods=manifest.periods,
            candidates=manifest.candidates,
            artifacts=[*manifest.artifacts, collision],
            projections=manifest.projections,
        )


def test_artifact_capture_provenance_is_exact_and_role_bound() -> None:
    zip_artifact = _zip("2026Q1")
    with pytest.raises(SecNoncanonicalPilotContractError, match="does not match"):
        dataclasses.replace(
            zip_artifact,
            source_url="https://www.sec.gov/files/2026q2_form345.zip",
        )
    with pytest.raises(SecNoncanonicalPilotContractError, match="retrieval time"):
        dataclasses.replace(zip_artifact, retrieved_at_utc="2026-09-24T12:00:00Z")
    with pytest.raises(SecNoncanonicalPilotContractError, match="capture git commit"):
        dataclasses.replace(zip_artifact, capture_git_commit="ABC")

    _, xml = _accession_artifacts("2026Q1", _accession(1))
    with pytest.raises(SecNoncanonicalPilotContractError, match="accession"):
        dataclasses.replace(
            xml,
            source_url=(
                "https://www.sec.gov/Archives/edgar/data/1/"
                "000000000226000002/form4.xml"
            ),
        )


def test_xml_per_file_limit_is_exact() -> None:
    _accession_artifacts(
        "2026Q1",
        _accession(1),
        xml_size=SEC_NONCANONICAL_PILOT_MAX_XML_SOURCE_BYTES,
    )
    with pytest.raises(SecNoncanonicalPilotContractError, match="2 MiB"):
        _accession_artifacts(
            "2026Q1",
            _accession(1),
            xml_size=SEC_NONCANONICAL_PILOT_MAX_XML_SOURCE_BYTES + 1,
        )


def _many_manifest(xml_count: int, xml_size: int):
    zip_1, zip_2 = _zip("2026Q1"), _zip("2026Q2")
    artifacts = [zip_1, zip_2]
    candidates = []
    projections = []
    for index in range(1, xml_count + 1):
        period = "2026Q1" if index % 2 else "2026Q2"
        accession_artifacts, projection = _projection(
            period,
            _accession(index),
            xml_size=xml_size,
        )
        artifacts.extend(accession_artifacts)
        projections.append(projection)
        candidates.append(
            _candidate(
                period,
                _accession(index),
                "4",
                zip_1.sha256 if period == "2026Q1" else zip_2.sha256,
                accession_artifacts,
            )
        )
    return build_sec_noncanonical_pilot_manifest(
        periods=["2026Q1", "2026Q2"],
        candidates=candidates,
        artifacts=artifacts,
        projections=projections,
    )


def test_xml_count_and_total_byte_limits_fail_closed() -> None:
    with pytest.raises(SecNoncanonicalPilotContractError, match="256"):
        _many_manifest(257, 1)
    assert _many_manifest(32, SEC_NONCANONICAL_PILOT_MAX_XML_SOURCE_BYTES)
    with pytest.raises(SecNoncanonicalPilotContractError, match="64 MiB"):
        _many_manifest(33, SEC_NONCANONICAL_PILOT_MAX_XML_SOURCE_BYTES)


def test_xml_hash_is_explicitly_computed_from_exact_xml_identity() -> None:
    metadata, xml = _accession_artifacts("2026Q1", _accession(1))
    valid = _field("primary_document_sha256", "", metadata, xml)
    assert valid.value == valid.parent_sha256 == xml.sha256
    assert valid.provenance is PilotFieldProvenance.EXACT_XML_SHA256
    with pytest.raises(SecNoncanonicalPilotContractError, match="equal"):
        dataclasses.replace(valid, value=SHA_A)
    with pytest.raises(SecNoncanonicalPilotContractError, match="exact-byte"):
        dataclasses.replace(valid, transform=PilotFieldTransform.ACCESSION_FROM_METADATA)


def test_core_fields_require_source_provenance_and_listed_parent() -> None:
    manifest = _manifest()
    projection = manifest.projections[0]
    accepted_at = next(item for item in projection.fields if item.field_name == "accepted_at")
    forged = object.__new__(PilotFieldDerivation)
    for field in dataclasses.fields(accepted_at):
        object.__setattr__(forged, field.name, getattr(accepted_at, field.name))
    object.__setattr__(forged, "provenance", PilotFieldProvenance.EXACT_XML_SHA256)
    fields = tuple(forged if item is accepted_at else item for item in projection.fields)
    with pytest.raises(
        SecNoncanonicalPilotContractError,
        match="exact-byte|field-level provenance",
    ):
        dataclasses.replace(projection, fields=fields)

    bad_parent = dataclasses.replace(accepted_at, parent_sha256=SHA_A)
    forged_projection = dataclasses.replace(
        projection,
        fields=tuple(bad_parent if item is accepted_at else item for item in projection.fields),
    )
    with pytest.raises(SecNoncanonicalPilotContractError, match="listed artifact"):
        build_sec_noncanonical_pilot_manifest(
            periods=manifest.periods,
            candidates=manifest.candidates,
            artifacts=manifest.artifacts,
            projections=[forged_projection, manifest.projections[1]],
        )


@pytest.mark.parametrize(
    "field_name",
    [
        "accession_number",
        "accepted_at",
        "filing_date",
        "form_type",
        "primary_document_url",
    ],
)
def test_every_source_core_field_requires_its_exact_transform(
    field_name: str,
) -> None:
    projection = _manifest().projections[0]
    target = next(item for item in projection.fields if item.field_name == field_name)
    changed = dataclasses.replace(
        target,
        transform=PilotFieldTransform.ORIGINAL_ACCESSION_FROM_METADATA,
    )
    with pytest.raises(SecNoncanonicalPilotContractError, match="unreviewed"):
        dataclasses.replace(
            projection,
            fields=tuple(changed if item is target else item for item in projection.fields),
        )


def test_projected_primary_url_must_equal_listed_xml_source_url() -> None:
    manifest = _manifest()
    projection = manifest.projections[0]
    target = next(
        item for item in projection.fields if item.field_name == "primary_document_url"
    )
    alternate = dataclasses.replace(
        target,
        value=target.value.replace("form4.xml", "alternate.xml"),
    )
    changed = dataclasses.replace(
        projection,
        fields=tuple(alternate if item is target else item for item in projection.fields),
    )
    with pytest.raises(SecNoncanonicalPilotContractError, match="does not match"):
        build_sec_noncanonical_pilot_manifest(
            periods=manifest.periods,
            candidates=manifest.candidates,
            artifacts=manifest.artifacts,
            projections=[changed, manifest.projections[1]],
        )


def test_derived_projection_cannot_claim_verbatim_ib1c_bytes() -> None:
    projection = _manifest().projections[0]
    assert projection.direct_ib1c_v1_verbatim_claim is False
    with pytest.raises(SecNoncanonicalPilotContractError, match="verbatim"):
        dataclasses.replace(projection, direct_ib1c_v1_verbatim_claim=True)


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("filing_date", "2026-02-30", "real calendar date"),
        ("filing_date", "2026-04-15", "projection period"),
        ("accepted_at", "2026-01-15T14:30:00Z", "explicit offset"),
        ("accepted_at", "2026-01-15T14:30:00.1-05:00", "explicit offset"),
        ("primary_document_url", "https://example.com/form4.xml", "SEC Archives"),
        (
            "primary_document_url",
            "https://www.sec.gov/Archives/edgar/data/1/999999999926999999/form4.xml",
            "SEC Archives",
        ),
    ],
)
def test_ib1c_flat_row_syntax_fails_closed(field_name: str, value: str, message: str) -> None:
    projection = next(item for item in _manifest().projections if item.period == "2026Q1")
    target = next(item for item in projection.fields if item.field_name == field_name)
    changed = dataclasses.replace(target, value=value)
    with pytest.raises(SecNoncanonicalPilotContractError, match=message):
        dataclasses.replace(
            projection,
            fields=tuple(changed if item is target else item for item in projection.fields),
        )


def test_form4a_without_source_link_is_quarantined_and_not_ib1e_eligible() -> None:
    amendment = next(item for item in _manifest().projections if item.form_type == "4/A")
    assert amendment.disposition.value == "quarantined"
    assert amendment.quarantine_reason == (
        "form4a_missing_source_backed_original_accession_link"
    )
    assert amendment.ib1e_eligible is False


def test_cross_period_form4a_with_source_backed_original_link_can_be_eligible() -> None:
    amendment_artifacts, amendment = _projection(
        "2026Q2",
        _accession(2),
        form_type="4/A",
        include_link=True,
    )
    assert amendment.disposition.value == "accepted"
    assert amendment.quarantine_reason is None
    assert amendment.ib1e_eligible is False

    original_accession = _accession(900000)
    original_artifacts, original = _projection("2026Q1", original_accession)
    zip_1, zip_2 = _zip("2026Q1"), _zip("2026Q2")
    manifest = build_sec_noncanonical_pilot_manifest(
        periods=["2026Q1", "2026Q2"],
        candidates=[
            _candidate("2026Q1", original_accession, "4", zip_1.sha256, original_artifacts),
            _candidate("2026Q2", amendment.accession_number, "4/A", zip_2.sha256, amendment_artifacts),
        ],
        artifacts=[zip_1, zip_2, *original_artifacts, *amendment_artifacts],
        projections=[amendment, original],
    )
    assert manifest.projection_is_ib1e_eligible(amendment) is True


def test_candidate_and_projection_accessions_are_globally_unique() -> None:
    manifest = _manifest()
    first_candidate = manifest.candidates[0]
    second_zip = next(
        item
        for item in manifest.artifacts
        if item.kind is PilotArtifactKind.QUARTERLY_ZIP and item.period == "2026Q2"
    )
    with pytest.raises(SecNoncanonicalPilotContractError, match="across periods"):
        build_sec_noncanonical_pilot_manifest(
            periods=manifest.periods,
            candidates=[
                *manifest.candidates,
                dataclasses.replace(
                    first_candidate,
                    period="2026Q2",
                    filing_date="2026-04-15",
                    quarterly_zip_sha256=second_zip.sha256,
                    metadata_relative_path=None,
                    xml_relative_path=None,
                ),
            ],
            artifacts=manifest.artifacts,
            projections=manifest.projections,
        )

    with pytest.raises(SecNoncanonicalPilotContractError, match="across periods"):
        build_sec_noncanonical_pilot_manifest(
            periods=manifest.periods,
            candidates=manifest.candidates,
            artifacts=manifest.artifacts,
            projections=[*manifest.projections, manifest.projections[0]],
        )


def test_candidate_upstream_date_year_and_issuer_lineage_are_exact() -> None:
    manifest = _manifest()
    candidate = manifest.candidates[0]
    with pytest.raises(SecNoncanonicalPilotContractError, match="accession year"):
        dataclasses.replace(
            candidate,
            accession_number="0000000001-25-000001",
        )
    with pytest.raises(SecNoncanonicalPilotContractError, match="cannot be zero"):
        dataclasses.replace(candidate, issuer_cik="0000000000")
    with pytest.raises(SecNoncanonicalPilotContractError, match="quarterly ZIP hash"):
        build_sec_noncanonical_pilot_manifest(
            periods=manifest.periods,
            candidates=[
                dataclasses.replace(candidate, quarterly_zip_sha256=SHA_B),
                *manifest.candidates[1:],
            ],
            artifacts=manifest.artifacts,
            projections=manifest.projections,
        )

    changed_date = dataclasses.replace(candidate, filing_date="2026-01-16")
    with pytest.raises(SecNoncanonicalPilotContractError, match="projected filing date"):
        build_sec_noncanonical_pilot_manifest(
            periods=manifest.periods,
            candidates=[changed_date, *manifest.candidates[1:]],
            artifacts=manifest.artifacts,
            projections=manifest.projections,
        )

    changed_issuer = dataclasses.replace(candidate, issuer_cik="0000000002")
    with pytest.raises(SecNoncanonicalPilotContractError, match="issuer CIK"):
        build_sec_noncanonical_pilot_manifest(
            periods=manifest.periods,
            candidates=[changed_issuer, *manifest.candidates[1:]],
            artifacts=manifest.artifacts,
            projections=manifest.projections,
        )


def test_projection_eligibility_rejects_foreign_projection() -> None:
    manifest = _manifest()
    foreign_artifacts, foreign = _projection("2026Q1", _accession(44))
    assert foreign_artifacts
    assert manifest.projection_is_ib1e_eligible(foreign) is False
    with pytest.raises(SecNoncanonicalPilotContractError, match="manifest member"):
        manifest.projection_quarantine_reason(foreign)


@pytest.mark.parametrize(
    "original_accepted_at",
    [
        "2026-04-15T14:30:00-05:00",
        "2026-04-15T15:30:00-05:00",
    ],
)
def test_form4a_requires_original_acceptance_before_amendment(
    original_accepted_at: str,
) -> None:
    original_accession = _accession(900000)
    original_artifacts, original = _projection("2026Q2", original_accession)
    accepted_field = next(
        item for item in original.fields if item.field_name == "accepted_at"
    )
    original = dataclasses.replace(
        original,
        fields=tuple(
            dataclasses.replace(item, value=original_accepted_at)
            if item is accepted_field
            else item
            for item in original.fields
        ),
    )
    amendment_artifacts, amendment = _projection(
        "2026Q2",
        _accession(2),
        form_type="4/A",
        include_link=True,
    )
    zip_1, zip_2 = _zip("2026Q1"), _zip("2026Q2")
    manifest = build_sec_noncanonical_pilot_manifest(
        periods=["2026Q1", "2026Q2"],
        candidates=[
            _candidate("2026Q2", original_accession, "4", zip_2.sha256, original_artifacts),
            _candidate("2026Q2", amendment.accession_number, "4/A", zip_2.sha256, amendment_artifacts),
        ],
        artifacts=[zip_1, zip_2, *original_artifacts, *amendment_artifacts],
        projections=[original, amendment],
    )
    assert manifest.projection_is_ib1e_eligible(amendment) is False
    assert manifest.projection_quarantine_reason(amendment) == (
        "form4a_original_acceptance_not_before_amendment"
    )


@pytest.mark.parametrize("original_form_type", ["4", "4/A"])
def test_form4a_target_must_be_an_in_sample_projected_original(
    original_form_type: str,
) -> None:
    original_accession = _accession(900000)
    amendment_artifacts, amendment = _projection(
        "2026Q2",
        _accession(2),
        form_type="4/A",
        include_link=True,
    )
    zip_1, zip_2 = _zip("2026Q1"), _zip("2026Q2")
    manifest = build_sec_noncanonical_pilot_manifest(
        periods=["2026Q1", "2026Q2"],
        candidates=[
            _candidate(
                "2026Q1",
                original_accession,
                original_form_type,
                zip_1.sha256,
            ),
            _candidate(
                "2026Q2",
                amendment.accession_number,
                "4/A",
                zip_2.sha256,
                amendment_artifacts,
            ),
        ],
        artifacts=[zip_1, zip_2, *amendment_artifacts],
        projections=[amendment],
    )
    assert manifest.projection_is_ib1e_eligible(amendment) is False
    assert manifest.projection_quarantine_reason(amendment) == (
        "form4a_original_form4_not_in_sample"
    )


def test_form4a_target_must_share_the_amendment_issuer() -> None:
    original_accession = _accession(900000)
    original_artifacts, original = _projection("2026Q1", original_accession)
    amendment_artifacts, amendment = _projection(
        "2026Q2",
        _accession(2),
        form_type="4/A",
        include_link=True,
    )
    rebound_metadata = dataclasses.replace(
        amendment_artifacts[0],
        source_url=amendment_artifacts[0].source_url.replace(
            "/edgar/data/1/",
            "/edgar/data/2/",
        ),
    )
    rebound_xml = dataclasses.replace(
        amendment_artifacts[1],
        source_url=amendment_artifacts[1].source_url.replace(
            "/edgar/data/1/",
            "/edgar/data/2/",
        ),
    )
    rebound_url_field = next(
        item for item in amendment.fields if item.field_name == "primary_document_url"
    )
    amendment = dataclasses.replace(
        amendment,
        fields=tuple(
            dataclasses.replace(rebound_url_field, value=rebound_xml.source_url)
            if item is rebound_url_field
            else item
            for item in amendment.fields
        ),
    )
    amendment_artifacts = (rebound_metadata, rebound_xml)
    zip_1, zip_2 = _zip("2026Q1"), _zip("2026Q2")
    manifest = build_sec_noncanonical_pilot_manifest(
        periods=["2026Q1", "2026Q2"],
        candidates=[
            _candidate("2026Q1", original_accession, "4", zip_1.sha256, original_artifacts),
            dataclasses.replace(
                _candidate(
                    "2026Q2",
                    amendment.accession_number,
                    "4/A",
                    zip_2.sha256,
                    amendment_artifacts,
                ),
                issuer_cik="0000000002",
            ),
        ],
        artifacts=[zip_1, zip_2, *original_artifacts, *amendment_artifacts],
        projections=[original, amendment],
    )
    assert manifest.projection_is_ib1e_eligible(amendment) is False
    assert manifest.projection_quarantine_reason(amendment) == (
        "form4a_original_issuer_mismatch"
    )


def test_report_exactly_accounts_for_every_input_with_named_reasons() -> None:
    report = _report()
    assert report.input_count == 2
    assert report.accepted_count + report.refused_count + report.quarantined_count == 2
    assert report.authority.research_looks == 0
    assert report.noncanonical is True
    assert report.operational_evidence_only is True
    with pytest.raises(SecNoncanonicalPilotContractError, match="exactly account"):
        dataclasses.replace(report, input_count=3)
    with pytest.raises(SecNoncanonicalPilotContractError, match="named accepted"):
        dataclasses.replace(report, accepted_count=0, refused_count=1)


def test_report_requires_named_resources_and_consistent_compatibility() -> None:
    report = _report()
    with pytest.raises(SecNoncanonicalPilotContractError, match="resource"):
        dataclasses.replace(report, resource_measurements=[])
    with pytest.raises(SecNoncanonicalPilotContractError, match="must be unique"):
        dataclasses.replace(
            report,
            compatibility_reasons=["same_reason", "same_reason"],
        )
    with pytest.raises(SecNoncanonicalPilotContractError, match="COMPATIBLE"):
        dataclasses.replace(
            report,
            compatibility=PilotCompatibilityOutcome.COMPATIBLE,
        )
    full_stages = [
        PilotStageIdentity(stage, f"{stage.lower()}-fixture", chr(97 + index) * 64)
        for index, stage in enumerate(("IB-1A", "IB-1B", "IB-1C", "IB-1D", "IB-1E"))
    ]
    with pytest.raises(SecNoncanonicalPilotContractError, match="all inputs accepted"):
        dataclasses.replace(
            report,
            compatibility=PilotCompatibilityOutcome.COMPATIBLE,
            compatibility_reasons=[],
            stage_identities=full_stages,
        )


def test_report_binds_manifest_projection_and_optional_stage_ids() -> None:
    manifest = _manifest()
    report = _report(manifest)
    report.verify_manifest(manifest)
    assert report.stage_identities[0].stage == "IB-1A"
    with pytest.raises(SecNoncanonicalPilotContractError, match="factory binding"):
        dataclasses.replace(report, manifest_sha256=SHA_A)


def test_report_requires_full_lowercase_parser_commit_and_stage_prefix() -> None:
    report = _report()
    with pytest.raises(SecNoncanonicalPilotContractError, match="parser git commit"):
        dataclasses.replace(report, parser_git_commit="ABC")
    with pytest.raises(SecNoncanonicalPilotContractError, match="IB-1A prefix"):
        dataclasses.replace(
            report,
            stage_identities=[PilotStageIdentity("IB-1B", "ib1b-fixture", SHA_A)],
        )
    assert dataclasses.replace(
        report,
        stage_identities=[
            PilotStageIdentity("IB-1B", "ib1b-fixture", SHA_B),
            PilotStageIdentity("IB-1A", "ib1a-fixture", SHA_A),
        ],
    ).stage_identities[1].stage == "IB-1B"


def test_for_manifest_derives_input_count_and_retains_prequarantine() -> None:
    manifest = _manifest()
    with pytest.raises(SecNoncanonicalPilotContractError, match="derived"):
        SecNoncanonicalPilotOperationalReport.for_manifest(
            manifest,
            input_count=2,
        )
    report = _report(manifest)
    assert report.input_count == len(manifest.projections)
    with pytest.raises(SecNoncanonicalPilotContractError, match="exactly retain"):
        dataclasses.replace(
            report,
            accepted_count=2,
            quarantined_count=0,
            reason_counts=[PilotReasonCount(PilotOperationalOutcome.ACCEPTED, "accepted", 2)],
        ).verify_manifest(manifest)


def test_candidate_inventory_allows_named_unprojected_refusals() -> None:
    manifest = _manifest()
    with pytest.raises(SecNoncanonicalPilotContractError, match="at least one"):
        build_sec_noncanonical_pilot_manifest(
            periods=manifest.periods,
            candidates=[],
            artifacts=[
                item
                for item in manifest.artifacts
                if item.kind is PilotArtifactKind.QUARTERLY_ZIP
            ],
            projections=[],
        )
    extra = _candidate(
        "2026Q1",
        _accession(3),
        "4",
        next(
            item.sha256
            for item in manifest.artifacts
            if item.kind is PilotArtifactKind.QUARTERLY_ZIP and item.period == "2026Q1"
        ),
    )
    expanded = build_sec_noncanonical_pilot_manifest(
        periods=manifest.periods,
        candidates=[*manifest.candidates, extra],
        artifacts=manifest.artifacts,
        projections=manifest.projections,
    )
    assert expanded.unprojected_candidate_count == 1
    report = SecNoncanonicalPilotOperationalReport.for_manifest(
        expanded,
        parser_git_commit="d" * 40,
        accepted_count=1,
        refused_count=1,
        quarantined_count=1,
        reason_counts=[
            PilotReasonCount(PilotOperationalOutcome.ACCEPTED, "accepted", 1),
            PilotReasonCount(
                PilotOperationalOutcome.QUARANTINED,
                "form4a_missing_source_backed_original_accession_link",
                1,
            ),
            PilotReasonCount(
                PilotOperationalOutcome.REFUSED,
                "unprojected_candidate",
                1,
            ),
        ],
        compatibility=PilotCompatibilityOutcome.PARTIALLY_COMPATIBLE,
        compatibility_reasons=["one_candidate_unprojected"],
        stage_identities=[PilotStageIdentity("IB-1A", "ib1a-fixture", SHA_A)],
    )
    report.verify_manifest(expanded)
    assert next(
        item.value
        for item in report.resource_measurements
        if item.name == "candidate_count"
    ) == 3
    with pytest.raises(SecNoncanonicalPilotContractError, match="unprojected"):
        dataclasses.replace(
            report,
            reason_counts=[
                item
                if item.outcome is not PilotOperationalOutcome.REFUSED
                else dataclasses.replace(item, reason="runtime_refusal")
                for item in report.reason_counts
            ],
        ).verify_manifest(expanded)


def test_derived_flat_json_bytes_and_profile_are_exactly_bound() -> None:
    projection = _manifest().projections[0]
    expected = (canonical_json(projection.flat_payload()) + "\n").encode("utf-8")
    payload = projection.to_payload()["derived_json"]
    assert projection.derived_json_bytes == expected
    assert projection.derived_json_sha256 == hash_bytes(expected)
    assert projection.derived_json_size_bytes == len(expected)
    assert payload["sha256"] == hash_bytes(expected)
    assert payload["size_bytes"] == len(expected)
    assert payload["flat_payload"] == projection.flat_payload()
    assert payload["profile_sha256"] == projection.profile_sha256
    assert projection.profile_sha256 == hash_payload(projection.profile_payload())
    assert payload["profile"] == projection.profile_payload()
    assert SEC_NONCANONICAL_PILOT_DERIVED_JSON_VERSION == (
        "INSETF-IB2-PILOT-DERIVED-FLAT-JSON-v1"
    )
    assert payload["serialization_version"] == (
        "INSETF-IB2-PILOT-DERIVED-FLAT-JSON-v1"
    )
    assert SEC_NONCANONICAL_PILOT_DERIVED_PROFILE_VERSION == (
        "INSETF-IB2-PILOT-IB1C-PROFILE-v1"
    )
    assert payload["profile"]["profile_id"] == (
        "noncanonical-pilot-derived-flat-ib1c-v1"
    )
    assert projection.direct_ib1c_v1_ingest_authorized is False
    assert projection.direct_ib1c_v1_verbatim_claim is False


def test_every_field_transform_has_an_exact_source_locator() -> None:
    manifest = _manifest()
    original = next(item for item in manifest.projections if item.form_type == "4")
    expected = {
        "accession_number": "verbatim-metadata.accession_number",
        "accepted_at": "verbatim-metadata.accepted_at",
        "filing_date": "verbatim-metadata.filing_date",
        "form_type": "verbatim-metadata.form_type",
        "primary_document_sha256": "exact-primary-xml-bytes",
        "primary_document_url": "verbatim-metadata.primary_document_url",
        "original_accession_number": "verbatim-metadata.form_type",
    }
    assert {
        item.field_name: item.to_payload()["source_locator"]
        for item in original.fields
    } == expected

    missing_link_amendment = next(
        item for item in manifest.projections if item.form_type == "4/A"
    )
    missing_link = next(
        item
        for item in missing_link_amendment.fields
        if item.field_name == "original_accession_number"
    )
    assert missing_link.to_payload()["source_locator"] == (
        "verbatim-metadata.original_accession_number-unavailable"
    )

    _, linked_amendment = _projection(
        "2026Q2",
        _accession(22),
        form_type="4/A",
        include_link=True,
    )
    linked = next(
        item
        for item in linked_amendment.fields
        if item.field_name == "original_accession_number"
    )
    assert linked.to_payload()["source_locator"] == (
        "verbatim-metadata.original_accession_number"
    )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("direct_ib1c_v1_verbatim_claim", True),
        ("direct_ib1c_v1_ingest_authorized", True),
        ("official_sec_profile_verified", True),
        ("canonical_evidence", True),
    ],
)
def test_projection_outer_scope_flags_fail_closed(field_name: str, value: bool) -> None:
    with pytest.raises(SecNoncanonicalPilotContractError):
        dataclasses.replace(_manifest().projections[0], **{field_name: value})


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("external_listed_only", False),
        ("discovery_authorized", True),
        ("optional_early_quarter_included", True),
        ("canonical_corpus", True),
    ],
)
def test_manifest_outer_scope_flags_fail_closed(field_name: str, value: bool) -> None:
    with pytest.raises(SecNoncanonicalPilotContractError):
        dataclasses.replace(_manifest(), **{field_name: value})


@pytest.mark.parametrize("field_name", ["operational_evidence_only", "noncanonical"])
def test_report_outer_scope_flags_fail_closed(field_name: str) -> None:
    with pytest.raises(SecNoncanonicalPilotContractError):
        dataclasses.replace(_report(), **{field_name: False})


def test_report_requires_factory_and_exact_zero_authority_type() -> None:
    report = _report()
    with pytest.raises(SecNoncanonicalPilotContractError, match="for_manifest"):
        dataclasses.replace(report, _factory_seal=None)
    assert report._factory_seal is not None
    forged_seal = dataclasses.replace(
        report._factory_seal,
        constraints=(len(_manifest().projections), 0, ()),
    )
    with pytest.raises(SecNoncanonicalPilotContractError, match="factory binding"):
        dataclasses.replace(report, _factory_seal=forged_seal)

    class ForgedAuthority(PilotZeroAuthority):
        def __post_init__(self) -> None:
            pass

    with pytest.raises(SecNoncanonicalPilotContractError, match="exact zero-authority"):
        dataclasses.replace(report, authority=ForgedAuthority())


def test_field_source_backing_and_identity_drift_fail_closed() -> None:
    projection = _manifest().projections[0]
    accession = next(item for item in projection.fields if item.field_name == "accession_number")
    with pytest.raises(SecNoncanonicalPilotContractError, match="source_backed"):
        dataclasses.replace(accession, source_backed=False)
    with pytest.raises(SecNoncanonicalPilotContractError, match="accession"):
        dataclasses.replace(
            projection,
            fields=tuple(
                dataclasses.replace(accession, value=_accession(99))
                if item is accession
                else item
                for item in projection.fields
            ),
        )
    form_type = next(item for item in projection.fields if item.field_name == "form_type")
    with pytest.raises(SecNoncanonicalPilotContractError, match="form type"):
        dataclasses.replace(
            projection,
            fields=tuple(
                dataclasses.replace(form_type, value="4/A")
                if item is form_type
                else item
                for item in projection.fields
            ),
        )


def test_amendment_link_transform_self_and_form4_directions_fail_closed() -> None:
    _, amendment = _projection(
        "2026Q1",
        _accession(2),
        form_type="4/A",
        include_link=True,
    )
    link = next(item for item in amendment.fields if item.field_name == "original_accession_number")
    with pytest.raises(SecNoncanonicalPilotContractError, match="reviewed source transform"):
        dataclasses.replace(
            amendment,
            fields=tuple(
                dataclasses.replace(
                    link,
                    transform=PilotFieldTransform.EMPTY_ORIGINAL_FROM_FORM_TYPE,
                )
                if item is link
                else item
                for item in amendment.fields
            ),
        )
    with pytest.raises(SecNoncanonicalPilotContractError, match="itself"):
        dataclasses.replace(
            amendment,
            fields=tuple(
                dataclasses.replace(link, value=amendment.accession_number)
                if item is link
                else item
                for item in amendment.fields
            ),
        )

    missing_amendment = next(
        item for item in _manifest().projections if item.form_type == "4/A"
    )
    missing_link = next(
        item
        for item in missing_amendment.fields
        if item.field_name == "original_accession_number"
    )
    with pytest.raises(SecNoncanonicalPilotContractError, match="unavailable transform"):
        dataclasses.replace(
            missing_amendment,
            fields=tuple(
                dataclasses.replace(
                    missing_link,
                    transform=PilotFieldTransform.ORIGINAL_ACCESSION_FROM_METADATA,
                    source_backed=True,
                )
                if item is missing_link
                else item
                for item in missing_amendment.fields
            ),
        )

    original = _manifest().projections[0]
    original_link = next(
        item for item in original.fields if item.field_name == "original_accession_number"
    )
    with pytest.raises(SecNoncanonicalPilotContractError, match="deterministic empty"):
        dataclasses.replace(
            original,
            fields=tuple(
                dataclasses.replace(
                    original_link,
                    value=_accession(9),
                    transform=PilotFieldTransform.ORIGINAL_ACCESSION_FROM_METADATA,
                )
                if item is original_link
                else item
                for item in original.fields
            ),
        )


@pytest.mark.parametrize(
    "url",
    [
        "https://www.sec.gov/foo/000000000126000001/../unrelated.txt",
        "https://www.sec.gov/foo//000000000126000001/file.txt",
        "https://www.sec.gov/foo/x000000000126000001y/file.txt",
    ],
)
def test_metadata_urls_refuse_traversal_empty_and_substring_segments(url: str) -> None:
    metadata, _ = _accession_artifacts("2026Q1", _accession(1))
    with pytest.raises(SecNoncanonicalPilotContractError, match="accession"):
        dataclasses.replace(metadata, source_url=url)


@pytest.mark.parametrize(
    "url",
    [
        (
            "https://www.sec.gov/Archives/edgar/data/999/"
            "000000000126000001/full-submission.txt"
        ),
        (
            "https://www.sec.gov/Archives/edgar/data/1/"
            "000000000126000001/extra/full-submission.txt"
        ),
    ],
)
def test_metadata_archives_url_binds_exact_candidate_issuer_lineage(
    url: str,
) -> None:
    manifest = _manifest()
    metadata = next(
        item
        for item in manifest.artifacts
        if item.kind is PilotArtifactKind.VERBATIM_METADATA
        and item.period == "2026Q1"
    )
    changed = dataclasses.replace(metadata, source_url=url)
    with pytest.raises(SecNoncanonicalPilotContractError, match="issuer lineage"):
        build_sec_noncanonical_pilot_manifest(
            periods=manifest.periods,
            candidates=manifest.candidates,
            artifacts=[
                changed if item.relative_path == metadata.relative_path else item
                for item in manifest.artifacts
            ],
            projections=manifest.projections,
        )


def test_acceptance_unknown_offset_window_and_retrieval_order_fail_closed() -> None:
    projection = _manifest().projections[0]
    accepted = next(item for item in projection.fields if item.field_name == "accepted_at")
    for value, message in (
        ("2026-01-15T14:30:00-00:00", "unknown"),
        ("2026-01-16T06:00:00+00:00", "filing-day window"),
    ):
        changed = dataclasses.replace(accepted, value=value)
        with pytest.raises(SecNoncanonicalPilotContractError, match=message):
            dataclasses.replace(
                projection,
                fields=tuple(changed if item is accepted else item for item in projection.fields),
            )

    manifest = _manifest()
    metadata = next(
        item
        for item in manifest.artifacts
        if item.kind is PilotArtifactKind.VERBATIM_METADATA and item.period == "2026Q1"
    )
    early = dataclasses.replace(metadata, retrieved_at_utc="2026-01-15T18:00:00+00:00")
    with pytest.raises(SecNoncanonicalPilotContractError, match="precede acceptance"):
        build_sec_noncanonical_pilot_manifest(
            periods=manifest.periods,
            candidates=manifest.candidates,
            artifacts=[early if item is metadata else item for item in manifest.artifacts],
            projections=manifest.projections,
        )


def test_zip_and_metadata_limits_match_existing_boundaries() -> None:
    assert dataclasses.replace(_zip("2026Q1"), size_bytes=SEC_NONCANONICAL_PILOT_MAX_ZIP_BYTES)
    with pytest.raises(SecNoncanonicalPilotContractError, match="512 MiB"):
        dataclasses.replace(
            _zip("2026Q1"),
            size_bytes=SEC_NONCANONICAL_PILOT_MAX_ZIP_BYTES + 1,
        )
    metadata, _ = _accession_artifacts("2026Q1", _accession(1))
    assert dataclasses.replace(
        metadata,
        size_bytes=SEC_NONCANONICAL_PILOT_MAX_METADATA_SOURCE_BYTES,
    )
    with pytest.raises(SecNoncanonicalPilotContractError, match="2 MiB"):
        dataclasses.replace(
            metadata,
            size_bytes=SEC_NONCANONICAL_PILOT_MAX_METADATA_SOURCE_BYTES + 1,
        )


@pytest.mark.parametrize(
    "change",
    [
        {"manifest_id": "other-manifest"},
        {"manifest_sha256": SHA_A},
        {"candidate_inventory_sha256": SHA_A},
        {"projection_inventory_sha256": SHA_A},
    ],
)
def test_report_factory_pins_every_manifest_identity(change) -> None:
    with pytest.raises(SecNoncanonicalPilotContractError, match="factory binding"):
        dataclasses.replace(_report(), **change)


def test_report_verify_manifest_rechecks_a_corrupted_identity() -> None:
    manifest = _manifest()
    report = _report(manifest)
    object.__setattr__(report, "manifest_sha256", SHA_A)
    with pytest.raises(SecNoncanonicalPilotContractError, match="exact pilot manifest"):
        report.verify_manifest(manifest)


def test_report_resources_input_count_and_unprojected_guard_are_pinned() -> None:
    manifest = _manifest()
    report = _report(manifest)
    assert {
        item.name: (item.value, item.unit)
        for item in report.resource_measurements
    } == {
        "artifact_count": (6, "count"),
        "candidate_count": (2, "count"),
        "declared_input_bytes": (640, "bytes"),
        "metadata_bytes": (240, "bytes"),
        "metadata_count": (2, "count"),
        "xml_bytes": (200, "bytes"),
        "xml_count": (2, "count"),
    }
    changed_resources = list(report.resource_measurements)
    changed_resources[0] = dataclasses.replace(
        changed_resources[0],
        value=changed_resources[0].value + 1,
    )
    with pytest.raises(SecNoncanonicalPilotContractError, match="resource"):
        dataclasses.replace(report, resource_measurements=changed_resources)
    with pytest.raises(SecNoncanonicalPilotContractError, match="unique"):
        dataclasses.replace(
            report,
            resource_measurements=[*report.resource_measurements, report.resource_measurements[0]],
        )
    with pytest.raises(SecNoncanonicalPilotContractError, match="factory binding"):
        dataclasses.replace(
            report,
            input_count=3,
            refused_count=1,
            reason_counts=[
                *report.reason_counts,
                PilotReasonCount(PilotOperationalOutcome.REFUSED, "runtime_refusal", 1),
            ],
        )


def test_compatibility_stage_semantics_and_stage_hash_are_exact() -> None:
    with pytest.raises(SecNoncanonicalPilotContractError, match="sha256"):
        PilotStageIdentity("IB-1A", "ib1a-fixture", "bad")
    full = [
        PilotStageIdentity(stage, f"{stage.lower()}-fixture", chr(97 + index) * 64)
        for index, stage in enumerate(("IB-1A", "IB-1B", "IB-1C", "IB-1D", "IB-1E"))
    ]
    artifacts, projection = _projection("2026Q1", _accession(1))
    zip_1, zip_2 = _zip("2026Q1"), _zip("2026Q2")
    accepted_manifest = build_sec_noncanonical_pilot_manifest(
        periods=["2026Q1", "2026Q2"],
        candidates=[
            _candidate("2026Q1", projection.accession_number, "4", zip_1.sha256, artifacts),
        ],
        artifacts=[zip_1, zip_2, *artifacts],
        projections=[projection],
    )
    compatible = SecNoncanonicalPilotOperationalReport.for_manifest(
        accepted_manifest,
        parser_git_commit="d" * 40,
        accepted_count=1,
        refused_count=0,
        quarantined_count=0,
        reason_counts=[
            PilotReasonCount(PilotOperationalOutcome.ACCEPTED, "accepted", 1),
        ],
        compatibility=PilotCompatibilityOutcome.COMPATIBLE,
        compatibility_reasons=[],
        stage_identities=full,
    )
    assert len(compatible.stage_identities) == 5
    report = _report()
    with pytest.raises(SecNoncanonicalPilotContractError, match="NOT_RUN"):
        dataclasses.replace(report, compatibility=PilotCompatibilityOutcome.NOT_RUN)
    not_run_manifest = build_sec_noncanonical_pilot_manifest(
        periods=["2026Q1", "2026Q2"],
        candidates=[_candidate("2026Q1", _accession(3), "4", zip_1.sha256)],
        artifacts=[zip_1, zip_2],
        projections=[],
    )
    not_run = SecNoncanonicalPilotOperationalReport.for_manifest(
        not_run_manifest,
        parser_git_commit="d" * 40,
        accepted_count=0,
        refused_count=1,
        quarantined_count=0,
        reason_counts=[
            PilotReasonCount(
                PilotOperationalOutcome.REFUSED,
                "unprojected_candidate",
                1,
            ),
        ],
        compatibility=PilotCompatibilityOutcome.NOT_RUN,
        compatibility_reasons=["not_started"],
        stage_identities=[],
    )
    assert not not_run.stage_identities


def test_zero_byte_bad_hash_bad_period_and_zip_role_fail_closed() -> None:
    artifact = _zip("2026Q1")
    for changes in (
        {"size_bytes": 0},
        {"sha256": "bad"},
        {"period": "2005Q4", "source_url": "https://www.sec.gov/files/2005q4_form345.zip"},
        {"accession_number": _accession(1), "form_type": "4"},
    ):
        with pytest.raises(SecNoncanonicalPilotContractError):
            dataclasses.replace(artifact, **changes)


def test_cross_accession_wrong_kind_and_duplicate_artifact_guards() -> None:
    manifest = _manifest()
    projection = manifest.projections[0]
    accepted = next(item for item in projection.fields if item.field_name == "accepted_at")
    other_metadata = next(
        item
        for item in manifest.artifacts
        if item.kind is PilotArtifactKind.VERBATIM_METADATA
        and item.accession_number != projection.accession_number
    )
    crossed = dataclasses.replace(
        accepted,
        parent_relative_path=other_metadata.relative_path,
        parent_sha256=other_metadata.sha256,
    )
    crossed_projection = dataclasses.replace(
        projection,
        fields=tuple(crossed if item is accepted else item for item in projection.fields),
    )
    with pytest.raises(SecNoncanonicalPilotContractError, match="crosses accession"):
        build_sec_noncanonical_pilot_manifest(
            periods=manifest.periods,
            candidates=manifest.candidates,
            artifacts=manifest.artifacts,
            projections=[crossed_projection, manifest.projections[1]],
        )

    xml = next(
        item
        for item in manifest.artifacts
        if item.kind is PilotArtifactKind.PRIMARY_FORM4_XML
        and item.accession_number == projection.accession_number
    )
    wrong_kind = dataclasses.replace(
        accepted,
        parent_relative_path=xml.relative_path,
        parent_sha256=xml.sha256,
    )
    wrong_projection = dataclasses.replace(
        projection,
        fields=tuple(wrong_kind if item is accepted else item for item in projection.fields),
    )
    with pytest.raises(SecNoncanonicalPilotContractError, match="wrong artifact kind"):
        build_sec_noncanonical_pilot_manifest(
            periods=manifest.periods,
            candidates=manifest.candidates,
            artifacts=manifest.artifacts,
            projections=[wrong_projection, manifest.projections[1]],
        )

    own_metadata = next(
        item
        for item in manifest.artifacts
        if item.kind is PilotArtifactKind.VERBATIM_METADATA
        and item.accession_number == projection.accession_number
    )
    duplicate = dataclasses.replace(
        own_metadata,
        relative_path=own_metadata.relative_path.replace(".sgml", "-copy.sgml"),
    )
    candidate = next(item for item in manifest.candidates if item.key == (projection.period, projection.accession_number))
    changed_candidate = dataclasses.replace(candidate, metadata_relative_path=duplicate.relative_path)
    with pytest.raises(SecNoncanonicalPilotContractError, match="reference|duplicated"):
        build_sec_noncanonical_pilot_manifest(
            periods=manifest.periods,
            candidates=[
                changed_candidate if item is candidate else item for item in manifest.candidates
            ],
            artifacts=[*manifest.artifacts, duplicate],
            projections=manifest.projections,
        )


def test_candidate_artifact_and_projection_outside_periods_fail_closed() -> None:
    manifest = _manifest()
    candidate = manifest.candidates[0]
    with pytest.raises(SecNoncanonicalPilotContractError, match="candidate"):
        build_sec_noncanonical_pilot_manifest(
            periods=manifest.periods,
            candidates=[dataclasses.replace(candidate, period="2025Q4"), *manifest.candidates[1:]],
            artifacts=manifest.artifacts,
            projections=manifest.projections,
        )
    artifact = next(
        item for item in manifest.artifacts if item.kind is PilotArtifactKind.VERBATIM_METADATA
    )
    with pytest.raises(SecNoncanonicalPilotContractError, match="artifact"):
        build_sec_noncanonical_pilot_manifest(
            periods=manifest.periods,
            candidates=manifest.candidates,
            artifacts=[dataclasses.replace(artifact, period="2025Q4"), *[item for item in manifest.artifacts if item is not artifact]],
            projections=manifest.projections,
        )
    projection = manifest.projections[0]
    with pytest.raises(SecNoncanonicalPilotContractError, match="projection"):
        build_sec_noncanonical_pilot_manifest(
            periods=manifest.periods,
            candidates=manifest.candidates,
            artifacts=manifest.artifacts,
            projections=[dataclasses.replace(projection, period="2025Q4"), manifest.projections[1]],
        )


def test_total_metadata_boundary_is_exact() -> None:
    def build(count: int):
        zip_1, zip_2 = _zip("2026Q1"), _zip("2026Q2")
        artifacts = [zip_1, zip_2]
        candidates = []
        for index in range(1, count + 1):
            period = "2026Q1" if index % 2 else "2026Q2"
            metadata, _ = _accession_artifacts(period, _accession(index))
            metadata = dataclasses.replace(
                metadata,
                size_bytes=SEC_NONCANONICAL_PILOT_MAX_METADATA_SOURCE_BYTES,
            )
            artifacts.append(metadata)
            candidates.append(
                _candidate(
                    period,
                    _accession(index),
                    "4",
                    zip_1.sha256 if period == "2026Q1" else zip_2.sha256,
                    (metadata,),
                )
            )
        return build_sec_noncanonical_pilot_manifest(
            periods=["2026Q1", "2026Q2"],
            candidates=candidates,
            artifacts=artifacts,
            projections=[],
        )

    assert build(32)
    with pytest.raises(SecNoncanonicalPilotContractError, match="64 MiB"):
        build(33)


def test_report_cannot_accept_or_quarantine_more_than_projected() -> None:
    base = _manifest()
    zip_sha = next(
        item.sha256
        for item in base.artifacts
        if item.kind is PilotArtifactKind.QUARTERLY_ZIP and item.period == "2026Q1"
    )
    manifest = build_sec_noncanonical_pilot_manifest(
        periods=base.periods,
        candidates=[
            *base.candidates,
            _candidate("2026Q1", _accession(3), "4", zip_sha),
        ],
        artifacts=base.artifacts,
        projections=base.projections,
    )
    report = SecNoncanonicalPilotOperationalReport.for_manifest(
        manifest,
        parser_git_commit="d" * 40,
        accepted_count=1,
        refused_count=1,
        quarantined_count=1,
        reason_counts=[
            PilotReasonCount(PilotOperationalOutcome.ACCEPTED, "accepted", 1),
            PilotReasonCount(PilotOperationalOutcome.REFUSED, "unprojected_candidate", 1),
            PilotReasonCount(
                PilotOperationalOutcome.QUARANTINED,
                "form4a_missing_source_backed_original_accession_link",
                1,
            ),
        ],
        compatibility=PilotCompatibilityOutcome.PARTIALLY_COMPATIBLE,
        compatibility_reasons=["one_candidate_unprojected"],
        stage_identities=[PilotStageIdentity("IB-1A", "ib1a-fixture", SHA_A)],
    )
    with pytest.raises(SecNoncanonicalPilotContractError, match="cannot exceed projections"):
        dataclasses.replace(
            report,
            accepted_count=2,
            refused_count=0,
            quarantined_count=1,
            reason_counts=[
                PilotReasonCount(PilotOperationalOutcome.ACCEPTED, "accepted", 2),
                PilotReasonCount(
                    PilotOperationalOutcome.QUARANTINED,
                    "form4a_missing_source_backed_original_accession_link",
                    1,
                ),
            ],
        ).verify_manifest(manifest)


def test_aggregates_revalidate_forged_nested_identities() -> None:
    manifest = _manifest()
    forged_artifact = next(
        item
        for item in manifest.artifacts
        if item.kind is PilotArtifactKind.QUARTERLY_ZIP
    )
    object.__setattr__(forged_artifact, "source_url", "https://evil.example/source.zip")
    with pytest.raises(SecNoncanonicalPilotContractError, match="SEC HTTPS"):
        build_sec_noncanonical_pilot_manifest(
            periods=manifest.periods,
            candidates=manifest.candidates,
            artifacts=manifest.artifacts,
            projections=manifest.projections,
        )

    manifest = _manifest()
    forged_candidate = manifest.candidates[0]
    object.__setattr__(forged_candidate, "submission_row_sha256", "bad")
    with pytest.raises(SecNoncanonicalPilotContractError, match="row sha256"):
        build_sec_noncanonical_pilot_manifest(
            periods=manifest.periods,
            candidates=manifest.candidates,
            artifacts=manifest.artifacts,
            projections=manifest.projections,
        )

    manifest = _manifest()
    forged_field = manifest.projections[0].fields[0]
    object.__setattr__(forged_field, "parent_sha256", "bad")
    with pytest.raises(SecNoncanonicalPilotContractError, match="parent sha256"):
        build_sec_noncanonical_pilot_manifest(
            periods=manifest.periods,
            candidates=manifest.candidates,
            artifacts=manifest.artifacts,
            projections=manifest.projections,
        )

    report = _report()
    forged_stage = report.stage_identities[0]
    object.__setattr__(forged_stage, "sha256", "bad")
    with pytest.raises(SecNoncanonicalPilotContractError, match="stage artifact sha256"):
        dataclasses.replace(report, stage_identities=[forged_stage])

    report = _report()
    forged_reason = report.reason_counts[0]
    object.__setattr__(forged_reason, "count", 0)
    with pytest.raises(SecNoncanonicalPilotContractError, match="must be positive"):
        dataclasses.replace(report, reason_counts=[forged_reason, *report.reason_counts[1:]])

    report = _report()
    forged_resource = report.resource_measurements[0]
    object.__setattr__(forged_resource, "value", -1)
    with pytest.raises(SecNoncanonicalPilotContractError, match="non-negative"):
        dataclasses.replace(
            report,
            resource_measurements=[forged_resource, *report.resource_measurements[1:]],
        )


def test_aggregate_copies_isolate_caller_authority_and_defaults() -> None:
    authority = PilotZeroAuthority()
    report = dataclasses.replace(_report(), authority=authority)
    object.__setattr__(authority, "network_access_authorized", True)
    assert report.authority.network_access_authorized is False
    assert _report().authority is not _report().authority


@pytest.mark.parametrize(
    "field_name",
    [field.name for field in dataclasses.fields(PilotZeroAuthority()) if not field.name.endswith("looks")],
)
def test_every_authority_escalation_fails_closed(field_name: str) -> None:
    with pytest.raises(SecNoncanonicalPilotContractError, match=field_name):
        dataclasses.replace(PilotZeroAuthority(), **{field_name: True})


@pytest.mark.parametrize(
    "field_name",
    [field.name for field in dataclasses.fields(PilotZeroAuthority()) if field.name.endswith("looks")],
)
def test_every_look_counter_escalation_fails_closed(field_name: str) -> None:
    with pytest.raises(SecNoncanonicalPilotContractError, match=field_name):
        dataclasses.replace(PilotZeroAuthority(), **{field_name: 1})


def test_module_import_and_call_boundary_is_pure_zero_io() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    assert imports == {
        "__future__",
        "dataclasses",
        "datetime",
        "enum",
        "re",
        "typing",
        "data.hashing",
    }
    forbidden_names = {"open", "exec", "eval", "compile", "input", "__import__"}
    forbidden_attributes = {
        "open",
        "read_bytes",
        "read_text",
        "write_bytes",
        "write_text",
        "request",
        "urlopen",
        "connect",
        "run",
        "Popen",
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        assert not (isinstance(node.func, ast.Name) and node.func.id in forbidden_names)
        assert not (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in forbidden_attributes
        )


def test_contracts_do_not_open_files(monkeypatch) -> None:
    def refuse(*_args, **_kwargs):
        raise AssertionError("contract attempted file access")

    monkeypatch.setattr("builtins.open", refuse)
    manifest = _manifest()
    report = _report(manifest)
    assert manifest.semantic_sha256
    assert report.semantic_sha256


def test_public_package_exports_match_module_contract() -> None:
    for name in pilot_module.__all__:
        assert getattr(insider_package, name) is getattr(pilot_module, name)
        assert name in insider_package.__all__
