"""Private, complete captured Sharadar master; never historical-PIT authority.

The provider's entire TICKERS snapshot is retained, including stocks that have
delisted. ACTIONS and DESCRIPTIONS retain every CSV row, refusal and lexical
value. Native permanent identifiers and documented date-only event labels are
not fabricated FIGIs, historical effective intervals or portfolio inputs.
This pure parser has no network, filesystem, credential or execution access.
"""
from __future__ import annotations

import csv
import dataclasses
import io
import json
import re
import zipfile
import zlib
from collections import Counter
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any

from data.exchange_calendar import parse_session_date
from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf.contracts import format_utc_timestamp, parse_utc_timestamp

TABLES = ("tickers", "actions", "descriptions")
REQUEST_IDS = tuple("metadata-" + table for table in TABLES) + tuple(
    "schema-" + table for table in TABLES
) + tuple(item for table in TABLES for item in ("issue-" + table, "download-" + table))
MAXIMUM_REQUESTS = 12
MAXIMUM_ARCHIVE_BYTES = 64 * 1024 * 1024
MAXIMUM_CSV_BYTES = 256 * 1024 * 1024
MAXIMUM_ROWS = {"tickers": 200000, "actions": 2000000, "descriptions": 100000}
MAXIMUM_FIELD_CHARACTERS = 65536
SCHEMA = "si-sharadar-securities-master-v1"
INTERFACE_SCHEMA = "si-native-provider-master-source-only-v3"
_API = "https://api.sharadar.com/v1.0/"
_ID = re.compile(r"^[1-9][0-9]{0,29}$")
_NUMBER = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$")
_FIGI = re.compile(r"^[A-Z]{2}G[A-Z0-9]{9}$")
_CATEGORY = re.compile(r"^(Domestic|ADR|Canadian) Common Stock(?: (Primary Class|Secondary Class))?$")
_ALIASES = {
    "descriptions": {"tablename": "table", "unitType": "unittype",
                     "isPrimaryKey": "isprimarykey", "isFilter": "isfilter"},
}
_REQUIRED = {
    "tickers": {"table", "permaticker", "ticker", "exchange", "isdelisted", "category"},
    "actions": {"date", "action", "ticker", "name", "value", "contraticker", "contraname"},
    "descriptions": {"table", "indicator", "title", "description", "unittype", "isprimarykey", "isfilter"},
}
_KNOWN = {
    "tickers": _REQUIRED["tickers"] | {
        "name", "cusips", "siccode", "sicsector", "sicindustry", "figi", "famaindustry",
        "sector", "industry", "scalemarketcap", "scalerevenue", "relatedtickers", "currency",
        "location", "lastupdated", "firstadded", "firstpricedate", "lastpricedate",
        "firstquarter", "lastquarter", "secfilings", "companysite",
    },
    "actions": _REQUIRED["actions"], "descriptions": _REQUIRED["descriptions"],
}
_PUBLIC_EVENT_CLASSES = {
    "sicchangefrom": "historical_SIC_prior_assertion",
    "sicchangeto": "historical_SIC_new_assertion",
    "exchangefrom": "historical_primary_venue_prior_assertion",
    "exchangeto": "historical_primary_venue_new_assertion",
}


class SharadarSecuritiesMasterError(ValueError):
    """Named safe reasons never interpolate source rows or signed URLs."""


def _refuse(reason: str) -> SharadarSecuritiesMasterError:
    return SharadarSecuritiesMasterError("REFUSED: " + reason)


def _table(table: Any) -> str:
    if type(table) is not str or table not in TABLES:
        raise _refuse("unknown_master_table")
    return table


def sharadar_master_request(request_id: str) -> dict[str, Any]:
    if type(request_id) is not str or request_id not in REQUEST_IDS:
        raise _refuse("unknown_master_request")
    kind, table = request_id.split("-", 1)
    if kind == "download":
        return {"request_id": request_id, "method": "GET", "table": table,
                "url": None, "params": {}, "authentication": "none",
                "target_rule": "exact_in_memory_HTTPS_Location_from_authenticated_fixed_origin_302",
                "signed_URL_persisted_or_hashed": False}
    params = {"format": "sqlite"} if kind == "schema" else {"years": "full"}
    if kind == "metadata":
        params["status"] = "True"
    return {"request_id": request_id, "method": "GET", "table": table,
            "url": _API + ("schema/" if kind == "schema" else "data/") + table,
            "params": params, "authentication": "none" if kind == "schema" else "existing_x_api_key_header"}


