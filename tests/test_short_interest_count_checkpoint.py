"""Original metadata kernel with explicit fabricated Main/source/volume issuers.

No source rows, claims, HTTP, images or actual native flags. The small plan is
factory-issued; the Main facts boundary is deliberately named and fabricated.
"""
import json
import os
import socket
import stat
from types import SimpleNamespace

import pytest
pytest.importorskip("resource")
fcntl = pytest.importorskip("fcntl")

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import short_interest_count_checkpoint as checkpoint
from test_short_interest_count_negative_custody import h as source_h, isolated as source_isolated
from test_short_interest_body_receipt_custody import kernel
import test_short_interest_count_durable_budget as budget_support


REFUSALS = (checkpoint.CountCheckpointRefusal, checkpoint.primitive.BodyReceiptRefusal,
    checkpoint.primitive.immutable.ImmutableMetadataRefusal, checkpoint.primitive.cache.contract.AnchorCacheRefusal)


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    for name in ("_ROOTS", "_ISSUED", "_KEEPERS", "_KEEPER_PINS", "_DIRECTORY_PINS", "_CHUNKS"):
        monkeypatch.setattr(checkpoint, name, {})
    monkeypatch.setattr(checkpoint, "_ATTEMPTED", set())
    monkeypatch.setattr(checkpoint, "_FAILED", set())
    monkeypatch.setattr(checkpoint, "_FAILED_NONCES", set())
    monkeypatch.setattr(checkpoint, "_ROUND", None)
    def one_chunk_plan(patcher):
        ledger = budget_support.support.baseline(patcher)
        model = budget_support.budget.research_budget
        patcher.setattr(model, "POSITIONS_PER_CHUNK", 4)
        patcher.setattr(model, "MAXIMUM_CHUNKS", 1)
        patcher.setattr(model, "MAXIMUM_CUMULATIVE_STARTS", 12)
        patcher.setattr(budget_support.budget, "_EXPECTED_SOURCE_PROFILE", budget_support.budget._source_profile())
        return model.freeze_count_recovery_plan(ledger)
    monkeypatch.setattr(budget_support, "genuine_plan", one_chunk_plan)
    def denied(*args, **kwargs): raise AssertionError("no actual network")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    real_close = os.close
    try: yield
    finally:
        descriptors = {fd for root in checkpoint._ROOTS.values() for fd in root[3:5]}
        descriptors.update(fd for keeper in checkpoint._KEEPER_PINS.values() for fd in keeper[3])
        for fd in descriptors:
            try: real_close(fd)
            except OSError: pass


