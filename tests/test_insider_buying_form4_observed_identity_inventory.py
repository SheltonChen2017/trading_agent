"""IB-2A observed-only Form 4 identity-inventory tests.

Every byte is synthetic.  These tests prove deterministic normalization and
fail-closed composition only.  They grant no official-source, identity-
resolution, canonical-filter, outcome, QuantConnect, or trading authority.
"""
from __future__ import annotations

import ast
import copy
import io
import tokenize
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying import (
    ClassificationOutcome,
    Form4ObservedIdentityDisposition,
    Form4ObservedIdentityInventoryError,
    Form4ObservedOwnerSetOutcome,
    Form4VersionDisposition,
    ProfileBoundForm4AmendmentEvidence,
    SecEdgarAcceptancePeriodInput,
    SecEdgarAcceptanceSnapshotIdentity,
    SecEdgarAvailabilityRecord,
    SecEdgarAvailabilityRule,
    SecEdgarAvailabilityTier,
    SecEdgarMetadataSchemaProfile,
    SecEdgarMetadataSource,
    SecEdgarMetadataSourceIdentity,
    SecForm4AmendmentEvidenceProfile,
    SecForm4XmlSource,
    assemble_sec_form4_multi_period_evidence,
    build_filing_corpus,
    build_form4_observed_identity_inventory,
    build_form4_provisional_disposition_report,
)
from research.insider_buying import (
    form4_multi_period_amendment_evidence as evidence_module,
)
from research.insider_buying import (
    form4_observed_identity_inventory as inventory_module,
)
from research.insider_buying.form4_provisional_disposition_report import (
    Form4ProvisionalDisposition,
)
from research.insider_buying.sec_edgar_acceptance_snapshot import (
    LoadedSecEdgarAcceptanceSnapshot,
)


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "insider_buying"
ORIGINAL = "0000123456-26-000001"
AMENDMENT = "0000123456-27-000002"
PARSER_COMMIT = "e" * 40
BUILDER_COMMIT = "f" * 40
CAPTURE_COMMIT = "c" * 40
EXACT_FIELDS = (
    "accession",
    "form",
    "filed",
    "accepted",
    "primary_url",
    "amends_accession",
    "primary_document_sha256",
)


@dataclass(frozen=True)
class _Spec:
    accession: str
    form: str
    accepted_at: datetime
    xml_bytes: bytes
    amends_accession: str | None = None


def _metadata_profile() -> SecEdgarMetadataSchemaProfile:
    return SecEdgarMetadataSchemaProfile(
        profile_id="synthetic-non-official-ib2a-metadata-v1",
        exact_fields=EXACT_FIELDS,
        accession_number_field="accession",
        form_type_field="form",
        filing_date_field="filed",
        accepted_at_field="accepted",
        primary_document_url_field="primary_url",
        valid_from_year=2026,
        valid_from_quarter=4,
        valid_through_year=2027,
        valid_through_quarter=1,
    )


def _primary_url(spec: _Spec) -> str:
    return (
        "https://www.sec.gov/Archives/edgar/data/123456/"
        f"{spec.accession.replace('-', '')}/primary.xml"
    )


def _loaded_period(
    year: int,
    quarter: int,
    spec: _Spec,
    profile: SecEdgarMetadataSchemaProfile,
) -> LoadedSecEdgarAcceptanceSnapshot:
    primary_url = _primary_url(spec)
    metadata_payload = {
        "accession": spec.accession,
        "form": spec.form,
        "filed": spec.accepted_at.date().isoformat(),
        "accepted": spec.accepted_at.isoformat(timespec="seconds"),
        "primary_url": primary_url,
        "amends_accession": spec.amends_accession or "",
        "primary_document_sha256": hash_bytes(spec.xml_bytes),
    }
    metadata = SecEdgarMetadataSource(
        metadata_bytes=(canonical_json(metadata_payload) + "\n").encode(
            "utf-8"
        ),
        source_url=(
            "https://www.sec.gov/Archives/edgar/data/123456/"
            f"{spec.accession.replace('-', '')}/metadata.json"
        ),
        retrieved_at=spec.accepted_at + timedelta(days=1),
        capture_git_commit=CAPTURE_COMMIT,
    )
    record = SecEdgarAvailabilityRecord(
        accession_number=spec.accession,
        document_type=spec.form,
        submission_row_id=hash_payload({"accession": spec.accession}),
        filing_date=spec.accepted_at.date(),
        availability_tier=SecEdgarAvailabilityTier.EXACT_ACCEPTANCE_TIMESTAMP,
        next_open_rule=SecEdgarAvailabilityRule.NEXT_OPEN_AFTER_ACCEPTANCE,
        accepted_at=spec.accepted_at,
        primary_document_url=primary_url,
        metadata_source_sha256=metadata.metadata_sha256,
    )
    metadata_identity = SecEdgarMetadataSourceIdentity(
        accession_number=spec.accession,
        metadata_sha256=metadata.metadata_sha256,
        metadata_size_bytes=len(metadata.metadata_bytes),
        source_url=metadata.source_url,
        retrieved_at_utc=metadata.retrieved_at_utc,
        capture_git_commit=metadata.capture_git_commit,
    )
    profile_hash = hash_payload(profile.to_payload())
    parsed_hash = hash_payload({"parsed": [year, quarter]})
    raw_hash = hash_payload({"raw": [year, quarter]})
    archive_hash = hash_payload({"archive": [year, quarter]})
    lineage_hash = hash_payload(
        {
            "period": [year, quarter],
            "profile_hash": profile_hash,
            "records": [record.to_payload()],
        }
    )
    identity = SecEdgarAcceptanceSnapshotIdentity(
        year=year,
        quarter=quarter,
        parser_git_commit="d" * 40,
        parsed_snapshot_id=f"parsed-{year}q{quarter}-{parsed_hash[:16]}",
        parsed_lineage_hash=parsed_hash,
        raw_snapshot_id=f"raw-{year}q{quarter}-{raw_hash[:16]}",
        raw_lineage_hash=raw_hash,
        raw_archive_sha256=archive_hash,
        metadata_profile=profile,
        metadata_profile_hash=profile_hash,
        source_inventory=(metadata_identity,),
        source_inventory_hash=hash_payload([metadata_identity.to_payload()]),
        record_count=1,
        exact_acceptance_count=1,
        filing_date_fallback_count=0,
        records_hash=hash_payload([record.to_payload()]),
        lineage_hash=lineage_hash,
        snapshot_id=(
            f"sec-edgar-acceptance-{year:04d}q{quarter}-"
            f"{lineage_hash[:16]}"
        ),
    )
    return LoadedSecEdgarAcceptanceSnapshot(
        identity=identity,
        records=(record,),
        sources=(metadata,),
    )


def _period(year: int, quarter: int) -> SecEdgarAcceptancePeriodInput:
    return SecEdgarAcceptancePeriodInput(
        acceptance_snapshot_path=f"{year}q{quarter}.json",
        parsed_snapshot_directory=f"parsed-{year}q{quarter}",
        raw_snapshot_directory=f"raw-{year}q{quarter}",
    )


def _xml_source(spec: _Spec) -> SecForm4XmlSource:
    return SecForm4XmlSource(
        accession_number=spec.accession,
        xml_bytes=spec.xml_bytes,
        primary_document_url=_primary_url(spec),
        retrieved_at=spec.accepted_at + timedelta(days=2),
        capture_git_commit=CAPTURE_COMMIT,
        amends_accession=spec.amends_accession,
    )


def _evidence_profile(
    profile: SecEdgarMetadataSchemaProfile,
) -> SecForm4AmendmentEvidenceProfile:
    return SecForm4AmendmentEvidenceProfile(
        profile_id="synthetic-non-official-ib2a-link-v1",
        exact_fields=EXACT_FIELDS,
        amends_accession_field="amends_accession",
        primary_document_sha256_field="primary_document_sha256",
        upstream_metadata_profile_hash=hash_payload(profile.to_payload()),
        valid_from_year=2026,
        valid_from_quarter=4,
        valid_through_year=2027,
        valid_through_quarter=1,
        official_sec_profile_verified=False,
    )


def _build_evidence(
    monkeypatch,
    *,
    original_xml: bytes | None = None,
    reverse: bool = False,
) -> ProfileBoundForm4AmendmentEvidence:
    original = _Spec(
        accession=ORIGINAL,
        form="4",
        accepted_at=datetime(2026, 12, 29, 18, 0, tzinfo=timezone.utc),
        xml_bytes=(
            original_xml
            if original_xml is not None
            else (FIXTURES / "form4_original.xml").read_bytes()
        ),
    )
    amendment = _Spec(
        accession=AMENDMENT,
        form="4/A",
        accepted_at=datetime(2027, 1, 4, 18, 0, tzinfo=timezone.utc),
        xml_bytes=(FIXTURES / "form4_amendment.xml").read_bytes(),
        amends_accession=ORIGINAL,
    )
    profile = _metadata_profile()
    loaded = {
        "2026q4.json": _loaded_period(2026, 4, original, profile),
        "2027q1.json": _loaded_period(2027, 1, amendment, profile),
    }

    def loader(snapshot_path, **_kwargs):
        return loaded[Path(snapshot_path).name]

    monkeypatch.setattr(
        evidence_module.acceptance_module,
        "load_sec_edgar_acceptance_snapshot",
        loader,
    )
    periods = (_period(2026, 4), _period(2027, 1))
    sources = (_xml_source(original), _xml_source(amendment))
    if reverse:
        periods = tuple(reversed(periods))
        sources = tuple(reversed(sources))
    return assemble_sec_form4_multi_period_evidence(
        periods,
        sources=sources,
        evidence_profile=_evidence_profile(profile),
        parser_git_commit=PARSER_COMMIT,
    )


