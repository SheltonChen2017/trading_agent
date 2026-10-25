"""Fresh pilot-only JIT parent custody; no old scope is resumed or rewritten.

Production is disabled until exact observed protected-selection control pins
are committed here. Fixtures cannot invoke the default transport, contact
reader, actual roots or production loader. Acquisition is not XML/canonical
admission. A claim/start remains consumed on every failure, including a local
publication error. Only fresh output leaves use settled-ctime/full-hash checks.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date
import errno
import fcntl
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import sys
import threading
import time
import weakref

from research import insider_buying_pilot_sec_parent_audit as audit
from research import insider_buying_pilot_sec_fresh_selection as fresh
from research import insider_buying_pilot_sec_exposure as exposure
from research import insider_buying_sec_2006q1_parent_capture_v1 as old
from research import insider_buying_sec_recovery_v4_capture as custody
from research import insider_buying_affected_quarter_selector_verification_v2 as selector
from research import insider_buying_pilot_sec_parent_audit_runner as source_runner
from research import insider_buying_pilot_sec_fresh_selection_runner as selection_runner
from research.insider_buying_sec_complete_acquisition import SecHttpResult
from research.insider_buying_sec_selected_parent_runner import _selected_sec_transport, _strict_selected_response


SCHEMA = "insider-pilot-sec-parent-first64-capture-v1"
SELF_PATH = "research/insider_buying_pilot_sec_parent_capture.py"
TEST_PATH = "tests/test_insider_buying_pilot_sec_parent_capture.py"
LANE_ROOT = exposure.bootstrap.custody.LANE_ROOT
ARTIFACT_PARTS = ("artifacts", "insider_buying", "pilot_sec_parent_capture_v1")
CAPTURE_ID = "ib-sec-pilot-2021q1-first64-20261025-once"
MAX_REQUESTS, MAX_PARENT_BYTES, MAX_CONTROL_BYTES = 64, 8 * 1024 * 1024, 2 * 1024 * 1024
MIN_FREE_BYTES = 8 * 1024**3
MIN_COMPLETION_INTERVAL_NS = 500_000_000
TRANSPORT_WALL_SECONDS = 30
LOCK_BYTES = b"INSETF-pilot-2021Q1-first64-JIT-accession-lock-v1\n"
SELECTION_PARTS = ("artifacts", "insider_buying", "pilot_sec_fresh_selection_v1")
SELECTION_AUDIT_ID = "ib-pilot-sec-first64-selection-20261025-once"
# Observed controls, byte sizes and serialized-selection location are filled
# only after the separately registered selector has actually completed.
ACTUAL_SELECTION_PINS = {}
ACTUAL_SELECTION_SHA256 = None
ACTUAL_SELECTION_HEAD = None
_TOKEN = object()
_REGISTRY = weakref.WeakKeyDictionary()
_DISPATCHES = weakref.WeakKeyDictionary()
_RAW_TRANSPORT = _selected_sec_transport
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_HEAD = re.compile(r"[0-9a-f]{40}\Z")


class PilotParentCaptureError(ValueError):
    """Fixed codes only; no source, contact or exception text."""


class _DeadlineExceeded(Exception):
    pass


def _need(value, code):
    if not value:
        raise PilotParentCaptureError(code)


_raw, _sha = audit._raw, audit._sha


def _digest(value):
    _need(type(value) is str and _SHA.fullmatch(value), "digest_required")
    return value


def _zero_authority(value):
    audit._authority(value)


def _clock_value(value):
    _need(type(value) is str and custody._stamp(lambda: value) == value, "canonical_utc_journal_time_required")
    return value


def _source_identity(value, *, required_paths=()):
    _need(type(value) is dict and set(value) == {"root", "branch", "head", "clean", "source_sha256", "source_inventory_sha256"}
          and value["root"] == str(LANE_ROOT) and value["branch"] == source_runner.LANE_BRANCH
          and type(value["head"]) is str and _HEAD.fullmatch(value["head"]) and value["clean"] is True
          and type(value["source_sha256"]) is dict and all(path in value["source_sha256"] for path in required_paths)
          and all(type(name) is str and not Path(name).is_absolute() and ".." not in Path(name).parts
              and type(digest) is str and _SHA.fullmatch(digest) for name, digest in value["source_sha256"].items())
          and value["source_inventory_sha256"] == _sha(_raw(value["source_sha256"])), "capture_source_identity_refused")
    return value


def _decode(raw, *, allow_floats=False):
    def pairs(items):
        result = {}
        for key, value in items:
            _need(key not in result, "duplicate_control_key")
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
            parse_float=float if allow_floats else lambda _: _need(False, "floating_control_refused"),
            parse_constant=lambda _: _need(False, "nonfinite_control_refused"))
        _need(type(value) is dict and _raw(value) == raw, "canonical_control_required")
        return value
    except PilotParentCaptureError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise PilotParentCaptureError("control_json_refused") from None


def _request(value):
    _need(type(value) is dict and set(value) == fresh._REQUEST_KEYS, "pilot_request_exact_schema_required")
    _need(all(type(item) is str for key, item in value.items() if key != "source_record_ordinal")
          and type(value["source_record_ordinal"]) is int and 1 <= value["source_record_ordinal"] <= audit.MAX_QUARTER_ROWS,
          "pilot_request_types_refused")
    _need(value["period"] == "2021Q1" and value["form_type"] in {"4", "4/A"}
          and type(value["accession_number"]) is str and audit._ACCESSION.fullmatch(value["accession_number"]),
          "pilot_request_scope_refused")
    try:
        filed = date.fromisoformat(value["filing_date"])
    except ValueError:
        raise PilotParentCaptureError("pilot_filing_date_refused") from None
    _need(filed.isoformat() == value["filing_date"] and date(2021, 1, 1) <= filed <= date(2021, 3, 31)
          and audit._cik(value["issuer_cik"]), "pilot_request_identity_refused")
    match = audit._PATH.fullmatch(value["archive_path"])
    _need(match is not None and int(match.group(1)) > 0 and match.group(2) == value["accession_number"]
          and value["url"] == "https://www.sec.gov/Archives/" + value["archive_path"], "pilot_exact_archive_path_required")
    for key, item in value.items():
        if key.endswith("sha256"):_digest(item)
    _need(len(_raw(value)) <= 16 * 1024, "pilot_request_bound_refused")
    return value


def _version(info):
    # NEW output only: full content hash is checked on every read/check.
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_uid, info.st_gid,
            info.st_size, info.st_mtime_ns)


class _NewDirectory:
    """FD-relative fresh leaves with repeated hashes, never relaxed old inputs."""
    def __init__(self, path, *, create=False):
        self.path = Path(path);self.tree = custody._Directory(self.path, create=create)
        self.fd = self.tree.fd;self.pins = {}

    def check(self):
        self.tree.check()
        for name, (digest, size, version) in tuple(self.pins.items()):
            raw, observed = self._read(name, size)
            _need(observed == version and _sha(raw) == digest and len(raw) == size, "new_output_leaf_changed")
        self.tree.check()

    def _read(self, name, cap):
        _need(type(name) is str and name not in {"", ".", ".."} and "/" not in name
              and type(cap) is int and 0 < cap <= MAX_PARENT_BYTES, "new_output_name_or_cap_refused")
        self.tree.check()
        named = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
        _need(stat.S_ISREG(named.st_mode) and named.st_uid == os.geteuid() and named.st_nlink == 1
              and stat.S_IMODE(named.st_mode) == 0o600 and 0 < named.st_size <= cap, "new_output_custody_refused")
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        try:
            before = os.fstat(descriptor);_need(_version(before) == _version(named), "new_output_substitution_refused")
            pieces, total = [], 0
            while chunk := os.read(descriptor, min(65536, cap + 1 - total)):
                total += len(chunk);_need(total <= cap, "new_output_read_bound_refused");pieces.append(chunk)
            after = os.fstat(descriptor);named_after = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            _need(_version(before) == _version(after) == _version(named_after) and total == after.st_size,
                  "new_output_read_changed")
            return b"".join(pieces), _version(after)
        finally:
            os.close(descriptor)

    def read(self, name, *, cap=MAX_CONTROL_BYTES):
        raw, version = self._read(name, cap)
        pin = (_sha(raw), len(raw), version)
        _need(name not in self.pins or self.pins[name] == pin, "new_output_leaf_changed")
        self.pins[name] = pin
        return raw

    def publish(self, name, raw, *, cap=MAX_CONTROL_BYTES):
        _need(type(raw) is bytes and 0 < len(raw) <= cap <= MAX_PARENT_BYTES, "new_output_publication_bound_refused")
        self.check()
        digest = self.tree.publish(name, raw, cap=cap)
        _need(self.read(name, cap=cap) == raw, "new_output_publication_readback_refused")
        self.check()
        return digest

    def close(self):
        self.tree.close()


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class InventedPilotCaptureSelection:
    _bytes: bytes = field(repr=False)
    _token: object = field(repr=False)

    def canonical_bytes(self):
        _need(type(self) in {InventedPilotCaptureSelection, _PinnedActualSelection}
              and self._token is _TOKEN and _REGISTRY.get(self) == self._bytes, "genuine_capture_selection_required")
        return self._bytes

    def to_payload(self):return _decode(self.canonical_bytes())
    @property
    def sha256(self):return _sha(self.canonical_bytes())


@dataclass(frozen=True, slots=True, eq=False)
class _PinnedActualSelection(InventedPilotCaptureSelection):
    pass


def _seal(body, *, observed):
    value = (_PinnedActualSelection if observed else InventedPilotCaptureSelection)(_raw(body), _TOKEN)
    _REGISTRY[value] = value._bytes
    return value


def _empty_exposure():
    return {"schema": audit.EXPOSURE_SCHEMA, "records": []}


def _invented_selection(requests, *, exposure_inventory=None):
    _need(type(requests) in {list, tuple} and 1 <= len(requests) <= MAX_REQUESTS, "invented_request_bound_refused")
    rows = []
    for request in requests:
        request = _request(request)
        rows.append({"request": request, "request_sha256": _sha(_raw(request))})
    _need(len({item["request"]["accession_number"] for item in rows}) == len(rows), "selection_accession_duplicate")
    exposures = _empty_exposure() if exposure_inventory is None else exposure_inventory
    audit._exposures(exposures)
    return _seal({"fixture_only": True, "selection_period": "2021Q1", "requests": rows,
        "exposure_inventory_sha256": _sha(_raw(exposures)), "authority": dict(audit._AUTHORITY)}, observed=False)


def _fixture_root(root):
    try:
        old._fixture_root(root)
    except (ValueError, OSError, RuntimeError):
        raise PilotParentCaptureError("invented_outside_lane_root_required") from None


def _native_fixture_denial():
    exposure.bootstrap.custody._effective_denial(require_fork=False)
    try:os.execve("/usr/bin/security", ["security", "help"], {"PATH": "/usr/bin:/bin"})
    except OSError as exc:_need(exc.errno in {errno.EPERM, errno.EACCES}, "native_credential_exec_denial_required")
    else:raise PilotParentCaptureError("native_credential_exec_denial_required")


def _identity(head):
    _need(Path(__file__).resolve() == LANE_ROOT / SELF_PATH, "inactive_capture_source_refused")
    identity = exposure.bootstrap.custody._identity(head)
    own = exposure.bootstrap.custody._source_bytes(LANE_ROOT, (SELF_PATH, TEST_PATH))
    for name, digest in own.items():
        _need(_sha(exposure.bootstrap.custody._git(LANE_ROOT, "show", head + ":" + name)) == digest,
              "capture_source_not_committed")
    inventory = {**identity["source_sha256"], **own}
    return {**identity, "source_sha256": inventory, "source_inventory_sha256": _sha(_raw(inventory))}


def _activation_ready():
    _need(type(ACTUAL_SELECTION_PINS) is dict and set(ACTUAL_SELECTION_PINS) == {"reservation.json", "terminal.json", "complete.json"}
          and all(type(pin) is tuple and len(pin) == 2 and type(pin[0]) is str and _SHA.fullmatch(pin[0])
                  and type(pin[1]) is int and 0 < pin[1] <= 2 * 1024 * 1024 for pin in ACTUAL_SELECTION_PINS.values())
          and type(ACTUAL_SELECTION_SHA256) is str and _SHA.fullmatch(ACTUAL_SELECTION_SHA256)
          and type(ACTUAL_SELECTION_HEAD) is str and _HEAD.fullmatch(ACTUAL_SELECTION_HEAD),
          "actual_capture_not_activated_without_observed_selection_pins")


def _load_actual_selection():
    _activation_ready()
    # This exact protected output schema/location is qualified together with
    # the observed pins before activation. No caller path or payload is accepted.
    tree = selector.held_io._HeldCapture(LANE_ROOT.joinpath(*SELECTION_PARTS, SELECTION_AUDIT_ID), private=True, settle_ctime=True)
    try:
        _need(tree.names == set(ACTUAL_SELECTION_PINS), "selection_control_inventory_refused")
        controls = {}
        for name, (digest, size) in ACTUAL_SELECTION_PINS.items():
            stream = tree.open(name, size);raw = stream.read(size + 1)
            _need(len(raw) == size and _sha(raw) == digest, "selection_control_pin_refused")
            controls[name] = _decode(raw, allow_floats=name == "terminal.json")
        complete, terminal, reservation = controls["complete.json"], controls["terminal.json"], controls["reservation.json"]
        _need(set(complete) == {"schema", "audit_id", "reservation_sha256", "terminal_sha256", "worker_result"}
              and complete["schema"] == "insider-pilot-sec-fresh-selection-observer-v1/complete"
              and complete["audit_id"] == SELECTION_AUDIT_ID
              and complete["reservation_sha256"] == _sha(_raw(reservation))
              and complete["terminal_sha256"] == _sha(_raw(terminal)), "protected_selection_control_links_refused")
        worker = complete["worker_result"]
        _need(type(worker) is dict and set(worker) == {"schema", "audit_id", "registration", "registration_sha256", "execution_identity",
                  "prior_audit_complete_sha256", "exposure_inventory_sha256", "exposure_snapshot_sha256", "retained_body_inventory_sha256",
                  "selection", "selection_sha256", "source_roster", "parent_audit", "locator_quarantines", "locator_quarantine_jsonl_sha256",
                  "locator_quarantine_jsonl_bytes", "native_network_fork_allwrite_securityexec_denial", "new_provider_requests",
                  "credential_reads", "qc_accesses", "outcome_looks", "backtests", "dispatch_authorized", "canonical_admitted", "backtesting_ready"},
              "protected_selection_worker_schema_refused")
        identity = _source_identity(worker.get("execution_identity"), required_paths=(selection_runner.SELF_PATH,))
        _need(set(reservation) == {"schema", "registration", "execution_identity"}
              and reservation["schema"] == selection_runner.SCHEMA + "/reservation"
              and reservation["registration"] == selection_runner.REGISTRATION
              and reservation["execution_identity"] == identity
              and worker.get("schema") == selection_runner.SCHEMA and worker.get("audit_id") == SELECTION_AUDIT_ID
              and worker.get("registration") == selection_runner.REGISTRATION
              and worker.get("registration_sha256") == _sha(_raw(selection_runner.REGISTRATION))
              and worker.get("prior_audit_complete_sha256") == selection_runner.retained.PINS["complete.json"][0],
              "protected_selection_registration_refused")
        for key in ("new_provider_requests", "credential_reads", "qc_accesses", "outcome_looks", "backtests"):
            _need(type(worker.get(key)) is int and worker[key] == 0, "protected_selection_access_refused")
        for key in ("dispatch_authorized", "canonical_admitted", "backtesting_ready"):
            _need(worker.get(key) is False, "protected_selection_authority_refused")
        _need(worker.get("native_network_fork_allwrite_securityexec_denial") is True,
              "protected_selection_isolation_required")
        _need(set(terminal) == {"schema", "reservation_sha256", "elapsed_seconds", "exit_code", "stdout_bytes", "stdout_sha256",
                  "stderr_bytes", "stderr_sha256"}
              and terminal["schema"] == "insider-pilot-sec-fresh-selection-observer-v1/terminal"
              and terminal["reservation_sha256"] == _sha(_raw(reservation))
              and type(terminal["elapsed_seconds"]) in {int, float} and math.isfinite(terminal["elapsed_seconds"])
              and terminal["elapsed_seconds"] >= 0
              and type(terminal["stdout_bytes"]) is int and terminal["stdout_bytes"] == len(_raw(worker)) + 1
              and terminal["stdout_sha256"] == _sha(_raw(worker) + b"\n")
              and type(terminal["stderr_bytes"]) is int and terminal["stderr_bytes"] == 0
              and terminal["stderr_sha256"] == _sha(b""), "protected_selection_terminal_refused")
        _need(terminal.get("exit_code") == 0 and type(terminal.get("exit_code")) is int
              and worker.get("execution_identity", {}).get("head") == ACTUAL_SELECTION_HEAD,
              "protected_selection_success_lineage_required")
        payload = fresh.validate_selection_payload(worker["selection"])
        _need(_sha(_raw(payload)) == ACTUAL_SELECTION_SHA256 and payload["fixture_only"] is False
              and worker.get("selection_sha256") == ACTUAL_SELECTION_SHA256
              and payload["selected_count"] == MAX_REQUESTS, "observed_selection_payload_refused")
        _need(payload["source_roster_sha256"] == _sha(_raw(worker.get("source_roster")))
              and payload["parent_audit_sha256"] == _sha(_raw(worker.get("parent_audit")))
              and payload["quarter_bindings"] == worker["parent_audit"]["quarters"]
              and payload["exposure_inventory_sha256"] == worker.get("exposure_inventory_sha256")
              and payload["retained_candidate_inventory_sha256"] == worker.get("retained_body_inventory_sha256"),
              "protected_selection_completed_source_crosslinks_refused")
        tree.check()
        return _seal(payload, observed=True), tree
    except BaseException:
        tree.close();raise


class _PriorRoots:
    def __init__(self, selection):
        self.trees, self.raw, _ = exposure.bootstrap.bootstrap_exposures(exposure.actual_roots())
        try:
            body = _decode(self.raw)
            _need(_sha(self.raw) == selection["exposure_inventory_sha256"], "prior_exposure_inventory_changed")
            self.exposed_accessions = set(audit._exposures(body))
        except BaseException:
            self.close();raise

    def recheck(self):
        for tree in self.trees:tree.recheck()

    def close(self):
        failure = False
        for tree in reversed(self.trees):
            try:tree.close()
            except BaseException:failure = True
        self.trees = []
        if failure and sys.exc_info()[0] is None:raise PilotParentCaptureError("prior_root_cleanup_refused")


class _CaptureInputs:
    """Full opaque intake hashes at boundaries, strict versions per dispatch."""
    def __init__(self, selection):
        self.prior = self.intake = None
        try:
            self.prior = _PriorRoots(selection)
            self.intake = selector._HeldIntake()  # Initial all-84 full hash.
            self.intake.recheck()
            tree = next((tree for tree in self.prior.trees if tree.spec.root_id == "masters-v3"), None)
            _need(tree is not None, "current_master_tree_missing")
            master = source_runner._master(tree, "2021Q1")
            aliases = {row.archive_path: row.to_payload() for row in master.rows}
            bindings = {row.period: row for row in self.intake.bindings}
            binding = bindings["2021Q1"]
            for item in selection["requests"]:
                request, source = _request(item["request"]), item["source"]
                _need(request["quarterly_zip_sha256"] == source["quarterly_zip_sha256"] == binding.sha256
                      and request["submission_member_sha256"] == source["submission_member_sha256"]
                      and request["submission_header_line_sha256"] == source["submission_header_line_sha256"]
                      and request["schema_profile_sha256"] == source["schema_profile_sha256"] == self.intake.context["schema_profile_sha256"]
                      and request["master_decoded_sha256"] == master.source_sha256
                      and request["master_receipt_sha256"] == master.receipt_sha256
                      and request["archive_path"] in aliases
                      and all(aliases[request["archive_path"]][key] == request[key] for key in
                          ("accession_number", "form_type", "filing_date", "archive_path")), "current_intake_master_request_binding_refused")
            self.exposed_accessions = self.prior.exposed_accessions
        except BaseException:
            self.close();raise

    def recheck(self):
        self.prior.recheck()
        self.intake.tree.check()  # Strict ctime/version, all84 names and FDs.

    def final_recheck(self):
        self.recheck();self.intake.recheck();self.recheck()

    def close(self):
        active, failed = sys.exc_info()[0] is not None, False
        for held in (self.intake, self.prior):
            if held is not None:
                try:held.close()
                except BaseException:failed = True
        self.intake = self.prior = None
        if failed and not active:raise PilotParentCaptureError("capture_input_cleanup_refused")


class _FixturePrior:
    def __init__(self):self.exposed_accessions = set()
    def recheck(self):pass
    def close(self):pass


class _DispatchContext:
    def __init__(self, *, observed, recheck, selection, rows, prove_start):
        self.observed, self.recheck, self.selection, self.rows, self.prove_start = observed, recheck, selection, rows, prove_start
        self.pending = None;self.attempted = set()


def _production_transport(context, ordinal, url, headers, maximum):
    _activation_ready()
    _need(type(context) is _DispatchContext and context.observed is True
          and type(context.selection) is _PinnedActualSelection and context.pending == ordinal
          and ordinal not in context.attempted and maximum == MAX_PARENT_BYTES
          and url == context.rows[ordinal]["request"]["url"], "production_dispatch_context_refused")
    _need(_DISPATCHES.get(context) == (context.selection.sha256, id(context.recheck), id(context.prove_start), id(context.rows))
          and context.selection.sha256 == ACTUAL_SELECTION_SHA256, "production_dispatch_seal_refused")
    context.recheck()
    context.prove_start(ordinal)
    _need(threading.current_thread() is threading.main_thread() and hasattr(signal, "setitimer"),
          "native_transport_deadline_unavailable")
    prior_timer = signal.getitimer(signal.ITIMER_REAL)
    _need(prior_timer == (0.0, 0.0), "preexisting_process_timer_refused")
    previous = signal.getsignal(signal.SIGALRM)
    def expired(*_):raise _DeadlineExceeded()
    signal.signal(signal.SIGALRM, expired)
    context.attempted.add(ordinal);context.pending = None
    start = time.monotonic()
    try:
        signal.setitimer(signal.ITIMER_REAL, TRANSPORT_WALL_SECONDS)
        response = _RAW_TRANSPORT(url, headers, maximum)
        _need(time.monotonic() - start <= TRANSPORT_WALL_SECONDS, "transport_wall_deadline_refused")
        return response
    except _DeadlineExceeded:
        raise PilotParentCaptureError("transport_wall_deadline_refused") from None
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _close_all(folders, prior, lock_fd, locked):
    active, failed = sys.exc_info()[0] is not None, False
    if lock_fd is not None:
        try:
            if locked:fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except BaseException:failed = True
        try:os.close(lock_fd)
        except BaseException:failed = True
    for folder in reversed(folders):
        try:folder.close()
        except BaseException:failed = True
    if prior is not None:
        try:prior.close()
        except BaseException:failed = True
    if failed and not active:raise PilotParentCaptureError("capture_cleanup_refused")


def _capture(selection, *, root, contact, transport, guard, prior_open, observed,
             clock=custody._utc, monotonic_ns=time.monotonic_ns, sleep=time.sleep, free_bytes=None, execution_identity=None):
    _need(type(selection) is (_PinnedActualSelection if observed else InventedPilotCaptureSelection), "selection_mode_required")
    body = selection.to_payload();rows = body["requests"]
    _zero_authority(body.get("authority"))
    _need(body["fixture_only"] is (not observed) and 1 <= len(rows) <= MAX_REQUESTS
          and body["authority"] == audit._AUTHORITY, "selection_scope_refused")
    if observed:
        _activation_ready();_need(root == LANE_ROOT and transport is _production_transport
            and contact in {old._stdin_contact, old._getpass_contact}, "fixed_production_front_required")
        _need(threading.current_thread() is threading.main_thread() and hasattr(signal, "setitimer"), "deadline_preflight_refused")
    else:
        _fixture_root(root);_need(callable(transport) and transport is not _RAW_TRANSPORT and transport is not _production_transport
            and contact is not old._stdin_contact and contact is not old._getpass_contact, "invented_transport_only")
        _native_fixture_denial()
    for row in rows:
        _request(row["request"]);_need(row["request_sha256"] == _sha(_raw(row["request"])), "selected_request_hash_refused")
    guard();prior = None;folders = [];lock_fd = None;locked = False
    try:
        prior = prior_open();prior.recheck()
        _need(not any(item["request"]["accession_number"] in prior.exposed_accessions for item in rows), "selected_accession_already_consumed")
        base = _NewDirectory(root.joinpath(*ARTIFACT_PARTS), create=True);folders.append(base)
        claims = _NewDirectory(base.path / "claims", create=True);folders.append(claims)
        runs = _NewDirectory(base.path / "runs", create=True);folders.append(runs)
        if not base.tree.exists("capture.lock"):base.publish("capture.lock", LOCK_BYTES)
        lock_fd = os.open("capture.lock", os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=base.fd)
        lock_version = _version(os.fstat(lock_fd));fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB);locked = True
        _need(base.read("capture.lock", cap=1024) == LOCK_BYTES and set(os.listdir(base.fd)) == {"claims", "runs", "capture.lock"}, "fresh_namespace_refused")
        _need(os.listdir(claims.fd) == [] and os.listdir(runs.fd) == [], "first64_namespace_cannot_resume")
        capacity = free_bytes() if free_bytes is not None else os.fstatvfs(base.fd).f_bavail * os.fstatvfs(base.fd).f_frsize
        _need(type(capacity) is int and capacity >= MIN_FREE_BYTES + len(rows) * MAX_PARENT_BYTES, "capture_disk_reserve_refused")
        os.mkdir(CAPTURE_ID, 0o700, dir_fd=runs.fd);os.fsync(runs.fd)
        run = _NewDirectory(runs.path / CAPTURE_ID);folders.append(run)
        objects = _NewDirectory(run.path / "objects", create=True);folders.append(objects)
        reservation = {"schema": SCHEMA + "/reservation", "capture_id": CAPTURE_ID, "fixture_only": not observed,
            "selection_sha256": selection.sha256, "selection": body, "reserved_at_utc": custody._stamp(clock),
            "capture_execution_identity": execution_identity if observed else {"fixture_only": True},
            "selection_execution_head": ACTUAL_SELECTION_HEAD if observed else None,
            "planned_requests": len(rows), "maximum_attempts_per_request": 1, "maximum_body_bytes": MAX_PARENT_BYTES,
            "minimum_completion_spacing_ns": MIN_COMPLETION_INTERVAL_NS, "transport_wall_seconds": TRANSPORT_WALL_SECONDS,
            "claim_policy": "just_in_time_permanent_accession", "contact_value_stored_or_hashed": False,
            "authority": dict(audit._AUTHORITY)}
        reservation_sha = run.publish("reservation.json", _raw(reservation))
        expected_claims, expected_objects, expected_run = set(), set(), {"reservation.json", "objects"}
        def check():
            guard();prior.recheck()
            _need(_version(os.fstat(lock_fd)) == lock_version
                  == _version(os.stat("capture.lock", dir_fd=base.fd, follow_symlinks=False)), "fresh_lock_changed")
            for folder in folders:folder.check()
            _need(set(os.listdir(base.fd)) == {"claims", "runs", "capture.lock"}
                  and set(os.listdir(runs.fd)) == {CAPTURE_ID} and set(os.listdir(claims.fd)) == expected_claims
                  and set(os.listdir(run.fd)) == expected_run and set(os.listdir(objects.fd)) == expected_objects, "fresh_journal_inventory_changed")
        check()
        contact_value = custody._contact(contact() if callable(contact) else contact, observed=observed)
        contact_sha = run.publish("contact-validated.json", _raw({"schema": SCHEMA + "/contact-validation",
            "reservation_sha256": reservation_sha, "contact_present": True, "contact_value_stored_or_hashed": False,
            "validated_at_utc": custody._stamp(clock)}));expected_run.add("contact-validated.json");check()
        headers = {"User-Agent": f"InsiderBuyingResearch-pilot-2021Q1-first64/1.0 ({contact_value})",
            "Accept": "*/*", "Accept-Encoding": "identity", "Connection": "close"}
        armed = {}
        def prove_start(ordinal):
            _need(ordinal in armed, "durable_start_latch_required")
            start_sha, claim_sha, claim_name = armed[ordinal]
            start = _decode(run.read(f"request-{ordinal:03d}-start.json"))
            _need(_sha(_raw(start)) == start_sha and start["claim_sha256"] == claim_sha
                  and start["request_sha256"] == rows[ordinal]["request_sha256"]
                  and _sha(claims.read(claim_name)) == claim_sha, "durable_start_claim_binding_refused")
        dispatch = _DispatchContext(observed=observed, recheck=check, selection=selection, rows=rows, prove_start=prove_start)
        if observed:
            _DISPATCHES[dispatch] = (selection.sha256, id(check), id(prove_start), id(rows))
        results, total, completed, header_bound, previous_finish = [], 0, 0, 0, None
        for ordinal, row in enumerate(rows):
            check();request = row["request"];name = _sha(request["accession_number"].encode("ascii")) + ".json"
            _need(name not in expected_claims and request["accession_number"] not in prior.exposed_accessions, "accession_permanently_consumed")
            capacity = free_bytes() if free_bytes is not None else os.fstatvfs(base.fd).f_bavail * os.fstatvfs(base.fd).f_frsize
            _need(type(capacity) is int and capacity >= MIN_FREE_BYTES + (len(rows)-ordinal) * MAX_PARENT_BYTES, "remaining_disk_reserve_refused")
            claim_sha = claims.publish(name, _raw({"schema": SCHEMA + "/request-claim", "capture_id": CAPTURE_ID,
                "reservation_sha256": reservation_sha, "selection_sha256": selection.sha256, "request": row,
                "claimed_at_utc": custody._stamp(clock)}));expected_claims.add(name)
            if previous_finish is not None:
                now = monotonic_ns();_need(type(now) is int and now >= previous_finish, "monotonic_clock_refused")
                if now-previous_finish < MIN_COMPLETION_INTERVAL_NS:sleep((MIN_COMPLETION_INTERVAL_NS-now+previous_finish)/1_000_000_000)
            started = monotonic_ns()
            _need(type(started) is int and started >= 0 and (previous_finish is None or started-previous_finish >= MIN_COMPLETION_INTERVAL_NS), "completion_spacing_refused")
            start_name = f"request-{ordinal:03d}-start.json"
            start_sha = run.publish(start_name, _raw({"schema": SCHEMA + "/attempt-start", "ordinal": ordinal, "attempt": 1,
                "request_sha256": row["request_sha256"], "reservation_sha256": reservation_sha, "claim_sha256": claim_sha,
                "started_utc": custody._stamp(clock), "started_monotonic_ns": started}));expected_run.add(start_name)
            check();armed[ordinal] = (start_sha, claim_sha, name);dispatch.pending = ordinal
            response = None
            try:
                response = (_production_transport(dispatch, ordinal, request["url"], headers, MAX_PARENT_BYTES) if observed
                    else transport(request["url"], headers, MAX_PARENT_BYTES))
            except Exception:
                pass  # Irreversible claim/start, no retry, unknown response.
            check()
            status = body_sha = body_size = header_sha = None
            retained, qualified, stop = False, False, True
            disposition = "ambiguous_transport_failure_no_retry"
            if response is not None:
                _need(type(response) is SecHttpResult and type(response.status) is int and 100 <= response.status <= 599
                    and type(response.headers) is tuple and len(response.headers) <= 64
                    and all(type(pair) is tuple and len(pair) == 2 and all(type(v) is str for v in pair) for pair in response.headers)
                    and len(_raw(response.headers)) <= 16384 and type(response.body) is bytes and len(response.body) <= MAX_PARENT_BYTES,
                    "response_metadata_refused")
                status = response.status
                persisting = False
                try:
                    for pair in response.headers:
                        for field in pair:custody._screen_contact_echo(field, contact_value)
                    custody._screen_contact_echo(_raw(response.headers).decode(), contact_value)
                    header_sha = _sha(_raw(response.headers))
                    if status != 200:
                        _need(response.body == b"", "non200_body_must_be_unread")
                        disposition = "http_refused_no_retry"
                    else:
                        raw = _strict_selected_response(response, max_bytes=MAX_PARENT_BYTES)
                        custody._screen_contact_echo(raw.decode("utf-8", "replace"), contact_value)
                        body_sha, body_size = _sha(raw), len(raw)
                        _need(total+body_size <= len(rows)*MAX_PARENT_BYTES, "total_body_bound_refused")
                        # Persistence failures are NOT source/privacy failures.
                        try:old._envelope_and_header(raw, request)
                        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):qualified = False
                        else:qualified = True
                        object_name = body_sha + ".bin"
                        persisting = True
                        if object_name in expected_objects:
                            _need(objects.read(object_name, cap=MAX_PARENT_BYTES) == raw, "repeated_body_object_changed")
                        else:
                            objects.publish(object_name, raw, cap=MAX_PARENT_BYTES);expected_objects.add(object_name)
                        persisting = False
                        retained = True;completed += 1;total += body_size;header_bound += qualified
                        disposition = "request_bound_parent_retained_header_bound" if qualified else "complete_raw_parent_retained_header_quarantined_no_retry"
                        stop = not qualified
                except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
                    if persisting:raise
                    disposition = "response_privacy_or_framing_refused_no_retry"
            previous_finish = monotonic_ns();_need(type(previous_finish) is int and previous_finish >= started, "completion_clock_refused")
            result_name = f"request-{ordinal:03d}-result.json"
            result = {"schema": SCHEMA + "/attempt-result", "ordinal": ordinal, "attempt": 1,
                "request_sha256": row["request_sha256"], "start_sha256": start_sha, "status": status,
                "response_headers_sha256": header_sha, "body_sha256": body_sha, "body_size_bytes": body_size,
                "body_retained": retained, "header_identity_bound": qualified, "disposition": disposition,
                "finished_utc": custody._stamp(clock), "finished_monotonic_ns": previous_finish}
            result_sha = run.publish(result_name, _raw(result));expected_run.add(result_name)
            results.append({"result_name": result_name, "result_sha256": result_sha});check()
            if stop:break
        if observed:prior.final_recheck()
        report = {"schema": SCHEMA + "/complete", "capture_id": CAPTURE_ID, "fixture_only": not observed,
            "capture_execution_identity": execution_identity if observed else {"fixture_only": True},
            "selection_execution_head": ACTUAL_SELECTION_HEAD if observed else None,
            "selection_sha256": selection.sha256, "reservation_sha256": reservation_sha, "contact_validation_sha256": contact_sha,
            "planned_requests": len(rows), "permanent_claims_created": len(expected_claims), "started_requests": len(results),
            "terminal_result_records": len(results), "raw_bodies_retained": completed, "header_bound_bodies": header_bound,
            "header_quarantined_bodies": completed-header_bound, "retained_body_bytes": total,
            "planned_unclaimed_unattempted": len(rows)-len(results), "all_requested_attempted": len(results) == len(rows),
            "capture_completed_without_refusal": len(results) == len(rows) and completed == header_bound == len(rows),
            "results": results, "completed_at_utc": custody._stamp(clock), "old_roots_written": False,
            "full_xml_projection_attempts": 0, "authority": dict(audit._AUTHORITY)}
        report_sha = run.publish("complete.json", _raw(report));expected_run.add("complete.json");check()
        if observed:prior.final_recheck()
        return {"capture_id": CAPTURE_ID, "fixture_only": not observed, "report_sha256": report_sha,
            **{key: report[key] for key in ("planned_requests", "started_requests", "raw_bodies_retained", "header_bound_bodies",
                "planned_unclaimed_unattempted", "capture_completed_without_refusal")}, "authority": dict(audit._AUTHORITY)}
    finally:
        _close_all(folders, prior, lock_fd, locked)


def _run_invented_capture(selection, *, root, transport, contact="invented@unit.test", guard=lambda: None,
                          prior_open=_FixturePrior, **kwargs):
    return _capture(selection, root=root, transport=transport, contact=contact, guard=guard,
        prior_open=prior_open, observed=False, **kwargs)


def _verify_capture(*, root, expected_report_sha256, fixture_only, execution_identity=None):
    """Exact control/body/hash plus header-only replay; no ownership XML parse."""
    _digest(expected_report_sha256)
    folders = []
    try:
        base = _NewDirectory(root.joinpath(*ARTIFACT_PARTS));folders.append(base)
        claims = _NewDirectory(base.path / "claims");folders.append(claims)
        runs = _NewDirectory(base.path / "runs");folders.append(runs)
        run = _NewDirectory(runs.path / CAPTURE_ID);folders.append(run)
        objects = _NewDirectory(run.path / "objects");folders.append(objects)
        _need(set(os.listdir(base.fd)) == {"claims", "runs", "capture.lock"}
              and set(os.listdir(runs.fd)) == {CAPTURE_ID} and base.read("capture.lock", cap=1024) == LOCK_BYTES,
              "capture_verifier_namespace_refused")
        report_raw = run.read("complete.json");_need(_sha(report_raw) == expected_report_sha256, "capture_report_hash_refused")
        report = _decode(report_raw);reservation_raw = run.read("reservation.json");reservation = _decode(reservation_raw)
        _need(set(report) == {"schema", "capture_id", "fixture_only", "capture_execution_identity", "selection_execution_head",
                  "selection_sha256", "reservation_sha256", "contact_validation_sha256", "planned_requests", "permanent_claims_created",
                  "started_requests", "terminal_result_records", "raw_bodies_retained", "header_bound_bodies", "header_quarantined_bodies",
                  "retained_body_bytes", "planned_unclaimed_unattempted", "all_requested_attempted", "capture_completed_without_refusal",
                  "results", "completed_at_utc", "old_roots_written", "full_xml_projection_attempts", "authority"}
              and set(reservation) == {"schema", "capture_id", "fixture_only", "selection_sha256", "selection", "reserved_at_utc",
                  "capture_execution_identity", "selection_execution_head", "planned_requests", "maximum_attempts_per_request",
                  "maximum_body_bytes", "minimum_completion_spacing_ns", "transport_wall_seconds", "claim_policy",
                  "contact_value_stored_or_hashed", "authority"}, "capture_report_exact_schema_refused")
        for record in (report, reservation):_zero_authority(record.get("authority"))
        _clock_value(report["completed_at_utc"]);_clock_value(reservation["reserved_at_utc"])
        _need(report.get("schema") == SCHEMA + "/complete" and report.get("capture_id") == CAPTURE_ID
              and report.get("fixture_only") is fixture_only and report.get("authority") == audit._AUTHORITY
              and report.get("reservation_sha256") == _sha(reservation_raw)
              and reservation.get("schema") == SCHEMA + "/reservation" and reservation.get("capture_id") == CAPTURE_ID
              and reservation.get("fixture_only") is fixture_only and reservation.get("authority") == audit._AUTHORITY
              and report.get("capture_execution_identity") == reservation.get("capture_execution_identity")
              and report.get("selection_execution_head") == reservation.get("selection_execution_head"), "capture_report_reservation_refused")
        selection = reservation.get("selection")
        _zero_authority(selection.get("authority") if type(selection) is dict else None)
        _need(type(selection) is dict and selection.get("fixture_only") is fixture_only
              and selection.get("authority") == audit._AUTHORITY
              and report.get("selection_sha256") == reservation.get("selection_sha256") == _sha(_raw(selection)),
              "capture_selection_binding_refused")
        rows = selection.get("requests");results = report.get("results")
        _need(type(rows) is list and 1 <= len(rows) <= MAX_REQUESTS and type(results) is list
              and 1 <= len(results) <= len(rows), "capture_verifier_request_count_refused")
        _need(type(reservation["planned_requests"]) is int and reservation["planned_requests"] == len(rows)
              and type(reservation["maximum_attempts_per_request"]) is int and reservation["maximum_attempts_per_request"] == 1
              and type(reservation["maximum_body_bytes"]) is int and reservation["maximum_body_bytes"] == MAX_PARENT_BYTES
              and type(reservation["minimum_completion_spacing_ns"]) is int and reservation["minimum_completion_spacing_ns"] == MIN_COMPLETION_INTERVAL_NS
              and type(reservation["transport_wall_seconds"]) is int and reservation["transport_wall_seconds"] == TRANSPORT_WALL_SECONDS
              and reservation["claim_policy"] == "just_in_time_permanent_accession"
              and reservation["contact_value_stored_or_hashed"] is False, "capture_verifier_reservation_limits_refused")
        if not fixture_only:
            _activation_ready();fresh.validate_selection_payload(selection)
            _need(len(rows) == MAX_REQUESTS and _sha(_raw(selection)) == ACTUAL_SELECTION_SHA256,
                  "actual_capture_selection_pin_refused")
            _need(report["capture_execution_identity"] == _source_identity(execution_identity, required_paths=(SELF_PATH, TEST_PATH))
                  and report["selection_execution_head"] == ACTUAL_SELECTION_HEAD,
                  "actual_capture_execution_source_binding_refused")
        _need(len({row["request"]["accession_number"] for row in rows}) == len(rows), "capture_verifier_accession_duplicate")
        contact_raw = run.read("contact-validated.json");contact = _decode(contact_raw)
        _need(set(contact) == {"schema", "reservation_sha256", "contact_present", "contact_value_stored_or_hashed", "validated_at_utc"},
              "capture_contact_exact_schema_refused")
        _clock_value(contact["validated_at_utc"])
        _need(_sha(contact_raw) == report.get("contact_validation_sha256")
              and contact.get("schema") == SCHEMA + "/contact-validation"
              and contact.get("reservation_sha256") == _sha(reservation_raw)
              and contact.get("contact_present") is True and contact.get("contact_value_stored_or_hashed") is False,
              "private_contact_control_binding_refused")
        expected_run, expected_objects, expected_claims = {"reservation.json", "contact-validated.json", "complete.json", "objects"}, set(), set()
        completed = qualified = total = 0;previous = None;stopped = False
        for ordinal, (row, descriptor) in enumerate(zip(rows, results)):
            request = _request(row["request"])
            _need(row["request_sha256"] == _sha(_raw(request)) and type(descriptor) is dict
                  and set(descriptor) == {"result_name", "result_sha256"}, "capture_verifier_request_hash_refused")
            result_name, start_name = f"request-{ordinal:03d}-result.json", f"request-{ordinal:03d}-start.json"
            _need(descriptor["result_name"] == result_name, "capture_verifier_order_refused")
            result_raw = run.read(result_name);result = _decode(result_raw);start_raw = run.read(start_name);start = _decode(start_raw)
            claim_name = _sha(request["accession_number"].encode("ascii")) + ".json"
            claim_raw = claims.read(claim_name);claim = _decode(claim_raw);expected_claims.add(claim_name)
            _need(set(result) == {"schema", "ordinal", "attempt", "request_sha256", "start_sha256", "status", "response_headers_sha256",
                      "body_sha256", "body_size_bytes", "body_retained", "header_identity_bound", "disposition", "finished_utc", "finished_monotonic_ns"}
                  and set(start) == {"schema", "ordinal", "attempt", "request_sha256", "reservation_sha256", "claim_sha256", "started_utc", "started_monotonic_ns"}
                  and set(claim) == {"schema", "capture_id", "reservation_sha256", "selection_sha256", "request", "claimed_at_utc"},
                  "capture_verifier_journal_exact_schema_refused")
            for record, key in ((claim, "claimed_at_utc"), (start, "started_utc"), (result, "finished_utc")):_clock_value(record[key])
            _need(_sha(result_raw) == descriptor["result_sha256"]
                  and result.get("schema") == SCHEMA + "/attempt-result" and start.get("schema") == SCHEMA + "/attempt-start"
                  and claim.get("schema") == SCHEMA + "/request-claim" and claim.get("capture_id") == CAPTURE_ID
                  and claim.get("request") == row and claim.get("selection_sha256") == report["selection_sha256"]
                  and claim.get("reservation_sha256") == _sha(reservation_raw)
                  and start.get("reservation_sha256") == _sha(reservation_raw) and start.get("claim_sha256") == _sha(claim_raw)
                  and result.get("start_sha256") == _sha(start_raw)
                  and all(type(record.get(key)) is int and record[key] == want for record in (start, result)
                      for key, want in (("ordinal", ordinal), ("attempt", 1)))
                  and start.get("request_sha256") == result.get("request_sha256") == row["request_sha256"],
                  "capture_verifier_claim_start_result_binding_refused")
            started, finished = start.get("started_monotonic_ns"), result.get("finished_monotonic_ns")
            _need(type(started) is int and type(finished) is int and 0 <= started <= finished
                  and (previous is None or started-previous >= MIN_COMPLETION_INTERVAL_NS), "capture_verifier_spacing_refused")
            previous = finished
            retained, bound = result.get("body_retained"), result.get("header_identity_bound")
            _need(type(retained) is bool and type(bound) is bool and (not bound or retained), "capture_verifier_body_facts_refused")
            disposition = result.get("disposition")
            _need(result["status"] is None or type(result["status"]) is int and 100 <= result["status"] <= 599,
                  "capture_verifier_status_refused")
            if result["response_headers_sha256"] is not None:_digest(result["response_headers_sha256"])
            if retained:
                digest, size = result.get("body_sha256"), result.get("body_size_bytes");_digest(digest)
                _need(type(size) is int and 0 < size <= MAX_PARENT_BYTES and result.get("status") == 200
                      and type(result.get("status")) is int and result["response_headers_sha256"] is not None,
                      "capture_verifier_retained_body_shape_refused")
                raw = objects.read(digest + ".bin", cap=MAX_PARENT_BYTES)
                _need(_sha(raw) == digest and len(raw) == size, "capture_verifier_body_hash_refused")
                expected_objects.add(digest + ".bin")
                try:old._envelope_and_header(raw, request)
                except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):observed_bound = False
                else:observed_bound = True
                _need(bound is observed_bound and disposition == ("request_bound_parent_retained_header_bound" if bound
                    else "complete_raw_parent_retained_header_quarantined_no_retry"), "capture_verifier_header_disposition_refused")
                completed += 1;qualified += bound;total += size;stopped = not bound
            else:
                _need(not bound and disposition in {"ambiguous_transport_failure_no_retry", "http_refused_no_retry",
                    "response_privacy_or_framing_refused_no_retry"}, "capture_verifier_refusal_disposition_refused")
                if disposition == "ambiguous_transport_failure_no_retry":
                    _need(all(result.get(key) is None for key in ("status", "response_headers_sha256", "body_sha256", "body_size_bytes")),
                          "capture_verifier_ambiguous_measurement_refused")
                if disposition == "http_refused_no_retry":
                    _need(type(result.get("status")) is int and result["status"] != 200
                          and result["response_headers_sha256"] is not None
                          and result.get("body_sha256") is None and result.get("body_size_bytes") is None,
                          "capture_verifier_http_refusal_measurement_refused")
                if disposition == "response_privacy_or_framing_refused_no_retry":
                    _need(result["status"] is not None and result["body_sha256"] is None and result["body_size_bytes"] is None,
                          "capture_verifier_unretained_privacy_measurement_refused")
                stopped = True
            _need(not stopped or ordinal == len(results)-1, "capture_continued_after_refusal")
            expected_run.update((start_name, result_name))
        _need(len(results) == len(rows) or stopped, "capture_verifier_unexplained_early_stop")
        expected = {"planned_requests": len(rows), "permanent_claims_created": len(results), "started_requests": len(results),
            "terminal_result_records": len(results), "raw_bodies_retained": completed, "header_bound_bodies": qualified,
            "header_quarantined_bodies": completed-qualified, "retained_body_bytes": total,
            "planned_unclaimed_unattempted": len(rows)-len(results)}
        _need(all(type(report.get(key)) is int and report[key] == want for key, want in expected.items())
              and report.get("all_requested_attempted") is (len(rows) == len(results))
              and report.get("capture_completed_without_refusal") is (len(results) == len(rows) and completed == qualified == len(rows))
              and report.get("old_roots_written") is False and type(report.get("full_xml_projection_attempts")) is int
              and report["full_xml_projection_attempts"] == 0, "capture_verifier_report_accounting_refused")
        _need(set(os.listdir(claims.fd)) == expected_claims and set(os.listdir(objects.fd)) == expected_objects
              and set(os.listdir(run.fd)) == expected_run, "capture_verifier_complete_inventory_refused")
        for folder in folders:folder.check()
        return {"capture_id": CAPTURE_ID, "fixture_only": fixture_only, "report_sha256": expected_report_sha256,
            **expected, "capture_completed_without_refusal": report["capture_completed_without_refusal"],
            "full_xml_projection_attempts": 0, "authority": dict(audit._AUTHORITY)}
    finally:
        _close_all(folders, None, None, False)


def verify_invented_capture(root, expected_report_sha256):
    _fixture_root(root);_native_fixture_denial()
    return _verify_capture(root=root, expected_report_sha256=expected_report_sha256, fixture_only=True)


def verify_actual_capture(*, expected_report_sha256, execution_identity):
    """Native-denied fixed-root replay, never dispatch or XML interpretation.

    The trusted launcher must establish Git/clean-head identity before launch
    and recheck it afterward. The isolated child independently binds current
    and frozen bytes to that supplied image; it does not claim to run Git
    under the required process-fork denial.
    """
    _activation_ready()
    _need(sys.flags.isolated == sys.flags.no_site == sys.flags.dont_write_bytecode == 1
          and sys.pycache_prefix == source_runner.EMPTY_CACHE_PREFIX, "isolated_capture_verifier_required")
    source_runner._prove_isolation()
    identity = _source_identity(execution_identity, required_paths=(SELF_PATH, TEST_PATH))
    def current():
        _need(exposure.bootstrap.custody._source_bytes(LANE_ROOT, tuple(identity["source_sha256"])) == identity["source_sha256"]
              and exposure.bootstrap.custody._source_bytes(LANE_ROOT, tuple(source_runner.FROZEN)) == source_runner.FROZEN,
              "capture_verifier_current_or_frozen_source_changed")
    current()
    result = _verify_capture(root=LANE_ROOT, expected_report_sha256=expected_report_sha256,
        fixture_only=False, execution_identity=identity)
    current()
    return {**result, "native_network_fork_allwrite_securityexec_denial": True,
        "source_identity_semantics": "trusted_launcher_git_identity_independent_child_current_and_frozen_bytes",
        "new_provider_requests": 0, "credential_reads": 0, "qc_accesses": 0, "outcome_looks": 0, "backtests": 0}


def run_actual_capture(*, expected_head, contact_mode="stdin"):
    _activation_ready()
    _need(contact_mode in {"stdin", "getpass"}, "private_contact_mode_refused")
    before = _identity(expected_head);selection, hold = _load_actual_selection()
    try:
        def guard():
            _need(_identity(expected_head) == before, "committed_capture_source_changed")
            hold.check()
            for name, stream, _, cap in hold.handles:
                _need(selector.held_io._hash_stream(stream, cap) == ACTUAL_SELECTION_PINS[name], "selection_control_changed")
        return _capture(selection, root=LANE_ROOT, transport=_production_transport,
            contact=old._stdin_contact if contact_mode == "stdin" else old._getpass_contact,
            guard=guard, prior_open=lambda: _CaptureInputs(selection.to_payload()), observed=True, execution_identity=before)
    finally:
        hold.close()


def main(argv=None):
    parser = argparse.ArgumentParser();parser.add_argument("--expected-head", required=True)
    parser.add_argument("--contact-mode", choices=("stdin", "getpass"), default="stdin")
    args = parser.parse_args(argv);saved = old._protect_stdin_echo()
    try:
        result = run_actual_capture(expected_head=args.expected_head, contact_mode=args.contact_mode)
        print(_raw(result).decode());return 0 if result["capture_completed_without_refusal"] else 2
    except Exception:
        sys.stderr.write("REFUSED: fresh pilot capture stopped; preserve every claim and start\n");return 2
    finally:
        old._restore_stdin_echo(saved)


if __name__ == "__main__":
    raise SystemExit(main())
