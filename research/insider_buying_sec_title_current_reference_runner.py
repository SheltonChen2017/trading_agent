"""Isolated SEC title/current Sharadar candidate-reference front.

Only its fixed clean committed lane image may operate. Every supplied input
is independently pinned before a fresh reservation. No acquisition, Actions
interpretation, financial getter, historical/PIT mapping, signal, QC or outcome
operation is performed. Current reference candidates are not historical IDs.
"""
from __future__ import annotations

import argparse
import base64
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from research import insider_buying_sec_2006q1_pem_reassessment_runner as view_front
from research import insider_buying_sec_2006q1_pem_reassessment_v1 as pem
from research import insider_buying_sec_2006q1_parent_projection_v1 as original
from research import insider_buying_sharadar_reference_cohort_runner as sharadar
from research import insider_buying_sec_title_current_reference_v1 as pure

SCHEMA = "insider-sec-title-current-reference-isolated-runner-v1"
SELF_PATH = "research/insider_buying_sec_title_current_reference_runner.py"
PURE_PATH = "research/insider_buying_sec_title_current_reference_v1.py"
OUTPUT_PARTS = ("artifacts", "insider_buying", "sec_title_current_reference_v1")
VIEW_ID = "ib-2006q1-pem-view-source-profile-v1-20261014-once"
VIEW_HEAD = "0b55707f6fcf95d1ed25a224b2513d92ac22d5bd"
VIEW_SOURCE_INVENTORY = "87b9999f4f4fda20d78e5abb977ec640288a3f294d25b02fe76723e42ce663db"
VIEW_LEAVES = {
    "reservation.json": ("718f4557bbf573132b6a84533a94fec6ab882c4886a608bc59871808dd943c63", 13975),
    "assessment.json": ("4665fb197a8ccaa495563f46608ae9a50cef012003261ecc11fe7ce1f51045da", 79842144),
    "parent-ledger.json": ("20202435af577eb523081ec0ddb54cdd136d0b8a457f031f53c45b3668cdda77", 338081),
    "source-view-inventory.json": ("87919b50b8eb60ac961b743c5e95d50c356e70cbf263267ca2deae962b4cb49b", 193274),
    "complete.json": ("c3a60ed272603a2ca3a337c8d9d5b475c1b50ea063ccec9a44874a6e11ba0641", 26049),
}
ORDERED_SOURCE_ROSTER = "d081c092c5abe29f3be51e3baa413b2ed38cd7d8709d5dd1e52c869cfeac8a99"
SHARADAR_ID = "ib-sharadar-cohort-2006q1-compact-v2-20261014-once"
SHARADAR_HEAD = "de9f54f76c58935fc01c97267397fb613dca2592"
SHARADAR_SOURCE_INVENTORY = "a3413c33147cefac8cea61140312cfc93185452eb828cd70c4845a97aab2c097"
SHARADAR_LEAVES = {
    "tickers_projection.json": ("da2bf31da6436127dd405154b339d1a31ad6c14a788d0017ce620ad5217aea60", 29841795),
    "actions_projection.json": ("27387a32fffe710e7733b8f8b225250fc92ad3d829d720efc77df77a015c5246", 116139300),
    "assessment.json": ("dca7b071e174bd898119ef86cd7ea1892856c38c92f061a2cf9fe668ecd35fa8", 178072103),
    "complete.json": ("07dd203d82c3d90f90e1af239b8ef2255ecba47400595d6f415a65989ee29f97", 7985),
}
MANIFEST_BYTES = 5998
MAX_OUTPUT_BYTES = 64 * 1024 * 1024
MAX_CONTROL_BYTES = 1024 * 1024
MAX_INPUT_BYTES = 256 * 1024 * 1024
MAX_CONTEXT_BYTES = original.MAX_WORKER_CONTEXT_BYTES
MIN_FREE_BYTES = 4 * 1024**3
_ID = re.compile(r"ib-sec-title-current-reference-[a-z0-9-]{1,70}\Z")
_FILES = frozenset({"reservation.json", "assessment.json", "complete.json"})
_FINAL_FILES = _FILES | {"readonly-verification.json"}
_PHASES = original._FAILURE_PHASES | {"parent_inputs", "worker_inputs", "parent_producer_sources",
    "parent_final_output_hold", "parent_final_source_view", "parent_final_reference",
    "parent_final_source_identity", "parent_final_output_recheck", "parent_cleanup"}
# Section 194 (Claude review): lane refusal classes are named, not collapsed to ValueError.
_LANE_CLASS_NAMES = ("SharadarCohortRunnerError", "ArchiveAssessmentRunnerError", "PemReassessmentRunnerError",
    "EarlyParentProjectionError", "OriginalPreparationCustodyError", "SecTitleCurrentReferenceError")
_FAILURE_CLASSES = frozenset({"SecTitleCurrentReferenceRunnerError", "OSError", "ValueError", "TypeError", "KeyError",
    "SubprocessError", "other_refusal", *_LANE_CLASS_NAMES})
_FAILURE_DISPOSITION = "offline_sec_title_current_reference_refused_outputs_preserved"

SOURCE_ONLY_BOOTSTRAP = r'''
import base64, errno, hashlib, json, sys, types
consumer = None
phase = "worker_bootstrap_context"
try:
    def need(condition):
        if not condition: raise ValueError("source-only current-reference context refused")
    raw = sys.stdin.buffer.read(33554433)
    need(0 < len(raw) <= 33554432)
    envelope = json.loads(raw)
    need(type(envelope) is dict and set(envelope) == {"sources", "context", "audit_id", "expected_head", "verify_only"})
    need(type(envelope["verify_only"]) is bool)
    rows = envelope["sources"]
    need(type(rows) is list)
    selected = [row for row in rows if row.get("path") == "research/insider_buying_affected_quarter_isolation.py"]
    need(len(selected) == 1)
    helper_raw = base64.b64decode(selected[0]["source_b64"], validate=True)
    need(hashlib.sha256(helper_raw).hexdigest() == selected[0]["sha256"])
    helper = types.ModuleType("_current_reference_captured_imports")
    helper.__file__ = "/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying/research/insider_buying_affected_quarter_isolation.py"
    sys.modules[helper.__name__] = helper
    exec(compile(helper_raw, helper.__file__, "exec", dont_inherit=True), helper.__dict__)
    sys.modules["research.insider_buying_affected_quarter_isolation"] = helper
    phase = "worker_bootstrap_source_decode"
    sources = helper._decode_sources(rows)
    need({path: helper._sha(source) for path, source in sources} == envelope["context"]["identity"]["source_sha256"])
    finder = helper._SourceFinder(sources)
    sys.meta_path.insert(0, finder)
    # No Python hook before the consumer proves native OS network/fork/write denial.
    phase = "worker_bootstrap_import"
    from research import insider_buying_sec_title_current_reference_runner as consumer
    phase = "worker_execution"
    result = consumer._worker(envelope["audit_id"], expected_head=envelope["expected_head"],
        context=envelope["context"], executed_sources=finder.executed,
        bootstrap_source={"path": "research/insider_buying_affected_quarter_isolation.py", "sha256": selected[0]["sha256"]},
        verify_only=envelope["verify_only"])
    print(consumer._raw(result).decode())
except Exception as exc:
    if consumer is not None and callable(getattr(consumer, "_failure_diagnostic", None)):
        body = consumer._failure_diagnostic(exc, phase)
    else:
        labels = ((OSError, "OSError"), (ValueError, "ValueError"), (TypeError, "TypeError"), (KeyError, "KeyError"))
        category = next((label for kind,label in labels if isinstance(exc, kind)), "other_refusal")
        number = exc.errno if isinstance(exc, OSError) else None
        if type(number) is not int or number not in errno.errorcode: number = None
        body = {"disposition": "offline_sec_title_current_reference_refused_outputs_preserved",
            "failure_phase": phase, "failure_class": category, "os_errno": number}
    print(json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False))
    raise SystemExit(2)
'''


