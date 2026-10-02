"""Synthetic, zero-I/O checks for the 82-quarter canonical source boundary."""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import fields, replace
from datetime import datetime, timezone

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying import (
    SecBulkSource,
    build_sec_bulk_parsed_snapshot,
    load_sec_bulk_parsed_snapshot,
    load_sec_bulk_snapshot,
    write_sec_bulk_snapshot,
)
from research.insider_buying.sec_bulk_parsed_snapshot import (
    ParsedSecBulkAccession,
    ParsedSecBulkArtifactIdentity,
    SecBulkParsedSnapshotIdentity,
    SecTsvSchemaProfile,
    SecTsvSchemaVariant,
)
from research.insider_buying.sec_bulk_snapshot import SecBulkSnapshotIdentity
from research.insider_buying import sec_canonical_source_manifest as manifest_module
from research.insider_buying.sec_canonical_source_manifest import (
    CanonicalIb2AccessionSource,
    CanonicalIb2ArtifactStream,
    CanonicalIb2QuarterInput,
    CanonicalIb2SourceManifest,
    CanonicalIb2SourceManifestError,
    build_canonical_ib2_source_manifest,
    verify_artifact_chunks,
)
from research.insider_buying.sec_owner_supplied_source_policy import (
    CANONICAL_IB2_REQUIRED_PERIODS,
    CanonicalIb2SourcePolicy,
)
from research.insider_buying.sec_owner_supplied_source_policy_v2 import (
    CANONICAL_IB2_SOURCE_POLICY_V2_SHA256,
    CANONICAL_IB2_SOURCE_V2_EVIDENCE_EPOCH,
    CanonicalIb2SourcePolicyV2,
)


_CAPTURE_COMMIT = "a" * 40
_PARSER_COMMIT = "b" * 40
_RETRIEVED_AT = "2026-09-25T00:00:00+00:00"


def _archive_url(accession_number: str, filename: str) -> str:
    return (
        "https://www.sec.gov/Archives/edgar/data/123456/"
        f"{accession_number.replace('-', '')}/{filename}"
    )


_ARTIFACT_URL = _archive_url("0000123456-06-000101", "x.xml")
_PROFILE = SecTsvSchemaProfile(
    profile_id="synthetic-only-82-quarter-profile",
    variants=(
        SecTsvSchemaVariant(
            schema_id="synthetic-submission",
            table_name="SUBMISSION.tsv",
            headers=(
                "ACCESSION_NUMBER",
                "FILING_DATE",
                "PERIOD_OF_REPORT",
                "DOCUMENT_TYPE",
                "ISSUERCIK",
                "ISSUERNAME",
                "ISSUERTRADINGSYMBOL",
            ),
            source_row_key_headers=(),
            valid_from_year=2006,
            valid_from_quarter=1,
            valid_through_year=2026,
            valid_through_quarter=2,
        ),
        SecTsvSchemaVariant(
            schema_id="synthetic-owner",
            table_name="REPORTINGOWNER.tsv",
            headers=("ACCESSION_NUMBER", "RPTOWNERCIK"),
            source_row_key_headers=(),
            valid_from_year=2006,
            valid_from_quarter=1,
            valid_through_year=2026,
            valid_through_quarter=2,
        ),
        SecTsvSchemaVariant(
            schema_id="synthetic-transaction",
            table_name="NONDERIV_TRANS.tsv",
            headers=("ACCESSION_NUMBER", "TRANSACTION_ID"),
            source_row_key_headers=("TRANSACTION_ID",),
            valid_from_year=2006,
            valid_from_quarter=1,
            valid_through_year=2026,
            valid_through_quarter=2,
        ),
    ),
)


def _accession(period: str, sequence: int, document_type: str) -> ParsedSecBulkAccession:
    year = int(period[:4]) % 100
    quarter = int(period[-1])
    number = f"0000123456-{year:02d}-{quarter * 100 + sequence:06d}"
    return ParsedSecBulkAccession(
        accession_number=number,
        document_type=document_type,
        submission_row_id=hash_bytes(f"submission:{number}".encode("ascii")),
        table_rows=(),
    )


def _stream(
    payload: bytes,
    *,
    chunks: tuple[bytes, ...] | None = None,
    source_url: str = _ARTIFACT_URL,
    retrieved_at_utc: str = _RETRIEVED_AT,
) -> CanonicalIb2ArtifactStream:
    return CanonicalIb2ArtifactStream(
        sha256=hash_bytes(payload),
        size_bytes=len(payload),
        chunks=(payload,) if chunks is None else chunks,
        source_url=source_url,
        retrieved_at_utc=retrieved_at_utc,
    )


def _source(accession: ParsedSecBulkAccession, period: str) -> CanonicalIb2AccessionSource:
    number = accession.accession_number
    return CanonicalIb2AccessionSource(
        accession_number=number,
        acceptance_metadata=_stream(
            f"metadata:{period}:{number}".encode("ascii"),
            source_url=_archive_url(number, "metadata.json"),
        ),
        primary_ownership_xml=_stream(
            f"<xml>{period}:{number}</xml>".encode("ascii"),
            source_url=_archive_url(number, "x.xml"),
        ),
    )


def _artifact(name: str, payload: bytes, count: int) -> ParsedSecBulkArtifactIdentity:
    return ParsedSecBulkArtifactIdentity(
        name=name,
        sha256=hash_bytes(payload),
        size_bytes=len(payload),
        record_count=count,
    )


def _relineage_raw(raw: SecBulkSnapshotIdentity) -> SecBulkSnapshotIdentity:
    lineage = hash_payload(raw.lineage_payload())
    return replace(
        raw,
        lineage_hash=lineage,
        snapshot_id=f"sec-insider-bulk-{raw.year:04d}q{raw.quarter}-{lineage[:16]}",
    )


def _relineage_parsed(parsed: SecBulkParsedSnapshotIdentity) -> SecBulkParsedSnapshotIdentity:
    lineage = hash_payload(parsed.lineage_payload())
    return replace(
        parsed,
        lineage_hash=lineage,
        snapshot_id=f"sec-insider-parsed-{parsed.year:04d}q{parsed.quarter}-{lineage[:16]}",
    )


