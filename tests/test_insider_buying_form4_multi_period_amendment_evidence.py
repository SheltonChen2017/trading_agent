"""IB-1E supplied-link-evidence and IB-1G disposition-report tests.

All records and XML images are synthetic.  The profile below is deliberately
non-official: these tests establish fail-closed composition and provisional
report boundaries, not SEC provenance, complete amendment coverage, canonical
filtering, aggregation, outcomes, or trading authority.
"""
from __future__ import annotations

import ast
import copy
from dataclasses import dataclass, fields, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying import (
    ClassificationOutcome,
    Form4ProvisionalDisposition,
    Form4ProvisionalDispositionReportError,
    Form4MultiPeriodEvidenceError,
    ParsedTransaction,
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
    build_form4_provisional_disposition_report,
)
from research.insider_buying import (
    form4_multi_period_amendment_evidence as evidence_module,
)
from research.insider_buying import (
    form4_provisional_disposition_report as disposition_module,
)
from research.insider_buying.sec_edgar_acceptance_snapshot import (
    LoadedSecEdgarAcceptanceSnapshot,
)


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "insider_buying"
ORIGINAL = "0000123456-26-000001"
OTHER_ORIGINAL = "0000123456-26-000003"
AMENDMENT = "0000123456-27-000002"
PARSER_COMMIT = "e" * 40
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
    issuer_cik: str = "123456"
    primary_document_sha256: str | None = None


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _profile(*, exact_fields: tuple[str, ...] = EXACT_FIELDS):
    return SecEdgarMetadataSchemaProfile(
        profile_id="synthetic-non-official-ib1e-qc-v1",
        exact_fields=exact_fields,
        accession_number_field="accession",
        form_type_field="form",
        filing_date_field="filed",
        accepted_at_field="accepted",
        primary_document_url_field="primary_url",
        valid_from_year=2026,
        valid_from_quarter=4,
        valid_through_year=2027,
        valid_through_quarter=4,
    )


def _primary_url(spec: _Spec) -> str:
    return (
        "https://www.sec.gov/Archives/edgar/data/"
        f"{spec.issuer_cik}/{spec.accession.replace('-', '')}/primary.xml"
    )


