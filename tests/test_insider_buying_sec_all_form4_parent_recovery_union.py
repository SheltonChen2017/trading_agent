"""Invented-source, offline replay of an accepted diagnostic and source union."""
from __future__ import annotations

from dataclasses import replace
import json

import pytest

from data.hashing import hash_bytes, hash_payload
from research.insider_buying_sec_complete_acquisition import SecHttpResult
import research.insider_buying_sec_all_form4_parent_campaign as campaign
import research.insider_buying_sec_all_form4_parent_recovery_preflight as partial
import research.insider_buying_sec_all_form4_parent_recovery_union as union
import research.insider_buying_sec_parent_refusal_diagnostic as diagnostic


_PRIOR_COMMIT = "d" * 40
_DIAGNOSTIC_COMMIT = "e" * 40
_CONTACT = "invented@example.test"


def _request(number: int) -> campaign.CampaignRequest:
    accession = f"0000000001-23-{number:06d}"
    return campaign.CampaignRequest(
        period="2023Q1", accession_number=accession, form_type="4",
        filing_date="2023-01-03", issuer_cik="0000000001",
        archive_path=f"edgar/data/1/{accession}.txt",
        submission_row_id=hash_bytes(f"row-{number}".encode()),
        parsed_lineage_hash="b" * 64, master_source_sha256="a" * 64,
    )


def _body(request: campaign.CampaignRequest, *, wrong: bool = False) -> bytes:
    outer = request.accession_number
    inner = "0000000001-23-999999" if wrong else outer
    return (
        f"<SEC-DOCUMENT>{outer}.txt : 20230103\n"
        f"<SEC-HEADER>{inner}.hdr.sgml : 20230103\n"
        "<ACCEPTANCE-DATETIME>20230103101112\n"
        f"<ACCESSION-NUMBER>{inner}\n<TYPE>4\n<FILING-DATE>20230103\n"
        "<REPORTING-OWNER>\n<OWNER-DATA>\n<CIK>0000000002\n"
        "<CONFORMED-NAME>Invented Owner\n</OWNER-DATA>\n</REPORTING-OWNER>\n"
        "<ISSUER>\n<COMPANY-DATA>\n<CIK>0000000001\n"
        "</COMPANY-DATA>\n</ISSUER>\n"
        "</SEC-HEADER>\n<DOCUMENT>\n<TYPE>4\n<SEQUENCE>1\n"
        "<FILENAME>invented.xml\n<TEXT>\ninvented\n</TEXT>\n"
        "</DOCUMENT>\n</SEC-DOCUMENT>\n"
    ).encode("ascii")


