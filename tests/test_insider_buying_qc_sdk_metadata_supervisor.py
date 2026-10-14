"""Private temp-only one-shot lineage proofs; never execute hosted SDK imports."""
import ast
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
from types import SimpleNamespace

import pytest


from research import insider_buying_qc_sdk_metadata_supervisor as supervisor
from research import insider_buying_qc_sdk_metadata_cell as cell
HERE = Path(supervisor.__file__).parent


@pytest.fixture
def tmp_path():
    """Section 194 (Claude review): a fresh 0700 root under /tmp.

    The supervisor admits fixture roots only beneath /tmp (/private/tmp on
    macOS). Pytest's default tmp_path on macOS lives under $TMPDIR
    (/private/var/folders/...), so the standard `python -m pytest` invocation
    refused every fixture here. The captured supervisor image is frozen, so the
    tests supply a root its existing guard accepts instead of loosening it.
    """
    root = Path(tempfile.mkdtemp(prefix="insider-qc-sdk-", dir="/tmp")).resolve()
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def raw(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def source_bytes():
    return {"cell_raw": (HERE / "insider_buying_qc_sdk_metadata_cell.py").read_bytes(),
            "invocation_raw": (HERE / "insider_buying_qc_sdk_metadata_invocation.py").read_bytes(),
            "supervisor_raw": (HERE / "insider_buying_qc_sdk_metadata_supervisor.py").read_bytes()}


def prepare(root):
    return supervisor.prepare_invented(fixture_root=root.resolve(), **source_bytes())


class ClrType:
    def __init__(self, name, args=()):
        self.FullName = name
        self.IsGenericType = bool(args)
        self._args = args
        self.BaseType = None
        self.Assembly = SimpleNamespace(GetName=lambda: SimpleNamespace(
            Name="QuantConnect.Common", Version=SimpleNamespace(ToString=lambda: "2.5.0.0")))
    def GetGenericTypeDefinition(self): return self
    def GetGenericArguments(self): return list(self._args)
    def GetInterfaces(self): return []
    def GetProperty(self, name):
        if name != "Data": return None
        result = SimpleNamespace(CanRead=True, CanWrite=True,
            PropertyType=ClrType("System.Collections.Generic.List`1", (ClrType("QuantConnect.Data.BaseData"),)),
            DeclaringType=ClrType("QuantConnect.Data.UniverseSelection.BaseDataCollection"))
        result.GetValue = lambda *_: pytest.fail("No property value getter")
        return result


def observation(prepared):
    namespace = Path(prepared["namespace"])
    return cell.inspect_invented(type_provider=ClrType,
        registration_raw=(namespace / "registration.json").read_bytes(),
        registration_sha256=prepared["registration_sha256"],
        start_raw=(namespace / "start.json").read_bytes(), start_sha256=prepared["start_sha256"],
        execution_source_sha256=prepared["cell_source_sha256"])


def complete(root, prepared, value):
    return supervisor.complete_invented(fixture_root=root.resolve(), metadata_raw=raw(value),
                                       expected_lineage_sha256=prepared["lineage_sha256"])


def test_registration_start_and_exact_distinct_source_lineage_precede_paste_artifacts(tmp_path):
    result = prepare(tmp_path)
    namespace = Path(result["namespace"])
    assert stat.S_IMODE(namespace.stat().st_mode) == 0o700
    assert set(item.name for item in namespace.iterdir()) == set(supervisor.PREPARED_FILES)
    assert all(stat.S_IMODE(item.stat().st_mode) == 0o600 and item.stat().st_nlink == 1
               for item in namespace.iterdir())
    binding = json.loads((namespace / "registration-bindings.json").read_bytes())
    start_binding = json.loads((namespace / "start-bindings.json").read_bytes())
    assert binding["committed_identity"]["fixture_only"] is True
    assert binding["invocation_source_sha256"] == result["invocation_source_sha256"]
    assert start_binding["registration_bindings_sha256"] == sha((namespace / "registration-bindings.json").read_bytes())
    assert start_binding["start_is_consumed_before_any_paste"] is True
    assert result["paste_order"] == ["cell-source.py", "control-input.py", "invocation.py"]
    assert result["hosted_execution_performed"] is False
    # The control-input cell contains exact receipts without executing invocation.
    controls = {}
    exec(compile((namespace / "control-input.py").read_bytes(), "invented-control-input", "exec"), controls)
    assert controls["_SDK_METADATA_CONTROL"]["registration_raw"] == (namespace / "registration.json").read_bytes()
    assert controls["_SDK_METADATA_CONTROL"]["start_raw"] == (namespace / "start.json").read_bytes()
    assert b"lineage_sha256" not in (namespace / "invocation.py").read_bytes()


def test_kernel_reset_cannot_restart_external_scope_or_overwrite_any_claim(tmp_path):
    result = prepare(tmp_path)
    namespace = Path(result["namespace"])
    before = {item.name: item.read_bytes() for item in namespace.iterdir()}
    cell._STARTED = False  # invented reset cannot mint external authority
    with pytest.raises(supervisor.SupervisorRefusal, match="scope-namespace-already-populated"):
        prepare(tmp_path)
    assert {item.name: item.read_bytes() for item in namespace.iterdir()} == before


def test_failure_after_claim_keeps_consumed_scope_no_retry_or_cleanup(tmp_path, monkeypatch):
    original = supervisor._HeldDirectories.write_new
    def fail(self, name, value):
        if name == "start.json":
            raise supervisor.SupervisorRefusal("REFUSED: invented-interruption-before-start")
        return original(self, name, value)
    monkeypatch.setattr(supervisor._HeldDirectories, "write_new", fail)
    with pytest.raises(supervisor.SupervisorRefusal, match="invented-interruption"):
        prepare(tmp_path)
    namespace = tmp_path.joinpath(*supervisor.NAMESPACE_PARTS)
    assert (namespace / "scope-claim.json").exists()
    assert (namespace / "registration.json").exists()
    assert not (namespace / "start.json").exists()
    monkeypatch.setattr(supervisor._HeldDirectories, "write_new", original)
    with pytest.raises(supervisor.SupervisorRefusal, match="scope-namespace-already-populated"):
        prepare(tmp_path)


def test_sanitized_invented_completion_is_append_only_and_cannot_claim_ready(tmp_path):
    prepared = prepare(tmp_path)
    value = observation(prepared)
    result = complete(tmp_path, prepared, value)
    namespace = Path(prepared["namespace"])
    assert result["fixture_only"] is True and result["scope_consumed"] is True
    assert result["backtest_ready"] is False
    assert (namespace / "metadata-observation.json").read_bytes() == raw(value)
    completion = json.loads((namespace / "completion.json").read_bytes())
    assert completion["external_execution_authenticated_here"] is False
    assert completion["dataset_or_history_shape_verified"] is False
    assert completion["actual_account_data_entitlement_verified"] is False
    before = (namespace / "completion.json").read_bytes()
    with pytest.raises(supervisor.SupervisorRefusal, match="immutable-leaf-already-exists"):
        complete(tmp_path, prepared, value)
    assert (namespace / "completion.json").read_bytes() == before


@pytest.mark.parametrize("mutation", ["extra-secret", "account-auth", "history-access", "fixture-as-real",
    "class-order", "property-order", "non-bool", "zero-bool", "property-getter-value",
    "version-path", "type-path", "too-many-interfaces", "start-before", "future-observation",
    "wrong-source", "wrong-registration", "wrong-start", "missing-available-metadata"])
def test_metadata_mutants_refused_without_new_completion_leaves(tmp_path, mutation):
    prepared = prepare(tmp_path)
    value = observation(prepared)
    prop = value["classes"][0]["metadata"]["properties"][0]
    if mutation == "extra-secret": value["private"] = "invented-not-real-secret"
    if mutation == "account-auth": value["owner_account_verified_here"] = True
    if mutation == "history-access": value["dataset_access_observed"] = True
    if mutation == "fixture-as-real": value["fixture_only"] = False
    if mutation == "class-order": value["classes"].reverse()
    if mutation == "property-order": value["classes"][0]["metadata"]["properties"].reverse()
    if mutation == "non-bool": prop["can_read"] = 1
    if mutation == "zero-bool": value["qc_backtests"] = False
    if mutation == "property-getter-value": prop["value"] = "invented-value"
    if mutation == "version-path": value["classes"][0]["metadata"]["assembly_version"] = "/private/path"
    if mutation == "type-path": prop["type"]["type_name"] = "/private/path"
    if mutation == "too-many-interfaces": value["classes"][0]["metadata"]["interfaces"] = [
        {"type_name": "System.IDisposable", "generic_argument_names": []}] * 33
    if mutation == "start-before": value["observed_at_utc"] = "2000-01-01T00:00:00Z"
    if mutation == "future-observation": value["observed_at_utc"] = "2099-01-01T00:00:00Z"
    if mutation == "wrong-source": value["declared_execution_source_sha256"] = "b" * 64
    if mutation == "wrong-registration": value["registration_sha256"] = "b" * 64
    if mutation == "wrong-start": value["start_sha256"] = "b" * 64
    if mutation == "missing-available-metadata": value["classes"][0]["metadata"] = None
    with pytest.raises(supervisor.SupervisorRefusal): complete(tmp_path, prepared, value)
    namespace = Path(prepared["namespace"])
    assert not (namespace / "metadata-observation.json").exists()
    assert not (namespace / "completion.json").exists()


def test_rehashed_lineage_is_not_an_external_expected_digest(tmp_path):
    prepared = prepare(tmp_path)
    value = observation(prepared)
    namespace = Path(prepared["namespace"])
    leaf = namespace / "invocation.py"
    leaf.write_bytes(leaf.read_bytes() + b"# invented substituted invocation\n")
    # Recompute every local descendant binding. Only the independently kept
    # pre-paste lineage digest can distinguish this internally consistent swap.
    rb_path = namespace / "registration-bindings.json"
    rb = json.loads(rb_path.read_bytes())
    rb["invocation_source_sha256"] = sha(leaf.read_bytes())
    rb["committed_identity"]["source_inventory"][1]["sha256"] = sha(leaf.read_bytes())
    rb["committed_identity"]["source_inventory"][1]["bytes"] = len(leaf.read_bytes())
    rb_path.write_bytes(raw(rb))
    sb_path = namespace / "start-bindings.json"
    sb = json.loads(sb_path.read_bytes())
    sb["invocation_source_sha256"] = sha(leaf.read_bytes())
    sb["registration_bindings_sha256"] = sha(rb_path.read_bytes())
    sb_path.write_bytes(raw(sb))
    lineage = json.loads((namespace / "lineage.json").read_bytes())
    for name in ("invocation.py", "registration-bindings.json", "start-bindings.json"):
        lineage["leaves_sha256"][name] = sha((namespace / name).read_bytes())
    (namespace / "lineage.json").write_bytes(raw(lineage))
    with pytest.raises(supervisor.SupervisorRefusal, match="expected-lineage"):
        complete(tmp_path, prepared, value)


def test_missing_claim_does_not_restart_a_populated_scope(tmp_path):
    prepared = prepare(tmp_path)
    namespace = Path(prepared["namespace"])
    (namespace / "scope-claim.json").unlink()
    with pytest.raises(supervisor.SupervisorRefusal, match="scope-namespace-already-populated"):
        prepare(tmp_path)
    assert not (namespace / "scope-claim.json").exists()


def test_unexpected_namespace_leaf_refuses_completion(tmp_path):
    prepared = prepare(tmp_path)
    value = observation(prepared)
    (Path(prepared["namespace"]) / "unexpected.txt").write_bytes(b"invented")
    with pytest.raises(supervisor.SupervisorRefusal, match="unexpected-scope-namespace-leaf"):
        complete(tmp_path, prepared, value)


@pytest.mark.parametrize("leaf_mode", [0o644, 0o640, 0o400])
def test_non_private_or_changed_receipt_mode_refuses(tmp_path, leaf_mode):
    prepared = prepare(tmp_path)
    value = observation(prepared)
    (Path(prepared["namespace"]) / "start.json").chmod(leaf_mode)
    with pytest.raises(supervisor.SupervisorRefusal): complete(tmp_path, prepared, value)


@pytest.mark.parametrize("kind", ["symlink-leaf", "hardlink-leaf", "symlink-namespace", "mode-namespace"])
def test_custody_aliases_and_unprivate_namespace_refuse(tmp_path, kind):
    prepared = prepare(tmp_path)
    value = observation(prepared)
    namespace = Path(prepared["namespace"])
    if kind in {"symlink-leaf", "hardlink-leaf"}:
        leaf = namespace / "start.json"
        other = tmp_path / "held-old-start.json"
        leaf.rename(other)
        if kind == "symlink-leaf": leaf.symlink_to(other)
        else: os.link(other, leaf)
    elif kind == "symlink-namespace":
        renamed = namespace.with_name("held-old-namespace")
        namespace.rename(renamed)
        namespace.symlink_to(renamed, target_is_directory=True)
    else: namespace.chmod(0o755)
    with pytest.raises(supervisor.SupervisorRefusal): complete(tmp_path, prepared, value)


def test_live_held_ancestor_replacement_is_detected_before_next_write(tmp_path):
    root = tmp_path.resolve()
    with supervisor._held(root, create=True) as held:
        namespace = root.joinpath(*supervisor.NAMESPACE_PARTS)
        namespace.rename(namespace.with_name("held-original"))
        namespace.mkdir(mode=0o700)
        with pytest.raises(supervisor.SupervisorRefusal, match="named-ancestry-changed"):
            held.write_new("invented.json", b"{}")
        assert not (namespace / "invented.json").exists()


@pytest.mark.parametrize("root", [supervisor.LANE_ROOT, supervisor.LANE_ROOT.parent,
                                   supervisor.LANE_ROOT / "artifacts"])
def test_fixture_real_lane_fence_runs_before_journal_constructor(monkeypatch, root):
    monkeypatch.setattr(supervisor, "_held", lambda *_args, **_kwargs: pytest.fail("real journal constructor"))
    with pytest.raises(supervisor.SupervisorRefusal, match="fixture-aliases-real-lane"):
        supervisor.prepare_invented(fixture_root=root, **source_bytes())


def test_inactive_image_production_api_refuses_before_git_or_namespace(monkeypatch):
    monkeypatch.setattr(supervisor, "__file__", str(HERE / "inactive-sdk-supervisor.py"))
    monkeypatch.setattr(supervisor, "_production_identity", lambda *_: pytest.fail("no actual Git/source read"))
    with pytest.raises(supervisor.SupervisorRefusal, match="private-draft-not-activated"):
        supervisor.prepare_once(expected_head="a" * 40, authenticated_safari_observation_sha256="b" * 64)
    with pytest.raises(supervisor.SupervisorRefusal, match="private-draft-not-activated"):
        supervisor.complete_once(expected_head="a" * 40, metadata_raw=b"{}",
            controlled_safari_execution_observation_sha256="b" * 64, expected_lineage_sha256="c" * 64)


def test_invocation_has_only_explicit_metadata_call_and_own_sanitized_output():
    tree = ast.parse((HERE / "insider_buying_qc_sdk_metadata_invocation.py").read_bytes())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    names = [node.func.id if isinstance(node.func, ast.Name) else node.func.attr for node in calls]
    assert set(names) == {"inspect_loaded_sdk_once", "print", "_raw", "decode"}
    assert "inspect_loaded_sdk_once" in names
    assert not any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in tree.body)
    assert supervisor.SOURCE_FILES[0] != supervisor.SOURCE_FILES[1]


def test_supervisor_has_no_actual_provider_sdk_browser_or_execution_api():
    tree = ast.parse((HERE / "insider_buying_qc_sdk_metadata_supervisor.py").read_bytes())
    forbidden = {"QuantBook", "History", "history", "GetValue", "CreateInstance", "getenv", "environ",
        "ObjectStore", "Config", "urlopen", "requests", "socket", "create_order", "backtest", "exec", "eval"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
            assert name not in forbidden
    assert not any(isinstance(node, ast.If) and "__name__" in ast.unparse(node.test) for node in tree.body)

