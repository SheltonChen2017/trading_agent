"""Fabricated registered-operation semantics and fake C library only.

No SourceLease, HTTP, provider, source, image or actual kernel flag operation.
The stand-in transport registry is explicitly not operational issuance proof.
"""
from contextlib import contextmanager
import _thread
import errno
import json
import os
from pathlib import Path
import socket
import sys
from types import ModuleType, SimpleNamespace

import pytest
pytest.importorskip("resource")
fcntl = pytest.importorskip("fcntl")

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import short_interest_count_control_custody as control
import test_short_interest_count_durable_budget as budget_support
from test_short_interest_body_receipt_custody import kernel
from test_short_interest_new_metadata_custody import Clock

REFUSALS = (control.CountControlRefusal, control.kernel.BodyReceiptRefusal,
    control.immutable.ImmutableMetadataRefusal, control.cache.contract.AnchorCacheRefusal)


@pytest.fixture(autouse=True)
def isolated_and_no_external(monkeypatch):
    for name in ("_CAPS", "_STATES", "_SHADOWS", "_CHOICES", "_HELD", "_ISSUED", "_VOLUMES"):
        monkeypatch.setattr(control, name, {})
    for name in ("_FAILED", "_USED", "_SETTER_USED", "_SEAL_USED"):
        monkeypatch.setattr(control, name, set())
    for name, value in (("_BUDGETS", {}), ("_TICKETS", {}), ("_LOCKS", {}), ("_FAILED", set()), ("_CONSUMED", set())):
        monkeypatch.setattr(control.budget, name, value)
    def denied(*args, **kwargs): raise AssertionError("real native/network forbidden")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(control.immutable.ctypes, "CDLL", denied)


@pytest.fixture
def h(monkeypatch, tmp_path):
    plan = budget_support.genuine_plan(monkeypatch)
    coordinator = control.budget.open_durable_count_budget(plan)
    base = tmp_path / "operation"; base.mkdir(mode=0o700)
    module = ModuleType("scripts.short_interest_count_durable_transport")
    operations, candidates, observations = {}, {}, {}
    class CountCaptureOperation: pass
    class ProvisionalRootClosureCandidate: pass
    class HttpObservation: pass
    op = CountCaptureOperation(); lock = _thread.RLock()
    parts = op, coordinator, plan, coordinator.budget_identity, 1, "a" * 64, "b" * 64, tmp_path, "c" * 40, "d" * 40, plan.sha256, lock, object(), object()
    operations[op] = parts
    active, final_payload, callbacks = [True], [{"members": []}], []
    volume, volume_good = object(), [True]
    permissions_good, permission_checks = [True], []
    def operation_binding(value):
        result = operations.get(value) if type(value) is CountCaptureOperation else None
        control.require(result is not None, "count_control_operation_changed")
        return result
    def volume_binding(value, live=True):
        operation_binding(value)
        control.require(volume_good[0] is True, "count_control_operation_changed")
        return volume, op, base
    def observe(ticket, claim, start, *, raw=b'{"synthetic":true}', status=200, diagnostic=None):
        result = HttpObservation(); original = control.budget.ticket_binding(ticket)
        start_original = control.start_binding(start)
        row = result, op, ticket, claim, start, original[8], start_original[4], parts[5], True, status, raw,
        row = (*row, "application/json" if raw is not None else None, "2026-10-27T10:00:00Z", diagnostic, "f" * 64, object())
        observations[result] = row
        return result
    def observation_binding(value):
        result = observations.get(value) if type(value) is HttpObservation else None
        control.require(result is not None, "count_control_binding_changed")
        return result
    def active_operation_binding(value):
        result = operation_binding(value)
        control.require(active[0] is True, "count_control_operation_changed")
        return result
    def directory(value, role, ticket=None):
        operation_binding(value)
        if role == "claim": return base / "claim"
        if role == "start": return base / "starts" / f"{control.budget.active_ticket_binding(ticket)[4]:06d}"
        if role == "received": return base / "received" / f"{control.budget.active_ticket_binding(ticket)[4]:06d}"
        return base / ("final_" + role)
    candidate = ProvisionalRootClosureCandidate(); candidates[candidate] = object()
    def final(value, supplied, role):
        operation_binding(value)
        control.require(type(supplied) is ProvisionalRootClosureCandidate and supplied in candidates,
            "count_control_binding_changed")
        return canonical_json({"schema": "si-count-final-control-v1", "role": role, "chunk": 1,
            "operator_protocol_sha256": parts[5], "registration_sha256": parts[6], "candidate_sha256": "e" * 64,
            "payload": final_payload[0], "source_admitted": False, "budget_release_authority": False}).encode()
    module.operation_binding, module.active_operation_binding = operation_binding, active_operation_binding
    def permission_binding(value, ticket):
        # Explicit fake fixed issuer for these storage-only tests; no actual
        # source-ref witness or provider authority is supplied by this fixture.
        with lock:
            operation_binding(value)
            original = control.budget.active_ticket_binding(ticket)
            control.require(permissions_good[0] is True and original[1] is coordinator,
                "count_control_operation_changed")
            permission_checks.append(ticket)
            return value, ticket, parts, object()
    module.start_permission_binding = permission_binding
    module.volume_for_operation = lambda value: (operation_binding(value), volume)[1]
    module._control_volume_binding = volume_binding
    module.http_observation_binding, module.HttpObservation = observation_binding, HttpObservation
    module._control_directory, module._final_control_payload = directory, final
    module.ProvisionalRootClosureCandidate = ProvisionalRootClosureCandidate
    monkeypatch.setitem(sys.modules, module.__name__, module)
    import scripts
    monkeypatch.setattr(scripts, "short_interest_count_durable_transport", module, raising=False)
    clock = Clock()
    def boundary():
        assert lock._is_owned(), "shared callback escaped original operation lock"
        callbacks.append(True)
    @contextmanager
    def owned(role, ticket=None):
        path = directory(op, role, ticket)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.mkdir(mode=0o700, exist_ok=True)
        with control._OwnedOutput(path, lambda: None) as output:
            yield output
    def claim(output):
        return control.prepare_owned_count_claim(output, op, boundary=boundary, monotonic=clock, sleep=clock.sleep)
    return SimpleNamespace(op=op, parts=parts, plan=plan, budget=coordinator, base=base, module=module,
        active=active, candidate=candidate, final_payload=final_payload, clock=clock, boundary=boundary,
        owned=owned, claim=claim, callbacks=callbacks, observe=observe, volume_good=volume_good, volume=volume,
        permissions_good=permissions_good, permission_checks=permission_checks)


