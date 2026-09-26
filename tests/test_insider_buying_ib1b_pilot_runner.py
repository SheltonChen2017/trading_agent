"""Synthetic-only integration and refusal pins for bounded IB-1B composition."""
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import zipfile

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying.sec_bulk_snapshot import ALLOWED_SEC_TABLES, SecBulkSnapshotError
from research.insider_buying.sec_bulk_parsed_snapshot import SecBulkParsedSnapshotError
from research.insider_buying.sec_ib1b_pilot_profile import (
    Ib1bPilotProfileError,
    approved_ib1b_archive_bindings,
    approved_ib1b_schema_profile,
)
from scripts import insider_buying_ib1b_pilot as runner


PARSER_COMMIT = "b" * 40
FORMS = ("3", "3/A", "4", "4/A", "5", "5/A", "UNKNOWN")


def _fixture_archive(binding, profile, *, defect=None):
    tables = {}
    receipts = []
    accessions = [f"0000123456-{binding.year % 100:02d}-{ordinal:06d}" for ordinal in range(1, 8)]
    for table in ALLOWED_SEC_TABLES:
        headers = profile.variant_for(table, binding.year, binding.quarter).headers
        rows = []
        for index, accession in enumerate(accessions):
            values = {name: "" for name in headers}
            values["ACCESSION_NUMBER"] = accession
            if table == "SUBMISSION.tsv":
                values.update(
                    FILING_DATE=f"{binding.year}-{'12' if binding.quarter == 4 else '03'}-01",
                    PERIOD_OF_REPORT=f"{binding.year}-{'11' if binding.quarter == 4 else '02'}-28",
                    DOCUMENT_TYPE=FORMS[index], ISSUERCIK="0000123456",
                    ISSUERNAME="Synthetic private row contents", ISSUERTRADINGSYMBOL="SYN",
                )
            elif table == "REPORTINGOWNER.tsv":
                values["RPTOWNERCIK"] = "0000000007"
            elif table in {"NONDERIV_TRANS.tsv", "DERIV_TRANS.tsv"}:
                values[table.removesuffix(".tsv") + "_SK"] = str(index + 1)
            rows.append(tuple(values[name] for name in headers))
        if table == "REPORTINGOWNER.tsv":
            rows.append(rows[0])  # No additional CIK uniqueness is inferred.
        if defect == "duplicate_submission" and table == "SUBMISSION.tsv":
            rows.append(rows[0])
        if defect in {"duplicate_transaction", "blank_transaction"} and table == "NONDERIV_TRANS.tsv":
            if defect == "duplicate_transaction":
                rows.append(rows[0])
            else:
                row = list(rows[0])
                row[headers.index("NONDERIV_TRANS_SK")] = ""
                rows[0] = tuple(row)
        header = ("\t".join(headers) + "\n").encode("ascii")
        content = header + "".join("\t".join(row) + "\n" for row in rows).encode("utf-8")
        tables[table] = content
        observed = next(item for item in binding.header_receipts if item.table_name == table)
        receipts.append(replace(observed, expanded_size_bytes=len(content)))
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in tables.items():
            archive.writestr(name, content)
        prefix = "insider_transactions" if binding.year == 2022 else "FORM_345"
        archive.writestr(prefix + "_metadata.json", b"{}\n")
        archive.writestr(prefix + "_readme.htm", b"<p>synthetic</p>\n")
    raw = stream.getvalue()
    return raw, replace(
        binding, archive_sha256=hash_bytes(raw), archive_size_bytes=len(raw),
        header_receipts=tuple(receipts),
    )


@pytest.fixture
def pilot(tmp_path):
    # Resolve the test framework's own temp alias, not user-supplied paths.
    root = tmp_path.resolve()
    source = root / "inputs"
    source.mkdir()
    profile = approved_ib1b_schema_profile()
    bindings = []
    for binding in approved_ib1b_archive_bindings():
        raw, synthetic_binding = _fixture_archive(binding, profile)
        (source / binding.filename).write_bytes(raw)
        bindings.append(synthetic_binding)
    return source, root / "outputs", tuple(bindings), profile


def _run(pilot):
    source, destination, bindings, profile = pilot
    return runner._run_ib1b_pilot(
        source, destination, PARSER_COMMIT, bindings=bindings, profile=profile,
    )