def _quarter(
    period: str,
    *,
    document_types: tuple[str, ...] = ("4", "3"),
) -> CanonicalIb2QuarterInput:
    year, quarter = int(period[:4]), int(period[-1])
    raw_bytes = f"synthetic-archive:{period}".encode("ascii")
    raw = _relineage_raw(
        SecBulkSnapshotIdentity(
            year=year,
            quarter=quarter,
            source_url=(
                "https://www.sec.gov/files/dera/data/insider-transactions-data-sets/"
                f"{year}q{quarter}_form345.zip"
            ),
            git_commit=_CAPTURE_COMMIT,
            retrieved_at_utc=_RETRIEVED_AT,
            archive_sha256=hash_bytes(raw_bytes),
            archive_size_bytes=len(raw_bytes),
            members=(),
            auxiliary_members=(),
            lineage_hash="",
            snapshot_id="",
        )
    )
    accessions = tuple(
        _accession(period, sequence, form)
        for sequence, form in enumerate(document_types, start=1)
    )
    accession_bytes = b"".join(
        (canonical_json(item.to_payload()) + "\n").encode("utf-8")
        for item in accessions
    )
    raw_manifest_bytes = (canonical_json(raw.to_payload()) + "\n").encode("utf-8")
    parsed = _relineage_parsed(
        SecBulkParsedSnapshotIdentity(
            year=year,
            quarter=quarter,
            parser_git_commit=_PARSER_COMMIT,
            raw_snapshot_id=raw.snapshot_id,
            raw_lineage_hash=raw.lineage_hash,
            raw_archive_sha256=raw.archive_sha256,
            raw_manifest_sha256=hash_bytes(raw_manifest_bytes),
            schema_profile=_PROFILE,
            schema_profile_hash=hash_payload(_PROFILE.to_payload()),
            absent_tables=(),
            tables=(),
            artifacts=(
                _artifact("rows.jsonl", b"", 0),
                _artifact("accessions.jsonl", accession_bytes, len(accessions)),
            ),
            lineage_hash="",
            snapshot_id="",
        )
    )
    sources = tuple(
        _source(item, period)
        for item in accessions
        if item.document_type in {"4", "4/A"}
    )
    return CanonicalIb2QuarterInput(
        raw=raw,
        parsed=parsed,
        accessions=accessions,
        sources=sources,
    )


def _quarters() -> tuple[CanonicalIb2QuarterInput, ...]:
    return tuple(_quarter(period) for period in CANONICAL_IB2_REQUIRED_PERIODS)


def _build(quarters=None, *, policy=None):
    return build_canonical_ib2_source_manifest(
        _quarters() if quarters is None else quarters,
        policy=CanonicalIb2SourcePolicy() if policy is None else policy,
    )


def _build_v2(quarters=None):
    return _build(quarters, policy=CanonicalIb2SourcePolicyV2())


@pytest.mark.parametrize("amended_form", ["3/A", "5/A"])
def test_v2_amended_context_is_retained_without_source_pairs(amended_form):
    quarters = list(_quarters())
    item = _quarter("2006Q1", document_types=("4", amended_form))
    assert len(item.sources) == 1
    quarters[0] = item
    summary = _build_v2(quarters).quarters[0]
    assert summary.form4_accession_count == 1
    assert summary.context_accession_count == 1
    assert summary.accessions_record_count == 2
    assert item.accessions[1].document_type == amended_form
    assert summary.accessions_artifact_sha256 == item.parsed.artifacts[1].sha256


def test_v1_manifest_identity_is_preserved_and_v2_is_a_distinct_epoch():
    legacy = _build()
    assert legacy.to_payload()["version"] == 1
    assert manifest_module.CANONICAL_IB2_SOURCE_MANIFEST_VERSION == 1
    assert manifest_module.CANONICAL_IB2_SOURCE_MANIFEST_V2_VERSION == 2
    assert legacy.manifest_sha256 == (
        "b2d9c77ca2f89d286093bcd29d84af6a131db6868c8c85d308354d8c5dfb4aea"
    )
    revised = _build_v2()
    payload = revised.to_payload()
    assert payload["version"] == 2
    assert payload["policy_sha256"] == CANONICAL_IB2_SOURCE_POLICY_V2_SHA256
    assert payload["revision"] == {
        "evidence_epoch_id": CANONICAL_IB2_SOURCE_V2_EVIDENCE_EPOCH,
        "supersedes_policy_sha256": legacy.policy_sha256,
    }
    assert legacy.quarters == revised.quarters
    assert legacy.manifest_sha256 != revised.manifest_sha256
    assert _build_v2().to_payload() == payload
    assert hash_payload(revised.lineage_payload()) == revised.manifest_sha256
    # A v2 hash cannot be reused under the old policy, nor vice versa.
    with pytest.raises(CanonicalIb2SourceManifestError, match="content hash"):
        replace(revised, policy_sha256=legacy.policy_sha256)
    with pytest.raises(CanonicalIb2SourceManifestError, match="content hash"):
        replace(legacy, policy_sha256=revised.policy_sha256)


@pytest.mark.parametrize("amended_form", ["3/A", "5/A"])
def test_v1_still_refuses_amended_context(amended_form):
    quarters = list(_quarters())
    quarters[0] = _quarter("2006Q1", document_types=("4", amended_form))
    with pytest.raises(CanonicalIb2SourceManifestError, match="unapproved document type"):
        _build(quarters)


def test_v2_all_six_types_across_82_quarters_keep_exact_form4_coverage():
    forms = ("3", "3/A", "4", "4/A", "5", "5/A")
    quarters = tuple(
        _quarter(period, document_types=forms)
        for period in CANONICAL_IB2_REQUIRED_PERIODS
    )
    manifest = _build_v2(_OneShot(quarters))
    assert len(manifest.quarters) == 82
    for item, summary in zip(quarters, manifest.quarters):
        assert tuple(row.document_type for row in item.accessions) == forms
        assert (
            summary.accessions_record_count,
            summary.form4_accession_count,
            summary.context_accession_count,
        ) == (6, 2, 4)
        assert len(item.sources) == 2
        assert summary.accessions_artifact_sha256 == item.parsed.artifacts[1].sha256


@pytest.mark.parametrize("form", ["8-K", "3/a", "5/a", "5/A ", "", "4/A/A"])
def test_v2_unknown_or_noncanonical_type_still_refuses(form):
    quarters = list(_quarters())
    quarters[0] = _quarter("2006Q1", document_types=("4", form))
    with pytest.raises(CanonicalIb2SourceManifestError, match="unapproved document type"):
        _build_v2(quarters)


@pytest.mark.parametrize("form", ["3", "3/A", "5", "5/A"])
def test_v2_context_only_quarter_needs_no_sources_and_refuses_extra_pair(form):
    quarters = list(_quarters())
    item = _quarter("2006Q1", document_types=(form,))
    assert item.sources == ()
    quarters[0] = item
    assert _build_v2(quarters).quarters[0].form4_accession_count == 0
    quarters[0] = replace(item, sources=(_source(item.accessions[0], "2006Q1"),))
    with pytest.raises(CanonicalIb2SourceManifestError, match="extra source"):
        _build_v2(quarters)


