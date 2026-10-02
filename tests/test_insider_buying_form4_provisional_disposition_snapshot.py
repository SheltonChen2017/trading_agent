"""IB-1H immutable provisional-disposition snapshot tests.

Every byte is synthetic.  Persistence proves only deterministic reconstruction
against exact supplied IB-1E evidence; it grants no official, canonical,
security-mapping, aggregation, outcome, QuantConnect, or trading authority.
"""
from __future__ import annotations

import ast
import copy
import json
import os
import shutil
from dataclasses import dataclass, fields, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying import (
    ClassificationOutcome,
    Form4ProvisionalDisposition,
    Form4ProvisionalDispositionReport,
    Form4ProvisionalDispositionReportError,
    Form4ProvisionalDispositionReportIdentity,
    Form4ProvisionalDispositionRow,
    Form4ProvisionalDispositionSnapshotError,
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
    build_form4_provisional_disposition_report,
    load_form4_provisional_disposition_snapshot,
    write_form4_provisional_disposition_snapshot,
)
from research.insider_buying import (
    form4_multi_period_amendment_evidence as evidence_module,
)
from research.insider_buying import (
    form4_provisional_disposition_snapshot as snapshot_module,
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
        profile_id="synthetic-non-official-ib1h-metadata-v1",
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
        metadata_bytes=(canonical_json(metadata_payload) + "\n").encode("utf-8"),
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
    records_hash = hash_payload([record.to_payload()])
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
        records_hash=records_hash,
        lineage_hash=lineage_hash,
        snapshot_id=(
            f"sec-edgar-acceptance-{year:04d}q{quarter}-{lineage_hash[:16]}"
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
        profile_id="synthetic-non-official-ib1h-link-v1",
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
    return assemble_sec_form4_multi_period_evidence(
        (_period(2026, 4), _period(2027, 1)),
        sources=(_xml_source(original), _xml_source(amendment)),
        evidence_profile=_evidence_profile(profile),
        parser_git_commit=PARSER_COMMIT,
    )


@pytest.fixture
def evidence(monkeypatch) -> ProfileBoundForm4AmendmentEvidence:
    return _build_evidence(monkeypatch)


@pytest.fixture
def report(evidence) -> Form4ProvisionalDispositionReport:
    return build_form4_provisional_disposition_report(
        evidence,
        builder_git_commit=BUILDER_COMMIT,
    )


def _bundle(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_bundle(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((canonical_json(payload) + "\n").encode("utf-8"))


def _rehash_readdress_bundle(payload: dict[str, object]) -> str:
    """Make all public report hashes/IDs coherent after a hostile mutation."""

    report_payload = payload["report"]
    identity = report_payload["identity"]
    rows = report_payload["rows"]
    for row in rows:
        row_lineage = dict(row)
        row_lineage.pop("row_id", None)
        row["row_id"] = hash_payload(row_lineage)
    identity["transaction_count"] = len(rows)
    identity["candidate_count"] = sum(
        row["disposition"]
        == "provisional_pre_aggregation_candidate"
        for row in rows
    )
    identity["quarantine_count"] = (
        len(rows) - identity["candidate_count"]
    )
    identity["row_inventory_hash"] = hash_payload(rows)
    identity_lineage = dict(identity)
    identity_lineage.pop("report_id", None)
    identity["report_id"] = (
        "form4-provisional-disposition-report-"
        f"{hash_payload(identity_lineage)[:16]}"
    )
    payload["report_payload_sha256"] = hash_bytes(
        canonical_json(report_payload).encode("utf-8")
    )
    return identity["report_id"]


def _simulate_redirect_status(monkeypatch, component: Path) -> None:
    """Mark one real component as a redirect without OS symlink privilege."""

    component_status = component.lstat()
    component_identity = (component_status.st_dev, component_status.st_ino)
    real_status_is_redirect = snapshot_module._status_is_redirect

    def status_is_redirect(value):
        return (
            (value.st_dev, value.st_ino) == component_identity
            or real_status_is_redirect(value)
        )

    monkeypatch.setattr(
        snapshot_module,
        "_status_is_redirect",
        status_is_redirect,
    )


def test_snapshot_round_trip_is_deterministic_idempotent_and_non_authoritative(
    tmp_path,
    evidence,
    report,
):
    target = write_form4_provisional_disposition_snapshot(report, tmp_path)
    original_bytes = target.read_bytes()

    assert target.name == f"{report.identity.report_id}.json"
    assert write_form4_provisional_disposition_snapshot(report, tmp_path) == target
    assert target.read_bytes() == original_bytes
    assert original_bytes.endswith(b"\n")

    loaded = load_form4_provisional_disposition_snapshot(
        target,
        evidence=evidence,
    )
    assert loaded == report
    assert loaded.official_profile_compatibility_verified is False
    assert loaded.official_amendment_link_verified is False
    assert loaded.complete_amendment_coverage_verified is False
    assert loaded.point_in_time_security_identity_verified is False
    assert loaded.canonical_filter_authorized is False
    assert loaded.lot_aggregation_authorized is False
    assert loaded.outcomes_authorized is False
    assert loaded.authorized_outcome_looks == 0

    payload = _bundle(target)
    assert payload["report"] == report.to_payload()
    assert payload["kind"] == (
        snapshot_module.FORM4_PROVISIONAL_DISPOSITION_SNAPSHOT_KIND
    )
    assert payload["report_payload_sha256"] == hash_bytes(
        canonical_json(payload["report"]).encode("utf-8")
    )


def test_writer_refuses_non_report_type_and_different_immutable_content(
    tmp_path,
    report,
):
    with pytest.raises(
        Form4ProvisionalDispositionSnapshotError,
        match="exact-type report",
    ):
        write_form4_provisional_disposition_snapshot(object(), tmp_path)

    target = write_form4_provisional_disposition_snapshot(report, tmp_path)
    target.write_bytes(b"different immutable content")
    with pytest.raises(
        Form4ProvisionalDispositionSnapshotError,
        match="conflicts",
    ):
        write_form4_provisional_disposition_snapshot(report, tmp_path)


def test_loader_requires_exact_evidence_type_before_file_access(tmp_path):
    missing = tmp_path / (
        "form4-provisional-disposition-report-0000000000000000.json"
    )
    with pytest.raises(
        Form4ProvisionalDispositionSnapshotError,
        match="exact profile-bound evidence",
    ):
        load_form4_provisional_disposition_snapshot(missing, evidence=object())


def test_loader_rebuilds_and_refuses_coherent_alternate_upstream(
    tmp_path,
    monkeypatch,
    evidence,
    report,
):
    target = write_form4_provisional_disposition_snapshot(report, tmp_path)
    original_xml = (FIXTURES / "form4_original.xml").read_bytes()
    assert b"5000" in original_xml
    alternate = _build_evidence(
        monkeypatch,
        original_xml=original_xml.replace(b"5000", b"5001", 1),
    )

    with pytest.raises(
        Form4ProvisionalDispositionSnapshotError,
        match="rebuilt upstream evidence",
    ):
        load_form4_provisional_disposition_snapshot(target, evidence=alternate)


def test_loader_refuses_fully_coherent_forged_row_against_unchanged_evidence(
    tmp_path,
    monkeypatch,
    evidence,
    report,
):
    source = write_form4_provisional_disposition_snapshot(
        report, tmp_path / "source"
    )
    payload = copy.deepcopy(_bundle(source))
    forged_row = payload["report"]["rows"][0]
    forged_row["shares"] = "999999"
    forged_row["transaction_payload_hash"] = hash_payload(
        {
            "forged_transaction": forged_row["event_id"],
            "shares": forged_row["shares"],
        }
    )
    forged_report_id = _rehash_readdress_bundle(payload)
    target = tmp_path / "forged" / f"{forged_report_id}.json"
    _write_bundle(target, payload)

    real_builder = snapshot_module.build_form4_provisional_disposition_report
    builder_calls = 0

    def counted_builder(*args, **kwargs):
        nonlocal builder_calls
        builder_calls += 1
        return real_builder(*args, **kwargs)

    monkeypatch.setattr(
        snapshot_module,
        "build_form4_provisional_disposition_report",
        counted_builder,
    )
    with pytest.raises(
        Form4ProvisionalDispositionSnapshotError,
        match="rebuilt upstream evidence",
    ):
        load_form4_provisional_disposition_snapshot(target, evidence=evidence)
    assert builder_calls == 1


def test_mixed_eligible_and_quarantine_refuses_before_upstream_builder(
    tmp_path,
    monkeypatch,
    evidence,
    report,
):
    source = write_form4_provisional_disposition_snapshot(
        report, tmp_path / "source"
    )
    payload = copy.deepcopy(_bundle(source))
    candidate = next(
        row
        for row in payload["report"]["rows"]
        if row["disposition"] == "provisional_pre_aggregation_candidate"
    )
    candidate["outcomes"] = [
        ClassificationOutcome.ELIGIBLE_FOR_LOT_AGGREGATION.value,
        ClassificationOutcome.EXCLUDE_PRICE_RANGE.value,
    ]
    candidate["disposition"] = "provisional_quarantine"
    forged_report_id = _rehash_readdress_bundle(payload)
    target = tmp_path / "mixed" / f"{forged_report_id}.json"
    _write_bundle(target, payload)
    monkeypatch.setattr(
        snapshot_module,
        "build_form4_provisional_disposition_report",
        lambda *_args, **_kwargs: pytest.fail("upstream builder was reached"),
    )

    with pytest.raises(
        Form4ProvisionalDispositionSnapshotError,
        match="row routing is inconsistent",
    ):
        load_form4_provisional_disposition_snapshot(target, evidence=evidence)


@pytest.mark.parametrize(
    "mutation",
    [
        "authority",
        "drop_row",
        "reverse_rows",
        "row_value",
        "unknown_row_field",
        "builder_commit",
    ],
)
def test_loader_refuses_canonical_tampering(
    tmp_path,
    evidence,
    report,
    mutation,
):
    source = write_form4_provisional_disposition_snapshot(
        report, tmp_path / "source"
    )
    payload = _bundle(source)
    identity = payload["report"]["identity"]
    rows = payload["report"]["rows"]
    if mutation == "authority":
        identity["canonical_filter_authorized"] = True
    elif mutation == "drop_row":
        rows.pop()
    elif mutation == "reverse_rows":
        rows.reverse()
    elif mutation == "row_value":
        rows[0]["shares"] = "999999"
    elif mutation == "unknown_row_field":
        rows[0]["future_unbound_field"] = "escaped"
    elif mutation == "builder_commit":
        identity["builder_git_commit"] = "0" * 40
    else:  # pragma: no cover - parameter list is closed.
        raise AssertionError(mutation)
    payload["report_payload_sha256"] = hash_bytes(
        canonical_json(payload["report"]).encode("utf-8")
    )
    target = tmp_path / mutation / source.name
    _write_bundle(target, payload)

    with pytest.raises(Form4ProvisionalDispositionSnapshotError):
        load_form4_provisional_disposition_snapshot(target, evidence=evidence)


def test_parser_refuses_wrong_declared_report_hash(report):
    report_payload = report.to_payload()
    payload = {
        "kind": snapshot_module.FORM4_PROVISIONAL_DISPOSITION_SNAPSHOT_KIND,
        "snapshot_contract_version": (
            snapshot_module.FORM4_PROVISIONAL_DISPOSITION_SNAPSHOT_VERSION
        ),
        "report_payload_sha256": "0" * 64,
        "report": report_payload,
    }
    raw = (canonical_json(payload) + "\n").encode("utf-8")

    with pytest.raises(
        Form4ProvisionalDispositionSnapshotError,
        match="report hash is invalid",
    ):
        snapshot_module._parse_snapshot_bytes(
            raw,
            expected_report_id=report.identity.report_id,
        )


@pytest.mark.parametrize("value", ["NaN", "Infinity", "01", "+1", "1e3"])
def test_parser_refuses_nonfinite_or_noncanonical_decimal_text(report, value):
    report_payload = report.to_payload()
    payload = {
        "kind": snapshot_module.FORM4_PROVISIONAL_DISPOSITION_SNAPSHOT_KIND,
        "snapshot_contract_version": (
            snapshot_module.FORM4_PROVISIONAL_DISPOSITION_SNAPSHOT_VERSION
        ),
        "report_payload_sha256": "0" * 64,
        "report": report_payload,
    }
    payload["report"]["rows"][0]["shares"] = value
    forged_report_id = _rehash_readdress_bundle(payload)
    raw = (canonical_json(payload) + "\n").encode("utf-8")

    with pytest.raises(
        Form4ProvisionalDispositionSnapshotError,
        match="row decimal",
    ):
        snapshot_module._parse_snapshot_bytes(
            raw,
            expected_report_id=forged_report_id,
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
def test_parser_refuses_every_coherently_readdressed_authority_claim(
    report,
    field_name,
    replacement,
):
    report_payload = report.to_payload()
    payload = {
        "kind": snapshot_module.FORM4_PROVISIONAL_DISPOSITION_SNAPSHOT_KIND,
        "snapshot_contract_version": (
            snapshot_module.FORM4_PROVISIONAL_DISPOSITION_SNAPSHOT_VERSION
        ),
        "report_payload_sha256": "0" * 64,
        "report": report_payload,
    }
    payload["report"]["identity"][field_name] = replacement
    forged_report_id = _rehash_readdress_bundle(payload)
    raw = (canonical_json(payload) + "\n").encode("utf-8")

    with pytest.raises(
        Form4ProvisionalDispositionSnapshotError,
        match="claims authority",
    ):
        snapshot_module._parse_snapshot_bytes(
            raw,
            expected_report_id=forged_report_id,
        )


@pytest.mark.parametrize("mutation", ["reverse", "duplicate"])
def test_parser_refuses_coherently_readdressed_row_order_or_duplicate(
    report,
    mutation,
):
    report_payload = report.to_payload()
    payload = {
        "kind": snapshot_module.FORM4_PROVISIONAL_DISPOSITION_SNAPSHOT_KIND,
        "snapshot_contract_version": (
            snapshot_module.FORM4_PROVISIONAL_DISPOSITION_SNAPSHOT_VERSION
        ),
        "report_payload_sha256": "0" * 64,
        "report": report_payload,
    }
    rows = payload["report"]["rows"]
    if mutation == "reverse":
        rows.reverse()
    else:
        rows.append(copy.deepcopy(rows[0]))
    forged_report_id = _rehash_readdress_bundle(payload)
    raw = (canonical_json(payload) + "\n").encode("utf-8")

    with pytest.raises(
        Form4ProvisionalDispositionSnapshotError,
        match="row inventory is inconsistent",
    ):
        snapshot_module._parse_snapshot_bytes(
            raw,
            expected_report_id=forged_report_id,
        )


def test_json_nesting_refuses_before_json_parser(monkeypatch):
    depth = (
        snapshot_module.MAX_FORM4_PROVISIONAL_DISPOSITION_SNAPSHOT_JSON_DEPTH
        + 1
    )
    raw = ("[" * depth + "]" * depth).encode("ascii")
    monkeypatch.setattr(
        snapshot_module.json,
        "loads",
        lambda *_args, **_kwargs: pytest.fail("json.loads was reached"),
    )

    with pytest.raises(
        Form4ProvisionalDispositionSnapshotError,
        match="nesting exceeds",
    ):
        snapshot_module._parse_snapshot_bytes(
            raw,
            expected_report_id=(
                "form4-provisional-disposition-report-0000000000000000"
            ),
        )


@pytest.mark.parametrize(
    "variant",
    [
        "whitespace",
        "duplicate_key",
        "unknown_field",
        "nan",
        "invalid_utf8",
        "escaped_surrogate",
    ],
)
def test_loader_refuses_noncanonical_or_unsafe_json(
    tmp_path,
    evidence,
    report,
    variant,
):
    source = write_form4_provisional_disposition_snapshot(
        report, tmp_path / "source"
    )
    raw = source.read_bytes()
    if variant == "whitespace":
        raw = raw.replace(b'{"kind"', b'{ "kind"', 1)
    elif variant == "duplicate_key":
        raw = raw.replace(
            b'{"kind":',
            b'{"kind":"duplicate","kind":',
            1,
        )
    elif variant == "unknown_field":
        payload = _bundle(source)
        payload["unknown"] = False
        raw = (canonical_json(payload) + "\n").encode("utf-8")
    elif variant == "nan":
        raw = raw.replace(b'"snapshot_contract_version":1', b'"snapshot_contract_version":NaN', 1)
    elif variant == "invalid_utf8":
        raw = b"\xff" + raw
    elif variant == "escaped_surrogate":
        marker = b'"security_title_raw":"Common Stock"'
        assert marker in raw
        raw = raw.replace(
            marker,
            b'"security_title_raw":"\\ud800"',
            1,
        )
    else:  # pragma: no cover - parameter list is closed.
        raise AssertionError(variant)
    target = tmp_path / variant / source.name
    target.parent.mkdir(parents=True)
    target.write_bytes(raw)

    with pytest.raises(Form4ProvisionalDispositionSnapshotError):
        load_form4_provisional_disposition_snapshot(target, evidence=evidence)


def test_loader_refuses_filename_mismatch(tmp_path, evidence, report):
    source = write_form4_provisional_disposition_snapshot(
        report, tmp_path / "source"
    )
    target = tmp_path / "other" / (
        "form4-provisional-disposition-report-0000000000000000.json"
    )
    target.parent.mkdir()
    shutil.copyfile(source, target)

    with pytest.raises(
        Form4ProvisionalDispositionSnapshotError,
        match="filename",
    ):
        load_form4_provisional_disposition_snapshot(target, evidence=evidence)


def test_loader_refuses_hard_link_alias(tmp_path, evidence, report):
    source = write_form4_provisional_disposition_snapshot(
        report, tmp_path / "source"
    )
    alias = tmp_path / "alias" / source.name
    alias.parent.mkdir()
    os.link(source, alias)

    with pytest.raises(
        Form4ProvisionalDispositionSnapshotError,
        match="single-link regular immutable file",
    ):
        load_form4_provisional_disposition_snapshot(alias, evidence=evidence)


def test_loader_and_writer_refuse_redirects(tmp_path, evidence, report):
    source = write_form4_provisional_disposition_snapshot(
        report, tmp_path / "source"
    )
    real_root = tmp_path / "real-root"
    real_nested = real_root / "nested"
    real_nested.mkdir(parents=True)
    shutil.copyfile(source, real_nested / source.name)
    outer = tmp_path / "outer"
    outer.mkdir()
    redirect = outer / "redirect"
    try:
        redirect.symlink_to(real_root, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink unavailable: {exc}")

    redirected_file = redirect / "nested" / source.name
    with pytest.raises(Form4ProvisionalDispositionSnapshotError, match="redirect"):
        load_form4_provisional_disposition_snapshot(
            redirected_file,
            evidence=evidence,
        )
    with pytest.raises(Form4ProvisionalDispositionSnapshotError, match="redirect"):
        write_form4_provisional_disposition_snapshot(
            report, redirect / "new" / "nested"
        )


def test_writer_refuses_simulated_nested_redirect_before_publish(
    tmp_path,
    monkeypatch,
    report,
):
    outer = tmp_path / "outer"
    outer.mkdir()
    output_root = outer / "new" / "nested"
    _simulate_redirect_status(monkeypatch, outer)
    monkeypatch.setattr(
        snapshot_module,
        "publish_immutable_bytes",
        lambda *_args, **_kwargs: pytest.fail("publisher was reached"),
    )

    with pytest.raises(
        Form4ProvisionalDispositionSnapshotError,
        match="ancestry contains a filesystem redirect",
    ):
        write_form4_provisional_disposition_snapshot(report, output_root)
    assert not output_root.exists()


def test_loader_refuses_simulated_nested_redirect_before_builder(
    tmp_path,
    monkeypatch,
    evidence,
    report,
):
    outer = tmp_path / "outer"
    source = write_form4_provisional_disposition_snapshot(
        report, outer / "snapshots"
    )
    _simulate_redirect_status(monkeypatch, outer)
    monkeypatch.setattr(
        snapshot_module,
        "build_form4_provisional_disposition_report",
        lambda *_args, **_kwargs: pytest.fail("upstream builder was reached"),
    )

    with pytest.raises(
        Form4ProvisionalDispositionSnapshotError,
        match="ancestry contains a filesystem redirect",
    ):
        load_form4_provisional_disposition_snapshot(source, evidence=evidence)


def test_loader_refuses_toctou_version_change(
    tmp_path,
    monkeypatch,
    evidence,
    report,
):
    target = write_form4_provisional_disposition_snapshot(report, tmp_path)
    monkeypatch.setattr(snapshot_module, "_same_file_version", lambda *_args: False)

    with pytest.raises(
        Form4ProvisionalDispositionSnapshotError,
        match="changed while it was read",
    ):
        load_form4_provisional_disposition_snapshot(target, evidence=evidence)


@pytest.mark.parametrize("resource", ["bytes", "depth", "rows"])
def test_resource_caps_refuse_before_upstream_rebuild(
    tmp_path,
    monkeypatch,
    evidence,
    report,
    resource,
):
    source = write_form4_provisional_disposition_snapshot(
        report, tmp_path / "source"
    )
    target = tmp_path / resource / source.name
    target.parent.mkdir()
    if resource == "bytes":
        shutil.copyfile(source, target)
        monkeypatch.setattr(
            snapshot_module,
            "MAX_FORM4_PROVISIONAL_DISPOSITION_SNAPSHOT_BYTES",
            len(source.read_bytes()) - 1,
        )
        monkeypatch.setattr(
            snapshot_module,
            "_parse_snapshot_bytes",
            lambda *_args, **_kwargs: pytest.fail("snapshot parser was reached"),
        )
    elif resource == "depth":
        depth = (
            snapshot_module.MAX_FORM4_PROVISIONAL_DISPOSITION_SNAPSHOT_JSON_DEPTH
            + 1
        )
        target.write_bytes(("[" * depth + "]" * depth).encode("ascii"))
    elif resource == "rows":
        shutil.copyfile(source, target)
        monkeypatch.setattr(snapshot_module, "MAX_TOTAL_TRANSACTIONS", 0)
    else:  # pragma: no cover - parameter list is closed.
        raise AssertionError(resource)
    if resource != "bytes":
        monkeypatch.setattr(
            snapshot_module,
            "build_form4_provisional_disposition_report",
            lambda *_args, **_kwargs: pytest.fail("upstream rebuild was reached"),
        )

    with pytest.raises(Form4ProvisionalDispositionSnapshotError):
        load_form4_provisional_disposition_snapshot(target, evidence=evidence)


def test_snapshot_payload_tracks_every_current_report_field(report):
    payload = report.to_payload()
    assert set(payload) == {
        item.name for item in fields(Form4ProvisionalDispositionReport)
    }
    assert set(payload["identity"]) == {
        item.name for item in fields(Form4ProvisionalDispositionReportIdentity)
    }
    assert payload["rows"]
    assert set(payload["rows"][0]) == {
        item.name for item in fields(Form4ProvisionalDispositionRow)
    }


def test_ib1h_module_has_no_network_outcome_execution_or_ui_imports():
    module_path = Path(snapshot_module.__file__)
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
    source = module_path.read_text(encoding="utf-8")
    assert "_VERIFIED_" not in source


def test_report_row_constructor_binds_disposition_to_outcomes(report):
    """Claude review regression (2026-09-03): disposition is derived from
    outcomes after the payload hash is taken, so the constructor is the first
    line that binds them. No test pinned it, and IB-2A replays this constructor
    on every rebuilt row, so a silent deletion here would weaken both layers."""
    target = next(
        row
        for row in report.rows
        if row.disposition
        is Form4ProvisionalDisposition.PROVISIONAL_PRE_AGGREGATION_CANDIDATE
    )
    with pytest.raises(
        Form4ProvisionalDispositionReportError,
        match="contradicts parser outcomes",
    ):
        replace(
            target,
            disposition=Form4ProvisionalDisposition.PROVISIONAL_QUARANTINE,
        )
