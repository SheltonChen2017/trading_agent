"""Fake APFS/kernel plus an explicitly fabricated operation issuer only."""
import ast
from concurrent.futures import ThreadPoolExecutor
import inspect
import json
import os
from pathlib import Path
import subprocess
import textwrap
import threading
import stat
from types import MethodType

import pytest
pytest.importorskip("resource")
fcntl = pytest.importorskip("fcntl")

from scripts import short_interest_count_response_volume as volume
from scripts import short_interest_count_durable_transport as transport
from scripts import short_interest_body_receipt_volume as prior
import test_short_interest_body_receipt_volume as prior_tests


@pytest.fixture
def h(tmp_path, monkeypatch):
    for name in ("_MINTED", "_ISSUED", "_FROZEN", "_CLOCKS", "_COMMANDS", "_ORIGIN_ISSUED",
            "_STATE_ORIGINS", "_ASSOCIATION_ISSUED", "_ROOT_ENFORCEMENTS", "_OPERATIONS", "_VOLUME_BINDINGS"):
        monkeypatch.setattr(volume, name, {})
    monkeypatch.setattr(volume, "_PRESERVATION_ORIGINS", {}, raising=False)
    monkeypatch.setattr(volume, "_PRESERVATION_PINS", {}, raising=False)
    monkeypatch.setattr(volume, "_SYSTEM_ORIGINS", {})
    monkeypatch.setattr(volume, "_SYSTEM_PINS", {})
    monkeypatch.setattr(volume, "_FAILED", set()); monkeypatch.setattr(volume, "_ATTEMPTED", set())
    monkeypatch.setattr(volume, "_PLAN", None); monkeypatch.setattr(volume, "_LAST_ASSOCIATION", None)
    namespace = volume.NAMESPACE_PREFIX + "-" + "a" * 64 + "-chunk001"
    # Reuse the established fabricated native/device/command fixture, with
    # only its expected fixed volume name adapted. No actual image is made.
    monkeypatch.setattr(prior_tests, "volume", volume)
    monkeypatch.setattr(volume, "NAMESPACE", namespace, raising=False)  # Fixture-only convenience; production never reads it.
    value = prior_tests.Harness(tmp_path, monkeypatch)
    source = textwrap.dedent(inspect.getsource(prior_tests.Harness.runner)).replace(
        "SI_BODY_RECEIPT_CUSTODY_V2", "SI_COUNT_RESPONSE_CUSTODY_V1")
    namespace_globals = {**prior_tests.__dict__, "volume": volume}
    functions = {}; exec(compile(source, "<fixed_fake_count_volume_runner>", "exec"), namespace_globals, functions)
    value.runner = MethodType(functions["runner"], value)
    monkeypatch.setattr(subprocess, "run", value.runner)
    value.operation = object.__new__(transport.CountCaptureOperation)
    value.plan, value.lock = object(), threading.RLock()
    value.origin = (value.operation, object(), value.plan, object(), 1, "b" * 64, "c" * 64,
        value.root, "d" * 40, "e" * 40, "a" * 64, value.lock, object(), object())
    current = [value.origin]
    def origin(operation):
        assert operation is value.operation
        return current[0]
    # Named semantic-operation issuer seam: genuine transport/source issuance
    # is covered separately; this fixture tests the new volume's full kernel.
    monkeypatch.setattr(transport, "active_operation_binding", origin)
    monkeypatch.setattr(transport, "operation_binding", origin)
    value.current = current
    original_hook = value.hook
    def locked():
        assert value.lock._is_owned(), "shared volume callback escaped original operation lock"
        original_hook()
    value.hook = locked
    value.monotonic = lambda: value.clock.value
    value.prepare = lambda: volume.prepare_registered_volume(value.root, operation=value.operation,
        boundary=value.boundary, monotonic=value.monotonic)
    return value