def _loaded_period(
    year: int,
    quarter: int,
    specs: tuple[_Spec, ...],
    *,
    profile: SecEdgarMetadataSchemaProfile | None = None,
) -> LoadedSecEdgarAcceptanceSnapshot:
    profile = profile or _profile()
    records: list[SecEdgarAvailabilityRecord] = []
    sources: list[SecEdgarMetadataSource] = []
    source_identities: list[SecEdgarMetadataSourceIdentity] = []
    for spec in sorted(specs, key=lambda item: item.accession):
        url = _primary_url(spec)
        payload = {
            "accession": spec.accession,
            "form": spec.form,
            "filed": spec.accepted_at.date().isoformat(),
            "accepted": spec.accepted_at.isoformat(timespec="seconds"),
            "primary_url": url,
            "amends_accession": spec.amends_accession or "",
            "primary_document_sha256": (
                spec.primary_document_sha256 or hash_bytes(spec.xml_bytes)
            ),
        }
        payload = {name: payload[name] for name in profile.exact_fields}
        metadata_bytes = (canonical_json(payload) + "\n").encode("utf-8")
        source = SecEdgarMetadataSource(
            metadata_bytes=metadata_bytes,
            source_url=(
                "https://www.sec.gov/Archives/edgar/data/"
                f"{spec.issuer_cik}/{spec.accession.replace('-', '')}/metadata.json"
            ),
            retrieved_at=spec.accepted_at + timedelta(days=1),
            capture_git_commit=CAPTURE_COMMIT,
        )
        record = SecEdgarAvailabilityRecord(
            accession_number=spec.accession,
            document_type=spec.form,
            submission_row_id=hash_payload({"accession": spec.accession}),
            filing_date=spec.accepted_at.date(),
            availability_tier=(
                SecEdgarAvailabilityTier.EXACT_ACCEPTANCE_TIMESTAMP
            ),
            next_open_rule=(
                SecEdgarAvailabilityRule.NEXT_OPEN_AFTER_ACCEPTANCE
            ),
            accepted_at=spec.accepted_at,
            primary_document_url=url,
            metadata_source_sha256=source.metadata_sha256,
        )
        records.append(record)
        sources.append(source)
        source_identities.append(
            SecEdgarMetadataSourceIdentity(
                accession_number=spec.accession,
                metadata_sha256=source.metadata_sha256,
                metadata_size_bytes=len(source.metadata_bytes),
                source_url=source.source_url,
                retrieved_at_utc=source.retrieved_at_utc,
                capture_git_commit=source.capture_git_commit,
            )
        )

    records_tuple = tuple(records)
    sources_tuple = tuple(sources)
    inventory = tuple(source_identities)
    profile_hash = hash_payload(profile.to_payload())
    parsed_hash = hash_payload({"parsed": [year, quarter]})
    raw_hash = hash_payload({"raw": [year, quarter]})
    archive_hash = hash_payload({"archive": [year, quarter]})
    lineage_hash = hash_payload(
        {
            "period": [year, quarter],
            "profile_hash": profile_hash,
            "records": [item.to_payload() for item in records_tuple],
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
        source_inventory=inventory,
        source_inventory_hash=hash_payload(
            [item.to_payload() for item in inventory]
        ),
        record_count=len(records_tuple),
        exact_acceptance_count=len(records_tuple),
        filing_date_fallback_count=0,
        records_hash=hash_payload(
            [item.to_payload() for item in records_tuple]
        ),
        lineage_hash=lineage_hash,
        snapshot_id=(
            f"sec-edgar-acceptance-{year:04d}q{quarter}-"
            f"{lineage_hash[:16]}"
        ),
    )
    return LoadedSecEdgarAcceptanceSnapshot(
        identity=identity,
        records=records_tuple,
        sources=sources_tuple,
    )


def _period(year: int, quarter: int) -> SecEdgarAcceptancePeriodInput:
    return SecEdgarAcceptancePeriodInput(
        acceptance_snapshot_path=f"{year}q{quarter}.json",
        parsed_snapshot_directory=f"parsed-{year}q{quarter}",
        raw_snapshot_directory=f"raw-{year}q{quarter}",
    )


def _install_loader(monkeypatch, loaded_periods) -> None:
    by_name = {
        f"{loaded.identity.year}q{loaded.identity.quarter}.json": loaded
        for loaded in loaded_periods
    }

    def fake_loader(snapshot_path, **_kwargs):
        return by_name[Path(snapshot_path).name]

    monkeypatch.setattr(
        evidence_module.acceptance_module,
        "load_sec_edgar_acceptance_snapshot",
        fake_loader,
    )


def _xml_source(spec: _Spec, *, asserted_target: str | None = None):
    return SecForm4XmlSource(
        accession_number=spec.accession,
        xml_bytes=spec.xml_bytes,
        primary_document_url=_primary_url(spec),
        retrieved_at=spec.accepted_at + timedelta(days=2),
        capture_git_commit=CAPTURE_COMMIT,
        amends_accession=(
            spec.amends_accession
            if asserted_target is None
            else asserted_target
        ),
    )


def _evidence_profile(profile: SecEdgarMetadataSchemaProfile):
    return SecForm4AmendmentEvidenceProfile(
        profile_id="synthetic-non-official-ib1e-link-evidence-v1",
        exact_fields=EXACT_FIELDS,
        amends_accession_field="amends_accession",
        primary_document_sha256_field="primary_document_sha256",
        upstream_metadata_profile_hash=hash_payload(profile.to_payload()),
        valid_from_year=2026,
        valid_from_quarter=4,
        valid_through_year=2027,
        valid_through_quarter=4,
        official_sec_profile_verified=False,
    )


@pytest.fixture
def baseline(monkeypatch):
    original = _Spec(
        ORIGINAL,
        "4",
        datetime(2026, 12, 29, 18, 0, tzinfo=timezone.utc),
        _fixture("form4_original.xml"),
    )
    amendment = _Spec(
        AMENDMENT,
        "4/A",
        datetime(2027, 1, 4, 18, 0, tzinfo=timezone.utc),
        _fixture("form4_amendment.xml"),
        ORIGINAL,
    )
    profile = _profile()
    q4 = _loaded_period(2026, 4, (original,), profile=profile)
    q1 = _loaded_period(2027, 1, (amendment,), profile=profile)
    _install_loader(monkeypatch, (q4, q1))
    return original, amendment, profile, q4, q1


def _assemble(original, amendment, profile, *, reverse=False):
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


def test_cross_year_lineage_is_observation_only_and_order_independent(baseline):
    original, amendment, profile, _q4, _q1 = baseline
    forward = _assemble(original, amendment, profile)
    reverse = _assemble(original, amendment, profile, reverse=True)

    assert forward == reverse
    assert forward.identity.declared_period_set_contiguous is True
    assert forward.official_amendment_link_verified is False
    assert forward.complete_amendment_coverage_verified is False
    assert forward.canonical_filter_authorized is False
    assert tuple(
        version.accession_number for version in forward.lineage(ORIGINAL).versions
    ) == (ORIGINAL, AMENDMENT)
    observed = forward.observed_state_at(
        ORIGINAL, datetime(2026, 12, 30, tzinfo=timezone.utc)
    )
    assert observed is not None
    assert observed.accession_number == ORIGINAL
    assert not hasattr(observed, "next_supplied_acceptance_at")


@pytest.mark.parametrize(
    "periods",
    [
        (_period(2026, 4), _period(2027, 2)),
        (_period(2026, 4), _period(2026, 4)),
    ],
)
def test_period_gap_and_overlap_refuse_before_xml_parsing(
    monkeypatch, baseline, periods
):
    original, amendment, profile, q4, q1 = baseline
    q2_amendment = replace(
        amendment,
        accepted_at=datetime(2027, 4, 4, 18, 0, tzinfo=timezone.utc),
    )
    q2 = _loaded_period(2027, 2, (q2_amendment,), profile=profile)
    _install_loader(monkeypatch, (q4, q1, q2))
    supplied_amendment = (
        q2_amendment if periods[-1] == _period(2027, 2) else amendment
    )
    monkeypatch.setattr(
        evidence_module,
        "parse_form4_xml",
        lambda *_args, **_kwargs: pytest.fail("XML parser was reached"),
    )
    with pytest.raises(Form4MultiPeriodEvidenceError, match="period"):
        assemble_sec_form4_multi_period_evidence(
            periods,
            sources=(_xml_source(original), _xml_source(supplied_amendment)),
            evidence_profile=_evidence_profile(profile),
            parser_git_commit=PARSER_COMMIT,
        )


def test_duplicate_accession_across_verified_periods_refuses(monkeypatch):
    spec = _Spec(
        ORIGINAL,
        "4",
        datetime(2026, 12, 29, 18, 0, tzinfo=timezone.utc),
        _fixture("form4_original.xml"),
    )
    later = replace(
        spec, accepted_at=datetime(2027, 1, 4, 18, 0, tzinfo=timezone.utc)
    )
    profile = _profile()
    _install_loader(
        monkeypatch,
        (
            _loaded_period(2026, 4, (spec,), profile=profile),
            _loaded_period(2027, 1, (later,), profile=profile),
        ),
    )
    with pytest.raises(Form4MultiPeriodEvidenceError, match="duplicate accession"):
        assemble_sec_form4_multi_period_evidence(
            (_period(2026, 4), _period(2027, 1)),
            sources=(_xml_source(spec),),
            evidence_profile=_evidence_profile(profile),
            parser_git_commit=PARSER_COMMIT,
        )


def test_profile_link_and_caller_link_must_agree(monkeypatch):
    accepted = datetime(2026, 12, 29, 18, 0, tzinfo=timezone.utc)
    original = _Spec(ORIGINAL, "4", accepted, _fixture("form4_original.xml"))
    other = _Spec(
        OTHER_ORIGINAL,
        "4",
        accepted + timedelta(hours=1),
        _fixture("form4_original.xml"),
    )
    amendment = _Spec(
        AMENDMENT,
        "4/A",
        datetime(2027, 1, 4, 18, 0, tzinfo=timezone.utc),
        _fixture("form4_amendment.xml"),
        ORIGINAL,
    )
    profile = _profile()
    _install_loader(
        monkeypatch,
        (
            _loaded_period(2026, 4, (original, other), profile=profile),
            _loaded_period(2027, 1, (amendment,), profile=profile),
        ),
    )
    with pytest.raises(Form4MultiPeriodEvidenceError, match="link"):
        assemble_sec_form4_multi_period_evidence(
            (_period(2026, 4), _period(2027, 1)),
            sources=(
                _xml_source(original),
                _xml_source(other),
                _xml_source(amendment, asserted_target=OTHER_ORIGINAL),
            ),
            evidence_profile=_evidence_profile(profile),
            parser_git_commit=PARSER_COMMIT,
        )


def test_cross_period_lineage_refuses_missing_target_cross_issuer_and_reversal(
    monkeypatch,
):
    profile = _profile()
    original_time = datetime(2026, 12, 29, 18, 0, tzinfo=timezone.utc)
    amendment_time = datetime(2027, 1, 4, 18, 0, tzinfo=timezone.utc)
    original = _Spec(
        ORIGINAL, "4", original_time, _fixture("form4_original.xml")
    )

    missing_target = _Spec(
        AMENDMENT,
        "4/A",
        amendment_time,
        _fixture("form4_amendment.xml"),
        "0000123456-26-999999",
    )
    _install_loader(
        monkeypatch,
        (
            _loaded_period(2026, 4, (original,), profile=profile),
            _loaded_period(2027, 1, (missing_target,), profile=profile),
        ),
    )
    with pytest.raises(Form4MultiPeriodEvidenceError, match="lineage"):
        assemble_sec_form4_multi_period_evidence(
            (_period(2026, 4), _period(2027, 1)),
            sources=(_xml_source(original), _xml_source(missing_target)),
            evidence_profile=_evidence_profile(profile),
            parser_git_commit=PARSER_COMMIT,
        )

    other_issuer_xml = _fixture("form4_amendment.xml").replace(
        b"<issuerCik>123456</issuerCik>",
        b"<issuerCik>654321</issuerCik>",
    )
    cross_issuer = _Spec(
        AMENDMENT,
        "4/A",
        amendment_time,
        other_issuer_xml,
        ORIGINAL,
        issuer_cik="654321",
    )
    _install_loader(
        monkeypatch,
        (
            _loaded_period(2026, 4, (original,), profile=profile),
            _loaded_period(2027, 1, (cross_issuer,), profile=profile),
        ),
    )
    with pytest.raises(Form4MultiPeriodEvidenceError, match="lineage"):
        assemble_sec_form4_multi_period_evidence(
            (_period(2026, 4), _period(2027, 1)),
            sources=(_xml_source(original), _xml_source(cross_issuer)),
            evidence_profile=_evidence_profile(profile),
            parser_git_commit=PARSER_COMMIT,
        )

    early_amendment = _Spec(
        "0000123456-26-000004",
        "4/A",
        original_time,
        _fixture("form4_amendment.xml"),
        ORIGINAL,
    )
    late_original = replace(
        original, accepted_at=original_time + timedelta(hours=1)
    )
    q1_unsupplied = _Spec(
        "0000123456-27-000005",
        "4",
        amendment_time,
        _fixture("form4_original.xml"),
    )
    _install_loader(
        monkeypatch,
        (
            _loaded_period(
                2026,
                4,
                (early_amendment, late_original),
                profile=profile,
            ),
            _loaded_period(2027, 1, (q1_unsupplied,), profile=profile),
        ),
    )
    with pytest.raises(Form4MultiPeriodEvidenceError, match="lineage"):
        assemble_sec_form4_multi_period_evidence(
            (_period(2026, 4), _period(2027, 1)),
            sources=(_xml_source(early_amendment), _xml_source(late_original)),
            evidence_profile=_evidence_profile(profile),
            parser_git_commit=PARSER_COMMIT,
        )


def test_profile_hash_binding_refuses_same_form_xml_swap(baseline):
    original, amendment, profile, _q4, _q1 = baseline
    altered = replace(
        amendment,
        xml_bytes=amendment.xml_bytes.replace(b"6000", b"6001"),
    )
    with pytest.raises(Form4MultiPeriodEvidenceError, match="document hash"):
        assemble_sec_form4_multi_period_evidence(
            (_period(2026, 4), _period(2027, 1)),
            sources=(_xml_source(original), _xml_source(altered)),
            evidence_profile=_evidence_profile(profile),
            parser_git_commit=PARSER_COMMIT,
        )


def test_same_quarter_lineage_retains_only_supplied_versions_and_not_coverage(
    monkeypatch,
):
    profile = _profile()
    original = _Spec(
        ORIGINAL,
        "4",
        datetime(2026, 12, 28, 18, 0, tzinfo=timezone.utc),
        _fixture("form4_original.xml"),
    )
    same_quarter_amendment = _Spec(
        "0000123456-26-000004",
        "4/A",
        datetime(2026, 12, 29, 18, 0, tzinfo=timezone.utc),
        _fixture("form4_amendment.xml"),
        ORIGINAL,
    )
    omitted_later_amendment = _Spec(
        AMENDMENT,
        "4/A",
        datetime(2027, 1, 4, 18, 0, tzinfo=timezone.utc),
        _fixture("form4_amendment.xml"),
        ORIGINAL,
    )
    _install_loader(
        monkeypatch,
        (
            _loaded_period(
                2026,
                4,
                (original, same_quarter_amendment),
                profile=profile,
            ),
            _loaded_period(
                2027, 1, (omitted_later_amendment,), profile=profile
            ),
        ),
    )
    result = assemble_sec_form4_multi_period_evidence(
        (_period(2026, 4), _period(2027, 1)),
        sources=(_xml_source(original), _xml_source(same_quarter_amendment)),
        evidence_profile=_evidence_profile(profile),
        parser_git_commit=PARSER_COMMIT,
    )

    assert tuple(
        version.accession_number for version in result.lineage(ORIGINAL).versions
    ) == (ORIGINAL, same_quarter_amendment.accession)
    assert {
        filing.envelope.accession_number for filing in result.as_filed_corpus.filings
    } == {ORIGINAL, same_quarter_amendment.accession}
    assert omitted_later_amendment.accession not in {
        item.accession_number for item in result.supplied_link_evidence
    }
    amended = result.as_filed_corpus.filing(same_quarter_amendment.accession)
    original_filing = result.as_filed_corpus.filing(ORIGINAL)
    assert original_filing.transactions
    assert all(
        transaction.outcomes
        == (ClassificationOutcome.ELIGIBLE_FOR_LOT_AGGREGATION,)
        for transaction in original_filing.transactions
    )
    assert amended.transactions
    assert all(
        transaction.outcomes
        == (ClassificationOutcome.EXCLUDE_AMENDED_FILING,)
        for transaction in amended.transactions
    )
    assert result.complete_amendment_coverage_verified is False


def test_coherent_alternate_same_issuer_target_remains_non_official(monkeypatch):
    profile = _profile()
    accepted = datetime(2026, 12, 28, 18, 0, tzinfo=timezone.utc)
    original = _Spec(ORIGINAL, "4", accepted, _fixture("form4_original.xml"))
    alternate = _Spec(
        OTHER_ORIGINAL,
        "4",
        accepted + timedelta(hours=1),
        _fixture("form4_original.xml"),
    )
    amendment = _Spec(
        AMENDMENT,
        "4/A",
        datetime(2027, 1, 4, 18, 0, tzinfo=timezone.utc),
        _fixture("form4_amendment.xml"),
        OTHER_ORIGINAL,
    )
    _install_loader(
        monkeypatch,
        (
            _loaded_period(2026, 4, (original, alternate), profile=profile),
            _loaded_period(2027, 1, (amendment,), profile=profile),
        ),
    )
    result = assemble_sec_form4_multi_period_evidence(
        (_period(2026, 4), _period(2027, 1)),
        sources=(
            _xml_source(original),
            _xml_source(alternate),
            _xml_source(amendment),
        ),
        evidence_profile=_evidence_profile(profile),
        parser_git_commit=PARSER_COMMIT,
    )

    assert tuple(
        item.accession_number for item in result.lineage(OTHER_ORIGINAL).versions
    ) == (OTHER_ORIGINAL, AMENDMENT)
    assert result.official_amendment_link_verified is False
    assert result.canonical_filter_authorized is False


def test_profile_drift_and_date_only_fallback_refuse(monkeypatch, baseline):
    original, amendment, profile, q4, q1 = baseline
    drift_profile = _profile(
        exact_fields=EXACT_FIELDS[:-1],
    )
    drift_q1 = _loaded_period(2027, 1, (amendment,), profile=drift_profile)
    _install_loader(monkeypatch, (q4, drift_q1))
    with pytest.raises(Form4MultiPeriodEvidenceError, match="profile"):
        _assemble(original, amendment, profile)

    fallback_record = replace(
        q1.records[0],
        availability_tier=SecEdgarAvailabilityTier.FILING_DATE_FALLBACK,
        next_open_rule=SecEdgarAvailabilityRule.NEXT_OPEN_AFTER_FILING_DATE,
        accepted_at=None,
        primary_document_url=None,
        metadata_source_sha256=None,
    )
    fallback_identity = replace(
        q1.identity,
        source_inventory=(),
        source_inventory_hash=hash_payload([]),
        exact_acceptance_count=0,
        filing_date_fallback_count=1,
        records_hash=hash_payload([fallback_record.to_payload()]),
    )
    fallback_lineage_hash = hash_payload(
        {
            "period": [2027, 1],
            "profile_hash": fallback_identity.metadata_profile_hash,
            "records": [fallback_record.to_payload()],
        }
    )
    fallback_identity = replace(
        fallback_identity,
        lineage_hash=fallback_lineage_hash,
        snapshot_id=(
            "sec-edgar-acceptance-2027q1-"
            f"{fallback_lineage_hash[:16]}"
        ),
    )
    _install_loader(
        monkeypatch,
        (
            q4,
            replace(
                q1,
                identity=fallback_identity,
                records=(fallback_record,),
                sources=(),
            ),
        ),
    )
    with pytest.raises(Form4MultiPeriodEvidenceError, match="exact acceptance"):
        _assemble(original, amendment, profile)


def test_period_cap_refuses_before_loading(monkeypatch, baseline):
    original, amendment, profile, _q4, _q1 = baseline
    monkeypatch.setattr(
        evidence_module.acceptance_module,
        "load_sec_edgar_acceptance_snapshot",
        lambda *_args, **_kwargs: pytest.fail("loader was reached"),
    )
    periods = tuple(
        _period(2026 + index // 4, index % 4 + 1)
        for index in range(evidence_module.MAX_FORM4_EVIDENCE_PERIODS + 1)
    )
    with pytest.raises(Form4MultiPeriodEvidenceError, match="period inputs"):
        assemble_sec_form4_multi_period_evidence(
            periods,
            sources=(_xml_source(original), _xml_source(amendment)),
            evidence_profile=_evidence_profile(profile),
            parser_git_commit=PARSER_COMMIT,
        )


def test_aggregate_record_cap_refuses_before_xml_parsing(monkeypatch, baseline):
    original, amendment, profile, q4, q1 = baseline
    q2_spec = _Spec(
        "0000123456-27-000006",
        "4",
        datetime(2027, 4, 4, 18, 0, tzinfo=timezone.utc),
        _fixture("form4_original.xml"),
    )
    q2 = _loaded_period(2027, 2, (q2_spec,), profile=profile)
    by_name = {
        "2026q4.json": q4,
        "2027q1.json": q1,
        "2027q2.json": q2,
    }
    loader_calls: list[str] = []

    def counted_loader(snapshot_path, **_kwargs):
        name = Path(snapshot_path).name
        loader_calls.append(name)
        return by_name[name]

    monkeypatch.setattr(
        evidence_module.acceptance_module,
        "load_sec_edgar_acceptance_snapshot",
        counted_loader,
    )
    monkeypatch.setattr(evidence_module, "MAX_FORM4_EVIDENCE_RECORDS", 1)
    monkeypatch.setattr(
        evidence_module,
        "parse_form4_xml",
        lambda *_args, **_kwargs: pytest.fail("XML parser was reached"),
    )
    with pytest.raises(Form4MultiPeriodEvidenceError, match="resource cap"):
        assemble_sec_form4_multi_period_evidence(
            (_period(2026, 4), _period(2027, 1), _period(2027, 2)),
            sources=(_xml_source(original), _xml_source(amendment)),
            evidence_profile=_evidence_profile(profile),
            parser_git_commit=PARSER_COMMIT,
        )
    assert loader_calls == ["2026q4.json", "2027q1.json"]


def test_identity_and_result_cannot_be_forged_into_authority(baseline):
    original, amendment, profile, _q4, _q1 = baseline
    result = _assemble(original, amendment, profile)

    with pytest.raises(Form4MultiPeriodEvidenceError, match="authority"):
        replace(result.identity, official_amendment_link_verified=True)
    with pytest.raises(Form4MultiPeriodEvidenceError, match="authority"):
        replace(result.identity, complete_amendment_coverage_verified=True)
    with pytest.raises(Form4MultiPeriodEvidenceError, match="authority"):
        replace(result.identity, canonical_filter_authorized=True)
    with pytest.raises(Form4MultiPeriodEvidenceError, match="factory-created"):
        ProfileBoundForm4AmendmentEvidence(
            identity=result.identity,
            xml_sources=result.xml_sources,
            supplied_link_evidence=result.supplied_link_evidence,
            as_filed_corpus=result.as_filed_corpus,
            lineages=result.lineages,
        )
    with pytest.raises(Form4MultiPeriodEvidenceError, match="factory-created"):
        replace(result.identity)
    with pytest.raises(Form4MultiPeriodEvidenceError, match="inventories"):
        replace(result.identity, period_inventory_hash="0" * 64)
    with pytest.raises(Form4MultiPeriodEvidenceError, match="inventories"):
        replace(result.identity, supplied_link_evidence_hash="0" * 64)
    tampered_evidence = (
        replace(
            result.identity.supplied_link_evidence[0],
            primary_document_sha256="0" * 64,
        ),
        *result.identity.supplied_link_evidence[1:],
    )
    tampered_evidence_hash = hash_payload(
        [item.to_payload() for item in tampered_evidence]
    )
    tampered_lineage_payload = result.identity.lineage_payload()
    tampered_lineage_payload["supplied_link_evidence_hash"] = (
        tampered_evidence_hash
    )
    start = result.identity.period_inventory[0]
    end = result.identity.period_inventory[-1]
    tampered_id = (
        f"form4-multi-period-evidence-{start.year:04d}q{start.quarter}-"
        f"{end.year:04d}q{end.quarter}-"
        f"{hash_payload(tampered_lineage_payload)[:16]}"
    )
    with pytest.raises(Form4MultiPeriodEvidenceError, match="XML source inventory"):
        replace(
            result.identity,
            supplied_link_evidence=tampered_evidence,
            supplied_link_evidence_hash=tampered_evidence_hash,
            evidence_id=tampered_id,
        )


def test_malformed_profile_document_hash_refuses(monkeypatch, baseline):
    original, amendment, profile, q4, _q1 = baseline
    bad = replace(amendment, primary_document_sha256="f" * 63)
    q1 = _loaded_period(2027, 1, (bad,), profile=profile)
    _install_loader(monkeypatch, (q4, q1))
    with pytest.raises(Form4MultiPeriodEvidenceError, match="document hash"):
        _assemble(original, amendment, profile)


def test_supplied_xml_issuer_must_agree_with_verified_acceptance_evidence(
    monkeypatch,
):
    """Bind the parsed XML issuer to the CIK the verified IB-1C URL anchors.

    Both supplied filings declare the same foreign issuer, so the corpus-level
    original-versus-amendment issuer comparison stays satisfied and only the
    XML-to-acceptance-evidence binding can refuse. Without it a caller could
    file one issuer's XML under another issuer's verified accession and corrupt
    the audit lineage that later QC evidence rests on.
    """
    foreign = b"<issuerCik>999999</issuerCik>"
    original = _Spec(
        ORIGINAL,
        "4",
        datetime(2026, 12, 29, 18, 0, tzinfo=timezone.utc),
        _fixture("form4_original.xml").replace(
            b"<issuerCik>123456</issuerCik>", foreign
        ),
    )
    amendment = _Spec(
        AMENDMENT,
        "4/A",
        datetime(2027, 1, 4, 18, 0, tzinfo=timezone.utc),
        _fixture("form4_amendment.xml").replace(
            b"<issuerCik>123456</issuerCik>", foreign
        ),
        ORIGINAL,
    )
    profile = _profile()
    _install_loader(
        monkeypatch,
        (
            _loaded_period(2026, 4, (original,), profile=profile),
            _loaded_period(2027, 1, (amendment,), profile=profile),
        ),
    )

    with pytest.raises(
        Form4MultiPeriodEvidenceError,
        match="XML issuer CIK disagrees with acceptance evidence",
    ):
        _assemble(original, amendment, profile)


def test_ib1e_module_has_no_network_outcome_execution_or_ui_imports():
    module_path = Path(evidence_module.__file__)
    tree = ast.parse(
        module_path.read_text(encoding="utf-8"), filename=str(module_path)
    )
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])
    forbidden = {
        "assistant",
        "backtest",
        "execution",
        "httpx",
        "outcomes",
        "quantconnect",
        "requests",
        "risk",
        "signals",
        "socket",
        "strategies",
        "streamlit",
        "urllib",
        "yfinance",
    }
    assert imported.isdisjoint(forbidden), imported & forbidden


