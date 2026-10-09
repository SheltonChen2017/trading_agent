"""Invented one-quarter inputs; no retained-root replay or source acquisition."""

from __future__ import annotations

import csv
import base64
import io
import json
import os
import subprocess
import types
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from research import insider_buying_ib1c_v2_affected_quarter_runner as runner
from research import insider_buying_affected_quarter_isolation as isolation
from research.insider_buying import sec_zip_corpus_census as census_module
from research.insider_buying.ib1b_82q_offline_runner import _quarter_headers
from research.insider_buying.sec_bulk_snapshot import ALLOWED_SEC_TABLES
from research.insider_buying.sec_ib1b_82q_schema_profile import (
    build_retained_82q_schema_profile_candidate,
)
from research.insider_buying.sec_ib1c_identity_v2 import _authority
from test_insider_buying_ib1b_82q_snapshot_runner import (
    _CAPTURE_COMMIT, _PERIODS, _STAMP, _url,
)


_PARSER_COMMIT = "b" * 40
_SOURCE_INVENTORY_SHA256 = "c" * 64
_FORMS = ("3", "3/A", "4", "4/A", "5", "5/A")
_MANIFEST_NAME = "insider_quarterly_zip_manifest_2006q1_2026q2.csv"


def _archive(*, malformed: str | None = None) -> bytes:
    """Six real logical rows, with one opaque 2005 accession in 2006Q1."""
    profile = build_retained_82q_schema_profile_candidate()
    sink = io.BytesIO()
    with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for table in ALLOWED_SEC_TABLES:
            headers = profile.variant_for(table, 2006, 1).headers
            lines = ["\t".join(headers)]
            if table == "SUBMISSION.tsv":
                for ordinal, form in enumerate(_FORMS, start=1):
                    accession_year = "05" if ordinal == 3 else "06"
                    accession = f"0000123456-{accession_year}-{ordinal:06d}"
                    values = {header: "" for header in headers}
                    values.update(
                        ACCESSION_NUMBER=accession,
                        FILING_DATE="15-JAN-2006",
                        PERIOD_OF_REPORT="14-JAN-2006",
                        DOCUMENT_TYPE=form,
                        ISSUERCIK="123456",
                        ISSUERNAME="Invented one-quarter issuer",
                        ISSUERTRADINGSYMBOL="INVT",
                    )
                    if ordinal == 3 and malformed == "date":
                        values["FILING_DATE"] = "30-FEB-2006"
                    if ordinal == 3 and malformed == "cik":
                        values["ISSUERCIK"] = "0"
                    if ordinal == 3 and malformed == "form":
                        values["DOCUMENT_TYPE"] = "8-K"
                    if ordinal == 3 and malformed == "duplicate_accession":
                        values["ACCESSION_NUMBER"] = "0000123456-06-000001"
                    line = "\t".join(values[header] for header in headers)
                    if ordinal == 3 and malformed == "ragged":
                        line += "\textra"
                    lines.append(line)
            if table == "NONDERIV_TRANS.tsv" and malformed == "duplicate_key":
                values = {header: "" for header in headers}
                values.update(
                    ACCESSION_NUMBER="0000123456-05-000003",
                    NONDERIV_TRANS_SK="1",
                )
                line = "\t".join(values[header] for header in headers)
                lines.extend((line, line))
            archive.writestr(table, ("\n".join(lines) + "\n").encode("utf-8"))
    return sink.getvalue()