def _stopped_source(tmp_path, monkeypatch, *, short_source_cik=False):
    requests = tuple(_request(index) for index in range(1, 8))
    if short_source_cik:
        requests = (*requests[:4], replace(requests[4], issuer_cik="1"),
                    *requests[5:])
    reused = {requests[index].accession_number: _body(requests[index])
              for index in (0, 3, 5)}
    descriptors = tuple(campaign.CampaignReuse(
        accession_number=accession,
        object_sha256=hash_bytes(raw), object_size_bytes=len(raw),
        prior_report_sha256="f" * 64,
    ) for accession, raw in sorted(reused.items()))
    plan = campaign.CampaignPlan(
        scope="synthetic_test_manifest", manifest_sha256="c" * 64,
        requests=requests, reuses=descriptors, shard_size=3,
    )
    selected = tmp_path / "selected"
    (selected / "objects").mkdir(parents=True)
    for raw in reused.values():
        (selected / "objects" / f"{hash_bytes(raw)}.bin").write_bytes(raw)

    clock = [0]

    def monotonic_ns():
        clock[0] += 1_000_000
        return clock[0]

    def sleep(seconds):
        clock[0] += int(seconds * 1_000_000_000) + 1_000_000

    monkeypatch.setattr(campaign, "_capacity_ok", lambda *_, **__: True)
    monkeypatch.setattr(campaign.time, "monotonic_ns", monotonic_ns)
    monkeypatch.setattr(campaign.time, "sleep", sleep)
    seen = []

    def transport(url, _headers, _cap):
        seen.append(url)
        request = next(row for row in requests if row.url == url)
        raw = _body(request, wrong=request is requests[4])
        return SecHttpResult(200, (("Content-Length", str(len(raw))),), raw)

    prior = tmp_path / "stopped-v1"
    with pytest.raises(campaign.CampaignError, match="REFUSED"):
        campaign.run_synthetic_campaign(
            plan, prior, transport=transport, reused_bytes=reused,
            contact_email=_CONTACT, capture_git_commit=_PRIOR_COMMIT,
        )
    assert seen == [requests[index].url for index in (1, 2, 4)]
    reports = tuple(next((prior / f"shard-{index:04d}").glob("shard-report-*.json"))
                    for index in (0, 1))
    expected = partial.PartialCampaignExpectation(
        capture_git_commit=_PRIOR_COMMIT,
        shard_report_sha256s=tuple(path.name[13:-5] for path in reports),
        completed_counts=(3, 1), reused_counts=(1, 1),
        total_attempt_count=3,
    )
    receipt = partial.verify_partial_campaign(plan, prior, expected=expected)
    binding = diagnostic.RefusedParentBinding(
        request=receipt.refused_request,
        prior_campaign_plan_sha256=receipt.prior_campaign_plan_sha256,
        prior_shard_report_sha256s=receipt.prior_shard_report_sha256s,
        prior_shard_journal_sha256s=receipt.prior_shard_journal_sha256s,
    )
    body = _body(receipt.refused_request)
    diag = tmp_path / "one-shot-diagnostic"
    def capture():
        return diagnostic._capture_one(
            binding, diag,
            transport=lambda *_: SecHttpResult(
                200, (("Content-Length", str(len(body))),), body,
            ),
            contact_email=_CONTACT, capture_git_commit=_DIAGNOSTIC_COMMIT,
            protected_roots=(prior, selected),
        )

    if short_source_cik:
        with monkeypatch.context() as patch:
            def original_validator(raw, request):
                if len(request["issuer_cik"]) != 10:
                    raise campaign.CampaignError(
                        "REFUSED: issuer CIK is not ten padded nonzero digits"
                    )
                campaign._validate_parent_header(raw, request)

            patch.setattr(diagnostic, "_validate_parent_header", original_validator)
            report = capture()
    else:
        report = capture()
    return plan, prior, diag, selected, expected, report.name[18:-5], binding


@pytest.fixture
def stopped_source(tmp_path, monkeypatch):
    return _stopped_source(tmp_path, monkeypatch)


@pytest.fixture
def stopped_short_source(tmp_path, monkeypatch):
    return _stopped_source(tmp_path, monkeypatch, short_source_cik=True)


def _union(stopped_source):
    plan, prior, diag, selected, expected, report_sha, _binding = stopped_source
    return union.preflight_source_union(
        plan, prior, diag, selected,
        prior_expectation=expected,
        diagnostic_capture_git_commit=_DIAGNOSTIC_COMMIT,
        expected_diagnostic_report_sha256=report_sha,
    )


def _files(root):
    return {str(path.relative_to(root)): hash_bytes(path.read_bytes())
            for path in root.rglob("*") if path.is_file()}


def test_accepted_diagnostic_and_disjoint_source_union_are_read_only(stopped_source):
    plan, prior, diag, selected, _expected, report_sha, binding = stopped_source
    before = tuple(_files(root) for root in (prior, diag, selected))
    verified = union.verify_accepted_diagnostic(
        diag, binding, capture_git_commit=_DIAGNOSTIC_COMMIT,
        expected_report_sha256=report_sha,
    )
    assert verified.body_sha256 == hash_bytes(_body(plan.requests[4]))
    receipt = _union(stopped_source)
    assert tuple(_files(root) for root in (prior, diag, selected)) == before
    assert receipt["total_parents"] == 7
    assert receipt["prior_completed_count"] == 4
    assert receipt["prior_selected_reused_count"] == 2
    assert receipt["prior_newly_acquired_count"] == 2
    assert receipt["prior_attempt_count"] == 3
    assert receipt["accepted_diagnostic_count"] == 1
    assert receipt["diagnostic_attempt_count"] == 1
    assert receipt["known_attempt_count"] == 4
    assert receipt["refused_parent_total_attempt_count"] == 2
    assert receipt["remaining_selected_reuse_count"] == 1
    assert receipt["later_unattempted_request_count"] == 1
    assert receipt["later_unattempted_request_inventory_sha256"] == hash_payload(
        [plan.requests[6].to_payload()]
    )
    assert receipt["source_assignment_sha256"] == hash_payload(
        ["prior_completed"] * 4 + ["accepted_diagnostic",
                                  "remaining_selected_reuse", "later_unattempted"]
    )
    assert receipt["sec_dispatches"] == receipt["research_looks"] == receipt["qc_jobs"] == 0
    assert receipt["complete_parent_bytes_acquired"] is False
    assert receipt["source_authenticated"] is False
    assert receipt["canonical_evidence"] is False
    assert receipt["point_in_time_data"] is False