@pytest.fixture
def h(source_h, kernel, monkeypatch):
    """Fake typed facts issuer, LIVE native origin and C function; real files."""
    original = source_h
    monkeypatch.setattr(checkpoint.transport, "volume_for_operation", lambda op: original.volume if op is original.op else None)
    monkeypatch.setattr(checkpoint.transport, "_source_check", lambda lease: lease is original.anchor[12])
    monkeypatch.setattr(checkpoint.time, "monotonic", original.clock)
    monkeypatch.setattr(checkpoint.time, "sleep", original.clock.sleep)
    candidate, minted, cache, calls = object(), {}, {}, []
    class CountCheckpointFacts:
        __slots__ = ("_anchor", "_identity")
        def __init__(self): raise AssertionError("test original issuer required")
    def facts_binding(value):
        assert type(value) is CountCheckpointFacts
        saved = minted[value]
        assert value._anchor is value._identity is saved
        return saved
    def issue(op, supplied, role, roots=()):
        assert op is original.op and supplied is candidate and not original.failed[0]
        calls.append((role, roots))
        if role in cache: return cache[role]
        payload = {"schema": "si-count-checkpoint-descriptor-v1" if role == "chunk" else "si-count-checkpoint-round-v1",
            "phase": "PROVISIONAL_STORAGE_FACTS", "producer": {"head": "c" * 40,
                "code_manifest": [["fabricated/code.py", "a" * 64]], "code_identity_sha256": "b" * 64,
                "source_authority_sha256": "d" * 64, "operator_protocol_sha256": "e" * 64,
                "run_protocol_sha256": "f" * 64, "negative_policy_sha256": "a" * 64},
            "volume": {"mount": str(original.mount)}, "authority": checkpoint.authority()}
        if role == "round":
            payload["roots"] = [{"body_sha256": checkpoint.checkpoint_binding(cap)[6],
                "directory_pins": [{"path": path.relative_to(original.mount).as_posix(), "pin5": list(pin)}
                    for path, pin in checkpoint.checkpoint_directory_pins(cap)]} for cap in roots]
        raw = canonical_json(payload).encode()
        cap = object.__new__(CountCheckpointFacts)
        saved = cap, op, supplied, original.anchor, (object(),), raw, hash_bytes(raw), (), (), object()
        cap._anchor = cap._identity = saved; minted[cap] = saved; cache[role] = cap
        return cap
    outer = SimpleNamespace(CountCheckpointFacts=CountCheckpointFacts, checkpoint_facts_binding=facts_binding,
        checkpoint_facts=lambda op, cap: issue(op, cap, "chunk"),
        checkpoint_round_facts=lambda op, cap, roots: issue(op, cap, "round", roots))
    monkeypatch.setattr(checkpoint, "_outer", lambda: outer)
    monkeypatch.setattr(checkpoint, "CHECKPOINT_POLICY_SHA256", hash_payload(checkpoint.policy()))
    original.candidate, original.facts, original.calls = candidate, minted, calls
    original.outer, original.kernel = outer, kernel
    original.publish = lambda: checkpoint.publish_provisional_chunk_checkpoint(original.op, candidate)
    original.round = lambda: checkpoint.publish_provisional_round_checkpoint(original.op, candidate)
    return original


def test_registration_false_authority_and_independent_finite_bounds():
    value = checkpoint.policy()
    assert checkpoint.CHECKPOINT_POLICY_SHA256 == "PENDING"
    assert value["maximum_descriptor_bytes"] == 2 * 1024 ** 2
    assert value["maximum_receipt_bytes"] == 1024 and value["maximum_chunks"] == 133
    assert value["maximum_owned_FDs"] == 668 and value["maximum_transient_FDs"] == 16
    assert value["independent_metadata_audit_seconds"] == 1800
    assert all(item is False or type(item) is int and item == 0 for item in value["authority"].values())
    with pytest.raises(checkpoint.CountCheckpointRefusal, match="registration_pending"): checkpoint._registered()


def test_genuine_metadata_kernel_closes_pair_then_issues_original_root_and_pins(h):
    checkpoint.preflight_checkpoint_resources(h.op, h.volume)
    result = h.publish(); bound = checkpoint.checkpoint_binding(result)
    assert len(bound) == 12 and bound[0] is result and bound[1] is h.op and bound[2] is h.candidate
    assert bound[3] == "chunk" and bound[4] is next(iter(h.facts.values())) and bound[5] is h.origin
    assert bound[10] == "checkpoint/chunk" and len(bound[7]) == len(bound[9]) == 9
    assert len(h.kernel.calls) == 2 and h.clock.sleeps == [.25] * 8
    path = h.mount / bound[10]
    body = (path / checkpoint.primitive.BODY_NAME).read_bytes()
    receipt_raw = (path / checkpoint.primitive.RECEIPT_NAME).read_bytes(); receipt = json.loads(receipt_raw)
    assert hash_bytes(body) == bound[6] == bound[4][6] and hash_bytes(receipt_raw) == bound[8]
    assert receipt["body_bytes"] == len(body) and receipt["body_sha256"] == bound[6]
    assert receipt["source_admitted"] is receipt["budget_release_authority"] is False
    dirs = checkpoint.checkpoint_directory_pins(result)
    assert dirs is checkpoint.checkpoint_directory_pins(result) and [path for path, pin in dirs] == [path.parent, path]
    assert all(len(pin) == 5 and pin[-1] == 0o700 for path, pin in dirs)
    assert h.calls == [("chunk", ()), ("chunk", ())]
    assert checkpoint.audit_original_checkpoint_roots()["original_roots_checked"] == 1
    assert not result.public_summary()["authority"]["actual_process_EXIT0_attested"]