@pytest.mark.parametrize("mutation", ["changed", "missing", "extra"])
def test_v2_complete_amended_context_inventory_remains_digest_bound(mutation):
    quarters = list(_quarters())
    item = _quarter("2006Q1", document_types=("4", "3/A", "5/A"))
    if mutation == "changed":
        rows = (
            item.accessions[0],
            replace(item.accessions[1], document_type="3"),
            item.accessions[2],
        )
    elif mutation == "missing":
        rows = item.accessions[:2]
    else:
        rows = (*item.accessions, _accession("2006Q1", 4, "5/A"))
    quarters[0] = replace(item, accessions=rows)
    with pytest.raises(CanonicalIb2SourceManifestError, match="artifact"):
        _build_v2(quarters)


@pytest.mark.parametrize("mutation", ["missing", "wrong_accession", "extra"])
def test_v2_form4_amendments_keep_one_to_one_sources(mutation):
    quarters = list(_quarters())
    item = _quarter("2006Q1", document_types=("3/A", "4", "4/A", "5/A"))
    if mutation == "missing":
        sources = item.sources[:1]
    elif mutation == "wrong_accession":
        sources = (item.sources[1], item.sources[0])
    else:
        sources = (*item.sources, item.sources[1])
    quarters[0] = replace(item, sources=sources)
    with pytest.raises(CanonicalIb2SourceManifestError, match="metadata/XML"):
        _build_v2(quarters)


def test_v2_cross_quarter_duplicate_amended_context_is_refused():
    quarters = list(_quarters())
    first = _quarter("2006Q1", document_types=("3/A",))
    second = _quarter("2006Q2", document_types=("5/A",))
    repeated = replace(
        second.accessions[0],
        accession_number=first.accessions[0].accession_number,
    )
    data = (canonical_json(repeated.to_payload()) + "\n").encode("utf-8")
    artifacts = tuple(
        _artifact("accessions.jsonl", data, 1) if a.name == "accessions.jsonl" else a
        for a in second.parsed.artifacts
    )
    quarters[0] = first
    quarters[1] = replace(
        second,
        accessions=(repeated,),
        parsed=_relineage_parsed(replace(second.parsed, artifacts=artifacts)),
    )
    with pytest.raises(CanonicalIb2SourceManifestError, match="duplicate accession"):
        _build_v2(quarters)


def test_v2_relabeling_an_amendment_changes_content_identity_not_form4_count():
    amended = list(_quarters())
    original = list(_quarters())
    amended[0] = _quarter("2006Q1", document_types=("4", "3/A", "5/A"))
    original[0] = _quarter("2006Q1", document_types=("4", "3", "5"))
    left, right = _build_v2(amended), _build_v2(original)
    assert left.manifest_sha256 != right.manifest_sha256
    assert (
        left.quarters[0].accession_sources_sha256
        == right.quarters[0].accession_sources_sha256
    )
    assert (
        left.quarters[0].form4_accession_count
        == right.quarters[0].form4_accession_count == 1
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("context_document_types", ("3", "5")),
        ("evidence_epoch_id", "forged-epoch"),
        ("supersedes_policy_sha256", "0" * 64),
        ("canonical_scoring_authorized", True),
    ],
)
def test_v2_hostile_policy_mutation_before_or_during_streaming_refuses(field, value):
    policy = CanonicalIb2SourcePolicyV2()
    object.__setattr__(policy, field, value)
    with pytest.raises(CanonicalIb2SourceManifestError, match="frozen version"):
        _build(policy=policy)
    policy = CanonicalIb2SourcePolicyV2()
    quarters = list(_quarters())
    item = quarters[-1]
    source = item.sources[0]
    payload = tuple(source.acceptance_metadata.chunks)

    def chunks():
        object.__setattr__(policy, field, value)
        yield from payload

    quarters[-1] = replace(
        item,
        sources=(
            replace(
                source,
                acceptance_metadata=replace(source.acceptance_metadata, chunks=chunks()),
            ),
        ),
    )
    with pytest.raises(CanonicalIb2SourceManifestError, match="changed while streaming"):
        _build(quarters, policy=policy)


def test_v2_policy_subclass_is_not_a_frozen_policy():
    class ForgedPolicy(CanonicalIb2SourcePolicyV2):
        pass

    # The v2 constructor also refuses subclasses. Bypass it to prove that the
    # consumer independently checks exact type, rather than relying on it.
    forged = object.__new__(ForgedPolicy)
    valid = CanonicalIb2SourcePolicyV2()
    for item in fields(valid):
        object.__setattr__(forged, item.name, getattr(valid, item.name))
    with pytest.raises(CanonicalIb2SourceManifestError, match="frozen version"):
        _build(policy=forged)


def test_v2_coherent_public_digest_rebinding_does_not_widen_the_consumer(monkeypatch):
    from research.insider_buying import sec_owner_supplied_source_policy_v2 as v2

    policy = CanonicalIb2SourcePolicyV2()
    object.__setattr__(policy, "context_document_types", ("3", "5", "8-K"))
    monkeypatch.setattr(v2, "CANONICAL_IB2_SOURCE_POLICY_V2_SHA256", policy.semantic_sha256)
    with pytest.raises(CanonicalIb2SourceManifestError, match="frozen version"):
        _build(policy=policy)


def test_v2_policy_and_manifest_package_exports_are_explicit():
    import research.insider_buying as package
    from research.insider_buying import sec_owner_supplied_source_policy_v2 as v2

    for name in v2.__all__:
        assert name in package.__all__
        assert getattr(package, name) is getattr(v2, name)
    name = "CANONICAL_IB2_SOURCE_MANIFEST_V2_VERSION"
    assert name in package.__all__
    assert getattr(package, name) == 2


def test_v2_builder_with_amended_context_has_no_io(monkeypatch):
    import builtins
    import socket
    from pathlib import Path

    quarters = list(_quarters())
    quarters[0] = _quarter("2006Q1", document_types=("4", "3/A", "5/A"))
    policy = CanonicalIb2SourcePolicyV2()

    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected I/O")

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(Path, "open", forbidden)
        patch.setattr(socket, "socket", forbidden)
        manifest = _build(quarters, policy=policy)
    assert manifest.quarters[0].context_accession_count == 2
    assert policy.authorized_outcome_looks == policy.consumed_outcome_looks == 0


def test_valid_82_quarter_manifest_is_deterministic_and_retains_context():
    first = _build()
    second = _build()
    assert len(first.quarters) == 82
    assert first.manifest_sha256 == second.manifest_sha256
    assert first.to_payload() == second.to_payload()
    assert first.quarters[0].period == "2006Q1"
    assert first.quarters[-1].period == "2026Q2"
    # Form 3 is retained in the artifact, but only Form 4 needs a source pair.
    first_payload = first.to_payload()["quarters"][0]
    assert first_payload["accessions_record_count"] == 2
    assert first_payload["context_accession_count"] == 1
    assert first_payload["form4_accession_count"] == 1
    assert set(first.to_payload()) == {
        "kind",
        "version",
        "policy_sha256",
        "quarters",
        "manifest_sha256",
    }


