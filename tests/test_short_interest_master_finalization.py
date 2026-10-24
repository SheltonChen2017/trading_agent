"""Fabricated protected receipts; no credentials or source requests."""
from __future__ import annotations

import io
import json
from pathlib import Path
import zipfile

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts.qualify_finra_short_interest import _prepare_capture_directory, _publish, _publish_json
import scripts.finalize_short_interest_master_offline as finalize
import os

# Only protected-I/O cases require POSIX; pure parsing, transport and early
# refusal checks must remain active on the supported Windows host.
_POSIX_CAPTURE_ONLY = pytest.mark.skipif(
    not hasattr(os, "getuid"),
    reason=(
        "the protected-capture runtime requires POSIX ownership and mode "
        "semantics (os.getuid, O_NOFOLLOW, 0o600/0o700, symlinks); it cannot "
        "execute on this host, see the lane record SI-CR17-002"
    ),
)

START = "2026-10-12T05:58:00Z"
END = "2026-10-12T06:01:39Z"


def zipped(table):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(table + ".csv", "a,b\nfixture,only\n")
    return buffer.getvalue()


def source(tmp_path, monkeypatch, *, change=None):
    directory = _prepare_capture_directory(tmp_path / finalize.SOURCE)
    protocol = finalize.master.qualification_protocol()
    start = {"schema": "si-sharadar-master-capture-start-v1", "run_id": directory.name,
        "started_at": START, "code_head": finalize.SOURCE_HEAD, "remote_head": finalize.SOURCE_REMOTE,
        "protocol_sha256": finalize.master.PROTOCOL_SHA256, "maximum_attempts": 12,
        "source_only": True, "outcome_looks_consumed": 0, "qc_launch_attempts": 0}
    claim = {"schema": "si-sharadar-master-whole-round-budget-v1", "run_id": directory.name,
        "protocol_sha256": finalize.master.PROTOCOL_SHA256, "code_head": finalize.SOURCE_HEAD,
        "remote_head": finalize.SOURCE_REMOTE, "maximum_attempts": 12, "started_at": START,
        "resumption_allowed": False}
    blobs = {"protocol.json": protocol, "started.json": start,
        "refused.json": {"status": "capture_refused", "code": "private_report_size_limit",
            "http_status": None, "backtest_result_exists": False, "refused_at": END,
            "outcome_looks_consumed": 0, "qc_launch_attempts": 0}}
    raw_blobs = {}
    for ordinal, rid in enumerate(finalize.master.REQUEST_IDS, 1):
        kind, table = rid.split("-", 1)
        prefix = f"attempt-{ordinal:02d}"
        began_at = f"2026-10-12T05:58:{ordinal:02d}Z"
        received_at = began_at
        spec, digest = finalize.master.sharadar_master_request(rid), finalize.master.request_sha256(rid)
        blobs[prefix + ".started.json"] = {"schema": "si-sharadar-master-request-start-v1",
            "attempt": ordinal, "request_id": rid, "request": spec, "request_sha256": digest,
            "code_head": finalize.SOURCE_HEAD, "protocol_sha256": finalize.master.PROTOCOL_SHA256,
            "started_at": began_at}
        if kind == "metadata":
            raw = canonical_json({"table": table, "name": table + ".csv.zip", "size": len(zipped(table)),
                                  "sizeLabel": "fixture", "modified": "2026-10-12T05:00:00Z"}).encode()
        elif kind == "schema":
            raw = ("CREATE TABLE " + table + " (x TEXT);").encode()
        else:
            raw = None if kind == "issue" else zipped(table)
        if raw is not None:
            raw_blobs[prefix + ".raw"] = raw
        blobs[prefix + ".received.json"] = {"schema": "si-sharadar-master-response-receipt-v1",
            "attempt": ordinal, "request_id": rid, "request_sha256": digest,
            "http_status": 302 if raw is None else 200, "content_type": None if raw is None else "fixture/plain",
            "raw_path": None if raw is None else prefix + ".raw", "raw_bytes": None if raw is None else len(raw),
            "raw_sha256": None if raw is None else hash_bytes(raw), "received_at": received_at,
            "signed_URL_persisted_or_hashed": False}
    if change:
        change(blobs, claim)
    for name, value in blobs.items():
        _publish_json(directory, name, value)
    for name, value in raw_blobs.items():
        _publish(directory, name, value)
    budget = directory.parent / ("budget-" + finalize.master.PROTOCOL_SHA256 + ".json")
    _publish_json(directory.parent, budget.name, claim)
    inventory = [{"name": name, "sha256": hash_bytes((directory / name).read_bytes())}
                 for name in finalize._source_names()]
    monkeypatch.setattr(finalize, "SOURCE_INVENTORY_SHA256", hash_payload(inventory))
    monkeypatch.setattr(finalize, "BUDGET_SHA256", hash_bytes(budget.read_bytes()))
    return directory