def _inventory(monkeypatch, *, original_xml: bytes | None = None):
    evidence = _build_evidence(monkeypatch, original_xml=original_xml)
    return evidence, build_form4_observed_identity_inventory(
        evidence,
        builder_git_commit=BUILDER_COMMIT,
    )


def _identity_for_rows(inventory, *, filings=None, owners=None, transactions=None):
    filings = inventory.filings if filings is None else filings
    owners = inventory.reporting_owners if owners is None else owners
    transactions = inventory.transactions if transactions is None else transactions
    candidate_count = sum(
        row.identity_disposition
        is Form4ObservedIdentityDisposition.UNRESOLVED_PROVISIONAL_CANDIDATE
        for row in transactions
    )
    lineage = inventory.identity.lineage_payload()
    lineage.update(
        {
            "filing_count": len(filings),
            "amendment_count": sum(
                row.document_type == "4/A" for row in filings
            ),
            "reporting_owner_count": len(owners),
            "non_single_owner_filing_count": sum(
                row.reporting_owner_count != 1 for row in filings
            ),
            "transaction_count": len(transactions),
            "provisional_candidate_count": candidate_count,
            "quarantine_count": len(transactions) - candidate_count,
            "filing_inventory_hash": hash_payload(
                [row.to_payload() for row in filings]
            ),
            "reporting_owner_inventory_hash": hash_payload(
                [row.to_payload() for row in owners]
            ),
            "transaction_inventory_hash": hash_payload(
                [row.to_payload() for row in transactions]
            ),
        }
    )
    return replace(
        inventory.identity,
        filing_count=lineage["filing_count"],
        amendment_count=lineage["amendment_count"],
        reporting_owner_count=lineage["reporting_owner_count"],
        non_single_owner_filing_count=lineage[
            "non_single_owner_filing_count"
        ],
        transaction_count=lineage["transaction_count"],
        provisional_candidate_count=lineage["provisional_candidate_count"],
        quarantine_count=lineage["quarantine_count"],
        filing_inventory_hash=lineage["filing_inventory_hash"],
        reporting_owner_inventory_hash=lineage[
            "reporting_owner_inventory_hash"
        ],
        transaction_inventory_hash=lineage["transaction_inventory_hash"],
        inventory_id=(
            "form4-observed-identity-inventory-"
            f"{hash_payload(lineage)[:16]}"
        ),
        _verified_factory_token=(
            inventory_module._VERIFIED_IDENTITY_FACTORY_TOKEN
        ),
    )


def _remove_first_owner(xml_bytes: bytes) -> bytes:
    start = xml_bytes.index(b"  <reportingOwner>")
    end = xml_bytes.index(b"  </reportingOwner>", start) + len(
        b"  </reportingOwner>"
    )
    return xml_bytes[:start] + xml_bytes[end:]


def test_inventory_accounts_once_for_every_observation(monkeypatch):
    evidence, inventory = _inventory(monkeypatch)
    report = build_form4_provisional_disposition_report(
        evidence,
        builder_git_commit=BUILDER_COMMIT,
    )

    assert inventory.identity.filing_count == len(inventory.filings) == 2
    assert inventory.identity.reporting_owner_count == len(
        inventory.reporting_owners
    ) == 2
    assert inventory.identity.transaction_count == len(
        inventory.transactions
    ) == len(report.rows) == 2
    assert inventory.identity.amendment_count == 1
    assert inventory.identity.provisional_candidate_count == 1
    assert inventory.identity.quarantine_count == 1
    assert inventory.identity.non_single_owner_filing_count == 0
    assert inventory.identity.upstream_evidence_id == evidence.identity.evidence_id
    assert inventory.identity.upstream_evidence_identity_hash == hash_payload(
        evidence.identity.to_payload()
    )
    assert inventory.identity.upstream_parsed_corpus_hash == (
        evidence.identity.parsed_corpus_hash
    )
    assert inventory.identity.upstream_source_inventory_hash == (
        evidence.identity.source_inventory_hash
    )
    assert inventory.identity.upstream_report_id == report.identity.report_id
    assert inventory.identity.upstream_report_identity_hash == hash_payload(
        report.identity.to_payload()
    )
    assert inventory.identity.upstream_report_row_inventory_hash == (
        report.identity.row_inventory_hash
    )
    assert inventory.identity.filing_inventory_hash == hash_payload(
        [item.to_payload() for item in inventory.filings]
    )
    assert inventory.identity.reporting_owner_inventory_hash == hash_payload(
        [item.to_payload() for item in inventory.reporting_owners]
    )
    assert inventory.identity.transaction_inventory_hash == hash_payload(
        [item.to_payload() for item in inventory.transactions]
    )
    assert inventory.identity.inventory_id == (
        "form4-observed-identity-inventory-"
        f"{hash_payload(inventory.identity.lineage_payload())[:16]}"
    )

    report_by_key = {
        (row.accession_number, row.source_sha256, row.row_index, row.event_id): row
        for row in report.rows
    }
    assert set(report_by_key) == {
        (
            row.accession_number,
            row.source_sha256,
            row.row_index,
            row.event_id,
        )
        for row in inventory.transactions
    }
    for row in inventory.transactions:
        upstream = report_by_key[
            (row.accession_number, row.source_sha256, row.row_index, row.event_id)
        ]
        assert row.upstream_report_row_id == upstream.row_id
        assert row.transaction_payload_hash == upstream.transaction_payload_hash
        assert row.security_title_raw == upstream.security_title_raw
        assert row.transaction_date == upstream.transaction_date
        assert row.resolved_security_identity is None

    evidence_filings = {
        item.envelope.accession_number: item
        for item in evidence.as_filed_corpus.filings
    }
    for filing_row in inventory.filings:
        filing = evidence_filings[filing_row.accession_number]
        envelope = filing.envelope
        assert filing_row.source_sha256 == envelope.source_sha256
        assert filing_row.document_type == envelope.form_type
        assert filing_row.accepted_at_utc == (
            envelope.availability.accepted_at.astimezone(timezone.utc).isoformat(
                timespec="seconds"
            )
        )
        assert filing_row.primary_document_url == envelope.source_name
        assert filing_row.issuer_cik == envelope.issuer_cik
        assert filing_row.issuer_name == envelope.issuer_name
        assert filing_row.issuer_symbol_raw == envelope.issuer_symbol_raw
        observed_owners = tuple(
            item
            for item in inventory.reporting_owners
            if item.accession_number == filing_row.accession_number
        )
        assert len(observed_owners) == len(filing.reporting_owners)
        for owner_row, owner in zip(
            observed_owners,
            filing.reporting_owners,
            strict=True,
        ):
            assert owner_row.owner_cik == owner.owner_cik
            assert owner_row.owner_name == owner.owner_name
            assert owner_row.is_director is owner.is_director
            assert owner_row.is_officer is owner.is_officer
            assert owner_row.is_ten_percent_owner is owner.is_ten_percent_owner
            assert owner_row.is_other is owner.is_other
            assert owner_row.officer_title == owner.officer_title


def test_inventory_is_order_independent_and_hash_deterministic(monkeypatch):
    forward_evidence = _build_evidence(monkeypatch)
    forward = build_form4_observed_identity_inventory(
        forward_evidence,
        builder_git_commit=BUILDER_COMMIT,
    )
    reverse_evidence = _build_evidence(monkeypatch, reverse=True)
    reverse = build_form4_observed_identity_inventory(
        reverse_evidence,
        builder_git_commit=BUILDER_COMMIT,
    )

    assert forward == reverse
    assert forward.to_payload() == reverse.to_payload()
    assert canonical_json(forward.to_payload()) == canonical_json(
        reverse.to_payload()
    )
    assert tuple(
        (item.accession_number, item.source_sha256) for item in forward.filings
    ) == tuple(
        sorted(
            (item.accession_number, item.source_sha256)
            for item in forward.filings
        )
    )


def test_joint_owners_are_retained_without_transaction_fanout(monkeypatch):
    evidence, inventory = _inventory(
        monkeypatch,
        original_xml=(FIXTURES / "form4_joint_owners.xml").read_bytes(),
    )
    original_filing = next(
        item for item in inventory.filings if item.accession_number == ORIGINAL
    )
    original_owners = tuple(
        item
        for item in inventory.reporting_owners
        if item.accession_number == ORIGINAL
    )
    original_transactions = tuple(
        item for item in inventory.transactions if item.accession_number == ORIGINAL
    )

    assert len(evidence.as_filed_corpus.filing(ORIGINAL).transactions) == 1
    assert len(original_owners) == 2
    assert tuple(item.reporting_owner_index for item in original_owners) == (0, 1)
    assert tuple(item.owner_cik for item in original_owners) == (
        "0000987654",
        "0000987655",
    )
    assert len(original_transactions) == 1
    assert original_filing.owner_set_outcomes == (
        Form4ObservedOwnerSetOutcome.MULTIPLE_OWNER_SET_QUARANTINED,
    )
    assert original_transactions[0].identity_disposition is (
        Form4ObservedIdentityDisposition.UNRESOLVED_QUARANTINE
    )
    assert inventory.identity.non_single_owner_filing_count == 1


