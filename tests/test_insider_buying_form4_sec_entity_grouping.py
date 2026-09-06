"""IB-2B SEC-entity grouping tests (synthetic, offline, zero authority).

The fixtures exercise deterministic SEC-CIK grouping and owner-attribution
quarantine only.  They confer no market-security resolution, outcome access,
QuantConnect, execution, deployment, or trading authority.
"""
from __future__ import annotations

import ast
import io
import tokenize
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying import (
    FORM4_SEC_ENTITY_GROUPING_VERSION,
    Form4OwnerAttributionOutcome,
    Form4SecEntityGroupingError,
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
    build_form4_observed_identity_inventory,
    build_form4_sec_entity_grouping,
)
from research.insider_buying import (
    form4_multi_period_amendment_evidence as evidence_module,
)
from research.insider_buying import form4_sec_entity_grouping as grouping_module
from research.insider_buying.sec_edgar_acceptance_snapshot import (
    LoadedSecEdgarAcceptanceSnapshot,
)


PARSER_COMMIT = "e" * 40
INVENTORY_COMMIT = "f" * 40
GROUPING_COMMIT = "a" * 40
CAPTURE_COMMIT = "c" * 40
ISSUER_CIK = "0000123456"
OTHER_ISSUER_CIK = "0000654321"
OWNER_CIK = "0000987654"
OTHER_OWNER_CIK = "0000111222"
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
class _Owner:
    cik: str = OWNER_CIK
    name: str = "Fixture Officer"
    is_director: bool | None = False
    is_officer: bool | None = True
    is_ten_percent_owner: bool | None = False
    is_other: bool | None = False
    title: str | None = "Chief Financial Officer"


