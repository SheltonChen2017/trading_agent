"""Synthetic R297 duplicates: no operational leaves, IDs or provider access."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest

from scripts import characterize_arv2_r297_duplicates as d

HEAD, SHA = "a" * 40, "b" * 64


@pytest.fixture(autouse=True)
def isolation(monkeypatch):
    monkeypatch.setattr(d.subprocess, "run", lambda *_a, **_k: pytest.fail("real commands forbidden"))
    monkeypatch.setattr(d.delta, "authenticate_capture", lambda *_a, **_k: pytest.fail("old authority forbidden"))
    monkeypatch.setattr(d.delta, "_authenticate_capture", lambda *_a, **_k: pytest.fail("old authority forbidden"))
    monkeypatch.setattr(d.diagnostic.original.credentials, "load_key", lambda *_a, **_k: pytest.fail("credentials forbidden"))
    for target in (d.diagnostic, d.diagnostic.original):
        for name in ("run", "_run", "_claim", "_preflight"):
            monkeypatch.setattr(target, name, lambda *_a, **_k: pytest.fail("old operation forbidden"))


@pytest.fixture
def control(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    path = tmp_path / "D4-SYNTHETIC"
    monkeypatch.setattr(d, "CONTROL", path)
    monkeypatch.setattr(d, "_preflight", lambda *_a: None)
    monkeypatch.setattr(d.capture, "_require_operational_artifact_scope", lambda *_a: None)
    return path


def snapshot(tmp_path, monkeypatch, pages):
    path = tmp_path / "capture-synthetic"
    path.mkdir(mode=0o700)
    records, cursor = [], None
    for number, rows in enumerate(pages, 1):
        body = {"status": "OK", "results": rows}
        if number != len(pages):
            body["next_url"] = f"https://api.massive.com/benzinga/v1/ratings?cursor=page{number+1}"
        raw = json.dumps(body).encode()
        extracted, _ = d.capture._response_rows_and_next_url(raw, page_limit=1000)
        record = d.delta.build_page_record(page_number=number, raw_response=raw, provider_rows=extracted,
            response_received_at="2026-10-13T01:00:01.000000Z", request_cursor_sha256=cursor)
        cursor = record["next_cursor_sha256"]
        records.append(record)
        for name, payload in zip(d.delta.page_names(number), (raw, extracted), strict=True):
            (path / name).write_bytes(payload)
            (path / name).chmod(0o600)
    manifest = d.delta.canonical_bytes(d.delta.build_manifest(pages=records,
        capture_started_at="2026-10-13T01:00:00.000000Z", capture_completed_at="2026-10-13T01:00:02.000000Z"))
    digest = hashlib.sha256(manifest).hexdigest()
    for name, payload in (("manifest.json", manifest), ("manifest.sha256", (digest+"\n").encode())):
        (path / name).write_bytes(payload)
        (path / name).chmod(0o600)
    monkeypatch.setattr(d, "CAPTURE_PATH", path)
    monkeypatch.setattr(d, "MANIFEST_SHA256", digest)
    monkeypatch.setattr(d, "MANIFEST_BYTES", len(manifest))
    return path


def row(identifier, value=1):
    return {"benzinga_id": identifier, "private_value": value}


def test_all_location_and_conflict_classes_and_no_identifiers(control, tmp_path, monkeypatch, capsys):
    snapshot(tmp_path, monkeypatch, [
        [row("PRIVATE-A"), row("PRIVATE-A"), row("PRIVATE-B"), row("PRIVATE-C"), {}],
        [row("PRIVATE-B"), row("PRIVATE-C", 2), row("PRIVATE-C", 2), row("PRIVATE-D")]])
    assert d.run(HEAD, SHA) == 0
    text = capsys.readouterr().out
    assert "PRIVATE-" not in text and "private_value" not in text
    envelope = json.loads(text)
    report = envelope["report"]
    assert report["counters"] == dict(total_rows=9, valid_id_rows=8, invalid_id_rows=1,
        unique_ids=4, repeated_groups=3, repeated_occurrences_including_first=7,
        excess_repeated_occurrences=4, byte_identical_groups=2, conflicting_groups=1,
        within_page_only_groups=1, across_pages_only_groups=1, within_and_across_page_groups=1)
    for field in ("original_capture_accepted", "authority_minted", "quarantine_or_collapse",
            "point_in_time_proven", "backtest_ready", "paper_or_live_ready", "provider_contact_authorized"):
        assert report[field] is False
    assert report["diagnostic_only"] is True and report["provider_request_count"] is None
    payload = (control / "report.json").read_bytes()
    assert envelope["report_bytes"] == len(payload)
    assert envelope["report_sha256"] == hashlib.sha256(payload).hexdigest()
    assert "assistant.dispatch_fence" not in sys.modules


@pytest.mark.parametrize("pages,expected", [
    ([[]], (0, 0, 0, 0, 0, 0)),
    ([[{}, row(None), row(1)]], (3, 0, 3, 0, 0, 0)),
    ([[row("a"), row("b")]], (2, 2, 0, 2, 0, 0)),
    ([[row("a"), row("a", 2)]], (2, 2, 0, 1, 1, 1)),
    ([[row("a")], [row("a", 2)]], (2, 2, 0, 1, 1, 1)),
    ([[row("a")], [row("a")]], (2, 2, 0, 1, 1, 0)),
    ([[row("a"), row("a")], [row("a")]], (3, 3, 0, 1, 1, 0)),
])
def test_empty_invalid_unique_identical_and_conflicting_cases(tmp_path, monkeypatch, pages, expected):
    snapshot(tmp_path, monkeypatch, pages)
    result = d._characterize(time.monotonic()+30)
    assert tuple(result[name] for name in ("total_rows", "valid_id_rows", "invalid_id_rows", "unique_ids",
        "repeated_groups", "conflicting_groups")) == expected
    assert result["byte_identical_groups"] + result["conflicting_groups"] == result["repeated_groups"]
    assert sum(result[name] for name in ("within_page_only_groups", "across_pages_only_groups",
        "within_and_across_page_groups")) == result["repeated_groups"]


def test_each_leaf_read_once_and_all_rows_counted(tmp_path, monkeypatch):
    snapshot(tmp_path, monkeypatch, [[row(str(n)) for n in range(1000)], [row(str(n)) for n in range(1000, 2000)]])
    original, names = d.delta._read_held, []
    def read(directory, name, *args, **kwargs):
        names.append(name)
        return original(directory, name, *args, **kwargs)
    monkeypatch.setattr(d.delta, "_read_held", read)
    result = d._characterize(time.monotonic()+30)
    assert len(names) == len(set(names)) == 6
    assert result["total_rows"] == result["valid_id_rows"] == result["unique_ids"] == 2000


@pytest.mark.parametrize("mutation", ["manifest_pin", "marker", "extra", "raw_hash", "rows_hash", "size", "mode", "symlink", "hardlink"])
def test_source_authentication_failures_return_no_counters(control, tmp_path, monkeypatch, capsys, mutation):
    path = snapshot(tmp_path, monkeypatch, [[row("private-A"), row("private-A")]])
    raw = path / "page0001.raw.json"
    if mutation == "manifest_pin":
        monkeypatch.setattr(d, "MANIFEST_SHA256", "c"*64)
    elif mutation == "marker":
        (path / "manifest.sha256").write_bytes(b"c"*64+b"\n")
    elif mutation == "extra":
        (path / "extra").write_bytes(b"x")
    elif mutation == "raw_hash":
        raw.write_bytes(raw.read_bytes().replace(b"private-A", b"private-B"))
    elif mutation == "rows_hash":
        leaf = path / "page0001.rows.jsonl"
        leaf.write_bytes(leaf.read_bytes().replace(b"private-A", b"private-B"))
    elif mutation == "size":
        raw.write_bytes(raw.read_bytes()+b" ")
    elif mutation == "mode":
        raw.chmod(0o644)
    elif mutation == "symlink":
        target = tmp_path / "synthetic-original"
        raw.rename(target)
        raw.symlink_to(target)
    else:
        os.link(raw, tmp_path / "synthetic-hardlink")
    assert d.run(HEAD, SHA) == 2
    report = json.loads(capsys.readouterr().out)["report"]
    assert report["counters"] is None and report["original_capture_accepted"] is False


def test_external_page_hash_checked_before_any_provider_parser(tmp_path, monkeypatch):
    path = snapshot(tmp_path, monkeypatch, [[row("private-A")]])
    raw = path / "page0001.raw.json"
    raw.write_bytes(raw.read_bytes().replace(b"private-A", b"private-B"))
    monkeypatch.setattr(d.delta, "build_page_record", lambda **_k: pytest.fail("parse before pin"))
    with pytest.raises(d.DuplicateDiagnosticError, match="page_external_pin"):
        d._characterize(time.monotonic()+30)


@pytest.mark.parametrize("mutation,reason", [("leaf", "leaf_final_changed"),
    ("inventory", "directory_final_changed"), ("ancestor", "ancestor_changed")])
def test_metadata_change_after_counts_never_emits_partial_counts(control, tmp_path, monkeypatch, capsys, mutation, reason):
    path = snapshot(tmp_path, monkeypatch, [[row("private-A"), row("private-A")]])
    original = d.delta._input._candidate_provider_event_id
    count = []
    def observe(value):
        count.append(True)
        if len(count) == 2:
            if mutation == "leaf":
                (path / "page0001.raw.json").chmod(0o644)
            elif mutation == "inventory":
                (path / "unexpected").write_bytes(b"synthetic")
            else:
                tmp_path.chmod(0o750)
        return original(value)
    monkeypatch.setattr(d.delta._input, "_candidate_provider_event_id", observe)
    assert d.run(HEAD, SHA) == 2
    report = json.loads(capsys.readouterr().out)["report"]
    assert report["counters"] is None and report["refusal_code"] == reason


def test_claim_collision_and_repeat_do_not_open_source(control, tmp_path, monkeypatch, capsys):
    snapshot(tmp_path, monkeypatch, [[row("private-A")]])
    assert d.run(HEAD, SHA) == 0
    capsys.readouterr()
    monkeypatch.setattr(d, "_characterize", lambda *_a: pytest.fail("repeat source read"))
    assert d.run(HEAD, SHA) == 2
    assert json.loads(capsys.readouterr().out)["attempt_consumed"] is None


def test_preflight_refusal_never_claims_or_reads(control, monkeypatch, capsys):
    def refuse(*_):
        raise d.DuplicateDiagnosticError("diagnostic_refused")
    monkeypatch.setattr(d, "_preflight", refuse)
    monkeypatch.setattr(d, "_characterize", lambda *_a: pytest.fail("source read"))
    assert d.run(HEAD, SHA) == 2
    assert not control.exists()
    assert json.loads(capsys.readouterr().out)["attempt_consumed"] is False


@pytest.mark.parametrize("mutation", ["none", "root", "branch", "head", "dirty", "stderr", "returncode", "pin", "caller"])
def test_preflight_bindings(monkeypatch, mutation):
    monkeypatch.setattr(d, "SOURCE_PINS", {"synthetic.py": SHA})
    outputs = [str(d.ROOT), d.BRANCH, HEAD, ""]
    changes = {"root": 0, "branch": 1, "head": 2, "dirty": 3}
    if mutation in changes:
        outputs[changes[mutation]] = "wrong"
    def command(*_a, **_k):
        return SimpleNamespace(stdout=(outputs.pop(0)+"\n").encode(),
            stderr=b"wrong" if mutation == "stderr" else b"", returncode=1 if mutation == "returncode" else 0)
    monkeypatch.setattr(d.subprocess, "run", command)
    monkeypatch.setattr(d.helpers, "_source_digest", lambda path: "c"*64 if mutation == "pin" and path != d.SOURCE
        or mutation == "caller" and path == d.SOURCE else SHA)
    if mutation == "none":
        d._preflight(HEAD, SHA, time.monotonic()+10)
    else:
        with pytest.raises(ValueError):
            d._preflight(HEAD, SHA, time.monotonic()+10)


def test_unknown_errors_never_render_private_arguments():
    class Opaque:
        def __str__(self):
            raise AssertionError("private rendering")
        def __repr__(self):
            raise AssertionError("private rendering")
    assert d._failure(d.DuplicateDiagnosticError(Opaque())) == ("duplicate_diagnostic_error", "unknown")
    assert d._failure(ValueError(Opaque())) == ("value_error", "unknown")


def test_parent_alarm_bounds_source_characterization(control, monkeypatch, capsys):
    monkeypatch.setattr(d, "DEADLINE_SECONDS", 0.03)
    monkeypatch.setattr(d, "_characterize", lambda *_a: time.sleep(1))
    started = time.monotonic()
    assert d.run(HEAD, SHA) == 2
    assert time.monotonic()-started < 0.5
    assert "original_capture_accepted\":false" in capsys.readouterr().out


def test_late_publication_failure_does_not_return_normal_counter_envelope(control, tmp_path, monkeypatch, capsys):
    snapshot(tmp_path, monkeypatch, [[row("private-A"), row("private-A")]])
    write, clock = d.diagnostic.original.transport._write_held, time.monotonic
    late = []
    def publish(directory, name, value):
        result = write(directory, name, value)
        if name == "report.json":
            late.append(True)
        return result
    monkeypatch.setattr(d.diagnostic.original.transport, "_write_held", publish)
    monkeypatch.setattr(time, "monotonic", lambda: 10**20 if late else clock())
    assert d.run(HEAD, SHA) == 2
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["terminal"] == "diagnostic_publication_ambiguous" and "report" not in envelope
    assert json.loads((control / "report.json").read_bytes())["counters"]["repeated_groups"] == 1
