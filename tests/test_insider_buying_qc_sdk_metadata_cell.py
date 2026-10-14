"""Invented CLR reflection metadata only; no installed/hosted LEAN required."""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


from research import insider_buying_qc_sdk_metadata_cell as cell
PATH = Path(cell.__file__)


def raw(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")


def sha(value):
    return hashlib.sha256(value).hexdigest()


def receipts():
    registration = {"schema": "insider-sdk-metadata-preregistration-v1", "profile": cell.PROFILE,
        "run_id": "invented-sdk-metadata-once", "project_id": cell.PROJECT_ID,
        "source_sha256": "a" * 64, "registered_at_utc": "2026-10-13T00:00:00Z",
        "allowed_type_names": list(cell.TARGETS), "allowed_member_names": list(cell.MEMBERS),
        "data_access_permitted": False}
    registration_raw = raw(registration)
    start = {"schema": "insider-sdk-metadata-start-v1", "profile": cell.PROFILE,
        "run_id": registration["run_id"], "registration_sha256": sha(registration_raw),
        "source_sha256": "a" * 64, "started_at_utc": "2026-10-13T00:00:01Z"}
    start_raw = raw(start)
    return {"registration_raw": registration_raw, "registration_sha256": sha(registration_raw),
            "start_raw": start_raw, "start_sha256": sha(start_raw), "execution_source_sha256": "a" * 64}


class ClrType:
    def __init__(self, name, *, generic_args=(), can_read=True):
        self.FullName = name
        self.IsGenericType = bool(generic_args)
        self._args = generic_args
        self.BaseType = None if name.startswith("System.") else ClrType("System.Object")
        self.CanRead = can_read
        self.Assembly = SimpleNamespace(GetName=lambda: SimpleNamespace(
            Name="QuantConnect.Common", Version=SimpleNamespace(ToString=lambda: "2.5.0.0")))
    def GetGenericTypeDefinition(self): return self
    def GetGenericArguments(self): return list(self._args)
    def GetInterfaces(self): return [ClrType("System.Collections.IEnumerable")]
    def GetProperty(self, name):
        if name != "Data": return None
        # PropertyInfo metadata only. A value getter must never be called.
        prop = SimpleNamespace(CanRead=self.CanRead, CanWrite=True,
            PropertyType=ClrType("System.Collections.Generic.List`1",
                                 generic_args=(ClrType("QuantConnect.Data.BaseData"),)),
            DeclaringType=ClrType("QuantConnect.Data.UniverseSelection.BaseDataCollection"))
        prop.GetValue = lambda *_: pytest.fail("No instance/property value may be evaluated")
        return prop


def provider(name): return ClrType(name)


def test_only_class_metadata_and_assembly_version_are_returned():
    result = cell.inspect_invented(type_provider=provider, **receipts())
    assert result["fixture_only"] is True
    assert len(result["classes"]) == 5
    for row in result["classes"]:
        assert row["metadata"]["assembly_version"] == "2.5.0.0"
        data = row["metadata"]["properties"][0]
        assert data["type"] == {"type_name": "System.Collections.Generic.List`1",
                                "generic_argument_names": ["QuantConnect.Data.BaseData"]}
    assert result["dataset_access_observed"] is False
    assert result["history_return_shape_observed"] is False
    assert result["platform_engine_build_observed"] is False
    assert result["source_identity_verified_here"] is False


def test_absent_class_and_member_are_explicit_not_assumed_available():
    result = cell.inspect_invented(type_provider=lambda name: None if name.endswith(".Fundamentals") else ClrType(name),
                                  **receipts())
    assert result["classes"][0] == {"requested_type": cell.TARGETS[0], "available": False, "metadata": None}
    assert result["classes"][1]["metadata"]["properties"][1]["available"] is False


@pytest.mark.parametrize("mutation", ["source", "project-bool", "data-true", "extra-property", "start-source",
                                     "registration-hash", "start-before", "future-start", "extra-field", "noncanonical"])
def test_bad_receipts_refuse_before_any_type_import_or_provider(mutation):
    values = receipts()
    registration = json.loads(values["registration_raw"])
    start = json.loads(values["start_raw"])
    if mutation == "source": registration["source_sha256"] = "b" * 64
    if mutation == "project-bool": registration["project_id"] = True
    if mutation == "data-true": registration["data_access_permitted"] = True
    if mutation == "extra-property": registration["allowed_member_names"].append("MarketCap")
    if mutation == "start-source": start["source_sha256"] = "b" * 64
    if mutation == "start-before": start["started_at_utc"] = "2026-10-12T23:59:59Z"
    if mutation == "future-start": start["started_at_utc"] = "2099-01-01T00:00:00Z"
    if mutation == "extra-field": registration["token"] = "invented-secret-not-to-be-returned"
    values["registration_raw"] = raw(registration)
    values["registration_sha256"] = sha(values["registration_raw"])
    start["registration_sha256"] = values["registration_sha256"]
    if mutation == "registration-hash": start["registration_sha256"] = "b" * 64
    values["start_raw"] = raw(start); values["start_sha256"] = sha(values["start_raw"])
    if mutation == "noncanonical":
        values["registration_raw"] += b"\n"; values["registration_sha256"] = sha(values["registration_raw"])
    with pytest.raises(cell.MetadataRefusal):
        cell.inspect_invented(type_provider=lambda *_: pytest.fail("Preflight must precede type access"), **values)


def test_repasting_source_retains_kernel_guard_not_new_authority(monkeypatch):
    monkeypatch.setattr(cell, "_STARTED", True)
    source = PATH.read_bytes()
    exec(compile(source, str(PATH), "exec"), cell.__dict__)
    assert cell._STARTED is True
    with pytest.raises(cell.MetadataRefusal, match="kernel-already-started"):
        cell.inspect_loaded_sdk_once(**receipts())
    cell._STARTED = False


def test_failed_real_type_import_consumes_guard_and_sanitizes_message(monkeypatch):
    monkeypatch.setattr(cell, "_STARTED", False)
    def failed(): raise RuntimeError("invented-private-path-or-key-must-not-appear")
    monkeypatch.setattr(cell, "_loaded_type_provider", failed)
    with pytest.raises(cell.MetadataRefusal) as failure:
        cell.inspect_loaded_sdk_once(**receipts())
    assert str(failure.value) == "REFUSED: loaded-sdk-type-import-failed"
    assert cell._STARTED is True


def test_metadata_provider_error_does_not_leak_runtime_exception():
    def failed(*_): raise RuntimeError("invented-private-path-or-key-must-not-appear")
    with pytest.raises(cell.MetadataRefusal) as failure:
        cell.inspect_invented(type_provider=failed, **receipts())
    assert str(failure.value) == "REFUSED: type-metadata-operation-failed"


@pytest.mark.parametrize("mutation", ["wrong-type", "assembly-path", "version-private", "canread-bool"])
def test_unexpected_metadata_cannot_be_a_channel_for_private_text(mutation):
    def changed(name):
        value = ClrType(name)
        if mutation == "wrong-type": value.FullName = "private-type"
        if mutation == "assembly-path": value.Assembly.GetName = lambda: SimpleNamespace(Name="/private/file", Version=None)
        if mutation == "version-private": value.Assembly.GetName = lambda: SimpleNamespace(Name="QuantConnect.Common",
            Version=SimpleNamespace(ToString=lambda: "private-information"))
        if mutation == "canread-bool": value.CanRead = 1
        return value
    with pytest.raises(cell.MetadataRefusal): cell.inspect_invented(type_provider=changed, **receipts())


def test_source_has_no_dataset_or_execution_calls_or_automatic_probe():
    tree = ast.parse(PATH.read_bytes())
    forbidden = {"QuantBook", "history", "History", "cik", "Cik", "add_security", "add_equity",
                 "GetValue", "CreateInstance", "GetEnvironmentVariable", "ObjectStore", "Config",
                 "place_order", "market_order", "backtest", "environ", "getenv"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
            assert name not in forbidden
        if isinstance(node, ast.ImportFrom):
            assert node.module != "QuantConnect.Research"
    assert not any(isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) for node in tree.body)
    assert not any(isinstance(node, ast.If) and "__name__" in ast.unparse(node.test) for node in tree.body)
