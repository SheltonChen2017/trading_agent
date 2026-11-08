"""Claude review section 375: retained PIT audit runner guards without a pin.

Invented values only; no retained input, git operation, sandbox launch, provider
or account access. The caller supplies native process-tree network denial.
"""
import json
import os

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX custody support; Windows custody port deferred")
from research import insider_buying_pilot_pit_retained_audit_runner_v1 as m


IDENTITY = {"head": "1" * 40, "sources": {}, "source_inventory_sha256": "2" * 64}


@pytest.mark.parametrize("attribute", ("base_prefix", "executable"))
@pytest.mark.parametrize("covering", ("lane-root", "lane-parent", "custody-parent"))
def test_interpreter_prefix_cannot_grant_the_lane_or_custody_roots(monkeypatch, attribute, covering):
    prefix = {"lane-root": m.ROOT, "lane-parent": m.ROOT.parent,
              "custody-parent": m.stable.PRIVATE_CUSTODY_ROOT.parent}[covering]
    # sys.executable is two levels below the directory the policy grants.
    value = prefix / "bin" / "python" if attribute == "executable" else prefix
    monkeypatch.setattr(m.sys, attribute, str(value))
    with pytest.raises(m.AuditRunnerError, match="source_refused"):
        m.policy(sources=m.OWN)


def test_unrelated_interpreter_prefix_keeps_the_native_denials(monkeypatch):
    monkeypatch.setattr(m.sys, "base_prefix", "/opt/invented-python")
    monkeypatch.setattr(m.sys, "executable", "/opt/invented-python/bin/python")
    policy = m.policy(sources=m.OWN)
    assert "(deny file-read-data)" in policy and "(deny network*)" in policy


@pytest.mark.parametrize("attribute", ("base_prefix", "executable"))
@pytest.mark.parametrize("nested", ("lane-data", "custody-epoch", "fixed-input"))
def test_interpreter_prefix_inside_a_protected_tree_cannot_grant_extra_data(monkeypatch, attribute, nested):
    prefix = {"lane-data": m.ROOT / "artifacts" / "invented-other-epoch",
              "custody-epoch": m.stable.PRIVATE_CUSTODY_ROOT / "invented-other-epoch",
              "fixed-input": m.SHARADAR / "invented-runtime"}[nested]
    value = prefix / "bin" / "python" if attribute == "executable" else prefix
    monkeypatch.setattr(m.sys, attribute, str(value))
    with pytest.raises(m.AuditRunnerError, match="source_refused"):
        m.policy(sources=m.OWN)


@pytest.mark.parametrize("attribute", ("base_prefix", "executable"))
@pytest.mark.parametrize("location", ("lane", "nested-lane", "nested-custody"))
def test_data_volume_runtime_alias_cannot_bypass_protected_directory_identity(monkeypatch, attribute, location):
    original = {"lane": m.ROOT, "nested-lane": m.ROOT / "artifacts" / "invented-runtime",
                "nested-custody": m.stable.PRIVATE_CUSTODY_ROOT / "invented-runtime"}[location]
    prefix = m.Path("/System/Volumes/Data" + str(original))
    value = prefix / "bin" / "python" if attribute == "executable" else prefix
    monkeypatch.setattr(m.sys, attribute, str(value))
    with pytest.raises(m.AuditRunnerError, match="source_refused"):
        m.policy(sources=m.OWN)


def test_runtime_directory_metadata_refuses_a_regular_file(tmp_path):
    path = tmp_path / "invented-runtime"
    path.write_bytes(b"invented")
    with pytest.raises(m.AuditRunnerError, match="source_refused"):
        m._directory_ancestors(path)


def test_runtime_directory_metadata_failure_is_finite(monkeypatch, tmp_path):
    path = tmp_path / "invented-runtime"
    original = m.Path.stat
    def refused(self, *args, **kwargs):
        if self == path:
            raise PermissionError("PRIVATE PATH AND ACCOUNT")
        return original(self, *args, **kwargs)
    monkeypatch.setattr(m.Path, "stat", refused)
    with pytest.raises(m.AuditRunnerError) as caught:
        m._directory_ancestors(path)
    assert str(caught.value) == "source_refused"


@pytest.mark.parametrize("relation", ("covers", "nested", "shared-ancestor-only"))
def test_runtime_physical_ancestry_checks_endpoints_not_a_common_root(monkeypatch, relation):
    runtime, protected = m.Path("/invented-runtime"), m.Path("/invented-private")
    root = m.Path("/")
    runtime_chain = {runtime: (1, 10), root: (1, 1)}
    protected_chain = {protected: (1, 20), root: (1, 1)}
    if relation == "covers":
        protected_chain[m.Path("/invented-private-parent")] = (1, 10)
    if relation == "nested":
        runtime_chain[m.Path("/invented-runtime-parent")] = (1, 20)
    monkeypatch.setattr(m, "_directory_ancestors", lambda p: {runtime: runtime_chain, protected: protected_chain}[p])
    if relation == "shared-ancestor-only":
        m._disjoint_runtime_directories((runtime,), (protected,))
    else:
        with pytest.raises(m.AuditRunnerError, match="source_refused"):
            m._disjoint_runtime_directories((runtime,), (protected,))