def test_registered_plan_chunk_has_fresh_volume_and_original_live_then_closed_binding(h):
    with h.prepare() as cap:
        assert type(cap) is volume.CountResponseVolume
        binding = volume.volume_binding(cap, live=True)
        assert len(binding) == 9 and binding[:3] == (cap, h.operation, h.mount)
        assert binding[3:6] == (1, "a" * 64, "b" * 64)
        assert cap.observation()["status"] == "live_provisional_count_chunk_volume"
        assert h.namespace.name == volume._namespace(h.origin)
    assert volume.volume_binding(cap) is binding
    assert cap.closed_summary()["status"] == "closed_count_chunk_storage_only"
    assert cap.closed_summary()["authority"]["source_admitted"] is False
    with pytest.raises(volume.CountResponseVolumeRefusal): volume.volume_binding(cap, live=True)
    assert h.image.exists() and h.mount.exists()
    assert all(args[1] in ("create", "attach", "info") for args, unused in h.calls)


def fabricated_system_entry(h, monkeypatch, *, name=".fseventsd", make=True):
    """Fake rootUID/native device metadata, never chown/native/mount calls."""
    control = {"uid": 0, "gid": None, "mode": 0o700, "device": h.host_device + 101}
    original_stat, original_hook = os.stat, h.command_hook
    def names(verb):
        original_hook(verb)
        if make and verb == "info" and h.attached and not (h.mount / name).exists():
            (h.mount / name).mkdir(mode=0o700)
            if control["gid"] is None: control["gid"] = original_stat(h.mount).st_gid
    h.command_hook = names
    def changed(*args, **kwargs):
        info = original_stat(*args, **kwargs); value = os.fspath(args[0])
        component = Path(value).name
        if component in (name, "capture", "claim", "checkpoint"):
            fields = {key: getattr(info, key) for key in dir(info) if key.startswith("st_")}
            fields["st_dev"] = control["device"]
            if component == name:
                fields.update(st_uid=control["uid"], st_gid=control["gid"],
                    st_mode=stat.S_IFMT(info.st_mode) | control["mode"])
            return SimpleNamespace(**fields)
        return info
    from types import SimpleNamespace
    monkeypatch.setattr(os, "stat", changed)
    return control


def test_original_optional_system_tuple_is_captured_before_source_and_never_reads_contents(h, monkeypatch):
    fabricated_system_entry(h, monkeypatch)
    real_open, calls = os.open, []
    def opened(name, *args, **kwargs):
        calls.append(os.fspath(name))
        assert Path(name).name != ".fseventsd", "root-owned system contents must not be opened"
        return real_open(name, *args, **kwargs)
    monkeypatch.setattr(os, "open", opened)
    monkeypatch.setattr(os, "supports_dir_fd", os.supports_dir_fd | {opened})  # Truthful test-only forwarding declaration.
    with h.prepare() as cap:
        first = volume.volume_system_entries(cap, h.operation)
        assert first is volume.volume_system_entries(cap, h.operation) and type(first) is tuple
        assert first[0][0] == ".fseventsd" and first[0][1][2:] == (0, h.mount.stat().st_gid, stat.S_IFDIR | 0o700)
        assert first[0][1][0] == h.host_device + 101 and not (h.mount / "claim").exists()
        for name in ("capture", "claim", "checkpoint"): (h.mount / name).mkdir(mode=0o700)
        cap.check()
    assert cap.closed_summary()["status"] == "closed_count_chunk_storage_only"


def test_absent_system_directory_cannot_appear_later_or_be_adopted(h):
    with pytest.raises(volume.CountResponseVolumeRefusal, match="root_membership_changed"):
        with h.prepare() as cap:
            assert volume.volume_system_entries(cap, h.operation) == ()
            (h.mount / ".fseventsd").mkdir(mode=0o700)
            cap.check()
    assert id(cap) in volume._FAILED and (h.mount / ".fseventsd").exists()


@pytest.mark.parametrize("name", ["FOREIGN", ".Spotlight-V100", "claim", "checkpoint"])
def test_unknown_or_source_name_before_baseline_refuses_before_capability(h, monkeypatch, name):
    fabricated_system_entry(h, monkeypatch, name=name)
    with pytest.raises(volume.CountResponseVolumeRefusal, match="root_membership_changed"):
        with h.prepare(): pytest.fail("unexpected pre-source name was adopted")
    assert not volume._MINTED and (h.mount / name).exists()


@pytest.mark.parametrize("field,value", [("uid", 50101), ("gid", 50102), ("mode", 0o755), ("device", -1)])
def test_fixed_known_name_requires_original_system_protection_before_source(h, monkeypatch, field, value):
    control = fabricated_system_entry(h, monkeypatch); control[field] = value
    with pytest.raises(volume.CountResponseVolumeRefusal, match="system_entry_refused"):
        with h.prepare(): pytest.fail("unprotected known name admitted")
    assert not volume._MINTED


