"""Read-only diagnosis of the consumed v1 Feed-directory control namespace.

This additive observer never resumes that scope or calls a transport/contact
API. Only retained local control metadata is read. Replaying its pinned old
decoder is code-derived evidence, not a measurement of original HTTP dispatch.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import sys

from research import insider_buying_sec_feed_directory_inventory as original
from research import insider_buying_pilot_sec_parent_audit_runner as base


SELF_PATH = "research/insider_buying_sec_feed_directory_stopped_controls.py"
TEST_PATH = "tests/test_insider_buying_sec_feed_directory_stopped_controls.py"
SCHEMA = "insider-sec-feed-directory-stopped-controls-v1"
AUDIT_ID = "ib-sec-feed-directory-2021q1-stopped-controls-20261025-once"
LANE_ROOT, LANE_BRANCH = base.LANE_ROOT, base.LANE_BRANCH
EMPTY_CACHE_PREFIX = "/var/empty/insider-sec-feed-stopped-controls-no-bytecode"
FAILED_HEAD = "2e3224d6d69e4eb9ce2c877505b9ea2473b0ceb3"
FAILED_SOURCE_SHA256 = "c40fb29f3cb01fe0d27dc7305db8c41f87df2439e31151572d20bb0337b2199f"
FAILED_TEST_SHA256 = "6abc8a6cee7f8e5a538f2f22036953151c7151ad0f81de00fbfd74575390a80e"
FAILED_SCOPE_SHA256 = "5ebe6aa7bdc9d069ee6e43ead51c608fb9f749220f7e7758f267891fe3ebb0eb"
OBSERVED_RESERVATION_BYTES = 14281
MAX_CONTROL_BYTES = 256 * 1024
MAX_REPORT_BYTES = 1024 * 1024
CONTROL_TIMEOUT = 60
CONTROL_NAMES = ("scope.lock", "claim.json", "reservation.json", "contact-validated.json", "request-start.json")
RUN_NAMES = frozenset(CONTROL_NAMES[2:])
_SHA, _HEAD = re.compile(r"[0-9a-f]{64}\Z"), re.compile(r"[0-9a-f]{40}\Z")
_PATH = re.compile(r"[A-Za-z0-9_./-]{1,512}\Z")
_raw, _sha = base._raw, base._sha
_REFUSAL_CODES = frozenset({"bounded_json_bytes_required", "duplicate_json_key", "json_resource_bound_refused",
    "json_key_bound_refused", "json_string_bound_refused", "json_object_required", "json_schema_refused",
    "floating_json_refused", "nonfinite_json_refused"})
REGISTRATION = {
    "schema": SCHEMA + "/registration", "audit_id": AUDIT_ID,
    "original_audit_id": original.AUDIT_ID, "original_execution_head": FAILED_HEAD,
    "original_source_sha256": FAILED_SOURCE_SHA256, "original_test_sha256": FAILED_TEST_SHA256,
    "original_scope_sha256": FAILED_SCOPE_SHA256, "original_reservation_bytes": OBSERVED_RESERVATION_BYTES,
    "original_namespace_mutated": False, "original_scope_resumed": False, "url_retry_authorized": False,
    "original_total_leaf_count": 5, "original_run_leaf_count": 3, "original_url_claim_count": 1,
    "worker_invocations": 1, "new_provider_requests": 0, "credential_reads": 0,
    "qc_accesses": 0, "outcome_looks": 0, "backtests": 0,
    "native_network_fork_allwrite_securityexec_denial": True, "persistent_result_published": False,
    "source_authenticated_here": False, "canonical_admitted": False, "backtesting_ready": False,
}


class StoppedControlError(ValueError):
    """Fixed diagnostic refusal codes; never retained control text."""


def _need(value, code):
    if not value: raise StoppedControlError(code)


def _decode_control(raw, *, ipc=False):
    """Own canonical controls, deliberately NOT the foreign directory profile.

    Real execution identities exceed the old foreign-profile 32-key limit.
    This observer changes neither that decoder nor its consumed operation.
    """
    _need(type(ipc) is bool and type(raw) is bytes and 0 < len(raw) <=
        (MAX_REPORT_BYTES if ipc else MAX_CONTROL_BYTES), "control_byte_bound")
    def pairs(items):
        value = {}
        for key, child in items:
            _need(key not in value, "control_duplicate_key")
            value[key] = child
        return value
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
            parse_float=lambda _: _need(False, "control_float_refused"),
            parse_constant=lambda _: _need(False, "control_nonfinite_refused"))
        pending, nodes = [(value, 0)], 0
        while pending:
            item, depth = pending.pop(); nodes += 1
            _need(nodes <= 8192 and depth <= 24, "control_resource_bound")
            if type(item) is dict:
                _need(len(item) <= 2048 and all(type(k) is str and len(k) <= 512 for k in item), "control_object_bound")
                pending.extend((child, depth + 1) for child in item.values())
            elif type(item) is list:
                _need(len(item) <= 256, "control_list_bound")
                pending.extend((child, depth + 1) for child in item)
            elif type(item) is str:
                _need(len(item) <= (2 * MAX_CONTROL_BYTES if ipc else 16384), "control_string_bound")
        _need(type(value) is dict and _raw(value) == raw, "canonical_control_required")
        return value
    except StoppedControlError: raise
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise StoppedControlError("control_json_refused") from None


def _identity(value, *, original_identity=False):
    _need(type(value) is dict and set(value) == {"root", "branch", "head", "clean", "source_sha256", "source_inventory_sha256"}
        and value["root"] == str(LANE_ROOT) and value["branch"] == LANE_BRANCH and value["clean"] is True
        and type(value["head"]) is str and _HEAD.fullmatch(value["head"])
        and type(value["source_sha256"]) is dict and 1 <= len(value["source_sha256"]) <= 2048
        and value["source_inventory_sha256"] == _sha(_raw(value["source_sha256"])), "execution_identity_refused")
    for name, digest in value["source_sha256"].items():
        _need(type(name) is str and _PATH.fullmatch(name) and not name.startswith("/")
            and all(p not in {"", ".", ".."} for p in name.split("/"))
            and type(digest) is str and _SHA.fullmatch(digest), "execution_source_entry_refused")
    needed = {original.SELF_PATH, original.TEST_PATH} if original_identity else {SELF_PATH, TEST_PATH, original.SELF_PATH}
    _need(needed <= set(value["source_sha256"]), "execution_source_roster_refused")
    if original_identity:
        _need(value["head"] == FAILED_HEAD and value["source_sha256"][original.SELF_PATH] == FAILED_SOURCE_SHA256
            and value["source_sha256"][original.TEST_PATH] == FAILED_TEST_SHA256, "original_execution_source_refused")
    return value


def _old_refusal(raw):
    try: original._decode(raw, canonical=True)
    except original.FeedDirectoryError as exc:
        code = str(exc)
        return code if code in _REFUSAL_CODES else "original_decoder_unclassified_refusal"
    return None


def _invented_102():
    sources = {original.SELF_PATH: FAILED_SOURCE_SHA256, original.TEST_PATH: FAILED_TEST_SHA256,
        **{f"research/invented_{i:03}.py": "a" * 64 for i in range(100)}}
    identity = {"root": str(LANE_ROOT), "branch": LANE_BRANCH, "head": FAILED_HEAD, "clean": True,
        "source_sha256": sources, "source_inventory_sha256": _sha(_raw(sources))}
    return _old_refusal(_raw(original._reservation(identity, False)))


def diagnose_controls(controls, *, expected_reservation_bytes):
    """Pure diagnosis of supplied canonical metadata; never reads any path."""
    _need(type(controls) is dict and set(controls) == set(CONTROL_NAMES)
        and all(type(raw) is bytes and 0 < len(raw) <= MAX_CONTROL_BYTES for raw in controls.values()), "stopped_control_inventory")
    _need(type(expected_reservation_bytes) is int and 0 < expected_reservation_bytes <= MAX_CONTROL_BYTES
        and len(controls["reservation.json"]) == expected_reservation_bytes, "stopped_reservation_size")
    _need(controls["scope.lock"] == original.LOCK_BYTES
        and _sha(_raw(original._scope())) == FAILED_SCOPE_SHA256, "original_scope_or_lock_refused")
    decoded = {name: _decode_control(raw) for name, raw in controls.items() if name != "scope.lock"}
    reservation = decoded["reservation.json"]
    _need(type(reservation.get("execution_identity")) is dict, "original_reservation_identity_required")
    identity = _identity(reservation["execution_identity"], original_identity=True)
    _need(controls["reservation.json"] == _raw(original._reservation(identity, False)), "original_reservation_refused")
    reservation_sha = _sha(controls["reservation.json"])
    _need(controls["claim.json"] == _raw({"schema": original.SCHEMA + "/url-claim", "method": "GET", "url": original.URL,
        "scope_sha256": FAILED_SCOPE_SHA256, "reservation_sha256": reservation_sha}), "original_claim_refused")
    _need(controls["request-start.json"] == _raw({"schema": original.SCHEMA + "/start", "scope_sha256": FAILED_SCOPE_SHA256,
        "reservation_sha256": reservation_sha, "claim_sha256": _sha(controls["claim.json"]), "attempt": 1}), "original_start_refused")
    _need(controls["contact-validated.json"] == _raw({"schema": original.SCHEMA + "/contact", "reservation_sha256": reservation_sha,
        "contact_present": True, "contact_value_stored_or_hashed": False}), "original_contact_control_refused")
    refusal = _old_refusal(controls["reservation.json"])
    return {"schema": SCHEMA + "/diagnosis", "original_execution_head": FAILED_HEAD,
        "original_source_sha256": FAILED_SOURCE_SHA256, "original_scope_sha256": FAILED_SCOPE_SHA256,
        "original_source_count": len(identity["source_sha256"]), "original_source_inventory_sha256": identity["source_inventory_sha256"],
        "original_total_leaf_count": 5, "original_run_leaf_count": 3, "original_url_claim_count": 1,
        "no_http_result_or_body_retained": True, "original_decoder_refusal_code": refusal,
        "invented_102_source_decoder_refusal_code": _invented_102(),
        "original_reservation_decoder_precedes_raw_transport_in_pinned_source": True,
        "code_derived_reservation_decode_blocks_raw_transport": refusal is not None,
        "measured_original_http_request_count": None, "measured_original_transferred_bytes": None,
        "actual_dispatch_observation": "not instrumented; consumed URL claim remains preserved",
        "original_scope_status": "stopped and consumed; not resumed or retried",
        "original_observation_replaced": False, "retry_authorized": False, "authority": original._authority()}


def _version(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_uid, info.st_gid,
        info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _isolated():
    _need(sys.flags.isolated == sys.flags.no_site == sys.flags.no_user_site == sys.flags.dont_write_bytecode == 1
        and sys.pycache_prefix == EMPTY_CACHE_PREFIX, "stopped_worker_isolated_flags_required")


class _HeldStopped:
    """Strict old-source ctime, private owner, ancestry, inventory and hashes."""
    def __init__(self, root=LANE_ROOT, *, fixture=False):
        if fixture:
            original.publication._fixture_root(root); original.publication._native_fixture_denial()
        else:
            _need(root == LANE_ROOT, "fixed_stopped_namespace_required")
            _isolated(); base._prove_isolation()
        self.inputs, self.versions, self.lock_fd = base.custody._Inputs(root), [], None
        try:
            parts = original.ARTIFACT_PARTS
            self.base = self.inputs.directory(parts)
            claims = self.inputs.directory((*parts, "claims")); runs = self.inputs.directory((*parts, "runs"))
            run = self.inputs.directory((*parts, "runs", original.AUDIT_ID))
            for chain, names in ((self.base, {"scope.lock", "claims", "runs"}), (claims, {original._claim_name()}),
                    (runs, {original.AUDIT_ID}), (run, RUN_NAMES)):
                info = os.fstat(chain.fd)
                _need(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700, "stopped_directory_owner_or_mode")
                self.versions.append((chain, None, _version(info))); self.inputs.inventory(chain, names)
            self.lock_fd = os.open("scope.lock", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.base.fd)
            fcntl.flock(self.lock_fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            self.controls = {}
            for key, chain, path, name in (("scope.lock", self.base, parts, "scope.lock"),
                    ("claim.json", claims, (*parts, "claims"), original._claim_name()),
                    *((name, run, (*parts, "runs", original.AUDIT_ID), name) for name in sorted(RUN_NAMES))):
                info = os.stat(name, dir_fd=chain.fd, follow_symlinks=False)
                _need(info.st_uid == os.geteuid(), "stopped_leaf_owner")
                self.controls[key] = self.inputs.read(chain, path, name, limit=MAX_CONTROL_BYTES)
                self.versions.append((chain, name, _version(os.stat(name, dir_fd=chain.fd, follow_symlinks=False))))
            self.lock_version = _version(os.fstat(self.lock_fd)); self.recheck()
        except BaseException:
            base.selector._close_all((self,), phase="stopped_controls_open_cleanup"); raise

    def recheck(self):
        self.inputs.recheck()
        for chain, name, version in self.versions:
            info = os.fstat(chain.fd) if name is None else os.stat(name, dir_fd=chain.fd, follow_symlinks=False)
            _need(_version(info) == version, "stopped_input_metadata_changed")
        _need(_version(os.fstat(self.lock_fd)) == self.lock_version ==
            _version(os.stat("scope.lock", dir_fd=self.base.fd, follow_symlinks=False)), "stopped_lock_changed")

    def close(self):
        first = None
        fds = ([self.lock_fd] if self.lock_fd is not None else [])
        self.lock_fd = None
        for chain in reversed(self.inputs.chains):
            fds.extend(reversed(chain.fds)); chain.fds = []
        for fd in fds:
            try: os.close(fd)
            except OSError as exc:
                if first is None: first = exc
        if first is not None: raise first


def _current_sources(identity):
    _need(base.custody._source_bytes(LANE_ROOT, tuple(identity["source_sha256"])) == identity["source_sha256"]
        and base.custody._source_bytes(LANE_ROOT, tuple(base.FROZEN)) == base.FROZEN
        and base.custody._source_bytes(LANE_ROOT, (original.SELF_PATH, original.TEST_PATH)) == {
            original.SELF_PATH: FAILED_SOURCE_SHA256, original.TEST_PATH: FAILED_TEST_SHA256}, "stopped_current_or_frozen_source_changed")


def _control_witness(result):
    witness = result["original_control_witness"]
    _need(type(witness) is dict and set(witness) == set(CONTROL_NAMES), "stopped_witness_inventory")
    controls = {}
    for name, value in witness.items():
        _need(type(value) is str and 0 < len(value) <= 2 * MAX_CONTROL_BYTES and len(value) % 2 == 0
            and re.fullmatch(r"[0-9a-f]+", value), "stopped_witness_encoding")
        controls[name] = bytes.fromhex(value)
    return controls


def _validate(result, identity, *, expected_reservation_bytes=OBSERVED_RESERVATION_BYTES):
    _identity(identity)
    keys = {"schema", "audit_id", "registration", "registration_sha256", "execution_identity", "original_control_pins",
        "original_control_witness", "diagnostic", "diagnostic_sha256", "native_network_fork_allwrite_securityexec_denial",
        "new_provider_requests", "credential_reads", "qc_accesses", "outcome_looks", "backtests",
        "original_namespace_mutated", "persistent_result_published", "source_authenticated_here", "canonical_admitted", "backtesting_ready"}
    _need(type(result) is dict and set(result) == keys and result["schema"] == SCHEMA and result["audit_id"] == AUDIT_ID
        and _raw(result["registration"]) == _raw(REGISTRATION) and result["registration_sha256"] == _sha(_raw(REGISTRATION))
        and _raw(result["execution_identity"]) == _raw(identity), "stopped_result_schema")
    for key in ("new_provider_requests", "credential_reads", "qc_accesses", "outcome_looks", "backtests"):
        _need(type(result[key]) is int and result[key] == 0, "stopped_result_access")
    for key in ("original_namespace_mutated", "persistent_result_published", "source_authenticated_here", "canonical_admitted", "backtesting_ready"):
        _need(result[key] is False, "stopped_result_authority")
    _need(result["native_network_fork_allwrite_securityexec_denial"] is True, "stopped_result_native_denial")
    controls = _control_witness(result)
    pins = {name: {"sha256": _sha(raw), "bytes": len(raw)} for name, raw in controls.items()}
    diagnostic = diagnose_controls(controls, expected_reservation_bytes=expected_reservation_bytes)
    _need(_raw(result["original_control_pins"]) == _raw(pins) and _raw(result["diagnostic"]) == _raw(diagnostic)
        and result["diagnostic_sha256"] == _sha(_raw(diagnostic)) and len(_raw(result)) <= MAX_REPORT_BYTES,
        "stopped_result_crosslinks")
    return result


def _worker(identity):
    _isolated(); _identity(identity); base._prove_isolation(); _current_sources(identity)
    held = None
    try:
        held = _HeldStopped()
        diagnostic = diagnose_controls(held.controls, expected_reservation_bytes=OBSERVED_RESERVATION_BYTES)
        held.recheck(); _current_sources(identity)
        result = {"schema": SCHEMA, "audit_id": AUDIT_ID, "registration": REGISTRATION,
            "registration_sha256": _sha(_raw(REGISTRATION)), "execution_identity": identity,
            "original_control_pins": {name: {"sha256": _sha(raw), "bytes": len(raw)} for name, raw in held.controls.items()},
            "original_control_witness": {name: raw.hex() for name, raw in held.controls.items()},
            "diagnostic": diagnostic, "diagnostic_sha256": _sha(_raw(diagnostic)),
            "native_network_fork_allwrite_securityexec_denial": True, "new_provider_requests": 0, "credential_reads": 0,
            "qc_accesses": 0, "outcome_looks": 0, "backtests": 0, "original_namespace_mutated": False,
            "persistent_result_published": False, "source_authenticated_here": False, "canonical_admitted": False, "backtesting_ready": False}
        _validate(result, identity); held.recheck(); _current_sources(identity)
        return result
    finally: base.selector._close_all((held,), phase="stopped_controls_worker_cleanup")


class _Guard(base._ParentGuard):
    def _write(self, path, *, mkdir=False): raise StoppedControlError("stopped_parent_all_writes_refused")

    def _git(self, executable, command, cwd, env):
        if (executable == "/usr/bin/git" and type(command) in {tuple, list} and len(command) == 3
                and command[0] == executable and command[1] == "show" and type(command[2]) is str
                and self._lane_cwd(cwd) and env == {"PATH": "/usr/bin:/bin"}):
            commit, separator, name = command[2].partition(":")
            if (commit == FAILED_HEAD and separator and _PATH.fullmatch(name) and name.endswith(".py")
                    and not name.startswith("/") and all(p not in {"", ".", ".."} for p in name.split("/"))):
                return True
        return super()._git(executable, command, cwd, env)


def _committed_identity(expected_head):
    identity = base.custody._identity(expected_head)
    own = base.custody._source_bytes(LANE_ROOT, (SELF_PATH, TEST_PATH))
    for name, digest in own.items():
        _need(_sha(base.custody._git(LANE_ROOT, "show", expected_head + ":" + name)) == digest, "stopped_uncommitted_source")
    sources = {**identity["source_sha256"], **own}
    identity = _identity({**identity, "source_sha256": sources, "source_inventory_sha256": _sha(_raw(sources))})
    _current_sources(identity)
    return identity


def _command(identity):
    code = ("import sys;sys.path.insert(0," + repr(str(LANE_ROOT)) + ");import json;"
        "from research import insider_buying_sec_feed_directory_stopped_controls as m;"
        "identity=json.loads(" + repr(_raw(identity).decode()) + ");"
        "\ntry: result=m._worker(identity)\nexcept Exception: print('{\"disposition\":\"stopped_control_worker_refused\"}');sys.exit(2)\n"
        "print(m._raw(result).decode())")
    policy = '(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)(deny process-exec (literal "/usr/bin/security"))'
    return ("/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "/usr/bin/sandbox-exec", "-p", policy,
        sys.executable, "-I", "-S", "-B", "-X", "pycache_prefix=" + EMPTY_CACHE_PREFIX, "-c", code)


def run_actual_diagnostic(expected_head):
    _need(Path(__file__).resolve() == LANE_ROOT / SELF_PATH, "stopped_fixed_source_required")
    identity = _committed_identity(expected_head)
    command = _command(identity); sys.addaudithook(_Guard(expected_head, command))
    child = base.launcher.run_child(command, cwd=LANE_ROOT, env=None, timeout=CONTROL_TIMEOUT, cap=MAX_REPORT_BYTES)
    _need(child.returncode == 0 and child.stderr == b"" and 0 < len(child.stdout) <= MAX_REPORT_BYTES, "stopped_worker_refused")
    # IPC is our own metadata schema, not the unchanged foreign 32-key decoder.
    result = _validate(_decode_control(child.stdout.removesuffix(b"\n"), ipc=True), identity)
    original_identity = _decode_control(_control_witness(result)["reservation.json"])["execution_identity"]
    for name, digest in original_identity["source_sha256"].items():
        _need(_sha(base.custody._git(LANE_ROOT, "show", FAILED_HEAD + ":" + name)) == digest, "stopped_original_git_source_mismatch")
    _need(_committed_identity(expected_head) == identity, "stopped_parent_source_changed")
    public = dict(result); del public["original_control_witness"]
    public.update({"original_control_witness_validated_and_omitted": True, "original_source_inventory_matched_failed_commit": True,
        "observed_worker_stdout_bytes": len(child.stdout), "observed_worker_stdout_sha256": _sha(child.stdout)})
    return public


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--expected-head", required=True)
    args = parser.parse_args(argv)
    try: result = run_actual_diagnostic(args.expected_head)
    except Exception:
        print('{"disposition":"stopped_control_diagnostic_refused"}'); return 2
    print(_raw(result).decode()); return 0


if __name__ == "__main__": raise SystemExit(main())
