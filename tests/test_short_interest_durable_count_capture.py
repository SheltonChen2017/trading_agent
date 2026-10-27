"""Outer authority tests; original toy archive, explicit code/storage seams.

These tests create no actual image, native flags, credentials or provider
request. Archive tests execute the old real source-held toy producer/closures.
Other tests name their fabricated source/code/control/volume boundaries and
do not establish actual-domain durability or source readiness.
"""
from contextlib import contextmanager
from types import SimpleNamespace
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
def fresh_outer_registries(monkeypatch):
    for name, value in (("_ARCHIVES", {}), ("_ARCHIVE_PLANS", {}), ("_ARCHIVE_FAILED", set()),
        ("_LEASES", {}), ("_LEASE_FAILED", set()), ("_LEASE_TERMINALS", {}), ("_LEASE_PHASES", {}),
        ("_LEASE_CLOCKS", {}), ("_RUNS", {}), ("_RUN_ORIGINS", {}), ("_TERMINAL_ORIGINS", {}),
        ("_TERMINALS", {}), ("_TERMINAL_FAILED", set()), ("_DIRECTORIES", {}), ("_PRESERVATION_HOLD", {})):
        monkeypatch.setattr(outer, name, value)
    for name, value in (("_PRESERVATION_LEASES", {}), ("_NEGATIVE_STATUS", {}), ("_NEGATIVE_ORIGINS", {}),
        ("_NEGATIVE_ATTEMPTED", set()), ("_BLOCKED_OPERATIONS", set()), ("_RETENTION_ANNOUNCED", set()),
        ("_SOURCE_BATCHES", {}), ("_SOURCE_BATCH_FAILED", set()), ("_NEGATIVE_FINAL_ATTEMPTED", set()),
        ("_PRESERVATION_PROFILES", {})):
        monkeypatch.setattr(outer, name, value)
    monkeypatch.setattr(outer, "_SETTLED_CONTRIBUTIONS", {})
    monkeypatch.setattr(outer, "_CONTRIBUTION_ORIGINS", {})
    for name, value in (("_CHECKPOINT_FACTS", {}), ("_CHECKPOINT_FACTS_FAILED", set()),
        ("_CHECKPOINT_CAPS", {}), ("_CHECKPOINT_ROUND", {}), ("_WRITTEN_CHECKPOINTS", {})):
        monkeypatch.setattr(outer, name, value)
    for name, value in (("_CONTRIBUTIONS", {}), ("_PRIVATE_PROOFS", {}), ("_CLOSED_ORIGINS", {}),
        ("_UNIONS", {}), ("_FAILED", set()), ("_UNION_FAILED", set())):
        monkeypatch.setattr(outer.transport_union, name, value)


def test_default_registration_blocks_before_archive_key_claim_native_or_provider(monkeypatch, tmp_path):
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


def test_cli_is_fixed_refusal_and_never_formats_exception_payload(capsys):
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


def test_pending_negative_preservation_barrier_survives_other_registered_hashes(monkeypatch):
    monkeypatch.setattr(outer, "SOURCE_AUTHORITY_SHA256", "a" * 64)
    monkeypatch.setattr(outer.transport, "SOURCE_AUTHORITY_SHA256", "a" * 64)
    monkeypatch.setattr(outer.transport, "PROTOCOL_SHA256", "b" * 64)
    monkeypatch.setattr(outer, "NEGATIVE_PRESERVATION_POLICY_SHA256", "c" * 64)
    monkeypatch.setattr(outer, "RUN_PROTOCOL_SHA256", hash_payload(outer.protocol()))
    with pytest.raises(outer.DurableCountCaptureRefusal, match="negative_preservation_pending"): outer.registered()


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
