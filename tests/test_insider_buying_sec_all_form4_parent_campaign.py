"""Invented Form 4 parent bytes and injected transport only; no SEC request."""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from data.hashing import hash_bytes
import research.insider_buying_sec_all_form4_parent_campaign as campaign
from research.insider_buying_sec_selected_parent_runner import SecHttpResult


CONTACT = "research@example.test"
COMMIT = "d" * 40


def _request(number: int) -> campaign.CampaignRequest:
    accession = f"0000000001-23-{number:06d}"
    return campaign.CampaignRequest(
        period="2023Q1",
        accession_number=accession,
        form_type="4",
        filing_date="2023-01-03",
        issuer_cik="0000000001",
        archive_path=f"edgar/data/1/{accession}.txt",
        submission_row_id=hash_bytes(f"row-{number}".encode()),
        parsed_lineage_hash="b" * 64,
        master_source_sha256="a" * 64,
    )


def _plan(*numbers: int, shard_size: int = 2,
          reuses: tuple[campaign.CampaignReuse, ...] = ()) -> campaign.CampaignPlan:
    return campaign.CampaignPlan(
        scope="synthetic_test_manifest",
        manifest_sha256="c" * 64,
        requests=tuple(_request(number) for number in numbers),
        reuses=reuses,
        shard_size=shard_size,
    )


def _parent(request: campaign.CampaignRequest, *, accession: str | None = None,
            header_accession: str | None = None, issuer_cik: str | None = None,
            form_type: str | None = None) -> bytes:
    outer_accession = accession or request.accession_number
    inner_accession = header_accession or outer_accession
    issuer = issuer_cik or request.issuer_cik
    form = form_type or request.form_type
    filed = request.filing_date.replace("-", "")
    return (
        f"<SEC-DOCUMENT>{outer_accession}.txt : {filed}\n"
        f"<SEC-HEADER>{inner_accession}.hdr.sgml : {filed}\n"
        f"<ACCEPTANCE-DATETIME>{filed}101112\n"
        f"<ACCESSION-NUMBER>{inner_accession}\n"
        f"<TYPE>{form}\n<FILING-DATE>{filed}\n"
        "<REPORTING-OWNER>\n<OWNER-DATA>\n<CIK>0000000002\n"
        "<CONFORMED-NAME>Invented Owner\n</OWNER-DATA>\n</REPORTING-OWNER>\n"
        f"<ISSUER>\n<COMPANY-DATA>\n<CIK>{issuer}\n"
        "</COMPANY-DATA>\n</ISSUER>\n</SEC-HEADER>\n"
        "<DOCUMENT>\n<TYPE>4\n<SEQUENCE>1\n<FILENAME>invented.xml\n"
        "<TEXT>\ninvented\n</TEXT>\n</DOCUMENT>\n</SEC-DOCUMENT>\n"
    ).encode("ascii")


def _response(url: str | None = None, *, body: bytes | None = None,
              status: int = 200) -> SecHttpResult:
    if status != 200:
        return SecHttpResult(status, (), b"")
    if body is None:
        assert url is not None
        body = _parent(_request(int(url.rsplit("-", 1)[1].removesuffix(".txt"))))
    return SecHttpResult(200, (("Content-Length", str(len(body))),), body)


def _json(path):
    return json.loads(path.read_bytes())


def _run(plan, output, transport, *, resume=False, reused_bytes=None):
    return campaign.run_synthetic_campaign(
        plan, output, transport=transport, reused_bytes=reused_bytes,
        contact_email=CONTACT, capture_git_commit=COMMIT, resume=resume,
    )


@pytest.mark.parametrize("field", ["period", "form_type"])
def test_unhashable_request_enum_refuses_with_campaign_error(field):
    malformed = replace(_request(1), **{field: []})
    with pytest.raises(campaign.CampaignError, match="REFUSED"):
        malformed.to_payload()


def test_unhashable_plan_scope_refuses_with_campaign_error():
    malformed = replace(_plan(1), scope=[])
    with pytest.raises(campaign.CampaignError, match="REFUSED"):
        malformed.to_payload()


