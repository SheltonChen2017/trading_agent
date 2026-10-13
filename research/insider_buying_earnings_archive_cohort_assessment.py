"""Pure metadata reconciliation, never earnings-archive or identity admission.

The caller independently secures and hashes actual journal files. This module
checks their supplied canonical metadata chain without filesystem, transport,
credential, financial-value or outcome access. Unattempted windows can be
fulfilled by a later campaign; an attempted/refused window cannot be replaced.
Historical labels and observed provider basenames form discovery relations,
not historical CIK/share-class/QC-SID mappings or complete empty coverage.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import calendar
import hashlib
import json
import re


SCHEMA = "insider-earnings-archive-cohort-assessment-v1"
INVENTORY_SCHEMA = "insider-2006q1-earnings-issuer-label-inventory-v1"
CAMPAIGN_SCHEMAS = frozenset({"insider-eodhd-date-window-earnings-campaign-v1",
                            "insider-eodhd-date-window-earnings-continuation-v2"})
CONTINUATION_SCHEMA = "insider-eodhd-date-window-earnings-continuation-v2"
QUARANTINE_REASONS = frozenset({"source_row_not_object", "source_row_field_shape_unknown",
    "source_code_unknown", "source_report_date_unknown", "source_fiscal_date_unknown",
    "report_date_outside_registered_scope", "fiscal_date_after_report_date", "source_timing_unknown",
    "source_financial_shape_unknown", "current_provider_reported_status_unknown"})
FORMS = ("3", "3/A", "4", "4/A", "5", "5/A")
MAX_INVENTORY_BYTES = 128 * 1024 * 1024
MAX_JOURNAL_BYTES = 16 * 1024 * 1024
MAX_WINDOW_ROWS = 50_000
MAX_CAMPAIGNS = 4
MAX_TOTAL_ROWS = 248 * MAX_WINDOW_ROWS
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_CIK = re.compile(r"[0-9]{10}\Z")
_CODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}\.[A-Za-z0-9]{1,12}\Z")
_TOKEN = object()


class EarningsArchiveAssessmentError(ValueError):
    """A fixed sanitized metadata refusal, never supplied source text."""


def _need(condition, code):
    if not condition:
        raise EarningsArchiveAssessmentError("REFUSED: " + code)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _digest(value):
    _need(type(value) is str and _SHA.fullmatch(value) is not None, "digest_schema")
    return value


def _count(value):
    _need(type(value) is int and value >= 0, "count_schema")
    return value


def _keys(value, fields, code):
    _need(type(value) is dict and set(value) == set(fields), code)
    return value


def _day(value):
    _need(type(value) is str and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value), "date_schema")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise EarningsArchiveAssessmentError("REFUSED: date_schema") from None


def _utc(value):
    _need(type(value) is str, "observation_time_schema")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise EarningsArchiveAssessmentError("REFUSED: observation_time_schema") from None
    _need(parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0), "observation_time_schema")
    return parsed.astimezone(timezone.utc)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _need(key not in result, "duplicate_json_member")
        result[key] = value
    return result


def _decode(raw, digest, cap):
    _need(type(raw) is bytes and 0 < len(raw) <= cap, "metadata_byte_bound")
    _need(_sha(raw) == _digest(digest), "metadata_hash_mismatch")
    try:
        body = json.loads(raw, object_pairs_hook=_pairs,
                          parse_constant=lambda _: _need(False, "nonfinite_json"))
        _need(type(body) is dict and _canonical(body) == raw, "canonical_metadata_required")
        return body
    except (UnicodeError, json.JSONDecodeError, RecursionError, OverflowError):
        raise EarningsArchiveAssessmentError("REFUSED: metadata_json_schema") from None


def supporting_windows():
    """Conservative staging envelope; not an exact event or source window."""
    return tuple((date(year, month, 1).isoformat(),
                  date(year, month, calendar.monthrange(year, month)[1]).isoformat())
                 for year in range(2005, 2027) for month in range(1, 13)
                 if (2005, 12) <= (year, month) <= (2026, 7))


SUPPORT_WINDOWS = supporting_windows()


@dataclass(frozen=True, slots=True)
class ArchiveWindowMetadata:
    complete_raw: bytes
    complete_sha256: str
    metadata_raw: bytes | None = None
    metadata_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class ArchiveCampaignMetadata:
    manifest_raw: bytes
    manifest_sha256: str
    complete_raw: bytes
    complete_sha256: str
    windows: tuple[ArchiveWindowMetadata, ...]


@dataclass(frozen=True, slots=True)
class EarningsArchiveCohortAssessment:
    _raw: bytes = field(repr=False)
    _token: object = field(repr=False, compare=False)
    _factory_raw: bytes | None = field(default=None, init=False, repr=False, compare=False)

    def canonical_bytes(self):
        _need(type(self) is EarningsArchiveCohortAssessment and self._token is _TOKEN
              and self._raw == self._factory_raw, "genuine_unchanged_assessment_required")
        return self._raw

    def to_payload(self):
        return json.loads(self.canonical_bytes())

    @property
    def sha256(self):
        return _sha(self.canonical_bytes())


def _inventory(raw, digest):
    body = _decode(raw, digest, MAX_INVENTORY_BYTES)
    _need(body.get("schema") == INVENTORY_SCHEMA and body.get("period") == "2006Q1"
          and body.get("scope") == "complete_submission_metadata_only", "inventory_scope")
    filings, declared = body.get("filings"), body.get("all_form_issuers")
    _need(type(filings) is list and 0 < len(filings) <= 250_000
          and type(declared) is list, "inventory_rows")
    forms, issuers, accessions = Counter(), {}, set()
    for ordinal, row in enumerate(filings, 1):
        _keys(row, {"source_record_ordinal", "accession_number", "form_type", "raw_issuer_cik",
                    "issuer_cik", "raw_symbol_label", "raw_filing_date", "filing_date",
                    "relevant_form4_or_amendment", "accession_year_mismatch"}, "filing_schema")
        cik, label, form = row["issuer_cik"], row["raw_symbol_label"], row["form_type"]
        _need(type(row["source_record_ordinal"]) is int and row["source_record_ordinal"] == ordinal,
              "filing_ordinals")
        _need(type(cik) is str and _CIK.fullmatch(cik) and int(cik) > 0
              and type(label) is str and len(label.encode("utf-8")) <= 4096
              and type(form) is str and form in FORMS, "filing_identity")
        accession = row["accession_number"]
        _need(type(accession) is str and re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession)
              and accession not in accessions, "filing_accession")
        day = _day(row["filing_date"])
        _need(date(2006, 1, 1) <= day <= date(2006, 3, 31), "filing_quarter")
        _need(type(row["relevant_form4_or_amendment"]) is bool
              and row["relevant_form4_or_amendment"] == (form in {"4", "4/A"})
              and type(row["accession_year_mismatch"]) is bool, "filing_relevance")
        accessions.add(accession); forms[form] += 1
        item = issuers.setdefault(cik, {"issuer_cik": cik, "symbol_labels": set(), "filing_count": 0,
            "first_filing_date": row["filing_date"], "last_filing_date": row["filing_date"], "form_counts": Counter()})
        item["symbol_labels"].add(label); item["filing_count"] += 1; item["form_counts"][form] += 1
        item["first_filing_date"] = min(item["first_filing_date"], row["filing_date"])
        item["last_filing_date"] = max(item["last_filing_date"], row["filing_date"])
    expected = [{**issuers[cik], "symbol_labels": sorted(issuers[cik]["symbol_labels"]),
                 "form_counts": {form: issuers[cik]["form_counts"][form] for form in FORMS}}
                for cik in sorted(issuers)]
    _need(_canonical(declared) == _canonical(expected), "complete_issuer_inventory_accounting")
    accounting = body.get("accounting")
    _need(type(accounting) is dict and _count(accounting.get("filings")) == len(filings)
          and accounting.get("form_counts") == {form: forms[form] for form in FORMS}
          and _count(accounting.get("all_form_issuers")) == len(expected), "source_counts")
    _need(all(type(value) is int for value in accounting["form_counts"].values()), "source_count_types")
    return body, expected


def _planned(manifest):
    rows = manifest.get("windows")
    _need(type(rows) is list and 0 < len(rows) <= len(SUPPORT_WINDOWS), "planned_window_inventory")
    windows = []
    for row in rows:
        _need(type(row) is list and len(row) == 2 and all(type(value) is str for value in row), "planned_window_schema")
        window = tuple(row)
        _need(window in SUPPORT_WINDOWS, "planned_window_outside_support_envelope")
        _need(not windows or SUPPORT_WINDOWS.index(window) == SUPPORT_WINDOWS.index(windows[-1]) + 1,
              "planned_windows_not_ordered_contiguous")
        windows.append(window)
    return tuple(windows)


def _rows(metadata, receipt, window):
    v2 = metadata["schema"] == CONTINUATION_SCHEMA
    _keys(metadata, {"schema", "body_sha256", "rows"} |
          ({"metadata_acceptance_is_source_coverage_or_identity_admission"} if v2 else set()), "window_metadata_schema")
    _need(not v2 or metadata["metadata_acceptance_is_source_coverage_or_identity_admission"] is False,
          "metadata_acceptance_is_not_admission")
    _need(metadata["body_sha256"] == _digest(receipt["body_sha256"]), "metadata_body_binding")
    rows = metadata["rows"]
    _need(type(rows) is list and len(rows) <= MAX_WINDOW_ROWS
          and len(rows) == _count(receipt["sample_rows"]), "metadata_row_accounting")
    ordinals, reported, unknown, timing, accepted = set(), 0, 0, 0, 0
    reasons_count = Counter()
    for position, row in enumerate(rows):
        _keys(row, {"source_row_ordinal", "code", "report_date", "fiscal_date",
                    "before_after_market", "current_provider_reported_status"} |
              ({"metadata_accepted", "quarantine_reasons"} if v2 else set()), "projected_row_schema")
        ordinal, code = row["source_row_ordinal"], row["code"]
        _need(type(ordinal) is int and 0 <= ordinal < len(rows) and ordinal not in ordinals
              and (not v2 or ordinal == position), "projected_row_ordinals")
        reasons = row["quarantine_reasons"] if v2 else []
        if v2:
            _need(type(row["metadata_accepted"]) is bool and type(reasons) is list
                  and all(type(reason) is str and reason in QUARANTINE_REASONS for reason in reasons)
                  and len(set(reasons)) == len(reasons)
                  and row["metadata_accepted"] == (not reasons), "projected_quarantine_schema")
        nonobject = "source_row_not_object" in reasons
        if code is None and v2:
            _need(nonobject or "source_code_unknown" in reasons, "missing_code_reason")
        else:
            _need(type(code) is str and _CODE.fullmatch(code), "provider_code_schema")
        day = None if v2 and row["report_date"] is None else _day(row["report_date"])
        fiscal = None if v2 and row["fiscal_date"] is None else _day(row["fiscal_date"])
        if v2:
            _need(day is not None or nonobject or "source_report_date_unknown" in reasons, "missing_report_date_reason")
            _need(fiscal is not None or nonobject or "source_fiscal_date_unknown" in reasons, "missing_fiscal_date_reason")
        if day is not None:
            in_window = _day(window[0]) <= day <= _day(window[1])
            _need(in_window or v2 and "report_date_outside_registered_scope" in reasons, "projected_row_dates")
        if day is not None and fiscal is not None:
            _need(fiscal <= day or v2 and "fiscal_date_after_report_date" in reasons, "projected_row_dates")
        category, status = row["before_after_market"], row["current_provider_reported_status"]
        _need(category is None or type(category) is str and category in {"BeforeMarket", "AfterMarket"}, "projected_timing")
        _need(type(status) is str and status in {"reported", "unknown"}, "projected_status")
        if v2:
            _need(category is not None or nonobject or "source_timing_unknown" in reasons, "missing_timing_reason")
            _need(status != "unknown" or nonobject or "current_provider_reported_status_unknown" in reasons, "missing_status_reason")
        accepted += row["metadata_accepted"] if v2 else 1
        reasons_count.update(reasons)
        ordinals.add(ordinal); reported += status == "reported"; unknown += status == "unknown"; timing += category is None
    _need(v2 or rows == sorted(rows, key=lambda row: (row["report_date"], row["code"], row["fiscal_date"], row["source_row_ordinal"])),
          "projected_rows_reordered")
    _need(all(type(receipt[key]) is int and receipt[key] == value for key, value in (
        ("reported_rows", reported), ("unknown_status_rows", unknown), ("timing_unknown_rows", timing))), "status_count_accounting")
    if v2:
        _need(receipt.get("all_rows_retained_in_source_order") is True
              and type(receipt.get("metadata_accepted_rows")) is int and receipt["metadata_accepted_rows"] == accepted
              and type(receipt.get("quarantined_rows")) is int and receipt["quarantined_rows"] == len(rows) - accepted,
              "quarantined_row_accounting")
    return rows, accepted, dict(sorted(reasons_count.items()))


def assess_earnings_archive_cohort(*, inventory_raw: bytes, inventory_sha256: str,
        campaigns: tuple[ArchiveCampaignMetadata, ...]) -> EarningsArchiveCohortAssessment:
    """Account all source issuers and archive windows without promoting either.

    Multiple manifests may declare the same still-unattempted window. Exactly
    one actual attempted window is permitted across the collection. No source
    event date or complete earnings coverage is inferred from filing dates.
    """
    inventory, issuers = _inventory(inventory_raw, inventory_sha256)
    _need(type(campaigns) is tuple and 1 <= len(campaigns) <= MAX_CAMPAIGNS
          and all(type(item) is ArchiveCampaignMetadata for item in campaigns), "campaign_collection")
    attempted, campaigns_seen, descriptors, periods, codes = {}, set(), [], {}, {}
    planned_union, total, last_registration, last_attempt = set(), 0, None, None
    previous_observation, previous_campaign_end = None, None
    quarantined_total, unkeyable_periods, rows_missing_code = 0, 0, 0
    all_reasons = Counter()
    for campaign in campaigns:
        manifest = _decode(campaign.manifest_raw, campaign.manifest_sha256, MAX_JOURNAL_BYTES)
        complete = _decode(campaign.complete_raw, campaign.complete_sha256, MAX_JOURNAL_BYTES)
        schema, identity = manifest.get("schema"), manifest.get("campaign_id")
        _need(type(schema) is str and schema in CAMPAIGN_SCHEMAS and complete.get("schema") == schema
              and type(identity) is str and re.fullmatch(r"ib-eodhd-campaign-[a-z0-9-]{1,80}", identity)
              and identity not in campaigns_seen and complete.get("campaign_id") == identity, "campaign_identity")
        _need(complete.get("manifest_sha256") == campaign.manifest_sha256
              and complete.get("identity") == manifest.get("identity"), "campaign_source_binding")
        _need(type(manifest.get("fixture_only")) is bool and complete.get("fixture_only") is manifest["fixture_only"], "campaign_fixture_binding")
        _need({"registered_at_utc"} <= set(manifest) and {"completed_at_utc"} <= set(complete),
              "campaign_observation_schema")
        registered, ended = _utc(manifest["registered_at_utc"]), _utc(complete["completed_at_utc"])
        _need(registered <= ended and (last_registration is None or last_registration <= registered)
              and (previous_campaign_end is None or previous_campaign_end <= registered), "campaign_observation_order")
        last_registration = registered
        previous_campaign_end = ended
        windows = _planned(manifest)
        planned_union.update(windows); campaigns_seen.add(identity)
        results = complete.get("window_results")
        _need(type(results) is list and len(results) <= len(windows)
              and type(campaign.windows) is tuple and len(campaign.windows) == len(results), "attempt_metadata_count")
        _need(type(complete.get("planned_windows")) is int and complete["planned_windows"] == len(windows)
              and type(complete.get("transport_invocation_count")) is int and complete["transport_invocation_count"] == len(results)
              and complete.get("unattempted_windows") == [list(window) for window in windows[len(results):]], "campaign_unattempted_accounting")
        observed, refused = 0, 0
        for index, (summary, evidence) in enumerate(zip(results, campaign.windows, strict=True)):
            _need(type(evidence) is ArchiveWindowMetadata, "window_evidence_type")
            _keys(summary, {"index", "window", "receipt", "complete_sha256"}, "summary_window_schema")
            window = windows[index]
            _need(type(summary["index"]) is int and summary["index"] == index
                  and summary["window"] == list(window) and window not in attempted
                  and (last_attempt is None or SUPPORT_WINDOWS.index(last_attempt) < SUPPORT_WINDOWS.index(window)),
                  "attempted_window_duplicate_or_reordered")
            _need(summary["complete_sha256"] == evidence.complete_sha256, "window_completion_binding")
            child = _decode(evidence.complete_raw, evidence.complete_sha256, MAX_JOURNAL_BYTES)
            _keys(child, {"schema", "window", "index", "completed_at_utc", "manifest_sha256",
                          "started_sha256", "scope_reservation_sha256", "receipt"}, "window_completion_schema")
            _need(child["schema"] == schema and type(child["index"]) is int and child["index"] == index
                  and child["window"] == list(window) and child["manifest_sha256"] == campaign.manifest_sha256
                  and child["receipt"] == summary["receipt"], "window_receipt_binding")
            _digest(child["started_sha256"]); _digest(child["scope_reservation_sha256"])
            when = _utc(child["completed_at_utc"])
            _need(registered <= when <= ended and (previous_observation is None or previous_observation <= when),
                  "window_observation_order")
            previous_observation = when
            receipt = child["receipt"]
            _need(type(receipt) is dict and {"calendar_window_observed", "transport_invocation_count", "http_status",
                "empty_result_is_coverage_evidence", "financial_values_evaluated_or_projected", "response_body_retained",
                "disposition", "body_sha256", "body_size_bytes", "sample_rows", "reported_rows", "unknown_status_rows",
                "timing_unknown_rows"} <= set(receipt) and type(receipt.get("calendar_window_observed")) is bool
                  and type(receipt.get("transport_invocation_count")) is int and receipt["transport_invocation_count"] == 1
                  and type(receipt.get("disposition")) is str
                  and re.fullmatch(r"[a-z][a-z0-9_-]{0,127}", receipt["disposition"]) is not None
                  and receipt.get("empty_result_is_coverage_evidence") is False
                  and receipt.get("financial_values_evaluated_or_projected") is False, "window_receipt_schema")
            success = receipt["calendar_window_observed"]
            _need(index == len(results) - 1 or success, "campaign_continued_after_refusal")
            reference = {"campaign_id": identity, "campaign_schema": schema, "index": index,
                "window": list(window), "window_complete_sha256": evidence.complete_sha256,
                "observed_at_utc": child["completed_at_utc"], "disposition": receipt.get("disposition"),
                "status": "OBSERVED" if success else "REFUSED_OR_AMBIGUOUS", "metadata_sha256": evidence.metadata_sha256,
                "body_sha256": receipt.get("body_sha256"), "source_rows": receipt.get("sample_rows")}
            if success:
                _need(type(receipt.get("http_status")) is int and receipt["http_status"] == 200
                      and receipt.get("response_body_retained") is True and _count(receipt.get("body_size_bytes")) > 0,
                      "observed_response_receipt")
                if schema == CONTINUATION_SCHEMA:
                    _need(receipt.get("metadata_sha256") == evidence.metadata_sha256
                          and type(receipt.get("metadata_sha256")) is str,
                          "producer_metadata_hash_binding")
                metadata = _decode(evidence.metadata_raw, evidence.metadata_sha256, MAX_JOURNAL_BYTES)
                _need(metadata.get("schema") == schema, "metadata_schema_epoch")
                rows, accepted, reason_counts = _rows(metadata, receipt, window)
                total += len(rows); _need(total <= MAX_TOTAL_ROWS, "total_metadata_row_bound")
                quarantined_total += len(rows) - accepted
                all_reasons.update(reason_counts)
                reference.update(metadata_accepted_rows=accepted, quarantined_rows=len(rows) - accepted,
                                 quarantine_reason_counts=reason_counts)
                for row in rows:
                    code = row["code"]
                    if code is None:
                        rows_missing_code += 1; unkeyable_periods += 1
                        continue
                    stats = codes.setdefault(code, {"rows": 0, "reported_rows": 0, "unknown_rows": 0,
                        "timing_unknown_rows": 0, "quarantined_rows": 0, "report_date_unknown_rows": 0,
                        "2006q1_rows": 0, "first_report_date": None, "last_report_date": None})
                    stats["rows"] += 1; stats["reported_rows"] += row["current_provider_reported_status"] == "reported"
                    stats["unknown_rows"] += row["current_provider_reported_status"] == "unknown"
                    stats["timing_unknown_rows"] += row["before_after_market"] is None
                    stats["quarantined_rows"] += not row.get("metadata_accepted", True)
                    stats["report_date_unknown_rows"] += row["report_date"] is None
                    if row["report_date"] is not None:
                        stats["2006q1_rows"] += "2006-01-01" <= row["report_date"] <= "2006-03-31"
                        stats["first_report_date"] = min(stats["first_report_date"] or row["report_date"], row["report_date"])
                        stats["last_report_date"] = max(stats["last_report_date"] or row["report_date"], row["report_date"])
                    if row["fiscal_date"] is None:
                        unkeyable_periods += 1
                        continue
                    variant = (row["report_date"], row["before_after_market"], row["current_provider_reported_status"])
                    periods.setdefault((code, row["fiscal_date"]), []).append((variant,
                        {"campaign_id": identity, "window_index": index, "source_row_ordinal": row["source_row_ordinal"]}))
                observed += 1
            else:
                _need(evidence.metadata_raw is None and evidence.metadata_sha256 is None
                      and receipt.get("response_body_retained") is False
                      and receipt.get("body_sha256") is None and receipt.get("sample_rows") is None,
                      "refused_window_cannot_carry_selected_metadata")
                refused += 1
            attempted[window] = reference; last_attempt = window
        _need(type(complete.get("observed_windows")) is int and complete["observed_windows"] == observed
              and type(complete.get("refused_or_ambiguous_windows")) is int and complete["refused_or_ambiguous_windows"] == refused
              and type(complete.get("all_registered_windows_observed")) is bool
              and complete["all_registered_windows_observed"] == (observed == len(windows)), "campaign_completion_accounting")
        descriptors.append({"campaign_id": identity, "schema": schema, "manifest_sha256": campaign.manifest_sha256,
                            "complete_sha256": campaign.complete_sha256, "fixture_only": manifest["fixture_only"]})
    _need(planned_union == set(SUPPORT_WINDOWS), "complete_planned_support_envelope_required")
    window_accounting = [attempted.get(window, {"window": list(window), "status": "UNATTEMPTED",
        "metadata_sha256": None, "body_sha256": None, "source_rows": None}) for window in SUPPORT_WINDOWS]
    exact, folded = defaultdict(set), defaultdict(set)
    for code in codes:
        basename = code.rsplit(".", 1)[0]
        exact[basename].add(code); folded[basename.casefold()].add(code)
    label_ciks = defaultdict(set)
    for issuer in issuers:
        for label in issuer["symbol_labels"]:
            label_ciks[label].add(issuer["issuer_cik"])
    relations = []
    for issuer in issuers:
        labels = []
        for label in issuer["symbol_labels"]:
            exact_codes, fold_codes = sorted(exact[label]), sorted(folded[label.casefold()] - exact[label])
            labels.append({"raw_symbol_label": label, "exact_observed_basename_codes": exact_codes,
                "casefold_only_observed_basename_codes": fold_codes,
                "source_label_issuer_ciks": sorted(label_ciks[label]), "historical_mapping_admitted": False})
        exact_codes = sorted(set().union(*(set(row["exact_observed_basename_codes"]) for row in labels)))
        relations.append({**issuer, "candidate_label_relations": labels, "exact_candidate_codes": exact_codes,
            "candidate_rows_in_support_envelope": sum(codes[code]["rows"] for code in exact_codes),
            "candidate_rows_in_2006q1": sum(codes[code]["2006q1_rows"] for code in exact_codes),
            "coverage_disposition": "UNKNOWN", "historical_mapping_admitted": False,
            "no_observed_rows_means_no_earnings": False})
    duplicates = [{"provider_code": code, "fiscal_date": fiscal, "rows": len(rows),
        "metadata_conflict": len({row[0] for row in rows}) > 1,
        "source_references": [row[1] for row in rows], "vendor_revision_history_verified": False}
        for (code, fiscal), rows in sorted(periods.items()) if len(rows) > 1]
    unavailable = [row["window"] for row in window_accounting if row["status"] != "OBSERVED"]
    output = {"schema": SCHEMA, "inventory_sha256": inventory_sha256, "source_period": "2006Q1",
        "scope": "all_form_issuer_labels_and_observed_support_archive_metadata_only", "campaigns": descriptors,
        "fixture_only": any(row["fixture_only"] for row in descriptors), "input_file_custody_verified_here": False,
        "support_envelope": ["2005-12-01", "2026-07-31"], "support_envelope_is_exact_event_window": False,
        "window_accounting": window_accounting, "unavailable_windows": unavailable,
        "all_planned_acquisition_windows_observed": not unavailable,
        "full_source_issuer_accounting_verified": True, "source_filings": inventory["accounting"]["filings"],
        "source_form_counts": inventory["accounting"]["form_counts"], "all_form_issuer_count": len(issuers),
        "relevant_issuer_count": sum(row["form_counts"]["4"] + row["form_counts"]["4/A"] > 0 for row in issuers),
        "source_metadata_rows": total, "provider_code_count": len(codes),
        "metadata_accepted_rows": total - quarantined_total, "quarantined_metadata_rows": quarantined_total,
        "quarantine_reason_counts": dict(sorted(all_reasons.items())), "rows_missing_provider_code": rows_missing_code,
        "rows_without_code_fiscal_period_key": unkeyable_periods,
        "every_row_preserved_by_window_metadata_identity": True,
        "provider_code_metadata": [{"code": code, **codes[code]} for code in sorted(codes)],
        "issuer_relations": relations, "cross_archive_duplicate_fiscal_periods": duplicates,
        "cross_archive_conflicting_fiscal_periods": sum(row["metadata_conflict"] for row in duplicates),
        "source_rows_deduplicated": False, "financial_values_evaluated_or_projected": False,
        "observation_times_are_original_availability": False, "as_known_earnings_schedule_required_for_retrospective_diagnostic": False,
        "earnings_diagnostic_windows_sessions": [2, 5], "earnings_used_for_primary_event_selection": False,
        "earnings_used_for_execution_clock": False, "event_windows_derived_from_filing_dates": False,
        "authority": {name: False for name in ("source_authenticated", "actual_earnings_coverage_complete",
            "historical_identity_verified", "point_in_time_verified", "complete_parent_admitted", "rights_verified",
            "qc_processing_rights_verified", "qc_entitlement_verified", "canonical_ready", "backtesting_ready",
            "outcome_access_authorized", "execution_authorized")}, "research_looks": 0, "qc_jobs": 0,
        "provider_dispatches": 0, "raw_financial_bytes_interpreted": False}
    raw = _canonical(output)
    _need(len(raw) <= MAX_INVENTORY_BYTES, "assessment_output_bound")
    result = EarningsArchiveCohortAssessment(raw, _TOKEN)
    object.__setattr__(result, "_factory_raw", raw)
    return result