@pytest.mark.parametrize("change", ["inode", "uid", "gid", "mode", "missing", "foreign", "symlink"])
def test_postbaseline_system_or_root_change_is_permanent_without_rebaseline(h, monkeypatch, change):
    control = fabricated_system_entry(h, monkeypatch)
    with pytest.raises(volume.CountResponseVolumeRefusal):
        with h.prepare() as cap:
            original = volume.volume_system_entries(cap, h.operation)
            if change in ("uid", "gid", "mode"): control[change] += 1
            elif change == "foreign": (h.mount / "unregistered.refused.json").write_bytes(b"SYNTHETIC")
            else:
                (h.mount / ".fseventsd").rename(h.root / "retained-original-system-directory")
                if change == "inode": (h.mount / ".fseventsd").mkdir(mode=0o700)
                if change == "symlink": (h.mount / ".fseventsd").symlink_to(h.root / "retained-original-system-directory")
            cap.check()
    assert id(cap) in volume._FAILED and original[0][0] == ".fseventsd"


def test_copied_system_tuple_cannot_replace_the_factory_original(h, monkeypatch):
    fabricated_system_entry(h, monkeypatch)
    with pytest.raises(volume.CountResponseVolumeRefusal, match="system_entry_changed"):
        with h.prepare() as cap:
            state = volume._MINTED[id(cap)][2]
            original = volume.volume_system_entries(cap, h.operation)
            state["system_entries"] = tuple(list(original))
            cap.check()
    assert id(cap) in volume._FAILED


def test_closed_original_volume_rejects_late_foreign_root_membership(h):
    with h.prepare() as cap: pass
    (h.mount / "unregistered.refused.json").write_bytes(b"SYNTHETIC")
    with pytest.raises(volume.CountResponseVolumeRefusal, match="root_membership_changed"):
        volume.volume_binding(cap)


def test_system_names_policy_cannot_expand_into_a_new_adoption_catalogue(h, monkeypatch):
    monkeypatch.setattr(volume, "SYSTEM_ENTRY_NAMES", frozenset((".fseventsd", "OTHER")))
    with pytest.raises(volume.CountResponseVolumeRefusal, match="system_entry_refused"):
        with h.prepare(): pytest.fail("expanded catalogue admitted")
    assert not h.calls


def test_same_original_plan_chunk_cannot_be_restarted_after_first_creation(h):
    with h.prepare(): pass
    before = len(h.calls)
    with pytest.raises(volume.CountResponseVolumeRefusal, match="already_used"):
        with h.prepare(): pytest.fail("spent chunk namespace reused")
    assert len(h.calls) == before and h.image.exists()


def test_namespace_is_only_exact_plan_digest_and_bounded_chunk(h):
    assert volume._namespace(h.origin) == volume.NAMESPACE_PREFIX + "-" + "a" * 64 + "-chunk001"
    for chunk in (0, 134, True):
        h.current[0] = (*h.origin[:4], chunk, *h.origin[5:])
        with pytest.raises(volume.CountResponseVolumeRefusal): volume._operation_origin(h.operation, active=True)
    h.current[0] = (*h.origin[:10], "../not-a-plan", *h.origin[11:])
    with pytest.raises(volume.CountResponseVolumeRefusal): volume._operation_origin(h.operation, active=True)
    assert h.calls == []


@pytest.mark.parametrize("kind", ["exact_deadline", "backwards"])
def test_registered_one_hour_is_strict_and_clock_failure_is_permanent(h, kind):
    cap = None
    with pytest.raises(volume.CountResponseVolumeRefusal, match="deadline|clock_refused|failure_latched"):
        with h.prepare() as cap:
            state = volume._MINTED[id(cap)][2]
            h.clock.value = state["begin"] + 3600 if kind == "exact_deadline" else state["begin"] - 1
            cap.check()
    assert cap is not None and id(cap) not in volume._ISSUED
    h.clock.value = 20
    with pytest.raises(volume.CountResponseVolumeRefusal): cap.closed_summary()
    assert h.image.exists() and h.mount.exists()


