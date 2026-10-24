"""One fresh, offline-only full-original structural corroboration operation.

The parent sees source/control bytes and hashes only. Complete original parents
and quarter data are interpreted only by a source-captured -I/-S/-B worker after
native process-tree network, fork, Keychain-exec and write-confinement probes.
Frozen captures, original v2 quarantine and all four frozen v3 files are inputs,
not rewritten or impersonated. Structural agreement is never canonical/PIT.
"""
from __future__ import annotations

import argparse
import base64
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

from research import insider_buying_sec_2006q1_parent_projection_v1 as original
from research import insider_buying_sec_2006q1_original_admission_v1 as pure
from research import insider_buying_sec_2006q1_pem_reassessment_runner as previous


SCHEMA = "insider-2006q1-isolated-full-original-structural-corroboration-v1"
SELF_PATH = "research/insider_buying_sec_2006q1_original_admission_runner.py"
PURE_PATH = "research/insider_buying_sec_2006q1_original_admission_v1.py"
PARSER_PATH = "research/insider_buying_sec_early_original_parent_v1.py"
SOURCE_SEEDS = frozenset({SELF_PATH, PURE_PATH, PARSER_PATH})
OUTPUT_PARTS = ("artifacts", "insider_buying", "sec_2006q1_original_admission_v1")
AUDIT_ID = "ib-2006q1-original64-structural-admission-20261024-once"
CAPTURE_REPORT_SHA256 = "7d42a6634bf378f159f00e62697eaac446b41038f276f05ca12fe524e8a9076a"
MAX_ASSESSMENT_BYTES = pure.MAX_ASSESSMENT_BYTES
MAX_CONTROL_BYTES = original.MAX_CONTROL_BYTES
MAX_LEDGER_BYTES = 2 * 1024 * 1024
MAX_CONTEXT_BYTES = original.MAX_WORKER_CONTEXT_BYTES
FILES = frozenset({"reservation.json", "assessment.json", "parent-admission.json", "complete.json"})
COMPLETE_KEYS = frozenset({"schema", "audit_id", "fixture_only", "current_execution_identity", "frozen_sources", "reservation_sha256",
    "pinned_metadata_evidence", "capture_id", "capture_report_sha256", "capture_execution_head",
    "capture_execution_source_inventory_sha256", "bootstrap_execution_head", "original_preparation_producer_commit",
    "original_preparation_completion_sha256", "original_preparation_assessment_sha256", "assessment_sha256", "assessment_bytes",
    "parent_ledger_sha256", "parent_ledger_bytes", "counts", "form_counts", "accounting_sha256", "parsed_snapshot_id",
    "parsed_lineage_hash", "census_quarter_sha256", "whole_quarter_identity_sha256", "frozen_baseline_assessment_sha256",
    "frozen_baseline_accounting_sha256", "source_execution", "source_only_bootstrap_sha256",
    "effective_process_tree_network_denial", "effective_process_fork_denial", "effective_keychain_exec_denial",
    "writes_confined_to_fresh_output_by_launcher", "authority"})
COUNT_KEYS = frozenset({"source_filings", "target_filings", "context_filings", "selected_parents", "retained_parent_bodies",
    "structurally_bound_original_parents", "parser_quarantined_parents", "unavailable_selected_parents",
    "structurally_bound_noncanonical_filings", "quarantined_filings", "target_original_binding_missing",
    "retained_parent_bytes", "preserved_capture_header_quarantines"})
_PHASES = frozenset({"parent_preflight", "parent_original_sources", "parent_output_reservation", "parent_captured_sources",
    "parent_worker_launch", "parent_worker_result", "parent_final_output_check", "worker_bootstrap_context",
    "worker_bootstrap_source_decode", "worker_bootstrap_import", "worker_execution", "worker_preflight",
    "worker_output_reservation", "worker_isolation", "worker_preparation", "worker_capture", "worker_composition",
    "worker_replay", "worker_publication", "worker_readback", "worker_cleanup"})
_CLASS_NAMES = frozenset({"OriginalAdmissionRunnerError", "OriginalAdmissionError", "OSError", "ValueError",
    "TypeError", "KeyError", "SubprocessError", "other_refusal"})

SOURCE_ONLY_BOOTSTRAP = r'''
import base64, errno, hashlib, json, sys, types
consumer = None
phase = "worker_bootstrap_context"
try:
    def need(value):
        if not value: raise ValueError("source-only original context refused")
    raw = sys.stdin.buffer.read(33554433)
    need(0 < len(raw) <= 33554432)
    envelope = json.loads(raw)
    need(type(envelope) is dict and set(envelope) == {"sources", "parent_context", "audit_id", "expected_head"})
    rows = envelope["sources"]
    need(type(rows) is list)
    selected = [r for r in rows if type(r) is dict and r.get("path") == "research/insider_buying_affected_quarter_isolation.py"]
    need(len(selected) == 1)
    helper_raw = base64.b64decode(selected[0]["source_b64"], validate=True)
    need(hashlib.sha256(helper_raw).hexdigest() == selected[0]["sha256"])
    helper = types.ModuleType("_original_admission_captured_imports")
    helper.__file__ = "/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying/research/insider_buying_affected_quarter_isolation.py"
    sys.modules[helper.__name__] = helper
    exec(compile(helper_raw, helper.__file__, "exec", dont_inherit=True), helper.__dict__)
    sys.modules["research.insider_buying_affected_quarter_isolation"] = helper
    phase = "worker_bootstrap_source_decode"
    sources = helper._decode_sources(rows)
    need({p: helper._sha(data) for p,data in sources} == envelope["parent_context"]["identity"]["source_sha256"])
    finder = helper._SourceFinder(sources)
    sys.meta_path.insert(0, finder)
    phase = "worker_bootstrap_import"
    from research import insider_buying_sec_2006q1_original_admission_runner as consumer
    phase = "worker_execution"
    result = consumer._worker(envelope["audit_id"], expected_head=envelope["expected_head"],
        parent_context=envelope["parent_context"], executed_sources=lambda: [{"path":
        "research/insider_buying_affected_quarter_isolation.py", "sha256": selected[0]["sha256"]}, *finder.executed])
    print(consumer._raw(result).decode())
except Exception as exc:
    if consumer is not None:
        diagnostic = consumer._failure_diagnostic(exc, phase)
    else:
        category = next((name for kind,name in ((OSError,"OSError"),(ValueError,"ValueError"),
            (TypeError,"TypeError"),(KeyError,"KeyError")) if isinstance(exc,kind)), "other_refusal")
        number = exc.errno if isinstance(exc,OSError) else None
        if type(number) is not int or number not in errno.errorcode: number = None
        diagnostic = {"disposition":"offline_original_admission_refused_outputs_preserved",
            "failure_phase":phase,"failure_class":category,"os_errno":number}
    print(json.dumps(diagnostic,sort_keys=True,separators=(",",":"),allow_nan=False))
    raise SystemExit(2)
'''