def test_synthetic_both_header_eras_replay_all_tables_and_forms(pilot):
    report = _run(pilot)
    envelope = json.loads(report.read_bytes())
    payload = envelope["payload"]
    digest = hash_payload(payload)
    assert set(envelope) == {"payload", "payload_sha256"}
    assert envelope["payload_sha256"] == digest
    assert report.name == f"ib1b-pilot-report-{digest}.json"
    assert report.read_bytes() == (canonical_json(envelope) + "\n").encode()
    assert payload["canonical"] is False
    assert payload["point_in_time_data"] is False
    assert payload["archive_counts"] == {"accepted": 2, "refused": 0, "quarantined": 0}
    assert all(value == (0 if name.endswith("looks") else False) for name, value in payload["authority"].items())
    for quarter, binding in zip(payload["quarters"], pilot[2], strict=True):
        assert quarter["counts"] == {
            "rows": 57, "accessions": 7,
            "document_forms": {"3": 1, "3/A": 1, "4": 1, "4/A": 1, "5": 1, "5/A": 1, "OTHER": 1},
        }
        assert tuple(item["table_name"] for item in quarter["ib1b"]["tables"]) == ALLOWED_SEC_TABLES
        assert quarter["timestamp_evidence"]["original_local_last_write_utc"] == binding.local_last_write_utc
        assert quarter["timestamp_evidence"]["basis"] == "filesystem_last_write_unverified"
        assert quarter["timestamp_evidence"]["legacy_field_is_verified_retrieval"] is False
        assert quarter["timestamp_evidence"]["legacy_ib1a_retrieved_at_utc_representation"].endswith("+00:00")
        assert quarter["ib1b"]["raw_snapshot_id"] == quarter["ib1a"]["snapshot_id"]
    assert "AFF10B5ONE" not in payload["quarters"][0]["ib1b"]["tables"][0]["headers"]
    assert payload["quarters"][1]["ib1b"]["tables"][0]["headers"][-1] == "AFF10B5ONE"
    assert b"Synthetic private row contents" not in report.read_bytes()
    assert not list(pilot[1].glob("*.tmp"))


@pytest.mark.parametrize("acknowledgement", [False, None, 0, 1, "yes"])
def test_public_review_acknowledgement_refuses_before_io(monkeypatch, acknowledgement):
    def forbidden(*args, **kwargs):
        pytest.fail("I/O core must not be reached")
    monkeypatch.setattr(runner, "_run_ib1b_pilot", forbidden)
    with pytest.raises(runner.Ib1bPilotError, match="acknowledged before I/O"):
        runner.run_approved_ib1b_pilot("unused", "unused", PARSER_COMMIT, reviewed_preparation=acknowledgement)


def test_public_entry_refuses_synthetic_sources(pilot):
    with pytest.raises(runner.Ib1bPilotError, match="exact hash/size"):
        runner.run_approved_ib1b_pilot(pilot[0], pilot[1], PARSER_COMMIT, reviewed_preparation=True)
    assert not pilot[1].exists()


def test_public_factory_override_cannot_bypass_literal_binding(monkeypatch, pilot):
    monkeypatch.setattr(runner, "approved_ib1b_archive_bindings", lambda: pilot[2])
    with pytest.raises(Ib1bPilotProfileError, match="fingerprint"):
        runner.run_approved_ib1b_pilot(pilot[0], pilot[1], PARSER_COMMIT, reviewed_preparation=True)
    assert not pilot[1].exists()


@pytest.mark.parametrize("commit", [True, "b" * 39, "B" * 40, " b" + "b" * 39])
def test_parser_commit_refusal_precedes_outputs(pilot, commit):
    with pytest.raises(runner.Ib1bPilotError, match="Git commit"):
        runner._run_ib1b_pilot(pilot[0], pilot[1], commit, bindings=pilot[2], profile=pilot[3])
    assert not pilot[1].exists()


def test_window_refusal_precedes_outputs(pilot):
    with pytest.raises(runner.Ib1bPilotError, match="two-quarter window"):
        runner._run_ib1b_pilot(pilot[0], pilot[1], PARSER_COMMIT, bindings=pilot[2][::-1], profile=pilot[3])
    assert not pilot[1].exists()


