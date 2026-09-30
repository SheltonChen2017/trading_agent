"""Invented source only; partial-root recovery preflight never dispatches."""
from __future__ import annotations

import pytest

from data.hashing import hash_bytes, hash_payload
from research.insider_buying_sec_complete_acquisition import SecHttpResult
import research.insider_buying_sec_all_form4_parent_campaign as campaign
import research.insider_buying_sec_all_form4_parent_recovery_preflight as recovery


_CAPTURE = "d" * 40


def _request(number: int) -> campaign.CampaignRequest:
    identifier = f"0000000001-23-{number:06d}"
    return campaign.CampaignRequest(
        period="2023Q1", accession_number=identifier, form_type="4",
        filing_date="2023-01-03", issuer_cik="0000000001",
        archive_path=f"edgar/data/1/{identifier}.txt",
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
        "<ISSUER>\n<COMPANY-DATA>\n<CIK>0000000001\n</COMPANY-DATA>\n</ISSUER>\n"
        "</SEC-HEADER>\n<DOCUMENT>\n<TYPE>4\n<SEQUENCE>1\n"
        "<FILENAME>invented.xml\n<TEXT>\ninvented\n</TEXT>\n"
        "</DOCUMENT>\n</SEC-DOCUMENT>\n"
    ).encode("ascii")


def _plan() -> tuple[campaign.CampaignPlan, dict[str, bytes]]:
    requests = tuple(_request(index) for index in range(1, 8))
    reused = {requests[index].accession_number: _body(requests[index])
              for index in (0, 3, 5)}
    descriptors = tuple(
        campaign.CampaignReuse(
            accession_number=key, object_sha256=hash_bytes(value),
            object_size_bytes=len(value), prior_report_sha256="e" * 64,
        ) for key, value in sorted(reused.items())
    )
    return campaign.CampaignPlan(
        scope="synthetic_test_manifest", manifest_sha256="c" * 64,
        requests=requests, reuses=descriptors, shard_size=3,
    ), reused


@pytest.fixture
def partial_root(tmp_path, monkeypatch):
    plan, reused = _plan()
    root = tmp_path / "prior"
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
        request = next(item for item in plan.requests if item.url == url)
        raw = _body(request, wrong=request is plan.requests[4])
        return SecHttpResult(200, (("Content-Length", str(len(raw))),), raw)

    with pytest.raises(campaign.CampaignError, match="REFUSED"):
        campaign.run_synthetic_campaign(
            plan, root, transport=transport, reused_bytes=reused,
            contact_email="research@example.test", capture_git_commit=_CAPTURE,
        )
    assert len(seen) == 3
    assert all(seen[position] == plan.requests[index].url
               for position, index in enumerate((1, 2, 4)))
    reports = tuple(next((root / f"shard-{index:04d}").glob("shard-report-*.json"))
                    for index in (0, 1))
    expected = recovery.PartialCampaignExpectation(
        capture_git_commit=_CAPTURE,
        shard_report_sha256s=tuple(path.name[13:-5] for path in reports),
        completed_counts=(3, 1), reused_counts=(1, 1),
        total_attempt_count=3,
    )
    return plan, root, expected


def test_partial_replay_and_continuation_inventory_are_exact_and_read_only(partial_root):
    plan, root, expected = partial_root
    before = {str(path.relative_to(root)): hash_bytes(path.read_bytes())
              for path in root.rglob("*") if path.is_file()}
    receipt = recovery.verify_partial_campaign(plan, root, expected=expected)
    after = {str(path.relative_to(root)): hash_bytes(path.read_bytes())
             for path in root.rglob("*") if path.is_file()}
    assert before == after
    assert receipt.completed_count == 4
    assert receipt.prior_selected_reused_count == 2
    assert receipt.prior_newly_acquired_count == 2
    assert receipt.prior_attempt_count == 3
    assert receipt.refused_prior_attempt_count == 1
    assert len(receipt.completed) == 4
    assert [item.request_index for item in receipt.completed] == list(range(4))
    assert receipt.refused_request is plan.requests[4]
    assert receipt.remaining_selected_reuse_count == 1
    assert receipt.remaining_new_request_count == 2
    assert len(receipt.prior_shard_journal_sha256s) == 2
    assert receipt.prior_shard_report_sha256s == expected.shard_report_sha256s
    assert receipt.continuation_request_inventory_sha256 == hash_payload(
        [plan.requests[index].to_payload() for index in (4, 6)]
    )


@pytest.mark.parametrize("member", ["object", "event", "journal", "report", "plan", "extra"])
def test_partial_replay_refuses_tampering_before_continuation(partial_root, member):
    plan, root, expected = partial_root
    paths = {
        "object": sorted(root.rglob("objects/*.bin")),
        "event": sorted(root.rglob("event-*.json")),
        "journal": sorted(root.rglob("attempts.jsonl")),
        "report": sorted(root.rglob("shard-report-*.json")),
        "plan": [root / "campaign-plan.json"],
        "extra": [root / "unexpected.bin"],
    }
    path = paths[member][0]
    if member == "extra":
        path.write_bytes(b"x")
    else:
        path.write_bytes(path.read_bytes() + b"x")
    with pytest.raises(campaign.CampaignError, match="REFUSED"):
        recovery.verify_partial_campaign(plan, root, expected=expected)


def test_partial_replay_refuses_wrong_capture_or_report_anchor(partial_root):
    plan, root, expected = partial_root
    wrong_capture = recovery.PartialCampaignExpectation(
        capture_git_commit="f" * 40,
        shard_report_sha256s=expected.shard_report_sha256s,
        completed_counts=expected.completed_counts,
        reused_counts=expected.reused_counts,
        total_attempt_count=expected.total_attempt_count,
    )
    with pytest.raises(campaign.CampaignError, match="REFUSED"):
        recovery.verify_partial_campaign(plan, root, expected=wrong_capture)
    wrong_report = recovery.PartialCampaignExpectation(
        capture_git_commit=expected.capture_git_commit,
        shard_report_sha256s=("f" * 64, expected.shard_report_sha256s[1]),
        completed_counts=expected.completed_counts,
        reused_counts=expected.reused_counts,
        total_attempt_count=expected.total_attempt_count,
    )
    with pytest.raises(campaign.CampaignError, match="REFUSED"):
        recovery.verify_partial_campaign(plan, root, expected=wrong_report)