class OriginalAdmissionRunnerError(ValueError):
    """Fixed classifications only, never source, path or exception contents."""


def _need(value, code):
    if not value:raise OriginalAdmissionRunnerError(code)


def _raw(value):return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
def _sha(value):return hashlib.sha256(value).hexdigest()
def _digest(value):return original._digest(value)


def _at(phase, function, *args, **kwargs):
    _need(phase in _PHASES, "failure_phase_refused")
    try:return function(*args, **kwargs)
    except Exception as exc:
        exc._original_admission_phase = phase
        raise


def _failure_diagnostic(exc, fallback="parent_preflight"):
    if type(exc) is ReportedWorkerError:return _strict_failure(exc.diagnostic)
    phase = getattr(exc, "_original_admission_phase", None)
    if phase not in _PHASES:phase = fallback if fallback in _PHASES else "parent_preflight"
    classes = ((OriginalAdmissionRunnerError, "OriginalAdmissionRunnerError"), (pure.OriginalAdmissionError, "OriginalAdmissionError"),
        (OSError, "OSError"), (ValueError, "ValueError"), (TypeError, "TypeError"), (KeyError, "KeyError"),
        (subprocess.SubprocessError, "SubprocessError"))
    number = exc.errno if isinstance(exc, OSError) else None
    if type(number) is not int or number not in errno.errorcode:number = None
    return {"disposition": "offline_original_admission_refused_outputs_preserved", "failure_phase": phase,
        "failure_class": next((label for cls,label in classes if isinstance(exc,cls)), "other_refusal"), "os_errno": number}


def _strict_failure(value):
    _need(type(value) is dict and set(value) == {"disposition", "failure_phase", "failure_class", "os_errno"}
        and value["disposition"] == "offline_original_admission_refused_outputs_preserved"
        and type(value["failure_phase"]) is str and value["failure_phase"] in _PHASES
        and type(value["failure_class"]) is str and value["failure_class"] in _CLASS_NAMES
        and (value["os_errno"] is None or type(value["os_errno"]) is int and value["os_errno"] in errno.errorcode),
        "worker_failure_schema_refused")
    return dict(value)


class ReportedWorkerError(OriginalAdmissionRunnerError):
    def __init__(self, diagnostic):
        self.diagnostic = _strict_failure(diagnostic)
        super().__init__("isolated_worker_refused_outputs_preserved")


def _close_all(helds):
    primary, first = sys.exc_info()[1], None
    for held in helds:
        if held is not None:
            try:held.close()
            except Exception as exc:
                if first is None:first = exc
    if primary is None and first is not None:raise first


def _version(info):
    # Newly created output leaves only: ctime is omitted because macOS tracking
    # may settle after publication. Every check rehashes the complete held body.
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_uid, info.st_size, info.st_mtime_ns)