@pytest.mark.parametrize("defect", ["duplicate_submission", "duplicate_transaction", "blank_transaction"])
def test_existing_accession_and_transaction_integrity_refuses_without_partial_report(pilot, defect):
    source, destination, bindings, profile = pilot
    raw, second = _fixture_archive(bindings[1], profile, defect=defect)
    (source / second.filename).write_bytes(raw)
    with pytest.raises(SecBulkParsedSnapshotError):
        runner._run_ib1b_pilot(source, destination, PARSER_COMMIT, bindings=(bindings[0], second), profile=profile)
    assert not list(destination.glob("ib1b-pilot-report-*.json"))
    assert list((destination / "ib1b").glob("sec-*"))  # First immutable quarter retained.
    assert not (destination / ".ib1b-pilot.running").exists()


@pytest.mark.parametrize("overlap", ["same", "descendant", "ancestor", "repository"])
def test_output_overlap_refused(pilot, overlap):
    source, _, bindings, profile = pilot
    destination = {
        "same": source, "descendant": source / "child", "ancestor": source.parent,
        "repository": Path(runner.__file__).resolve().parents[1] / "blocked-ib1b-test-output",
    }[overlap]
    with pytest.raises(runner.Ib1bPilotError, match="overlap"):
        runner._run_ib1b_pilot(source, destination, PARSER_COMMIT, bindings=bindings, profile=profile)


@pytest.mark.parametrize("overlap", ["input_alias", "repository_alias"])
def test_output_overlap_refused_through_a_case_variant_alias(pilot, overlap):
    # macOS volumes are case-insensitive by default, so a differently cased
    # spelling of an input or repository directory is the same directory.
    source, _, bindings, profile = pilot
    repository = Path(runner.__file__).resolve().parents[1]
    target = source if overlap == "input_alias" else repository
    alias = target.parent / target.name.swapcase()
    if alias == target or not alias.exists() or not os.path.samefile(alias, target):
        pytest.skip("filesystem is case-sensitive; no alias spelling exists")
    destination = alias / "blocked-ib1b-test-output"
    with pytest.raises(runner.Ib1bPilotError, match="overlap"):
        runner._run_ib1b_pilot(source, destination, PARSER_COMMIT, bindings=bindings, profile=profile)
    assert not destination.exists()


def test_relative_output_refused(pilot):
    with pytest.raises(runner.Ib1bPilotError, match="absolute"):
        runner._run_ib1b_pilot(pilot[0], "relative", PARSER_COMMIT, bindings=pilot[2], profile=pilot[3])


def test_no_overwrite_of_populated_output(pilot):
    _run(pilot)
    with pytest.raises(runner.Ib1bPilotError, match="fresh or empty"):
        _run(pilot)


def test_input_symlink_refused(pilot):
    source, _, bindings, _ = pilot
    original = source / bindings[0].filename
    target = source / "synthetic-backing.zip"
    original.rename(target)
    original.symlink_to(target)
    with pytest.raises(SecBulkSnapshotError, match="regular immutable"):
        _run(pilot)
    assert not pilot[1].exists()


def test_output_ancestor_redirect_refused(pilot):
    alias = pilot[0].parent / "alias"
    alias.symlink_to(pilot[0].parent, target_is_directory=True)
    with pytest.raises(runner.Ib1bPilotError, match="redirect"):
        runner._run_ib1b_pilot(pilot[0], alias / "outputs", PARSER_COMMIT, bindings=pilot[2], profile=pilot[3])


def test_header_receipt_size_drift_refused_before_publication(pilot):
    altered = replace(pilot[2][1], header_receipts=(
        replace(pilot[2][1].header_receipts[0], expanded_size_bytes=pilot[2][1].header_receipts[0].expanded_size_bytes + 1),
        *pilot[2][1].header_receipts[1:],
    ))
    with pytest.raises(runner.Ib1bPilotError, match="expanded table size"):
        runner._run_ib1b_pilot(pilot[0], pilot[1], PARSER_COMMIT, bindings=(pilot[2][0], altered), profile=pilot[3])
    assert not pilot[1].exists()