def closed_claim(h):
    with h.owned("claim") as owned:
        with h.claim(owned) as claim: claim.check()
    return claim


def test_claim_is_original_spent_canonical_and_authenticates_only_after_own_close(h, kernel):
    with h.owned("claim") as owned:
        with h.claim(owned) as claim:
            raw = claim.read(); parsed = json.loads(raw); observation = claim.observation()
            assert type(claim) is control.CountClaim and parsed["spent"] is True and len(raw) <= 1024
            assert raw == canonical_json(parsed).encode() and parsed["plan_sha256"] == h.plan.sha256
            assert not observation["closed"] and not parsed["dispatch_authority"]
            fd = claim._anchor[7]
        binding = control.claim_binding(claim)
        assert len(binding) == 12 and binding[:2] == (claim, h.op)
        assert binding[2] is h.budget and binding[3] is h.plan and binding[6] == hash_bytes(raw)
        assert binding[8] is claim._anchor and hash_payload(binding[9]) == observation["seal_stamp_sha256"]
    claim.check_after_close()
    assert claim.read() == raw and h.callbacks and len(kernel.calls) == 1
    with pytest.raises(OSError): os.fstat(fd)
    assert control.creator.MAXIMUM_BYTES == 1024


def test_start_binds_exact_genuine_claim_ticket_request_and_lifetime_try(h, kernel):
    claim = closed_claim(h); ticket = h.budget.reserve_start_slot(5)
    with h.owned("start", ticket) as owned:
        with control.prepare_owned_count_start(owned, h.op, ticket, claim, boundary=h.boundary,
                monotonic=h.clock, sleep=h.clock.sleep) as start:
            parsed = json.loads(start.read())
            assert parsed["spent"] is True and parsed["request_sha256"] == ticket.public_summary()["request_sha256"]
            assert parsed["lifetime_try"] == 2 and parsed["reservation_sha256"] == ticket.reservation_sha256
    binding = control.start_binding(start)
    assert len(binding) == 12 and binding[:4] == (start, h.op, ticket, claim)
    assert binding[7] == control.claim_binding(claim)[6] and binding[9] is start._anchor
    assert len(kernel.calls) == 2 and h.budget.public_summary()["new_START_reservations"] == 1