class _Output:
    def __init__(self, path):
        self.tree = original.capture.custody._Directory(path)
        self.path, self.fd, self.holds = self.tree.path, self.tree.fd, {}

    def _open(self, name, digest, size, cap):
        self.check()
        _digest(digest)
        _need(name in FILES and name not in self.holds and type(size) is int and 0 < size <= cap,
            "output_leaf_contract_refused")
        named = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
        _need(stat.S_ISREG(named.st_mode) and named.st_nlink == 1 and named.st_uid == os.geteuid()
            and stat.S_IMODE(named.st_mode) == 0o600 and named.st_size == size, "private_output_leaf_required")
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        try:
            _need(_version(named) == _version(os.fstat(fd)), "output_leaf_substituted")
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            stream = os.fdopen(fd, "rb")
        except BaseException:os.close(fd);raise
        self.holds[name] = (stream, _version(named), digest, size)
        self.check()

    def check(self, *, final=False):
        self.tree.check()
        names = set(os.listdir(self.fd))
        _need(names <= FILES and (not final or names == FILES), "output_inventory_refused")
        for name,(stream, version, digest, size) in self.holds.items():
            _need(_version(os.fstat(stream.fileno())) == version and
                _version(os.stat(name, dir_fd=self.fd, follow_symlinks=False)) == version, "output_leaf_version_changed")
            stream.seek(0);hashed, count = hashlib.sha256(), 0
            while chunk := stream.read(1024 * 1024):
                count += len(chunk);_need(count <= size, "output_leaf_size_changed");hashed.update(chunk)
            _need(count == size and hashed.hexdigest() == digest, "output_leaf_content_changed")
            _need(_version(os.fstat(stream.fileno())) == version and
                _version(os.stat(name, dir_fd=self.fd, follow_symlinks=False)) == version, "output_leaf_changed_while_hashing")
            stream.seek(0)
        self.tree.check()

    def publish(self, name, raw, *, cap):
        self.check()
        digest = self.tree.publish(name, raw, cap=cap)
        self._open(name, digest, len(raw), cap)
        return digest

    def read_control(self, name, *, expected_sha256=None):
        _need(name in {"reservation.json", "complete.json"}, "parent_control_only_read_required")
        if name not in self.holds:
            # New OUTPUT custody intentionally does not call the historical
            # strict-ctime input reader. Both initial read and later holds use
            # the output-only settled version plus a complete content hash.
            self.check()
            named = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            _need(stat.S_ISREG(named.st_mode) and named.st_nlink == 1 and named.st_uid == os.geteuid()
                and stat.S_IMODE(named.st_mode) == 0o600 and 0 < named.st_size <= MAX_CONTROL_BYTES,
                "private_output_control_required")
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
            try:
                before = _version(os.fstat(fd))
                _need(before == _version(named), "output_control_substituted")
                fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
                pieces = bytearray()
                while chunk := os.read(fd, min(65536, MAX_CONTROL_BYTES + 1 - len(pieces))):
                    pieces.extend(chunk)
                    _need(len(pieces) <= MAX_CONTROL_BYTES, "output_control_bound_refused")
                _need(before == _version(os.fstat(fd)) == _version(os.stat(name,dir_fd=self.fd,follow_symlinks=False))
                    and len(pieces) == named.st_size, "output_control_changed_while_reading")
                raw = bytes(pieces)
            finally:os.close(fd)
            if expected_sha256 is not None:_need(_sha(raw) == expected_sha256, "control_anchor_differs")
            self._open(name, _sha(raw), len(raw), MAX_CONTROL_BYTES)
        self.check();stream = self.holds[name][0];stream.seek(0);raw = stream.read(MAX_CONTROL_BYTES + 1);stream.seek(0)
        _need(0 < len(raw) <= MAX_CONTROL_BYTES and (expected_sha256 is None or _sha(raw) == expected_sha256),
            "control_anchor_or_bound_refused")
        self.check();return raw

    def read_metadata(self, name):
        # Newly generated identity/structural METADATA only. The parent never
        # opens/reprojects an original XML/financial source body.
        _need(name in {"assessment.json", "parent-admission.json"} and name in self.holds,
            "held_metadata_output_required")
        self.check();stream, _, digest, size = self.holds[name];stream.seek(0)
        raw = stream.read(size + 1);stream.seek(0)
        _need(len(raw) == size and _sha(raw) == digest, "metadata_read_hash_differs")
        self.check();return original.capture._json(raw)

    def close(self):
        _close_all([*(hold[0] for hold in reversed(tuple(self.holds.values()))), self.tree])


def _fixed_source_identity(head):
    _need(Path(__file__).resolve() == original.capture.bootstrap.custody.LANE_ROOT / SELF_PATH
        and Path.cwd() == original.capture.bootstrap.custody.LANE_ROOT, "fixed_lane_runner_source_required")
    identity, frozen = original._fixed_source_identity(head)
    _need(SOURCE_SEEDS <= set(identity["source_sha256"]), "complete_original_source_closure_required")
    return identity, frozen


def _current_bytes(identity, frozen):
    _need(SOURCE_SEEDS <= set(identity["source_sha256"]), "complete_original_source_closure_required")
    original._current_bytes(identity, frozen)


class _PinnedEvidence:
    """Held old metadata roster + sealed capture controls, never original bodies."""
    def __init__(self):
        self.baseline = self.capture = None
        try:
            self.baseline = previous._PinnedBaseline(previous.BASELINE_COMPLETE)
            root = original.capture.bootstrap.custody.LANE_ROOT.joinpath(*original.capture.ARTIFACT_PARTS)
            self.capture = original.capture.bootstrap._Tree(original.capture.bootstrap.RootSpec(
                "original64-control-evidence", root, "control-only-capture"))
            lock = self.capture.open(())
            fd = os.open("capture.lock", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=lock.fd)
            try:fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BaseException:os.close(fd);raise
            self.capture.locks.append((lock, "capture.lock", fd, original.capture.bootstrap.custody._version(os.fstat(fd))))
            parts = ("runs", original.CAPTURE_ID)
            report = original.capture._json(self.capture.read(parts, "complete.json", cap=MAX_CONTROL_BYTES,
                expected=CAPTURE_REPORT_SHA256))
            reservation = original.capture._json(self.capture.read(parts, "reservation.json", cap=MAX_CONTROL_BYTES,
                expected=report["reservation_sha256"]))
            original.capture._verify_selection_payload(reservation["selection"], fixture_only=False)
            selection, anchors = reservation["selection"], []
            _need(len(selection["requests"]) == len(report["results"]) == 64, "fixed_original64_control_inventory_required")
            for ordinal,(selected, observed) in enumerate(zip(selection["requests"], report["results"], strict=True)):
                request = original.capture._request(selected["request"])
                result = original.capture._json(self.capture.read(parts, observed["result_name"], cap=MAX_CONTROL_BYTES,
                    expected=observed["result_sha256"]))
                _need(selected["prefix_ordinal"] == ordinal and selected["request_sha256"] == _sha(_raw(request))
                    and result["disposition"] == "complete_raw_response_retained_header_quarantined"
                    and result["header_identity_bound"] is False and result["body_retained"] is True,
                    "unchanged_original64_header_quarantine_required")
                _digest(result["body_sha256"]);_digest(observed["result_sha256"])
                _need(type(result["body_size_bytes"]) is int and 0 < result["body_size_bytes"] <= original.capture.MAX_PARENT_BYTES,
                    "original_capture_control_body_size_refused")
                anchors.append({"prefix_ordinal": ordinal, "source_record_ordinal": request["source_record_ordinal"],
                    "accession_number": request["accession_number"], "request_sha256": selected["request_sha256"],
                    "result_sha256": observed["result_sha256"], "terminal_disposition": result["disposition"],
                    "body_sha256": result["body_sha256"], "body_size_bytes": result["body_size_bytes"], "header_identity_bound": False})
            context = previous._loaded_capture_context(reservation, report)
            _need(context == self.baseline.metadata["capture_execution_context"], "original_capture_baseline_lineage_differs")
            old_assessment = original.capture._json(self.baseline.tree.read((), "assessment.json",
                cap=previous.BASELINE_LEAVES["assessment.json"][1],expected=previous.BASELINE_LEAVES["assessment.json"][0]))
            _digest(old_assessment["accounting_sha256"])
            self.metadata = {"frozen_original_baseline": self.baseline.metadata,
                "capture_execution_context": context, "selected_parent_anchors": anchors,
                "selected_parent_anchors_sha256": _sha(_raw(anchors)),
                "frozen_baseline_accounting_sha256":old_assessment["accounting_sha256"]}
            self.recheck()
        except BaseException:_close_all((self.capture,self.baseline));raise

    def recheck(self):
        self.baseline.recheck();self.capture.recheck()

    def close(self):_close_all((self.capture,self.baseline))


