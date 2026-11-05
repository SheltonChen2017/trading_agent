"""Private dated US-listing/class relations, not counts or PIT intervals.

One date is qualified after both advertised active panels terminate. Complete
raw response files remain the authority for every row locator. Compact tuples
retain outside/malformed/collision rows rather than expanding full URLs and
master dictionaries into millions of SI cells.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import dataclasses
from decimal import Decimal
import json
import re
from types import MappingProxyType
from urllib.parse import parse_qsl, urlsplit

from data.exchange_calendar import parse_session_date
from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf.contracts import parse_utc_timestamp
import research.short_interest_etf.sharadar_securities_master as master

ENDPOINT = "https://api.massive.com/v3/reference/tickers"
MAXIMUM_PAGES_PER_PANEL = 64
MAXIMUM_RESPONSE_BYTES = 8 * 1024 * 1024
MAXIMUM_PAGE_ROWS = 1000
MAXIMUM_ROWS = 5_000_000
MAXIMUM_TOTAL_BYTES = 4 * 1024 * 1024 * 1024
EXPECTED_DATES = 112
MAXIMUM_REQUESTS = EXPECTED_DATES * 2 * MAXIMUM_PAGES_PER_PANEL
MAXIMUM_DATE_REPORT_BYTES = 256 * 1024 * 1024
_FIGI = re.compile(r"^[A-Z]{2}G[A-Z0-9]{9}$")
_KNOWN = {"active", "base_currency_name", "base_currency_symbol", "cik", "composite_figi",
          "currency_name", "currency_symbol", "delisted_utc", "last_updated_utc", "locale",
          "market", "name", "primary_exchange", "share_class_figi", "ticker", "type"}
ROW_FIELDS = ("page_ordinal", "row_index", "ticker", "composite_figi", "share_class_figi",
              "provider_security_id", "locale", "market", "type", "active", "primary_exchange",
              "currency_name", "cik", "delisted_utc", "last_updated_utc", "master_row_index",
              "refusal_reasons")


class NativeDatedIdentityError(ValueError):
    pass


def _require(value, reason):
    if not value:
        raise NativeDatedIdentityError("REFUSED: " + reason)


def _authority():
    return {"source_only": True, "latest_revised": True, "point_in_time_data": False,
            "source_admitted": False, "historical_effective_intervals_admitted": False,
            "same_class_denominator_admitted": False, "market_cap_admitted": False,
            "ready_for_empirical_backtest": False, "outcome_looks": 0, "qc_attempts": 0,
            "production_authoritative": False, "trading_authority": False}


def identity_policy():
    return {"schema": "si-native-dated-identity-policy-v1", "endpoint": ENDPOINT,
            "documentation": "https://massive.com/docs/rest/stocks/tickers/all-tickers",
            "expected_settlement_dates": EXPECTED_DATES, "active_panels": [True, False],
            "query_fields": {"market": "stocks", "type": "CS", "limit": "1000",
                             "sort": "ticker", "order": "asc"},
            "maximum_pages_per_panel": MAXIMUM_PAGES_PER_PANEL,
            "maximum_requests": MAXIMUM_REQUESTS, "maximum_response_bytes": MAXIMUM_RESPONSE_BYTES,
            "maximum_rows_per_page": MAXIMUM_PAGE_ROWS,
            "maximum_total_bytes": MAXIMUM_TOTAL_BYTES, "maximum_rows": MAXIMUM_ROWS,
            "maximum_date_report_bytes": MAXIMUM_DATE_REPORT_BYTES,
            "cumulative_budget_reservation": "before_attempt_reserve_full_8MiB_and_1000_rows_reclaim_only_actual_successful_page_usage",
            "automatic_retries": 0, "pagination": "exact_observed_fixed_origin_path_cursor_same_scope_no_secret",
            "population": "dated_US_market_commonstock_candidates_not_verified_exchange_or_issuer_domicile",
            "local_filters": {"locale": "us", "market": "stocks", "type": "CS"},
            "outside_and_missing_rule": "all_rows_retained_with_raw_file_and_row_locator",
            "collision_rule": "both_panels_all_identifiable_malformed_peers_ticker_composite_class_axes",
            "native_rule": "unique_original_STOCKS_composite_assertion_no_ticker_fallback_or_FIGI_cast",
            "temporal_rule": "same_date_source_assertion_not_original_availability_or_fabricated_interval",
            "row_fields": list(ROW_FIELDS), "publication": "protected_private_no_rows_or_fitness_in_Git_chat",
            "authority": _authority()}


POLICY_SHA256 = "6c5e29c1a041b14ebb3474f6d49eabe0e87ed649759cd43f71f7664c5b2fdd7b"


def request_descriptor(at, active):
    _require(type(at) is str and parse_session_date(at).isoformat() == at, "canonical_query_date")
    _require(type(active) is bool, "exact_active_panel")
    return {"method": "GET", "url": ENDPOINT,
            "params": {"market": "stocks", "type": "CS", "date": at,
                       "active": "true" if active else "false", "limit": "1000",
                       "sort": "ticker", "order": "asc"}, "authentication": "Bearer_header_not_recorded"}


def next_url(value, at, active):
    _require(type(value) is str and 1 <= len(value) <= 16384, "pagination_URL_shape")
    parsed = urlsplit(value)
    _require(parsed.scheme == "https" and parsed.netloc == "api.massive.com"
             and parsed.path == "/v3/reference/tickers" and not parsed.fragment,
             "pagination_origin_or_path")
    try:
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        raise NativeDatedIdentityError("REFUSED: pagination_query_shape") from None
    _require(pairs and len({key for key, _ in pairs}) == len(pairs), "pagination_query_duplicates")
    query, expected = dict(pairs), request_descriptor(at, active)["params"]
    _require(set(query) <= set(expected) | {"cursor"} and "cursor" in query,
             "pagination_cursor_or_secret_query")
    _require(type(query["cursor"]) is str and 1 <= len(query["cursor"]) <= 8192
             and all(33 <= ord(char) <= 126 for char in query["cursor"]), "pagination_cursor_shape")
    _require(all(key not in query or query[key] == expected_value for key, expected_value in expected.items()),
             "pagination_scope_changed")
    return value


def _json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _require(key not in result, "duplicate_source_JSON_key")
            result[key] = value
        return result
    def finite(value):
        raise NativeDatedIdentityError("REFUSED: nonfinite_source_JSON")
    try:
        _require(type(raw) is bytes and len(raw) <= MAXIMUM_RESPONSE_BYTES, "bounded_immutable_response")
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                          parse_float=Decimal, parse_constant=finite)
    except (UnicodeError, json.JSONDecodeError):
        raise NativeDatedIdentityError("REFUSED: malformed_source_JSON") from None


def page_payload(raw):
    payload = _json(raw)
    _require(type(payload) is dict and set(payload) <= {"status", "results", "next_url", "request_id", "count"}
             and payload.get("status") == "OK" and type(payload.get("results")) is list
             and len(payload["results"]) <= MAXIMUM_PAGE_ROWS, "source_page_contract")
    if "count" in payload:
        _require(type(payload["count"]) is int and payload["count"] == len(payload["results"]), "source_count_conflict")
    _require(payload.get("next_url") is None or type(payload["next_url"]) is str, "pagination_URL_shape")
    return payload


def _text(value, maximum=128):
    return (value if type(value) is str and 1 <= len(value) <= maximum
            and value == value.strip() and all(32 <= ord(char) != 127 for char in value) else None)


def _collision(value):
    return _text(value.strip()) if type(value) is str else None


def _figi(value):
    return value if type(value) is str and _FIGI.fullmatch(value) else None


def _collision_figi(value):
    return _figi(value.strip()) if type(value) is str else None


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class CompositeNativeIndex:
    _bytes: bytes = dataclasses.field(repr=False)
    _metadata_bytes: bytes = dataclasses.field(repr=False)
    _mapping: MappingProxyType = dataclasses.field(repr=False)
    _anchor: tuple = dataclasses.field(repr=False)
    _identity: tuple = dataclasses.field(repr=False)

    def __init__(self):
        raise NativeDatedIdentityError("REFUSED: composite_index_requires_original_archive_factory")

    def _guard(self):
        _require(type(self) is CompositeNativeIndex and self._anchor is self._identity
                 and type(self._anchor) is tuple and len(self._anchor) == 3
                 and all(current is original for current, original in zip(
                     (self._bytes, self._metadata_bytes, self._mapping), self._anchor)),
                 "sealed_composite_index_changed")

    def to_payload(self):
        self._guard()
        return json.loads(self._bytes)

    def metadata(self):
        self._guard()
        return json.loads(self._metadata_bytes)

    def lookup(self, composite):
        self._guard()
        return self._mapping.get(composite, ())


def build_composite_native_index(archive):
    _require(type(archive) is master.CapturedSharadarMasterArchive and archive.table == "tickers",
             "exact_original_TICKERS_archive_required")
    parsed = master._parsed(archive)
    natives, composites = defaultdict(list), defaultdict(list)
    rows = []
    for row in parsed["rows"]:
        raw = master._raw_row(parsed, row)
        if raw.get("table", "").strip() not in {"stocks", "SEP"}:
            continue
        native, composite = raw.get("permaticker"), raw.get("figi")
        key = native.strip().lstrip("0") or "0" if type(native) is str and native.strip().isascii() and native.strip().isdigit() else None
        ckey = _collision_figi(composite)
        index = row["origin"]["row_index"]
        if key is not None:
            natives[key].append(index)
        if ckey is not None:
            composites[ckey].append(index)
        rows.append((index, native, composite, row["normalized"] is not None))
    result = []
    for index, native, composite, valid in rows:
        reasons = []
        if not valid or type(native) is not str or re.fullmatch(r"[1-9][0-9]{0,29}", native) is None:
            reasons.append("malformed_original_native_master_row")
        if _figi(composite) is None:
            reasons.append("missing_or_malformed_original_composite_assertion")
        if len(natives.get(native, ())) != 1:
            reasons.append("ambiguous_original_native_owner")
        if len(composites.get(_collision_figi(composite), ())) != 1:
            reasons.append("ambiguous_original_composite_owner")
        result.append([index, composite if _figi(composite) else None,
                       "sharadar:permaticker:" + native if not reasons else None, reasons])
    payload = {"schema": "si-original-composite-native-index-v1", "archive_sha256": parsed["archive_sha256"],
               "CSV_sha256": parsed["CSV_sha256"], "rows": result, "authority": _authority()}
    raw = canonical_json(payload).encode()
    metadata = canonical_json({key: payload[key] for key in ("schema", "archive_sha256", "CSV_sha256")}).encode()
    groups = defaultdict(list)
    for row in result:
        if row[1] is not None:
            groups[row[1]].append((row[0], row[1], row[2], tuple(row[3])))
    mapping = MappingProxyType({key: tuple(value) for key, value in groups.items()})
    value = object.__new__(CompositeNativeIndex)
    anchor = (raw, metadata, mapping)
    for name, item in (("_bytes", raw), ("_metadata_bytes", metadata), ("_mapping", mapping),
                       ("_anchor", anchor), ("_identity", anchor)):
        object.__setattr__(value, name, item)
    value.to_payload()
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class CapturedDatedIdentityPage:
    query_date: str
    active_panel: bool
    ordinal: int
    request_url: str
    raw: bytes = dataclasses.field(repr=False)
    request_started_at: str
    received_at: str
    http_status: int
    content_type: str
    _anchor: tuple = dataclasses.field(init=False, repr=False)

    def __post_init__(self):
        _require(type(self) is CapturedDatedIdentityPage, "exact_page_capture_type")
        anchored = hasattr(self, "_anchor")
        if anchored:
            self._guard()
        request_descriptor(self.query_date, self.active_panel)
        _require(type(self.ordinal) is int and 1 <= self.ordinal <= MAXIMUM_PAGES_PER_PANEL, "bounded_panel_ordinal")
        _require(type(self.request_url) is str and type(self.raw) is bytes
                 and len(self.raw) <= MAXIMUM_RESPONSE_BYTES, "immutable_page_bytes_and_URL")
        _require(type(self.http_status) is int and self.http_status == 200
                 and type(self.content_type) is str
                 and self.content_type.split(";", 1)[0].strip().lower() == "application/json", "successful_JSON_page_required")
        _require(parse_utc_timestamp(self.request_started_at, "request_started_at")
                 <= parse_utc_timestamp(self.received_at, "received_at"), "capture_page_chronology")
        if not anchored:
            object.__setattr__(self, "_anchor", self._parts())

    def _parts(self):
        return (self.query_date, self.active_panel, self.ordinal, self.request_url, self.raw,
                self.request_started_at, self.received_at, self.http_status, self.content_type)

    def _guard(self):
        _require(type(self) is CapturedDatedIdentityPage and type(self._anchor) is tuple
                 and len(self._anchor) == 9 and all(value is original for value, original in zip(
                    self._parts(), self._anchor)), "capture_page_changed")


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class DatedIdentityQualification:
    _bytes: bytes = dataclasses.field(repr=False)
    _anchor: tuple = dataclasses.field(repr=False)
    _identity: tuple = dataclasses.field(repr=False)

    def __init__(self):
        raise NativeDatedIdentityError("REFUSED: dated_identity_requires_bound_factory")

    def to_bytes(self):
        _require(type(self) is DatedIdentityQualification and self._anchor is self._identity
                 and self._bytes is self._anchor[0], "sealed_dated_identity_changed")
        return self._bytes

    def to_payload(self):
        return json.loads(self.to_bytes())


def qualify_dated_identity(pages, index, *, query_date, started_at, retrieved_at):
    _require(type(pages) is tuple and type(index) is CompositeNativeIndex
             and type(query_date) is str, "exact_pages_and_master_index_required")
    _require(all(type(page) is CapturedDatedIdentityPage for page in pages)
             and tuple((page.active_panel, page.ordinal) for page in pages)
             == tuple(sorted(((page.active_panel, page.ordinal) for page in pages), key=lambda item: (not item[0], item[1]))),
             "exact_ordered_capture_inventory_required")
    source = index.metadata()
    beginning, end = parse_utc_timestamp(started_at, "started_at"), parse_utc_timestamp(retrieved_at, "retrieved_at")
    _require(beginning <= end, "date_report_chronology")
    locators, rows, peers = [], [], []
    previous, consumed = beginning, 0
    for active in (True, False):
        selected = [item for item in pages if type(item) is CapturedDatedIdentityPage and item.active_panel is active]
        _require(selected and len(selected) <= MAXIMUM_PAGES_PER_PANEL, "both_active_panels_required")
        expected, seen = None, set()
        for ordinal, page in enumerate(selected, 1):
            page._guard()
            _require(page.query_date == query_date and page.ordinal == ordinal, "page_query_date_or_ordinal_binding")
            if ordinal == 1:
                from urllib.parse import urlencode
                expected = ENDPOINT + "?" + urlencode(request_descriptor(query_date, active)["params"])
            _require(page.request_url == expected and expected not in seen, "exact_panel_chain_or_cycle")
            seen.add(expected)
            began, received = parse_utc_timestamp(page.request_started_at, "request_started_at"), parse_utc_timestamp(page.received_at, "received_at")
            _require(previous <= began <= received <= end, "enclosing_page_report_chronology")
            payload = page_payload(page.raw)
            next_value = payload.get("next_url")
            if next_value is not None:
                next_value = next_url(next_value, query_date, active)
            _require((ordinal == len(selected)) == (next_value is None), "complete_advertised_panel_chain_required")
            page_number = len(locators) + 1
            locators.append({"query_date": query_date, "active_panel": active, "ordinal": ordinal,
                             "request_url": page.request_url, "request_sha256": hash_payload({"method": "GET", "url": page.request_url, "authentication": "Bearer_header_not_recorded"}),
                             "source_file_sha256": hash_bytes(page.raw), "raw_bytes": len(page.raw),
                             "request_started_at": page.request_started_at, "received_at": page.received_at,
                             "http_status": page.http_status, "content_type": page.content_type, "next_url": next_value})
            for row_number, raw in enumerate(payload["results"]):
                reasons = []
                if type(raw) is not dict:
                    raw, reasons = {}, ["source_row_not_object"]
                if set(raw) - _KNOWN:
                    reasons.append("unknown_source_row_fields")
                ticker, composite, class_figi = _text(raw.get("ticker")), _figi(raw.get("composite_figi")), _figi(raw.get("share_class_figi"))
                peers.append((_collision(raw.get("ticker")), _collision_figi(raw.get("composite_figi")), _collision_figi(raw.get("share_class_figi"))))
                if ticker is None or composite is None or class_figi is None:
                    reasons.append("missing_or_malformed_dated_identity_fields")
                if (raw.get("locale"), raw.get("market"), raw.get("type")) != ("us", "stocks", "CS"):
                    reasons.append("outside_dated_US_listing_common_stock")
                if type(raw.get("active")) is not bool or raw["active"] is not active:
                    reasons.append("active_panel_assertion_conflict")
                master_rows = index.lookup(composite)
                native, master_row = None, None
                if len(master_rows) != 1 or master_rows[0][2] is None:
                    reasons.append("original_native_composite_owner_missing_or_ambiguous")
                else:
                    master_row, native = master_rows[0][0], master_rows[0][2]
                optional = []
                for key in ("primary_exchange", "currency_name", "cik", "delisted_utc", "last_updated_utc"):
                    value = raw.get(key)
                    if value is not None and _text(value) is None:
                        reasons.append("malformed_optional_identity_field")
                        value = None
                    if key.endswith("_utc") and value is not None:
                        try:
                            parse_utc_timestamp(value, key)
                        except ValueError:
                            reasons.append("malformed_optional_identity_clock")
                    optional.append(value)
                if optional[2] is not None and re.fullmatch(r"[0-9]{10}", optional[2]) is None:
                    reasons.append("malformed_optional_CIK")
                for key in ("name", "base_currency_name", "base_currency_symbol", "currency_symbol"):
                    if key in raw and raw[key] is not None and _text(raw[key], maximum=4096) is None:
                        reasons.append("malformed_optional_identity_field")
                rows.append([page_number, row_number, ticker, composite, class_figi, native,
                             _text(raw.get("locale")), _text(raw.get("market")), _text(raw.get("type")),
                             raw.get("active") if type(raw.get("active")) is bool else None,
                             *optional, master_row, reasons])
            consumed += 1
            expected, previous = next_value, received
    _require(consumed == len(pages) and previous <= end, "exact_ordered_capture_inventory_required")
    ticker_counts = Counter(peer[0] for peer in peers if peer[0] is not None)
    comp_classes, class_natives = defaultdict(set), defaultdict(set)
    for peer, row in zip(peers, rows):
        if peer[1] is not None:
            comp_classes[peer[1]].add(peer[2])
        if peer[2] is not None:
            class_natives[peer[2]].add(row[5])
    for peer, row in zip(peers, rows):
        if peer[0] is not None and ticker_counts[peer[0]] != 1:
            row[-1].append("duplicate_dated_ticker_all_copies_quarantined")
        if peer[1] is not None and len(comp_classes[peer[1]]) != 1:
            row[-1].append("conflicting_composite_class_assertions")
        if peer[2] is not None and (len(class_natives[peer[2]]) != 1 or None in class_natives[peer[2]]):
            row[-1].append("class_native_missing_or_conflicting")
        row[-1] = sorted(set(row[-1]))
        if row[-1]:
            row[5] = None
    payload = {"schema": "si-native-dated-identity-qualified-date-v1", "query_date": query_date,
               "policy_sha256": hash_payload(identity_policy()), "started_at": started_at,
               "retrieved_at": retrieved_at, "master_archive_sha256": source["archive_sha256"],
               "master_CSV_sha256": source["CSV_sha256"], "page_origins": locators,
               "row_fields": list(ROW_FIELDS), "rows": rows, "authority": _authority()}
    raw = canonical_json(payload).encode()
    _require(len(raw) <= MAXIMUM_DATE_REPORT_BYTES, "bounded_private_date_report")
    result = object.__new__(DatedIdentityQualification)
    anchor = (raw,)
    for name, item in (("_bytes", raw), ("_anchor", anchor), ("_identity", anchor)):
        object.__setattr__(result, name, item)
    result.to_bytes()
    return result