class SecTitleCurrentReferenceRunnerError(ValueError): pass


class ReportedCurrentReferenceWorkerError(SecTitleCurrentReferenceRunnerError):
    def __init__(self, diagnostic):
        self.diagnostic = _strict_failure(diagnostic)
        super().__init__("isolated_current_reference_worker_failed_outputs_preserved")


def _need(value, code):
    if not value: raise SecTitleCurrentReferenceRunnerError(code)


def _raw(value): return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
def _sha(raw): return hashlib.sha256(raw).hexdigest()
def _digest(value): return original._digest(value)
def _authority(): return pure._authority()


def _at_phase(phase, function, *args, **kwargs):
    _need(type(phase) is str and phase in _PHASES, "internal_failure_phase_refused")
    try: return function(*args, **kwargs)
    except Exception as exc:
        exc._current_reference_failure_phase = phase
        raise


def _close_all(phase, *objects):
    """Close every hold; never mask a primary refusal with a cleanup error."""
    primary = sys.exc_info()[1]
    first = None
    for held in objects:
        if held is not None:
            try: held.close()
            except Exception as exc:
                if first is None: first = exc
    if first is not None and primary is None:
        first._current_reference_failure_phase = phase
        raise first


def _failure_diagnostic(exc, fallback="parent_preflight"):
    if type(exc) is ReportedCurrentReferenceWorkerError:
        try:return _strict_failure(exc.diagnostic)
        except (ValueError, TypeError, KeyError, AttributeError):
            return {"disposition": _FAILURE_DISPOSITION, "failure_phase": "parent_worker_result",
                "failure_class": "SecTitleCurrentReferenceRunnerError", "os_errno": None}
    phase = getattr(exc, "_current_reference_failure_phase", None)
    if type(phase) is not str or phase not in _PHASES: phase = fallback if fallback in _PHASES else "parent_preflight"
    categories = ((SecTitleCurrentReferenceRunnerError, "SecTitleCurrentReferenceRunnerError"),
        (sharadar.SharadarCohortRunnerError, "SharadarCohortRunnerError"),
        (original.capture.bootstrap.custody.ArchiveAssessmentRunnerError, "ArchiveAssessmentRunnerError"),
        (view_front.PemReassessmentRunnerError, "PemReassessmentRunnerError"),
        (original.EarlyParentProjectionError, "EarlyParentProjectionError"),
        (original.OriginalPreparationCustodyError, "OriginalPreparationCustodyError"),
        (pure.SecTitleCurrentReferenceError, "SecTitleCurrentReferenceError"),
        (OSError, "OSError"), (ValueError, "ValueError"), (TypeError, "TypeError"),
        (KeyError, "KeyError"), (subprocess.SubprocessError, "SubprocessError"))
    category = next((label for kind,label in categories if isinstance(exc, kind)), "other_refusal")
    number = exc.errno if isinstance(exc, OSError) else None
    if type(number) is not int or number not in errno.errorcode: number = None
    return {"disposition": "offline_sec_title_current_reference_refused_outputs_preserved",
        "failure_phase": phase, "failure_class": category, "os_errno": number}


def _strict_failure(body):
    _need(type(body) is dict and set(body) == {"disposition", "failure_phase", "failure_class", "os_errno"}
        and body["disposition"] == _FAILURE_DISPOSITION and type(body["failure_phase"]) is str
        and body["failure_phase"] in _PHASES and type(body["failure_class"]) is str
        and body["failure_class"] in _FAILURE_CLASSES
        and (body["os_errno"] is None or type(body["os_errno"]) is int and body["os_errno"] in errno.errorcode),
        "strict_current_reference_failure_required")
    return dict(body)


def _raise_reported_worker_failure(child, output, *, audit_id, stage):
    _need(stage in {"composition", "readonly_semantic_verification"} and type(child.returncode) is int
        and child.returncode == 2 and child.stderr == b"" and type(child.stdout) is bytes
        and 0 < len(child.stdout) <= MAX_CONTROL_BYTES, "isolated_current_reference_worker_failed_outputs_preserved")
    diagnostic = _strict_failure(original.capture._json(child.stdout.removesuffix(b"\n")))
    _need(child.stdout == _raw(diagnostic) + b"\n" and diagnostic["failure_phase"].startswith("worker_"),
        "strict_child_worker_failure_framing_required")
    _need(set(os.listdir(output.fd)) <= _FILES and "reservation.json" in os.listdir(output.fd),
        "failed_worker_output_inventory_changed")
    output.publish("worker-failure.json", _raw({"schema": SCHEMA + "/worker-failure", "audit_id": audit_id,
        "stage": stage, "observed_at_utc": original.capture.custody._utc(),
        "diagnostic": diagnostic, "authority": _authority()}), cap=MAX_CONTROL_BYTES)
    output.check()
    raise ReportedCurrentReferenceWorkerError(diagnostic)


def _fixture_fence(root):
    # BEFORE any actual-root helper/callback; this fixture cannot inspect or write a sibling retained root.
    view_front._strict_temp_fixture_root(root)
    original.capture._fixture_root(root)


def _pins(pins, expected_names):
    _need(type(pins) is dict and set(pins) == set(expected_names), "exact_external_input_leaf_roster_required")
    for digest, size in pins.values():
        _digest(digest)
        _need(type(size) is int and 0 < size <= MAX_INPUT_BYTES, "bounded_external_input_leaf_size_required")