def _output_directory(audit_id, *, create):
    _need(audit_id == AUDIT_ID and type(audit_id) is str and type(create) is bool, "fixed_fresh_original_scope_required")
    base = original.capture.bootstrap.custody.LANE_ROOT.joinpath(*OUTPUT_PARTS)
    if create:
        parent = original.capture.custody._Directory(base, create=True)
        try:
            _need(not parent.exists(audit_id), "fresh_original_namespace_required")
            space = os.fstatvfs(parent.fd)
            _need(space.f_bavail * space.f_frsize >= original.MIN_FREE_BYTES + MAX_ASSESSMENT_BYTES + MAX_LEDGER_BYTES
                + 2 * MAX_CONTROL_BYTES, "offline_original_disk_reserve_refused")
            os.mkdir(audit_id, 0o700, dir_fd=parent.fd);os.fsync(parent.fd)
        finally:parent.close()
    return _Output(base / audit_id)


def _reservation(identity, frozen, evidence):
    return {"schema": SCHEMA + "/reservation", "audit_id": AUDIT_ID, "capture_id": original.CAPTURE_ID,
        "capture_report_sha256": CAPTURE_REPORT_SHA256, "current_execution_identity": identity, "frozen_sources": frozen,
        "original_preparation_completion_sha256": original.downstream.EXPECTED_COMPLETION_SHA256,
        "original_preparation_assessment_sha256": original.downstream.EXPECTED_ASSESSMENT_SHA256,
        "source_only_bootstrap_sha256": _sha(SOURCE_ONLY_BOOTSTRAP.encode()), "pinned_metadata_evidence": evidence,
        "authority": pure.authority()}


def _prove_worker_isolation(path):
    # These are actual OS probes BEFORE installing the secondary Python hook or
    # opening any retained quarter/source/complete-original input.
    original._prove_worker_isolation(path)
    # Exec directly, not posix_spawn: a fork-denied spawn does not separately
    # prove process-exec denial. The harmless help operation reads no item.
    # Unexpected success replaces this worker, preventing a success receipt.
    try:os.execve("/usr/bin/security", ["/usr/bin/security", "help"], {"PATH": "/usr/bin:/bin"})
    except OSError as exc:_need(exc.errno in {errno.EPERM, errno.EACCES}, "native_keychain_exec_denial_not_observed")
    else:
        raise OriginalAdmissionRunnerError("native_keychain_exec_denial_not_observed")


def _executed_sources(rows, identity):
    _need(type(rows) is list and 1 <= len(rows) <= 512, "executed_source_inventory_refused")
    seen = set()
    for row in rows:
        _need(type(row) is dict and set(row) == {"path", "sha256"} and type(row["path"]) is str
            and row["path"] not in seen and row["sha256"] == identity["source_sha256"].get(row["path"]),
            "executed_source_inventory_refused")
        _digest(row["sha256"]);seen.add(row["path"])
    _need(SOURCE_SEEDS <= seen and "research/insider_buying/sec_ib1c_identity_v2.py" in seen,
        "executed_original_parser_consumer_required")
    return {"source_only_lane_imports": True, "executed_sources": rows, "executed_source_count": len(rows),
        "executed_source_inventory_sha256": _sha(_raw(rows)), "full_historical_environment_reconstructed": False}


def _strict_counts(counts, *, actual=True):
    _need(type(actual) is bool, "count_validation_mode_refused")
    _need(type(counts) is dict and set(counts) == COUNT_KEYS
        and all(type(value) is int and value >= 0 for value in counts.values()), "whole_quarter_count_types_refused")
    c = counts
    _need(c["source_filings"] == c["target_filings"] + c["context_filings"]
        and c["selected_parents"] <= 64 and c["retained_parent_bodies"] <= 64
        and c["structurally_bound_original_parents"] + c["parser_quarantined_parents"] == c["retained_parent_bodies"]
        and c["retained_parent_bodies"] + c["unavailable_selected_parents"] == c["selected_parents"]
        and c["structurally_bound_original_parents"] == c["structurally_bound_noncanonical_filings"]
        and c["structurally_bound_noncanonical_filings"] + c["quarantined_filings"] == c["source_filings"]
        and c["target_original_binding_missing"] + c["structurally_bound_noncanonical_filings"] == c["target_filings"]
        and c["preserved_capture_header_quarantines"] <= c["retained_parent_bodies"]
        and c["retained_parent_bytes"] <= original.identity_v2.MAX_CORROBORATING_BYTES
        and (c["retained_parent_bytes"] > 0) is (c["retained_parent_bodies"] > 0), "whole_quarter_count_partition_refused")
    if actual:
        _need(c["source_filings"] == 83_657 and c["target_filings"] == 71_679 and c["context_filings"] == 11_978
            and c["selected_parents"] == c["retained_parent_bodies"] == c["preserved_capture_header_quarantines"] == 64,
            "actual_full_quarter_original64_profile_refused")
    return counts


