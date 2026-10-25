"""Fabricated, network-denied custody/replay checks for the refused child."""
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import short_interest_refused_count_snapshot as snapshot

spec = importlib.util.spec_from_file_location("fabricated_refused_snapshot_parent",
        Path(__file__).with_name("test_short_interest_count_recovery.py"))
fabricated = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fabricated
spec.loader.exec_module(fabricated)


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("fabricated snapshot tests forbid network")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def _write(path, raw):
    path.write_bytes(raw)
    path.chmod(0o600)


def _fixture(monkeypatch, tmp_path):
    source, unused, unused_files, unused_claim, unused_code, parent, binding = fabricated.small_domain(monkeypatch)
    monkeypatch.setattr(snapshot, "SOURCE_STARTS", 2)
    monkeypatch.setattr(snapshot, "SOURCE_RAW_BODIES", 1)
    monkeypatch.setattr(snapshot, "SOURCE_MEMBER_COUNT", 9)
    code = b"fabricated committed historical code"
    code_sha = hash_payload({"git_commit": snapshot.SOURCE_HEAD, "files": [
        {"path": name, "sha256": hash_bytes(code)} for name in snapshot.old.expected_code_paths()]})
    monkeypatch.setattr(snapshot, "SOURCE_CODE_SHA256", code_sha)
    monkeypatch.setattr(snapshot.old.cache, "_git", lambda root, arguments, guard:
        b"" if arguments[0] == "merge-base" else code)
    monkeypatch.setattr(snapshot.lane, "ROOT", tmp_path)
    head, remote = "b648f60112af141efc2a12fbaef03b38846d219d", "b211db7f81103df9cc3d736a05a4cc82d8efe4b0"
    def runner(root, arguments):
        if arguments[1] == "rev-parse":
            return (str(tmp_path) + "\n").encode()
        assert arguments[1] == "status"
        return (f"# branch.oid {head}\n# branch.head codex/strategy-short-interest\n").encode()
    guard = snapshot.lane.LaneGuard(tmp_path, expected_head=head, expected_remote=remote,
        runner=runner, physical=lambda root: None)
    @contextmanager
    def verified_prefix(root, supplied_source, supplied_plan, supplied_guard):
        assert root == tmp_path and supplied_source is source
        assert supplied_plan.sha256 == binding.parent_plan.sha256 and supplied_guard is guard
        yield parent
    monkeypatch.setattr(snapshot, "_load_parent_prefix", verified_prefix)
    old = snapshot.old
    began, ended = fabricated.stamp(200), fabricated.stamp(220)
    files = {"protocol.private.json": canonical_json(old.protocol()).encode(),
        "started.json": canonical_json({"schema": "si-manual-count-recovery-start-v1",
            "started_at": began, "parent_inventory_sha256": parent.inventory.sha256,
            "child_plan_sha256": binding.child_plan.sha256, "code_head": snapshot.SOURCE_HEAD,
            "code_identity_sha256": code_sha, "protocol_sha256": old.PROTOCOL_SHA256,
            "authority": old.authority()}).encode()}
    raw = b'{"status":"OK"}'
    for ordinal, query in enumerate(binding.child_plan._queries.iter_queries(), 1):
        ticket, prefix = query.to_payload(), f"query-{ordinal:08d}"
        at, received = fabricated.stamp(201 + ordinal * 2), fabricated.stamp(202 + ordinal * 2)
        files[prefix + ".started.json"] = canonical_json({
            "schema": "si-manual-count-recovery-request-start-v1", "query_ordinal": ordinal,
            "original_count_position": old.NEW_POSITIONS[ordinal - 1], "request": ticket["request"],
            "request_sha256": ticket["request_sha256"], "started_at": at,
            "child_plan_sha256": binding.child_plan.sha256, "code_head": snapshot.SOURCE_HEAD,
            "whole_page_bytes_reserved": old.parallel.MAXIMUM_RESPONSE_BYTES}).encode()
        success = ordinal == 1
        files[prefix + ".received.json"] = canonical_json({"query_ordinal": ordinal,
            "request_sha256": ticket["request_sha256"], "started_at": at, "received_at": received,
            "http_attempted": True, "http_status": 200 if success else None,
            "body_observed": success, "raw_path": prefix + ".raw" if success else None,
            "raw_sha256": hash_bytes(raw) if success else None, "raw_bytes": len(raw) if success else None,
            "content_type": "application/json" if success else None,
            "code": "received" if success else "material_request_refused"}).encode()
        if success:
            files[prefix + ".raw"] = raw
        else:
            files[prefix + ".diagnostic.private.json"] = canonical_json({"query_ordinal": ordinal,
                "failure_stage": "transport", "http_attempted": True, "http_status": None,
                "observed_receipt_at": received, "protocol_sha256": old.PROTOCOL_SHA256}).encode()
    charged = len(raw) + old.parallel.MAXIMUM_RESPONSE_BYTES
    monkeypatch.setattr(snapshot, "SOURCE_CHARGED_BYTES", charged)
    files["run.refused.json"] = canonical_json({"schema": "si-manual-count-recovery-refused-v1",
        "code": "child_started_prefix_drained_or_unreceipted_no_restart", "refused_at": ended,
        "child_starts": 2, "cumulative_starts": old.PARENT_STARTED + 2,
        "child_charged_response_bytes": charged, "cumulative_charged_response_bytes": old.PARENT_CHARGED_BYTES + charged,
        "child_known_http_invocations": 2, "cumulative_known_http_invocations": old.PARENT_HTTP + 2,
        "http_invocation_count_exact": True, "first_failed_child_ordinal": 2,
        "unreceipted_diagnostics": [], "complete_child_capture": False,
        "protocol_sha256": old.PROTOCOL_SHA256, "authority": old.authority()}).encode()
    claim = canonical_json({"schema": "si-manual-count-recovery-spent-claim-v1",
        "protocol_sha256": old.PROTOCOL_SHA256, "parent_manifest_sha256": old.PARENT_MANIFEST_SHA256,
        "parent_claim_sha256": old.PARENT_CLAIM_SHA256, "parent_inventory_sha256": parent.inventory.sha256,
        "parent_charged_response_bytes": old.PARENT_CHARGED_BYTES, "child_plan_sha256": binding.child_plan.sha256,
        "new_position_mapping_sha256": old.MAPPING_SHA256, "maximum_new_starts": old.MAXIMUM_NEW_STARTS,
        "maximum_cumulative_starts": old.MAXIMUM_CUMULATIVE_STARTS, "maximum_child_response_bytes": old.MAXIMUM_CHILD_BYTES,
        "maximum_cumulative_response_bytes": old.MAXIMUM_CUMULATIVE_BYTES, "code_head": snapshot.SOURCE_HEAD,
        "remote_head": remote, "code_identity_sha256": code_sha, "started_at": began,
        "automatic_retries": 0, "restart_allowed": False}).encode()
    for constant, raw_value in (("SOURCE_CLAIM_SHA256", claim), ("SOURCE_REFUSAL_SHA256", files["run.refused.json"]),
        ("SOURCE_FAILURE_RECEIPT_SHA256", files["query-00000002.received.json"]),
        ("SOURCE_DIAGNOSTIC_SHA256", files["query-00000002.diagnostic.private.json"])):
        monkeypatch.setattr(snapshot, constant, hash_bytes(raw_value))
    directory = tmp_path / old.OUTPUT
    directory.mkdir(parents=True, mode=0o700)
    directory.parent.chmod(0o700)
    for name, value in files.items():
        _write(directory / name, value)
    _write(directory.parent / old.CLAIM_NAME, claim)
    manifest = canonical_json([{ "name": name, "bytes": len(files[name]), "sha256": hash_bytes(files[name])}
        for name in sorted(files)]).encode()
    return source, guard, directory, files, manifest


