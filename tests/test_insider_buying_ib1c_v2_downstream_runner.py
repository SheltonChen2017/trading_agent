"""Genuine synthetic publication/readback; no retained roots or source access."""

from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import stat

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from research import insider_buying_ib1c_v2_affected_quarter_runner as preparation
from research import insider_buying_ib1c_v2_downstream_runner as downstream
from research.insider_buying.sec_ib1b_82q_schema_profile import (
    build_retained_82q_schema_profile_candidate,
)
from test_insider_buying_ib1c_v2_affected_quarter_runner import (
    _fixture, _payload, _run, _rewrite_envelope,
    _PARSER_COMMIT, _SOURCE_INVENTORY_SHA256,
)


_FORMS = ("3", "3/A", "4", "4/A", "5", "5/A")


def _repin(monkeypatch: pytest.MonkeyPatch, output: Path) -> None:
    assessment = (output / "assessment.json").read_bytes()
    monkeypatch.setattr(downstream, "EXPECTED_COMPLETION_SHA256",
                        hash_bytes((output / "completion.json").read_bytes()))
    monkeypatch.setattr(downstream, "EXPECTED_ASSESSMENT_SHA256", hash_bytes(assessment))
    monkeypatch.setattr(downstream, "EXPECTED_ASSESSMENT_BYTES", len(assessment))


