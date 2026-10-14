"""Compact, source-only class-query matrix from a bound full SI page chain.

The protected runtime authenticates files and historical capture code. This
pure stage independently binds manifest/page receipts, consumes raw pages once
and derives completion from their next-URL chain, never a caller boolean. Raw
bodies remain in their original protected files; compact row origins retain
all malformed/duplicate exclusions. No signal, price, outcome or order exists.
"""
from __future__ import annotations

from array import array
import dataclasses
from datetime import date
import hashlib
import json
import re
import struct
import sys
from urllib.parse import parse_qsl, quote, urlencode, urlsplit

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf.contracts import parse_utc_timestamp

SCHEMA = "si-native-population-class-matrix-v1"
REPORT_SCHEMA = "si-native-population-continuation-inventory-v1"
ENDPOINT = "https://api.massive.com/stocks/v1/short-interest"
PARAMS = {"settlement_date.gte": "2022-01-01", "settlement_date.lte": "2026-08-31",
          "limit": "50000", "sort": "settlement_date.asc,ticker.asc"}
INITIAL_URL = ENDPOINT + "?" + urlencode(PARAMS)
MAXIMUM_BYTES, MAXIMUM_PAGES, PARENT_PAGES = 32 * 1024 * 1024, 96, 32
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_HEAD = re.compile(r"[0-9a-f]{40}\Z")
_TICKER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_QUERY = struct.Struct("<IIII")
_REFUSAL = struct.Struct("<iiIIII")
REASONS = ("", "unidentifiable_or_nonobject_SI_row", "not_open_short_position_snapshot",
           "raw_ticker_not_canonical_route_token", "noncanonical_settlement_date",
           "settlement_outside_frozen_request_range", "invalid_exact_open_short_quantity",
           "duplicate_identifiable_ticker_settlement_all_copies_quarantined")


class NativePopulationMatrixError(ValueError):
    """Fixed codes contain no private source values or cursor."""


def _require(value, reason):
    if not value:
        raise NativePopulationMatrixError("REFUSED: " + reason)


def _authority():
    return {"source_matrix_only": True, "source_admitted": False, "point_in_time_data": False,
            "historical_identity_admitted": False, "denominator_admitted": False,
            "actual_input_execution_admitted": False, "outcome_access_authorized": False,
            "qc_authorized": False, "trading_authority": False,
            "actual_outcome_looks": 0, "allocated_alpha": 0, "qc_attempts": 0}


def matrix_policy():
    return {"schema": SCHEMA + "-protocol", "source_endpoint": ENDPOINT, "initial_query": dict(PARAMS),
            "parent_pages": PARENT_PAGES, "maximum_cumulative_pages": MAXIMUM_PAGES,
            "maximum_response_bytes": MAXIMUM_BYTES, "maximum_rows_per_page": 50000,
            "key": "exact_source_raw_ticker_and_settlement_no_alias_or_current_active_filter",
            "collision": "all_identifiable_peers_trim_for_refusal_only_no_positive_repair",
            "source_retention": "original_raw_pages_plus_compact_page_row_origins_and_all_refusals",
            "completion": "independently_reconstructed_raw_page_chain_final_None_not_report_boolean",
            "query": "one_dated_class_overview_per_unique_valid_SI_slot_no_retry_paging_or_fallback",
            "query_encoding": "exact_URL_unreserved_ticker_path_no_casefold_or_alias",
            "compact_format": "little_endian_uint32_queries_int32_int32_uint32x4_refusals",
            "no_financial_computation": True, "authority": _authority()}


def _digest(value):
    _require(type(value) is str and _SHA.fullmatch(value) is not None, "canonical_source_digest_required")
    return value


def _date(value):
    _require(type(value) is str, "canonical_source_date_required")
    try:
        _require(date.fromisoformat(value).isoformat() == value, "canonical_source_date_required")
    except ValueError:
        raise NativePopulationMatrixError("REFUSED: canonical_source_date_required") from None
    return value


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        _require(key not in value, "duplicate_source_JSON_key")
        value[key] = item
    return value


def _json(raw):
    def nonfinite(_):
        raise NativePopulationMatrixError("REFUSED: nonfinite_source_JSON")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_float=str, parse_constant=nonfinite)
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise NativePopulationMatrixError("REFUSED: source_JSON_refused") from None


