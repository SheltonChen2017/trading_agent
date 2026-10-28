"""Outer authority tests; original toy archive, explicit code/storage seams.

These tests create no actual image, native flags, credentials or provider
request. Archive tests execute the old real source-held toy producer/closures.
Other tests name their fabricated source/code/control/volume boundaries and
do not establish actual-domain durability or source readiness.
"""
from contextlib import contextmanager
from types import SimpleNamespace
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import capture_short_interest_durable_counts as outer
from scripts import short_interest_count_durable_transport as transport
from test_short_interest_count_durable_budget import genuine_plan, isolated_registries_and_no_network
from test_short_interest_count_durable_transport import operation
from test_short_interest_count_epoch_ledger_loader import Harness, forbid_external_or_capture_seams


@pytest.fixture(autouse=True)
def fresh_outer_registries(monkeypatch, tmp_path_factory):
    # Every reached hold writes its durable report here, never into the lane.
    monkeypatch.setattr(outer, "HOLD_REPORT_DIRECTORY", tmp_path_factory.mktemp("hold") / "count_hold_reports")
    for name, value in (("_ARCHIVES", {}), ("_ARCHIVE_PLANS", {}), ("_ARCHIVE_FAILED", set()),
        ("_LEASES", {}), ("_LEASE_FAILED", set()), ("_LEASE_TERMINALS", {}), ("_LEASE_PHASES", {}),
        ("_LEASE_CLOCKS", {}), ("_RUNS", {}), ("_RUN_ORIGINS", {}), ("_TERMINAL_ORIGINS", {}),
        ("_TERMINALS", {}), ("_TERMINAL_FAILED", set()), ("_DIRECTORIES", {}), ("_PRESERVATION_HOLD", {})):
        monkeypatch.setattr(outer, name, value)
    for name, value in (("_PRESERVATION_LEASES", {}), ("_NEGATIVE_STATUS", {}), ("_NEGATIVE_ORIGINS", {}),
        ("_NEGATIVE_ATTEMPTED", set()), ("_BLOCKED_OPERATIONS", set()), ("_RETENTION_ANNOUNCED", set()),
        ("_SOURCE_BATCHES", {}), ("_SOURCE_BATCH_FAILED", set()), ("_NEGATIVE_FINAL_ATTEMPTED", set()),
        ("_PRESERVATION_PROFILES", {}), ("_PRESERVATION_FAILURES", {}), ("_PRESERVATION_FAILURE_ORIGINS", {})):
        monkeypatch.setattr(outer, name, value)
    monkeypatch.setattr(outer, "_SETTLED_CONTRIBUTIONS", {})
    monkeypatch.setattr(outer, "_CONTRIBUTION_ORIGINS", {})
    for name, value in (("_CHECKPOINT_FACTS", {}), ("_CHECKPOINT_FACTS_FAILED", set()),
        ("_CHECKPOINT_CAPS", {}), ("_CHECKPOINT_ROUND", {}), ("_WRITTEN_CHECKPOINTS", {})):
        monkeypatch.setattr(outer, name, value)
    for name, value in (("_ATTEMPT_SLOTS", {}), ("_ATTEMPT_BY_TICKET", {}), ("_RESPONSE_SLOTS", {}),
        ("_ATTEMPT_USED", set()), ("_RESPONSE_USED", set()), ("_ATTEMPT_RESULTS", {}), ("_WORKER_RETAINED", {})):
        monkeypatch.setattr(outer, name, value)
    for name, value in (("_CONTRIBUTIONS", {}), ("_PRIVATE_PROOFS", {}), ("_CLOSED_ORIGINS", {}),
        ("_UNIONS", {}), ("_FAILED", set()), ("_UNION_FAILED", set())):
        monkeypatch.setattr(outer.transport_union, name, value)


def test_default_registration_blocks_before_archive_key_claim_native_or_provider(monkeypatch, tmp_path):
    monkeypatch.setattr(outer, "SOURCE_AUTHORITY_SHA256", "PENDING")
    calls = []
    for obj, name in ((outer.archive_loader, "load_registered_count_epoch_ledger"),
        (outer.storage, "prepare_registered_volume"), (outer.transport, "read_named_keychain"),
        (outer.controls, "prepare_owned_count_claim"), (outer.transport.wire, "http")):
        monkeypatch.setattr(obj, name, lambda *a, **k: calls.append("FORBIDDEN"))
    with pytest.raises(outer.DurableCountCaptureRefusal, match="registration_pending"):
        outer.run_registered(tmp_path, runtime_head="a" * 40, actual_remote="b" * 40,
            complete_code_manifest={}, archive_code_manifest={})
    assert calls == [] and outer._ARCHIVES == outer._LEASES == outer._TERMINALS == {}


def test_operational_manifest_explicitly_binds_new_plan_and_historical_antecedents():
    paths = outer.code_paths()
    assert "research/short_interest_etf/native_count_recovery_budget.py" in paths
    assert paths == tuple(sorted(set(paths)))
    assert outer.protocol()["bound_antecedent_not_runtime_imported"] == [
        outer.antecedent.previous.WRAPPER, outer.antecedent.WRAPPER]


def test_cli_refusal_never_formats_exception_payload(monkeypatch, capsys):
    def refused(arguments): raise RuntimeError("PRIVATE TOKEN URL BODY")
    monkeypatch.setattr(outer, "_run_cli", refused)
    assert outer.main(["run_registered", "--runtime-head", "a" * 40, "--actual-remote", "b" * 40]) == 2
    value = __import__("json").loads(capsys.readouterr().out)
    assert value["status"] == "refused" and value["authority"]["ready_for_backtest"] is False
    assert outer.failure_summary(RuntimeError("PRIVATE TOKEN URL BODY"))["category"] == "unknown_local_error"