def request_sha256(request_id: str) -> str:
    return hash_payload(sharadar_master_request(request_id))


def _authority() -> dict[str, Any]:
    return {"source_only": True, "point_in_time_data": False,
            "source_admitted": False, "whole_US_listed_universe_verified": False,
            "ready_for_empirical_backtest": False, "historical_identity_admitted": False,
            "outcome_access_authorized": False, "qc_authorized": False,
            "production_authoritative": False, "trading_authority": False,
            "actual_outcome_looks": 0, "allocated_alpha": 0, "qc_attempts": 0}


def _policy() -> dict[str, Any]:
    return {
        "schema": "si-sharadar-securities-master-protocol-v1",
        "interface_schema": INTERFACE_SCHEMA, "source_route": "direct_Sharadar_existing_personal_API",
        "purpose": "private_full_captured_STOCKS_master_and_historical_event_dictionary_not_outcomes",
        "tables": list(TABLES), "request_ids": list(REQUEST_IDS),
        "requests": [sharadar_master_request(item) for item in REQUEST_IDS],
        "maximum_requests": MAXIMUM_REQUESTS, "automatic_retries": 0,
        "history_selection": "full_for_all_three_tables_before_retrieval_no_fallback",
        "issuer_rule": "fixed_HTTPS_origin_single_302_Location_no_body_or_cookie_auth_forwarding",
        "download_rule": "single_public_pinned_peer_HTTPS_GET_no_proxy_or_redirect_require_200",
        "archive_rule": "one_ZIP32_exact_table_csv_no_dirs_links_encryption_comments_undeclared_gaps_or_trailing_bytes_CRC_verified",
        "compression_methods": ["stored", "deflate"],
        "maximum_archive_bytes": MAXIMUM_ARCHIVE_BYTES, "maximum_csv_bytes": MAXIMUM_CSV_BYTES,
        "maximum_rows": dict(MAXIMUM_ROWS), "maximum_field_characters": MAXIMUM_FIELD_CHARACTERS,
        "CSV_rule": "strict_UTF8_no_NUL_unique_normalized_headers_exact_row_width",
        "required_headers": {key: sorted(value) for key, value in _REQUIRED.items()},
        "known_headers": {key: sorted(value) for key, value in _KNOWN.items()},
        "documented_header_aliases": _ALIASES,
        "unknown_header_rule": "retain_header_and_all_cells_record_schema_refusal_no_unknown_semantics",
        "duplicate_rule": "all_identifiable_primary_key_collisions_quarantined_before_value_validation",
        "permaticker_rule": "canonical_positive_lexical_digits_native_sharadar_namespace_no_FIGI_cast",
        "master_table_values": ["stocks", "SEP"],
        "common_stock_category_pattern": _CATEGORY.pattern,
        "category_rule": "current_common_stock_candidates_only_primary_secondary_not_denominator_or_PIT",
        "identity_rule": "unique_current_ticker_and_permaticker_both_axes_only_not_historical_effective_interval",
        "event_rule": "date_only_current_owner_candidates_dictionary_labels_never_guessed_field_meanings",
        "public_event_classes": _PUBLIC_EVENT_CLASSES,
        "financial_rule": "CSV_lexical_exact_Decimal_Fraction_no_rounding_or_cashflow_authority",
        "retention_rule": "every_CSV_row_raw_cells_file_hash_index_and_disposition_private",
        "population_rule": "complete_captured_STOCKS_snapshot_including_delisted_not_all_US_coverage_claim",
        "signed_URL_persisted_or_hashed": False,
        "publication_scope": "private_only_not_data_usability_publication",
        "authority": _authority(),
    }


PROTOCOL_SHA256 = "a14e6d22c9fd9b1e5edbd3dae8b41f2380648b8b00710bf8ca2865a4884bc44c"


def qualification_protocol() -> dict[str, Any]:
    payload = _policy()
    if hash_payload(payload) != PROTOCOL_SHA256:
        raise _refuse("master_protocol_hash_mismatch")
    return json.loads(canonical_json(payload))