def test_originally_refused_short_cik_diagnostic_needs_offline_correction(
    tmp_path, stopped_source, monkeypatch,
):
    _plan, prior, _diag, selected, _expected, _sha, binding = stopped_source
    short_binding = replace(
        binding, request=replace(binding.request, issuer_cik="1"),
    )
    body = _body(short_binding.request)
    corrected_root = tmp_path / "originally-refused-short-cik"
    current_validator = campaign._validate_parent_header

    def old_validator(raw, request):
        if len(request["issuer_cik"]) != 10:
            raise campaign.CampaignError(
                "REFUSED: issuer CIK is not ten padded nonzero digits"
            )
        return current_validator(raw, request)

    with monkeypatch.context() as patch:
        patch.setattr(diagnostic, "_validate_parent_header", old_validator)
        report_path = diagnostic._capture_one(
            short_binding, corrected_root,
            transport=lambda *_: SecHttpResult(
                200, (("Content-Length", str(len(body))),), body,
            ),
            contact_email=_CONTACT, capture_git_commit=_DIAGNOSTIC_COMMIT,
            protected_roots=(prior, selected),
        )
    report_sha = report_path.name[18:-5]
    assert json.loads(report_path.read_bytes())["envelope_outcome"] == "refused"
    with pytest.raises(union.RecoveryUnionError, match="REFUSED"):
        union.verify_accepted_diagnostic(
            corrected_root, short_binding,
            capture_git_commit=_DIAGNOSTIC_COMMIT,
            expected_report_sha256=report_sha,
        )
    verified = union.verify_offline_corrected_diagnostic(
        corrected_root, short_binding,
        capture_git_commit=_DIAGNOSTIC_COMMIT,
        expected_report_sha256=report_sha,
    )
    assert verified.body_sha256 == hash_bytes(body)
    assert verified.original_envelope_outcome == "refused"
    assert verified.source_class == "offline_corrected_diagnostic"
    assert verified.validator_source_sha256 is not None
    assert verified.offline_correction_receipt_sha256 == hash_payload({
        "kind": union.OFFLINE_CORRECTION_VERSION,
        "original_diagnostic_report_sha256": report_sha,
        "original_diagnostic_capture_git_commit": _DIAGNOSTIC_COMMIT,
        "refused_request_sha256": hash_payload(short_binding.request.to_payload()),
        "body_sha256": hash_bytes(body),
        "body_size_bytes": len(body),
        "original_envelope_outcome": "refused",
        "original_envelope_reason": "REFUSED: issuer CIK is not ten padded nonzero digits",
        "offline_header_validated": True,
        "validator_source_sha256": verified.validator_source_sha256,
        "sec_dispatches": 0,
        "source_authenticated": False,
        "canonical_evidence": False,
        "point_in_time_data": False,
    })


def test_corrected_diagnostic_fills_exact_refused_source_without_rewriting_history(
    stopped_short_source,
):
    plan, prior, diag, selected, expected, report_sha, _binding = stopped_short_source
    receipt = union.preflight_source_union(
        plan, prior, diag, selected,
        prior_expectation=expected,
        diagnostic_capture_git_commit=_DIAGNOSTIC_COMMIT,
        expected_diagnostic_report_sha256=report_sha,
        diagnostic_mode="offline_corrected",
    )
    assert receipt["original_diagnostic_envelope_outcome"] == "refused"
    assert receipt["accepted_diagnostic_count"] == 0
    assert receipt["offline_corrected_diagnostic_count"] == 1
    assert receipt["diagnostic_attempt_count"] == 1
    assert receipt["refused_parent_total_attempt_count"] == 2
    assert receipt["source_assignment_sha256"] == hash_payload(
        ["prior_completed"] * 4 + ["offline_corrected_diagnostic",
                                  "remaining_selected_reuse", "later_unattempted"]
    )
    assert json.loads((diag / f"diagnostic-report-{report_sha}.json").read_bytes())[
        "envelope_outcome"
    ] == "refused"


