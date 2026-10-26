"""Offline pilot SEC metadata/reuse audit; no transport or admission authority.

The trusted parent only checks committed source and publishes bounded controls.
One initially sandboxed worker reads retained SUBMISSION metadata, quarterly
master indexes and operational journals. Original bodies are only hash-checked;
no ownership financial table, outcome, credential or QC interface is opened.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import uuid

from research import insider_buying_affected_quarter_selector_launcher_v3 as launcher
from research import insider_buying_affected_quarter_selector_verification_v2 as selector
from research import insider_buying_earnings_archive_assessment_runner as custody
from research import insider_buying_pilot_coverage_audit as prior
from research import insider_buying_pilot_sec_exposure as exposure
from research import insider_buying_pilot_sec_parent_audit as compiler
from research import insider_buying_pilot_sec_parent_readback as readback
from research import insider_buying_pilot_sec_roster as roster
from research import insider_buying_sec_2006q1_parent_bootstrap as bootstrap
from research.insider_buying.sec_quarter_master_index import parse_sec_quarter_master_index


SELF_PATH = "research/insider_buying_pilot_sec_parent_audit_runner.py"
SCHEMA = "insider-pilot-sec-parent-custody-audit-runner-v1"
LANE_ROOT, LANE_BRANCH = custody.LANE_ROOT, custody.LANE_BRANCH
OUTPUT_PARTS = ("artifacts", "insider_buying", "pilot_sec_parent_audit_v1")
AUDIT_ID = "ib-pilot-sec-parent-coverage-reuse-20261025-once"
EMPTY_CACHE_PREFIX = "/var/empty/insider-pilot-sec-parent-audit-no-bytecode"
MAX_REPORT = 128 * 1024 * 1024
_HEAD = re.compile(r"[0-9a-f]{40}\Z")
FROZEN = {
    "research/insider_buying_sec_all_form4_parent_recovery_union.py": "67a72b5cfd3be3ae9b1fc938a241da74df0a57979ca1a114d13122b675848a48",
    "research/insider_buying_sec_all_form4_parent_campaign.py": "33f2a54944b8f5674ae92c77c4a17ff03e6455ffcf7c0d07d377945e8dbad551",
    "research/insider_buying/sec_complete_submission.py": "d15ed661d32f13fd1f3644106bd6a21c428605b1a001d58ea5fc6a3319af63a6",
    "research/insider_buying/sec_raw_parent_projection.py": "d5631b6a2684e30061be1753e00e7f50f56690643537a9d67e34e228dd20578b",
}
REGISTRATION = {
    "schema": SCHEMA + "/registration", "audit_id": AUDIT_ID,
    "source_quarters": "2020Q1..2026Q1", "pilot_quarters": "2021Q1..2025Q4",
    "source_tables_interpreted": ["SUBMISSION.tsv"], "all_six_forms_retained": True,
    "master_indexes": "25 retained exact quarterly masters; no issuer-derived URL",
    "parent_body_interpretation": "opaque SHA256/size check only; not original-parent admission",
    "dispatch_history": "all explicit retained operational roots; claims/starts suppress redispatch",
    "stopped_v3_ambiguity_preserved": True, "new_provider_requests": 0,
    "credential_reads": 0, "qc_access": False, "outcome_access": False,
    "backtest_readiness_granted": False, "worker_invocations": 1,
    "worker_isolation": "initial native network/fork/all-write/Keychain-exec denial",
    "parent_isolation": "trusted unsandboxed controls only; Python audit guard is not OS isolation",
    "full_row_ledger_persisted": False,
    "full_row_accounting": "every source row consumed and bound by ordered per-quarter digest",
    "maximum_control_report_bytes": MAX_REPORT,
}


class PilotParentRunnerError(ValueError):
    """Sanitized refusal only; no private body or source text."""


def _need(value, code):
    if not value:
        raise PilotParentRunnerError(code)


def _raw(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _decode(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            _need(key not in value, "duplicate_control_key")
            value[key] = item
        return value
    value = json.loads(raw, object_pairs_hook=pairs,
        parse_constant=lambda _: _need(False, "nonfinite_control"))
    _need(type(value) is dict and _raw(value) == raw, "canonical_control_required")
    return value


def _master(tree, period):
    """Bind both compression envelope and independently reparsed locator receipt."""
    commit_raw = tree.read((), "commit.json", expected=bootstrap.MASTER_COMMIT_SHA256)
    commit = bootstrap._json(commit_raw)
    name = commit.get("report_name")
    _need(type(name) is str and "/" not in name, "master_report_name")
    report_raw = tree.read((), name, expected=bootstrap.MASTER_REPORT_SHA256)
    _need(commit.get("report_sha256") == _sha(report_raw), "master_commit_binding")
    rows = bootstrap._json(report_raw).get("master_indexes")
    _need(type(rows) is list and len(rows) == 82, "master_82_inventory")
    selected = [row for row in rows if type(row) is dict and row.get("period") == period]
    _need(len(selected) == 1, "master_period_unique")
    item = selected[0]
    _need(item.get("source_url") == f"https://www.sec.gov/Archives/edgar/full-index/{period[:4]}/QTR{period[-1]}/master.gz",
        "master_exact_url")
    descriptor, pin = item.get("raw_object"), item.get("receipt")
    _need(type(descriptor) is dict and type(pin) is dict, "master_descriptor")
    digest = descriptor.get("sha256")
    _need(type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest)
        and descriptor.get("relative_path") == "objects/" + digest + ".bin", "master_object_path")
    compressed = tree.read(("objects",), digest + ".bin", cap=8 * 1024 * 1024, expected=digest)
    _need(type(descriptor.get("size_bytes")) is int and len(compressed) == descriptor["size_bytes"], "master_object_size")
    decoded = bootstrap._decompress_master(compressed)
    _need(pin.get("decoded_sha256") == _sha(decoded) and type(pin.get("decoded_size_bytes")) is int
        and pin["decoded_size_bytes"] == len(decoded), "master_decoded_binding")
    result = parse_sec_quarter_master_index(decoded, year=int(period[:4]), quarter=int(period[-1]))
    _need(result.receipt_sha256 == pin.get("master_receipt_sha256"), "master_reparsed_receipt")
    return result


def _prove_isolation():
    custody._effective_denial(require_fork=True)
    try:
        os.execve("/usr/bin/security", ["security", "help"], {"PATH": "/usr/bin:/bin"})
    except OSError as exc:
        _need(exc.errno in {errno.EPERM, errno.EACCES}, "credential_exec_denial_required")
    else:
        raise PilotParentRunnerError("credential_exec_denial_required")
    path = Path("/private/tmp") / ("ib-pilot-sec-readonly-" + uuid.uuid4().hex)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except OSError as exc:
        _need(exc.errno in {errno.EPERM, errno.EACCES}, "all_write_denial_required")
    else:
        os.close(fd)
        raise PilotParentRunnerError("all_write_denial_required")


def _worker(identity):
    _need(sys.flags.isolated == 1 and sys.flags.no_site == 1 and sys.flags.dont_write_bytecode == 1
        and sys.pycache_prefix == EMPTY_CACHE_PREFIX, "isolated_worker_required")
    _need(type(identity) is dict and identity.get("root") == str(LANE_ROOT)
        and identity.get("branch") == LANE_BRANCH and identity.get("clean") is True
        and type(identity.get("head")) is str and _HEAD.fullmatch(identity["head"])
        and identity.get("source_inventory_sha256") == _sha(_raw(identity.get("source_sha256"))), "exact_identity_required")
    _prove_isolation()
    _need(custody._source_bytes(LANE_ROOT, tuple(identity["source_sha256"])) == identity["source_sha256"], "worker_source_changed")
    _need(custody._source_bytes(LANE_ROOT, tuple(FROZEN)) == FROZEN, "frozen_source_changed")
    trees, intake, prior_held = [], None, prior._Held(LANE_ROOT)
    phase = "accepted_selector_controls"
    try:
        # Revalidate the genuine successful selector/observer, not the failed
        # predecessor's equal candidate bytes. No earnings rows are needed.
        accepted = prior._selector(prior_held, prior.ACTUAL_ANCHORS)
        selection_raw = prior_held.leaf(prior.SELECTOR_PARTS, "selection.json", prior.MAX_CONTROL,
            prior.ACTUAL_ANCHORS.selection)
        phase = "retained_operational_controls"
        trees, exposure_raw, snapshot_raw, candidates_raw = exposure.observe_exposures(exposure.actual_roots(), fixture_only=False)
        phase = "retained_opaque_body_hashes"
        retained_raw = exposure.hash_candidate_bodies(trees, candidates_raw)
        master_tree = next((tree for tree in trees if tree.spec.root_id == "masters-v3"), None)
        _need(master_tree is not None, "master_tree_missing")
        # Interface is finalized together with the pure streaming compiler.
        phase = "compiler_metadata_inventory"
        audit = compiler.PilotSecParentAuditCompiler(exposure_raw=exposure_raw,
            expected_exposure_sha256=_sha(exposure_raw), candidates_raw=retained_raw,
            expected_candidates_sha256=_sha(retained_raw),
            master_for_period=lambda period: _master(master_tree.tree, period))
        phase = "held_source_intake"
        intake = selector._HeldIntake()
        phase = "source_roster_and_master_join"
        result = roster.derive_pilot_sec_roster(intake_manifest_raw=intake.manifest_raw,
            expected_manifest_sha256=intake.context["manifest_sha256"], selection_raw=selection_raw,
            expected_selection_sha256=prior.ACTUAL_ANCHORS.selection,
            quarter_inputs=roster.held_context_quarters(intake),
            consume_row=audit.consume, fixture_only=False)
        summary = result.to_payload()
        phase = "full_source_stream_conservation"
        joined = audit.finish(result)
        if hasattr(joined, "to_payload"):
            joined = joined.to_payload()
        phase = "final_held_input_recheck"
        intake.recheck()
        prior_held.recheck()
        for tree in trees:
            tree.recheck()
        _need(custody._source_bytes(LANE_ROOT, tuple(identity["source_sha256"])) == identity["source_sha256"], "worker_source_changed")
        return {"schema": SCHEMA, "audit_id": AUDIT_ID, "execution_identity": identity,
            "registration": REGISTRATION, "registration_sha256": _sha(_raw(REGISTRATION)),
            "source_roster": summary, "parent_audit": joined,
            "exposure_inventory_sha256": _sha(exposure_raw), "exposure_snapshot_sha256": _sha(snapshot_raw),
            "retained_body_inventory_sha256": _sha(retained_raw),
            "exposure_observer": _decode(snapshot_raw), "retained_body_inventory": _decode(retained_raw),
            "accepted_selector_pilot_counts": accepted["pilot_counts"],
            "intake_context": intake.context, "effective_native_network_fork_allwrite_denial": True,
            "effective_native_credential_exec_denial": True, "new_provider_requests": 0,
            "credential_reads": 0, "qc_accesses": 0, "outcome_looks": 0, "backtests": 0,
            "parent_financial_bodies_parsed": False, "original_parent_admission_established": False,
            "backtesting_ready": False}
    except Exception as exc:
        exc._pilot_audit_phase = phase
        raise
    finally:
        selector._close_all((intake, prior_held, *reversed(trees)), phase="pilot_parent_audit_cleanup")


def _failure_control(exc):
    # Only these local exceptions use closed, source-independent refusal codes.
    known = (PilotParentRunnerError, compiler.PilotSecParentAuditError, roster.PilotSecRosterError,
        exposure.PilotSecExposureError, bootstrap.ParentBootstrapError, prior.PilotCoverageError)
    code = str(exc) if type(exc) in known else "sanitized_worker_refusal"
    if re.fullmatch(r"[a-z][a-z0-9_]{0,159}", code) is None:
        code = "sanitized_worker_refusal"
    phase = getattr(exc, "_pilot_audit_phase", "before_source_intake")
    if type(phase) is not str or re.fullmatch(r"[a-z][a-z0-9_]{0,79}", phase) is None:
        phase = "sanitized_phase"
    return {"worker_refused": type(exc).__name__, "code": code, "phase": phase}


class _ParentGuard(launcher.ParentAuditGuard):
    """Exact commands and two exclusive control leaves, not a native sandbox."""
    def __init__(self, head, command):
        super().__init__("observer", head=head, commands=(command,))
        self.command, self.used = tuple(command), False
        self.output = LANE_ROOT.joinpath(*OUTPUT_PARTS, AUDIT_ID)

    def _write(self, path, *, mkdir=False):
        allowed = path in {self.output.parent, self.output} if mkdir else (
            path.parent == self.output and path.name in {"reservation.json", "complete.json", "terminal.json"})
        _need(allowed, "trusted_parent_write_refused")

    def _known_devnull_open(self, path, mode, flags):
        # This subclass adds one __call__ frame to the historical guard. The
        # exception remains CPython's exact known-child stdin sink, never an
        # arbitrary /dev/null or file-write exemption.
        if (path != "/dev/null" or type(path) is not str or mode is not None
                or type(flags) is not int or flags not in {os.O_RDWR, os.O_RDWR | getattr(os, "O_CLOEXEC", 0)}):
            return False
        frame = sys._getframe(3)
        owner = frame.f_locals.get("self")
        return (frame.f_code is launcher.subprocess.Popen._get_devnull.__code__
            and type(owner) is launcher.subprocess.Popen
            and tuple(owner.args) == self.command and not self.used)

    def __call__(self, event, args):
        if event == "subprocess.Popen":
            executable, command, cwd, env = args
            if self._git(executable, command, cwd, env):
                return
            _need(not self.used and tuple(command) == self.command and executable == "/usr/bin/env"
                and Path(cwd) == LANE_ROOT and env is None, "trusted_parent_child_refused")
            self.used = True
            self.used_commands.add(self.command)
            return
        super().__call__(event, args)


class _Publication:
    """Continuously held NEW controls; old source ctime rules are untouched."""
    def __init__(self, chain, *, fixture_path=None):
        if fixture_path is None:
            self.path = LANE_ROOT.joinpath(*OUTPUT_PARTS, AUDIT_ID)
        else:
            _need(isinstance(fixture_path, Path) and fixture_path.is_absolute()
                and fixture_path.resolve() == fixture_path and prior._outside_lane(fixture_path),
                "invented_publication_root_required")
            self.path = fixture_path
        self.chain, self.tree, self.pins = chain, None, {}
        _need(os.listdir(chain.fd) == [], "publication_cannot_resume")

    def publish(self, name, raw):
        _need(name in {"reservation.json", "terminal.json", "complete.json"} and name not in self.pins
            and type(raw) is bytes and 0 < len(raw) <= MAX_REPORT, "publication_bound")
        self.recheck()
        fd = os.open(self.path / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(self.chain.fd)
        self.chain.recheck()
        expected = {*self.pins, name}
        _need(set(os.listdir(self.chain.fd)) == expected, "publication_inventory_changed")
        if self.tree is None:
            self.tree = selector.held_io._HeldCapture(self.path, private=True, settle_ctime=True)
        else:
            # Only this freshly, exclusively published known leaf may extend
            # the continuously held output namespace. Never a source intake.
            self.tree.names = expected
        self.tree.open(name, len(raw))
        self.pins[name] = (_sha(raw), len(raw))
        self.recheck()
        return self.pins[name][0]

    def recheck(self, *, final=False):
        self.chain.recheck()
        _need(set(os.listdir(self.chain.fd)) == set(self.pins), "publication_inventory_changed")
        if final:
            _need(set(self.pins) == {"reservation.json", "terminal.json", "complete.json"}, "publication_incomplete")
        if self.tree is not None:
            self.tree.check()
            for name, stream, _, cap in self.tree.handles:
                _need(selector.held_io._hash_stream(stream, cap) == self.pins[name], "published_control_changed")
            self.tree.check()

    def close(self):
        selector._close_tree(self.tree, phase="pilot_parent_output_cleanup")


def _validate_result(result, identity):
    keys = {"schema", "audit_id", "execution_identity", "registration", "registration_sha256", "source_roster",
        "parent_audit", "exposure_inventory_sha256", "exposure_snapshot_sha256", "retained_body_inventory_sha256",
        "exposure_observer", "retained_body_inventory", "accepted_selector_pilot_counts", "intake_context",
        "effective_native_network_fork_allwrite_denial", "effective_native_credential_exec_denial",
        "new_provider_requests", "credential_reads", "qc_accesses", "outcome_looks", "backtests",
        "parent_financial_bodies_parsed", "original_parent_admission_established", "backtesting_ready"}
    _need(type(result) is dict and set(result) == keys and result["execution_identity"] == identity
        and result["schema"] == SCHEMA and result["audit_id"] == AUDIT_ID and result["registration"] == REGISTRATION
        and result["registration_sha256"] == _sha(_raw(REGISTRATION)), "worker_result_identity")
    for key in ("new_provider_requests", "credential_reads", "qc_accesses", "outcome_looks", "backtests"):
        _need(type(result[key]) is int and result[key] == 0, "worker_result_access_refused")
    for key in ("parent_financial_bodies_parsed", "original_parent_admission_established", "backtesting_ready"):
        _need(result[key] is False, "worker_result_authority_refused")
    for key in ("effective_native_network_fork_allwrite_denial", "effective_native_credential_exec_denial"):
        _need(result[key] is True, "worker_isolation_not_observed")
    for key in ("source_roster", "parent_audit", "exposure_observer", "retained_body_inventory", "intake_context"):
        _need(type(result[key]) is dict and result[key], "worker_result_summary_refused")
    _need(result["exposure_snapshot_sha256"] == _sha(_raw(result["exposure_observer"]))
        and result["retained_body_inventory_sha256"] == _sha(_raw(result["retained_body_inventory"])),
        "worker_result_inventory_crosslink")
    # Transporting a committed worker's report does not create authority. All
    # nested authority maps must retain false/zero values with exact types.
    def authorities(node):
        if type(node) is dict:
            for key, value in node.items():
                if key == "authority":
                    _need(type(value) is dict and value and all(item is False or type(item) is int and item == 0
                        for item in value.values()), "worker_nested_authority_refused")
                authorities(value)
        elif type(node) is list:
            for value in node:
                authorities(value)
    authorities(result)
    readback.validate_summaries(result)
    return result


def run_actual(expected_head):
    _need(Path(__file__).resolve() == LANE_ROOT / SELF_PATH, "fixed_source_required")
    identity = custody._identity(expected_head)
    _need(SELF_PATH in identity["source_sha256"], "committed_runner_required")
    code = ("import sys;sys.path.insert(0," + repr(str(LANE_ROOT)) + ");"
        "from research import insider_buying_pilot_sec_parent_audit_runner as m;import json;"
        "identity=json.loads(" + repr(_raw(identity).decode()) + ");"
        "\ntry: result=m._worker(identity)\nexcept Exception as exc: "
        "print(m._raw(m._failure_control(exc)).decode());sys.exit(2)"
        "\nprint(m._raw(result).decode())")
    policy = '(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)(deny process-exec (literal "/usr/bin/security"))'
    command = ("/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "/usr/bin/sandbox-exec", "-p", policy,
        sys.executable, "-I", "-S", "-B", "-X", "pycache_prefix=" + EMPTY_CACHE_PREFIX, "-c", code)
    sys.addaudithook(_ParentGuard(expected_head, command))
    # Claim a fresh output namespace before reading actual source data.
    parent = custody._Chain(LANE_ROOT, OUTPUT_PARTS[:2])
    try:
        try:
            os.mkdir(LANE_ROOT.joinpath(*OUTPUT_PARTS), 0o700)
        except FileExistsError:
            pass
        parent.recheck()
    finally:
        parent.close()
    output = custody._Chain(LANE_ROOT, OUTPUT_PARTS)
    try:
        os.mkdir(LANE_ROOT.joinpath(*OUTPUT_PARTS, AUDIT_ID), 0o700)
        output.recheck()
    finally:
        output.close()
    output = custody._Chain(LANE_ROOT, (*OUTPUT_PARTS, AUDIT_ID))
    publication = None
    try:
        publication = _Publication(output)
        _need(os.fstatvfs(output.fd).f_bavail * os.fstatvfs(output.fd).f_frsize >= 4 * 1024**3 + 3 * MAX_REPORT,
            "publication_disk_reserve")
        reservation = {"schema": SCHEMA + "/reservation", "registration": REGISTRATION,
            "registration_sha256": _sha(_raw(REGISTRATION)), "execution_identity": identity}
        reservation_sha = publication.publish("reservation.json", _raw(reservation))
        started = time.monotonic()
        child = launcher.run_child(command, cwd=LANE_ROOT, env=None, timeout=1800, cap=MAX_REPORT)
        terminal = {"schema": SCHEMA + "/terminal", "reservation_sha256": reservation_sha,
            "elapsed_seconds": round(time.monotonic() - started, 6), "exit_code": child.returncode}
        # run_child retains raw bytes only in memory; published controls bind
        # their hashes/counts, never uncontrolled stderr text.
        stdout, stderr = child.stdout, child.stderr
        terminal.update(stdout_bytes=len(stdout), stdout_sha256=_sha(stdout),
            stderr_bytes=len(stderr), stderr_sha256=_sha(stderr))
        success = child.returncode == 0 and not stderr and 0 < len(stdout) <= MAX_REPORT
        terminal["success"] = success
        if not success and not stderr and 0 < len(stdout) <= 1024:
            try:
                refusal = _decode(stdout.removesuffix(b"\n"))
                _need(set(refusal) == {"worker_refused", "code", "phase"}
                    and all(type(value) is str and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,159}", value)
                        for value in refusal.values()), "sanitized_refusal_schema")
                terminal["worker_refusal"] = refusal
            except Exception:
                pass
        publication.publish("terminal.json", _raw(terminal))
        _need(success, "isolated_audit_worker_refused")
        result = _decode(stdout.removesuffix(b"\n"))
        _validate_result(result, identity)
        _need(custody._identity(expected_head) == identity, "parent_source_changed")
        digest = publication.publish("complete.json", _raw(result))
        publication.recheck(final=True)
        return {"schema": SCHEMA, "audit_id": AUDIT_ID, "complete_sha256": digest,
            "complete_bytes": len(_raw(result)), "elapsed_seconds": terminal["elapsed_seconds"],
            "source_roster_counts": result["source_roster"]["counts"],
            "parent_context_counts": result["parent_audit"]["context_counts"],
            "parent_pilot_counts": result["parent_audit"]["pilot_counts"],
            "parent_audit_sha256": _sha(_raw(result["parent_audit"])),
            "backtesting_ready": False}
    finally:
        selector._close_all((publication, output), phase="pilot_parent_publication_cleanup")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    args = parser.parse_args(argv)
    try:
        result = run_actual(args.expected_head)
    except Exception:
        print('{"disposition":"pilot_sec_parent_audit_refused"}')
        return 2
    print(_raw(result).decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
