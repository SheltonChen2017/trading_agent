"""One-shot diagnostic custody with invented bytes and injected transport only."""
from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

from data.hashing import hash_bytes, hash_payload
import research.insider_buying_sec_parent_refusal_diagnostic as diagnostic
from research.insider_buying_sec_all_form4_parent_campaign import CampaignRequest
from research.insider_buying_sec_complete_acquisition import SecHttpResult


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


def _binding() -> diagnostic.RefusedParentBinding:
    return diagnostic.RefusedParentBinding(
        request=_request(), prior_campaign_plan_sha256="1" * 64,
        prior_shard_report_sha256s=("2" * 64, "3" * 64),
        prior_shard_journal_sha256s=("4" * 64, "5" * 64),
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


def _run(tmp_path, transport, *, name="diagnostic"):
    prior = tmp_path / "prior-campaign"
    prior.mkdir(exist_ok=True)
    sentinel = prior / "untouched.bin"
    if not sentinel.exists():
        sentinel.write_bytes(b"original immutable marker")
    report_path = diagnostic._capture_one(
        _binding(), tmp_path / name, transport=transport,
        contact_email=CONTACT, capture_git_commit=COMMIT,
        protected_roots=(prior,),
    )
    assert sentinel.read_bytes() == b"original immutable marker"
    return report_path


def test_refused_200_body_is_fsynced_before_envelope_validation_and_never_retried(tmp_path):
    body = b"invented bounded body with no SEC parent envelope"
    wire_headers = (("Content-Type", "text/plain"), ("Content-Length", str(len(body))))
    calls = []

    def transport(url, headers, bound):
        calls.append(url)
        assert headers["User-Agent"].endswith(f"({CONTACT})")
        assert bound == diagnostic.MAX_COMPLETE_TXT_BYTES
        assert (tmp_path / "diagnostic" / "attempt-start.json").is_file()
        return SecHttpResult(200, wire_headers, body)

    report_path = _run(tmp_path, transport)
    output = report_path.parent
    report = _read(report_path)
    response = _read(output / "response.json")
    manifest = _read(output / "manifest.json")
    assert len(calls) == 1
    assert report["status"] == 200
    assert report["envelope_outcome"] == "refused"
    assert report["campaign_advanced"] is False
    assert report["body_sha256"] == response["body_sha256"] == hash_bytes(body)
    assert report["body_size_bytes"] == response["body_size_bytes"] == len(body)
    assert response["headers"] == [list(pair) for pair in wire_headers]
    assert response["headers_sha256"] == hash_payload(response["headers"])
    assert (output / "objects" / f"{hash_bytes(body)}.bin").read_bytes() == body
    assert manifest["refused_request_sha256"] == hash_payload(_request().to_payload())
    assert manifest["prior_campaign_plan_sha256"] == "1" * 64
    assert manifest["prior_shard_report_sha256s"] == ["2" * 64, "3" * 64]
    assert manifest["prior_shard_journal_sha256s"] == ["4" * 64, "5" * 64]
    assert _read(output / "commit.json")["report_sha256"] == hash_bytes(report_path.read_bytes())
    public_metadata = b"".join(path.read_bytes() for path in output.glob("*.json"))
    assert _request().accession_number.encode() not in public_metadata
    assert CONTACT.encode() not in public_metadata
    with pytest.raises(diagnostic.RefusedParentDiagnosticError, match="already exists"):
        _run(tmp_path, lambda *_: pytest.fail("second SEC dispatch"))
    assert len(calls) == 1


def test_valid_parent_is_retained_but_does_not_complete_original_campaign(tmp_path):
    body = _parent(_request())
    report = _read(_run(
        tmp_path,
        lambda *_: SecHttpResult(200, (("Content-Length", str(len(body))),), body),
    ))
    assert report["envelope_outcome"] == "accepted"
    assert report["body_sha256"] == hash_bytes(body)
    assert report["campaign_advanced"] is False
    assert report["canonical_evidence"] is False
    assert report["qc_jobs"] == report["outcome_looks"] == 0


def test_non_200_preserves_status_and_headers_without_reading_a_body(tmp_path):
    report_path = _run(
        tmp_path,
        lambda *_: SecHttpResult(403, (("Retry-After", "30"),), b""),
    )
    report = _read(report_path)
    response = _read(report_path.parent / "response.json")
    assert report["status"] == response["status"] == 403
    assert response["headers"] == [["Retry-After", "30"]]
    assert report["body_sha256"] is None
    assert report["envelope_outcome"] == "not_checked"
    assert list((report_path.parent / "objects").iterdir()) == []


def test_interruption_after_durable_start_has_no_resume_or_retry(tmp_path):
    prior = tmp_path / "prior-campaign"
    prior.mkdir()
    output = tmp_path / "interrupted"
    calls = []

    def interrupt(*_):
        calls.append(1)
        assert (output / "attempt-start.json").is_file()
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        diagnostic._capture_one(
            _binding(), output, transport=interrupt,
            contact_email=CONTACT, capture_git_commit=COMMIT,
            protected_roots=(prior,),
        )
    assert (output / "manifest.json").is_file()
    assert not (output / "commit.json").exists()
    with pytest.raises(diagnostic.RefusedParentDiagnosticError, match="already exists"):
        diagnostic._capture_one(
            _binding(), output, transport=lambda *_: pytest.fail("second SEC dispatch"),
            contact_email=CONTACT, capture_git_commit=COMMIT,
            protected_roots=(prior,),
        )
    assert calls == [1]


def test_parent_directory_entry_is_fsynced_before_dispatch(monkeypatch, tmp_path):
    prior = tmp_path / "prior-campaign"
    prior.mkdir()
    output = tmp_path / "diagnostic"
    original_fsync = os.fsync
    parent_info = tmp_path.stat()
    parent_synced = False

    def fsync(descriptor):
        nonlocal parent_synced
        info = os.fstat(descriptor)
        if (info.st_dev, info.st_ino) == (parent_info.st_dev, parent_info.st_ino):
            parent_synced = True
        return original_fsync(descriptor)

    def transport(*_):
        assert parent_synced, "diagnostic root entry was not durable before SEC dispatch"
        return SecHttpResult(403, (), b"")

    monkeypatch.setattr(os, "fsync", fsync)
    diagnostic._capture_one(
        _binding(), output, transport=transport,
        contact_email=CONTACT, capture_git_commit=COMMIT,
        protected_roots=(prior,),
    )


def test_malformed_binding_or_contact_refuses_before_output_or_dispatch(tmp_path):
    prior = tmp_path / "prior"
    prior.mkdir()
    output = tmp_path / "bad"
    invalid = diagnostic.RefusedParentBinding(
        request=_request(), prior_campaign_plan_sha256="not-a-sha",
        prior_shard_report_sha256s=("2" * 64, "3" * 64),
        prior_shard_journal_sha256s=("4" * 64, "5" * 64),
    )
    with pytest.raises(diagnostic.RefusedParentDiagnosticError):
        diagnostic._capture_one(
            invalid, output, transport=lambda *_: pytest.fail("SEC dispatch"),
            contact_email=CONTACT, capture_git_commit=COMMIT,
            protected_roots=(prior,),
        )
    assert not output.exists()
    with pytest.raises(diagnostic.RefusedParentDiagnosticError):
        diagnostic._capture_one(
            _binding(), output, transport=lambda *_: pytest.fail("SEC dispatch"),
            contact_email="bad\r\nheader@example.test", capture_git_commit=COMMIT,
            protected_roots=(prior,),
        )
    assert not output.exists()


def test_real_entry_uses_verified_partial_receipt_and_fixed_one_shot_root(
    monkeypatch, tmp_path,
):
    # The real entry's network and committed-tree checks are replaced by
    # controlled fakes. No SEC connection is opened by this test.
    from research import insider_buying_sec_all_form4_parent_recovery_preflight as recovery

    source_paths = [tmp_path / f"source-{index}" for index in range(6)]
    for path in source_paths:
        path.mkdir()
    prior = tmp_path / "old-campaign"
    prior.mkdir()
    marker = prior / "old-marker.bin"
    marker.write_bytes(b"unchanged")
    verification_calls = []
    transport_calls = []

    def verify(*args):
        verification_calls.append(args)
        assert args == (*source_paths, prior)
        return SimpleNamespace(
            refused_request=_request(),
            prior_campaign_plan_sha256="1" * 64,
            prior_shard_report_sha256s=("2" * 64, "3" * 64),
            prior_shard_journal_sha256s=("4" * 64, "5" * 64),
        )

    def transport(url, _headers, _bound):
        transport_calls.append(url)
        body = b"invented rejected source envelope"
        return SecHttpResult(200, (("Content-Length", str(len(body))),), body)

    monkeypatch.setattr(diagnostic, "_verify_exact_committed_code", lambda _sha: None)
    monkeypatch.setattr(recovery, "load_observed_partial_all_form4_parent_campaign", verify)
    monkeypatch.setattr(diagnostic, "_selected_sec_transport", transport)
    monkeypatch.setattr(diagnostic, "_PRIOR_CAMPAIGN_ROOT", prior, raising=False)
    args = (*source_paths, prior)
    report_path = diagnostic.run_observed_refused_parent_diagnostic(
        *args, contact_email=CONTACT, capture_git_commit=COMMIT,
    )
    assert report_path.parent == tmp_path / "refused-parent-diagnostic-v1"
    assert _read(report_path)["envelope_outcome"] == "refused"
    assert marker.read_bytes() == b"unchanged"
    assert len(verification_calls) == len(transport_calls) == 1
    with pytest.raises(diagnostic.RefusedParentDiagnosticError, match="already exists"):
        diagnostic.run_observed_refused_parent_diagnostic(
            *args, contact_email=CONTACT, capture_git_commit=COMMIT,
        )
    assert len(transport_calls) == 1


def test_real_entry_rejects_alternate_prior_root_before_verification_or_dispatch(
    monkeypatch, tmp_path,
):
    from research import insider_buying_sec_all_form4_parent_recovery_preflight as recovery

    source_paths = [tmp_path / f"source-{index}" for index in range(6)]
    for path in source_paths:
        path.mkdir()
    pinned_prior = tmp_path / "pinned" / "old-campaign"
    pinned_prior.parent.mkdir()
    pinned_prior.mkdir()
    copied_prior = tmp_path / "copy" / "old-campaign"
    copied_prior.parent.mkdir()
    copied_prior.mkdir()
    monkeypatch.setattr(diagnostic, "_PRIOR_CAMPAIGN_ROOT", pinned_prior, raising=False)
    monkeypatch.setattr(diagnostic, "_verify_exact_committed_code", lambda _sha: None)
    monkeypatch.setattr(
        recovery, "load_observed_partial_all_form4_parent_campaign",
        lambda *_: pytest.fail("copied root reached recovery verifier"),
    )
    monkeypatch.setattr(
        diagnostic, "_selected_sec_transport",
        lambda *_: pytest.fail("copied root launched SEC request"),
    )
    with pytest.raises(diagnostic.RefusedParentDiagnosticError, match="exact prior campaign root"):
        diagnostic.run_observed_refused_parent_diagnostic(
            *source_paths, copied_prior,
            contact_email=CONTACT, capture_git_commit=COMMIT,
        )
    assert not (copied_prior.parent / "refused-parent-diagnostic-v1").exists()