@pytest.mark.parametrize(
    "transform,expected_count,expected_outcomes",
    [
        (
            _remove_first_owner,
            0,
            (Form4ObservedOwnerSetOutcome.MISSING_OWNER_SET_QUARANTINED,),
        ),
        (
            lambda value: value.replace(
                b"<isOfficer>1</isOfficer>",
                b"<isOfficer>yes</isOfficer>",
                1,
            ),
            1,
            (
                Form4ObservedOwnerSetOutcome.INCOMPLETE_OWNER_RELATIONSHIP_QUARANTINED,
            ),
        ),
    ],
)
def test_missing_and_incomplete_owner_sets_have_named_quarantines(
    monkeypatch,
    transform,
    expected_count,
    expected_outcomes,
):
    xml_bytes = transform((FIXTURES / "form4_original.xml").read_bytes())
    _evidence, inventory = _inventory(monkeypatch, original_xml=xml_bytes)
    filing = next(
        item for item in inventory.filings if item.accession_number == ORIGINAL
    )
    owners = tuple(
        item
        for item in inventory.reporting_owners
        if item.accession_number == ORIGINAL
    )
    transaction = next(
        item for item in inventory.transactions if item.accession_number == ORIGINAL
    )

    assert filing.reporting_owner_count == len(owners) == expected_count
    assert filing.owner_set_outcomes == expected_outcomes
    assert filing.all_owner_relationships_complete is False
    assert transaction.identity_disposition is (
        Form4ObservedIdentityDisposition.UNRESOLVED_QUARANTINE
    )
    if owners:
        assert owners[0].owner_cik == "0000987654"
        assert owners[0].relationship_complete is False


def test_multiple_incomplete_owners_retain_both_ordered_quarantines(
    monkeypatch,
):
    xml_bytes = (FIXTURES / "form4_joint_owners.xml").read_bytes().replace(
        b"<isOfficer>1</isOfficer>",
        b"<isOfficer>yes</isOfficer>",
        1,
    )
    _evidence, inventory = _inventory(monkeypatch, original_xml=xml_bytes)
    filing = next(
        item for item in inventory.filings if item.accession_number == ORIGINAL
    )
    assert filing.owner_set_outcomes == (
        Form4ObservedOwnerSetOutcome.MULTIPLE_OWNER_SET_QUARANTINED,
        Form4ObservedOwnerSetOutcome.INCOMPLETE_OWNER_RELATIONSHIP_QUARANTINED,
    )


def test_amendment_is_distinct_and_permanently_noncanonical(monkeypatch):
    _evidence, inventory = _inventory(monkeypatch)
    filings = {item.accession_number: item for item in inventory.filings}
    transactions = {
        item.accession_number: item for item in inventory.transactions
    }

    assert filings[ORIGINAL].original_accession == ORIGINAL
    assert filings[ORIGINAL].amends_accession is None
    assert filings[ORIGINAL].version_disposition is (
        Form4VersionDisposition.ORIGINAL_OBSERVED_IN_SUPPLIED_SAMPLE
    )
    assert filings[AMENDMENT].original_accession == ORIGINAL
    assert filings[AMENDMENT].amends_accession == ORIGINAL
    assert filings[AMENDMENT].version_disposition is (
        Form4VersionDisposition.QUARANTINED_UNRESOLVED_AMENDMENT
    )
    assert transactions[AMENDMENT].identity_disposition is (
        Form4ObservedIdentityDisposition.UNRESOLVED_QUARANTINE
    )
    assert transactions[AMENDMENT].resolved_security_identity is None
    assert len(inventory.transactions) == 2
    assert not hasattr(inventory, "canonical_transactions")


@pytest.mark.parametrize("target", ["issuer", "owner", "transaction"])
def test_builder_rebuilds_public_report_and_refuses_forged_retained_state(
    monkeypatch,
    target,
):
    evidence = _build_evidence(monkeypatch)
    original = evidence.as_filed_corpus.filing(ORIGINAL)
    if target == "issuer":
        forged_child = replace(original.envelope, issuer_name="Forged Issuer")
        forged_filing = replace(original, envelope=forged_child)
    elif target == "owner":
        forged_child = replace(
            original.reporting_owners[0], owner_name="Forged Owner"
        )
        forged_filing = replace(original, reporting_owners=(forged_child,))
    else:
        forged_child = replace(
            original.transactions[0], security_title_raw="Forged Security"
        )
        forged_filing = replace(original, transactions=(forged_child,))
    forged_corpus = build_filing_corpus(
        [
            forged_filing
            if item.envelope.accession_number == ORIGINAL
            else item
            for item in evidence.as_filed_corpus.filings
        ]
    )
    forged_evidence = copy.copy(evidence)
    object.__setattr__(forged_evidence, "as_filed_corpus", forged_corpus)

    with pytest.raises(
        Form4ObservedIdentityInventoryError,
        match="independent revalidation",
    ):
        build_form4_observed_identity_inventory(
            forged_evidence,
            builder_git_commit=BUILDER_COMMIT,
        )