@pytest.mark.parametrize("change", ["missing", "duplicate", "reordered", "extra"])
def test_exact_82_quarter_inventory_refuses_drift(change):
    quarters = list(_quarters())
    if change == "missing":
        quarters.pop(30)
    elif change == "duplicate":
        quarters[30] = quarters[29]
    elif change == "reordered":
        quarters[30], quarters[31] = quarters[31], quarters[30]
    else:
        quarters.append(_quarter("2026Q3"))
    with pytest.raises(CanonicalIb2SourceManifestError):
        _build(quarters)


def test_only_exact_frozen_policy_is_accepted():
    with pytest.raises(CanonicalIb2SourceManifestError):
        _build(policy=object())
    class PolicySubclass(CanonicalIb2SourcePolicy):
        pass

    with pytest.raises(CanonicalIb2SourceManifestError):
        _build(policy=PolicySubclass())
    policy = CanonicalIb2SourcePolicy()
    object.__setattr__(policy, "source_manifest_bound", True)
    with pytest.raises(CanonicalIb2SourceManifestError):
        _build(policy=policy)


def test_manifest_hash_cannot_be_forged_after_construction():
    manifest = _build()
    assert isinstance(manifest, CanonicalIb2SourceManifest)
    with pytest.raises(CanonicalIb2SourceManifestError):
        replace(manifest, manifest_sha256="0" * 64)


@pytest.mark.parametrize("mutation", ["raw_hash", "parsed_hash", "parent", "manifest"])
def test_raw_parsed_lineage_and_parent_binding_refuse_mismatch(mutation):
    quarters = list(_quarters())
    item = quarters[5]
    if mutation == "raw_hash":
        item = replace(item, raw=replace(item.raw, lineage_hash="0" * 64))
    elif mutation == "parsed_hash":
        item = replace(item, parsed=replace(item.parsed, lineage_hash="0" * 64))
    elif mutation == "parent":
        item = replace(
            item,
            parsed=_relineage_parsed(
                replace(item.parsed, raw_lineage_hash="0" * 64)
            ),
        )
    else:
        item = replace(
            item,
            parsed=_relineage_parsed(
                replace(item.parsed, raw_manifest_sha256="0" * 64)
            ),
        )
    quarters[5] = item
    with pytest.raises(CanonicalIb2SourceManifestError):
        _build(quarters)


@pytest.mark.parametrize("mutation", ["raw_member", "parsed_profile"])
def test_malformed_nested_identity_refuses_with_domain_error(mutation):
    quarters = list(_quarters())
    item = quarters[0]
    if mutation == "raw_member":
        item = replace(item, raw=replace(item.raw, members=(None,)))
    else:
        item = replace(item, parsed=replace(item.parsed, schema_profile=None))
    quarters[0] = item
    with pytest.raises(CanonicalIb2SourceManifestError):
        _build(quarters)


@pytest.mark.parametrize("mutation", ["changed_context", "missing_context", "extra_context"])
def test_complete_accessions_jsonl_binds_context_rows(mutation):
    quarters = list(_quarters())
    item = quarters[10]
    if mutation == "changed_context":
        context = replace(item.accessions[1], submission_row_id="0" * 64)
        accessions = (item.accessions[0], context)
    elif mutation == "missing_context":
        accessions = item.accessions[:1]
    else:
        accessions = (*item.accessions, _accession("2008Q3", 99, "5"))
    quarters[10] = replace(item, accessions=accessions)
    with pytest.raises(CanonicalIb2SourceManifestError):
        _build(quarters)


def test_same_accession_in_two_quarters_refuses_with_coherent_local_lineage():
    quarters = list(_quarters())
    previous = quarters[39]
    current = quarters[40]
    repeated_form4 = previous.accessions[0]
    # Keep the target quarter's local JSONL artifact and parsed lineage honest;
    # only the corpus-wide uniqueness invariant is broken.
    accessions = (repeated_form4, current.accessions[1])
    accession_bytes = b"".join(
        (canonical_json(item.to_payload()) + "\n").encode("utf-8")
        for item in accessions
    )
    artifacts = tuple(
        _artifact("accessions.jsonl", accession_bytes, len(accessions))
        if artifact.name == "accessions.jsonl"
        else artifact
        for artifact in current.parsed.artifacts
    )
    parsed = _relineage_parsed(replace(current.parsed, artifacts=artifacts))
    quarters[40] = replace(
        current,
        parsed=parsed,
        accessions=accessions,
        sources=(previous.sources[0],),
    )
    with pytest.raises(CanonicalIb2SourceManifestError, match="duplicate|repeated"):
        _build(quarters)


def test_queued_accession_mutation_cannot_hide_cross_quarter_duplicate():
    quarters = list(_quarters())
    first, second = quarters[0], quarters[1]
    queued_first = first.accessions[0]
    original_number = queued_first.accession_number
    repeated_number = "0000123456-06-000150"
    assert original_number < repeated_number

    # Keep both declared JSONL artifacts, local lineage hashes, and serialized
    # accession order coherent with the post-mutation B value. The Q1 source
    # intentionally remains A, the heap key captured before Q2 is primed.
    repeated_row_id = hash_bytes(f"submission:{repeated_number}".encode("ascii"))
    first_context_number = "0000123456-06-000199"
    first_context = replace(
        first.accessions[1],
        accession_number=first_context_number,
        submission_row_id=hash_bytes(
            f"submission:{first_context_number}".encode("ascii")
        ),
    )
    assert repeated_number < first_context_number
    first_declared = (
        replace(
            queued_first,
            accession_number=repeated_number,
            submission_row_id=repeated_row_id,
        ),
        first_context,
    )
    second_form4 = replace(
        second.accessions[0],
        accession_number=repeated_number,
        submission_row_id=repeated_row_id,
    )
    second_declared = (second_form4, second.accessions[1])

    def with_declared_accessions(item, declared, actual, sources):
        artifact_bytes = b"".join(
            (canonical_json(accession.to_payload()) + "\n").encode("utf-8")
            for accession in declared
        )
        artifacts = tuple(
            _artifact("accessions.jsonl", artifact_bytes, len(declared))
            if artifact.name == "accessions.jsonl"
            else artifact
            for artifact in item.parsed.artifacts
        )
        parsed = _relineage_parsed(replace(item.parsed, artifacts=artifacts))
        return replace(item, parsed=parsed, accessions=actual, sources=sources)

    quarters[0] = with_declared_accessions(
        first, first_declared, (queued_first, first_context), first.sources
    )

    def second_accessions():
        # Priming Q2 happens after Q1 has entered the merge heap as A.
        object.__setattr__(queued_first, "accession_number", repeated_number)
        object.__setattr__(queued_first, "submission_row_id", repeated_row_id)
        yield from second_declared

    quarters[1] = with_declared_accessions(
        second,
        second_declared,
        second_accessions(),
        (_source(second_form4, "2006Q2"),),
    )
    with pytest.raises(CanonicalIb2SourceManifestError):
        _build(quarters)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "extra", "cross_quarter"])
