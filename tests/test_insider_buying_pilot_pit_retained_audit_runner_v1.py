"""Invented pinned metadata only; native denial is required by the caller."""
from copy import deepcopy
import hashlib
import os
from pathlib import Path

import pytest

pytest.importorskip("fcntl", reason="supported macOS/POSIX retained-metadata audit")
from research import insider_buying_pilot_pit_retained_audit_runner_v1 as m


def pin(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def test_pin_is_authenticated_before_json_decode(monkeypatch):
    monkeypatch.setattr(m.json, "loads", lambda *_a, **_k: pytest.fail("decode before pin"))
    with pytest.raises(m.AuditRunnerError, match="input_pin_refused"):
        m.decode(b'{"invented":1}', {"bytes": 14, "sha256": "1" * 64})


@pytest.mark.parametrize("data", (b'{"a":1,"a":2}', b'{"x":NaN}', b'{ "a":1}', b'[]', b'{"x":Infinity}'))
def test_strict_json_rejects_duplicate_nonfinite_noncanonical_or_wrong_root(data):
    with pytest.raises(m.AuditRunnerError):
        m.decode(data, pin(data))


@pytest.mark.parametrize("value", (False, 0, -1, 2**30, 1.0))
def test_pin_size_requires_a_bounded_exact_integer(value):
    with pytest.raises(m.AuditRunnerError):
        m.decode(b"{}", {"bytes": value, "sha256": hashlib.sha256(b"{}").hexdigest()})


def test_private_fixture_reader_hashes_and_rechecks_retained_bytes(tmp_path):
    root = tmp_path / "invented"; root.mkdir(mode=0o700)
    data = m.raw({"invented": "metadata"})
    leaf = root / "complete.json"; leaf.write_bytes(data); leaf.chmod(0o600)
    pulses = []
    held = m.Held(root, fixture=True)
    try:
        assert held.read("complete.json", pin(data), check=lambda: pulses.append(1)) == data
        held.check(check=lambda: pulses.append(1))
        assert pulses
        leaf.write_bytes(data.replace(b"metadata", b"changed!"))
        with pytest.raises(m.AuditRunnerError, match="input_changed"):
            held.check(check=lambda: None)
    finally:
        held.close()


@pytest.mark.parametrize("fault", ("symlink", "hardlink", "permissions", "hash"))
def test_private_fixture_reader_refuses_unsafe_or_unbound_leaf(tmp_path, fault):
    root = tmp_path / "invented"; root.mkdir(mode=0o700)
    data = b'{"invented":true}'
    source = root / "source.json"; source.write_bytes(data); source.chmod(0o600)
    leaf = root / "complete.json"
    if fault == "symlink":
        leaf.symlink_to(source)
    elif fault == "hardlink":
        os.link(source, leaf)
    else:
        leaf.write_bytes(data); leaf.chmod(0o644 if fault == "permissions" else 0o600)
    held = m.Held(root, fixture=True)
    try:
        supplied = pin(data)
        if fault == "hash": supplied["sha256"] = "f" * 64
        with pytest.raises((m.AuditRunnerError, OSError)):
            held.read("complete.json", supplied, check=lambda: None)
    finally:
        held.close()


def test_actual_reader_accepts_only_fixed_roots_and_fixture_excludes_actual_root():
    with pytest.raises(m.AuditRunnerError, match="input_root_refused"):
        m.Held(Path("/private/tmp"))
    with pytest.raises(m.AuditRunnerError, match="input_root_refused"):
        m.Held(m.ROOT, fixture=True)


class FixtureHeld:
    def __init__(self, value):
        self.data = m.raw(value); self.checked = 0
    def read(self, name, supplied, *, check):
        check(); return self.data
    def check(self, *, check):
        check(); self.checked += 1


def projection():
    return {"schema": m.reference.TICKERS_SCHEMA, "capture_manifest_sha256": m.MANIFEST,
            "archive_sha256": "1" * 64, "member_sha256": "2" * 64,
            "columns": list(m.reference.TICKER_COLUMNS),
            "rows": [{"source_row_ordinal": 1, **dict.fromkeys(m.reference.TICKER_COLUMNS, "")} ]}


def rows(value):
    held = FixtureHeld(value)
    result = list(m.projection(held, "tickers_projection.json", pin(held.data),
        columns=m.reference.TICKER_COLUMNS, schema=m.reference.TICKERS_SCHEMA,
        count=1, check=lambda: None))
    return result, held


def test_projection_conserves_rows_and_runs_final_recheck():
    value = projection(); result, held = rows(value)
    assert result == value["rows"] and held.checked == 1


@pytest.mark.parametrize("fault", ("manifest", "columns", "schema", "count", "ordinal", "field", "extra", "financial"))
def test_projection_bindings_and_every_row_shape_are_required(fault):
    value = projection()
    if fault == "manifest": value["capture_manifest_sha256"] = "0" * 64
    elif fault == "columns": value["columns"] = value["columns"][::-1]
    elif fault == "schema": value["schema"] = "invented"
    elif fault == "count": value["rows"] = []
    elif fault == "ordinal": value["rows"][0]["source_row_ordinal"] = True
    elif fault == "field": value["rows"][0]["ticker"] = 1
    elif fault == "extra": value["new"] = True
    else: value["rows"][0]["price"] = "PRIVATE FINANCIAL SENTINEL"
    with pytest.raises(m.AuditRunnerError): rows(value)


def test_actual_policy_has_exact_data_leaves_and_native_denials():
    policy = m.policy(sources=m.OWN)
    assert "(deny network*)" in policy and "(deny process-fork)" in policy
    assert "(deny process-exec)" in policy and "(deny file-write*)" in policy
    assert "(deny file-read-data)" in policy
    assert len(m.fixed_input_paths()) == 7
    assert all('(literal "' + str(path) + '")' in policy for path in m.fixed_input_paths())
    assert '(subpath "' + str(m.ROOT) + '")' not in policy
    assert '(subpath "' + str(m.ROOT / "artifacts") + '")' not in policy
    assert '(subpath "' + str(m.stable.PRIVATE_CUSTODY_ROOT) + '")' not in policy
    assert '(subpath "/Volumes")' not in policy


@pytest.mark.parametrize("name", ("../outside.py", "/outside.py", "artifacts/private.json", "research/../outside.py"))
def test_source_allowlist_cannot_escape_to_other_data(name):
    with pytest.raises(m.AuditRunnerError): m.policy(sources=[name])


@pytest.mark.parametrize("name", ("baskets.py", "config.py", "market_analytics.py", "signals/common.py"))
def test_identity_bound_python_closure_uses_exact_leaves_without_whole_directory_grants(name):
    policy = m.policy(sources=[name])
    assert '(literal "' + str(m.ROOT / name) + '")' in policy
    assert '(subpath "' + str(m.ROOT) + '")' not in policy


def test_source_check_does_not_accept_a_self_asserted_positive_inventory():
    with pytest.raises(m.AuditRunnerError, match="source_refused"):
        m._source_current({"head": "1" * 40, "sources": {}, "source_inventory_sha256": "f" * 64})


def storage():
    physical = {"schema": m.stable.SCHEMA + "/storage-identity", "root_kind": "fixed_user_application_support",
                "device": 1, "inode": 2, "mode": 0o700, "owner": os.geteuid(), "group": 20}
    proof = {"passed": True, "fixture_only": False, "storage_identity": deepcopy(physical)}
    qualification = {**deepcopy(proof), "receipt_sha256": m.PINS["proof_complete"]["sha256"]}
    return physical, proof, qualification


def test_readonly_audit_requires_both_historical_and_current_physical_bindings():
    m.storage_binding(*storage())


@pytest.mark.parametrize("fault", ("moved-root", "missing-root", "wrong-proof", "fixture-proof", "not-passed", "bool-alias"))
def test_copied_or_missing_custody_identity_cannot_supply_a_readonly_audit(fault):
    physical, proof, qualification = storage()
    if fault == "moved-root": physical["inode"] += 1
    elif fault == "missing-root": qualification.pop("storage_identity")
    elif fault == "wrong-proof": qualification["receipt_sha256"] = "0" * 64
    elif fault == "fixture-proof": proof["fixture_only"] = True
    elif fault == "not-passed": qualification["passed"] = False
    else: proof["storage_identity"]["device"] = True
    with pytest.raises(m.AuditRunnerError, match="storage_identity_refused"):
        m.storage_binding(physical, proof, qualification)


def test_parent_never_runs_worker_before_clean_committed_identity(monkeypatch):
    monkeypatch.setattr(m, "_identity", lambda *_: (_ for _ in ()).throw(m.AuditRunnerError("source_refused")))
    monkeypatch.setattr(m.stable.source, "_launch", lambda *_a, **_k: pytest.fail("worker activated"))
    with pytest.raises(m.AuditRunnerError, match="source_refused"):
        m.run_actual("1" * 40)
