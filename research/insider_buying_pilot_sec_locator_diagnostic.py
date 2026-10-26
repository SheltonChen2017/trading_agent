"""Pure all-form master metadata diagnosis of a pinned pilot quarantine.

Supplied whole-control and master hashes are external caller roots, not
source authenticity, custody, historical availability, rights or permission.
No file, original body, transport, credential, outcome or QC access exists.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import hashlib
import json
import re
import weakref

from research import insider_buying_pilot_sec_parent_audit as audit
from research import insider_buying_pilot_sec_fresh_selection as fresh
from research.insider_buying import sec_quarter_master_index as master


SCHEMA = "insider-pilot-sec-full-master-locator-diagnostic-v1"
PRIOR_SCHEMA = "insider-pilot-sec-fresh-selection-observer-v1"
PRIOR_AUDIT_ID = "ib-pilot-sec-first64-selection-20261025-once"
MAX_COMPLETE_BYTES = 4 * 1024 * 1024
MAX_MATCHING_ROWS = 4096
MAX_FORM_TYPES = 4096
MAX_RESULT_BYTES = 16 * 1024 * 1024
COLUMNS = ("CIK", "Company Name", "Form Type", "Date Filed", "Filename")
_TOKEN = object()
_SEALS = weakref.WeakKeyDictionary()
_RAW, _SHA = audit._raw, audit._sha
_WORKER_KEYS = frozenset({"schema", "audit_id", "registration", "registration_sha256", "execution_identity",
    "prior_audit_complete_sha256", "exposure_inventory_sha256", "exposure_snapshot_sha256", "retained_body_inventory_sha256",
    "selection", "selection_sha256", "source_roster", "parent_audit", "locator_quarantines",
    "locator_quarantine_jsonl_sha256", "locator_quarantine_jsonl_bytes", "native_network_fork_allwrite_securityexec_denial",
    "new_provider_requests", "credential_reads", "qc_accesses", "outcome_looks", "backtests",
    "dispatch_authorized", "canonical_admitted", "backtesting_ready"})
_REGISTRATION_KEYS = frozenset({"schema", "audit_id", "prior_audit_id", "prior_audit_pins", "selection_period",
    "selection_limit", "selection_policy", "full_source_scope", "locator_quarantines",
    "whole_stream_and_operational_inputs_must_equal_completed_audit", "new_provider_requests", "credential_reads", "qc_accesses",
    "outcome_looks", "backtests", "backtesting_ready", "worker_invocations",
    "native_worker_network_fork_allwrite_securityexec_denial", "trusted_parent_not_native_isolation"})
_BOOL_KEYS = ("relevant_parent_target", "prior_consumed", "cross_quarter_accession_repeat",
    "cross_quarter_source_identity_conflict", "historical_ambiguous_start_preserved", "retained_candidate_body_identity_conflict",
    "body_candidate_is_not_parent_admission", "complete_parent_parsed_here", "fresh_locatable_candidate",
    "dispatch_authorized", "canonical_admitted")


class PilotSecLocatorDiagnosticError(ValueError):
    """Fixed source-independent refusal codes."""


def _need(condition, code):
    if not condition:
        raise PilotSecLocatorDiagnosticError(code)


def _digest(value):
    _need(type(value) is str and audit._SHA.fullmatch(value) is not None, "locator_external_digest_required")
    return value


def _decode(raw, digest):
    _need(type(raw) is bytes and 0 < len(raw) <= MAX_COMPLETE_BYTES
        and _SHA(raw) == _digest(digest), "locator_complete_bytes_or_hash")
    def pairs(items):
        result = {}
        for key, value in items:
            _need(key not in result, "locator_duplicate_control_key")
            result[key] = value
        return result
    try:
        body = json.loads(raw, object_pairs_hook=pairs,
            parse_float=lambda _: _need(False, "locator_floating_control"),
            parse_constant=lambda _: _need(False, "locator_nonfinite_control"))
        _need(type(body) is dict and _RAW(body) == raw, "locator_canonical_control_required")
        return body
    except PilotSecLocatorDiagnosticError:
        raise
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise PilotSecLocatorDiagnosticError("locator_control_decode_refused") from None


def _quarantine(row):
    _need(type(row) is dict and set(row) == fresh._DISPOSITION_KEYS
        and row["schema"] == audit.SCHEMA + "/filing", "locator_quarantine_schema")
    source, _ = audit._source(row["source"])
    _need(all(type(row[key]) is bool for key in _BOOL_KEYS), "locator_quarantine_boolean")
    _need(source["form_type"] in {"4", "4/A"} and row["source_record_sha256"] == source["filing_metadata_sha256"]
        and row["relevant_parent_target"] is True and row["selected_locator"] is None
        and row["request"] is None and row["request_sha256"] is None and row["pre_normalization_target"] is None
        and row["body_candidate_is_not_parent_admission"] is True and row["complete_parent_parsed_here"] is False
        and row["fresh_locatable_candidate"] is False and row["dispatch_authorized"] is False
        and row["canonical_admitted"] is False, "locator_quarantine_identity_or_authority")
    # Exact captured-selector scope, not a generic relaxation of prior claims.
    _need(row["prior_consumed"] is False and row["prior_exposure_evidence"] == []
        and row["historical_ambiguous_start_preserved"] is False and row["prior_source_occurrence"] is None
        and row["cross_quarter_accession_repeat"] is False and row["cross_quarter_source_identity_conflict"] is False
        and row["candidate_identity_conflicts"] == [] and row["matching_retained_candidates"] == []
        and row["retained_candidate_body_identity_conflict"] is False
        and row["disposition"] == "no_prior_dispatch_observed_locator_quarantined", "locator_prior_consumption_scope")
    _need(type(row["locator_quarantine_reasons"]) is list and len(row["locator_quarantine_reasons"]) == 1
        and row["locator_quarantine_reasons"][0] in {"master_locator_missing", "master_form_disagreement",
            "master_filing_date_disagreement", "multiple_master_aliases_without_unique_issuer_path"}, "locator_prior_reason")
    aliases = row["master_aliases"]
    _need(type(aliases) is list and len(aliases) <= audit.MAX_EVIDENCE_PER_ACCESSION, "locator_prior_alias_bound")
    for value in aliases:
        _need(type(value) is dict and set(value) == {"accession_number", "form_type", "filing_date", "archive_path"},
            "locator_prior_alias_schema")
        _need(master.SecMasterIndexRow(**value).to_payload() == value
            and value["accession_number"] == source["accession_number"], "locator_prior_alias_identity")
    return source


def _completed_row(raw, expected, index, row_sha):
    complete = _decode(raw, expected)
    _need(set(complete) == {"schema", "audit_id", "reservation_sha256", "terminal_sha256", "worker_result"}
        and complete["schema"] == PRIOR_SCHEMA + "/complete" and complete["audit_id"] == PRIOR_AUDIT_ID,
        "locator_protected_complete_schema")
    _digest(complete["reservation_sha256"]);_digest(complete["terminal_sha256"])
    worker = complete["worker_result"]
    _need(type(worker) is dict and set(worker) == _WORKER_KEYS and worker["schema"] == PRIOR_SCHEMA
        and worker["audit_id"] == PRIOR_AUDIT_ID and type(worker["registration"]) is dict
        and set(worker["registration"]) == _REGISTRATION_KEYS
        and worker["registration_sha256"] == _SHA(_RAW(worker["registration"]))
        and worker["registration"].get("schema") == PRIOR_SCHEMA + "/registration"
        and worker["registration"].get("audit_id") == PRIOR_AUDIT_ID
        and worker["registration"].get("selection_period") == fresh.PERIOD
        and type(worker["registration"].get("selection_limit")) is int
        and worker["registration"]["selection_limit"] == fresh.LIMIT
        and worker["registration"].get("selection_policy") == fresh.POLICY
        and type(worker["registration"].get("worker_invocations")) is int
        and worker["registration"]["worker_invocations"] == 1
        and worker["native_network_fork_allwrite_securityexec_denial"] is True, "locator_protected_worker_identity")
    registration = worker["registration"]
    _need(registration["prior_audit_id"] == "ib-pilot-sec-parent-coverage-reuse-20261025-once"
        and registration["full_source_scope"] == "25quarter2020Q1..2026Q1_all_six_forms"
        and registration["locator_quarantines"] == "all target quarantines retained as metadata, never synthesized URLs"
        and registration["whole_stream_and_operational_inputs_must_equal_completed_audit"] is True
        and registration["native_worker_network_fork_allwrite_securityexec_denial"] is True
        and registration["trusted_parent_not_native_isolation"] is True
        and registration["backtesting_ready"] is False, "locator_prior_registration_scope")
    for key in ("new_provider_requests", "credential_reads", "qc_accesses", "outcome_looks", "backtests"):
        _need(type(registration[key]) is int and registration[key] == 0, "locator_prior_registration_access")
    pins = registration["prior_audit_pins"]
    _need(type(pins) is dict and set(pins) == {"reservation.json", "terminal.json", "complete.json"}, "locator_prior_registration_pins")
    for pin in pins.values():
        _need(type(pin) is dict and set(pin) == {"sha256", "bytes"} and type(pin["bytes"]) is int
            and 0 < pin["bytes"] <= 128 * 1024 * 1024, "locator_prior_control_pin_schema")
        _digest(pin["sha256"])
    _need(pins["complete.json"]["sha256"] == worker["prior_audit_complete_sha256"], "locator_prior_complete_pin_link")
    identity = worker["execution_identity"]
    _need(type(identity) is dict and set(identity) == {"root", "branch", "head", "clean", "source_sha256", "source_inventory_sha256"}
        and type(identity["root"]) is str and identity["root"].startswith("/") and len(identity["root"]) <= 4096
        and identity["branch"] == "codex/strategy-insider-buying" and identity["clean"] is True
        and type(identity["head"]) is str and re.fullmatch(r"[0-9a-f]{40}", identity["head"])
        and type(identity["source_sha256"]) is dict and identity["source_sha256"]
        and "research/insider_buying_pilot_sec_fresh_selection_runner.py" in identity["source_sha256"]
        and identity["source_inventory_sha256"] == _SHA(_RAW(identity["source_sha256"])), "locator_prior_execution_identity")
    for name, digest in identity["source_sha256"].items():
        _need(type(name) is str and 0 < len(name) <= 512 and not name.startswith("/")
            and all(part not in {"", ".", ".."} for part in name.split("/")), "locator_prior_source_path")
        _digest(digest)
    for key in ("new_provider_requests", "credential_reads", "qc_accesses", "outcome_looks", "backtests"):
        _need(type(worker[key]) is int and worker[key] == 0, "locator_prior_access_required_zero")
    for key in ("dispatch_authorized", "canonical_admitted", "backtesting_ready"):
        _need(worker[key] is False, "locator_prior_authority_false")
    for key in ("prior_audit_complete_sha256", "exposure_inventory_sha256", "exposure_snapshot_sha256", "retained_body_inventory_sha256"):
        _digest(worker[key])
    selected = fresh.validate_selection_payload(worker["selection"])
    _need(worker["selection_sha256"] == _SHA(_RAW(selected))
        and selected["source_roster_sha256"] == _SHA(_RAW(worker["source_roster"]))
        and selected["parent_audit_sha256"] == _SHA(_RAW(worker["parent_audit"]))
        and selected["exposure_inventory_sha256"] == worker["exposure_inventory_sha256"]
        and selected["retained_candidate_inventory_sha256"] == worker["retained_body_inventory_sha256"]
        and selected["quarter_bindings"] == worker["parent_audit"]["quarters"], "locator_prior_completed_source_links")
    _need(type(worker["source_roster"]) is dict and worker["source_roster"].get("schema") == fresh.roster.SCHEMA
        and worker["source_roster"].get("fixture_only") is selected["fixture_only"]
        and worker["source_roster"].get("counts") == selected["source_roster_counts"]
        and worker["source_roster"].get("financial_values_interpreted_or_projected") is False
        and worker["source_roster"].get("other_table_rows_parsed") is False
        and worker["parent_audit"].get("schema") == audit.SCHEMA
        and worker["parent_audit"].get("fixture_only") is selected["fixture_only"]
        and worker["parent_audit"].get("context_counts") == selected["parent_context_counts"]
        and worker["parent_audit"].get("pilot_counts") == selected["parent_pilot_counts"]
        and worker["parent_audit"].get("source_roster_sha256") == selected["source_roster_sha256"]
        and worker["parent_audit"].get("exposure_inventory_sha256") == selected["exposure_inventory_sha256"]
        and worker["parent_audit"].get("retained_candidate_inventory_sha256") == selected["retained_candidate_inventory_sha256"],
        "locator_prior_roster_audit_scope")
    for stem in ("source_row", "disposition", "fresh_request"):
        _need(all(selected["full_" + stem + suffix] == worker["parent_audit"][stem + suffix]
            for suffix in ("_jsonl_sha256", "_jsonl_bytes")), "locator_prior_complete_stream_binding")
    rows = worker["locator_quarantines"]
    _need(type(rows) is list and 1 <= len(rows) <= 256 and type(index) is int and 0 <= index < len(rows),
        "locator_prior_row_index")
    counts, previous = Counter(), (-1, 0)
    for row in rows:
        source = _quarantine(row)
        ordering = (audit.PERIODS.index(source["period"]), source["source_record_ordinal"])
        _need(previous < ordering, "locator_prior_quarantine_order")
        counts[source["period"]] += 1;previous = ordering
    _need(all(counts[q["period"]] == q["counts"]["locator_quarantined_targets"] for q in selected["quarter_bindings"]),
        "locator_prior_quarantine_count_binding")
    lines = b"".join(_RAW(row) + b"\n" for row in rows)
    _need(worker["locator_quarantine_jsonl_sha256"] == _SHA(lines)
        and type(worker["locator_quarantine_jsonl_bytes"]) is int and worker["locator_quarantine_jsonl_bytes"] == len(lines),
        "locator_prior_quarantine_stream_binding")
    row = rows[index]
    _need(_SHA(_RAW(row)) == _digest(row_sha), "locator_prior_exact_row_pin")
    return complete, worker, row


def _reason(source, aliases):
    if not aliases: return "master_locator_missing"
    if any(row["form_type"] != source["form_type"] for row in aliases): return "master_form_disagreement"
    if any(row["filing_date"] != source["filing_date"] for row in aliases): return "master_filing_date_disagreement"
    matching = [row for row in aliases
        if audit._cik(master._PATH_RE.fullmatch(row["archive_path"]).group("archive_cik")) == source["issuer_comparison_key"]]
    _need(len(aliases) > 1 and len(matching) != 1, "locator_prior_quarantine_not_reproduced")
    return "multiple_master_aliases_without_unique_issuer_path"


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class PilotSecLocatorDiagnostic:
    _bytes: bytes = field(repr=False)
    _token: object = field(repr=False)

    def canonical_bytes(self):
        _need(type(self) is PilotSecLocatorDiagnostic and self._token is _TOKEN and _SEALS.get(self) == self._bytes,
            "genuine_unchanged_locator_diagnostic_required")
        return self._bytes

    def to_payload(self):return json.loads(self.canonical_bytes())
    @property
    def sha256(self):return _SHA(self.canonical_bytes())


def validate_pilot_sec_locator_diagnostic(value):
    _need(type(value) is PilotSecLocatorDiagnostic, "exact_locator_diagnostic_factory_required")
    value.canonical_bytes()
    return value


def _scan_master(raw, period, decoded_sha, receipt_sha, wanted):
    _need(type(raw) is bytes and 0 < len(raw) <= master.MAX_MASTER_INDEX_BYTES
        and _SHA(raw) == _digest(decoded_sha), "locator_full_master_pin")
    receipt = master.parse_sec_quarter_master_index(raw, year=int(period[:4]), quarter=int(period[-1]))
    _need(type(receipt) is master.SecQuarterMasterIndexReceipt and receipt.source_sha256 == decoded_sha
        and receipt.receipt_sha256 == _digest(receipt_sha) and receipt.source_size_bytes == len(raw), "locator_genuine_master_receipt")
    receipt.__post_init__()
    lines = master._line_vector(raw);body_start = master._body_start(lines)
    all_forms, matching, target_rows, metadata_hash, metadata_bytes = Counter(), {a: [] for a in wanted}, [], hashlib.sha256(), 0
    for ordinal, line in enumerate(lines[body_start:], 1):
        parts = line.split(b"|")
        _need(len(parts) == 5, "locator_full_master_column_count")
        decoded = [part.decode("cp1252" if index == 1 else "ascii") for index, part in enumerate(parts)]
        fields = dict(zip(COLUMNS, decoded, strict=True))
        _need(b"|".join(value.encode("cp1252" if index == 1 else "ascii") for index, value in enumerate(decoded)) == line,
            "locator_lossless_five_columns")
        match = master._PATH_RE.fullmatch(fields["Filename"])
        _need(match is not None, "locator_all_form_archive_path")
        accession = match.group("accession")
        item = {"all_filing_row_ordinal": ordinal, "raw_columns": fields, "accession_number_from_archive_path": accession,
            "raw_five_column_line_sha256": _SHA(line), "raw_five_column_line_bytes": len(line)}
        encoded = _RAW(item) + b"\n";metadata_hash.update(encoded);metadata_bytes += len(encoded)
        form = fields["Form Type"];all_forms[form] += 1
        _need(len(all_forms) <= MAX_FORM_TYPES, "locator_distinct_form_bound")
        if form in {"4", "4/A"}:
            target_rows.append({"accession_number": accession, "form_type": form, "filing_date": fields["Date Filed"], "archive_path": fields["Filename"]})
        if accession in matching:
            _need(len(matching[accession]) < MAX_MATCHING_ROWS, "locator_matching_rows_bound")
            matching[accession].append(item)
    _need(sum(all_forms.values()) == receipt.all_filing_row_count
        and sorted(target_rows, key=lambda row: (row["accession_number"], row["archive_path"]))
            == [row.to_payload() for row in receipt.rows], "locator_full_scan_receipt_conservation")
    summary = {"period": period, "decoded_sha256": decoded_sha, "decoded_size_bytes": len(raw),
        "parsed_receipt_sha256": receipt.receipt_sha256, "parser_version": master.MASTER_INDEX_PARSER_VERSION,
        "all_filing_row_count": receipt.all_filing_row_count, "form4_or_4a_path_rows": len(receipt.rows),
        "all_form_counts": dict(sorted(all_forms.items())), "header_metadata_sha256": _SHA(b"\n".join(lines[:body_start]) + b"\n"),
        "header_line_count": body_start, "ordered_all_form_row_metadata_sha256": metadata_hash.hexdigest(),
        "ordered_all_form_row_metadata_bytes": metadata_bytes,
        "line_metadata_framing": "five_source_columns_lossless_after_consistent_newline_framing_removal",
        "exact_source_line_endings_bound_by_full_master_sha256": True}
    aliases = {a: [row.to_payload() for row in receipt.rows if row.accession_number == a] for a in wanted}
    return summary, matching, aliases


_FALSE_REPORT = ("original_body_requested", "original_body_admitted", "canonical_request_constructed", "source_quarantine_rewritten",
    "source_or_custody_authenticated_here", "protected_prior_execution_replayed_here", "official_availability_or_pit_established",
    "financial_numeric_values_interpreted", "dispatch_authorized", "canonical_admitted", "backtesting_ready")
_ZERO_REPORT = ("new_provider_requests", "credential_reads", "qc_jobs", "outcome_looks", "backtests")
_MASTER_KEYS = frozenset(("period", "decoded_sha256", "decoded_size_bytes", "parsed_receipt_sha256", "parser_version",
    "all_filing_row_count", "form4_or_4a_path_rows", "all_form_counts", "header_metadata_sha256", "header_line_count",
    "ordered_all_form_row_metadata_sha256", "ordered_all_form_row_metadata_bytes", "line_metadata_framing",
    "exact_source_line_endings_bound_by_full_master_sha256"))
_REPORT_KEYS = frozenset(("schema", "scope", "fixture_only", "prior_selection_complete_sha256", "prior_selection_sha256",
    "prior_parent_audit_sha256", "quarantine_index", "quarantine_sha256", "quarantine_row", "source_record_sha256",
    "source_record", "master", "matching_rows", "matching_row_count", "matching_form_counts", "matching_ownership_row_count",
    "classification", "prior_quarantine_reason", "authority", *_FALSE_REPORT, *_ZERO_REPORT))


def _classification(source, rows):
    relevant = [row for row in rows if row["raw_columns"]["Form Type"] in {"4", "4/A"}]
    return ("accession_absent_from_supplied_full_quarter_master" if not rows else
        "accession_present_only_under_other_forms" if not relevant else
        "ownership_form_disagreement" if any(row["raw_columns"]["Form Type"] != source["form_type"] for row in relevant) else
        "ownership_filing_date_disagreement" if any(row["raw_columns"]["Date Filed"] != source["filing_date"] for row in relevant) else
        "ownership_aliases_not_uniquely_resolved")


def _report(worker, quarantine, index, complete_sha, row_sha, scanned):
    source = _quarantine(quarantine);summary, by_accession, aliases = scanned
    accession = source["accession_number"];matching = by_accession[accession]
    _need(aliases[accession] == quarantine["master_aliases"]
        and quarantine["locator_quarantine_reasons"] == [_reason(source, aliases[accession])], "locator_prior_master_alias_or_reason_changed")
    return {"schema": SCHEMA, "scope": "supplied_full_master_metadata_diagnostic_only",
        "fixture_only": worker["selection"]["fixture_only"], "prior_selection_complete_sha256": complete_sha,
        "prior_selection_sha256": worker["selection_sha256"], "prior_parent_audit_sha256": worker["selection"]["parent_audit_sha256"],
        "quarantine_index": index, "quarantine_sha256": row_sha, "quarantine_row": quarantine,
        "source_record_sha256": source["filing_metadata_sha256"], "source_record": source, "master": summary,
        "matching_rows": matching, "matching_row_count": len(matching),
        "matching_form_counts": dict(sorted(Counter(row["raw_columns"]["Form Type"] for row in matching).items())),
        "matching_ownership_row_count": sum(row["raw_columns"]["Form Type"] in {"4", "4/A"} for row in matching),
        "classification": _classification(source, matching), "prior_quarantine_reason": quarantine["locator_quarantine_reasons"][0],
        **dict.fromkeys(_FALSE_REPORT, False), **dict.fromkeys(_ZERO_REPORT, 0), "authority": dict(audit._AUTHORITY)}


def _seal(body):
    raw = _RAW(body);_need(len(raw) <= MAX_RESULT_BYTES, "locator_result_byte_bound")
    value = PilotSecLocatorDiagnostic(raw, _TOKEN);_SEALS[value] = raw
    return validate_pilot_sec_locator_diagnostic(value)


def validate_locator_diagnostic_payload(body):
    """Strict detached IPC validation, never a source/custody or factory seal."""
    try:
        _need(type(body) is dict and set(body) == _REPORT_KEYS and body["schema"] == SCHEMA
            and body["scope"] == "supplied_full_master_metadata_diagnostic_only" and type(body["fixture_only"]) is bool,
            "locator_report_schema")
        for key in _FALSE_REPORT:_need(body[key] is False, "locator_report_authority")
        for key in _ZERO_REPORT:_need(type(body[key]) is int and body[key] == 0, "locator_report_access")
        _need(body["authority"] == audit._AUTHORITY and all(type(body["authority"][k]) is type(v) for k,v in audit._AUTHORITY.items()),
            "locator_report_authority")
        for key in ("prior_selection_complete_sha256", "prior_selection_sha256", "prior_parent_audit_sha256", "quarantine_sha256", "source_record_sha256"):
            _digest(body[key])
        source = _quarantine(body["quarantine_row"])
        _need(body["source_record"] == source and body["source_record_sha256"] == source["filing_metadata_sha256"]
            and body["quarantine_sha256"] == _SHA(_RAW(body["quarantine_row"]))
            and type(body["quarantine_index"]) is int and 0 <= body["quarantine_index"] < 256
            and body["prior_quarantine_reason"] == body["quarantine_row"]["locator_quarantine_reasons"][0], "locator_report_source_binding")
        summary = body["master"]
        _need(type(summary) is dict and set(summary) == _MASTER_KEYS and summary["period"] == source["period"]
            and summary["parser_version"] == master.MASTER_INDEX_PARSER_VERSION
            and summary["line_metadata_framing"] == "five_source_columns_lossless_after_consistent_newline_framing_removal"
            and summary["exact_source_line_endings_bound_by_full_master_sha256"] is True, "locator_report_master_schema")
        for key in ("decoded_sha256", "parsed_receipt_sha256", "header_metadata_sha256", "ordered_all_form_row_metadata_sha256"):_digest(summary[key])
        for key in ("decoded_size_bytes", "all_filing_row_count", "form4_or_4a_path_rows", "header_line_count", "ordered_all_form_row_metadata_bytes"):
            _need(type(summary[key]) is int and summary[key] >= 0, "locator_report_master_count")
        _need(0 < summary["decoded_size_bytes"] <= master.MAX_MASTER_INDEX_BYTES and 0 < summary["header_line_count"] <= 17
            and 0 <= summary["form4_or_4a_path_rows"] <= summary["all_filing_row_count"] <= master.MAX_MASTER_INDEX_ROWS,
            "locator_report_master_bound")
        forms = summary["all_form_counts"]
        _need(type(forms) is dict and 0 < len(forms) <= MAX_FORM_TYPES
            and all(type(k) is str and master._FORM_RE.fullmatch(k) and type(v) is int and v > 0 for k,v in forms.items())
            and sum(forms.values()) == summary["all_filing_row_count"]
            and sum(forms.get(k,0) for k in ("4","4/A")) == summary["form4_or_4a_path_rows"], "locator_report_master_conservation")
        rows = body["matching_rows"]
        _need(type(rows) is list and len(rows) <= MAX_MATCHING_ROWS and type(body["matching_row_count"]) is int
            and len(rows) == body["matching_row_count"], "locator_report_matching_count")
        previous, aliases = 0, []
        for row in rows:
            _need(type(row) is dict and set(row) == {"all_filing_row_ordinal", "raw_columns", "accession_number_from_archive_path",
                "raw_five_column_line_sha256", "raw_five_column_line_bytes"}
                and type(row["all_filing_row_ordinal"]) is int and previous < row["all_filing_row_ordinal"] <= summary["all_filing_row_count"],
                "locator_report_physical_order")
            fields = row["raw_columns"]
            _need(type(fields) is dict and set(fields) == set(COLUMNS) and all(type(v) is str for v in fields.values()), "locator_report_columns")
            line = b"|".join(fields[key].encode("cp1252" if index == 1 else "ascii") for index,key in enumerate(COLUMNS))
            _need(0 < len(line) <= master.MAX_MASTER_INDEX_LINE_BYTES and _SHA(line) == row["raw_five_column_line_sha256"]
                and type(row["raw_five_column_line_bytes"]) is int and len(line) == row["raw_five_column_line_bytes"]
                and master._FORM_RE.fullmatch(fields["Form Type"]), "locator_report_lossless_line")
            match = master._PATH_RE.fullmatch(fields["Filename"])
            _need(match is not None and row["accession_number_from_archive_path"] == match.group("accession") == source["accession_number"],
                "locator_report_accession")
            if fields["Form Type"] in {"4", "4/A"}:
                aliases.append(master.SecMasterIndexRow(source["accession_number"], fields["Form Type"], fields["Date Filed"], fields["Filename"]).to_payload())
            previous = row["all_filing_row_ordinal"]
        aliases.sort(key=lambda row:(row["accession_number"],row["archive_path"]))
        _need(aliases == body["quarantine_row"]["master_aliases"]
            and _reason(source,aliases) == body["prior_quarantine_reason"]
            and body["classification"] == _classification(source,rows)
            and body["matching_form_counts"] == dict(sorted(Counter(row["raw_columns"]["Form Type"] for row in rows).items()))
            and all(type(v) is int for v in body["matching_form_counts"].values())
            and type(body["matching_ownership_row_count"]) is int and body["matching_ownership_row_count"] == len(aliases),
            "locator_report_matching_conservation")
        _need(len(_RAW(body)) <= MAX_RESULT_BYTES, "locator_result_byte_bound")
        return json.loads(_RAW(body))
    except PilotSecLocatorDiagnosticError:raise
    except Exception:raise PilotSecLocatorDiagnosticError("locator_report_validation_refused") from None


def assess_pilot_sec_locator_quarantine(*, master_decoded_raw, expected_master_decoded_sha256,
        expected_master_receipt_sha256, selection_complete_raw, expected_selection_complete_sha256,
        quarantine_index, expected_quarantine_sha256):
    """Diagnose one externally pinned row; never repair a master or request."""
    try:
        _,worker,row = _completed_row(selection_complete_raw,expected_selection_complete_sha256,quarantine_index,expected_quarantine_sha256)
        source = _quarantine(row)
        scanned = _scan_master(master_decoded_raw,source["period"],expected_master_decoded_sha256,
            expected_master_receipt_sha256,{source["accession_number"]})
        body = _report(worker,row,quarantine_index,expected_selection_complete_sha256,expected_quarantine_sha256,scanned)
        validate_locator_diagnostic_payload(body)
        return _seal(body)
    except PilotSecLocatorDiagnosticError:raise
    except Exception:raise PilotSecLocatorDiagnosticError("locator_supplied_metadata_refused") from None


_BATCH_KEYS = frozenset(("schema","scope","fixture_only","prior_selection_complete_sha256","prior_selection_sha256",
    "prior_quarantine_jsonl_sha256","quarantine_count","pilot_quarantine_count","affected_periods","master_scan_count",
    "reports","reports_jsonl_sha256","reports_jsonl_bytes",*_FALSE_REPORT,*_ZERO_REPORT,"authority"))


def validate_locator_diagnostic_batch_payload(body):
    """Detached batch validation; not a genuine result or source admission."""
    try:
        _need(type(body) is dict and set(body) == _BATCH_KEYS and body["schema"] == SCHEMA+"/batch"
            and body["scope"] == "all_pinned_selector_quarantines" and type(body["fixture_only"]) is bool, "locator_batch_schema")
        for key in _FALSE_REPORT:_need(body[key] is False, "locator_batch_authority")
        for key in _ZERO_REPORT:_need(type(body[key]) is int and body[key] == 0, "locator_batch_access")
        _need(body["authority"] == audit._AUTHORITY and all(type(body["authority"][k]) is type(v) for k,v in audit._AUTHORITY.items()),
            "locator_batch_authority")
        for key in ("prior_selection_complete_sha256","prior_selection_sha256","prior_quarantine_jsonl_sha256"):_digest(body[key])
        reports = body["reports"]
        _need(type(reports) is list and 1 <= len(reports) <= 256 and type(body["quarantine_count"]) is int
            and body["quarantine_count"] == len(reports), "locator_batch_count")
        periods, prior, masters = [],(-1,0),{}
        for index,report in enumerate(reports):
            report = validate_locator_diagnostic_payload(report);source=report["source_record"]
            key=(audit.PERIODS.index(source["period"]),source["source_record_ordinal"])
            _need(prior < key and report["quarantine_index"] == index and report["fixture_only"] is body["fixture_only"]
                and report["prior_selection_complete_sha256"] == body["prior_selection_complete_sha256"]
                and report["prior_selection_sha256"] == body["prior_selection_sha256"], "locator_batch_report_link")
            _need(source["period"] not in masters or masters[source["period"]] == report["master"], "locator_batch_master_conflict")
            masters[source["period"]] = report["master"];prior=key
            if source["period"] not in periods:periods.append(source["period"])
        lines=b"".join(_RAW(r)+b"\n" for r in reports)
        qlines=b"".join(_RAW(r["quarantine_row"])+b"\n" for r in reports)
        _need(body["affected_periods"] == periods and type(body["master_scan_count"]) is int and body["master_scan_count"] == len(periods)
            and type(body["pilot_quarantine_count"]) is int and body["pilot_quarantine_count"] == sum(
                r["source_record"]["period"] in audit.PILOT_PERIODS for r in reports)
            and body["reports_jsonl_sha256"] == _SHA(lines) and type(body["reports_jsonl_bytes"]) is int
            and body["reports_jsonl_bytes"] == len(lines) and body["prior_quarantine_jsonl_sha256"] == _SHA(qlines),
            "locator_batch_conservation")
        _need(len(_RAW(body)) <= MAX_RESULT_BYTES,"locator_result_byte_bound")
        return json.loads(_RAW(body))
    except PilotSecLocatorDiagnosticError:raise
    except Exception:raise PilotSecLocatorDiagnosticError("locator_batch_validation_refused") from None


def assess_pilot_sec_locator_quarantines(*, master_inputs, selection_complete_raw,
        expected_selection_complete_sha256, expected_quarantine_sha256s):
    """Bind the complete quarantine list and scan each affected master once."""
    try:
        _need(type(expected_quarantine_sha256s) is tuple and 1 <= len(expected_quarantine_sha256s) <= 256,
            "locator_batch_row_pins")
        _,worker,_ = _completed_row(selection_complete_raw,expected_selection_complete_sha256,0,expected_quarantine_sha256s[0])
        rows=worker["locator_quarantines"]
        _need(len(rows) == len(expected_quarantine_sha256s) and all(_SHA(_RAW(row)) == _digest(pin)
            for row,pin in zip(rows,expected_quarantine_sha256s,strict=True)), "locator_batch_exact_membership")
        periods=sorted({row["source"]["period"] for row in rows},key=audit.PERIODS.index)
        _need(type(master_inputs) is tuple and len(master_inputs) == len(periods), "locator_batch_master_roster")
        reports_by_index={}
        for period,item in zip(periods,master_inputs,strict=True):
            _need(type(item) is dict and set(item) == {"period","decoded_raw","expected_decoded_sha256","expected_receipt_sha256"}
                and item["period"] == period,"locator_batch_master_roster")
            selected=[(i,r) for i,r in enumerate(rows) if r["source"]["period"] == period]
            scanned=_scan_master(item["decoded_raw"],period,item["expected_decoded_sha256"],item["expected_receipt_sha256"],
                {r["source"]["accession_number"] for _,r in selected})
            for index,row in selected:
                reports_by_index[index]=_report(worker,row,index,expected_selection_complete_sha256,expected_quarantine_sha256s[index],scanned)
        reports=[reports_by_index[i] for i in range(len(rows))]
        lines=b"".join(_RAW(r)+b"\n" for r in reports)
        body={"schema":SCHEMA+"/batch","scope":"all_pinned_selector_quarantines","fixture_only":worker["selection"]["fixture_only"],
            "prior_selection_complete_sha256":expected_selection_complete_sha256,"prior_selection_sha256":worker["selection_sha256"],
            "prior_quarantine_jsonl_sha256":worker["locator_quarantine_jsonl_sha256"],"quarantine_count":len(rows),
            "pilot_quarantine_count":sum(r["source"]["period"] in audit.PILOT_PERIODS for r in rows),
            "affected_periods":periods,"master_scan_count":len(periods),"reports":reports,
            "reports_jsonl_sha256":_SHA(lines),"reports_jsonl_bytes":len(lines),
            **dict.fromkeys(_FALSE_REPORT,False),**dict.fromkeys(_ZERO_REPORT,0),"authority":dict(audit._AUTHORITY)}
        validate_locator_diagnostic_batch_payload(body)
        return _seal(body)
    except PilotSecLocatorDiagnosticError:raise
    except Exception:raise PilotSecLocatorDiagnosticError("locator_batch_inputs_refused") from None