def test_original_toy_archive_issues_token_only_after_original_all_context_closure(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    with h.load() as loaded:
        model = loaded._anchor[0]
        assert model.public_summary()["START_debits"] == 50
    monkeypatch.setattr(outer, "BASELINE_LEDGER_SHA256", model.sha256)
    token = outer._token_from_original_closed_archive(loaded)
    saved = outer._archive_binding(token)
    assert saved[1] is loaded and saved[2] is loaded._anchor and saved[3] is model
    assert saved[6] is model._parts[1].query_plan and outer.sourcelease_model(token) is model
    assert saved[5] == hash_bytes(canonical_json(loaded.closed_summary()).encode())
    assert "saved_context_exited" in h.events
    with pytest.raises(outer.DurableCountCaptureRefusal, match="archive_capacity"):
        outer._token_from_original_closed_archive(loaded)


def test_live_or_failed_archive_cannot_issue_closed_token(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    with pytest.raises(outer.archive_loader._StageFailure):
        with h.load() as loaded:
            outer._token_from_original_closed_archive(loaded)
    assert outer._ARCHIVES == {}


def test_closed_archive_clone_or_matching_payload_is_not_genuine_origin(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path)
    with h.load() as loaded: pass
    monkeypatch.setattr(outer, "BASELINE_LEDGER_SHA256", loaded._anchor[0].sha256)
    forged = object.__new__(outer.archive_loader.RegisteredCountEpochLedger)
    for name in outer.archive_loader.RegisteredCountEpochLedger.__slots__:
        if name != "__weakref__": object.__setattr__(forged, name, getattr(loaded, name))
    with pytest.raises(outer.archive_loader.CountEpochLoaderRefusal): outer._token_from_original_closed_archive(forged)
    assert outer._ARCHIVES == {}


@pytest.fixture
def fabricated_current_code_lease(monkeypatch, tmp_path):
    """Genuine plan/budget; explicit fake already-closed archive and code IO."""
    h = SimpleNamespace(plan=genuine_plan(monkeypatch), tick=100., events=[], fail_close=False)
    h.budget = outer.accounting.open_durable_count_budget(h.plan)
    monkeypatch.setattr(outer.source_scope, "require_dispatch_allowed", lambda: None)  # Explicit SOFTWARE-ONLY fixture seam.
    h.token = object.__new__(outer.OriginalClosedArchiveToken)
    model = h.plan._parts[1]; h.archive = (h.token, object(), object(), model, b"{}", "d" * 64,
        model._parts[1].query_plan, object())
    monkeypatch.setattr(outer, "registered", lambda: None)  # Explicit TEST ONLY registration.
    monkeypatch.setattr(outer, "_archive_binding", lambda token: h.archive if token is h.token else pytest.fail("bad archive"))
    outer._ARCHIVE_PLANS[h.token] = h.plan
    monkeypatch.setattr(outer, "ROOT", tmp_path); monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(outer, "code_paths", lambda: ("fabricated-current-code.py",))
    h.manifest = {"fabricated-current-code.py": "a" * 64}
    monkeypatch.setattr(outer.time, "monotonic", lambda: h.tick)
    monkeypatch.setattr(outer.transport, "_clock", lambda: "2026-10-27T00:00:00Z")
    class Guard:
        def __init__(self, root, *, expected_head, expected_remote): self.root, self.head, self.remote = root, expected_head, expected_remote
        def check(self): h.events.append("current-root-check")
        def refresh(self):
            h.events.append("current-root+matching-remote-check")
            if getattr(h, "remote_advanced", False):
                raise outer.DurableCountCaptureRefusal("REFUSED: durable_capture_START_evidence_changed")
            return outer.lane._evidence({"schema": "si-bounded-batch-lane-evidence-v1", "HEAD": self.head,
                "branch": outer.BRANCH, "actual_remote": self.remote, "actual_ref": outer.lane.REF,
                "status": "clean", "maximum_HTTP_slots": 8})
        def binding(self): return self.root, self.head, self.remote
    monkeypatch.setattr(outer.lane, "LaneGuard", Guard)
    class Held:
        def __init__(self, paths, *, protected, boundary): self.boundary = boundary
        def __enter__(self): h.events.append("current-code-context-open"); return self
        def check(self): h.events.append("current-original-code-check")
        def __exit__(self, *args):
            h.events.append("current-original-code-context-exit")
            if h.fail_close: raise RuntimeError("FABRICATED_CODE_CONTEXT_FAILURE")
    monkeypatch.setattr(outer.archive_loader.count.old.cache, "HeldFiles", Held)
    def audit(root, guard, manifest, held=None):
        assert manifest == tuple(sorted(h.manifest.items()))
        h.events.append("current-held-committed-code-audit" if held is not None else "fresh-postcontext-committed-code-audit")
    monkeypatch.setattr(outer, "_audit_code", audit)
    h.context = lambda: outer._prepare_registered_source_lease(h.token, h.budget, root=tmp_path,
        runtime_head="c" * 40, actual_remote="b" * 40, complete_code_manifest=h.manifest)
    return h


def test_new_lease_uses_original_plan_query_lock_and_closed_archive_lineage(fabricated_current_code_lease):
    h = fabricated_current_code_lease
    with h.context() as lease:
        original = outer.source_lease_live_binding(lease)
        assert len(original) == 16 and original[0] is lease and original[4] is h.plan and original[5] is h.budget
        assert original[6] is h.archive[6] and type(original[12]) is outer._RLOCK_TYPE
        assert original[7] == tuple(sorted(h.manifest.items()))
        assert original[11].name == "capture" and original[11].parent.name == "mount"
    terminal = outer.source_lease_terminal_binding(lease)
    assert terminal is original and outer._source_boundary(lease) is original
    assert h.events.index("current-original-code-context-exit") < h.events.index("fresh-postcontext-committed-code-audit")


@pytest.mark.parametrize("failure", ["context-exit", "late-window", "state-replacement", "fresh-code"])
def test_no_source_terminal_witness_after_original_exit_or_postcheck_failure(fabricated_current_code_lease, monkeypatch, failure):
    h = fabricated_current_code_lease; lease = None
    if failure == "context-exit": h.fail_close = True
    if failure == "fresh-code":
        previous = outer._audit_code
        def audit(root, guard, manifest, held=None):
            if held is None: raise RuntimeError("FABRICATED_FRESH_CODE_FAILURE")
            return previous(root, guard, manifest, held)
        monkeypatch.setattr(outer, "_audit_code", audit)
    with pytest.raises((RuntimeError, outer.DurableCountCaptureRefusal)):
        with h.context() as lease:
            if failure == "late-window": h.tick += 3600
            if failure == "state-replacement": lease._anchor = tuple(list(lease._anchor))
    assert lease not in outer._LEASE_TERMINALS
    with pytest.raises(outer.DurableCountCaptureRefusal): outer.source_lease_terminal_binding(lease)


def test_closed_lease_never_reenters_live_or_reissues_after_a_failed_public_access(fabricated_current_code_lease):
    h = fabricated_current_code_lease
    with h.context() as lease: pass
    with pytest.raises(outer.DurableCountCaptureRefusal, match="not_live"): outer.source_lease_live_binding(lease)
    with pytest.raises(outer.DurableCountCaptureRefusal): outer.source_lease_terminal_binding(lease)
    assert lease in outer._LEASE_FAILED


@pytest.mark.parametrize("field", ["phase", "clock"])
def test_current_lease_phase_or_previous_clock_cannot_be_rebased(fabricated_current_code_lease, field):
    h = fabricated_current_code_lease
    with pytest.raises(outer.DurableCountCaptureRefusal):
        with h.context() as lease:
            record = outer._LEASES[lease]
            if field == "phase": record[4][0] = "CLOSED"
            else: record[6][0] -= 1
            outer.source_lease_live_binding(lease)
    assert lease not in outer._LEASE_TERMINALS


def prepare_original_test_operator(h, monkeypatch):
    """Original operator+lease core with explicit fixture Root/code registration."""
    for name, value in (("_OPERATIONS", {}), ("_FAILED", set()), ("_RESPONSE_CAPS", {}), ("_RECEIVED_CAPS", {}),
        ("_FINAL_CAPS", {}), ("_WINDOWS", {}), ("_REMOTE_BATCHES", {}), ("_START_PERMISSIONS", {}), ("_START_CONSUMED", set())):
        monkeypatch.setattr(transport, name, value)
    monkeypatch.setattr(transport, "ROOT", outer.ROOT)
    monkeypatch.setattr(transport, "SOURCE_AUTHORITY_SHA256", "a" * 64)
    monkeypatch.setattr(outer, "SOURCE_AUTHORITY_SHA256", "a" * 64)
    monkeypatch.setattr(transport, "PROTOCOL_SHA256", hash_payload(transport.policy()))
    monkeypatch.setattr(transport, "_registered", lambda *args: None)
    monkeypatch.setattr(transport, "_coordinator", lambda: outer)


def test_original_source_lease_factory_refreshes_exact_ref_and_issues_original_ticket_roster(fabricated_current_code_lease, monkeypatch):
    h = fabricated_current_code_lease; prepare_original_test_operator(h, monkeypatch)
    ticket = h.budget.reserve_start_slot(h.plan.chunk_positions(1)[0])
    with h.context() as lease:
        op = transport.bind_registered_operation(lease, h.budget)
        before = h.events.count("current-root+matching-remote-check")
        op.authorize_start_batch((ticket,))
        assert h.events.count("current-root+matching-remote-check") == before + 1
        permission = transport.start_permission_binding(op, ticket)
        evidence = outer.source_start_batch_binding(permission[3])
        assert evidence is permission[4] and evidence[1] is op and evidence[2] is outer.source_lease_binding(lease)
        assert evidence[4] == (ticket,) and evidence[5].payload()["actual_ref"] == outer.lane.REF
        clone = object.__new__(outer.SourceStartBatchEvidence); clone._anchor = clone._identity = evidence
        with pytest.raises(outer.DurableCountCaptureRefusal): outer.source_start_batch_binding(clone)
    assert lease in outer._LEASE_TERMINALS


def test_original_ref_advance_during_START_authorization_has_no_permission(fabricated_current_code_lease, monkeypatch):
    h = fabricated_current_code_lease; prepare_original_test_operator(h, monkeypatch)
    ticket = h.budget.reserve_start_slot(h.plan.chunk_positions(1)[0])
    with pytest.raises(outer.DurableCountCaptureRefusal, match="START_evidence_changed"):
        with h.context() as lease:
            op = transport.bind_registered_operation(lease, h.budget); h.remote_advanced = True
            op.authorize_start_batch((ticket,))
    assert transport._START_PERMISSIONS == {} and outer._SOURCE_BATCHES == {} and op in transport._FAILED


def test_forged_chain_hashes_cannot_replace_the_frozen_semantic_authority(monkeypatch):
    monkeypatch.setattr(outer, "SOURCE_AUTHORITY_SHA256", "a" * 64)
    monkeypatch.setattr(outer.transport, "SOURCE_AUTHORITY_SHA256", "a" * 64)
    monkeypatch.setattr(outer.transport, "PROTOCOL_SHA256", "b" * 64)
    monkeypatch.setattr(outer, "NEGATIVE_PRESERVATION_POLICY_SHA256", "c" * 64)
    monkeypatch.setattr(outer, "RUN_PROTOCOL_SHA256", hash_payload(outer.protocol()))
    with pytest.raises(outer.DurableCountCaptureRefusal, match="registration_pending"): outer.registered()


@pytest.fixture
def fabricated_member_caps(operation, monkeypatch):
    h = operation; h.controls.CountClaim = type(h.claim)
    monkeypatch.setattr(outer, "controls", h.controls); monkeypatch.setattr(outer, "responses", h.responses)
    monkeypatch.setattr(outer, "source_lease_binding", lambda lease: h.coordinator.source_lease_binding(lease))
    h.responses.BODY_NAME, h.responses.RECEIPT_NAME = "response.raw", "response.receipt.private.json"
    base = h.coordinator.source_lease_binding(h.lease)[11]
    def origin(path, name, raw): return (None, (path,), None, name, raw, hash_bytes(raw), None, None, None, None, None, None, None, None, None)
    def stamp(raw, inode): return (1, inode, os.getuid(), 0o600, 1, len(raw), 7, 8, 2)
    original_received = h.controls.received_binding
    def received(cap):
        saved = original_received(cap)
        if saved[7] is None:
            ordinal = outer.accounting.ticket_binding(saved[2])[4]
            changed = list(saved); changed[7] = origin(base / "received" / f"{ordinal:06d}", "received.private.json", b"RECEIVED")
            changed[6] = hash_bytes(b"RECEIVED"); changed[8] = stamp(b"RECEIVED", 30 + ordinal); h.received[cap] = tuple(changed)
        return original_received(cap)
    original_response = h.responses.response_binding
    def response(cap):
        saved = original_response(cap)
        if saved[9] is None:
            changed = list(saved); changed[9] = stamp(h.raw, 2); changed[10] = stamp(b"RECEIPT", 4)
            h.response_bindings[cap] = tuple(changed)
        return original_response(cap)
    h.controls.received_binding = received; h.responses.response_binding = response
    for ticket in h.tickets:
        ordinal = ticket.public_summary()["reservation_ordinal"]
        start = h.starts[ticket]; old = list(h.start_bindings[start]); old[9] = origin(base / "starts" / f"{ordinal:06d}", "START.spent.json", b"START")
        old[4] = hash_bytes(b"START"); old[10] = stamp(b"START", 20 + ordinal)
        h.start_bindings[start] = tuple(old)
        h.receive(h.op.dispatch(ticket, h.claim, start))
    h.candidate = h.op.freeze_provisional_root(); h.base = base
    return h


def test_FINAL_members_derive_original_typed_origins_and_exclude_claim_and_self(fabricated_member_caps):
    h = fabricated_member_caps; rows = outer.final_member_rows(h.op, h.candidate)
    assert len(rows) == 8 and [row["name"] for row in rows] == sorted(row["name"] for row in rows)
    assert rows[0]["name"] == "received/000001/received.private.json"
    assert all("claim" not in row["name"] and "manifest" not in row["name"] for row in rows)
    assert any(row["name"] == "responses/000001/response.raw" and row["bytes"] == len(h.raw) for row in rows)


def test_FINAL_member_cannot_adopt_same_raw_file_in_another_directory(fabricated_member_caps):
    h = fabricated_member_caps; start = h.starts[h.tickets[0]]
    saved = list(h.start_bindings[start]); origin = list(saved[9]); origin[1] = (h.base / "wrong",)
    saved[9] = tuple(origin); h.start_bindings[start] = tuple(saved)
    with pytest.raises(outer.DurableCountCaptureRefusal, match="member_changed"): outer.final_member_rows(h.op, h.candidate)
    assert h.op in transport._FAILED


def test_terminal_helper_cannot_be_called_by_a_matching_payload_or_complete_flag(fabricated_member_caps):
    h = fabricated_member_caps
    with pytest.raises(outer.DurableCountCaptureRefusal, match="terminal_required"):
        outer._finish_original_chunk(h.op, h.candidate)
    assert outer._TERMINALS == {}


def test_checkpoint_facts_constructor_and_raw_payload_helper_cannot_mint(fabricated_member_caps):
    h = fabricated_member_caps
    with pytest.raises(outer.DurableCountCaptureRefusal, match="checkpoint_required"): outer.CountCheckpointFacts()
    with pytest.raises(outer.DurableCountCaptureRefusal, match="checkpoint_required"):
        outer._issue_checkpoint_facts(h.op, h.candidate, {"complete": True}, (), ())
    assert outer._CHECKPOINT_FACTS == {}


def test_pure_original_checkpoint_facts_do_not_reenter_expired_source_callbacks(monkeypatch):
    """Explicit fabricated original issuer record; tests only pure provenance."""
    cap = object.__new__(outer.CountCheckpointFacts); raw = canonical_json({"phase": "PROVISIONAL_STORAGE_FACTS"}).encode()
    original = (cap, object(), object(), (), (), raw, hash_bytes(raw), (), (), object())
    cap._anchor = cap._identity = original; outer._CHECKPOINT_FACTS[cap] = original
    monkeypatch.setattr(outer, "source_lease_binding", lambda *a: pytest.fail("expired source callback"))
    assert outer.checkpoint_facts_binding(cap) is original
    clone = object.__new__(outer.CountCheckpointFacts); clone._anchor = clone._identity = original
    with pytest.raises(outer.DurableCountCaptureRefusal): outer.checkpoint_facts_binding(clone)


def test_checkpoint_facts_all_full9_origins_are_persisted_not_current_stat_baselines(fabricated_member_caps, monkeypatch):
    """Genuine toy tickets/operator; FAKE closed control/native/storage origins."""
    import json
    h = fabricated_member_caps; source = h.coordinator.source_lease_binding(h.lease)
    monkeypatch.setattr(outer, "source_lease_live_binding", h.coordinator.source_lease_live_binding)
    monkeypatch.setattr(outer, "_audit_membership", lambda *a: None)  # Named fabricated membership IO.
    mount = h.base.parent
    def stamp(raw, ordinal): return (1, ordinal, os.getuid(), 0o600, 1, len(raw), 7, 8, 2)
    def origin(path, name, raw): return (None, (path,), None, name, raw, hash_bytes(raw), None, None, None, None, None, None, None, None, None)
    claim = list(h.claims[h.claim]); claim[8] = origin(mount / "claim", "claim.spent.json", b"CLAIM")
    claim[6], claim[9] = hash_bytes(b"CLAIM"), stamp(b"CLAIM", 10); h.claims[h.claim] = tuple(claim)
    for role in transport.FINAL_ROLES:
        cap = object(); raw = transport._final_control_payload(h.op, h.candidate, role)
        name = {"inventory": "inventory.private.json", "provisional": "provisional.json", "closed": "closed.json", "manifest": "manifest.private.json"}[role]
        h.finals[cap] = (cap, h.op, role, hash_bytes(raw), origin(h.base / ("final_" + role), name, raw), stamp(raw, 40 + len(h.finals)), h.candidate, object())
        h.op.accept_final_control(cap)
    pin = (1, 2, os.getuid(), 0o700)
    state = {"mount_pin": pin, "root_creation_pin": (1, 2, os.getuid(), os.getgid(), 0o700),
        "mount_native": ((1, 2), os.getuid(), 4096, 0, 1, 0, "apfs", str(mount), "/dev/fabricated"),
        "device_node_pin": (1, 2, 3, 4, 5, 6), "backing_pin": (1, 2, os.getuid(), 0o600, 1),
        "directories": ((mount.parent, None, pin),), "namespace": mount.parent, "device": "/dev/fabricated"}
    h.volume = SimpleNamespace(_binding=lambda: state, check=lambda: None)
    volume_original = (h.volume, h.op, mount, 1, h.plan.sha256, source[10], object(), transport.operation_binding(h.op), object())
    monkeypatch.setattr(transport, "volume_for_operation", lambda op: h.volume)
    monkeypatch.setattr(outer.storage, "volume_binding", lambda *a, **k: volume_original)
    monkeypatch.setattr(outer.storage, "volume_system_entries", lambda *a: (), raising=False)
    monkeypatch.setattr(outer, "_lease_record", lambda lease: (source, "fabricated-archive-token"))
    monkeypatch.setattr(outer, "_archive_binding", lambda token: (None, None, None, None, None, "f" * 64))
    outer._DIRECTORIES[h.op] = ((h.base, pin), (mount / "claim", pin))
    facts = outer.checkpoint_facts(h.op, h.candidate); saved = outer.checkpoint_facts_binding(facts)
    payload = json.loads(saved[5])
    assert payload["phase"] == "PROVISIONAL_STORAGE_FACTS" and payload["authority"]["source_admitted"] is False
    assert len(payload["files"]) == 13  # 2 START +2 received +4 response +4 FINAL + external claim.
    assert all(len(row["seal9"]) == 9 for row in payload["files"])
    assert payload["producer"]["code_manifest"] == [list(row) for row in source[7]]
    assert payload["account"]["covered_positions"] == list(h.plan.chunk_positions(1))
    assert outer.checkpoint_facts(h.op, h.candidate) is facts
    # Revalidation reconstructs all original facts; no changed descriptor may
    # inherit the cached cap or install a new seal.
    state["device"] = "/dev/changed"
    with pytest.raises(outer.DurableCountCaptureRefusal): outer.checkpoint_facts(h.op, h.candidate)


def test_independent_FD_cleanup_drains_other_descriptor_even_when_first_close_fails(monkeypatch):
    calls = []
    def close(fd):
        calls.append(fd)
        if fd == 2: raise OSError(5, "PRIVATE PATH AND MESSAGE")
    monkeypatch.setattr(outer.os, "close", close)
    fds = [1, 2]
    with pytest.raises(outer.DurableCountCaptureRefusal, match="fd_close_failed"): outer._drain_fds(fds)
    assert calls == [2, 1] and fds == []


def test_fixed_manifest_rejects_missing_extra_or_subclass_input(monkeypatch):
    monkeypatch.setattr(outer, "code_paths", lambda: ("a.py",))
    class D(dict): pass
    for candidate in ({}, {"a.py": "b" * 64, "extra.py": "c" * 64}, D({"a.py": "b" * 64})):
        with pytest.raises(outer.DurableCountCaptureRefusal, match="code_changed"): outer._manifest_shape(candidate)
    assert outer._manifest_shape({"a.py": "b" * 64}) == (("a.py", "b" * 64),)


def test_actual_original_inventory_stream_receives_required_phase_aware_boundary(operation, monkeypatch, tmp_path):
    h = operation; directory = tmp_path / "synthetic-inventory"; directory.mkdir(mode=0o700)
    (directory / "fixed-marker").write_bytes(b"SYNTHETIC")
    checks = []
    monkeypatch.setattr(outer, "_source_boundary", lambda lease: checks.append(lease))
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        assert outer._member_names(h.op, fd) == ("fixed-marker",)
        assert outer._member_names(h.op, fd) == ("fixed-marker",)
    finally: os.close(fd)
    assert checks and all(lease is h.lease for lease in checks)


@pytest.mark.parametrize("module,error_class", [(outer, outer.DurableCountCaptureRefusal),
    (transport, transport.CountTransportRefusal), (outer.reader, outer.reader.ClosedCountChunkRefusal)])
def test_safe_own_refusal_projection_never_calls_hostile_argument_comparison_or_formatting(module, error_class):
    calls = []
    class Hostile:
        def __eq__(self, other): calls.append("eq"); raise AssertionError("UNSAFE ARGUMENT EQUALITY")
        def __str__(self): calls.append("str"); raise AssertionError("UNSAFE ARGUMENT STRING")
    error = error_class(Hostile())
    value = module.failure_summary(error)
    assert value["contract_code"] is None and calls == []


@pytest.fixture
def fabricated_outer_run(operation, monkeypatch):
    """Original outer/reader/budget functions; fake source/volume/publish IO.

    This deliberately supplies no source, native or durable-file authority.
    It tests original terminal ordering/provenance, not physical admission.
    """
    h = operation; h.events = []; h.volume_closed, h.source_closed, h.drift = False, False, False
    # This inherited ordering/negative fixture intentionally stays serial.
    # Separate barrier tests below exercise the actual <=8 scheduling path.
    monkeypatch.setattr(outer, "_batch_width", lambda: 1)
    monkeypatch.setattr(outer, "_prepare_attempt_slot", lambda op, ticket, claim: (op, ticket, claim))
    def receive_worker(slot):
        try: return outer._publish_attempt(*slot)
        except BaseException: transport._latch(slot[0]); raise
    monkeypatch.setattr(outer, "_receive_worker", receive_worker)
    monkeypatch.setattr(outer, "_prepare_response_slot", lambda op, slot, observed: (op, slot, observed))
    monkeypatch.setattr(outer, "_response_worker", lambda response: None)  # Fake publish below already registers a fake pair.
    from scripts import short_interest_count_checkpoint as checkpoint
    # Explicit fabricated checkpoint storage seam; the original producer is
    # exercised by its own kernel/FD tests, not these ordering-only fixtures.
    checkpoint_roots = {}
    def checkpoint_publish(op, candidate):
        value = object(); checkpoint_roots[value] = (value, op, candidate, "chunk", None, None,
            "a" * 64, tuple(range(9)), "b" * 64, tuple(range(9)), "checkpoint/chunk", object())
        h.events.append("provisional-checkpoint-publication"); return value
    monkeypatch.setattr(checkpoint, "preflight_checkpoint_resources", lambda *args: h.events.append("checkpoint-preclaim-preflight"))
    monkeypatch.setattr(checkpoint, "publish_provisional_chunk_checkpoint", checkpoint_publish)
    monkeypatch.setattr(checkpoint, "checkpoint_binding", lambda value: checkpoint_roots[value])
    monkeypatch.setattr(checkpoint, "audit_original_checkpoint_roots", lambda: h.events.append("original-checkpoint-postcontext-audit"))
    for ticket in h.tickets: transport._START_PERMISSIONS.pop(ticket, None)
    transport._REMOTE_BATCHES[h.op] = ()  # Explicit fake source fixture begins a fresh outer authorization epoch.
    h.failed_source_checks = 0
    monkeypatch.setattr(outer, "registered", lambda: None)
    monkeypatch.setattr(outer, "RUN_PROTOCOL_SHA256", "a" * 64)
    source = h.coordinator.source_lease_binding(h.lease)
    monkeypatch.setattr(outer, "source_lease_binding", lambda lease: source)
    def live(lease):
        if h.op in transport._FAILED:
            h.failed_source_checks += 1; raise RuntimeError("FABRICATED_QUALIFICATION_FAILURE_MUST_NOT_BE_BYPASSED")
        assert not h.source_closed and lease is h.lease; return source
    def terminal(lease):
        assert h.source_closed and lease is h.lease; return source
    monkeypatch.setattr(outer, "source_lease_live_binding", live)
    monkeypatch.setattr(outer, "source_lease_terminal_binding", terminal)
    monkeypatch.setattr(outer, "SourceStartBatchEvidence", h.coordinator.SourceStartBatchEvidence)
    monkeypatch.setattr(outer, "source_lease_authorize_start_batch", h.coordinator.source_lease_authorize_start_batch)
    monkeypatch.setattr(outer, "source_start_batch_binding", h.coordinator.source_start_batch_binding)
    monkeypatch.setattr(outer, "_source_boundary", lambda lease: terminal(lease) if h.source_closed else live(lease))
    @contextmanager
    def source_context(*args, **kwargs):
        h.events.append("source-code-enter")
        try: yield h.lease
        finally: h.events.append("original-source-code-exits"); h.source_closed = True; h.live = False
    monkeypatch.setattr(outer, "_prepare_registered_source_lease", source_context)
    monkeypatch.setattr(outer.transport, "bind_registered_operation", lambda lease, budget: h.op)
    class Volume:
        mountpoint = source[11].parent
        def check(self): assert not h.volume_closed
        def check_after_close(self):
            assert h.volume_closed
            if h.drift: raise RuntimeError("FABRICATED_ORIGINAL_VOLUME_DRIFT")
        def closed_summary(self): self.check_after_close(); return {"closed": True, "source_admitted": False}
    h.volume = Volume(); op_origin = transport.operation_binding(h.op)
    volume_origin = h.volume, h.op, h.volume.mountpoint, 1, h.plan.sha256, op_origin[5], object(), op_origin, object()
    def volume_binding(value, *, live=False):
        assert value is h.volume
        if live: value.check()
        elif h.volume_closed: value.check_after_close()
        return volume_origin
    @contextmanager
    def volume_context(*args, **kwargs):
        h.events.append("volume-enter")
        try: yield h.volume
        finally: h.events.append("original-volume-exits"); h.volume_closed = True
    storage = SimpleNamespace(CountResponseVolume=Volume, volume_binding=volume_binding,
        prepare_registered_volume=volume_context)
    monkeypatch.setattr(outer, "storage", storage); monkeypatch.setattr(transport, "_volume_module", lambda: storage)
    monkeypatch.setattr(transport, "_coordinator", lambda: outer)
    monkeypatch.setattr(outer, "_lease_record", lambda lease: (None, None, None, object(), None, None, None))
    def fresh_code(*args):
        assert h.source_closed and h.volume_closed; h.events.append("fresh-original-code-audit")
    monkeypatch.setattr(outer, "_audit_code", fresh_code)
    monkeypatch.setattr(outer, "_audit_membership", lambda *a, **k: h.events.append("original-member-audit"))
    monkeypatch.setattr(outer, "_new_directory", lambda *a: a[-1])
    @contextmanager
    def owned(*args):
        yield object(); h.events.append("original-owned-output-exit")
    monkeypatch.setattr(outer, "_owned", owned)
    h.controls.CountClaim = type(h.claim)
    @contextmanager
    def claim(*args, **kwargs): h.events.append("claim-publication"); yield h.claim
    @contextmanager
    def final(owned, operation, candidate, *, role, boundary):
        raw = transport._final_control_payload(operation, candidate, role)
        value = object(); origin = (None, None, None, role, raw, hash_bytes(raw), None, None, None, None, None, None, None, None, None)
        h.finals[value] = value, operation, role, hash_bytes(raw), origin, None, candidate, object()
        yield value
    h.controls.prepare_owned_count_claim, h.controls.prepare_owned_count_final_control = claim, final
    monkeypatch.setattr(outer, "controls", h.controls)
    h.preserved, h.preservation_calls, h.block_negative = [], [], False
    h.final_marker, h.final_calls, h.fail_final = False, [], False
    real_negative_authority = outer.negative.authority
    class PreservationLease:
        def __init__(self): self.fd_open = True
    def prepare_preservation(op, volume):
        assert op is h.op and volume is h.volume and not h.source_closed and not h.volume_closed
        assert op not in transport._FAILED and not h.key_calls and not h.wire_calls
        h.events.append("original-preservation-lease-before-claim-key")
        h.preservation = PreservationLease(); return h.preservation
    def negative_report(lease):
        assert lease is h.preservation
        pending = len(transport._OPERATIONS[h.op][1][1]) - len(h.preserved)
        return {"schema": "si-negative-preservation-observation-v1",
            "status": "blocked_private_bytes_and_FDs_must_remain_alive" if h.block_negative else
                "negative_quarantine_incomplete_process_must_remain_alive" if pending or not h.final_marker else
                "preservation_manifest_sealed_only",
            "requires_process_hold": h.block_negative or pending != 0 or not h.final_marker,
            "final_negative_manifest_issued": h.final_marker,
            "retained_opaque_observations": len(h.preservation_calls), "originally_closed_negative_attempts": len(h.preserved),
            "verified_durable_negative_attempts": 0 if h.block_negative else len(h.preserved),
            "pending_already_started_attempts": pending, "original_mount_FD_retained": lease.fd_open,
            "budget_changes_performed": False, "authority": real_negative_authority()}
    def preserve(lease, observation):
        assert lease is h.preservation and h.op in transport._FAILED
        assert type(observation) is transport.UnqualifiedHttpObservation
        transport.drained_http_observation_binding(observation)
        h.preservation_calls.append(observation); h.events.append("negative-original-observation-publication")
        h.preserved.append(observation); return negative_report(lease)
    def finalize(lease):
        assert lease is h.preservation and h.op in transport._FAILED and not transport._OPERATIONS[h.op][1][2]
        assert len(h.preserved) == len(transport._OPERATIONS[h.op][1][1])
        h.final_calls.append(True); h.events.append("negative-final-preservation-marker-only")
        if h.fail_final: h.block_negative = True
        else: h.final_marker = True
        return negative_report(lease)
    h.negative = SimpleNamespace(OriginalPreservationLease=PreservationLease, authority=real_negative_authority,
        prepare_original_preservation_lease=prepare_preservation, preserve_failed_observation=preserve,
        preservation_binding=negative_report, finalize_failed_chunk=finalize)
    monkeypatch.setattr(outer, "negative", h.negative)
    def publish(operation, ticket, claim):
        observed = operation.dispatch(ticket, claim, h.starts[ticket]); h.receive(observed); return observed
    monkeypatch.setattr(outer, "_publish_attempt", publish)
    tickets = iter(h.tickets)
    monkeypatch.setattr(type(h.budget), "reserve_start_slot", lambda self, position: next(tickets))
    h.member_rows = [{"name": "starts/000001/START.spent.json", "bytes": 1, "sha256": "a" * 64}]
    monkeypatch.setattr(outer, "final_member_rows", lambda *args: h.member_rows)
    h.run = lambda: outer._capture_chunk(object(), h.budget, root=source[1], runtime_head=source[2],
        actual_remote=source[3], complete_code_manifest={"FABRICATED": "d" * 64})
    return h


def test_original_outer_issues_then_settles_only_after_all_original_context_exits(fabricated_outer_run):
    h = fabricated_outer_run; value = h.run()
    assert type(value) is outer.reader.ClosedCountChunk
    assert h.events.index("original-volume-exits") < h.events.index("original-source-code-exits")
    assert h.events.index("original-source-code-exits") < h.events.index("fresh-original-code-audit")
    assert h.events.index("checkpoint-preclaim-preflight") < h.events.index("original-preservation-lease-before-claim-key")
    assert h.events.index("provisional-checkpoint-publication") < h.events.index("original-volume-exits")
    bound = outer.reader.closed_count_chunk_accounting(value)
    assert bound[0] is h.budget.budget_identity and bound[1] is h.plan and bound[3] == h.tickets
    assert h.budget.public_summary()["current_chunk"] == 2
    contributions = outer._original_settled_contributions(h.budget)
    assert len(contributions) == 1
    assert outer.transport_union.contribution_binding(contributions[0])[5] is outer.accounting.settled_chunk_accounting(h.budget)[3][0]
    assert outer.authority()["source_admitted"] is outer.authority()["ready_for_backtest"] is False


def test_original_terminal_pointer_and_late_original_volume_failure_latch(fabricated_outer_run):
    h = fabricated_outer_run; value = h.run(); candidate = outer._TERMINALS[h.op][1]
    original = outer.terminal_chunk_binding(h.op, candidate)
    outer._TERMINALS[h.op] = tuple(list(original))
    with pytest.raises(outer.DurableCountCaptureRefusal): outer.terminal_chunk_binding(h.op, candidate)
    outer._TERMINALS[h.op] = original
    with pytest.raises(transport.CountTransportRefusal): outer.reader.closed_count_chunk_accounting(value)
    assert h.op in outer._TERMINAL_FAILED


def test_late_original_storage_drift_vetoes_already_issued_result(fabricated_outer_run):
    h = fabricated_outer_run; value = h.run(); h.drift = True
    with pytest.raises(RuntimeError, match="FABRICATED_ORIGINAL_VOLUME_DRIFT"):
        outer.reader.closed_count_chunk_accounting(value)
    h.drift = False
    with pytest.raises(outer.reader.ClosedCountChunkRefusal): outer.reader.closed_count_chunk_accounting(value)


def fail_after_first_genuine_observation(h, monkeypatch):
    def publish(operation, ticket, claim):
        operation.dispatch(ticket, claim, h.starts[ticket])
        raise RuntimeError("PRIVATE_EXCEPTION_SENTINEL")
    monkeypatch.setattr(outer, "_publish_attempt", publish)


def test_negative_lease_precedes_claim_key_and_positive_path_does_not_activate_it(fabricated_outer_run):
    h = fabricated_outer_run; h.run()
    assert h.events.index("original-preservation-lease-before-claim-key") < h.events.index("claim-publication")
    assert h.preservation_calls == [] and h.preservation.fd_open and len(h.wire_calls) == len(h.tickets)


def test_failed_publication_quarantines_original_body_inside_volume_without_qualified_guard_reset(fabricated_outer_run, monkeypatch):
    h = fabricated_outer_run; fail_after_first_genuine_observation(h, monkeypatch)
    with pytest.raises(RuntimeError, match="PRIVATE_EXCEPTION_SENTINEL"): h.run()
    assert len(h.preservation_calls) == len(h.preserved) == 1
    opaque = h.preserved[0]
    assert transport.drained_http_observation_binding(opaque)[10] == h.raw
    assert h.events.index("negative-original-observation-publication") < h.events.index("original-volume-exits")
    assert h.events.index("negative-final-preservation-marker-only") < h.events.index("original-volume-exits")
    assert h.op in transport._FAILED and h.failed_source_checks == 0
    assert h.preservation.fd_open and len(h.key_calls) == len(h.wire_calls) == 1
    assert outer._TERMINALS == {} and outer.accounting.settled_chunk_accounting(h.budget)[3] == ()
    assert h.budget._state[0] == 1
    with pytest.raises(outer.accounting.DurableCountBudgetRefusal): h.budget.public_summary()
    assert outer._negative_summaries()[0]["status"] == "negative_preservation_complete"
    assert not outer._requires_process_hold()
    assert h.final_marker and h.final_calls == [True]


class HoldingTestSentinel(BaseException): pass


def test_blocked_private_bytes_and_original_FD_enter_hold_before_context_teardown(fabricated_outer_run, monkeypatch):
    h = fabricated_outer_run; h.block_negative = True; fail_after_first_genuine_observation(h, monkeypatch)
    holds = []
    def hold():
        holds.append((h.volume_closed, h.source_closed, h.preservation.fd_open))
        raise HoldingTestSentinel()
    monkeypatch.setattr(outer, "_retain_failed_process", hold)
    with pytest.raises(HoldingTestSentinel): h.run()
    assert holds[0] == (False, False, True)  # Fake interruption only; production never leaves this hold.
    assert h.preservation.fd_open and h.failed_source_checks == 0 and len(h.wire_calls) == 1
    assert outer._requires_process_hold() and outer._PRESERVATION_HOLD[h.op][4].args == ("PRIVATE_EXCEPTION_SENTINEL",)
    assert len(h.preservation_calls) == 1  # No namespace retry during outer/context cleanup.
    assert outer._TERMINALS == {}


def test_retention_loop_emits_only_fixed_projection_and_has_no_source_or_network_step(fabricated_outer_run, monkeypatch, capsys):
    h = fabricated_outer_run; h.block_negative = True; h.raw = b"PRIVATE_BODY_SENTINEL"
    fail_after_first_genuine_observation(h, monkeypatch)
    original_hold = outer._retain_failed_process
    monkeypatch.setattr(outer, "_retain_failed_process", lambda: (_ for _ in ()).throw(HoldingTestSentinel()))
    with pytest.raises(HoldingTestSentinel): h.run()
    monkeypatch.setattr(outer, "_retain_failed_process", original_hold)
    sleeps = []
    def wait(seconds): sleeps.append(seconds); raise HoldingTestSentinel()
    monkeypatch.setattr(outer.time, "sleep", wait)
    with pytest.raises(HoldingTestSentinel): original_hold()
    output = capsys.readouterr().out
    assert sleeps == [30] and "preservation_blocked" in output
    assert "PRIVATE_BODY_SENTINEL" not in output and "PRIVATE_EXCEPTION_SENTINEL" not in output
    assert len(h.key_calls) == len(h.wire_calls) == 1 and h.preservation.fd_open


def test_retention_announcement_never_claims_complete_private_retention(fabricated_outer_run, monkeypatch, capsys):
    # SI-CR24-006: a hold report must not let an operator infer that every
    # unexported RAM observation survived; only the process itself retains it.
    h = fabricated_outer_run; h.block_negative = True
    fail_after_first_genuine_observation(h, monkeypatch)
    original_hold = outer._retain_failed_process
    monkeypatch.setattr(outer, "_retain_failed_process", lambda: (_ for _ in ()).throw(HoldingTestSentinel()))
    with pytest.raises(HoldingTestSentinel): h.run()
    monkeypatch.setattr(outer, "_retain_failed_process", original_hold)
    monkeypatch.setattr(outer.time, "sleep", lambda seconds: (_ for _ in ()).throw(HoldingTestSentinel()))
    with pytest.raises(HoldingTestSentinel): original_hold()
    lines = [line for line in capsys.readouterr().out.splitlines() if "preservation_blocked" in line]
    assert len(lines) == 1
    summary = json.loads(lines[0])
    assert summary["requires_process_hold"] is True
    assert summary["known_private_observations_are_complete"] is False
    assert all(summary[name] == 0 for name in ("additional_HTTP_from_hold", "new_claims_from_hold",
        "new_STARTs_from_hold", "new_credentials_from_hold"))


def _reach_real_hold(h, monkeypatch):
    h.block_negative = True; h.raw = b"PRIVATE_BODY_SENTINEL"
    fail_after_first_genuine_observation(h, monkeypatch)
    original_hold = outer._retain_failed_process
    monkeypatch.setattr(outer, "_retain_failed_process", lambda: (_ for _ in ()).throw(HoldingTestSentinel()))
    with pytest.raises(HoldingTestSentinel): h.run()
    monkeypatch.setattr(outer, "_retain_failed_process", original_hold)
    monkeypatch.setattr(outer.time, "sleep", lambda seconds: (_ for _ in ()).throw(HoldingTestSentinel()))
    return original_hold


def test_hold_report_is_durable_content_addressed_and_written_before_stdout(fabricated_outer_run, monkeypatch, capsys):
    # SI-CR24-002: exec13448's stdout projection became unavailable after its
    # process disappeared; the accounting copy must already be on disk before stdout.
    hold = _reach_real_hold(fabricated_outer_run, monkeypatch)
    directory, seen, synced = outer.HOLD_REPORT_DIRECTORY, [], []
    def recording_print(*args, **kwargs):
        seen.append(sorted(path.name for path in directory.iterdir()) if directory.exists() else [])
        print(*args, **kwargs)
    monkeypatch.setattr(outer, "print", recording_print, raising=False)
    real_fsync = os.fsync
    def fsync(fd):
        info = os.fstat(fd); synced.append((info.st_dev, info.st_ino))
        return real_fsync(fd)
    monkeypatch.setattr(outer.os, "fsync", fsync)
    with pytest.raises(HoldingTestSentinel): hold()
    files = sorted(directory.iterdir())
    assert len(files) == 1 and seen and seen[0] == [files[0].name]
    # Distinct durable barriers: file bytes, report entry, and newly created directory's parent entry.
    assert synced == [(info.st_dev, info.st_ino) for info in
        (files[0].lstat(), directory.lstat(), directory.parent.lstat())]
    data = files[0].read_bytes()
    assert files[0].name == "hold-" + hash_bytes(data) + ".json"
    assert files[0].lstat().st_mode & 0o777 == 0o400 and directory.lstat().st_mode & 0o777 == 0o700
    assert b"PRIVATE_BODY_SENTINEL" not in data and b"PRIVATE_EXCEPTION_SENTINEL" not in data
    lines = capsys.readouterr().out.splitlines()
    summary = json.loads(next(line for line in lines if "preservation_blocked" in line))
    record = json.loads(data)
    assert record["retention_summary"] == summary and record["release_or_settlement_authority"] is False
    assert record["private_bytes_retained_only_by_holding_process"] is True
    persisted = json.loads(next(line for line in lines if "si-count-hold-report-persistence-v1" in line))
    assert persisted == {"schema": "si-count-hold-report-persistence-v1", "durable_report_written": True,
        "durable_report_sha256": hash_bytes(data)}


@pytest.mark.parametrize("hazard", ["symlink", "group_readable"])
def test_unsafe_hold_report_directory_never_receives_the_report_or_releases_hold(fabricated_outer_run, monkeypatch,
        capsys, tmp_path, hazard):
    hold = _reach_real_hold(fabricated_outer_run, monkeypatch)
    target = tmp_path / "elsewhere"; target.mkdir(mode=0o700)
    if hazard == "symlink":
        outer.HOLD_REPORT_DIRECTORY.parent.mkdir(exist_ok=True)
        outer.HOLD_REPORT_DIRECTORY.symlink_to(target, target_is_directory=True)
    else:
        outer.HOLD_REPORT_DIRECTORY.mkdir(); outer.HOLD_REPORT_DIRECTORY.chmod(0o750)
    with pytest.raises(HoldingTestSentinel): hold()  # Still holds after the refused copy.
    assert list(target.iterdir()) == [] and (hazard == "symlink" or list(outer.HOLD_REPORT_DIRECTORY.iterdir()) == [])
    output = capsys.readouterr().out
    assert "preservation_blocked" in output and '"durable_report_written":false' in output


def test_hold_report_name_is_never_replaced(monkeypatch):
    real = outer.datetime
    class FixedClock:
        @staticmethod
        def now(zone): return real(2026, 10, 28, tzinfo=zone)
    monkeypatch.setattr(outer, "datetime", FixedClock)
    raw = canonical_json({"status": "preservation_blocked"})
    digest = outer._persist_hold_report(raw)
    path = outer.HOLD_REPORT_DIRECTORY / ("hold-" + digest + ".json"); original = path.read_bytes()
    with pytest.raises(FileExistsError): outer._persist_hold_report(raw)
    assert path.read_bytes() == original and len(list(outer.HOLD_REPORT_DIRECTORY.iterdir())) == 1


def test_new_hold_report_directory_link_is_fsynced_before_durable_success(monkeypatch):
    directory = outer.HOLD_REPORT_DIRECTORY
    containing = directory.parent.lstat(); synced = []
    real_fsync = os.fsync
    def fsync(fd):
        info = os.fstat(fd); synced.append((info.st_dev, info.st_ino))
        return real_fsync(fd)
    monkeypatch.setattr(outer.os, "fsync", fsync)
    digest = outer._persist_hold_report(canonical_json({"status": "preservation_blocked"}))
    report = (directory / ("hold-" + digest + ".json")).lstat()
    created = directory.lstat()
    assert (report.st_dev, report.st_ino) in synced
    assert (created.st_dev, created.st_ino) in synced
    assert (containing.st_dev, containing.st_ino) in synced  # Parent owns the newly created directory entry.


def test_hold_report_zero_progress_refuses_without_retrying_or_hanging(monkeypatch):
    real_write = os.write; calls = []
    def write(fd, data):
        calls.append(len(data))
        return 0 if len(calls) == 1 else real_write(fd, data)
    monkeypatch.setattr(outer.os, "write", write)
    with pytest.raises(outer.DurableCountCaptureRefusal, match="hold_report_refused"):
        outer._persist_hold_report(canonical_json({"status": "preservation_blocked"}))
    assert len(calls) == 1


def test_named_hold_directory_replacement_cannot_announce_durable_success(fabricated_outer_run, monkeypatch, capsys):
    hold = _reach_real_hold(fabricated_outer_run, monkeypatch)
    directory = outer.HOLD_REPORT_DIRECTORY; directory.mkdir(mode=0o700)
    original = directory.lstat(); moved = directory.with_name("original-moved")
    real_open = os.open; changed = []
    def open_with_replacement(*args, **kwargs):
        fd = real_open(*args, **kwargs); info = os.fstat(fd)
        if not changed and (info.st_dev, info.st_ino) == (original.st_dev, original.st_ino):
            directory.rename(moved); directory.mkdir(mode=0o700); changed.append(True)
        return fd
    monkeypatch.setattr(outer.os, "open", open_with_replacement)
    with pytest.raises(HoldingTestSentinel): hold()
    assert changed == [True] and list(directory.iterdir()) == []
    output = capsys.readouterr().out
    assert '"durable_report_written":false' in output
    assert '"durable_report_written":true' not in output
    assert outer._requires_process_hold() and fabricated_outer_run.preservation.fd_open


@pytest.mark.parametrize("mutation_barrier", [1, 3])
def test_hold_report_same_size_original_inode_mutation_refuses_instead_of_wrong_digest(monkeypatch, mutation_barrier):
    real_fsync = os.fsync; changed, barriers, original_writer = [], [], []
    def fsync(fd):
        real_fsync(fd); info = os.fstat(fd)
        barriers.append(fd)
        if outer.stat.S_ISREG(info.st_mode): original_writer.append(fd)
        if len(barriers) == mutation_barrier:
            assert os.pwrite(original_writer[0], b"X", 0) == 1
            changed.append(True)
    monkeypatch.setattr(outer.os, "fsync", fsync)
    with pytest.raises(outer.DurableCountCaptureRefusal, match="hold_report_refused"):
        outer._persist_hold_report(canonical_json({"status": "preservation_blocked"}))
    assert changed == [True]


@pytest.mark.parametrize("amount", [False, -1, None, 3 * 1024 ** 2])
def test_hold_report_invalid_write_progress_refuses_immediately(monkeypatch, amount):
    calls = []
    def write(fd, data): calls.append(len(data)); return amount
    monkeypatch.setattr(outer.os, "write", write)
    with pytest.raises(outer.DurableCountCaptureRefusal, match="hold_report_refused"):
        outer._persist_hold_report(canonical_json({"status": "preservation_blocked"}))
    assert len(calls) == 1


def test_hold_report_short_writes_preserve_exact_original_copy(monkeypatch):
    real_write = os.write; calls = []
    def write(fd, data):
        calls.append(len(data)); return real_write(fd, data[:7])
    monkeypatch.setattr(outer.os, "write", write)
    digest = outer._persist_hold_report(canonical_json({"status": "preservation_blocked"}))
    saved = (outer.HOLD_REPORT_DIRECTORY / ("hold-" + digest + ".json")).read_bytes()
    assert hash_bytes(saved) == digest and len(calls) > 1


def test_hold_report_exact_original_inode_readback_is_required(monkeypatch):
    calls = []
    def wrong_read(fd, size): calls.append(size); return b"X" * size
    monkeypatch.setattr(outer.os, "read", wrong_read)
    with pytest.raises(outer.DurableCountCaptureRefusal, match="hold_report_refused"):
        outer._persist_hold_report(canonical_json({"status": "preservation_blocked"}))
    assert calls and all(0 < amount <= 65536 for amount in calls)


@pytest.mark.parametrize("failed_barrier", [1, 2, 3])
def test_hold_report_fsync_failure_keeps_original_private_hold(fabricated_outer_run, monkeypatch, capsys, failed_barrier):
    hold = _reach_real_hold(fabricated_outer_run, monkeypatch)
    real_fsync = os.fsync; calls = []
    def fsync(fd):
        calls.append(fd)
        if len(calls) == failed_barrier: raise OSError("PRIVATE_FSYNC_DIAGNOSTIC_SENTINEL")
        return real_fsync(fd)
    monkeypatch.setattr(outer.os, "fsync", fsync)
    with pytest.raises(HoldingTestSentinel): hold()
    output = capsys.readouterr().out
    assert len(calls) == failed_barrier and '"durable_report_written":false' in output
    assert "PRIVATE_FSYNC_DIAGNOSTIC_SENTINEL" not in output
    assert outer._requires_process_hold() and fabricated_outer_run.preservation.fd_open
    assert list(outer.HOLD_REPORT_DIRECTORY.iterdir())  # Preserve original partial/unconfirmed evidence.


def test_hold_report_refuses_symlinked_ancestor_before_creating_copy(monkeypatch, tmp_path):
    target = tmp_path / "physical"; target.mkdir(mode=0o700)
    alias = tmp_path / "alias"; alias.symlink_to(target, target_is_directory=True)
    monkeypatch.setattr(outer, "HOLD_REPORT_DIRECTORY", alias / "count_hold_reports")
    with pytest.raises(outer.DurableCountCaptureRefusal, match="hold_report_refused"):
        outer._persist_hold_report(canonical_json({"status": "preservation_blocked"}))
    assert list(target.iterdir()) == []


@pytest.mark.parametrize("hazard", ["directory_mode", "file_mode", "extra_file_link"])
def test_hold_report_protection_drift_at_final_barrier_refuses(monkeypatch, hazard):
    real_fsync = os.fsync; calls = []
    def fsync(fd):
        real_fsync(fd); calls.append(fd)
        if len(calls) == 3:
            directory = outer.HOLD_REPORT_DIRECTORY
            saved = next(directory.iterdir())
            if hazard == "directory_mode": directory.chmod(0o750)
            elif hazard == "file_mode": saved.chmod(0o440)
            else: os.link(saved, directory / "extra-link")
    monkeypatch.setattr(outer.os, "fsync", fsync)
    with pytest.raises(outer.DurableCountCaptureRefusal, match="hold_report_refused"):
        outer._persist_hold_report(canonical_json({"status": "preservation_blocked"}))
    assert len(calls) == 3


def test_hold_report_final_named_directory_audit_runs_after_all_descriptors_close(monkeypatch):
    directory = outer.HOLD_REPORT_DIRECTORY
    containing = directory.parent.lstat(); real_close = os.close; changed = []
    def close(fd):
        info = os.fstat(fd); real_close(fd)
        if not changed and (info.st_dev, info.st_ino) == (containing.st_dev, containing.st_ino):
            directory.rename(directory.with_name("original-after-close")); directory.mkdir(mode=0o700)
            changed.append(True)
    monkeypatch.setattr(outer.os, "close", close)
    with pytest.raises(outer.DurableCountCaptureRefusal, match="hold_report_refused"):
        outer._persist_hold_report(canonical_json({"status": "preservation_blocked"}))
    assert changed == [True] and list(directory.iterdir()) == []


def test_hold_report_bound_refuses_before_any_new_directory(monkeypatch):
    raw = canonical_json({"status": "X" * (2 * 1024 ** 2)})
    with pytest.raises(outer.DurableCountCaptureRefusal, match="hold_report_refused"):
        outer._persist_hold_report(raw)
    assert not outer.HOLD_REPORT_DIRECTORY.exists()


def test_CLI_returns_two_only_after_all_negative_attempts_are_preserved(fabricated_outer_run, monkeypatch, capsys):
    h = fabricated_outer_run; fail_after_first_genuine_observation(h, monkeypatch)
    monkeypatch.setattr(outer, "_run_cli", lambda arguments: h.run())
    result = outer.main(["run_registered", "--runtime-head", "c" * 40, "--actual-remote", "b" * 40])
    output = capsys.readouterr().out
    assert result == 2 and "negative_preservation_complete" in output and "PRIVATE_EXCEPTION_SENTINEL" not in output
    assert not outer._requires_process_hold() and h.preservation.fd_open


def test_CLI_cannot_exit_two_while_original_private_preservation_requires_hold(fabricated_outer_run, monkeypatch):
    h = fabricated_outer_run; h.block_negative = True; fail_after_first_genuine_observation(h, monkeypatch)
    monkeypatch.setattr(outer, "_run_cli", lambda arguments: h.run())
    holds = []
    def hold(): holds.append(True); raise HoldingTestSentinel()
    monkeypatch.setattr(outer, "_retain_failed_process", hold)
    with pytest.raises(HoldingTestSentinel):
        outer.main(["run_registered", "--runtime-head", "c" * 40, "--actual-remote", "b" * 40])
    assert holds and outer._requires_process_hold() and h.preservation.fd_open


def test_drain_waits_for_all_original_inflight_results_then_preserves_each_once(fabricated_outer_run, monkeypatch):
    h = fabricated_outer_run
    h.preservation = h.negative.prepare_original_preservation_lease(h.op, h.volume)
    outer._PRESERVATION_LEASES[h.op] = h.preservation, transport.operation_binding(h.op), h.volume, object()
    outer._PRESERVATION_PROFILES[h.op] = tuple(h.negative.authority().items())
    h.op.authorize_start_batch(h.tickets)
    entered, release = threading.Barrier(3), threading.Event()
    def opened(*args, **kwargs):
        entered.wait(timeout=5); assert release.wait(timeout=5); return h.response(h.raw)
    monkeypatch.setattr(h.opener, "open", opened)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(h.op.dispatch, ticket, h.claim, h.starts[ticket]) for ticket in h.tickets]
        entered.wait(timeout=5)
        timer = threading.Timer(.05, release.set); timer.start()
        try: report = outer._preserve_failed_chunk(h.op, h.volume, RuntimeError("PRIVATE_EXCEPTION_SENTINEL"))
        finally: release.set(); timer.join(timeout=5)
        returned = tuple(future.result(timeout=5) for future in futures)
    assert all(type(item) is transport.UnqualifiedHttpObservation for item in returned)
    assert len(h.preservation_calls) == len(h.preserved) == 2 and report["requires_process_hold"] is False
    assert h.failed_source_checks == 0 and h.preservation.fd_open and outer._TERMINALS == {}
    assert not transport._OPERATIONS[h.op][1][2] and h.op in transport._FAILED


def test_one_quarantine_error_keeps_all_bodies_and_attempts_other_original_results(fabricated_outer_run, monkeypatch):
    h = fabricated_outer_run
    h.preservation = h.negative.prepare_original_preservation_lease(h.op, h.volume)
    outer._PRESERVATION_LEASES[h.op] = h.preservation, transport.operation_binding(h.op), h.volume, object()
    outer._PRESERVATION_PROFILES[h.op] = tuple(h.negative.authority().items())
    h.op.authorize_start_batch(h.tickets)
    for ticket in h.tickets: h.op.dispatch(ticket, h.claim, h.starts[ticket])
    original = h.negative.preserve_failed_observation
    failures = []
    def preserve(lease, observation):
        if not failures: failures.append(observation); raise OSError(5, "PRIVATE_ERROR_SENTINEL")
        return original(lease, observation)
    h.negative.preserve_failed_observation = preserve
    report = outer._preserve_failed_chunk(h.op, h.volume, RuntimeError("PRIVATE_EXCEPTION_SENTINEL"))
    assert report["requires_process_hold"] is True and len(failures) == len(h.preserved) == 1
    assert len(outer._PRESERVATION_HOLD[h.op][3]) == 2 and h.preservation.fd_open
    # A second exception boundary audits; it never retries an old namespace.
    outer._preserve_failed_chunk(h.op, h.volume, RuntimeError("LATER_EXCEPTION"))
    assert len(failures) == len(h.preserved) == 1


def test_contribution_snapshots_immediately_before_settlement_and_is_retained_only_after_append(fabricated_outer_run, monkeypatch):
    h = fabricated_outer_run; order = []
    original_snapshot = outer.transport_union.freeze_closed_count_transport_contribution
    original_settle = type(h.budget).settle_closed_chunk
    def snapshot(closed):
        assert outer.accounting.settled_chunk_accounting(h.budget)[3] == ()
        assert h.budget not in outer._SETTLED_CONTRIBUTIONS
        order.append("original_snapshot_before_settle")
        return original_snapshot(closed)
    def settle(budget, closed):
        assert order == ["original_snapshot_before_settle"]
        assert h.budget not in outer._SETTLED_CONTRIBUTIONS
        result = original_settle(budget, closed); order.append("original_irreversible_append"); return result
    monkeypatch.setattr(outer.transport_union, "freeze_closed_count_transport_contribution", snapshot)
    monkeypatch.setattr(type(h.budget), "settle_closed_chunk", settle)
    h.run()
    assert order == ["original_snapshot_before_settle", "original_irreversible_append"]
    assert len(outer._original_settled_contributions(h.budget)) == 1


def test_failed_settlement_never_enters_outer_union_registry(fabricated_outer_run, monkeypatch):
    h = fabricated_outer_run
    def refuse(budget, closed): raise RuntimeError("FABRICATED_ORIGINAL_SETTLEMENT_FAILURE")
    monkeypatch.setattr(type(h.budget), "settle_closed_chunk", refuse)
    with pytest.raises(RuntimeError, match="FABRICATED_ORIGINAL_SETTLEMENT_FAILURE"): h.run()
    assert h.budget not in outer._SETTLED_CONTRIBUTIONS
    assert outer.accounting.settled_chunk_accounting(h.budget)[3] == ()


def test_all_frozen_registration_hashes_match_without_source_IO(monkeypatch):
    calls = []
    for obj, name in ((outer.archive_loader, "load_registered_count_epoch_ledger"),
            (outer.storage, "prepare_registered_volume"), (outer.transport, "read_named_keychain")):
        monkeypatch.setattr(obj, name, lambda *a, **k: calls.append("FORBIDDEN"))
    assert outer.registered() is None and calls == []


@pytest.mark.parametrize("module,field,error", [
    (outer.negative, "PRESERVATION_POLICY_SHA256", outer.negative.NegativePreservationRefusal),
    (outer.checkpoints, "CHECKPOINT_POLICY_SHA256", outer.checkpoints.CountCheckpointRefusal)])
def test_forged_outer_hash_cannot_skip_independent_preservation_registration(monkeypatch, module, field, error):
    monkeypatch.setattr(module, field, "0" * 64)
    if module is outer.negative: monkeypatch.setattr(outer, "NEGATIVE_PRESERVATION_POLICY_SHA256", "0" * 64)
    monkeypatch.setattr(outer, "RUN_PROTOCOL_SHA256", hash_payload(outer.protocol()))
    with pytest.raises(error, match="registration_pending"): outer.registered()


def test_registered_wrong_root_still_refuses_before_archive_or_claim(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(outer.archive_loader, "load_registered_count_epoch_ledger", lambda *a, **k: calls.append(1))
    with pytest.raises(outer.DurableCountCaptureRefusal, match="exact_root_required"):
        outer.run_registered(tmp_path, runtime_head="a" * 40, actual_remote="b" * 40,
            complete_code_manifest={}, archive_code_manifest={})
    assert calls == []


@pytest.mark.parametrize("head,remote", [("bad", "b" * 40), ("a" * 40, "bad"), (True, "b" * 40)])
def test_CLI_hash_shape_refuses_before_repository_or_source_factory(monkeypatch, head, remote):
    monkeypatch.setattr(outer, "_require_lane_root", lambda root: None)  # Explicit fake physical-root seam.
    monkeypatch.setattr(outer.lane, "LaneGuard", lambda *a, **k: pytest.fail("repository reached"))
    args = outer.argparse.Namespace(command="run_registered", runtime_head=head, actual_remote=remote)
    with pytest.raises(outer.DurableCountCaptureRefusal, match="CLI_arguments_refused"): outer._run_cli(args)


def test_CLI_passes_only_fixed_committed_catalogues_to_canonical_factory(monkeypatch, capsys):
    from types import SimpleNamespace
    calls = []
    monkeypatch.setattr(outer.source_scope, "require_dispatch_allowed", lambda: None)  # Explicit SOFTWARE-ONLY fixture seam.
    manifest = {name: "d" * 64 for name in outer.code_paths()}
    monkeypatch.setattr(outer, "_require_lane_root", lambda root: calls.append(("physical", root)))
    monkeypatch.setattr(outer.lane, "LaneGuard", lambda root, **kw: SimpleNamespace(refresh=lambda: calls.append("fresh-ref")))
    monkeypatch.setattr(outer, "_committed_CLI_manifest", lambda guard, head: manifest)
    def run(root, **kwargs): calls.append(("canonical", root, kwargs)); return {"source_admitted": False}
    monkeypatch.setattr(outer, "run_registered", run)
    args = outer.argparse.Namespace(command="run_registered", runtime_head="a" * 40, actual_remote="b" * 40)
    assert outer._run_cli(args) == {"source_admitted": False}
    selected = calls[-1][2]
    assert selected["complete_code_manifest"] is manifest
    assert selected["archive_code_manifest"] == {name: manifest[name] for name in outer.archive_loader.code_paths()}
    value = __import__("json").loads(capsys.readouterr().out)
    assert value["stage"] == "before_original_archive_replay" and value["new_HTTP_started"] is False


def test_module_entrypoint_delegates_to_canonical_registry_without_source(monkeypatch):
    import runpy
    calls = []
    monkeypatch.setattr(outer, "main", lambda: calls.append(outer.CountSourceLease) or 17)
    with pytest.raises(SystemExit) as result: runpy.run_path(outer.__file__, run_name="__main__")
    assert result.value.code == 17 and calls == [outer.CountSourceLease]


@pytest.mark.parametrize("failure", [BrokenPipeError, OSError, ValueError, RuntimeError])
def test_announcement_failure_keeps_required_private_hold(monkeypatch, failure):
    class StopFabricatedHold(BaseException): pass
    calls = []
    monkeypatch.setattr(outer, "_requires_process_hold", lambda: True)
    monkeypatch.setattr(outer, "_retention_summary", lambda: {"status": "preservation_blocked"})
    def failed_print(*args, **kwargs): raise failure("FABRICATED_PRIVATE_NOTIFICATION_ERROR")
    monkeypatch.setattr(outer, "print", failed_print, raising=False)
    def sleep(seconds): calls.append(seconds); raise StopFabricatedHold
    monkeypatch.setattr(outer.time, "sleep", sleep)
    with pytest.raises(StopFabricatedHold): outer._retain_failed_process()
    assert calls == [30] and outer._RETENTION_ANNOUNCED == {"announced"}


def test_summary_failure_keeps_required_private_hold(monkeypatch):
    class StopFabricatedHold(BaseException): pass
    calls = []
    monkeypatch.setattr(outer, "_requires_process_hold", lambda: True)
    def failed_summary(): raise RuntimeError("FABRICATED_PRIVATE_SUMMARY_ERROR")
    monkeypatch.setattr(outer, "_retention_summary", failed_summary)
    def sleep(seconds): calls.append(seconds); raise StopFabricatedHold
    monkeypatch.setattr(outer.time, "sleep", sleep)
    with pytest.raises(StopFabricatedHold): outer._retain_failed_process()
    assert calls == [30] and outer._RETENTION_ANNOUNCED == {"announced"}


@pytest.mark.parametrize("route", ["CLI", "round", "lease"])
def test_unresolved_prior_run_gate_precedes_every_source_dispatch_route(monkeypatch, tmp_path, route):
    monkeypatch.setattr(outer, "registered", lambda: None)  # SOFTWARE-ONLY registration and physical-root seams.
    monkeypatch.setattr(outer, "_require_lane_root", lambda root: None)
    monkeypatch.setattr(outer, "ROOT", tmp_path); monkeypatch.chdir(tmp_path)
    calls = []
    for module, name in ((outer.lane, "LaneGuard"), (outer, "_archive_binding"),
            (outer, "load_registered_closed_archive"), (outer.storage, "prepare_registered_volume"),
            (outer.controls, "prepare_owned_count_claim"), (outer.transport, "read_named_keychain")):
        monkeypatch.setattr(module, name, lambda *a, **k: calls.append("FORBIDDEN_SOURCE_OR_IO"))
    with pytest.raises(outer.source_scope.CountSourceAuthorityRefusal, match="count_source_prior_run_unresolved"):
        if route == "CLI":
            outer._run_cli(outer.argparse.Namespace(command="run_registered", runtime_head="c" * 40,
                actual_remote="b" * 40))
        elif route == "round":
            outer.run_registered(tmp_path, runtime_head="c" * 40, actual_remote="b" * 40,
                complete_code_manifest={}, archive_code_manifest={})
        else:
            with outer._prepare_registered_source_lease(object(), object(), root=tmp_path,
                    runtime_head="c" * 40, actual_remote="b" * 40, complete_code_manifest={}):
                pytest.fail("unresolved prior operation yielded source lease")
    assert calls == []


def _fabricated_blocked_hold(h, monkeypatch):
    h.block_negative = True
    fail_after_first_genuine_observation(h, monkeypatch)
    monkeypatch.setattr(outer, "_retain_failed_process", lambda: (_ for _ in ()).throw(HoldingTestSentinel()))
    with pytest.raises(HoldingTestSentinel): h.run()
    return outer._PRESERVATION_HOLD[h.op]


def test_prehold_diagnostics_classify_original_without_private_text_or_failed_guard(fabricated_outer_run, monkeypatch):
    h = fabricated_outer_run
    held = _fabricated_blocked_hold(h, monkeypatch)
    # A later cleanup error cannot replace the very first capture error.
    outer._preserve_failed_chunk(h.op, h.volume, ValueError("LATER_PRIVATE_ERROR"))
    detail = outer._hold_diagnostics(h.op)
    assert outer._PRESERVATION_HOLD[h.op][4] is held[4]
    assert detail["original_failure"] == {"availability": "available", "fixed_diagnostic": {
        "category": "unknown_local_error", "errno_name": None, "contract_code": None}}
    assert detail["accounting"]["availability"] == "unavailable"  # Toy policy is not the actual frozen baseline.
    assert all(value is None for name, value in detail["accounting"].items()
        if name not in {"availability", "actual_START_or_HTTP_observation"})
    text = canonical_json(detail)
    assert "PRIVATE_EXCEPTION_SENTINEL" not in text and "LATER_PRIVATE_ERROR" not in text
    assert h.failed_source_checks == 0 and len(h.key_calls) == len(h.wire_calls) == 1
    assert h.op in transport._FAILED and outer._requires_process_hold()


def test_prehold_pure_accounting_authenticates_full_original_reservations(fabricated_outer_run, monkeypatch):
    h = fabricated_outer_run; _fabricated_blocked_hold(h, monkeypatch)
    # Explicit TOY-profile seam: genuine pure budget/journal/ticket identities remain required.
    profile = tuple(getattr(outer.research_budget, name) for name in ("PRIOR_STARTS", "PRIOR_CHARGED_BYTES",
        "MAXIMUM_CUMULATIVE_STARTS", "MAXIMUM_CUMULATIVE_BYTES", "MAXIMUM_RESPONSE_BYTES"))
    monkeypatch.setattr(outer, "_HOLD_BASELINE", profile)
    before = h.budget._state
    detail = outer._hold_accounting(h.op)
    assert detail["availability"] == "authenticated_original_pure_journal"
    assert detail["new_START_reservations"] == len(before[1]) == 2
    assert detail["cumulative_START_reservations_upper_bound"] == profile[0] + 2
    assert detail["outstanding_full_page_bytes"] == 2 * profile[4]
    assert detail["cumulative_charged_plus_reserved_bytes"] == profile[1] + 2 * profile[4]
    assert detail["actual_START_or_HTTP_observation"] is False
    assert h.budget._state is before and h.failed_source_checks == 0
    assert outer.accounting.settled_chunk_accounting(h.budget)[3] == ()
    assert outer._requires_process_hold() and outer._TERMINALS == {}
    ticket = before[1][0]; original = outer.accounting._TICKETS[ticket]
    outer.accounting._TICKETS[ticket] = tuple(list(original))
    corrupted = outer._hold_accounting(h.op)
    assert corrupted["availability"] == "unavailable" and corrupted["new_START_reservations"] is None
    assert corrupted["outstanding_full_page_bytes"] is None


def test_prehold_projection_retains_distinct_permanent_negative_floor(monkeypatch):
    from test_short_interest_count_durable_budget import support
    ledger, exposed, plan = support.genuine_exposure_plan(monkeypatch)
    monkeypatch.setattr(outer.accounting, "_EXPECTED_SOURCE_PROFILE", outer.accounting._source_profile())
    budget = outer.accounting.open_durable_count_budget(plan)
    budget.reserve_start_slot(plan.chunk_positions(1)[0])
    # Explicit operation-authentication seam only: the plan, original budget,
    # ticket and append-issued journal are genuine pure fabricated factories.
    operation = object(); op = [None] * 14
    op[0], op[1], op[2], op[3], op[4] = operation, budget, plan, budget._anchor[3], 1
    monkeypatch.setattr(outer, "_failed_original_state", lambda value: (tuple(op), None))
    profile = plan.budget_profile()
    monkeypatch.setattr(outer, "_HOLD_BASELINE", (profile["known_baseline_START_debits"],
        profile["known_baseline_charged_bytes"], profile["maximum_cumulative_STARTs"],
        profile["maximum_cumulative_bytes"], profile["maximum_response_bytes"]))
    before = budget._state
    outer.accounting._FAILED.add(budget)
    report = outer._hold_accounting(operation)
    assert report["availability"] == "authenticated_original_pure_journal"
    assert report["permanent_unknown_START_upper_debits"] == 8
    assert report["permanent_unknown_byte_debits"] == 16777216
    assert report["cumulative_START_reservations_upper_bound"] == profile["initial_START_upper_bound"] + 1
    assert report["cumulative_charged_plus_reserved_bytes"] == profile["initial_byte_upper_bound"] + 2097152
    assert report["actual_START_or_HTTP_observation"] is False and budget._state is before


def test_prehold_negative_codes_require_original_registry_identity_and_literal_catalogue(fabricated_outer_run, monkeypatch):
    h = fabricated_outer_run; _fabricated_blocked_hold(h, monkeypatch)
    from scripts import short_interest_count_negative_custody as real_negative
    monkeypatch.setattr(outer, "negative", real_negative)
    # Explicit fabricated private-registry issuer seam; no native/file/source callback is invoked.
    lease = object.__new__(real_negative.OriginalPreservationLease)
    op = transport._OPERATIONS[h.op][0]
    anchor = (lease, h.op, op, h.volume, None, None, None, None, None, None, outer._thread.RLock())
    lease._anchor = lease._identity = anchor
    fixed = {"category": "local_contract_refusal", "contract_code": "negative_source_catalogue_changed", "errno_name": None}
    state = (), (), (fixed,)
    monkeypatch.setattr(real_negative, "_LEASES", {lease: anchor})
    monkeypatch.setattr(real_negative, "_STATES", {lease: state})
    monkeypatch.setattr(real_negative, "_STATE_PINS", {lease: state})
    outer._PRESERVATION_LEASES[h.op] = lease, op, h.volume, object()
    detail = outer._hold_diagnostics(h.op)["preservation_failures"]
    assert detail["availability"] == "available" and detail["negative_registry_authenticated"] is True
    assert detail["fixed_diagnostics"] == [fixed]
    real_negative._STATES[lease] = tuple(list(state))
    detail = outer._hold_diagnostics(h.op)["preservation_failures"]
    assert detail["availability"] == "available_partial" and detail["negative_registry_authenticated"] is False
    assert detail["fixed_diagnostics"] == []
    real_negative._STATES[lease] = state
    state[2][0]["contract_code"] = "PRIVATE_UNREGISTERED_PATH_TOKEN"
    detail = outer._hold_diagnostics(h.op)
    assert detail["preservation_failures"]["negative_registry_authenticated"] is False
    assert "PRIVATE_UNREGISTERED_PATH_TOKEN" not in canonical_json(detail)


@pytest.mark.parametrize("value", [
    {"category": "PRIVATE", "errno_name": None, "contract_code": None},
    {"category": "local_os_error", "errno_name": "PRIVATE", "contract_code": None},
    {"category": "local_contract_refusal", "errno_name": None, "contract_code": "PRIVATE"},
    {"category": "unknown_local_error", "errno_name": None, "contract_code": None, "private": "PRIVATE"},
])
def test_hold_projection_refuses_dynamic_fields_instead_of_serializing_them(value):
    with pytest.raises(outer.DurableCountCaptureRefusal): outer._fixed_hold_diagnostic(value)


def test_preservation_failure_diagnostics_are_bounded_and_original_failures_are_recorded(fabricated_outer_run, monkeypatch):
    h = fabricated_outer_run
    h.fail_final = True
    original = h.negative.finalize_failed_chunk
    def failed_final(lease):
        original(lease)
        raise outer.DurableCountCaptureRefusal("REFUSED: durable_capture_preservation_changed")
    h.negative.finalize_failed_chunk = failed_final
    fail_after_first_genuine_observation(h, monkeypatch)
    monkeypatch.setattr(outer, "_retain_failed_process", lambda: (_ for _ in ()).throw(HoldingTestSentinel()))
    with pytest.raises(HoldingTestSentinel): h.run()
    observed = outer._PRESERVATION_FAILURES[h.op]
    assert len(observed) == 1 and dict(observed[0])["contract_code"] == "durable_capture_preservation_changed"
    for code in sorted(outer._CODES):
        outer._remember_preservation_failure(h.op, outer.DurableCountCaptureRefusal("REFUSED: " + code))
    assert len(outer._PRESERVATION_FAILURES[h.op]) == 16
    assert outer._PRESERVATION_FAILURES[h.op] is outer._PRESERVATION_FAILURE_ORIGINS[h.op]
    assert h.op in transport._FAILED and outer._requires_process_hold() and h.final_calls == [True]


def test_pure_contribution_history_never_reopens_expired_reader_and_partial_plan_cannot_form_union(fabricated_outer_run, monkeypatch):
    h = fabricated_outer_run; h.run(); h.tick += 4000
    def expired(*args): raise AssertionError("EXPIRED_SOURCE_READER_MUST_NOT_BE_CALLED")
    monkeypatch.setattr(outer.reader, "closed_count_chunk_accounting", expired)
    monkeypatch.setattr(outer, "terminal_chunk_binding", expired)
    contributions = outer._original_settled_contributions(h.budget)
    assert len(contributions) == 1 < len(h.plan._parts[3])
    report = contributions[0].public_summary()
    assert report["authority"]["ready_for_backtest"] is False and report["authority"]["source_admitted"] is False
    with pytest.raises(outer.transport_union.CountTransportUnionRefusal, match="transport_union_incomplete"):
        outer.transport_union.seal_count_transport_union(h.plan._parts[1], h.plan, contributions, h.budget)


def test_operator_failure_preserves_prior_original_contribution_and_pure_journal(fabricated_outer_run, monkeypatch):
    h = fabricated_outer_run; h.run()
    before = outer.accounting.settled_chunk_accounting(h.budget)
    original = outer._original_settled_contributions(h.budget)
    transport._latch(h.op)
    with pytest.raises(outer.accounting.DurableCountBudgetRefusal): h.budget.public_summary()
    assert outer.accounting.settled_chunk_accounting(h.budget) is before
    assert outer._original_settled_contributions(h.budget) is original
    assert original[0].public_summary()["authority"]["source_admitted"] is False


@pytest.mark.parametrize("stage", ["claim", "START"])
def test_zero_observation_failure_requires_original_final_negative_marker_before_exit(fabricated_outer_run, monkeypatch, stage):
    h = fabricated_outer_run
    if stage == "claim":
        @contextmanager
        def refuse(*args, **kwargs):
            raise RuntimeError("FABRICATED_CLAIM_PARTIAL_PUBLICATION")
            yield
        h.controls.prepare_owned_count_claim = refuse
    else:
        def refuse(*args): raise RuntimeError("FABRICATED_START_PARTIAL_PUBLICATION")
        monkeypatch.setattr(outer, "_publish_attempt", refuse)
    with pytest.raises(RuntimeError): h.run()
    assert h.wire_calls == h.key_calls == [] and h.preservation_calls == []
    assert h.final_marker and h.final_calls == [True]
    assert h.events.index("negative-final-preservation-marker-only") < h.events.index("original-volume-exits")
    report = outer._negative_summaries()[0]
    assert report["final_negative_manifest_issued"] is True and report["source_or_process_closure_claimed"] is False
    assert not outer._requires_process_hold()


def test_failed_final_negative_marker_can_never_be_retried_or_allow_exit_two(fabricated_outer_run, monkeypatch):
    h = fabricated_outer_run; h.fail_final = True; fail_after_first_genuine_observation(h, monkeypatch)
    holds = []
    def hold(): holds.append((h.volume_closed, h.source_closed)); raise HoldingTestSentinel()
    monkeypatch.setattr(outer, "_retain_failed_process", hold)
    with pytest.raises(HoldingTestSentinel): h.run()
    assert holds[0] == (False, False) and h.final_calls == [True] and not h.final_marker
    assert outer._requires_process_hold() and h.preservation.fd_open and outer._TERMINALS == {}


def test_negative_report_uses_original_live_profile_after_authority_function_changes(fabricated_outer_run, monkeypatch):
    h = fabricated_outer_run
    original_publish = outer._publish_attempt
    def publish(*args):
        observed = original_publish(*args)
        h.negative.authority = lambda: (_ for _ in ()).throw(AssertionError("CHANGED_AUTHORITY_MUST_NOT_RUN"))
        raise RuntimeError("FABRICATED_LATE_QUALIFICATION_FAILURE")
    monkeypatch.setattr(outer, "_publish_attempt", publish)
    with pytest.raises(RuntimeError, match="FABRICATED_LATE_QUALIFICATION_FAILURE"): h.run()
    assert h.final_marker and not outer._requires_process_hold()
    assert outer._negative_summaries()[0]["authority"]["source_admitted"] is False


def test_drain_revisits_original_result_after_inflight_pop_before_observation_mint(fabricated_outer_run, monkeypatch):
    h = fabricated_outer_run
    h.preservation = h.negative.prepare_original_preservation_lease(h.op, h.volume)
    outer._PRESERVATION_LEASES[h.op] = h.preservation, transport.operation_binding(h.op), h.volume, object()
    outer._PRESERVATION_PROFILES[h.op] = tuple(h.negative.authority().items())
    ticket = h.tickets[0]; h.op.authorize_start_batch((ticket,))
    gap, release = threading.Event(), threading.Event(); original_clock = transport._clock
    def delayed_clock():
        gap.set(); assert release.wait(timeout=5); return original_clock()
    monkeypatch.setattr(transport, "_clock", delayed_clock)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(h.op.dispatch, ticket, h.claim, h.starts[ticket]); assert gap.wait(timeout=5)
        assert not transport._OPERATIONS[h.op][1][2] and transport._OPERATIONS[h.op][1][3] == ()
        timer = threading.Timer(.1, release.set); timer.start()
        try: report = outer._preserve_failed_chunk(h.op, h.volume, RuntimeError("FABRICATED_LOCAL_FAILURE_DURING_MINT_GAP"))
        finally: release.set(); timer.join(timeout=5)
        returned = future.result(timeout=5)
    assert type(returned) is transport.UnqualifiedHttpObservation
    assert report["pending_already_started_attempts"] == 0 and report["requires_process_hold"] is False
    assert h.preserved == [returned] and h.final_calls == [True] and h.preservation.fd_open


@pytest.fixture
def batched_filesystem_io(operation, monkeypatch):
    """Real fresh dirs/OwnedOutput FDs and original operator/ticket factories.

    Main/source/native/control sealing/wire are explicitly fabricated. No
    provider, source artifact, image or native flag operation is exercised.
    """
    h = operation; h.owner = threading.get_ident(); h.events, h.created = [], []; h.refresh_calls.clear()
    h.base = h.coordinator.source_lease_binding(h.lease)[11]
    h.base.mkdir(parents=True, mode=0o700)
    for name in ("starts", "received", "responses"): (h.base / name).mkdir(mode=0o700)
    outer._DIRECTORIES[h.op] = tuple((path, outer._directory_stamp(path.lstat()))
        for path in (h.base, h.base / "starts", h.base / "received", h.base / "responses"))
    monkeypatch.setattr(outer, "source_lease_binding", h.coordinator.source_lease_binding)
    monkeypatch.setattr(outer, "_source_boundary", lambda lease: h.coordinator.source_lease_live_binding(lease))
    monkeypatch.setattr(transport, "_control_volume_binding", lambda *a, **k: None)  # Explicit fake live volume.
    for ticket in h.tickets: transport._START_PERMISSIONS.pop(ticket, None)
    transport._REMOTE_BATCHES[h.op] = ()
    original_reserve = type(h.budget).reserve_start_slot
    preissued = {outer.accounting.ticket_binding(ticket)[5]: ticket for ticket in h.tickets}
    def reserve(self, position):
        assert threading.get_ident() == h.owner
        h.events.append(("reserve", position, threading.get_ident()))
        if position in preissued: return preissued.pop(position)
        return original_reserve(self, position)
    monkeypatch.setattr(type(h.budget), "reserve_start_slot", reserve)
    def new_directory(operation, path):
        assert operation is h.op and threading.get_ident() == h.owner
        h.events.append(("mkdir", path, threading.get_ident())); h.created.append(path)
        path.mkdir(mode=0o700)
        outer._DIRECTORIES[h.op] = (*outer._DIRECTORIES[h.op], (path, outer._directory_stamp(path.lstat())))
        return path
    monkeypatch.setattr(outer, "_new_directory", new_directory)
    @contextmanager
    def start(owned, operation, ticket, claim, *, boundary):
        assert operation is h.op and claim is h.claim and threading.get_ident() != h.owner
        boundary(); h.events.append(("START", ticket, threading.get_ident()))
        if ticket not in h.starts:
            bound = outer.accounting.ticket_binding(ticket); cap = type(next(iter(h.starts.values())))()
            h.start_bindings[cap] = (cap, h.op, ticket, h.claim, hash_payload([bound[9], "START"]),
                bound[8], transport.operation_binding(h.op)[5], h.claims[h.claim][6],
                "2026-10-27T00:00:00Z", None, None, object())
            h.starts[ticket] = cap
        yield h.starts[ticket]
    @contextmanager
    def received(owned, operation, observed, *, boundary):
        boundary(); bound = transport.http_observation_binding(observed)
        h.events.append(("received", bound[2], threading.get_ident()))
        cap = h.controls.CountReceived()
        h.received[cap] = cap, h.op, bound[2], observed, h.claim, bound[4], hash_payload([bound[14], "received"]), None, None, bound[12], bound[7], object()
        yield cap
    @contextmanager
    def response(owned, *, ticket, observation, boundary):
        boundary(); observed = transport.http_observation_binding(observation)
        h.events.append(("pair", ticket, threading.get_ident()))
        cap = h.responses.CountResponseCustody()
        h.response_bindings[cap] = (cap, h.op, ticket, observation, h.claim, observed[4],
            hash_bytes(observed[10]), len(observed[10]), "9" * 64, None, None, object(), object())
        yield cap
    h.controls.prepare_owned_count_start = start; h.controls.prepare_owned_count_received = received
    h.responses.prepare_owned_count_response = response
    monkeypatch.setattr(outer, "controls", h.controls); monkeypatch.setattr(outer, "responses", h.responses)
    h.schedule = lambda: outer._schedule_chunk_attempts(h.op, h.budget, h.claim)
    return h


def test_exact_remote_roster_precedes_original_worker_STARTs_and_Main_owns_budget_dirs(batched_filesystem_io, monkeypatch):
    h = batched_filesystem_io; entered = threading.Barrier(len(h.tickets)); original_open = h.opener.open
    def open_wire(*args, **kwargs):
        h.events.append(("wire-enter", threading.get_ident())); entered.wait(timeout=5)
        return original_open(*args, **kwargs)
    monkeypatch.setattr(h.opener, "open", open_wire)
    h.schedule()
    assert h.refresh_calls == [h.tickets]
    assert len(h.response_bindings) == len(h.received) == len(h.tickets)
    assert all(row[-1] == h.owner for row in h.events if row[0] in ("reserve", "mkdir"))
    assert all(row[-1] != h.owner for row in h.events if row[0] in ("START", "received", "pair"))
    first_START = next(index for index, row in enumerate(h.events) if row[0] == "START")
    assert sum(row[0] == "reserve" for row in h.events[:first_START]) == len(h.tickets)
    assert sum(row[0] == "mkdir" for row in h.events[:first_START]) == 2 * len(h.tickets)
    first_pair = next(index for index, row in enumerate(h.events) if row[0] == "pair")
    assert sum(row[0] == "received" for row in h.events[:first_pair]) == len(h.tickets)
    assert not outer._WORKER_RETAINED


def test_concurrent_original_OwnedOutput_directories_have_private_worker_FDs(batched_filesystem_io, monkeypatch):
    h = batched_filesystem_io; barrier = threading.Barrier(len(h.tickets)); live = []
    original_start = h.controls.prepare_owned_count_start
    @contextmanager
    def start(owned, *args, **kwargs):
        with original_start(owned, *args, **kwargs) as cap:
            fd = owned._anchor[2]; info = os.fstat(fd)
            live.append((fd, info.st_dev, info.st_ino)); barrier.wait(timeout=5)
            yield cap
    monkeypatch.setattr(h.controls, "prepare_owned_count_start", start)
    h.schedule()
    assert len(live) == len({row[0] for row in live}) == len({row[1:] for row in live}) == len(h.tickets)


def test_missing_original_remote_permission_has_no_worker_inode_or_wire(batched_filesystem_io):
    h = batched_filesystem_io
    with pytest.raises(transport.CountTransportRefusal, match="START_permission_required"):
        outer._prepare_attempt_slot(h.op, h.tickets[0], h.claim)
    assert h.created == [] and h.key_calls == h.wire_calls == []


def test_original_worker_slot_cannot_be_cloned_or_replayed(batched_filesystem_io):
    h = batched_filesystem_io; h.op.authorize_start_batch((h.tickets[0],))
    slot = outer._prepare_attempt_slot(h.op, h.tickets[0], h.claim)
    with pytest.raises(outer.DurableCountCaptureRefusal): outer._attempt_slot(tuple(list(slot)))
    observed, = outer._run_worker_stage(h.op, (slot,), outer._receive_worker)
    assert type(observed) is transport.HttpObservation
    with pytest.raises(outer.DurableCountCaptureRefusal): outer._receive_worker(slot)
    assert len(h.wire_calls) == len(h.key_calls) == 1


def test_worker_control_failure_joins_all_accepted_wire_and_retains_original_bytes(batched_filesystem_io, monkeypatch):
    h = batched_filesystem_io; entered = threading.Barrier(len(h.tickets)); original_open = h.opener.open
    def open_wire(*args, **kwargs): entered.wait(timeout=5); return original_open(*args, **kwargs)
    monkeypatch.setattr(h.opener, "open", open_wire)
    original_received = h.controls.prepare_owned_count_received
    @contextmanager
    def received(owned, operation, observed, **kwargs):
        if transport.http_observation_binding(observed)[2] is h.tickets[0]:
            raise RuntimeError("FABRICATED_RECEIPT_FAILURE")
        with original_received(owned, operation, observed, **kwargs) as cap: yield cap
    monkeypatch.setattr(h.controls, "prepare_owned_count_received", received)
    with pytest.raises((RuntimeError, transport.CountTransportRefusal)): h.schedule()
    assert h.op in transport._FAILED and len(transport._OPERATIONS[h.op][1][1]) == 2
    for original in tuple(transport._OBSERVATIONS.values()):
        if original[1] is h.op: transport.downgrade_http_observation_for_preservation(original[0])
    rows = [transport.drained_http_observation_binding(cap) for cap in transport._DRAINED
        if transport._DRAINED[cap][1] is h.op]
    assert {id(row[2]) for row in rows} == {id(ticket) for ticket in h.tickets}
    assert all(row[10] == h.raw for row in rows)
    assert all(future.done() for future in outer._WORKER_RETAINED[h.op][1])
    assert not any(path.parent == h.base / "responses" for path in h.created)
    assert len(h.key_calls) == len(h.wire_calls) == 2 and not outer._TERMINALS


def test_OPEN_retry_waits_original_backoff_and_never_creates_empty_response_dir(batched_filesystem_io, monkeypatch):
    h = batched_filesystem_io; original_open = h.opener.open; lock = threading.Lock(); count = [0]; sleeps = []
    def open_wire(*args, **kwargs):
        with lock: count[0] += 1; number = count[0]
        if number == 1:
            raise transport.wire.RecoveryTransportFailure("network_failure", phase="open", failure_class="timeout", retryable=True)
        return original_open(*args, **kwargs)
    def wait(seconds): sleeps.append(seconds); h.tick += seconds
    monkeypatch.setattr(h.opener, "open", open_wire); monkeypatch.setattr(outer.time, "sleep", wait)
    h.schedule()
    original = transport._OPERATIONS[h.op][1]
    observed = [transport.http_observation_binding(obs) for obs in original[3]]
    negative = next(row for row in observed if row[9] is None)
    failed_ordinal = outer.accounting.ticket_binding(negative[2])[4]
    assert h.base / "responses" / f"{failed_ordinal:06d}" not in h.created
    assert len([path for path in h.created if path.parent == h.base / "responses"]) == len(h.tickets)
    assert len(h.refresh_calls) == 2 and h.refresh_calls[0] == h.tickets and len(h.refresh_calls[1]) == 1
    assert sleeps == [2] and len(original[1]) == len(observed) == 3
    assert h.budget.public_summary()["new_START_reservations"] == 3


def test_stage_runs_eight_independent_workers_and_rejects_ninth_before_submit(operation, monkeypatch):
    h = operation; entered = threading.Barrier(8); finished = []
    def worker(slot): entered.wait(timeout=5); finished.append(slot); return slot
    monkeypatch.setattr(outer, "_receive_worker", worker)
    assert outer._run_worker_stage(h.op, tuple(range(8)), worker) == tuple(range(8))
    assert sorted(finished) == list(range(8))
    with pytest.raises(outer.DurableCountCaptureRefusal): outer._run_worker_stage(h.op, tuple(range(9)), worker)
    assert len(finished) == 8


def test_stage_joins_other_accepted_worker_after_first_error_and_blocks_followup(operation, monkeypatch):
    h = operation; entered, release = threading.Barrier(3), threading.Event(); exited = []
    def worker(slot):
        entered.wait(timeout=5)
        if slot == 0:
            transport._latch(h.op); release.set(); raise RuntimeError("FABRICATED_STAGE_FAILURE")
        assert release.wait(timeout=5); exited.append(slot); return slot
    monkeypatch.setattr(outer, "_receive_worker", worker)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(outer._run_worker_stage, h.op, (0, 1), worker)
        entered.wait(timeout=5)
        with pytest.raises(RuntimeError, match="FABRICATED_STAGE_FAILURE"): future.result(timeout=5)
    assert exited == [1] and h.op in transport._FAILED
    assert all(item.done() for item in outer._WORKER_RETAINED[h.op][1])
    with pytest.raises(outer.accounting.DurableCountBudgetRefusal): h.budget.reserve_start_slot(h.plan.chunk_positions(1)[0])


def test_outer_batched_failure_drains_both_wire_outcomes_before_negative_marker_and_teardown(fabricated_outer_run, monkeypatch):
    h = fabricated_outer_run; monkeypatch.setattr(outer, "_batch_width", lambda: 2)
    entered, release = threading.Barrier(2), threading.Event(); local = threading.local()
    original_open = h.opener.open
    def opened(*args, **kwargs):
        entered.wait(timeout=5)
        if local.ticket is h.tickets[1]: assert release.wait(timeout=5)
        return original_open(*args, **kwargs)
    monkeypatch.setattr(h.opener, "open", opened)
    def publish(operation, ticket, claim):
        local.ticket = ticket
        observed = operation.dispatch(ticket, claim, h.starts[ticket])
        h.events.append("accepted-wire-outcome-" + str(h.tickets.index(ticket)))
        if ticket is h.tickets[0]: raise RuntimeError("FABRICATED_BATCHED_LOCAL_FAILURE")
        return observed  # Original dispatcher returns a distinct unqualified opaque result after the latch.
    monkeypatch.setattr(outer, "_publish_attempt", publish)
    def release_after_latch():
        for unused in range(500):
            if h.op in transport._FAILED: release.set(); return
            release.wait(.01)
        release.set()
    releaser = threading.Thread(target=release_after_latch); releaser.start()
    try:
        with pytest.raises(RuntimeError, match="FABRICATED_BATCHED_LOCAL_FAILURE"): h.run()
    finally: release.set(); releaser.join(timeout=5)
    assert len(h.preserved) == len(h.wire_calls) == len(h.key_calls) == 2
    assert all(transport.drained_http_observation_binding(value)[10] == h.raw for value in h.preserved)
    marker = h.events.index("negative-final-preservation-marker-only")
    assert all(h.events.index("accepted-wire-outcome-" + str(number)) < marker for number in range(2))
    assert marker < h.events.index("original-volume-exits") < h.events.index("original-source-code-exits")
    assert h.final_marker and h.preservation.fd_open and not outer._requires_process_hold()
    assert h.failed_source_checks == 0 and outer._TERMINALS == {}
    assert outer.accounting.settled_chunk_accounting(h.budget)[3] == ()