def _validate_metadata(body, evidence, *, fixture_only=False):
    """Independently recount published METADATA against the held original roster.

    No original raw body, parser, financial table or provider is read here. This
    is equally used inside the denied worker and by parent final readback.
    """
    keys = {"schema", "fixture_only", "period", "capture_report_sha256", "form_counts", "parsed_snapshot_id",
        "parsed_lineage_hash", "census_quarter_sha256", "frozen_baseline_assessment_sha256", "frozen_baseline_accounting_sha256",
        "parser_profile", "parent_ledger", "parent_ledger_sha256", "rows", "accounting_sha256", "counts",
        "whole_quarter_identity_sha256", "authority"}
    _need(type(fixture_only) is bool and type(body) is dict and set(body) == keys and body["schema"] == pure.SCHEMA
        and body["fixture_only"] is fixture_only and body["period"] == "2006Q1"
        and body["capture_report_sha256"] == CAPTURE_REPORT_SHA256 and body["parser_profile"] == pure.parser.PROFILE
        and body["whole_quarter_identity_sha256"] is None and _raw(body["authority"]) == _raw(pure.authority()),
        "structural_metadata_schema_or_authority_refused")
    _strict_counts(body["counts"], actual=not fixture_only)
    baseline = evidence["frozen_original_baseline"]
    context = baseline["preparation_context"]
    _need(body["parsed_snapshot_id"] == context["parsed_snapshot_id"]
        and body["parsed_lineage_hash"] == context["parsed_lineage_sha256"]
        and body["census_quarter_sha256"] == context["census_quarter_sha256"], "metadata_preparation_context_differs")
    for key in ("accounting_sha256", "frozen_baseline_accounting_sha256", "frozen_baseline_assessment_sha256"):_digest(body[key])
    _need(body["frozen_baseline_assessment_sha256"] == baseline["publication_pins"]["assessment.json"]["sha256"]
        and body["frozen_baseline_accounting_sha256"] == evidence["frozen_baseline_accounting_sha256"],
        "metadata_frozen_baseline_digest_differs")
    rows, ledger = body["rows"], body["parent_ledger"]
    _need(type(rows) is list and type(ledger) is list and body["accounting_sha256"] == pure.hash_payload(rows)
        and body["parent_ledger_sha256"] == _sha(_raw(ledger)), "metadata_content_hashes_refused")
    _need(previous._source_identity_inventory(rows) == {key:context[key] for key in
        ("source_row_count", "ordered_source_row_identity_sha256")}, "metadata_full_original_source_roster_differs")
    forms = {form:sum(row["form_type"] == form for row in rows) for form in pure.FORM_COUNTS}
    _need(type(body["form_counts"]) is dict and set(body["form_counts"]) == set(forms)
        and all(type(value) is int for value in body["form_counts"].values()) and body["form_counts"] == forms
        and (fixture_only or forms == pure.FORM_COUNTS), "metadata_measured_six_form_census_differs")
    anchor_keys = {"prefix_ordinal", "source_record_ordinal", "accession_number", "request_sha256", "result_sha256",
        "terminal_disposition", "body_sha256", "body_size_bytes", "header_identity_bound"}
    ledger_keys = anchor_keys | {"original_projection", "original_projection_refusal", "disposition"}
    anchors = evidence["selected_parent_anchors"]
    _need(type(anchors) is list and evidence["selected_parent_anchors_sha256"] == _sha(_raw(anchors))
        and len(ledger) == len(anchors), "original_parent_anchor_inventory_refused")
    parents = {}
    for ordinal,(row,anchor) in enumerate(zip(ledger,anchors,strict=True)):
        _need(type(row) is dict and set(row) == ledger_keys and type(row["prefix_ordinal"]) is int
            and row["prefix_ordinal"] == ordinal and type(row["source_record_ordinal"]) is int
            and type(row["header_identity_bound"]) is bool
            and (row["body_size_bytes"] is None or type(row["body_size_bytes"]) is int)
            and {key:row[key] for key in anchor_keys} == anchor
            and row["accession_number"] not in parents, "metadata_parent_anchor_or_prefix_differs")
        parents[row["accession_number"]] = row
        projection = row["original_projection"]
        if projection is not None:
            _need(type(projection) is dict and set(projection) == {"projection_sha256", "original_parent_sha256", "capture_result_sha256",
                "header_sha256", "xml_sha256", "header_topology", "accepted_clock_verified", "capture_header_identity_bound"}
                and projection["original_parent_sha256"] == row["body_sha256"]
                and projection["capture_result_sha256"] == row["result_sha256"]
                and projection["accepted_clock_verified"] is False
                and projection["capture_header_identity_bound"] is row["header_identity_bound"]
                and projection["header_topology"] in {"owner-first", "issuer-first"}
                and row["disposition"] == "original_structurally_bound_noncanonical"
                and row["original_projection_refusal"] is None, "metadata_original_projection_lineage_refused")
            for key in ("projection_sha256", "original_parent_sha256", "capture_result_sha256", "header_sha256", "xml_sha256"):
                _digest(projection[key])
        elif row["body_sha256"] is not None:
            _need(row["disposition"] == "original_parent_structure_quarantined"
                and row["original_projection_refusal"] == "early_original_parser_refused", "metadata_parser_quarantine_refused")
        else:
            _need(row["disposition"] == "original_complete_parent_unavailable" and row["original_projection_refusal"] is None,
                "metadata_unavailable_disposition_refused")
    source_keys = set(previous._SOURCE_ROW_KEYS)
    row_keys = source_keys | {"corroboration", "disposition", "quarantine_reasons", "frozen_baseline_disposition",
        "frozen_baseline_quarantine_reasons", "original_parent_evidence"}
    for row in rows:
        _need(type(row) is dict and set(row) == row_keys and row["corroboration"] is None
            and row["frozen_baseline_disposition"] == "quarantined", "metadata_exact_new_row_contract_required")
        parent = parents.get(row["accession_number"])
        projection = None if parent is None else parent["original_projection"]
        _need((parent is None or row["source_record_ordinal"] == parent["source_record_ordinal"])
            and row["original_parent_evidence"] == projection, "metadata_parent_row_copy_or_ordinal_differs")
        target = row["form_type"] in {"4", "4/A"}
        expected_old = ["complete_parent_corroboration_missing" if target else "unsupported_parent_corroboration_form"]
        _need(row["frozen_baseline_quarantine_reasons"] == expected_old
            and row["disposition"] == ("original_structurally_bound_noncanonical" if projection is not None else "quarantined")
            and row["quarantine_reasons"] == ([] if projection is not None else expected_old)
            and (projection is None or target), "metadata_quarantine_or_structural_disposition_refused")
    _need(set(parents) <= {row["accession_number"] for row in rows}, "metadata_parent_not_in_original_source_roster")
    bound = sum(row["original_projection"] is not None for row in ledger)
    measured = {"source_filings":len(rows), "target_filings":forms["4"]+forms["4/A"],
        "context_filings":sum(forms[form] for form in ("3","3/A","5","5/A")), "selected_parents":len(ledger),
        "retained_parent_bodies":sum(row["body_sha256"] is not None for row in ledger),
        "structurally_bound_original_parents":bound,
        "parser_quarantined_parents":sum(row["disposition"] == "original_parent_structure_quarantined" for row in ledger),
        "unavailable_selected_parents":sum(row["disposition"] == "original_complete_parent_unavailable" for row in ledger),
        "structurally_bound_noncanonical_filings":sum(row["disposition"] == "original_structurally_bound_noncanonical" for row in rows),
        "quarantined_filings":sum(row["disposition"] == "quarantined" for row in rows),
        "target_original_binding_missing":sum(row["form_type"] in {"4","4/A"} and row["original_parent_evidence"] is None for row in rows),
        "retained_parent_bytes":sum(row["body_size_bytes"] or 0 for row in ledger),
        "preserved_capture_header_quarantines":sum(row["terminal_disposition"] ==
            "complete_raw_response_retained_header_quarantined" for row in ledger)}
    _need(body["counts"] == measured, "metadata_independent_row_or_parent_counts_differ")
    return body