def test_eight_workers_serialize_shared_volume_callbacks_without_global_clock_race(h):
    with h.prepare() as cap:
        with ThreadPoolExecutor(max_workers=8) as workers:
            futures = [workers.submit(lambda: [cap.check() for unused in range(8)]) for unused in range(8)]
            for result in futures: result.result(timeout=10)
    assert cap.closed_summary()["chunk"] == 1 and h.boundaries > 64


def test_operation_origin_replacement_cannot_be_restored_after_detected_drift(h):
    with pytest.raises(volume.CountResponseVolumeRefusal):
        with h.prepare() as cap:
            h.current[0] = tuple(list(h.origin))
            with pytest.raises(volume.CountResponseVolumeRefusal): cap.check()
            h.current[0] = h.origin
            cap.check()
    assert h.image.exists() and id(cap) not in volume._ISSUED


@pytest.mark.parametrize("field,value", [("flags", 0), ("owner", 999999), ("fstype", "hfs")])
def test_original_native_mount_predicates_still_refuse(h, field, value):
    h.native_change = lambda row: {**row, field: value}
    with pytest.raises(volume.CountResponseVolumeRefusal):
        with h.prepare(): pytest.fail("bad original kernel identity admitted")


def test_postclose_original_image_or_device_drift_vetoes_reloader(h):
    with h.prepare() as cap: pass
    h.node_change = lambda row: {**row, "st_ino": row["st_ino"] + 1}
    with pytest.raises(volume.CountResponseVolumeRefusal, match="device_node_changed"):
        volume.volume_binding(cap)
    h.node_change = lambda row: row
    with pytest.raises(volume.CountResponseVolumeRefusal): cap.closed_summary()


def test_late_filesystem_identity_cannot_be_rebaselined(h):
    with pytest.raises(volume.CountResponseVolumeRefusal, match="native_identity_changed"):
        with h.prepare() as cap:
            h.native_change = lambda row: {**row, "fsid": (0, 0)}
            cap.check()
    assert id(cap) not in volume._ISSUED


def test_kernel_predicate_ast_is_unchanged_from_closed_body_volume():
    names = ("_StatFS64", "_platform", "_native_statfs", "_directory", "_backing", "_mount_identity",
        "_entities", "_mounted_descriptor", "_device_node_stat", "_check_mount", "_node_pin", "_native_contract",
        "_fresh_root_identity", "_root_enforcement_record", "_enforce_new_root")
    class Normalize(ast.NodeTransformer):
        def visit_Name(self, node):
            if node.id == "CountResponseVolumeRefusal": node.id = "IsolatedVolumeRefusal"
            return node
        def visit_Constant(self, node):
            if type(node.value) is str: node.value = node.value.replace("count_volume_", "isolated_")
            return node
    for name in names:
        old = ast.parse(textwrap.dedent(inspect.getsource(getattr(prior, name))))
        new = ast.parse(textwrap.dedent(inspect.getsource(getattr(volume, name))))
        assert ast.dump(Normalize().visit(new), include_attributes=False) == ast.dump(old, include_attributes=False)


def test_new_volume_policy_separates_source_cap_and_virtual_container():
    value = volume.policy()
    assert value["virtual_bytes"] == 8 * 1024 ** 3 and value["source_byte_ceiling"] == 4 * 1024 ** 3
    assert value["maximum_seconds"] == 3600 and value["subprocess_seconds"] == 120
    assert value["maximum_chunks"] == 133 and value["extra_tickets_per_chunk"] == 16
    assert value["payload_output_component"] == "capture" and value["external_claim_component"] == "claim"
    assert value["virtual_image_bytes_are_source_budget"] is False
    assert value["authority"]["source_admitted"] is value["authority"]["ready_for_backtest"] is False
    assert prior.MAXIMUM_SECONDS == 300


def active_capacity_ticket(h, monkeypatch):
    """Named typed-ticket issuer seam; no real reservation/source authority."""
    budget = transport.accounting
    ticket = object.__new__(budget.CountAttemptTicket)
    original = (ticket, h.origin[1], h.origin[2], h.origin[4], 1, 5, 5, 1,
        "1" * 64, "2" * 64, "3" * 64, 2097152, h.origin[3], b"fabricated")
    def issued(value):
        budget.require(value is ticket, "attempt_ticket_binding_changed")
        return original
    monkeypatch.setattr(budget, "active_ticket_binding", issued)
    return ticket