def _producer_identity(identity, *, head, inventory):
    _need(type(identity) is dict and identity.get("root") == str(original.capture.bootstrap.custody.LANE_ROOT)
        and identity.get("branch") == original.capture.bootstrap.custody.LANE_BRANCH and identity.get("head") == head
        and identity.get("clean") is True and type(identity.get("source_sha256")) is dict
        and identity.get("source_inventory_sha256") == inventory == _sha(_raw(identity["source_sha256"])),
        "independent_original_producer_identity_refused")
    for name, digest in identity["source_sha256"].items():
        _need(type(name) is str and not Path(name).is_absolute() and ".." not in Path(name).parts,
            "producer_source_path_refused")
        _digest(digest)


def _verify_producer_git(identity):
    for name, digest in identity["source_sha256"].items():
        _need(_sha(original.capture.bootstrap.custody._git(original.capture.bootstrap.custody.LANE_ROOT,
            "show", identity["head"] + ":" + name)) == digest, "original_producer_committed_source_differs")


class _PinnedSourceView:
    """All five exact view publications and independently pinned old full roster."""
    def __init__(self, *, fixture_only=False, root=None, leaf_pins=None, baseline_context=None):
        _need(type(fixture_only) is bool, "source_view_reader_mode_refused")
        self.baseline = self.tree = None
        try:
            if fixture_only:
                _fixture_fence(root)
                _need(type(baseline_context) is dict, "invented_baseline_context_required")
                baseline = baseline_context
            else:
                _need(root is None and leaf_pins is None and baseline_context is None, "fixed_actual_source_view_root_required")
                self.baseline = view_front._PinnedBaseline(view_front.BASELINE_COMPLETE)
                baseline = self.baseline.metadata
                root = original.capture.bootstrap.custody.LANE_ROOT.joinpath(*view_front.OUTPUT_PARTS, VIEW_ID)
                leaf_pins = VIEW_LEAVES
            _pins(leaf_pins, VIEW_LEAVES)
            self.tree = original.capture.bootstrap._Tree(original.capture.bootstrap.RootSpec("sec-title-source-view", root, "sealed-source-view"))
            _need(set(self.tree.names()) == set(VIEW_LEAVES), "source_view_exact_publication_roster_required")
            raw = {name: self.tree.read((), name, cap=size, expected=digest) for name,(digest,size) in leaf_pins.items()}
            _need(all(len(raw[name]) == size for name,(_,size) in leaf_pins.items()), "source_view_exact_leaf_size_refused")
            complete = original.capture._json(raw["complete.json"])
            assessment = original.capture._json(raw["assessment.json"])
            reservation = original.capture._json(raw["reservation.json"])
            ledger = original.capture._json(raw["parent-ledger.json"])
            inventory = original.capture._json(raw["source-view-inventory.json"])
            _need(complete.get("schema") == view_front.SCHEMA + "/complete" and complete.get("audit_id") == VIEW_ID
                and complete.get("fixture_only") is fixture_only
                and complete.get("capture_id") == original.CAPTURE_ID and complete.get("capture_report_sha256") == view_front.CAPTURE_REPORT
                and _raw(complete.get("authority")) == _raw(pem._authority())
                and _raw(complete.get("frozen_original_baseline")) == _raw(baseline)
                and complete.get("reservation_sha256") == _sha(raw["reservation.json"])
                and complete.get("assessment_sha256") == _sha(raw["assessment.json"])
                and complete.get("parent_ledger_sha256") == _sha(raw["parent-ledger.json"])
                and complete.get("source_view_inventory_sha256") == _sha(raw["source-view-inventory.json"])
                and all(type(complete.get(key)) is int and complete[key] == len(raw[name]) for name,key in (
                    ("assessment.json", "assessment_bytes"), ("parent-ledger.json", "parent_ledger_bytes"),
                    ("source-view-inventory.json", "source_view_inventory_bytes")))
                and reservation.get("audit_id") == VIEW_ID and reservation.get("capture_report_sha256") == view_front.CAPTURE_REPORT
                and _raw(reservation.get("frozen_original_baseline")) == _raw(baseline)
                and _raw(reservation.get("current_execution_identity")) == _raw(complete.get("current_execution_identity"))
                and _raw(reservation.get("frozen_sources")) == _raw(complete.get("frozen_sources")),
                "source_view_immutable_receipt_chain_refused")
            view_front._validate_assessment(assessment, fixture_only=fixture_only, preparation_context=baseline["preparation_context"])
            _need(ledger == view_front._ledger_payload(assessment, baseline)
                and inventory == assessment["source_view_inventory"]
                and complete["counts"] == assessment["counts"]
                and complete["refusal_counts"] == view_front._refusal_counts(assessment), "source_view_deep_accounting_differs")
            view_front._require_observed_lineage(complete, baseline)
            identity = complete["current_execution_identity"]
            if not fixture_only:
                _producer_identity(identity, head=VIEW_HEAD, inventory=VIEW_SOURCE_INVENTORY)
                _need(baseline["preparation_context"]["ordered_source_row_identity_sha256"] == ORDERED_SOURCE_ROSTER
                    and assessment["counts"]["frozen_source_view_projections"] == 57
                    and assessment["counts"]["source_view_parser_quarantined"] == 7
                    and assessment["counts"]["selected_parents"] == 64,
                    "exact_observed_parent_and_population_scope_required")
            source_context = view_front._source_execution_context(complete["source_execution"]["executed_sources"], identity)
            _need(_raw(source_context) == _raw(complete["source_execution"]), "source_view_executed_source_context_differs")
            self.raw = raw
            self.assessment = assessment
            self.complete = complete
            self.producer_identity = identity
            self.context = {"audit_id": VIEW_ID, "publication_pins": {name: {"sha256": digest, "bytes": size}
                for name,(digest,size) in leaf_pins.items()}, "producer_identity": identity,
                "frozen_sources": complete["frozen_sources"], "original_baseline": baseline,
                "capture_context": view_front._capture_context_from(complete),
                "source_execution": complete["source_execution"], "source_view_profile": pem.pem.PROFILE,
                "full_ordered_source_identity": baseline["preparation_context"], "counts": assessment["counts"]}
            self.recheck()
        except BaseException:
            self.close(); raise

    def recheck(self):
        self.tree.recheck()
        if self.baseline is not None: self.baseline.recheck()

    def close(self):
        if self.tree is not None: self.tree.close()
        if self.baseline is not None: self.baseline.close()


