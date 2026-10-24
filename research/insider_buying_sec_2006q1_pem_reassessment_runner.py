"""Isolated original-to-PEM-view full-quarter reassessment front.

Only the fixed clean committed lane image can run production. The
observed frozen original-body baseline is pinned before fresh reservation.
No acquisition, signature/authenticity verification or original-body
admission is performed. The worker imports captured lane source bytes only.
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
import tempfile

from research import insider_buying_sec_2006q1_parent_projection_v1 as original
from research import insider_buying_sec_2006q1_pem_reassessment_v1 as pure


SCHEMA = "insider-2006q1-isolated-pem-source-view-reassessment-v1"
SELF_PATH = "research/insider_buying_sec_2006q1_pem_reassessment_runner.py"
PURE_PATH = "research/insider_buying_sec_2006q1_pem_reassessment_v1.py"
VIEW_PATH = "research/insider_buying_sec_early_pem_source_view_v1.py"
OUTPUT_PARTS = ("artifacts", "insider_buying", "sec_2006q1_pem_reassessment_v1")
BASELINE_ID = "ib-2006q1-parent-projection-public-layout-v2-20261014-once"
BASELINE_HEAD = "c1ccbc601c9c2b40217938cc55346c6281c85b5f"
BASELINE_SOURCE_INVENTORY = "35cedb27c44c92935e3edd5a554382d1fdcf7ec8023b588d9ff75a8ce1e8a419"
BASELINE_COMPLETE = "3263625af39268bc1ab4d2c44522e6ce0b8a3a6df80f61202bb6b725df567434"
CAPTURE_REPORT = "7d42a6634bf378f159f00e62697eaac446b41038f276f05ca12fe524e8a9076a"
BASELINE_LEAVES = {
    "complete.json": (BASELINE_COMPLETE, 23590),
    "assessment.json": ("3000a184944aa1718854dba90842ec774032c269fc36740dc46ddbe90c1f1525", 63409871),
    "parent-projection.json": ("44d3e228121fdfe2f15d1c7e7af6de1a9610c67fcc72f2d49443ff8f946a8e95", 42116),
    "reservation.json": ("b0cf6c3d5e4d1530afacf9e1cd882e7a741f6437f66a0a903d9b7a131270abbe", 11658),
}
MAX_ASSESSMENT_BYTES = pure.MAX_OUTPUT_BYTES
MAX_CONTROL_BYTES = 1024 * 1024
MAX_LEDGER_BYTES = 2 * 1024 * 1024
MAX_CONTEXT_BYTES = original.MAX_WORKER_CONTEXT_BYTES
MIN_FREE_BYTES = original.MIN_FREE_BYTES
_ID = re.compile(r"ib-2006q1-pem-view-[a-z0-9-]{1,70}\Z")
_COUNT_KEYS = frozenset({"source_filings", "target_filings", "context_filings", "selected_parents",
    "original_bodies_retained", "exact_pem_source_views", "frozen_source_view_projections",
    "pem_profile_quarantined", "source_view_parser_quarantined", "source_view_unavailable",
    "source_view_corroborated_noncanonical", "quarantined_filings", "original_parent_bytes", "original_body_admitted"})
_REFUSALS = frozenset({*original.PARSER_REFUSAL_CODES, "legacy_blank_separator_refused",
    "exact_pem_outer_envelope_profile_refused"})
_PHASES = original._FAILURE_PHASES | {"parent_baseline", "worker_baseline"}
_FILES = frozenset({"reservation.json", "assessment.json", "parent-ledger.json", "source-view-inventory.json", "complete.json"})
_PREPARATION_LABEL_KEYS = frozenset({"parsed_snapshot_id", "parsed_lineage_sha256", "census_quarter_sha256"})
_PREPARATION_KEYS = _PREPARATION_LABEL_KEYS | {"source_row_count", "ordered_source_row_identity_sha256"}
_CAPTURE_CONTEXT_KEYS = frozenset({"capture_id", "capture_execution_head", "capture_execution_source_inventory_sha256", "bootstrap_execution_head"})
_SOURCE_ROW_KEYS = ("period", "source_record_ordinal", "accession_number", "form_type", "raw_filing_date", "filing_date",
    "raw_issuer_cik", "issuer_comparison_key", "short_cik", "accession_year_mismatch", "submission_row_id",
    "raw_archive_sha256", "raw_submission_member_sha256", "parsed_lineage_hash")


SOURCE_ONLY_BOOTSTRAP = r'''
import base64, errno, hashlib, json, sys, types
consumer = None
phase = "worker_bootstrap_context"
try:
    def need(value):
        if not value: raise ValueError("source-only PEM context refused")
    context_raw = sys.stdin.buffer.read(33554433)
    need(0 < len(context_raw) <= 33554432)
    envelope = json.loads(context_raw)
    need(type(envelope) is dict and set(envelope) == {"sources", "parent_context", "audit_id", "expected_head", "report_sha256", "baseline_sha256"})
    rows = envelope["sources"]
    need(type(rows) is list)
    selected = [r for r in rows if r.get("path") == "research/insider_buying_affected_quarter_isolation.py"]
    need(len(selected) == 1)
    raw = base64.b64decode(selected[0]["source_b64"], validate=True)
    need(hashlib.sha256(raw).hexdigest() == selected[0]["sha256"])
    helper = types.ModuleType("_pem_captured_imports")
    helper.__file__ = "/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying/research/insider_buying_affected_quarter_isolation.py"
    sys.modules[helper.__name__] = helper
    exec(compile(raw, helper.__file__, "exec", dont_inherit=True), helper.__dict__)
    sys.modules["research.insider_buying_affected_quarter_isolation"] = helper
    phase = "worker_bootstrap_source_decode"
    sources = helper._decode_sources(rows)
    need({p: helper._sha(b) for p,b in sources} == envelope["parent_context"]["identity"]["source_sha256"])
    finder = helper._SourceFinder(sources)
    sys.meta_path.insert(0, finder)
    # Effective OS denial is proven by the consumer BEFORE installing the
    # Python hook. The hook cannot masquerade as the required OS probe result.
    phase = "worker_bootstrap_import"
    from research import insider_buying_sec_2006q1_pem_reassessment_runner as consumer
    phase = "worker_execution"
    result = consumer._worker(envelope["audit_id"], expected_head=envelope["expected_head"],
        expected_capture_report_sha256=envelope["report_sha256"],
        expected_baseline_complete_sha256=envelope["baseline_sha256"], parent_context=envelope["parent_context"],
        executed_sources=finder.executed,
        bootstrap_source={"path": "research/insider_buying_affected_quarter_isolation.py", "sha256": selected[0]["sha256"]})
    print(consumer._raw(result).decode())
except Exception as exc:
    if consumer is not None and callable(getattr(consumer, "_failure_diagnostic", None)):
        body = consumer._failure_diagnostic(exc, phase)
    else:
        labels = ((OSError, "OSError"), (ValueError, "ValueError"), (TypeError, "TypeError"), (KeyError, "KeyError"))
        category = next((label for kind,label in labels if isinstance(exc, kind)), "other_refusal")
        number = exc.errno if isinstance(exc, OSError) else None
        if type(number) is not int or number not in errno.errorcode: number = None
        body = {"disposition": "offline_pem_source_view_refused_outputs_preserved",
            "failure_phase": phase, "failure_class": category, "os_errno": number}
    print(json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False))
    raise SystemExit(2)
'''


class PemReassessmentRunnerError(ValueError):
    """Fixed codes only; retained private/source exception text excluded."""


class ReportedWorkerError(PemReassessmentRunnerError):
    def __init__(self, diagnostic):
        self.diagnostic = _strict_failure(diagnostic)
        super().__init__("isolated_pem_reassessment_failed_outputs_preserved")


def _need(value, code):
    if not value: raise PemReassessmentRunnerError(code)


def _raw(body):return json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
def _sha(raw):return hashlib.sha256(raw).hexdigest()
def _authority():return pure._authority()
def _digest(value):return original._digest(value)


def _at_phase(phase, function, *args, **kwargs):
    _need(phase in _PHASES, "internal_failure_phase_refused")
    try:return function(*args, **kwargs)
    except Exception as exc:
        exc._pem_failure_phase = phase
        raise


def _failure_diagnostic(exc, fallback="parent_preflight"):
    if type(exc) is ReportedWorkerError:return _strict_failure(exc.diagnostic)
    phase = getattr(exc, "_pem_failure_phase", None)
    if type(phase) is not str or phase not in _PHASES:phase = fallback if fallback in _PHASES else "parent_preflight"
    classes = ((PemReassessmentRunnerError, "PemReassessmentRunnerError"),
        (pure.PemSourceViewEvidenceError, "PemSourceViewEvidenceError"),
        (original.OriginalPreparationCustodyError, "OriginalPreparationCustodyError"),
        (original.EarlyParentProjectionError, "EarlyParentProjectionError"),
        (OSError, "OSError"), (ValueError, "ValueError"), (TypeError, "TypeError"),
        (KeyError, "KeyError"), (subprocess.SubprocessError, "SubprocessError"))
    label = next((label for kind,label in classes if isinstance(exc, kind)), "other_refusal")
    number = exc.errno if isinstance(exc, OSError) else None
    if type(number) is not int or number not in errno.errorcode:number = None
    return {"disposition": "offline_pem_source_view_refused_outputs_preserved",
        "failure_phase": phase, "failure_class": label, "os_errno": number}


def _strict_failure(body):
    labels = {"PemReassessmentRunnerError", "PemSourceViewEvidenceError", "OriginalPreparationCustodyError",
        "EarlyParentProjectionError", "OSError", "ValueError", "TypeError", "KeyError", "SubprocessError", "other_refusal"}
    _need(type(body) is dict and set(body) == {"disposition", "failure_phase", "failure_class", "os_errno"}
        and body["disposition"] == "offline_pem_source_view_refused_outputs_preserved"
        and type(body["failure_phase"]) is str and body["failure_phase"] in _PHASES
        and type(body["failure_class"]) is str and body["failure_class"] in labels
        and (body["os_errno"] is None or type(body["os_errno"]) is int and body["os_errno"] in errno.errorcode),
        "worker_failure_diagnostic_refused")
    return dict(body)


def _close_all(holds, *, phase):
    """Close every hold; a cleanup failure never replaces the primary refusal.

    Section 194 (Claude review): the earlier loops stopped at the first close
    that raised, leaving later holds open and masking the original exception.
    """
    _need(phase is None or phase in _PHASES, "internal_failure_phase_refused")
    primary, first = sys.exc_info()[1], None
    for held in holds:
        if held is not None:
            try:held.close()
            except Exception as exc:
                if first is None:first = exc
    if primary is None and first is not None:
        if phase is not None:first._pem_failure_phase = phase
        raise first


class _PinnedBaseline:
    """Exact four-file original-body baseline, held/rechecked, never rewritten."""
    def __init__(self, expected_complete_sha256, *, fixture_only=False, root=None, leaf_pins=None):
        _digest(expected_complete_sha256)
        _need(type(fixture_only) is bool, "baseline_mode_refused")
        if fixture_only:
            _strict_temp_fixture_root(root)
            original.capture._fixture_root(root)
            _need(type(leaf_pins) is dict and set(leaf_pins) == set(BASELINE_LEAVES), "fixture_baseline_leaf_pins_required")
        else:
            _need(root is None and leaf_pins is None and expected_complete_sha256 == BASELINE_COMPLETE,
                "fixed_external_frozen_baseline_pin_required")
            root = original.capture.bootstrap.custody.LANE_ROOT.joinpath(*original.OUTPUT_PARTS, BASELINE_ID)
            leaf_pins = BASELINE_LEAVES
        self.tree = original.capture.bootstrap._Tree(original.capture.bootstrap.RootSpec("early-pem-frozen-baseline", root, "frozen-original-baseline"))
        try:
            _need(set(self.tree.names()) == set(BASELINE_LEAVES), "frozen_baseline_publication_inventory_refused")
            for name, item in leaf_pins.items():
                _need(type(item) is tuple and len(item) == 2 and type(item[1]) is int and 0 < item[1]
                    <= (MAX_ASSESSMENT_BYTES if name == "assessment.json" else MAX_CONTROL_BYTES), "baseline_leaf_pin_shape_refused")
                _digest(item[0])
            _need(leaf_pins["complete.json"][0] == expected_complete_sha256, "baseline_external_complete_pin_differs")
            raw = {name: self.tree.read((), name, cap=size, expected=digest) for name,(digest,size) in leaf_pins.items()}
            _need(all(len(raw[name]) == size for name,(_,size) in leaf_pins.items()), "baseline_exact_leaf_size_refused")
            complete = original.capture._json(raw["complete.json"])
            reservation = original.capture._json(raw["reservation.json"])
            ledger = original.capture._json(raw["parent-projection.json"])
            _need(complete.get("schema") == original.SCHEMA + "/complete" and complete.get("audit_id") == BASELINE_ID
                and complete.get("fixture_only") is fixture_only and complete.get("capture_id") == original.CAPTURE_ID
                and complete.get("capture_report_sha256") == CAPTURE_REPORT
                and complete.get("reservation_sha256") == _sha(raw["reservation.json"])
                and complete.get("assessment_sha256") == _sha(raw["assessment.json"])
                and complete.get("projection_ledger_sha256") == _sha(raw["parent-projection.json"])
                and type(complete.get("assessment_bytes")) is int and complete["assessment_bytes"] == len(raw["assessment.json"])
                and type(complete.get("projection_ledger_bytes")) is int and complete["projection_ledger_bytes"] == len(raw["parent-projection.json"])
                and _raw(complete.get("authority")) == _raw(original._authority())
                and _raw(complete.get("counts")) == _raw(ledger.get("counts"))
                and _raw(complete.get("projection_refusal_counts")) == _raw(ledger.get("projection_refusal_counts"))
                and reservation.get("audit_id") == BASELINE_ID and reservation.get("capture_report_sha256") == CAPTURE_REPORT,
                "frozen_baseline_receipt_chain_refused")
            summary = {"audit_id": BASELINE_ID, "fixture_only": False, "complete_sha256": expected_complete_sha256,
                "assessment_sha256": complete["assessment_sha256"], "projection_ledger_sha256": complete["projection_ledger_sha256"],
                "capture_report_sha256": CAPTURE_REPORT, "counts": complete["counts"],
                "projection_refusal_counts": complete["projection_refusal_counts"], "authority": original._authority()}
            if not fixture_only:
                original._strict_summary(summary, audit_id=BASELINE_ID, report_sha=CAPTURE_REPORT)
                _need(complete["counts"]["projected_complete_parents"] == 0
                    and complete["counts"]["grammar_quarantined_parents"] == 64
                    and complete["counts"]["quarantined_filings"] == 83_657
                    and complete["projection_refusal_counts"]["sec_document_envelope_refused"] == 64,
                    "unchanged_original_body_baseline_required")
            else:
                _need(type(complete.get("counts")) is dict and set(complete["counts"]) == original._COUNT_KEYS
                    and all(type(value) is int and value >= 0 for value in complete["counts"].values())
                    and complete["counts"]["projected_complete_parents"] == complete["counts"]["corroborated_noncanonical_filings"] == 0
                    and complete["counts"]["grammar_quarantined_parents"] == complete["counts"]["retained_parent_bodies"]
                    == complete["projection_refusal_counts"]["sec_document_envelope_refused"]
                    and complete["counts"]["quarantined_filings"] == complete["counts"]["source_filings"],
                    "invented_original_body_baseline_partition_refused")
            if not fixture_only:
                _need(complete["current_execution_identity"]["head"] == BASELINE_HEAD
                    and complete["current_execution_identity"]["source_inventory_sha256"] == BASELINE_SOURCE_INVENTORY,
                    "actual_baseline_execution_lineage_refused")
            # The externally pinned old assessment contains metadata identity
            # only, not transaction/outcome values. Hash its entire ordered
            # immutable row roster to prevent equal-count population swaps.
            baseline_assessment = original.capture._json(raw["assessment.json"])
            preparation_context = {key: ledger.get(key) for key in _PREPARATION_LABEL_KEYS}
            preparation_context.update(_source_identity_inventory(baseline_assessment.get("rows")))
            _validate_preparation_context(preparation_context)
            _need(preparation_context["source_row_count"] == complete["counts"]["source_filings"],
                "original_baseline_source_population_refused")
            if not fixture_only:
                _need(preparation_context["parsed_snapshot_id"] == original.PARSED_ID,
                    "actual_baseline_parsed_snapshot_refused")
            self.metadata = {"audit_id": BASELINE_ID, "complete_sha256": expected_complete_sha256,
                "publication_pins": {name: {"sha256": digest, "size_bytes": size} for name,(digest,size) in leaf_pins.items()},
                "execution_head": complete["current_execution_identity"]["head"],
                "execution_source_inventory_sha256": complete["current_execution_identity"]["source_inventory_sha256"],
                "preparation_context": preparation_context,
                "capture_execution_context": _capture_context_from(complete),
                "original_body_quarantine_unchanged": True}
            _require_observed_lineage(complete, self.metadata)
            self.tree.recheck()
        except BaseException:self.tree.close();raise

    def recheck(self):self.tree.recheck()
    def close(self):self.tree.close()


def _strict_temp_fixture_root(root):
    """Fenced BEFORE any old helper or actual-root/tree custody interaction."""
    trusted = Path(tempfile.gettempdir()).resolve()
    _need(isinstance(root, Path) and root.is_absolute() and ".." not in root.parts
        and root != trusted and root.is_relative_to(trusted), "strict_temporary_fixture_descendant_required")
    _need(root.resolve() == root and root.resolve().is_relative_to(trusted),
        "fixture_symlink_or_case_alias_refused")


def _validate_preparation_context(context):
    _need(type(context) is dict and set(context) == _PREPARATION_KEYS
        and type(context["parsed_snapshot_id"]) is str
        and re.fullmatch(r"sec-insider-parsed-2006q1-[0-9a-f]{16}", context["parsed_snapshot_id"]),
        "strict_observed_preparation_context_required")
    _digest(context["parsed_lineage_sha256"]);_digest(context["census_quarter_sha256"])
    _digest(context["ordered_source_row_identity_sha256"])
    _need(type(context["source_row_count"]) is int and 0 < context["source_row_count"] <= 83_657,
        "observed_source_row_count_refused")
    _need(context["parsed_snapshot_id"].endswith(context["parsed_lineage_sha256"][:16]),
        "observed_preparation_snapshot_lineage_refused")
    return context


def _source_identity_inventory(rows):
    _need(type(rows) is list and 0 < len(rows) <= 83_657, "bounded_ordered_source_identity_rows_required")
    identities = []
    for ordinal,row in enumerate(rows, 1):
        _need(type(row) is dict and set(_SOURCE_ROW_KEYS) <= set(row)
            and type(row["source_record_ordinal"]) is int and row["source_record_ordinal"] == ordinal
            and row["period"] == "2006Q1" and row["form_type"] in original.capture.bootstrap.locators.FORMS
            and type(row["short_cik"]) is bool and type(row["accession_year_mismatch"]) is bool
            and all(type(row[key]) is str for key in _SOURCE_ROW_KEYS if key not in {"source_record_ordinal", "short_cik", "accession_year_mismatch"}),
            "typed_immutable_source_row_identity_required")
        identities.append({key: row[key] for key in _SOURCE_ROW_KEYS})
    _need(len({row["accession_number"] for row in identities}) == len(identities), "duplicate_source_roster_accession_refused")
    return {"source_row_count": len(identities), "ordered_source_row_identity_sha256": _sha(_raw(identities))}


def _capture_context_from(body):
    _need(type(body) is dict, "observed_capture_context_required")
    context = {key: body.get(key) for key in _CAPTURE_CONTEXT_KEYS}
    _need(context["capture_id"] == original.CAPTURE_ID
        and all(type(context[key]) is str and re.fullmatch(r"[0-9a-f]{40}", context[key])
            for key in ("capture_execution_head", "bootstrap_execution_head")), "typed_observed_capture_lineage_required")
    _digest(context["capture_execution_source_inventory_sha256"])
    return context


def _require_observed_lineage(body, baseline):
    expected = {**baseline["capture_execution_context"],
        "original_preparation_producer_commit": original.downstream.PRODUCER_COMMIT,
        "original_preparation_completion_sha256": original.downstream.EXPECTED_COMPLETION_SHA256,
        "original_preparation_assessment_sha256": original.downstream.EXPECTED_ASSESSMENT_SHA256}
    _need(_raw({key: body.get(key) for key in expected}) == _raw(expected),
        "observed_capture_or_original_preparation_lineage_differs")


def _loaded_capture_context(reservation, report):
    return _capture_context_from({"capture_id": original.CAPTURE_ID, "capture_execution_head": report["capture_execution_head"],
        "bootstrap_execution_head": report["bootstrap_execution_head"],
        "capture_execution_source_inventory_sha256": reservation["execution_identity"]["source_inventory_sha256"]})


def _fixed_source_identity(expected_head):
    _need(Path(__file__).resolve() == original.capture.bootstrap.custody.LANE_ROOT / SELF_PATH,
        "inactive_pem_runner_not_production_source")
    identity, frozen = original._fixed_source_identity(expected_head)
    _need({SELF_PATH, PURE_PATH, VIEW_PATH} <= set(identity["source_sha256"]), "committed_pem_source_closure_required")
    return identity, frozen


def _current_bytes(identity, frozen):
    _need({SELF_PATH, PURE_PATH, VIEW_PATH} <= set(identity["source_sha256"]), "worker_pem_source_closure_required")
    original._current_bytes(identity, frozen)


def _output_directory(audit_id, *, create):
    _need(type(audit_id) is str and _ID.fullmatch(audit_id), "pem_audit_id_refused")
    base = original.capture.bootstrap.custody.LANE_ROOT.joinpath(*OUTPUT_PARTS)
    if create:
        parent = original.capture.custody._Directory(base, create=True)
        try:
            _need(not parent.exists(audit_id), "fresh_pem_output_required")
            info = os.fstatvfs(parent.fd)
            _need(info.f_bavail * info.f_frsize >= MIN_FREE_BYTES + MAX_ASSESSMENT_BYTES + 3 * MAX_LEDGER_BYTES,
                "pem_disk_reserve_refused")
            os.mkdir(audit_id, 0o700, dir_fd=parent.fd);os.fsync(parent.fd)
        finally:parent.close()
    return original.capture.custody._Directory(base / audit_id)


def _reservation(audit_id, identity, frozen, report_sha, baseline):
    return {"schema": SCHEMA + "/reservation", "audit_id": audit_id, "fixture_only": False,
        "capture_id": original.CAPTURE_ID, "capture_report_sha256": report_sha, "frozen_original_baseline": baseline,
        "current_execution_identity": identity, "frozen_sources": frozen,
        "original_preparation_completion_sha256": original.downstream.EXPECTED_COMPLETION_SHA256,
        "original_preparation_assessment_sha256": original.downstream.EXPECTED_ASSESSMENT_SHA256,
        "source_only_bootstrap_sha256": _sha(SOURCE_ONLY_BOOTSTRAP.encode()),
        "source_view_profile": pure.pem.PROFILE, "evidence_epoch": pure.EVIDENCE_EPOCH, "authority": _authority()}


def _validate_counts(counts, *, actual):
    _need(type(actual) is bool and type(counts) is dict and set(counts) == _COUNT_KEYS
        and all(type(value) is int and value >= 0 for value in counts.values()), "strict_pem_counts_required")
    _need(counts["target_filings"] + counts["context_filings"] == counts["source_filings"]
        and counts["original_bodies_retained"] + counts["source_view_unavailable"] == counts["selected_parents"]
        and counts["exact_pem_source_views"] + counts["pem_profile_quarantined"] == counts["original_bodies_retained"]
        and counts["frozen_source_view_projections"] + counts["source_view_parser_quarantined"] == counts["exact_pem_source_views"]
        and counts["source_view_corroborated_noncanonical"] <= counts["frozen_source_view_projections"]
        and counts["source_view_corroborated_noncanonical"] + counts["quarantined_filings"] == counts["source_filings"]
        and counts["selected_parents"] <= 64 and counts["original_parent_bytes"] <= pure.v2.MAX_CORROBORATING_BYTES
        and (counts["original_parent_bytes"] > 0) is (counts["original_bodies_retained"] > 0)
        and counts["original_body_admitted"] == 0, "pem_population_partition_refused")
    if actual:
        _need((counts["source_filings"], counts["target_filings"], counts["context_filings"], counts["selected_parents"])
            == (83_657, 71_679, 11_978, 64), "actual_pem_population_required")


def _refusal_counts(payload):
    counts = {key: 0 for key in _REFUSALS}
    for row in payload["parent_qualification_ledger"]:
        if row["disposition"] in {"original_pem_profile_quarantined", "source_view_frozen_parser_quarantined"}:
            code = row["quarantine_code"]
            _need(type(code) is str and code in counts, "fixed_pem_refusal_code_required")
            counts[code] += 1
    _need(sum(counts.values()) == payload["counts"]["pem_profile_quarantined"]
        + payload["counts"]["source_view_parser_quarantined"], "pem_refusal_partition_refused")
    return counts


def _validate_assessment(payload, *, fixture_only, preparation_context):
    """Recount real rows and every selected parent, not reported sum-only totals."""
    _need(type(fixture_only) is bool and type(payload) is dict and payload.get("schema") == pure.SCHEMA
        and payload.get("evidence_epoch") == pure.EVIDENCE_EPOCH and payload.get("fixture_only") is fixture_only
        and payload.get("period") == "2006Q1"
        and payload.get("source_identity_kind") == "original_raw_body_to_exact_view_to_frozen_projection_bridge"
        and payload.get("v2_source_view_assessment_kind") == pure.v2.IDENTITY_V2_VERSION
        and payload.get("source_view_profile") == pure.pem.PROFILE and payload.get("capture_report_sha256") == CAPTURE_REPORT
        and _raw(payload.get("authority")) == _raw(_authority())
        and payload.get("original_capture_header_quarantines_unchanged") is True
        and payload.get("v2_contract_alone_admits_original_whole_bodies") is False
        and payload.get("whole_original_parent_identity_sha256") is None and payload.get("whole_quarter_identity_sha256") is None,
        "strict_pem_assessment_context_required")
    _validate_preparation_context(preparation_context)
    _need({key: payload.get(key) for key in _PREPARATION_LABEL_KEYS}
        == {key: preparation_context[key] for key in _PREPARATION_LABEL_KEYS},
        "observed_preparation_identity_differs")
    counts = payload["counts"];_validate_counts(counts, actual=not fixture_only)
    rows, ledger, inventory = payload.get("rows"), payload.get("parent_qualification_ledger"), payload.get("source_view_inventory")
    _need(type(rows) is list and type(ledger) is list and type(inventory) is dict
        and payload.get("rows_sha256") == _sha(_raw(rows))
        and payload.get("parent_qualification_ledger_sha256") == _sha(_raw(ledger))
        and payload.get("source_view_inventory_sha256") == _sha(_raw(inventory)), "pem_assessment_inventory_digest_refused")
    _need(_source_identity_inventory(rows) == {key: preparation_context[key]
        for key in ("source_row_count", "ordered_source_row_identity_sha256")}, "observed_full_source_row_identity_differs")
    allowed = {"quarantined", "source_view_corroborated_noncanonical"}
    _need(all(type(row) is dict and row.get("disposition") in allowed and row.get("whole_original_parent_admitted") is False
        and row.get("form_type") in original.capture.bootstrap.locators.FORMS for row in rows), "strict_pem_row_dispositions_required")
    forms = {form: sum(row["form_type"] == form for row in rows) for form in original.capture.bootstrap.locators.FORMS}
    _need(type(payload.get("form_counts")) is dict and set(payload["form_counts"]) == set(forms)
        and all(type(value) is int for value in payload["form_counts"].values())
        and payload["form_counts"] == forms, "measured_pem_form_counts_differ")
    if not fixture_only:
        _need(forms == {"3": 5694, "3/A": 534, "4": 68520, "4/A": 3159, "5": 5539, "5/A": 211},
            "actual_six_form_counts_required")
    identities = [(row.get("accession_number"), row.get("source_record_ordinal")) for row in rows]
    _need(all(type(accession) is str and type(ordinal) is int and ordinal > 0 for accession,ordinal in identities)
        and len(set(identities)) == len(rows) and [ordinal for _,ordinal in identities] == list(range(1, len(rows)+1)),
        "pem_source_row_identity_inventory_refused")
    allowed_parents = {"source_view_unavailable", "original_pem_profile_quarantined",
        "source_view_frozen_parser_quarantined", "source_view_projected_noncanonical"}
    _need(all(type(row) is dict and type(row.get("prefix_ordinal")) is int and row["prefix_ordinal"] == ordinal
        and row.get("disposition") in allowed_parents and row.get("original_capture_header_identity_bound") is False
        and row.get("original_capture_header_quarantine_preserved") is True for ordinal,row in enumerate(ledger)),
        "strict_pem_parent_ledger_required")
    parents = {row["accession_number"]: row for row in ledger}
    _need(len(parents) == len(ledger) and set(parents) <= {accession for accession,_ in identities},
        "pem_parent_ledger_population_refused")
    bridges = []
    for row in ledger:
        raw, view, bridge = row["original_raw_parent"], row["source_view"], row["projection_bridge"]
        if raw is not None:
            _need(type(raw) is dict and set(raw) == {"sha256", "size_bytes"} and type(raw["size_bytes"]) is int
                and 0 < raw["size_bytes"] <= pure.pem.MAX_ORIGINAL_BODY_BYTES, "strict_original_body_metadata_required")
            _digest(raw["sha256"])
        if view is not None:
            _need(type(view) is dict and view.get("original_raw_parent") == raw and view.get("profile") == pure.pem.PROFILE
                and view.get("roles_reordered") is False and view.get("sgml_or_xml_normalized") is False
                and view.get("original_body_unchanged") is True and _raw(view.get("authority")) == _raw(pure.pem._authority()),
                "unchanged_original_to_view_metadata_required")
            derived = view["derived_sec_document_source_view"]
            _digest(derived["sha256"])
            _need(all(type(derived.get(key)) is int for key in ("size_bytes", "source_offset_bytes", "source_end_offset_exclusive_bytes"))
                and derived["source_offset_bytes"] == pure.pem.PREFIX_BYTES
                and derived["source_end_offset_exclusive_bytes"] == raw["size_bytes"] - pure.pem.SUFFIX_BYTES
                and derived["size_bytes"] == raw["size_bytes"] - pure.pem.PREFIX_BYTES - pure.pem.SUFFIX_BYTES
                and derived["size_bytes"] > 0 and derived["sha256"] != raw["sha256"], "original_view_hash_or_span_conflation_refused")
        if bridge is not None:
            _need(type(bridge) is dict and view is not None and bridge.get("original_raw_parent") == raw
                and bridge.get("derived_sec_document_source_view") == view["derived_sec_document_source_view"]
                and bridge.get("frozen_source_view_projection", {}).get("source_view_parent_sha256")
                    == view["derived_sec_document_source_view"]["sha256"]
                and _raw(bridge.get("authority")) == _raw(_authority()), "genuine_projection_metadata_bridge_required")
            bridges.append(bridge)
        expected_presence = {"source_view_unavailable": (False, False, False),
            "original_pem_profile_quarantined": (True, False, False),
            "source_view_frozen_parser_quarantined": (True, True, False), "source_view_projected_noncanonical": (True, True, True)}
        _need((raw is not None, view is not None, bridge is not None) == expected_presence[row["disposition"]],
            "parent_disposition_metadata_presence_refused")
    for row in rows:
        parent = parents.get(row["accession_number"])
        expected_custody = None if parent is None else {"original_raw_parent": parent["original_raw_parent"],
            "original_capture_result_sha256": parent["original_capture_result_sha256"],
            "original_capture_header_identity_bound": False, "original_capture_header_quarantine_preserved": True}
        expected_view = None if parent is None else {"disposition": parent["disposition"], "quarantine_code": parent["quarantine_code"],
            "source_view": parent["source_view"], "projection_bridge": parent["projection_bridge"]}
        _need(_raw(row.get("original_parent_custody")) == _raw(expected_custody)
            and _raw(row.get("source_view_qualification")) == _raw(expected_view)
            and (parent is None or row["source_record_ordinal"] == parent["source_record_ordinal"]),
            "row_original_custody_or_source_view_copy_differs")
        if row["disposition"] == "source_view_corroborated_noncanonical":
            _need(row["form_type"] in {"4", "4/A"} and row.get("v2_inner_assessment_disposition") == "corroborated_noncanonical"
                and row.get("corroboration_identity_kind") == "derived_view_not_original_complete_parent"
                and parent is not None and parent["projection_bridge"] is not None
                and row.get("corroboration", {}).get("parent_sha256")
                    == parent["source_view"]["derived_sec_document_source_view"]["sha256"], "source_view_corroborated_row_bridge_refused")
        else:_need(row.get("v2_inner_assessment_disposition") == "quarantined", "quarantined_inner_disposition_required")
    measured = {"source_filings": len(rows), "target_filings": forms["4"] + forms["4/A"],
        "context_filings": sum(forms[form] for form in ("3", "3/A", "5", "5/A")), "selected_parents": len(ledger),
        "original_bodies_retained": sum(row["original_raw_parent"] is not None for row in ledger),
        "exact_pem_source_views": sum(row["source_view"] is not None for row in ledger), "frozen_source_view_projections": len(bridges),
        "pem_profile_quarantined": sum(row["disposition"] == "original_pem_profile_quarantined" for row in ledger),
        "source_view_parser_quarantined": sum(row["disposition"] == "source_view_frozen_parser_quarantined" for row in ledger),
        "source_view_unavailable": sum(row["disposition"] == "source_view_unavailable" for row in ledger),
        "source_view_corroborated_noncanonical": sum(row["disposition"] == "source_view_corroborated_noncanonical" for row in rows),
        "quarantined_filings": sum(row["disposition"] == "quarantined" for row in rows),
        "original_parent_bytes": sum(row["original_raw_parent"]["size_bytes"] for row in ledger if row["original_raw_parent"] is not None),
        "original_body_admitted": 0}
    _need(counts == measured, "measured_pem_rows_or_ledger_counts_differ")
    _need(inventory.get("schema") == pure.SCHEMA + "/source-view-inventory"
        and inventory.get("evidence_epoch") == pure.EVIDENCE_EPOCH and inventory.get("rows") == bridges
        and type(inventory.get("parent_count")) is int and inventory["parent_count"] == len(bridges)
        and type(inventory.get("original_parent_bytes")) is int and inventory["original_parent_bytes"]
            == sum(row["original_raw_parent"]["size_bytes"] for row in bridges)
        and type(inventory.get("derived_source_view_bytes")) is int and inventory["derived_source_view_bytes"]
            == sum(row["derived_sec_document_source_view"]["size_bytes"] for row in bridges)
        and inventory.get("ordered_bridges_sha256") == _sha(_raw(bridges))
        and inventory.get("whole_original_parent_admission") is False and _raw(inventory.get("authority")) == _raw(_authority()),
        "measured_source_view_inventory_differs")
    _refusal_counts(payload)
    return payload


def _ledger_payload(payload, baseline):
    return {"schema": SCHEMA + "/parent-ledger", "evidence_epoch": pure.EVIDENCE_EPOCH,
        "counts": payload["counts"], "refusal_counts": _refusal_counts(payload),
        "parent_qualification_ledger": payload["parent_qualification_ledger"],
        "parent_qualification_ledger_sha256": payload["parent_qualification_ledger_sha256"],
        "capture_report_sha256": payload["capture_report_sha256"], "frozen_original_baseline": baseline,
        "original_capture_header_quarantines_unchanged": True, "authority": _authority()}


def _strict_summary(body, *, audit_id, report_sha, baseline_sha):
    keys = {"audit_id", "fixture_only", "complete_sha256", "assessment_sha256", "parent_ledger_sha256",
        "source_view_inventory_sha256", "capture_report_sha256", "baseline_complete_sha256", "counts", "refusal_counts", "authority"}
    _need(type(body) is dict and set(body) == keys and body["audit_id"] == audit_id and body["fixture_only"] is False
        and body["capture_report_sha256"] == report_sha and body["baseline_complete_sha256"] == baseline_sha
        and _raw(body["authority"]) == _raw(_authority()), "strict_pem_worker_summary_required")
    _validate_counts(body["counts"], actual=True)
    reasons = body["refusal_counts"]
    _need(type(reasons) is dict and set(reasons) == _REFUSALS
        and all(type(value) is int and value >= 0 for value in reasons.values())
        and sum(reasons.values()) == body["counts"]["pem_profile_quarantined"] + body["counts"]["source_view_parser_quarantined"],
        "strict_pem_refusal_summary_required")
    for key in keys:
        if key.endswith("sha256"):_digest(body[key])
    return body


def _source_execution_context(rows, identity):
    context = original._source_execution_context(rows, identity)
    _need({SELF_PATH, PURE_PATH, VIEW_PATH} <= {row["path"] for row in rows}, "executed_pem_sources_required")
    return context


def _publish_assessment(output, result, *, audit_id, reservation_raw, identity, frozen, baseline,
        capture_reservation, capture_report, executed_sources, bootstrap_source, fixture_only=False):
    _need(type(fixture_only) is bool and type(result) is pure.PemQuarterReassessment, "genuine_pem_result_required")
    _need(_raw(_loaded_capture_context(capture_reservation, capture_report)) == _raw(baseline["capture_execution_context"]),
        "loaded_capture_differs_from_authenticated_baseline")
    payload = _validate_assessment(result.to_payload(), fixture_only=fixture_only,
        preparation_context=baseline["preparation_context"])
    _need(payload["fixture_only"] is fixture_only and _raw(payload["authority"]) == _raw(_authority())
        and payload["original_capture_header_quarantines_unchanged"] is True
        and payload["v2_contract_alone_admits_original_whole_bodies"] is False,
        "pem_result_authority_or_original_lineage_refused")
    encoded = result.canonical_bytes();assessment_sha = output.publish("assessment.json", encoded, cap=MAX_ASSESSMENT_BYTES)
    ledger = _ledger_payload(payload, baseline)
    ledger_raw, inventory_raw = _raw(ledger), _raw(payload["source_view_inventory"])
    ledger_sha = output.publish("parent-ledger.json", ledger_raw, cap=MAX_LEDGER_BYTES)
    inventory_sha = output.publish("source-view-inventory.json", inventory_raw, cap=MAX_LEDGER_BYTES)
    _need(inventory_sha == payload["source_view_inventory_sha256"], "published_view_inventory_digest_differs")
    complete = {"schema": SCHEMA + "/complete", "audit_id": audit_id, "fixture_only": fixture_only,
        "observed_at_utc": original.capture.custody._utc(), "current_execution_identity": identity,
        "frozen_sources": frozen, "frozen_original_baseline": baseline, "reservation_sha256": _sha(reservation_raw),
        "capture_id": original.CAPTURE_ID, "capture_report_sha256": payload["capture_report_sha256"],
        "capture_execution_head": capture_report["capture_execution_head"],
        "capture_execution_source_inventory_sha256": capture_reservation["execution_identity"]["source_inventory_sha256"],
        "bootstrap_execution_head": capture_report["bootstrap_execution_head"],
        "original_preparation_producer_commit": original.downstream.PRODUCER_COMMIT,
        "original_preparation_completion_sha256": original.downstream.EXPECTED_COMPLETION_SHA256,
        "original_preparation_assessment_sha256": original.downstream.EXPECTED_ASSESSMENT_SHA256,
        "assessment_sha256": assessment_sha, "assessment_bytes": len(encoded),
        "parent_ledger_sha256": ledger_sha, "parent_ledger_bytes": len(ledger_raw),
        "source_view_inventory_sha256": inventory_sha, "source_view_inventory_bytes": len(inventory_raw),
        "counts": payload["counts"], "refusal_counts": ledger["refusal_counts"],
        "source_execution": _source_execution_context([bootstrap_source, *executed_sources], identity),
        "source_only_bootstrap_sha256": _sha(SOURCE_ONLY_BOOTSTRAP.encode()),
        "evidence_epoch": pure.EVIDENCE_EPOCH, "source_view_profile": pure.pem.PROFILE,
        "whole_original_parent_identity_sha256": None, "whole_quarter_identity_sha256": None,
        "authority": _authority()}
    # Completion is the last write. The caller rechecks ALL source inputs just
    # before entering this publication phase and again after its readback.
    complete_sha = output.publish("complete.json", _raw(complete), cap=MAX_CONTROL_BYTES)
    summary = {"audit_id": audit_id, "fixture_only": fixture_only, "complete_sha256": complete_sha,
        "assessment_sha256": assessment_sha, "parent_ledger_sha256": ledger_sha, "source_view_inventory_sha256": inventory_sha,
        "capture_report_sha256": payload["capture_report_sha256"], "baseline_complete_sha256": baseline["complete_sha256"],
        "counts": payload["counts"], "refusal_counts": ledger["refusal_counts"], "authority": _authority()}
    _verify_publication(output, summary, identity=identity, frozen=frozen, baseline=baseline, fixture_only=fixture_only)
    return summary


def _verify_publication(output, summary, *, identity, frozen, baseline, fixture_only=False):
    _need(type(fixture_only) is bool and summary.get("fixture_only") is fixture_only, "publication_mode_refused")
    if fixture_only:_validate_counts(summary["counts"], actual=False)
    else:_strict_summary(summary, audit_id=summary["audit_id"], report_sha=CAPTURE_REPORT, baseline_sha=BASELINE_COMPLETE)
    _need(set(os.listdir(output.fd)) == _FILES, "exact_pem_publication_inventory_required")
    complete_raw = output.read("complete.json", cap=MAX_CONTROL_BYTES)
    _need(_sha(complete_raw) == summary["complete_sha256"], "complete_publication_digest_differs")
    complete = original.capture._json(complete_raw)
    _require_observed_lineage(complete, baseline)
    _need(complete.get("schema") == SCHEMA + "/complete" and complete.get("audit_id") == summary["audit_id"]
        and complete.get("fixture_only") is fixture_only and _raw(complete.get("current_execution_identity")) == _raw(identity)
        and _raw(complete.get("frozen_sources")) == _raw(frozen) and _raw(complete.get("frozen_original_baseline")) == _raw(baseline)
        and _raw(complete.get("authority")) == _raw(_authority())
        and _raw(complete.get("counts")) == _raw(summary["counts"])
        and _raw(complete.get("refusal_counts")) == _raw(summary["refusal_counts"])
        and complete.get("source_only_bootstrap_sha256") == _sha(SOURCE_ONLY_BOOTSTRAP.encode())
        and complete.get("evidence_epoch") == pure.EVIDENCE_EPOCH and complete.get("source_view_profile") == pure.pem.PROFILE
        and complete.get("whole_original_parent_identity_sha256") is None and complete.get("whole_quarter_identity_sha256") is None,
        "complete_publication_context_differs")
    publications = {}
    for name, digest_key, size_key, cap in (("assessment.json", "assessment_sha256", "assessment_bytes", MAX_ASSESSMENT_BYTES),
            ("parent-ledger.json", "parent_ledger_sha256", "parent_ledger_bytes", MAX_LEDGER_BYTES),
            ("source-view-inventory.json", "source_view_inventory_sha256", "source_view_inventory_bytes", MAX_LEDGER_BYTES)):
        raw = output.read(name, cap=cap)
        _need(_sha(raw) == complete.get(digest_key) == summary.get(digest_key)
            and type(complete.get(size_key)) is int and complete[size_key] == len(raw), "publication_data_digest_or_size_differs")
        publications[name] = raw
    assessment = _validate_assessment(original.capture._json(publications["assessment.json"]), fixture_only=fixture_only,
        preparation_context=baseline["preparation_context"])
    _need(_raw(assessment["counts"]) == _raw(summary["counts"])
        and _raw(_refusal_counts(assessment)) == _raw(summary["refusal_counts"])
        and publications["parent-ledger.json"] == _raw(_ledger_payload(assessment, baseline))
        and publications["source-view-inventory.json"] == _raw(assessment["source_view_inventory"]),
        "publication_measured_rows_or_inventory_differ")
    reservation_raw = output.read("reservation.json", cap=MAX_CONTROL_BYTES)
    _need(_sha(reservation_raw) == complete.get("reservation_sha256"), "publication_reservation_digest_differs")
    _need(original.capture._json(reservation_raw) == _reservation(summary["audit_id"], identity, frozen,
        summary["capture_report_sha256"], baseline), "publication_reservation_context_differs")
    _need(complete.get("capture_report_sha256") == summary["capture_report_sha256"]
        and baseline["complete_sha256"] == summary["baseline_complete_sha256"], "publication_external_source_pins_differ")
    source_execution = _source_execution_context(complete.get("source_execution", {}).get("executed_sources"), identity)
    _need(_raw(complete.get("source_execution")) == _raw(source_execution), "typed_executed_source_metadata_differs")
    output.check()
    return complete


def _worker(audit_id, *, expected_head, expected_capture_report_sha256, expected_baseline_complete_sha256,
        parent_context, executed_sources=None, bootstrap_source=None):
    _need(Path(__file__).resolve() == original.capture.bootstrap.custody.LANE_ROOT / SELF_PATH
        and Path.cwd() == original.capture.bootstrap.custody.LANE_ROOT, "inactive_pem_runner_not_production_source")
    _need(type(parent_context) is dict and set(parent_context) == {"identity", "frozen_sources", "baseline"}
        and type(executed_sources) is list and type(bootstrap_source) is dict, "captured_pem_worker_context_required")
    identity, frozen = parent_context["identity"], parent_context["frozen_sources"]
    _at_phase("worker_preflight", original.capture.bootstrap._required_identity, identity, expected_head)
    _at_phase("worker_preflight", _current_bytes, identity, frozen)
    _need(expected_capture_report_sha256 == CAPTURE_REPORT and expected_baseline_complete_sha256 == BASELINE_COMPLETE,
        "fixed_actual_capture_and_baseline_pins_required")
    output = _at_phase("worker_output_reservation", _output_directory, audit_id, create=False)
    baseline = inputs = raw = parents = None
    try:
        _need(set(os.listdir(output.fd)) == {"reservation.json"}, "fresh_reserved_pem_output_required")
        reservation_raw = output.read("reservation.json", cap=MAX_CONTROL_BYTES)
        _need(original.capture._json(reservation_raw) == _reservation(audit_id, identity, frozen,
            expected_capture_report_sha256, parent_context["baseline"]), "worker_pem_reservation_differs")
        _at_phase("worker_isolation", original._prove_worker_isolation, output.path)
        sys.addaudithook(original.isolation._audit_event)
        baseline = _at_phase("worker_baseline", _PinnedBaseline, expected_baseline_complete_sha256)
        _need(baseline.metadata == parent_context["baseline"], "parent_worker_baseline_context_differs")
        inputs, raw, snapshot, census = _at_phase("worker_preparation", original._load_original_preparation)
        measured_preparation = {"parsed_snapshot_id": snapshot.identity.snapshot_id,
            "parsed_lineage_sha256": snapshot.identity.lineage_hash,
            "census_quarter_sha256": original.hash_payload(census.to_payload())}
        measured_preparation.update(_source_identity_inventory(
            original.identity_v2.assess_ib1c_v2_quarter_identity(snapshot, census, ()).to_payload()["rows"]))
        _need(_raw(measured_preparation) == _raw(baseline.metadata["preparation_context"]),
            "worker_preparation_differs_from_authenticated_original_baseline")
        parents, descriptors, capture_reservation, capture_report = _at_phase("worker_capture", original._load_sealed_capture,
            expected_capture_report_sha256)
        _need(_raw(_loaded_capture_context(capture_reservation, capture_report)) == _raw(baseline.metadata["capture_execution_context"]),
            "worker_capture_differs_from_authenticated_baseline")
        result = _at_phase("worker_composition", pure.assess_2006q1_pem_source_view_identity, snapshot, census, descriptors,
            expected_capture_report_sha256=expected_capture_report_sha256, fixture_only=False)
        repeated = _at_phase("worker_replay", pure.assess_2006q1_pem_source_view_identity, snapshot, census, descriptors,
            expected_capture_report_sha256=expected_capture_report_sha256, fixture_only=False)
        _need(result.canonical_bytes() == repeated.canonical_bytes(), "complete_pem_reassessment_reexecution_differs")
        for held in (baseline, inputs, raw, parents):held.recheck()
        _current_bytes(identity, frozen)
        summary = _at_phase("worker_publication", _publish_assessment, output, result, audit_id=audit_id,
            reservation_raw=reservation_raw, identity=identity, frozen=frozen, baseline=baseline.metadata,
            capture_reservation=capture_reservation, capture_report=capture_report,
            executed_sources=executed_sources, bootstrap_source=bootstrap_source)
        for held in (baseline, inputs, raw, parents):held.recheck()
        _current_bytes(identity, frozen)
        return _strict_summary(summary, audit_id=audit_id, report_sha=expected_capture_report_sha256,
            baseline_sha=expected_baseline_complete_sha256)
    finally:
        _close_all((parents, raw, inputs, baseline, output), phase="worker_cleanup")


def run_observed_reassessment(audit_id, *, expected_head, expected_capture_report_sha256, expected_baseline_complete_sha256):
    identity, frozen = _at_phase("parent_preflight", _fixed_source_identity, expected_head)
    _need(expected_capture_report_sha256 == CAPTURE_REPORT and expected_baseline_complete_sha256 == BASELINE_COMPLETE,
        "fixed_actual_capture_and_baseline_pins_required")
    _at_phase("parent_original_sources", original.capture._verify_original_committed_sources, original.CAPTURE_ID, expected_capture_report_sha256)
    # External observed baseline must exist and verify BEFORE a fresh output
    # reservation, not a receipt invented by the source-view worker itself.
    baseline = _at_phase("parent_baseline", _PinnedBaseline, expected_baseline_complete_sha256)
    output = None
    try:
        output = _at_phase("parent_output_reservation", _output_directory, audit_id, create=True)
        reservation = _reservation(audit_id, identity, frozen, expected_capture_report_sha256, baseline.metadata)
        _at_phase("parent_output_reservation", output.publish, "reservation.json", _raw(reservation), cap=MAX_CONTROL_BYTES)
        source_rows = []
        for name,digest in sorted(identity["source_sha256"].items()):
            raw = _at_phase("parent_captured_sources", original.isolation._read_source, name)
            _need(_sha(raw) == digest, "parent_captured_pem_source_changed")
            source_rows.append({"path": name, "sha256": digest, "source_b64": base64.b64encode(raw).decode("ascii")})
        envelope = _raw({"sources": source_rows, "parent_context": {"identity": identity, "frozen_sources": frozen, "baseline": baseline.metadata},
            "audit_id": audit_id, "expected_head": expected_head, "report_sha256": expected_capture_report_sha256,
            "baseline_sha256": expected_baseline_complete_sha256})
        _need(len(envelope) <= MAX_CONTEXT_BYTES, "captured_pem_context_bound_refused")
        baseline.recheck()
        _need(_fixed_source_identity(expected_head) == (identity, frozen), "parent_source_changed_before_worker")
        command = ["/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "/usr/bin/sandbox-exec", "-p",
            original.isolation._worker_policy(output.path), sys.executable, "-I", "-S", "-B", "-c", SOURCE_ONLY_BOOTSTRAP]
        child = _at_phase("parent_worker_launch", subprocess.run, command, cwd=original.capture.bootstrap.custody.LANE_ROOT,
            input=envelope, capture_output=True, check=False, timeout=1800)
        baseline.recheck()
        _need(_fixed_source_identity(expected_head) == (identity, frozen), "parent_source_changed_after_worker")
        _need(type(child.stdout) is bytes and type(child.returncode) is int and child.stderr == b""
            and 0 < len(child.stdout) <= MAX_CONTROL_BYTES and child.stdout.endswith(b"\n") and not child.stdout.endswith(b"\n\n"),
            "isolated_pem_result_wire_refused")
        wire = original.capture._json(child.stdout.removesuffix(b"\n"))
        if child.returncode != 0:
            diagnostic = _strict_failure(wire)
            _need(diagnostic["failure_phase"].startswith("worker_"), "nonworker_child_diagnostic_refused")
            output.publish("worker-failure.json", _raw({"schema": SCHEMA + "/worker-failure", "audit_id": audit_id,
                "diagnostic": diagnostic, "authority": _authority()}), cap=MAX_CONTROL_BYTES)
            raise ReportedWorkerError(diagnostic)
        result = _at_phase("parent_worker_result", _strict_summary, wire, audit_id=audit_id,
            report_sha=expected_capture_report_sha256, baseline_sha=expected_baseline_complete_sha256)
        _at_phase("parent_publication_verification", _verify_publication, output, result,
            identity=identity, frozen=frozen, baseline=baseline.metadata)
        baseline.recheck();_need(_fixed_source_identity(expected_head) == (identity, frozen), "parent_source_changed_at_publication")
        return result
    finally:
        # The parent had no cleanup phase label; untagged failures keep the fallback phase.
        _close_all((output, baseline), phase=None)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-id", required=True);parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-capture-report-sha256", required=True)
    parser.add_argument("--expected-baseline-complete-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        result = run_observed_reassessment(args.audit_id, expected_head=args.expected_head,
            expected_capture_report_sha256=args.expected_capture_report_sha256,
            expected_baseline_complete_sha256=args.expected_baseline_complete_sha256)
        print(_raw(result).decode());return 0
    except (ValueError, OSError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        print(_raw(_failure_diagnostic(exc)).decode());return 2


if __name__ == "__main__":raise SystemExit(main())