def _ZIP32_layout(raw: bytes, member: zipfile.ZipInfo, eocd: int) -> None:
    central_at = int.from_bytes(raw[eocd + 16:eocd + 20], "little")
    central_size = int.from_bytes(raw[eocd + 12:eocd + 16], "little")
    if central_at < 30 or central_size < 46 or central_at + central_size != eocd:
        raise _refuse("archive_central_directory_layout")
    central = raw[central_at:central_at + 46]
    name_length = int.from_bytes(central[28:30], "little")
    extra_length = int.from_bytes(central[30:32], "little")
    comment_length = int.from_bytes(central[32:34], "little")
    expected_name = member.filename.encode("ascii")
    if (central[:4] != b"PK\x01\x02" or 46 + name_length + extra_length + comment_length != central_size
            or comment_length or central[34:36] != b"\x00\x00"
            or central[42:46] != b"\x00" * 4
            or raw[central_at + 46:central_at + 46 + name_length] != expected_name):
        raise _refuse("archive_central_member_layout")
    for encoded, expected in ((central[8:10], member.flag_bits), (central[10:12], member.compress_type),
                              (central[16:20], member.CRC), (central[20:24], member.compress_size),
                              (central[24:28], member.file_size)):
        if int.from_bytes(encoded, "little") != expected:
            raise _refuse("archive_central_member_mismatch")
    local = raw[:30]
    local_name_length = int.from_bytes(local[26:28], "little")
    local_extra_length = int.from_bytes(local[28:30], "little")
    if (int.from_bytes(local[6:8], "little") != member.flag_bits
            or int.from_bytes(local[8:10], "little") != member.compress_type
            or raw[30:30 + local_name_length] != expected_name):
        raise _refuse("archive_local_member_mismatch")
    payload_end = 30 + local_name_length + local_extra_length + member.compress_size
    if payload_end > central_at:
        raise _refuse("archive_member_overlaps_central_directory")
    values = (member.CRC, member.compress_size, member.file_size)
    local_values = tuple(int.from_bytes(local[a:b], "little") for a, b in ((14, 18), (18, 22), (22, 26)))
    if member.flag_bits & 8:
        descriptor = raw[payload_end:central_at]
        if len(descriptor) == 16 and descriptor[:4] == b"PK\x07\x08":
            descriptor = descriptor[4:]
        if len(descriptor) != 12 or tuple(int.from_bytes(descriptor[a:a + 4], "little")
                for a in (0, 4, 8)) != values or any(actual not in {0, expected}
                for actual, expected in zip(local_values, values)):
            raise _refuse("archive_data_descriptor_layout")
    elif payload_end != central_at or local_values != values:
        raise _refuse("archive_undeclared_gap_or_local_size_mismatch")


def validate_archive(table: str, raw: bytes) -> bytes:
    """Return exactly the bounded CRC-verified CSV, without extracting a file."""
    _table(table)
    if type(raw) is not bytes or not 22 <= len(raw) <= MAXIMUM_ARCHIVE_BYTES:
        raise _refuse("invalid_archive_bytes_or_size")
    if not raw.startswith(b"PK\x03\x04"):
        raise _refuse("archive_local_header_missing")
    # ZipFile accepts junk after a ZIP; the prospective archive contract does not.
    eocd = raw.rfind(b"PK\x05\x06", max(0, len(raw) - 65557))
    if eocd < 0 or eocd + 22 != len(raw) or raw[eocd + 20:eocd + 22] != b"\x00\x00":
        raise _refuse("archive_trailing_bytes_or_comment")
    if (raw[eocd + 4:eocd + 8] != b"\x00" * 4
            or int.from_bytes(raw[eocd + 8:eocd + 10], "little") != 1
            or int.from_bytes(raw[eocd + 10:eocd + 12], "little") != 1):
        raise _refuse("archive_multidisk_or_member_count")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            if len(members) != 1 or archive.comment:
                raise _refuse("archive_requires_one_member")
            member = members[0]
            mode = member.external_attr >> 16
            if (member.filename != table + ".csv" or member.is_dir()
                    or member.external_attr & 0x10
                    or (mode & 0o170000) not in {0, 0o100000}):
                raise _refuse("archive_member_path_or_type")
            if member.flag_bits & 1 or member.comment:
                raise _refuse("archive_encrypted_or_member_comment")
            if member.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                raise _refuse("archive_compression_method")
            if (not 1 <= member.file_size <= MAXIMUM_CSV_BYTES
                    or not 1 <= member.compress_size <= MAXIMUM_ARCHIVE_BYTES):
                raise _refuse("archive_member_size")
            if member.header_offset != 0:
                raise _refuse("archive_prefixed_data")
            _ZIP32_layout(raw, member, eocd)
            with archive.open(member) as source:
                content = source.read(MAXIMUM_CSV_BYTES + 1)
            if len(content) != member.file_size or len(content) > MAXIMUM_CSV_BYTES:
                raise _refuse("archive_decompressed_size_mismatch")
            return content
    except SharadarSecuritiesMasterError:
        raise
    except (zipfile.BadZipFile, zlib.error, RuntimeError, OSError, EOFError, ValueError, NotImplementedError) as exc:
        raise _refuse("invalid_archive_or_CRC") from exc