def _disposition_report(baseline, *, reverse: bool = False):
    original, amendment, profile, _q4, _q1 = baseline
    evidence = _assemble(original, amendment, profile, reverse=reverse)
    return build_form4_provisional_disposition_report(
        evidence,
        builder_git_commit="f" * 40,
    )


def _custom_evidence(monkeypatch, original_xml: bytes):
    original = _Spec(
        ORIGINAL,
        "4",
        datetime(2026, 12, 29, 18, 0, tzinfo=timezone.utc),
        original_xml,
    )
    amendment = _Spec(
        AMENDMENT,
        "4/A",
        datetime(2027, 1, 4, 18, 0, tzinfo=timezone.utc),
        _fixture("form4_amendment.xml"),
        ORIGINAL,
    )
    profile = _profile()
    _install_loader(
        monkeypatch,
        (
            _loaded_period(2026, 4, (original,), profile=profile),
            _loaded_period(2027, 1, (amendment,), profile=profile),
        ),
    )
    return _assemble(original, amendment, profile)


def test_provisional_report_is_deterministic_and_accounts_for_every_row(
    baseline,
):
    forward = _disposition_report(baseline)
    reverse = _disposition_report(baseline, reverse=True)

    assert forward == reverse
    assert forward.identity.report_id.startswith(
        "form4-provisional-disposition-report-"
    )
    assert forward.identity.transaction_count == len(forward.rows) == 2
    assert forward.identity.candidate_count == 1
    assert forward.identity.quarantine_count == 1
    assert forward.identity.authorized_outcome_looks == 0
    assert forward.official_profile_compatibility_verified is False
    assert forward.official_amendment_link_verified is False
    assert forward.complete_amendment_coverage_verified is False
    assert forward.point_in_time_security_identity_verified is False
    assert forward.canonical_filter_authorized is False
    assert forward.lot_aggregation_authorized is False
    assert forward.outcomes_authorized is False
    assert forward.identity.official_profile_compatibility_verified is False
    assert forward.identity.official_amendment_link_verified is False
    assert forward.identity.complete_amendment_coverage_verified is False
    assert forward.identity.point_in_time_security_identity_verified is False
    assert forward.identity.canonical_filter_authorized is False
    assert forward.identity.lot_aggregation_authorized is False
    assert forward.identity.outcomes_authorized is False

    rows_by_accession = {row.accession_number: row for row in forward.rows}
    original = rows_by_accession[ORIGINAL]
    amendment = rows_by_accession[AMENDMENT]
    assert original.disposition is (
        Form4ProvisionalDisposition.PROVISIONAL_PRE_AGGREGATION_CANDIDATE
    )
    assert original.outcomes == (
        ClassificationOutcome.ELIGIBLE_FOR_LOT_AGGREGATION,
    )
    assert amendment.disposition is (
        Form4ProvisionalDisposition.PROVISIONAL_QUARANTINE
    )
    assert amendment.outcomes == (
        ClassificationOutcome.EXCLUDE_AMENDED_FILING,
    )
    assert forward.to_payload() == reverse.to_payload()
    assert canonical_json(forward.to_payload()) == canonical_json(
        reverse.to_payload()
    )

    original_spec, amendment_spec, profile, _q4, _q1 = baseline
    evidence = _assemble(original_spec, amendment_spec, profile)
    transactions = {
        (transaction.accession_number, transaction.row_index): transaction
        for filing in evidence.as_filed_corpus.filings
        for transaction in filing.transactions
    }
    assert set(transactions) == {
        (row.accession_number, row.row_index) for row in forward.rows
    }
    for row in forward.rows:
        transaction = transactions[(row.accession_number, row.row_index)]
        assert row.outcomes == transaction.outcomes
        assert row.diagnostics == transaction.diagnostics
        assert row.transaction_payload_hash == hash_payload(
            disposition_module._transaction_payload(transaction)
        )
        assert {
            field.name for field in fields(ParsedTransaction)
        } == set(disposition_module._transaction_payload(transaction))