def test_pure_binding_and_own_metadata_audit_survive_old_source_failure_and_original_fd_close(h):
    cap = h.publish(); original = checkpoint.checkpoint_binding(cap)
    os.close(h.original_fd); h.original_fd = -1
    h.fail(); calls = len(h.active_calls), len(h.accessor_calls)
    assert checkpoint.checkpoint_binding(cap) is original
    assert checkpoint.audit_original_checkpoint_roots()["audit_context_closed"] is True
    assert (len(h.active_calls), len(h.accessor_calls)) == calls
    assert h.failed[0] and h.op in checkpoint.transport._FAILED


def test_round_index_only_after_all_original_roots_and_final_hashes_do_not_claim_exit(h):
    with pytest.raises(checkpoint.CountCheckpointRefusal, match="round_incomplete"): h.round()
    cap = h.publish(); index = h.round(); bound = checkpoint.checkpoint_binding(index)
    assert bound[3] == "round" and len(checkpoint._CHUNKS) == 1 and checkpoint._ROUND is index
    payload = json.loads(bound[4][5])
    assert payload["roots"][0]["body_sha256"] == checkpoint.checkpoint_binding(cap)[6]
    report = checkpoint.final_checkpoint_roots()
    assert report["index_raw_sha256"] == bound[6] and report["index_receipt_raw_sha256"] == bound[8]
    assert report["index_body_original9_sha256"] == hash_payload(bound[7])
    assert report["index_receipt_original9_sha256"] == hash_payload(bound[9])
    pins = [{"path": path.relative_to(h.mount).as_posix(), "pin5": list(pin)}
        for path, pin in checkpoint.checkpoint_directory_pins(index)]
    assert report["directory_pins_sha256"] == hash_payload(pins)
    assert report["producer"]["head"] == "c" * 40 and report["producer"]["run_protocol_sha256"] == "f" * 64
    assert report["authority"]["actual_process_EXIT0_attested"] is False
    assert "actual_union_sha256" not in report and len(h.kernel.calls) == 4


@pytest.mark.parametrize("existing", ["checkpoint", "checkpoint/chunk"])
def test_existing_namespace_is_never_adopted_or_reset(h, existing):
    path = h.mount / existing; path.mkdir(mode=0o700, parents=True)
    (path / "preserved").write_bytes(b"SYNTHETIC_PRESERVED")
    with pytest.raises(checkpoint.CountCheckpointRefusal, match="role_spent"): h.publish()
    assert (path / "preserved").read_bytes() == b"SYNTHETIC_PRESERVED" and not h.kernel.calls
    with pytest.raises(checkpoint.CountCheckpointRefusal, match="role_spent"): h.publish()


def test_repeated_role_and_copied_cap_cannot_mint_or_rebaseline(h):
    cap = h.publish(); calls = len(h.kernel.calls)
    with pytest.raises(checkpoint.CountCheckpointRefusal, match="role_spent"): h.publish()
    forged = object.__new__(checkpoint.ProvisionalCountCheckpoint)
    forged._anchor = forged._identity = cap._anchor
    with pytest.raises(checkpoint.CountCheckpointRefusal, match="binding_changed"): checkpoint.checkpoint_binding(forged)
    assert len(h.kernel.calls) == calls