def test_form4_requires_exactly_one_matched_source_pair(mutation):
    quarters = list(_quarters())
    item = quarters[7]
    if mutation == "missing":
        sources = ()
    elif mutation == "duplicate":
        sources = (item.sources[0], item.sources[0])
    elif mutation == "extra":
        sources = (item.sources[0], _source(_accession("2007Q4", 99, "4"), "2007Q4"))
    else:
        sources = (quarters[8].sources[0],)
    quarters[7] = replace(item, sources=sources)
    with pytest.raises(CanonicalIb2SourceManifestError):
        _build(quarters)


def test_form4_amendment_is_also_covered_by_exact_source_pair():
    quarters = list(_quarters())
    item = _quarter("2006Q1", document_types=("4", "4/A", "3"))
    quarters[0] = item
    assert len(_build(quarters).quarters) == 82
    quarters[0] = replace(item, sources=item.sources[:1])
    with pytest.raises(CanonicalIb2SourceManifestError):
        _build(quarters)


@pytest.mark.parametrize("bad", ["digest", "size", "type", "oversize"])
def test_artifact_stream_refuses_corrupt_or_unbounded_input(bad):
    payload = b"synthetic metadata"
    chunks = (payload,)
    sha256 = hash_bytes(payload)
    size = len(payload)
    if bad == "digest":
        sha256 = "0" * 64
    elif bad == "size":
        size += 1
    elif bad == "type":
        chunks = ("not bytes",)
    elif bad == "oversize":
        chunks = (b"x" * (1024 * 1024 + 1),)
    with pytest.raises(CanonicalIb2SourceManifestError):
        verify_artifact_chunks(chunks, sha256=sha256, size_bytes=size)


def test_zero_length_chunk_refuses_even_when_final_digest_and_size_match():
    with pytest.raises(CanonicalIb2SourceManifestError, match="chunk"):
        verify_artifact_chunks(
            (b"", b"x"),
            sha256=hash_bytes(b"x"),
            size_bytes=1,
        )


@pytest.mark.parametrize("kind", ["acceptance_metadata", "primary_ownership_xml"])
def test_required_source_artifacts_must_be_nonempty(kind):
    quarters = list(_quarters())
    item = quarters[0]
    source = item.sources[0]
    empty = _stream(b"", chunks=())
    quarters[0] = replace(item, sources=(replace(source, **{kind: empty}),))
    with pytest.raises(CanonicalIb2SourceManifestError):
        _build(quarters)


@pytest.mark.parametrize("kind", ["acceptance_metadata", "primary_ownership_xml"])
def test_required_source_artifacts_cannot_be_omitted_individually(kind):
    quarters = list(_quarters())
    item = quarters[0]
    quarters[0] = replace(item, sources=(replace(item.sources[0], **{kind: None}),))
    with pytest.raises(CanonicalIb2SourceManifestError):
        _build(quarters)


def test_declared_source_artifact_above_64_mib_refuses_without_allocation():
    quarters = list(_quarters())
    item = quarters[0]
    source = item.sources[0]
    oversized = replace(
        source.acceptance_metadata,
        size_bytes=64 * 1024 * 1024 + 1,
    )
    quarters[0] = replace(
        item, sources=(replace(source, acceptance_metadata=oversized),)
    )
    with pytest.raises(CanonicalIb2SourceManifestError):
        _build(quarters)

    class Unreadable:
        def __iter__(self):
            raise AssertionError("oversized artifact must be rejected before reading")

    with pytest.raises(CanonicalIb2SourceManifestError):
        verify_artifact_chunks(
            Unreadable(),
            sha256="0" * 64,
            size_bytes=64 * 1024 * 1024 + 1,
        )


@pytest.mark.parametrize("kind", ["acceptance_metadata", "primary_ownership_xml"])
@pytest.mark.parametrize("field", ["source_url", "retrieved_at_utc"])
def test_source_provenance_is_bound_into_manifest_identity(kind, field):
    baseline = _build().manifest_sha256
    quarters = list(_quarters())
    item = quarters[0]
    source = item.sources[0]
    updated = replace(
        getattr(source, kind),
        **{
            field: (
                _ARTIFACT_URL.replace("/x.xml", "/y.xml")
                if field == "source_url"
                else "2026-09-25T00:00:01+00:00"
            )
        },
    )
    quarters[0] = replace(item, sources=(replace(source, **{kind: updated}),))
    assert _build(quarters).manifest_sha256 != baseline


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("source_url", "http://www.sec.gov/Archives/edgar/data/1/x.xml"),
        ("source_url", "https://example.com/Archives/edgar/data/1/x.xml"),
        ("retrieved_at_utc", "2026-09-25T00:00:00"),
        ("retrieved_at_utc", "not-a-time"),
    ],
)
@pytest.mark.parametrize("kind", ["acceptance_metadata", "primary_ownership_xml"])
def test_malformed_source_provenance_refuses(kind, field, invalid):
    quarters = list(_quarters())
    item = quarters[0]
    source = item.sources[0]
    updated = replace(getattr(source, kind), **{field: invalid})
    quarters[0] = replace(item, sources=(replace(source, **{kind: updated}),))
    with pytest.raises(CanonicalIb2SourceManifestError):
        _build(quarters)


@pytest.mark.parametrize(
    ("field", "forged"),
    [
        ("source_url", "https://example.com/Archives/edgar/data/1/x.xml"),
        ("retrieved_at_utc", "2026-09-25T00:00:00"),
    ],
)
def test_source_provenance_mutated_while_streaming_refuses(field, forged):
    quarters = list(_quarters())
    item = quarters[0]
    source = item.sources[0]
    stream = replace(source.acceptance_metadata, chunks=())
    payload = f"metadata:2006Q1:{item.accessions[0].accession_number}".encode("ascii")

    def mutating_chunks():
        # A frozen dataclass does not stop a hostile caller-held generator from
        # rebinding the object after the builder's initial provenance check.
        object.__setattr__(stream, field, forged)
        yield payload

    object.__setattr__(stream, "chunks", mutating_chunks())
    quarters[0] = replace(
        item,
        sources=(replace(source, acceptance_metadata=stream),),
    )
    with pytest.raises(CanonicalIb2SourceManifestError):
        _build(quarters)