def test_builder_uses_public_upstream_report_exactly_once(monkeypatch):
    evidence = _build_evidence(monkeypatch)
    real_builder = inventory_module.build_form4_provisional_disposition_report
    calls = 0

    def counted_builder(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real_builder(*args, **kwargs)

    monkeypatch.setattr(
        inventory_module,
        "build_form4_provisional_disposition_report",
        counted_builder,
    )
    build_form4_observed_identity_inventory(
        evidence,
        builder_git_commit=BUILDER_COMMIT,
    )
    assert calls == 1


@pytest.mark.parametrize(
    "mutation",
    [
        "owner_name",
        "official_amendment_link_verified",
        "complete_amendment_coverage_verified",
        "canonical_filter_authorized",
        "xml_sources",
        "supplied_link_evidence",
        "lineage_source_sha256",
        "accepted_at_microsecond",
    ],
)
def test_post_validation_evidence_mutation_is_refused(monkeypatch, mutation):
    evidence = _build_evidence(monkeypatch)
    real_builder = inventory_module.build_form4_provisional_disposition_report

    def mutate_after_validation(*args, **kwargs):
        report = real_builder(*args, **kwargs)
        if mutation == "owner_name":
            filing = evidence.as_filed_corpus.filing(ORIGINAL)
            object.__setattr__(
                filing.reporting_owners[0],
                "owner_name",
                "Forged After Validation",
            )
        elif mutation == "xml_sources":
            object.__setattr__(
                evidence,
                "xml_sources",
                tuple(reversed(evidence.xml_sources)),
            )
        elif mutation == "supplied_link_evidence":
            object.__setattr__(
                evidence,
                "supplied_link_evidence",
                tuple(reversed(evidence.supplied_link_evidence)),
            )
        elif mutation == "lineage_source_sha256":
            object.__setattr__(
                evidence.lineages[0].versions[0],
                "source_sha256",
                "0" * 64,
            )
        elif mutation == "accepted_at_microsecond":
            availability = evidence.as_filed_corpus.filing(
                ORIGINAL
            ).envelope.availability
            object.__setattr__(
                availability,
                "accepted_at",
                availability.accepted_at + timedelta(microseconds=1),
            )
        else:
            object.__setattr__(evidence.identity, mutation, True)
        return report

    monkeypatch.setattr(
        inventory_module,
        "build_form4_provisional_disposition_report",
        mutate_after_validation,
    )
    with pytest.raises(
        Form4ObservedIdentityInventoryError,
        match="changed during upstream report validation",
    ):
        build_form4_observed_identity_inventory(
            evidence,
            builder_git_commit=BUILDER_COMMIT,
        )


@pytest.mark.parametrize(
    "field_name,replacement",
    [
        ("upstream_evidence_id", "forged-evidence-id"),
        ("upstream_evidence_identity_hash", "0" * 64),
        ("upstream_parsed_corpus_hash", "0" * 64),
        ("upstream_source_inventory_hash", "0" * 64),
        ("canonical_filter_authorized", True),
        ("authorized_outcome_looks", 1),
    ],
)
def test_forged_upstream_report_identity_binding_is_refused(
    monkeypatch,
    field_name,
    replacement,
):
    evidence = _build_evidence(monkeypatch)
    real_builder = inventory_module.build_form4_provisional_disposition_report

    def forge_report(*args, **kwargs):
        report = real_builder(*args, **kwargs)
        identity = copy.copy(report.identity)
        object.__setattr__(identity, field_name, replacement)
        object.__setattr__(
            identity,
            "report_id",
            (
                "form4-provisional-disposition-report-"
                f"{hash_payload(identity.lineage_payload())[:16]}"
            ),
        )
        forged = copy.copy(report)
        object.__setattr__(forged, "identity", identity)
        return forged

    monkeypatch.setattr(
        inventory_module,
        "build_form4_provisional_disposition_report",
        forge_report,
    )
    with pytest.raises(
        Form4ObservedIdentityInventoryError,
        match="rebuilt upstream report",
    ):
        build_form4_observed_identity_inventory(
            evidence,
            builder_git_commit=BUILDER_COMMIT,
        )


def test_forged_report_duplicate_payload_hash_is_refused(monkeypatch):
    evidence = _build_evidence(monkeypatch)
    real_builder = inventory_module.build_form4_provisional_disposition_report

    def forge_report(*args, **kwargs):
        report = real_builder(*args, **kwargs)
        first, second = report.rows
        row_payload = second.lineage_payload()
        row_payload["transaction_payload_hash"] = first.transaction_payload_hash
        forged_second = replace(
            second,
            transaction_payload_hash=first.transaction_payload_hash,
            row_id=hash_payload(row_payload),
        )
        rows = (first, forged_second)
        identity = copy.copy(report.identity)
        object.__setattr__(
            identity,
            "row_inventory_hash",
            hash_payload([row.to_payload() for row in rows]),
        )
        object.__setattr__(
            identity,
            "report_id",
            (
                "form4-provisional-disposition-report-"
                f"{hash_payload(identity.lineage_payload())[:16]}"
            ),
        )
        forged = copy.copy(report)
        object.__setattr__(forged, "identity", identity)
        object.__setattr__(forged, "rows", rows)
        return forged

    monkeypatch.setattr(
        inventory_module,
        "build_form4_provisional_disposition_report",
        forge_report,
    )
    with pytest.raises(
        Form4ObservedIdentityInventoryError,
        match="rebuilt upstream report",
    ):
        build_form4_observed_identity_inventory(
            evidence,
            builder_git_commit=BUILDER_COMMIT,
        )


def test_forged_report_cannot_promote_a_quarantined_transaction(monkeypatch):
    xml_bytes = (FIXTURES / "form4_original.xml").read_bytes().replace(
        b"<value>Common Stock</value>",
        b"<value>Ordinary Shares</value>",
        1,
    )
    evidence = _build_evidence(monkeypatch, original_xml=xml_bytes)
    real_builder = inventory_module.build_form4_provisional_disposition_report

    def forge_report(*args, **kwargs):
        report = real_builder(*args, **kwargs)
        target = next(
            row for row in report.rows if row.accession_number == ORIGINAL
        )
        row_payload = target.lineage_payload()
        row_payload["outcomes"] = [
            ClassificationOutcome.ELIGIBLE_FOR_LOT_AGGREGATION.value
        ]
        row_payload["disposition"] = (
            Form4ProvisionalDisposition.PROVISIONAL_PRE_AGGREGATION_CANDIDATE.value
        )
        forged_target = replace(
            target,
            outcomes=(ClassificationOutcome.ELIGIBLE_FOR_LOT_AGGREGATION,),
            disposition=(
                Form4ProvisionalDisposition.PROVISIONAL_PRE_AGGREGATION_CANDIDATE
            ),
            row_id=hash_payload(row_payload),
        )
        rows = tuple(
            forged_target if row is target else row for row in report.rows
        )
        identity = copy.copy(report.identity)
        object.__setattr__(identity, "candidate_count", 1)
        object.__setattr__(identity, "quarantine_count", 1)
        object.__setattr__(
            identity,
            "row_inventory_hash",
            hash_payload([row.to_payload() for row in rows]),
        )
        object.__setattr__(
            identity,
            "report_id",
            (
                "form4-provisional-disposition-report-"
                f"{hash_payload(identity.lineage_payload())[:16]}"
            ),
        )
        forged = copy.copy(report)
        object.__setattr__(forged, "identity", identity)
        object.__setattr__(forged, "rows", rows)
        return forged

    monkeypatch.setattr(
        inventory_module,
        "build_form4_provisional_disposition_report",
        forge_report,
    )
    with pytest.raises(
        Form4ObservedIdentityInventoryError,
        match="captured evidence",
    ):
        build_form4_observed_identity_inventory(
            evidence,
            builder_git_commit=BUILDER_COMMIT,
        )


def test_forged_report_cannot_rewrite_retained_transaction_hash(monkeypatch):
    evidence = _build_evidence(monkeypatch)
    real_builder = inventory_module.build_form4_provisional_disposition_report

    def forge_report(*args, **kwargs):
        report = real_builder(*args, **kwargs)
        target = next(
            row for row in report.rows if row.accession_number == ORIGINAL
        )
        replacement_hash = "a" * 64
        assert replacement_hash not in {
            row.transaction_payload_hash for row in report.rows
        }
        row_payload = target.lineage_payload()
        row_payload["transaction_payload_hash"] = replacement_hash
        forged_target = replace(
            target,
            transaction_payload_hash=replacement_hash,
            row_id=hash_payload(row_payload),
        )
        rows = tuple(
            forged_target if row is target else row for row in report.rows
        )
        identity = copy.copy(report.identity)
        object.__setattr__(
            identity,
            "row_inventory_hash",
            hash_payload([row.to_payload() for row in rows]),
        )
        object.__setattr__(
            identity,
            "report_id",
            (
                "form4-provisional-disposition-report-"
                f"{hash_payload(identity.lineage_payload())[:16]}"
            ),
        )
        forged = copy.copy(report)
        object.__setattr__(forged, "identity", identity)
        object.__setattr__(forged, "rows", rows)
        return forged

    monkeypatch.setattr(
        inventory_module,
        "build_form4_provisional_disposition_report",
        forge_report,
    )
    with pytest.raises(
        Form4ObservedIdentityInventoryError,
        match="captured evidence",
    ):
        build_form4_observed_identity_inventory(
            evidence,
            builder_git_commit=BUILDER_COMMIT,
        )


@pytest.mark.parametrize("target", ["identity", "row"])
def test_shadowed_report_serializer_refuses_before_it_can_execute(
    monkeypatch,
    target,
):
    evidence = _build_evidence(monkeypatch)
    real_builder = inventory_module.build_form4_provisional_disposition_report

    def forge_report(*args, **kwargs):
        report = real_builder(*args, **kwargs)
        victim = report.identity if target == "identity" else report.rows[0]

        def hostile_to_payload():
            pytest.fail("shadowed report serializer executed")

        object.__setattr__(victim, "to_payload", hostile_to_payload)
        return report

    monkeypatch.setattr(
        inventory_module,
        "build_form4_provisional_disposition_report",
        forge_report,
    )
    with pytest.raises(
        Form4ObservedIdentityInventoryError,
        match="instance state is not exact",
    ):
        build_form4_observed_identity_inventory(
            evidence,
            builder_git_commit=BUILDER_COMMIT,
        )


def test_report_scalar_is_projected_before_equality_callbacks(monkeypatch):
    evidence = _build_evidence(monkeypatch)
    real_builder = inventory_module.build_form4_provisional_disposition_report

    class HostileValue:
        def __ne__(self, _other):
            pytest.fail("hostile report equality callback executed")

    def forge_report(*args, **kwargs):
        report = real_builder(*args, **kwargs)
        object.__setattr__(
            report.identity,
            "contract_version",
            HostileValue(),
        )
        return report

    monkeypatch.setattr(
        inventory_module,
        "build_form4_provisional_disposition_report",
        forge_report,
    )
    with pytest.raises(Form4ObservedIdentityInventoryError, match="unsupported"):
        build_form4_observed_identity_inventory(
            evidence,
            builder_git_commit=BUILDER_COMMIT,
        )


def test_factory_rows_and_cross_inventory_bindings_fail_closed(monkeypatch):
    _evidence, inventory = _inventory(monkeypatch)

    with pytest.raises(Form4ObservedIdentityInventoryError, match="factory-created"):
        replace(inventory.identity)
    with pytest.raises(Form4ObservedIdentityInventoryError, match="factory-created"):
        replace(inventory)
    with pytest.raises(Form4ObservedIdentityInventoryError, match="observation ID"):
        replace(inventory.reporting_owners[0], owner_observation_id="0" * 64)

    first, second = inventory.transactions
    payload = first.lineage_payload()
    payload["filing_observation_id"] = second.filing_observation_id
    cross_wired = replace(
        first,
        filing_observation_id=second.filing_observation_id,
        transaction_observation_id=hash_payload(payload),
    )
    with pytest.raises(
        Form4ObservedIdentityInventoryError,
        match="transaction-to-filing binding",
    ):
        replace(
            inventory,
            transactions=(cross_wired, second),
            _verified_factory_token=(
                inventory_module._VERIFIED_INVENTORY_FACTORY_TOKEN
            ),
        )


def test_identity_factory_gate_precedes_hostile_version_comparison(monkeypatch):
    _evidence, inventory = _inventory(monkeypatch)

    class HostileVersion:
        def __ne__(self, _other):
            pytest.fail("hostile contract-version comparison executed")

    with pytest.raises(
        Form4ObservedIdentityInventoryError,
        match="factory-created",
    ):
        replace(inventory.identity, contract_version=HostileVersion())
    with pytest.raises(Form4ObservedIdentityInventoryError, match="invalid"):
        replace(
            inventory.identity,
            contract_version=HostileVersion(),
            _verified_factory_token=(
                inventory_module._VERIFIED_IDENTITY_FACTORY_TOKEN
            ),
        )

    class VersionSubclass(str):
        pass

    with pytest.raises(Form4ObservedIdentityInventoryError, match="invalid"):
        replace(
            inventory.identity,
            contract_version=VersionSubclass(
                inventory.identity.contract_version
            ),
            _verified_factory_token=(
                inventory_module._VERIFIED_IDENTITY_FACTORY_TOKEN
            ),
        )


@pytest.mark.parametrize(
    "mutation",
    ["absent_original", "cross_issuer", "not_after_original", "before_original"],
)
def test_self_consistent_amendment_requires_its_observed_original(
    monkeypatch,
    mutation,
):
    _evidence, inventory = _inventory(monkeypatch)
    target = next(
        row for row in inventory.filings if row.accession_number == AMENDMENT
    )
    filing_payload = target.lineage_payload()
    replacements = {}
    if mutation == "absent_original":
        absent_original = "0000123456-26-999999"
        replacements.update(
            original_accession=absent_original,
            amends_accession=absent_original,
        )
    elif mutation == "cross_issuer":
        replacements["issuer_cik"] = "0000000001"
    elif mutation == "before_original":
        # An amendment cannot be publicly accepted before the filing it
        # amends. Only the equal-time case was previously exercised, so the
        # strict-order half of the guard could be deleted unnoticed.
        original = next(
            row
            for row in inventory.filings
            if row.accession_number == ORIGINAL
        )
        replacements["accepted_at_utc"] = (
            datetime.fromisoformat(original.accepted_at_utc)
            - timedelta(seconds=1)
        ).isoformat(timespec="seconds")
    else:
        original = next(
            row
            for row in inventory.filings
            if row.accession_number == ORIGINAL
        )
        replacements["accepted_at_utc"] = original.accepted_at_utc
    filing_payload.update(replacements)
    forged_filing = replace(
        target,
        **replacements,
        filing_observation_id=hash_payload(filing_payload),
    )
    filings = tuple(
        forged_filing if row is target else row for row in inventory.filings
    )
    target_transaction = next(
        row
        for row in inventory.transactions
        if row.accession_number == AMENDMENT
    )
    transaction_payload = target_transaction.lineage_payload()
    transaction_payload["filing_observation_id"] = (
        forged_filing.filing_observation_id
    )
    forged_transaction = replace(
        target_transaction,
        filing_observation_id=forged_filing.filing_observation_id,
        transaction_observation_id=hash_payload(transaction_payload),
    )
    transactions = tuple(
        forged_transaction if row is target_transaction else row
        for row in inventory.transactions
    )
    forged_identity = _identity_for_rows(
        inventory,
        filings=filings,
        transactions=transactions,
    )

    with pytest.raises(
        Form4ObservedIdentityInventoryError,
        match="amendment-to-original|acceptance times are ambiguous",
    ):
        replace(
            inventory,
            identity=forged_identity,
            filings=filings,
            transactions=transactions,
            _verified_factory_token=(
                inventory_module._VERIFIED_INVENTORY_FACTORY_TOKEN
            ),
        )


def test_self_consistent_duplicate_filing_accession_is_refused(monkeypatch):
    _evidence, inventory = _inventory(monkeypatch)
    template = next(
        row for row in inventory.filings if row.accession_number == ORIGINAL
    )
    payload = template.lineage_payload()
    payload.update(
        {
            "source_sha256": "2" * 64,
            "reporting_owner_count": 0,
            "all_owner_relationships_complete": False,
            "owner_set_outcomes": [
                Form4ObservedOwnerSetOutcome.MISSING_OWNER_SET_QUARANTINED.value
            ],
            "reporting_owner_observation_ids": [],
            "reporting_owner_inventory_hash": hash_payload([]),
        }
    )
    duplicate = replace(
        template,
        source_sha256=payload["source_sha256"],
        reporting_owner_count=0,
        all_owner_relationships_complete=False,
        owner_set_outcomes=(
            Form4ObservedOwnerSetOutcome.MISSING_OWNER_SET_QUARANTINED,
        ),
        reporting_owner_observation_ids=(),
        reporting_owner_inventory_hash=payload[
            "reporting_owner_inventory_hash"
        ],
        filing_observation_id=hash_payload(payload),
    )
    filings = tuple(
        sorted(
            (*inventory.filings, duplicate),
            key=lambda row: (row.accession_number, row.source_sha256),
        )
    )
    forged_identity = _identity_for_rows(inventory, filings=filings)

    with pytest.raises(
        Form4ObservedIdentityInventoryError,
        match="order or uniqueness",
    ):
        replace(
            inventory,
            identity=forged_identity,
            filings=filings,
            _verified_factory_token=(
                inventory_module._VERIFIED_INVENTORY_FACTORY_TOKEN
            ),
        )


def test_self_consistent_lineage_cannot_repeat_an_acceptance_time(monkeypatch):
    _evidence, inventory = _inventory(monkeypatch)
    template = next(
        row for row in inventory.filings if row.accession_number == AMENDMENT
    )
    payload = template.lineage_payload()
    payload.update(
        {
            "accession_number": "0000123456-27-000003",
            "source_sha256": "1" * 64,
            "reporting_owner_count": 0,
            "all_owner_relationships_complete": False,
            "owner_set_outcomes": [
                Form4ObservedOwnerSetOutcome.MISSING_OWNER_SET_QUARANTINED.value
            ],
            "reporting_owner_observation_ids": [],
            "reporting_owner_inventory_hash": hash_payload([]),
        }
    )
    duplicate_time = replace(
        template,
        accession_number=payload["accession_number"],
        source_sha256=payload["source_sha256"],
        reporting_owner_count=0,
        all_owner_relationships_complete=False,
        owner_set_outcomes=(
            Form4ObservedOwnerSetOutcome.MISSING_OWNER_SET_QUARANTINED,
        ),
        reporting_owner_observation_ids=(),
        reporting_owner_inventory_hash=payload[
            "reporting_owner_inventory_hash"
        ],
        filing_observation_id=hash_payload(payload),
    )
    filings = tuple(
        sorted(
            (*inventory.filings, duplicate_time),
            key=lambda row: (row.accession_number, row.source_sha256),
        )
    )
    forged_identity = _identity_for_rows(inventory, filings=filings)

    with pytest.raises(
        Form4ObservedIdentityInventoryError,
        match="acceptance times are ambiguous",
    ):
        replace(
            inventory,
            identity=forged_identity,
            filings=filings,
            _verified_factory_token=(
                inventory_module._VERIFIED_INVENTORY_FACTORY_TOKEN
            ),
        )


def test_self_consistent_transaction_row_index_hole_is_refused(monkeypatch):
    _evidence, inventory = _inventory(monkeypatch)
    target = next(
        row for row in inventory.transactions if row.accession_number == ORIGINAL
    )
    payload = target.lineage_payload()
    payload["row_index"] = 1
    forged = replace(
        target,
        row_index=1,
        transaction_observation_id=hash_payload(payload),
    )
    transactions = tuple(
        forged if row is target else row for row in inventory.transactions
    )
    forged_identity = _identity_for_rows(
        inventory,
        transactions=transactions,
    )

    with pytest.raises(
        Form4ObservedIdentityInventoryError,
        match="row indexes are not contiguous",
    ):
        replace(
            inventory,
            identity=forged_identity,
            transactions=transactions,
            _verified_factory_token=(
                inventory_module._VERIFIED_INVENTORY_FACTORY_TOKEN
            ),
        )


@pytest.mark.parametrize(
    "field_name",
    ["upstream_report_row_id", "transaction_payload_hash"],
)
def test_self_consistent_duplicate_upstream_transaction_identity_is_refused(
    monkeypatch,
    field_name,
):
    _evidence, inventory = _inventory(monkeypatch)
    first, second = inventory.transactions
    duplicate_value = getattr(first, field_name)
    payload = second.lineage_payload()
    payload[field_name] = duplicate_value
    forged_second = replace(
        second,
        **{
            field_name: duplicate_value,
            "transaction_observation_id": hash_payload(payload),
        },
    )
    transactions = (first, forged_second)
    forged_identity = _identity_for_rows(
        inventory,
        transactions=transactions,
    )

    with pytest.raises(
        Form4ObservedIdentityInventoryError,
        match="order or uniqueness",
    ):
        replace(
            inventory,
            identity=forged_identity,
            transactions=transactions,
            _verified_factory_token=(
                inventory_module._VERIFIED_INVENTORY_FACTORY_TOKEN
            ),
        )


@pytest.mark.parametrize(
    "owner_mode",
    ["amendment", "multiple", "missing", "incomplete"],
)
def test_self_consistent_candidate_cannot_bypass_filing_quarantine(
    monkeypatch,
    owner_mode,
):
    original_xml = None
    target_accession = AMENDMENT
    if owner_mode == "multiple":
        original_xml = (FIXTURES / "form4_joint_owners.xml").read_bytes()
        target_accession = ORIGINAL
    elif owner_mode == "missing":
        original_xml = _remove_first_owner(
            (FIXTURES / "form4_original.xml").read_bytes()
        )
        target_accession = ORIGINAL
    elif owner_mode == "incomplete":
        original_xml = (FIXTURES / "form4_original.xml").read_bytes().replace(
            b"<isOfficer>1</isOfficer>",
            b"<isOfficer>yes</isOfficer>",
            1,
        )
        target_accession = ORIGINAL
    _evidence, inventory = _inventory(
        monkeypatch,
        original_xml=original_xml,
    )
    target = next(
        item
        for item in inventory.transactions
        if item.accession_number == target_accession
    )
    transaction_payload = target.lineage_payload()
    transaction_payload["upstream_disposition"] = (
        Form4ProvisionalDisposition.PROVISIONAL_PRE_AGGREGATION_CANDIDATE.value
    )
    transaction_payload["identity_disposition"] = (
        Form4ObservedIdentityDisposition.UNRESOLVED_PROVISIONAL_CANDIDATE.value
    )
    forged_transaction = replace(
        target,
        upstream_disposition=(
            Form4ProvisionalDisposition.PROVISIONAL_PRE_AGGREGATION_CANDIDATE
        ),
        identity_disposition=(
            Form4ObservedIdentityDisposition.UNRESOLVED_PROVISIONAL_CANDIDATE
        ),
        transaction_observation_id=hash_payload(transaction_payload),
    )
    transactions = tuple(
        forged_transaction if item is target else item
        for item in inventory.transactions
    )
    identity_lineage = inventory.identity.lineage_payload()
    identity_lineage["transaction_inventory_hash"] = hash_payload(
        [item.to_payload() for item in transactions]
    )
    identity_lineage["provisional_candidate_count"] += 1
    identity_lineage["quarantine_count"] -= 1
    forged_identity = replace(
        inventory.identity,
        transaction_inventory_hash=identity_lineage[
            "transaction_inventory_hash"
        ],
        provisional_candidate_count=identity_lineage[
            "provisional_candidate_count"
        ],
        quarantine_count=identity_lineage["quarantine_count"],
        inventory_id=(
            "form4-observed-identity-inventory-"
            f"{hash_payload(identity_lineage)[:16]}"
        ),
        _verified_factory_token=(
            inventory_module._VERIFIED_IDENTITY_FACTORY_TOKEN
        ),
    )
    with pytest.raises(
        Form4ObservedIdentityInventoryError,
        match="contradicts filing quarantine",
    ):
        replace(
            inventory,
            identity=forged_identity,
            transactions=transactions,
            _verified_factory_token=(
                inventory_module._VERIFIED_INVENTORY_FACTORY_TOKEN
            ),
        )


def test_bool_count_and_tuple_subclass_are_refused(monkeypatch):
    _evidence, inventory = _inventory(monkeypatch)
    with pytest.raises(Form4ObservedIdentityInventoryError, match="counts"):
        replace(
            inventory.identity,
            filing_count=True,
            _verified_factory_token=(
                inventory_module._VERIFIED_IDENTITY_FACTORY_TOKEN
            ),
        )

    class TupleSubclass(tuple):
        pass

    forged = copy.copy(inventory)
    object.__setattr__(forged, "filings", TupleSubclass(inventory.filings))
    with pytest.raises(Form4ObservedIdentityInventoryError, match="state"):
        inventory_module.Form4ObservedIdentityInventory.__post_init__(
            forged,
            inventory_module._VERIFIED_INVENTORY_FACTORY_TOKEN,
        )


@pytest.mark.parametrize(
    "field_name",
    [
        "official_profile_compatibility_verified",
        "official_amendment_link_verified",
        "complete_amendment_coverage_verified",
        "point_in_time_issuer_identity_verified",
        "point_in_time_reporting_owner_identity_verified",
        "point_in_time_security_identity_verified",
        "point_in_time_transaction_identity_verified",
        "ordinary_equity_classification_verified",
        "canonical_filter_authorized",
        "lot_aggregation_authorized",
        "outcomes_authorized",
        "qc_execution_authorized",
        "deployment_authorized",
        "trading_authorized",
    ],
)
def test_every_inventory_authority_escalation_refuses(
    monkeypatch,
    field_name,
):
    _evidence, inventory = _inventory(monkeypatch)
    with pytest.raises(Form4ObservedIdentityInventoryError, match="authority"):
        replace(
            inventory.identity,
            **{field_name: True},
            _verified_factory_token=(
                inventory_module._VERIFIED_IDENTITY_FACTORY_TOKEN
            ),
        )


def test_look_and_transaction_authority_escalations_refuse(monkeypatch):
    _evidence, inventory = _inventory(monkeypatch)
    for field_name in ("authorized_outcome_looks", "consumed_outcome_looks"):
        with pytest.raises(
            Form4ObservedIdentityInventoryError,
            match="authority",
        ):
            replace(
                inventory.identity,
                **{field_name: 1},
                _verified_factory_token=(
                    inventory_module._VERIFIED_IDENTITY_FACTORY_TOKEN
                ),
            )
    for field_name in (
        "point_in_time_security_identity_verified",
        "canonical_filter_authorized",
        "lot_aggregation_authorized",
    ):
        with pytest.raises(
            Form4ObservedIdentityInventoryError,
            match="authority",
        ):
            replace(inventory.transactions[0], **{field_name: True})
    with pytest.raises(Form4ObservedIdentityInventoryError, match="authority"):
        replace(
            inventory.transactions[0],
            resolved_security_identity="invented-security-id",
        )
    assert inventory.authorized_outcome_looks == 0
    assert inventory.consumed_outcome_looks == 0
    assert inventory.official_profile_compatibility_verified is False
    assert inventory.official_amendment_link_verified is False
    assert inventory.complete_amendment_coverage_verified is False
    assert inventory.point_in_time_issuer_identity_verified is False
    assert inventory.point_in_time_reporting_owner_identity_verified is False
    assert inventory.point_in_time_security_identity_verified is False
    assert inventory.point_in_time_transaction_identity_verified is False
    assert inventory.ordinary_equity_classification_verified is False
    assert inventory.canonical_filter_authorized is False
    assert inventory.lot_aggregation_authorized is False
    assert inventory.outcomes_authorized is False
    assert inventory.qc_execution_authorized is False
    assert inventory.deployment_authorized is False
    assert inventory.trading_authorized is False


def test_preflight_caps_refuse_before_upstream_report(monkeypatch):
    evidence = _build_evidence(monkeypatch)
    forged_corpus = copy.copy(evidence.as_filed_corpus)
    object.__setattr__(
        forged_corpus,
        "filings",
        (evidence.as_filed_corpus.filings[0],)
        * (inventory_module.MAX_FORM4_OBSERVED_IDENTITY_FILINGS + 1),
    )
    forged_evidence = copy.copy(evidence)
    object.__setattr__(forged_evidence, "as_filed_corpus", forged_corpus)
    monkeypatch.setattr(
        inventory_module,
        "build_form4_provisional_disposition_report",
        lambda *_args, **_kwargs: pytest.fail("upstream report was reached"),
    )

    with pytest.raises(Form4ObservedIdentityInventoryError, match="resource"):
        build_form4_observed_identity_inventory(
            forged_evidence,
            builder_git_commit=BUILDER_COMMIT,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "identity_period_inventory",
        "profile_exact_fields",
        "identity_source_inventory",
        "identity_supplied_link_evidence",
        "xml_sources",
        "supplied_link_evidence",
        "lineages",
        "superseded_edges",
        "filing_footnotes",
        "transaction_footnote_ids",
    ],
)
def test_every_retained_collection_cap_refuses_before_projection_or_report(
    monkeypatch,
    mutation,
):
    evidence = _build_evidence(monkeypatch)
    if mutation == "identity_period_inventory":
        object.__setattr__(
            evidence.identity,
            "period_inventory",
            (evidence.identity.period_inventory[0],)
            * (inventory_module.MAX_FORM4_EVIDENCE_PERIODS + 1),
        )
    elif mutation == "profile_exact_fields":
        object.__setattr__(
            evidence.identity.evidence_profile,
            "exact_fields",
            (("nested",),),
        )
    elif mutation == "identity_source_inventory":
        object.__setattr__(
            evidence.identity,
            "source_inventory",
            (evidence.identity.source_inventory[0],)
            * (inventory_module.MAX_FORM4_EVIDENCE_XML_SOURCES + 1),
        )
    elif mutation == "identity_supplied_link_evidence":
        object.__setattr__(
            evidence.identity,
            "supplied_link_evidence",
            (evidence.identity.supplied_link_evidence[0],)
            * (inventory_module.MAX_FORM4_EVIDENCE_XML_SOURCES + 1),
        )
    elif mutation == "xml_sources":
        object.__setattr__(
            evidence,
            "xml_sources",
            (evidence.xml_sources[0],)
            * (inventory_module.MAX_FORM4_EVIDENCE_XML_SOURCES + 1),
        )
    elif mutation == "supplied_link_evidence":
        object.__setattr__(
            evidence,
            "supplied_link_evidence",
            (evidence.supplied_link_evidence[0],)
            * (inventory_module.MAX_FORM4_EVIDENCE_XML_SOURCES + 1),
        )
    elif mutation == "lineages":
        object.__setattr__(
            evidence,
            "lineages",
            (evidence.lineages[0],)
            * (inventory_module.MAX_FORM4_EVIDENCE_XML_SOURCES + 1),
        )
    elif mutation == "superseded_edges":
        corpus = copy.copy(evidence.as_filed_corpus)
        object.__setattr__(
            corpus,
            "superseded_by",
            (evidence.as_filed_corpus.superseded_by[0],)
            * (inventory_module.MAX_FORM4_OBSERVED_IDENTITY_FILINGS + 1),
        )
        object.__setattr__(evidence, "as_filed_corpus", corpus)
    elif mutation == "filing_footnotes":
        original = evidence.as_filed_corpus.filing(ORIGINAL)
        forged = replace(
            original,
            footnotes=(("F1", "bounded synthetic text"),)
            * (inventory_module.MAX_FOOTNOTES_PER_FILING + 1),
        )
        corpus = copy.copy(evidence.as_filed_corpus)
        object.__setattr__(
            corpus,
            "filings",
            tuple(
                forged
                if item.envelope.accession_number == ORIGINAL
                else item
                for item in corpus.filings
            ),
        )
        object.__setattr__(evidence, "as_filed_corpus", corpus)
    else:
        original = evidence.as_filed_corpus.filing(ORIGINAL)
        transaction = replace(
            original.transactions[0],
            footnote_ids=("F1",)
            * (inventory_module.MAX_FOOTNOTES_PER_FILING + 1),
        )
        forged = replace(original, transactions=(transaction,))
        corpus = copy.copy(evidence.as_filed_corpus)
        object.__setattr__(
            corpus,
            "filings",
            tuple(
                forged
                if item.envelope.accession_number == ORIGINAL
                else item
                for item in corpus.filings
            ),
        )
        object.__setattr__(evidence, "as_filed_corpus", corpus)

    monkeypatch.setattr(
        inventory_module,
        "hash_payload",
        lambda *_args, **_kwargs: pytest.fail("projection hash was reached"),
    )
    monkeypatch.setattr(
        inventory_module,
        "build_form4_provisional_disposition_report",
        lambda *_args, **_kwargs: pytest.fail("upstream report was reached"),
    )
    with pytest.raises(Form4ObservedIdentityInventoryError, match="resource"):
        build_form4_observed_identity_inventory(
            evidence,
            builder_git_commit=BUILDER_COMMIT,
        )


