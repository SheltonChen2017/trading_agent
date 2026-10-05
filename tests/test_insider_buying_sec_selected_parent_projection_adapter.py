"""Synthetic selected-parent roots only; no SEC or QC access."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.insider_buying_sec_selected_parent_runner as runner
import research.insider_buying_sec_selected_parent_projection_adapter as adapter
from research.insider_buying_sec_selected_parent_projection_adapter import (
    SecSelectedParentProjectionError,
    SelectedParentProjectionReceipt,
    load_observed_selected_parent_root,
    replay_synthetic_selected_parent_root,
)


_COMMIT = "d" * 40
_CONTACT = "research@example.test"


def _request(number: int, *, form: str = "4") -> runner.SelectedParentRequest:
    accession = f"0000999999-22-{number:06d}"
    return runner.SelectedParentRequest(
        period="2022Q4", accession_number=accession, form_type=form,
        filing_date="2022-11-07", issuer_cik="0000123456",
        master_source_sha256="a" * 64, parsed_lineage_hash="b" * 64,
        url=f"https://www.sec.gov/Archives/edgar/data/999999/{accession}.txt",
    )


def _plan(*requests: runner.SelectedParentRequest) -> runner.SelectedParentPlan:
    return runner.SelectedParentPlan(
        scope="synthetic_test_manifest", locator_manifest_sha256="c" * 64,
        requests=requests,
        request_inventory_sha256=hash_payload([row.to_payload() for row in requests]),
    )


def _parent(request: runner.SelectedParentRequest, *, owners: tuple[str, ...]) -> bytes:
    accession = request.accession_number
    header_owners = b"".join(
        ("<REPORTING-OWNER>\n<OWNER-DATA>\n"
         f"<CIK>{cik}\n<CONFORMED-NAME>Invented Owner\n"
         "</OWNER-DATA>\n</REPORTING-OWNER>\n").encode("ascii")
        for cik in owners
    )
    xml_owners = b"".join(
        ("<reportingOwner><reportingOwnerId>"
         f"<rptOwnerCik>{cik}</rptOwnerCik>"
         "</reportingOwnerId></reportingOwner>").encode("ascii")
        for cik in owners
    )
    header = (
        f"<SEC-HEADER>{accession}.hdr.sgml : 20221107\n"
        "<ACCEPTANCE-DATETIME>20221107101112\n"
        f"<ACCESSION-NUMBER>{accession}\n<TYPE>{request.form_type}\n"
        "<FILING-DATE>20221107\n"
    ).encode("ascii") + header_owners + (
        b"<ISSUER>\n<COMPANY-DATA>\n<CIK>0000123456\n"
        b"</COMPANY-DATA>\n</ISSUER>\n</SEC-HEADER>\n"
    )
    xml = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        + f"<ownershipDocument><documentType>{request.form_type}</documentType>".encode("ascii")
        + b"<issuer><issuerCik>0000123456</issuerCik></issuer>"
        + xml_owners + b"</ownershipDocument>\n"
    )
    return (
        f"<SEC-DOCUMENT>{accession}.txt : 20221107\n".encode("ascii")
        + header
        + f"<DOCUMENT>\n<TYPE>{request.form_type}\n".encode("ascii")
        + b"<SEQUENCE>1\n<FILENAME>ownership.xml\n<TEXT>\n"
        + xml + b"</TEXT>\n</DOCUMENT>\n</SEC-DOCUMENT>\n"
    )


def _root(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_capacity", lambda *_: True)
    requests = (_request(1), _request(2, form="4/A"))
    plan = _plan(*requests)
    parents = {
        requests[0].url: _parent(requests[0], owners=("0000999999",)),
        requests[1].url: _parent(requests[1], owners=("0000999999", "0000888888")),
    }

    def transport(url, _headers, _cap):
        body = parents[url]
        return runner.SecHttpResult(200, (("Content-Length", str(len(body))),), body)

    report = runner._run_selected(
        plan, tmp_path / "selected", contact_email=_CONTACT,
        capture_git_commit=_COMMIT, transport=transport,
    )
    return plan, report.parent


def test_replay_projects_exact_parents_but_never_promotes_amendment_or_multiowner(tmp_path, monkeypatch):
    plan, root = _root(tmp_path, monkeypatch)
    receipt = replay_synthetic_selected_parent_root(root, plan)
    assert receipt.source_scope == "synthetic_test_manifest"
    assert len(receipt.rows) == 2
    assert [row.accession_number for row in receipt.rows] == [
        request.accession_number for request in plan.requests
    ]
    assert receipt.rows[0].header_owner_ciks == ("0000999999",)
    assert receipt.rows[1].header_owner_ciks == ("0000999999", "0000888888")
    assert receipt.amendment_count == 1
    assert receipt.multi_owner_count == 1
    assert receipt.report_sha256 == json.loads((root / "commit.json").read_text())["report_sha256"]
    assert receipt.projections_verified is True
    assert receipt.quarter_population_complete is False
    assert receipt.acceptance_timezone_verified is False
    assert receipt.amendment_links_verified is False
    assert receipt.multi_owner_economic_attribution_verified is False
    assert receipt.canonical_evidence is False
    assert receipt.point_in_time_data is False
    assert receipt.research_looks == 0


@pytest.mark.parametrize("mutation", ["missing_object", "changed_object", "extra_object", "reordered_journal", "changed_event"])
def test_replay_refuses_missing_changed_or_reordered_source_bytes(tmp_path, monkeypatch, mutation):
    plan, root = _root(tmp_path, monkeypatch)
    report_name = json.loads((root / "commit.json").read_text())["report_name"]
    report = json.loads((root / report_name).read_text())
    object_path = root / report["rows"][0]["raw_object"]["relative_path"]
    if mutation == "missing_object":
        object_path.unlink()
    elif mutation == "changed_object":
        object_path.write_bytes(b"changed")
    elif mutation == "extra_object":
        (root / "objects" / ("f" * 64 + ".bin")).write_bytes(b"extra")
    elif mutation == "changed_event":
        event = sorted(root.glob("event-*.json"))[0]
        raw = json.loads(event.read_text())
        raw["url"] = "https://www.sec.gov/Archives/edgar/data/1/other.txt"
        event.write_bytes((canonical_json(raw) + "\n").encode())
    else:
        journal = root / "attempts.jsonl"
        lines = journal.read_bytes().splitlines(keepends=True)
        journal.write_bytes(b"".join(reversed(lines)))
    with pytest.raises(SecSelectedParentProjectionError, match="REFUSED"):
        replay_synthetic_selected_parent_root(root, plan)


def test_replay_refuses_wrong_expected_request_even_if_root_self_consistent(tmp_path, monkeypatch):
    plan, root = _root(tmp_path, monkeypatch)
    wrong = _plan(plan.requests[0], replace(plan.requests[1], issuer_cik="0000777777"))
    with pytest.raises(SecSelectedParentProjectionError, match="REFUSED"):
        replay_synthetic_selected_parent_root(root, wrong)


def test_replay_refuses_report_authority_even_with_rehashed_commit(tmp_path, monkeypatch):
    plan, root = _root(tmp_path, monkeypatch)
    commit_path = root / "commit.json"
    commit = json.loads(commit_path.read_text())
    original = root / commit["report_name"]
    report = json.loads(original.read_text())
    report["canonical_evidence"] = True
    raw = (canonical_json(report) + "\n").encode()
    new_sha = hash_bytes(raw)
    name = f"sec-selected-parents-report-{new_sha}.json"
    original.unlink()
    (root / name).write_bytes(raw)
    commit["report_name"] = name
    commit["report_sha256"] = new_sha
    commit_path.write_bytes((canonical_json(commit) + "\n").encode())
    with pytest.raises(SecSelectedParentProjectionError, match="REFUSED"):
        replay_synthetic_selected_parent_root(root, plan)


def test_replay_refuses_incomplete_root_without_partial_projection(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_capacity", lambda *_: True)
    request = _request(1)
    plan = _plan(request)
    runner._run_selected(
        plan, tmp_path / "missing", contact_email=_CONTACT,
        capture_git_commit=_COMMIT,
        transport=lambda *_: runner.SecHttpResult(404, (("Content-Length", "0"),), b""),
    )
    with pytest.raises(SecSelectedParentProjectionError, match="REFUSED"):
        replay_synthetic_selected_parent_root(tmp_path / "missing", plan)


def test_real_entry_refuses_unbound_quarters_and_receipt_cannot_be_forged(tmp_path):
    with pytest.raises(SecSelectedParentProjectionError, match="REFUSED"):
        load_observed_selected_parent_root(tmp_path / "missing", ())
    with pytest.raises(TypeError):
        SelectedParentProjectionReceipt(
            source_scope="synthetic_test_manifest", locator_manifest_sha256="c" * 64,
            request_inventory_sha256="d" * 64, inventory_sha256="e" * 64,
            attempt_journal_sha256="f" * 64, report_sha256="a" * 64,
            capture_git_commit=_COMMIT, rows=(), lineage_sha256="b" * 64,
        )


def test_replay_refuses_lock_replacement_during_projection(tmp_path, monkeypatch):
    plan, root = _root(tmp_path, monkeypatch)
    original = adapter.project_sec_complete_submission
    changed = False

    def replace_lock(target, raw):
        nonlocal changed
        projection = original(target, raw)
        if not changed:
            (root / "run.lock").unlink()
            (root / "run.lock").write_bytes(b"")
            changed = True
        return projection

    monkeypatch.setattr(adapter, "project_sec_complete_submission", replace_lock)
    with pytest.raises(SecSelectedParentProjectionError, match="REFUSED"):
        replay_synthetic_selected_parent_root(root, plan)