def _launched(monkeypatch, value, *, identities=(IDENTITY, IDENTITY)):
    remaining = iter(identities)
    monkeypatch.setattr(m, "_identity", lambda *_: next(remaining))
    monkeypatch.setattr(m, "policy", lambda **_: "invented-policy")
    monkeypatch.setattr(m.stable.source, "_launch", lambda *_a, **_k: value)


def test_parent_returns_a_completed_worker_result(monkeypatch):
    value = {"completed": True, "read_only": True}
    _launched(monkeypatch, value)
    assert m.run_actual("1" * 40) is value


@pytest.mark.parametrize("value", ({}, {"completed": None}, {"completed": 1}, {"completed": "true"}))
def test_parent_refuses_a_worker_result_without_exact_completion(monkeypatch, value):
    _launched(monkeypatch, value)
    with pytest.raises(m.AuditRunnerError, match="retained_identity_audit_refused"):
        m.run_actual("1" * 40)


def test_parent_refuses_when_the_source_identity_moved_during_the_worker(monkeypatch):
    moved = {**IDENTITY, "source_inventory_sha256": "3" * 64}
    _launched(monkeypatch, {"completed": True}, identities=(IDENTITY, moved))
    with pytest.raises(m.AuditRunnerError, match="retained_identity_audit_refused"):
        m.run_actual("1" * 40)


class _Guard:
    def check(self):
        pass

    def close(self):
        pass


def test_worker_failure_wire_has_only_finite_fields_and_the_parent_reads_it_as_a_refusal(monkeypatch, capsysbinary):
    monkeypatch.setattr(m.stable.native, "_isolated", lambda: None)
    monkeypatch.setattr(m.stable.native.batch.campaign.base, "_prove_isolation", lambda: None)
    monkeypatch.setattr(m.stable.native, "_WorkerMemoryGuard", _Guard)
    monkeypatch.setattr(m, "_source_current", lambda _identity: None)
    def held(*_a, **_k):
        raise OSError(13, "PRIVATE ACCOUNT BODY", "/private/PRIVATE-TOKEN")
    monkeypatch.setattr(m, "Held", held)
    m.worker(IDENTITY)
    wire = capsysbinary.readouterr().out
    assert b"PRIVATE" not in wire
    expected = {"completed": False, "read_only": True, "phase": "open_provider",
                "failure_class": "os_error", "os_errno": 13, "refusal_code": "unknown"}
    assert json.loads(wire) == {"ok": True, "value": expected}
    assert m.stable.source._ipc_result(wire, b"", 0) == expected
    assert m.ReportedAuditRefusal(expected).diagnostic == expected


def test_a_failure_after_the_success_wire_cannot_reach_the_parent_as_success():
    # The worker writes its success line, then runs one more guard check. A
    # failure there appends a diagnostic line, so stdout holds two documents.
    success = m.raw({"ok": True, "value": {"completed": True}}) + b"\n"
    late = m.raw({"ok": True, "value": m.failure_info("serialization", RuntimeError())}) + b"\n"
    assert m.stable.source._ipc_result(success, b"", 0) == {"completed": True}
    with pytest.raises(m.stable.source.FirstRateQualificationError):
        m.stable.source._ipc_result(success + late, b"", 0)


def _storage():
    physical = {"schema": m.stable.SCHEMA + "/storage-identity", "root_kind": "fixed_user_application_support",
                "device": 1, "inode": 2, "mode": 0o700, "owner": os.geteuid(), "group": 20}
    proof = {"passed": True, "fixture_only": False, "storage_identity": dict(physical)}
    return physical, proof, {**proof, "storage_identity": dict(physical), "receipt_sha256": m.PINS["proof_complete"]["sha256"]}


def test_storage_diagnostic_reports_changed_field_names_without_identity_values():
    physical, proof, qualification = _storage()
    physical.update(device=987654321, inode=987654322)
    result = m.storage_difference(physical, proof, qualification)
    assert result["binding_passed"] is False
    assert result["current_vs_proof_changed_fields"] == ["device", "inode"]
    assert result["current_vs_qualification_changed_fields"] == ["device", "inode"]
    assert b"98765432" not in m.raw(result)
    # A diagnostic does not weaken the original guard.
    with pytest.raises(m.AuditRunnerError):
        m.storage_binding(physical, proof, qualification)


def test_storage_diagnostic_distinguishes_identity_match_from_wrong_receipt_pin():
    physical, proof, qualification = _storage()
    assert m.storage_difference(physical, proof, qualification)["binding_passed"] is True
    qualification["receipt_sha256"] = "0" * 64
    result = m.storage_difference(physical, proof, qualification)
    assert result["binding_passed"] is result["qualification_receipt_pin_matches"] is False
    assert result["current_vs_proof_changed_fields"] == result["current_vs_qualification_changed_fields"] == []


