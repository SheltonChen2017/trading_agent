"""Offline acceptance tests for the one-shot v3 ambiguity diagnostic."""
from __future__ import annotations

from dataclasses import replace
import json
import os

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying_sec_all_form4_parent_campaign import CampaignRequest
from research.insider_buying_sec_all_form4_parent_recovery_partial_verifier import (
    VerifiedPartialV3Receipt,
)
from research.insider_buying_sec_complete_acquisition import SecHttpResult
import research.insider_buying_sec_all_form4_parent_ambiguous_diagnostic as capture
import research.insider_buying_sec_all_form4_parent_ambiguous_diagnostic_verifier as verify


_COMMIT = "d" * 40


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
    stopped = tmp_path / "stopped-v3"
    stopped.mkdir(mode=0o700)
    request = _request()
    return VerifiedPartialV3Receipt(
        pending_request=request,
        pending_request_sha256=hash_payload(request.to_payload()),
        pending_global_index=20_000, pending_attempt_number=1,
        pending_shard_name="shard-0002", v3_root=stopped,
        capture_git_commit="a" * 40, root_plan_sha256="1" * 64,
        source_plan_sha256="2" * 64,
        pending_shard_inventory_sha256="3" * 64,
        pending_shard_journal_sha256="4" * 64,
        pending_attempt_start_sha256="5" * 64,
        completed_new_count=1_846, attempt_count=1_847,
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
        "<TYPE>4\n"
        f"<FILING-DATE>{filed}\n"
        "<REPORTING-OWNER>\n<OWNER-DATA>\n<CIK>0000000002\n"
        "<CONFORMED-NAME>Invented Owner\n</OWNER-DATA>\n</REPORTING-OWNER>\n"
        "<ISSUER>\n<COMPANY-DATA>\n<CIK>0000000001\n"
        "</COMPANY-DATA>\n</ISSUER>\n</SEC-HEADER>\n"
    ).encode("ascii")


def _write_json(path, value):
    raw = (canonical_json(value) + "\n").encode("utf-8")
    path.write_bytes(raw)
    os.chmod(path, 0o600)
    return hash_bytes(raw)


def _accepted(tmp_path):
    receipt = _receipt(tmp_path)
    body = _parent(receipt.pending_request)
    calls = []

    def offline_transport(url, _headers, _bound):
        calls.append(url)
        return SecHttpResult(200, (("Content-Length", str(len(body))),), body)

    report_path = capture._capture_one(
        receipt, tmp_path / "one-shot-v3-ambiguity",
        transport=offline_transport, contact_email="invented@example.test",
        capture_git_commit=_COMMIT, protected_roots=(receipt.v3_root,),
    )
    assert calls == [receipt.pending_request.url]
    return receipt, report_path


def _verify(receipt, report_path):
    return verify.verify_accepted_ambiguity_diagnostic(
        receipt, report_path.parent, capture_git_commit=_COMMIT,
        expected_report_sha256=hash_bytes(report_path.read_bytes()),
    )


def _repin_report(report_path, report):
    root = report_path.parent
    report_path.unlink()
    raw = (canonical_json(report) + "\n").encode("utf-8")
    new_digest = hash_bytes(raw)
    new_path = root / f"diagnostic-report-{new_digest}.json"
    new_path.write_bytes(raw)
    os.chmod(new_path, 0o600)
    commit = json.loads((root / "commit.json").read_bytes())
    commit["report_name"] = new_path.name
    commit["report_sha256"] = new_digest
    _write_json(root / "commit.json", commit)
    return new_path


def test_accepts_one_exact_private_body_without_promoting_authority(tmp_path):
    receipt, report_path = _accepted(tmp_path)
    root = report_path.parent
    before = {str(path.relative_to(root)): hash_bytes(path.read_bytes())
              for path in root.rglob("*") if path.is_file()}
    checked = _verify(receipt, report_path)
    after = {str(path.relative_to(root)): hash_bytes(path.read_bytes())
             for path in root.rglob("*") if path.is_file()}
    assert after == before
    assert checked.report_sha256 == hash_bytes(report_path.read_bytes())
    assert checked.ambiguous_request_sha256 == receipt.pending_request_sha256
    assert checked.original_pending_start_sha256 == receipt.pending_attempt_start_sha256
    assert checked.body_sha256 == hash_bytes(_parent(receipt.pending_request))
    assert checked.body_size_bytes == len(_parent(receipt.pending_request))