def _manifest(raw: bytes) -> bytes:
    """All 82 selection metadata rows, but only the selected ZIP is needed."""
    text = io.StringIO(newline="")
    writer = csv.writer(text, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow((
        "Period", "FileName", "SourceUrl", "SizeBytes", "SHA256",
        "LocalLastWriteUtc", "TimestampBasis", "CaptureCommit", "SourceIndexUrl",
    ))
    for period in _PERIODS:
        writer.writerow((
            period, f"{period.lower()}_form345.zip", _url(period),
            str(len(raw)), hash_bytes(raw), _STAMP,
            "local filesystem last-write time; not SEC-attested", _CAPTURE_COMMIT,
            "https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets",
        ))
    return text.getvalue().encode("utf-8")


def _payload(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    envelope = json.loads(raw)
    assert raw == (canonical_json(envelope) + "\n").encode("utf-8")
    assert envelope["payload_sha256"] == hash_payload(envelope["payload"])
    return envelope["payload"]


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, malformed=None):
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    output.mkdir()
    raw = _archive(malformed=malformed)
    manifest = _manifest(raw)
    (source / _MANIFEST_NAME).write_bytes(manifest)
    (source / "2006q1_form345.zip").write_bytes(raw)
    profile = build_retained_82q_schema_profile_candidate()
    header_receipt = _quarter_headers(raw, "2006Q1", profile)
    for name, value in {
        "EXPECTED_MANIFEST_SHA256": hash_bytes(manifest),
        "EXPECTED_MANIFEST_SIZE_BYTES": len(manifest),
        "EXPECTED_ZIP_SHA256": hash_bytes(raw),
        "EXPECTED_ZIP_SIZE_BYTES": len(raw),
        "EXPECTED_HEADER_RECEIPT_SHA256": hash_payload(header_receipt.to_payload()),
    }.items():
        monkeypatch.setattr(runner, name, value)
    return source, output


def _run(source: Path, output: Path) -> dict[str, object]:
    return runner._run_quarter(
        source, output, _PARSER_COMMIT, _SOURCE_INVENTORY_SHA256,
    )


def _verify(source: Path, output: Path) -> dict[str, object]:
    return runner._verify_quarter(
        source, output, _PARSER_COMMIT, _SOURCE_INVENTORY_SHA256,
    )


def _rewrite_envelope(path: Path, mutate) -> None:
    envelope = json.loads(path.read_bytes())
    mutate(envelope["payload"])
    envelope["payload_sha256"] = hash_payload(envelope["payload"])
    path.write_bytes((canonical_json(envelope) + "\n").encode("utf-8"))


def test_one_quarter_retains_all_six_forms_and_withholds_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, output = _fixture(tmp_path, monkeypatch)
    before = {path.name: path.read_bytes() for path in source.iterdir()}
    result = _run(source, output)
    assert type(result) is dict and result["period"] == "2006Q1"
    assert all(type(value) in {str, int, bool, type(None)} for value in result.values())
    assert _verify(source, output) == result
    assert {path.name: path.read_bytes() for path in source.iterdir()} == before
    assert len(list((output / "ib1a").glob("sec-insider-bulk-*"))) == 1
    assert len(list((output / "ib1b").glob("sec-insider-parsed-*"))) == 1
    assert not (output / "ib1b-82q-completion.json").exists()
    assert not (output / "journal").exists()
    body = _payload(output / "assessment.json")
    assert body["period"] == "2006Q1"
    assert body["submission_count"] == body["quarantined_count"] == 6
    assert body["corroborated_count"] == 0
    assert body["short_cik_count"] == 6
    assert body["accession_year_mismatch_count"] == 1
    assert body["whole_quarter_identity_sha256"] is None
    assert [row["form_type"] for row in body["rows"]] == list(_FORMS)
    assert [row["source_record_ordinal"] for row in body["rows"]] == list(range(1, 7))
    assert all(row["raw_issuer_cik"] == "123456" for row in body["rows"])
    assert all(row["raw_filing_date"] == "15-JAN-2006" for row in body["rows"])
    assert body["rows"][2]["accession_number"] == "0000123456-05-000003"
    assert body["rows"][2]["accession_year_mismatch"] is True
    for row in body["rows"]:
        reason = ("complete_parent_corroboration_missing" if row["form_type"] in {"4", "4/A"}
                  else "unsupported_parent_corroboration_form")
        assert row["quarantine_reasons"] == [reason]
        assert row["corroboration"] is None
    assert all(value is False or type(value) is int and value == 0
               for value in body["authority"].values())
    for name, expected in _authority().items():
        assert result[name] == expected and type(result[name]) is type(expected)
    assert len((output / "completion.json").read_bytes()) <= 16 * 1024
    assert b"Invented one-quarter issuer" not in (output / "completion.json").read_bytes()


def test_public_parsed_loader_is_given_committed_raw_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, output = _fixture(tmp_path, monkeypatch)
    original = runner.load_sec_bulk_parsed_snapshot
    calls = []

    def observed(directory, *, raw_snapshot_directory):
        calls.append((Path(directory), Path(raw_snapshot_directory)))
        return original(directory, raw_snapshot_directory=raw_snapshot_directory)

    monkeypatch.setattr(runner, "load_sec_bulk_parsed_snapshot", observed)
    _run(source, output)
    _verify(source, output)
    assert len(calls) >= 2
    assert all(parsed.parent == output / "ib1b" and raw.parent == output / "ib1a"
               for parsed, raw in calls)
    assert len(set(calls)) == 1


def test_exactly_one_publication_and_existing_empty_parent_assessment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, output = _fixture(tmp_path, monkeypatch)
    calls = []
    for name in ("write_sec_bulk_snapshot", "build_sec_bulk_parsed_snapshot"):
        original = getattr(runner, name)

        def observed(*args, _original=original, _name=name, **kwargs):
            calls.append(_name)
            return _original(*args, **kwargs)

        monkeypatch.setattr(runner, name, observed)
    assessor = runner.assess_ib1c_v2_quarter_identity

    def assess(snapshot, quarter, parents):
        assert quarter.period == "2006Q1"
        assert type(parents) is tuple and parents == ()
        calls.append("assess")
        return assessor(snapshot, quarter, parents)

    monkeypatch.setattr(runner, "assess_ib1c_v2_quarter_identity", assess)
    result = _run(source, output)
    assert calls == ["write_sec_bulk_snapshot", "build_sec_bulk_parsed_snapshot", "assess"]
    raw = (source / "2006q1_form345.zip").read_bytes()
    manifest = (source / _MANIFEST_NAME).read_bytes()
    quarter = census_module._census_quarter(raw, census_module._manifest_bindings(manifest)[0])
    headers = _quarter_headers(raw, "2006Q1", build_retained_82q_schema_profile_candidate())
    assert result["manifest_sha256"] == hash_bytes(manifest)
    assert result["zip_sha256"] == hash_bytes(raw)
    assert result["header_receipt_sha256"] == hash_payload(headers.to_payload())
    assert result["census_quarter_sha256"] == hash_payload(quarter.to_payload())
    assert result["source_inventory_sha256"] == _SOURCE_INVENTORY_SHA256
    assert result["parser_commit"] == _PARSER_COMMIT
    assert result["assessment_sha256"] == hash_payload(_payload(output / "assessment.json"))
    assert result["assessment_envelope_sha256"] == hash_bytes((output / "assessment.json").read_bytes())
    assert result["assessment_envelope_bytes"] == len((output / "assessment.json").read_bytes())
    assert result["quarters_assessed"] == 1 and result["supplied_parent_count"] == 0
    completion = _payload(output / "completion.json")
    assert completion["receipt"] == result
    assert completion["selection_scanned_quarters"] == 1
    metadata = completion["quarter_snapshot"]
    assert metadata["document_forms"] == dict.fromkeys(_FORMS, 1)
    assert metadata["accession_count"] == 6
    assert metadata["legacy_field_is_verified_retrieval"] is False
    assert metadata["source_timestamp_basis"] == "filesystem_last_write_unverified"
    assert metadata["parser_git_commit_verified"] is False


def test_absent_mismatch_cannot_be_relabelled_as_affected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, output = _fixture(tmp_path, monkeypatch)
    sink = io.BytesIO()
    with zipfile.ZipFile(source / "2006q1_form345.zip") as original:
        with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_DEFLATED) as rebuilt:
            for name in original.namelist():
                rebuilt.writestr(name, original.read(name).replace(b"0000123456-05-000003", b"0000123456-06-000003"))
    raw = sink.getvalue()
    manifest = _manifest(raw)
    (source / "2006q1_form345.zip").write_bytes(raw)
    (source / _MANIFEST_NAME).write_bytes(manifest)
    headers = _quarter_headers(raw, "2006Q1", build_retained_82q_schema_profile_candidate())
    monkeypatch.setattr(runner, "EXPECTED_MANIFEST_SHA256", hash_bytes(manifest))
    monkeypatch.setattr(runner, "EXPECTED_MANIFEST_SIZE_BYTES", len(manifest))
    monkeypatch.setattr(runner, "EXPECTED_ZIP_SHA256", hash_bytes(raw))
    monkeypatch.setattr(runner, "EXPECTED_ZIP_SIZE_BYTES", len(raw))
    monkeypatch.setattr(runner, "EXPECTED_HEADER_RECEIPT_SHA256", hash_payload(headers.to_payload()))
    with pytest.raises(ValueError, match="REFUSED.*affected"):
        _run(source, output)
    assert list(output.iterdir()) == []


