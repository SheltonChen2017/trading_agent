"""Pure SEC-view title/current-permaticker candidate integration.

This extracts exact decoded XML title declarations from genuine frozen derived
views only. It neither interprets financial fields nor matches titles to a
historical share class. Current canonical SEC-URL CIK/permaticker relationships
are candidates, not economic/PIT/SID identity or original-parent admission.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
import hashlib
import json
import re
import weakref
from xml.etree import ElementTree as ET

from research import insider_buying_sec_2006q1_pem_reassessment_v1 as pem
from research import insider_buying_sec_2006q1_pem_reassessment_runner as preceding
from research import insider_buying_sharadar_reference_cohort as sharadar
from research.insider_buying_eodhd_earnings_demo import FALSE_FLAGS as OBSERVER_FALSE_FLAGS
from research.insider_buying_provider_reference_identity import _sec_cik_url


SCHEMA = "insider-sec-title-current-reference-v1"
PROFILE = "INSETF-IB-SEC-VIEW-TITLE-CURRENT-PERMATICKER-v1"
MAX_RESULT_BYTES = 64 * 1024 * 1024
MAX_ASSESSMENT_BYTES = 128 * 1024 * 1024
MAX_TICKERS_BYTES = 256 * 1024 * 1024
MAX_CONTROL_BYTES = 1024 * 1024
MAX_TITLE_OCCURRENCES = 20_000
MAX_TITLE_FIELD_BYTES = 4096
MAX_TITLE_TEXT_BYTES = 2 * 1024 * 1024
MAX_CURRENT_GROUPS = 74_150
SOURCE_ASSESSMENT_SHA = "4665fb197a8ccaa495563f46608ae9a50cef012003261ecc11fe7ce1f51045da"
SOURCE_COMPLETE_SHA = "c3a60ed272603a2ca3a337c8d9d5b475c1b50ea063ccec9a44874a6e11ba0641"
TICKERS_SHA = "da2bf31da6436127dd405154b339d1a31ad6c14a788d0017ce620ad5217aea60"
SHARADAR_COMPLETE_SHA = "07dd203d82c3d90f90e1af239b8ef2255ecba47400595d6f415a65989ee29f97"
CAPTURE_MANIFEST_SHA = "94251ffdf0529b118ff331b98c4a144d97bc734380d7e7333f94045e4aa6f09b"
SOURCE_ROSTER_SHA = "d081c092c5abe29f3be51e3baa413b2ed38cd7d8709d5dd1e52c869cfeac8a99"
_PERMA = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_TOKEN = object()
_REGISTRY = {}
TITLE_REFUSAL_CODES = frozenset({"security_title_missing", "security_title_ambiguous", "security_title_value_missing",
    "security_title_value_ambiguous", "security_title_attributes", "security_title_unexpected_child",
    "security_title_mixed_content", "security_title_value_not_plain", "security_title_text_empty",
    "security_title_text_controls", "non_derivative_table_ambiguous"})
TICKER_REFUSAL_CODES = frozenset({"source_table_not_security_candidate", "provider_permaticker_unknown",
    "sec_filings_url_missing", "sec_filings_url_not_canonical", "sec_filings_url_cik_missing_or_invalid",
    "duplicate_exact_current_row", "conflicting_current_primary_key_row", "current_ticker_label_invalid",
    "nonessential_name_control_characters", "current_metadata_date_invalid", "current_delisting_flag_unknown"})
COUNT_KEYS = frozenset({"source_filings", "target_filings", "context_filings", "selected_parents", "genuine_view_parents",
    "parser_refused_selected_parents", "unselected_filings", "genuine_parents_without_nonderivative_rows",
    "nonderivative_rows_observed", "uninterpreted_nonderivative_child_rows", "title_occurrences", "plain_title_occurrences",
    "quarantined_title_occurrences", "unique_cik_titles", "ticker_rows", "quarantined_ticker_rows",
    "ticker_rows_with_cik_candidates", "ticker_rows_without_cik_candidates", "duplicate_exact_ticker_rows",
    "conflicting_ticker_key_rows", "current_permaticker_groups", "conflicted_current_permaticker_groups",
    "titles_without_current_cik_groups", "titles_with_one_current_cik_group", "titles_with_multiple_current_cik_groups",
    "title_source_original_bytes", "title_source_view_bytes", "title_source_xml_bytes"})


class SecTitleCurrentReferenceError(ValueError):
    """Fixed refusal codes only; no source text/URL/name/exception serialization."""


def _need(value, code):
    if not value:raise SecTitleCurrentReferenceError(code)


def _raw(body):return json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
def _sha(raw):return hashlib.sha256(raw).hexdigest()
def _authority():
    return {**pem._authority(), **dict.fromkeys(sharadar.FALSE_FLAGS, False), **dict.fromkeys(OBSERVER_FALSE_FLAGS, False),
        "exact_title_matching_performed": False, "company_names_used_as_join_keys": False,
        "related_tickers_used_as_identity": False, "native_sid_or_history_verified": False,
        "financial_values_interpreted": False, "qc_jobs": 0, "research_looks": 0, "provider_dispatches": 0}


def _json(raw, expected, cap, *, canonical=True):
    try:return sharadar._json(raw, expected, limit=cap, canonical=canonical)
    except ValueError:raise SecTitleCurrentReferenceError("supplied_input_hash_or_json_refused") from None


def _source_inputs(raw, sha, complete_raw, complete_sha, inventory, fixture_only):
    _need(type(inventory) is pem.PemSourceViewInventory, "genuine_frozen_parent_inventory_required")
    source = _json(raw, sha, MAX_ASSESSMENT_BYTES)
    complete = _json(complete_raw, complete_sha, MAX_CONTROL_BYTES)
    _need(complete.get("schema") == preceding.SCHEMA + "/complete" and complete.get("fixture_only") is fixture_only
        and complete.get("assessment_sha256") == sha and type(complete.get("assessment_bytes")) is int
        and complete["assessment_bytes"] == len(raw)
        and _raw(complete.get("authority")) == _raw(pem._authority())
        and complete.get("capture_report_sha256") == preceding.CAPTURE_REPORT
        and complete.get("source_view_profile") == pem.pem.PROFILE
        # Section 194 (Claude review): both shapes were dereferenced below without a type check.
        and type(complete.get("frozen_original_baseline")) is dict and type(complete.get("capture_id")) is str,
        "observed_source_view_completion_binding_refused")
    context = complete["frozen_original_baseline"].get("preparation_context")
    try:preceding._validate_assessment(source, fixture_only=fixture_only, preparation_context=context)
    except (ValueError, TypeError, KeyError):raise SecTitleCurrentReferenceError("full_source_cohort_context_refused") from None
    body = inventory.to_payload()
    _need(body == source["source_view_inventory"] and inventory.sha256 == source["source_view_inventory_sha256"]
        == complete.get("source_view_inventory_sha256") and _raw(source["counts"]) == _raw(complete.get("counts")),
        "genuine_inventory_differs_from_observed_source_views")
    projections = inventory.frozen_projections_for_v2()
    _need(len(projections) == len(body["rows"]) == source["counts"]["frozen_source_view_projections"],
        "complete_genuine_view_inventory_required")
    if not fixture_only:
        _need(sha == SOURCE_ASSESSMENT_SHA and complete_sha == SOURCE_COMPLETE_SHA
            and context["ordered_source_row_identity_sha256"] == SOURCE_ROSTER_SHA
            and source["counts"]["selected_parents"] == 64 and len(projections) == 57
            and source["counts"]["source_view_parser_quarantined"] == 7
            and source["counts"]["pem_profile_quarantined"] == source["counts"]["source_view_unavailable"] == 0,
            "fixed_actual_source_view_profile_required")
    return source, complete, body, projections, context


def _ticker_inputs(raw, sha, manifest_raw, manifest_sha, complete_raw, complete_sha, fixture_only):
    try:
        manifest, entries = sharadar._manifest(manifest_raw, manifest_sha)
        rows = sharadar._projection(raw, sha, schema=sharadar.TICKERS_SCHEMA, columns=sharadar.TICKER_COLUMNS,
            manifest_digest=manifest_sha, entry=entries["tickers"])
    except ValueError:raise SecTitleCurrentReferenceError("tickers_projection_or_capture_binding_refused") from None
    complete = _json(complete_raw, complete_sha, MAX_CONTROL_BYTES)
    _need(complete.get("schema") == "insider-sharadar-reference-cohort-observer-v2"
        and complete.get("fixture_only") is fixture_only and complete.get("capture_manifest_sha256") == manifest_sha
        and complete.get("tickers_projection_sha256") == sha and complete.get("original_capture_lineage_preserved") is True
        and complete.get("fundamentals_decoded") is False and complete.get("financial_values_interpreted") is False
        and type(complete.get("provider_dispatches")) is int and complete["provider_dispatches"] == 0
        and type(complete.get("credential_reads")) is int and complete["credential_reads"] == 0
        # The compact observer emits these exact flags. Missing pure-assessor
        # flags are NOT source evidence; this result separately declares its
        # own stricter all-false authority without inventing receipt fields.
        and all(complete.get(flag) is False for flag in OBSERVER_FALSE_FLAGS), "observed_tickers_producer_binding_refused")
    counts = complete.get("counts")
    _need(type(counts) is dict and all(type(counts.get(key)) is int and counts[key] == len(rows)
        for key in ("source_ticker_rows", "ticker_rows_accounted")), "full_tickers_row_accounting_required")
    _need(len(rows) <= MAX_CURRENT_GROUPS, "bounded_complete_tickers_profile_required")
    if not fixture_only:
        _need(sha == TICKERS_SHA and complete_sha == SHARADAR_COMPLETE_SHA and manifest_sha == CAPTURE_MANIFEST_SHA
            and len(rows) == 74_150, "fixed_actual_tickers_profile_required")
    return rows, manifest, complete


def _current_groups(rows):
    row_reports, groups, key_hashes = [], {}, {}
    duplicate_count = conflict_count = 0
    for row in rows:
        reasons = []
        table_ok = row["table"] in sharadar._SECURITY_TABLES
        perma_ok = _PERMA.fullmatch(row["permaticker"]) is not None
        if not table_ok:reasons.append("source_table_not_security_candidate")
        if not perma_ok:reasons.append("provider_permaticker_unknown")
        # These are context-quality diagnostics only. None supplies a title,
        # identity join, historical listing instant or source eligibility.
        if sharadar._LABEL.fullmatch(row["ticker"]) is None:reasons.append("current_ticker_label_invalid")
        if any(char in "\r\n\t" for char in row["name"]):reasons.append("nonessential_name_control_characters")
        if row["isdelisted"] not in {"Y", "N"}:reasons.append("current_delisting_flag_unknown")
        if any(row[key] and sharadar._day(row[key]) is None for key in ("firstpricedate", "lastpricedate", "firstadded", "lastupdated")):
            reasons.append("current_metadata_date_invalid")
        cik, status = _sec_cik_url(row["secfilings"])
        if cik is None:reasons.append(status)
        # Ticker/table is used only to ACCOUNT provider duplicate records,
        # never to join source issuers or convert aliases into securities.
        key = (row["table"], row["permaticker"], row["ticker"])
        record_sha = _sha(_raw({key: value for key,value in row.items() if key != "source_row_ordinal"}))
        seen_hashes = key_hashes.setdefault(key, set())
        if record_sha in seen_hashes:
            reasons.append("duplicate_exact_current_row");duplicate_count += 1
        elif seen_hashes:
            reasons.append("conflicting_current_primary_key_row");conflict_count += 1
        seen_hashes.add(record_sha)
        # Conflicts are GLOBAL to the current exact provider identifier. A
        # nonsecurity table observation remains evidence of a conflict, but
        # never supplies a security-table CIK relation to a SEC title.
        if perma_ok:
            group = groups.setdefault(row["permaticker"], {"provider_permaticker": row["permaticker"],
                "ticker_source_ordinals": [], "current_cik_candidates": set(), "tables": set(),
                "security_table_source_ordinals": [], "security_table_cik_candidates": set(), "conflicting_primary_key": False})
            group["ticker_source_ordinals"].append(row["source_row_ordinal"]);group["tables"].add(row["table"])
            if cik is not None:group["current_cik_candidates"].add(cik)
            if table_ok:
                group["security_table_source_ordinals"].append(row["source_row_ordinal"])
                if cik is not None:group["security_table_cik_candidates"].add(cik)
            group["conflicting_primary_key"] |= "conflicting_current_primary_key_row" in reasons
        _need(set(reasons) <= TICKER_REFUSAL_CODES, "fixed_ticker_refusal_code_required")
        row_reports.append({"source_row_ordinal": row["source_row_ordinal"], "source_row_sha256": _sha(_raw(row)),
            "current_sec_url_cik_claim": cik, "sec_url_disposition": status,
            "provider_permaticker_group": row["permaticker"] if perma_ok else None,
            "quarantine_reasons": sorted(set(reasons)), "historical_mapping_admitted": False})
    current, by_cik = [], defaultdict(list)
    for perma,item in sorted(groups.items()):
        group = {**item, "current_cik_candidates": sorted(item["current_cik_candidates"]), "tables": sorted(item["tables"]),
            "security_table_cik_candidates": sorted(item["security_table_cik_candidates"]),
            "competing_current_cik_candidates": len(item["current_cik_candidates"]) > 1}
        index = len(current);current.append(group)
        for cik in group["security_table_cik_candidates"]:by_cik[cik].append(index)
    return row_reports,current,dict(sorted(by_cik.items())),duplicate_count,conflict_count


def _only_whitespace(value):return value is None or not value.strip()


def _declared_titles(projection, bridge, prefix_ordinal, *, text_budget, occurrence_start):
    projection.to_payload()  # Exact frozen full byte/header/XML reparse first.
    raw = projection.xml_bytes
    try:root = ET.fromstring(raw)
    except ET.ParseError:raise SecTitleCurrentReferenceError("genuine_title_source_xml_refused") from None
    _need(root.tag == "ownershipDocument", "genuine_title_source_xml_refused")
    tables = [node for node in root if node.tag == "nonDerivativeTable"]
    observations, row_count, unknown_children = [], 0, 0
    for table_index,table in enumerate(tables):
        tag_ordinals = Counter()
        for child_index,item in enumerate(table):
            if item.tag not in {"nonDerivativeTransaction", "nonDerivativeHolding"}:
                unknown_children += 1;continue
            row_count += 1
            tag_ordinals[item.tag] += 1
            titles = [node for node in item if node.tag == "securityTitle"]
            # A missing title is an observed row-level refusal, not a vanished
            # transaction or evidence of no economic trade.
            for title_index,title in enumerate(titles or (None,)):
                reasons = []
                if len(tables) > 1:reasons.append("non_derivative_table_ambiguous")
                if title is None:reasons.append("security_title_missing");values = [];declared = None
                else:
                    if len(titles) != 1:reasons.append("security_title_ambiguous")
                    if title.attrib:reasons.append("security_title_attributes")
                    if not _only_whitespace(title.text):reasons.append("security_title_mixed_content")
                    if any(node.tag not in {"value", "footnoteId"} for node in title):reasons.append("security_title_unexpected_child")
                    if any(not _only_whitespace(node.tail) for node in title):reasons.append("security_title_mixed_content")
                    values = [node for node in title if node.tag == "value"]
                    if not values:reasons.append("security_title_value_missing")
                    elif len(values) != 1:reasons.append("security_title_value_ambiguous")
                    declared = values[0].text if len(values) == 1 else None
                    if len(values) == 1 and (values[0].attrib or len(values[0])):
                        reasons.append("security_title_value_not_plain");declared = None
                    if declared is not None:
                        _need(type(declared) is str, "title_metadata_text_type_refused")
                        try:encoded = declared.encode("utf-8")
                        except UnicodeError:raise SecTitleCurrentReferenceError("title_metadata_encoding_refused") from None
                        _need(len(encoded) <= MAX_TITLE_FIELD_BYTES, "title_metadata_field_bound_refused")
                        text_budget += len(encoded)
                        _need(text_budget <= MAX_TITLE_TEXT_BYTES, "title_metadata_aggregate_bound_refused")
                        if not declared or not declared.strip():reasons.append("security_title_text_empty")
                        if any(ord(char) < 32 for char in declared):reasons.append("security_title_text_controls")
                    elif len(values) == 1 and not len(values[0]) and not values[0].attrib:reasons.append("security_title_text_empty")
                _need(len(observations) + occurrence_start < MAX_TITLE_OCCURRENCES, "title_occurrence_bound_refused")
                row_path = f"/ownershipDocument/nonDerivativeTable[{table_index+1}]/{item.tag}[{tag_ordinals[item.tag]}]"
                path = f"{row_path}/securityTitle[{title_index+1}]/value"
                observations.append({"title_occurrence_ordinal": occurrence_start + len(observations),
                    "prefix_ordinal": prefix_ordinal, "source_record_ordinal": bridge["request"]["source_record_ordinal"],
                    "accession_number": bridge["request"]["accession_number"], "issuer_cik": bridge["request"]["issuer_cik"],
                    "xml_occurrence_path": path,
                    "xml_occurrence_path_kind": ("exact_observed_singleton_title_value_node" if title is not None and len(values)==1
                        else "attempted_refused_title_value_field_path"),
                    "xml_nonderivative_row_path": row_path, "security_title_child_count": len(titles),
                    "declared_title_decoded_text": declared,
                    "non_derivative_table_child_ordinal": child_index+1,
                    "declared_title_text_sha256": None if declared is None else _sha(declared.encode()),
                    "value_child_count": len(values), "quarantine_reasons": sorted(set(reasons)),
                    "title_profile_qualified": not reasons,
                    "source_original_body_sha256": bridge["original_raw_parent"]["sha256"],
                    "derived_source_view_sha256": bridge["derived_sec_document_source_view"]["sha256"],
                    "source_xml_sha256": _sha(raw), "frozen_projection_sha256": projection.sha256,
                    "original_capture_header_identity_bound": False, "whole_original_parent_admitted": False,
                    "exact_security_title_mapping_admitted": False})
    return observations,row_count,unknown_children,text_budget


@dataclass(frozen=True, slots=True, weakref_slot=True)
class SecTitleCurrentReferenceAssessment:
    _bytes: bytes = field(repr=False)
    _inventory: pem.PemSourceViewInventory = field(repr=False, compare=False)
    _inventory_sha256: str
    _token: object = field(repr=False, compare=False)

    def canonical_bytes(self):
        registered = _REGISTRY.get(id(self))
        _need(type(self) is SecTitleCurrentReferenceAssessment and self._token is _TOKEN and registered is not None
            and registered[0]() is self and type(self._bytes) is bytes and registered[1] == self._bytes,
            "genuine_unchanged_title_reference_assessment_required")
        _need(self._inventory.sha256 == self._inventory_sha256, "genuine_title_parent_inventory_changed")
        return self._bytes

    def to_payload(self):return json.loads(self.canonical_bytes())
    @property
    def sha256(self):return _sha(self.canonical_bytes())


def assess_sec_title_current_reference(*, source_view_assessment_raw, expected_source_view_assessment_sha256,
        source_view_complete_raw, expected_source_view_complete_sha256, source_view_parent_inventory,
        tickers_projection_raw, expected_tickers_projection_sha256, capture_manifest_raw, expected_capture_manifest_sha256,
        sharadar_complete_raw, expected_sharadar_complete_sha256, fixture_only):
    """Consume supplied real/fixture metadata and genuine views; no I/O or lookup."""
    _need(type(fixture_only) is bool, "explicit_title_reference_profile_required")
    source,complete,inventory,projections,context = _source_inputs(source_view_assessment_raw,
        expected_source_view_assessment_sha256, source_view_complete_raw, expected_source_view_complete_sha256,
        source_view_parent_inventory, fixture_only)
    tickers,manifest,shara_complete = _ticker_inputs(tickers_projection_raw, expected_tickers_projection_sha256,
        capture_manifest_raw, expected_capture_manifest_sha256, sharadar_complete_raw, expected_sharadar_complete_sha256, fixture_only)
    ticker_reports,groups,cik_index,duplicates,conflicts = _current_groups(tickers)
    bridge_lookup = {row["request"]["accession_number"]: (row,projection) for row,projection in zip(inventory["rows"], projections, strict=True)}
    source_lookup = {row["accession_number"]: row for row in source["parent_qualification_ledger"]}
    parents,occurrences,by_accession = [],[],{}
    text_budget = nond_rows = unknown_children = no_rows = 0
    for row in source["parent_qualification_ledger"]:
        accession = row["accession_number"];indices = []
        if row["projection_bridge"] is not None:
            bridge,projection = bridge_lookup[accession]
            _need(bridge == row["projection_bridge"], "genuine_title_bridge_ledger_relation_refused")
            found,count,unknown,text_budget = _declared_titles(projection, bridge, row["prefix_ordinal"],
                text_budget=text_budget, occurrence_start=len(occurrences))
            nond_rows += count;unknown_children += unknown;no_rows += count == 0
            indices = [item["title_occurrence_ordinal"] for item in found];occurrences.extend(found)
            status = "genuine_frozen_derived_view_title_scope"
        else:status = row["disposition"]
        by_accession[accession] = indices
        parents.append({"prefix_ordinal": row["prefix_ordinal"], "source_record_ordinal": row["source_record_ordinal"],
            "accession_number": accession, "source_parent_disposition": row["disposition"],
            "title_source_disposition": status, "source_parent_quarantine_code": row["quarantine_code"],
            "title_occurrence_indices": indices, "original_capture_header_identity_bound": False,
            "whole_original_parent_admitted": False})
    title_keys,by_title = [],{}
    for item in occurrences:
        _need(set(item["quarantine_reasons"]) <= TITLE_REFUSAL_CODES, "fixed_title_refusal_code_required")
        key = (item["issuer_cik"], item["declared_title_decoded_text"])
        if item["title_profile_qualified"]:
            if key not in by_title:
                by_title[key] = len(title_keys)
                title_keys.append({"title_key_index": len(title_keys), "issuer_cik": key[0], "declared_title_decoded_text": key[1],
                    "title_text_sha256": _sha(key[1].encode()), "title_occurrence_indices": [],
                    "exact_security_title_matching_performed": False,
                    "historical_share_class_admitted": False})
            item["title_key_index"] = by_title[key];title_keys[by_title[key]]["title_occurrence_indices"].append(item["title_occurrence_ordinal"])
        else:item["title_key_index"] = None
    roster = []
    for row in source["rows"]:
        parent = source_lookup.get(row["accession_number"])
        status = ("unsupported_context_source_form" if row["form_type"] not in {"4", "4/A"} else
            "no_qualified_frozen_parent_view" if parent is None else parent["disposition"])
        roster.append({"source_record_ordinal": row["source_record_ordinal"], "accession_number": row["accession_number"],
            "form_type": row["form_type"], "issuer_cik": row["issuer_comparison_key"],
            "source_parent_status": status, "title_occurrence_indices": by_accession.get(row["accession_number"], []),
            "historical_mapping_admitted": False})
    counts = {"source_filings": len(roster), "target_filings": source["counts"]["target_filings"], "context_filings": source["counts"]["context_filings"],
        "selected_parents": len(parents), "genuine_view_parents": len(projections),
        "parser_refused_selected_parents": sum(row["source_parent_disposition"] == "source_view_frozen_parser_quarantined" for row in parents),
        "unselected_filings": len(roster)-len(parents), "genuine_parents_without_nonderivative_rows": no_rows,
        "nonderivative_rows_observed": nond_rows, "uninterpreted_nonderivative_child_rows": unknown_children,
        "title_occurrences": len(occurrences), "plain_title_occurrences": sum(row["title_profile_qualified"] for row in occurrences),
        "quarantined_title_occurrences": sum(not row["title_profile_qualified"] for row in occurrences), "unique_cik_titles": len(title_keys),
        "ticker_rows": len(tickers), "quarantined_ticker_rows": sum(bool(row["quarantine_reasons"]) for row in ticker_reports),
        "ticker_rows_with_cik_candidates": sum(row["current_sec_url_cik_claim"] is not None for row in ticker_reports),
        "ticker_rows_without_cik_candidates": sum(row["current_sec_url_cik_claim"] is None for row in ticker_reports),
        "duplicate_exact_ticker_rows": duplicates, "conflicting_ticker_key_rows": conflicts,
        "current_permaticker_groups": len(groups), "conflicted_current_permaticker_groups": sum(row["conflicting_primary_key"]
            or row["competing_current_cik_candidates"] for row in groups),
        "titles_without_current_cik_groups": sum(not cik_index.get(row["issuer_cik"], []) for row in title_keys),
        "titles_with_one_current_cik_group": sum(len(cik_index.get(row["issuer_cik"], [])) == 1 for row in title_keys),
        "titles_with_multiple_current_cik_groups": sum(len(cik_index.get(row["issuer_cik"], [])) > 1 for row in title_keys),
        "title_source_original_bytes": inventory["original_parent_bytes"], "title_source_view_bytes": inventory["derived_source_view_bytes"],
        "title_source_xml_bytes": sum(len(parent.xml_bytes) for parent in projections)}
    _need(set(counts) == COUNT_KEYS and all(type(value) is int and value >= 0 for value in counts.values()), "strict_title_reference_counts_required")
    _need(counts["plain_title_occurrences"] + counts["quarantined_title_occurrences"] == counts["title_occurrences"]
        and counts["ticker_rows_with_cik_candidates"] + counts["ticker_rows_without_cik_candidates"] == counts["ticker_rows"]
        and counts["target_filings"] + counts["context_filings"] == counts["source_filings"], "complete_title_reference_partitions_required")
    title_reasons = Counter(code for row in occurrences for code in row["quarantine_reasons"])
    ticker_reasons = Counter(code for row in ticker_reports for code in row["quarantine_reasons"])
    body = {"schema": SCHEMA, "profile": PROFILE, "fixture_only": fixture_only, "period": "2006Q1",
        "source_identity_kind": "genuine_derived_view_titles_to_current_cik_permaticker_candidates_only",
        "source_cohort_binding": {**context, "source_view_assessment_sha256": expected_source_view_assessment_sha256,
            "source_view_complete_sha256": expected_source_view_complete_sha256, "source_view_inventory_sha256": source_view_parent_inventory.sha256},
        "capture_binding": {"capture_id": complete["capture_id"], "capture_report_sha256": complete["capture_report_sha256"],
            "original_header_quarantines_preserved": True, "whole_original_parent_admitted": False},
        "sharadar_binding": {"capture_manifest_sha256": expected_capture_manifest_sha256,
            "tickers_projection_sha256": expected_tickers_projection_sha256, "sharadar_complete_sha256": expected_sharadar_complete_sha256,
            "original_capture_started_at": manifest["capture_started_at"], "original_capture_completed_at": manifest["capture_completed_at"],
            "current_provider_context_not_historical_vintage": True},
        "filing_roster": roster, "filing_roster_sha256": _sha(_raw(roster)), "parent_title_dispositions": parents,
        "title_occurrences": occurrences, "title_key_index": title_keys, "current_permaticker_groups": groups,
        "current_group_semantics": {"all_table_sec_url_cik_claims_are_not_issuer_evidence": True,
            "shared_index_contains_security_table_cik_candidates_only": True,
            "row_and_title_candidate_relation": "issuer_cik_key_into_shared_current_cik_group_index_missing_key_means_no_candidates",
            "same_security_alias_admitted": False, "historical_share_class_admitted": False},
        "current_cik_group_index": cik_index, "ticker_row_dispositions": ticker_reports, "counts": counts,
        "count_semantics": {"duplicate_exact_ticker_rows": "repeat_of_any_previously_observed_exact_current_record_variant_per_exact_table_permaticker_ticker_key",
            "conflicting_ticker_key_rows": "first_occurrence_of_each_additional_distinct_current_record_variant_per_exact_table_permaticker_ticker_key",
            "refusal_counts": "overlapping_fixed_reason_occurrences_not_unique_row_partitions"},
        "title_refusal_counts": {code: title_reasons[code] for code in sorted(TITLE_REFUSAL_CODES)},
        "ticker_refusal_counts": {code: ticker_reasons[code] for code in sorted(TICKER_REFUSAL_CODES)},
        "title_text_kind": "exact_decoded_XML_value_text_not_original_lexical_XML_byte_span",
        "financial_fields_interpreted_or_projected": False, "company_names_used_as_join_keys": False,
        "ticker_alias_relatedticker_figi_cusip_join_performed": False, "actions_read_or_interpreted": False,
        "full_historical_environment_reconstructed": False, "authority": _authority()}
    encoded = _raw(body);_need(len(encoded) <= MAX_RESULT_BYTES, "title_reference_output_bound_refused")
    result = SecTitleCurrentReferenceAssessment(encoded, source_view_parent_inventory, source_view_parent_inventory.sha256, _TOKEN)
    _REGISTRY[id(result)] = (weakref.ref(result, lambda _,key=id(result):_REGISTRY.pop(key,None)), encoded)
    result.canonical_bytes()
    return result


def validate_sec_title_current_reference_payload(payload, **source_arguments):
    """Independent full input-derived readback, not count/hash self-assertion.

    Recompute from the held immutable raw controls/projection and genuine
    source-view inventory. The caller still establishes actual provenance and
    custody; this performs no file/account/network or authenticated lookup.
    """
    _need(type(payload) is dict, "strict_title_reference_result_payload_required")
    repeated = assess_sec_title_current_reference(**source_arguments)
    _need(_raw(payload) == repeated.canonical_bytes(), "input_derived_title_reference_result_differs")
    return {"profile": PROFILE, "sha256": repeated.sha256, "counts": repeated.to_payload()["counts"],
        "authority": _authority()}