def test_contact_email_control_byte_refuses_before_output_or_network(tmp_path):
    output = tmp_path / "bad-contact"
    with pytest.raises(campaign.CampaignError, match="REFUSED"):
        campaign.run_synthetic_campaign(
            _plan(1), output,
            transport=lambda *_: pytest.fail("network was called"),
            contact_email="research@example.test\x00",
            capture_git_commit=COMMIT,
        )
    assert not output.exists()


@pytest.fixture(autouse=True)
def _fake_capacity_and_clock(monkeypatch):
    """Keep focused tests fast while retaining observable request spacing."""
    monotonic = [0]

    def monotonic_ns():
        monotonic[0] += 1_000_000
        return monotonic[0]

    def sleep(seconds):
        monotonic[0] += int(seconds * 1_000_000_000) + 1_000_000

    monkeypatch.setattr(campaign, "_capacity_ok", lambda *_, **__: True)
    monkeypatch.setattr(campaign.time, "monotonic_ns", monotonic_ns)
    monkeypatch.setattr(campaign.time, "sleep", sleep)
    return monotonic


def test_deterministic_small_shards_exercise_thirteen_shard_boundary(tmp_path):
    # 25 invented locators at a synthetic cap of 2 model 99,394 at 8,192.
    plan = _plan(*range(1, 26), shard_size=2)
    calls = []

    def transport(url, headers, cap):
        calls.append(url)
        assert headers["User-Agent"].endswith(f"({CONTACT})")
        assert cap > 0
        return _response(url)

    report_path = _run(plan, tmp_path / "first", transport)
    published_plan = _json(report_path.parent / "campaign-plan.json")
    shards = published_plan["shards"]
    assert len(shards) == 13
    assert [(s["start"], s["count"]) for s in shards] == [
        (2 * index, 2 if index < 12 else 1) for index in range(13)
    ]
    assert [s["name"] for s in shards] == [f"shard-{index:04d}" for index in range(13)]
    assert len({s["inventory_sha256"] for s in shards}) == 13
    assert calls == [item.url for item in plan.requests]
    assert _json(report_path)["complete_all_form4_parent_raw_set_acquired"] is True
    assert (report_path.parent / "commit.json").is_file()

    _run(plan, tmp_path / "second", lambda url, *_: _response(url))
    assert (tmp_path / "second" / "campaign-plan.json").read_bytes() == (
        tmp_path / "first" / "campaign-plan.json").read_bytes()


def test_global_dispatch_spacing_includes_shard_boundary(tmp_path, _fake_capacity_and_clock):
    plan = _plan(1, 2, 3, 4, shard_size=2)
    dispatches = []

    def transport(url, _headers, _cap):
        dispatches.append((url, _fake_capacity_and_clock[0]))
        return _response(url)

    _run(plan, tmp_path / "paced", transport)
    assert [url for url, _ in dispatches] == [item.url for item in plan.requests]
    assert all(later[1] - earlier[1] >= 500_000_000
               for earlier, later in zip(dispatches, dispatches[1:]))


def test_crash_resume_skips_completed_parent_and_prior_shard(tmp_path):
    plan = _plan(1, 2, 3, shard_size=2)
    output = tmp_path / "resumable"
    calls = []

    def interrupt_second(url, _headers, _cap):
        calls.append(url)
        if url == plan.requests[1].url:
            raise KeyboardInterrupt
        return _response(url)

    with pytest.raises(KeyboardInterrupt):
        _run(plan, output, interrupt_second)
    assert not (output / "commit.json").exists()

    def resumed(url, _headers, _cap):
        calls.append(url)
        return _response(url)

    report = _json(_run(plan, output, resumed, resume=True))
    assert calls.count(plan.requests[0].url) == 1
    assert calls.count(plan.requests[1].url) == 2
    assert calls.count(plan.requests[2].url) == 1
    assert report["attempt_count"] == 4
    assert report["complete_all_form4_parent_raw_set_acquired"] is True


def test_resume_after_committed_shard_does_not_repeat_its_requests(tmp_path):
    plan = _plan(1, 2, 3, 4, shard_size=2)
    output = tmp_path / "shard-boundary"
    calls = []

    def interrupt_next_shard(url, _headers, _cap):
        calls.append(url)
        if url == plan.requests[2].url:
            raise KeyboardInterrupt
        return _response(url)

    with pytest.raises(KeyboardInterrupt):
        _run(plan, output, interrupt_next_shard)
    committed_shard = output / "shard-0000" / "commit.json"
    prior_commit = committed_shard.read_bytes()
    assert not (output / "commit.json").exists()

    def resumed(url, _headers, _cap):
        calls.append(url)
        return _response(url)

    report = _json(_run(plan, output, resumed, resume=True))
    assert committed_shard.read_bytes() == prior_commit
    assert [calls.count(item.url) for item in plan.requests] == [1, 1, 2, 1]
    assert report["complete_all_form4_parent_raw_set_acquired"] is True