def test_nested_contract_cycle_refuses_before_projection_or_report(monkeypatch):
    evidence = _build_evidence(monkeypatch)
    version = evidence.lineages[0].versions[0]
    object.__setattr__(version, "accepted_at", version)
    monkeypatch.setattr(
        inventory_module,
        "build_form4_provisional_disposition_report",
        lambda *_args, **_kwargs: pytest.fail("upstream report was reached"),
    )

    with pytest.raises(Form4ObservedIdentityInventoryError, match="cycle"):
        build_form4_observed_identity_inventory(
            evidence,
            builder_git_commit=BUILDER_COMMIT,
        )


def test_malformed_identity_refuses_before_a_forgeable_report_callback(
    monkeypatch,
):
    evidence = _build_evidence(monkeypatch)
    object.__setattr__(evidence.identity, "parser_git_commit", ())
    monkeypatch.setattr(
        inventory_module,
        "build_form4_provisional_disposition_report",
        lambda *_args, **_kwargs: pytest.fail("forged callback was reached"),
    )

    with pytest.raises(
        Form4ObservedIdentityInventoryError,
        match="independent revalidation",
    ):
        build_form4_observed_identity_inventory(
            evidence,
            builder_git_commit=BUILDER_COMMIT,
        )


def test_shadowed_dataclass_method_refuses_before_it_can_execute(monkeypatch):
    evidence = _build_evidence(monkeypatch)

    def hostile_to_payload():
        pytest.fail("shadowed identity method executed")

    object.__setattr__(evidence.identity, "to_payload", hostile_to_payload)
    monkeypatch.setattr(
        inventory_module,
        "build_form4_provisional_disposition_report",
        lambda *_args, **_kwargs: pytest.fail("forged callback was reached"),
    )

    with pytest.raises(
        Form4ObservedIdentityInventoryError,
        match="instance state is not exact",
    ):
        build_form4_observed_identity_inventory(
            evidence,
            builder_git_commit=BUILDER_COMMIT,
        )


