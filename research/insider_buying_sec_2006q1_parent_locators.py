"""Pure complete 2006Q1 metadata/master locator accounting; no acquisition.

All six forms and source ordinals survive. Archive CIKs identify as-indexed
paths, never inferred issuers. Prior exposure is externally hash-bound input,
not a verified operational journal bootstrap. No filesystem, credentials,
financial table, outcome, provider, QC or execution operation occurs here.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
import hashlib
import json
import re

from research.insider_buying.sec_quarter_master_index import (
    SecQuarterMasterIndexError, parse_sec_quarter_master_index,
)
from research.insider_buying.sec_edgar_acceptance_snapshot import (
    SecEdgarAcceptanceSnapshotError, _upstream_submission_filing_date,
)

# Input vocabulary, not a call into the inventory's filesystem publisher.
INVENTORY_SCHEMA = "insider-2006q1-earnings-issuer-label-inventory-v1"
FORMS = ("3", "3/A", "4", "4/A", "5", "5/A")

SCHEMA = "insider-2006q1-original-parent-locator-accounting-v1"
EXPOSURE_SCHEMA = "insider-original-parent-prior-exposure-inventory-v1"
PERIOD = "2006Q1"
RETAINED_INVENTORY_SHA256 = "a36662f0d29888ee3d38543c9cae2a2d702073790419280b596fe879ea24c30f"
RETAINED_ZIP_SHA256 = "62becdadbe5eaff68f03edefe2ba2357c8bb498a1f825b697003e087cf98e6ce"
RETAINED_MASTER_SHA256 = "e464984945ec875d9316657d0b470d10c7898d92789f46bb19429d00a3063eb7"
MAX_INVENTORY_BYTES = 128 * 1024 * 1024
MAX_EXPOSURE_BYTES = 64 * 1024 * 1024
MAX_OUTPUT_BYTES = 256 * 1024 * 1024
MAX_FILINGS = 250_000
MAX_PRIOR_ACCESSIONS = 250_000
MAX_PREFIX = 4096
_ACCESSION = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_CIK = re.compile(r"[0-9]{1,10}\Z")
_ROOT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,100}\Z")
_PATH = re.compile(r"edgar/data/([0-9]{1,10})/([0-9]{10}-[0-9]{2}-[0-9]{6})\.txt\Z")
_STATES = frozenset({"completed", "reserved", "started", "ambiguous", "refused", "reused"})
_FILING_KEYS = frozenset({"source_record_ordinal", "accession_number", "form_type", "raw_issuer_cik",
    "issuer_cik", "raw_symbol_label", "raw_filing_date", "filing_date",
    "relevant_form4_or_amendment", "accession_year_mismatch"})
_INVENTORY_KEYS = frozenset({"schema", "period", "scope", "archive_sha256", "archive_bytes",
    "submission_sha256", "submission_bytes", "submission_schema_profile_sha256", "member_inventory",
    "non_submission_member_bodies_interpreted", "non_submission_crc_verified", "filing_date_dialect",
    "filings", "all_form_issuers", "relevant_form_issuers", "relevant_symbol_collisions",
    "qualification_selector", "accounting", "authority", "research_looks", "provider_dispatches", "qc_jobs"})
_INVENTORY_AUTHORITY_KEYS = frozenset({"source_authenticated", "complete_parent_admitted",
    "historical_identity_verified", "point_in_time_verified", "delisted_or_reused_ticker_identity_verified",
    "actual_earnings_coverage_complete", "rights_verified", "canonical_ready", "qc_entitlement_verified",
    "outcome_access_authorized", "backtesting_ready", "execution_authorized", "event_windows_derived_from_filing_dates"})
_COUNTS = ("context_filings", "target_filings", "context_master_form_disagreements", "master_alias_path_rows",
    "archive_folder_differs_from_issuer_paths", "master_locator_missing", "master_form_disagreement",
    "master_filing_date_disagreement", "multi_alias_unique_issuer_path_resolved",
    "multiple_master_aliases_without_unique_issuer_path", "locator_quarantined", "locatable_prior_exposed",
    "locatable_unexposed", "selected_archive_folder_matches_issuer", "selected_archive_folder_differs_from_issuer",
    "prior_exposed_targets", "prior_exposed_context")
_TOKEN = object()


class ParentLocatorError(ValueError):
    """A fixed sanitized refusal; no caller data or source text is printed."""


def _need(condition: bool, code: str) -> None:
    if not condition:
        raise ParentLocatorError(code)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def accession_key(accession: str) -> str:
    _need(type(accession) is str and _ACCESSION.fullmatch(accession) is not None, "accession_key_refused")
    return _sha(accession.encode("ascii"))


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _need(key not in result, "source_duplicate_json_key")
        result[key] = value
    return result


def _nonfinite(_):
    raise ParentLocatorError("source_nonfinite_json_refused")


def _load(raw: bytes, expected: str, limit: int) -> dict:
    _need(type(raw) is bytes and 0 < len(raw) <= limit, "source_byte_bound_refused")
    _need(type(expected) is str and _SHA.fullmatch(expected) is not None and _sha(raw) == expected,
          "external_source_hash_mismatch")
    try:
        body = json.loads(raw, object_pairs_hook=_unique, parse_constant=_nonfinite)
        _need(type(body) is dict and _canonical(body) == raw, "source_canonical_json_required")
        return body
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise ParentLocatorError("source_json_refused") from None


def _authority() -> dict:
    return {name: False for name in (
        "source_authenticated", "prior_operational_journals_verified", "parent_bytes_acquired",
        "complete_parent_admitted", "official_acceptance_verified", "publication_time_verified",
        "historical_identity_verified", "point_in_time_verified", "rights_verified", "canonical_ready",
        "qc_entitlement_verified", "outcome_access_authorized", "backtesting_ready", "execution_authorized",
    )}


@dataclass(frozen=True, slots=True)
class ParentLocatorAccounting:
    """Weak factory/byte seal, not authentication against arbitrary Python."""

    _raw: bytes = field(repr=False)
    _token: object = field(repr=False, compare=False)
    _factory_raw: bytes | None = field(default=None, init=False, repr=False, compare=False)

    def canonical_bytes(self) -> bytes:
        _need(type(self) is ParentLocatorAccounting and self._token is _TOKEN and
              type(self._raw) is bytes and self._raw == self._factory_raw,
              "genuine_unchanged_locator_accounting_required")
        return self._raw

    def to_payload(self) -> dict:
        return json.loads(self.canonical_bytes())

    @property
    def sha256(self) -> str:
        return _sha(self.canonical_bytes())


def _exposures(body: dict) -> dict:
    _need(set(body) == {"schema", "records"} and body["schema"] == EXPOSURE_SCHEMA and
          type(body["records"]) is list and len(body["records"]) <= MAX_PRIOR_ACCESSIONS,
          "prior_exposure_schema_refused")
    previous, result = "", {}
    for record in body["records"]:
        _need(type(record) is dict and set(record) == {"accession_number", "accession_key_sha256", "evidence"},
              "prior_exposure_record_schema_refused")
        accession = record["accession_number"]
        key = accession_key(accession)
        _need(previous < accession and record["accession_key_sha256"] == key,
              "prior_exposure_order_or_accession_key_refused")
        evidence = record["evidence"]
        _need(type(evidence) is list and 1 <= len(evidence) <= 1024, "prior_exposure_evidence_bound_refused")
        prior = None
        for item in evidence:
            _need(type(item) is dict and set(item) == {"root_id", "journal_sha256", "state"} and
                  type(item["root_id"]) is str and _ROOT_ID.fullmatch(item["root_id"]) is not None and
                  type(item["journal_sha256"]) is str and _SHA.fullmatch(item["journal_sha256"]) is not None and
                  type(item["state"]) is str and item["state"] in _STATES,
                  "prior_exposure_evidence_schema_refused")
            ordering = (item["root_id"], item["journal_sha256"], item["state"])
            _need(prior is None or prior < ordering, "prior_exposure_evidence_duplicate_or_unsorted")
            prior = ordering
        previous, result[accession] = accession, evidence
    return result


def _filings(body: dict) -> list:
    _need(set(body) == _INVENTORY_KEYS and body.get("schema") == INVENTORY_SCHEMA and body.get("period") == PERIOD and
          body.get("scope") == "complete_submission_metadata_only" and
          type(body.get("filings")) is list and 1 <= len(body["filings"]) <= MAX_FILINGS and
          type(body.get("accounting")) is dict and type(body.get("authority")) is dict and
          set(body["authority"]) == _INVENTORY_AUTHORITY_KEYS and
          all(value is False for value in body["authority"].values()), "submission_inventory_schema_refused")
    _need(type(body.get("archive_sha256")) is str and _SHA.fullmatch(body["archive_sha256"]) is not None and
          type(body.get("submission_sha256")) is str and _SHA.fullmatch(body["submission_sha256"]) is not None and
          type(body["submission_schema_profile_sha256"]) is str and
          _SHA.fullmatch(body["submission_schema_profile_sha256"]) is not None and
          type(body["archive_bytes"]) is int and body["archive_bytes"] > 0 and
          type(body["submission_bytes"]) is int and body["submission_bytes"] > 0 and
          body["non_submission_member_bodies_interpreted"] is False and body["non_submission_crc_verified"] is False and
          all(type(body[name]) is int and body[name] == 0 for name in ("provider_dispatches", "research_looks", "qc_jobs")),
          "submission_source_hash_schema_refused")
    counts, seen, dialect, year_mismatches = Counter(), set(), None, 0
    for ordinal, row in enumerate(body["filings"], start=1):
        _need(type(row) is dict and set(row) == _FILING_KEYS and
              type(row["source_record_ordinal"]) is int and row["source_record_ordinal"] == ordinal,
              "source_filing_ordinal_or_shape_refused")
        accession_key(row["accession_number"])
        _need(row["accession_number"] not in seen and type(row["form_type"]) is str and row["form_type"] in FORMS,
              "source_duplicate_accession_or_unknown_form")
        seen.add(row["accession_number"])
        _need(type(row["raw_issuer_cik"]) is str and _CIK.fullmatch(row["raw_issuer_cik"]) is not None and
              int(row["raw_issuer_cik"]) > 0 and row["issuer_cik"] == row["raw_issuer_cik"].zfill(10),
              "source_issuer_cik_refused")
        try:
            filed = date.fromisoformat(row["filing_date"])
        except (ValueError, TypeError):
            raise ParentLocatorError("source_filing_date_refused") from None
        _need(filed.isoformat() == row["filing_date"] and date(2006, 1, 1) <= filed <= date(2006, 3, 31),
              "source_filing_date_outside_2006q1")
        try:
            source_date, current_dialect = _upstream_submission_filing_date(row["raw_filing_date"])
        except SecEdgarAcceptanceSnapshotError:
            raise ParentLocatorError("source_raw_filing_date_refused") from None
        _need(source_date == filed and (dialect is None or dialect == current_dialect),
              "source_raw_filing_date_or_dialect_differs")
        dialect = current_dialect
        _need(type(row["raw_symbol_label"]) is str and len(row["raw_symbol_label"].encode("utf-8")) <= 4096 and
              not any(ord(char) < 32 for char in row["raw_symbol_label"]), "source_symbol_label_schema_refused")
        relevant, mismatch = row["form_type"] in {"4", "4/A"}, int(row["accession_number"][11:13]) != 6
        _need(type(row["relevant_form4_or_amendment"]) is bool and row["relevant_form4_or_amendment"] is relevant and
              type(row["accession_year_mismatch"]) is bool and row["accession_year_mismatch"] is mismatch,
              "source_filing_derived_fields_refused")
        counts[row["form_type"]] += 1
        year_mismatches += mismatch
    accounting = body["accounting"]
    relevant = counts["4"] + counts["4/A"]
    _need(type(accounting.get("filings")) is int and accounting["filings"] == len(body["filings"]) and
          type(accounting.get("relevant_filings")) is int and accounting["relevant_filings"] == relevant and
          type(accounting.get("context_filings")) is int and accounting["context_filings"] == len(body["filings"]) - relevant and
          type(accounting.get("accession_year_mismatches")) is int and accounting["accession_year_mismatches"] == year_mismatches and
          body["filing_date_dialect"] == dialect and type(accounting.get("form_counts")) is dict and
          set(accounting["form_counts"]) == set(FORMS) and
          all(type(value) is int and value >= 0 for value in accounting["form_counts"].values()) and
          accounting.get("form_counts") == {form: counts[form] for form in FORMS},
          "complete_source_filing_accounting_refused")
    return body["filings"]


def build_2006q1_parent_locators(inventory_raw: bytes, master_raw: bytes, prior_exposure_raw: bytes, *,
                               expected_inventory_sha256: str, expected_master_sha256: str,
                               expected_prior_exposure_sha256: str, maximum_prefix: int = 64) -> ParentLocatorAccounting:
    """Reconcile every supplied filing; prepare an outcome-blind fresh prefix.

    Hash inputs must come from independent caller custody. A sealed return is
    not operational journal verification or authority to invoke a transport.
    Missing/ambiguous locators survive instead of changing the denominator.
    """
    _need(type(maximum_prefix) is int and 1 <= maximum_prefix <= MAX_PREFIX, "prefix_bound_refused")
    inventory = _load(inventory_raw, expected_inventory_sha256, MAX_INVENTORY_BYTES)
    filings = _filings(inventory)
    exposures = _exposures(_load(prior_exposure_raw, expected_prior_exposure_sha256, MAX_EXPOSURE_BYTES))
    _need(type(master_raw) is bytes and type(expected_master_sha256) is str and
          _SHA.fullmatch(expected_master_sha256) is not None and _sha(master_raw) == expected_master_sha256,
          "external_master_hash_mismatch")
    try:
        master = parse_sec_quarter_master_index(master_raw, year=2006, quarter=1)
    except SecQuarterMasterIndexError:
        raise ParentLocatorError("master_source_schema_refused") from None
    by_accession = defaultdict(list)
    for row in master.rows:
        by_accession[row.accession_number].append(row)
    accounting, fresh, counts = [], [], Counter({name: 0 for name in _COUNTS})
    for filing in filings:
        accession, issuer = filing["accession_number"], filing["issuer_cik"]
        aliases = [{**row.to_payload(), "archive_cik": _PATH.fullmatch(row.archive_path).group(1),
                    "archive_folder_matches_issuer": int(_PATH.fullmatch(row.archive_path).group(1)) == int(issuer)}
                   for row in by_accession.get(accession, ())]
        reasons, locator = [], None
        relevant = filing["relevant_form4_or_amendment"]
        exposed = accession in exposures
        if not relevant:
            disposition = "context_retained_not_parent_candidate"
            counts["context_filings"] += 1
            counts["prior_exposed_context"] += exposed
            if aliases:
                reasons.append("context_form_has_form4_master_locator")
                counts["context_master_form_disagreements"] += 1
        else:
            counts["target_filings"] += 1
            counts["master_alias_path_rows"] += len(aliases)
            counts["archive_folder_differs_from_issuer_paths"] += sum(not row["archive_folder_matches_issuer"] for row in aliases)
            if not aliases:
                reasons.append("master_locator_missing")
            else:
                if any(row["form_type"] != filing["form_type"] for row in aliases):
                    reasons.append("master_form_disagreement")
                if any(row["filing_date"] != filing["filing_date"] for row in aliases):
                    reasons.append("master_filing_date_disagreement")
            if aliases and not reasons:
                matches = [row for row in aliases if row["archive_folder_matches_issuer"]]
                if len(aliases) == 1:
                    locator = aliases[0]
                elif len(matches) == 1:
                    locator = matches[0]
                    counts["multi_alias_unique_issuer_path_resolved"] += 1
                else:
                    reasons.append("multiple_master_aliases_without_unique_issuer_path")
            if reasons:
                disposition = "locator_quarantined"
                counts["locator_quarantined"] += 1
                for reason in reasons:
                    counts[reason] += 1
            else:
                disposition = "locatable_prior_exposed" if exposed else "locatable_unexposed"
                counts[disposition] += 1
                counts["selected_archive_folder_matches_issuer" if locator["archive_folder_matches_issuer"] else
                       "selected_archive_folder_differs_from_issuer"] += 1
            counts["prior_exposed_targets"] += exposed
        request = None
        if locator is not None:
            request = {"period": PERIOD, "accession_number": accession, "form_type": filing["form_type"],
                "filing_date": filing["filing_date"], "issuer_cik": issuer,
                "archive_path": locator["archive_path"], "url": "https://www.sec.gov/Archives/" + locator["archive_path"],
                "source_record_ordinal": filing["source_record_ordinal"], "accession_key_sha256": accession_key(accession),
                "filing_metadata_sha256": _sha(_canonical(filing)), "submission_inventory_sha256": expected_inventory_sha256,
                "quarterly_zip_sha256": inventory["archive_sha256"], "submission_member_sha256": inventory["submission_sha256"],
                "master_decoded_sha256": expected_master_sha256, "master_receipt_sha256": master.receipt_sha256}
            if not exposed:
                fresh.append(request)
        accounting.append({"source_record_ordinal": filing["source_record_ordinal"], "accession_number": accession,
            "accession_key_sha256": accession_key(accession), "form_type": filing["form_type"],
            "filing_date": filing["filing_date"], "issuer_cik": issuer, "raw_issuer_cik": filing["raw_issuer_cik"],
            "accession_year_mismatch": filing["accession_year_mismatch"], "relevant_form4_or_amendment": relevant,
            "filing_metadata_sha256": _sha(_canonical(filing)), "master_aliases": aliases,
            "selected_locator": locator, "prior_exposed": exposed,
            "prior_exposure_evidence": exposures.get(accession, []), "disposition": disposition,
            "quarantine_reasons": reasons})
    targets = {filing["accession_number"] for filing in filings if filing["relevant_form4_or_amendment"]}
    extras = [{"accession_number": accession, "master_aliases": [row.to_payload() for row in by_accession[accession]]}
              for accession in sorted(set(by_accession) - targets)]
    fresh.sort(key=lambda row: (row["filing_date"], row["accession_number"], row["source_record_ordinal"]))
    prefix = fresh[:maximum_prefix]
    matches_retained = expected_inventory_sha256 == RETAINED_INVENTORY_SHA256 and expected_master_sha256 == RETAINED_MASTER_SHA256
    if matches_retained:
        _need(len(filings) == 83_657 and len(targets) == 71_679 and counts["context_filings"] == 11_978 and
              inventory["archive_sha256"] == RETAINED_ZIP_SHA256, "retained_source_count_or_zip_anchor_refused")
    body = {"schema": SCHEMA, "period": PERIOD, "submission_inventory_sha256": expected_inventory_sha256,
        "master_decoded_sha256": expected_master_sha256, "master_receipt_sha256": master.receipt_sha256,
        "prior_exposure_inventory_sha256": expected_prior_exposure_sha256,
        "prior_exposure_input_records": len(exposures), "retained_source_hashes_match": matches_retained,
        "all_source_filings_accounted_relative_to_supplied_bytes": True, "source_filings": len(filings),
        "form_counts": inventory["accounting"]["form_counts"], "counts": dict(sorted(counts.items())),
        "master_all_filing_rows": master.all_filing_row_count,
        "master_path_rows": len(master.rows), "master_distinct_form4_accessions": len(by_accession),
        "master_extra_accessions": extras, "master_extra_accession_count": len(extras),
        "filing_accounting": accounting, "filing_accounting_sha256": _sha(_canonical(accounting)),
        "fresh_locator_count": len(fresh), "ordered_fresh_locator_inventory_sha256": _sha(_canonical(fresh)),
        "maximum_prefix": maximum_prefix, "prefix": prefix, "prefix_sha256": _sha(_canonical(prefix)),
        "prefix_selection": "filing_date_then_accession_then_source_ordinal; prior_exposure_excluded",
        "authority": _authority(), "provider_dispatches": 0, "research_looks": 0, "qc_jobs": 0}
    raw = _canonical(body)
    _need(len(raw) <= MAX_OUTPUT_BYTES, "locator_accounting_output_bound_exceeded")
    result = ParentLocatorAccounting(raw, _TOKEN)
    object.__setattr__(result, "_factory_raw", raw)
    return result