@pytest.mark.parametrize("member", [
    "manifest.json", "attempt-start.json", "response.json", "report", "commit.json",
])
def test_any_changed_immutable_metadata_refuses_with_original_anchor(tmp_path, member):
    receipt, report_path = _accepted(tmp_path)
    path = report_path if member == "report" else report_path.parent / member
    value = json.loads(path.read_bytes())
    value["untrusted_extra"] = True
    _write_json(path, value)
    with pytest.raises(verify.AmbiguousDiagnosticVerificationError, match="REFUSED"):
        verify.verify_accepted_ambiguity_diagnostic(
            receipt, report_path.parent, capture_git_commit=_COMMIT,
            expected_report_sha256=report_path.name.split("-")[-1][:-5],
        )


@pytest.mark.parametrize("field,value", [
    ("envelope_outcome", "refused"),
    ("source_authenticated", True),
    ("v3_campaign_advanced", True),
    ("point_in_time_data", True),
    ("outcome_looks", 1),
])
def test_self_consistent_reanchored_report_cannot_claim_other_status(tmp_path, field, value):
    receipt, report_path = _accepted(tmp_path)
    report = json.loads(report_path.read_bytes())
    report[field] = value
    report_path = _repin_report(report_path, report)
    with pytest.raises(verify.AmbiguousDiagnosticVerificationError, match="REFUSED"):
        _verify(receipt, report_path)


def test_changed_partial_receipt_or_extra_artifact_refuses(tmp_path):
    receipt, report_path = _accepted(tmp_path)
    stale = replace(receipt, pending_attempt_start_sha256="e" * 64)
    with pytest.raises(verify.AmbiguousDiagnosticVerificationError, match="REFUSED"):
        _verify(stale, report_path)
    (report_path.parent / "extra.json").write_bytes(b"{}\n")
    with pytest.raises(verify.AmbiguousDiagnosticVerificationError, match="REFUSED"):
        _verify(receipt, report_path)


def test_private_modes_and_body_hash_are_enforced(tmp_path):
    receipt, report_path = _accepted(tmp_path)
    body_name = hash_bytes(_parent(receipt.pending_request)) + ".bin"
    body_path = report_path.parent / "objects" / body_name
    body_path.write_bytes(b"invented wrong bytes")
    with pytest.raises(verify.AmbiguousDiagnosticVerificationError, match="REFUSED"):
        _verify(receipt, report_path)
    body_path.write_bytes(_parent(receipt.pending_request))
    os.chmod(report_path.parent, 0o755)
    with pytest.raises(verify.AmbiguousDiagnosticVerificationError, match="REFUSED"):
        _verify(receipt, report_path)


def test_self_consistent_wrong_response_framing_refuses(tmp_path):
    receipt, report_path = _accepted(tmp_path)
    root = report_path.parent
    response = json.loads((root / "response.json").read_bytes())
    response["headers"] = [["Content-Length", "1"]]
    response["headers_sha256"] = hash_payload(response["headers"])
    _write_json(root / "response.json", response)
    report = json.loads(report_path.read_bytes())
    report["response_headers_sha256"] = response["headers_sha256"]
    report_path = _repin_report(report_path, report)
    with pytest.raises(verify.AmbiguousDiagnosticVerificationError, match="REFUSED"):
        _verify(receipt, report_path)


def test_reanchored_wrong_parent_identity_refuses(tmp_path):
    receipt, report_path = _accepted(tmp_path)
    root = report_path.parent
    old = _parent(receipt.pending_request)
    wrong = old.replace(b"<CIK>0000000001", b"<CIK>0000000009")
    assert len(old) == len(wrong)
    old_sha, new_sha = hash_bytes(old), hash_bytes(wrong)
    (root / "objects" / f"{old_sha}.bin").unlink()
    new_object = root / "objects" / f"{new_sha}.bin"
    new_object.write_bytes(wrong)
    os.chmod(new_object, 0o600)
    response = json.loads((root / "response.json").read_bytes())
    response["body_sha256"] = new_sha
    _write_json(root / "response.json", response)
    report = json.loads(report_path.read_bytes())
    report["body_sha256"] = new_sha
    report_path = _repin_report(report_path, report)
    with pytest.raises(verify.AmbiguousDiagnosticVerificationError, match="REFUSED"):
        _verify(receipt, report_path)