def _published(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source, output = _fixture(tmp_path, monkeypatch)
    receipt = _run(source, output)
    _repin(monkeypatch, output)
    monkeypatch.setattr(downstream, "PRODUCER_COMMIT", _PARSER_COMMIT)
    monkeypatch.setattr(downstream, "PRODUCER_SOURCE_INVENTORY_SHA256",
                        _SOURCE_INVENTORY_SHA256)
    return source, output, receipt


def _tree(root: Path):
    """Ignore read-induced atime, but preserve every file/name/version/link."""
    result = {}
    for path in (root, *sorted(root.rglob("*"))):
        info = path.lstat()
        content = (str(path.readlink()) if stat.S_ISLNK(info.st_mode)
                   else hash_bytes(path.read_bytes()) if stat.S_ISREG(info.st_mode)
                   else None)
        result[str(path.relative_to(root))] = (
            info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, content,
        )
    return result


def _refused_without_change(source: Path, output: Path):
    before = (_tree(source), _tree(output))
    with pytest.raises(downstream.Ib1cV2DownstreamLoadError, match="REFUSED"):
        downstream.load_retained_2006_coverage(source, output)
    assert (_tree(source), _tree(output)) == before


def _rebind_changed_assessment(output: Path) -> None:
    body = _payload(output / "assessment.json")
    raw = (output / "assessment.json").read_bytes()

    def update(completion):
        receipt = completion["receipt"]
        receipt["assessment_sha256"] = hash_payload(body)
        receipt["assessment_envelope_sha256"] = hash_bytes(raw)
        receipt["assessment_envelope_bytes"] = len(raw)

    _rewrite_envelope(output / "completion.json", update)


def test_genuine_publication_loads_all_rows_without_source_identity_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, output, _ = _published(tmp_path, monkeypatch)
    before = (_tree(source), _tree(output))
    coverage = downstream.load_retained_2006_coverage(source, output)
    metadata = coverage.to_payload()
    rows = coverage.pilot_rows()
    assert metadata["submission_count"] == metadata["quarantined_count"] == 6
    assert metadata["corroborated_count"] == 0
    assert metadata["short_cik_count"] == 6
    assert metadata["accession_year_mismatch_count"] == 1
    assert metadata["form_counts"] == dict.fromkeys(_FORMS, 1)
    assert metadata["source_identity_complete"] is False
    assert metadata["source_identity_sha256"] is None
    assert len(rows) == 6 and coverage.admitted_rows() == []
    assert [row["form_type"] for row in rows] == list(_FORMS)
    assert [row["source_record_ordinal"] for row in rows] == list(range(1, 7))
    assert all(row["raw_issuer_cik"] == "123456" for row in rows)
    assert all(row["raw_filing_date"] == "15-JAN-2006" for row in rows)
    assert rows[2]["accession_number"] == "0000123456-05-000003"
    assert rows[2]["accession_year_mismatch"] is True
    original_rows = _payload(output / "assessment.json")["rows"]
    for original, loaded in zip(original_rows, rows, strict=True):
        for key, value in original.items():
            assert loaded[key] == value and type(loaded[key]) is type(value)
    assert metadata["rows_sha256"] == hash_payload(rows)
    assert all(value is False or type(value) is int and value == 0
               for value in metadata["authority"].values())
    assert (_tree(source), _tree(output)) == before


def test_loader_invokes_public_parsed_reload_with_exact_raw_upstream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, output, receipt = _published(tmp_path, monkeypatch)
    original = downstream.load_sec_bulk_parsed_snapshot
    calls = []

    def observed(directory, *, raw_snapshot_directory):
        calls.append((Path(directory), Path(raw_snapshot_directory)))
        return original(directory, raw_snapshot_directory=raw_snapshot_directory)

    monkeypatch.setattr(downstream, "load_sec_bulk_parsed_snapshot", observed)
    downstream.load_retained_2006_coverage(source, output)
    assert calls == [(output / "ib1b" / receipt["parsed_snapshot_id"],
                      output / "ib1a" / receipt["raw_snapshot_id"])]


def test_downstream_loader_never_calls_publication_or_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, output, _ = _published(tmp_path, monkeypatch)
    before = (_tree(source), _tree(output))

    def forbidden(*args, **kwargs):
        pytest.fail("read-only downstream invoked a preparation publisher")

    for name in ("write_sec_bulk_snapshot", "build_sec_bulk_parsed_snapshot", "_publish_envelope"):
        monkeypatch.setattr(preparation, name, forbidden)
    coverage = downstream.load_retained_2006_coverage(source, output)
    assert coverage.to_payload()["submission_count"] == 6
    assert (_tree(source), _tree(output)) == before


def test_detached_coverage_outputs_do_not_mutate_factory_accounting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, output, _ = _published(tmp_path, monkeypatch)
    coverage = downstream.load_retained_2006_coverage(source, output)
    expected = coverage.to_payload()
    payload = coverage.to_payload()
    payload["quarantined_count"] = 0
    payload["authority"]["canonical_evidence"] = True
    rows = coverage.pilot_rows()
    rows[0]["raw_issuer_cik"] = "different"
    rows[0]["quarantine_reasons"].clear()
    rows.pop()
    assert coverage.to_payload() == expected
    assert len(coverage.pilot_rows()) == 6
    assert coverage.pilot_rows()[0]["raw_issuer_cik"] == "123456"
    assert coverage.pilot_rows()[0]["quarantine_reasons"]


def test_loader_preserves_producer_lineage_instead_of_consumer_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, output, receipt = _published(tmp_path, monkeypatch)
    metadata = downstream.load_retained_2006_coverage(source, output).to_payload()
    binding = metadata["preparation_binding"]
    assert binding["producer_commit"] == receipt["parser_commit"] == _PARSER_COMMIT
    assert binding["producer_source_inventory_sha256"] == receipt["source_inventory_sha256"] == _SOURCE_INVENTORY_SHA256
    assert binding["completion_envelope_sha256"] == hash_bytes((output / "completion.json").read_bytes())
    assert binding["assessment_envelope_sha256"] == hash_bytes((output / "assessment.json").read_bytes())
    assert binding["assessment_envelope_bytes"] == len((output / "assessment.json").read_bytes())
    assert binding["raw_snapshot_id"] == receipt["raw_snapshot_id"]
    assert binding["parsed_snapshot_id"] == receipt["parsed_snapshot_id"]
    assert binding["profile_sha256"] == receipt["schema_profile_sha256"]
    assert binding["census_quarter_sha256"] == receipt["census_quarter_sha256"]
    assert metadata["artifact_loading_verified_here"] is False


def test_loaded_coverage_cannot_be_replaced_as_a_factory_verified_object(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, output, _ = _published(tmp_path, monkeypatch)
    coverage = downstream.load_retained_2006_coverage(source, output)
    changed = replace(coverage, _summary_raw=b"{}")
    with pytest.raises(ValueError, match="REFUSED"):
        changed.to_payload()
    with pytest.raises(ValueError, match="REFUSED"):
        changed.pilot_rows()
    assert coverage.to_payload()["quarantined_count"] == 6


def test_real_scope_handoff_is_complete_bookkeeping_not_complete_identity_or_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, output, _ = _published(tmp_path, monkeypatch)
    before = (_tree(source), _tree(output))
    handoff = downstream.build_retained_2006_handoff(source, output)
    quarter, selected, partial, pilot = (
        handoff["quarter"], handoff["selected_scope"],
        handoff["retained_82_partial_scope"], handoff["pilot"],
    )
    assert quarter["submission_count"] == quarter["quarantined_count"] == 6
    assert selected["expected_periods"] == selected["loaded_periods"] == ["2006Q1"]
    assert selected["missing_periods"] == []
    assert selected["loaded_scope_complete"] is True
    assert selected["source_identity_complete"] is False
    assert selected["source_identity_sha256"] is None
    assert len(partial["expected_periods"]) == 82
    assert partial["loaded_periods"] == ["2006Q1"]
    assert len(partial["missing_periods"]) == 81
    assert partial["loaded_scope_complete"] is False
    assert partial["source_identity_complete"] is False
    assert partial["source_identity_sha256"] is None
    assert pilot["row_count"] == pilot["quarantined_count"] == 6
    assert pilot["source_only_admitted_count"] == 0
    assert pilot["event_eligibility"] == "not_evaluated"
    assert pilot["candidate_signal_count"] is None
    pipeline = handoff["backtest_pipeline"]
    assert pipeline["submission_count"] == pipeline["quarantined_count"] == 6
    assert pipeline["relevant_form4_count"] == 2
    assert pipeline["relevant_form4_identity_complete"] is False
    assert pipeline["eligible_events_evaluated"] is False
    assert pipeline["admitted_event_count"] == 0
    assert pipeline["backtesting_ready"] is False
    assert pipeline["coverage_sha256"] == hash_payload(quarter)
    assert len(pipeline["missing_evidence"]) == 4
    assert all(value is False or type(value) is int and value == 0
               for value in handoff["authority"].values())
    assert len(canonical_json(handoff).encode("utf-8")) < 64 * 1024
    assert "Invented one-quarter issuer" not in canonical_json(handoff)
    assert (_tree(source), _tree(output)) == before


@pytest.mark.parametrize("pin", [
    "EXPECTED_COMPLETION_SHA256", "EXPECTED_ASSESSMENT_SHA256",
    "EXPECTED_ASSESSMENT_BYTES", "PRODUCER_COMMIT",
    "PRODUCER_SOURCE_INVENTORY_SHA256",
])
def test_wrong_expected_artifact_or_producer_pin_refuses_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pin: str,
) -> None:
    source, output, _ = _published(tmp_path, monkeypatch)
    value = getattr(downstream, pin)
    changed = value + 1 if type(value) is int else "d" * len(value)
    monkeypatch.setattr(downstream, pin, changed)
    _refused_without_change(source, output)


@pytest.mark.parametrize("pin,bad", [
    ("EXPECTED_ASSESSMENT_BYTES", True),
    ("EXPECTED_ASSESSMENT_BYTES", 0),
    ("EXPECTED_ASSESSMENT_SHA256", None),
    ("EXPECTED_COMPLETION_SHA256", "A" * 64),
    ("PRODUCER_COMMIT", True),
    ("PRODUCER_COMMIT", "b" * 39),
    ("PRODUCER_SOURCE_INVENTORY_SHA256", ""),
])
def test_malformed_expected_binding_is_a_typed_read_only_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pin: str, bad,
) -> None:
    source, output, _ = _published(tmp_path, monkeypatch)
    monkeypatch.setattr(downstream, pin, bad)
    _refused_without_change(source, output)