@pytest.mark.parametrize("role", ["inventory", "provisional", "closed", "manifest"])
def test_final_control_uses_genuine_candidate_internal_builder_and_distinct_scope(h, kernel, role):
    h.final_payload[0] = {"members": [{"name": "responses/00001/attempt-body.raw", "bytes": 17, "sha256": "e" * 64}]}
    with h.owned(role) as owned:
        with control.prepare_owned_count_final_control(owned, h.op, h.candidate, role=role,
                boundary=h.boundary, monotonic=h.clock, sleep=h.clock.sleep) as cap:
            assert type(cap) is control.CountFinalControl and cap.observation()["role"] == role
    binding = control.final_control_binding(cap)
    assert len(binding) == 8 and binding[0] is cap and binding[1] is h.op and binding[2] == role
    assert binding[4] is cap._anchor and binding[6] is h.candidate and binding[3] == hash_bytes(cap.read())
    assert not json.loads(cap.read())["source_admitted"] and len(kernel.calls) == 1


def test_final_metadata_can_reach_exact_new_2MiB_cap_without_changing_old_small_limit(h, kernel):
    h.final_payload[0] = {"padding": ""}
    base = len(h.module._final_control_payload(h.op, h.candidate, "inventory"))
    h.final_payload[0] = {"padding": "x" * (control.MAXIMUM_FINAL_BYTES - base)}
    with h.owned("inventory") as owned:
        with control.prepare_owned_count_final_control(owned, h.op, h.candidate, role="inventory",
                boundary=h.boundary, monotonic=h.clock, sleep=h.clock.sleep) as cap:
            assert len(cap.read()) == 2097152
    assert len(cap.read()) == 2097152 and control.creator.MAXIMUM_BYTES == 1024


@pytest.mark.parametrize("change", ["too_large", "unknown_key", "authority", "noncanonical", "NaN"])
def test_final_bounds_and_schema_fail_before_any_inode_and_spend_role(h, kernel, monkeypatch, change):
    original = h.module._final_control_payload
    def altered(op, candidate, role):
        if change == "too_large": return b"x" * (control.MAXIMUM_FINAL_BYTES + 1)
        if change == "NaN": return b'{"padding":NaN}'
        raw = original(op, candidate, role)
        if change == "noncanonical": return raw + b"\n"
        payload = json.loads(raw)
        if change == "unknown_key": payload["unknown"] = True
        if change == "authority": payload["source_admitted"] = True
        return canonical_json(payload).encode()
    monkeypatch.setattr(h.module, "_final_control_payload", altered)
    with h.owned("inventory") as owned:
        with pytest.raises(REFUSALS):
            with control.prepare_owned_count_final_control(owned, h.op, h.candidate, role="inventory",
                    boundary=h.boundary, monotonic=h.clock, sleep=h.clock.sleep): pass
        assert not tuple(owned._anchor[0].iterdir()) and not kernel.calls
        monkeypatch.setattr(h.module, "_final_control_payload", original)
        with pytest.raises(control.CountControlRefusal, match="role_spent"):
            with control.prepare_owned_count_final_control(owned, h.op, h.candidate, role="inventory",
                    boundary=h.boundary, monotonic=h.clock, sleep=h.clock.sleep): pass


def test_wrong_directory_and_existing_member_never_adopt_or_rewrite(h, kernel):
    with h.owned("inventory") as owned:
        with pytest.raises(control.CountControlRefusal, match="directory_changed"):
            with h.claim(owned): pass
        assert not tuple(owned._anchor[0].iterdir()) and not kernel.calls
    with h.owned("claim") as owned:
        with pytest.raises(control.CountControlRefusal, match="role_spent"):
            with h.claim(owned): pass


def test_partial_write_progress_and_ENOSPC_preserve_spent_role_and_existing_bytes(h, kernel, monkeypatch):
    real_write = os.write
    def partial(fd, raw):
        if len(raw) > 8: return real_write(fd, raw[:8])
        raise OSError(errno.ENOSPC, "SECRET private path")
    monkeypatch.setattr(control.os, "write", partial)
    with h.owned("claim") as owned:
        with pytest.raises(OSError) as caught:
            with h.claim(owned): pass
        assert control.failure_summary(caught.value) == {"category": "local_os_error", "errno_name": "ENOSPC", "contract_code": None}
        raw = (owned._anchor[0] / "claim.spent.json").read_bytes()
        assert raw and not kernel.calls
        with pytest.raises(control.CountControlRefusal, match="role_spent"):
            with h.claim(owned): pass
        assert (owned._anchor[0] / "claim.spent.json").read_bytes() == raw


