"""One-shot v3 ambiguity diagnostic: invented parents and offline transport only."""
from __future__ import annotations

import json
import os

import pytest

from data.hashing import hash_bytes, hash_payload
from research.insider_buying_sec_all_form4_parent_campaign import CampaignRequest
from research.insider_buying_sec_complete_acquisition import SecHttpResult
from research.insider_buying_sec_all_form4_parent_recovery_partial_verifier import (
    VerifiedPartialV3Receipt,
)
import research.insider_buying_sec_all_form4_parent_ambiguous_diagnostic as diagnostic


CONTACT = "invented@example.test"
COMMIT = "d" * 40


def _request() -> CampaignRequest:
    accession = "0000000001-23-000001"
    return CampaignRequest(
        period="2023Q1", accession_number=accession, form_type="4",
        filing_date="2023-01-03", issuer_cik="0000000001",
        archive_path=f"edgar/data/1/{accession}.txt",
        submission_row_id="a" * 64, parsed_lineage_hash="b" * 64,
        master_source_sha256="c" * 64,
    )


def _receipt(tmp_path) -> VerifiedPartialV3Receipt:
    root = tmp_path / "stopped-v3"
    root.mkdir()
    request = _request()
    return VerifiedPartialV3Receipt(
        pending_request=request,
        pending_request_sha256=hash_payload(request.to_payload()),
        pending_global_index=20_000,
        pending_attempt_number=1,
        pending_shard_name="shard-0002",
        v3_root=root,
        capture_git_commit="a" * 40,
        root_plan_sha256="1" * 64,
        source_plan_sha256="2" * 64,
        pending_shard_inventory_sha256="3" * 64,
        pending_shard_journal_sha256="4" * 64,
        pending_attempt_start_sha256="5" * 64,
        completed_new_count=1_846,
        attempt_count=1_847,
        source_assignment_sha256="6" * 64,
    )


def _parent(request: CampaignRequest) -> bytes:
    filed = request.filing_date.replace("-", "")
    accession = request.accession_number
    return (
        f"<SEC-DOCUMENT>{accession}.txt : {filed}\n"
        f"<SEC-HEADER>{accession}.hdr.sgml : {filed}\n"
        f"<ACCEPTANCE-DATETIME>{filed}101112\n"
        f"<ACCESSION-NUMBER>{accession}\n"
        f"<TYPE>4\n<FILING-DATE>{filed}\n"
        "<REPORTING-OWNER>\n<OWNER-DATA>\n<CIK>0000000002\n"
        "<CONFORMED-NAME>Invented Owner\n</OWNER-DATA>\n</REPORTING-OWNER>\n"
        "<ISSUER>\n<COMPANY-DATA>\n<CIK>0000000001\n"
        "</COMPANY-DATA>\n</ISSUER>\n</SEC-HEADER>\n"
    ).encode("ascii")


def _read(path):
    return json.loads(path.read_bytes())


def _capture(tmp_path, receipt, transport):
    return diagnostic._capture_one(
        receipt, tmp_path / "one-shot-v3-ambiguity",
        transport=transport, contact_email=CONTACT,
        capture_git_commit=COMMIT,
        protected_roots=(receipt.v3_root,),
    )