def test_unavailable_report_platform_refuses_before_source_io(monkeypatch, pilot):
    monkeypatch.setattr(runner.os, "supports_dir_fd", set())
    monkeypatch.setattr(runner, "_read_bound_archive", lambda *args: pytest.fail("source I/O reached"))
    with pytest.raises(runner.Ib1bPilotError, match="platform lacks"):
        _run(pilot)


def test_report_publication_refuses_path_open_root_redirect(monkeypatch, tmp_path):
    destination = tmp_path.resolve() / "destination"
    outside = tmp_path.resolve() / "outside"
    destination.mkdir()
    outside.mkdir()
    original_open = Path.open
    def redirect(path, *args, **kwargs):
        if path.parent == destination and path.suffix == ".tmp":
            destination.rename(destination.with_name("detached"))
            destination.symlink_to(outside, target_is_directory=True)
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", redirect)
    # Descriptor publication never invokes this vulnerable path-based hook.
    report = runner._publish_report(destination, {"synthetic": True})
    assert report.parent == destination and report.is_file()
    assert not list(outside.iterdir())
    assert not destination.is_symlink()


def test_report_publication_refuses_post_anchor_root_redirect(monkeypatch, tmp_path):
    destination = tmp_path.resolve() / "destination"
    outside = tmp_path.resolve() / "outside"
    destination.mkdir()
    outside.mkdir()
    original_link = os.link
    def redirect(*args, **kwargs):
        destination.rename(destination.with_name("detached"))
        destination.symlink_to(outside, target_is_directory=True)
        return original_link(*args, **kwargs)
    monkeypatch.setattr(os, "link", redirect)
    monkeypatch.setattr(os, "supports_dir_fd", {*os.supports_dir_fd, redirect})
    with pytest.raises(runner.Ib1bPilotError, match="redirect|changed"):
        runner._publish_report(destination, {"synthetic": True})
    assert not list(outside.iterdir())
    assert not list(destination.with_name("detached").glob("*.tmp"))


def test_report_immutable_same_path_not_overwritten(tmp_path):
    destination = tmp_path.resolve()
    report = runner._publish_report(destination, {"synthetic": True})
    before = report.read_bytes()
    with pytest.raises(runner.Ib1bPilotError, match="could not be published"):
        runner._publish_report(destination, {"synthetic": True})
    assert report.read_bytes() == before


def test_replaced_running_marker_is_preserved_and_run_refused(monkeypatch, pilot):
    original_publish = runner._publish_report
    marker = pilot[1] / ".ib1b-pilot.running"
    def replace_marker(*args, **kwargs):
        marker.unlink()
        marker.write_bytes(b"foreign replacement")
        return original_publish(*args, **kwargs)
    monkeypatch.setattr(runner, "_publish_report", replace_marker)
    with pytest.raises(runner.Ib1bPilotError, match="replaced pilot marker"):
        _run(pilot)
    assert marker.read_bytes() == b"foreign replacement"
    # A late cleanup refusal can leave complete artifacts; it is not acceptance.
    assert len(list(pilot[1].glob("ib1b-pilot-report-*.json"))) == 1


def test_operational_envelope_is_not_a_standalone_acceptance_boundary():
    # A coherent hash is identity, not authentication or raw-row replay. Only
    # the reviewed IB-1A/B loaders validate the actual stage publications.
    assert not hasattr(runner, "load_approved_ib1b_pilot_report")
    assert not hasattr(runner, "_load_ib1b_pilot_report")


def test_cli_requires_all_explicit_inputs_and_no_synthetic_switch():
    with pytest.raises(SystemExit) as caught:
        runner.main(["--allow-synthetic"])
    assert caught.value.code == 2


def _rewrite_member(raw: bytes, name: str, transform) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as source, zipfile.ZipFile(
        stream, "w", compression=zipfile.ZIP_DEFLATED
    ) as target:
        for info in source.infolist():
            content = source.read(info)
            target.writestr(info.filename, transform(content) if info.filename == name else content)
    return stream.getvalue()