def test_dataclass_dict_subclass_refuses_before_iteration_callback(monkeypatch):
    evidence = _build_evidence(monkeypatch)

    class HostileDict(dict):
        def __iter__(self):
            pytest.fail("hostile instance-state iterator executed")

    object.__setattr__(
        evidence.identity,
        "__dict__",
        HostileDict(vars(evidence.identity)),
    )
    monkeypatch.setattr(
        inventory_module,
        "build_form4_provisional_disposition_report",
        lambda *_args, **_kwargs: pytest.fail("upstream report was reached"),
    )

    with pytest.raises(
        Form4ObservedIdentityInventoryError,
        match="instance state is not exact",
    ):
        build_form4_observed_identity_inventory(
            evidence,
            builder_git_commit=BUILDER_COMMIT,
        )


def test_deep_acyclic_contract_graph_refuses_before_python_recursion(
    monkeypatch,
):
    evidence = _build_evidence(monkeypatch)
    nested = "synthetic"
    for _ in range(
        inventory_module.MAX_FORM4_OBSERVED_IDENTITY_PROJECTION_DEPTH + 1
    ):
        nested = (nested,)
    object.__setattr__(evidence.identity, "evidence_id", nested)
    monkeypatch.setattr(
        inventory_module,
        "build_form4_provisional_disposition_report",
        lambda *_args, **_kwargs: pytest.fail("upstream report was reached"),
    )

    with pytest.raises(Form4ObservedIdentityInventoryError, match="depth"):
        build_form4_observed_identity_inventory(
            evidence,
            builder_git_commit=BUILDER_COMMIT,
        )