@pytest.mark.parametrize("failure", ["wrong_header", "other_reason", "padded_source"])
def test_offline_correction_does_not_launder_other_refusals(
    tmp_path, stopped_short_source, monkeypatch, failure,
):
    _plan, prior, _diag, selected, _expected, _sha, binding = stopped_short_source
    if failure == "padded_source":
        binding = replace(binding, request=replace(binding.request, issuer_cik="0000000001"))
    body = _body(binding.request, wrong=failure == "wrong_header")
    reason = ("REFUSED: different original reason" if failure == "other_reason"
              else union.ORIGINAL_SHORT_CIK_REASON)

    def original_validator(_raw, _request):
        raise campaign.CampaignError(reason)

    with monkeypatch.context() as patch:
        patch.setattr(diagnostic, "_validate_parent_header", original_validator)
        report_path = diagnostic._capture_one(
            binding, tmp_path / failure,
            transport=lambda *_: SecHttpResult(
                200, (("Content-Length", str(len(body))),), body,
            ),
            contact_email=_CONTACT, capture_git_commit=_DIAGNOSTIC_COMMIT,
            protected_roots=(prior, selected),
        )
    with pytest.raises(union.RecoveryUnionError, match="REFUSED"):
        union.verify_offline_corrected_diagnostic(
            report_path.parent, binding,
            capture_git_commit=_DIAGNOSTIC_COMMIT,
            expected_report_sha256=report_path.name[18:-5],
        )


@pytest.mark.parametrize("member", [
    "manifest", "start", "response", "body", "report", "commit", "extra", "lock",
])
def test_diagnostic_replay_refuses_changed_or_extra_member(stopped_source, member):
    _plan, _prior, diag, _selected, _expected, report_sha, binding = stopped_source
    paths = {
        "manifest": diag / "manifest.json",
        "start": diag / "attempt-start.json",
        "response": diag / "response.json",
        "body": next((diag / "objects").glob("*.bin")),
        "report": diag / f"diagnostic-report-{report_sha}.json",
        "commit": diag / "commit.json",
        "extra": diag / "extra.bin",
        "lock": diag / "run.lock",
    }
    target = paths[member]
    target.write_bytes(target.read_bytes() + b"x" if target.exists() else b"x")
    with pytest.raises(union.RecoveryUnionError, match="REFUSED"):
        union.verify_accepted_diagnostic(
            diag, binding, capture_git_commit=_DIAGNOSTIC_COMMIT,
            expected_report_sha256=report_sha,
        )


def test_diagnostic_replay_requires_trusted_report_and_exact_old_binding(stopped_source):
    _plan, _prior, diag, _selected, _expected, report_sha, binding = stopped_source
    with pytest.raises(union.RecoveryUnionError, match="REFUSED"):
        union.verify_accepted_diagnostic(
            diag, binding, capture_git_commit=_DIAGNOSTIC_COMMIT,
            expected_report_sha256="0" * 64,
        )
    altered = replace(binding, prior_campaign_plan_sha256="0" * 64)
    with pytest.raises(union.RecoveryUnionError, match="REFUSED"):
        union.verify_accepted_diagnostic(
            diag, altered, capture_git_commit=_DIAGNOSTIC_COMMIT,
            expected_report_sha256=report_sha,
        )


def test_diagnostic_replay_refuses_noncanonical_response_json(stopped_source):
    _plan, _prior, diag, _selected, _expected, report_sha, binding = stopped_source
    path = diag / "response.json"
    path.write_text(json.dumps(json.loads(path.read_bytes()), indent=2))
    with pytest.raises(union.RecoveryUnionError, match="REFUSED"):
        union.verify_accepted_diagnostic(
            diag, binding, capture_git_commit=_DIAGNOSTIC_COMMIT,
            expected_report_sha256=report_sha,
        )