def test_provisional_report_reparses_instead_of_trusting_retained_rows(
    baseline,
):
    original, amendment, profile, _q4, _q1 = baseline
    evidence = _assemble(original, amendment, profile)
    filing = evidence.as_filed_corpus.filing(ORIGINAL)
    transaction = filing.transactions[0]
    forged_transaction = replace(
        transaction,
        price_per_share=Decimal("1"),
        purchase_value_usd=Decimal("5000"),
    )
    forged_filing = replace(
        filing,
        transactions=(forged_transaction, *filing.transactions[1:]),
    )
    forged_corpus = build_filing_corpus(
        [
            forged_filing
            if item.envelope.accession_number == ORIGINAL
            else item
            for item in evidence.as_filed_corpus.filings
        ]
    )
    forged_identity = copy.copy(evidence.identity)
    object.__setattr__(
        forged_identity,
        "parsed_corpus_hash",
        disposition_module._parsed_corpus_hash(forged_corpus),
    )
    start = forged_identity.period_inventory[0]
    end = forged_identity.period_inventory[-1]
    object.__setattr__(
        forged_identity,
        "evidence_id",
        (
            f"form4-multi-period-evidence-{start.year:04d}q{start.quarter}-"
            f"{end.year:04d}q{end.quarter}-"
            f"{hash_payload(forged_identity.lineage_payload())[:16]}"
        ),
    )
    forged_evidence = copy.copy(evidence)
    object.__setattr__(forged_evidence, "identity", forged_identity)
    object.__setattr__(forged_evidence, "as_filed_corpus", forged_corpus)

    with pytest.raises(
        Form4ProvisionalDispositionReportError,
        match="reparsed corpus",
    ):
        build_form4_provisional_disposition_report(
            forged_evidence,
            builder_git_commit="f" * 40,
        )


