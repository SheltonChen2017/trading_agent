"""Outer authority tests; original toy archive, explicit code/storage seams.

These tests create no actual image, native flags, credentials or provider
request. Archive tests execute the old real source-held toy producer/closures.
Other tests name their fabricated source/code/control/volume boundaries and
do not establish actual-domain durability or source readiness.
"""
from contextlib import contextmanager
from types import SimpleNamespace
import os

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
        def refresh(self): h.events.append("current-root+matching-remote-check")
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
    for ticket in h.tickets:
        got, pair = h.receive(h.op.dispatch(ticket, h.claim, h.starts[ticket])); ordinal = ticket.public_summary()["reservation_ordinal"]
        start = h.starts[ticket]; old = list(h.start_bindings[start]); old[9] = origin(base / "starts" / f"{ordinal:06d}", "START.spent.json", b"START")
        h.start_bindings[start] = tuple(old)
        old = list(h.received[got]); old[7] = origin(base / "received" / f"{ordinal:06d}", "received.private.json", b"RECEIVED")
        h.received[got] = tuple(old)
        old = list(h.response_bindings[pair]); old[9] = (1, 2, 3, 0o600, 1, len(h.raw), 7, 8, 2)
        old[10] = (1, 4, 3, 0o600, 1, 9, 7, 8, 2); h.response_bindings[pair] = tuple(old)
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
    monkeypatch.setattr(outer, "registered", lambda: None)
    monkeypatch.setattr(outer, "RUN_PROTOCOL_SHA256", "a" * 64)
    source = h.coordinator.source_lease_binding(h.lease)
    monkeypatch.setattr(outer, "source_lease_binding", lambda lease: source)
    def live(lease):
        assert not h.source_closed and lease is h.lease; return source
    def terminal(lease):
        assert h.source_closed and lease is h.lease; return source
    monkeypatch.setattr(outer, "source_lease_live_binding", live)
    monkeypatch.setattr(outer, "source_lease_terminal_binding", terminal)
    monkeypatch.setattr(outer, "_source_boundary", lambda lease: terminal(lease) if h.source_closed else live(lease))
    @contextmanager
    def source_context(*args, **kwargs):
        h.events.append("source-code-enter"); yield h.lease
        h.events.append("original-source-code-exits"); h.source_closed = True; h.live = False
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
        h.events.append("volume-enter"); yield h.volume
        h.events.append("original-volume-exits"); h.volume_closed = True
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
    def claim(*args, **kwargs): yield h.claim
    @contextmanager
    def final(owned, operation, candidate, *, role, boundary):
        raw = transport._final_control_payload(operation, candidate, role)
        value = object(); origin = (None, None, None, role, raw, hash_bytes(raw), None, None, None, None, None, None, None, None, None)
        h.finals[value] = value, operation, role, hash_bytes(raw), origin, None, candidate, object()
        yield value
    h.controls.prepare_owned_count_claim, h.controls.prepare_owned_count_final_control = claim, final
    monkeypatch.setattr(outer, "controls", h.controls)
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
    bound = outer.reader.closed_count_chunk_accounting(value)
    assert bound[0] is h.budget.budget_identity and bound[1] is h.plan and bound[3] == h.tickets
    assert h.budget.public_summary()["current_chunk"] == 2
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