def _url(value, *, continuation=False):
    _require(type(value) is str and len(value) <= 16384, "fixed_SI_URL_required")
    try:
        parsed = urlsplit(value)
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        raise NativePopulationMatrixError("REFUSED: fixed_SI_URL_required") from None
    _require(parsed.scheme == "https" and parsed.netloc == "api.massive.com"
             and parsed.path == "/stocks/v1/short-interest" and not parsed.fragment
             and parsed.username is None and parsed.password is None, "fixed_SI_URL_required")
    query = dict(pairs)
    _require(len(pairs) == len(query) and set(query) <= set(PARAMS) | {"cursor"}
             and all(value for value in query.values()), "SI_query_duplicates_secret_or_filter_refused")
    _require(all(key not in query or query[key] == val for key, val in PARAMS.items()), "SI_query_scope_changed")
    if continuation:
        cursor = query.get("cursor")
        _require(type(cursor) is str and 1 <= len(cursor) <= 8192
                 and all(33 <= ord(char) <= 126 for char in cursor), "bound_SI_cursor_required")
    return value


def _descriptor(value):
    _require(type(value) is dict and set(value) == {"method", "url", "authentication"}
             and type(value["method"]) is str and value["method"] == "GET"
             and type(value["authentication"]) is str
             and value["authentication"] == "Bearer_header_not_recorded", "fixed_request_descriptor_required")
    _url(value["url"])
    return dict(value)


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class CapturedNativePopulationPage:
    _raw: bytes = dataclasses.field(repr=False)
    _meta: str = dataclasses.field(repr=False)
    _anchor: tuple = dataclasses.field(repr=False)
    _anchor_identity: tuple = dataclasses.field(repr=False)

    def __init__(self):
        raise NativePopulationMatrixError("REFUSED: page_requires_bound_factory")

    def _guard(self):
        _require(type(self) is CapturedNativePopulationPage and self._anchor is self._anchor_identity
                 and self._raw is self._anchor[0] and self._meta is self._anchor[1], "sealed_population_page_changed")

    def metadata(self):
        self._guard()
        return json.loads(self._meta)

    def raw_bytes(self):
        self._guard()
        return self._raw


def capture_native_population_page(*, ordinal, segment, descriptor, request_sha256, raw, raw_sha256,
                                   received_at, http_status, content_type):
    _require(type(ordinal) is int and 1 <= ordinal <= MAXIMUM_PAGES
             and type(segment) is str and segment in {"parent", "child"}, "page_ordinal_or_segment_refused")
    descriptor = _descriptor(descriptor)
    _require(_digest(request_sha256) == hash_payload(descriptor), "page_request_digest_changed")
    _require(type(raw) is bytes and len(raw) <= MAXIMUM_BYTES
             and _digest(raw_sha256) == hash_bytes(raw), "page_raw_bytes_changed")
    _require(type(http_status) is int and http_status == 200 and type(content_type) is str
             and len(content_type) <= 4096 and content_type.split(";", 1)[0].strip().lower() == "application/json",
             "page_HTTP_or_media_refused")
    try:
        parse_utc_timestamp(received_at, "received_at")
    except (ValueError, TypeError):
        raise NativePopulationMatrixError("REFUSED: page_clock_refused") from None
    meta = canonical_json({"ordinal": ordinal, "segment": segment, "request": descriptor,
            "request_sha256": request_sha256, "raw_sha256": raw_sha256, "raw_bytes": len(raw),
            "received_at": received_at, "http_status": http_status, "content_type": content_type})
    obj = object.__new__(CapturedNativePopulationPage)
    anchor = (raw, meta)
    for name, value in (("_raw", raw), ("_meta", meta), ("_anchor", anchor), ("_anchor_identity", anchor)):
        object.__setattr__(obj, name, value)
    obj._guard()
    return obj


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class NativePopulationManifest:
    _json: str = dataclasses.field(repr=False)
    _source_bytes_sha256: str
    _anchor: tuple = dataclasses.field(repr=False)
    _anchor_identity: tuple = dataclasses.field(repr=False)

    def __init__(self):
        raise NativePopulationMatrixError("REFUSED: manifest_requires_bound_factory")

    def to_payload(self):
        _require(type(self) is NativePopulationManifest and self._anchor is self._anchor_identity
                 and self._json is self._anchor[0] and self._source_bytes_sha256 is self._anchor[1],
                 "sealed_population_manifest_changed")
        return json.loads(self._json)


