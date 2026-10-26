"""Registered prospective selector verification v2; no acquisition or IB1B publication.

This versioned coordinator deliberately snapshots the qualified predecessor.
It never mutates predecessor globals or resumes its failed output namespace.
Its original terminal failure and missing original trace remain preserved.

Only the fixed clean committed production image may operate on actual inputs.
The parent holds all 84 exact intake leaves and remains hash/control-only.
Its captured-source worker proves native network/fork/all-write denial before
opening input bytes, derives the full selection twice, and returns no row or
financial values. Explicit temporary fixtures cannot select an actual root.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

from research import insider_buying_sec_2006q1_parent_projection_v1 as original
from research import insider_buying_sec_2006q1_pem_reassessment_runner as view_front
from research import insider_buying_sharadar_reference_cohort_runner as held_io
from research import insider_buying_affected_quarter_selector_v1 as pure
from research import insider_buying_affected_quarter_selector_runner as previous

SCHEMA = "insider-retained-affected-quarter-selector-verification-v2"
SELF_PATH = "research/insider_buying_affected_quarter_selector_verification_v2.py"
PURE_PATH = "research/insider_buying_affected_quarter_selector_v1.py"
INPUT_PARTS = ("artifacts", "sec_insider", "raw")
_AUX_NAME = ".gitattributes"
_AUX_PIN = ("fb4e806a1f4a7ad3addbfb805a9ab1936138c2bb1222166044fb8d403d5ee62b",156)
OUTPUT_PARTS = ("artifacts", "insider_buying", "affected_quarter_selector_verification_v2")
MAX_SELECTION_BYTES = 1024 * 1024
MAX_CONTROL_BYTES = 1024 * 1024
MAX_CHILD_BYTES = 2 * 1024 * 1024
MAX_CONTEXT_BYTES = original.MAX_WORKER_CONTEXT_BYTES
MIN_FREE_BYTES = 4 * 1024**3
_ID = re.compile(r"ib-affected-quarter-selector-[a-z0-9-]{1,70}\Z")
_FILES = frozenset({"reservation.json", "selection.json", "complete.json"})
AUDIT_ID = "ib-affected-quarter-selector-ctime-verified-v2-20261021-once"
PREDECESSOR_AUDIT_ID = "ib-affected-quarter-selector-all6-retained-v1-20261014-once"
PREDECESSOR_PARTS = ("artifacts", "insider_buying", "affected_quarter_selector_v1")
PREDECESSOR_PINS = {
    "reservation.json": "08a11e4dea01408970ad5ab6df12a31b411ae12472fdf9a712195b01515fe8d8",
    "selection.json": "d1dd4e093d5505fac6373562bb24198c7ad6fc61ef7745912a40bff84528aaef",
    "complete.json": "ca0fb475cbb102505cc07bf33e7a67568919ecfc4687bee7b9475162c3045e57",
}
PREDECESSOR_BYTES = {"reservation.json": 27812, "selection.json": 91237, "complete.json": 39794}
REGISTRATION_RAW = json.dumps({
    "schema": SCHEMA + "/operation-registration",
    "audit_id": AUDIT_ID,
    "output_namespace": "/".join(OUTPUT_PARTS),
    "operation": "prospective_corrected_final_custody_verification_not_original_failure_reconstruction",
    "source_window": "2006Q1..2026Q2",
    "input_leaf_count": 84,
    "all_six_ownership_forms": True,
    "prior_counter_review_head": "725b81ceb9e8584aa1bebdcceb66ae66cef82aaf",
    "predecessor": {
        "audit_id": PREDECESSOR_AUDIT_ID,
        "output_namespace": "/".join(PREDECESSOR_PARTS),
        "terminal_status": "FAILED",
        "observed_exit_code": 2,
        "original_failure_phase": "parent_final_output_check",
        "original_precise_cause_established": False,
        "leaf_pins": {name: {"sha256": PREDECESSOR_PINS[name], "bytes": PREDECESSOR_BYTES[name]}
            for name in sorted(PREDECESSOR_PINS)},
    },
    "predecessor_promoted_or_rewritten": False,
    "new_provider_or_sec_or_qc_access": False,
    "backtesting_readiness_granted": False,
}, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
REGISTRATION_SHA256 = hashlib.sha256(REGISTRATION_RAW).hexdigest()
_PHASES = frozenset({"parent_preflight", "parent_inputs", "parent_source_capture", "parent_output_reservation",
    "parent_predecessor_hold", "parent_predecessor_recheck",
    "parent_before_worker_inputs", "parent_before_worker_sources", "parent_worker_launch", "parent_worker_result",
    "parent_after_worker_inputs", "parent_after_worker_sources", "parent_publication", "parent_final_output_hold",
    "parent_final_inputs", "parent_final_sources", "parent_final_output_check", "parent_cleanup",
    "worker_bootstrap_context", "worker_bootstrap_source_decode", "worker_bootstrap_import", "worker_execution",
    "worker_native_denial", "worker_current_sources", "worker_inputs", "worker_selection", "worker_input_recheck",
    "worker_rederivation", "worker_final_sources", "worker_cleanup"})
_DISPOSITION = "offline_affected_quarter_verification_refused_outputs_preserved"
# Section 194 (Claude review): lane refusal classes are named, not collapsed to ValueError.
_LANE_CLASS_NAMES = ("SharadarCohortRunnerError", "ArchiveAssessmentRunnerError", "PemReassessmentRunnerError",
    "EarlyParentProjectionError", "OriginalPreparationCustodyError", "AffectedQuarterSelectorError")
_CLASSES = frozenset({"AffectedQuarterSelectorRunnerError", "OSError", "ValueError", "TypeError", "KeyError",
    "SubprocessError", "other_refusal", *_LANE_CLASS_NAMES})

SOURCE_ONLY_BOOTSTRAP = r'''
import base64, errno, hashlib, json, sys, types
consumer = None
phase = "worker_bootstrap_context"
try:
    def need(value):
        if not value: raise ValueError("captured selector context refused")
    raw = sys.stdin.buffer.read(33554433)
    need(0 < len(raw) <= 33554432)
    envelope = json.loads(raw)
    need(type(envelope) is dict and set(envelope) == {"sources", "context", "audit_id", "expected_head"})
    rows = envelope["sources"]
    need(type(rows) is list)
    selected = [row for row in rows if row.get("path") == "research/insider_buying_affected_quarter_isolation.py"]
    need(len(selected) == 1)
    source = base64.b64decode(selected[0]["source_b64"], validate=True)
    need(hashlib.sha256(source).hexdigest() == selected[0]["sha256"])
    helper = types.ModuleType("_captured_affected_selector_imports")
    helper.__file__ = "/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying/research/insider_buying_affected_quarter_isolation.py"
    sys.modules[helper.__name__] = helper
    exec(compile(source, helper.__file__, "exec", dont_inherit=True), helper.__dict__)
    sys.modules["research.insider_buying_affected_quarter_isolation"] = helper
    phase = "worker_bootstrap_source_decode"
    sources = helper._decode_sources(rows)
    need({path: helper._sha(source) for path, source in sources} == envelope["context"]["identity"]["source_sha256"])
    finder = helper._SourceFinder(sources)
    sys.meta_path.insert(0, finder)
    phase = "worker_bootstrap_import"
    from research import insider_buying_affected_quarter_selector_verification_v2 as consumer
    phase = "worker_execution"
    result = consumer._worker(envelope["audit_id"], expected_head=envelope["expected_head"], context=envelope["context"],
        executed_sources=finder.executed, bootstrap_source={"path": "research/insider_buying_affected_quarter_isolation.py", "sha256": selected[0]["sha256"]})
    print(consumer._raw(result).decode())
except Exception as exc:
    if consumer is not None:
        body = consumer._failure_diagnostic(exc, phase)
    else:
        kinds = ((OSError,"OSError"),(ValueError,"ValueError"),(TypeError,"TypeError"),(KeyError,"KeyError"))
        category = next((name for kind,name in kinds if isinstance(exc,kind)), "other_refusal")
        number = exc.errno if isinstance(exc,OSError) else None
        if type(number) is not int or number not in errno.errorcode: number = None
        body = {"disposition":"offline_affected_quarter_verification_refused_outputs_preserved", "failure_phase":phase,
            "failure_class":category, "os_errno":number}
    print(json.dumps(body,sort_keys=True,separators=(",",":"),allow_nan=False))
    raise SystemExit(2)
'''


class AffectedQuarterSelectorRunnerError(ValueError): pass


class ReportedSelectorWorkerError(AffectedQuarterSelectorRunnerError):
    def __init__(self,diagnostic):
        self.diagnostic = _strict_failure(diagnostic)
        super().__init__("isolated_selector_worker_refused")


def _need(value, code):
    if not value: raise AffectedQuarterSelectorRunnerError(code)


def _raw(value): return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
def _sha(raw): return hashlib.sha256(raw).hexdigest()
def _authority(): return pure._authority()


def _registration():
    """Return a fresh copy; caller mutation cannot alter the committed bytes."""
    return json.loads(REGISTRATION_RAW)


def _registered_audit_id(audit_id):
    _need(type(audit_id) is str and audit_id == AUDIT_ID
        and _ID.fullmatch(audit_id) is not None, "exact_registered_verification_id_required")
    return audit_id


def _registration_fields():
    return {"operation_registration": _registration(), "operation_registration_sha256": REGISTRATION_SHA256}


class _Number(str):
    """Unknown JSON numeric tokens remain lexical, including refused fields."""


def _opaque_json(raw):
    def unique(pairs):
        body = {}
        for key,value in pairs:
            _need(key not in body,"duplicate_control_key_refused")
            body[key] = value
        return body
    def constant(_): raise AffectedQuarterSelectorRunnerError("nonfinite_control_token_refused")
    try: return json.loads(raw,object_pairs_hook=unique,parse_int=_Number,parse_float=_Number,parse_constant=constant)
    except (ValueError,UnicodeError,RecursionError):
        raise AffectedQuarterSelectorRunnerError("malformed_control_json_refused") from None


def _interpret_metadata_int(value):
    if type(value) is int:
        _need(0 <= value < 2**63,"bounded_metadata_integer_required")
        return value
    _need(type(value) is _Number and re.fullmatch(r"0|[1-9][0-9]{0,18}",value) is not None,
        "unsigned_lexical_metadata_integer_required")
    result = int(value)
    _need(result < 2**63,"bounded_metadata_integer_required")
    return result


def _counts_control(body,keys):
    _need(type(body) is dict and set(body) == set(keys),"exact_metadata_count_fields_required")
    return {key:_interpret_metadata_int(body[key]) for key in body}


def _known_context(value,expected):
    """Promote only explicit integer slots in an already authenticated context."""
    if type(expected) is dict:
        _need(type(value) is dict and set(value) == set(expected),"known_context_fields_differ")
        return {key:_known_context(value[key],item) for key,item in expected.items()}
    if type(expected) is list:
        _need(type(value) is list and len(value) == len(expected),"known_context_sequence_differs")
        return [_known_context(item,known) for item,known in zip(value,expected,strict=True)]
    if type(expected) is int:
        result = _interpret_metadata_int(value)
        _need(result == expected,"known_context_integer_differs")
        return result
    _need(type(value) is type(expected) and value == expected,"known_context_scalar_differs")
    return value


def _normalize_worker_control(body,context):
    keys = {"schema","audit_id","fixture_only","selection_b64","selection_sha256","selection_bytes","counts",
        "intake_context","source_execution","authority","effective_process_tree_network_denial",
        "effective_process_fork_denial","effective_all_write_denial","full_input_rederivations","operation_registration_sha256"}
    _need(type(body) is dict and set(body) == keys,"strict_worker_result_fields_required")
    result = dict(body)
    _known_context(body["operation_registration_sha256"], REGISTRATION_SHA256)
    result["counts"] = _counts_control(body["counts"],pure.COUNT_KEYS)
    result["selection_bytes"] = _interpret_metadata_int(body["selection_bytes"])
    result["full_input_rederivations"] = _interpret_metadata_int(body["full_input_rederivations"])
    result["intake_context"] = _known_context(body["intake_context"],context["intake_context"])
    result["authority"] = _known_context(body["authority"],_authority())
    execution = body["source_execution"]
    _need(type(execution) is dict and set(execution) == {"source_only_lane_imports","executed_sources",
        "executed_source_inventory_sha256","executed_source_count","full_historical_environment_reconstructed"},
        "strict_executed_source_fields_required")
    execution = dict(execution)
    execution["executed_source_count"] = _interpret_metadata_int(execution["executed_source_count"])
    result["source_execution"] = execution
    return result


def _selection_metadata(raw,*,context):
    body = _opaque_json(raw)
    fixed = {"schema":pure.SCHEMA,"profile":pure.PROFILE,"fixture_only":False,"source_window":"2006Q1..2026Q2",
        "retained_source_capture_commit":pure.census._CAPTURE_COMMIT,
        "schema_profile_sha256":pure.RETAINED_82Q_SCHEMA_PROFILE_SHA256,
        "selection_rule":"source_short_raw_ascii_cik_or_accession_year_different_from_source_filing_year_across_all_six_forms",
        "count_semantics":"sums_of_within_quarter_unique_source_accessions_not_cross_quarter_global_deduplication",
        "raw_source_cik_rewritten":False,"comparison_padding_does_not_change_original_bytes":True,
        "source_observation_clock_kind":"unverified_original_local_filesystem_last_write_not_retrieval_acceptance_publication_or_pit",
        "source_rows_or_ciks_or_names_published":False,"financial_values_interpreted_or_projected":False,
        "other_table_rows_parsed":False,"existing_table_integrity_utf8_crc_hash_checks_performed":True,
        "ib1b_snapshots_published":False,"whole_population_promotion_sha256":None}
    variable = {"intake_manifest_sha256","intake_manifest_bytes","census_sha256","header_preflight_sha256","quarters",
        "quarters_sha256","short_cik_periods","accession_year_mismatch_periods","affected_periods","counts",
        "source_form_counts","complete_parent_inputs","authority"}
    _need(type(body) is dict and set(body) == set(fixed)|variable,"exact_metadata_selection_fields_required")
    for key,value in fixed.items():_known_context(body[key],value)
    body["authority"] = _known_context(body["authority"],_authority())
    body["complete_parent_inputs"] = _known_context(body["complete_parent_inputs"],0)
    pins = context["intake_context"]
    for key,parent in (("intake_manifest_sha256","manifest_sha256"),("census_sha256","census_sha256"),
        ("header_preflight_sha256","header_preflight_sha256")):
        _known_context(body[key],pins[parent])
    body["intake_manifest_bytes"] = _known_context(body["intake_manifest_bytes"],pins["manifest_bytes"])
    body["counts"] = _counts_control(body["counts"],pure.COUNT_KEYS)
    body["source_form_counts"] = _counts_control(body["source_form_counts"],pure.FORMS)
    quarters = body["quarters"]
    _need(type(quarters) is list and len(quarters) == 82,"complete_ordered_metadata_quarters_required")
    scalars = {"zip_size_bytes","submission_member_bytes","submission_rows","form4_or_4a_rows","short_cik_rows",
        "short_cik_form4_or_4a_rows","accession_year_mismatch_rows","accession_year_mismatch_form4_or_4a_rows"}
    maps = {"source_form_counts","short_cik_form_counts","accession_year_mismatch_form_counts"}
    hashes = {"zip_sha256","submission_member_sha256","submission_header_line_sha256","schema_header_receipt_sha256","census_quarter_sha256"}
    other = {"period","local_filesystem_observation_unverified","filing_date_dialect","selected_affected"}
    rows = []
    for period,row in zip(pure._periods(),quarters,strict=True):
        _need(type(row) is dict and set(row) == scalars|maps|hashes|other,"exact_metadata_quarter_fields_required")
        row = dict(row)
        for key in hashes:pure._digest(row[key])
        for key in scalars:row[key] = _interpret_metadata_int(row[key])
        for key in maps:row[key] = _counts_control(row[key],pure.FORMS)
        _known_context(row["period"],period)
        pin = pins["leaf_pins"][period.lower()+"_form345.zip"]
        _known_context(row["zip_sha256"],pin["sha256"]);_known_context(row["zip_size_bytes"],pin["bytes"])
        _need(type(row["local_filesystem_observation_unverified"]) is str
            and pure.census._LOCAL_STAMP.fullmatch(row["local_filesystem_observation_unverified"]) is not None
            and row["filing_date_dialect"] in {"legacy","iso",None},"bounded_metadata_source_date_required")
        _known_context(row["local_filesystem_observation_unverified"],pins["quarter_observations"][period])
        forms = row["source_form_counts"]
        _need(sum(forms.values()) == row["submission_rows"] <= pure.MAX_ROWS_PER_TABLE
            and forms["4"]+forms["4/A"] == row["form4_or_4a_rows"],"metadata_quarter_form_partition_differs")
        for prefix,group in (("short_cik",row["short_cik_form_counts"]),("accession_year_mismatch",row["accession_year_mismatch_form_counts"])):
            _need(sum(group.values()) == row[prefix+"_rows"] and group["4"]+group["4/A"] == row[prefix+"_form4_or_4a_rows"]
                and all(group[form] <= forms[form] for form in pure.FORMS),"metadata_quarter_anomaly_partition_differs")
        _known_context(row["selected_affected"],row["short_cik_rows"]>0 or row["accession_year_mismatch_rows"]>0)
        rows.append(row)
    body["quarters"] = rows
    short = [row["period"] for row in rows if row["short_cik_rows"]]
    mismatches = [row["period"] for row in rows if row["accession_year_mismatch_rows"]]
    affected = [row["period"] for row in rows if row["selected_affected"]]
    for key,values in (("short_cik_periods",short),("accession_year_mismatch_periods",mismatches),("affected_periods",affected)):
        _known_context(body[key],values)
    counts = {"quarters_scanned":82,**{key:sum(row[key] for row in rows) for key in (
        "submission_rows","form4_or_4a_rows","short_cik_rows","short_cik_form4_or_4a_rows",
        "accession_year_mismatch_rows","accession_year_mismatch_form4_or_4a_rows")},"short_cik_quarters":len(short),
        "accession_year_mismatch_quarters":len(mismatches),"affected_quarters":len(affected),
        "overlap_anomaly_quarters":len(set(short)&set(mismatches))}
    forms = {form:sum(row["source_form_counts"][form] for row in rows) for form in pure.FORMS}
    _need(body["counts"] == counts and body["source_form_counts"] == forms
        and body["quarters_sha256"] == _sha(_raw(rows)) and _raw(body) == raw,"canonical_metadata_full_accounting_differs")
    return body


def _at_phase(phase, function, *args, **kwargs):
    _need(phase in _PHASES, "internal_selector_phase_refused")
    try: return function(*args, **kwargs)
    except Exception as exc:
        exc._selector_failure_phase = phase
        raise


def _failure_diagnostic(exc, fallback="parent_preflight"):
    if type(exc) is ReportedSelectorWorkerError:
        try:return _strict_failure(exc.diagnostic)
        except (ValueError,TypeError,KeyError,AttributeError):
            return {"disposition":_DISPOSITION,"failure_phase":"parent_worker_result",
                "failure_class":"AffectedQuarterSelectorRunnerError","os_errno":None}
    phase = getattr(exc, "_selector_failure_phase", None)
    if type(phase) is not str or phase not in _PHASES: phase = fallback if fallback in _PHASES else "parent_preflight"
    kinds = ((AffectedQuarterSelectorRunnerError,"AffectedQuarterSelectorRunnerError"),
        (held_io.SharadarCohortRunnerError,"SharadarCohortRunnerError"),
        (original.capture.bootstrap.custody.ArchiveAssessmentRunnerError,"ArchiveAssessmentRunnerError"),
        (view_front.PemReassessmentRunnerError,"PemReassessmentRunnerError"),
        (original.EarlyParentProjectionError,"EarlyParentProjectionError"),
        (original.OriginalPreparationCustodyError,"OriginalPreparationCustodyError"),
        (pure.AffectedQuarterSelectorError,"AffectedQuarterSelectorError"),(OSError,"OSError"),
        (ValueError,"ValueError"),(TypeError,"TypeError"),(KeyError,"KeyError"),(subprocess.SubprocessError,"SubprocessError"))
    category = next((name for kind,name in kinds if isinstance(exc,kind)), "other_refusal")
    number = exc.errno if isinstance(exc,OSError) else None
    if type(number) is not int or number not in errno.errorcode: number = None
    return {"disposition":_DISPOSITION,"failure_phase":phase,"failure_class":category,"os_errno":number}


def _strict_failure(body):
    _need(type(body) is dict and set(body) == {"disposition","failure_phase","failure_class","os_errno"}
        and body["disposition"] == _DISPOSITION and type(body["failure_phase"]) is str
        and body["failure_phase"] in _PHASES and type(body["failure_class"]) is str
        and body["failure_class"] in _CLASSES,"strict_selector_failure_fields_required")
    result = dict(body)
    if result["os_errno"] is not None:
        result["os_errno"] = _interpret_metadata_int(result["os_errno"])
        _need(result["os_errno"] in errno.errorcode,"strict_selector_failure_errno_required")
    return result


def _close_all(holds, *, phase):
    primary = sys.exc_info()[1]
    first = None
    for held in holds:
        if held is not None:
            try: held.close()
            except Exception as exc:
                if first is None: first = exc
    if primary is None and first is not None:
        first._selector_failure_phase = phase
        raise first


class _DirectoryDescriptor:
    def __init__(self,fd):self.fd = fd
    def close(self):os.close(self.fd)


def _close_tree(tree,*,phase):
    """Drain this front's known held leaves and ancestry, despite one failure.

    The shared helper's convenience close stops at its first failed stream or
    descriptor. Do not alter it: detach only this owned tree's inventory and
    attempt every known leaf and directory descriptor independently. An active
    primary remains primary, including when a close rethrows that same object.
    """
    if tree is None:return
    streams = tuple(stream for _,stream,_,_ in reversed(tree.handles))
    descriptors = tuple(_DirectoryDescriptor(fd) for fd in reversed(tree.chain.fds))
    tree.handles = [];tree.chain.fds = []
    _close_all((*streams,*descriptors),phase=phase)


def _fixture_fence(root):
    # The strict temp-only descendant fence precedes any constructor/callback.
    view_front._strict_temp_fixture_root(root)
    original.capture._fixture_root(root)


class _HeldIntake:
    """Hold/recheck full namespace and every manifest/ZIP leaf; no ZIP parsing."""
    def __init__(self, *, fixture_only=False, root=None, manifest_pin=None, census_pin=None, header_pin=None, auxiliary_pin=None):
        _need(type(fixture_only) is bool, "explicit_intake_mode_required")
        self.tree = None
        try:
            if fixture_only:
                _fixture_fence(root)
                _need(type(manifest_pin) is tuple and len(manifest_pin) == 2, "invented_manifest_pin_required")
                _need(type(auxiliary_pin) is tuple and len(auxiliary_pin) == 2,
                    "invented_opaque_auxiliary_pin_required")
                pure._digest(auxiliary_pin[0])
                _need(type(auxiliary_pin[1]) is int and 0 < auxiliary_pin[1] <= MAX_CONTROL_BYTES,
                    "bounded_auxiliary_control_required")
                for value in (manifest_pin[0], census_pin, header_pin): pure._digest(value)
                _need(type(manifest_pin[1]) is int and 0 < manifest_pin[1] <= pure.MAX_MANIFEST_BYTES, "bounded_manifest_size_required")
            else:
                _need(root is manifest_pin is census_pin is header_pin is auxiliary_pin is None, "fixed_actual_intake_required")
                root = original.capture.bootstrap.custody.LANE_ROOT.joinpath(*INPUT_PARTS)
                manifest_pin = (pure.census.RETAINED_ZIP_MANIFEST_SHA256, pure.census.RETAINED_ZIP_MANIFEST_SIZE_BYTES)
                census_pin = pure.headers.RETAINED_82Q_CENSUS_SHA256
                header_pin = pure.RETAINED_HEADER_SHA256
                auxiliary_pin = _AUX_PIN
            self.tree = held_io._HeldCapture(root, private=False)
            manifest = self.tree.open(pure.census._MANIFEST_NAME, manifest_pin[1])
            raw = manifest.read(manifest_pin[1] + 1)
            _need((len(raw), _sha(raw)) == (manifest_pin[1], manifest_pin[0]), "external_intake_manifest_differs")
            bindings = pure.census._manifest_bindings(raw)
            names = {pure.census._MANIFEST_NAME,_AUX_NAME,*(item.filename for item in bindings)}
            _need(len(bindings) == 82 and self.tree.names == names, "exact_84_leaf_intake_required")
            auxiliary = self.tree.open(_AUX_NAME,auxiliary_pin[1])
            _need(held_io._hash_stream(auxiliary,auxiliary_pin[1]) == auxiliary_pin,
                "opaque_auxiliary_control_differs")
            for item in bindings:
                stream = self.tree.open(item.filename, item.size_bytes)
                _need(held_io._hash_stream(stream,item.size_bytes) == (item.sha256,item.size_bytes), "bound_intake_zip_differs")
            self.bindings = bindings
            self.manifest_raw = raw
            self.context = {"fixture_only":fixture_only,"manifest_sha256":manifest_pin[0],"manifest_bytes":manifest_pin[1],
                "census_sha256":census_pin,"header_preflight_sha256":header_pin,
                "schema_profile_sha256":pure.RETAINED_82Q_SCHEMA_PROFILE_SHA256,"source_window":"2006Q1..2026Q2",
                "leaf_pins":{pure.census._MANIFEST_NAME:{"sha256":manifest_pin[0],"bytes":manifest_pin[1]},
                    _AUX_NAME:{"sha256":auxiliary_pin[0],"bytes":auxiliary_pin[1]},
                    **{item.filename:{"sha256":item.sha256,"bytes":item.size_bytes} for item in bindings}},
                "leaf_names":sorted(names),"leaf_count":84,"retained_source_capture_commit":pure.census._CAPTURE_COMMIT,
                "auxiliary_control_semantics":"opaque_current_committed_gitattributes_not_source_data",
                "quarter_observations":{item.period:item.local_last_write_utc for item in bindings}}
            self.recheck()
        except BaseException:
            _close_all((self,),phase="worker_cleanup"); raise

    def recheck(self):
        self.tree.check()
        for name,stream,version,cap in self.tree.handles:
            _need(stat.S_IMODE(version[2]) in {0o600,0o644}, "intake_leaf_readonly_owner_mode_required")
            pin = self.context["leaf_pins"][name]
            _need(held_io._hash_stream(stream,cap) == (pin["sha256"],pin["bytes"]), "held_intake_bytes_changed")
        self.tree.check()

    def source_arguments(self):
        by_name = {name:(stream,cap) for name,stream,_,cap in self.tree.handles}
        def quarter_stream():
            for binding in self.bindings:
                stream,cap = by_name[binding.filename]
                self.tree.check(); stream.seek(0)
                raw = stream.read(cap + 1)
                _need(len(raw) == cap and _sha(raw) == binding.sha256, "held_exact_quarter_bytes_changed")
                self.tree.check()
                yield pure.QuarterArchive(binding.period,raw)
                del raw
        return {"intake_manifest_raw":self.manifest_raw,"expected_manifest_sha256":self.context["manifest_sha256"],
            "quarter_inputs":quarter_stream(),"expected_census_sha256":self.context["census_sha256"],
            "expected_header_preflight_sha256":self.context["header_preflight_sha256"],"fixture_only":self.context["fixture_only"]}

    def close(self):
        _close_tree(self.tree,phase="worker_cleanup")


def _fixed_source_identity(expected_head):
    _need(Path(__file__).resolve() == original.capture.bootstrap.custody.LANE_ROOT / SELF_PATH, "inactive_selector_not_production_image")
    identity,frozen = original._fixed_source_identity(expected_head)
    _need({SELF_PATH,PURE_PATH} <= set(identity["source_sha256"]), "selector_committed_closure_required")
    auxiliary = original.capture.bootstrap.custody._git(original.capture.bootstrap.custody.LANE_ROOT,
        "show",expected_head+":"+"/".join((*INPUT_PARTS,_AUX_NAME)))
    _need((_sha(auxiliary),len(auxiliary)) == _AUX_PIN,"current_committed_auxiliary_control_differs")
    return identity,frozen


def _equal_source_identity(expected_head,identity,frozen):
    _need(_fixed_source_identity(expected_head) == (identity,frozen),"selector_current_source_identity_changed")


def _source_context(rows,identity):
    base = original._source_execution_context(rows,identity)
    _need({SELF_PATH,PURE_PATH} <= {row["path"] for row in rows}, "executed_selector_sources_required")
    return base


def _captured_sources(identity):
    sources = []
    for name,digest in sorted(identity["source_sha256"].items()):
        raw = original.isolation._read_source(name)
        _need(_sha(raw) == digest,"captured_selector_source_differs")
        sources.append({"path":name,"sha256":digest,"source_b64":base64.b64encode(raw).decode("ascii")})
    return sources


def _derive_twice(held):
    first = pure.select_affected_quarters(**held.source_arguments())
    held.recheck()
    second = pure.select_affected_quarters(**held.source_arguments())
    _need(first.canonical_bytes() == second.canonical_bytes(),"independent_full_selector_rederivation_differs")
    held.recheck()
    return first


def _held_for_context(context):
    held = _HeldIntake()
    try:
        _need(_raw(held.context) == _raw(context["intake_context"]),"worker_parent_intake_context_differs")
        return held
    except BaseException:
        _close_all((held,),phase="worker_cleanup")
        raise


def _captured_envelope(sources,context,audit_id,expected_head):
    envelope = _raw({"sources":sources,"context":context,"audit_id":audit_id,"expected_head":expected_head})
    _need(len(envelope) <= MAX_CONTEXT_BYTES,"captured_selector_context_bound_refused")
    return envelope


def _prove_allwrite_denial(output_path):
    original._prove_worker_isolation(output_path)
    try: probe = os.open(output_path / ".selector-allwrite-probe",os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    except OSError as exc: _need(exc.errno in {errno.EPERM,errno.EACCES}, "effective_inside_write_denial_not_observed")
    else: os.close(probe); raise AffectedQuarterSelectorRunnerError("effective_inside_write_denial_not_observed")


def _worker(audit_id, *, expected_head, context, executed_sources, bootstrap_source):
    _need(Path(__file__).resolve() == original.capture.bootstrap.custody.LANE_ROOT / SELF_PATH
        and Path.cwd() == original.capture.bootstrap.custody.LANE_ROOT,"inactive_selector_worker_not_production_image")
    _registered_audit_id(audit_id)
    output_path = original.capture.bootstrap.custody.LANE_ROOT.joinpath(*OUTPUT_PARTS,audit_id)
    _at_phase("worker_native_denial",_prove_allwrite_denial,output_path)
    # Native denial is proven first; hooks are only a second defense.
    sys.addaudithook(original.isolation._audit_event)
    _need(type(context) is dict and set(context) == {"identity","frozen_sources","intake_context",
        "operation_registration","operation_registration_sha256"}
        and context["identity"]["head"] == expected_head and context["intake_context"]["fixture_only"] is False,
        "strict_actual_worker_context_required")
    _known_context(context["operation_registration"], _registration())
    _known_context(context["operation_registration_sha256"], REGISTRATION_SHA256)
    original.capture.bootstrap._required_identity(context["identity"],expected_head)
    _at_phase("worker_current_sources",original._current_bytes,context["identity"],context["frozen_sources"])
    held = None
    try:
        held = _at_phase("worker_inputs",_held_for_context,context)
        first = _at_phase("worker_rederivation",_derive_twice,held)
        _at_phase("worker_input_recheck",held.recheck)
        _at_phase("worker_final_sources",original._current_bytes,context["identity"],context["frozen_sources"])
        rows = [bootstrap_source,*executed_sources]
        execution = _at_phase("worker_final_sources",_source_context,rows,context["identity"])
        result = {"schema":SCHEMA+"/worker-result","audit_id":audit_id,"fixture_only":False,
            "selection_b64":base64.b64encode(first.canonical_bytes()).decode("ascii"),"selection_sha256":first.sha256,
            "selection_bytes":len(first.canonical_bytes()),"counts":first.to_payload()["counts"],
            "intake_context":held.context,"source_execution":execution,"authority":_authority(),
            "effective_process_tree_network_denial":True,"effective_process_fork_denial":True,
            "effective_all_write_denial":True,"full_input_rederivations":2,
            "operation_registration_sha256":REGISTRATION_SHA256}
        _need(len(_raw(result)) <= MAX_CHILD_BYTES, "worker_selector_result_bound_refused")
        return result
    finally: _close_all((held,),phase="worker_cleanup")


def _validate_worker_result(body, *, audit_id, context):
    _registered_audit_id(audit_id)
    _known_context(context["operation_registration"], _registration())
    _known_context(context["operation_registration_sha256"], REGISTRATION_SHA256)
    body = _normalize_worker_control(body,context)
    _need(type(body) is dict and set(body) == {"schema","audit_id","fixture_only","selection_b64","selection_sha256",
        "selection_bytes","counts","intake_context","source_execution","authority","effective_process_tree_network_denial",
        "effective_process_fork_denial","effective_all_write_denial","full_input_rederivations",
        "operation_registration_sha256"}, "strict_worker_result_fields_required")
    _need(body["schema"] == SCHEMA+"/worker-result" and body["audit_id"] == audit_id and body["fixture_only"] is False
        and _raw(body["intake_context"]) == _raw(context["intake_context"])
        and _raw(body["authority"]) == _raw(_authority()) and type(body["full_input_rederivations"]) is int
        and body["full_input_rederivations"] == 2 and all(body[key] is True for key in (
            "effective_process_tree_network_denial","effective_process_fork_denial","effective_all_write_denial")), "worker_context_or_denial_differs")
    _need(type(body["selection_b64"]) is str and 0 < len(body["selection_b64"]) <= 4*((MAX_SELECTION_BYTES+2)//3), "bounded_selection_encoding_required")
    try: selection = base64.b64decode(body["selection_b64"],validate=True)
    except (ValueError,TypeError): raise AffectedQuarterSelectorRunnerError("strict_selection_base64_required") from None
    _need(type(body["selection_bytes"]) is int and 0 < len(selection) == body["selection_bytes"] <= MAX_SELECTION_BYTES
        and base64.b64encode(selection).decode("ascii") == body["selection_b64"]
        and _sha(selection) == pure._digest(body["selection_sha256"]), "worker_selection_bytes_binding_differs")
    # Parent interprets only canonical metadata/control, never any ZIP rows.
    selected = _selection_metadata(selection,context=context)
    _need(selected.get("schema") == pure.SCHEMA and selected.get("profile") == pure.PROFILE and selected.get("fixture_only") is False
        and selected.get("counts") == body["counts"] == pure.EXPECTED_ACTUAL_COUNTS
        and selected.get("source_form_counts") == pure.EXPECTED_ACTUAL_FORM_COUNTS
        and all(type(value) is int for value in body["counts"].values())
        and _raw(selected.get("authority")) == _raw(_authority())
        and selected.get("intake_manifest_sha256") == context["intake_context"]["manifest_sha256"]
        and selected.get("census_sha256") == context["intake_context"]["census_sha256"]
        and selected.get("header_preflight_sha256") == context["intake_context"]["header_preflight_sha256"], "worker_selection_metadata_context_differs")
    _need(_raw(_source_context(body["source_execution"]["executed_sources"],context["identity"])) == _raw(body["source_execution"]),
        "worker_executed_source_context_differs")
    return selection


def _child_result(child,*,context):
    _need(type(child.returncode) is int and child.returncode in {0,2} and child.stderr == b"" and type(child.stdout) is bytes
        and 0 < len(child.stdout) <= MAX_CHILD_BYTES, "selector_child_refused_outputs_preserved")
    body = _opaque_json(child.stdout.removesuffix(b"\n"))
    body = _strict_failure(body) if child.returncode == 2 else _normalize_worker_control(body,context)
    _need(child.stdout == _raw(body)+b"\n", "strict_selector_child_framing_required")
    if child.returncode == 2:
        _need(body["failure_phase"].startswith("worker_"),"strict_worker_failure_phase_required")
        raise ReportedSelectorWorkerError(body)
    return body


def _output_directory(audit_id):
    _registered_audit_id(audit_id)
    base = original.capture.bootstrap.custody.LANE_ROOT.joinpath(*OUTPUT_PARTS)
    parent = original.capture.custody._Directory(base,create=True)
    try:
        _need(not parent.exists(audit_id), "fresh_selector_namespace_required")
        info = os.fstatvfs(parent.fd)
        _need(info.f_bavail*info.f_frsize >= MIN_FREE_BYTES+MAX_SELECTION_BYTES+2*MAX_CONTROL_BYTES, "selector_disk_reserve_refused")
        os.mkdir(audit_id,0o700,dir_fd=parent.fd);os.fsync(parent.fd)
    finally: parent.close()
    return original.capture.custody._Directory(base/audit_id)


class _HeldPublication:
    def __init__(self,path,pins,*,fixture_only=False):
        _need(type(fixture_only) is bool,"explicit_publication_mode_required")
        if fixture_only: _fixture_fence(path)
        else:
            base = original.capture.bootstrap.custody.LANE_ROOT.joinpath(*OUTPUT_PARTS)
            _need(type(path) is type(base) and path.parent == base and path.name == AUDIT_ID,"fixed_selector_publication_root_required")
        _need(type(pins) is dict and set(pins) == _FILES,"exact_selector_output_pins_required")
        self.tree = None;self.pins = dict(pins)
        try:
            # Section 194: just-published leaves; recheck() rehashes their content.
            self.tree = held_io._HeldCapture(path, settle_ctime=True)
            _need(self.tree.names == _FILES,"exact_selector_output_inventory_required")
            for name,digest in sorted(pins.items()):
                pure._digest(digest);self.tree.open(name,MAX_SELECTION_BYTES if name == "selection.json" else MAX_CONTROL_BYTES)
            self.recheck()
        except BaseException: _close_all((self,),phase="parent_cleanup");raise

    def recheck(self):
        self.tree.check()
        for name,stream,_,cap in self.tree.handles:
            _need(held_io._hash_stream(stream,cap)[0] == self.pins[name],"held_selector_output_bytes_changed")
        self.tree.check()

    def close(self):
        _close_tree(self.tree,phase="parent_cleanup")


class _HeldPredecessorPublication:
    """Hold the exact refused predecessor read-only; never interpret its rows."""
    def __init__(self):
        self.held = None
        try:
            path = original.capture.bootstrap.custody.LANE_ROOT.joinpath(*PREDECESSOR_PARTS, PREDECESSOR_AUDIT_ID)
            self.held = previous._HeldPublication(path, PREDECESSOR_PINS)
            self.recheck()
        except BaseException:
            _close_all((self,), phase="parent_cleanup")
            raise

    def recheck(self):
        _need(self.held is not None, "predecessor_publication_hold_required")
        self.held.recheck()
        for name, stream, _, cap in self.held.tree.handles:
            _need(held_io._hash_stream(stream, cap) == (PREDECESSOR_PINS[name], PREDECESSOR_BYTES[name]),
                "preserved_failed_predecessor_pin_differs")
        self.held.recheck()

    def close(self):
        if self.held is not None:
            held, self.held = self.held, None
            held.close()


class _TreeCloser:
    def __init__(self, tree):
        self.tree = tree

    def close(self):
        _close_tree(self.tree, phase="parent_cleanup")


def run_observed_verification(audit_id, *, expected_head):
    _at_phase("parent_preflight", _registered_audit_id, audit_id)
    identity,frozen = _at_phase("parent_preflight",_fixed_source_identity,expected_head)
    held = output = publication = predecessor = None
    try:
        predecessor = _at_phase("parent_predecessor_hold", _HeldPredecessorPublication)
        held = _at_phase("parent_inputs",_HeldIntake)
        context = {"identity":identity,"frozen_sources":frozen,"intake_context":held.context, **_registration_fields()}
        sources = _at_phase("parent_source_capture",_captured_sources,identity)
        envelope = _at_phase("parent_source_capture",_captured_envelope,sources,context,audit_id,expected_head)
        _at_phase("parent_before_worker_inputs",held.recheck)
        _at_phase("parent_before_worker_sources",_equal_source_identity,expected_head,identity,frozen)
        _at_phase("parent_predecessor_recheck", predecessor.recheck)
        output = _at_phase("parent_output_reservation",_output_directory,audit_id)
        reservation = _raw({"schema":SCHEMA+"/reservation","audit_id":audit_id,"fixture_only":False,
            "current_execution_identity":identity,"frozen_sources":frozen,"intake_context":held.context,
            "source_only_bootstrap_sha256":_sha(SOURCE_ONLY_BOOTSTRAP.encode()),"authority":_authority(),
            **_registration_fields()})
        _at_phase("parent_output_reservation",output.publish,"reservation.json",reservation,cap=MAX_CONTROL_BYTES)
        child = _at_phase("parent_worker_launch",subprocess.run,["/usr/bin/env","-i","PATH=/usr/bin:/bin:/usr/sbin:/sbin",
            "/usr/bin/sandbox-exec","-p",original.isolation._worker_policy(output.path,readonly=True),
            sys.executable,"-I","-S","-B","-c",SOURCE_ONLY_BOOTSTRAP],cwd=original.capture.bootstrap.custody.LANE_ROOT,
            input=envelope,capture_output=True,check=False,timeout=1800)
        _at_phase("parent_after_worker_inputs",held.recheck)
        _at_phase("parent_after_worker_sources",_equal_source_identity,expected_head,identity,frozen)
        body = _at_phase("parent_worker_result",_child_result,child,context=context)
        selection = _at_phase("parent_worker_result",_validate_worker_result,body,audit_id=audit_id,context=context)
        _at_phase("parent_predecessor_recheck", predecessor.recheck)
        selection_sha = _at_phase("parent_publication",output.publish,"selection.json",selection,cap=MAX_SELECTION_BYTES)
        complete = _raw({"schema":SCHEMA+"/complete","audit_id":audit_id,"fixture_only":False,
            "observed_at_utc":original.capture.custody._utc(),
            "observer_clock_kind":"current_execution_completion_not_original_source_or_sec_publication_time",
            "current_execution_identity":identity,"frozen_sources":frozen,"intake_context":held.context,
            "reservation_sha256":_sha(reservation),"selection_sha256":selection_sha,"selection_bytes":len(selection),
            "worker_result_sha256":_sha(_raw(body)),"source_execution":body["source_execution"],"counts":body["counts"],
            "source_only_bootstrap_sha256":_sha(SOURCE_ONLY_BOOTSTRAP.encode()),"full_input_rederivations":2,
            "effective_process_tree_network_denial":True,"effective_process_fork_denial":True,
            "effective_all_write_denial":True,"authority":_authority(), **_registration_fields()})
        complete_sha = _at_phase("parent_publication",output.publish,"complete.json",complete,cap=MAX_CONTROL_BYTES)
        publication = _at_phase("parent_final_output_hold",_HeldPublication,output.path,
            {"reservation.json":_sha(reservation),"selection.json":selection_sha,"complete.json":complete_sha})
        _at_phase("parent_final_inputs",held.recheck)
        _at_phase("parent_final_sources",_equal_source_identity,expected_head,identity,frozen)
        _at_phase("parent_final_output_check",publication.recheck)
        _at_phase("parent_predecessor_recheck", predecessor.recheck)
        _at_phase("parent_final_output_check",publication.recheck)
        return {"audit_id":audit_id,"fixture_only":False,"selection_sha256":selection_sha,"complete_sha256":complete_sha,
            "counts":body["counts"],"authority":_authority(),"operation_registration_sha256":REGISTRATION_SHA256,
            "predecessor_status":"FAILED_preserved_not_promoted"}
    finally: _close_all((publication,output,held,predecessor),phase="parent_cleanup")


def verify_observed_completion(*, expected_head, expected_selection_sha256,
        expected_complete_sha256, observed_cli_success):
    """Read-only metadata/custody verification, not another selector execution.

    The caller separately observes the actual CLI return code and stdout. Its
    boolean hint is deliberately NOT authenticated by this function, and a
    complete.json leaf alone never establishes terminal success. This parent
    performs hash/control reads and Git identity checks (which spawn Git); it
    neither parses source ZIP rows nor launches a semantic worker. Enforce
    process-tree network denial and write denial externally; fork denial is
    incompatible with these explicit Git identity subprocesses.
    """
    _need(type(observed_cli_success) is bool and observed_cli_success,
        "external_cli_success_hint_required_not_authenticated_here")
    pure._digest(expected_selection_sha256)
    pure._digest(expected_complete_sha256)
    identity, frozen = _fixed_source_identity(expected_head)
    held = predecessor = tree = None
    try:
        predecessor = _HeldPredecessorPublication()
        held = _HeldIntake()
        context = {"identity": identity, "frozen_sources": frozen,
            "intake_context": held.context, **_registration_fields()}
        path = original.capture.bootstrap.custody.LANE_ROOT.joinpath(*OUTPUT_PARTS, AUDIT_ID)
        tree = held_io._HeldCapture(path, settle_ctime=True)
        _need(tree.names == _FILES, "exact_verification_readback_inventory_required")
        leaves = {}
        for name in sorted(_FILES):
            cap = MAX_SELECTION_BYTES if name == "selection.json" else MAX_CONTROL_BYTES
            stream = tree.open(name, cap)
            raw = stream.read(cap + 1)
            _need(0 < len(raw) <= cap, "bounded_verification_readback_leaf_required")
            leaves[name] = raw
        tree.check()
        _need(_sha(leaves["selection.json"]) == expected_selection_sha256
            and _sha(leaves["complete.json"]) == expected_complete_sha256,
            "external_verification_readback_pin_differs")
        selected = _selection_metadata(leaves["selection.json"], context=context)
        reservation = {"schema": SCHEMA + "/reservation", "audit_id": AUDIT_ID,
            "fixture_only": False, "current_execution_identity": identity,
            "frozen_sources": frozen, "intake_context": held.context,
            "source_only_bootstrap_sha256": _sha(SOURCE_ONLY_BOOTSTRAP.encode()),
            "authority": _authority(), **_registration_fields()}
        _need(leaves["reservation.json"] == _raw(reservation),
            "canonical_registered_reservation_differs")
        complete = _opaque_json(leaves["complete.json"])
        _need(type(complete) is dict and "source_execution" in complete
            and "observed_at_utc" in complete, "complete_verification_control_required")
        observed = complete["observed_at_utc"]
        _need(type(observed) is str and 1 <= len(observed) <= 64,
            "bounded_observer_completion_clock_required")
        try:
            stamp = datetime.fromisoformat(observed)
        except (TypeError, ValueError):
            raise AffectedQuarterSelectorRunnerError("strict_observer_completion_clock_required") from None
        _need(stamp.tzinfo is not None and stamp.utcoffset() == timezone.utc.utcoffset(stamp)
            and stamp.isoformat() == observed, "strict_utc_observer_completion_clock_required")
        execution = complete["source_execution"]
        _need(type(execution) is dict and "executed_sources" in execution,
            "readback_executed_source_inventory_required")
        execution = _source_context(execution["executed_sources"], identity)
        worker = {"schema": SCHEMA + "/worker-result", "audit_id": AUDIT_ID,
            "fixture_only": False,
            "selection_b64": base64.b64encode(leaves["selection.json"]).decode("ascii"),
            "selection_sha256": expected_selection_sha256,
            "selection_bytes": len(leaves["selection.json"]), "counts": selected["counts"],
            "intake_context": held.context, "source_execution": execution,
            "authority": _authority(), "effective_process_tree_network_denial": True,
            "effective_process_fork_denial": True, "effective_all_write_denial": True,
            "full_input_rederivations": 2, "operation_registration_sha256": REGISTRATION_SHA256}
        _need(_validate_worker_result(worker, audit_id=AUDIT_ID, context=context)
            == leaves["selection.json"], "readback_worker_control_reconstruction_differs")
        expected_complete = {"schema": SCHEMA + "/complete", "audit_id": AUDIT_ID,
            "fixture_only": False, "observed_at_utc": observed,
            "observer_clock_kind": "current_execution_completion_not_original_source_or_sec_publication_time",
            "current_execution_identity": identity, "frozen_sources": frozen,
            "intake_context": held.context, "reservation_sha256": _sha(leaves["reservation.json"]),
            "selection_sha256": expected_selection_sha256,
            "selection_bytes": len(leaves["selection.json"]),
            "worker_result_sha256": _sha(_raw(worker)), "source_execution": execution,
            "counts": selected["counts"],
            "source_only_bootstrap_sha256": _sha(SOURCE_ONLY_BOOTSTRAP.encode()),
            "full_input_rederivations": 2, "effective_process_tree_network_denial": True,
            "effective_process_fork_denial": True, "effective_all_write_denial": True,
            "authority": _authority(), **_registration_fields()}
        normalized = _known_context(complete, expected_complete)
        _need(_raw(normalized) == leaves["complete.json"],
            "canonical_completion_or_reconstructed_worker_hash_differs")
        held.recheck()
        _equal_source_identity(expected_head, identity, frozen)
        predecessor.recheck()
        tree.check()
        for name, stream, _, cap in tree.handles:
            _need(held_io._hash_stream(stream, cap) == (_sha(leaves[name]), len(leaves[name])),
                "held_verification_readback_bytes_changed")
        tree.check()
        return {"schema": SCHEMA + "/read-only-verification", "audit_id": AUDIT_ID,
            "fixture_only": False, "metadata_only": True,
            "semantic_rederivations_performed_here": 0,
            "terminal_cli_status_authenticated_here": False,
            "external_cli_success_hint_supplied": True,
            "operation_registration_sha256": REGISTRATION_SHA256,
            "selection_sha256": expected_selection_sha256,
            "complete_sha256": expected_complete_sha256,
            "reservation_sha256": _sha(leaves["reservation.json"]),
            "counts": selected["counts"], "predecessor_status": "FAILED_preserved_not_promoted",
            "authority": _authority()}
    finally:
        _close_all((held, predecessor, _TreeCloser(tree)), phase="parent_cleanup")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-id",required=True);parser.add_argument("--expected-head",required=True)
    args = parser.parse_args(argv)
    try:
        print(_raw(run_observed_verification(args.audit_id,expected_head=args.expected_head)).decode());return 0
    except (ValueError,OSError,TypeError,KeyError,subprocess.SubprocessError) as exc:
        print(_raw(_failure_diagnostic(exc)).decode());return 2


if __name__ == "__main__": raise SystemExit(main())
