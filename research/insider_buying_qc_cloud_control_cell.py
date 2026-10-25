"""Prepare one control-only QC cell; never upload, execute or access QC here.

The fixed cloud cell checks one exact own key, then makes at most one save.
ObjectStore has no documented atomic create-only operation: this precheck is
not CAS and the local one-shot intent is not a claim of cloud immutability.
Only own execution acknowledgements may leave the cell, never stored content.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import sys

from research import insider_buying_pilot_sec_parent_capture as publication
from research import insider_buying_pilot_sec_parent_audit_runner as sources
from research import insider_buying_sec_feed_directory_stopped_controls as codec


SELF_PATH = "research/insider_buying_qc_cloud_control_cell.py"
TEST_PATH = "tests/test_insider_buying_qc_cloud_control_cell.py"
SCHEMA = "insider-qc-cloud-control-cell-v1"
AUDIT_ID = "ib-qc-cloud-control-20261025-once"
PROJECT_ID = 37465795
NOTEBOOK = "ib_qc_cloud_control_20261025.ipynb"
ARTIFACT_PARTS = ("artifacts", "insider_buying", "qc_cloud_control_v1")
LANE_ROOT, LANE_BRANCH = sources.LANE_ROOT, sources.LANE_BRANCH
EMPTY_CACHE_PREFIX = "/var/empty/insider-qc-cloud-control-no-bytecode"
MAX_CONTROL_BYTES, MAX_CELL_BYTES = 256 * 1024, 32 * 1024
LOCK_BYTES = b"INSETF-QC-own-control-cell-permanently-claimed-v1\n"
_SHA, _HEAD = re.compile(r"[0-9a-f]{64}\Z"), re.compile(r"[0-9a-f]{40}\Z")
_SOURCE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_][A-Za-z0-9_.-]*)*\.py\Z")
_raw, _sha = publication._raw, publication._sha


class CloudControlError(ValueError):
    """Fixed local codes only, never SDK messages or cloud content."""


def _need(value, code):
    if not value:
        raise CloudControlError(code)


# This generic core has no hash of its own bytes or of the final cell. The
# registration binds CORE_SHA256; the external local intent binds final bytes.
# Imports, construction and SDK calls are inside discard-only stdout/stderr
# contexts. Managed/runtime output outside Python redirection is not certified.
CORE_SOURCE = '''def _ib_control_run(_qb_factory, _registration_text, _expected_registration_sha256):
    import contextlib
    import hashlib
    import json
    class _Discard:
        def write(self, value):
            return len(value)
        def flush(self):
            return None
    def _canonical(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    _ack = {"schema":"insider-qc-cloud-control-cell-v1/acknowledgement", "disposition":"registration_refused"}
    try:
        _r = json.loads(_registration_text)
        if (type(_r) is not dict or _canonical(_r) != _registration_text
                or hashlib.sha256(_registration_text.encode()).hexdigest() != _expected_registration_sha256
                or set(_r) != {"schema","audit_id","project_id","notebook","cell_index","key","nonce","fixture_only","core_sha256","payload_text","scope"}
                or _r["schema"] != "insider-qc-cloud-control-cell-v1/registration"
                or _r["audit_id"] != "ib-qc-cloud-control-20261025-once"
                or type(_r["project_id"]) is not int or _r["project_id"] != 37465795
                or _r["notebook"] != "ib_qc_cloud_control_20261025.ipynb"
                or type(_r["cell_index"]) is not int or _r["cell_index"] != 0
                or type(_r["fixture_only"]) is not bool
                or type(_r["nonce"]) is not str or len(_r["nonce"]) != 64
                or any(c not in "0123456789abcdef" for c in _r["nonce"])
                or type(_r["core_sha256"]) is not str or len(_r["core_sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in _r["core_sha256"])
                or _r["key"] != "37465795/ib-qc-cloud-control-20261025-once/" + _r["nonce"] + "/control.json"
                or _canonical(_r["scope"]) != _canonical({"exact_own_key_prechecks":1,"maximum_saves":1,"reads_downloads_lists_deletes":0,"dataset_or_history_calls":0,"jobs_backtests":0,"atomic_create_or_immutability_guaranteed":False})
                or _r["payload_text"] != _canonical({"schema":"insider-qc-cloud-control-cell-v1/own-control","audit_id":_r["audit_id"],"core_sha256":_r["core_sha256"],"purpose":"own-control-only; no data values"})):
            raise ValueError()
        _ack = {"schema":"insider-qc-cloud-control-cell-v1/acknowledgement", "audit_id":_r["audit_id"],
            "project_id":_r["project_id"], "notebook":_r["notebook"], "cell_index":0,
            "key":_r["key"], "registration_sha256":_expected_registration_sha256,
            "core_sha256":_r["core_sha256"], "fixture_only":_r["fixture_only"],
            "disposition":"cloud_control_refused", "own_key_precheck_invocations":0,
            "save_invocations":0, "save_returned_true":None,
            "object_store_contents_exported":False, "independent_stored_bytes_verified":False,
            "atomic_create_or_immutability_guaranteed":False, "dataset_or_history_calls":0,
            "jobs_backtests":0, "backtesting_ready":False}
        _marker = "_ib_qc_cloud_control_claim_" + _r["nonce"]
        if _marker in globals():
            _ack["disposition"] = "kernel_claim_already_consumed"
        else:
            globals()[_marker] = True
            with contextlib.redirect_stdout(_Discard()), contextlib.redirect_stderr(_Discard()):
                _qb = _qb_factory()
                if type(_qb.project_id) is not int or _qb.project_id != 37465795:
                    _ack["disposition"] = "project_mismatch"
                else:
                    _store = _qb.object_store
                    _ack["own_key_precheck_invocations"] = 1
                    _exists = _store.contains_key(_r["key"])
                    if type(_exists) is not bool:
                        _ack["disposition"] = "own_key_precheck_nonboolean"
                    elif _exists:
                        _ack["disposition"] = "own_key_already_exists_no_save"
                    else:
                        _ack["save_invocations"] = 1
                        _saved = _store.save(_r["key"], _r["payload_text"])
                        if type(_saved) is not bool:
                            _ack["disposition"] = "save_nonboolean_no_retry"
                        else:
                            _ack["save_returned_true"] = _saved
                            _ack["disposition"] = "save_acknowledged_true" if _saved else "save_acknowledged_false_no_retry"
    except BaseException:
        # The local intent and kernel marker remain consumed. Never print a
        # foreign exception, object repr, trace, stored value or contents hash.
        if _ack["disposition"] != "registration_refused":
            _ack["disposition"] = "cloud_control_exception_no_retry"
    print(_canonical(_ack))
'''
CORE_SHA256 = _sha(CORE_SOURCE.encode())


def _scope():
    return {"exact_own_key_prechecks": 1, "maximum_saves": 1, "reads_downloads_lists_deletes": 0,
        "dataset_or_history_calls": 0, "jobs_backtests": 0, "atomic_create_or_immutability_guaranteed": False}


def _registration(nonce, fixture):
    _need(type(nonce) is str and _SHA.fullmatch(nonce) and type(fixture) is bool, "control_nonce_or_mode_refused")
    return {"schema": SCHEMA + "/registration", "audit_id": AUDIT_ID, "project_id": PROJECT_ID,
        "notebook": NOTEBOOK, "cell_index": 0, "key": f"{PROJECT_ID}/{AUDIT_ID}/{nonce}/control.json",
        "nonce": nonce, "fixture_only": fixture, "core_sha256": CORE_SHA256,
        "payload_text": _raw({"schema": SCHEMA + "/own-control", "audit_id": AUDIT_ID,
            "core_sha256": CORE_SHA256, "purpose": "own-control-only; no data values"}).decode(), "scope": _scope()}


def _cell(nonce, fixture):
    registration_raw = _raw(_registration(nonce, fixture)); digest = _sha(registration_raw)
    wrapper = ("\ndef _ib_quantbook_factory():\n    from QuantConnect.Research import QuantBook\n    return QuantBook()\n"
        + "_ib_control_run(_ib_quantbook_factory, " + repr(registration_raw.decode()) + ", " + repr(digest) + ")\n")
    raw = (CORE_SOURCE + wrapper).encode()
    _need(0 < len(raw) <= MAX_CELL_BYTES, "control_cell_bound_refused")
    compile(raw, "<fixed-qc-own-control-cell>", "exec")
    return registration_raw, raw


def build_invented_cell(nonce):
    """Same generated core with fixture_only=True; no SDK import or execution."""
    return _cell(nonce, True)


def _decode(raw):
    try:
        return codec._decode_control(raw)
    except codec.StoppedControlError:
        raise CloudControlError("own_control_codec_refused") from None


def _source_identity(value, root):
    _need(type(value) is dict and set(value) == {"root", "branch", "head", "clean", "source_sha256", "source_inventory_sha256"}
        and value["root"] == str(root) and value["branch"] == LANE_BRANCH and value["clean"] is True
        and type(value["head"]) is str and _HEAD.fullmatch(value["head"])
        and type(value["source_sha256"]) is dict and 2 <= len(value["source_sha256"]) <= 2048
        and {SELF_PATH, TEST_PATH} <= set(value["source_sha256"])
        and all(type(name) is str and len(name) <= 512 and _SOURCE.fullmatch(name)
            and Path(name).as_posix() == name and ".." not in Path(name).parts
            and type(digest) is str and _SHA.fullmatch(digest) for name, digest in value["source_sha256"].items())
        and value["source_inventory_sha256"] == _sha(_raw(value["source_sha256"])), "cloud_control_source_identity_refused")
    return value


def _identity(head):
    _need(Path(__file__).resolve() == LANE_ROOT / SELF_PATH, "fixed_cloud_control_source_required")
    identity = sources.custody._identity(head)
    own = sources.custody._source_bytes(LANE_ROOT, (SELF_PATH, TEST_PATH))
    for name, digest in own.items():
        _need(_sha(sources.custody._git(LANE_ROOT, "show", head + ":" + name)) == digest, "uncommitted_cloud_control_source")
    inventory = {**identity["source_sha256"], **own}
    value = _source_identity({**identity, "source_sha256": inventory,
        "source_inventory_sha256": _sha(_raw(inventory))}, LANE_ROOT)
    _current(value)
    return value


def _current(identity):
    _source_identity(identity, LANE_ROOT)
    _need(set(sources.custody._internal_source_paths(LANE_ROOT)) <= set(identity["source_sha256"]), "cloud_control_loaded_closure_missing")
    _need(sources.custody._source_bytes(LANE_ROOT, tuple(identity["source_sha256"])) == identity["source_sha256"]
        and sources.custody._source_bytes(LANE_ROOT, tuple(sources.FROZEN)) == sources.FROZEN, "cloud_control_current_or_frozen_source_changed")


def _intent(identity, registration_raw, cell_raw, proof, fixture):
    registration = _decode(registration_raw)
    return {"schema": SCHEMA + "/permanent-local-intent", "audit_id": AUDIT_ID, "fixture_only": fixture,
        "execution_identity": identity, "registration_sha256": _sha(registration_raw),
        "core_sha256": CORE_SHA256, "cell_sha256": _sha(cell_raw), "cell_bytes": len(cell_raw),
        "project_id": PROJECT_ID, "notebook": NOTEBOOK, "cell_index": 0, "key": registration["key"],
        "source_preflight": proof, "local_scope_permanently_consumed": True,
        "maximum_selected_cell_executions": 1, "no_retry_even_after_kernel_reset": True,
        "cloud_execution_observed": False, "cloud_or_credential_accesses_by_preparer": 0,
        "object_store_immutability_or_atomic_create_claimed": False, "backtesting_ready": False}


def _proof(identity, fixture):
    return {"schema": SCHEMA + "/source-preflight", "fixture_only": fixture,
        "source_inventory_sha256": identity["source_inventory_sha256"], "source_count": len(identity["source_sha256"]),
        "initial_native_network_fork_allwrite_securityexec_denial": not fixture,
        "current_frozen_and_loaded_sources_verified": not fixture, "qc_or_credential_accesses": 0}


def _capacity(identity, fixture):
    _source_identity(identity, Path(identity["root"]))
    registration_raw, cell_raw = _cell("0" * 64, fixture)
    # Unpublished, synthetic capacity specimen, never an observed nonce/run.
    for value in (identity, _registration("0" * 64, fixture), _intent(identity, registration_raw, cell_raw, _proof(identity, fixture), fixture)):
        raw = _raw(value)
        _need(0 < len(raw) <= MAX_CONTROL_BYTES and _raw(_decode(raw)) == raw, "cloud_control_capacity_refused")


def _worker(identity):
    _isolated()
    sources._prove_isolation()
    _current(identity); _capacity(identity, False); _current(identity)
    return _proof(identity, False)


def _isolated():
    _need(sys.flags.isolated == sys.flags.no_site == sys.flags.no_user_site == sys.flags.dont_write_bytecode == 1
        and sys.pycache_prefix == EMPTY_CACHE_PREFIX, "cloud_control_initial_isolation_required")


def _source_preflight(identity):
    code = ("import sys;sys.path.insert(0," + repr(str(LANE_ROOT)) + ");import json;"
        "from research import insider_buying_qc_cloud_control_cell as m;identity=json.loads(" + repr(_raw(identity).decode()) + ");"
        "\ntry: result=m._worker(identity)\nexcept BaseException: print('{\"disposition\":\"cloud_control_source_preflight_refused\"}');sys.exit(2)\nprint(m._raw(result).decode())")
    policy = '(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)(deny process-exec (literal "/usr/bin/security"))'
    command = ("/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "LANG=C", "LC_ALL=C",
        "/usr/bin/sandbox-exec", "-p", policy, sys.executable, "-I", "-S", "-B", "-X", "pycache_prefix=" + EMPTY_CACHE_PREFIX, "-c", code)
    child = sources.launcher.run_child(command, cwd=LANE_ROOT, env=None, timeout=60, cap=8192)
    _need(child.returncode == 0 and child.stderr == b"" and child.stdout == _raw(_proof(identity, False)) + b"\n", "cloud_control_source_preflight_refused")
    return _proof(identity, False)


def _prepare(root, identity, *, fixture, guard, preflight, nonce_factory):
    _need(type(fixture) is bool and callable(guard) and callable(preflight) and callable(nonce_factory), "cloud_control_preparation_mode_refused")
    if fixture:
        publication._fixture_root(root); publication._native_fixture_denial()
        _need(preflight is not _source_preflight and nonce_factory is not secrets.token_hex, "invented_preparation_callbacks_required")
    else:
        _need(root == LANE_ROOT and preflight is _source_preflight and nonce_factory is secrets.token_hex, "production_cloud_control_preparer_required")
    _source_identity(identity, root); _capacity(identity, fixture); guard()
    proof = preflight(identity)
    _need(_raw(proof) == _raw(_proof(identity, fixture)), "cloud_control_preflight_evidence_refused")
    guard()  # no output claim, nonce, credential or QC activity before proof
    chain = folder = None
    try:
        chain = sources.custody._Chain(root, ARTIFACT_PARTS, create=True, exclusive_last=True)
        folder = publication._NewDirectory(root.joinpath(*ARTIFACT_PARTS))
        expected = set()
        def check():
            guard(); chain.recheck(); folder.check()
            _need(set(os.listdir(folder.fd)) == expected, "cloud_control_output_inventory_changed")
        def publish(name, raw, cap=MAX_CONTROL_BYTES):
            check(); digest = folder.publish(name, raw, cap=cap); expected.add(name); check(); return digest
        publish("scope.lock", LOCK_BYTES)
        nonce = nonce_factory(32)
        registration_raw, cell_raw = _cell(nonce, fixture)
        registration_sha = publish("registration.json", registration_raw)
        cell_sha = publish("cell.py", cell_raw, MAX_CELL_BYTES)
        intent = _intent(identity, registration_raw, cell_raw, proof, fixture)
        intent_sha = publish("intent.json", _raw(intent))
        ready = {"schema": SCHEMA + "/prepared-not-executed", "audit_id": AUDIT_ID, "fixture_only": fixture,
            "registration_sha256": registration_sha, "cell_sha256": cell_sha, "cell_bytes": len(cell_raw),
            "intent_sha256": intent_sha, "core_sha256": CORE_SHA256, "key": _decode(registration_raw)["key"],
            "project_id": PROJECT_ID, "notebook": NOTEBOOK, "cell_index": 0,
            "local_scope_permanently_consumed": True, "cloud_execution_observed": False,
            "qc_or_credential_accesses": 0, "backtesting_ready": False}
        ready_sha = publish("ready.json", _raw(ready)); check()
        return {**ready, "ready_sha256": ready_sha, "cell_source": cell_raw.decode(),
            "cell_path": str(folder.path / "cell.py"), "intent_path": str(folder.path / "intent.json")}
    finally:
        publication._close_all((folder, chain), None, None, False)


def prepare_actual_cell(expected_head):
    """Local-only source proof and permanent intent; never interacts with QC."""
    _isolated()
    before = _identity(expected_head)
    def guard():
        _need(_identity(expected_head) == before, "cloud_control_committed_source_changed")
    return _prepare(LANE_ROOT, before, fixture=False, guard=guard,
        preflight=_source_preflight, nonce_factory=secrets.token_hex)


def prepare_invented_cell(root, *, nonce="a" * 64, guard=lambda: None, preflight=None):
    sources_map = {SELF_PATH: "a" * 64, TEST_PATH: "b" * 64,
        **{f"research/invented_control_{i:03}.py": "c" * 64 for i in range(104)}}
    identity = {"root": str(root), "branch": LANE_BRANCH, "head": "a" * 40, "clean": True,
        "source_sha256": sources_map, "source_inventory_sha256": _sha(_raw(sources_map))}
    return _prepare(root, identity, fixture=True, guard=guard,
        preflight=(lambda identity: _proof(identity, True)) if preflight is None else preflight,
        nonce_factory=lambda count: nonce if count == 32 else _need(False, "fixed_nonce_length_required"))


def validate_acknowledgement(raw, *, registration_raw):
    """Own bounded acknowledgement only; no ObjectStore contents are read."""
    _need(type(raw) is bytes and 0 < len(raw) <= 8192, "cloud_control_ack_bound")
    registration = _decode(registration_raw)
    _need(_raw(registration) == _raw(_registration(registration.get("nonce"), registration.get("fixture_only"))), "cloud_control_registration_refused")
    value = _decode(raw.removesuffix(b"\n"))
    fixed = {"schema": SCHEMA + "/acknowledgement", "audit_id": AUDIT_ID, "project_id": PROJECT_ID,
        "notebook": NOTEBOOK, "cell_index": 0, "key": registration["key"], "registration_sha256": _sha(registration_raw),
        "core_sha256": CORE_SHA256, "fixture_only": registration["fixture_only"], "object_store_contents_exported": False,
        "independent_stored_bytes_verified": False, "atomic_create_or_immutability_guaranteed": False,
        "dataset_or_history_calls": 0, "jobs_backtests": 0, "backtesting_ready": False}
    states = {"kernel_claim_already_consumed": (0, 0, None), "project_mismatch": (0, 0, None),
        "own_key_precheck_nonboolean": (1, 0, None), "own_key_already_exists_no_save": (1, 0, None),
        "save_nonboolean_no_retry": (1, 1, None), "save_acknowledged_true": (1, 1, True),
        "save_acknowledged_false_no_retry": (1, 1, False)}
    disposition = value.get("disposition")
    choices = ((0, 0, None), (1, 0, None), (1, 1, None)) if disposition == "cloud_control_exception_no_retry" else (states.get(disposition),)
    _need(any(state is not None and _raw(value) == _raw({**fixed, "disposition": disposition,
        "own_key_precheck_invocations": state[0], "save_invocations": state[1], "save_returned_true": state[2]}) for state in choices), "cloud_control_ack_schema_refused")
    return value


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "cloud_control_argument_refused\n")


def main(argv=None):
    parser = _ArgumentParser(description=__doc__); parser.add_argument("--expected-head", required=True); args = parser.parse_args(argv)
    try:
        result = prepare_actual_cell(args.expected_head)
    except BaseException:
        print('{"disposition":"cloud_control_local_preparation_refused"}'); return 2
    print(_raw({key: value for key, value in result.items() if key != "cell_source"}).decode()); return 0


if __name__ == "__main__":
    raise SystemExit(main())