def bind_native_population_manifest(report_raw, report_bytes_sha256):
    _require(type(report_raw) is bytes and len(report_raw) <= 4 * 1024 * 1024
             and _digest(report_bytes_sha256) == hash_bytes(report_raw), "manifest_raw_bytes_changed")
    value = _json(report_raw)
    _require(type(value) is dict and value.get("schema") == REPORT_SCHEMA, "continuation_manifest_schema_refused")
    reported = value.get("report_sha256")
    expected = dict(value)
    expected.pop("report_sha256", None)
    _require(_digest(reported) == hash_payload(expected), "manifest_payload_digest_changed")
    for segment, fields in (("parent_source", {"run", "head", "protocol_sha256", "inventory_sha256",
                                "budget_bytes_sha256", "last_next_url_sha256"}),
                            ("child_source", {"run", "head", "protocol_sha256", "code_identity_sha256"})):
        source = value.get(segment)
        _require(type(source) is dict and fields <= set(source), "source_segment_lineage_missing")
        _require(type(source["run"]) is str and bool(source["run"]) and source["run"] == source["run"].strip()
                 and type(source["head"]) is str and _HEAD.fullmatch(source["head"]) is not None,
                 "source_segment_identity_refused")
        for field in fields - {"run", "head"}:
            _digest(source[field])
    pages = value.get("pages")
    _require(type(pages) is list and PARENT_PAGES < len(pages) <= MAXIMUM_PAGES, "continuation_page_inventory_bound")
    previous = None
    for ordinal, page in enumerate(pages, 1):
        _require(type(page) is dict and type(page.get("ordinal")) is int and page["ordinal"] == ordinal
                 and page.get("segment") == ("parent" if ordinal <= PARENT_PAGES else "child"),
                 "ordered_original_and_child_page_inventory_required")
        request = _descriptor(page.get("request"))
        receipt = page.get("receipt")
        _require(type(receipt) is dict and receipt.get("request_sha256") == hash_payload(request),
                 "manifest_request_receipt_changed")
        _digest(receipt.get("raw_sha256"))
        _require(type(receipt.get("raw_bytes")) is int and 0 <= receipt["raw_bytes"] <= MAXIMUM_BYTES
                 and type(page.get("row_count")) is int and 0 <= page["row_count"] <= 50000,
                 "manifest_page_size_or_row_count_refused")
        try:
            at = parse_utc_timestamp(receipt.get("received_at"), "received_at")
        except (TypeError, ValueError):
            raise NativePopulationMatrixError("REFUSED: manifest_page_clock_refused") from None
        _require(previous is None or previous <= at, "manifest_page_chronology")
        previous = at
        if page.get("next_url") is not None:
            _url(page["next_url"], continuation=True)
    _require(type(pages[PARENT_PAGES - 1].get("next_url")) is str
             and hash_bytes(pages[PARENT_PAGES - 1]["next_url"].encode()) == value["parent_source"]["last_next_url_sha256"],
             "parent_terminal_cursor_pin_changed")
    try:
        _require(previous <= parse_utc_timestamp(value.get("retrieved_at"), "retrieved_at"), "manifest_report_chronology")
    except (TypeError, ValueError):
        raise NativePopulationMatrixError("REFUSED: manifest_report_chronology") from None
    encoded = canonical_json(value)
    obj = object.__new__(NativePopulationManifest)
    anchor = (encoded, report_bytes_sha256)
    for name, item in (("_json", encoded), ("_source_bytes_sha256", report_bytes_sha256),
                       ("_anchor", anchor), ("_anchor_identity", anchor)):
        object.__setattr__(obj, name, item)
    obj.to_payload()
    return obj


def _identifiable(row):
    if type(row) is not dict or type(row.get("ticker")) is not str or type(row.get("settlement_date")) is not str:
        return None
    ticker, at = row["ticker"].strip(), row["settlement_date"].strip()
    if not _TICKER.fullmatch(ticker):
        return None
    try:
        return ticker, _date(at)
    except NativePopulationMatrixError:
        return None