def _strict_summary(result):
    keys = {"audit_id", "fixture_only", "complete_sha256", "assessment_sha256", "parent_ledger_sha256",
        "capture_report_sha256", "counts", "authority"}
    _need(type(result) is dict and set(result) == keys and result["audit_id"] == AUDIT_ID
        and result["fixture_only"] is False and result["capture_report_sha256"] == CAPTURE_REPORT_SHA256
        and _raw(result["authority"]) == _raw(pure.authority()), "worker_summary_refused")
    for key in ("complete_sha256", "assessment_sha256", "parent_ledger_sha256", "capture_report_sha256"):_digest(result[key])
    _strict_counts(result["counts"])
    return result


def _worker(audit_id, *, expected_head, parent_context, executed_sources=None):
    _need(Path(__file__).resolve() == original.capture.bootstrap.custody.LANE_ROOT / SELF_PATH
        and Path.cwd() == original.capture.bootstrap.custody.LANE_ROOT and audit_id == AUDIT_ID,
        "fixed_original_worker_source_and_scope_required")
    _need(type(parent_context) is dict and set(parent_context) == {"identity", "frozen_sources", "pinned_metadata_evidence"}
        and callable(executed_sources), "captured_source_worker_context_required")
    identity, frozen = parent_context["identity"], parent_context["frozen_sources"]
    _at("worker_preflight", original.capture.bootstrap._required_identity, identity, expected_head)
    _at("worker_preflight", _current_bytes, identity, frozen)
    output = _at("worker_output_reservation", _output_directory, audit_id, create=False)
    preparation = public = parents = evidence = None
    phase = "worker_output_reservation"
    try:
        _need(set(os.listdir(output.fd)) == {"reservation.json"}, "fresh_reserved_original_output_required")
        reservation_raw = output.read_control("reservation.json")
        _need(original.capture._json(reservation_raw) == _reservation(identity, frozen, parent_context["pinned_metadata_evidence"]),
            "worker_reservation_context_differs")
        _at("worker_isolation", _prove_worker_isolation, output.path)
        sys.addaudithook(original.isolation._audit_event)
        evidence = _at("worker_preparation", _PinnedEvidence)
        _need(evidence.metadata == parent_context["pinned_metadata_evidence"], "worker_observed_evidence_differs_from_parent")
        preparation, public, snapshot, census = _at("worker_preparation", original._load_original_preparation)
        parents, descriptors, capture_reservation, capture_report = _at("worker_capture", original._load_sealed_capture, CAPTURE_REPORT_SHA256)
        phase = "worker_composition"
        _current_bytes(identity, frozen)
        result = _at("worker_composition", pure.assess_original_admission, snapshot, census, descriptors,
            expected_capture_report_sha256=CAPTURE_REPORT_SHA256, fixture_only=False)
        body = result.to_payload()
        _validate_metadata(body, evidence.metadata)
        phase = "worker_replay"
        repeated = _at("worker_replay", pure.assess_original_admission, snapshot, census, descriptors,
            expected_capture_report_sha256=CAPTURE_REPORT_SHA256, fixture_only=False)
        _need(result.canonical_bytes() == repeated.canonical_bytes(), "original_structural_replay_differs")
        _strict_counts(body["counts"])
        for held in (preparation, public, parents, evidence):held.recheck()
        _current_bytes(identity, frozen)
        ledger_raw = _raw({key:value for key,value in body.items() if key != "rows"})
        phase = "worker_publication"
        assessment_raw = result.canonical_bytes()
        assessment_sha = output.publish("assessment.json", assessment_raw, cap=MAX_ASSESSMENT_BYTES)
        ledger_sha = output.publish("parent-admission.json", ledger_raw, cap=MAX_LEDGER_BYTES)
        complete = {"schema": SCHEMA + "/complete", "audit_id": AUDIT_ID, "fixture_only": False,
            "current_execution_identity": identity, "frozen_sources": frozen, "reservation_sha256": _sha(reservation_raw),
            "pinned_metadata_evidence": evidence.metadata,
            "capture_id": original.CAPTURE_ID, "capture_report_sha256": CAPTURE_REPORT_SHA256,
            "capture_execution_head": capture_report["capture_execution_head"],
            "capture_execution_source_inventory_sha256": capture_reservation["execution_identity"]["source_inventory_sha256"],
            "bootstrap_execution_head": capture_report["bootstrap_execution_head"],
            "original_preparation_producer_commit": original.downstream.PRODUCER_COMMIT,
            "original_preparation_completion_sha256": original.downstream.EXPECTED_COMPLETION_SHA256,
            "original_preparation_assessment_sha256": original.downstream.EXPECTED_ASSESSMENT_SHA256,
            "assessment_sha256": assessment_sha, "assessment_bytes": len(assessment_raw),
            "parent_ledger_sha256": ledger_sha, "parent_ledger_bytes": len(ledger_raw), "counts": body["counts"],
            "form_counts": body["form_counts"], "accounting_sha256": body["accounting_sha256"],
            "parsed_snapshot_id": body["parsed_snapshot_id"], "parsed_lineage_hash": body["parsed_lineage_hash"],
            "census_quarter_sha256": body["census_quarter_sha256"], "whole_quarter_identity_sha256": None,
            "frozen_baseline_assessment_sha256": body["frozen_baseline_assessment_sha256"],
            "frozen_baseline_accounting_sha256": body["frozen_baseline_accounting_sha256"],
            "source_execution": _executed_sources(executed_sources(), identity),
            "source_only_bootstrap_sha256": _sha(SOURCE_ONLY_BOOTSTRAP.encode()),
            "effective_process_tree_network_denial": True, "effective_process_fork_denial": True,
            "effective_keychain_exec_denial": True, "writes_confined_to_fresh_output_by_launcher": True,
            "authority": pure.authority()}
        for held in (preparation, public, parents, evidence):held.recheck()
        _current_bytes(identity, frozen)
        complete_sha = output.publish("complete.json", _raw(complete), cap=MAX_CONTROL_BYTES)
        phase = "worker_readback"
        output.check(final=True)
        _validate_metadata(output.read_metadata("assessment.json"), evidence.metadata)
        for held in (preparation, public, parents, evidence):held.recheck()
        _current_bytes(identity, frozen)
        return _strict_summary({"audit_id": AUDIT_ID, "fixture_only": False, "complete_sha256": complete_sha,
            "assessment_sha256": assessment_sha, "parent_ledger_sha256": ledger_sha,
            "capture_report_sha256": CAPTURE_REPORT_SHA256, "counts": body["counts"], "authority": pure.authority()})
    except Exception as exc:
        if getattr(exc, "_original_admission_phase", None) not in _PHASES:exc._original_admission_phase = phase
        raise
    finally:_close_all((parents, public, preparation, evidence, output))