@pytest.mark.parametrize("target", ["raw", "parsed"])
def test_corrupt_committed_snapshot_is_not_recovered_by_loader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str,
) -> None:
    source, output, receipt = _published(tmp_path, monkeypatch)
    if target == "raw":
        directory = output / "ib1a" / receipt["raw_snapshot_id"]
        artifact = next(path for path in directory.iterdir() if path.name.endswith(".zip"))
    else:
        artifact = output / "ib1b" / receipt["parsed_snapshot_id"] / "rows.jsonl"
    artifact.write_bytes(artifact.read_bytes() + b"changed")
    _refused_without_change(source, output)


@pytest.mark.parametrize("change", [
    "drop", "reorder", "quarantine_reason", "raw_cik", "raw_date",
    "accession", "ordinal", "source_row_id", "canonical", "identity_digest",
    "authority_integer_false", "count_boolean", "extra_field", "wrong_epoch",
])
def test_self_rehashed_assessment_cannot_replace_raw_bound_all_row_accounting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str,
) -> None:
    source, output, _ = _published(tmp_path, monkeypatch)

    def alter(body):
        row = body["rows"][2]
        if change == "drop":
            body["rows"].pop()
        elif change == "reorder":
            body["rows"].reverse()
        elif change == "quarantine_reason":
            row["quarantine_reasons"] = ["invented_reason"]
        elif change == "raw_cik":
            row["raw_issuer_cik"] = "0000123456"
            row["short_cik"] = False
        elif change == "raw_date":
            row["raw_filing_date"] = "2006-01-15"
        elif change == "accession":
            row["accession_number"] = "0000123456-06-000003"
            row["accession_year_mismatch"] = False
        elif change == "ordinal":
            row["source_record_ordinal"] = 99
        elif change == "source_row_id":
            row["submission_row_id"] = "d" * 64
        elif change == "canonical":
            body["authority"]["canonical_evidence"] = True
        elif change == "identity_digest":
            body["whole_quarter_identity_sha256"] = "d" * 64
        elif change == "authority_integer_false":
            body["authority"]["source_authenticated"] = 0
        elif change == "count_boolean":
            body["corroborated_count"] = False
        elif change == "extra_field":
            body["unbound"] = None
        else:
            body["evidence_epoch"] = "invented-evidence-epoch"
        body["accounting_sha256"] = hash_payload(body["rows"])

    _rewrite_envelope(output / "assessment.json", alter)
    _rebind_changed_assessment(output)
    _repin(monkeypatch, output)
    _refused_without_change(source, output)