def test_projection_rejects_an_unapproved_nested_enum_before_report(monkeypatch):
    evidence = _build_evidence(monkeypatch)
    owner = evidence.as_filed_corpus.filing(ORIGINAL).reporting_owners[0]
    object.__setattr__(
        owner,
        "owner_name",
        Form4ObservedOwnerSetOutcome.MISSING_OWNER_SET_QUARANTINED,
    )
    monkeypatch.setattr(
        inventory_module,
        "build_form4_provisional_disposition_report",
        lambda *_args, **_kwargs: pytest.fail("upstream report was reached"),
    )

    with pytest.raises(
        Form4ObservedIdentityInventoryError,
        match="unsupported",
    ):
        build_form4_observed_identity_inventory(
            evidence,
            builder_git_commit=BUILDER_COMMIT,
        )


def test_projection_rejects_hostile_metaclass_without_attribute_lookup(
    monkeypatch,
):
    evidence = _build_evidence(monkeypatch)

    class HostileMeta(type):
        def __getattribute__(cls, name):
            if name == "__dataclass_fields__":
                pytest.fail("hostile metaclass callback executed")
            return super().__getattribute__(name)

    class HostileValue(metaclass=HostileMeta):
        pass

    owner = evidence.as_filed_corpus.filing(ORIGINAL).reporting_owners[0]
    object.__setattr__(owner, "owner_name", HostileValue())
    monkeypatch.setattr(
        inventory_module,
        "build_form4_provisional_disposition_report",
        lambda *_args, **_kwargs: pytest.fail("upstream report was reached"),
    )

    with pytest.raises(Form4ObservedIdentityInventoryError, match="unsupported"):
        build_form4_observed_identity_inventory(
            evidence,
            builder_git_commit=BUILDER_COMMIT,
        )


def test_projection_rejects_non_utc_datetime_before_report(monkeypatch):
    evidence = _build_evidence(monkeypatch)
    source = evidence.xml_sources[0]
    object.__setattr__(
        source,
        "retrieved_at",
        source.retrieved_at.astimezone(timezone(timedelta(hours=1))),
    )
    monkeypatch.setattr(
        inventory_module,
        "build_form4_provisional_disposition_report",
        lambda *_args, **_kwargs: pytest.fail("upstream report was reached"),
    )

    with pytest.raises(
        Form4ObservedIdentityInventoryError,
        match="exact UTC",
    ):
        build_form4_observed_identity_inventory(
            evidence,
            builder_git_commit=BUILDER_COMMIT,
        )


def test_decimal_projection_consumes_the_shared_text_budget(monkeypatch):
    monkeypatch.setattr(
        inventory_module,
        "MAX_FORM4_OBSERVED_IDENTITY_TEXT_CHARACTERS",
        3,
    )
    with pytest.raises(Form4ObservedIdentityInventoryError, match="resource"):
        inventory_module._contract_payload(Decimal("1234"))


def test_text_cap_refuses_before_upstream_report(monkeypatch):
    evidence = _build_evidence(monkeypatch)
    monkeypatch.setattr(
        inventory_module,
        "MAX_FORM4_OBSERVED_IDENTITY_TEXT_CHARACTERS",
        1,
    )
    monkeypatch.setattr(
        inventory_module,
        "build_form4_provisional_disposition_report",
        lambda *_args, **_kwargs: pytest.fail("upstream report was reached"),
    )
    with pytest.raises(Form4ObservedIdentityInventoryError, match="resource"):
        build_form4_observed_identity_inventory(
            evidence,
            builder_git_commit=BUILDER_COMMIT,
        )


@pytest.mark.parametrize(
    "builder_git_commit",
    [None, True, "", "F" * 40, "f" * 39, "g" * 40],
)
def test_builder_commit_requires_full_lowercase_sha1(
    monkeypatch,
    builder_git_commit,
):
    evidence = _build_evidence(monkeypatch)
    with pytest.raises(Form4ObservedIdentityInventoryError, match="Git commit"):
        build_form4_observed_identity_inventory(
            evidence,
            builder_git_commit=builder_git_commit,
        )


def test_missing_retained_state_uses_the_public_lane_error(monkeypatch):
    evidence = copy.copy(_build_evidence(monkeypatch))
    object.__delattr__(evidence, "as_filed_corpus")
    with pytest.raises(
        Form4ObservedIdentityInventoryError,
        match="missing|malformed",
    ):
        build_form4_observed_identity_inventory(
            evidence,
            builder_git_commit=BUILDER_COMMIT,
        )