def test_census_count_disagreement_refuses_without_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, output = _fixture(tmp_path, monkeypatch)
    original = runner._census_quarter

    def wrong_count(*args):
        census = original(*args)
        return replace(census, form_counts=(2, 1, 1, 1, 1, 1))

    monkeypatch.setattr(runner, "_census_quarter", wrong_count)
    with pytest.raises(ValueError, match="REFUSED"):
        _run(source, output)
    assert list(output.iterdir()) == []


@pytest.mark.parametrize("name", [
    "EXPECTED_MANIFEST_SHA256", "EXPECTED_MANIFEST_SIZE_BYTES",
    "EXPECTED_ZIP_SHA256", "EXPECTED_ZIP_SIZE_BYTES",
    "EXPECTED_HEADER_RECEIPT_SHA256",
])
def test_wrong_source_or_header_pin_refuses_before_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str,
) -> None:
    source, output = _fixture(tmp_path, monkeypatch)
    current = getattr(runner, name)
    monkeypatch.setattr(runner, name, current + 1 if type(current) is int else "e" * 64)
    with pytest.raises(ValueError, match="REFUSED"):
        _run(source, output)
    assert list(output.iterdir()) == []


@pytest.mark.parametrize("kind", ["missing", "extra", "reordered"])
def test_manifest_requires_complete_ordered_82_quarter_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str,
) -> None:
    source, output = _fixture(tmp_path, monkeypatch)
    path = source / _MANIFEST_NAME
    rows = list(csv.reader(io.StringIO(path.read_text(), newline="")))
    if kind == "missing":
        rows.pop()
    elif kind == "extra":
        rows.append(rows[-1])
    else:
        rows[1], rows[2] = rows[2], rows[1]
    text = io.StringIO(newline="")
    csv.writer(text, quoting=csv.QUOTE_ALL, lineterminator="\r\n").writerows(rows)
    raw = text.getvalue().encode("utf-8")
    path.write_bytes(raw)
    monkeypatch.setattr(runner, "EXPECTED_MANIFEST_SHA256", hash_bytes(raw))
    monkeypatch.setattr(runner, "EXPECTED_MANIFEST_SIZE_BYTES", len(raw))
    with pytest.raises(ValueError, match="REFUSED"):
        _run(source, output)
    assert list(output.iterdir()) == []


