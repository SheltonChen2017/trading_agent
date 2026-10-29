"""Independent invented-only retained-prefix orchestration boundaries."""
from __future__ import annotations

import copy

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX custody support; Windows custody port deferred")
import fcntl
import json
import os
from pathlib import Path
import zlib


from research import insider_buying_sec_feed_prefix_shape_runner_v1 as m


CONTACT = "invented@unit.test"


def _old_capture(root):
    root.mkdir(mode=0o700)
    encoder = zlib.compressobj(level=0, wbits=31)
    raw = (encoder.compress(b"public invented observation "*5000)+encoder.flush())[:65536]
    assert len(raw) == 65536
    headers = (("Content-Length", "65536"), ("Content-Range", "bytes 0-65535/1000000"),
        ("Content-Encoding", "identity"), ("Content-Type", "application/gzip"))

    def transport(url, request_headers, cap):
        assert url == m.capture.URL and request_headers["Range"] == m.capture.RANGE and cap == 65536
        return m.capture.PrefixHttpResult(206, headers, raw, None, 1000000, True)

    result = m.capture._invented(root=root, transport=transport)
    assert result["result"]["prefix_retained"] is True
    return result


def _old_run(root):
    return root.joinpath(*m.capture.ARTIFACT_PARTS, "runs", m.capture.AUDIT_ID)


def _new_run(root):
    return root.joinpath(*m.ARTIFACT_PARTS, "runs", m.AUDIT_ID)


def _pins(root, result):
    values = {name: m._sha((_old_run(root)/name).read_bytes()) for name in m.ORIGINAL_PINS
        if name not in {"claim", "prefix.bin"}}
    values["complete.json"] = result["complete_sha256"]
    values["claim"] = m._sha(root.joinpath(*m.capture.ARTIFACT_PARTS, "claims", m.capture._claim_name()).read_bytes())
    values["prefix.bin"] = result["result"]["prefix_sha256"]
    return values


def _run(root, original_root, original_result, **kwargs):
    root.mkdir(mode=0o700)
    return m._invented(root=root, original_root=original_root,
        original_complete_sha256=original_result["complete_sha256"], **kwargs)


def test_review_fixture_front_cannot_read_actual_control_paths_before_boundary_refusal(tmp_path, monkeypatch):
    new = tmp_path/"new"
    new.mkdir(mode=0o700)
    monkeypatch.setattr(Path, "read_bytes", lambda path: pytest.fail("fixture reached an unqualified old control read"))
    with pytest.raises(ValueError):
        m._invented(root=new, original_root=m.LANE_ROOT, original_complete_sha256="a"*64)


@pytest.mark.parametrize("change", ("authority", "shape", "extra", "original_contact", "identity", "count_alias", "source_pin"))
def test_review_dirty_worker_report_cannot_be_hashed_or_published(tmp_path, monkeypatch, change):
    old = tmp_path/"old"
    previous = _old_capture(old)
    analyse = m._analyse

    def dirty(*args, **kwargs):
        report = analyse(*args, **kwargs)
        if change == "authority":
            report["authority"]["backtesting_ready"] = True
        elif change == "shape":
            report["shape"]["backtesting_ready"] = True
        elif change == "extra":
            report["unregistered_assertion"] = True
        elif change == "original_contact":
            report["original_current_contact_equality_attested"] = True
        elif change == "identity":
            report["execution_identity"] = {"head": "b"*40}
        elif change == "count_alias":
            report["shape"]["files_read_written"] = False
        else:
            report["shape"]["prefix_core_source_sha256"] = "f"*64
        return report

    monkeypatch.setattr(m, "_analyse", dirty)
    new = tmp_path/"new"
    result = _run(new, old, previous)
    assert result["result"]["report_retained"] is False
    assert not (_new_run(new)/"report.json").exists()


def _identity(root):
    sources = {m.SELF_PATH: "a"*64, m.TEST_PATH: "b"*64}
    return {"root": str(root), "branch": m.LANE_BRANCH, "head": "a"*40, "clean": True,
        "source_sha256": sources, "source_inventory_sha256": m._sha(m._raw(sources))}


@pytest.mark.parametrize("change", ("frontier", "checksum"))
def test_review_report_rejects_inconsistent_physical_observation_crosslinks(tmp_path, change):
    old = tmp_path/"old"
    previous = _old_capture(old)
    held = m._HeldPrefix(old, fixture=True, pins=_pins(old, previous))
    try:
        identity = _identity(tmp_path/"new")
        report = m._analyse(identity, CONTACT, held, fixture=True)
        m._report_valid(copy.deepcopy(report), identity, held.metadata, True)
        physical = report["shape"]["physical_shape_observations"]
        if change == "frontier":
            assert physical["following_bytes_not_interpreted"] > 1
            physical["structural_frontier_bytes"] += 1
            physical["following_bytes_not_interpreted"] -= 1
        else:
            assert physical["headers"][0]["header_checksum_matches"] is False
            assert report["shape"]["prefix_format_descriptor"]["first_tar_header_observation"]["header_checksum_matches"] is False
            physical["headers"][0]["header_checksum_matches"] = True
        with pytest.raises(m.PrefixShapeRunnerError, match="analysis_refused"):
            m._report_valid(report, identity, held.metadata, True)
    finally:
        held.close()