@pytest.mark.parametrize(
    "field_name,replacement",
    [
        ("period_inventory_hash", "0" * 64),
        ("evidence_profile_hash", "0" * 64),
        ("amendment_count", 0),
    ],
)
def test_provisional_report_revalidates_the_complete_upstream_identity(
    baseline,
    field_name,
    replacement,
):
    original, amendment, profile, _q4, _q1 = baseline
    evidence = _assemble(original, amendment, profile)
    forged_identity = copy.copy(evidence.identity)
    object.__setattr__(forged_identity, field_name, replacement)
    start = forged_identity.period_inventory[0]
    end = forged_identity.period_inventory[-1]
    object.__setattr__(
        forged_identity,
        "evidence_id",
        (
            f"form4-multi-period-evidence-{start.year:04d}q{start.quarter}-"
            f"{end.year:04d}q{end.quarter}-"
            f"{hash_payload(forged_identity.lineage_payload())[:16]}"
        ),
    )
    forged_evidence = copy.copy(evidence)
    object.__setattr__(forged_evidence, "identity", forged_identity)

    with pytest.raises(
        Form4ProvisionalDispositionReportError,
        match="upstream evidence revalidation",
    ):
        build_form4_provisional_disposition_report(
            forged_evidence,
            builder_git_commit="f" * 40,
        )