def test_preservation_origin_is_live_original_once_and_retained_fd_is_readonly(h):
    with h.prepare() as cap:
        original = volume.preservation_volume_origin(cap, h.operation)
        assert len(original) == 10 and original[:3] == (cap, h.operation, h.mount)
        assert original[4][:3] == original[5][:3]
        assert original[4][-1] == 0o700 and len(original[6]) == 9 and len(original[7]) == 6
        assert original[8] is cap._anchor
        assert fcntl.fcntl(original[3], fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY
        assert volume.preservation_volume_origin(cap, h.operation) is original
        copied = list(original); copied[2] = Path("/fabricated/not-original")
        assert volume.preservation_volume_origin(cap, h.operation) is original
        duplicate = os.dup(original[3])
    try:
        # This independent live duplicate is the prospective negative lease's
        # own resource. The old accessor does not reopen or adopt any inode.
        assert os.fstat(duplicate).st_ino == original[4][1]
        with pytest.raises(volume.CountResponseVolumeRefusal):
            volume.preservation_volume_origin(cap, h.operation)
    finally: os.close(duplicate)


def test_preservation_origin_never_mints_from_failed_or_cross_operation_volume(h):
    with pytest.raises(volume.CountResponseVolumeRefusal):
        with h.prepare() as cap:
            with pytest.raises(volume.CountResponseVolumeRefusal):
                volume.preservation_volume_origin(cap, object())
            volume.preservation_volume_origin(cap, h.operation)
    assert cap not in volume._PRESERVATION_ORIGINS


def test_preservation_origin_registry_replacement_cannot_issue_a_new_nonce(h):
    with pytest.raises(volume.CountResponseVolumeRefusal):
        with h.prepare() as cap:
            original = volume.preservation_volume_origin(cap, h.operation)
            volume._PRESERVATION_ORIGINS[cap] = (*original[:-1], object())
            volume.preservation_volume_origin(cap, h.operation)
    assert id(cap) not in volume._ISSUED


def test_capacity_gate_rechecks_original_host_and_mounted_native_before_dispatch(h, monkeypatch):
    ticket = active_capacity_ticket(h, monkeypatch)
    with h.prepare() as cap:
        before, commands = len(h.native_reads), len(h.calls)
        assert cap.check_capacity_before_dispatch(ticket) is None
        assert len(h.native_reads) > before and len(h.calls) == commands


@pytest.mark.parametrize("kind", ["host_free", "mount_free", "host_fsid", "mount_fsid", "wrong_ticket", "not_live_op"])
def test_capacity_failure_is_before_dispatch_and_cannot_be_rebased(h, monkeypatch, kind):
    ticket = active_capacity_ticket(h, monkeypatch)
    with pytest.raises((volume.CountResponseVolumeRefusal, transport.accounting.DurableCountBudgetRefusal,
            transport.CountTransportRefusal)):
        with h.prepare() as cap:
            if kind == "host_free": h.host_change = lambda row: {**row, "bavail": 0}
            elif kind == "mount_free": h.native_change = lambda row: {**row, "bavail": 0}
            elif kind == "host_fsid": h.host_change = lambda row: {**row, "fsid": (0, 0)}
            elif kind == "mount_fsid": h.native_change = lambda row: {**row, "fsid": (0, 0)}
            elif kind == "wrong_ticket": ticket = object()
            else:
                def inactive(unused): raise transport.CountTransportRefusal("REFUSED: count_operator_not_live")
                monkeypatch.setattr(transport, "active_operation_binding", inactive)
            cap.check_capacity_before_dispatch(ticket)
    assert id(cap) not in volume._ISSUED
    h.host_change = h.native_change = lambda row: row
    with pytest.raises(volume.CountResponseVolumeRefusal): cap.closed_summary()


def test_fresh_capacity_thresholds_match_initial_fixed_thresholds_exactly(h, monkeypatch):
    ticket = active_capacity_ticket(h, monkeypatch)
    with h.prepare() as cap:
        h.host_change = lambda row: {**row, "bsize": 4096, "bavail": (9 * 1024 ** 3) // 4096}
        h.native_change = lambda row: {**row, "bsize": 4096, "bavail": (4 * 1024 ** 3) // 4096}
        cap.check_capacity_before_dispatch(ticket)