def test_missing_terminal_report_does_not_complete_network_failure(tmp_path):
    receipt = _receipt(tmp_path)
    report_path = capture._capture_one(
        receipt, tmp_path / "one-shot-v3-ambiguity",
        transport=lambda *_: (_ for _ in ()).throw(OSError("invented reset")),
        contact_email="invented@example.test", capture_git_commit=_COMMIT,
        protected_roots=(receipt.v3_root,),
    )
    with pytest.raises(verify.AmbiguousDiagnosticVerificationError, match="REFUSED"):
        _verify(receipt, report_path)
    report_path.unlink()
    with pytest.raises(verify.AmbiguousDiagnosticVerificationError, match="REFUSED"):
        verify.verify_accepted_ambiguity_diagnostic(
            receipt, report_path.parent, capture_git_commit=_COMMIT,
            expected_report_sha256="0" * 64,
        )


def _observed_wrapper(tmp_path, monkeypatch, *, drift=False):
    tmp_path.mkdir(parents=True, exist_ok=True)
    receipt, report_path = _accepted(tmp_path)
    monkeypatch.setattr(verify, "_OBSERVED_V3_ROOT", receipt.v3_root)
    monkeypatch.setattr(verify, "_OBSERVED_DIAGNOSTIC_ROOT", report_path.parent)
    calls = []

    def replay(*_args):
        calls.append(1)
        if drift and len(calls) == 2:
            return replace(receipt, pending_shard_journal_sha256="f" * 64)
        return receipt

    def committed_blob(commit):
        if commit != _COMMIT:
            raise verify.AmbiguousDiagnosticVerificationError(
                "REFUSED: invented wrong capture commit"
            )
        return "e" * 64

    monkeypatch.setattr(verify, "load_observed_partial_all_form4_recovery_v3", replay)
    monkeypatch.setattr(verify, "_verify_observed_capture_blob", committed_blob)
    source_args = (tmp_path / "q4raw", tmp_path / "q4parsed",
                   tmp_path / "q1raw", tmp_path / "q1parsed",
                   tmp_path / "pilot", tmp_path / "selected",
                   tmp_path / "prior", tmp_path / "old-diagnostic",
                   receipt.v3_root, report_path.parent)
    return receipt, report_path, source_args, calls


def test_observed_wrapper_requires_fresh_replay_before_and_after(tmp_path, monkeypatch):
    receipt, report_path, args, calls = _observed_wrapper(tmp_path, monkeypatch)
    checked = verify.load_observed_accepted_v3_ambiguity_diagnostic(
        *args, capture_git_commit=_COMMIT,
        expected_report_sha256=hash_bytes(report_path.read_bytes()),
    )
    assert checked.ambiguous_request_sha256 == receipt.pending_request_sha256
    assert checked.v3_root_plan_sha256 == receipt.root_plan_sha256
    assert checked.pending_shard_journal_sha256 == receipt.pending_shard_journal_sha256
    assert calls == [1, 1]