def test_diagnostic_replay_refuses_float_body_size_even_with_matching_report_hash(
    stopped_source,
):
    _plan, _prior, diag, _selected, _expected, report_sha, binding = stopped_source
    old_report = diag / f"diagnostic-report-{report_sha}.json"
    payload = json.loads(old_report.read_bytes())
    payload["body_size_bytes"] = float(payload["body_size_bytes"])
    changed_raw = diagnostic._bytes(payload)
    changed_sha = hash_bytes(changed_raw)
    new_report = diag / f"diagnostic-report-{changed_sha}.json"
    old_report.rename(new_report)
    new_report.write_bytes(changed_raw)
    commit_path = diag / "commit.json"
    commit = json.loads(commit_path.read_bytes())
    commit["report_name"] = new_report.name
    commit["report_sha256"] = changed_sha
    commit_path.write_bytes(diagnostic._bytes(commit))
    with pytest.raises(union.RecoveryUnionError, match="REFUSED"):
        union.verify_accepted_diagnostic(
            diag, binding, capture_git_commit=_DIAGNOSTIC_COMMIT,
            expected_report_sha256=changed_sha,
        )


@pytest.mark.parametrize("member", ["root", "response", "body"])
def test_diagnostic_replay_refuses_publicly_readable_private_member(
    stopped_source, member,
):
    _plan, _prior, diag, _selected, _expected, report_sha, binding = stopped_source
    target = {
        "root": diag,
        "response": diag / "response.json",
        "body": next((diag / "objects").glob("*.bin")),
    }[member]
    target.chmod(0o755 if member == "root" else 0o644)
    with pytest.raises(union.RecoveryUnionError, match="REFUSED"):
        union.verify_accepted_diagnostic(
            diag, binding, capture_git_commit=_DIAGNOSTIC_COMMIT,
            expected_report_sha256=report_sha,
        )


def test_union_refuses_changed_remaining_selected_object(stopped_source):
    plan, _prior, _diag, selected, _expected, _sha, _binding = stopped_source
    raw = _body(plan.requests[5])
    (selected / "objects" / f"{hash_bytes(raw)}.bin").write_bytes(raw + b"x")
    with pytest.raises(union.RecoveryUnionError, match="REFUSED"):
        _union(stopped_source)


def test_union_refuses_source_plan_changed_after_old_capture(stopped_source):
    plan, prior, diag, selected, expected, report_sha, _binding = stopped_source
    wrong_request = replace(plan.requests[-1], filing_date="2023-01-04")
    wrong_plan = replace(plan, requests=(*plan.requests[:-1], wrong_request))
    with pytest.raises(union.RecoveryUnionError, match="REFUSED"):
        union.preflight_source_union(
            wrong_plan, prior, diag, selected,
            prior_expectation=expected,
            diagnostic_capture_git_commit=_DIAGNOSTIC_COMMIT,
            expected_diagnostic_report_sha256=report_sha,
        )


def test_report_claim_alone_cannot_accept_wrong_diagnostic_body(
    tmp_path, stopped_source, monkeypatch,
):
    _plan, prior, _diag, selected, _expected, _sha, binding = stopped_source
    wrong_body = _body(binding.request, wrong=True)
    forged = tmp_path / "forged-accepted-report"
    with monkeypatch.context() as patch:
        patch.setattr(diagnostic, "_validate_parent_header", lambda *_: None)
        forged_report = diagnostic._capture_one(
            binding, forged,
            transport=lambda *_: SecHttpResult(
                200, (("Content-Length", str(len(wrong_body))),), wrong_body,
            ),
            contact_email=_CONTACT, capture_git_commit=_DIAGNOSTIC_COMMIT,
            protected_roots=(prior, selected),
        )
    assert json.loads(forged_report.read_bytes())["envelope_outcome"] == "accepted"
    with pytest.raises(union.RecoveryUnionError, match="REFUSED"):
        union.verify_accepted_diagnostic(
            forged, binding, capture_git_commit=_DIAGNOSTIC_COMMIT,
            expected_report_sha256=forged_report.name[18:-5],
        )