def test_fabricated_refused_snapshot_replays_real_clocks_and_spent_debits(monkeypatch, tmp_path):
    source, guard, directory, files, manifest = _fixture(monkeypatch, tmp_path)
    before = {path: path.read_bytes() for path in (*directory.iterdir(), directory.parent / snapshot.old.CLAIM_NAME)}
    assert snapshot.measure_manifest(tmp_path, guard) == manifest
    with snapshot.load_refused_child(tmp_path, source, guard, hash_bytes(manifest)) as held:
        inventory = held.inventory
        assert type(inventory) is snapshot.old.parallel.ParallelCountInventory
        assert inventory.to_payload()["halted"] is True
        assert inventory.to_payload()["complete_frozen_request_sequence"] is False
        assert inventory.to_payload()["charged_response_bytes"] == snapshot.SOURCE_CHARGED_BYTES
        assert inventory.receipt_for_ordinal(2)["received_at"] == json.loads(files["query-00000002.received.json"])["received_at"]
        assert held.manifest_raw == manifest and held.names() == tuple(sorted(files))
        assert held.read("query-00000001.raw", 64) == files["query-00000001.raw"]
    with pytest.raises(snapshot.RefusedSnapshotError, match="snapshot_closed"):
        held.check()
    assert {path: path.read_bytes() for path in before} == before


