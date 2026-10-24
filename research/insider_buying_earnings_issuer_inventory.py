"""Bounded offline 2006Q1 issuer-label census for earnings qualification.

Only the complete SUBMISSION metadata table is interpreted. Every ownership
filing and raw symbol label is retained, including context forms, placeholder
labels and conflicting CIK associations. Other ZIP members are inventoried,
never opened. Hash agreement binds supplied bytes, not SEC authentication.

The deterministic selector identifies syntax/association challenges, NOT an
eligible stock universe, PIT mapping, actual earnings coverage, or event dates.
No credential, provider request, price, outcome, QC job or look is accessed.
This standalone helper is not imported by the production Insider package.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass, field
import hashlib
import io
import json
import os
import re
import stat
import zipfile
import zlib

from research.insider_buying.sec_bulk_snapshot import ALLOWED_SEC_TABLES
from research.insider_buying.sec_edgar_acceptance_snapshot import (
    SecEdgarAcceptanceSnapshotError, _upstream_submission_filing_date,
)
from research.insider_buying.sec_ib1b_82q_schema_profile import (
    RETAINED_82Q_SCHEMA_PROFILE_SHA256, build_retained_82q_schema_profile_candidate,
)
from research.insider_buying_eodhd_earnings_demo import EodhdDemoError, _read_leaf
from research.insider_buying_provider_metadata_audit import _bytes, _exclusive_json


SCHEMA = "insider-2006q1-earnings-issuer-label-inventory-v1"
PERIOD = "2006Q1"
RETAINED_ZIP_SHA256 = "62becdadbe5eaff68f03edefe2ba2357c8bb498a1f825b697003e087cf98e6ce"
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_SUBMISSION_BYTES = 64 * 1024 * 1024
MAX_TOTAL_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_FILINGS = 250_000
MAX_FIELD_BYTES = 128 * 1024
MAX_SYMBOL_BYTES = 4096
MAX_OUTPUT_BYTES = 128 * 1024 * 1024
FORMS = ("3", "3/A", "4", "4/A", "5", "5/A")
RELEVANT_FORMS = frozenset({"4", "4/A"})
_AUXILIARY = ("insider_transactions_metadata.json", "insider_transactions_readme.htm")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_CIK = re.compile(r"[0-9]{1,10}\Z")
_ACCESSION = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z")
_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9.\-]{0,63}\Z")
_PLACEHOLDERS = frozenset({"none", "null", "na", "n.a.", "unknown"})
_TOKEN = object()


class EarningsIssuerInventoryError(ValueError):
    """Sanitized source-metadata refusal; source text is never interpolated."""


def _need(condition: bool, code: str) -> None:
    if not condition:
        raise EarningsIssuerInventoryError("REFUSED: " + code)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _label_candidate(label: str) -> bool:
    # Case, spelling and punctuation stay verbatim in the complete inventory.
    return bool(_LABEL.fullmatch(label)) and label.casefold() not in _PLACEHOLDERS


def _authority() -> dict:
    return {name: False for name in (
        "source_authenticated", "complete_parent_admitted", "historical_identity_verified",
        "point_in_time_verified", "delisted_or_reused_ticker_identity_verified",
        "actual_earnings_coverage_complete", "rights_verified", "canonical_ready",
        "qc_entitlement_verified", "outcome_access_authorized", "backtesting_ready",
        "execution_authorized", "event_windows_derived_from_filing_dates",
    )}


@dataclass(frozen=True, slots=True)
class EarningsIssuerInventory:
    _raw: bytes = field(repr=False)
    _token: object = field(repr=False, compare=False)
    _factory_raw: bytes | None = field(default=None, init=False, repr=False, compare=False)

    def canonical_bytes(self) -> bytes:
        _need(type(self) is EarningsIssuerInventory and self._token is _TOKEN
              and type(self._raw) is bytes and self._raw == self._factory_raw,
              "genuine_unchanged_inventory_required")
        return self._raw

    def to_payload(self) -> dict:
        return json.loads(self.canonical_bytes())

    @property
    def sha256(self) -> str:
        return _sha(self.canonical_bytes())


def _submission_bytes(archive_raw: bytes) -> tuple[bytes, list[dict]]:
    """Check bounded central-directory shape; interpret no other member body."""
    try:
        with zipfile.ZipFile(io.BytesIO(archive_raw)) as archive:
            members = archive.infolist()
            names = [member.filename for member in members]
            _need(len(names) == len(set(names)) and set(names) == set(ALLOWED_SEC_TABLES + _AUXILIARY),
                  "complete_exact_archive_member_inventory_required")
            _need(sum(member.file_size for member in members) <= MAX_TOTAL_EXPANDED_BYTES,
                  "expanded_archive_bound_exceeded")
            inventory = []
            for member in sorted(members, key=lambda item: item.filename):
                _need(not member.is_dir() and not member.flag_bits & 1
                      and not stat.S_ISLNK(member.external_attr >> 16)
                      and member.compress_type in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                      and 0 <= member.file_size <= MAX_TOTAL_EXPANDED_BYTES
                      and member.compress_size >= 0,
                      "archive_member_metadata_refused")
                inventory.append({"name": member.filename, "expanded_bytes": member.file_size,
                                  "compressed_bytes": member.compress_size, "crc32": f"{member.CRC:08x}"})
            member = archive.getinfo("SUBMISSION.tsv")
            _need(0 < member.file_size <= MAX_SUBMISSION_BYTES, "submission_byte_bound_exceeded")
            with archive.open(member) as stream:
                raw = stream.read(MAX_SUBMISSION_BYTES + 1)
            _need(len(raw) == member.file_size, "submission_length_differs")
            return raw, inventory
    except EarningsIssuerInventoryError:
        raise
    except (zipfile.BadZipFile, OSError, RuntimeError, KeyError, ValueError, zlib.error):
        raise EarningsIssuerInventoryError("REFUSED: archive_decode_refused") from None


def assess_earnings_issuer_inventory(archive_raw: bytes, *, expected_archive_sha256: str) -> EarningsIssuerInventory:
    """Census one supplied exact-schema quarter; never select canonical signals.

    A caller supplies the external ZIP hash. The retained production hash is
    exported separately, not claimed authenticated by this pure factory. A
    malformed form/CIK/date/header refuses the entire input, never drops rows.
    """
    _need(type(archive_raw) is bytes and 0 < len(archive_raw) <= MAX_ARCHIVE_BYTES,
          "archive_bytes_refused")
    _need(type(expected_archive_sha256) is str and _SHA.fullmatch(expected_archive_sha256) is not None
          and _sha(archive_raw) == expected_archive_sha256, "external_archive_hash_differs")
    raw, member_inventory = _submission_bytes(archive_raw)
    profile = build_retained_82q_schema_profile_candidate()
    headers = next(item.headers for item in profile.variants
                   if item.table_name == "SUBMISSION.tsv" and item.valid_from_year == 2006)
    try:
        reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), delimiter="\t", strict=True)
        _need(tuple(next(reader)) == headers, "exact_submission_header_required")
        positions = {name: headers.index(name) for name in (
            "ACCESSION_NUMBER", "DOCUMENT_TYPE", "FILING_DATE", "ISSUERCIK", "ISSUERTRADINGSYMBOL")}
        filings, accessions, forms = [], set(), Counter()
        all_issuers, relevant_issuers, dialect = {}, {}, None
        symbol_ciks = defaultdict(set)
        for ordinal, values in enumerate(reader, start=1):
            _need(ordinal <= MAX_FILINGS and len(values) == len(headers), "submission_row_count_or_width_refused")
            _need(all(len(value.encode("utf-8")) <= MAX_FIELD_BYTES for value in values), "submission_field_bound_exceeded")
            accession, form, raw_date, raw_cik, label = (values[positions[name]] for name in positions)
            _need(_ACCESSION.fullmatch(accession) is not None and accession not in accessions,
                  "accession_invalid_or_duplicate")
            _need(form in FORMS, "unknown_ownership_form_refused")
            _need(_CIK.fullmatch(raw_cik) is not None and int(raw_cik) > 0, "issuer_cik_invalid")
            _need(len(label.encode("utf-8")) <= MAX_SYMBOL_BYTES
                  and not any(ord(char) < 32 for char in label), "symbol_label_invalid")
            filed, current_dialect = _upstream_submission_filing_date(raw_date)
            _need(filed.year == 2006 and (filed.month - 1) // 3 + 1 == 1, "filing_date_outside_2006q1")
            _need(dialect is None or dialect == current_dialect, "mixed_filing_date_dialects_refused")
            dialect = current_dialect
            cik, relevant = raw_cik.zfill(10), form in RELEVANT_FORMS
            metadata = {"source_record_ordinal": ordinal, "accession_number": accession,
                        "form_type": form, "raw_issuer_cik": raw_cik, "issuer_cik": cik,
                        "raw_symbol_label": label, "raw_filing_date": raw_date, "filing_date": filed.isoformat(),
                        "relevant_form4_or_amendment": relevant,
                        "accession_year_mismatch": int(accession[11:13]) != filed.year % 100}
            filings.append(metadata); accessions.add(accession); forms[form] += 1
            for target in (all_issuers, relevant_issuers) if relevant else (all_issuers,):
                if cik not in target:
                    target[cik] = {"issuer_cik": cik, "symbol_labels": set(), "filing_count": 0,
                                   "first_filing_date": metadata["filing_date"], "last_filing_date": metadata["filing_date"],
                                   "form_counts": Counter()}
                issuer = target[cik]
                issuer["symbol_labels"].add(label); issuer["filing_count"] += 1; issuer["form_counts"][form] += 1
                issuer["first_filing_date"] = min(issuer["first_filing_date"], metadata["filing_date"])
                issuer["last_filing_date"] = max(issuer["last_filing_date"], metadata["filing_date"])
            if relevant: symbol_ciks[label].add(cik)
        _need(bool(filings), "empty_submission_refused")
    except EarningsIssuerInventoryError:
        raise
    except (UnicodeError, csv.Error, StopIteration, SecEdgarAcceptanceSnapshotError):
        raise EarningsIssuerInventoryError("REFUSED: submission_decode_or_date_refused") from None

    def records(mapping):
        return [{**mapping[cik], "symbol_labels": sorted(mapping[cik]["symbol_labels"]),
                 "form_counts": {form: mapping[cik]["form_counts"][form] for form in FORMS}}
                for cik in sorted(mapping)]

    relevant_records = records(relevant_issuers)
    collisions = [{"raw_symbol_label": label, "issuer_ciks": sorted(ciks)}
                  for label, ciks in sorted(symbol_ciks.items()) if len(ciks) > 1]
    singles = [row for row in relevant_records if len(row["symbol_labels"]) == 1
               and _label_candidate(row["symbol_labels"][0])
               and len(symbol_ciks[row["symbol_labels"][0]]) == 1]
    multiples = [row for row in relevant_records if len(row["symbol_labels"]) > 1
                 and sum(_label_candidate(label) for label in row["symbol_labels"]) > 1]
    eligible_collisions = [row for row in collisions if _label_candidate(row["raw_symbol_label"])]
    aapl = relevant_issuers.get("0000320193")
    selection = {
        "first_lexical_single_label_unambiguous_association": (
            {"issuer_cik": singles[0]["issuer_cik"], "raw_symbol_labels": singles[0]["symbol_labels"]} if singles else None),
        "first_lexical_multi_label_issuer": (
            {"issuer_cik": multiples[0]["issuer_cik"], "raw_symbol_labels": multiples[0]["symbol_labels"]} if multiples else None),
        "first_lexical_nonplaceholder_multi_cik_label": eligible_collisions[0] if eligible_collisions else None,
        "fixed_aapl_feasibility_only_not_representative": (
            {"issuer_cik": "0000320193", "raw_symbol_labels": ["AAPL"]} if aapl and "AAPL" in aapl["symbol_labels"] else None),
        "selection_kind": "historical_source_label_challenges_not_historical_security_mapping",
        "provider_symbols_inferred": False, "request_urls_constructed": False,
        "delisted_or_reused_status_inferred": False, "missing_strata_dropped": False,
    }
    body = {"schema": SCHEMA, "period": PERIOD, "scope": "complete_submission_metadata_only",
            "archive_sha256": expected_archive_sha256, "archive_bytes": len(archive_raw),
            "submission_sha256": _sha(raw), "submission_bytes": len(raw),
            "submission_schema_profile_sha256": RETAINED_82Q_SCHEMA_PROFILE_SHA256,
            "member_inventory": member_inventory, "non_submission_member_bodies_interpreted": False,
            "non_submission_crc_verified": False, "filing_date_dialect": dialect,
            "filings": filings, "all_form_issuers": records(all_issuers), "relevant_form_issuers": relevant_records,
            "relevant_symbol_collisions": collisions, "qualification_selector": selection,
            "accounting": {"filings": len(filings), "form_counts": {form: forms[form] for form in FORMS},
                "relevant_filings": sum(forms[form] for form in RELEVANT_FORMS),
                "context_filings": sum(forms[form] for form in FORMS if form not in RELEVANT_FORMS),
                "all_form_issuers": len(all_issuers), "relevant_issuers": len(relevant_records),
                "relevant_multi_label_issuers": sum(len(row["symbol_labels"]) > 1 for row in relevant_records),
                "relevant_multi_cik_labels": len(collisions),
                "relevant_missing_label_filings": sum(not row["raw_symbol_label"] for row in filings if row["relevant_form4_or_amendment"]),
                "accession_year_mismatches": sum(row["accession_year_mismatch"] for row in filings)},
            "authority": _authority(), "research_looks": 0, "provider_dispatches": 0, "qc_jobs": 0}
    encoded = _bytes(body)
    _need(len(encoded) <= MAX_OUTPUT_BYTES, "inventory_output_bound_exceeded")
    result = EarningsIssuerInventory(encoded, _TOKEN)
    object.__setattr__(result, "_factory_raw", encoded)
    return result


def publish_inventory(inventory: EarningsIssuerInventory, *, private_directory_fd: int) -> str:
    """Write one exclusive private leaf in a caller-owned open private directory.

    No CLI/path loader or named-directory race guarantee is supplied. The caller
    must bind and reattach its directory/root custody independently; this helper
    protects the leaf and refuses any existing name, including identical bytes.
    """
    _need(type(inventory) is EarningsIssuerInventory and type(private_directory_fd) is int,
          "genuine_inventory_and_directory_fd_required")
    raw = inventory.canonical_bytes()
    try:
        info = os.fstat(private_directory_fd)
        _need(stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o700
              and info.st_uid == os.geteuid(), "private_owned_directory_required")
        digest = _exclusive_json(private_directory_fd, "inventory.json", inventory.to_payload())
        _need(_read_leaf(private_directory_fd, "inventory.json", limit=MAX_OUTPUT_BYTES) == raw
              and digest == inventory.sha256, "published_inventory_bytes_differ")
        return digest
    except EarningsIssuerInventoryError:
        raise
    except (OSError, EodhdDemoError):
        raise EarningsIssuerInventoryError("REFUSED: exclusive_private_publication_refused") from None