@pytest.mark.parametrize("change", ["source", "subset"])
def test_resume_refuses_changed_source_or_subset_before_network(tmp_path, change):
    plan = _plan(1, 2, 3)
    output = tmp_path / "identity"
    with pytest.raises(KeyboardInterrupt):
        _run(plan, output, lambda url, *_: (_ for _ in ()).throw(KeyboardInterrupt)
             if url == plan.requests[1].url else _response(url))
    if change == "source":
        modified = replace(plan, manifest_sha256="f" * 64)
    else:
        modified = replace(plan, requests=(_request(1), _request(4), _request(3)))
    with pytest.raises(campaign.CampaignError):
        _run(modified, output, lambda *_: pytest.fail("network was called"), resume=True)
    assert not (output / "commit.json").exists()


def test_corrupt_campaign_plan_refuses_resume_before_network(tmp_path):
    plan = _plan(1, 2)
    output = tmp_path / "corrupt-plan"
    with pytest.raises(KeyboardInterrupt):
        _run(plan, output, lambda url, *_: (_ for _ in ()).throw(KeyboardInterrupt)
             if url == plan.requests[1].url else _response(url))
    path = output / "campaign-plan.json"
    raw = path.read_bytes()
    assert b'"manifest_sha256":"' + b"c" * 64 + b'"' in raw
    path.write_bytes(raw.replace(b"c" * 64, b"f" * 64, 1))
    with pytest.raises(campaign.CampaignError):
        _run(plan, output, lambda *_: pytest.fail("network was called"), resume=True)
    assert not (output / "commit.json").exists()


def test_corrupt_hash_chain_event_refuses_resume_before_network(tmp_path):
    plan = _plan(1, 2)
    output = tmp_path / "corrupt-event"
    with pytest.raises(KeyboardInterrupt):
        _run(plan, output, lambda url, *_: (_ for _ in ()).throw(KeyboardInterrupt)
             if url == plan.requests[1].url else _response(url))
    event = sorted(output.rglob("event-*.json"))[0]
    raw = event.read_bytes()
    assert b'"kind"' in raw
    event.write_bytes(raw.replace(b'"kind"', b'"kinx"', 1))
    assert event.read_bytes() != raw
    with pytest.raises(campaign.CampaignError):
        _run(plan, output, lambda *_: pytest.fail("network was called"), resume=True)


def test_reuse_is_hash_bound_and_does_not_dispatch(tmp_path):
    first = _request(1)
    raw = _parent(first)
    reuse = campaign.CampaignReuse(
        accession_number=first.accession_number,
        object_sha256=hash_bytes(raw),
        object_size_bytes=len(raw),
        prior_report_sha256="e" * 64,
    )
    plan = _plan(1, 2, reuses=(reuse,))
    calls = []

    def transport(url, _headers, _cap):
        calls.append(url)
        return _response(url)

    with pytest.raises(campaign.CampaignError):
        _run(plan, tmp_path / "bad", transport,
             reused_bytes={first.accession_number: b"wrong"})
    assert not calls
    report = _json(_run(plan, tmp_path / "good", transport,
                        reused_bytes={first.accession_number: raw}))
    assert calls == [plan.requests[1].url]
    assert report["attempt_count"] == 1