@pytest.mark.parametrize("change", [
    "producer_commit", "producer_inventory", "authority_integer_false",
    "count_boolean", "form_counts", "profile", "raw_lineage", "parsed_lineage",
    "census", "selection_scope", "extra_field",
])
def test_self_rehashed_completion_cannot_override_rederived_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str,
) -> None:
    source, output, _ = _published(tmp_path, monkeypatch)

    def alter(body):
        receipt, snapshot = body["receipt"], body["quarter_snapshot"]
        if change == "producer_commit":
            receipt["parser_commit"] = "d" * 40
        elif change == "producer_inventory":
            receipt["source_inventory_sha256"] = "d" * 64
        elif change == "authority_integer_false":
            receipt["source_authenticated"] = 0
        elif change == "count_boolean":
            receipt["quarters_assessed"] = True
        elif change == "form_counts":
            snapshot["document_forms"]["3"] = 0
            snapshot["document_forms"]["4"] = 2
        elif change == "profile":
            receipt["schema_profile_sha256"] = "d" * 64
        elif change == "raw_lineage":
            snapshot["raw_lineage_sha256"] = "d" * 64
        elif change == "parsed_lineage":
            snapshot["parsed_lineage_sha256"] = "d" * 64
        elif change == "census":
            receipt["census_quarter_sha256"] = "d" * 64
        elif change == "selection_scope":
            body["selection_scanned_quarters"] = 82
        else:
            body["unbound"] = None

    _rewrite_envelope(output / "completion.json", alter)
    _repin(monkeypatch, output)
    _refused_without_change(source, output)


@pytest.mark.parametrize("leaf", ["assessment.json", "completion.json"])
@pytest.mark.parametrize("kind", ["missing", "truncated", "noncanonical"])
def test_missing_or_malformed_envelope_is_never_recovered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, leaf: str, kind: str,
) -> None:
    source, output, _ = _published(tmp_path, monkeypatch)
    path = output / leaf
    if kind == "missing":
        path.unlink()
    elif kind == "truncated":
        path.write_bytes(path.read_bytes()[:50])
    else:
        path.write_bytes(b" " + path.read_bytes())
    _refused_without_change(source, output)


@pytest.mark.parametrize("leaf", ["assessment.json", "completion.json", "2006q1_form345.zip"])
@pytest.mark.parametrize("kind", ["symlink", "hardlink"])
def test_source_or_assessment_alias_refuses_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, leaf: str, kind: str,
) -> None:
    source, output, _ = _published(tmp_path, monkeypatch)
    path = (source if leaf.endswith(".zip") else output) / leaf
    original = tmp_path / (leaf + ".outside")
    path.rename(original)
    if kind == "symlink":
        path.symlink_to(original)
    else:
        os.link(original, path)
    before = original.read_bytes()
    _refused_without_change(source, output)
    assert original.read_bytes() == before


@pytest.mark.parametrize("residue", ["foreign.bin", ".assessment.json.aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.tmp"])
def test_unbound_namespace_or_temp_is_preserved_not_recovered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, residue: str,
) -> None:
    source, output, _ = _published(tmp_path, monkeypatch)
    (output / residue).write_bytes(b"preserve unknown bytes")
    _refused_without_change(source, output)


def test_profile_drift_cannot_reuse_original_artifact_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, output, _ = _published(tmp_path, monkeypatch)
    profile = build_retained_82q_schema_profile_candidate()
    monkeypatch.setattr(preparation, "build_retained_82q_schema_profile_candidate",
                        lambda: replace(profile, profile_id="unreviewed"))
    _refused_without_change(source, output)


def test_changed_input_archive_refuses_without_touching_preparation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, output, _ = _published(tmp_path, monkeypatch)
    path = source / "2006q1_form345.zip"
    path.write_bytes(path.read_bytes() + b"changed")
    _refused_without_change(source, output)


def test_census_count_drift_is_not_another_loaded_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, output, _ = _published(tmp_path, monkeypatch)
    original = preparation._census_quarter

    def altered(*args):
        return replace(original(*args), form_counts=(2, 1, 1, 1, 1, 1))

    monkeypatch.setattr(preparation, "_census_quarter", altered)
    _refused_without_change(source, output)