class _PinnedSharadar:
    """Read TICKERS+controls; only stream-hash Actions and old assessment."""
    def __init__(self, *, fixture_only=False, root=None, capture_root=None, leaf_pins=None, manifest_pin=None):
        _need(type(fixture_only) is bool, "sharadar_reader_mode_refused")
        self.capture = self.projected = None
        try:
            if fixture_only:
                _fixture_fence(root); _fixture_fence(capture_root)
                _need(type(manifest_pin) is tuple and len(manifest_pin) == 2, "invented_manifest_pin_required")
            else:
                _need(root is None and capture_root is None and leaf_pins is None and manifest_pin is None,
                    "fixed_actual_sharadar_input_roots_required")
                root = original.capture.bootstrap.custody.LANE_ROOT.joinpath(*sharadar.OUTPUT_PARTS, SHARADAR_ID)
                capture_root = sharadar.CAPTURE_ROOT
                leaf_pins = SHARADAR_LEAVES
                manifest_pin = (sharadar.CAPTURE_MANIFEST_SHA256, MANIFEST_BYTES)
            _pins(leaf_pins, SHARADAR_LEAVES); _digest(manifest_pin[0])
            _need(type(manifest_pin[1]) is int and 0 < manifest_pin[1] <= MAX_CONTROL_BYTES, "manifest_exact_size_refused")
            self.capture = sharadar._HeldCapture(capture_root)
            _need(self.capture.names == {"manifest.json", "manifest.sha256", *sharadar.supplied.FILES}, "original_capture_exact_inventory_required")
            manifest = self.capture.open("manifest.json", manifest_pin[1])
            manifest_raw = manifest.read(manifest_pin[1] + 1)
            _need(len(manifest_raw) == manifest_pin[1] and _sha(manifest_raw) == manifest_pin[0], "original_capture_manifest_pin_refused")
            sidecar = self.capture.open("manifest.sha256", 65)
            _need(sidecar.read(66) == (manifest_pin[0] + "\n").encode(), "original_capture_manifest_sidecar_refused")
            self.projected = sharadar._HeldCapture(root)
            _need(self.projected.names == set(SHARADAR_LEAVES), "compact_sharadar_exact_publication_roster_required")
            raw = {}
            for name, (digest,size) in leaf_pins.items():
                stream = self.projected.open(name, size)
                observed, observed_size = sharadar._hash_stream(stream, size)
                _need(observed == digest and observed_size == size, "compact_sharadar_publication_pin_refused")
                if name in {"tickers_projection.json", "complete.json"}:
                    raw[name] = stream.read(size + 1)
                    _need(len(raw[name]) == size and _sha(raw[name]) == digest, "compact_sharadar_read_binding_refused")
            complete = original.capture._json(raw["complete.json"])
            identity = complete.get("execution_identity")
            _need(complete.get("schema") == sharadar.SCHEMA and complete.get("audit_id") == SHARADAR_ID
                and complete.get("fixture_only") is fixture_only and complete.get("capture_manifest_sha256") == manifest_pin[0]
                and complete.get("tickers_projection_sha256") == leaf_pins["tickers_projection.json"][0]
                and complete.get("actions_projection_sha256") == leaf_pins["actions_projection.json"][0]
                and complete.get("assessment_sha256") == leaf_pins["assessment.json"][0]
                and type(complete.get("assessment_bytes")) is int and complete["assessment_bytes"] == leaf_pins["assessment.json"][1]
                and complete.get("original_capture_lineage_preserved") is True
                and complete.get("fundamentals_decoded") is False and complete.get("financial_values_interpreted") is False
                and type(complete.get("provider_dispatches")) is int and complete["provider_dispatches"] == 0
                and type(complete.get("credential_reads")) is int and complete["credential_reads"] == 0
                and type(complete.get("looks_jobs_backtests")) is list and len(complete["looks_jobs_backtests"]) == 3
                and all(type(value) is int and value == 0 for value in complete["looks_jobs_backtests"])
                and all(complete.get(flag) is False for flag in sharadar.FALSE_FLAGS),
                "compact_sharadar_immutable_receipt_context_refused")
            if not fixture_only:
                _producer_identity(identity, head=SHARADAR_HEAD, inventory=SHARADAR_SOURCE_INVENTORY)
                _need(complete.get("inventory_sha256") == original.capture.bootstrap.custody.INVENTORY_SHA256
                    and complete.get("census_complete_sha256") == original.capture.bootstrap.custody.CENSUS_COMPLETE_SHA256
                    and complete.get("counts", {}).get("source_ticker_rows") == 74150,
                    "fixed_sharadar_cohort_population_required")
            self.raw = raw
            self.manifest_raw = manifest_raw
            self.complete = complete
            self.producer_identity = identity
            self.context = {"audit_id": SHARADAR_ID, "publication_pins": {name: {"sha256": digest, "bytes": size}
                for name,(digest,size) in leaf_pins.items()}, "capture_manifest_sha256": manifest_pin[0],
                "capture_manifest_bytes": manifest_pin[1], "producer_identity": identity,
                "census_inventory_sha256": complete.get("inventory_sha256"),
                "census_complete_sha256": complete.get("census_complete_sha256"), "counts": complete.get("counts"),
                "actions_and_prior_assessment_hash_only": True, "financial_fields_interpreted": False}
            self.recheck()
        except BaseException:
            self.close(); raise

    def recheck(self):
        self.capture.check(); self.projected.check()
        _need(_sha(self.manifest_raw) == self.context["capture_manifest_sha256"], "held_manifest_bytes_changed")
        for name, stream, _, cap in self.capture.handles:
            expected = (self.context["capture_manifest_sha256"], self.context["capture_manifest_bytes"]) if name == "manifest.json" else (
                _sha((self.context["capture_manifest_sha256"] + "\n").encode()), 65)
            _need(sharadar._hash_stream(stream, cap) == expected, "original_capture_control_bytes_changed")
        for name, stream, _, cap in self.projected.handles:
            _need(sharadar._hash_stream(stream, cap) == (
                self.context["publication_pins"][name]["sha256"], self.context["publication_pins"][name]["bytes"]),
                "compact_sharadar_bytes_changed")
        self.capture.check(); self.projected.check()

    def close(self):
        if self.capture is not None: self.capture.close()
        if self.projected is not None: self.projected.close()


class _PinnedPublication:
    """Hold every canonical final output through the final input/source checks."""
    def __init__(self, path, expected_hashes, *, fixture_only=False):
        _need(type(fixture_only) is bool, "final_publication_reader_mode_refused")
        if fixture_only:_fixture_fence(path)
        else:
            base = original.capture.bootstrap.custody.LANE_ROOT.joinpath(*OUTPUT_PARTS)
            _need(isinstance(path, Path) and path.parent == base and _ID.fullmatch(path.name),
                "fixed_actual_final_publication_root_required")
        _need(type(expected_hashes) is dict and set(expected_hashes) == _FINAL_FILES,
            "exact_final_publication_hash_inventory_required")
        self.tree = None
        self.hashes = dict(expected_hashes)
        try:
            # Section 194: just-published leaves; recheck() rehashes their content.
            self.tree = sharadar._HeldCapture(path, settle_ctime=True)
            _need(self.tree.names == _FINAL_FILES, "final_publication_exact_leaf_inventory_required")
            for name,digest in sorted(self.hashes.items()):
                _digest(digest)
                self.tree.open(name, MAX_OUTPUT_BYTES if name == "assessment.json" else MAX_CONTROL_BYTES)
            self.recheck()
        except BaseException:
            self.close();raise

    def recheck(self):
        self.tree.check()
        for name,stream,_,cap in self.tree.handles:
            _need(sharadar._hash_stream(stream, cap)[0] == self.hashes[name], "final_held_publication_bytes_changed")
        self.tree.check()

    def close(self):
        if self.tree is not None:self.tree.close()