def test_profile_label_drift_refuses_before_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, output = _fixture(tmp_path, monkeypatch)
    profile = build_retained_82q_schema_profile_candidate()
    monkeypatch.setattr(
        runner, "build_retained_82q_schema_profile_candidate",
        lambda: replace(profile, profile_id="invented-unreviewed"),
    )
    with pytest.raises(ValueError, match="REFUSED"):
        _run(source, output)
    assert list(output.iterdir()) == []


@pytest.mark.parametrize("malformed", [
    "date", "cik", "form", "duplicate_accession", "ragged", "duplicate_key",
])
def test_malformed_logical_inputs_never_publish_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, malformed: str,
) -> None:
    source, output = _fixture(tmp_path, monkeypatch, malformed=malformed)
    with pytest.raises(ValueError, match="REFUSED"):
        _run(source, output)
    assert not (output / "assessment.json").exists()
    assert not (output / "completion.json").exists()
    if malformed != "duplicate_key":
        assert list(output.iterdir()) == []


@pytest.mark.parametrize("bad", [None, True, 123, "", "A" * 64, "a" * 63])
def test_inventory_digest_must_be_exact_lowercase_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad,
) -> None:
    source, output = _fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="REFUSED"):
        runner._run_quarter(source, output, _PARSER_COMMIT, bad)
    assert list(output.iterdir()) == []


@pytest.mark.parametrize("bad", [None, True, "", "b" * 39, "B" * 40])
def test_parser_commit_shape_refuses_before_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad,
) -> None:
    source, output = _fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="REFUSED"):
        runner._run_quarter(source, output, bad, _SOURCE_INVENTORY_SHA256)
    assert list(output.iterdir()) == []


def test_nonempty_output_is_not_a_resume_or_overwrite_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, output = _fixture(tmp_path, monkeypatch)
    sentinel = output / "foreign.bin"
    sentinel.write_bytes(b"preserve-me")
    with pytest.raises(ValueError, match="REFUSED"):
        _run(source, output)
    assert sentinel.read_bytes() == b"preserve-me"
    assert sorted(path.name for path in output.iterdir()) == ["foreign.bin"]


def test_output_cannot_overlap_the_retained_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, _ = _fixture(tmp_path, monkeypatch)
    output = source / "output"
    output.mkdir()
    before = {path.name: path.read_bytes() for path in source.iterdir() if path.is_file()}
    with pytest.raises(ValueError, match="REFUSED"):
        _run(source, output)
    assert list(output.iterdir()) == []
    assert {path.name: path.read_bytes() for path in source.iterdir() if path.is_file()} == before


def test_source_root_redirect_is_not_followed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, output = _fixture(tmp_path, monkeypatch)
    alias = tmp_path / "source-alias"
    alias.symlink_to(source, target_is_directory=True)
    with pytest.raises(ValueError, match="REFUSED"):
        _run(alias, output)
    assert list(output.iterdir()) == []


@pytest.mark.parametrize("limit_name", ["MAX_ASSESSMENT_BYTES", "MAX_COMPLETION_BYTES"])
def test_bounded_receipt_failure_publishes_neither_success_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, limit_name: str,
) -> None:
    source, output = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(runner, limit_name, 1)
    with pytest.raises(ValueError, match="REFUSED.*byte cap"):
        _run(source, output)
    assert not (output / "assessment.json").exists()
    assert not (output / "completion.json").exists()


def test_completion_publication_occurs_only_after_assessment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, output = _fixture(tmp_path, monkeypatch)
    original = runner._publish_envelope
    calls = []

    def observed(directory, name, *args, **kwargs):
        if name == "completion.json":
            assert (output / "assessment.json").is_file()
        calls.append(name)
        return original(directory, name, *args, **kwargs)

    monkeypatch.setattr(runner, "_publish_envelope", observed)
    _run(source, output)
    assert calls == ["assessment.json", "completion.json"]