def test_provisional_report_revalidates_nested_period_identity(baseline):
    original, amendment, profile, _q4, _q1 = baseline
    evidence = _assemble(original, amendment, profile)
    forged_period = copy.copy(evidence.identity.period_inventory[0])
    object.__setattr__(forged_period, "record_count", -1)
    forged_periods = (forged_period, *evidence.identity.period_inventory[1:])
    forged_identity = copy.copy(evidence.identity)
    object.__setattr__(forged_identity, "period_inventory", forged_periods)
    object.__setattr__(
        forged_identity,
        "period_inventory_hash",
        hash_payload([item.to_payload() for item in forged_periods]),
    )
    start = forged_periods[0]
    end = forged_periods[-1]
    object.__setattr__(
        forged_identity,
        "evidence_id",
        (
            f"form4-multi-period-evidence-{start.year:04d}q{start.quarter}-"
            f"{end.year:04d}q{end.quarter}-"
            f"{hash_payload(forged_identity.lineage_payload())[:16]}"
        ),
    )
    forged_evidence = copy.copy(evidence)
    object.__setattr__(forged_evidence, "identity", forged_identity)

    with pytest.raises(
        Form4ProvisionalDispositionReportError,
        match="upstream evidence revalidation",
    ):
        build_form4_provisional_disposition_report(
            forged_evidence,
            builder_git_commit="f" * 40,
        )


