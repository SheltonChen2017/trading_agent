"""Readonly checkpoint software tests; synthetic bytes/native/registration only.

No protected actual artifacts, provider, image, credential, source claim or
native mutation is exercised. A valid fixture is not actual source readiness.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import os

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import load_short_interest_count_checkpoints as reader
from test_short_interest_count_durable_budget import genuine_plan, isolated_registries_and_no_network
from test_short_interest_count_recovery_budget import genuine_exposure_plan


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    for name, value in (("_ISSUED", {}), ("_FAILED", set()), ("_CLOSED", {}), ("_PRIVATE", {}),
            ("_DEADLINES", {}), ("_DEADLINE_LAST", {}), ("_PRODUCERS", {}), ("_PRODUCER_PINS", {})):
        monkeypatch.setattr(reader, name, value)
    monkeypatch.setattr(reader, "_RESOLUTION_PHASE", None)
    monkeypatch.setattr(reader, "_RESOLUTION_ISSUED", {})


def test_loader_operative_accounting_never_drops_the_genuine_permanent_floor(monkeypatch):
    ledger, exposure, plan = genuine_exposure_plan(monkeypatch)
    profile = plan.budget_profile()
    result = reader._operative_accounting(plan, 3, 7)
    assert result["known_baseline_START_debits"] == ledger.public_summary()["START_debits"]
    assert result["negative_exposure_sha256"] == exposure.sha256
    assert result["operative_cumulative_START_upper_bound"] == profile["initial_START_upper_bound"] + 3
    assert result["operative_cumulative_byte_upper_bound"] == profile["initial_byte_upper_bound"] + 7
    for starts, charged in ((profile["maximum_new_STARTs"] + 1, 0),
            (0, profile["maximum_cumulative_bytes"] - profile["initial_byte_upper_bound"] + 1)):
        with pytest.raises(reader.CountCheckpointLoaderRefusal, match="accounting_changed"):
            reader._operative_accounting(plan, starts, charged)


def test_registered_old_producer_reconstructs_only_legacy_plan_without_resolution(monkeypatch):
    plan = genuine_plan(monkeypatch); ledger = plan._parts[1]
    monkeypatch.setattr(reader, "EXPECTED_PRODUCER_PROTOCOL", reader.LEGACY_EIGHT_PART_PRODUCER_PROTOCOLS[0])
    monkeypatch.setattr(reader, "EXPECTED_PRODUCER_PLAN_PROFILE", "legacy_four_epochs")
    monkeypatch.setattr(reader.plans, "freeze_count_recovery_plan", lambda source: plan if source is ledger else None)
    monkeypatch.setattr(reader.negative_resolution, "resolve_registered", lambda *a, **k: pytest.fail("legacy reopens negative footprint"))
    assert reader._recovery_plan(ledger, runtime_head="a" * 40, actual_remote="b" * 40,
        boundary=lambda: None) is plan and len(plan._parts) == 8


def test_current_reader_reconstructs_nine_part_plan_only_from_issued_resolution_binding(monkeypatch):
    ledger, exposed, unused = genuine_exposure_plan(monkeypatch)
    monkeypatch.setattr(reader.plans, "_PLAN_MINTS", {}); monkeypatch.setattr(reader.plans, "_PLAN_KEYS", set())
    result = object(); calls = []
    def resolve(source, *, runtime_head, actual_remote):
        assert reader._resolution_phase_active() and source is ledger
        calls.append((source, runtime_head, actual_remote)); return result
    # Explicit fabricated forensic-issuer seam. The negative cap/model are genuine toy factories.
    monkeypatch.setattr(reader, "_RESOLUTION_FUNCTION", resolve)
    monkeypatch.setattr(reader, "_RESOLUTION_CODE", resolve.__code__)
    monkeypatch.setattr(reader.negative_resolution, "resolve_registered", resolve)
    monkeypatch.setattr(reader.negative_resolution, "resolution_binding", lambda value:
        (value, exposed, ledger, b"{}", "c" * 64, object()) if value is result else pytest.fail("foreign result"))
    monkeypatch.setattr(reader, "EXPECTED_PRODUCER_PROTOCOL", "d" * 64)
    monkeypatch.setattr(reader.producer, "RUN_PROTOCOL_SHA256", "d" * 64)
    monkeypatch.setattr(reader, "EXPECTED_PRODUCER_PLAN_PROFILE", "permanent_run13448_negative8")
    plan = reader._recovery_plan(ledger, runtime_head="a" * 40, actual_remote="b" * 40, boundary=lambda: None)
    assert len(plan._parts) == 9 and plan._parts[1] is ledger and plan._parts[8] is exposed
    assert plan.budget_profile()["permanent_unknown_START_upper_debits"] == 8
    assert calls == [(ledger, "a" * 40, "b" * 40)] and not reader._resolution_phase_active()
    assert reader._RESOLUTION_ISSUED == {}


def test_new_plan_json_or_caller_status_cannot_replace_registered_resolution(monkeypatch):
    ledger, exposed, unused = genuine_exposure_plan(monkeypatch)
    monkeypatch.setattr(reader, "EXPECTED_PRODUCER_PROTOCOL", "d" * 64)
    monkeypatch.setattr(reader.producer, "RUN_PROTOCOL_SHA256", "d" * 64)
    monkeypatch.setattr(reader, "EXPECTED_PRODUCER_PLAN_PROFILE", "permanent_run13448_negative8")
    monkeypatch.setattr(reader.negative_resolution, "resolve_registered", lambda *a, **k: {"complete": True})
    with pytest.raises(reader.CountCheckpointLoaderRefusal, match="baseline_changed"):
        reader._recovery_plan(ledger, runtime_head="a" * 40, actual_remote="b" * 40, boundary=lambda: None)
    assert reader._RESOLUTION_PHASE is None and reader._RESOLUTION_ISSUED == {}


def test_resolution_audit_phase_permits_only_exact_readonly_info_and_null(monkeypatch):
    import sys
    ledger, exposed, unused = genuine_exposure_plan(monkeypatch)
    monkeypatch.setattr(reader.plans, "_PLAN_MINTS", {}); monkeypatch.setattr(reader.plans, "_PLAN_KEYS", set())
    token = object(); events = []
    before = reader.HISTORICAL_HEADS
    def resolve(source, *, runtime_head, actual_remote):
        assert reader._resolution_phase_active()
        sys.audit("subprocess.Popen", "/usr/bin/hdiutil", ["/usr/bin/hdiutil", "info", "-plist"], None, {})
        sys.audit("open", "/dev/null", None, os.O_RDWR)
        events.append("exact-info-and-null")
        assert reader._git_allowed("git", ["git", "show", reader.negative_resolution.OLD_HEAD + ":"
            + reader.negative_resolution.HISTORICAL_PATHS[0]], reader.ROOT, runtime_head)
        for command in (["/usr/bin/hdiutil", "attach", "-readonly"], ["/usr/bin/hdiutil", "create", "new"],
                ["/usr/bin/hdiutil", "info", "-plist", "extra"]):
            with pytest.raises(reader.CountCheckpointLoaderRefusal, match="readonly_required"):
                sys.audit("subprocess.Popen", command[0], command, None, {})
        with pytest.raises(reader.CountCheckpointLoaderRefusal, match="readonly_required"):
            sys.audit("open", "/private/fabricated-source", None, os.O_RDWR)
        with pytest.raises(reader.CountCheckpointLoaderRefusal, match="readonly_required"):
            sys.audit("open", "/dev/null", None, os.O_RDWR | os.O_CREAT)
        with pytest.raises(reader.CountCheckpointLoaderRefusal, match="readonly_required"):
            sys.audit("socket.connect", object(), None)
        return token
    monkeypatch.setattr(reader, "_RESOLUTION_FUNCTION", resolve)
    monkeypatch.setattr(reader, "_RESOLUTION_CODE", resolve.__code__)
    monkeypatch.setattr(reader.negative_resolution, "resolve_registered", resolve)
    monkeypatch.setattr(reader.negative_resolution, "resolution_binding", lambda value:
        (value, exposed, ledger, b"{}", "c" * 64, object()))
    monkeypatch.setattr(reader, "EXPECTED_PRODUCER_PROTOCOL", "d" * 64)
    monkeypatch.setattr(reader.producer, "RUN_PROTOCOL_SHA256", "d" * 64)
    monkeypatch.setattr(reader, "EXPECTED_PRODUCER_PLAN_PROFILE", "permanent_run13448_negative8")
    with reader._readonly_seams("a" * 40):
        for event, args in (("open", ("/dev/null", None, os.O_RDWR)),
                ("subprocess.Popen", ("/usr/bin/hdiutil", ["/usr/bin/hdiutil", "info", "-plist"], None, {}))):
            with pytest.raises(reader.CountCheckpointLoaderRefusal, match="readonly_required"): sys.audit(event, *args)
        reader._recovery_plan(ledger, runtime_head="a" * 40, actual_remote="b" * 40, boundary=lambda: None)
        with pytest.raises(reader.CountCheckpointLoaderRefusal, match="readonly_required"):
            sys.audit("open", "/dev/null", None, os.O_RDWR)
    assert events == ["exact-info-and-null"] and reader.HISTORICAL_HEADS is before
    assert reader._RESOLUTION_PHASE is None and reader._RESOLUTION_ISSUED == {}


def test_resolution_phase_is_revoked_after_original_resolver_failure(monkeypatch):
    ledger, unused, unused2 = genuine_exposure_plan(monkeypatch)
    def resolve(*args, **kwargs):
        assert reader._resolution_phase_active()
        raise RuntimeError("FABRICATED_PRIVATE_FORENSIC_ERROR")
    monkeypatch.setattr(reader, "_RESOLUTION_FUNCTION", resolve)
    monkeypatch.setattr(reader, "_RESOLUTION_CODE", resolve.__code__)
    monkeypatch.setattr(reader.negative_resolution, "resolve_registered", resolve)
    monkeypatch.setattr(reader, "EXPECTED_PRODUCER_PROTOCOL", "d" * 64)
    monkeypatch.setattr(reader.producer, "RUN_PROTOCOL_SHA256", "d" * 64)
    monkeypatch.setattr(reader, "EXPECTED_PRODUCER_PLAN_PROFILE", "permanent_run13448_negative8")
    with pytest.raises(RuntimeError):
        reader._recovery_plan(ledger, runtime_head="a" * 40, actual_remote="b" * 40, boundary=lambda: None)
    assert not reader._resolution_phase_active() and reader._RESOLUTION_ISSUED == {}


def test_unregistered_entry_refuses_before_receipt_source_code_or_native(monkeypatch, tmp_path):
    calls = []
    for obj, name in ((reader, "_receipt"), (reader.storage, "_native_statfs"),
            (reader.old_archive, "load_registered_count_epoch_ledger")):
        monkeypatch.setattr(obj, name, lambda *a, **k: calls.append("FORBIDDEN"))
    with pytest.raises(reader.CountCheckpointLoaderRefusal, match="registration_pending"):
        with reader.load_registered_count_checkpoints(tmp_path, runtime_head="a" * 40,
                actual_remote="b" * 40, complete_code_manifest={}, archive_code_manifest={}): pass
    assert calls == []


@pytest.mark.parametrize("raw", [b'{"a":1,"a":1}', b'{"a":NaN}', b'{"a":Infinity}',
    b'{"a": 1}', b'', b'[]\n', b'"\xff"'])
def test_canonical_parser_rejects_duplicate_nonfinite_noncanonical_or_invalid(raw):
    with pytest.raises(reader.CountCheckpointLoaderRefusal): reader._parse(raw)


def test_canonical_parser_retains_exact_private_metadata():
    value = {"private": [1, None, False], "sha256": "a" * 64}
    assert reader._parse(canonical_json(value).encode()) == value


@pytest.mark.parametrize("index,value", [(0, True), (3, 0o644), (4, 2), (5, 0), (5, 2097153), (8, 0)])
def test_original_full9_has_exact_types_and_immutable_owner_protection(index, value):
    pin = [1, 2, os.getuid(), 0o600, 1, 3, 4, 5, 2]; pin[index] = value
    with pytest.raises(reader.CountCheckpointLoaderRefusal, match="seal_changed"): reader._seal(pin)


@pytest.mark.parametrize("name", ["../x", "x/../y", "./x", "/x", "x//y", "x\\y", "x/.", "x\x00y"])
def test_catalogue_path_is_fixed_relative_and_unambiguous(name):
    with pytest.raises(reader.CountCheckpointLoaderRefusal): reader._relative(name)


def test_real_readonly_file_is_checked_against_original_full9_and_raw_bytes(monkeypatch, tmp_path):
    path = tmp_path.resolve() / "synthetic-private.json"; raw = b'{"fabricated":true}'
    path.write_bytes(raw); path.chmod(0o600)
    original_stamp = reader._stamp
    monkeypatch.setattr(reader, "_stamp", lambda info: (*original_stamp(info)[:8], 2))  # Explicit fake UF_IMMUTABLE.
    seal = list(reader._stamp(path.lstat())); calls = []
    found, original = reader._read_original(path, hash_bytes(raw), seal, lambda: calls.append("check"))
    assert found == raw and original == tuple(seal) and len(calls) >= 3
    with pytest.raises(reader.CountCheckpointLoaderRefusal, match="seal_changed"):
        reader._read_original(path, hash_bytes(raw), None, lambda: None, seal_hash="f" * 64)


def test_file_mutation_at_last_boundary_is_not_rebaselined(monkeypatch, tmp_path):
    path = tmp_path.resolve() / "synthetic.json"; path.write_bytes(b"{}"); path.chmod(0o600)
    original_stamp = reader._stamp
    monkeypatch.setattr(reader, "_stamp", lambda info: (*original_stamp(info)[:8], 2))
    seal = list(reader._stamp(path.lstat())); calls = []
    def boundary():
        calls.append(1)
        if len(calls) == 3: path.write_bytes(b"[]")
    with pytest.raises(reader.CountCheckpointLoaderRefusal, match="seal_changed"):
        reader._read_original(path, hash_bytes(b"{}"), seal, boundary)


def test_symlink_and_unknown_current_stamp_cannot_bootstrap_original_seal(monkeypatch, tmp_path):
    target = tmp_path / "target"; target.write_bytes(b"{}"); target.chmod(0o600)
    link = tmp_path / "link"; link.symlink_to(target)
    with pytest.raises(reader.CountCheckpointLoaderRefusal):
        reader._read_original(link, hash_bytes(b"{}"), None, lambda: None)
    with pytest.raises(reader.CountCheckpointLoaderRefusal):
        reader._read_original(target, hash_bytes(b"{}"), None, lambda: None)


def test_both_independent_file_descriptors_are_drained_after_first_close_failure(monkeypatch):
    closed = []
    def close(fd):
        closed.append(fd)
        if fd == 2: raise OSError("FABRICATED_PRIVATE_SENTINEL")
    monkeypatch.setattr(reader.os, "close", close)
    with pytest.raises(reader.CountCheckpointLoaderRefusal, match="close_failed"): reader._close([1, 2])
    assert closed == [2, 1]


def test_caller_complete_flags_clone_and_matching_json_never_issue_a_corpus():
    with pytest.raises(reader.CountCheckpointLoaderRefusal): reader.RequalifiedCountTransportCorpus()
    fake = object.__new__(reader.RequalifiedCountTransportCorpus)
    fake._anchor = fake._identity = (fake, b'{"complete":true}', ())
    with pytest.raises(reader.CountCheckpointLoaderRefusal): fake.closed_summary()
    assert id(fake) in reader._FAILED and reader._CLOSED == {}


def test_live_summary_probe_permanently_latches_before_factory_terminal():
    cap = object.__new__(reader.RequalifiedCountTransportCorpus); private = (object(),)
    original = cap, b"{}", private
    cap._anchor = cap._identity = original; reader._ISSUED[cap] = original; reader._PRIVATE[cap] = private
    with pytest.raises(reader.CountCheckpointLoaderRefusal, match="not_closed"): cap.closed_summary()
    reader._CLOSED[cap] = original, b"{}", hash_bytes(b"{}")
    with pytest.raises(reader.CountCheckpointLoaderRefusal, match="binding_changed"): cap.closed_summary()


def test_safe_failure_projection_never_invokes_hostile_equality_or_text():
    class Hostile:
        def __eq__(self, other): pytest.fail("hostile equality executed")
        def __str__(self): pytest.fail("hostile text executed")
    error = reader.CountCheckpointLoaderRefusal(Hostile())
    assert reader.failure_summary(error) == {"category": "unknown_local_error", "contract_code": None, "errno_name": None}


def test_Main_known_exit0_receipt_schema_fits_unchanged_small_metadata_cap():
    value = {"schema": "si-count-actual-exit0-receipt-v1", "known_exec_session": 123456789,
        "process_exit": 0, "producer_head": "a" * 40, "producer_protocol": "b" * 64,
        "round_index_body_sha256": "c" * 64, "round_index_body_seal9_sha256": "d" * 64,
        "round_index_receipt_sha256": "e" * 64, "round_index_receipt_seal9_sha256": "f" * 64,
        "expected_union_binding_sha256": "0" * 64, "actual_union_sha256": "1" * 64}
    assert len(canonical_json(value).encode()) <= 1024


@pytest.fixture
def known_receipt(monkeypatch, tmp_path):
    value = {"schema": "si-count-actual-exit0-receipt-v1", "known_exec_session": 1234, "process_exit": 0,
        "producer_head": "a" * 40, "producer_protocol": "b" * 64,
        "round_index_body_sha256": "c" * 64, "round_index_body_seal9_sha256": "d" * 64,
        "round_index_receipt_sha256": "e" * 64, "round_index_receipt_seal9_sha256": "f" * 64,
        "expected_union_binding_sha256": "0" * 64, "actual_union_sha256": "1" * 64}
    for name, found in (("EXPECTED_PRODUCER_HEAD", value["producer_head"]),
        ("EXPECTED_PRODUCER_PROTOCOL", value["producer_protocol"]),
        ("EXPECTED_ROUND_BODY_SHA256", value["round_index_body_sha256"]),
        ("EXPECTED_ROUND_BODY_SEAL9_SHA256", value["round_index_body_seal9_sha256"]),
        ("EXPECTED_ROUND_RECEIPT_SHA256", value["round_index_receipt_sha256"]),
        ("EXPECTED_ROUND_RECEIPT_SEAL9_SHA256", value["round_index_receipt_seal9_sha256"]),
        ("EXPECTED_RECEIPT_PATH", str(tmp_path / "synthetic-Main-receipt.json"))): monkeypatch.setattr(reader, name, found)
    monkeypatch.setattr(reader, "_read_original", lambda *a, **k: (canonical_json(value).encode(), tuple(range(9))))
    return value


@pytest.mark.parametrize("field,value", [("process_exit", True), ("process_exit", 2), ("known_exec_session", 0),
    ("known_exec_session", True), ("producer_head", "f" * 40), ("round_index_body_sha256", "0" * 64),
    ("actual_union_sha256", "PENDING")])
def test_provisional_files_or_caller_status_do_not_replace_frozen_Main_known_receipt(known_receipt, field, value):
    known_receipt[field] = value
    with pytest.raises(reader.CountCheckpointLoaderRefusal, match="receipt_required"): reader._receipt(lambda: None)


def test_receipt_unknown_field_is_not_ignored(known_receipt):
    known_receipt["complete"] = True
    with pytest.raises(reader.CountCheckpointLoaderRefusal, match="shape_changed"): reader._receipt(lambda: None)


def test_authority_never_recreates_old_process_or_source_budget():
    found = reader.authority()
    assert found["source_resume_authority"] is found["source_admitted"] is found["budget_release_authority"] is False
    assert found["provider_HTTP"] == found["new_claims"] == found["new_STARTs"] == found["qc_attempts"] == 0


@pytest.fixture
def account_fixture(monkeypatch):
    """Genuine toy query plan/tickets; explicit synthetic saved control bytes."""
    from scripts import short_interest_count_durable_budget as budget
    plan = genuine_plan(monkeypatch); instance = budget.open_durable_count_budget(plan)
    private, attempts = {}, []
    claim = canonical_json({"schema": "si-count-spent-claim-v1", "spent": True, "chunk": 1,
        "plan_sha256": plan.sha256}).encode(); private["claim/claim.spent.json"] = claim
    raw = b'{"synthetic":true}'
    for number, position in enumerate(plan.chunk_positions(1), 1):
        ticket = instance.reserve_start_slot(position); bound = budget.ticket_binding(ticket)
        reserved = __import__("json").loads(bound[13]); observed = hash_payload(["synthetic", number])
        start_path, received_path = f"capture/starts/{number:06d}/START.spent.json", f"capture/received/{number:06d}/received.private.json"
        body, receipt = f"capture/responses/{number:06d}/response.raw", f"capture/responses/{number:06d}/response.receipt.private.json"
        started = {"reservation_sha256": bound[9], "request_sha256": bound[8], "spent": True,
            "claim_sha256": hash_bytes(claim), "ordinal": number, "lifetime_try": bound[7], "started_at": "2026-10-27T00:00:00Z"}
        private[start_path] = canonical_json(started).encode()
        private[received_path] = canonical_json({"observation_sha256": observed, "START_sha256": hash_bytes(private[start_path]),
            "http_invoked": True, "http_status": 200, "body_sha256": hash_bytes(raw)}).encode()
        private[body] = raw; private[receipt] = canonical_json({"body_sha256": hash_bytes(raw), "body_bytes": len(raw),
            "http_observation_sha256": observed, "source_admitted": False, "budget_release_authority": False}).encode()
        attempts.append({"reservation": reserved, "reservation_sha256": bound[9], "observation_sha256": observed,
            "http_invoked": True, "http_status": 200, "received_at": "2026-10-27T00:00:01Z", "fixed_diagnostic": None,
            "START_path": start_path, "received_path": received_path, "body_path": body, "receipt_path": receipt,
            "charged_bytes": len(raw)})
    account = {"chunk": 1, "reservation_sha256s": [row["reservation_sha256"] for row in attempts],
        "charges": [len(raw)] * len(attempts), "covered_positions": list(plan.chunk_positions(1)), "manifest_sha256": "f" * 64}
    descriptor = {"plan": {"chunk": 1}, "attempts": attempts, "external_claim_path": "claim/claim.spent.json",
        "account": account, "final_manifest_sha256": "f" * 64}
    return SimpleNamespace(plan=plan, descriptor=descriptor, private=private, lifetime=list(plan._parts[4][0]))


def test_original_saved_tickets_query_identity_controls_and_body_debits_reconstruct_account(account_fixture):
    h = account_fixture
    assert reader._attempts(h.descriptor, h.private, h.plan, h.lifetime) == h.descriptor["account"]


@pytest.mark.parametrize("field,value", [("http_status", True), ("http_invoked", 1), ("charged_bytes", 0),
    ("body_path", None), ("START_path", "capture/starts/000002/START.spent.json")])
def test_saved_accounting_cannot_use_status_aliases_zero_debits_or_wrong_ticket_paths(account_fixture, field, value):
    h = account_fixture; h.descriptor["attempts"][0][field] = value
    with pytest.raises((reader.CountCheckpointLoaderRefusal, KeyError)):
        reader._attempts(h.descriptor, h.private, h.plan, h.lifetime)


def test_request_hash_must_derive_from_original_query_not_an_equal_shape_payload(account_fixture):
    h = account_fixture; row = h.descriptor["attempts"][0]
    row["reservation"]["request_sha256"] = "e" * 64
    row["reservation_sha256"] = hash_payload(row["reservation"])
    with pytest.raises(reader.CountCheckpointLoaderRefusal, match="accounting_changed"):
        reader._attempts(h.descriptor, h.private, h.plan, h.lifetime)


def test_complete133_round_account_roots_fit_fixed2MiB_without_dropping_chunk_accounts():
    account = {"chunk": 1, "reservation_sha256s": ["a" * 64] * 528,
        "charges": [2097152] * 528, "covered_positions": list(range(1, 513)), "manifest_sha256": "b" * 64}
    roots = [reader._account_root(dict(account, chunk=number)) for number in range(1, 134)]
    assert len(canonical_json(roots).encode()) < 128 * 1024
    assert roots[0]["STARTs"] == 528 and roots[0]["charged_bytes"] == 528 * 2097152
    assert roots[0]["charges_sha256"] == hash_payload(account["charges"])


def test_foreign_or_negative_native_root_sibling_refuses_before_any_listed_source_bytes(monkeypatch, tmp_path):
    for name in ("capture", "claim", "checkpoint"): (tmp_path / name).mkdir(mode=0o700)
    (tmp_path / "UNREGISTERED.refused.json").write_bytes(b'{"synthetic":true}')
    calls = []
    monkeypatch.setattr(reader, "_read_original", lambda *a, **k: calls.append("FORBIDDEN SOURCE READ"))
    with pytest.raises(reader.CountCheckpointLoaderRefusal, match="negative"):
        reader._catalogue(tmp_path, [{"path": "claim/claim.spent.json", "bytes": 2,
            "sha256": "a" * 64, "seal9": [1, 2, os.getuid(), 0o600, 1, 2, 3, 4, 2]}], [], lambda: None)
    assert calls == []


def test_late_native_root_negative_during_last_catalogue_read_vetoes_result(monkeypatch, tmp_path):
    mount = tmp_path.resolve()
    for name in ("capture", "claim", "checkpoint"): (mount / name).mkdir(mode=0o700)
    path = mount / "claim" / "claim.spent.json"; raw = b"SYNTHETIC_CLAIM"
    path.write_bytes(raw); path.chmod(0o600)
    stamp = reader._stamp
    monkeypatch.setattr(reader, "_stamp", lambda info: (*stamp(info)[:8], 2))  # Explicit fake immutable flags only.
    row = {"path": "claim/claim.spent.json", "bytes": len(raw), "sha256": hash_bytes(raw), "seal9": list(reader._stamp(path.lstat()))}
    directories = [{"path": name, "pin4": list(reader.storage._directory((mount / name).lstat()))}
        for name in (".", "claim")]
    calls = []
    def boundary():
        calls.append(1)
        if len(calls) == 4: (mount / "late.refused.json").write_bytes(b"{}")
    with pytest.raises(reader.CountCheckpointLoaderRefusal, match="negative"):
        reader._catalogue(mount, [row], directories, boundary)
    assert len(calls) == 4


@pytest.fixture
def terminal_metadata_fixture(monkeypatch, tmp_path):
    """Real readonly metadata IO; explicit fake native epoch and flags only."""
    mount = tmp_path.resolve() / "mounted"; mount.mkdir(mode=0o700)
    for name in ("capture", "claim", "checkpoint"): (mount / name).mkdir(mode=0o700)
    for name in ("chunk", "round"): (mount / "checkpoint" / name).mkdir(mode=0o700)
    original_stamp = reader._stamp
    monkeypatch.setattr(reader, "_stamp", lambda info: (*original_stamp(info)[:8], 2))
    def file(path):
        path.write_bytes(b"SYNTHETIC_FIXED_BYTES"); path.chmod(0o600)
        return list(reader._stamp(path.lstat()))
    claim = mount / "claim" / "claim.spent.json"; claim9 = file(claim)
    pairs = {}
    for role in ("chunk", "round"):
        base = mount / "checkpoint" / role
        pairs[role] = (file(base / "attempt-body.raw"), file(base / "attempt-receipt.private.json"))
    main = tmp_path.resolve() / "Main-receipt.raw"; main9 = file(main)
    def directories(role):
        result = []
        for name in ("checkpoint", "checkpoint/" + role):
            info = (mount / name).lstat()
            result.append({"path": name, "pin5": [info.st_dev, info.st_ino, info.st_uid, info.st_gid, stat_mode(info)]})
        return result
    source = {"volume": {"system_entries": []}, "files": [{"path": "claim/claim.spent.json", "seal9": claim9}],
        "directories": [{"path": name, "pin4": list(reader.storage._directory((mount / name).lstat()))}
            for name in (".", "claim")]}
    index = {"plan_sha256": "a" * 64, "chunks": [{"body_seal9": pairs["chunk"][0],
        "receipt_seal9": pairs["chunk"][1], "directory_pins": directories("chunk")}]}
    monkeypatch.setattr(reader, "EXPECTED_ROUND_MOUNT", str(mount))
    monkeypatch.setattr(reader, "_native", lambda volume, plan, chunk, boundary: mount)  # Named fake native epoch.
    monkeypatch.setattr(reader, "_read_original", lambda *a, **k: pytest.fail("terminal metadata reread body bytes"))
    ticks = [0.0]; deadline = reader._new_deadline(lambda: ticks[0])
    return SimpleNamespace(mount=mount, claim=claim, main=main, ticks=ticks, deadline=deadline,
        audit=lambda: reader._terminal_metadata(index, [source], directories("round"),
            *pairs["round"], (main, "b" * 64, main9), deadline))


def test_terminal_original_metadata_pass_uses_no_body_reread(terminal_metadata_fixture):
    terminal_metadata_fixture.audit()


@pytest.mark.parametrize("changed", ["root", "source", "checkpoint", "Main_receipt"])
def test_terminal_metadata_pass_vetoes_last_clock_callback_drift(terminal_metadata_fixture, changed):
    h = terminal_metadata_fixture
    # Simulates the final clock/code callback occurring AFTER the last full
    # byte sweep. No source context, body read, new seal or native mutation.
    if changed == "root": (h.mount / "late.refused.json").write_bytes(b"{}")
    elif changed == "checkpoint": (h.mount / "checkpoint" / "chunk" / "late.refused.json").write_bytes(b"{}")
    else: (h.claim if changed == "source" else h.main).write_bytes(b"SYNTHETIC_FIXED_BYTES")
    with pytest.raises(reader.CountCheckpointLoaderRefusal): h.audit()


def test_native_root_accepts_only_exact_original_system_pin_not_late_adoption(monkeypatch, tmp_path):
    for name in ("capture", "claim", "checkpoint", ".fabricated-system"): (tmp_path / name).mkdir(mode=0o700)
    monkeypatch.setattr(reader.storage, "SYSTEM_ENTRY_NAMES", frozenset({".fabricated-system"}), raising=False)
    info = (tmp_path / ".fabricated-system").lstat()
    rows = [{"name": ".fabricated-system", "pin5": [info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode]}]
    reader._root_membership(tmp_path, rows, lambda: None)
    rows[0]["pin5"][1] += 1
    with pytest.raises(reader.CountCheckpointLoaderRefusal, match="directory_changed"):
        reader._root_membership(tmp_path, rows, lambda: None)


def test_checkpoint_parent_foreign_or_negative_sibling_refuses_before_metadata_reads(monkeypatch, tmp_path):
    parent = tmp_path / "checkpoint"; parent.mkdir(mode=0o700)
    for name in ("chunk", "round"): (parent / name).mkdir(mode=0o700)
    (parent / "run.refused.json").write_bytes(b"{}")
    rows = []
    for name in ("checkpoint", "checkpoint/round"):
        info = (tmp_path / name).lstat()
        rows.append({"path": name, "pin5": [info.st_dev, info.st_ino, info.st_uid, info.st_gid, stat_mode(info)]})
    calls = []
    monkeypatch.setattr(reader, "_read_original", lambda *a, **k: calls.append("FORBIDDEN READ"))
    with pytest.raises(reader.CountCheckpointLoaderRefusal, match="negative"):
        reader._pair(tmp_path, "checkpoint/round", "a" * 64, [], "b" * 64, [], lambda: None, directory_pins=rows)
    assert calls == []


def test_checkpoint_late_child_negative_after_final_receipt_boundary_vetoes_pair(monkeypatch, tmp_path):
    parent = tmp_path.resolve() / "checkpoint"; parent.mkdir(mode=0o700)
    child = parent / "chunk"; child.mkdir(mode=0o700)
    body = b'{"fabricated":true}'
    receipt = canonical_json({"body_sha256": hash_bytes(body), "body_bytes": len(body),
        "source_admitted": False, "budget_release_authority": False}).encode()
    rows, pins = [], []
    for path in (parent, child):
        info = path.lstat(); rows.append({"path": path.relative_to(tmp_path).as_posix(),
            "pin5": [info.st_dev, info.st_ino, info.st_uid, info.st_gid, stat_mode(info)]})
    original_stamp = reader._stamp
    monkeypatch.setattr(reader, "_stamp", lambda info: (*original_stamp(info)[:8], 2))  # Explicit fake immutable flags.
    for name, raw in (("attempt-body.raw", body), ("attempt-receipt.private.json", receipt)):
        path = child / name; path.write_bytes(raw); path.chmod(0o600); pins.append(list(reader._stamp(path.lstat())))
    calls = []
    def boundary():
        calls.append(1)
        if len(calls) == 6: (child / "late.refused.json").write_bytes(b"{}")
    with pytest.raises(reader.CountCheckpointLoaderRefusal, match="negative"):
        reader._pair(tmp_path.resolve(), "checkpoint/chunk", hash_bytes(body), pins[0],
            hash_bytes(receipt), pins[1], boundary, directory_pins=rows)
    assert len(calls) == 6


def stat_mode(info): return __import__("stat").S_IMODE(info.st_mode)


def test_postyield_origin_gate_never_hashes_a_late_hostile_class_slot(monkeypatch):
    cap = object.__new__(reader.RequalifiedCountTransportCorpus); private = (object(),)
    original = cap, b"{}", private
    cap._anchor = cap._identity = original; reader._ISSUED[cap] = original; reader._PRIVATE[cap] = private
    calls = []
    def hostile(self): calls.append("HOSTILE HASH"); return 1
    monkeypatch.setattr(reader.RequalifiedCountTransportCorpus, "__hash__", hostile)
    with pytest.raises(reader.CountCheckpointLoaderRefusal, match="binding_changed"): reader._corpus_origin(cap, original)
    assert calls == []


def test_hostile_hash_restoration_cannot_revive_a_public_failed_corpus(monkeypatch):
    cap = object.__new__(reader.RequalifiedCountTransportCorpus); private = (object(),)
    original = cap, b"{}", private
    cap._anchor = cap._identity = original; reader._ISSUED[cap] = original; reader._PRIVATE[cap] = private
    reader._CLOSED[cap] = original, b"{}", hash_bytes(b"{}")
    calls = []
    with monkeypatch.context() as changed:
        changed.setattr(reader.RequalifiedCountTransportCorpus, "__hash__", lambda self: calls.append("HOSTILE") or 1)
        with pytest.raises(reader.CountCheckpointLoaderRefusal): cap.closed_summary()
    assert calls == [] and id(cap) in reader._FAILED
    with pytest.raises(reader.CountCheckpointLoaderRefusal): cap.closed_summary()


def test_saved_ordinals_are_global_across_chunks_not_restarted_at_one(account_fixture):
    h = account_fixture; remapped = dict(h.private)
    for number, row in enumerate(h.descriptor["attempts"], 1):
        ordinal = number + 10
        row["reservation"]["reservation_ordinal"] = ordinal
        row["reservation_sha256"] = hash_payload(row["reservation"])
        start = reader._parse(remapped.pop(row["START_path"])); received = reader._parse(remapped.pop(row["received_path"]))
        start["ordinal"], start["reservation_sha256"] = ordinal, row["reservation_sha256"]
        row["START_path"] = f"capture/starts/{ordinal:06d}/START.spent.json"
        row["received_path"] = f"capture/received/{ordinal:06d}/received.private.json"
        remapped[row["START_path"]] = canonical_json(start).encode(); received["START_sha256"] = hash_bytes(remapped[row["START_path"]])
        remapped[row["received_path"]] = canonical_json(received).encode()
        for role, filename in (("body_path", "response.raw"), ("receipt_path", "response.receipt.private.json")):
            raw = remapped.pop(row[role]); row[role] = f"capture/responses/{ordinal:06d}/{filename}"; remapped[row[role]] = raw
    h.descriptor["account"]["reservation_sha256s"] = [row["reservation_sha256"] for row in h.descriptor["attempts"]]
    assert reader._attempts(h.descriptor, remapped, h.plan, h.lifetime, ordinal_offset=10) == h.descriptor["account"]
    with pytest.raises(reader.CountCheckpointLoaderRefusal):
        reader._attempts(h.descriptor, remapped, h.plan, list(h.plan._parts[4][0]))


def test_loader_catalogue_binds_every_reachable_eager_or_fixed_lazy_repository_import():
    """AST discovery is causal for the import catalogue, not runtime proof."""
    import ast
    root = Path(reader.__file__).resolve().parent.parent
    reached, todo = set(), [reader.DRIVER]
    def candidates(module):
        stem = module.replace(".", "/")
        for name in (stem + ".py", stem + "/__init__.py"):
            if (root / name).is_file(): yield name
    while todo:
        name = todo.pop()
        if name in reached: continue
        reached.add(name); tree = ast.parse((root / name).read_text())
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import): modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules.append(node.module); modules.extend(node.module + "." + alias.name for alias in node.names)
            for module in modules:
                for target in candidates(module):
                    todo.append(target)
                    parts = Path(target).parts[:-1]
                    for index in range(1, len(parts) + 1):
                        parent = "/".join(parts[:index]) + "/__init__.py"
                        if (root / parent).is_file(): todo.append(parent)
    assert reached <= set(reader.code_paths()), sorted(reached - set(reader.code_paths()))
    assert set(reader.code_paths()) - reached == set(reader.producer.protocol()["bound_antecedent_not_runtime_imported"])


def test_Git_allowlist_accepts_original_producer_show_and_both_exact_ref_ABIs(monkeypatch):
    from scripts import diagnose_short_interest_count_guard_timing as timing
    assert reader.HISTORICAL_HEADS == timing.HISTORICAL_HEADS
    runtime = "a" * 40; calls = []
    cache = reader.old_archive.count.old.cache
    def run(command, **kwargs):
        assert reader._git_allowed(command[0], command, kwargs["cwd"], runtime)
        calls.append(tuple(command)); return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
    monkeypatch.setattr(cache.subprocess, "run", run)
    guard = SimpleNamespace(check=lambda: None)
    assert set(cache.WRITER_CODE_FILES) <= set(reader.code_paths())
    for head in reader.HISTORICAL_HEADS:
        for name in cache.WRITER_CODE_FILES:
            cache._git(reader.ROOT, ["show", head + ":" + name], guard)
        cache._git(reader.ROOT, ["merge-base", "--is-ancestor", head, runtime], guard)
    for args in (["ls-remote", "origin", reader.lane.REF], ["ls-remote", "--exit-code", "origin", reader.lane.REF]):
        cache._git(reader.ROOT, args, guard)
    assert len(calls) == len(reader.HISTORICAL_HEADS) * (len(cache.WRITER_CODE_FILES) + 1) + 2


@pytest.mark.parametrize("command", [
    ["git", "ls-remote", "origin", "refs/heads/other"],
    ["git", "ls-remote", "--exit-code", "origin", "refs/heads/other"],
    ["git", "ls-remote", "origin"], ["git", "show", "HEAD:secrets.py"],
    ["git", "show", "a" * 40 + ":unregistered.py"], ["git", "show", "--stat"],
    ["git", "status"], ["git", "rev-parse", "--all"],
    ["git", "merge-base", "--is-ancestor", "f" * 40, "a" * 40]])
def test_Git_allowlist_rejects_unrelated_ref_paths_heads_or_broad_metadata(command):
    assert not reader._git_allowed("git", command, reader.ROOT, "a" * 40)


@pytest.fixture
def repository_unit_fixture(monkeypatch, tmp_path):
    """ORIGINAL LaneGuard/_git; only the physical/Git producer is fabricated."""
    root = tmp_path.resolve(); head, remote = "a" * 40, "b" * 40
    calls, status, committed = [], ["clean"], {}
    monkeypatch.setattr(reader, "ROOT", root); monkeypatch.setattr(reader.lane, "ROOT", root)
    def runner(where, command):
        assert where == root; calls.append(tuple(command))
        if command == ["git", "rev-parse", "--show-toplevel"]: return (str(root) + "\n").encode()
        if command[:2] == ["git", "status"]:
            oid = "c" * 40 if status[0] == "advanced" else head
            raw = ("# branch.oid " + oid + "\n# branch.head " + reader.lane.BRANCH + "\n").encode()
            return raw + (b"? changed.py\n" if status[0] == "dirty" else b"")
        assert command[:2] == ["git", "show"]
        return committed[command[2]]
    def physical(where): assert where == root and where.resolve() == root
    guard = reader.lane.LaneGuard(root, expected_head=head, expected_remote=remote,
        runner=runner, physical=physical)
    def subprocess_run(command, *, cwd, **unused):
        return SimpleNamespace(returncode=0, stdout=runner(cwd, command), stderr=b"")
    monkeypatch.setattr(reader.old_archive.count.old.cache.subprocess, "run", subprocess_run)
    ticks = [100.0]; deadline = reader._new_deadline(lambda: ticks[0])
    return SimpleNamespace(root=root, guard=guard, calls=calls, status=status, committed=committed,
        ticks=ticks, deadline=deadline, head=head, remote=remote)


@pytest.mark.parametrize("length,original_commands", [(1, 6), (65536, 6), (65537, 8), (2097152, 68)])
def test_descriptor_bracket_bounds_Git_calls_without_skipping_original_byte_reads(
        repository_unit_fixture, monkeypatch, length, original_commands):
    h = repository_unit_fixture; raw = b"F" * length
    path = h.root / "fabricated-body.raw"; path.write_bytes(raw); path.chmod(0o600)
    original_stamp = reader._stamp
    monkeypatch.setattr(reader, "_stamp", lambda info: (*original_stamp(info)[:8], 2))
    pin = list(reader._stamp(path.lstat()))
    # The old per-read callback performed a complete two-Git snapshot for
    # every 64KiB. The original file reader and original guards are unchanged.
    assert reader._read_original(path, hash_bytes(raw), pin, h.guard.check)[0] == raw
    assert len(h.calls) == original_commands; h.calls.clear()
    with reader._repository_unit(h.guard, h.deadline):
        found, seal = reader._read_original(path, hash_bytes(raw), pin, lambda: reader._tick(h.deadline))
    assert found == raw and seal == tuple(pin)
    assert len(h.calls) == 4  # Entry+exit snapshots, independent of body size.


@pytest.mark.parametrize("changed", ["dirty", "advanced"])
def test_descriptor_exit_snapshot_rejects_changed_repository(repository_unit_fixture, changed):
    h = repository_unit_fixture
    with pytest.raises(reader.lane.LaneBatchRefusal):
        with reader._repository_unit(h.guard, h.deadline): h.status[0] = changed
    assert len(h.calls) == 4


def test_pure_inner_clock_keeps_original_seal_mutation_veto(repository_unit_fixture, monkeypatch):
    h = repository_unit_fixture; path = h.root / "fabricated-body.raw"
    path.write_bytes(b"{}"); path.chmod(0o600); original_stamp = reader._stamp
    monkeypatch.setattr(reader, "_stamp", lambda info: (*original_stamp(info)[:8], 2))
    pin = list(reader._stamp(path.lstat())); calls = []
    def boundary():
        reader._tick(h.deadline); calls.append(1)
        if len(calls) == 3: path.write_bytes(b"[]")
    with pytest.raises(reader.CountCheckpointLoaderRefusal, match="seal_changed"):
        with reader._repository_unit(h.guard, h.deadline):
            reader._read_original(path, hash_bytes(b"{}"), pin, boundary)
    assert len(h.calls) == 4


@pytest.fixture
def invariant_producer(repository_unit_fixture, monkeypatch):
    h = repository_unit_fixture
    bodies = {"scripts/fabricated_a.py": b"FIXED_A", "scripts/fabricated_b.py": b"FIXED_B"}
    manifest = tuple((name, hash_bytes(raw)) for name, raw in sorted(bodies.items()))
    monkeypatch.setattr(reader, "EXPECTED_PRODUCER_HEAD", h.head)
    monkeypatch.setattr(reader, "EXPECTED_PRODUCER_PROTOCOL", "c" * 64)
    monkeypatch.setattr(reader, "EXPECTED_PRODUCER_CODE_MANIFEST", manifest)
    monkeypatch.setattr(reader, "code_paths", lambda: tuple(bodies))  # Explicit synthetic code profile.
    h.committed.update({h.head + ":" + name: raw for name, raw in bodies.items()})
    profile = {"head": h.head, "remote": h.remote, "code_manifest": [list(row) for row in manifest],
        "code_identity_sha256": hash_payload({"git_commit": h.head, "files": [
            {"path": name, "sha256": digest} for name, digest in manifest]}),
        "source_authority_sha256": "d" * 64, "operator_protocol_sha256": "e" * 64,
        "run_protocol_sha256": "c" * 64, "negative_policy_sha256": "f" * 64,
        "registration_sha256": "0" * 64}
    def for_chunk(chunk):
        value = deepcopy(profile)
        value["registration_sha256"] = hash_payload({"plan_sha256": "1" * 64, "chunk": chunk,
            "protocol_sha256": value["operator_protocol_sha256"], "head": value["head"], "remote": value["remote"],
            "code_identity_sha256": value["code_identity_sha256"],
            "code_manifest_sha256": hash_payload(dict(manifest))})
        return value
    h.manifest, h.for_chunk = manifest, for_chunk
    return h


def test_producer_initial_terminal_original_Git_audits_are_constant_across_133_chunks(invariant_producer):
    h = invariant_producer
    witness = reader._new_producer_witness(h.for_chunk(1), h.guard, h.deadline)
    assert len(h.calls) == 5 * len(h.manifest)
    for unused_sweep in range(3):
        for chunk in range(1, 134): reader._match_producer(h.for_chunk(chunk), witness, "1" * 64, chunk)
    assert len(h.calls) == 5 * len(h.manifest)  # No per-descriptor Git verification.
    reader._audit_producer_code(witness, h.guard, h.deadline)
    assert len(h.calls) == 10 * len(h.manifest)
    assert len(h.calls) < 5 * len(h.manifest) * 133 * 3


@pytest.mark.parametrize("field", ["registration_sha256", "source_authority_sha256", "operator_protocol_sha256"])
def test_producer_invariant_and_each_original_chunk_registration_are_recomputed(invariant_producer, field):
    h = invariant_producer; witness = reader._new_producer_witness(h.for_chunk(1), h.guard, h.deadline)
    value = h.for_chunk(2); value[field] = "9" * 64
    with pytest.raises(reader.CountCheckpointLoaderRefusal, match="producer_changed"):
        reader._match_producer(value, witness, "1" * 64, 2)
    with pytest.raises(reader.CountCheckpointLoaderRefusal, match="producer_changed"):
        reader._match_producer(h.for_chunk(1), witness, "1" * 64, 2)


def test_wrong_initial_committed_code_never_mints_producer_witness(invariant_producer):
    h = invariant_producer; h.committed[h.head + ":" + h.manifest[-1][0]] = b"CHANGED"
    with pytest.raises(reader.CountCheckpointLoaderRefusal, match="producer_changed"):
        reader._new_producer_witness(h.for_chunk(1), h.guard, h.deadline)
    assert reader._PRODUCERS == reader._PRODUCER_PINS == {}


def test_original_producer_terminal_code_and_private_witness_cannot_be_substituted(invariant_producer):
    h = invariant_producer; witness = reader._new_producer_witness(h.for_chunk(1), h.guard, h.deadline)
    forged = object.__new__(reader._ProducerCodeWitness)
    forged._anchor = forged._identity = witness._anchor
    with pytest.raises(reader.CountCheckpointLoaderRefusal, match="producer_changed"): reader._producer_origin(forged)
    h.committed[h.head + ":" + h.manifest[-1][0]] = b"CHANGED"
    with pytest.raises(reader.CountCheckpointLoaderRefusal, match="producer_changed"):
        reader._audit_producer_code(witness, h.guard, h.deadline)


@pytest.mark.parametrize("changed", [True, float("nan"), -1.0, 1800.0])
def test_original_pinned_clock_rejects_invalid_backward_and_final_deadline(changed):
    ticks = [0.0]; deadline = reader._new_deadline(lambda: ticks[0]); ticks[0] = changed
    with pytest.raises(reader.CountCheckpointLoaderRefusal): reader._tick(deadline)


def test_pinned_clock_never_looks_up_rebound_module_clock(monkeypatch):
    ticks = [0.0]; deadline = reader._new_deadline(lambda: ticks[0])
    monkeypatch.setattr(reader.time, "monotonic", lambda: pytest.fail("untrusted rebound clock called"))
    ticks[0] = 1.0; reader._tick(deadline)


def test_original_test_clock_code_cannot_be_replaced_after_mint():
    def clock(): return 0.0
    deadline = reader._new_deadline(clock)
    original = clock.__code__
    try:
        clock.__code__ = (lambda: 0.0).__code__
        with pytest.raises(reader.CountCheckpointLoaderRefusal, match="clock_changed"): reader._tick(deadline)
    finally: clock.__code__ = original


def test_final_metadata_deadline_includes_last_original_Main_receipt_audit(terminal_metadata_fixture, monkeypatch):
    h = terminal_metadata_fixture; original = reader._file_metadata
    def audit(path, seal9):
        original(path, seal9)
        if path == h.main: h.ticks[0] = 1800.0
    monkeypatch.setattr(reader, "_file_metadata", audit)
    with pytest.raises(reader.CountCheckpointLoaderRefusal, match="window_exhausted"): h.audit()