@pytest.mark.parametrize("role", [0, 1])
@pytest.mark.parametrize("change", ["ctime", "flags", "bytes", "mode", "link", "replacement"])
def test_any_original_file9_or_bytes_change_permanently_refuses_without_reseal(h, role, change):
    cap = h.publish(); bound = checkpoint.checkpoint_binding(cap); keeper = checkpoint._KEEPERS[cap]
    name = (checkpoint.primitive.BODY_NAME, checkpoint.primitive.RECEIPT_NAME)[role]
    path = keeper[1] / name; info = path.stat(); original = path.read_bytes()
    if change == "ctime": path.chmod(0o600)
    elif change == "flags": h.kernel.flags[info.st_dev, info.st_ino] = 0
    elif change == "bytes": path.write_bytes(b"x" * len(original))
    elif change == "mode": path.chmod(0o640)
    elif change == "link": os.link(path, h.mount / "preserved-link")
    else:
        path.rename(path.with_name("preserved-original")); path.write_bytes(original); path.chmod(0o600)
    with pytest.raises(REFUSALS): checkpoint.audit_original_checkpoint_roots()
    assert cap in checkpoint._FAILED and len(h.kernel.calls) == 2
    with pytest.raises(checkpoint.CountCheckpointRefusal): checkpoint.checkpoint_binding(cap)
    assert bound[7] is cap._anchor[7] and bound[9] is cap._anchor[9]


@pytest.mark.parametrize("change", ["root_gid", "child_mode", "extra_child", "extra_file", "native", "node"])
def test_original_directory_native_and_full_membership_drift_refuse(h, monkeypatch, change):
    cap = h.publish()
    if change == "root_gid":
        real = checkpoint._dir
        # Fixed fake stat projection: no real chown or native operation.
        monkeypatch.setattr(checkpoint, "_dir", lambda info: (*real(info)[:3], real(info)[3] + 1, real(info)[4]))
    elif change == "child_mode": (h.mount / "checkpoint/chunk").chmod(0o750)
    elif change == "extra_child": (h.mount / "checkpoint/foreign").mkdir(mode=0o700)
    elif change == "extra_file": (h.mount / "checkpoint/chunk/foreign").write_bytes(b"synthetic")
    elif change == "native": h.native["fsid"] = (999, 456)
    else: monkeypatch.setattr(checkpoint.storage, "_node_pin", lambda *args: (0,) * 6)
    with pytest.raises(REFUSALS): checkpoint.audit_original_checkpoint_roots()
    assert cap in checkpoint._FAILED


def test_directory_registry_copy_cannot_become_original_pin_witness(h):
    cap = h.publish(); original = checkpoint.checkpoint_directory_pins(cap)
    checkpoint._DIRECTORY_PINS[cap] = tuple(list(original))
    with pytest.raises(checkpoint.CountCheckpointRefusal, match="binding_changed"): checkpoint.checkpoint_directory_pins(cap)
    assert original is checkpoint._KEEPER_PINS[cap][6]
    checkpoint._DIRECTORY_PINS[cap] = original
    with pytest.raises(checkpoint.CountCheckpointRefusal, match="binding_changed"): checkpoint.checkpoint_binding(cap)


@pytest.mark.parametrize("tamper", ["anchor", "keeper", "class_hash"])
def test_original_identity_cannot_be_forged_or_hash_callback_executed(h, monkeypatch, tamper):
    cap = h.publish(); callbacks = []
    if tamper == "anchor": cap._identity = tuple(list(cap._anchor))
    elif tamper == "keeper": checkpoint._KEEPERS[cap] = tuple(list(checkpoint._KEEPERS[cap]))
    else: monkeypatch.setattr(checkpoint.ProvisionalCountCheckpoint, "__hash__", lambda self: callbacks.append(True) or 1)
    with pytest.raises(checkpoint.CountCheckpointRefusal): checkpoint.checkpoint_binding(cap)
    assert not callbacks


def test_replaced_own_checker_cannot_validate_late_code_drift(h, monkeypatch):
    h.publish(); monkeypatch.setattr(checkpoint, "_check_code", lambda pins: None)
    with pytest.raises(checkpoint.CountCheckpointRefusal, match="code_changed"): checkpoint.audit_original_checkpoint_roots()