def test_storage_diagnostic_reports_missing_or_wrong_typed_proof_without_private_text():
    physical, proof, qualification = _storage()
    proof["storage_identity"] = "PRIVATE SOURCE"
    qualification["storage_identity"]["device"] = True
    result = m.storage_difference(physical, proof, qualification)
    assert result["current_vs_proof_changed_fields"] == ["storage_identity"]
    assert result["current_vs_qualification_changed_fields"] == ["device"]
    assert result["binding_passed"] is False and b"PRIVATE" not in m.raw(result)


@pytest.mark.parametrize("cleanup_failure", (None, "held", "guard"))
def test_storage_diagnostic_worker_reads_only_three_leaves_and_refuses_cleanup_failure(monkeypatch, capsysbinary, cleanup_failure):
    physical, proof, qualification = _storage()
    physical["inode"] += 1
    reads, closes = [], []
    complete = {"published_leaf_pins": {"storage-qualification.json": {"bytes": 2, "sha256": "1" * 64}}}
    values = {(m.PROVIDER, "complete.json"): complete,
              (m.PROOF, "complete.json"): proof,
              (m.PROVIDER, "storage-qualification.json"): qualification}
    bodies = {}
    class Held:
        def __init__(self, root):
            assert root in {m.PROVIDER, m.PROOF}
            self.root, self.leaves = root, {}
        def read(self, name, pin, *, check):
            check(); reads.append((self.root, name)); self.leaves[name] = pin
            data = str(len(reads)).encode(); bodies[data] = values[self.root, name]
            return data
        def check(self, *, check):
            check()
        def close(self):
            closes.append(self.root)
            if cleanup_failure == "held": raise OSError("PRIVATE")
    class Guard(_Guard):
        def close(self):
            if cleanup_failure == "guard": raise OSError("PRIVATE")
    class Chain:
        def __init__(self, *_): pass
        def close(self): pass
    monkeypatch.setattr(m, "Held", Held)
    monkeypatch.setattr(m, "decode", lambda body, _pin: bodies[body])
    monkeypatch.setattr(m, "_source_current", lambda _identity: None)
    monkeypatch.setattr(m.stable.native, "_isolated", lambda: None)
    monkeypatch.setattr(m.stable.native.batch.campaign.base, "_prove_isolation", lambda: None)
    monkeypatch.setattr(m.stable.native, "_WorkerMemoryGuard", Guard)
    monkeypatch.setattr(m.stable, "_HeldChain", Chain)
    monkeypatch.setattr(m.stable, "_managed", lambda _held: None)
    monkeypatch.setattr(m.stable, "_storage_identity", lambda *_a, **_k: physical)
    if cleanup_failure:
        with pytest.raises(SystemExit) as caught:
            m.storage_diagnostic_worker(IDENTITY)
        assert caught.value.code == 2
    else:
        m.storage_diagnostic_worker(IDENTITY)
    wire = capsysbinary.readouterr().out
    assert b"PRIVATE" not in wire and len(reads) == 3 and set(closes) == {m.PROVIDER, m.PROOF}
    value = json.loads(wire)["value"]
    assert value["completed"] is value["diagnostic_only"] is True
    assert value["binding_passed"] is False and value["actual_input_leaves"] == 3
    if cleanup_failure:
        with pytest.raises(m.stable.source.FirstRateQualificationError):
            m.stable.source._ipc_result(wire, b"", 2)


@pytest.mark.parametrize(("field", "value"), (("schema", "invented"), ("root_kind", "fixture"), ("mode", 0o755),
    ("owner", os.geteuid() + 1 if hasattr(os, "geteuid") else 1), ("inode", 0), ("device", -1), ("group", "20")))
def test_current_storage_identity_fields_are_each_required(field, value):
    physical, proof, qualification = _storage()
    changed = {**physical, field: value}
    # The stored proofs agree with the changed value, so only the field rule can refuse it.
    proof["storage_identity"] = dict(changed)
    qualification["storage_identity"] = dict(changed)
    with pytest.raises(m.AuditRunnerError, match="storage_identity_refused"):
        m.storage_binding(changed, proof, qualification)


def test_unexpected_failure_code_is_reported_as_unknown():
    assert m.failure_info("derive", m.AuditRunnerError("PRIVATE VALUE"))["refusal_code"] == "unknown"
    assert m.failure_info("derive", m.audit.PitRetainedAuditError("row_limit_refused"))["refusal_code"] == "row_limit_refused"
    assert m.failure_info("derive", OSError(999, "PRIVATE"))["os_errno"] is None
    # A foreign exception whose text happens to equal a safe code is still not an own refusal.
    assert m.failure_info("derive", ValueError("row_limit_refused"))["refusal_code"] == "unknown"