@dataclasses.dataclass(frozen=True, slots=True)
class CapturedSharadarMasterArchive:
    table: str
    raw: bytes = dataclasses.field(repr=False)
    request_sha256: str

    def __post_init__(self) -> None:
        if type(self) is not CapturedSharadarMasterArchive:
            raise _refuse("exact_master_archive_type_required")
        _table(self.table)
        if type(self.request_sha256) is not str or self.request_sha256 != request_sha256("download-" + self.table):
            raise _refuse("archive_request_binding_mismatch")
        validate_archive(self.table, self.raw)


def _csv(table: str, raw: bytes) -> tuple[list[str], list[str], list[list[str]]]:
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise _refuse("CSV_not_UTF8") from exc
    if "\x00" in text:
        raise _refuse("CSV_contains_NUL")
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        headers = next(reader)
        if (not headers or len(headers) > 128 or any(
                not item or item != item.strip() or len(item) > 128
                or any(ord(char) < 32 or ord(char) == 127 for char in item) for item in headers)):
            raise _refuse("invalid_CSV_headers")
        normalized = [_ALIASES.get(table, {}).get(item, item) for item in headers]
        if len(set(headers)) != len(headers) or len(set(normalized)) != len(normalized):
            raise _refuse("duplicate_CSV_headers")
        if not _REQUIRED[table] <= set(normalized):
            raise _refuse("required_CSV_headers_missing")
        rows = []
        for cells in reader:
            if len(cells) != len(headers):
                raise _refuse("CSV_row_width_mismatch")
            if any(len(cell) > MAXIMUM_FIELD_CHARACTERS for cell in cells):
                raise _refuse("CSV_field_limit_exceeded")
            rows.append(cells)
            if len(rows) > MAXIMUM_ROWS[table]:
                raise _refuse("CSV_row_limit_exceeded")
        return headers, normalized, rows
    except SharadarSecuritiesMasterError:
        raise
    except (csv.Error, StopIteration, UnicodeError, ValueError) as exc:
        raise _refuse("malformed_CSV") from exc