@pytest.mark.parametrize("getter", [checkpoint.checkpoint_binding, checkpoint.checkpoint_directory_pins])
@pytest.mark.parametrize("method", ["__hash__", "__eq__"])
def test_public_class_identity_rejection_has_no_callback_and_cannot_revive_cap(h, getter, method):
    cap = h.publish(); cls = type(cap); callbacks = []
    original = getattr(cls, method)
    def hostile(*args): callbacks.append(True); raise AssertionError("PRIVATE_CALLBACK")
    setattr(cls, method, hostile)
    try:
        with pytest.raises(checkpoint.CountCheckpointRefusal, match="binding_changed"): getter(cap)
    finally: setattr(cls, method, original)
    assert not callbacks
    with pytest.raises(checkpoint.CountCheckpointRefusal, match="binding_changed"): checkpoint.checkpoint_binding(cap)


@pytest.mark.parametrize("soft", [0, 16, 667, 683])
def test_fd_preflight_fails_before_any_metadata_or_claim_when_headroom_insufficient(h, monkeypatch, soft):
    monkeypatch.setattr(checkpoint.resource, "getrlimit", lambda limit: (soft, soft))
    with pytest.raises(checkpoint.CountCheckpointRefusal, match="fd_headroom"):
        checkpoint.preflight_checkpoint_resources(h.op, h.volume)
    assert not (h.mount / "checkpoint").exists() and not h.kernel.calls


@pytest.mark.parametrize("elapsed", [1800, -1, float("inf"), True])
def test_independent_audit_clock_never_extends_old_source_window(h, monkeypatch, elapsed):
    h.publish(); now = h.clock.now
    sequence = iter((now, now + elapsed if type(elapsed) is not bool else elapsed))
    monkeypatch.setattr(checkpoint.time, "monotonic", lambda: next(sequence))
    with pytest.raises(checkpoint.CountCheckpointRefusal, match="clock_refused|audit_deadline"):
        checkpoint.audit_original_checkpoint_roots()
    assert all(cap in checkpoint._FAILED for cap in checkpoint._ISSUED)


def test_hostile_failure_args_do_not_execute_or_escape():
    seen = []
    class Hostile:
        def __eq__(self, other): seen.append("eq"); raise AssertionError("private")
        def __str__(self): seen.append("str"); raise AssertionError("private")
    error = checkpoint.CountCheckpointRefusal(Hostile())
    report = checkpoint.failure_summary(error)
    assert not seen and report == {"category": "local_contract_refusal", "contract_code": None, "errno_name": None}


def test_worst_case_full9_descriptor_bound_is_below_unchanged_two_MiB(h):
    # Public fabricated lengths only; no licensed source/request payloads.
    stamp = [18446744073709551615] * 9
    files, attempts = [], []
    reserved = h.budget.reserve_start_slot(5).public_summary()
    reserved.update(reservation_ordinal=70013, source_position=81875, matrix_query_ordinal=999999999,
        chunk_number=133, lifetime_try=3)
    for number in range(1, 529):
        paths = [f"capture/{role}/{number:06d}/{name}" for role, name in
            (("starts", "START.spent.json"), ("received", "received.private.json"),
             ("responses", "attempt-body.raw"), ("responses", "attempt-receipt.private.json"))]
        files.extend({"path": path, "bytes": 2097152, "sha256": "f" * 64, "seal9": stamp} for path in paths)
        attempts.append({"reservation": reserved,
            "reservation_sha256": "b" * 64, "observation_sha256": "d" * 64, "http_invoked": True,
            "http_status": 200, "received_at": "2026-10-27T12:00:00.123456Z",
            "fixed_diagnostic": {"stage": "x" * 128, "category": "x" * 128,
                "contract_code": "x" * 128, "errno_name": "x" * 128},
            "START_path": paths[0], "received_path": paths[1], "body_path": paths[2], "receipt_path": paths[3],
            "charged_bytes": 2097152})
    for number in range(5):
        files.append({"path": "claim/claim.spent.json" if number == 0 else f"capture/final_{number}/control.private.json",
            "bytes": 2097152, "sha256": "f" * 64, "seal9": stamp})
    value = {"files": files, "attempts": attempts, "producer": {"code_manifest":
        [["scripts/" + "x" * 100 + ".py", "f" * 64] for unused in range(256)]},
        "directories": [{"path": f"capture/{role}/{number:06d}", "pin4": stamp[:4]}
            for role in ("starts", "received", "responses") for number in range(1, 529)]}
    raw = canonical_json(value).encode()
    assert 1_000_000 < len(raw) < checkpoint.MAXIMUM_BYTES == 2097152