@pytest.mark.parametrize("change", ["ctime", "flags", "state", "anchor"])
def test_postseal_refusal_is_permanent_even_after_restoration(h, kernel, change):
    with h.owned("claim") as owned:
        with pytest.raises(REFUSALS):
            with h.claim(owned) as cap:
                original, state = cap._anchor, control._STATES[cap]
                if change == "ctime": (owned._anchor[0] / "claim.spent.json").chmod(0o600)
                elif change == "flags": kernel.flags[original[8][:2]] = 0
                elif change == "state": state["last_tick"] = -1
                else: cap._anchor = tuple(list(original))
                try: cap.check()
                finally:
                    if change == "flags": kernel.flags[original[8][:2]] = original[10]
                    if change == "anchor": cap._anchor = original
        with pytest.raises(REFUSALS): control.claim_binding(cap)
        assert cap not in control._ISSUED


def test_live_completion_flag_and_copied_anchor_cannot_mint_closed_claim(h, kernel):
    with h.owned("claim") as owned:
        with pytest.raises(REFUSALS):
            with h.claim(owned) as cap:
                state = control._STATES[cap]; state["phase"] = "CLOSED"
                with pytest.raises(REFUSALS): control.claim_binding(cap)
    fake = object.__new__(control.CountClaim); fake._anchor = fake._identity = cap._anchor
    with pytest.raises(REFUSALS): control.claim_binding(fake)


def test_unique_seal_and_chosen_stamp_gap_are_not_rebaselined(h, kernel):
    with h.owned("claim") as owned:
        with pytest.raises(REFUSALS):
            with h.claim(owned) as cap: cap.seal_once()
    assert len(kernel.calls) == 1 and cap not in control._ISSUED


def test_late_negative_sibling_during_postclose_full_read_vetoes_claim(h, kernel, monkeypatch):
    real_read = control.kernel._read_original
    injected = []
    def read(origin, fd, expected, **kwargs):
        result = real_read(origin, fd, expected, **kwargs)
        if sys._getframe(1).f_code is control._audit_closed.__code__ and not injected:
            injected.append(True)
            (origin[1][0] / "negative.refused.json").write_bytes(b"FABRICATED_NEGATIVE")
        return result
    monkeypatch.setattr(control.kernel, "_read_original", read)
    with h.owned("claim") as owned:
        with pytest.raises(REFUSALS):
            with h.claim(owned) as cap: pass
        assert cap not in control._ISSUED and len(tuple(owned._anchor[0].iterdir())) == 2


def test_original_clock_rollback_and_creation_deadline_prevent_native(h, kernel):
    h.clock.hook = lambda: setattr(h.clock, "now", -1.0)
    with h.owned("claim") as owned:
        with pytest.raises(REFUSALS):
            with h.claim(owned): pass
        assert len(kernel.calls) == 1  # rollback occurs in first quiet sample after the single setter


def test_builder_source_guard_time_counts_inside_original_eight_second_window(h, kernel, monkeypatch):
    original = h.module.active_operation_binding
    def delayed(op):
        value = original(op); h.clock.now += 9; return value
    monkeypatch.setattr(h.module, "active_operation_binding", delayed)
    with h.owned("claim") as owned:
        with pytest.raises(control.CountControlRefusal, match="window_exhausted"):
            with h.claim(owned): pass
        assert not kernel.calls and not tuple(owned._anchor[0].iterdir())


def test_historical_controls_reauthenticate_after_operation_closes_but_new_role_cannot(h, kernel):
    claim = closed_claim(h); h.active[0] = False
    assert control.claim_binding(claim)[1] is h.op
    with h.owned("inventory") as owned:
        with pytest.raises(control.CountControlRefusal):
            with control.prepare_owned_count_final_control(owned, h.op, h.candidate, role="inventory",
                    boundary=h.boundary, monotonic=h.clock, sleep=h.clock.sleep): pass


def test_missing_original_remote_START_permission_refuses_before_timer_or_inode(h, kernel):
    claim = closed_claim(h); ticket = h.budget.reserve_start_slot(5)
    h.permissions_good[0] = False; before_time, before_native = h.clock.now, len(kernel.calls)
    with h.owned("start", ticket) as owned:
        with pytest.raises(control.CountControlRefusal):
            control.prepare_owned_count_start(owned, h.op, ticket, claim,
                boundary=h.boundary, monotonic=h.clock, sleep=h.clock.sleep)
        assert not tuple(owned._anchor[0].iterdir())
    assert h.clock.now == before_time and len(kernel.calls) == before_native