@_POSIX_CAPTURE_ONLY
def test_all_consumed_receipts_reload_once_without_key_or_transport(tmp_path, monkeypatch):
    directory = source(tmp_path, monkeypatch)
    captures, anchor = finalize._reload(tmp_path)
    assert tuple(item.table for item in captures) == finalize.master.TABLES
    assert anchor == END
    assert len(list(directory.glob("attempt-*.started.json"))) == 12
    assert not hasattr(finalize, "_read_key") and not hasattr(finalize, "_http")


@pytest.mark.parametrize("field,value", [("attempt", True), ("http_status", 200.0),
    ("raw_bytes", 1), ("raw_sha256", "a" * 64), ("request_id", "download-actions"),
    ("received_at", "2026-10-12T05:00:00Z"), ("signed_URL_persisted_or_hashed", 0)])
@_POSIX_CAPTURE_ONLY
def test_response_receipt_dangerous_changes_refuse_before_qualification(tmp_path, monkeypatch, field, value):
    source(tmp_path, monkeypatch, change=lambda blobs, claim:
           blobs["attempt-08.received.json"].__setitem__(field, value))
    with pytest.raises(finalize.CaptureRefusal):
        finalize._reload(tmp_path)


@pytest.mark.parametrize("record,field,value", [("started.json", "code_head", "b" * 40),
    ("started.json", "source_only", 1), ("started.json", "qc_launch_attempts", False),
    ("refused.json", "code", "another_failure"), ("refused.json", "backtest_result_exists", 0),
    ("refused.json", "refused_at", "2026-10-12T05:58:01Z")])
@_POSIX_CAPTURE_ONLY
def test_only_the_observed_post_capture_failure_can_be_finalized(tmp_path, monkeypatch, record, field, value):
    source(tmp_path, monkeypatch, change=lambda blobs, claim: blobs[record].__setitem__(field, value))
    with pytest.raises(finalize.CaptureRefusal):
        finalize._reload(tmp_path)


@pytest.mark.parametrize("kind", ["extra", "changed_bytes", "changed_claim", "symlink", "permissions"])
@_POSIX_CAPTURE_ONLY
def test_protected_pinned_inventory_cannot_be_replaced_or_extended(tmp_path, monkeypatch, kind):
    directory = source(tmp_path, monkeypatch)
    if kind == "extra":
        _publish_json(directory, "attempt-13.started.json", {"fake": True})
    elif kind == "changed_bytes":
        monkeypatch.setattr(finalize, "SOURCE_INVENTORY_SHA256", "a" * 64)
    elif kind == "changed_claim":
        monkeypatch.setattr(finalize, "BUDGET_SHA256", "a" * 64)
    elif kind == "permissions":
        (directory / "attempt-08.raw").chmod(0o644)
    else:
        original = directory / "attempt-08.raw"
        moved = tmp_path / "fake-archive"
        original.rename(moved)
        original.symlink_to(moved)
    with pytest.raises(finalize.CaptureRefusal):
        finalize._reload(tmp_path)


@_POSIX_CAPTURE_ONLY
def test_exclusive_offline_output_cannot_overwrite_or_reset_capture(tmp_path, monkeypatch):
    directory = source(tmp_path, monkeypatch)
    output = _prepare_capture_directory(directory / finalize.OUTPUT_NAME)
    _publish_json(output, "started.json", {"fake": True})
    monkeypatch.setattr(finalize, "_guard", lambda *args: None)
    with pytest.raises(FileExistsError):
        finalize._finalize(tmp_path, head="a" * 40, remote="b" * 40)
    assert json.loads((directory / "refused.json").read_bytes())["code"] == "private_report_size_limit"
    assert json.loads((output / "started.json").read_bytes()) == {"fake": True}