def test_pending_manifest_pin_refuses_before_any_snapshot(monkeypatch, tmp_path):
    monkeypatch.setattr(snapshot, "_Snapshot", lambda *args: pytest.fail("pending pin must precede filesystem reads"))
    with pytest.raises(snapshot.RefusedSnapshotError, match="prospectively_bound_manifest_digest_required"):
        with snapshot.load_refused_child(tmp_path, None, None, "PENDING"):
            pytest.fail("must not yield")


@pytest.mark.parametrize("mutation", ["raw", "mapping", "receipt_clock", "code", "claim", "negative", "extra"])
def test_refused_snapshot_rejects_rehashed_or_replaced_evidence(monkeypatch, tmp_path, mutation):
    source, guard, directory, files, manifest = _fixture(monkeypatch, tmp_path)
    if mutation == "raw":
        files["query-00000001.raw"] += b" "
    elif mutation == "mapping":
        key = "query-00000001.started.json"
        value = json.loads(files[key]); value["original_count_position"] = 48
        files[key] = canonical_json(value).encode()
    elif mutation == "receipt_clock":
        key = "query-00000001.received.json"
        value = json.loads(files[key]); value["received_at"] = fabricated.stamp(0)
        files[key] = canonical_json(value).encode()
    elif mutation == "code":
        monkeypatch.setattr(snapshot.old.cache, "_git", lambda root, args, guard: b"" if args[0] == "merge-base" else b"changed")
    elif mutation == "claim":
        _write(directory.parent / snapshot.old.CLAIM_NAME, b"{}")
    elif mutation == "negative":
        files["run.refused.json"] += b" "
    else:
        _write(directory / "round.closed.qualified.json", b"{}")
    for name, raw in files.items():
        _write(directory / name, raw)
    # Rebinding a manifest does not bypass semantic, original-claim, or code checks.
    manifest = canonical_json([{ "name": name, "bytes": len(files[name]), "sha256": hash_bytes(files[name])}
        for name in sorted(files)]).encode()
    with pytest.raises((snapshot.RefusedSnapshotError, snapshot.old.parallel.ParallelCountRefusal)):
        with snapshot.load_refused_child(tmp_path, source, guard, hash_bytes(manifest)):
            pytest.fail("must not yield")


@pytest.mark.parametrize("mutation", ["replace", "permissions", "link", "truncate"])
def test_live_snapshot_custody_rejects_member_changes(monkeypatch, tmp_path, mutation):
    source, guard, directory, files, manifest = _fixture(monkeypatch, tmp_path)
    with pytest.raises(snapshot.RefusedSnapshotError):
        with snapshot.load_refused_child(tmp_path, source, guard, hash_bytes(manifest)) as held:
            path = directory / "query-00000001.raw"
            if mutation == "replace":
                path.unlink(); _write(path, files[path.name])
                held.check()
            elif mutation == "permissions":
                path.chmod(0o644); held.read(path.name, 64)
            elif mutation == "link":
                other = tmp_path / "second-name"
                os.link(path, other); held.read(path.name, 64)
            else:
                path.write_bytes(b""); held.read(path.name, 64)


def test_wrong_frozen_manifest_digest_refuses_before_code_replay(monkeypatch, tmp_path):
    source, guard, directory, files, manifest = _fixture(monkeypatch, tmp_path)
    monkeypatch.setattr(snapshot, "_historical_identity", lambda *args: pytest.fail("digest mismatch must precede code replay"))
    with pytest.raises(snapshot.RefusedSnapshotError, match="prospectively_bound_manifest_changed"):
        with snapshot.load_refused_child(tmp_path, source, guard, "0" * 64):
            pytest.fail("must not yield")


def test_new_sibling_chunk_and_claim_do_not_mutate_old_snapshot(monkeypatch, tmp_path):
    source, guard, directory, files, manifest = _fixture(monkeypatch, tmp_path)
    with snapshot.load_refused_child(tmp_path, source, guard, hash_bytes(manifest)) as held:
        (directory.parent / "new-successor-chunk").mkdir(mode=0o700)
        _write(directory.parent / "new-successor-claim.json", b"{}")
        held.check()
        assert held.names() == tuple(sorted(files))
        assert held.inventory.to_payload()["halted"] is True


@pytest.mark.parametrize("field", ["_pins", "_manifest_raw", "_inventory", "_prefix"])
def test_reflective_snapshot_binding_changes_refuse(monkeypatch, tmp_path, field):
    source, guard, directory, files, manifest = _fixture(monkeypatch, tmp_path)
    with pytest.raises(snapshot.RefusedSnapshotError, match="snapshot_custody_binding_changed"):
        with snapshot.load_refused_child(tmp_path, source, guard, hash_bytes(manifest)) as held:
            setattr(held, field, None)
            held.check()