def test_valid_duplicate_is_one_shot_and_binds_exact_v3_start(tmp_path):
    receipt = _receipt(tmp_path)
    body = _parent(receipt.pending_request)
    seen = []

    def transport(url, headers, bound):
        seen.append(url)
        output = tmp_path / "one-shot-v3-ambiguity"
        assert (output / "manifest.json").is_file()
        assert (output / "attempt-start.json").is_file()
        assert headers["User-Agent"].endswith(f"({CONTACT})")
        assert bound == diagnostic.MAX_COMPLETE_TXT_BYTES
        return SecHttpResult(200, (("Content-Length", str(len(body))),), body)

    report_path = _capture(tmp_path, receipt, transport)
    output = report_path.parent
    report = _read(report_path)
    manifest = _read(output / "manifest.json")
    response = _read(output / "response.json")
    assert seen == [receipt.pending_request.url]
    assert manifest["ambiguous_request_sha256"] == receipt.pending_request_sha256
    assert manifest["pending_attempt_start_sha256"] == receipt.pending_attempt_start_sha256
    assert manifest["pending_shard_journal_sha256"] == receipt.pending_shard_journal_sha256
    assert manifest["maximum_additional_dispatches"] == 1
    assert manifest["possible_duplicate_of_ambiguous_v3_start"] is True
    assert report["envelope_outcome"] == "accepted"
    assert report["v3_campaign_advanced"] is False
    assert report["source_authenticated"] is False
    assert report["point_in_time_data"] is False
    assert report["qc_jobs"] == report["outcome_looks"] == 0
    assert response["body_sha256"] == hash_bytes(body)
    assert (output / "objects" / f"{hash_bytes(body)}.bin").read_bytes() == body
    assert _read(output / "commit.json")["report_sha256"] == hash_bytes(report_path.read_bytes())
    public_metadata = b"".join(path.read_bytes() for path in output.glob("*.json"))
    assert receipt.pending_request.accession_number.encode() not in public_metadata
    assert CONTACT.encode() not in public_metadata
    with pytest.raises(diagnostic.AmbiguousParentDiagnosticError, match="already exists"):
        _capture(tmp_path, receipt, lambda *_: pytest.fail("second SEC dispatch"))
    assert seen == [receipt.pending_request.url]


def test_network_error_is_a_consumed_diagnostic_not_permission_to_retry(tmp_path):
    receipt = _receipt(tmp_path)
    seen = []

    def transport(*_):
        seen.append(1)
        raise OSError("invented TLS reset")

    report = _read(_capture(tmp_path, receipt, transport))
    assert report["transport_outcome"] == "network_error"
    assert report["envelope_outcome"] == "not_checked"
    assert report["body_sha256"] is None
    with pytest.raises(diagnostic.AmbiguousParentDiagnosticError, match="already exists"):
        _capture(tmp_path, receipt, lambda *_: pytest.fail("second SEC dispatch"))
    assert seen == [1]


def test_interruption_after_start_consumes_one_shot_even_without_report(tmp_path):
    receipt = _receipt(tmp_path)
    output = tmp_path / "one-shot-v3-ambiguity"

    def interrupt(*_):
        assert (output / "attempt-start.json").is_file()
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        _capture(tmp_path, receipt, interrupt)
    assert (output / "manifest.json").is_file()
    assert not (output / "commit.json").exists()
    with pytest.raises(diagnostic.AmbiguousParentDiagnosticError, match="already exists"):
        _capture(tmp_path, receipt, lambda *_: pytest.fail("second SEC dispatch"))


def test_invalid_200_is_retained_but_not_accepted(tmp_path):
    receipt = _receipt(tmp_path)
    body = b"invented bounded body with no SEC parent envelope"
    report_path = _capture(
        tmp_path, receipt,
        lambda *_: SecHttpResult(200, (("Content-Length", str(len(body))),), body),
    )
    assert _read(report_path)["envelope_outcome"] == "refused"
    assert (report_path.parent / "objects" / f"{hash_bytes(body)}.bin").read_bytes() == body


def test_non_200_preserves_status_without_body_or_campaign_advance(tmp_path):
    receipt = _receipt(tmp_path)
    report_path = _capture(tmp_path, receipt, lambda *_: SecHttpResult(403, (), b""))
    report = _read(report_path)
    assert report["status"] == 403
    assert report["body_sha256"] is None
    assert report["v3_campaign_advanced"] is False
    assert list((report_path.parent / "objects").iterdir()) == []


def test_root_entry_is_fsynced_before_single_dispatch(tmp_path, monkeypatch):
    receipt = _receipt(tmp_path)
    parent_info = tmp_path.stat()
    synced = False
    original_fsync = os.fsync

    def fsync(descriptor):
        nonlocal synced
        info = os.fstat(descriptor)
        if (info.st_dev, info.st_ino) == (parent_info.st_dev, parent_info.st_ino):
            synced = True
        return original_fsync(descriptor)

    def transport(*_):
        assert synced
        return SecHttpResult(403, (), b"")

    monkeypatch.setattr(os, "fsync", fsync)
    _capture(tmp_path, receipt, transport)