def test_observed_wrapper_refuses_wrong_root_commit_report_and_source_drift(
    tmp_path, monkeypatch,
):
    _receipt_value, report_path, args, calls = _observed_wrapper(tmp_path, monkeypatch)
    anchor = hash_bytes(report_path.read_bytes())
    with pytest.raises(verify.AmbiguousDiagnosticVerificationError, match="REFUSED"):
        verify.load_observed_accepted_v3_ambiguity_diagnostic(
            *args[:-1], tmp_path / "other-diagnostic", capture_git_commit=_COMMIT,
            expected_report_sha256=anchor,
        )
    assert calls == []
    with pytest.raises(verify.AmbiguousDiagnosticVerificationError, match="REFUSED"):
        verify.load_observed_accepted_v3_ambiguity_diagnostic(
            *args, capture_git_commit="f" * 40,
            expected_report_sha256=anchor,
        )
    assert calls == []
    with pytest.raises(verify.AmbiguousDiagnosticVerificationError, match="REFUSED"):
        verify.load_observed_accepted_v3_ambiguity_diagnostic(
            *args, capture_git_commit=_COMMIT,
            expected_report_sha256="0" * 64,
        )
    assert calls == [1]

    # A fresh fixture isolates the after-replay drift direction.
    _receipt_value, report_path, args, calls = _observed_wrapper(
        tmp_path / "drift-case", monkeypatch, drift=True,
    )
    with pytest.raises(verify.AmbiguousDiagnosticVerificationError, match="REFUSED"):
        verify.load_observed_accepted_v3_ambiguity_diagnostic(
            *args, capture_git_commit=_COMMIT,
            expected_report_sha256=hash_bytes(report_path.read_bytes()),
        )
    assert calls == [1, 1]


def test_observed_capture_blob_must_match_exact_committed_file(monkeypatch):
    lane = verify._OBSERVED_LANE_ROOT
    source = (lane / verify._CAPTURE_SOURCE).read_bytes()

    def git_output(args, *, cwd, stderr):
        assert cwd == lane
        assert stderr is not None
        if args[1:] == ("rev-parse", "--show-toplevel"):
            return str(lane).encode()
        if args[1:] == ("branch", "--show-current"):
            return b"codex/strategy-insider-buying\n"
        assert args[1:] == (
            "cat-file", "blob", f"{_COMMIT}:{verify._CAPTURE_SOURCE}",
        )
        return source

    monkeypatch.setattr(verify.subprocess, "check_output", git_output)
    assert verify._verify_observed_capture_blob(_COMMIT) == hash_bytes(source)

    def wrong_blob(args, *, cwd, stderr):
        value = git_output(args, cwd=cwd, stderr=stderr)
        return b"invented different code" if args[1] == "cat-file" else value

    monkeypatch.setattr(verify.subprocess, "check_output", wrong_blob)
    with pytest.raises(verify.AmbiguousDiagnosticVerificationError, match="REFUSED"):
        verify._verify_observed_capture_blob(_COMMIT)


# Section 119 (Claude review): the external report digest is the verifier's
# trust anchor. A canonical, shape-valid report stored under the anchored
# file name must refuse on the digest itself; earlier cases added an unknown
# key, which the key-set check refused first. The read-only directory wrapper
# replaces the specific reason with a generic one, so the reason is asserted
# on the exception chain.
def _refusal_chain(error: BaseException) -> list[str]:
    reasons = []
    current: BaseException | None = error
    while current is not None:
        reasons.append(str(current))
        current = current.__cause__
    return reasons


def test_shape_valid_report_under_the_anchored_name_fails_the_external_digest(tmp_path):
    receipt, report_path = _accepted(tmp_path)
    anchor = hash_bytes(report_path.read_bytes())
    report = json.loads(report_path.read_bytes())
    assert report["finished_utc"].endswith("+00:00")
    report["finished_utc"] = "2031-01-01T00:00:00.000000+00:00"
    assert _write_json(report_path, report) != anchor
    with pytest.raises(verify.AmbiguousDiagnosticVerificationError) as refused:
        verify.verify_accepted_ambiguity_diagnostic(
            receipt, report_path.parent, capture_git_commit=_COMMIT,
            expected_report_sha256=anchor,
        )
    assert any("differs from its separate trusted digest" in reason
               for reason in _refusal_chain(refused.value))


@pytest.mark.parametrize("field,value", [
    ("canonical_evidence", True),
    ("envelope_reason", "REFUSED: invented reason"),
])
def test_reanchored_report_cannot_claim_canonical_evidence_or_a_refusal_reason(
    tmp_path, field, value,
):
    receipt, report_path = _accepted(tmp_path)
    report = json.loads(report_path.read_bytes())
    report[field] = value
    # The report is re-anchored and self-consistent, so only the report's own
    # status and authority rule can refuse it.
    with pytest.raises(verify.AmbiguousDiagnosticVerificationError, match="REFUSED"):
        _verify(receipt, _repin_report(report_path, report))