def _row_reason(row):
    if type(row) is not dict:
        return 1
    if any(key in row for key in ("short_volume", "short_sale_volume", "trade_date")):
        return 2
    ticker = row.get("ticker")
    if type(ticker) is not str or _TICKER.fullmatch(ticker) is None:
        return 3
    try:
        at = _date(row.get("settlement_date"))
    except NativePopulationMatrixError:
        return 4
    if not PARAMS["settlement_date.gte"] <= at <= PARAMS["settlement_date.lte"]:
        return 5
    quantity = row.get("short_interest")
    return 0 if type(quantity) is int and 0 <= quantity <= 10**18 else 6


def _little_bytes(values):
    _require(values.itemsize == 4, "32_bit_compact_integer_platform_required")
    if sys.byteorder != "little":
        values.byteswap()
    return values.tobytes()


def _matrix_digest(header, queries, refusals):
    digest = hashlib.sha256()
    for part in (b"SI-NATIVE-CLASS-MATRIX-v1\n", header, b"\n", queries, b"\n", refusals):
        digest.update(part)
    return digest.hexdigest()


def _seal_matrix(header, queries, refusals, digest):
    obj = object.__new__(NativePopulationClassMatrix)
    anchor = (header, queries, refusals, digest)
    for name, value in zip(("_header", "_queries", "_refusals", "_digest"), anchor):
        object.__setattr__(obj, name, value)
    object.__setattr__(obj, "_anchor", anchor)
    object.__setattr__(obj, "_anchor_identity", anchor)
    obj._guard()
    return obj


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class NativePopulationClassMatrix:
    _header: bytes = dataclasses.field(repr=False)
    _queries: bytes = dataclasses.field(repr=False)
    _refusals: bytes = dataclasses.field(repr=False)
    _digest: str
    _anchor: tuple = dataclasses.field(repr=False)
    _anchor_identity: tuple = dataclasses.field(repr=False)

    def __init__(self):
        raise NativePopulationMatrixError("REFUSED: matrix_requires_bound_factory")

    def _guard(self):
        _require(type(self) is NativePopulationClassMatrix and self._anchor is self._anchor_identity
                 and all(current is expected for current, expected in zip(
                    (self._header, self._queries, self._refusals, self._digest), self._anchor)),
                 "sealed_class_matrix_changed")

    @property
    def sha256(self):
        self._guard()
        return self._digest

    def header(self):
        self._guard()
        return json.loads(self._header)

    def parts(self):
        self._guard()
        return self._header, self._queries, self._refusals

    def iter_queries(self):
        self._guard()
        header = self.header()
        symbols, dates = header["symbols"], header["settlements"]
        for ordinal, (symbol, at, page, row) in enumerate(_QUERY.iter_unpack(self._queries), 1):
            self._guard()
            ticker, settlement = symbols[symbol], dates[at]
            descriptor = {"method": "GET", "url": "https://api.massive.com/v3/reference/tickers/" + quote(ticker, safe=""),
                          "params": {"date": settlement}, "authentication": "Bearer_header_not_recorded"}
            yield {"query_ordinal": ordinal, "ticker": ticker, "settlement_date": settlement,
                   "request": descriptor, "request_sha256": hash_payload(descriptor),
                   "source_origin": {"page_ordinal": page, "row_index": row,
                        "source_file_sha256": header["page_origins"][page - 1]["raw_sha256"]}}

    def iter_refusals(self):
        self._guard()
        header = self.header()
        for symbol, at, page, row, primary, original in _REFUSAL.iter_unpack(self._refusals):
            self._guard()
            yield {"ticker": None if symbol < 0 else header["symbols"][symbol],
                   "settlement_date": None if at < 0 else header["settlements"][at],
                   "source_origin": {"page_ordinal": page, "row_index": row,
                        "source_file_sha256": header["page_origins"][page - 1]["raw_sha256"]},
                   "refusal_reasons": [REASONS[primary]] + ([REASONS[original]] if original and original != primary else [])}