def test_unrepresentable_retained_acceptance_uses_the_public_lane_error(
    monkeypatch,
):
    evidence = _build_evidence(monkeypatch)
    availability = evidence.as_filed_corpus.filing(
        ORIGINAL
    ).envelope.availability
    object.__setattr__(
        availability,
        "accepted_at",
        datetime(1, 1, 1, tzinfo=timezone(timedelta(hours=14))),
    )
    with pytest.raises(
        Form4ObservedIdentityInventoryError,
        match="malformed|exact UTC",
    ):
        build_form4_observed_identity_inventory(
            evidence,
            builder_git_commit=BUILDER_COMMIT,
        )


def test_inventory_payload_is_deeply_detached(monkeypatch):
    evidence, inventory = _inventory(monkeypatch)
    expected = inventory.to_payload()
    payload = inventory.to_payload()
    payload["identity"]["filing_count"] = 99
    payload["filings"][0]["owner_set_outcomes"].append("forged")
    payload["reporting_owners"][0]["owner_name"] = "forged"
    payload["transactions"][0]["security_title_raw"] = "forged"

    assert inventory.to_payload() == expected
    assert type(inventory.filings) is tuple
    assert type(inventory.reporting_owners) is tuple
    assert type(inventory.transactions) is tuple

    retained_owner = evidence.as_filed_corpus.filing(ORIGINAL).reporting_owners[0]
    object.__setattr__(retained_owner, "owner_name", "mutated after build")
    assert inventory.to_payload() == expected


@pytest.mark.parametrize("title", ["Common Stock", "Class A Common Stock"])
def test_supported_titles_remain_unresolved_observations(monkeypatch, title):
    xml_bytes = (FIXTURES / "form4_original.xml").read_bytes().replace(
        b"<value>Common Stock</value>",
        f"<value>{title}</value>".encode(),
        1,
    )
    _evidence, inventory = _inventory(monkeypatch, original_xml=xml_bytes)
    row = next(
        item for item in inventory.transactions if item.accession_number == ORIGINAL
    )
    assert row.security_title_raw == title
    assert row.upstream_disposition is (
        Form4ProvisionalDisposition.PROVISIONAL_PRE_AGGREGATION_CANDIDATE
    )
    assert row.identity_disposition is (
        Form4ObservedIdentityDisposition.UNRESOLVED_PROVISIONAL_CANDIDATE
    )
    assert row.resolved_security_identity is None
    assert row.point_in_time_security_identity_verified is False


@pytest.mark.parametrize(
    "title",
    ["Ordinary Shares", "Class A Ordinary Shares", "Common Shares"],
)
def test_share_title_variants_remain_unresolved_quarantine(
    monkeypatch,
    title,
):
    xml_bytes = (FIXTURES / "form4_original.xml").read_bytes().replace(
        b"<value>Common Stock</value>",
        f"<value>{title}</value>".encode(),
        1,
    )
    _evidence, inventory = _inventory(monkeypatch, original_xml=xml_bytes)
    row = next(
        item for item in inventory.transactions if item.accession_number == ORIGINAL
    )
    assert row.security_title_raw == title
    assert row.upstream_disposition is (
        Form4ProvisionalDisposition.PROVISIONAL_QUARANTINE
    )
    assert row.identity_disposition is (
        Form4ObservedIdentityDisposition.UNRESOLVED_QUARANTINE
    )
    assert row.resolved_security_identity is None


def test_ib2a_module_has_no_float_network_outcome_qc_or_execution_surface():
    module_path = Path(inventory_module.__file__)
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(module_path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])
    allowed = {
        "__future__",
        "data",
        "dataclasses",
        "datetime",
        "decimal",
        "enum",
        "re",
        "research",
    }
    assert imported <= allowed, imported - allowed
    assert not any(
        isinstance(node, ast.Name) and node.id == "float"
        for node in ast.walk(tree)
    )
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "__import__"
        for node in ast.walk(tree)
    )
    assert not any(
        token.type == tokenize.NUMBER
        and any(marker in token.string.lower() for marker in (".", "e"))
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
    )
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "open"
        for node in ast.walk(tree)
    )


# ---------------------------------------------------------------------------
# Claude review regressions (2026-09-03). A targeted mutation sweep of the
# eight IB-2A dangerous directions left several guards standing with the suite
# green. Each test below pins one such guard so it can no longer be deleted
# silently. Guards proven redundant behind an earlier check are recorded in
# the lane record instead of being given a test that could only pass by
# mutating the earlier check.
# ---------------------------------------------------------------------------


def test_evidence_mutation_during_independent_revalidation_is_refused(
    monkeypatch,
):
    """Direction 1: the re-fingerprint immediately after reparse must fire.

    The post-validation check is already pinned. This reaches the earlier
    intermediate check by mutating the evidence as a side effect of the
    reparse itself, which is the window that check exists to close.
    """
    evidence = _build_evidence(monkeypatch)
    real_reparse = inventory_module._reparse_profile_bound_evidence

    def mutating_reparse(*args, **kwargs):
        result = real_reparse(*args, **kwargs)
        object.__setattr__(evidence.identity, "canonical_filter_authorized", True)
        return result

    monkeypatch.setattr(
        inventory_module, "_reparse_profile_bound_evidence", mutating_reparse
    )
    with pytest.raises(
        Form4ObservedIdentityInventoryError,
        match="changed during independent revalidation",
    ):
        build_form4_observed_identity_inventory(
            evidence, builder_git_commit=BUILDER_COMMIT
        )


def test_forged_report_disposition_alone_cannot_drift_from_captured_evidence(
    monkeypatch,
):
    """Direction 3: disposition is derived after the payload hash is taken, so
    the hash does not bind it. IB-2A therefore replays every rebuilt row's
    constructor, which re-applies the disposition-to-outcomes binding even
    when a forgery bypassed that constructor. This pins the replay: a row
    whose disposition drifts while outcomes and payload hash stay intact must
    be refused there, before any comparison with retained evidence."""
    evidence = _build_evidence(monkeypatch)
    real_builder = inventory_module.build_form4_provisional_disposition_report

    def forge_report(*args, **kwargs):
        report = real_builder(*args, **kwargs)
        target = next(
            row
            for row in report.rows
            if row.disposition
            is Form4ProvisionalDisposition.PROVISIONAL_PRE_AGGREGATION_CANDIDATE
        )
        row_payload = target.lineage_payload()
        row_payload["disposition"] = (
            Form4ProvisionalDisposition.PROVISIONAL_QUARANTINE.value
        )
        # The report row constructor already refuses this through replace()
        # ("provisional disposition contradicts parser outcomes"), so the
        # forgery deliberately bypasses the constructor, exactly as the
        # identity forgeries above do, to reach the IB-2A binding itself.
        forged_target = copy.copy(target)
        object.__setattr__(
            forged_target,
            "disposition",
            Form4ProvisionalDisposition.PROVISIONAL_QUARANTINE,
        )
        object.__setattr__(forged_target, "row_id", hash_payload(row_payload))
        assert forged_target.outcomes == target.outcomes
        assert (
            forged_target.transaction_payload_hash
            == target.transaction_payload_hash
        )
        rows = tuple(
            forged_target if row is target else row for row in report.rows
        )
        identity = copy.copy(report.identity)
        object.__setattr__(
            identity, "candidate_count", report.identity.candidate_count - 1
        )
        object.__setattr__(
            identity, "quarantine_count", report.identity.quarantine_count + 1
        )
        object.__setattr__(
            identity,
            "row_inventory_hash",
            hash_payload([row.to_payload() for row in rows]),
        )
        object.__setattr__(
            identity,
            "report_id",
            (
                "form4-provisional-disposition-report-"
                f"{hash_payload(identity.lineage_payload())[:16]}"
            ),
        )
        forged = copy.copy(report)
        object.__setattr__(forged, "identity", identity)
        object.__setattr__(forged, "rows", rows)
        return forged

    monkeypatch.setattr(
        inventory_module,
        "build_form4_provisional_disposition_report",
        forge_report,
    )
    with pytest.raises(
        Form4ObservedIdentityInventoryError,
        match="rebuilt upstream report row is invalid",
    ):
        build_form4_observed_identity_inventory(
            evidence, builder_git_commit=BUILDER_COMMIT
        )


def test_filing_cannot_list_one_owner_observation_twice(monkeypatch):
    """Direction 6: a filing whose owner set repeats one observation id would
    let a single owner count twice. A combined mutant that neutralised all
    three owner-uniqueness clauses left the suite green; this pins the
    filing-level clause, the first line that construction actually reaches."""
    _evidence, inventory = _inventory(monkeypatch)
    filing = next(
        row for row in inventory.filings if row.accession_number == ORIGINAL
    )
    assert filing.reporting_owner_count == 1
    (owner_id,) = filing.reporting_owner_observation_ids

    payload = filing.lineage_payload()
    payload["reporting_owner_count"] = 2
    payload["owner_set_outcomes"] = [
        Form4ObservedOwnerSetOutcome.MULTIPLE_OWNER_SET_QUARANTINED.value
    ]
    payload["reporting_owner_observation_ids"] = [owner_id, owner_id]

    with pytest.raises(
        Form4ObservedIdentityInventoryError,
        match="filing owner-set observation is inconsistent",
    ):
        replace(
            filing,
            reporting_owner_count=2,
            owner_set_outcomes=(
                Form4ObservedOwnerSetOutcome.MULTIPLE_OWNER_SET_QUARANTINED,
            ),
            reporting_owner_observation_ids=(owner_id, owner_id),
            filing_observation_id=hash_payload(payload),
        )