def _recreate_inventory(descriptors, assessment, *, fixture_only=False):
    _need(type(fixture_only) is bool and type(descriptors) is tuple, "retained_capture_descriptor_tuple_required")
    ledger = assessment.get("parent_qualification_ledger")
    _need(type(ledger) is list and len(ledger) == len(descriptors), "exact_selected_parent_roster_required")
    bridges = []
    for ordinal, (item, expected) in enumerate(zip(descriptors, ledger, strict=True)):
        request = original.capture._request(item["request"])
        raw = item["raw_bytes"]
        _need(type(item["prefix_ordinal"]) is int and type(expected["prefix_ordinal"]) is int
            and item["prefix_ordinal"] == expected["prefix_ordinal"] == ordinal
            and request["accession_number"] == expected["accession_number"]
            and request["source_record_ordinal"] == expected["source_record_ordinal"]
            and item["request_sha256"] == expected["request_sha256"] == _sha(_raw(request))
            and item["result_sha256"] == expected["original_capture_result_sha256"]
            and item["header_identity_bound"] is False and expected["original_capture_header_identity_bound"] is False
            and expected["original_capture_header_quarantine_preserved"] is True
            and item["terminal_disposition"] == "complete_raw_response_retained_header_quarantined"
            and type(raw) is bytes and _sha(raw) == item["body_sha256"]
            and type(item["body_size_bytes"]) is int and len(raw) == item["body_size_bytes"]
            and expected["original_raw_parent"] == {"sha256": item["body_sha256"], "size_bytes": len(raw)},
            "retained_original_to_recorded_ledger_binding_refused")
        view = pem.pem.build_early_pem_source_view(raw, expected_original_body_sha256=item["body_sha256"])
        _need(view.to_payload() == expected["source_view"], "recreated_exact_source_view_differs")
        try:
            bridge = pem.project_genuine_pem_source_view(request, view, capture_result_sha256=item["result_sha256"])
        except pem.SecCompleteSubmissionError as error:
            code = "legacy_blank_separator_refused" if str(error) == "REFUSED: legacy header blank line is not a section separator" else original._parser_refusal_code(error)
            _need(expected["disposition"] == "source_view_frozen_parser_quarantined"
                and expected["projection_bridge"] is None and expected["quarantine_code"] == code,
                "recorded_frozen_parser_refusal_changed")
        else:
            _need(expected["disposition"] == "source_view_projected_noncanonical"
                and expected["quarantine_code"] is None and expected["projection_bridge"] == bridge.to_payload(),
                "genuine_recreated_bridge_differs_from_observed_record")
            bridges.append(bridge)
    inventory = pem.build_pem_source_view_inventory(tuple(bridges))
    _need(inventory.to_payload() == assessment["source_view_inventory"]
        and inventory.sha256 == assessment["source_view_inventory_sha256"], "genuine_recreated_inventory_differs")
    if not fixture_only:
        _need(len(descriptors) == 64 and len(bridges) == 57
            and sum(row["disposition"] == "source_view_frozen_parser_quarantined" for row in ledger) == 7,
            "actual_64_57_7_recreated_partition_required")
    return inventory


def _compose(view, reference, inventory, *, fixture_only):
    return pure.assess_sec_title_current_reference(
        source_view_assessment_raw=view.raw["assessment.json"],
        expected_source_view_assessment_sha256=view.context["publication_pins"]["assessment.json"]["sha256"],
        source_view_complete_raw=view.raw["complete.json"],
        expected_source_view_complete_sha256=view.context["publication_pins"]["complete.json"]["sha256"],
        source_view_parent_inventory=inventory,
        tickers_projection_raw=reference.raw["tickers_projection.json"],
        expected_tickers_projection_sha256=reference.context["publication_pins"]["tickers_projection.json"]["sha256"],
        capture_manifest_raw=reference.manifest_raw,
        expected_capture_manifest_sha256=reference.context["capture_manifest_sha256"],
        sharadar_complete_raw=reference.raw["complete.json"],
        expected_sharadar_complete_sha256=reference.context["publication_pins"]["complete.json"]["sha256"],
        fixture_only=fixture_only)


def _fixed_source_identity(expected_head):
    _need(Path(__file__).resolve() == original.capture.bootstrap.custody.LANE_ROOT / SELF_PATH,
        "inactive_current_reference_runner_not_production_source")
    identity, frozen = original._fixed_source_identity(expected_head)
    _need({SELF_PATH, PURE_PATH, view_front.SELF_PATH, view_front.PURE_PATH, view_front.VIEW_PATH,
        "research/insider_buying_sharadar_reference_cohort_runner.py"} <= set(identity["source_sha256"]),
        "current_reference_committed_source_closure_required")
    return identity, frozen


def _current_bytes(identity, frozen):
    _need({SELF_PATH, PURE_PATH} <= set(identity["source_sha256"]), "current_reference_source_closure_required")
    original._current_bytes(identity, frozen)


def _output_directory(audit_id, *, create):
    _need(type(audit_id) is str and _ID.fullmatch(audit_id), "current_reference_audit_id_refused")
    base = original.capture.bootstrap.custody.LANE_ROOT.joinpath(*OUTPUT_PARTS)
    if create:
        parent = original.capture.custody._Directory(base, create=True)
        try:
            _need(not parent.exists(audit_id), "fresh_current_reference_output_required")
            info = os.fstatvfs(parent.fd)
            _need(info.f_bavail * info.f_frsize >= MIN_FREE_BYTES + MAX_OUTPUT_BYTES + 3 * MAX_CONTROL_BYTES,
                "current_reference_disk_reserve_refused")
            os.mkdir(audit_id, 0o700, dir_fd=parent.fd); os.fsync(parent.fd)
        finally: parent.close()
    return original.capture.custody._Directory(base / audit_id)


def _reservation(audit_id, context):
    return {"schema": SCHEMA + "/reservation", "audit_id": audit_id, "fixture_only": False,
        "current_execution_identity": context["identity"], "frozen_sources": context["frozen_sources"],
        "source_view_context": context["source_view_context"], "sharadar_context": context["sharadar_context"],
        "source_only_bootstrap_sha256": _sha(SOURCE_ONLY_BOOTSTRAP.encode()), "authority": _authority()}


def _source_execution_context(rows, identity):
    context = view_front._source_execution_context(rows, identity)
    _need({SELF_PATH, PURE_PATH, "research/insider_buying_sharadar_reference_cohort.py"}
        <= {row["path"] for row in rows}, "executed_current_reference_sources_required")
    return context