def rebuild_native_population_class_matrix(header_raw, queries_raw, refusals_raw, expected_matrix_sha256):
    """Rehydrate fixed protected parts, not authenticate files or a raw chain.

    The runtime must authenticate its fixed byte pins and source custody first.
    This factory requires that exact matrix digest and verifies compact format
    invariants without rereading original pages for every future class query.
    """
    maximum_rows = MAXIMUM_PAGES * 50000
    _require(type(header_raw) is bytes and len(header_raw) <= 32 * 1024 * 1024
             and type(queries_raw) is bytes and len(queries_raw) <= maximum_rows * _QUERY.size
             and type(refusals_raw) is bytes and len(refusals_raw) <= maximum_rows * _REFUSAL.size,
             "bounded_immutable_matrix_parts_required")
    _require(_digest(expected_matrix_sha256) == _matrix_digest(header_raw, queries_raw, refusals_raw),
             "protected_matrix_digest_changed")
    header = _json(header_raw)
    _require(type(header) is dict and header.get("schema") == SCHEMA
             and header.get("format_policy_sha256") == hash_payload(matrix_policy()), "saved_matrix_policy_refused")
    _require(canonical_json(header.get("authority")) == canonical_json(_authority()), "saved_matrix_authority_refused")
    for field in ("source_manifest_bytes_sha256", "source_manifest_payload_sha256", "queries_sha256", "refusals_sha256"):
        _digest(header.get(field))
    _require(header["queries_sha256"] == hash_bytes(queries_raw)
             and header["refusals_sha256"] == hash_bytes(refusals_raw), "saved_matrix_component_digest_changed")
    for field in ("source_row_count", "query_count", "refusal_count"):
        _require(type(header.get(field)) is int and 0 <= header[field] <= maximum_rows, "saved_matrix_count_refused")
    _require(type(header.get("query_record_bytes")) is int and header["query_record_bytes"] == _QUERY.size
             and type(header.get("refusal_record_bytes")) is int and header["refusal_record_bytes"] == _REFUSAL.size
             and len(queries_raw) == header["query_count"] * _QUERY.size
             and len(refusals_raw) == header["refusal_count"] * _REFUSAL.size
             and header["source_row_count"] == header["query_count"] + header["refusal_count"],
             "saved_matrix_record_counts_changed")
    symbols, dates, origins = header.get("symbols"), header.get("settlements"), header.get("page_origins")
    _require(type(symbols) is list and all(type(value) is str and _TICKER.fullmatch(value) for value in symbols)
             and symbols == sorted(set(symbols)), "saved_matrix_symbol_table_refused")
    _require(type(dates) is list and all(_date(value) == value for value in dates)
             and dates == sorted(set(dates)), "saved_matrix_date_table_refused")
    _require(type(origins) is list and PARENT_PAGES < len(origins) <= MAXIMUM_PAGES,
             "saved_matrix_page_origins_refused")
    previous_clock = None
    for ordinal, origin in enumerate(origins, 1):
        _require(type(origin) is dict and type(origin.get("ordinal")) is int and origin["ordinal"] == ordinal
                 and origin.get("segment") == ("parent" if ordinal <= PARENT_PAGES else "child"),
                 "saved_matrix_source_segment_changed")
        for field in ("request_sha256", "raw_sha256"):
            _digest(origin.get(field))
        try:
            clock = parse_utc_timestamp(origin.get("received_at"), "received_at")
        except (TypeError, ValueError):
            raise NativePopulationMatrixError("REFUSED: saved_matrix_source_clock_refused") from None
        _require(previous_clock is None or previous_clock <= clock, "saved_matrix_source_chronology")
        previous_clock = clock
    for source_name, required in (("parent_source", {"run", "head", "protocol_sha256", "inventory_sha256",
                                     "budget_bytes_sha256", "last_next_url_sha256"}),
                                 ("child_source", {"run", "head", "protocol_sha256", "code_identity_sha256"})):
        source = header.get(source_name)
        _require(type(source) is dict and required <= set(source) and type(source["run"]) is str and bool(source["run"])
                 and type(source["head"]) is str and _HEAD.fullmatch(source["head"]), "saved_matrix_lineage_refused")
        for field in required - {"run", "head"}:
            _digest(source[field])
    _require(type(header.get("complete_advertised_page_chain_reconstructed")) is bool
             and header["complete_advertised_page_chain_reconstructed"] is True
             and header.get("refusal_codes") == list(REASONS)
             and header.get("scope") == "reported_provider_population_not_US_universe_or_historical_PIT"
             and header.get("publication_scope") == "private_only_no_rows_or_fitness_publication",
             "saved_matrix_scope_refused")
    bitmap = bytearray((len(origins) * 50000 + 7) // 8)
    page_counts, page_max = [0] * len(origins), [-1] * len(origins)
    def mark(page, row):
        _require(1 <= page <= len(origins) and 0 <= row < 50000, "saved_matrix_origin_bounds")
        number = (page - 1) * 50000 + row
        offset, bit = divmod(number, 8)
        _require(not bitmap[offset] & (1 << bit), "saved_matrix_duplicate_row_origin")
        bitmap[offset] |= 1 << bit
        page_counts[page - 1] += 1
        page_max[page - 1] = max(page_max[page - 1], row)
    last_key = None
    for symbol, at, page, row in _QUERY.iter_unpack(queries_raw):
        _require(symbol < len(symbols) and at < len(dates) and PARAMS["settlement_date.gte"] <= dates[at] <= PARAMS["settlement_date.lte"],
                 "saved_matrix_query_index_bounds")
        key = symbol, at
        _require(last_key is None or last_key < key, "saved_matrix_query_slots_not_unique_sorted")
        last_key = key
        mark(page, row)
    refusal_groups = {}
    def has_query(key):
        low, high = 0, header["query_count"]
        while low < high:
            middle = (low + high) // 2
            candidate = _QUERY.unpack_from(queries_raw, middle * _QUERY.size)[:2]
            if candidate < key:
                low = middle + 1
            else:
                high = middle
        return low < header["query_count"] and _QUERY.unpack_from(queries_raw, low * _QUERY.size)[:2] == key
    for symbol, at, page, row, primary, original in _REFUSAL.iter_unpack(refusals_raw):
        _require((symbol == at == -1) or (0 <= symbol < len(symbols) and 0 <= at < len(dates)),
                 "saved_matrix_refusal_index_bounds")
        _require(1 <= primary <= 7 and (original == primary if primary != 7 else 0 <= original <= 6),
                 "saved_matrix_refusal_code_changed")
        if symbol >= 0:
            key = symbol, at
            _require(not has_query(key), "saved_matrix_query_refusal_collision")
            count, all_duplicate = refusal_groups.get(key, (0, True))
            refusal_groups[key] = count + 1, all_duplicate and primary == 7
        else:
            _require(primary != 7, "unidentifiable_duplicate_refusal_refused")
        mark(page, row)
    _require(all((count >= 2 and all_duplicate) or (count == 1 and not all_duplicate)
                 for count, all_duplicate in refusal_groups.values()), "saved_matrix_duplicate_refusal_group_changed")
    _require(all(count == maximum + 1 for count, maximum in zip(page_counts, page_max)),
             "saved_matrix_source_row_origin_gap")
    return _seal_matrix(header_raw, queries_raw, refusals_raw, expected_matrix_sha256)


def freeze_native_population_class_matrix(manifest, pages):
    _require(type(manifest) is NativePopulationManifest, "exact_bound_population_manifest_required")
    inventory = manifest.to_payload()
    policy_sha256 = hash_payload(matrix_policy())
    symbols, dates, groups = {}, {}, {}
    rows = array("i")
    expected_url, seen, origins = INITIAL_URL, set(), []
    iterator = iter(pages)
    for expected in inventory["pages"]:
        _require(hash_payload(matrix_policy()) == policy_sha256, "matrix_policy_changed_during_replay")
        try:
            page = next(iterator)
        except StopIteration:
            raise NativePopulationMatrixError("REFUSED: missing_bound_population_page") from None
        _require(hash_payload(matrix_policy()) == policy_sha256, "matrix_policy_changed_during_replay")
        _require(type(page) is CapturedNativePopulationPage, "exact_bound_population_page_required")
        meta = page.metadata()
        receipt = expected["receipt"]
        _require(meta["ordinal"] == expected["ordinal"] and meta["segment"] == expected["segment"]
                 and meta["request"] == expected["request"] and meta["request"]["url"] == expected_url
                 and expected_url not in seen, "population_page_chain_or_segment_changed")
        seen.add(expected_url)
        _require(all(meta[key] == receipt.get(key) for key in ("request_sha256", "raw_sha256", "raw_bytes",
                     "received_at", "http_status", "content_type")), "population_page_receipt_changed")
        body = _json(page.raw_bytes())
        _require(type(body) is dict and type(body.get("status")) is str and body["status"] == "OK"
                 and type(body.get("results")) is list and len(body["results"]) == expected["row_count"]
                 and len(body["results"]) <= 50000, "population_page_envelope_changed")
        if "count" in body:
            _require(type(body["count"]) is int and body["count"] == len(body["results"]), "source_page_count_changed")
        next_url = body.get("next_url")
        _require(next_url == expected.get("next_url"), "raw_population_cursor_changed")
        if next_url is not None:
            _url(next_url, continuation=True)
        expected_url = next_url
        origins.append({key: meta[key] for key in ("ordinal", "segment", "request_sha256", "raw_sha256", "received_at")})
        for row_index, row in enumerate(body["results"]):
            slot, reason = _identifiable(row), _row_reason(row)
            if slot is None:
                symbol = at = -1
            else:
                symbol = symbols.setdefault(slot[0], len(symbols))
                at = dates.setdefault(slot[1], len(dates))
                key = symbol, at
                previous = groups.get(key)
                if previous is None:
                    groups[key] = (len(rows) // 5, 1)
                else:
                    groups[key] = (previous[0], previous[1] + 1)
            rows.extend((symbol, at, meta["ordinal"], row_index, reason))
        del body, page
    try:
        next(iterator)
    except StopIteration:
        pass
    else:
        raise NativePopulationMatrixError("REFUSED: unbound_extra_population_page")
    _require(expected_url is None, "advertised_population_page_chain_incomplete")
    _require(hash_payload(matrix_policy()) == policy_sha256, "matrix_policy_changed_during_replay")
    sorted_symbols, sorted_dates = sorted(symbols), sorted(dates)
    symbol_map = {old: new for new, token in enumerate(sorted_symbols) for old in (symbols[token],)}
    date_map = {old: new for new, token in enumerate(sorted_dates) for old in (dates[token],)}
    queries, refusals = array("I"), array("i")
    for symbol, at in sorted(groups, key=lambda key: (symbol_map[key[0]], date_map[key[1]])):
        first, count = groups[(symbol, at)]
        start = first * 5
        if count == 1 and rows[start + 4] == 0:
            queries.extend((symbol_map[symbol], date_map[at], rows[start + 2], rows[start + 3]))
    for start in range(0, len(rows), 5):
        symbol, at, page, row, reason = rows[start:start + 5]
        duplicate = symbol >= 0 and groups[(symbol, at)][1] > 1
        if reason or duplicate:
            refusals.extend((symbol_map.get(symbol, -1), date_map.get(at, -1), page, row,
                             7 if duplicate else reason, reason))
    qbytes, rbytes = _little_bytes(queries), _little_bytes(refusals)
    header = {"schema": SCHEMA, "format_policy_sha256": policy_sha256,
              "source_manifest_bytes_sha256": manifest._source_bytes_sha256,
              "source_manifest_payload_sha256": inventory["report_sha256"],
              "parent_source": inventory["parent_source"], "child_source": inventory["child_source"],
              "page_origins": origins, "symbols": sorted_symbols, "settlements": sorted_dates,
              "source_row_count": len(rows) // 5, "query_count": len(queries) // 4,
              "refusal_count": len(refusals) // 6, "query_record_bytes": _QUERY.size,
              "refusal_record_bytes": _REFUSAL.size, "queries_sha256": hash_bytes(qbytes),
              "refusals_sha256": hash_bytes(rbytes), "refusal_codes": list(REASONS),
              "complete_advertised_page_chain_reconstructed": True,
              "scope": "reported_provider_population_not_US_universe_or_historical_PIT",
              "publication_scope": "private_only_no_rows_or_fitness_publication", "authority": _authority()}
    hbytes = canonical_json(header).encode()
    digest = _matrix_digest(hbytes, qbytes, rbytes)
    return _seal_matrix(hbytes, qbytes, rbytes, digest)