def test_raw_archive_digest_mutated_while_streaming_refuses():
    quarters = list(_quarters())
    item = quarters[0]
    source = item.sources[0]
    payload = f"metadata:2006Q1:{item.accessions[0].accession_number}".encode("ascii")

    def mutating_chunks():
        # The IB-1A identity is correct at the initial parent check. Its
        # caller-held object must not be trusted again after this yield.
        object.__setattr__(item.raw, "archive_sha256", "0" * 64)
        yield payload

    stream = replace(source.acceptance_metadata, chunks=mutating_chunks())
    quarters[0] = replace(
        item, sources=(replace(source, acceptance_metadata=stream),)
    )
    with pytest.raises(CanonicalIb2SourceManifestError):
        _build(quarters)


@pytest.mark.parametrize("field", ["raw_archive_sha256", "schema_profile_hash"])
def test_later_quarter_stream_mutating_earlier_parsed_identity_refuses(field):
    quarters = list(_quarters())
    earlier = quarters[0]
    later = quarters[40]
    source = later.sources[0]
    period = f"{later.raw.year:04d}Q{later.raw.quarter}"
    payload = f"metadata:{period}:{later.accessions[0].accession_number}".encode(
        "ascii"
    )

    def mutating_chunks():
        # The first quarter was checked before this much later source runs.
        object.__setattr__(earlier.parsed, field, "0" * 64)
        yield payload

    stream = replace(source.acceptance_metadata, chunks=mutating_chunks())
    quarters[40] = replace(
        later, sources=(replace(source, acceptance_metadata=stream),)
    )
    with pytest.raises(CanonicalIb2SourceManifestError, match="changed|parsed"):
        _build(quarters)


def test_owner_policy_mutated_while_streaming_refuses():
    policy = CanonicalIb2SourcePolicy()
    quarters = list(_quarters())
    item = quarters[0]
    source = item.sources[0]
    payload = f"metadata:2006Q1:{item.accessions[0].accession_number}".encode("ascii")

    def mutating_chunks():
        # The builder checked the policy hash before iterating this source.
        object.__setattr__(policy, "required_periods", policy.required_periods[:-1])
        yield payload

    stream = replace(source.acceptance_metadata, chunks=mutating_chunks())
    quarters[0] = replace(
        item, sources=(replace(source, acceptance_metadata=stream),)
    )
    with pytest.raises(CanonicalIb2SourceManifestError):
        _build(quarters, policy=policy)


def test_data_sec_gov_metadata_provenance_is_accepted_but_changes_identity():
    baseline = _build().manifest_sha256
    quarters = list(_quarters())
    item = quarters[0]
    source = item.sources[0]
    metadata = replace(
        source.acceptance_metadata,
        source_url=(
            "https://data.sec.gov/submissions/0000123456/"
            f"{item.accessions[0].accession_number.replace('-', '')}/metadata.json"
        ),
    )
    quarters[0] = replace(
        item, sources=(replace(source, acceptance_metadata=metadata),)
    )
    assert _build(quarters).manifest_sha256 != baseline


@pytest.mark.parametrize("kind", ["acceptance_metadata", "primary_ownership_xml"])
def test_sec_source_url_for_another_accession_refuses(kind):
    quarters = list(_quarters())
    item = quarters[0]
    source = item.sources[0]
    foreign = quarters[1].accessions[0].accession_number.replace("-", "")
    wrong_url = (
        "https://www.sec.gov/Archives/edgar/data/123456/"
        f"{foreign}/x.xml"
    )
    changed = replace(getattr(source, kind), source_url=wrong_url)
    quarters[0] = replace(item, sources=(replace(source, **{kind: changed}),))
    with pytest.raises(CanonicalIb2SourceManifestError, match="URL|accession"):
        _build(quarters)


@pytest.mark.parametrize("foreign_format", ["compact", "dashed"])
def test_metadata_url_with_correct_and_foreign_accession_segments_refuses(
    foreign_format,
):
    quarters = list(_quarters())
    item = quarters[0]
    source = item.sources[0]
    correct = item.accessions[0].accession_number.replace("-", "")
    foreign = quarters[1].accessions[0].accession_number
    if foreign_format == "compact":
        foreign = foreign.replace("-", "")
    ambiguous_url = (
        f"https://data.sec.gov/submissions/{correct}/{foreign}/metadata.json"
    )
    changed = replace(source.acceptance_metadata, source_url=ambiguous_url)
    quarters[0] = replace(
        item, sources=(replace(source, acceptance_metadata=changed),)
    )
    with pytest.raises(CanonicalIb2SourceManifestError, match="URL|accession"):
        _build(quarters)


def test_sec_source_url_above_ib1c_8kib_cap_refuses():
    quarters = list(_quarters())
    item = quarters[0]
    source = item.sources[0]
    accession = item.accessions[0].accession_number.replace("-", "")
    long_url = (
        "https://www.sec.gov/Archives/edgar/data/123456/"
        f"{accession}/{'x' * 8200}.xml"
    )
    assert len(long_url) > 8 * 1024
    changed = replace(source.primary_ownership_xml, source_url=long_url)
    quarters[0] = replace(
        item, sources=(replace(source, primary_ownership_xml=changed),)
    )
    with pytest.raises(CanonicalIb2SourceManifestError, match="URL"):
        _build(quarters)


@pytest.mark.parametrize(
    "wrong_url_kind", ["data_sec_gov", "wrong_archives_position"]
)
def test_primary_xml_requires_exact_www_sec_archives_position(wrong_url_kind):
    quarters = list(_quarters())
    item = quarters[0]
    source = item.sources[0]
    accession = item.accessions[0].accession_number.replace("-", "")
    if wrong_url_kind == "data_sec_gov":
        wrong_url = (
            "https://data.sec.gov/submissions/0000123456/"
            f"{accession}/x.xml"
        )
    else:
        wrong_url = (
            "https://www.sec.gov/Archives/edgar/data/123456/extra/"
            f"{accession}/x.xml"
        )
    # Both satisfy the generic SEC-host and exact-accession-segment checks.
    changed = replace(source.primary_ownership_xml, source_url=wrong_url)
    quarters[0] = replace(
        item, sources=(replace(source, primary_ownership_xml=changed),)
    )
    with pytest.raises(CanonicalIb2SourceManifestError, match="primary XML"):
        _build(quarters)


class _OneShot:
    def __init__(self, items):
        self.items = tuple(items)
        self.calls = 0

    def __iter__(self):
        self.calls += 1
        if self.calls != 1:
            raise AssertionError("stream was iterated more than once")
        return iter(self.items)