def _text(value: Any, *, blank: bool = False, maximum: int = 512) -> str:
    if (type(value) is not str or len(value) > maximum or value != value.strip()
            or (not blank and not value) or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise _refuse("invalid_master_text")
    return value


def _permaticker(value: Any) -> str:
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise _refuse("noncanonical_permaticker")
    return value


def _date(value: Any, *, nullable: bool = False) -> str | None:
    if value == "" and nullable:
        return None
    try:
        parse_session_date(value)
    except (ValueError, TypeError) as exc:
        raise _refuse("invalid_master_date") from exc
    return value


def _number(value: str) -> dict[str, int] | None:
    if value == "":
        return None
    if type(value) is not str or len(value) > 128 or _NUMBER.fullmatch(value) is None:
        raise _refuse("invalid_action_numeric_token")
    try:
        parsed = Decimal(value)
        if not parsed.is_finite() or abs(parsed.adjusted()) > 128:
            raise _refuse("action_numeric_bound")
        result = Fraction(parsed)
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise _refuse("invalid_action_numeric_token") from exc
    return {"numerator": result.numerator, "denominator": result.denominator}


def _key(table: str, row: dict[str, str]) -> tuple[str, ...] | None:
    try:
        fields = {"tickers": ("table", "permaticker", "ticker"),
                  "actions": ("date", "action", "ticker", "name", "contraticker", "contraname"),
                  "descriptions": ("table", "indicator")}[table]
        # Identifiable collisions precede financial/date/identifier validation.
        return tuple(_text(row[field], blank=table == "actions", maximum=4096) for field in fields)
    except SharadarSecuritiesMasterError:
        return None


def _normalize(table: str, row: dict[str, str]) -> dict[str, Any]:
    if table == "descriptions":
        for field in ("table", "indicator", "title", "unittype"):
            _text(row[field], blank=field in {"title", "unittype"})
        if row["isprimarykey"] not in {"Y", "N"} or row["isfilter"] not in {"Y", "N"}:
            raise _refuse("invalid_dictionary_flag")
        if len(row["description"]) > MAXIMUM_FIELD_CHARACTERS:
            raise _refuse("dictionary_description_too_long")
        return {field: row[field] for field in sorted(_REQUIRED[table])}
    if table == "actions":
        return {"date": _date(row["date"]), "action": _text(row["action"]),
                "ticker": _text(row["ticker"], maximum=128),
                "name": _text(row["name"], blank=True, maximum=4096),
                "value": _number(row["value"]),
                "contraticker": _text(row["contraticker"], blank=True, maximum=128),
                "contraname": _text(row["contraname"], blank=True, maximum=4096),
                "date_precision": "calendar_day_only", "effective_at": None,
                "payment_timestamp": None, "terminal_economics_admitted": False}
    token = _permaticker(row["permaticker"])
    category = _text(row["category"], blank=True)
    if row["isdelisted"] not in {"Y", "N"}:
        raise _refuse("invalid_delisted_flag")
    dates = {field: _date(row.get(field, ""), nullable=True) for field in (
        "lastupdated", "firstadded", "firstpricedate", "lastpricedate", "firstquarter", "lastquarter")}
    if dates["firstpricedate"] and dates["lastpricedate"] and dates["firstpricedate"] > dates["lastpricedate"]:
        raise _refuse("reversed_price_date_assertions")
    composite = _text(row.get("figi", ""), blank=True)
    if composite and _FIGI.fullmatch(composite) is None:
        raise _refuse("invalid_composite_FIGI_assertion")
    match = _CATEGORY.fullmatch(category)
    security_table = _text(row["table"])
    return {
        "table": security_table, "provider_security_id": "sharadar:permaticker:" + token,
        "permaticker": token, "ticker": _text(row["ticker"], maximum=128),
        "is_STOCKS_master_row": security_table in {"stocks", "SEP"},
        "isdelisted": row["isdelisted"] == "Y", "category_assertion": category,
        "current_common_stock_candidate": match is not None,
        "filing_origin_assertion": None if match is None else match.group(1),
        "share_class_role_assertion": None if match is None else match.group(2),
        "current_exchange_assertion": _text(row["exchange"], blank=True),
        "composite_figi_assertion": composite or None, "share_class_figi": None,
        "current_reference_assertions": {**dates, **{field: _text(row.get(field, ""), blank=True, maximum=4096)
            for field in ("name", "relatedtickers", "cusips", "siccode", "sicsector", "sector", "currency", "location")}},
        "historical_effective_intervals": [], "point_in_time_data": False,
        "same_share_class_denominator": None,
    }


def _parsed(capture: CapturedSharadarMasterArchive) -> dict[str, Any]:
    if type(capture) is not CapturedSharadarMasterArchive:
        raise _refuse("exact_master_archive_type_required")
    CapturedSharadarMasterArchive.__post_init__(capture)
    content = validate_archive(capture.table, capture.raw)
    headers, normalized, cells = _csv(capture.table, content)
    raw_rows = [dict(zip(normalized, values)) for values in cells]
    keys = [_key(capture.table, row) for row in raw_rows]
    counts = Counter(key for key in keys if key is not None)
    archive_sha, csv_sha = hash_bytes(capture.raw), hash_bytes(content)
    rows = []
    for index, (row, values, key) in enumerate(zip(raw_rows, cells, keys)):
        origin = {"archive_sha256": archive_sha, "CSV_sha256": csv_sha, "row_index": index,
                  "raw_record_sha256": hash_payload({"CSV_sha256": csv_sha, "row_index": index})}
        normalized_row, refusal = None, None
        if key is not None and counts[key] > 1:
            refusal = "duplicate_primary_key_all_copies_quarantined"
        else:
            try:
                normalized_row = _normalize(capture.table, row)
            except SharadarSecuritiesMasterError as exc:
                refusal = str(exc).removeprefix("REFUSED: ")
        rows.append({"origin": origin, "raw_cells": values,
                     "status": "normalized_source_assertion" if refusal is None else "refused",
                     "normalized": normalized_row, "refusal_reason": refusal})
    return {"table": capture.table, "request_sha256": capture.request_sha256,
            "archive_sha256": archive_sha, "CSV_sha256": csv_sha,
            "headers": headers, "normalized_headers": normalized,
            "schema_refusals": [{"reason": "unknown_CSV_columns_not_interpreted", "columns": sorted(set(normalized) - _KNOWN[capture.table])}]
                if set(normalized) - _KNOWN[capture.table] else [],
            "input_row_count": len(rows), "rows": rows,
            "all_input_rows_retained": True}


def _raw_row(table: dict, item: dict) -> dict[str, str]:
    return dict(zip(table["normalized_headers"], item["raw_cells"]))


def _current_indexes(master: dict) -> tuple[list[dict], dict[str, list[dict]], dict[str, list[dict]]]:
    stock_rows = [row for row in master["rows"] if _raw_row(master, row)["table"] in {"stocks", "SEP"}]
    by_ticker: dict[str, list[dict]] = {}
    by_permaticker: dict[str, list[dict]] = {}
    for item in stock_rows:
        raw = _raw_row(master, item)
        by_ticker.setdefault(raw["ticker"], []).append(item)
        by_permaticker.setdefault(raw["permaticker"], []).append(item)
    return stock_rows, by_ticker, by_permaticker


def _unique_current(candidates: list[dict], by_ticker: dict[str, list[dict]],
                    by_permaticker: dict[str, list[dict]]) -> dict | None:
    if len(candidates) != 1 or candidates[0]["normalized"] is None:
        return None
    item = candidates[0]
    normalized = item["normalized"]
    if len(by_ticker.get(normalized["ticker"], [])) != 1 or len(by_permaticker.get(normalized["permaticker"], [])) != 1:
        return None
    return item


def _build(captures: tuple[CapturedSharadarMasterArchive, ...], retrieved_at: str) -> dict[str, Any]:
    qualification_protocol()
    if type(captures) is not tuple or len(captures) != 3 or any(
            type(item) is not CapturedSharadarMasterArchive for item in captures):
        raise _refuse("three_exact_ordered_archives_required")
    if tuple(item.table for item in captures) != TABLES:
        raise _refuse("master_archive_order_or_inventory")
    try:
        if (type(retrieved_at) is not str or not retrieved_at.endswith("Z")
                or format_utc_timestamp(parse_utc_timestamp(retrieved_at, "master retrieval")) != retrieved_at):
            raise _refuse("canonical_master_retrieval_clock_required")
    except (TypeError, ValueError) as exc:
        if isinstance(exc, SharadarSecuritiesMasterError):
            raise
        raise _refuse("canonical_master_retrieval_clock_required") from exc
    tables = [_parsed(item) for item in captures]
    master, actions, descriptions = tables
    stock_rows, by_ticker, by_permaticker = _current_indexes(master)
    dictionary = [row for row in descriptions["rows"] if row["normalized"] is not None
                  and row["normalized"]["table"] == "actiontypes"]
    dictionary_by_label = {row["normalized"]["indicator"]: row for row in dictionary}
    event_candidates = []
    for item in actions["rows"]:
        row = item["normalized"]
        if row is None:
            continue
        owners = by_ticker.get(row["ticker"], [])
        unique_owner = _unique_current(owners, by_ticker, by_permaticker)
        documentation = dictionary_by_label.get(row["action"])
        reasons = ["date_only_action_not_effective_instant_or_historical_interval",
                   "dictionary_label_does_not_by_itself_prove_alias_field_meaning"]
        if unique_owner is None:
            reasons.append("missing_or_ambiguous_current_native_owner")
        if documentation is None:
            reasons.append("missing_or_refused_action_dictionary_entry")
        event_candidates.append({"action_row_index": item["origin"]["row_index"],
            "action_origin": item["origin"], "dictionary_row_index": None if documentation is None else documentation["origin"]["row_index"],
            "current_native_owner": None if unique_owner is None else unique_owner["normalized"]["provider_security_id"],
            "current_native_owner_origin": None if unique_owner is None else unique_owner["origin"],
            "public_documented_event_class": _PUBLIC_EVENT_CLASSES.get(row["action"]),
            "dictionary_label_retained": documentation is not None,
            "historical_mapping_admitted": False, "effective_at": None,
            "historical_alias": None, "refusal_reasons": reasons})
    identity = hash_payload([{ "table": item.table, "request_sha256": item.request_sha256,
                               "archive_sha256": hash_bytes(item.raw)} for item in captures])
    payload = {"schema": SCHEMA, "interface_schema": INTERFACE_SCHEMA,
        "protocol_sha256": PROTOCOL_SHA256, "capture_identity_sha256": identity,
        "retrieved_at": retrieved_at, "publication_scope": "private_only_not_data_usability_publication",
        "population_scope": "all_captured_STOCKS_master_rows_including_delisted_no_US_market_completeness_claim",
        "tables": tables, "STOCKS_master_row_indices": [row["origin"]["row_index"] for row in stock_rows],
        "current_common_stock_candidate_indices": [row["origin"]["row_index"] for row in stock_rows
            if row["normalized"] is not None and row["normalized"]["current_common_stock_candidate"]],
        "excluded_or_refused_STOCKS_rows": [{"row_index": row["origin"]["row_index"],
            "reason": row["refusal_reason"] or "current_category_not_recognized_common_stock"}
            for row in stock_rows if row["normalized"] is None or not row["normalized"]["current_common_stock_candidate"]],
        "temporal_event_candidates": event_candidates,
        "historical_ticker_intervals": [], "authority": _authority()}
    payload["report_sha256"] = hash_payload(payload)
    return payload


@dataclasses.dataclass(frozen=True, slots=True)
class SharadarSecuritiesMasterQualification:
    captures: tuple[CapturedSharadarMasterArchive, ...] = dataclasses.field(repr=False)
    retrieved_at: str
    _capture_identity_sha256: str = dataclasses.field(init=False, repr=False)
    _payload_json: str = dataclasses.field(init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self) is not SharadarSecuritiesMasterQualification:
            raise _refuse("exact_master_qualification_type_required")
        payload = _build(self.captures, self.retrieved_at)
        object.__setattr__(self, "_capture_identity_sha256", payload["capture_identity_sha256"])
        object.__setattr__(self, "_payload_json", canonical_json(payload))

    def to_payload(self) -> dict[str, Any]:
        if type(self) is not SharadarSecuritiesMasterQualification:
            raise _refuse("exact_master_qualification_type_required")
        expected = _build(self.captures, self.retrieved_at)
        if (type(self._capture_identity_sha256) is not str
                or expected["capture_identity_sha256"] != self._capture_identity_sha256
                or type(self._payload_json) is not str or self._payload_json != canonical_json(expected)):
            raise _refuse("captured_master_identity_changed")
        return json.loads(self._payload_json)

    @property
    def sha256(self) -> str:
        return SharadarSecuritiesMasterQualification.to_payload(self)["report_sha256"]


def qualify_sharadar_securities_master(captures: tuple[CapturedSharadarMasterArchive, ...],
                                      *, retrieved_at: str) -> SharadarSecuritiesMasterQualification:
    return SharadarSecuritiesMasterQualification(captures, retrieved_at)


def lookup_current_security(qualification: SharadarSecuritiesMasterQualification, *,
                            ticker: str | None = None, permaticker: str | None = None) -> dict[str, Any]:
    """Unique source-current native assertion, not a historical identity permit."""
    if type(qualification) is not SharadarSecuritiesMasterQualification:
        raise _refuse("exact_master_qualification_type_required")
    if (ticker is None) == (permaticker is None):
        raise _refuse("one_exact_current_lookup_selector_required")
    value = _text(ticker, maximum=128) if ticker is not None else _permaticker(permaticker)
    payload = SharadarSecuritiesMasterQualification.to_payload(qualification)
    master = payload["tables"][0]
    _, by_ticker, by_permaticker = _current_indexes(master)
    candidates = (by_ticker if ticker is not None else by_permaticker).get(value, [])
    selected = _unique_current(candidates, by_ticker, by_permaticker)
    if selected is None:
        raise _refuse("missing_refused_or_ambiguous_current_security")
    return {"schema": "si-current-native-security-assertion-v1", "report_sha256": payload["report_sha256"],
            "lookup_semantic": "unique_current_provider_native_assertion_only",
            "candidate": selected["normalized"], "origin": selected["origin"],
            "historical_mapping_admitted": False, "point_in_time_data": False,
            "same_share_class_denominator": None, "outcome_access_authorized": False}