@dataclass(frozen=True)
class _Spec:
    accession: str
    form: str
    accepted_at: datetime
    xml_bytes: bytes
    issuer_cik: str = ISSUER_CIK
    amends_accession: str | None = None

    @property
    def period(self) -> tuple[int, int]:
        month = self.accepted_at.month
        return self.accepted_at.year, ((month - 1) // 3) + 1


def _relationship(owner: _Owner) -> str:
    tags = (
        ("isDirector", owner.is_director),
        ("isOfficer", owner.is_officer),
        ("isTenPercentOwner", owner.is_ten_percent_owner),
        ("isOther", owner.is_other),
    )
    rendered = "".join(
        f"<{name}>{int(value)}</{name}>"
        for name, value in tags
        if value is not None
    )
    if owner.title is not None:
        rendered += f"<officerTitle>{owner.title}</officerTitle>"
    return rendered


def _xml(
    *,
    form: str = "4",
    issuer_cik: str = ISSUER_CIK,
    issuer_name: str = "Fixture Manufacturing, Inc.",
    symbol: str = "FIXT",
    owners: tuple[_Owner, ...] = (_Owner(),),
    shares: str = "5000",
    include_transaction: bool = True,
) -> bytes:
    owner_xml = "".join(
        "<reportingOwner>"
        "<reportingOwnerId>"
        f"<rptOwnerCik>{owner.cik}</rptOwnerCik>"
        f"<rptOwnerName>{owner.name}</rptOwnerName>"
        "</reportingOwnerId>"
        "<reportingOwnerRelationship>"
        f"{_relationship(owner)}"
        "</reportingOwnerRelationship>"
        "</reportingOwner>"
        for owner in owners
    )
    transaction_xml = (
        "<nonDerivativeTable><nonDerivativeTransaction>"
        "<securityTitle><value>Common Stock</value></securityTitle>"
        "<transactionDate><value>2026-08-18</value></transactionDate>"
        "<transactionCoding><transactionCode>P</transactionCode>"
        "</transactionCoding><transactionAmounts>"
        f"<transactionShares><value>{shares}</value></transactionShares>"
        "<transactionPricePerShare><value>12.50</value>"
        "</transactionPricePerShare>"
        "<transactionAcquiredDisposedCode><value>A</value>"
        "</transactionAcquiredDisposedCode></transactionAmounts>"
        "<postTransactionAmounts><sharesOwnedFollowingTransaction>"
        "<value>15000</value></sharesOwnedFollowingTransaction>"
        "</postTransactionAmounts><ownershipNature>"
        "<directOrIndirectOwnership><value>D</value>"
        "</directOrIndirectOwnership></ownershipNature>"
        "</nonDerivativeTransaction></nonDerivativeTable>"
        if include_transaction
        else ""
    )
    return (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<ownershipDocument>"
        f"<documentType>{form}</documentType>"
        "<periodOfReport>2026-08-20</periodOfReport>"
        "<issuer>"
        f"<issuerCik>{issuer_cik}</issuerCik>"
        f"<issuerName>{issuer_name}</issuerName>"
        f"<issuerTradingSymbol>{symbol}</issuerTradingSymbol>"
        "</issuer>"
        f"{owner_xml}"
        f"{transaction_xml}"
        "</ownershipDocument>"
    ).encode("utf-8")


def _spec(
    sequence: int,
    *,
    year: int = 2026,
    month: int = 12,
    day: int | None = None,
    form: str = "4",
    issuer_cik: str = ISSUER_CIK,
    issuer_name: str = "Fixture Manufacturing, Inc.",
    symbol: str = "FIXT",
    owners: tuple[_Owner, ...] = (_Owner(),),
    amends_accession: str | None = None,
    include_transaction: bool = True,
) -> _Spec:
    accepted = datetime(
        year,
        month,
        day or min(20 + sequence, 28),
        18,
        0,
        tzinfo=timezone.utc,
    )
    return _Spec(
        accession=f"0000123456-{year % 100:02d}-{sequence:06d}",
        form=form,
        accepted_at=accepted,
        xml_bytes=_xml(
            form=form,
            issuer_cik=issuer_cik,
            issuer_name=issuer_name,
            symbol=symbol,
            owners=owners,
            shares=str(5000 + sequence),
            include_transaction=include_transaction,
        ),
        issuer_cik=issuer_cik,
        amends_accession=amends_accession,
    )


def _profile() -> SecEdgarMetadataSchemaProfile:
    return SecEdgarMetadataSchemaProfile(
        profile_id="synthetic-non-official-ib2b-metadata-v1",
        exact_fields=EXACT_FIELDS,
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
        f"{int(spec.issuer_cik)}/{spec.accession.replace('-', '')}/primary.xml"
    )


def _loaded_period(
    year: int,
    quarter: int,
    specs: tuple[_Spec, ...],
    profile: SecEdgarMetadataSchemaProfile,
) -> LoadedSecEdgarAcceptanceSnapshot:
    records = []
    sources = []
    source_identities = []
    for spec in sorted(specs, key=lambda item: item.accession):
        primary_url = _primary_url(spec)
        payload = {
            "accession": spec.accession,
            "form": spec.form,
            "filed": spec.accepted_at.date().isoformat(),
            "accepted": spec.accepted_at.isoformat(timespec="seconds"),
            "primary_url": primary_url,
            "amends_accession": spec.amends_accession or "",
            "primary_document_sha256": hash_bytes(spec.xml_bytes),
        }
        source = SecEdgarMetadataSource(
            metadata_bytes=(canonical_json(payload) + "\n").encode("utf-8"),
            source_url=(
                "https://www.sec.gov/Archives/edgar/data/"
                f"{int(spec.issuer_cik)}/"
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
            availability_tier=(
                SecEdgarAvailabilityTier.EXACT_ACCEPTANCE_TIMESTAMP
            ),
            next_open_rule=SecEdgarAvailabilityRule.NEXT_OPEN_AFTER_ACCEPTANCE,
            accepted_at=spec.accepted_at,
            primary_document_url=primary_url,
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
    content_key = [
        [item.accession, hash_bytes(item.xml_bytes)] for item in specs
    ]
    parsed_hash = hash_payload({"parsed": [year, quarter, content_key]})
    raw_hash = hash_payload({"raw": [year, quarter, content_key]})
    archive_hash = hash_payload({"archive": [year, quarter, content_key]})
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


def _evidence_profile(
    profile: SecEdgarMetadataSchemaProfile,
) -> SecForm4AmendmentEvidenceProfile:
    return SecForm4AmendmentEvidenceProfile(
        profile_id="synthetic-non-official-ib2b-link-v1",
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


def _inventory_for_specs(monkeypatch, specs: tuple[_Spec, ...], *, reverse=False):
    profile = _profile()
    grouped: dict[tuple[int, int], list[_Spec]] = {}
    for spec in specs:
        grouped.setdefault(spec.period, []).append(spec)
    if len(grouped) == 1:
        year, quarter = next(iter(grouped))
        adjacent = (year + 1, 1) if quarter == 4 else (year, quarter + 1)
        grouped[adjacent] = []
    loaded = {
        f"{year}q{quarter}.json": _loaded_period(
            year, quarter, tuple(items), profile
        )
        for (year, quarter), items in grouped.items()
    }

    def loader(snapshot_path, **_kwargs):
        return loaded[Path(snapshot_path).name]

    monkeypatch.setattr(
        evidence_module.acceptance_module,
        "load_sec_edgar_acceptance_snapshot",
        loader,
    )
    periods = tuple(_period(*period) for period in sorted(grouped))
    sources = tuple(
        SecForm4XmlSource(
            accession_number=spec.accession,
            xml_bytes=spec.xml_bytes,
            primary_document_url=_primary_url(spec),
            retrieved_at=spec.accepted_at + timedelta(days=2),
            capture_git_commit=CAPTURE_COMMIT,
            amends_accession=spec.amends_accession,
        )
        for spec in specs
    )
    if reverse:
        periods = tuple(reversed(periods))
        sources = tuple(reversed(sources))
    evidence = assemble_sec_form4_multi_period_evidence(
        periods,
        sources=sources,
        evidence_profile=_evidence_profile(profile),
        parser_git_commit=PARSER_COMMIT,
    )
    return build_form4_observed_identity_inventory(
        evidence,
        builder_git_commit=INVENTORY_COMMIT,
    )


def _group(monkeypatch, specs: tuple[_Spec, ...], *, reverse=False):
    inventory = _inventory_for_specs(monkeypatch, specs, reverse=reverse)
    grouping = build_form4_sec_entity_grouping(
        inventory,
        builder_git_commit=GROUPING_COMMIT,
    )
    return inventory, grouping


def _pair(*, alias=False) -> tuple[_Spec, _Spec]:
    original = _spec(1)
    amendment = _spec(
        2,
        year=2027,
        month=1,
        day=4,
        form="4/A",
        issuer_name=("Fixture Manufacturing Holdings" if alias else "Fixture Manufacturing, Inc."),
        symbol=("FIXH" if alias else "FIXT"),
        owners=(
            _Owner(
                name=("Fixture Executive" if alias else "Fixture Officer"),
                title=("Treasurer" if alias else "Chief Financial Officer"),
            ),
        ),
        amends_accession=original.accession,
    )
    return original, amendment


def _forge(value, **updates):
    forged = object.__new__(type(value))
    for name, item in vars(value).items():
        object.__setattr__(forged, name, item)
    for name, item in updates.items():
        object.__setattr__(forged, name, item)
    return forged


def _rehash_issuer_observation(observation, **updates):
    changed = _forge(observation, **updates)
    return _forge(
        changed,
        issuer_observation_id=hash_payload(
            grouping_module._issuer_observation_payload(changed)
        ),
    )


def _rehash_issuer_candidate(candidate, observations):
    changed = _forge(
        candidate,
        observations=observations,
        observation_inventory_hash=hash_payload(
            [item.to_payload() for item in observations]
        ),
    )
    return _forge(
        changed,
        issuer_candidate_id=hash_payload(
            grouping_module._issuer_candidate_payload(changed)
        ),
    )


def _rehash_owner_observation(observation, **updates):
    changed = _forge(observation, **updates)
    return _forge(
        changed,
        owner_observation_id=hash_payload(
            grouping_module._owner_observation_payload(changed)
        ),
    )


def _rehash_owner_candidate(candidate, observations):
    changed = _forge(
        candidate,
        observations=observations,
        observation_inventory_hash=hash_payload(
            [item.to_payload() for item in observations]
        ),
    )
    return _forge(
        changed,
        owner_candidate_id=hash_payload(
            grouping_module._owner_candidate_payload(changed)
        ),
    )


def _rehash_transaction_attribution(row, **updates):
    changed = _forge(row, **updates)
    return _forge(
        changed,
        transaction_attribution_id=hash_payload(
            grouping_module._transaction_attribution_payload(changed)
        ),
    )


def _rehash_grouping(
    grouping,
    *,
    issuer_candidates=None,
    reporting_owner_candidates=None,
    transaction_attributions=None,
):
    issuers = (
        grouping.issuer_candidates
        if issuer_candidates is None
        else issuer_candidates
    )
    owners = (
        grouping.reporting_owner_candidates
        if reporting_owner_candidates is None
        else reporting_owner_candidates
    )
    transactions = (
        grouping.transaction_attributions
        if transaction_attributions is None
        else transaction_attributions
    )
    identity = _forge(
        grouping.identity,
        issuer_candidate_inventory_hash=hash_payload(
            [item.to_payload() for item in issuers]
        ),
        reporting_owner_candidate_inventory_hash=hash_payload(
            [item.to_payload() for item in owners]
        ),
        transaction_attribution_inventory_hash=hash_payload(
            [item.to_payload() for item in transactions]
        ),
    )
    identity = _forge(
        identity,
        grouping_id=(
            "form4-sec-entity-grouping-"
            f"{hash_payload(grouping_module._grouping_identity_payload(identity))[:16]}"
        ),
    )
    return _forge(
        grouping,
        identity=identity,
        issuer_candidates=issuers,
        reporting_owner_candidates=owners,
        transaction_attributions=transactions,
    )


def _validate_forged_grouping(grouping) -> None:
    grouping_module.Form4SecEntityGrouping.__post_init__(
        grouping,
        grouping_module._GROUPING_FACTORY_TOKEN,
    )


def test_same_cik_groups_aliases_and_keeps_amendment_observations_distinct(
    monkeypatch,
):
    inventory, grouping = _group(monkeypatch, _pair(alias=True))

    assert grouping.identity.contract_version == FORM4_SEC_ENTITY_GROUPING_VERSION
    assert len(grouping.issuer_candidates) == 1
    issuer = grouping.issuer_candidates[0]
    assert issuer.issuer_cik == ISSUER_CIK
    assert {item.issuer_name for item in issuer.observations} == {
        "Fixture Manufacturing, Inc.",
        "Fixture Manufacturing Holdings",
    }
    assert {item.issuer_symbol_raw for item in issuer.observations} == {
        "FIXT",
        "FIXH",
    }
    assert len({item.issuer_observation_id for item in issuer.observations}) == 2
    amendment = next(
        item for item in issuer.observations if item.document_type == "4/A"
    )
    assert amendment.amends_accession == inventory.filings[0].accession_number
    assert amendment.original_accession == inventory.filings[0].accession_number
    assert {item.filing_observation_id for item in issuer.observations} == {
        item.filing_observation_id for item in inventory.filings
    }
    assert len(grouping.transaction_attributions) == 2
    assert {
        item.accession_number for item in grouping.transaction_attributions
    } == {item.accession_number for item in inventory.transactions}
    assert len(
        {
            item.transaction_attribution_id
            for item in grouping.transaction_attributions
        }
    ) == 2


def test_different_issuer_ciks_never_group_by_matching_name_or_symbol(monkeypatch):
    specs = (
        _spec(1),
        _spec(
            3,
            issuer_cik=OTHER_ISSUER_CIK,
            issuer_name="Fixture Manufacturing, Inc.",
            symbol="FIXT",
        ),
    )
    _inventory, grouping = _group(monkeypatch, specs)

    assert len(grouping.issuer_candidates) == 2
    assert {item.issuer_cik for item in grouping.issuer_candidates} == {
        ISSUER_CIK,
        OTHER_ISSUER_CIK,
    }
    assert all(len(item.observations) == 1 for item in grouping.issuer_candidates)


def test_reporting_owners_group_only_by_cik_not_name_or_title(monkeypatch):
    specs = (
        _spec(1),
        _spec(
            3,
            owners=(_Owner(name="Officer Alias", title="Treasurer"),),
        ),
        _spec(
            4,
            owners=(
                _Owner(
                    cik=OTHER_OWNER_CIK,
                    name="Fixture Officer",
                    title="Chief Financial Officer",
                ),
            ),
        ),
    )
    _inventory, grouping = _group(monkeypatch, specs)

    by_cik = {item.owner_cik: item for item in grouping.reporting_owner_candidates}
    assert set(by_cik) == {OWNER_CIK, OTHER_OWNER_CIK}
    assert {item.owner_name for item in by_cik[OWNER_CIK].observations} == {
        "Fixture Officer",
        "Officer Alias",
    }
    assert len(by_cik[OWNER_CIK].observations) == 2
    assert len(by_cik[OTHER_OWNER_CIK].observations) == 1


def test_alias_histories_use_acceptance_then_accession_source_order(monkeypatch):
    earlier_high_accession = _spec(9, day=21)
    later_low_accession = _spec(1, day=28)
    _inventory, grouping = _group(
        monkeypatch,
        (later_low_accession, earlier_high_accession),
    )

    issuer_observations = grouping.issuer_candidates[0].observations
    owner_observations = grouping.reporting_owner_candidates[0].observations
    expected_accessions = (
        earlier_high_accession.accession,
        later_low_accession.accession,
    )
    assert tuple(item.accession_number for item in issuer_observations) == (
        expected_accessions
    )
    assert tuple(item.accession_number for item in owner_observations) == (
        expected_accessions
    )
    assert tuple(item.accepted_at_utc for item in issuer_observations) == tuple(
        sorted(item.accepted_at_utc for item in issuer_observations)
    )
    assert tuple(item.accepted_at_utc for item in owner_observations) == tuple(
        sorted(item.accepted_at_utc for item in owner_observations)
    )


def test_single_complete_owner_is_attributed_to_the_exact_cik_candidate(monkeypatch):
    inventory, grouping = _group(monkeypatch, (_spec(1),))

    assert len(grouping.transaction_attributions) == len(inventory.transactions) == 1
    row = grouping.transaction_attributions[0]
    owner = grouping.reporting_owner_candidates[0]
    assert row.attributed_owner_cik == OWNER_CIK
    assert row.attributed_owner_candidate_id == owner.owner_candidate_id
    assert row.owner_attribution_outcomes == (
        Form4OwnerAttributionOutcome.SINGLE_COMPLETE_OWNER_CIK_ATTRIBUTED,
    )


@pytest.mark.parametrize(
    ("owners", "expected"),
    (
        (
            (),
            (Form4OwnerAttributionOutcome.MISSING_OWNER_SET_QUARANTINED,),
        ),
        (
            (_Owner(), _Owner(cik=OTHER_OWNER_CIK, name="Other Officer")),
            (Form4OwnerAttributionOutcome.MULTIPLE_OWNER_SET_QUARANTINED,),
        ),
        (
            (_Owner(), _Owner()),
            (
                Form4OwnerAttributionOutcome.MULTIPLE_OWNER_SET_QUARANTINED,
                Form4OwnerAttributionOutcome.DUPLICATE_OWNER_CIK_QUARANTINED,
            ),
        ),
        (
            (_Owner(is_other=None),),
            (
                Form4OwnerAttributionOutcome.INCOMPLETE_OWNER_RELATIONSHIP_QUARANTINED,
            ),
        ),
    ),
    ids=("missing", "multiple", "duplicate-cik", "incomplete"),
)
def test_ambiguous_owner_sets_have_named_quarantine_without_attribution(
    monkeypatch,
    owners,
    expected,
):
    inventory, grouping = _group(monkeypatch, (_spec(1, owners=owners),))

    assert len(grouping.transaction_attributions) == len(inventory.transactions) == 1
    row = grouping.transaction_attributions[0]
    assert row.owner_attribution_outcomes == expected
    assert row.attributed_owner_cik is None
    assert row.attributed_owner_candidate_id is None


@pytest.mark.parametrize(
    "owners",
    (
        (_Owner(), _Owner(cik=OTHER_OWNER_CIK, name="Joint Officer")),
        (_Owner(), _Owner()),
    ),
    ids=("distinct-ciks", "duplicate-cik"),
)
def test_joint_owner_observations_never_fan_out_transactions(monkeypatch, owners):
    inventory, grouping = _group(monkeypatch, (_spec(1, owners=owners),))

    assert len(inventory.reporting_owners) == 2
    assert len(inventory.transactions) == 1
    assert len(grouping.transaction_attributions) == 1
    assert grouping.transaction_attributions[0].attributed_owner_cik is None


def test_grouping_exhaustively_accounts_for_each_upstream_observation_once(
    monkeypatch,
):
    inventory, grouping = _group(monkeypatch, _pair(alias=True))

    issuer_links = [
        observation.filing_observation_id
        for candidate in grouping.issuer_candidates
        for observation in candidate.observations
    ]
    owner_links = [
        observation.upstream_owner_observation_id
        for candidate in grouping.reporting_owner_candidates
        for observation in candidate.observations
    ]
    transaction_links = [
        row.upstream_transaction_observation_id
        for row in grouping.transaction_attributions
    ]
    assert sorted(issuer_links) == sorted(
        item.filing_observation_id for item in inventory.filings
    )
    assert sorted(owner_links) == sorted(
        item.owner_observation_id for item in inventory.reporting_owners
    )
    assert sorted(transaction_links) == sorted(
        item.transaction_observation_id for item in inventory.transactions
    )
    assert len(issuer_links) == len(set(issuer_links))
    assert len(owner_links) == len(set(owner_links))
    assert len(transaction_links) == len(set(transaction_links))
    identity = grouping.identity
    assert identity.filing_observation_count == len(inventory.filings)
    assert identity.reporting_owner_observation_count == len(
        inventory.reporting_owners
    )
    assert identity.transaction_attribution_count == len(inventory.transactions)
    assert identity.issuer_candidate_count == len(grouping.issuer_candidates)
    assert identity.reporting_owner_candidate_count == len(
        grouping.reporting_owner_candidates
    )


def test_grouping_is_order_independent_and_hash_deterministic(monkeypatch):
    specs = _pair(alias=True)
    forward_inventory = _inventory_for_specs(monkeypatch, specs)
    forward = build_form4_sec_entity_grouping(
        forward_inventory,
        builder_git_commit=GROUPING_COMMIT,
    )
    reverse_inventory = _inventory_for_specs(monkeypatch, specs, reverse=True)
    reverse = build_form4_sec_entity_grouping(
        reverse_inventory,
        builder_git_commit=GROUPING_COMMIT,
    )

    assert forward_inventory == reverse_inventory
    assert forward == reverse
    assert forward.identity.grouping_id == reverse.identity.grouping_id
    assert forward.identity.issuer_candidate_inventory_hash == hash_payload(
        [item.to_payload() for item in forward.issuer_candidates]
    )
    assert forward.identity.reporting_owner_candidate_inventory_hash == hash_payload(
        [item.to_payload() for item in forward.reporting_owner_candidates]
    )
    assert forward.identity.transaction_attribution_inventory_hash == hash_payload(
        [item.to_payload() for item in forward.transaction_attributions]
    )


def test_forged_upstream_identity_hash_and_row_semantics_fail_closed(monkeypatch):
    inventory = _inventory_for_specs(monkeypatch, (_spec(1),))
    bad_identity = _forge(
        inventory.identity,
        filing_inventory_hash="0" * 64,
    )
    bad_inventory = _forge(inventory, identity=bad_identity)
    with pytest.raises(Form4SecEntityGroupingError):
        grouping_module._validate_upstream_inventory(bad_inventory)
    with pytest.raises(Form4SecEntityGroupingError):
        build_form4_sec_entity_grouping(
            bad_inventory,
            builder_git_commit=GROUPING_COMMIT,
        )

    bad_filing = _forge(
        inventory.filings[0],
        issuer_name="Unbound Alias",
    )
    bad_inventory = _forge(
        inventory,
        filings=(bad_filing,) + inventory.filings[1:],
    )
    with pytest.raises(Form4SecEntityGroupingError):
        grouping_module._validate_upstream_inventory(bad_inventory)
    with pytest.raises(Form4SecEntityGroupingError):
        build_form4_sec_entity_grouping(
            bad_inventory,
            builder_git_commit=GROUPING_COMMIT,
        )


def test_coherent_object_forgery_without_factory_provenance_is_refused(
    monkeypatch,
):
    """Cascaded hashes cannot substitute for factory provenance."""

    inventory = _inventory_for_specs(monkeypatch, (_spec(1),))
    filing = _forge(inventory.filings[0], issuer_cik=OTHER_ISSUER_CIK)
    filing = _forge(
        filing,
        filing_observation_id=hash_payload(filing.lineage_payload()),
    )
    transaction = _forge(
        inventory.transactions[0],
        filing_observation_id=filing.filing_observation_id,
    )
    transaction = _forge(
        transaction,
        transaction_observation_id=hash_payload(transaction.lineage_payload()),
    )
    identity = _forge(
        inventory.identity,
        filing_inventory_hash=hash_payload([filing.to_payload()]),
        transaction_inventory_hash=hash_payload([transaction.to_payload()]),
    )
    identity = _forge(
        identity,
        inventory_id=(
            "form4-observed-identity-inventory-"
            f"{hash_payload(identity.lineage_payload())[:16]}"
        ),
    )
    forged_inventory = _forge(
        inventory,
        identity=identity,
        filings=(filing,),
        transactions=(transaction,),
    )

    with pytest.raises(Form4SecEntityGroupingError, match="factory"):
        build_form4_sec_entity_grouping(
            forged_inventory,
            builder_git_commit=GROUPING_COMMIT,
        )


def test_registered_inventory_rejects_coherent_pre_call_mutation(monkeypatch):
    """Object identity alone cannot replace the factory's original digest."""

    inventory = _inventory_for_specs(monkeypatch, (_spec(1),))
    filing = _forge(inventory.filings[0], issuer_cik=OTHER_ISSUER_CIK)
    filing = _forge(
        filing,
        filing_observation_id=hash_payload(filing.lineage_payload()),
    )
    transaction = _forge(
        inventory.transactions[0],
        filing_observation_id=filing.filing_observation_id,
    )
    transaction = _forge(
        transaction,
        transaction_observation_id=hash_payload(transaction.lineage_payload()),
    )
    identity = _forge(
        inventory.identity,
        filing_inventory_hash=hash_payload([filing.to_payload()]),
        transaction_inventory_hash=hash_payload([transaction.to_payload()]),
    )
    identity = _forge(
        identity,
        inventory_id=(
            "form4-observed-identity-inventory-"
            f"{hash_payload(identity.lineage_payload())[:16]}"
        ),
    )
    object.__setattr__(inventory, "identity", identity)
    object.__setattr__(inventory, "filings", (filing,))
    object.__setattr__(inventory, "transactions", (transaction,))

    with pytest.raises(Form4SecEntityGroupingError, match="factory|provenance"):
        build_form4_sec_entity_grouping(
            inventory,
            builder_git_commit=GROUPING_COMMIT,
        )


@pytest.mark.parametrize(
    "observed_fingerprint",
    (None, True, "A" * 64, "a" * 63, "g" * 64, "0" * 64),
)
def test_factory_registry_matcher_refuses_malformed_fingerprints(
    monkeypatch,
    observed_fingerprint,
):
    inventory = _inventory_for_specs(monkeypatch, (_spec(1),))
    exact_fingerprint = grouping_module._upstream_fingerprint(inventory)

    assert (
        grouping_module
        ._matches_factory_created_observed_identity_inventory_fingerprint(
            inventory,
            exact_fingerprint,
        )
    )
    assert not (
        grouping_module
        ._matches_factory_created_observed_identity_inventory_fingerprint(
            inventory,
            observed_fingerprint,
        )
    )


def test_transient_inventory_swap_cannot_change_the_consumed_snapshot(monkeypatch):
    """An A-to-B-to-A swap during validation must never emit B as A."""

    inventory_a = _inventory_for_specs(monkeypatch, (_spec(1),))
    inventory_b = _inventory_for_specs(
        monkeypatch,
        (_spec(3, issuer_cik=OTHER_ISSUER_CIK),),
    )
    original_state = {
        name: vars(inventory_a)[name]
        for name in grouping_module._INVENTORY_FIELDS
    }
    replacement_state = {
        name: vars(inventory_b)[name]
        for name in grouping_module._INVENTORY_FIELDS
    }
    real_validate = grouping_module._validate_upstream_inventory

    def validate_during_transient_swap(value):
        for name, item in replacement_state.items():
            object.__setattr__(inventory_a, name, item)
        try:
            return real_validate(value)
        finally:
            for name, item in original_state.items():
                object.__setattr__(inventory_a, name, item)

    monkeypatch.setattr(
        grouping_module,
        "_validate_upstream_inventory",
        validate_during_transient_swap,
    )
    with pytest.raises(Form4SecEntityGroupingError, match="factory|provenance"):
        build_form4_sec_entity_grouping(
            inventory_a,
            builder_git_commit=GROUPING_COMMIT,
        )
    assert all(
        vars(inventory_a)[name] is item
        for name, item in original_state.items()
    )


@pytest.mark.parametrize(
    "mismatch_field",
    ("accession_number", "source_sha256", "accepted_at_utc"),
)
def test_coherent_owner_observation_must_match_its_referenced_issuer(
    monkeypatch,
    mismatch_field,
):
    specs = (
        _spec(1),
        _spec(
            3,
            owners=(
                _Owner(
                    cik=OTHER_OWNER_CIK,
                    name="Other Officer",
                    title="Treasurer",
                ),
            ),
        ),
    )
    _inventory, grouping = _group(monkeypatch, specs)
    owner_candidate = next(
        item
        for item in grouping.reporting_owner_candidates
        if item.owner_cik == OWNER_CIK
    )
    owner_observation = owner_candidate.observations[0]
    mismatches = {
        "accession_number": "0000123456-26-999997",
        "source_sha256": "1" * 64,
        "accepted_at_utc": (
            datetime.fromisoformat(owner_observation.accepted_at_utc)
            + timedelta(seconds=1)
        ).isoformat(timespec="seconds"),
    }
    changed_observation = _rehash_owner_observation(
        owner_observation,
        **{mismatch_field: mismatches[mismatch_field]},
    )
    changed_candidate = _rehash_owner_candidate(
        owner_candidate,
        (changed_observation,),
    )
    owner_candidates = tuple(
        changed_candidate if item is owner_candidate else item
        for item in grouping.reporting_owner_candidates
    )
    transactions = tuple(
        _rehash_transaction_attribution(
            item,
            attributed_owner_candidate_id=changed_candidate.owner_candidate_id,
        )
        if item.filing_observation_id == owner_observation.filing_observation_id
        else item
        for item in grouping.transaction_attributions
    )
    forged = _rehash_grouping(
        grouping,
        reporting_owner_candidates=owner_candidates,
        transaction_attributions=transactions,
    )

    with pytest.raises(Form4SecEntityGroupingError):
        _validate_forged_grouping(forged)


@pytest.mark.parametrize(
    ("mismatch_field", "mismatch_value"),
    (
        ("accession_number", "0000123456-26-999998"),
        ("source_sha256", "2" * 64),
    ),
)
def test_coherent_transaction_must_match_its_referenced_filing(
    monkeypatch,
    mismatch_field,
    mismatch_value,
):
    _inventory, grouping = _group(monkeypatch, _pair())
    transaction = grouping.transaction_attributions[0]
    changed_transaction = _rehash_transaction_attribution(
        transaction,
        **{mismatch_field: mismatch_value},
    )
    transactions = tuple(
        changed_transaction if item is transaction else item
        for item in grouping.transaction_attributions
    )
    forged = _rehash_grouping(
        grouping,
        transaction_attributions=transactions,
    )

    with pytest.raises(Form4SecEntityGroupingError):
        _validate_forged_grouping(forged)


def test_coherent_amendment_observation_requires_valid_original_lineage(
    monkeypatch,
):
    _inventory, grouping = _group(monkeypatch, _pair())
    issuer_candidate = grouping.issuer_candidates[0]
    amendment = next(
        item for item in issuer_candidate.observations if item.document_type == "4/A"
    )
    changed_amendment = _rehash_issuer_observation(
        amendment,
        amends_accession="0000123456-26-999999",
    )
    observations = tuple(
        changed_amendment if item is amendment else item
        for item in issuer_candidate.observations
    )
    changed_candidate = _rehash_issuer_candidate(
        issuer_candidate,
        observations,
    )
    transactions = tuple(
        _rehash_transaction_attribution(
            item,
            issuer_candidate_id=changed_candidate.issuer_candidate_id,
        )
        for item in grouping.transaction_attributions
    )
    forged = _rehash_grouping(
        grouping,
        issuer_candidates=(changed_candidate,),
        transaction_attributions=transactions,
    )

    with pytest.raises(Form4SecEntityGroupingError):
        _validate_forged_grouping(forged)


def test_coherent_duplicate_filing_key_across_issuer_candidates_is_refused(
    monkeypatch,
):
    specs = (
        _spec(1, owners=(), include_transaction=False),
        _spec(
            3,
            issuer_cik=OTHER_ISSUER_CIK,
            owners=(),
            include_transaction=False,
        ),
    )
    _inventory, grouping = _group(monkeypatch, specs)
    first_candidate, second_candidate = grouping.issuer_candidates
    first_observation = first_candidate.observations[0]
    second_observation = second_candidate.observations[0]
    changed_observation = _rehash_issuer_observation(
        second_observation,
        accession_number=first_observation.accession_number,
        source_sha256=first_observation.source_sha256,
    )
    changed_candidate = _rehash_issuer_candidate(
        second_candidate,
        (changed_observation,),
    )
    forged = _rehash_grouping(
        grouping,
        issuer_candidates=(first_candidate, changed_candidate),
    )

    with pytest.raises(Form4SecEntityGroupingError):
        _validate_forged_grouping(forged)


def test_coherent_duplicate_upstream_owner_observation_id_is_refused(monkeypatch):
    owners = (
        _Owner(),
        _Owner(cik=OTHER_OWNER_CIK, name="Other Officer", title="Treasurer"),
    )
    _inventory, grouping = _group(
        monkeypatch,
        (_spec(1, owners=owners, include_transaction=False),),
    )
    first_candidate, second_candidate = grouping.reporting_owner_candidates
    first_observation = first_candidate.observations[0]
    second_observation = second_candidate.observations[0]
    changed_observation = _rehash_owner_observation(
        second_observation,
        upstream_owner_observation_id=(
            first_observation.upstream_owner_observation_id
        ),
    )
    changed_candidate = _rehash_owner_candidate(
        second_candidate,
        (changed_observation,),
    )
    forged = _rehash_grouping(
        grouping,
        reporting_owner_candidates=(first_candidate, changed_candidate),
    )

    with pytest.raises(Form4SecEntityGroupingError):
        _validate_forged_grouping(forged)


@pytest.mark.parametrize(
    "duplicate_kind",
    ("source-row", "report-row", "payload"),
)
def test_coherent_duplicate_transaction_lineage_ids_are_refused(
    monkeypatch,
    duplicate_kind,
):
    _inventory, grouping = _group(monkeypatch, _pair())
    first, second = grouping.transaction_attributions
    if duplicate_kind == "source-row":
        updates = {
            "accession_number": first.accession_number,
            "source_sha256": first.source_sha256,
            "row_index": first.row_index,
            "filing_observation_id": first.filing_observation_id,
        }
    elif duplicate_kind == "report-row":
        updates = {"upstream_report_row_id": first.upstream_report_row_id}
    else:
        updates = {"transaction_payload_hash": first.transaction_payload_hash}
    changed = _rehash_transaction_attribution(second, **updates)
    forged = _rehash_grouping(
        grouping,
        transaction_attributions=(first, changed),
    )

    with pytest.raises(Form4SecEntityGroupingError):
        _validate_forged_grouping(forged)


def test_upstream_mutation_during_validation_is_refused(monkeypatch):
    inventory = _inventory_for_specs(monkeypatch, (_spec(1),))
    real_validate = grouping_module._validate_upstream_inventory

    def mutate_after_validation(value):
        result = real_validate(value)
        object.__setattr__(
            value.identity,
            "filing_count",
            value.identity.filing_count + 1,
        )
        return result

    monkeypatch.setattr(
        grouping_module,
        "_validate_upstream_inventory",
        mutate_after_validation,
    )
    with pytest.raises(Form4SecEntityGroupingError):
        build_form4_sec_entity_grouping(
            inventory,
            builder_git_commit=GROUPING_COMMIT,
        )


@pytest.mark.parametrize("value", (object(), {}, ()))
def test_non_exact_upstream_types_fail_with_the_public_error(value):
    with pytest.raises(Form4SecEntityGroupingError):
        build_form4_sec_entity_grouping(
            value,
            builder_git_commit=GROUPING_COMMIT,
        )


@pytest.mark.parametrize(
    "builder_commit",
    (None, True, "a" * 39, "A" * 40),
)
def test_builder_commit_requires_a_full_lowercase_sha1(monkeypatch, builder_commit):
    inventory = _inventory_for_specs(monkeypatch, (_spec(1),))
    with pytest.raises(Form4SecEntityGroupingError, match="Git commit"):
        build_form4_sec_entity_grouping(
            inventory,
            builder_git_commit=builder_commit,
        )


def test_extra_state_and_contract_cycles_fail_before_grouping(monkeypatch):
    inventory = _inventory_for_specs(monkeypatch, (_spec(1),))
    extra = _forge(inventory)
    object.__setattr__(extra, "unexpected_state", "forged")
    with pytest.raises(Form4SecEntityGroupingError):
        build_form4_sec_entity_grouping(
            extra,
            builder_git_commit=GROUPING_COMMIT,
        )
    with pytest.raises(Form4SecEntityGroupingError, match="state"):
        grouping_module._project_upstream(extra)

    cyclic = _forge(inventory)
    object.__setattr__(cyclic, "filings", (cyclic,))
    with pytest.raises(Form4SecEntityGroupingError):
        build_form4_sec_entity_grouping(
            cyclic,
            builder_git_commit=GROUPING_COMMIT,
        )
    with pytest.raises(Form4SecEntityGroupingError, match="cycle"):
        grouping_module._project_upstream(cyclic)


def test_projection_resource_bound_fails_closed(monkeypatch):
    inventory = _inventory_for_specs(monkeypatch, (_spec(1),))
    monkeypatch.setattr(
        grouping_module,
        "MAX_FORM4_SEC_ENTITY_GROUPING_PROJECTION_NODES",
        1,
    )
    with pytest.raises(Form4SecEntityGroupingError, match="node bound"):
        build_form4_sec_entity_grouping(
            inventory,
            builder_git_commit=GROUPING_COMMIT,
        )


@pytest.mark.parametrize(
    ("value_factory", "constant_name", "expected_message"),
    (
        (
            lambda: {"key": "value"},
            "MAX_FORM4_SEC_ENTITY_GROUPING_PROJECTION_NODES",
            "node bound",
        ),
        (
            lambda: "value",
            "MAX_FORM4_OBSERVED_IDENTITY_TEXT_CHARACTERS",
            "text bound",
        ),
        (
            lambda: [None],
            "MAX_FORM4_SEC_ENTITY_GROUPING_PROJECTION_DEPTH",
            "depth bound",
        ),
    ),
)
def test_validated_snapshot_resource_guards_fail_closed(
    monkeypatch,
    value_factory,
    constant_name,
    expected_message,
):
    monkeypatch.setattr(grouping_module, constant_name, 0)
    with pytest.raises(Form4SecEntityGroupingError, match=expected_message):
        grouping_module._project_validated_snapshot(value_factory())


def test_validated_snapshot_shape_guards_fail_closed():
    cyclic: list[object] = []
    cyclic.append(cyclic)
    for value, expected_message in (
        (cyclic, "cycle"),
        ({1: "value"}, "exact text"),
        (object(), "unsupported value"),
    ):
        with pytest.raises(Form4SecEntityGroupingError, match=expected_message):
            grouping_module._project_validated_snapshot(value)


def test_projection_node_cap_covers_the_declared_upstream_maximum_envelope():
    filing_count = grouping_module.MAX_FORM4_OBSERVED_IDENTITY_FILINGS
    owner_count = (
        grouping_module.MAX_FORM4_OBSERVED_IDENTITY_REPORTING_OWNERS
    )
    transaction_count = (
        grouping_module.MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS
    )
    identity_nodes = 1 + len(grouping_module._INVENTORY_IDENTITY_FIELDS)
    filing_nodes = (
        filing_count * (1 + len(grouping_module._FILING_FIELDS) + 5)
        + owner_count
    )
    owner_nodes = owner_count * (1 + len(grouping_module._OWNER_FIELDS))
    transaction_nodes = transaction_count * (
        1 + len(grouping_module._TRANSACTION_FIELDS) + 2
    )
    maximum_nodes = (
        1  # root inventory dataclass
        + identity_nodes
        + 3  # filing, owner, and transaction tuples
        + filing_nodes
        + owner_nodes
        + transaction_nodes
    )

    assert (
        grouping_module.MAX_FORM4_SEC_ENTITY_GROUPING_PROJECTION_NODES
        >= maximum_nodes
    )


def test_every_identity_and_transaction_authority_gate_is_zero(monkeypatch):
    _inventory, grouping = _group(monkeypatch, _pair())

    payloads = [grouping.identity.to_payload()]
    payloads.extend(item.to_payload() for item in grouping.issuer_candidates)
    payloads.extend(
        item.to_payload() for item in grouping.reporting_owner_candidates
    )
    payloads.extend(item.to_payload() for item in grouping.transaction_attributions)
    for payload in payloads:
        for name, value in payload.items():
            if name.endswith("_verified") or name.endswith("_authorized"):
                assert value is False, name
    authority_names = tuple(
        name
        for name in grouping.identity.to_payload()
        if name.endswith("_verified") or name.endswith("_authorized")
    )
    for name in authority_names:
        assert getattr(grouping, name) is False, name
    assert grouping.identity.authorized_outcome_looks == 0
    assert grouping.identity.consumed_outcome_looks == 0
    assert grouping.authorized_outcome_looks == 0
    assert grouping.consumed_outcome_looks == 0


@pytest.mark.parametrize(
    ("target_name", "field_name"),
    (
        ("identity", "official_profile_compatibility_verified"),
        ("identity", "official_amendment_link_verified"),
        ("identity", "complete_amendment_coverage_verified"),
        ("identity", "point_in_time_issuer_identity_verified"),
        ("identity", "point_in_time_reporting_owner_identity_verified"),
        ("identity", "point_in_time_security_identity_verified"),
        ("identity", "point_in_time_transaction_identity_verified"),
        ("identity", "ordinary_equity_classification_verified"),
        ("identity", "canonical_filter_authorized"),
        ("identity", "lot_aggregation_authorized"),
        ("identity", "outcomes_authorized"),
        ("identity", "qc_execution_authorized"),
        ("identity", "deployment_authorized"),
        ("identity", "trading_authorized"),
        ("identity", "authorized_outcome_looks"),
        ("identity", "consumed_outcome_looks"),
        ("issuer", "point_in_time_issuer_identity_verified"),
        ("owner", "point_in_time_reporting_owner_identity_verified"),
        ("transaction", "point_in_time_issuer_identity_verified"),
        ("transaction", "point_in_time_reporting_owner_identity_verified"),
        ("transaction", "point_in_time_security_identity_verified"),
        ("transaction", "point_in_time_transaction_identity_verified"),
        ("transaction", "canonical_filter_authorized"),
        ("transaction", "lot_aggregation_authorized"),
    ),
)
def test_every_output_authority_escalation_is_refused(
    monkeypatch,
    target_name,
    field_name,
):
    _inventory, grouping = _group(monkeypatch, _pair())
    targets = {
        "identity": (
            grouping.identity,
            grouping_module._IDENTITY_FACTORY_TOKEN,
        ),
        "issuer": (
            grouping.issuer_candidates[0],
            grouping_module._CANDIDATE_FACTORY_TOKEN,
        ),
        "owner": (
            grouping.reporting_owner_candidates[0],
            grouping_module._CANDIDATE_FACTORY_TOKEN,
        ),
        "transaction": (
            grouping.transaction_attributions[0],
            grouping_module._ROW_FACTORY_TOKEN,
        ),
    }
    target, token = targets[target_name]
    escalated_value = 1 if field_name.endswith("_looks") else True
    forged = _forge(target, **{field_name: escalated_value})

    with pytest.raises(Form4SecEntityGroupingError, match="authority|identity"):
        type(target).__post_init__(forged, token)


def test_public_result_types_are_factory_gated(monkeypatch):
    _inventory, grouping = _group(monkeypatch, (_spec(1),))

    for value in (
        grouping,
        grouping.identity,
        grouping.issuer_candidates[0],
        grouping.issuer_candidates[0].observations[0],
        grouping.reporting_owner_candidates[0],
        grouping.reporting_owner_candidates[0].observations[0],
        grouping.transaction_attributions[0],
    ):
        with pytest.raises(Form4SecEntityGroupingError, match="factory-created"):
            replace(value)


def test_ib2b_module_has_no_float_network_provider_outcome_qc_or_execution_surface():
    module_path = Path(grouping_module.__file__)
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(module_path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert imported == {
        "__future__",
        "data.hashing",
        "dataclasses",
        "datetime",
        "enum",
        "re",
        "research.insider_buying.form4_amendment_reconciliation",
        "research.insider_buying.form4_observed_identity_inventory",
        "research.insider_buying.form4_provisional_disposition_report",
    }
    assert imported.isdisjoint(
        {
            "QuantConnect",
            "aiohttp",
            "alpaca",
            "execution",
            "httpx",
            "numpy",
            "pandas",
            "requests",
            "socket",
            "urllib",
            "yfinance",
        }
    )
    assert not any(
        isinstance(node, ast.Name) and node.id == "float"
        for node in ast.walk(tree)
    )
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"__import__", "open"}
        for node in ast.walk(tree)
    )
    assert not any(
        token.type == tokenize.NUMBER
        and any(marker in token.string.lower() for marker in (".", "e"))
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
    )