@pytest.mark.parametrize("mismatch", [
    "outer_accession", "header_accession", "issuer_cik", "form_type",
])
def test_http_200_wrong_parent_identity_cannot_complete_or_advance(tmp_path, mismatch):
    plan = _plan(1, 2, shard_size=1)
    first = plan.requests[0]
    changes = {
        "outer_accession": {"accession": "0000000001-23-999999",
                            "header_accession": first.accession_number},
        "header_accession": {"header_accession": "0000000001-23-999999"},
        "issuer_cik": {"issuer_cik": "0000000003"},
        "form_type": {"form_type": "4/A"},
    }
    body = _parent(first, **changes[mismatch])
    calls = []

    def transport(url, _headers, _cap):
        calls.append(url)
        return _response(url, body=body)

    output = tmp_path / mismatch
    with pytest.raises(campaign.CampaignError, match="REFUSED"):
        _run(plan, output, transport)
    assert calls == [first.url]
    assert not (output / "commit.json").exists()
    events = [_json(path) for path in sorted(output.rglob("event-*.json"))]
    assert "source_envelope_refusal" in [event.get("outcome") for event in events]
    assert not any(event.get("kind") == "item-complete" for event in events)


@pytest.mark.parametrize("mismatch", [
    "outer_accession", "header_accession", "issuer_cik", "form_type",
])
def test_hash_matching_reused_wrong_parent_identity_cannot_complete(tmp_path, mismatch):
    first = _request(1)
    changes = {
        "outer_accession": {"accession": "0000000001-23-999999",
                            "header_accession": first.accession_number},
        "header_accession": {"header_accession": "0000000001-23-999999"},
        "issuer_cik": {"issuer_cik": "0000000003"},
        "form_type": {"form_type": "4/A"},
    }
    raw = _parent(first, **changes[mismatch])
    reuse = campaign.CampaignReuse(
        accession_number=first.accession_number,
        object_sha256=hash_bytes(raw),
        object_size_bytes=len(raw),
        prior_report_sha256="e" * 64,
    )
    output = tmp_path / mismatch
    with pytest.raises(campaign.CampaignError, match="REFUSED"):
        _run(_plan(1, 2, reuses=(reuse,)), output,
             lambda *_: pytest.fail("SEC transport was called"),
             reused_bytes={first.accession_number: raw})
    assert not (output / "commit.json").exists()
    assert not any(_json(path).get("kind") == "item-complete"
                   for path in output.rglob("event-*.json"))


def test_completed_root_replay_rechecks_header_identity(monkeypatch, tmp_path):
    plan = _plan(1)
    output = tmp_path / "historical-invalid-header"
    bad = _parent(plan.requests[0], issuer_cik="0000000003")
    with monkeypatch.context() as bypass:
        bypass.setattr(campaign, "_validate_parent_header", lambda *_: None)
        _run(plan, output, lambda url, *_: _response(url, body=bad))
    with pytest.raises(campaign.CampaignError, match="issuer CIK disagrees"):
        campaign.verify_completed_synthetic_campaign(
            plan, output, capture_git_commit=COMMIT,
        )


def test_three_attempt_ceiling_stops_campaign_without_final_commit(tmp_path):
    plan = _plan(1, 2, 3, shard_size=2)
    calls = []

    def unavailable(url, _headers, _cap):
        calls.append(url)
        return _response(status=503)

    output = tmp_path / "exhausted"
    with pytest.raises(campaign.CampaignError):
        _run(plan, output, unavailable)
    assert calls == [plan.requests[0].url] * 3
    assert not (output / "commit.json").exists()
    assert not list(output.glob("campaign-report-*.json"))


def test_terminal_http_denial_stops_all_later_shards(tmp_path):
    plan = _plan(1, 2, 3, shard_size=1)
    calls = []

    def denied(url, _headers, _cap):
        calls.append(url)
        return _response(status=403)

    output = tmp_path / "denied"
    with pytest.raises(campaign.CampaignError):
        _run(plan, output, denied)
    assert calls == [plan.requests[0].url]
    assert not (output / "commit.json").exists()


def test_terminal_shard_commit_cannot_be_replayed_into_a_complete_campaign(tmp_path):
    plan = _plan(1, 2, shard_size=1)
    output = tmp_path / "terminal-replay"
    with pytest.raises(campaign.CampaignError):
        _run(plan, output, lambda *_: _response(status=403))
    terminal_commit = output / "shard-0000" / "commit.json"
    prior_commit = terminal_commit.read_bytes()
    with pytest.raises(campaign.CampaignError):
        _run(plan, output, lambda *_: pytest.fail("network was called"), resume=True)
    assert terminal_commit.read_bytes() == prior_commit
    assert not (output / "commit.json").exists()