def test_physical_header_drift_refuses_in_preflight_before_any_output(pilot):
    # The receipt still matches the approved profile; only the ZIP's physical
    # header line differs (two same-length columns swapped). Preflight must
    # refuse before IB-1A publishes anything, not leave it to IB-1B later.
    source, destination, bindings, profile = pilot
    binding = bindings[0]
    path = source / binding.filename

    def swap_first_two_columns(content: bytes) -> bytes:
        header, rest = content.split(b"\n", 1)
        columns = header.split(b"\t")
        columns[1], columns[2] = columns[2], columns[1]
        return b"\t".join(columns) + b"\n" + rest

    raw = _rewrite_member(path.read_bytes(), "SUBMISSION.tsv", swap_first_two_columns)
    path.write_bytes(raw)
    altered = replace(binding, archive_sha256=hash_bytes(raw), archive_size_bytes=len(raw))
    with pytest.raises(runner.Ib1bPilotError, match="physical header"):
        runner._run_ib1b_pilot(
            source, destination, PARSER_COMMIT, bindings=(altered, bindings[1]), profile=profile,
        )
    assert not destination.exists()


def test_expanded_size_budget_refuses_in_preflight_before_any_output(monkeypatch, pilot):
    source, destination, bindings, profile = pilot
    declared = sum(item.expanded_size_bytes for item in bindings[0].header_receipts)
    # Only the runner's preflight constant is lowered; IB-1B's own cap is
    # untouched, so without the preflight the pipeline would succeed.
    monkeypatch.setattr(runner, "MAX_TOTAL_PARSED_INPUT_BYTES", declared - 1)
    with pytest.raises(runner.Ib1bPilotError, match="exceeds the unchanged IB-1B limit"):
        _run(pilot)
    assert not destination.exists()


def test_output_appearing_during_preflight_refuses_without_adopting_it(monkeypatch, pilot):
    source, destination, bindings, profile = pilot
    original_read = runner._read_bound_archive
    foreign = destination / "foreign.txt"

    def read_and_intrude(*args, **kwargs):
        if not destination.exists():
            destination.mkdir()
            foreign.write_bytes(b"not this run's output")
        return original_read(*args, **kwargs)

    monkeypatch.setattr(runner, "_read_bound_archive", read_and_intrude)
    with pytest.raises(runner.Ib1bPilotError, match="fresh or empty"):
        _run(pilot)
    assert foreign.read_bytes() == b"not this run's output"
    assert sorted(item.name for item in destination.iterdir()) == ["foreign.txt"]


def test_source_receipt_mutated_during_processing_refuses_without_report(monkeypatch, pilot):
    source, destination, bindings, profile = pilot
    original_write = runner.write_sec_bulk_snapshot
    calls = []

    def write_then_mutate(*args, **kwargs):
        result = original_write(*args, **kwargs)
        if not calls:
            object.__setattr__(bindings[1], "local_last_write_utc", "2026-09-24T22:53:38.0000000Z")
        calls.append(1)
        return result

    monkeypatch.setattr(runner, "write_sec_bulk_snapshot", write_then_mutate)
    with pytest.raises(runner.Ib1bPilotError, match="source receipts changed"):
        _run(pilot)
    assert not list(destination.glob("ib1b-pilot-report-*.json"))


def test_report_above_its_byte_cap_refuses_without_publication(monkeypatch, pilot):
    monkeypatch.setattr(runner, "MAX_REPORT_BYTES", 1024)
    with pytest.raises(runner.Ib1bPilotError, match="byte-size cap"):
        _run(pilot)
    assert not list(pilot[1].glob("ib1b-pilot-report-*.json"))
    assert not list(pilot[1].glob(".ib1b-pilot-report-*.tmp"))


def test_publication_refuses_a_target_that_is_not_its_complete_temporary(monkeypatch, tmp_path):
    destination = tmp_path.resolve() / "destination"
    destination.mkdir()
    original_link = os.link

    def substitute(src, dst, *, src_dir_fd=None, dst_dir_fd=None, follow_symlinks=True):
        descriptor = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=dst_dir_fd)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(b"substituted")

    monkeypatch.setattr(os, "link", substitute)
    monkeypatch.setattr(os, "supports_dir_fd", {*os.supports_dir_fd, substitute})
    with pytest.raises(runner.Ib1bPilotError, match="differs from its complete temporary"):
        runner._publish_report(destination, {"synthetic": True})
    assert original_link is not substitute