@pytest.mark.parametrize("reverse_completion_clock", [False, True])
@_POSIX_CAPTURE_ONLY
def test_finalizer_publishes_exact_codec_bytes_with_no_new_request_or_secret_read(tmp_path, monkeypatch, reverse_completion_clock):
    directory = source(tmp_path, monkeypatch)
    guards = []
    monkeypatch.setattr(finalize, "_guard", lambda *args: guards.append(args))
    monkeypatch.setattr(finalize, "_code_identity", lambda *args: "a" * 64)
    class Report:
        def to_payload(self):
            return {"fabricated_only": True}
    monkeypatch.setattr(finalize.master, "qualify_sharadar_securities_master", lambda *args, **kwargs: Report())
    class Index:
        def to_bytes(self):
            return b'{"fabricated_index":true}'
        def to_payload(self):
            return {"index_sha256": "c" * 64}
    class Segmented:
        parts = (b"fabricated-byte-part",)
        index = Index()
    def encode(raw, *, provenance):
        assert raw == b'{"fabricated_only":true}'
        assert provenance.reconstruction_anchor_utc == END
        assert provenance.source_capture_receipt_sha256 == finalize.SOURCE_INVENTORY_SHA256
        return Segmented()
    monkeypatch.setattr(finalize.segments, "encode_report", encode)
    if reverse_completion_clock:
        clocks = iter(["2026-10-12T06:10:00Z", "2026-10-12T06:09:59Z", "2026-10-12T06:10:01Z"])
        monkeypatch.setattr(finalize, "_utc_now", lambda: next(clocks))
        with pytest.raises(finalize.CaptureRefusal):
            finalize._finalize(tmp_path, head="a" * 40, remote="b" * 40)
        output = directory / finalize.OUTPUT_NAME
        assert not (output / "completed.json").exists()
        assert (output / "refused.json").exists()
        assert (output / "part-001.private").exists()
        assert (directory / "refused.json").exists()
        return
    result = finalize._finalize(tmp_path, head="a" * 40, remote="b" * 40)
    output = directory / finalize.OUTPUT_NAME
    assert len(guards) == 3
    assert (output / "index.private.json").read_bytes() == Index().to_bytes()
    assert (output / "part-001.private").read_bytes() == Segmented.parts[0]
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in output.iterdir())
    assert result["status"] == "offline_finalization_complete"
    assert result["provider_requests"] == result["credential_reads"] == result["qc_attempts"] == 0
    assert result["outcome_looks"] == 0 and result["backtest_result_exists"] is False
    assert (directory / "refused.json").exists()


@pytest.mark.parametrize("early_guard_failure", [True, False])
@_POSIX_CAPTURE_ONLY
def test_failed_or_repeated_invocation_cannot_append_refusal_to_prior_completed_output(tmp_path, monkeypatch, early_guard_failure):
    directory = source(tmp_path, monkeypatch)
    output = _prepare_capture_directory(directory / finalize.OUTPUT_NAME)
    _publish_json(output, "started.json", {"fake_prior_start": True})
    _publish_json(output, "completed.json", {"fake_prior_completion": True})
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    monkeypatch.chdir(tmp_path)
    def guard(*args):
        if early_guard_failure:
            raise finalize.CaptureRefusal("fake lane changed")
    monkeypatch.setattr(finalize, "_guard", guard)
    assert finalize.main(["--expected-head", "a" * 40, "--expected-remote", "b" * 40]) == 2
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before


@_POSIX_CAPTURE_ONLY
def test_new_finalization_cannot_start_before_observed_source_refusal(tmp_path, monkeypatch):
    directory = source(tmp_path, monkeypatch)
    monkeypatch.setattr(finalize, "_guard", lambda *args: None)
    monkeypatch.setattr(finalize, "_utc_now", lambda: "2026-10-12T06:00:00Z")
    monkeypatch.setattr(finalize, "_write_report", lambda *args, **kwargs: {"status": "fake"})
    with pytest.raises(finalize.CaptureRefusal, match="chronology"):
        finalize._finalize(tmp_path, head="a" * 40, remote="b" * 40)
    assert not (directory / finalize.OUTPUT_NAME).exists()
