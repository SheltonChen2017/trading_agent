"""Synthetic complete-submission replay; no real SEC bytes or network access."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from research import insider_buying_sec_complete_acquisition as runner
from research import insider_buying_sec_complete_projection_adapter as adapter
from research.insider_buying_sec_acquisition import SecPilotCandidate


CODE = "a" * 40
_INDEX_HEADER = (
    b"Description: Master Index of EDGAR Dissemination Feed\n"
    b"Last Data Received: March 31, 2023\n"
    b"Comments: webmaster@sec.gov\n\n"
    b"CIK|Company Name|Form Type|Date Filed|Filename\n"
    b"--------------------------------------------------------------------------------\n"
)


def _candidates() -> tuple[SecPilotCandidate, ...]:
    items = []
    for index, accession in enumerate(adapter.FIXED_ACCESSIONS):
        period = "2022Q4" if index < 8 else "2023Q1"
        items.append(SecPilotCandidate(
            period=period, accession_number=accession,
            form_type="4" if index % 8 < 6 else "4/A",
            filing_date="2022-11-07" if index < 8 else "2023-02-10",
            filing_date_raw="INVENTED", issuer_cik="0000123456",
            quarterly_zip_sha256=runner._QUARTER_ZIP_SHA256[period],
            submission_row_id="b" * 64, raw_snapshot_id="invented",
            raw_lineage_sha256="c" * 64,
        ))
    return tuple(items)


def _index(items: tuple[SecPilotCandidate, ...], period: str) -> bytes:
    return _INDEX_HEADER + b"".join(
        (f"888888|Invented Corp|{item.form_type}|{item.filing_date}|"
         f"edgar/data/123456/{item.accession_number}.txt\n").encode("ascii")
        for item in items if item.period == period
    )


def _complete(item: SecPilotCandidate) -> bytes:
    compact = item.filing_date.replace("-", "")
    return (
        f"<SEC-DOCUMENT>{item.accession_number}.txt : {compact}\n"
        f"<SEC-HEADER>{item.accession_number}.hdr.sgml : {compact}\n"
        f"<ACCEPTANCE-DATETIME>{compact}101112\n"
        f"<ACCESSION-NUMBER>{item.accession_number}\n<TYPE>{item.form_type}\n"
        f"<FILING-DATE>{compact}\n"
        "<REPORTING-OWNER>\n<OWNER-DATA>\n<CIK>0000002178\n"
        "<CONFORMED-NAME>Invented Owner\n</OWNER-DATA>\n</REPORTING-OWNER>\n"
        f"<ISSUER>\n<COMPANY-DATA>\n<CIK>{item.issuer_cik}\n"
        "</COMPANY-DATA>\n</ISSUER>\n</SEC-HEADER>\n"
        f"<DOCUMENT>\n<TYPE>{item.form_type}\n<SEQUENCE>1\n"
        "<FILENAME>ownership.xml\n<DESCRIPTION>Invented document\n<TEXT>\n"
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        f"<ownershipDocument><documentType>{item.form_type}</documentType>"
        f"<issuer><issuerCik>{item.issuer_cik}</issuerCik></issuer>"
        "<reportingOwner><reportingOwnerId><rptOwnerCik>0000002178</rptOwnerCik>"
        "</reportingOwnerId></reportingOwner></ownershipDocument>\n"
        "</TEXT>\n</DOCUMENT>\n</SEC-DOCUMENT>\n"
    ).encode("ascii")


def _canonical(value: object) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def _publication(monkeypatch, tmp_path: Path) -> tuple[Path, str, str]:
    items = _candidates()
    images = {
        runner._MASTER_URLS[period]: gzip.compress(_index(items, period), mtime=0)
        for period in ("2022Q4", "2023Q1")
    }
    for item in items:
        images[f"https://www.sec.gov/Archives/edgar/data/123456/{item.accession_number}.txt"] = _complete(item)
    assert len(images) == 18
    source, prior, output = (tmp_path / name for name in ("source", "prior", "output"))
    source.mkdir()
    prior.mkdir()
    monkeypatch.setattr(runner, "_verify_exact_committed_code", lambda _: None)
    monkeypatch.setattr(runner, "select_fixed_pilot", lambda _source, _prior: items)
    inventory_sha = hash_payload([item.to_payload() for item in items])
    monkeypatch.setattr(runner, "_APPROVED_SIXTEEN_INVENTORY_SHA256", inventory_sha)
    # Each clock read advances more than the 500 ms transport interval. The
    # synthetic transport never sleeps or touches the network.
    clock = [1_000_000_000]

    def now_ns() -> int:
        clock[0] += 600_000_000
        return clock[0]

    monkeypatch.setattr(runner.time, "monotonic_ns", now_ns)
    monkeypatch.setattr(runner.time, "sleep", lambda _: None)

    def transport(url, headers, max_bytes):
        assert url in images and max_bytes >= len(images[url])
        assert "synthetic@example.org" in headers["User-Agent"]
        raw = images[url]
        return runner.SecHttpResult(200, (("Content-Length", str(len(raw))),), raw)

    report_path = runner.run_fixed_complete_submissions(
        source, prior, output, contact_email="synthetic@example.org",
        capture_git_commit=CODE, transport=transport,
    )
    report_sha = report_path.name.removeprefix("sec-complete-report-").removesuffix(".json")
    assert "synthetic@example.org" not in report_path.read_text(encoding="utf-8")
    return output, report_sha, inventory_sha


def _load(root: Path, report_sha: str, inventory_sha: str):
    return adapter._load_complete_pilot(
        root, report_sha256=report_sha, inventory_sha256=inventory_sha,
        code_commit=CODE, expected_accessions=adapter.FIXED_ACCESSIONS,
    )


def _rebind_report(root: Path, old_sha: str, report: dict[str, object]) -> str:
    old_name = f"sec-complete-report-{old_sha}.json"
    (root / old_name).unlink()
    raw = _canonical(report)
    new_sha = hash_bytes(raw)
    new_name = f"sec-complete-report-{new_sha}.json"
    (root / new_name).write_bytes(raw)
    (root / "commit.json").write_bytes(_canonical({
        "kind": "sec-complete-commit", "report_name": new_name,
        "report_sha256": new_sha,
        "attempt_journal_sha256": report["attempt_journal"]["sha256"],
    }))
    return new_sha


def _rebind_journal(root: Path, report_sha: str, events: list[dict[str, object]]) -> str:
    report_path = root / f"sec-complete-report-{report_sha}.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    old_sha = report["attempt_journal"]["sha256"]
    (root / "objects" / f"{old_sha}.bin").unlink()
    raw = b"".join(_canonical(event) for event in events)
    new_sha = hash_bytes(raw)
    (root / "attempts.jsonl").write_bytes(raw)
    (root / "objects" / f"{new_sha}.bin").write_bytes(raw)
    report["attempt_journal"] = {
        "relative_path": f"objects/{new_sha}.bin", "sha256": new_sha,
        "size_bytes": len(raw),
    }
    return _rebind_report(root, report_sha, report)


def test_synthetic_exact_sixteen_replays_with_no_promoted_authority(monkeypatch, tmp_path):
    root, report_sha, inventory_sha = _publication(monkeypatch, tmp_path)
    receipt = _load(root, report_sha, inventory_sha)
    payload = receipt.to_payload()
    assert len(payload["rows"]) == 16
    assert tuple(item["accession_number"] for item in payload["rows"]) == adapter.FIXED_ACCESSIONS
    assert {item["period"] for item in payload["rows"]} == {"2022Q4", "2023Q1"}
    assert payload["source_report_sha256"] == report_sha
    assert payload["authority"]["canonical_evidence"] is False
    assert payload["authority"]["direct_ib1c_ingest_authorized"] is False
    assert payload["authority"]["research_looks"] == 0
    assert payload["authority"]["qc_job_authorized"] is False
    assert payload["authority"]["input_scope"] == "synthetic_test_receipt"


def test_receipt_rejects_rebinding_synthetic_as_public_pilot(monkeypatch, tmp_path):
    root, report_sha, inventory_sha = _publication(monkeypatch, tmp_path)
    receipt = _load(root, report_sha, inventory_sha)
    object.__setattr__(receipt, "_public_pilot", True)
    with pytest.raises(adapter.SecCompletePilotAdapterError, match="REFUSED"):
        receipt.to_payload()


def test_public_loader_refuses_a_different_synthetic_report(monkeypatch, tmp_path):
    root, _, _ = _publication(monkeypatch, tmp_path)
    with pytest.raises(adapter.SecCompletePilotAdapterError, match="REFUSED"):
        adapter.load_fixed_complete_pilot(root)


@pytest.mark.parametrize("swapped", ("root", "objects"))
def test_directory_symlink_swap_cannot_redirect_verified_reads(monkeypatch, tmp_path, swapped):
    root, report_sha, inventory_sha = _publication(monkeypatch, tmp_path)
    original_read = adapter._read
    swapped_once = False

    def swap_before_first_file_read(path, name, *, label, max_bytes):
        nonlocal swapped_once
        if not swapped_once and name == "commit.json":
            source = root if swapped == "root" else root / "objects"
            outside = tmp_path / f"outside-{swapped}"
            source.rename(outside)
            source.symlink_to(outside, target_is_directory=True)
            swapped_once = True
        return original_read(path, name, label=label, max_bytes=max_bytes)

    monkeypatch.setattr(adapter, "_read", swap_before_first_file_read)
    with pytest.raises(adapter.SecCompletePilotAdapterError, match="REFUSED"):
        _load(root, report_sha, inventory_sha)
    assert swapped_once


def test_extra_root_file_and_object_alias_refuse(monkeypatch, tmp_path):
    root, report_sha, inventory_sha = _publication(monkeypatch, tmp_path)
    (root / "extra").write_text("unexpected", encoding="utf-8")
    with pytest.raises(adapter.SecCompletePilotAdapterError, match="topology"):
        _load(root, report_sha, inventory_sha)
    (root / "extra").unlink()
    (root / "objects" / "extra.bin").write_bytes(b"unexpected")
    with pytest.raises(adapter.SecCompletePilotAdapterError, match="object directory"):
        _load(root, report_sha, inventory_sha)


def test_raw_object_corruption_refuses_even_with_intact_report(monkeypatch, tmp_path):
    root, report_sha, inventory_sha = _publication(monkeypatch, tmp_path)
    report = json.loads((root / f"sec-complete-report-{report_sha}.json").read_text())
    descriptor = report["filings"][0]["raw_object"]
    (root / descriptor["relative_path"]).write_bytes(b"corrupt")
    with pytest.raises(adapter.SecCompletePilotAdapterError, match="REFUSED"):
        _load(root, report_sha, inventory_sha)


def test_coherently_rebound_projection_row_is_rederived_and_refused(monkeypatch, tmp_path):
    root, report_sha, inventory_sha = _publication(monkeypatch, tmp_path)
    report = json.loads((root / f"sec-complete-report-{report_sha}.json").read_text())
    report["filings"][0]["projection"]["children"]["primary_xml"]["sha256"] = "0" * 64
    new_sha = _rebind_report(root, report_sha, report)
    with pytest.raises(adapter.SecCompletePilotAdapterError, match="projection differs"):
        _load(root, new_sha, inventory_sha)


@pytest.mark.parametrize("change", ("status", "url", "pacing"))
def test_coherently_rebound_journal_anomaly_refuses(monkeypatch, tmp_path, change):
    root, report_sha, inventory_sha = _publication(monkeypatch, tmp_path)
    events = [json.loads(line) for line in (root / "attempts.jsonl").read_text().splitlines()]
    if change == "status":
        events[1]["status"] = 201
    elif change == "url":
        events[2]["url"] = events[0]["url"]
    else:
        previous_end = events[1]["request_end_monotonic_ns"]
        events[3]["request_start_monotonic_ns"] = previous_end + 1
    new_sha = _rebind_journal(root, report_sha, events)
    with pytest.raises(adapter.SecCompletePilotAdapterError, match="REFUSED"):
        _load(root, new_sha, inventory_sha)


def test_duplicate_json_key_refuses_before_receipt(monkeypatch, tmp_path):
    root, report_sha, inventory_sha = _publication(monkeypatch, tmp_path)
    commit = root / "commit.json"
    raw = commit.read_bytes().removesuffix(b"\n")
    commit.write_bytes(raw[:-1] + b',"kind":"sec-complete-commit"}\n')
    with pytest.raises(adapter.SecCompletePilotAdapterError, match="repeats a key"):
        _load(root, report_sha, inventory_sha)


def test_malformed_journal_descriptor_refuses_with_domain_error(monkeypatch, tmp_path):
    root, report_sha, inventory_sha = _publication(monkeypatch, tmp_path)
    report_path = root / f"sec-complete-report-{report_sha}.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["attempt_journal"] = []
    report_path.unlink()
    raw = _canonical(report)
    new_sha = hash_bytes(raw)
    (root / f"sec-complete-report-{new_sha}.json").write_bytes(raw)
    with pytest.raises(adapter.SecCompletePilotAdapterError, match="journal descriptor"):
        _load(root, new_sha, inventory_sha)


def test_receipt_rechecks_caller_mutation(monkeypatch, tmp_path):
    root, report_sha, inventory_sha = _publication(monkeypatch, tmp_path)
    receipt = _load(root, report_sha, inventory_sha)
    object.__setattr__(receipt, "projections", receipt.projections[:-1])
    with pytest.raises(adapter.SecCompletePilotAdapterError, match="partial|binding"):
        receipt.to_payload()


# Section 107 (Claude review): replay-side regression for IBSECCOM-CR02.
def test_corrupt_master_deflate_stream_is_a_typed_refusal():
    good = gzip.compress(_index(_candidates(), "2022Q4"), mtime=0)
    with pytest.raises(adapter.SecCompletePilotAdapterError, match="master.gz is malformed"):
        adapter._master_plain(good[:10] + b"\xff" + good[11:])