def _verify_outputs(output, result, identity, frozen, evidence, *, fixture_only=False):
    _need(type(fixture_only) is bool, "readback_validation_mode_refused")
    complete_raw = output.read_control("complete.json", expected_sha256=result["complete_sha256"])
    complete = original.capture._json(complete_raw)
    reservation_raw = output.read_control("reservation.json")
    _need(type(complete) is dict and set(complete) == COMPLETE_KEYS
        and original.capture._json(reservation_raw) == _reservation(identity, frozen, evidence)
        and complete.get("schema") == SCHEMA + "/complete" and complete.get("audit_id") == AUDIT_ID
        and complete.get("fixture_only") is fixture_only and complete.get("current_execution_identity") == identity
        and complete.get("frozen_sources") == frozen and complete.get("reservation_sha256") == _sha(reservation_raw)
        and complete.get("pinned_metadata_evidence") == evidence
        and complete.get("capture_id") == original.CAPTURE_ID and complete.get("capture_report_sha256") == CAPTURE_REPORT_SHA256
        and complete.get("original_preparation_producer_commit") == original.downstream.PRODUCER_COMMIT
        and complete.get("original_preparation_completion_sha256") == original.downstream.EXPECTED_COMPLETION_SHA256
        and complete.get("original_preparation_assessment_sha256") == original.downstream.EXPECTED_ASSESSMENT_SHA256
        and complete.get("source_only_bootstrap_sha256") == _sha(SOURCE_ONLY_BOOTSTRAP.encode())
        and complete.get("assessment_sha256") == result["assessment_sha256"]
        and complete.get("parent_ledger_sha256") == result["parent_ledger_sha256"]
        and _raw(complete.get("counts")) == _raw(result["counts"])
        and _raw(complete.get("authority")) == _raw(pure.authority()) and complete.get("whole_quarter_identity_sha256") is None
        and (fixture_only or complete.get("form_counts") == pure.FORM_COUNTS)
        and all(complete.get(key) is True for key in ("effective_process_tree_network_denial", "effective_process_fork_denial",
            "effective_keychain_exec_denial", "writes_confined_to_fresh_output_by_launcher")), "worker_publication_context_refused")
    _need(complete.get("source_execution") == _executed_sources(complete.get("source_execution", {}).get("executed_sources"), identity),
        "published_full_source_execution_context_differs")
    _need({key:complete.get(key) for key in previous._CAPTURE_CONTEXT_KEYS} == evidence["capture_execution_context"],
        "published_capture_execution_lineage_differs")
    for name,key,cap in (("assessment.json","assessment",MAX_ASSESSMENT_BYTES),
                         ("parent-admission.json","parent_ledger",MAX_LEDGER_BYTES)):
        output._open(name, result[key + "_sha256"], complete[key + "_bytes"], cap)
    output.check(final=True)
    body = _validate_metadata(output.read_metadata("assessment.json"), evidence, fixture_only=fixture_only)
    _need(output.read_metadata("parent-admission.json") == {key:value for key,value in body.items() if key != "rows"},
        "metadata_parent_ledger_publication_differs")
    _need(all(complete.get(key) == body[key] for key in ("counts", "form_counts", "accounting_sha256", "parsed_snapshot_id",
        "parsed_lineage_hash", "census_quarter_sha256", "frozen_baseline_assessment_sha256", "frozen_baseline_accounting_sha256")),
        "complete_copied_assessment_metadata_differs")
    return complete