def test_permission_is_rechecked_at_original_context_entry_before_first_inode(h, kernel):
    claim = closed_claim(h); ticket = h.budget.reserve_start_slot(5)
    with h.owned("start", ticket) as owned:
        prepared = control.prepare_owned_count_start(owned, h.op, ticket, claim,
            boundary=h.boundary, monotonic=h.clock, sleep=h.clock.sleep)
        h.permissions_good[0] = False
        before_native = len(kernel.calls)
        with pytest.raises(control.CountControlRefusal):
            with prepared: pass
        assert not tuple(owned._anchor[0].iterdir()) and len(kernel.calls) == before_native


@pytest.mark.parametrize("status,raw", [(200, b'{"synthetic":true}'), (404, None), (None, None)])
def test_received_is_mandatory_semantic_receipt_for_positive_or_unknown_observation(h, kernel, status, raw):
    claim = closed_claim(h); ticket = h.budget.reserve_start_slot(5)
    with h.owned("start", ticket) as owned:
        with control.prepare_owned_count_start(owned, h.op, ticket, claim, boundary=h.boundary,
                monotonic=h.clock, sleep=h.clock.sleep) as start: pass
    from scripts.short_interest_recovery_transport import RecoveryTransportFailure
    detail = None if status == 200 else tuple(RecoveryTransportFailure("network_failure", phase="open",
        failure_class="connection_refused", errno_name="ECONNREFUSED", retryable=True).diagnostic().items())
    observation = h.observe(ticket, claim, start, raw=raw, status=status, diagnostic=detail)
    with h.owned("received", ticket) as owned:
        with control.prepare_owned_count_received(owned, h.op, observation, boundary=h.boundary,
                monotonic=h.clock, sleep=h.clock.sleep) as received:
            encoded = received.read(); payload = json.loads(encoded)
            assert len(encoded) <= 1024 and payload["http_status"] == status
            assert payload["body_bytes"] == (None if raw is None else len(raw))
            assert payload["body_sha256"] == (None if raw is None else hash_bytes(raw))
            assert payload["observation_sha256"] == "f" * 64 and not payload["budget_release_authority"]
    bound = control.received_binding(received)
    assert len(bound) == 12 and bound[:6] == (received, h.op, ticket, observation, claim, start)
    assert bound[7] is received._anchor and bound[6] == hash_bytes(encoded) and len(kernel.calls) == 3
    assert h.budget.public_summary()["outstanding_full_page_bytes"] == 2 * 1024 ** 2


def test_live_bool_or_reflected_observation_cannot_mint_received_control(h, kernel):
    ticket = h.budget.reserve_start_slot(5)
    for supplied in (True, {}, object.__new__(h.module.HttpObservation)):
        with h.owned("received", ticket) as owned:
            with pytest.raises(REFUSALS):
                with control.prepare_owned_count_received(owned, h.op, supplied, boundary=h.boundary,
                        monotonic=h.clock, sleep=h.clock.sleep): pass
            assert not tuple(owned._anchor[0].iterdir()) and not kernel.calls


def test_closed_control_requires_original_volume_even_on_same_named_host_directory(h, kernel):
    claim = closed_claim(h); raw = claim.read()
    h.volume_good[0] = False
    with pytest.raises(REFUSALS): control.claim_binding(claim)
    h.volume_good[0] = True
    with pytest.raises(control.CountControlRefusal, match="refused"): control.claim_binding(claim)
    assert (h.base / "claim" / "claim.spent.json").read_bytes() == raw


def test_unregistered_volume_never_creates_a_claim_inode(h, kernel):
    h.volume_good[0] = False
    with h.owned("claim") as owned:
        with pytest.raises(REFUSALS):
            with h.claim(owned): pass
        assert not kernel.calls and not tuple(owned._anchor[0].iterdir())


def test_initial_TRACKED_is_preserved(h, kernel, monkeypatch):
    real_chmod = os.fchmod
    def tracked(fd, mode):
        real_chmod(fd, mode); info = os.fstat(fd)
        kernel.flags.setdefault((info.st_dev, info.st_ino), 64)
    monkeypatch.setattr(control.os, "fchmod", tracked)
    claim = closed_claim(h)
    assert claim._anchor[9:11] == (64, 66) and kernel.calls[0][1] == 66


