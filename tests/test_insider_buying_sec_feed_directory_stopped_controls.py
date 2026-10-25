"""Invented stopped metadata only; never reads the actual consumed namespace."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fcntl", reason="macOS/POSIX custody support")
pytest.importorskip("termios", reason="macOS/POSIX original private-contact module")
from research import insider_buying_sec_feed_directory_stopped_controls as m


def _old_identity(count=102):
    sources = {m.original.SELF_PATH: m.FAILED_SOURCE_SHA256, m.original.TEST_PATH: m.FAILED_TEST_SHA256,
        **{f"research/invented_{i:03}.py": m._sha(b"# invented source") for i in range(count - 2)}}
    return {"root": str(m.LANE_ROOT), "branch": m.LANE_BRANCH, "head": m.FAILED_HEAD, "clean": True,
        "source_sha256": sources, "source_inventory_sha256": m._sha(m._raw(sources))}


def _controls(count=102, *, reservation_bytes=None):
    identity = _old_identity(count)
    if reservation_bytes is not None:
        extra = reservation_bytes - len(m._raw(m.original._reservation(identity, False)))
        assert extra >= 0
        for name in tuple(identity["source_sha256"]):
            if not name.startswith("research/invented_"): continue
            amount = min(extra, 512-len(name))
            identity["source_sha256"][name[:-3] + "_"*amount + ".py"] = identity["source_sha256"].pop(name)
            extra -= amount
            if not extra: break
        assert extra == 0
        identity["source_inventory_sha256"] = m._sha(m._raw(identity["source_sha256"]))
    reservation = m._raw(m.original._reservation(identity, False)); rsha = m._sha(reservation)
    claim = m._raw({"schema": m.original.SCHEMA+"/url-claim", "method": "GET", "url": m.original.URL,
        "scope_sha256": m.FAILED_SCOPE_SHA256, "reservation_sha256": rsha})
    result = {"scope.lock": m.original.LOCK_BYTES, "reservation.json": reservation, "claim.json": claim,
        "request-start.json": m._raw({"schema": m.original.SCHEMA+"/start", "scope_sha256": m.FAILED_SCOPE_SHA256,
            "reservation_sha256": rsha, "claim_sha256": m._sha(claim), "attempt": 1}),
        "contact-validated.json": m._raw({"schema": m.original.SCHEMA+"/contact", "reservation_sha256": rsha,
            "contact_present": True, "contact_value_stored_or_hashed": False})}
    if reservation_bytes is not None: assert len(reservation) == reservation_bytes
    return result


def _current_identity():
    sources = {m.SELF_PATH: "a"*64, m.TEST_PATH: "b"*64, m.original.SELF_PATH: m.FAILED_SOURCE_SHA256}
    return {"root": str(m.LANE_ROOT), "branch": m.LANE_BRANCH, "head": "c"*40, "clean": True,
        "source_sha256": sources, "source_inventory_sha256": m._sha(m._raw(sources))}


def _report(controls=None, identity=None):
    controls = _controls(reservation_bytes=m.OBSERVED_RESERVATION_BYTES) if controls is None else controls
    identity = _current_identity() if identity is None else identity
    diagnostic = m.diagnose_controls(controls, expected_reservation_bytes=len(controls["reservation.json"]))
    return {"schema": m.SCHEMA, "audit_id": m.AUDIT_ID, "registration": copy.deepcopy(m.REGISTRATION),
        "registration_sha256": m._sha(m._raw(m.REGISTRATION)), "execution_identity": identity,
        "original_control_pins": {name: {"sha256": m._sha(raw), "bytes": len(raw)} for name, raw in controls.items()},
        "original_control_witness": {name: raw.hex() for name, raw in controls.items()},
        "diagnostic": diagnostic, "diagnostic_sha256": m._sha(m._raw(diagnostic)),
        "native_network_fork_allwrite_securityexec_denial": True, "new_provider_requests": 0,
        "credential_reads": 0, "qc_accesses": 0, "outcome_looks": 0, "backtests": 0,
        "original_namespace_mutated": False, "persistent_result_published": False,
        "source_authenticated_here": False, "canonical_admitted": False, "backtesting_ready": False}


def _diagnose(controls): return m.diagnose_controls(controls, expected_reservation_bytes=len(controls["reservation.json"]))


@pytest.mark.parametrize("count", (31, 32, 33, 102))
def test_production_sized_controls_reproduce_old_limit_without_editing_old_decoder(count):
    controls = _controls(count); result = _diagnose(controls)
    assert result["original_source_count"] == count
    expected = None if count <= 32 else "json_resource_bound_refused"
    assert result["original_decoder_refusal_code"] == expected
    assert result["code_derived_reservation_decode_blocks_raw_transport"] is (expected is not None)
    assert result["invented_102_source_decoder_refusal_code"] == "json_resource_bound_refused"
    assert result["measured_original_http_request_count"] is result["measured_original_transferred_bytes"] is None
    assert not result["retry_authorized"] and not result["original_observation_replaced"]
    assert result["no_http_result_or_body_retained"] is True
    assert all(value is False or type(value) is int and value == 0 for value in result["authority"].values())


def test_own_control_bound_is_distinct_from_unchanged_foreign_profile():
    raw = m._raw({str(i): i for i in range(33)})
    assert len(m._decode_control(raw)) == 33
    with pytest.raises(m.original.FeedDirectoryError, match="json_resource_bound_refused"):
        m.original._decode(raw)


@pytest.mark.parametrize("raw", (b'{"x":0,"x":0}', b'{"x":NaN}', b'{"x":0.2}', b'not json',
    b'{ "x":0}', b'{"x":'+b'['*30+b'0'+b']'*30+b'}', b'{"x":"'+b'x'*16385+b'"}',
    b'{}'+b' '*m.MAX_CONTROL_BYTES))
def test_own_control_duplicate_nonfinite_noncanonical_and_resource_bounds(raw):
    with pytest.raises(m.StoppedControlError): m._decode_control(raw)


@pytest.mark.parametrize("fault", ("lock", "extra", "missing", "reservation_size", "fixture", "audit", "scope", "head",
    "source", "inventory_digest", "claim_url", "claim_link", "start_attempt", "start_link", "contact_bool", "contact_extra"))
def test_raw_control_schema_and_all_links_refuse_coherent_forgeries(fault):
    controls = _controls()
    if fault == "lock": controls["scope.lock"] += b"x"
    elif fault == "extra": controls["complete.json"] = b"{}"
    elif fault == "missing": del controls["claim.json"]
    elif fault == "reservation_size":
        with pytest.raises(m.StoppedControlError):
            m.diagnose_controls(controls, expected_reservation_bytes=True)
        return
    else:
        key = "reservation.json" if fault in {"fixture", "audit", "scope", "head", "source", "inventory_digest"} else (
            "claim.json" if fault.startswith("claim") else "request-start.json" if fault.startswith("start") else "contact-validated.json")
        value = json.loads(controls[key])
        if fault == "fixture": value["fixture_only"] = 0
        elif fault == "audit": value["audit_id"] += "-alias"
        elif fault == "scope": value["scope_sha256"] = "0"*64
        elif fault == "head": value["execution_identity"]["head"] = "0"*40
        elif fault == "source":
            value["execution_identity"]["source_sha256"][m.original.SELF_PATH] = "0"*64
            value["execution_identity"]["source_inventory_sha256"] = m._sha(m._raw(value["execution_identity"]["source_sha256"]))
        elif fault == "inventory_digest": value["execution_identity"]["source_inventory_sha256"] = "0"*64
        elif fault == "claim_url": value["url"] += "?alias=1"
        elif fault in {"claim_link", "start_link"}: value["reservation_sha256"] = "0"*64
        elif fault == "start_attempt": value["attempt"] = True
        elif fault == "contact_bool": value["contact_present"] = 1
        else: value["contact"] = "must never be accepted"
        controls[key] = m._raw(value)
    with pytest.raises(m.StoppedControlError): _diagnose(controls)


def test_real_size_metadata_witness_roundtrips_before_parent_strip():
    result = _report(); identity = result["execution_identity"]
    assert result["original_control_pins"]["reservation.json"]["bytes"] == 14281
    assert len(result["original_control_witness"]["reservation.json"]) == 28562
    encoded = m._raw(result)
    assert m._validate(m._decode_control(encoded, ipc=True), identity) == result
    with pytest.raises(m.StoppedControlError, match="control_string_bound"): m._decode_control(encoded)


@pytest.mark.parametrize("fault", ("bool_count", "authority_int", "native_int", "pin", "pin_bool", "diagnostic", "diagnostic_bool",
    "witness", "extra", "registration", "identity"))
def test_full_result_schema_witness_and_canonical_typed_crosslinks(fault):
    result = _report(); identity = copy.deepcopy(result["execution_identity"])
    if fault == "bool_count": result["credential_reads"] = False
    elif fault == "authority_int": result["backtesting_ready"] = 0
    elif fault == "native_int": result["native_network_fork_allwrite_securityexec_denial"] = 1
    elif fault == "pin": result["original_control_pins"]["reservation.json"]["sha256"] = "0"*64
    elif fault == "pin_bool": result["original_control_pins"]["scope.lock"]["bytes"] = True
    elif fault in {"diagnostic", "diagnostic_bool"}:
        result["diagnostic"]["measured_original_http_request_count" if fault == "diagnostic" else "retry_authorized"] = 0
        result["diagnostic_sha256"] = m._sha(m._raw(result["diagnostic"]))
    elif fault == "witness": result["original_control_witness"]["reservation.json"] += "00"
    elif fault == "extra": result["extra"] = None
    elif fault == "registration": result["registration"]["original_namespace_mutated"] = 0
    else: result["execution_identity"]["clean"] = 1
    with pytest.raises(m.StoppedControlError): m._validate(result, identity)


def _seed(root, controls=None):
    controls = _controls() if controls is None else controls
    base = root.joinpath(*m.original.ARTIFACT_PARTS); run = base/"runs"/m.original.AUDIT_ID; claims = base/"claims"
    run.mkdir(parents=True, mode=0o700); claims.mkdir(mode=0o700)
    for path in (root/"artifacts", root/"artifacts"/"insider_buying", base, base/"runs", run, claims): path.chmod(0o700)
    paths = {"scope.lock": base/"scope.lock", "claim.json": claims/m.original._claim_name(),
        **{name: run/name for name in m.RUN_NAMES}}
    for name, path in paths.items(): path.write_bytes(controls[name]); path.chmod(0o600)
    return paths


def test_strict_held_five_leaf_inventory_and_readonly_recheck(tmp_path):
    paths = _seed(tmp_path); before = {name: path.read_bytes() for name, path in paths.items()}
    held = m._HeldStopped(tmp_path, fixture=True)
    try:
        assert held.controls == before; held.recheck()
        assert len(held.controls) == 5 and _diagnose(held.controls)["original_source_count"] == 102
    finally: held.close()
    assert {name: path.read_bytes() for name, path in paths.items()} == before


@pytest.mark.parametrize("fault", ("extra", "missing", "symlink", "hardlink", "mode", "inode", "ctime", "bytes"))
def test_stopped_intake_never_settles_old_source_custody_changes(tmp_path, fault):
    paths = _seed(tmp_path); path = paths["reservation.json"]
    if fault in {"extra", "missing", "symlink", "hardlink", "mode"}:
        if fault == "extra": (path.parent/"complete.json").write_bytes(b"{}"); (path.parent/"complete.json").chmod(0o600)
        elif fault == "missing": path.unlink()
        elif fault == "symlink": path.unlink(); path.symlink_to(paths["request-start.json"])
        elif fault == "hardlink": os.link(path, tmp_path/"extra-hardlink")
        else: path.chmod(0o644)
        with pytest.raises(ValueError): m._HeldStopped(tmp_path, fixture=True)
        return
    held = m._HeldStopped(tmp_path, fixture=True)
    try:
        prior = path.stat(); raw = path.read_bytes()
        if fault == "inode":
            other = tmp_path/"replacement"; other.write_bytes(raw); other.chmod(0o600)
            os.utime(other, ns=(prior.st_atime_ns, prior.st_mtime_ns)); other.replace(path)
        elif fault == "ctime":
            path.chmod(0o640); path.chmod(0o600)
        else:
            path.write_bytes(raw.replace(b'"clean":true', b'"clean":null'))
            os.utime(path, ns=(prior.st_atime_ns, prior.st_mtime_ns))
        with pytest.raises(ValueError): held.recheck()
    finally: held.close()


def test_actual_fixture_boundary_and_native_flags_precede_any_namespace_read(monkeypatch):
    monkeypatch.setattr(m.base.custody, "_Inputs", lambda *a: pytest.fail("no real namespace reader"))
    with pytest.raises(ValueError): m._HeldStopped(m.LANE_ROOT, fixture=True)
    monkeypatch.setattr(m, "sys", SimpleNamespace(flags=SimpleNamespace(isolated=1,no_site=0,no_user_site=1,dont_write_bytecode=1),
        pycache_prefix=m.EMPTY_CACHE_PREFIX))
    with pytest.raises(m.StoppedControlError, match="isolated"): m._HeldStopped()


def test_worker_source_failure_precedes_held_artifacts(monkeypatch):
    monkeypatch.setattr(m, "_isolated", lambda: None)
    monkeypatch.setattr(m.base, "_prove_isolation", lambda: None)
    monkeypatch.setattr(m, "_current_sources", lambda _: (_ for _ in ()).throw(m.StoppedControlError("invented_source_change")))
    monkeypatch.setattr(m, "_HeldStopped", lambda *a,**k: pytest.fail("must not open artifacts"))
    with pytest.raises(m.StoppedControlError, match="invented_source_change"): m._worker(_current_identity())


def test_fixed_worker_command_initial_native_controls_and_no_contact_transport_api():
    command = m._command(_current_identity())
    assert command[:4] == ("/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "/usr/bin/sandbox-exec")
    assert all(value in command for value in ("-I", "-S", "-B", "pycache_prefix="+m.EMPTY_CACHE_PREFIX))
    policy = command[5]
    assert all(value in policy for value in ("(deny network*)", "(deny process-fork)", "(deny file-write*)", "/usr/bin/security"))
    code = command[-1]
    assert "m._worker(identity)" in code and "run_actual_probe" not in code and "contact" not in code and "transport" not in code


def test_parent_preflight_failure_does_not_launch_worker(monkeypatch):
    monkeypatch.setattr(m, "_committed_identity", lambda _: (_ for _ in ()).throw(m.StoppedControlError("invented_uncommitted_source")))
    monkeypatch.setattr(m.base.launcher, "run_child", lambda *a,**k: pytest.fail("no worker before committed identity"))
    with pytest.raises(m.StoppedControlError): m.run_actual_diagnostic("c"*40)


def test_parent_guard_permits_only_pinned_failed_commit_source_readback():
    guard = m._Guard("c"*40, m._command(_current_identity()))
    command = ("/usr/bin/git", "show", m.FAILED_HEAD+":"+m.original.SELF_PATH)
    assert guard._git("/usr/bin/git", command, m.LANE_ROOT, {"PATH":"/usr/bin:/bin"})
    for target in ("d"*40+":"+m.original.SELF_PATH, m.FAILED_HEAD+":../outside.py", m.FAILED_HEAD+":credentials.txt"):
        assert not guard._git("/usr/bin/git", ("/usr/bin/git","show",target),m.LANE_ROOT,{"PATH":"/usr/bin:/bin"})


def test_cli_refusal_has_fixed_exit2_without_private_exception(monkeypatch,capsys):
    monkeypatch.setattr(m,"run_actual_diagnostic",lambda *a: (_ for _ in ()).throw(ValueError("PRIVATE")))
    assert m.main(["--expected-head","c"*40]) == 2
    assert capsys.readouterr().out == '{"disposition":"stopped_control_diagnostic_refused"}\n'