def test_final_commit_only_after_every_shard_and_authority_stays_false(tmp_path):
    plan = _plan(1, 2, 3, shard_size=1)
    report_path = _run(plan, tmp_path / "complete", lambda url, *_: _response(url))
    report = _json(report_path)
    commit = _json(report_path.parent / "commit.json")
    assert commit["report_sha256"] == hash_bytes(report_path.read_bytes())
    assert report["complete_all_form4_parent_raw_set_acquired"] is True
    assert report["source_scope"] == "synthetic_test_manifest"
    assert report["shard_count"] == 3
    assert report["research_looks"] == report["consumed_outcome_looks"] == 0
    assert all(report[key] is False for key in (
        "canonical_evidence", "point_in_time_data", "source_authenticated",
        "acceptance_metadata_verified", "qc_job_authorized",
        "outcome_access_authorized", "broker_or_trading_authorized",
    ))
    assert CONTACT.encode() not in report_path.read_bytes()
    assert CONTACT.encode() not in (report_path.parent / "campaign-plan.json").read_bytes()


def test_completed_root_verifier_is_aggregate_only_read_only_and_network_free(
    monkeypatch, tmp_path,
):
    plan = _plan(1, 2, 3, shard_size=2)
    output = tmp_path / "verified"
    report_path = _run(plan, output, lambda url, *_: _response(url))
    before = {str(path.relative_to(output)): hash_bytes(path.read_bytes())
              for path in output.rglob("*") if path.is_file()}
    monkeypatch.setattr(
        campaign, "_selected_sec_transport",
        lambda *_: pytest.fail("SEC transport was called by offline verifier"),
    )
    result = campaign.verify_completed_synthetic_campaign(
        plan, output, capture_git_commit=COMMIT,
    )
    after = {str(path.relative_to(output)): hash_bytes(path.read_bytes())
             for path in output.rglob("*") if path.is_file()}
    assert after == before
    assert type(result) is dict
    assert result["total_accessions"] == result["complete_count"] == 3
    assert result["reused_count"] == 0
    assert result["newly_acquired_count"] == result["attempt_count"] == 3
    assert result["shard_count"] == 2
    assert result["manifest_sha256"] == "c" * 64
    assert result["report_sha256"] == hash_bytes(report_path.read_bytes())
    assert result["canonical_evidence"] is False
    assert result["point_in_time_data"] is False
    assert result["research_looks"] == 0


@pytest.mark.parametrize("target", ["object", "event", "journal", "report"])
def test_completed_root_verifier_refuses_tampered_immutable_evidence(
    tmp_path, target,
):
    plan = _plan(1, 2, shard_size=1)
    output = tmp_path / target
    _run(plan, output, lambda url, *_: _response(url))
    paths = {
        "object": sorted(output.rglob("objects/*.bin")),
        "event": sorted(output.rglob("event-*.json")),
        "journal": sorted(output.rglob("attempts.jsonl")),
        "report": sorted(output.glob("campaign-report-*.json")),
    }
    path = paths[target][0]
    path.write_bytes(path.read_bytes() + b"x")
    with pytest.raises(campaign.CampaignError, match="REFUSED"):
        campaign.verify_completed_synthetic_campaign(
            plan, output, capture_git_commit=COMMIT,
        )


def test_resume_recovers_lock_only_campaign_root_before_any_request(tmp_path):
    plan = _plan(1)
    output = tmp_path / "lock-only-root"
    output.mkdir()
    (output / "run.lock").write_bytes(b"")
    calls = []
    result = _run(plan, output, lambda url, *_: (calls.append(url), _response(url))[1],
                  resume=True)
    assert result.is_file()
    assert calls == [plan.requests[0].url]


def test_resume_recovers_lock_and_empty_objects_shard_before_request(tmp_path):
    plan = _plan(1)
    output = tmp_path / "empty-shard"
    output.mkdir()
    (output / "run.lock").write_bytes(b"")
    shards = campaign._shards(plan, COMMIT)
    (output / "campaign-plan.json").write_bytes(
        campaign._campaign_plan(plan, COMMIT, shards),
    )
    shard = output / "shard-0000"
    shard.mkdir()
    (shard / "run.lock").write_bytes(b"")
    (shard / "objects").mkdir()
    calls = []
    result = _run(plan, output, lambda url, *_: (calls.append(url), _response(url))[1],
                  resume=True)
    assert result.is_file()
    assert calls == [plan.requests[0].url]