def test_provisional_report_revalidates_nested_link_evidence(baseline):
    original, amendment, profile, _q4, _q1 = baseline
    evidence = _assemble(original, amendment, profile)
    forged_link = copy.copy(evidence.supplied_link_evidence[0])
    object.__setattr__(forged_link, "metadata_source_sha256", "bad")
    forged_links = (forged_link, *evidence.supplied_link_evidence[1:])
    forged_identity = copy.copy(evidence.identity)
    object.__setattr__(forged_identity, "supplied_link_evidence", forged_links)
    object.__setattr__(
        forged_identity,
        "supplied_link_evidence_hash",
        hash_payload([item.to_payload() for item in forged_links]),
    )
    start = forged_identity.period_inventory[0]
    end = forged_identity.period_inventory[-1]
    object.__setattr__(
        forged_identity,
        "evidence_id",
        (
            f"form4-multi-period-evidence-{start.year:04d}q{start.quarter}-"
            f"{end.year:04d}q{end.quarter}-"
            f"{hash_payload(forged_identity.lineage_payload())[:16]}"
        ),
    )
    forged_evidence = copy.copy(evidence)
    object.__setattr__(forged_evidence, "identity", forged_identity)
    object.__setattr__(forged_evidence, "supplied_link_evidence", forged_links)

    with pytest.raises(
        Form4ProvisionalDispositionReportError,
        match="upstream evidence revalidation",
    ):
        build_form4_provisional_disposition_report(
            forged_evidence,
            builder_git_commit="f" * 40,
        )


def test_provisional_report_rebuilds_cached_xml_source_identity(baseline):
    original, amendment, profile, _q4, _q1 = baseline
    evidence = _assemble(original, amendment, profile)
    forged_source = copy.copy(evidence.xml_sources[0])
    object.__setattr__(
        forged_source,
        "xml_bytes",
        forged_source.xml_bytes.replace(b"5000", b"5001", 1),
    )
    forged_evidence = copy.copy(evidence)
    object.__setattr__(
        forged_evidence,
        "xml_sources",
        (forged_source, *evidence.xml_sources[1:]),
    )

    with pytest.raises(
        Form4ProvisionalDispositionReportError,
        match="source inventory",
    ):
        build_form4_provisional_disposition_report(
            forged_evidence,
            builder_git_commit="f" * 40,
        )


def test_provisional_report_checks_identity_type_before_invoking_validation(
    baseline,
):
    original, amendment, profile, _q4, _q1 = baseline
    evidence = _assemble(original, amendment, profile)
    called = False

    class ForeignIdentity:
        def __post_init__(self, _token):
            nonlocal called
            called = True

    forged_evidence = copy.copy(evidence)
    object.__setattr__(forged_evidence, "identity", ForeignIdentity())

    with pytest.raises(
        Form4ProvisionalDispositionReportError,
        match="identity type",
    ):
        build_form4_provisional_disposition_report(
            forged_evidence,
            builder_git_commit="f" * 40,
        )
    assert called is False


def test_provisional_report_checks_source_cap_before_rebuilding(
    monkeypatch,
    baseline,
):
    original, amendment, profile, _q4, _q1 = baseline
    evidence = _assemble(original, amendment, profile)
    forged_evidence = copy.copy(evidence)
    object.__setattr__(
        forged_evidence,
        "xml_sources",
        (evidence.xml_sources[0],) * 257,
    )
    monkeypatch.setattr(
        disposition_module.ProfileBoundForm4AmendmentEvidence,
        "__post_init__",
        lambda *_args, **_kwargs: pytest.fail(
            "upstream result rebuilding was reached"
        ),
    )

    with pytest.raises(
        Form4ProvisionalDispositionReportError,
        match="resource bound",
    ):
        build_form4_provisional_disposition_report(
            forged_evidence,
            builder_git_commit="f" * 40,
        )