def test_snapshot_holds_constant_file_descriptor_count(monkeypatch, tmp_path):
    source, guard, directory, files, manifest = _fixture(monkeypatch, tmp_path)
    opened, peak = set(), [0]
    original_open, original_close = os.open, os.close
    def track_open(*args, **kwargs):
        fd = original_open(*args, **kwargs)
        opened.add(fd); peak[0] = max(peak[0], len(opened))
        return fd
    def track_close(fd):
        original_close(fd)
        opened.discard(fd)
    monkeypatch.setattr(os, "open", track_open)
    monkeypatch.setattr(os, "close", track_close)
    with snapshot.load_refused_child(tmp_path, source, guard, hash_bytes(manifest)) as held:
        assert len(opened) == 3
        held.read("query-00000001.raw", 64)
    assert not opened and peak[0] == 4


def test_actual_parent_wrapper_reuses_full_fabricated_proof_without_remote_refresh(monkeypatch, tmp_path):
    parent_loader = snapshot._load_parent_prefix
    source, guard, directory, files, manifest = _fixture(monkeypatch, tmp_path)
    unused_source, unused_plan, parent_files, parent_claim, parent_code, unused_prefix, unused_binding = fabricated.small_domain(monkeypatch)
    parent_directory = tmp_path / snapshot.old.PARENT
    parent_directory.mkdir(mode=0o700)
    for name, raw in parent_files.items():
        _write(parent_directory / name, raw)
    _write(parent_directory.parent / ("budget-" + snapshot.old.original.PROTOCOL_SHA256 + ".json"), parent_claim)
    monkeypatch.setattr(snapshot, "_load_parent_prefix", parent_loader)
    def historical(root, arguments, supplied_guard):
        assert arguments[0] in {"merge-base", "show"}
        assert supplied_guard is guard
        if arguments[0] == "merge-base":
            return b""
        return parent_code if arguments[1].startswith(snapshot.old.PARENT_HEAD + ":") else b"fabricated committed historical code"
    monkeypatch.setattr(snapshot.old.cache, "_git", historical)
    monkeypatch.setattr(snapshot.lane.LaneGuard, "refresh", lambda self: pytest.fail("offline replay must not refresh origin"))
    with snapshot.load_refused_child(tmp_path, source, guard, hash_bytes(manifest)) as held:
        assert held.inventory.to_payload()["halted"] is True
        assert held.inventory.to_payload()["attempts_started"] == 2


@pytest.mark.parametrize("name", ["query-00000001.raw", "query-00000001.started.json"])
def test_inplace_change_to_earlier_member_during_replay_prevents_inventory_yield(monkeypatch, tmp_path, name):
    source, guard, directory, files, manifest = _fixture(monkeypatch, tmp_path)
    original_replay = snapshot._replay
    def replay_then_change(*args):
        inventory = original_replay(*args)
        directory_stamp = directory.stat().st_mtime_ns
        path = directory / name
        path.write_bytes(files[name] + b" ")
        assert directory.stat().st_mtime_ns == directory_stamp
        return inventory
    monkeypatch.setattr(snapshot, "_replay", replay_then_change)
    with pytest.raises(snapshot.RefusedSnapshotError, match="snapshot_full_member_stamp_changed"):
        with snapshot.load_refused_child(tmp_path, source, guard, hash_bytes(manifest)):
            pytest.fail("in-place changes must be rejected before inventory yield")


@pytest.mark.parametrize("name", ["query-00000001.raw", "query-00000001.received.json"])
def test_inplace_change_after_yield_is_detected_by_explicit_and_exit_full_checks(monkeypatch, tmp_path, name):
    source, guard, directory, files, manifest = _fixture(monkeypatch, tmp_path)
    with pytest.raises(snapshot.RefusedSnapshotError, match="snapshot_full_member_stamp_changed"):
        with snapshot.load_refused_child(tmp_path, source, guard, hash_bytes(manifest)) as held:
            held.read(name, snapshot.MAXIMUM_MEMBER_BYTES)
            (directory / name).write_bytes(files[name] + b" ")
            held.full_check()


def test_context_exit_alone_rejects_inplace_change_to_previously_read_raw(monkeypatch, tmp_path):
    source, guard, directory, files, manifest = _fixture(monkeypatch, tmp_path)
    with pytest.raises(snapshot.RefusedSnapshotError, match="snapshot_full_member_stamp_changed"):
        with snapshot.load_refused_child(tmp_path, source, guard, hash_bytes(manifest)) as held:
            held.read("query-00000001.raw", 64)
            (directory / "query-00000001.raw").write_bytes(files["query-00000001.raw"] + b" ")
