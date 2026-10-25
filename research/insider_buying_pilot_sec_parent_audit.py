"""Pure streaming accession-level parent coverage for the separate pilot.

Every supplied six-form filing survives the metadata ledger. Operational
consumption and retained, opaque-body candidates are deliberately separate:
an invalid/missing body never releases a claim, and a separately retained
diagnostic never resolves an earlier ambiguous start. No source body, provider,
credential, financial value, native SID, QC job or outcome is opened here.
Callers own input custody and any private, write-confined ledger publication.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
import hashlib
import json
import re
import weakref

from research.insider_buying.sec_quarter_master_index import (
    SecQuarterMasterIndexError, SecQuarterMasterIndexReceipt,
)


SCHEMA = "insider-pilot-sec-parent-coverage-reuse-audit-v1"
EXPOSURE_SCHEMA = "insider-original-parent-prior-exposure-inventory-v1"
CANDIDATE_SCHEMA = "insider-pilot-sec-retained-exposure-v1/candidates"
PERIODS = tuple(f"{year}Q{quarter}" for year in range(2020, 2027)
                for quarter in range(1, 5) if (year, quarter) <= (2026, 1))
PILOT_PERIODS = tuple(period for period in PERIODS if "2021Q1" <= period <= "2025Q4")
FORMS = ("3", "3/A", "4", "4/A", "5", "5/A")
MAX_QUARTER_ROWS = 250_000
MAX_INVENTORY_BYTES = 128 * 1024 * 1024
MAX_EXPOSURES = 250_000
MAX_CANDIDATES = 250_000
MAX_EVIDENCE_PER_ACCESSION = 1024
MAX_ROW_BYTES = 32 * 1024
MAX_SUMMARY_BYTES = 2 * 1024 * 1024
MAX_BODY_BYTES = 8 * 1024 * 1024
SOURCE_FRAMING = "sha256_of_canonical_json_each_row_plus_one_lf_in_quarter_then_source_order"
LEDGER_FRAMING = "sha256_of_canonical_json_each_disposition_plus_one_lf_in_quarter_then_source_order"
QUEUE_FRAMING = "sha256_of_canonical_json_each_candidate_request_plus_one_lf_in_source_order"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ACCESSION = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z")
_CIK = re.compile(r"[0-9]{1,10}\Z")
_ROOT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,100}\Z")
_PATH = re.compile(r"edgar/data/([0-9]{1,10})/([0-9]{10}-[0-9]{2}-[0-9]{6})\.txt\Z")
_STATES = frozenset({"completed", "reserved", "started", "ambiguous", "refused", "reused"})
_SOURCE_KEYS = frozenset({"period", "source_record_ordinal", "accession_number", "form_type", "raw_filing_date",
    "filing_date", "raw_issuer_cik", "issuer_comparison_key", "short_cik", "accession_year_mismatch",
    "raw_symbol_label", "accession_key_sha256", "quarterly_zip_sha256", "submission_member_sha256",
    "submission_header_line_sha256", "schema_profile_sha256", "filing_metadata_sha256"})
_CANDIDATE_KEYS = frozenset({"root_id", "control_name", "control_sha256", "request_sha256", "request",
    "request_url", "retained_target", "raw_object", "body_currently_hash_verified", "complete_parent_parsed_here"})
_REQUEST_KEYS = frozenset({"accession_number", "period", "filing_date", "form_type", "issuer_cik", "url", "archive_path",
    "master_source_sha256", "parsed_lineage_hash", "submission_row_id", "filing_date_raw", "quarterly_zip_sha256",
    "raw_lineage_sha256", "raw_snapshot_id", "source_record_ordinal", "accession_key_sha256", "filing_metadata_sha256",
    "submission_inventory_sha256", "submission_member_sha256", "master_decoded_sha256", "master_receipt_sha256",
    "submission_header_line_sha256", "schema_profile_sha256"})
_AUTHORITY = {key: False for key in ("source_authenticated", "official_acceptance_verified", "publication_time_verified",
    "point_in_time_data", "rights_verified", "canonical_evidence", "complete_corpus", "direct_ib1c_ingest_authorized",
    "dispatch_enabled", "qc_authorized", "backtest_authorized", "execution_authorized")}
_AUTHORITY.update({key: 0 for key in ("sec_dispatches", "outcome_looks", "qc_jobs", "backtests")})
_COUNTS = ("source_filings", "context_filings", "target_filings", "prior_consumed_filings", "prior_consumed_targets",
    "ambiguous_consumption_targets", "no_prior_dispatch_observed_targets", "locator_qualified_targets",
    "locator_quarantined_targets", "fresh_locatable_candidate_requests", "retained_candidate_targets",
    "hash_verified_matching_body_candidate_targets", "unverified_matching_body_candidate_targets",
    "candidate_identity_conflict_targets", "candidate_body_identity_conflict_targets",
    "consumed_without_matching_verified_body_candidate_targets",
    "cross_quarter_repeat_filings", "cross_quarter_repeat_targets", "cross_quarter_identity_conflict_filings")
_TOKEN = object()
_SEALS = weakref.WeakKeyDictionary()


class PilotSecParentAuditError(ValueError):
    """Fixed refusal categories; never private rows, paths or exceptions."""


def _need(value, code):
    if not value:
        raise PilotSecParentAuditError(code)


def _raw(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _digest(value):
    _need(type(value) is str and _SHA.fullmatch(value) is not None, "digest_required")
    return value


def _accession(value):
    _need(type(value) is str and _ACCESSION.fullmatch(value) is not None, "accession_refused")
    return value


def _cik(value):
    _need(type(value) is str and _CIK.fullmatch(value) is not None and int(value) > 0, "issuer_cik_refused")
    return value.zfill(10)


def _relative(value):
    _need(type(value) is str and 0 < len(value) <= 1024 and "\\" not in value
          and not value.startswith("/") and all(part not in {"", ".", ".."} for part in value.split("/"))
          and len(value.split("/")) <= 16 and not any(ord(char) < 32 for char in value), "relative_metadata_path_refused")


def _json(raw, expected):
    _need(type(raw) is bytes and 0 < len(raw) <= MAX_INVENTORY_BYTES, "inventory_byte_bound_refused")
    _need(_sha(raw) == _digest(expected), "inventory_hash_refused")
    def pairs(items):
        result = {}
        for key, value in items:
            _need(key not in result, "duplicate_json_key_refused")
            result[key] = value
        return result
    try:
        body = json.loads(raw, object_pairs_hook=pairs, parse_float=lambda _: _need(False, "floating_metadata_refused"),
            parse_constant=lambda _: _need(False, "nonfinite_metadata_refused"))
        _need(type(body) is dict and _raw(body) == raw, "canonical_inventory_required")
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise PilotSecParentAuditError("inventory_json_refused") from None
    return body


def _authority(value):
    _need(type(value) is dict and set(value) == set(_AUTHORITY)
          and all(type(value[key]) is type(expected) and value[key] == expected for key, expected in _AUTHORITY.items()),
          "zero_authority_required")


def _exposures(body):
    _need(set(body) == {"schema", "records"} and body["schema"] == EXPOSURE_SCHEMA
          and type(body["records"]) is list and len(body["records"]) <= MAX_EXPOSURES, "exposure_schema_refused")
    result, previous = {}, ""
    for row in body["records"]:
        _need(type(row) is dict and set(row) == {"accession_number", "accession_key_sha256", "evidence"},
              "exposure_record_schema_refused")
        accession = _accession(row["accession_number"])
        _need(previous < accession and row["accession_key_sha256"] == _sha(accession.encode("ascii")),
              "exposure_order_or_accession_key_refused")
        evidence = row["evidence"]
        _need(type(evidence) is list and 1 <= len(evidence) <= MAX_EVIDENCE_PER_ACCESSION, "exposure_evidence_bound_refused")
        prior = None
        for item in evidence:
            _need(type(item) is dict and set(item) == {"root_id", "journal_sha256", "state"}
                  and type(item["root_id"]) is str and _ROOT.fullmatch(item["root_id"])
                  and type(item["state"]) is str and item["state"] in _STATES, "exposure_evidence_refused")
            _digest(item["journal_sha256"])
            ordering = (item["root_id"], item["journal_sha256"], item["state"])
            _need(prior is None or prior < ordering, "exposure_evidence_order_refused")
            prior = ordering
        result[accession], previous = evidence, accession
    return result


def _candidate_inventory(body):
    _need(set(body) == {"schema", "fixture_only", "records", "masters", "authority"}
          and body["schema"] == CANDIDATE_SCHEMA and type(body["fixture_only"]) is bool
          and type(body["records"]) is list and len(body["records"]) <= MAX_CANDIDATES
          and type(body["masters"]) is list and len(body["masters"]) <= 82, "candidate_inventory_schema_refused")
    _authority(body["authority"])
    # Master descriptors are not locator receipts: the caller must separately
    # hash/decompress/parse them before supplying master_for_period metadata.
    for row in body["masters"]:
        _need(type(row) is dict and set(row) == {"root_id", "control_name", "control_sha256", "period", "source_url",
              "raw_object", "producer_receipt", "body_currently_hash_verified", "master_decoded_here"}
              and type(row["period"]) is str and re.fullmatch(r"20[0-9]{2}Q[1-4]", row["period"])
              and row["source_url"] == f"https://www.sec.gov/Archives/edgar/full-index/{row['period'][:4]}/QTR{row['period'][-1]}/master.gz"
              and type(row["producer_receipt"]) is dict and row["master_decoded_here"] is False,
              "master_descriptor_schema_refused")
        _descriptor_common(row, master=True)
    result, previous, count = {}, "", 0
    for record in body["records"]:
        _need(type(record) is dict and set(record) == {"accession_number", "candidates"}, "candidate_record_schema_refused")
        accession = _accession(record["accession_number"])
        _need(previous < accession and type(record["candidates"]) is list
              and 1 <= len(record["candidates"]) <= MAX_EVIDENCE_PER_ACCESSION, "candidate_order_or_bound_refused")
        seen = set()
        for item in record["candidates"]:
            _need(type(item) is dict and set(item) == _CANDIDATE_KEYS, "candidate_descriptor_schema_refused")
            _descriptor_common(item)
            target, request = item["retained_target"], item["request"]
            _need(type(target) is dict and set(target) == {"accession_number", "period", "filing_date", "form_type", "issuer_cik"}
                  and all(type(value) is str for value in target.values()) and target["accession_number"] == accession
                  and re.fullmatch(r"20[0-9]{2}Q[1-4]", target["period"])
                  and target["form_type"] in {"4", "4/A"}, "candidate_target_refused")
            _cik(target["issuer_cik"]);_date(target["filing_date"], target["period"])
            _need(type(request) is dict and set(request) <= _REQUEST_KEYS and set(target) <= set(request)
                  and all(type(value) is str and len(value) <= 2048 and not any(ord(char) < 32 for char in value)
                      if key != "source_record_ordinal" else type(value) is int and 1 <= value <= MAX_QUARTER_ROWS
                      for key, value in request.items()) and len(_raw(request)) <= MAX_ROW_BYTES
                  and _sha(_raw(request)) == _digest(item["request_sha256"])
                  and item["complete_parent_parsed_here"] is False, "candidate_request_hash_or_scope_refused")
            for key in target:
                _need(key not in request or request[key] == target[key], "candidate_request_target_conflict")
            if "url" in request:
                _need(request["url"] == item["request_url"], "candidate_request_url_conflict")
            path = item["request_url"]
            _need(type(path) is str and path.startswith("https://www.sec.gov/Archives/"), "candidate_url_refused")
            match = _PATH.fullmatch(path.removeprefix("https://www.sec.gov/Archives/"))
            _need(match is not None and int(match.group(1)) > 0 and match.group(2) == accession, "candidate_url_accession_refused")
            identity = (item["root_id"], item["control_name"], item["control_sha256"], item["raw_object"]["sha256"])
            _need(identity not in seen, "candidate_duplicate_evidence_refused")
            seen.add(identity);count += 1
            _need(count <= MAX_CANDIDATES, "candidate_total_bound_refused")
        result[accession], previous = record["candidates"], accession
    return result


def _descriptor_common(item, *, master=False):
    _need(type(item["root_id"]) is str and _ROOT.fullmatch(item["root_id"])
          and type(item["body_currently_hash_verified"]) is bool, "descriptor_root_or_hash_fact_refused")
    _relative(item["control_name"]);_digest(item["control_sha256"])
    raw = item["raw_object"]
    _need(type(raw) is dict and set(raw) == {"relative_path", "sha256", "size_bytes"}
          and type(raw["size_bytes"]) is int and 0 < raw["size_bytes"] <= (64 * 1024 * 1024 if master else MAX_BODY_BYTES),
          "raw_object_descriptor_refused")
    _relative(raw["relative_path"]);_digest(raw["sha256"])


def _date(value, period):
    try:
        parsed = date.fromisoformat(value)
    except (ValueError, TypeError):
        raise PilotSecParentAuditError("filing_date_refused") from None
    _need(parsed.isoformat() == value and f"{parsed.year:04d}Q{(parsed.month-1)//3+1}" == period,
          "filing_quarter_refused")
    return parsed


def _source(row):
    _need(type(row) is dict and set(row) == _SOURCE_KEYS, "source_row_schema_refused")
    _need(type(row["period"]) is str and row["period"] in PERIODS and type(row["source_record_ordinal"]) is int
          and 1 <= row["source_record_ordinal"] <= MAX_QUARTER_ROWS
          and type(row["form_type"]) is str and row["form_type"] in FORMS,
          "source_context_or_ordinal_refused")
    accession = _accession(row["accession_number"])
    _need(row["accession_key_sha256"] == _sha(accession.encode("ascii")), "source_accession_key_refused")
    comparison = _cik(row["raw_issuer_cik"])
    _need(row["issuer_comparison_key"] == comparison and type(row["short_cik"]) is bool
          and row["short_cik"] is (len(row["raw_issuer_cik"]) < 10), "source_raw_cik_refused")
    filed = _date(row["filing_date"], row["period"])
    raw_date = row["raw_filing_date"]
    english_month = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")[filed.month-1]
    _need(type(raw_date) is str and (raw_date == filed.isoformat()
          or raw_date == f"{filed.day:02d}-{english_month}-{filed.year:04d}"),
          "source_raw_filing_date_refused")
    mismatch = int(accession[11:13]) != filed.year % 100
    _need(type(row["accession_year_mismatch"]) is bool and row["accession_year_mismatch"] is mismatch,
          "source_accession_year_fact_refused")
    label = row["raw_symbol_label"]
    _need(type(label) is str and len(label.encode()) <= 4096 and not any(ord(char) < 32 for char in label),
          "source_symbol_label_refused")
    for key in ("quarterly_zip_sha256", "submission_member_sha256", "submission_header_line_sha256", "schema_profile_sha256"):
        _digest(row[key])
    _need(row["filing_metadata_sha256"] == _sha(_raw({key: value for key, value in row.items() if key != "filing_metadata_sha256"})),
          "source_metadata_hash_refused")
    raw = _raw(row)
    _need(len(raw) + 1 <= MAX_ROW_BYTES, "source_row_byte_bound_refused")
    return json.loads(raw), raw + b"\n"


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class PilotSecParentAudit:
    _raw_bytes: bytes = field(repr=False)
    _token: object = field(repr=False)

    def canonical_bytes(self):
        _need(type(self) is PilotSecParentAudit and self._token is _TOKEN
              and _SEALS.get(self) == self._raw_bytes, "genuine_unchanged_audit_required")
        return self._raw_bytes

    def to_payload(self):
        return json.loads(self.canonical_bytes())

    @property
    def sha256(self):
        return _sha(self.canonical_bytes())


def validate_pilot_sec_parent_audit(value):
    _need(type(value) is PilotSecParentAudit, "genuine_audit_type_required")
    return value.to_payload()


class PilotSecParentAuditCompiler:
    """One-pass metadata compiler; any failed/partial callback poisons the run.

    ``master_for_period`` supplies an independently held, parsed genuine
    receipt once per quarter. ``emit_row`` receives a detached metadata copy;
    it is not an output-custody or source-authentication assertion. The full
    ledger/queue digests cover all rows, not just the bounded previews.
    """

    def __init__(self, *, exposure_raw, expected_exposure_sha256, candidates_raw, expected_candidates_sha256,
                 master_for_period=None, emit_row=None, maximum_preview=64):
        _need(master_for_period is None or callable(master_for_period), "master_metadata_callback_refused")
        _need(emit_row is None or callable(emit_row), "ledger_callback_refused")
        _need(type(maximum_preview) is int and 0 <= maximum_preview <= 256, "preview_bound_refused")
        self._exposures = _exposures(_json(exposure_raw, expected_exposure_sha256))
        candidates = _json(candidates_raw, expected_candidates_sha256)
        self._candidates = _candidate_inventory(candidates)
        _need(set(self._candidates) <= set(self._exposures), "retained_candidate_without_consumption_refused")
        self._fixture = candidates["fixture_only"]
        self._input_hashes = {"exposure_inventory_sha256": expected_exposure_sha256,
                              "retained_candidate_inventory_sha256": expected_candidates_sha256}
        self._master_for_period, self._emit, self._preview_bound = master_for_period, emit_row, maximum_preview
        self._closed = self._failed = self._busy = False
        # One compact source identity per unique accession, not parent bodies
        # or all disposition rows. Repeated source occurrences are conserved.
        self._seen = {}
        self._quarter_seen = set()
        self._cross_quarter_repeats = 0
        self._quarter, self._master, self._aliases, self._master_digest = None, None, {}, None
        self._quarters = {}
        self._source_digest, self._ledger_digest, self._queue_digest = (hashlib.sha256() for _ in range(3))
        self._source_bytes = self._ledger_bytes = self._queue_bytes = 0
        self._preview = []

    def _active(self):
        _need(not self._closed and not self._failed and not self._busy, "compiler_not_active")

    def _check_master(self):
        if self._master is not None:
            try:
                self._master.__post_init__()
            except (SecQuarterMasterIndexError, TypeError, ValueError):
                raise PilotSecParentAuditError("master_receipt_changed") from None
            _need(_sha(_raw(self._master.to_payload())) == self._master_digest, "master_receipt_changed")

    def _begin(self, period):
        self._check_master()
        _need(self._quarter is None or PERIODS.index(period) > PERIODS.index(self._quarter), "source_quarter_order_refused")
        master = None if self._master_for_period is None else self._master_for_period(period)
        _need(master is None or type(master) is SecQuarterMasterIndexReceipt, "genuine_master_receipt_required")
        self._quarter, self._master, self._aliases = period, master, defaultdict(list)
        self._quarter_seen = set()
        self._master_digest = None
        if master is not None:
            try:
                master.__post_init__()
            except (SecQuarterMasterIndexError, TypeError, ValueError):
                raise PilotSecParentAuditError("master_receipt_refused") from None
            _need(f"{master.year:04d}Q{master.quarter}" == period, "master_quarter_refused")
            self._master_digest = _sha(_raw(master.to_payload()))
            for alias in master.rows:
                self._aliases[alias.accession_number].append(alias.to_payload())
        self._quarters[period] = {"count": 0, "forms": Counter(), "counts": Counter({key: 0 for key in _COUNTS}),
            "source_hash": hashlib.sha256(), "source_bytes": 0, "ledger_hash": hashlib.sha256(), "ledger_bytes": 0,
            "queue_hash": hashlib.sha256(), "queue_bytes": 0, "anchors": None}

    def _locator(self, row):
        aliases = self._aliases.get(row["accession_number"], [])
        reasons, selected = [], None
        if self._master is None:
            reasons.append("quarter_master_not_supplied")
        elif not aliases:
            reasons.append("master_locator_missing")
        elif any(alias["form_type"] != row["form_type"] for alias in aliases):
            reasons.append("master_form_disagreement")
        elif any(alias["filing_date"] != row["filing_date"] for alias in aliases):
            reasons.append("master_filing_date_disagreement")
        elif len(aliases) == 1:
            selected = aliases[0]
        else:
            matching = [alias for alias in aliases if _cik(_PATH.fullmatch(alias["archive_path"]).group(1)) == row["issuer_comparison_key"]]
            if len(matching) == 1:
                selected = matching[0]
            else:
                reasons.append("multiple_master_aliases_without_unique_issuer_path")
        request = target = None
        if selected is not None:
            request = {"period": row["period"], "accession_number": row["accession_number"], "form_type": row["form_type"],
                "filing_date": row["filing_date"], "issuer_cik": row["raw_issuer_cik"], "archive_path": selected["archive_path"],
                "url": "https://www.sec.gov/Archives/" + selected["archive_path"], "source_record_ordinal": row["source_record_ordinal"],
                "filing_metadata_sha256": row["filing_metadata_sha256"], "quarterly_zip_sha256": row["quarterly_zip_sha256"],
                "submission_member_sha256": row["submission_member_sha256"], "submission_header_line_sha256": row["submission_header_line_sha256"],
                "schema_profile_sha256": row["schema_profile_sha256"], "master_decoded_sha256": self._master.source_sha256,
                "master_receipt_sha256": self._master.receipt_sha256}
            target = {key: request[key] for key in ("period", "accession_number", "form_type", "filing_date", "issuer_cik")}
            target.update(quarterly_index_sha256=self._master.source_sha256, complete_submission_url=request["url"])
        return aliases, selected, reasons, request, target

    def consume(self, supplied):
        self._active();self._busy = True
        try:
            row, source_line = _source(supplied)
            if row["period"] != self._quarter:
                self._begin(row["period"])
            quarter = self._quarters[self._quarter]
            _need(row["source_record_ordinal"] == quarter["count"] + 1, "source_ordinal_gap_or_repeat_refused")
            accession_key = bytes.fromhex(row["accession_key_sha256"])
            prior = self._seen.get(accession_key)
            _need(accession_key not in self._quarter_seen, "within_quarter_duplicate_accession_refused")
            self._quarter_seen.add(accession_key)
            identity = _sha(_raw({key: row[key] for key in ("accession_number", "form_type", "filing_date", "issuer_comparison_key")}))
            prior_occurrence = None if prior is None else {"period": prior[0], "source_record_ordinal": prior[1],
                "filing_metadata_sha256": prior[2].hex()}
            repeated, source_conflict = prior is not None, prior is not None and prior[3].hex() != identity
            if prior is None:
                self._seen[accession_key] = (row["period"], row["source_record_ordinal"],
                    bytes.fromhex(row["filing_metadata_sha256"]), bytes.fromhex(identity))
            else:
                self._cross_quarter_repeats += 1
            anchors = {key: row[key] for key in ("quarterly_zip_sha256", "submission_member_sha256", "submission_header_line_sha256", "schema_profile_sha256")}
            _need(quarter["anchors"] is None or quarter["anchors"] == anchors, "quarter_source_anchors_changed")
            quarter["anchors"] = anchors
            evidence = self._exposures.get(row["accession_number"], [])
            candidates = self._candidates.get(row["accession_number"], [])
            relevant = row["form_type"] in {"4", "4/A"}
            matches, conflicts = [], []
            for item in candidates:
                target, retained_request = item["retained_target"], item["request"]
                same = (all(target[key] == row[key] for key in ("period", "accession_number", "form_type", "filing_date"))
                        and _cik(target["issuer_cik"]) == row["issuer_comparison_key"]
                        and all(key not in retained_request or retained_request[key] == row[key]
                            for key in ("source_record_ordinal", "quarterly_zip_sha256", "submission_member_sha256",
                                "submission_header_line_sha256", "schema_profile_sha256", "filing_metadata_sha256")))
                (matches if same else conflicts).append(item)
            body_conflict = len({(item["raw_object"]["sha256"], item["raw_object"]["size_bytes"]) for item in matches}) > 1
            verified = [] if conflicts or body_conflict or repeated else [item for item in matches if item["body_currently_hash_verified"]]
            ambiguous = any(item["state"] == "ambiguous" for item in evidence)
            aliases, selected, reasons, request, target = self._locator(row) if relevant else ([], None, [], None, None)
            fresh = relevant and not evidence and request is not None and not repeated
            disposition = ("context_retained_not_parent_candidate" if not relevant else
                "cross_quarter_repeat_retained_parent_target_quarantined" if repeated else
                "prior_consumed_with_matching_hash_verified_body_candidate" if verified else
                "prior_consumed_without_matching_hash_verified_body_candidate" if evidence else
                "no_prior_dispatch_observed_locator_quarantined" if request is None else
                "no_prior_dispatch_observed_locatable_candidate")
            output = {"schema": SCHEMA + "/filing", "source": row, "source_record_sha256": row["filing_metadata_sha256"],
                "relevant_parent_target": relevant, "prior_consumed": bool(evidence), "prior_exposure_evidence": evidence,
                "prior_source_occurrence": prior_occurrence, "cross_quarter_accession_repeat": repeated,
                "cross_quarter_source_identity_conflict": source_conflict,
                "historical_ambiguous_start_preserved": ambiguous, "candidate_identity_conflicts": conflicts,
                "retained_candidate_body_identity_conflict": body_conflict,
                "matching_retained_candidates": matches, "body_candidate_is_not_parent_admission": True,
                "complete_parent_parsed_here": False, "disposition": disposition,
                "master_aliases": aliases, "selected_locator": selected, "locator_quarantine_reasons": reasons,
                "pre_normalization_target": target, "request": request,
                "request_sha256": None if request is None else _sha(_raw(request)),
                "fresh_locatable_candidate": fresh, "dispatch_authorized": False, "canonical_admitted": False}
            ledger_line = _raw(output) + b"\n"
            _need(len(ledger_line) <= MAX_ROW_BYTES * (MAX_EVIDENCE_PER_ACCESSION + 2), "ledger_row_byte_bound_refused")
            counts = quarter["counts"]
            counts["source_filings"] += 1;counts["target_filings" if relevant else "context_filings"] += 1
            counts["prior_consumed_filings"] += bool(evidence)
            counts["cross_quarter_repeat_filings"] += repeated
            counts["cross_quarter_repeat_targets"] += repeated and relevant
            counts["cross_quarter_identity_conflict_filings"] += source_conflict
            if relevant:
                for key, flag in (("prior_consumed_targets", bool(evidence)), ("ambiguous_consumption_targets", ambiguous),
                    ("no_prior_dispatch_observed_targets", not evidence), ("locator_qualified_targets", selected is not None),
                    ("locator_quarantined_targets", selected is None), ("fresh_locatable_candidate_requests", fresh),
                    ("retained_candidate_targets", bool(candidates)), ("hash_verified_matching_body_candidate_targets", bool(verified)),
                    ("unverified_matching_body_candidate_targets", any(not item["body_currently_hash_verified"] for item in matches)),
                    ("candidate_identity_conflict_targets", bool(conflicts)),
                    ("candidate_body_identity_conflict_targets", body_conflict),
                    ("consumed_without_matching_verified_body_candidate_targets", bool(evidence) and not verified)):
                    counts[key] += flag
            quarter["count"] += 1;quarter["forms"][row["form_type"]] += 1
            quarter["source_hash"].update(source_line);quarter["source_bytes"] += len(source_line)
            quarter["ledger_hash"].update(ledger_line);quarter["ledger_bytes"] += len(ledger_line)
            self._source_digest.update(source_line);self._source_bytes += len(source_line)
            self._ledger_digest.update(ledger_line);self._ledger_bytes += len(ledger_line)
            if fresh:
                queue_line = _raw(request) + b"\n"
                quarter["queue_hash"].update(queue_line);quarter["queue_bytes"] += len(queue_line)
                self._queue_digest.update(queue_line);self._queue_bytes += len(queue_line)
                if len(self._preview) < self._preview_bound:
                    self._preview.append({"request": request, "request_sha256": _sha(_raw(request)), "pre_normalization_target": target})
            if self._emit is not None:
                self._emit(json.loads(ledger_line))
        except BaseException:
            self._failed = True
            raise
        finally:
            self._busy = False

    def finish(self, roster):
        self._active();self._busy = True
        try:
            from research import insider_buying_pilot_sec_roster as source
            body = source.validate_pilot_sec_roster(roster).to_payload()
            _need(body["fixture_only"] is self._fixture and body["source_row_digest_framing"] == SOURCE_FRAMING,
                  "source_roster_scope_refused")
            _need(body["source_row_jsonl_sha256"] == self._source_digest.hexdigest()
                  and body["source_row_jsonl_bytes"] == self._source_bytes, "full_source_stream_roster_mismatch")
            _need(type(body["quarters"]) is list and [row["period"] for row in body["quarters"]] == list(PERIODS),
                  "complete_25quarter_roster_required")
            self._check_master()
            quarters = []
            for expected in body["quarters"]:
                period = expected["period"]
                quarter = self._quarters.get(period)
                _need(quarter is not None, "source_quarter_missing")
                _need(expected["submission_rows"] == quarter["count"]
                      and expected["source_form_counts"] == {form: quarter["forms"][form] for form in FORMS}
                      and expected["source_row_jsonl_sha256"] == quarter["source_hash"].hexdigest()
                      and expected["source_row_jsonl_bytes"] == quarter["source_bytes"], "quarter_source_stream_roster_mismatch")
                for key, anchor in (("zip_sha256", "quarterly_zip_sha256"), ("submission_member_sha256", "submission_member_sha256"),
                                    ("submission_header_line_sha256", "submission_header_line_sha256")):
                    _need(expected[key] == quarter["anchors"][anchor], "source_roster_anchor_mismatch")
                _need(quarter["anchors"]["schema_profile_sha256"] == body["schema_profile_sha256"], "source_profile_mismatch")
                counts = dict(quarter["counts"])
                _need(counts["source_filings"] == counts["context_filings"] + counts["target_filings"]
                      and counts["target_filings"] == counts["prior_consumed_targets"] + counts["no_prior_dispatch_observed_targets"]
                      and counts["target_filings"] == counts["locator_qualified_targets"] + counts["locator_quarantined_targets"],
                      "filing_partition_conservation_refused")
                quarters.append({"period": period, "counts": counts, "source_form_counts": expected["source_form_counts"],
                    "source_row_jsonl_sha256": quarter["source_hash"].hexdigest(), "source_row_jsonl_bytes": quarter["source_bytes"],
                    "disposition_jsonl_sha256": quarter["ledger_hash"].hexdigest(), "disposition_jsonl_bytes": quarter["ledger_bytes"],
                    "fresh_request_jsonl_sha256": quarter["queue_hash"].hexdigest(), "fresh_request_jsonl_bytes": quarter["queue_bytes"]})
            aggregate = lambda selected: {key: sum(row["counts"][key] for row in selected) for key in _COUNTS}
            result = {"schema": SCHEMA, "fixture_only": self._fixture, "source_roster_sha256": roster.sha256,
                **self._input_hashes, "quarters": quarters, "context_counts": aggregate(quarters),
                "pilot_counts": aggregate([row for row in quarters if row["period"] in PILOT_PERIODS]),
                "source_row_jsonl_sha256": self._source_digest.hexdigest(), "source_row_jsonl_bytes": self._source_bytes,
                "source_row_digest_framing": SOURCE_FRAMING, "disposition_jsonl_sha256": self._ledger_digest.hexdigest(),
                "disposition_jsonl_bytes": self._ledger_bytes, "disposition_digest_framing": LEDGER_FRAMING,
                "fresh_request_jsonl_sha256": self._queue_digest.hexdigest(), "fresh_request_jsonl_bytes": self._queue_bytes,
                "fresh_request_digest_framing": QUEUE_FRAMING, "maximum_preview": self._preview_bound, "fresh_request_preview": self._preview,
                "candidate_queue_requires_cross_quarter_repeat_reconciliation": self._cross_quarter_repeats > 0,
                "first_seen_candidates_are_provisional_if_later_accession_repeats": True,
                "source_accession_occurrences_are_not_globally_deduplicated": True,
                "global_consumed_accessions": len(self._exposures), "retained_candidate_accessions": len(self._candidates),
                "coverage_scope": "explicit_known_retained_operational_roots_not_proof_of_no_unjournaled_access",
                "retained_body_hash_verification_is_not_complete_parent_admission": True,
                "retained_candidate_join_policy": "exact_accession_form_filing_date_period_cik_comparison_and_every_available_source_record_anchor",
                "separate_diagnostic_does_not_resolve_original_ambiguous_start": True,
                "native_sid_required_for_accession_custody": False, "raw_source_cik_rewritten": False,
                "financial_values_interpreted_or_projected": False, "full_parent_bodies_opened_here": 0,
                "authority": dict(_AUTHORITY)}
            raw = _raw(result);_need(len(raw) <= MAX_SUMMARY_BYTES, "summary_byte_bound_refused")
            value = PilotSecParentAudit(raw, _TOKEN);_SEALS[value] = raw
            self._closed = True
            return value
        except BaseException:
            self._failed = True
            raise
        finally:
            self._busy = False