def test_malformed_binding_and_contact_refuse_before_root_or_transport(tmp_path):
    from dataclasses import replace

    receipt = _receipt(tmp_path)
    output = tmp_path / "one-shot-v3-ambiguity"
    bad = replace(receipt, pending_request_sha256="0" * 64)
    with pytest.raises(diagnostic.AmbiguousParentDiagnosticError, match="REFUSED"):
        _capture(tmp_path, bad, lambda *_: pytest.fail("SEC dispatch"))
    assert not output.exists()
    with pytest.raises(diagnostic.AmbiguousParentDiagnosticError, match="REFUSED"):
        diagnostic._capture_one(
            receipt, output, transport=lambda *_: pytest.fail("SEC dispatch"),
            contact_email="bad\r\nheader@example.test", capture_git_commit=COMMIT,
            protected_roots=(receipt.v3_root,),
        )
    assert not output.exists()


def test_synthetic_seam_refuses_the_production_sec_transport_before_root(
    tmp_path, monkeypatch,
):
    receipt = _receipt(tmp_path)
    output = tmp_path / "one-shot-v3-ambiguity"

    def forbidden(*_):
        pytest.fail("production SEC transport reached through synthetic seam")

    monkeypatch.setattr(diagnostic, "_selected_sec_transport", forbidden)
    with pytest.raises(diagnostic.AmbiguousParentDiagnosticError, match="synthetic"):
        diagnostic._capture_one(
            receipt, output, transport=forbidden, contact_email=CONTACT,
            capture_git_commit=COMMIT, protected_roots=(receipt.v3_root,),
        )
    assert not output.exists()


def test_observed_mode_rechecks_clean_commit_after_durable_start_before_dispatch(
    tmp_path, monkeypatch,
):
    from dataclasses import replace

    receipt = replace(
        _receipt(tmp_path),
        capture_git_commit="aa0d635d00b64825bf8003289e0a60279bd52e73",
    )
    output = tmp_path / "one-shot-v3-ambiguity"
    checks = []

    def verify(_commit):
        checks.append(1)
        if len(checks) == 2:
            assert (output / "attempt-start.json").is_file()
            raise diagnostic.AmbiguousParentDiagnosticError("REFUSED: invented lane drift")

    def forbidden(*_):
        pytest.fail("observed SEC transport dispatched after lane drift")

    monkeypatch.setattr(diagnostic, "_OBSERVED_V3_ROOT", receipt.v3_root)
    monkeypatch.setattr(diagnostic, "_OBSERVED_DIAGNOSTIC_ROOT", output)
    monkeypatch.setattr(diagnostic, "_selected_sec_transport", forbidden)
    monkeypatch.setattr(diagnostic, "_verify_exact_committed_code", verify)
    with pytest.raises(diagnostic.AmbiguousParentDiagnosticError, match="lane drift"):
        diagnostic._capture_one(
            receipt, output, transport=forbidden, contact_email=CONTACT,
            capture_git_commit=COMMIT, protected_roots=(receipt.v3_root,),
            observed=True,
        )
    assert checks == [1, 1]
    assert (output / "attempt-start.json").is_file()
    assert not (output / "commit.json").exists()


# Section 119 (Claude review): every test in this file replaces the clean-lane
# check, so its own dirty-tree clause had no test.
def test_dirty_lane_is_not_an_exact_committed_diagnostic_state(monkeypatch):
    import research.insider_buying_sec_all_form4_parent_ambiguous_diagnostic as module

    commit = "c" * 40
    root = str(module._LANE_ROOT)

    def git_output(command, **_kwargs):
        if command == ("git", "rev-parse", "--show-toplevel"):
            return (root + "\n").encode()
        if command == ("git", "branch", "--show-current"):
            return b"codex/strategy-insider-buying\n"
        if command == ("git", "rev-parse", "HEAD"):
            return (commit + "\n").encode()
        if command == ("git", "status", "--porcelain=v1", "--untracked-files=all"):
            return b"?? invented-untracked-file\n"
        pytest.fail(f"dependency blobs were read on a dirty lane: {command!r}")

    monkeypatch.setattr(module.subprocess, "check_output", git_output)
    with pytest.raises(module.AmbiguousParentDiagnosticError,
                       match="exact clean committed Insider lane is required"):
        module._verify_exact_committed_code(commit)