def test_provisional_report_preserves_multiple_quarantine_reasons(monkeypatch):
    xml_bytes = _fixture("form4_original.xml").replace(
        b"<value>Common Stock</value>",
        b"<value>Ordinary Shares</value>",
        1,
    ).replace(
        b"<transactionCode>P</transactionCode>",
        b"<transactionCode>S</transactionCode>",
        1,
    )
    report = build_form4_provisional_disposition_report(
        _custom_evidence(monkeypatch, xml_bytes),
        builder_git_commit="f" * 40,
    )
    row = next(item for item in report.rows if item.accession_number == ORIGINAL)

    assert row.disposition is (
        Form4ProvisionalDisposition.PROVISIONAL_QUARANTINE
    )
    assert row.outcomes == (
        ClassificationOutcome.EXCLUDE_NON_COMMON_STOCK,
        ClassificationOutcome.EXCLUDE_SALE,
    )
    assert report.identity.transaction_count == len(report.rows) == 2


@pytest.mark.parametrize("title", ["Ordinary Shares", "Common Shares"])
def test_provisional_report_keeps_synthetic_share_variants_quarantined(
    monkeypatch,
    title,
):
    xml_bytes = _fixture("form4_original.xml").replace(
        b"<value>Common Stock</value>",
        f"<value>{title}</value>".encode(),
        1,
    )
    report = build_form4_provisional_disposition_report(
        _custom_evidence(monkeypatch, xml_bytes),
        builder_git_commit="f" * 40,
    )
    row = next(item for item in report.rows if item.accession_number == ORIGINAL)

    assert row.disposition is (
        Form4ProvisionalDisposition.PROVISIONAL_QUARANTINE
    )
    assert row.outcomes == (
        ClassificationOutcome.EXCLUDE_NON_COMMON_STOCK,
    )


def test_provisional_report_does_not_aggregate_subminimum_same_lot_rows(
    monkeypatch,
):
    xml_bytes = _fixture("form4_original.xml").replace(
        b"<transactionShares><value>5000</value></transactionShares>",
        b"<transactionShares><value>1000</value></transactionShares>",
        1,
    )
    start = xml_bytes.index(b"    <nonDerivativeTransaction>")
    end = xml_bytes.index(b"    </nonDerivativeTransaction>") + len(
        b"    </nonDerivativeTransaction>"
    )
    row_bytes = xml_bytes[start:end]
    xml_bytes = xml_bytes.replace(
        b"  </nonDerivativeTable>",
        row_bytes + b"\n  </nonDerivativeTable>",
        1,
    )
    report = build_form4_provisional_disposition_report(
        _custom_evidence(monkeypatch, xml_bytes),
        builder_git_commit="f" * 40,
    )
    original_rows = tuple(
        row for row in report.rows if row.accession_number == ORIGINAL
    )

    assert len(original_rows) == 2
    assert {row.row_index for row in original_rows} == {0, 1}
    assert len({row.row_id for row in original_rows}) == 2
    assert all(row.purchase_value_usd == Decimal("12500.00") for row in original_rows)
    assert all(
        row.disposition
        is Form4ProvisionalDisposition.PROVISIONAL_PRE_AGGREGATION_CANDIDATE
        for row in original_rows
    )
    assert report.identity.candidate_count == 2
    assert not hasattr(report, "aggregated_lots")


def test_provisional_report_identity_and_result_fail_closed_on_tampering(
    baseline,
):
    report = _disposition_report(baseline)

    with pytest.raises(
        Form4ProvisionalDispositionReportError,
        match="factory-created",
    ):
        replace(report.identity)
    with pytest.raises(
        Form4ProvisionalDispositionReportError,
        match="factory-created",
    ):
        replace(report)
    tampered_lineage = report.identity.lineage_payload()
    tampered_lineage["row_inventory_hash"] = "0" * 64
    tampered_identity = replace(
        report.identity,
        row_inventory_hash="0" * 64,
        report_id=(
            "form4-provisional-disposition-report-"
            f"{hash_payload(tampered_lineage)[:16]}"
        ),
        _verified_factory_token=(
            disposition_module._VERIFIED_IDENTITY_FACTORY_TOKEN
        ),
    )
    with pytest.raises(
        Form4ProvisionalDispositionReportError,
        match="inventory",
    ):
        replace(
            report,
            identity=tampered_identity,
            _verified_factory_token=(
                disposition_module._VERIFIED_REPORT_FACTORY_TOKEN
            ),
        )
    with pytest.raises(
        Form4ProvisionalDispositionReportError,
        match="row",
    ):
        replace(report.rows[0], row_id="0" * 64)
    with pytest.raises(
        Form4ProvisionalDispositionReportError,
        match="count",
    ):
        replace(
            report,
            rows=report.rows[:-1],
            _verified_factory_token=(
                disposition_module._VERIFIED_REPORT_FACTORY_TOKEN
            ),
        )


@pytest.mark.parametrize(
    "field_name,replacement",
    [
        ("official_profile_compatibility_verified", True),
        ("official_amendment_link_verified", True),
        ("complete_amendment_coverage_verified", True),
        ("point_in_time_security_identity_verified", True),
        ("canonical_filter_authorized", True),
        ("lot_aggregation_authorized", True),
        ("outcomes_authorized", True),
        ("authorized_outcome_looks", 1),
    ],
)
def test_provisional_report_identity_refuses_every_authority_claim(
    baseline,
    field_name,
    replacement,
):
    report = _disposition_report(baseline)

    with pytest.raises(
        Form4ProvisionalDispositionReportError,
        match="authority",
    ):
        replace(
            report.identity,
            **{field_name: replacement},
            _verified_factory_token=(
                disposition_module._VERIFIED_IDENTITY_FACTORY_TOKEN
            ),
        )


def test_ib1g_module_has_no_network_outcome_execution_or_ui_imports():
    module_path = Path(disposition_module.__file__)
    tree = ast.parse(
        module_path.read_text(encoding="utf-8"), filename=str(module_path)
    )
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])
    forbidden = {
        "assistant",
        "backtest",
        "execution",
        "httpx",
        "outcomes",
        "quantconnect",
        "requests",
        "risk",
        "signals",
        "socket",
        "strategies",
        "streamlit",
        "urllib",
        "yfinance",
    }
    assert imported.isdisjoint(forbidden), imported & forbidden