def test_artifact_stream_is_one_pass_and_chunk_boundary_invariant():
    payload = b"synthetic metadata with multiple chunks"
    once = _OneShot((payload[:10], payload[10:]))
    receipt = verify_artifact_chunks(
        once,
        sha256=hash_bytes(payload),
        size_bytes=len(payload),
    )
    whole = verify_artifact_chunks(
        (payload,), sha256=hash_bytes(payload), size_bytes=len(payload)
    )
    assert receipt == whole
    assert once.calls == 1

    quarters_a = list(_quarters())
    quarters_b = list(_quarters())
    item = quarters_b[2]
    source = item.sources[0]
    original = b"metadata:2006Q3:" + item.accessions[0].accession_number.encode("ascii")
    assert source.acceptance_metadata.sha256 == hash_bytes(original)
    source = replace(
        source,
        acceptance_metadata=replace(
            source.acceptance_metadata,
            chunks=(original[:7], original[7:]),
        ),
    )
    quarters_b[2] = replace(item, sources=(source,))
    assert _build(quarters_a).manifest_sha256 == _build(quarters_b).manifest_sha256


def test_builder_consumes_quarter_iterable_once():
    quarters = _OneShot(_quarters())
    assert len(_build(quarters).quarters) == 82
    assert quarters.calls == 1


def test_builder_consumes_accession_and_source_iterables_once():
    quarters = list(_quarters())
    item = quarters[0]
    accessions = _OneShot(item.accessions)
    sources = _OneShot(item.sources)
    quarters[0] = replace(item, accessions=accessions, sources=sources)
    assert len(_build(quarters).quarters) == 82
    assert accessions.calls == sources.calls == 1


def test_heap_lookahead_does_not_retain_full_serialized_accession_bytes():
    item = _quarter("2006Q1")
    large = replace(
        item.accessions[0],
        table_rows=(
            (
                "NONDERIV_TRANS.tsv",
                tuple(f"{index:064x}" for index in range(3_500)),
            ),
        ),
    )
    accessions = (large, item.accessions[1])
    accession_bytes = b"".join(
        (canonical_json(accession.to_payload()) + "\n").encode("utf-8")
        for accession in accessions
    )
    assert len(accession_bytes) > 200_000
    artifacts = tuple(
        _artifact("accessions.jsonl", accession_bytes, len(accessions))
        if artifact.name == "accessions.jsonl"
        else artifact
        for artifact in item.parsed.artifacts
    )
    item = replace(
        item,
        parsed=_relineage_parsed(replace(item.parsed, artifacts=artifacts)),
        accessions=accessions,
    )
    cursor = manifest_module._quarter_cursor(item, expected_period="2006Q1")
    assert manifest_module._advance_cursor(cursor) == large.accession_number
    retained_bytes = {
        field.name: len(value)
        for field in fields(cursor)
        if isinstance(value := getattr(cursor, field.name), bytes)
    }
    retained_accessions = {
        field.name
        for field in fields(cursor)
        if isinstance(getattr(cursor, field.name), ParsedSecBulkAccession)
    }
    # Caller-owned iterators may retain input rows. The merge cursor must not
    # add 82 full JSONL byte images or live row references of its own.
    assert all(size <= 64 for size in retained_bytes.values()), retained_bytes
    assert not retained_accessions, retained_accessions


def test_manifest_construction_has_no_filesystem_or_network_side_effect(monkeypatch):
    import builtins
    import socket
    from pathlib import Path

    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected I/O")

    quarters = _quarters()
    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(Path, "open", forbidden)
        patch.setattr(socket, "socket", forbidden)
        manifest = _build(quarters)
    assert len(manifest.quarters) == 82
    assert CanonicalIb2SourcePolicy().authorized_outcome_looks == 0
    assert CanonicalIb2SourcePolicy().consumed_outcome_looks == 0


def test_document_type_outside_the_sec_domain_refuses_before_source_pairing():
    # The whitelist is the only guard that names the accepted forms; without
    # it an unknown type would fall through to Form 4 source pairing and be
    # refused, if at all, only by the artifact digest.
    quarters = list(_quarters())
    item = quarters[0]
    accessions = (replace(item.accessions[0], document_type="8-K"), item.accessions[1])
    quarters[0] = replace(item, accessions=accessions)
    with pytest.raises(CanonicalIb2SourceManifestError, match="unapproved document type"):
        _build(quarters)


def test_unordered_accessions_within_a_quarter_refuse():
    quarters = list(_quarters())
    item = _quarter("2006Q1", document_types=("3", "4"))
    quarters[0] = replace(item, accessions=(item.accessions[1], item.accessions[0]))
    with pytest.raises(CanonicalIb2SourceManifestError, match="unordered"):
        _build(quarters)


def test_single_chunk_above_1_mib_refuses_even_with_a_matching_receipt():
    # The existing oversize case also breaks the declared size, so it never
    # reaches the chunk cap that bounds how much input is held at once.
    payload = b"x" * (1024 * 1024 + 1)
    with pytest.raises(CanonicalIb2SourceManifestError, match="bounded exact bytes"):
        verify_artifact_chunks(
            (payload,), sha256=hash_bytes(payload), size_bytes=len(payload)
        )


def test_stream_overflow_refuses_before_requesting_another_chunk():
    def chunks():
        yield b"xx"
        raise AssertionError("a chunk was requested after the declared size was exceeded")

    with pytest.raises(
        CanonicalIb2SourceManifestError, match="exceeds its declared byte size"
    ):
        verify_artifact_chunks(chunks(), sha256=hash_bytes(b"x"), size_bytes=1)


def test_metadata_url_above_8_kib_refuses_without_a_filename_cap():
    # The primary XML filename is capped at 255 characters by its own regex;
    # a metadata URL has only the 8 KiB cap between it and the manifest.
    quarters = list(_quarters())
    item = quarters[0]
    source = item.sources[0]
    accession = item.accessions[0].accession_number.replace("-", "")
    long_url = (
        "https://data.sec.gov/submissions/"
        + "/".join(["segment"] * 1200)
        + f"/{accession}/metadata.json"
    )
    assert len(long_url) > 8 * 1024
    changed = replace(source.acceptance_metadata, source_url=long_url)
    quarters[0] = replace(
        item, sources=(replace(source, acceptance_metadata=changed),)
    )
    with pytest.raises(CanonicalIb2SourceManifestError, match="URL is not canonical"):
        _build(quarters)


def test_raw_lineage_hash_must_recompute_even_when_the_parent_binding_agrees():
    # A forged raw lineage hash that the parsed parent fields also carry
    # passes every binding check; only the recomputation from the raw
    # payload exposes it.
    quarters = list(_quarters())
    item = quarters[3]
    forged = "1" * 64
    raw = replace(item.raw, lineage_hash=forged)
    raw_manifest_sha256 = hash_bytes(
        (canonical_json(raw.to_payload()) + "\n").encode("utf-8")
    )
    parsed = _relineage_parsed(
        replace(
            item.parsed,
            raw_lineage_hash=forged,
            raw_manifest_sha256=raw_manifest_sha256,
        )
    )
    quarters[3] = replace(item, raw=raw, parsed=parsed)
    with pytest.raises(CanonicalIb2SourceManifestError, match="raw snapshot lineage"):
        _build(quarters)