@pytest.mark.parametrize("path_kind", ["symlink", "hardlink"])
def test_source_zip_alias_refuses_without_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path_kind: str,
) -> None:
    source, output = _fixture(tmp_path, monkeypatch)
    leaf = source / "2006q1_form345.zip"
    sentinel = tmp_path / "original.zip"
    leaf.rename(sentinel)
    if path_kind == "symlink":
        leaf.symlink_to(sentinel)
    else:
        os.link(sentinel, leaf)
    original = sentinel.read_bytes()
    with pytest.raises(ValueError, match="REFUSED"):
        _run(source, output)
    assert sentinel.read_bytes() == original
    assert list(output.iterdir()) == []


def test_verify_rejects_source_change_without_rewriting_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, output = _fixture(tmp_path, monkeypatch)
    _run(source, output)
    before = {str(path.relative_to(output)): path.read_bytes()
              for path in output.rglob("*") if path.is_file()}
    archive = source / "2006q1_form345.zip"
    archive.write_bytes(archive.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="REFUSED"):
        _verify(source, output)
    assert {str(path.relative_to(output)): path.read_bytes()
            for path in output.rglob("*") if path.is_file()} == before


@pytest.mark.parametrize("target", ["assessment.json", "completion.json"])
def test_self_rehashed_forged_readback_is_not_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str,
) -> None:
    source, output = _fixture(tmp_path, monkeypatch)
    _run(source, output)
    path = output / target
    _rewrite_envelope(path, lambda payload: payload.update(period="2006Q2"))
    wrong = path.read_bytes()
    with pytest.raises(ValueError, match="REFUSED"):
        _verify(source, output)
    assert path.read_bytes() == wrong


def test_assessment_count_bool_and_false_authority_forgery_refuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, output = _fixture(tmp_path, monkeypatch)
    _run(source, output)
    path = output / "assessment.json"
    original = path.read_bytes()
    for mutate in (
        lambda payload: payload.update(submission_count=True),
        lambda payload: payload["authority"].update(source_authenticated=0),
        lambda payload: payload.update(whole_quarter_identity_sha256="a" * 64),
    ):
        path.write_bytes(original)
        _rewrite_envelope(path, mutate)
        with pytest.raises(ValueError, match="REFUSED"):
            _verify(source, output)


def test_completion_is_absent_when_assessment_publication_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, output = _fixture(tmp_path, monkeypatch)
    original = runner.assess_ib1c_v2_quarter_identity

    def interrupted(*args, **kwargs):
        original(*args, **kwargs)
        raise ValueError("REFUSED: invented assessment interruption")

    monkeypatch.setattr(runner, "assess_ib1c_v2_quarter_identity", interrupted)
    with pytest.raises(ValueError, match="invented assessment interruption"):
        _run(source, output)
    assert not (output / "assessment.json").exists()
    assert not (output / "completion.json").exists()


@pytest.mark.parametrize("change", [
    "authority_integer_false", "mismatch_boolean", "dropped_row", "count_boolean",
])
def test_compromised_assessor_summary_does_not_become_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str,
) -> None:
    """Defense in depth only: substitute an assessor, not an external exploit."""
    source, output = _fixture(tmp_path, monkeypatch)
    original = runner.assess_ib1c_v2_quarter_identity

    class AlteredAssessment:
        def __init__(self, payload):
            self.payload = payload

        def to_payload(self):
            return json.loads(canonical_json(self.payload))

        @property
        def sha256(self):
            return hash_payload(self.payload)

    def compromised(*args, **kwargs):
        payload = original(*args, **kwargs).to_payload()
        if change == "authority_integer_false":
            payload["authority"]["source_authenticated"] = 0
        elif change == "mismatch_boolean":
            payload["accession_year_mismatch_count"] = True
        elif change == "dropped_row":
            payload["rows"].pop()
        else:
            payload["corroborated_count"] = False
        return AlteredAssessment(payload)

    monkeypatch.setattr(runner, "assess_ib1c_v2_quarter_identity", compromised)
    with pytest.raises(ValueError, match="REFUSED"):
        _run(source, output)
    assert not (output / "assessment.json").exists()
    assert not (output / "completion.json").exists()