def _prove_readonly_isolation(output_path):
    original._prove_worker_isolation(output_path)
    try:probe = os.open(output_path / ".readonly-write-probe", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except OSError as exc:_need(exc.errno in {errno.EPERM, errno.EACCES}, "effective_readonly_output_write_denial_not_observed")
    else:os.close(probe);raise SecTitleCurrentReferenceRunnerError("effective_readonly_output_write_denial_not_observed")


def _child_json(child):
    _need(type(child.returncode) is int and child.returncode == 0 and child.stderr == b""
        and type(child.stdout) is bytes and 0 < len(child.stdout) <= MAX_CONTROL_BYTES,
        "isolated_current_reference_child_failed_outputs_preserved")
    body = original.capture._json(child.stdout.removesuffix(b"\n"))
    _need(child.stdout == _raw(body) + b"\n", "strict_success_child_canonical_framing_required")
    return body


def _validate_summary(body, *, audit_id, context, fixture_only=False):
    _need(type(body) is dict and set(body) == {"audit_id", "fixture_only", "complete_sha256", "assessment_sha256",
        "counts", "title_refusal_counts", "ticker_refusal_counts", "authority"}
        and body["audit_id"] == audit_id and body["fixture_only"] is fixture_only
        and _raw(body["authority"]) == _raw(_authority()), "strict_current_reference_summary_required")
    _digest(body["complete_sha256"]); _digest(body["assessment_sha256"])
    _need(type(body["counts"]) is dict and set(body["counts"]) == set(pure.COUNT_KEYS)
        and all(type(value) is int and value >= 0 for value in body["counts"].values()), "strict_current_reference_counts_required")
    for key, codes in (("title_refusal_counts", pure.TITLE_REFUSAL_CODES), ("ticker_refusal_counts", pure.TICKER_REFUSAL_CODES)):
        _need(type(body[key]) is dict and set(body[key]) == set(codes)
            and all(type(value) is int and value >= 0 for value in body[key].values()), "strict_current_reference_refusal_counts_required")
    counts = body["counts"]
    source = context["source_view_context"]["counts"]
    ticker = context["sharadar_context"]["counts"]["source_ticker_rows"]
    bindings = {"source_filings": "source_filings", "target_filings": "target_filings", "context_filings": "context_filings",
        "selected_parents": "selected_parents", "genuine_view_parents": "frozen_source_view_projections",
        "parser_refused_selected_parents": "source_view_parser_quarantined"}
    _need(all(type(source.get(key)) is int and counts[name] == source[key] for name,key in bindings.items())
        and type(ticker) is int and counts["ticker_rows"] == ticker,
        "summary_held_input_population_differs")
    _need(counts["target_filings"] + counts["context_filings"] == counts["source_filings"]
        and counts["selected_parents"] + counts["unselected_filings"] == counts["source_filings"]
        and counts["genuine_view_parents"] + counts["parser_refused_selected_parents"] == counts["selected_parents"]
        and counts["plain_title_occurrences"] + counts["quarantined_title_occurrences"] == counts["title_occurrences"]
        and counts["ticker_rows_with_cik_candidates"] + counts["ticker_rows_without_cik_candidates"] == ticker
        and counts["titles_without_current_cik_groups"] + counts["titles_with_one_current_cik_group"]
            + counts["titles_with_multiple_current_cik_groups"] == counts["unique_cik_titles"]
        and counts["current_permaticker_groups"] <= ticker and counts["conflicted_current_permaticker_groups"] <= counts["current_permaticker_groups"]
        and counts["genuine_parents_without_nonderivative_rows"] <= counts["genuine_view_parents"]
        and counts["quarantined_ticker_rows"] <= ticker
        and counts["duplicate_exact_ticker_rows"] <= ticker and counts["conflicting_ticker_key_rows"] <= ticker
        and counts["unique_cik_titles"] <= counts["plain_title_occurrences"] <= pure.MAX_TITLE_OCCURRENCES
        and sum(body["title_refusal_counts"].values()) >= counts["quarantined_title_occurrences"]
        and sum(body["ticker_refusal_counts"].values()) >= counts["quarantined_ticker_rows"],
        "summary_complete_partitions_refused")
    return body


def _verify_publication(output, summary, *, context, expected_assessment_raw=None, fixture_only=False):
    _need(type(expected_assessment_raw) is bytes and 0 < len(expected_assessment_raw) <= MAX_OUTPUT_BYTES,
        "independently_rederived_canonical_result_required")
    _validate_summary(summary, audit_id=summary["audit_id"], context=context, fixture_only=fixture_only)
    _need(set(os.listdir(output.fd)) == _FILES, "exact_current_reference_publication_roster_required")
    reservation_raw = output.read("reservation.json", cap=MAX_CONTROL_BYTES)
    _need(original.capture._json(reservation_raw) == _reservation(summary["audit_id"], context), "publication_reservation_context_differs")
    complete_raw = output.read("complete.json", cap=MAX_CONTROL_BYTES)
    _need(_sha(complete_raw) == summary["complete_sha256"], "current_reference_completion_hash_differs")
    complete = original.capture._json(complete_raw)
    expected_keys = {"schema", "audit_id", "fixture_only", "observed_at_utc", "current_execution_identity", "frozen_sources",
        "source_view_context", "sharadar_context", "reservation_sha256", "assessment_sha256", "assessment_bytes",
        "counts", "title_refusal_counts", "ticker_refusal_counts", "source_execution", "source_only_bootstrap_sha256", "authority"}
    _need(set(complete) == expected_keys and complete["schema"] == SCHEMA + "/complete"
        and complete["audit_id"] == summary["audit_id"] and complete["fixture_only"] is fixture_only
        and _raw(complete["current_execution_identity"]) == _raw(context["identity"])
        and _raw(complete["frozen_sources"]) == _raw(context["frozen_sources"])
        and _raw(complete["source_view_context"]) == _raw(context["source_view_context"])
        and _raw(complete["sharadar_context"]) == _raw(context["sharadar_context"])
        and complete["reservation_sha256"] == _sha(reservation_raw)
        and complete["source_only_bootstrap_sha256"] == _sha(SOURCE_ONLY_BOOTSTRAP.encode())
        and all(_raw(complete[key]) == _raw(summary[key]) for key in ("counts", "title_refusal_counts", "ticker_refusal_counts", "authority")),
        "current_reference_completion_full_context_differs")
    original.capture.bootstrap._utc(complete["observed_at_utc"])
    encoded = output.read("assessment.json", cap=MAX_OUTPUT_BYTES)
    _need(_sha(encoded) == complete["assessment_sha256"] == summary["assessment_sha256"]
        and type(complete["assessment_bytes"]) is int and complete["assessment_bytes"] == len(encoded), "current_reference_assessment_hash_or_size_differs")
    _need(encoded == expected_assessment_raw, "current_reference_readback_differs_from_twice_rederived_result")
    payload = original.capture._json(encoded)
    _need(payload.get("schema") == pure.SCHEMA and payload.get("profile") == pure.PROFILE
        and payload.get("fixture_only") is fixture_only
        and all(_raw(payload.get(key)) == _raw(summary[key]) for key in ("counts", "title_refusal_counts", "ticker_refusal_counts", "authority")),
        "current_reference_private_assessment_summary_differs")
    execution = _source_execution_context(complete["source_execution"]["executed_sources"], context["identity"])
    _need(execution == complete["source_execution"], "current_reference_execution_inventory_differs")
    output.check()
    return complete


def _publish(output, result, *, audit_id, context, reservation_raw, executed_sources, fixture_only=False):
    _need(type(result) is pure.SecTitleCurrentReferenceAssessment, "genuine_current_reference_result_required")
    encoded = result.canonical_bytes()
    _need(type(encoded) is bytes and 0 < len(encoded) <= MAX_OUTPUT_BYTES, "bounded_current_reference_result_required")
    payload = result.to_payload()
    assessment_sha = output.publish("assessment.json", encoded, cap=MAX_OUTPUT_BYTES)
    complete = {"schema": SCHEMA + "/complete", "audit_id": audit_id, "fixture_only": fixture_only,
        "observed_at_utc": original.capture.custody._utc(), "current_execution_identity": context["identity"],
        "frozen_sources": context["frozen_sources"], "source_view_context": context["source_view_context"],
        "sharadar_context": context["sharadar_context"], "reservation_sha256": _sha(reservation_raw),
        "assessment_sha256": assessment_sha, "assessment_bytes": len(encoded), "counts": payload["counts"],
        "title_refusal_counts": payload["title_refusal_counts"], "ticker_refusal_counts": payload["ticker_refusal_counts"],
        "source_execution": _source_execution_context(executed_sources, context["identity"]),
        "source_only_bootstrap_sha256": _sha(SOURCE_ONLY_BOOTSTRAP.encode()), "authority": _authority()}
    complete_sha = output.publish("complete.json", _raw(complete), cap=MAX_CONTROL_BYTES)
    summary = {"audit_id": audit_id, "fixture_only": fixture_only, "complete_sha256": complete_sha,
        "assessment_sha256": assessment_sha, "counts": payload["counts"], "title_refusal_counts": payload["title_refusal_counts"],
        "ticker_refusal_counts": payload["ticker_refusal_counts"], "authority": _authority()}
    _verify_publication(output, summary, context=context, expected_assessment_raw=encoded, fixture_only=fixture_only)
    return summary


def _worker(audit_id, *, expected_head, context, executed_sources=None, bootstrap_source=None, verify_only=False):
    _need(Path(__file__).resolve() == original.capture.bootstrap.custody.LANE_ROOT / SELF_PATH
        and Path.cwd() == original.capture.bootstrap.custody.LANE_ROOT, "inactive_current_reference_worker_not_production_source")
    _need(type(context) is dict and set(context) == {"identity", "frozen_sources", "source_view_context", "sharadar_context"}
        and type(executed_sources) is list and type(bootstrap_source) is dict and type(verify_only) is bool,
        "captured_current_reference_context_required")
    identity, frozen = context["identity"], context["frozen_sources"]
    original.capture.bootstrap._required_identity(identity, expected_head); _current_bytes(identity, frozen)
    output = _at_phase("worker_output_reservation", _output_directory, audit_id, create=False)
    view = reference = capture = None
    try:
        _need(set(os.listdir(output.fd)) == (_FILES if verify_only else {"reservation.json"}), "fresh_reserved_current_reference_output_required")
        reservation_raw = output.read("reservation.json", cap=MAX_CONTROL_BYTES)
        _need(original.capture._json(reservation_raw) == _reservation(audit_id, context), "worker_current_reference_reservation_differs")
        _at_phase("worker_isolation", _prove_readonly_isolation if verify_only else original._prove_worker_isolation, output.path)
        sys.addaudithook(original.isolation._audit_event)
        view = _at_phase("worker_inputs", _PinnedSourceView)
        reference = _at_phase("worker_inputs", _PinnedSharadar)
        _need(view.context == context["source_view_context"] and reference.context == context["sharadar_context"],
            "independent_parent_worker_input_context_differs")
        capture, descriptors, reservation, report = _at_phase("worker_capture", original._load_sealed_capture, view_front.CAPTURE_REPORT)
        _need(view_front._loaded_capture_context(reservation, report) == view.context["capture_context"], "retained_capture_context_differs_from_bound_source_view")
        inventory = _at_phase("worker_composition", _recreate_inventory, descriptors, view.assessment)
        result = _at_phase("worker_composition", _compose, view, reference, inventory, fixture_only=False)
        repeated = _at_phase("worker_replay", _compose, view, reference, inventory, fixture_only=False)
        _need(result.canonical_bytes() == repeated.canonical_bytes(), "current_reference_full_pure_reexecution_differs")
        for held in (view, reference, capture): held.recheck()
        _current_bytes(identity, frozen)
        if verify_only:
            # Fresh independently captured, native READ-ONLY process: never publish,
            # rerun the original operation, or infer semantics from receipt labels.
            complete_raw = output.read("complete.json", cap=MAX_CONTROL_BYTES)
            payload = result.to_payload()
            summary = {"audit_id": audit_id, "fixture_only": False, "complete_sha256": _sha(complete_raw),
                "assessment_sha256": result.sha256, **{key: payload[key] for key in (
                    "counts", "title_refusal_counts", "ticker_refusal_counts", "authority")}}
            _at_phase("worker_readback", _verify_publication, output, summary, context=context,
                expected_assessment_raw=result.canonical_bytes())
        else:
            summary = _at_phase("worker_publication", _publish, output, result, audit_id=audit_id, context=context,
                reservation_raw=reservation_raw, executed_sources=[bootstrap_source, *executed_sources])
        for held in (view, reference, capture): held.recheck()
        _current_bytes(identity, frozen)
        _validate_summary(summary, audit_id=audit_id, context=context)
        if verify_only:
            return {"schema": SCHEMA + "/readonly-verification", "verified_summary": summary,
                "source_execution": _source_execution_context([bootstrap_source, *executed_sources], identity),
                "effective_process_tree_network_denial": True, "effective_process_fork_denial": True,
                "effective_inside_output_write_denial": True, "authority": _authority()}
        return summary
    finally:
        _close_all("worker_cleanup", capture, reference, view, output)


def run_observed_assessment(audit_id, *, expected_head):
    identity, frozen = _at_phase("parent_preflight", _fixed_source_identity, expected_head)
    _at_phase("parent_original_sources", original.capture._verify_original_committed_sources, original.CAPTURE_ID, view_front.CAPTURE_REPORT)
    view = reference = output = publication = None
    try:
        # Every actual context and historical producing image is checked BEFORE reservation.
        view = _at_phase("parent_inputs", _PinnedSourceView)
        reference = _at_phase("parent_inputs", _PinnedSharadar)
        for source in (view, reference): _at_phase("parent_producer_sources", _verify_producer_git, source.producer_identity)
        context = {"identity": identity, "frozen_sources": frozen, "source_view_context": view.context, "sharadar_context": reference.context}
        output = _at_phase("parent_output_reservation", _output_directory, audit_id, create=True)
        reservation_raw = _raw(_reservation(audit_id, context))
        output.publish("reservation.json", reservation_raw, cap=MAX_CONTROL_BYTES)
        sources = []
        for name, digest in sorted(identity["source_sha256"].items()):
            raw = original.isolation._read_source(name)
            _need(_sha(raw) == digest, "captured_current_reference_source_differs")
            sources.append({"path": name, "sha256": digest, "source_b64": base64.b64encode(raw).decode("ascii")})
        envelope_body = {"sources": sources, "context": context, "audit_id": audit_id, "expected_head": expected_head, "verify_only": False}
        envelope = _raw(envelope_body)
        _need(len(envelope) <= MAX_CONTEXT_BYTES, "captured_current_reference_context_bound_refused")
        for held in (view, reference): held.recheck()
        _need(_fixed_source_identity(expected_head) == (identity, frozen), "current_reference_source_changed_before_worker")
        child = _at_phase("parent_worker_launch", subprocess.run, ["/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin",
            "/usr/bin/sandbox-exec", "-p", original.isolation._worker_policy(output.path), sys.executable, "-I", "-S", "-B", "-c", SOURCE_ONLY_BOOTSTRAP],
            cwd=original.capture.bootstrap.custody.LANE_ROOT, input=envelope, capture_output=True, check=False, timeout=1800)
        for held in (view, reference): held.recheck()
        _need(_fixed_source_identity(expected_head) == (identity, frozen), "current_reference_source_changed_after_worker")
        if child.returncode != 0:
            _at_phase("parent_worker_result", _raise_reported_worker_failure, child, output, audit_id=audit_id, stage="composition")
        _need(type(child.returncode) is int and child.returncode == 0 and child.stderr == b""
            and type(child.stdout) is bytes and 0 < len(child.stdout) <= MAX_CONTROL_BYTES
            and child.stdout.endswith(b"\n") and not child.stdout.endswith(b"\n\n"), "isolated_current_reference_worker_failed_outputs_preserved")
        summary = _at_phase("parent_worker_result", _validate_summary, _child_json(child), audit_id=audit_id, context=context)
        # The parent remains hash/control-only. All retained parsing and semantic
        # readback run in a fresh captured-source native-denied read-only verifier.
        envelope_body["verify_only"] = True
        verifier = _at_phase("parent_worker_launch", subprocess.run, ["/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin",
            "/usr/bin/sandbox-exec", "-p", original.isolation._worker_policy(output.path, readonly=True),
            sys.executable, "-I", "-S", "-B", "-c", SOURCE_ONLY_BOOTSTRAP],
            cwd=original.capture.bootstrap.custody.LANE_ROOT, input=_raw(envelope_body), capture_output=True, check=False, timeout=1800)
        for held in (view, reference): held.recheck()
        _need(_fixed_source_identity(expected_head) == (identity, frozen), "current_reference_source_changed_after_readonly_verifier")
        if verifier.returncode != 0:
            _at_phase("parent_worker_result", _raise_reported_worker_failure, verifier, output,
                audit_id=audit_id, stage="readonly_semantic_verification")
        _need(type(verifier.returncode) is int and verifier.returncode == 0 and verifier.stderr == b""
            and type(verifier.stdout) is bytes and 0 < len(verifier.stdout) <= MAX_CONTROL_BYTES
            and verifier.stdout.endswith(b"\n") and not verifier.stdout.endswith(b"\n\n"),
            "isolated_current_reference_readonly_verifier_failed_outputs_preserved")
        verification = _at_phase("parent_publication_verification", _child_json, verifier)
        _need(type(verification) is dict and set(verification) == {"schema", "verified_summary", "source_execution",
            "effective_process_tree_network_denial", "effective_process_fork_denial", "effective_inside_output_write_denial", "authority"}
            and verification["schema"] == SCHEMA + "/readonly-verification"
            and all(verification[flag] is True for flag in ("effective_process_tree_network_denial", "effective_process_fork_denial",
                "effective_inside_output_write_denial")) and _raw(verification["authority"]) == _raw(_authority())
            and _source_execution_context(verification["source_execution"]["executed_sources"], identity) == verification["source_execution"],
            "strict_independent_readonly_verification_receipt_required")
        verified = _at_phase("parent_publication_verification", _validate_summary,
            verification["verified_summary"], audit_id=audit_id, context=context)
        _need(_raw(verified) == _raw(summary), "independent_readonly_semantic_verification_differs")
        _need(set(os.listdir(output.fd)) == _FILES
            and output.read("reservation.json", cap=MAX_CONTROL_BYTES) == reservation_raw
            and _sha(output.read("assessment.json", cap=MAX_OUTPUT_BYTES)) == summary["assessment_sha256"]
            and _sha(output.read("complete.json", cap=MAX_CONTROL_BYTES)) == summary["complete_sha256"],
            "parent_final_held_receipt_hashes_differ")
        output.check()
        verification_raw = _raw(verification)
        output.publish("readonly-verification.json", verification_raw, cap=MAX_CONTROL_BYTES)
        _need(set(os.listdir(output.fd)) == _FINAL_FILES
            and output.read("readonly-verification.json", cap=MAX_CONTROL_BYTES) == verification_raw,
            "parent_final_readonly_verification_receipt_differs")
        output.check()
        publication = _at_phase("parent_final_output_hold", _PinnedPublication, output.path, {"reservation.json": _sha(reservation_raw),
            "assessment.json": summary["assessment_sha256"], "complete.json": summary["complete_sha256"],
            "readonly-verification.json": _sha(verification_raw)})
        _at_phase("parent_final_source_view", view.recheck)
        _at_phase("parent_final_reference", reference.recheck)
        final_identity = _at_phase("parent_final_source_identity", _fixed_source_identity, expected_head)
        _at_phase("parent_final_source_identity", _need, final_identity == (identity, frozen),
            "current_reference_source_changed_at_publication")
        _at_phase("parent_final_output_recheck", publication.recheck)
        return summary
    finally:
        _close_all("parent_cleanup", publication, output, reference, view)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-id", required=True); parser.add_argument("--expected-head", required=True)
    args = parser.parse_args(argv)
    try:
        result = run_observed_assessment(args.audit_id, expected_head=args.expected_head)
        print(_raw(result).decode()); return 0
    except (ValueError, OSError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        print(_raw(_failure_diagnostic(exc)).decode()); return 2


if __name__ == "__main__": raise SystemExit(main())