@pytest.mark.parametrize("bad", [b"", b"x" * (2097152 + 1), b'{"phase":"complete"}', b"{", b"[]"])
def test_invalid_or_oversized_original_facts_never_create_an_inode(h, bad):
    cap = h.outer.checkpoint_facts(h.op, h.candidate); original = h.facts[cap]
    changed = (*original[:5], bad, hash_bytes(bad), *original[7:])
    cap._anchor = cap._identity = changed; h.facts[cap] = changed
    with pytest.raises((checkpoint.CountCheckpointRefusal, json.JSONDecodeError)):
        h.publish()
    assert not h.kernel.calls and not (h.mount / "checkpoint").exists()


def test_postpair_original_facts_change_cannot_issue_root(h, monkeypatch):
    real = h.outer.checkpoint_facts
    calls = []
    def changed(*args):
        cap = real(*args); calls.append(cap)
        if len(calls) == 2:
            original = h.facts[cap]
            replacement = object.__new__(h.outer.CountCheckpointFacts)
            copied = (replacement, *original[1:])
            replacement._anchor = replacement._identity = copied; h.facts[replacement] = copied
            return replacement
        return cap
    monkeypatch.setattr(h.outer, "checkpoint_facts", changed)
    with pytest.raises(checkpoint.CountCheckpointRefusal, match="original_facts_required"): h.publish()
    assert not checkpoint._ISSUED and len(h.kernel.calls) == 2
    assert set(path.name for path in (h.mount / "checkpoint/chunk").iterdir()) == {
        checkpoint.primitive.BODY_NAME, checkpoint.primitive.RECEIPT_NAME}
    with pytest.raises(checkpoint.CountCheckpointRefusal, match="role_spent"): h.publish()


def test_postseal_failure_drains_all_duplicate_fds_and_keeps_evidence(h, monkeypatch):
    real = checkpoint.primitive.BodyReceiptCustody.closed_summary
    duplicates, close_attempts = [], []
    duplicate, close = os.dup, os.close
    def dup(fd):
        result = duplicate(fd); duplicates.append(result); return result
    def closer(fd): close_attempts.append(fd); return close(fd)
    def failed(pair):
        real(pair)
        raise checkpoint.CountCheckpointRefusal("REFUSED: checkpoint_original_facts_required")
    monkeypatch.setattr(os, "dup", dup)
    monkeypatch.setattr(os, "close", closer)
    monkeypatch.setattr(checkpoint.primitive.BodyReceiptCustody, "closed_summary", failed)
    with pytest.raises(checkpoint.CountCheckpointRefusal, match="original_facts_required"): h.publish()
    # The unchanged pair also duplicates one metadata reader per original
    # file; both of its FDs and both checkpoint-owned duplicates must drain.
    assert len(duplicates) == 5 and all(fd in close_attempts for fd in duplicates[1:])
    for fd in duplicates[1:]:
        with pytest.raises(OSError): os.fstat(fd)
    assert os.fstat(duplicates[0]).st_ino == h.origin[4][1]  # Original mount dup deliberately retained.
    assert not checkpoint._ISSUED and len(h.kernel.calls) == 2
    assert (h.mount / "checkpoint/chunk" / checkpoint.primitive.BODY_NAME).exists()