def test_review_new_output_lock_ctime_only_change_obeys_qualified_publication_policy(tmp_path):
    old = tmp_path/"old"
    previous = _old_capture(old)
    new = tmp_path/"new"
    changes = []

    def guard():
        lock = new.joinpath(*m.ARTIFACT_PARTS, "scope.lock")
        if not changes and (_new_run(new)/"reservation.json").exists():
            before = lock.stat()
            lock.chmod(0o640)
            lock.chmod(0o600)
            after = lock.stat()
            assert before.st_ctime_ns != after.st_ctime_ns
            assert (before.st_dev, before.st_ino, before.st_mode, before.st_uid, before.st_nlink,
                before.st_size, before.st_mtime_ns) == (after.st_dev, after.st_ino, after.st_mode,
                after.st_uid, after.st_nlink, after.st_size, after.st_mtime_ns)
            changes.append(True)

    result = _run(new, old, previous, guard=guard)
    assert changes == [True]
    assert result["result"]["report_retained"] is True


def test_review_old_prefix_ctime_stays_strict_after_hold(tmp_path):
    old = tmp_path/"old"
    previous = _old_capture(old)
    held = m._HeldPrefix(old, fixture=True, pins=_pins(old, previous))
    try:
        path = _old_run(old)/"prefix.bin"
        before = path.stat()
        path.chmod(0o640)
        path.chmod(0o600)
        after = path.stat()
        assert before.st_ctime_ns != after.st_ctime_ns
        assert before.st_mtime_ns == after.st_mtime_ns and before.st_size == after.st_size
        with pytest.raises(ValueError):
            held.check()
    finally:
        held.close()


def test_review_metadata_preflight_never_reads_or_hashes_old_prefix(tmp_path, monkeypatch):
    old = tmp_path/"old"
    previous = _old_capture(old)
    pins = _pins(old, previous)
    inode = (_old_run(old)/"prefix.bin").stat().st_ino
    original = os.read

    def read(fd, cap):
        if os.fstat(fd).st_ino == inode:
            pytest.fail("metadata preflight read raw prefix")
        return original(fd, cap)

    monkeypatch.setattr(os, "read", read)
    held = m._HeldPrefix(old, fixture=True, pins=pins)
    try:
        assert held.metadata["raw_prefix_read_by_metadata_preflight"] is False
        held.check()
    finally:
        held.close()


def test_review_genuine_report_and_independent_readback_preserve_original_prefix(tmp_path):
    old = tmp_path/"old"
    previous = _old_capture(old)
    pins = _pins(old, previous)
    original_body_pin = pins["prefix.bin"]
    new = tmp_path/"new"
    result = _run(new, old, previous)
    assert result["result"]["report_retained"] is True
    observed = m._verify_files(new, result["complete_sha256"], CONTACT,
        fixture=True, original_root=old, original_pins=pins)
    assert observed["result"] == result["result"]
    assert observed["producer_execution_identity"]["head"] == "a"*40
    assert observed["original_input_plan"]["inputs"]["original_execution_identity"]["root"] == str(old)
    assert observed["original_contact_screen_replayed"] is False
    assert observed["original_current_contact_equality_attested"] is False
    assert m._sha((_old_run(old)/"prefix.bin").read_bytes()) == original_body_pin


def test_review_extra_old_header_control_refuses_before_current_contact_or_output(tmp_path):
    old = tmp_path/"old"
    previous = _old_capture(old)
    path = _old_run(old)/"response-headers.json"
    headers = json.loads(path.read_bytes())
    headers["unbound_extra"] = True
    path.write_bytes(m._raw(headers))
    new = tmp_path/"new"
    with pytest.raises(ValueError):
        _run(new, old, previous, contact=lambda: pytest.fail("contact preceded old control validation"))
    assert not new.joinpath(*m.ARTIFACT_PARTS).exists()


def test_review_old_prefix_exclusive_producer_lock_blocks_new_analysis(tmp_path):
    old = tmp_path/"old"
    previous = _old_capture(old)
    pins = _pins(old, previous)
    descriptor = os.open(old.joinpath(*m.capture.ARTIFACT_PARTS, "scope.lock"), os.O_RDONLY)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            m._HeldPrefix(old, fixture=True, pins=pins)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
    held = m._HeldPrefix(old, fixture=True, pins=pins)
    held.close()


def test_review_actual_readback_rechecks_exact_git_identity_before_public_return(monkeypatch):
    identity = _identity(m.LANE_ROOT)
    plan = m._plan(identity, {"schema": m.SCHEMA+"/original-input"})
    reply = {"producer_execution_identity": identity, "original_input_plan": copy.deepcopy(plan),
        "result": {"report_retained": False}}
    calls = []

    def source(head):
        calls.append(head)
        value = copy.deepcopy(identity)
        if len(calls) > 1:
            value["head"] = "b"*40
        return value

    monkeypatch.setattr(m, "_identity", source)
    monkeypatch.setattr(m, "_current", lambda value: None)
    monkeypatch.setattr(m, "_parent_proofs", lambda value: None)
    monkeypatch.setattr(m.previous, "_source_git", lambda value: None)
    monkeypatch.setattr(m.contact_io, "_stdin_contact", lambda: CONTACT)
    monkeypatch.setattr(m.privacy, "_contact", lambda value, observed: value)
    monkeypatch.setattr(m, "_child", lambda role, value, payload=b"": copy.deepcopy(plan if role == "preflight" else reply))
    with pytest.raises(m.PrefixShapeRunnerError, match="source_changed"):
        m.verify_actual(expected_head="a"*40, expected_report_sha256="c"*64)
    assert calls == ["a"*40, "a"*40]


def test_review_post_report_publication_guard_failure_is_terminal_not_false_nonretention(tmp_path):
    old = tmp_path/"old"
    previous = _old_capture(old)
    new = tmp_path/"new"
    tripped = []

    def guard():
        if not tripped and (_new_run(new)/"report.json").exists():
            tripped.append(True)
            raise RuntimeError("invented one-shot publication guard refusal")

    with pytest.raises(m.PrefixShapeRunnerError):
        _run(new, old, previous, guard=guard)
    assert tripped == [True]
    assert not (_new_run(new)/"complete.json").exists()