def test_unknown_initial_flags_refuse_without_native_rewrite(h, kernel, monkeypatch):
    real_chmod = os.fchmod
    def unknown(fd, mode):
        real_chmod(fd, mode); info = os.fstat(fd)
        kernel.flags[info.st_dev, info.st_ino] = 128
    monkeypatch.setattr(control.os, "fchmod", unknown)
    with h.owned("claim") as owned:
        with pytest.raises(control.CountControlRefusal, match="initial_flags_changed"):
            with h.claim(owned): pass
        assert not kernel.calls and (owned._anchor[0] / "claim.spent.json").is_file()


def test_postclose_descriptor_cleanup_drains_all_original_audit_FDs_on_first_error(h, kernel, monkeypatch):
    real_open, real_close = os.open, os.close
    descriptors, failed = [], []
    def open_fd(*args, **kwargs):
        fd = real_open(*args, **kwargs)
        if sys._getframe(1).f_code is control._audit_closed.__code__: descriptors.append(fd)
        return fd
    def close_fd(fd):
        real_close(fd)
        if fd in descriptors and not failed:
            failed.append(fd); raise OSError(errno.EIO, "SECRET close failure")
    monkeypatch.setattr(control.os, "open", open_fd)
    # The test wrapper forwards dir_fd unchanged; production os.open and its
    # actual capability set are never replaced by the operational factory.
    monkeypatch.setattr(control.os, "supports_dir_fd", {*os.supports_dir_fd, open_fd})
    monkeypatch.setattr(control.os, "close", close_fd)
    with h.owned("claim") as owned:
        with pytest.raises(OSError, match="SECRET"):
            with h.claim(owned) as cap: pass
        assert len(descriptors) == 3 and cap not in control._ISSUED
        for fd in descriptors:
            with pytest.raises(OSError): os.fstat(fd)
        owned.check()


def test_live_claim_binding_is_a_terminal_refusal_not_a_provisional_grant(h, kernel):
    with h.owned("claim") as owned:
        with pytest.raises(REFUSALS):
            with h.claim(owned) as cap:
                with pytest.raises(control.CountControlRefusal, match="not_closed"): control.claim_binding(cap)
        assert cap not in control._ISSUED


def test_preexisting_member_is_never_adopted_even_when_exact_name_matches(h, kernel):
    with h.owned("claim") as owned:
        path = owned._anchor[0] / "claim.spent.json"; path.write_bytes(b"PRESERVE_OLD"); path.chmod(0o600)
        with pytest.raises(control.CountControlRefusal, match="membership_changed"):
            with h.claim(owned): pass
        assert path.read_bytes() == b"PRESERVE_OLD" and not kernel.calls


def test_clock_rollback_after_creation_never_reaches_the_native_setter(h, kernel, monkeypatch):
    real_close = os.close; changed = []
    def close(fd):
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        real_close(fd)
        if flags & os.O_ACCMODE == os.O_RDWR and not changed:
            changed.append(True); h.clock.now = -1
    monkeypatch.setattr(control.os, "close", close)
    with h.owned("claim") as owned:
        with pytest.raises(REFUSALS):
            with h.claim(owned): pass
        assert not kernel.calls


def test_hostile_error_projection_never_formats_dynamic_values():
    class Hostile:
        def __str__(self): pytest.fail("secret formatting")
        def __repr__(self): pytest.fail("secret repr")
    class Error(Exception):
        def __getattribute__(self, name): pytest.fail("secret property")
    for error in (Error(), control.CountControlRefusal(Hostile()), control.CountControlRefusal("REFUSED: SECRET")):
        assert control.failure_summary(error)["contract_code"] is None
        assert "SECRET" not in canonical_json(control.failure_summary(error))


def test_full_current_policy_and_exact_role_types_refuse_and_latch(h, kernel, monkeypatch):
    claim = closed_claim(h); safe = control.authority()
    monkeypatch.setattr(control, "authority", lambda: {**safe, "dispatch_authority": True})
    with pytest.raises(control.CountControlRefusal, match="policy_changed"): control.claim_binding(claim)
    monkeypatch.setattr(control, "authority", lambda: safe)
    with pytest.raises(control.CountControlRefusal, match="refused"): control.claim_binding(claim)
    class Alias(str): pass
    monkeypatch.setattr(control, "_NAMES", ((Alias("claim"), "claim.spent.json"), *control._NAMES[1:]))
    with pytest.raises(control.CountControlRefusal, match="policy_changed"): control._policy()