def test_no_closed_pair_or_caller_true_can_be_a_checkpoint_cap(h):
    for value in (True, {}, b"complete", h.candidate):
        with pytest.raises(checkpoint.CountCheckpointRefusal, match="binding_changed"):
            checkpoint.checkpoint_binding(value)
    with pytest.raises(checkpoint.CountCheckpointRefusal, match="factory_required"):
        checkpoint.ProvisionalCountCheckpoint()


@pytest.mark.parametrize("where", ["child", "parent"])
def test_last_receipt_read_cannot_introduce_a_dominating_negative_after_catalogue_check(h, monkeypatch, where):
    read, enabled, target = os.read, [False], [None]
    def read_then_drift(fd, maximum):
        raw = read(fd, maximum)
        if enabled[0] and fd == target[0] and maximum == 1:
            enabled[0] = False
            directory = h.mount / "checkpoint" / "chunk" if where == "child" else h.mount / "checkpoint"
            (directory / "late.refused.json").write_bytes(b"SYNTHETIC_NEGATIVE")
        return raw
    monkeypatch.setattr(os, "read", read_then_drift)  # Original registered fixture code pin, before creation.
    cap = h.publish(); target[0] = checkpoint._KEEPERS[cap][3][2]; enabled[0] = True
    with pytest.raises(checkpoint.CountCheckpointRefusal, match="membership_changed"):
        checkpoint.audit_original_checkpoint_roots()
    assert cap._anchor[11] in checkpoint._FAILED_NONCES and cap in checkpoint._FAILED
    assert (h.mount / "checkpoint" / ("chunk" if where == "child" else "") / "late.refused.json").exists()
    with pytest.raises(checkpoint.CountCheckpointRefusal): checkpoint.checkpoint_binding(cap)


@pytest.mark.parametrize("change", ["earlier_body_flags", "native", "child_mode"])
def test_end_boundary_rechecks_all_original_files_native_and_directories(h, monkeypatch, change):
    read, enabled, target, bound = os.read, [False], [None], [None]
    def read_then_drift(fd, maximum):
        raw = read(fd, maximum)
        if enabled[0] and fd == target[0] and maximum == 1:
            enabled[0] = False
            if change == "earlier_body_flags": h.kernel.flags[bound[0][7][0], bound[0][7][1]] = 0
            elif change == "native": h.native["fsid"] = (999, 888)
            else: (h.mount / "checkpoint/chunk").chmod(0o750)
        return raw
    monkeypatch.setattr(os, "read", read_then_drift)
    cap = h.publish(); bound[0] = checkpoint.checkpoint_binding(cap)
    target[0] = checkpoint._KEEPERS[cap][3][2]; enabled[0] = True
    with pytest.raises(checkpoint.CountCheckpointRefusal): checkpoint.audit_original_checkpoint_roots()
    assert cap._anchor[11] in checkpoint._FAILED_NONCES and len(h.kernel.calls) == 2


def test_last_round_read_cannot_change_a_previously_audited_chunk_root(h, monkeypatch):
    read, enabled, target = os.read, [False], [None]
    def read_then_drift(fd, maximum):
        raw = read(fd, maximum)
        if enabled[0] and fd == target[0] and maximum == 1:
            enabled[0] = False
            (h.mount / "checkpoint/chunk/late.refused.json").write_bytes(b"SYNTHETIC_NEGATIVE")
        return raw
    monkeypatch.setattr(os, "read", read_then_drift)
    first = h.publish(); index = h.round()
    target[0] = checkpoint._KEEPERS[index][3][2]; enabled[0] = True
    with pytest.raises(checkpoint.CountCheckpointRefusal, match="membership_changed"):
        checkpoint.final_checkpoint_roots()
    assert first._anchor[11] in checkpoint._FAILED_NONCES