def run_observed_admission(*, expected_head):
    identity, frozen = _at("parent_preflight", _fixed_source_identity, expected_head)
    _at("parent_original_sources", original.capture._verify_original_committed_sources, original.CAPTURE_ID, CAPTURE_REPORT_SHA256)
    evidence = _at("parent_original_sources", _PinnedEvidence)
    output = None
    phase = "parent_output_reservation"
    try:
        _need(_fixed_source_identity(expected_head) == (identity, frozen), "source_changed_before_scope_claim")
        evidence.recheck()
        output = _at("parent_output_reservation", _output_directory, AUDIT_ID, create=True)
        output.publish("reservation.json", _raw(_reservation(identity, frozen, evidence.metadata)), cap=MAX_CONTROL_BYTES)
        phase = "parent_captured_sources"
        sources = []
        for name,digest in sorted(identity["source_sha256"].items()):
            raw = original.isolation._read_source(name)
            _need(_sha(raw) == digest, "captured_source_bytes_changed")
            sources.append({"path": name, "sha256": digest, "source_b64": base64.b64encode(raw).decode("ascii")})
        envelope = _raw({"sources": sources, "parent_context": {"identity": identity, "frozen_sources": frozen,
            "pinned_metadata_evidence": evidence.metadata},
            "audit_id": AUDIT_ID, "expected_head": expected_head})
        _need(len(envelope) <= MAX_CONTEXT_BYTES, "captured_source_context_bound_refused")
        _need(_fixed_source_identity(expected_head) == (identity, frozen), "source_or_head_changed_before_worker")
        evidence.recheck()
        policy = original.isolation._worker_policy(output.path)
        command = ["/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "/usr/bin/sandbox-exec", "-p", policy,
            sys.executable, "-I", "-S", "-B", "-X", "pycache_prefix=/var/empty/insider-buying-no-bytecode", "-c", SOURCE_ONLY_BOOTSTRAP]
        phase = "parent_worker_launch"
        child = subprocess.run(command, cwd=original.capture.bootstrap.custody.LANE_ROOT, input=envelope,
            capture_output=True, check=False, timeout=1800)
        phase = "parent_worker_result"
        _need(_fixed_source_identity(expected_head) == (identity, frozen), "source_or_head_changed_after_worker")
        evidence.recheck()
        _need(type(child.stdout) is bytes and 0 < len(child.stdout) <= MAX_CONTROL_BYTES and child.stderr == b""
            and child.stdout.endswith(b"\n") and not child.stdout.endswith(b"\n\n"), "worker_stdout_framing_refused")
        value = original.capture._json(child.stdout.removesuffix(b"\n"))
        if child.returncode != 0:
            diagnostic = _strict_failure(value)
            _need(diagnostic["failure_phase"].startswith("worker_"), "worker_failure_phase_refused")
            raise ReportedWorkerError(diagnostic)
        _need(type(child.returncode) is int and child.returncode == 0, "worker_exit_status_refused")
        result = _strict_summary(value)
        phase = "parent_final_output_check"
        _verify_outputs(output, result, identity, frozen, evidence.metadata)
        _need(_fixed_source_identity(expected_head) == (identity, frozen), "source_or_head_changed_at_final_check")
        output.check(final=True)
        evidence.recheck()
        return result
    except Exception as exc:
        if getattr(exc, "_original_admission_phase", None) not in _PHASES:exc._original_admission_phase = phase
        raise
    finally:_close_all((output,evidence))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    args = parser.parse_args(argv)
    try:
        result = run_observed_admission(expected_head=args.expected_head)
        print(_raw(result).decode());return 0
    except Exception as exc:
        print(_raw(_failure_diagnostic(exc)).decode());return 2


if __name__ == "__main__":raise SystemExit(main())