@pytest.mark.parametrize("change", ["integer_false", "integer_true", "missing_authority"])
def test_compromised_worker_cannot_forge_scalar_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str,
) -> None:
    """Substitute worker metadata only; production captured core stays trusted."""
    source, output = _fixture(tmp_path, monkeypatch)
    receipt = _run(source, output)
    assert isolation._scalar_receipt(receipt, _PARSER_COMMIT, _SOURCE_INVENTORY_SHA256) == receipt
    if change == "integer_false":
        receipt["source_authenticated"] = 0
    elif change == "integer_true":
        receipt["source_authenticated"] = 1
    else:
        receipt.pop("source_authenticated")
    with pytest.raises(isolation.AffectedQuarterIsolationError, match="REFUSED"):
        isolation._scalar_receipt(receipt, _PARSER_COMMIT, _SOURCE_INVENTORY_SHA256)


def _mock_isolation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Mock only the external launch/context, never launch a nested sandbox."""
    source, seed = _fixture(tmp_path, monkeypatch)
    receipt = _run(source, seed)
    output = tmp_path / "isolated-output"
    sources = tuple(sorted((
        (isolation._WORKER_PATH, b"# invented captured launcher\n"),
        (isolation._CORE_PATH, b"# invented captured core\n"),
    )))
    inventory_sha = isolation._digest(isolation._inventory(sources))
    receipt["source_inventory_sha256"] = inventory_sha
    trace = isolation._inventory(sources)
    payload = {"receipt": receipt, "executed_modules": trace}
    context = (str(isolation.LANE_ROOT), isolation.LANE_BRANCH, _PARSER_COMMIT)
    monkeypatch.setattr(isolation, "_repository_snapshot", lambda _: context)
    monkeypatch.setattr(isolation, "_source_snapshot", lambda: sources)
    monkeypatch.setattr(isolation, "_verify_committed_sources", lambda *args: None)
    launches = []

    def launch(raw, destination):
        bundle = json.loads(raw)
        assert bundle["input_root"] == str(source)
        assert bundle["output_root"] == str(output)
        assert bundle["source_inventory_sha256"] == inventory_sha
        launches.append(bundle)
        return subprocess.CompletedProcess((), 0, isolation._canonical(payload) + b"\n", b"")

    monkeypatch.setattr(isolation, "_run_worker", launch)
    return source, output, payload, launches, sources


def test_mocked_launcher_binds_captured_sources_and_preserves_scalar_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, output, payload, launches, sources = _mock_isolation(tmp_path, monkeypatch)
    result = isolation.run_isolated(source, output, _PARSER_COMMIT)
    assert len(launches) == 1
    assert {key: result[key] for key in payload["receipt"]} == payload["receipt"]
    assert result["worker_source_sha256"] == hash_bytes(dict(sources)[isolation._WORKER_PATH])
    assert result["worker_bootstrap_sha256"] == hash_bytes(isolation._BOOTSTRAP.encode("utf-8"))
    assert result["executed_source_inventory_sha256"] == isolation._digest(payload["executed_modules"])
    assert result["executed_source_count"] == 2
    for key in ("os_network_denied", "os_output_write_confined", "os_process_fork_denied",
                "audit_additional_processes_denied", "source_only_lane_imports"):
        assert result[key] is True
    assert output.stat().st_mode & 0o077 == 0


@pytest.mark.parametrize("change", [
    "wrong_commit", "wrong_inventory", "missing_receipt", "extra_wrapper",
    "missing_trace", "empty_trace", "missing_core", "duplicate_trace",
    "unknown_source", "wrong_source_hash", "reserved_field", "nested_scalar",
    "negative_integer", "huge_string", "true_authority", "missing_authority",
])
def test_mocked_worker_return_refuses_unbound_or_unbounded_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str,
) -> None:
    source, output, payload, _, _ = _mock_isolation(tmp_path, monkeypatch)
    if change == "wrong_commit":
        payload["receipt"]["parser_commit"] = "d" * 40
    elif change == "wrong_inventory":
        payload["receipt"]["source_inventory_sha256"] = "d" * 64
    elif change == "missing_receipt":
        payload.pop("receipt")
    elif change == "extra_wrapper":
        payload["unbound"] = None
    elif change == "missing_trace":
        payload.pop("executed_modules")
    elif change == "empty_trace":
        payload["executed_modules"] = []
    elif change == "missing_core":
        payload["executed_modules"] = [payload["executed_modules"][0]]
    elif change == "duplicate_trace":
        payload["executed_modules"][1] = payload["executed_modules"][0]
    elif change == "unknown_source":
        payload["executed_modules"][1]["path"] = "research/unbound.py"
    elif change == "wrong_source_hash":
        payload["executed_modules"][1]["sha256"] = "e" * 64
    elif change == "reserved_field":
        payload["receipt"]["os_network_denied"] = False
    elif change == "nested_scalar":
        payload["receipt"]["unbound"] = []
    elif change == "negative_integer":
        payload["receipt"]["unbound"] = -1
    elif change == "huge_string":
        payload["receipt"]["unbound"] = "x" * 4097
    elif change == "true_authority":
        payload["receipt"]["source_authenticated"] = True
    else:
        payload["receipt"].pop("source_authenticated")
    with pytest.raises(isolation.AffectedQuarterIsolationError, match="REFUSED"):
        isolation.run_isolated(source, output, _PARSER_COMMIT)


@pytest.mark.parametrize("kind", ["refused", "stderr", "empty", "oversized", "invalid_json", "noncanonical"])
def test_mocked_worker_process_failure_never_returns_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str,
) -> None:
    source, output, payload, _, _ = _mock_isolation(tmp_path, monkeypatch)
    raw = isolation._canonical(payload) + b"\n"
    returncode, errors = 0, b""
    if kind == "refused":
        returncode = 1
    elif kind == "stderr":
        errors = b"private synthetic failure"
    elif kind == "empty":
        raw = b""
    elif kind == "oversized":
        raw = b"x" * (isolation._MAX_OUTPUT_BYTES + 1)
    elif kind == "invalid_json":
        raw = b"{broken}\n"
    else:
        raw = b" " + raw
    monkeypatch.setattr(isolation, "_run_worker", lambda *args: subprocess.CompletedProcess((), returncode, raw, errors))
    with pytest.raises(isolation.AffectedQuarterIsolationError, match="REFUSED") as caught:
        isolation.run_isolated(source, output, _PARSER_COMMIT)
    assert "private synthetic failure" not in str(caught.value)


def test_source_context_drift_refuses_and_preserves_incomplete_private_leaf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, output, _, launches, sources = _mock_isolation(tmp_path, monkeypatch)
    calls = 0

    def snapshot():
        nonlocal calls
        calls += 1
        return sources if calls == 1 else ((sources[0][0], b"changed\n"), sources[1])

    monkeypatch.setattr(isolation, "_source_snapshot", snapshot)
    with pytest.raises(isolation.AffectedQuarterIsolationError, match="REFUSED.*source inventory changed"):
        isolation.run_isolated(source, output, _PARSER_COMMIT)
    assert launches == []
    assert output.is_dir() and list(output.iterdir()) == []


def test_uncommitted_capture_refuses_before_output_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, output, _, launches, _ = _mock_isolation(tmp_path, monkeypatch)

    def mismatch(*args):
        raise isolation.AffectedQuarterIsolationError("REFUSED: committed blob changed")

    monkeypatch.setattr(isolation, "_verify_committed_sources", mismatch)
    with pytest.raises(isolation.AffectedQuarterIsolationError, match="REFUSED.*committed blob"):
        isolation.run_isolated(source, output, _PARSER_COMMIT)
    assert launches == [] and not output.exists()


@pytest.mark.parametrize("wrong", ["root", "branch", "head", "dirty"])
def test_launcher_repository_guard_requires_exact_clean_designated_lane(
    monkeypatch: pytest.MonkeyPatch, wrong: str,
) -> None:
    responses = {
        ("rev-parse", "--show-toplevel"): str(isolation.LANE_ROOT).encode() + b"\n",
        ("branch", "--show-current"): isolation.LANE_BRANCH.encode() + b"\n",
        ("rev-parse", "HEAD"): _PARSER_COMMIT.encode() + b"\n",
        ("status", "--porcelain=v1", "--untracked-files=all"): b"",
    }
    key = {
        "root": ("rev-parse", "--show-toplevel"),
        "branch": ("branch", "--show-current"),
        "head": ("rev-parse", "HEAD"),
        "dirty": ("status", "--porcelain=v1", "--untracked-files=all"),
    }[wrong]
    responses[key] = {
        "root": b"/not/the/lane\n", "branch": b"main\n",
        "head": b"dddddddddddddddddddddddddddddddddddddddd\n",
        "dirty": b"?? invented.py\n",
    }[wrong]
    monkeypatch.setattr(isolation, "_git", lambda *args: responses[args])
    with pytest.raises(isolation.AffectedQuarterIsolationError, match="REFUSED.*exact clean designated lane"):
        isolation._repository_snapshot(_PARSER_COMMIT)


@pytest.mark.parametrize("bad", [None, True, "", "b" * 39, "B" * 40])
def test_launcher_commit_shape_refuses_before_git_check(monkeypatch: pytest.MonkeyPatch, bad):
    calls = []
    monkeypatch.setattr(isolation, "_git", lambda *args: calls.append(args))
    with pytest.raises(isolation.AffectedQuarterIsolationError, match="REFUSED"):
        isolation._repository_snapshot(bad)
    assert calls == []


def test_required_sandbox_unavailable_refuses_before_output_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, output, _, launches, _ = _mock_isolation(tmp_path, monkeypatch)
    monkeypatch.setattr(isolation.os, "access", lambda *args: False)
    with pytest.raises(isolation.AffectedQuarterIsolationError, match="REFUSED.*sandbox is unavailable"):
        isolation.run_isolated(source, output, _PARSER_COMMIT)
    assert launches == [] and not output.exists()


@pytest.mark.parametrize("timeout", [True, False, 0, -1, 1801, 1.0, "1"])
def test_worker_timeout_refuses_without_process_launch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, timeout):
    calls = []
    monkeypatch.setattr(isolation.subprocess, "Popen", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(isolation.AffectedQuarterIsolationError, match="REFUSED"):
        isolation._run_worker(b"{}", tmp_path, timeout_seconds=timeout)
    assert calls == []


@pytest.mark.parametrize("raw", [None, "{}", b"", b"x" * (32 * 1024 * 1024 + 1)])
def test_worker_bundle_bounds_refuse_without_process_launch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, raw):
    calls = []
    monkeypatch.setattr(isolation.subprocess, "Popen", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(isolation.AffectedQuarterIsolationError, match="REFUSED"):
        isolation._run_worker(raw, tmp_path)
    assert calls == []


@pytest.mark.parametrize("event", [
    "socket.__new__", "socket.connect", "socket.bind", "socket.getaddrinfo",
    "subprocess.Popen", "os.system", "os.fork", "os.forkpty", "os.exec",
    "os.posix_spawn", "os.spawn", "ctypes.dlopen", "ctypes.dlsym",
])
def test_audit_refuses_network_and_additional_process_events(event: str):
    with pytest.raises(isolation.AffectedQuarterIsolationError, match="REFUSED"):
        isolation._audit_event(event, ())


def test_policy_denies_network_fork_and_writes_except_private_output(tmp_path: Path):
    output = tmp_path / "fresh-output"
    policy = isolation._worker_policy(output)
    assert "(deny network*)" in policy
    assert "(deny process-fork)" in policy
    assert "(deny process-exec)" in policy
    assert "(deny file-write*)" in policy
    assert f'(allow file-write* (subpath "{output}"))' in policy
    assert "(allow process-exec (literal " in policy
    # Literal interpreter exec allowances still require the production audit hook.
    assert "(allow process-fork" not in policy


@pytest.mark.parametrize("leaf", ['bad"quote', "bad\\slash", "bad\nline"])
def test_policy_path_cannot_inject_sandbox_rules(tmp_path: Path, leaf: str):
    with pytest.raises(isolation.AffectedQuarterIsolationError, match="REFUSED"):
        isolation._worker_policy(tmp_path / leaf)


def test_source_finder_executes_only_captured_bytes_and_records_identity():
    relative, raw = "research/invented_quarter.py", b"source_value = 'captured'\n"
    finder = isolation._SourceFinder(((relative, raw),))
    spec = finder.find_spec("research.invented_quarter")
    assert spec is not None and spec.origin == "captured:" + relative
    module = types.ModuleType("research.invented_quarter")
    finder.exec_module(module)
    assert module.source_value == "captured"
    assert module.__file__ == str(isolation.LANE_ROOT / relative)
    assert module.__cached__ is None
    assert finder.executed == [{"path": relative, "sha256": hash_bytes(raw)}]
    assert finder.find_spec("json") is None
    assert finder.find_spec("research") is not None


@pytest.mark.parametrize("name", ["research.missing", "data.missing", "ml.missing", "execution.missing"])
def test_source_finder_never_falls_back_for_uncaptured_repository_modules(name: str):
    finder = isolation._SourceFinder((("research/invented_quarter.py", b"pass\n"),))
    with pytest.raises(isolation.AffectedQuarterIsolationError, match="REFUSED"):
        finder.find_spec(name)


@pytest.mark.parametrize("change", ["extra", "missing", "wrong_hash", "wrong_type", "duplicate", "reordered"])
def test_source_codec_rejects_unbound_inventory_rows(change: str):
    rows = [{"path": path, "sha256": hash_bytes(raw), "source_b64": base64.b64encode(raw).decode("ascii")}
            for path, raw in (("research/a.py", b"a = 1\n"), ("research/b.py", b"b = 2\n"))]
    assert isolation._decode_sources(rows) == (("research/a.py", b"a = 1\n"), ("research/b.py", b"b = 2\n"))
    if change == "extra":
        rows[0]["unbound"] = None
    elif change == "missing":
        rows[0].pop("sha256")
    elif change == "wrong_hash":
        rows[0]["sha256"] = "f" * 64
    elif change == "wrong_type":
        rows[0]["source_b64"] = b"not-a-string"
    elif change == "duplicate":
        rows[1] = rows[0]
    else:
        rows.reverse()
    with pytest.raises(isolation.AffectedQuarterIsolationError, match="REFUSED"):
        isolation._decode_sources(rows)