def test_schema_profile_hash_must_match_the_profile_even_when_relineaged():
    quarters = list(_quarters())
    item = quarters[4]
    parsed = _relineage_parsed(replace(item.parsed, schema_profile_hash="2" * 64))
    quarters[4] = replace(item, parsed=parsed)
    with pytest.raises(CanonicalIb2SourceManifestError, match="schema profile hash"):
        _build(quarters)


def test_direct_manifest_construction_refuses_reordered_quarters():
    manifest = _build()
    quarters = list(manifest.quarters)
    quarters[0], quarters[1] = quarters[1], quarters[0]
    payload = {
        "kind": manifest_module.CANONICAL_IB2_SOURCE_MANIFEST_KIND,
        "version": manifest_module.CANONICAL_IB2_SOURCE_MANIFEST_VERSION,
        "policy_sha256": manifest.policy_sha256,
        "quarters": [quarter.to_payload() for quarter in quarters],
    }
    with pytest.raises(CanonicalIb2SourceManifestError, match="quarter inventory"):
        CanonicalIb2SourceManifest(
            policy_sha256=manifest.policy_sha256,
            quarters=tuple(quarters),
            manifest_sha256=hash_payload(payload),
        )


@pytest.mark.parametrize(
    "context_form,policy_factory",
    [("3", CanonicalIb2SourcePolicy), ("3/A", CanonicalIb2SourcePolicyV2),
     ("5/A", CanonicalIb2SourcePolicyV2)],
)
def test_builder_accepts_a_quarter_produced_by_the_ib1a_and_ib1b_loaders(
    tmp_path, context_form, policy_factory
):
    # Every other quarter in this file is an identity built by hand. This pins
    # that identities and accession rows produced by the real IB-1A/IB-1B
    # publish-and-load path satisfy the builder's recomputed lineage, parent,
    # profile, ordering, and JSONL digest checks.
    accession_form4 = "0000123456-06-000101"
    accession_form3 = "0000123456-06-000102"

    def tsv(headers, rows):
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(headers)
        writer.writerows(rows)
        return stream.getvalue().encode("utf-8")

    submission, owner, transaction = _PROFILE.variants
    tables = {
        "SUBMISSION.tsv": tsv(
            submission.headers,
            (
                (accession_form4, "2006-01-15", "2006-01-10", "4", "0000123456", "Synthetic Issuer", "SYN"),
                (accession_form3, "2006-01-16", "2006-01-10", context_form, "0000123456", "Synthetic Issuer", "SYN"),
            ),
        ),
        "REPORTINGOWNER.tsv": tsv(
            owner.headers, ((accession_form4, "0000000042"), (accession_form3, "0000000042"))
        ),
        "NONDERIV_TRANS.tsv": tsv(transaction.headers, ((accession_form4, "0000007"),)),
    }
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zipped:
        for name, data in tables.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 8, 20, 18, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100600 << 16
            zipped.writestr(info, data)
    source = SecBulkSource(
        year=2006,
        quarter=1,
        source_url=(
            "https://www.sec.gov/files/dera/data/insider-transactions-data-sets/"
            "2006q1_form345.zip"
        ),
        git_commit=_CAPTURE_COMMIT,
        retrieved_at=datetime(2026, 8, 20, 18, 0, tzinfo=timezone.utc),
    )
    raw = write_sec_bulk_snapshot(archive.getvalue(), source, tmp_path / "raw")
    raw_directory = tmp_path / "raw" / raw.snapshot_id
    parsed = build_sec_bulk_parsed_snapshot(
        raw_directory,
        tmp_path / "parsed",
        schema_profile=_PROFILE,
        parser_git_commit=_PARSER_COMMIT,
    )
    loaded_raw = load_sec_bulk_snapshot(raw_directory)
    loaded_parsed = load_sec_bulk_parsed_snapshot(
        tmp_path / "parsed" / parsed.snapshot_id,
        raw_snapshot_directory=raw_directory,
    )
    assert [
        (item.accession_number, item.document_type) for item in loaded_parsed.accessions
    ] == [(accession_form4, "4"), (accession_form3, context_form)]

    quarters = list(_quarters())
    quarters[0] = CanonicalIb2QuarterInput(
        raw=loaded_raw.identity,
        parsed=loaded_parsed.identity,
        accessions=loaded_parsed.accessions,
        sources=tuple(
            _source(item, "2006Q1")
            for item in loaded_parsed.accessions
            if item.document_type in {"4", "4/A"}
        ),
    )
    summary = _build(quarters, policy=policy_factory()).quarters[0].to_payload()
    assert summary["raw_snapshot_id"] == raw.snapshot_id
    assert summary["parsed_snapshot_id"] == parsed.snapshot_id
    assert (summary["form4_accession_count"], summary["context_accession_count"]) == (1, 1)


def test_direct_manifest_construction_refuses_a_foreign_policy_hash():
    # The builder checks the policy itself, so only direct construction can
    # present a policy hash that is neither pinned literal. The version
    # resolver must refuse it rather than default to a version.
    manifest = _build()
    foreign = "0" * 64
    payload = {
        "kind": manifest_module.CANONICAL_IB2_SOURCE_MANIFEST_KIND,
        "version": manifest_module.CANONICAL_IB2_SOURCE_MANIFEST_VERSION,
        "policy_sha256": foreign,
        "quarters": [quarter.to_payload() for quarter in manifest.quarters],
    }
    with pytest.raises(
        CanonicalIb2SourceManifestError, match="policy or quarter inventory"
    ):
        CanonicalIb2SourceManifest(
            policy_sha256=foreign,
            quarters=manifest.quarters,
            manifest_sha256=hash_payload(payload),
        )


def test_policy_class_swapped_mid_stream_is_refused():
    # A hostile caller-held generator can rebind __class__ on a frozen
    # instance to a same-layout subclass. The payload and digest do not
    # change, so only the final exact-type recheck can see it.
    class SwappedPolicy(CanonicalIb2SourcePolicyV2):
        pass

    policy = CanonicalIb2SourcePolicyV2()
    quarters = list(_quarters())
    item = quarters[-1]
    source = item.sources[0]
    payload = tuple(source.acceptance_metadata.chunks)

    def chunks():
        object.__setattr__(policy, "__class__", SwappedPolicy)
        yield from payload

    quarters[-1] = replace(
        item,
        sources=(
            replace(
                source,
                acceptance_metadata=replace(source.acceptance_metadata, chunks=chunks()),
            ),
        ),
    )
    with pytest.raises(CanonicalIb2SourceManifestError, match="changed while streaming"):
        _build(quarters, policy=policy)
    assert type(policy) is SwappedPolicy
    assert policy.semantic_sha256 == CANONICAL_IB2_SOURCE_POLICY_V2_SHA256
