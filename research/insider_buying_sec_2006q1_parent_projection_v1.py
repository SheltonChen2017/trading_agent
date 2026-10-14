"""Offline original-parent projection and complete-quarter reassessment.

Only the fixed-path clean committed lane image may run the real CLI. It reads sealed,
externally pinned local custody, never acquires source data. Full original XML
identity parsing uses the unchanged frozen Form4 parser; grammar refusal stays
in the parent ledger. All six source forms and every quarter row remain in the
unchanged IB-1C v2 assessment. Retrospective agreement is not admission or PIT.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from dataclasses import dataclass, field
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

from data.hashing import hash_payload
from research import insider_buying_sec_2006q1_parent_capture_v1 as capture
from research import insider_buying_ib1c_v2_affected_quarter_runner as preparation
from research import insider_buying_ib1c_v2_downstream_runner as downstream
from research import insider_buying_affected_quarter_isolation as isolation
from research.insider_buying.sec_bulk_snapshot import load_sec_bulk_snapshot
from research.insider_buying.sec_bulk_parsed_snapshot import load_sec_bulk_parsed_snapshot
from research.insider_buying.sec_complete_submission import (
    SecCompleteSubmissionError, SecCompleteSubmissionTarget, project_sec_complete_submission,
)
from research.insider_buying import sec_ib1c_identity_v2 as identity_v2
from research.insider_buying.sec_edgar_acceptance_snapshot import _upstream_submission_filing_date


SCHEMA = "insider-2006q1-original-parent-projection-ib1c-reassessment-v1"
SELF_PATH = "research/insider_buying_sec_2006q1_parent_projection_v1.py"
CAPTURE_ID = "ib-sec-2006q1-initial64-private-stdin-v2-20261014-once"
PREPARATION_ROOT = capture.bootstrap.custody.LANE_ROOT.parent / "insider-buying-ib1c-v2-2006q1-20261006.h7X8FN/candidate"
INPUT_ROOT = capture.bootstrap.custody.LANE_ROOT / "artifacts/sec_insider/raw"
OUTPUT_PARTS = ("artifacts", "insider_buying", "sec_2006q1_parent_projection_v1")
MAX_PARENT_COUNT = 64
MAX_ASSESSMENT_BYTES = 128 * 1024 * 1024
MAX_PROJECTED_LEDGER_BYTES = 1024 * 1024
MAX_INPUT_LEAF_BYTES = 256 * 1024 * 1024
MAX_CONTROL_BYTES = 1024 * 1024
MAX_WORKER_CONTEXT_BYTES = 32 * 1024 * 1024
MIN_FREE_BYTES = 4 * 1024 * 1024 * 1024
FROZEN_COMMIT = "aa0d635d00b64825bf8003289e0a60279bd52e73"
FROZEN_PATHS = (
    "research/insider_buying_sec_all_form4_parent_recovery_union.py",
    "research/insider_buying_sec_all_form4_parent_campaign.py",
    "research/insider_buying/sec_complete_submission.py",
    "research/insider_buying/sec_raw_parent_projection.py",
)
XML_PROFILE = {
    "version": "frozen-complete-submission-v1-plain-ownership-xml",
    "encoding": "strict-utf8-without-bom",
    "namespaces": "unsupported-quarantine",
    "dtd_and_entities": "refused",
    "forms": ["4", "4/A"],
    "raw_parent_maximum_bytes": 8 * 1024 * 1024,
    "primary_xml_maximum_bytes": 4 * 1024 * 1024,
    "source_acceptance_clock": "original-14-digit-source-declaration-not-official-publication",
    "clock_timezone_inferred": False,
    "financial_values_interpreted": False,
}
_ID = re.compile(r"ib-2006q1-parent-projection-[a-z0-9-]{1,70}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_TOKEN = object()
_COUNT_KEYS = frozenset({"source_filings", "target_filings", "context_filings", "selected_parents",
    "retained_parent_bodies", "projected_complete_parents", "grammar_quarantined_parents",
    "unavailable_selected_parents", "corroborated_noncanonical_filings", "quarantined_filings",
    "target_parent_corroboration_missing", "source_parent_identity_conflicts", "unsupported_context_forms",
    "retained_parent_bytes"})
PARSER_REFUSAL_CODES = frozenset({"source_body_encoding_or_bound_refused", "sec_document_envelope_refused",
    "original_header_grammar_refused", "header_target_identity_conflict", "source_acceptance_clock_refused",
    "complete_document_inventory_refused", "xml_security_profile_refused", "xml_dialect_refused",
    "xml_grammar_refused", "xml_target_identity_conflict", "header_xml_owner_identity_conflict",
    "unsupported_original_complete_parent_grammar"})
SOURCE_ONLY_BOOTSTRAP = r'''
import base64, hashlib, json, sys, types
def need(value):
    if not value: raise ValueError("source-only worker context refused")
context_raw = sys.stdin.buffer.read(33554433)
need(0 < len(context_raw) <= 33554432)
envelope = json.loads(context_raw)
need(type(envelope) is dict and set(envelope) == {"sources", "parent_context", "audit_id", "expected_head", "report_sha256"})
source_rows = envelope["sources"]
need(type(source_rows) is list)
selected = [r for r in source_rows if r.get("path") == "research/insider_buying_affected_quarter_isolation.py"]
need(len(selected) == 1)
bootstrap_raw = base64.b64decode(selected[0]["source_b64"], validate=True)
need(hashlib.sha256(bootstrap_raw).hexdigest() == selected[0]["sha256"])
helper = types.ModuleType("_early_projection_captured_imports")
helper.__file__ = "/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying/research/insider_buying_affected_quarter_isolation.py"
sys.modules[helper.__name__] = helper
exec(compile(bootstrap_raw, helper.__file__, "exec", dont_inherit=True), helper.__dict__)
# Reuse the exact executed helper image if the consumer imports its canonical
# name; do not execute the same bootstrap a second time through the finder.
sys.modules["research.insider_buying_affected_quarter_isolation"] = helper
sources = helper._decode_sources(source_rows)
identity = envelope["parent_context"]["identity"]
need({p: helper._sha(raw) for p,raw in sources} == identity["source_sha256"])
finder = helper._SourceFinder(sources)
sys.meta_path.insert(0, finder)
# The worker first proves inherited OS denial. Installing the Python hook
# here would intercept those probes before their required EPERM/EACCES result.
# The worker installs it after the probes and before opening retained inputs.
from research import insider_buying_sec_2006q1_parent_projection_v1 as consumer
result = consumer._worker(envelope["audit_id"], expected_head=envelope["expected_head"],
    expected_capture_report_sha256=envelope["report_sha256"], parent_context=envelope["parent_context"],
    executed_sources=lambda: [{"path": "research/insider_buying_affected_quarter_isolation.py", "sha256": selected[0]["sha256"]}, *finder.executed])
print(consumer._raw(result).decode())
'''


class EarlyParentProjectionError(ValueError):
    """Fixed codes only: raw XML, identities and private exception text excluded."""


def _need(value, code):
    if not value:
        raise EarlyParentProjectionError(code)


def _raw(body):
    return json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _digest(value):
    _need(type(value) is str and _SHA.fullmatch(value), "external_hash_required")
    return value


def _authority():
    return {**identity_v2._authority(), "complete_corpus": False,
        "historical_economic_identity_verified": False, "qc_entitlement_verified": False,
        "backtesting_ready": False, "output_is_canonical_source": False}


def _parser_refusal_code(error):
    """Categorize only the frozen parser's diagnostics; never serialize text.

    Unknown messages cannot become a source-defined output code. Classification
    is a diagnostic, not a second parser or grounds for relaxing the old one.
    """
    message = str(error).lower()
    if "dtd" in message or "entity" in message:return "xml_security_profile_refused"
    if "header and xml" in message and "owner" in message:return "header_xml_owner_identity_conflict"
    if "xml" in message and ("disagrees with target" in message or "differs from target" in message):
        return "xml_target_identity_conflict"
    if "xml" in message and any(word in message for word in ("namespace", "utf-8", "bom", "declaration")):
        return "xml_dialect_refused"
    if message.startswith("refused: xml"):return "xml_grammar_refused"
    if "acceptance" in message:return "source_acceptance_clock_refused"
    if "header" in message and any(word in message for word in ("disagree", "target", "opener disagrees")):
        return "header_target_identity_conflict"
    if "sec-document" in message:return "sec_document_envelope_refused"
    if "header" in message:return "original_header_grammar_refused"
    if any(word in message for word in ("document", "text scope", "primary xml", "xml wrapper")):
        return "complete_document_inventory_refused"
    if "complete submission" in message:return "source_body_encoding_or_bound_refused"
    return "unsupported_original_complete_parent_grammar"


@dataclass(frozen=True, slots=True)
class EarlyParentReassessment:
    _bytes: bytes = field(repr=False)
    _token: object = field(repr=False, compare=False)
    _factory_bytes: bytes | None = field(default=None, init=False, repr=False, compare=False)

    def canonical_bytes(self):
        _need(type(self) is EarlyParentReassessment and self._token is _TOKEN
              and type(self._bytes) is bytes and self._factory_bytes == self._bytes,
              "genuine_unchanged_reassessment_required")
        return self._bytes

    def to_payload(self):
        return json.loads(self.canonical_bytes())

    @property
    def sha256(self):
        return _sha(self.canonical_bytes())


def _source_filings(snapshot, base):
    table = next(t for t in snapshot.identity.tables if t.table_name == "SUBMISSION.tsv")
    columns = {key: table.headers.index(key) for key in (
        "DOCUMENT_TYPE", "ISSUERCIK", "ISSUERTRADINGSYMBOL", "FILING_DATE")}
    result = {}
    for source, assessed in zip((row for row in snapshot.rows if row.table_name == "SUBMISSION.tsv"), base["rows"], strict=True):
        _need(source.accession_number not in result, "duplicate_source_accession_refused")
        _need(source.accession_number == assessed["accession_number"]
              and source.source_record_ordinal == assessed["source_record_ordinal"], "source_assessment_row_binding_refused")
        values = source.values
        result[source.accession_number] = {"source_record_ordinal": source.source_record_ordinal,
            "accession_number": source.accession_number, "form_type": values[columns["DOCUMENT_TYPE"]],
            "raw_issuer_cik": values[columns["ISSUERCIK"]], "issuer_cik": assessed["issuer_comparison_key"],
            "raw_symbol_label": values[columns["ISSUERTRADINGSYMBOL"]],
            "raw_filing_date": values[columns["FILING_DATE"]], "filing_date": assessed["filing_date"],
            "relevant_form4_or_amendment": assessed["form_type"] in {"4", "4/A"},
            "accession_year_mismatch": assessed["accession_year_mismatch"]}
    _need(len(result) == len(base["rows"]) == table.row_count, "complete_source_filing_map_count_refused")
    return result


def assess_supplied_early_parents(snapshot, census, parent_inputs, *, expected_capture_report_sha256, fixture_only):
    """Pure bounded composition. Caller must verify original custody and inputs.

    A descriptor covers every selected prefix row, including unattempted or
    refused rows. Raw XML stays in memory; only hashes and identity accounting
    are returned. Supplied records cannot override source or readiness flags.
    """
    _digest(expected_capture_report_sha256)
    _need(type(fixture_only) is bool and type(parent_inputs) is tuple
          and len(parent_inputs) <= MAX_PARENT_COUNT, "bounded_parent_descriptor_tuple_required")
    _need(census.period == "2006Q1" and snapshot.identity.year == 2006 and snapshot.identity.quarter == 1,
          "fixed_early_quarter_required")
    base = identity_v2.assess_ib1c_v2_quarter_identity(snapshot, census, ()).to_payload()
    filings = _source_filings(snapshot, base)
    forms = {form: sum(row["form_type"] == form for row in base["rows"]) for form in capture.bootstrap.locators.FORMS}
    if not fixture_only:
        _need(base["submission_count"] == 83_657 and forms == {
            "3": 5694, "3/A": 534, "4": 68520, "4/A": 3159, "5": 5539, "5/A": 211}
            and len(parent_inputs) == MAX_PARENT_COUNT
            and snapshot.identity.raw_archive_sha256 == preparation.EXPECTED_ZIP_SHA256,
            "real_complete_quarter_population_required")
    parents, ledger, seen, total_bytes, previous = [], [], set(), 0, None
    descriptor_keys = {"prefix_ordinal", "request_sha256", "request", "result_sha256", "terminal_disposition",
        "body_sha256", "body_size_bytes", "raw_bytes", "header_identity_bound"}
    for ordinal, item in enumerate(parent_inputs):
        _need(type(item) is dict and set(item) == descriptor_keys
              and type(item["prefix_ordinal"]) is int and item["prefix_ordinal"] == ordinal,
              "parent_descriptor_order_or_shape_refused")
        request = capture._request(item["request"])
        _need(request["accession_number"] not in seen and item["request_sha256"] == _sha(_raw(request)),
              "parent_request_duplicate_or_hash_refused")
        seen.add(request["accession_number"])
        order = (request["filing_date"], request["accession_number"], request["source_record_ordinal"])
        _need(previous is None or previous < order, "parent_prefix_order_refused");previous = order
        filing = filings.get(request["accession_number"])
        _need(filing is not None and filing["relevant_form4_or_amendment"] is True
              and request["period"] == census.period
              and all(request[key] == filing[key] for key in ("form_type", "filing_date", "issuer_cik"))
              and request["source_record_ordinal"] == filing["source_record_ordinal"]
              and request["filing_metadata_sha256"] == _sha(_raw(filing))
              and request["quarterly_zip_sha256"] == snapshot.identity.raw_archive_sha256
              and request["submission_member_sha256"] == next(t.raw_member_sha256 for t in snapshot.identity.tables
                  if t.table_name == "SUBMISSION.tsv"), "parent_source_filing_binding_refused")
        if not fixture_only:
            _need(request["submission_inventory_sha256"] == capture.bootstrap.custody.INVENTORY_SHA256
                  and request["master_decoded_sha256"] == capture.bootstrap.locators.RETAINED_MASTER_SHA256
                  and request["master_receipt_sha256"] == capture.bootstrap.MASTER_RECEIPT_SHA256,
                  "actual_parent_original_source_anchor_refused")
        _need(type(item["header_identity_bound"]) is bool, "parent_header_binding_flag_refused")
        raw, terminal = item["raw_bytes"], item["terminal_disposition"]
        _need(type(terminal) is str, "parent_terminal_disposition_refused")
        row = {"prefix_ordinal": ordinal, "source_record_ordinal": request["source_record_ordinal"],
            "accession_number": request["accession_number"], "request_sha256": item["request_sha256"],
            "capture_result_sha256": item["result_sha256"], "capture_terminal_disposition": terminal,
            "header_identity_bound": item["header_identity_bound"], "body_sha256": item["body_sha256"],
            "body_size_bytes": item["body_size_bytes"], "projection": None, "quarantine_code": None}
        if raw is None:
            _need(item["body_sha256"] is None and item["body_size_bytes"] is None
                  and item["header_identity_bound"] is False and terminal in {
                      "planned_unattempted", "ambiguous_transport_failure_no_retry", "http_refused_no_retry",
                      "response_privacy_framing_or_custody_refused_no_retry"}, "missing_body_descriptor_refused")
            _need((item["result_sha256"] is None) is (terminal == "planned_unattempted"),
                  "unattempted_result_binding_refused")
            if item["result_sha256"] is not None:_digest(item["result_sha256"])
            row.update(disposition="complete_parent_unavailable", quarantine_code=terminal)
        else:
            _need(type(raw) is bytes and 0 < len(raw) <= capture.MAX_PARENT_BYTES
                  and type(item["body_size_bytes"]) is int and item["body_size_bytes"] == len(raw)
                  and item["body_sha256"] == _sha(raw) and terminal in {
                      "complete_raw_response_retained_header_bound", "complete_raw_response_retained_header_quarantined"}
                  and item["header_identity_bound"] is (terminal.endswith("_bound")), "retained_body_binding_refused")
            _digest(item["result_sha256"])
            total_bytes += len(raw)
            _need(total_bytes <= identity_v2.MAX_CORROBORATING_BYTES, "existing_v2_aggregate_parent_byte_bound_refused")
            target = SecCompleteSubmissionTarget(period=request["period"], accession_number=request["accession_number"],
                form_type=request["form_type"], filing_date=request["filing_date"], issuer_cik=request["issuer_cik"],
                quarterly_index_sha256=request["master_decoded_sha256"], complete_submission_url=request["url"])
            try:
                parent = project_sec_complete_submission(target, raw)
            except SecCompleteSubmissionError as exc:
                row.update(disposition="original_complete_parent_grammar_quarantined",
                           quarantine_code=_parser_refusal_code(exc))
            else:
                payload = parent.to_payload()
                _need(payload["raw_parent"]["sha256"] == item["body_sha256"], "projection_parent_identity_differs")
                row.update(disposition="original_complete_parent_projected_noncanonical", projection={
                    "version": payload["version"], "projection_sha256": parent.sha256,
                    "header_sha256": payload["children"]["header"]["sha256"],
                    "xml_sha256": payload["children"]["primary_xml"]["sha256"],
                    "xml_size_bytes": payload["children"]["primary_xml"]["size_bytes"],
                    "accepted_at_raw": payload["source_fields"]["accepted_at_raw"],
                    "accepted_clock_verified": False, "reporting_owner_count": len(payload["source_fields"]["header_owner_ciks"])})
                parents.append(parent)
        ledger.append(row)
    final = identity_v2.assess_ib1c_v2_quarter_identity(snapshot, census, tuple(parents)).to_payload()
    _need(all(type(final.get(key)) is int and final[key] >= 0 for key in (
              "submission_count", "corroborated_count", "quarantined_count", "short_cik_count", "accession_year_mismatch_count"))
          and type(final.get("rows")) is list and len(final["rows"]) == len(base["rows"]) and final["submission_count"] == base["submission_count"]
          and [(r["source_record_ordinal"], r["accession_number"]) for r in final["rows"]]
          == [(r["source_record_ordinal"], r["accession_number"]) for r in base["rows"]]
          and _raw(final["authority"]) == _raw(identity_v2._authority())
          and final.get("accounting_sha256") == hash_payload(final["rows"]), "whole_quarter_reassessment_accounting_refused")
    reasons = Counter(reason for r in final["rows"] for reason in r["quarantine_reasons"])
    counts = {"source_filings": len(final["rows"]), "target_filings": forms["4"] + forms["4/A"],
        "context_filings": sum(forms[f] for f in ("3", "3/A", "5", "5/A")),
        "selected_parents": len(ledger), "retained_parent_bodies": sum(r["body_sha256"] is not None for r in ledger),
        "projected_complete_parents": len(parents),
        "grammar_quarantined_parents": sum(r["disposition"] == "original_complete_parent_grammar_quarantined" for r in ledger),
        "unavailable_selected_parents": sum(r["disposition"] == "complete_parent_unavailable" for r in ledger),
        "corroborated_noncanonical_filings": final["corroborated_count"], "quarantined_filings": final["quarantined_count"],
        "target_parent_corroboration_missing": reasons["complete_parent_corroboration_missing"],
        "source_parent_identity_conflicts": reasons["complete_parent_identity_conflict"],
        "unsupported_context_forms": reasons["unsupported_parent_corroboration_form"], "retained_parent_bytes": total_bytes}
    _need(counts["corroborated_noncanonical_filings"] + counts["quarantined_filings"] == counts["source_filings"]
          and counts["target_parent_corroboration_missing"] + counts["source_parent_identity_conflicts"]
          + counts["corroborated_noncanonical_filings"] == counts["target_filings"]
          and counts["unsupported_context_forms"] == counts["context_filings"], "complete_quarantine_partition_refused")
    body = {"schema": SCHEMA, "fixture_only": fixture_only, "period": "2006Q1",
        "capture_report_sha256": expected_capture_report_sha256, "xml_profile": XML_PROFILE,
        "census_quarter_sha256": hash_payload(census.to_payload()), "parsed_snapshot_id": snapshot.identity.snapshot_id,
        "parsed_lineage_sha256": snapshot.identity.lineage_hash, "form_counts": forms,
        "parent_projection_ledger": ledger, "parent_projection_ledger_sha256": _sha(_raw(ledger)),
        "counts": counts, "projection_refusal_counts": {code: sum(row["quarantine_code"] == code for row in ledger)
            for code in sorted(PARSER_REFUSAL_CODES)}, "assessment": final, "assessment_sha256": hash_payload(final),
        "whole_quarter_identity_sha256": final["whole_quarter_identity_sha256"], "authority": _authority()}
    raw = _raw(body)
    _need(len(raw) <= MAX_ASSESSMENT_BYTES, "reassessment_output_bound_refused")
    result = EarlyParentReassessment(raw, _TOKEN)
    object.__setattr__(result, "_factory_bytes", raw)
    return result


def _fixed_source_identity(expected_head):
    _need(Path(__file__).resolve() == capture.bootstrap.custody.LANE_ROOT / SELF_PATH,
          "inactive_projection_draft_not_production_source")
    base_identity = capture.bootstrap.custody._identity(expected_head)
    _need(SELF_PATH in base_identity["source_sha256"], "committed_projection_source_required")
    # The general import closure need not include the two unused frozen
    # campaign modules. Bind their held current bytes and exact HEAD blobs
    # explicitly; absence from the import closure is not source drift.
    current = capture.bootstrap.custody._source_bytes(capture.bootstrap.custody.LANE_ROOT, FROZEN_PATHS)
    _need(set(current) == set(FROZEN_PATHS), "explicit_frozen_source_inventory_refused")
    frozen = {}
    for name in FROZEN_PATHS:
        committed = capture.bootstrap.custody._git(capture.bootstrap.custody.LANE_ROOT, "show", expected_head + ":" + name)
        _need(_sha(committed) == current[name]
              and (name not in base_identity["source_sha256"] or base_identity["source_sha256"][name] == current[name]),
              "current_frozen_source_differs_from_committed_blob")
        historical = capture.bootstrap.custody._git(capture.bootstrap.custody.LANE_ROOT, "show", FROZEN_COMMIT + ":" + name)
        digest = _sha(historical)
        _need(current[name] == digest, "frozen_current_source_differs_from_historical_blob")
        frozen[name] = digest
    _need(capture.bootstrap.custody._identity(expected_head) == base_identity
          and capture.bootstrap.custody._source_bytes(capture.bootstrap.custody.LANE_ROOT, FROZEN_PATHS) == current,
          "explicit_source_binding_changed")
    sources = {**base_identity["source_sha256"], **current}
    identity = {**base_identity, "source_sha256": sources, "source_inventory_sha256": _sha(_raw(sources))}
    return identity, frozen


def _tree_contents(tree, parts=()):
    """Hold/recheck every private original preparation leaf without modification."""
    for name in tree.names(parts):
        info = os.stat(name, dir_fd=tree.open(parts).fd, follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode):
            _tree_contents(tree, (*parts, name))
        else:
            tree.read(parts, name, cap=MAX_INPUT_LEAF_BYTES)
            if name.endswith(".publication.lock"):
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=tree.open(parts).fd)
                fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
                tree.locks.append((tree.open(parts), name, fd, capture.bootstrap.custody._version(os.fstat(fd))))


class _PinnedRetainedInput:
    """Only two exact externally hashed public ZIP/intake leaves may be 0644."""
    def __init__(self):
        self.chain = capture.bootstrap.custody._Chain(INPUT_ROOT, ())
        self.pins = {}
        try:
            for name, digest, size in (
                (preparation._MANIFEST_NAME, preparation.EXPECTED_MANIFEST_SHA256, preparation.EXPECTED_MANIFEST_SIZE_BYTES),
                (preparation.FILENAME, preparation.EXPECTED_ZIP_SHA256, preparation.EXPECTED_ZIP_SIZE_BYTES)):
                before = os.stat(name, dir_fd=self.chain.fd, follow_symlinks=False)
                _need(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid() and before.st_nlink == 1
                      and stat.S_IMODE(before.st_mode) in {0o600, 0o644} and before.st_size == size,
                      "retained_public_input_leaf_refused")
                raw = capture.bootstrap.custody._read_leaf(self.chain.fd, name, limit=size, private=False)
                _need(_sha(raw) == digest and capture.bootstrap.custody._version(before) ==
                      capture.bootstrap.custody._version(os.stat(name, dir_fd=self.chain.fd, follow_symlinks=False)),
                      "retained_public_input_hash_or_version_differs")
                self.pins[name] = (digest, size, capture.bootstrap.custody._version(before))
        except BaseException:
            self.chain.close();raise

    def recheck(self):
        self.chain.recheck()
        for name, (digest, size, version) in self.pins.items():
            _need(capture.bootstrap.custody._version(os.stat(name, dir_fd=self.chain.fd, follow_symlinks=False)) == version
                  and _sha(capture.bootstrap.custody._read_leaf(self.chain.fd, name, limit=size, private=False)) == digest,
                  "retained_public_input_changed")

    def close(self):self.chain.close()


def _load_original_preparation():
    tree = capture.bootstrap._Tree(capture.bootstrap.RootSpec("original-ib1cv2-preparation", PREPARATION_ROOT, "sealed-preparation"))
    public = None
    try:
        public = _PinnedRetainedInput()
        _tree_contents(tree)
        completion_raw = tree.read((), "completion.json", cap=preparation.MAX_COMPLETION_BYTES,
                                   expected=downstream.EXPECTED_COMPLETION_SHA256)
        tree.read((), "assessment.json", cap=MAX_ASSESSMENT_BYTES, expected=downstream.EXPECTED_ASSESSMENT_SHA256)
        completion = preparation._parse_envelope(completion_raw)
        receipt = completion["receipt"]
        # Independently regenerate the entire old empty-parent assessment and
        # completion. Original local clock and producer lineage stay unchanged.
        observed = preparation._verify_quarter(INPUT_ROOT, PREPARATION_ROOT,
            downstream.PRODUCER_COMMIT, downstream.PRODUCER_SOURCE_INVENTORY_SHA256)
        _need(observed == receipt, "original_preparation_full_replay_differs")
        _, _, quarter, _, _, _ = preparation._prepare_inputs(INPUT_ROOT)
        raw_path = PREPARATION_ROOT / "ib1a" / receipt["raw_snapshot_id"]
        loaded = load_sec_bulk_snapshot(raw_path)
        parsed = load_sec_bulk_parsed_snapshot(PREPARATION_ROOT / "ib1b" / receipt["parsed_snapshot_id"], raw_snapshot_directory=raw_path)
        _need(loaded.identity.archive_sha256 == preparation.EXPECTED_ZIP_SHA256
              and parsed.identity.raw_archive_sha256 == preparation.EXPECTED_ZIP_SHA256,
              "original_raw_upstream_binding_refused")
        tree.recheck();public.recheck()
        return tree, public, parsed, quarter
    except BaseException:
        tree.close()
        if public is not None:public.close()
        raise


def _load_sealed_capture(expected_report_sha256, *, fixture_only=False, root=None):
    _need(type(fixture_only) is bool, "capture_reader_mode_refused")
    if fixture_only:
        capture._fixture_root(root)
        capture.bootstrap.custody._effective_denial(require_fork=False)
    else:
        _need(root is None or root == capture.bootstrap.custody.LANE_ROOT, "actual_fixed_capture_root_required")
        root = capture.bootstrap.custody.LANE_ROOT
    first = capture._verify_capture(CAPTURE_ID, root=root,
        expected_report_sha256=expected_report_sha256, fixture_only=fixture_only)
    base = root.joinpath(*capture.ARTIFACT_PARTS)
    tree = capture.bootstrap._Tree(capture.bootstrap.RootSpec("early-parent-sealed-capture", base, "sealed-capture"))
    try:
        lock = tree.open(())
        fd = os.open("capture.lock", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=lock.fd)
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        tree.locks.append((lock, "capture.lock", fd, capture.bootstrap.custody._version(os.fstat(fd))))
        parts = ("runs", CAPTURE_ID)
        report = capture._json(tree.read(parts, "complete.json", cap=MAX_CONTROL_BYTES, expected=expected_report_sha256))
        reservation = capture._json(tree.read(parts, "reservation.json", cap=MAX_CONTROL_BYTES, expected=report["reservation_sha256"]))
        selection = reservation["selection"]
        capture._verify_selection_payload(selection, fixture_only=fixture_only)
        descriptors = []
        for ordinal, request in enumerate(selection["requests"]):
            descriptor = {**request, "result_sha256": None, "terminal_disposition": "planned_unattempted",
                "body_sha256": None, "body_size_bytes": None, "raw_bytes": None, "header_identity_bound": False}
            if ordinal < len(report["results"]):
                row = report["results"][ordinal]
                result = capture._json(tree.read(parts, row["result_name"], cap=MAX_CONTROL_BYTES, expected=row["result_sha256"]))
                tree.read(parts, f"request-{ordinal:03d}-start.json", cap=MAX_CONTROL_BYTES, expected=result["start_sha256"])
                tree.read(("claims",), request["request"]["accession_key_sha256"] + ".json", cap=MAX_CONTROL_BYTES)
                descriptor.update(result_sha256=row["result_sha256"], terminal_disposition=result["disposition"],
                    header_identity_bound=result["header_identity_bound"], body_sha256=result["body_sha256"],
                    body_size_bytes=result["body_size_bytes"])
                if result["body_retained"]:
                    descriptor["raw_bytes"] = tree.read((*parts, "objects"), result["body_sha256"] + ".bin",
                        cap=capture.MAX_PARENT_BYTES, expected=result["body_sha256"])
            descriptors.append(descriptor)
        _need(capture._verify_capture(CAPTURE_ID, root=root, expected_report_sha256=expected_report_sha256,
              fixture_only=fixture_only) == first, "sealed_capture_changed_during_loading")
        tree.recheck()
        return tree, tuple(descriptors), reservation, report
    except BaseException:
        tree.close();raise


def _output_directory(audit_id, *, create):
    _need(type(audit_id) is str and _ID.fullmatch(audit_id), "projection_audit_id_refused")
    base = capture.bootstrap.custody.LANE_ROOT.joinpath(*OUTPUT_PARTS)
    if create:
        parent = capture.custody._Directory(base, create=True)
        try:
            _need(not parent.exists(audit_id), "fresh_projection_output_required")
            statvfs = os.fstatvfs(parent.fd)
            _need(statvfs.f_bavail * statvfs.f_frsize >= MIN_FREE_BYTES + MAX_ASSESSMENT_BYTES + 2 * MAX_CONTROL_BYTES,
                  "projection_disk_reserve_refused")
            os.mkdir(audit_id, 0o700, dir_fd=parent.fd);os.fsync(parent.fd)
        finally:parent.close()
    return capture.custody._Directory(base / audit_id)


def _current_bytes(identity, frozen):
    _need(SELF_PATH in identity["source_sha256"] and set(FROZEN_PATHS) == set(frozen)
          and capture.bootstrap.custody._source_bytes(capture.bootstrap.custody.LANE_ROOT,
              tuple(identity["source_sha256"])) == identity["source_sha256"]
          and all(identity["source_sha256"][name] == frozen[name] for name in FROZEN_PATHS),
          "projection_current_or_frozen_source_changed")


def _prove_worker_isolation(output_path):
    capture.bootstrap.custody._effective_denial(require_fork=True)
    outside = output_path.parent / (output_path.name + ".outside-probe")
    try:probe = os.open(outside, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except OSError as exc:_need(exc.errno in {errno.EPERM, errno.EACCES}, "effective_projection_write_confinement_not_observed")
    else:os.close(probe);raise EarlyParentProjectionError("effective_projection_write_confinement_not_observed")


def _strict_summary(result, *, audit_id, report_sha):
    keys = {"audit_id", "fixture_only", "complete_sha256", "assessment_sha256", "projection_ledger_sha256",
        "capture_report_sha256", "counts", "projection_refusal_counts", "authority"}
    _need(type(result) is dict and set(result) == keys and result.get("audit_id") == audit_id
          and result.get("fixture_only") is False and result.get("capture_report_sha256") == report_sha
          and _raw(result.get("authority")) == _raw(_authority()) and type(result.get("counts")) is dict
          and set(result["counts"]) == _COUNT_KEYS
          and all(type(value) is int and value >= 0 for value in result["counts"].values()),
          "worker_reassessment_summary_refused")
    reasons = result.get("projection_refusal_counts")
    _need(type(reasons) is dict and set(reasons) == PARSER_REFUSAL_CODES
          and all(type(value) is int and value >= 0 for value in reasons.values())
          and sum(reasons.values()) == result["counts"]["grammar_quarantined_parents"],
          "worker_projection_refusal_summary_refused")
    for key in ("complete_sha256", "assessment_sha256", "projection_ledger_sha256", "capture_report_sha256"):
        _digest(result[key])
    counts = result["counts"]
    _need(counts["source_filings"] == 83_657 and counts["target_filings"] == 71_679
          and counts["context_filings"] == counts["unsupported_context_forms"] == 11_978
          and counts["selected_parents"] == MAX_PARENT_COUNT
          and counts["retained_parent_bodies"] <= MAX_PARENT_COUNT
          and counts["projected_complete_parents"] + counts["grammar_quarantined_parents"] == counts["retained_parent_bodies"]
          and counts["unavailable_selected_parents"] + counts["retained_parent_bodies"] == MAX_PARENT_COUNT
          and counts["corroborated_noncanonical_filings"] + counts["quarantined_filings"] == counts["source_filings"]
          and counts["target_parent_corroboration_missing"] + counts["source_parent_identity_conflicts"]
              + counts["corroborated_noncanonical_filings"] == counts["target_filings"]
          and counts["corroborated_noncanonical_filings"] + counts["source_parent_identity_conflicts"] == counts["projected_complete_parents"]
          and 0 <= counts["retained_parent_bytes"] <= identity_v2.MAX_CORROBORATING_BYTES
          and (counts["retained_parent_bytes"] > 0) is (counts["retained_parent_bodies"] > 0),
          "worker_reassessment_count_partition_refused")
    return result


def _worker(audit_id, *, expected_head, expected_capture_report_sha256, parent_context, executed_sources=None):
    _need(Path(__file__).resolve() == capture.bootstrap.custody.LANE_ROOT / SELF_PATH
          and Path.cwd() == capture.bootstrap.custody.LANE_ROOT, "inactive_projection_draft_not_production_source")
    _need(type(parent_context) is dict and set(parent_context) == {"identity", "frozen_sources"}, "worker_context_shape_refused")
    identity, frozen = parent_context["identity"], parent_context["frozen_sources"]
    _need(callable(executed_sources), "captured_source_only_worker_required")
    capture.bootstrap._required_identity(identity, expected_head)
    _current_bytes(identity, frozen)
    output = _output_directory(audit_id, create=False)
    inputs, raw, parents = None, None, None
    try:
        _need(set(os.listdir(output.fd)) == {"reservation.json"}, "fresh_reserved_projection_output_required")
        reservation_raw = output.read("reservation.json", cap=MAX_CONTROL_BYTES)
        reservation = capture._json(reservation_raw)
        _need(reservation == {"schema": SCHEMA + "/reservation", "audit_id": audit_id,
            "capture_id": CAPTURE_ID, "capture_report_sha256": expected_capture_report_sha256,
            "current_execution_identity": identity, "frozen_sources": frozen,
            "original_preparation_completion_sha256": downstream.EXPECTED_COMPLETION_SHA256,
            "original_preparation_assessment_sha256": downstream.EXPECTED_ASSESSMENT_SHA256,
            "source_only_bootstrap_sha256": _sha(SOURCE_ONLY_BOOTSTRAP.encode()),
            "authority": _authority()}, "projection_reservation_context_differs")
        _prove_worker_isolation(output.path)
        sys.addaudithook(isolation._audit_event)
        inputs, raw, snapshot, census = _load_original_preparation()
        parents, descriptors, capture_reservation, capture_report = _load_sealed_capture(expected_capture_report_sha256)
        _current_bytes(identity, frozen)
        result = assess_supplied_early_parents(snapshot, census, descriptors,
            expected_capture_report_sha256=expected_capture_report_sha256, fixture_only=False)
        payload = result.to_payload()
        repeated = assess_supplied_early_parents(snapshot, census, descriptors,
            expected_capture_report_sha256=expected_capture_report_sha256, fixture_only=False)
        _need(repeated.canonical_bytes() == result.canonical_bytes(), "complete_reassessment_reexecution_differs")
        inputs.recheck();raw.recheck();parents.recheck();_current_bytes(identity, frozen)
        assessment_raw = _raw(payload["assessment"])
        ledger_payload = {key: value for key, value in payload.items() if key != "assessment"}
        ledger_raw = _raw(ledger_payload)
        _need(len(ledger_raw) <= MAX_PROJECTED_LEDGER_BYTES, "projection_ledger_output_bound_refused")
        assessment_sha = output.publish("assessment.json", assessment_raw, cap=MAX_ASSESSMENT_BYTES)
        ledger_sha = output.publish("parent-projection.json", ledger_raw, cap=MAX_PROJECTED_LEDGER_BYTES)
        completed = {"schema": SCHEMA + "/complete", "audit_id": audit_id, "fixture_only": False,
            "observed_at_utc": capture.custody._utc(), "current_execution_identity": identity,
            "frozen_sources": frozen, "reservation_sha256": _sha(reservation_raw),
            "capture_id": CAPTURE_ID, "capture_report_sha256": expected_capture_report_sha256,
            "capture_execution_head": capture_report["capture_execution_head"],
            "capture_execution_source_inventory_sha256": capture_reservation["execution_identity"]["source_inventory_sha256"],
            "bootstrap_execution_head": capture_report["bootstrap_execution_head"],
            "original_preparation_producer_commit": downstream.PRODUCER_COMMIT,
            "original_preparation_completion_sha256": downstream.EXPECTED_COMPLETION_SHA256,
            "original_preparation_assessment_sha256": downstream.EXPECTED_ASSESSMENT_SHA256,
            "assessment_sha256": assessment_sha, "assessment_bytes": len(assessment_raw),
            "projection_ledger_sha256": ledger_sha, "projection_ledger_bytes": len(ledger_raw),
            "reassessment_payload_sha256": result.sha256, "counts": payload["counts"],
            "projection_refusal_counts": payload["projection_refusal_counts"],
            "source_execution": _source_execution_context(executed_sources(), identity),
            "source_only_bootstrap_sha256": _sha(SOURCE_ONLY_BOOTSTRAP.encode()),
            "xml_profile": XML_PROFILE, "authority": _authority()}
        inputs.recheck();raw.recheck();parents.recheck();_current_bytes(identity, frozen)
        complete_sha = output.publish("complete.json", _raw(completed), cap=MAX_CONTROL_BYTES)
        _need(output.read("assessment.json", cap=MAX_ASSESSMENT_BYTES) == assessment_raw
              and output.read("parent-projection.json", cap=MAX_PROJECTED_LEDGER_BYTES) == ledger_raw
              and set(os.listdir(output.fd)) == {"reservation.json", "assessment.json", "parent-projection.json", "complete.json"},
              "projection_publication_readback_refused")
        inputs.recheck();raw.recheck();parents.recheck();_current_bytes(identity, frozen);output.check()
        return {"audit_id": audit_id, "fixture_only": False, "complete_sha256": complete_sha,
            "assessment_sha256": assessment_sha, "projection_ledger_sha256": ledger_sha,
            "capture_report_sha256": expected_capture_report_sha256, "counts": payload["counts"],
            "projection_refusal_counts": payload["projection_refusal_counts"], "authority": _authority()}
    finally:
        for held in (parents, raw, inputs, output):
            if held is not None:held.close()


def run_observed_reassessment(audit_id, *, expected_head, expected_capture_report_sha256):
    identity, frozen = _fixed_source_identity(expected_head)
    _digest(expected_capture_report_sha256)
    # Independent acquisition source lineage, not the current code masquerading
    # as the historical producer. No unsealed output is accepted by this path.
    capture._verify_original_committed_sources(CAPTURE_ID, expected_capture_report_sha256)
    output = _output_directory(audit_id, create=True)
    try:
        reservation = {"schema": SCHEMA + "/reservation", "audit_id": audit_id, "capture_id": CAPTURE_ID,
            "capture_report_sha256": expected_capture_report_sha256, "current_execution_identity": identity,
            "frozen_sources": frozen, "original_preparation_completion_sha256": downstream.EXPECTED_COMPLETION_SHA256,
            "original_preparation_assessment_sha256": downstream.EXPECTED_ASSESSMENT_SHA256,
            "source_only_bootstrap_sha256": _sha(SOURCE_ONLY_BOOTSTRAP.encode()), "authority": _authority()}
        output.publish("reservation.json", _raw(reservation), cap=MAX_CONTROL_BYTES)
        sources = []
        for name, digest in sorted(identity["source_sha256"].items()):
            raw = isolation._read_source(name)
            _need(_sha(raw) == digest, "parent_captured_source_bytes_changed")
            sources.append({"path": name, "sha256": digest, "source_b64": base64.b64encode(raw).decode("ascii")})
        envelope = _raw({"sources": sources, "parent_context": {"identity": identity, "frozen_sources": frozen},
            "audit_id": audit_id, "expected_head": expected_head, "report_sha256": expected_capture_report_sha256})
        _need(len(envelope) <= MAX_WORKER_CONTEXT_BYTES, "source_only_worker_context_bound_refused")
        _need(_fixed_source_identity(expected_head) == (identity, frozen), "parent_source_changed_before_worker")
        policy = isolation._worker_policy(output.path)
        command = ["/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "/usr/bin/sandbox-exec", "-p", policy,
            sys.executable, "-I", "-S", "-B", "-c", SOURCE_ONLY_BOOTSTRAP]
        child = subprocess.run(command, cwd=capture.bootstrap.custody.LANE_ROOT,
            input=envelope, capture_output=True, check=False, timeout=1800)
        _need(_fixed_source_identity(expected_head) == (identity, frozen), "parent_source_or_head_changed")
        _need(child.returncode == 0 and not child.stderr and len(child.stdout) <= MAX_CONTROL_BYTES,
              "isolated_reassessment_failed_outputs_preserved")
        # print adds one framing LF, not an arbitrary whitespace suffix.
        result = _strict_summary(capture._json(child.stdout.removesuffix(b"\n")), audit_id=audit_id, report_sha=expected_capture_report_sha256)
        complete_raw = output.read("complete.json", cap=MAX_CONTROL_BYTES)
        _need(_sha(complete_raw) == result["complete_sha256"],
              "worker_complete_hash_refused")
        complete = capture._json(complete_raw)
        _need(_raw(complete.get("counts")) == _raw(result["counts"])
              and _raw(complete.get("projection_refusal_counts")) == _raw(result["projection_refusal_counts"])
              and _raw(complete.get("authority")) == _raw(_authority())
              and complete.get("assessment_sha256") == result["assessment_sha256"]
              and complete.get("projection_ledger_sha256") == result["projection_ledger_sha256"]
              and complete.get("current_execution_identity") == identity and complete.get("frozen_sources") == frozen
              and complete.get("source_only_bootstrap_sha256") == _sha(SOURCE_ONLY_BOOTSTRAP.encode())
              and _sha(output.read("assessment.json", cap=MAX_ASSESSMENT_BYTES)) == result["assessment_sha256"]
              and _sha(output.read("parent-projection.json", cap=MAX_PROJECTED_LEDGER_BYTES)) == result["projection_ledger_sha256"],
              "worker_publication_summary_or_data_hash_differs")
        output.check()
        _source_execution_context(complete.get("source_execution", {}).get("executed_sources"), identity)
        return result
    finally:output.close()


def _source_execution_context(rows, identity):
    _need(type(rows) is list and 1 <= len(rows) <= 512, "executed_source_inventory_refused")
    unique = {}
    for row in rows:
        _need(type(row) is dict and set(row) == {"path", "sha256"} and type(row["path"]) is str
              and row["sha256"] == identity["source_sha256"].get(row["path"]), "executed_source_inventory_refused")
        _need(row["path"] not in unique, "duplicate_executed_source_inventory_refused")
        unique[row["path"]] = _digest(row["sha256"])
    _need(SELF_PATH in unique and "research/insider_buying/sec_complete_submission.py" in unique
          and "research/insider_buying/sec_ib1c_identity_v2.py" in unique, "executed_projection_and_assessor_sources_required")
    return {"source_only_lane_imports": True, "executed_sources": rows,
        "executed_source_inventory_sha256": _sha(_raw(rows)), "executed_source_count": len(rows),
        "full_historical_environment_reconstructed": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-id", required=True);parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-capture-report-sha256", required=True)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.worker:
            context = capture._json(sys.stdin.buffer.read(4 * MAX_CONTROL_BYTES))
            result = _worker(args.audit_id, expected_head=args.expected_head,
                expected_capture_report_sha256=args.expected_capture_report_sha256, parent_context=context)
        else:
            result = run_observed_reassessment(args.audit_id, expected_head=args.expected_head,
                expected_capture_report_sha256=args.expected_capture_report_sha256)
        print(_raw(result).decode());return 0
    except (EarlyParentProjectionError, capture.EarlyParentCaptureError, capture.bootstrap.ParentBootstrapError,
            capture.bootstrap.custody.ArchiveAssessmentRunnerError, identity_v2.Ib1cIdentityV2Error,
            OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        print('{"disposition":"offline_parent_projection_refused_outputs_preserved"}');return 2


if __name__ == "__main__":
    raise SystemExit(main())

