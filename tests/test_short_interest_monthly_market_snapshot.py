"""Fabricated protected files only; no provider, credentials, or market rows."""
from datetime import datetime, timedelta, timezone
import json
import os
import socket

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import short_interest_monthly_market_snapshot as monthly


def stamp(second):
    return (datetime(2026, 10, 14, 0, 42, 32, tzinfo=timezone.utc)
        + timedelta(seconds=second)).isoformat().replace("+00:00", "Z")


def write(path, raw):
    path.write_bytes(raw)
    path.chmod(0o600)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("monthly snapshot fixtures forbid network")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def fixture(monkeypatch, tmp_path):
    monkeypatch.setattr(monthly.inputs, "MONTHS", (monthly.inputs.MONTHS[0],))
    monkeypatch.setattr(monthly, "ATTEMPTS", 2)
    monkeypatch.setattr(monthly, "MEMBERS", 12)
    monkeypatch.setattr(monthly.lane, "ROOT", tmp_path)
    protocol = monthly.inputs.market_input_protocol()
    monkeypatch.setattr(monthly, "PROTOCOL_SHA256", hash_payload(protocol))
    fake_code = b"fabricated historical code, no source bytes"
    code_sha = hash_payload({"git_commit": monthly.SOURCE_HEAD, "files": [
        {"path": path, "sha256": hash_bytes(fake_code)} for path in monthly.CODE_FILES]})
    monkeypatch.setattr(monthly, "CODE_IDENTITY_SHA256", code_sha)
    def git(root, arguments, guard):
        assert root == tmp_path and arguments[0] in {"merge-base", "show"}
        return b"" if arguments[0] == "merge-base" else fake_code
    monkeypatch.setattr(monthly, "_git", git)
    head = "2d11d1f5b73a04e0701c65bdeb81152766535f89"
    def runner(root, arguments):
        if arguments[1] == "rev-parse":
            return (str(tmp_path) + "\n").encode()
        assert arguments[1] == "status"
        return (f"# branch.oid {head}\n# branch.head codex/strategy-short-interest\n").encode()
    guard = monthly.lane.LaneGuard(tmp_path, expected_head=head, expected_remote="b" * 40,
        runner=runner, physical=lambda root: None)
    budget = {"schema": "si-native-market-input-budget-v1", "claim_sha256": monthly.CLAIM_ID,
        "code_head": monthly.SOURCE_HEAD, "remote_head": monthly.SOURCE_REMOTE,
        "run_id": monthly.DIRECTORY.name, "protocol_sha256": monthly.PROTOCOL_SHA256,
        "maximum_requests": protocol["maximum_requests"], "started_at": stamp(0), "restart_or_resume": False}
    start = {"schema": "si-native-market-input-start-v1", "code_head": monthly.SOURCE_HEAD,
        "remote_head": monthly.SOURCE_REMOTE, "protocol_sha256": monthly.PROTOCOL_SHA256,
        "code_identity_sha256": code_sha, "started_at": stamp(0),
        "maximum_requests": protocol["maximum_requests"], "outcome_looks": 0, "qc_attempts": 0}
    files = {"protocol.json": canonical_json(protocol).encode(), "started.json": canonical_json(start).encode()}
    panels = []
    total_bytes = 0
    for ordinal, panel in enumerate(protocol["panels"], 1):
        request = panel["initial_request"]
        raw = b'{"count":0,"data":[]}'
        prefix = f"attempt-{ordinal:05d}"
        files[prefix + ".started.json"] = canonical_json({"schema": "si-native-market-request-start-v1",
            "attempt": ordinal, "table": panel["table"], "month": panel["month"], "page": 0,
            "request": request, "request_sha256": hash_payload(request), "code_head": monthly.SOURCE_HEAD,
            "protocol_sha256": monthly.PROTOCOL_SHA256, "started_at": stamp(ordinal)}).encode()
        receipt = {"schema": "si-native-market-response-v1", "attempt": ordinal,
            "request_sha256": hash_payload(request), "http_status": 200, "content_type": "application/json",
            "raw_path": prefix + ".raw", "raw_sha256": hash_bytes(raw), "raw_bytes": len(raw),
            "received_at": stamp(ordinal)}
        files[prefix + ".received.json"] = canonical_json(receipt).encode()
        files[prefix + ".raw"] = raw
        files[prefix + ".refusals.private.json"] = canonical_json({"schema": "si-native-market-page-refusals-v1",
            "attempt": ordinal, "request_sha256": hash_payload(request), "raw_sha256": hash_bytes(raw),
            "refusals": [], "financial_values_normalized": False, "signal_or_return_computed": False}).encode()
        panels.append({"table": panel["table"], "month": panel["month"],
            "pages": [{"attempt": ordinal, "request": request, "receipt": receipt, "row_count": 0}],
            "malformed_refusals": [], "duplicate_groups": []})
        total_bytes += len(raw)
    inventory = {"schema": "si-native-market-input-inventory-v1", "code_head": monthly.SOURCE_HEAD,
        "protocol_sha256": monthly.PROTOCOL_SHA256, "retrieved_at": stamp(4), "panels": panels,
        "total_raw_bytes": total_bytes, "total_raw_rows": 0, "http_attempts": 2,
        "source_only": True, "data_or_fitness_admitted": False, "financial_values_normalized": False,
        "signal_or_return_computed": False, "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False}
    inventory["report_sha256"] = hash_payload(inventory)
    files["inventory.private.json"] = canonical_json(inventory).encode()
    files["completed.json"] = canonical_json({"schema": "si-native-market-input-complete-v1",
        "status": "private_market_source_capture_complete", "code_head": monthly.SOURCE_HEAD,
        "protocol_sha256": monthly.PROTOCOL_SHA256, "http_attempts": 2,
        "private_report_sha256": inventory["report_sha256"], "completed_at": stamp(5),
        "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False}).encode()
    budget_raw = canonical_json(budget).encode()
    monkeypatch.setattr(monthly, "CLAIM_SHA256", hash_bytes(budget_raw))
    monkeypatch.setattr(monthly, "CONTROL_PINS", {name: hash_bytes(files[name]) for name in monthly.CONTROL_PINS})
    directory = tmp_path / monthly.DIRECTORY
    directory.mkdir(parents=True, mode=0o700)
    directory.parent.chmod(0o700)
    for name, raw in files.items():
        write(directory / name, raw)
    write(directory.parent / ("budget-" + monthly.CLAIM_ID + ".json"), budget_raw)
    manifest = canonical_json([{"name": name, "bytes": len(files[name]), "sha256": hash_bytes(files[name])}
        for name in sorted(files)]).encode()
    monkeypatch.setattr(monthly, "MANIFEST_SHA256", hash_bytes(manifest))
    return guard, directory, files, manifest


def test_fixed_snapshot_closes_all_bytes_without_input_admission(monkeypatch, tmp_path):
    guard, directory, files, manifest = fixture(monkeypatch, tmp_path)
    before = {path: path.read_bytes() for path in (*directory.iterdir(),
        directory.parent / ("budget-" + monthly.CLAIM_ID + ".json"))}
    with monthly.load_registered_snapshot(tmp_path, guard) as held:
        assert held.manifest_raw == manifest
        assert held.names() == tuple(sorted(files))
        assert set(held.controls) == set(monthly.CONTROL_PINS)
        assert json.loads(held.controls["inventory.private.json"])["data_or_fitness_admitted"] is False
        assert held.read("attempt-00001.raw", monthly.MAXIMUM_BYTES) == files["attempt-00001.raw"]
        assert hash_bytes(held.claim_raw) == monthly.CLAIM_SHA256
        with pytest.raises(TypeError):
            held.controls["invented.json"] = b"{}"
    with pytest.raises(monthly.MonthlySnapshotRefusal, match="monthly_snapshot_binding_changed"):
        held.check()
    assert {path: path.read_bytes() for path in before} == before


@pytest.mark.parametrize("raw", [b'{"x":0,"x":1}', b'{"x":NaN}', b'{"x":Infinity}', b'\xff'])
def test_strict_control_JSON_refuses_duplicate_nonfinite_or_invalid_bytes(raw):
    with pytest.raises(monthly.MonthlySnapshotRefusal):
        monthly.parsed(raw)


@pytest.mark.parametrize("mutation", ["raw", "claim", "control", "historical", "membership", "mode", "hardlink", "symlink"])
def test_original_bytes_protection_and_exact_membership_are_not_caller_flags(monkeypatch, tmp_path, mutation):
    guard, directory, files, unused = fixture(monkeypatch, tmp_path)
    path = directory / "attempt-00001.raw"
    if mutation == "raw":
        write(path, files[path.name] + b" ")
    elif mutation == "claim":
        write(directory.parent / ("budget-" + monthly.CLAIM_ID + ".json"), b"{}")
    elif mutation == "control":
        write(directory / "started.json", b"{}")
    elif mutation == "historical":
        monkeypatch.setattr(monthly, "_git", lambda root, args, guard: b"" if args[0] == "merge-base" else b"changed")
    elif mutation == "membership":
        write(directory / "refused.json", b"{}")
    elif mutation == "mode":
        path.chmod(0o644)
    elif mutation == "hardlink":
        os.link(path, tmp_path / "another-name")
    else:
        path.unlink(); path.symlink_to(directory / "attempt-00002.raw")
    with pytest.raises(monthly.MonthlySnapshotRefusal):
        with monthly.load_registered_snapshot(tmp_path, guard):
            pytest.fail("must not yield unbound original evidence")


@pytest.mark.parametrize("control", ["budget", "started.json", "inventory.private.json", "completed.json"])
def test_rehashed_controls_cannot_change_original_global_contract(monkeypatch, tmp_path, control):
    guard, directory, files, unused = fixture(monkeypatch, tmp_path)
    if control == "budget":
        path = directory.parent / ("budget-" + monthly.CLAIM_ID + ".json")
        value = json.loads(path.read_bytes()); value["restart_or_resume"] = True
        write(path, canonical_json(value).encode())
        monkeypatch.setattr(monthly, "CLAIM_SHA256", hash_bytes(path.read_bytes()))
    else:
        value = json.loads(files[control])
        if control == "started.json":
            value["code_identity_sha256"] = "0" * 64
        elif control == "inventory.private.json":
            value["data_or_fitness_admitted"] = True
            value["report_sha256"] = hash_payload({key: item for key, item in value.items() if key != "report_sha256"})
        else:
            value["completed_at"] = stamp(-1)
        files[control] = canonical_json(value).encode()
        write(directory / control, files[control])
        monkeypatch.setattr(monthly, "CONTROL_PINS", dict(monthly.CONTROL_PINS, **{control: hash_bytes(files[control])}))
    with pytest.raises(monthly.MonthlySnapshotRefusal):
        with monthly.load_registered_snapshot(tmp_path, guard):
            pytest.fail("must not yield changed original global controls")


@pytest.mark.parametrize("name", ["attempt-00001.raw", "attempt-00001.started.json"])
def test_inplace_change_to_earlier_read_during_later_read_prevents_yield(monkeypatch, tmp_path, name):
    guard, directory, files, unused = fixture(monkeypatch, tmp_path)
    original = monthly._MonthlySnapshot.read
    mutated = [False]
    def read_then_change(self, member, maximum):
        raw = original(self, member, maximum)
        if member == "attempt-00002.raw" and not mutated[0]:
            mutated[0] = True
            (directory / name).write_bytes(files[name] + b" ")
        return raw
    monkeypatch.setattr(monthly._MonthlySnapshot, "read", read_then_change)
    with pytest.raises(monthly.MonthlySnapshotRefusal, match="monthly_earlier_file_changed"):
        with monthly.load_registered_snapshot(tmp_path, guard):
            pytest.fail("earlier in-place changes must be caught before outward yield")


def test_context_exit_and_explicit_full_check_detect_late_inplace_change(monkeypatch, tmp_path):
    guard, directory, files, unused = fixture(monkeypatch, tmp_path)
    with pytest.raises(monthly.MonthlySnapshotRefusal, match="monthly_earlier_file_changed"):
        with monthly.load_registered_snapshot(tmp_path, guard) as held:
            assert held.read("attempt-00001.raw", monthly.MAXIMUM_BYTES)
            (directory / "attempt-00001.raw").write_bytes(files["attempt-00001.raw"] + b" ")


def test_parent_siblings_allowed_but_snapshot_bindings_cannot_be_replaced(monkeypatch, tmp_path):
    guard, directory, files, unused = fixture(monkeypatch, tmp_path)
    with pytest.raises(monthly.MonthlySnapshotRefusal, match="monthly_snapshot_seal_changed"):
        with monthly.load_registered_snapshot(tmp_path, guard) as held:
            (directory.parent / "new-private-sibling").mkdir(mode=0o700)
            write(directory.parent / "separate-new-control.json", b"{}")
            held.full_check()
            held._controls = None
            held.check()


def test_three_retained_descriptors_and_one_transient_regardless_of_members(monkeypatch, tmp_path):
    guard, directory, files, unused = fixture(monkeypatch, tmp_path)
    original_open, original_close = os.open, os.close
    opened, peak = set(), [0]
    def opening(*args, **kwargs):
        fd = original_open(*args, **kwargs)
        opened.add(fd); peak[0] = max(peak[0], len(opened))
        return fd
    def closing(fd):
        original_close(fd); opened.discard(fd)
    monkeypatch.setattr(os, "open", opening)
    monkeypatch.setattr(os, "close", closing)
    with monthly.load_registered_snapshot(tmp_path, guard):
        assert len(opened) == 3
    assert not opened and peak[0] == 4
