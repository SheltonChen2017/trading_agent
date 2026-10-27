"""Fake APFS/kernel plus an explicitly fabricated operation issuer only."""
import ast
from concurrent.futures import ThreadPoolExecutor
import inspect
import json
from pathlib import Path
import subprocess
import textwrap
import threading
from types import MethodType

import pytest

from scripts import short_interest_count_response_volume as volume
from scripts import short_interest_count_durable_transport as transport
from scripts import short_interest_body_receipt_volume as prior
import test_short_interest_body_receipt_volume as prior_tests


@pytest.fixture
def h(tmp_path, monkeypatch):
    for name in ("_MINTED", "_ISSUED", "_FROZEN", "_CLOCKS", "_COMMANDS", "_ORIGIN_ISSUED",
            "_STATE_ORIGINS", "_ASSOCIATION_ISSUED", "_ROOT_ENFORCEMENTS", "_OPERATIONS", "_VOLUME_BINDINGS"):
        monkeypatch.setattr(volume, name, {})
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
