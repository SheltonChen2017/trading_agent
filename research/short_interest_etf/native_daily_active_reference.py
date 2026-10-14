"""Distinct source-only DAILY active-panel evidence, not two-panel coverage.

No current status, class, denomination or venue is projected over another day.
Original raw pages and the known TICKERS composite-native index remain the
authority for each compact row locator. Missing/unfinished days do not acquire
a report from a caller completion flag or fabricated inactive panel.
"""
from __future__ import annotations

from collections import defaultdict
import dataclasses
from datetime import date
import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf.contracts import parse_utc_timestamp
import research.short_interest_etf.native_dated_identity as identity
import research.short_interest_etf.native_listed_venue_namespace as venue

ENDPOINT = identity.ENDPOINT
FROM, TO = "2022-01-03", "2026-08-31"
EXPECTED_SESSIONS = 1169
SESSION_SHA256 = "f89d3ed418b4f821516d10c41f0ff4fc04db1d2bc66d2e8f507ea9f5242cb7b2"
MAXIMUM_RESPONSE_BYTES = 2 * 1024 * 1024
MAXIMUM_PAGE_ROWS = 1000
MAXIMUM_PAGES_PER_DAY = 64
MAXIMUM_DAY_CHAINS = 8
MAXIMUM_TOTAL_BYTES = 4 * 1024 * 1024 * 1024
MAXIMUM_REQUESTS = EXPECTED_SESSIONS * MAXIMUM_PAGES_PER_DAY
MAXIMUM_ROWS = MAXIMUM_REQUESTS * MAXIMUM_PAGE_ROWS
MAXIMUM_DAY_REPORT_BYTES = 256 * 1024 * 1024
ROW_FIELDS = identity.ROW_FIELDS
CompositeNativeIndex = identity.CompositeNativeIndex
_HASH = re.compile(r"[0-9a-f]{64}\Z")


class DailyActiveReferenceError(ValueError):
    pass


def _require(value, reason):
    if not value:
        raise DailyActiveReferenceError("REFUSED: " + reason)


def _authority():
    return {"source_only": True, "latest_revised_only": True, "active_panel_only": True,
        "inactive_panel_captured": False, "full_listing_lifecycle_coverage_proven": False,
        "historical_intervals_admitted": False, "issuer_domicile_assertion": None,
        "source_admitted": False, "price_volume_admitted": False, "same_class_denominator_admitted": False,
        "historical_identity_admitted": False, "market_cap_admitted": False,
        "USD_processing_permitted": False, "point_in_time_data": False,
        "actual_input_execution_admitted": False, "ready_for_empirical_backtest": False,
        "outcome_looks": 0, "allocated_alpha": 0, "qc_attempts": 0, "trading_authority": False}


def daily_active_policy():
    return {"schema": "si-daily-active-reference-policy-draft-v1", "endpoint": ENDPOINT,
        "documentation": "https://massive.com/docs/rest/stocks/tickers/all-tickers",
        "from": FROM, "to": TO, "sessions": EXPECTED_SESSIONS, "sessions_sha256": SESSION_SHA256,
        "active_panels": [True], "not_two_panel_settlement_stage": True,
        "query_fields": {"market": "stocks", "type": "CS", "limit": "1000", "sort": "ticker", "order": "asc"},
        "maximum_pages_per_day": MAXIMUM_PAGES_PER_DAY, "maximum_requests": MAXIMUM_REQUESTS,
        "maximum_response_bytes": MAXIMUM_RESPONSE_BYTES, "maximum_page_rows": MAXIMUM_PAGE_ROWS,
        "maximum_total_bytes": MAXIMUM_TOTAL_BYTES, "maximum_rows": MAXIMUM_ROWS,
        "maximum_concurrent_day_chains": MAXIMUM_DAY_CHAINS,
        "budget": "one_exclusive_global_claim_whole_2MiB_1000rows_reserved_before_each_START_failed_unknown_bodies_charged_ceiling",
        "automatic_retries": 0, "pagination": "exact_observed_same_active_date_fixed_origin_path_cursor_no_secret",
        "coverage": "each_day_only_complete_actual_active_chain_no_inactive_or_terminal_coverage_inference",
        "row_fields": list(ROW_FIELDS), "known_source_fields": sorted(identity._KNOWN),
        "namespace_policy_sha256": hash_payload(venue.venue_policy()),
        "required_source_candidate_fields": "literal_active_true_CS_us_stocks_declared_primary_MIC_positive_10digitCIK_usd_composite_class_unique_native_owner",
        "collisions": "all_identifiable_malformed_duplicate_key_ticker_composite_and_class_native_peers_quarantined",
        "temporal": "source_assertion_on_exact_request_date_no_current_metadata_backdating_or_interval_projection",
        "publication": "protected_ignored_private_pages_rows_origins_only_not_public_fitness",
        "authority": _authority()}


POLICY_SHA256 = "PENDING"


def _clock(value):
    try:
        return parse_utc_timestamp(value, "source_clock")
    except (TypeError, ValueError):
        raise DailyActiveReferenceError("REFUSED: UTC_source_clock_required") from None


def _date(value):
    _require(type(value) is str and len(value) == 10, "canonical_query_date")
    try:
        _require(date.fromisoformat(value).isoformat() == value and FROM <= value <= TO, "canonical_query_date")
    except ValueError:
        raise DailyActiveReferenceError("REFUSED: canonical_query_date") from None
    return value


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class DailyActiveReferencePlan:
    _sessions: tuple = dataclasses.field(repr=False)
    _bytes: bytes = dataclasses.field(repr=False)
    _anchor: tuple = dataclasses.field(repr=False)
    _identity: tuple = dataclasses.field(repr=False)

    def __init__(self):
        raise DailyActiveReferenceError("REFUSED: frozen_plan_factory_required")

    def _guard(self):
        _require(type(self) is DailyActiveReferencePlan and type(self._anchor) is tuple and len(self._anchor) == 2
                 and self._anchor is self._identity and self._sessions is self._anchor[0]
                 and self._bytes is self._anchor[1], "sealed_daily_plan_changed")

    def sessions(self):
        self._guard()
        return self._sessions

    def to_bytes(self):
        self._guard()
        return self._bytes

    def to_payload(self):
        return json.loads(self.to_bytes())

    @property
    def sha256(self):
        return hash_bytes(self.to_bytes())


def freeze_daily_active_plan(sessions, *, calendar_sha256):
    _require(type(sessions) is tuple and len(sessions) == EXPECTED_SESSIONS
        and sessions == tuple(sorted(set(sessions))) and all(_date(at) == at for at in sessions)
        and hash_payload(list(sessions)) == SESSION_SHA256, "exact_all_1169_shared_calendar_sessions_required")
    _require(type(calendar_sha256) is str and _HASH.fullmatch(calendar_sha256), "independent_calendar_pin_required")
    raw = canonical_json({"schema": "si-daily-active-reference-plan-draft-v1",
        "policy_sha256": hash_payload(daily_active_policy()), "calendar_sha256": calendar_sha256,
        "sessions_sha256": SESSION_SHA256, "day_count": EXPECTED_SESSIONS,
        "maximum_requests": MAXIMUM_REQUESTS, "maximum_total_bytes": MAXIMUM_TOTAL_BYTES,
        "maximum_rows": MAXIMUM_ROWS, "maximum_concurrent_day_chains": MAXIMUM_DAY_CHAINS,
        "calendar_custody_not_proven_by_factory": True, "authority": _authority()}).encode()
    result = object.__new__(DailyActiveReferencePlan)
    anchor = (sessions, raw)
    for name, item in (("_sessions", sessions), ("_bytes", raw), ("_anchor", anchor), ("_identity", anchor)):
        object.__setattr__(result, name, item)
    return result


def request_descriptor(plan, day_ordinal):
    _require(type(plan) is DailyActiveReferencePlan and type(day_ordinal) is int
             and 1 <= day_ordinal <= len(plan.sessions()), "exact_plan_day_ordinal_required")
    return {"method": "GET", "url": ENDPOINT,
        "params": {"market": "stocks", "type": "CS", "date": plan.sessions()[day_ordinal - 1],
                   "active": "true", "limit": "1000", "sort": "ticker", "order": "asc"},
        "authentication": "Bearer_header_not_recorded", "plan_sha256": plan.sha256, "day_ordinal": day_ordinal}


def first_url(plan, day_ordinal):
    value = request_descriptor(plan, day_ordinal)
    return value["url"] + "?" + urlencode(value["params"])


def page_request_sha256(url):
    _require(type(url) is str, "exact_clean_request_URL_required")
    return hash_payload({"method": "GET", "url": url, "authentication": "Bearer_header_not_recorded"})


def next_url(value, at):
    _date(at)
    _require(type(value) is str and 1 <= len(value) <= 16384, "pagination_URL_shape")
    parsed = urlsplit(value)
    _require(parsed.scheme == "https" and parsed.netloc == "api.massive.com"
             and parsed.path == "/v3/reference/tickers" and not parsed.fragment, "pagination_origin_or_path")
    try:
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        raise DailyActiveReferenceError("REFUSED: pagination_query_shape") from None
    _require(pairs and len({name for name, _ in pairs}) == len(pairs), "pagination_duplicate_fields")
    query = dict(pairs)
    expected = {"market": "stocks", "type": "CS", "date": at, "active": "true", "limit": "1000", "sort": "ticker", "order": "asc"}
    _require(set(query) <= set(expected) | {"cursor"} and "cursor" in query, "pagination_cursor_or_secret_query")
    _require(1 <= len(query["cursor"]) <= 8192 and all(33 <= ord(char) <= 126 for char in query["cursor"]), "pagination_cursor_shape")
    _require(all(name not in query or query[name] == value for name, value in expected.items()), "pagination_scope_changed")
    return value


class _Pairs(list):
    def values(self, name):
        return [value for key, value in self if key == name]


class _Numeric(str):
    pass


class _Nonfinite(str):
    pass


def _text(value, maximum=128):
    value = identity._text(value, maximum)
    if value is not None:
        try:
            value.encode("utf-8")
        except UnicodeError:
            return None
    return value


def _collision(value):
    return _text(value.strip()) if type(value) is str else None


def page_payload(raw):
    _require(type(raw) is bytes and len(raw) <= MAXIMUM_RESPONSE_BYTES, "bounded_immutable_page_bytes")
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_Pairs,
                             parse_float=_Numeric, parse_constant=_Nonfinite)
    except (UnicodeError, ValueError, RecursionError):
        raise DailyActiveReferenceError("REFUSED: source_UTF8_JSON_refused") from None
    _require(type(payload) is _Pairs, "source_page_envelope_required")
    names = [name for name, _ in payload]
    _require(len(names) == len(set(names)) and set(names) <= {"status", "results", "next_url", "request_id", "count"},
             "source_envelope_duplicate_or_unknown_fields")
    value = dict(payload)
    _require(value.get("status") == "OK" and type(value.get("results")) is list
             and type(value["results"]) is not _Pairs and len(value["results"]) <= MAXIMUM_PAGE_ROWS,
             "source_page_contract")
    if "count" in value:
        _require(type(value["count"]) is int and value["count"] == len(value["results"]), "source_count_conflict")
    _require(value.get("next_url") is None or type(value["next_url"]) is str, "pagination_URL_shape")
    if "request_id" in value:
        _require(_text(value["request_id"], 256) is not None, "source_request_id_shape")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class CapturedDailyActiveReferencePage:
    query_date: str
    ordinal: int
    request_url: str
    raw: bytes = dataclasses.field(repr=False)
    request_started_at: str
    received_at: str
    http_status: int
    content_type: str
    _anchor: tuple = dataclasses.field(init=False, repr=False)

    def __post_init__(self):
        _require(type(self) is CapturedDailyActiveReferencePage, "exact_daily_active_capture_type")
        anchored = hasattr(self, "_anchor")
        if anchored:
            self._guard()
        _date(self.query_date)
        _require(type(self.ordinal) is int and 1 <= self.ordinal <= MAXIMUM_PAGES_PER_DAY, "bounded_day_page_ordinal")
        _require(type(self.request_url) is str and len(self.request_url) <= 16384 and type(self.raw) is bytes
                 and len(self.raw) <= MAXIMUM_RESPONSE_BYTES, "bounded_immutable_page_and_URL")
        _require(type(self.http_status) is int and self.http_status == 200 and type(self.content_type) is str
                 and self.content_type.split(";", 1)[0].strip().lower() == "application/json", "successful_JSON_page_required")
        _require(_clock(self.request_started_at) <= _clock(self.received_at), "source_page_chronology")
        if not anchored:
            object.__setattr__(self, "_anchor", self._parts())

    def _parts(self):
        return (self.query_date, self.ordinal, self.request_url, self.raw, self.request_started_at,
                self.received_at, self.http_status, self.content_type)

    def _guard(self):
        _require(type(self) is CapturedDailyActiveReferencePage and type(self._anchor) is tuple
                 and len(self._anchor) == 8 and all(current is old for current, old in zip(self._parts(), self._anchor)),
                 "sealed_daily_active_capture_changed")


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class DailyActiveReferenceQualification:
    _bytes: bytes = dataclasses.field(repr=False)
    _rows: tuple = dataclasses.field(repr=False)
    _plan: DailyActiveReferencePlan = dataclasses.field(repr=False)
    _index: CompositeNativeIndex = dataclasses.field(repr=False)
    _anchor: tuple = dataclasses.field(repr=False)
    _identity: tuple = dataclasses.field(repr=False)

    def __init__(self):
        raise DailyActiveReferenceError("REFUSED: bound_daily_active_factory_required")

    def _guard(self):
        _require(type(self) is DailyActiveReferenceQualification and type(self._anchor) is tuple and len(self._anchor) == 4
             and self._anchor is self._identity and all(current is old for current, old in zip(
                 (self._bytes, self._rows, self._plan, self._index), self._anchor)), "sealed_daily_active_report_changed")
        self._plan._guard(); self._index._guard()

    def to_bytes(self):
        self._guard()
        return self._bytes

    def to_payload(self):
        return json.loads(self.to_bytes())

    @property
    def sha256(self):
        return hash_bytes(self.to_bytes())

    def iter_rows(self):
        self._guard()
        for row in self._rows:
            self._guard()
            yield row

    def require_actual_execution(self):
        self._guard()
        raise DailyActiveReferenceError("REFUSED: actual_execution_gates_not_supplied")


def qualify_daily_active_reference(plan, day_ordinal, pages, index, *, started_at, retrieved_at):
    _require(type(plan) is DailyActiveReferencePlan and type(index) is CompositeNativeIndex
             and type(pages) is tuple and 1 <= len(pages) <= MAXIMUM_PAGES_PER_DAY
             and all(type(page) is CapturedDailyActiveReferencePage for page in pages), "exact_frozen_daily_pages_and_original_index_required")
    at = request_descriptor(plan, day_ordinal)["params"]["date"]
    source = index.metadata()
    beginning, ending = _clock(started_at), _clock(retrieved_at)
    _require(beginning <= ending, "day_report_chronology")
    expected, seen, previous = first_url(plan, day_ordinal), set(), beginning
    origins, rows, peers = [], [], []
    for ordinal, page in enumerate(pages, 1):
        page._guard()
        _require(page.query_date == at and page.ordinal == ordinal and page.request_url == expected
                 and expected not in seen, "exact_dated_active_page_chain_required")
        seen.add(expected)
        began, received = _clock(page.request_started_at), _clock(page.received_at)
        _require(previous <= began <= received <= ending, "enclosing_serial_day_page_chronology")
        payload = page_payload(page.raw)
        following = payload.get("next_url")
        if following is not None:
            following = next_url(following, at)
        _require((ordinal == len(pages)) == (following is None), "complete_actual_advertised_active_chain_required")
        origins.append({"query_date": at, "active_panel": True, "ordinal": ordinal,
            "request_url": page.request_url, "request_sha256": page_request_sha256(page.request_url),
            "raw_sha256": hash_bytes(page.raw), "raw_bytes": len(page.raw),
            "request_started_at": page.request_started_at, "received_at": page.received_at,
            "http_status": page.http_status, "content_type": page.content_type, "next_url": following})
        for row_index, original in enumerate(payload["results"]):
            reasons = []
            if type(original) is not _Pairs:
                original = _Pairs()
                reasons.append("source_row_not_object")
            keys = [key for key, _ in original]
            if len(keys) != len(set(keys)):
                reasons.append("duplicate_source_row_JSON_key")
            if set(keys) - identity._KNOWN:
                reasons.append("unknown_source_row_fields")
            def single(name):
                values = original.values(name)
                return values[0] if len(values) == 1 else None
            ticker, composite, cls = _text(single("ticker")), identity._figi(single("composite_figi")), identity._figi(single("share_class_figi"))
            collision = tuple(tuple(sorted(set(filter(None, (normal(value) for value in original.values(name))))))
                for name, normal in (("ticker", _collision), ("composite_figi", identity._collision_figi), ("share_class_figi", identity._collision_figi)))
            peers.append(collision)
            if ticker is None or composite is None or cls is None:
                reasons.append("missing_or_malformed_dated_identity_fields")
            if (single("locale"), single("market"), single("type")) != ("us", "stocks", "CS"):
                reasons.append("outside_dated_US_market_common_stock")
            if single("active") is not True:
                reasons.append("source_active_panel_assertion_conflict")
            owners = index.lookup(composite)
            native, master_row = None, None
            if len(owners) != 1 or owners[0][2] is None:
                reasons.append("original_native_composite_owner_missing_or_ambiguous")
            else:
                master_row, native = owners[0][0], owners[0][2]
            optional = []
            for name in ("primary_exchange", "currency_name", "cik", "delisted_utc", "last_updated_utc"):
                value = single(name)
                if value is not None and _text(value) is None:
                    reasons.append("malformed_optional_identity_field")
                    value = None
                if name.endswith("_utc") and value is not None:
                    try:
                        _clock(value)
                    except DailyActiveReferenceError:
                        reasons.append("malformed_optional_identity_clock")
                optional.append(value)
            if optional[2] is None or re.fullmatch(r"[0-9]{10}", optional[2]) is None or int(optional[2]) == 0:
                reasons.append("positive_dated_CIK_missing_or_malformed")
            if optional[1] != "usd":
                reasons.append("dated_USD_currency_name_not_observed")
            namespace = venue.qualify_venue_namespace({"active": single("active"), "primary_exchange": optional[0],
                "locale": _text(single("locale")), "market": _text(single("market")), "type": _text(single("type"))})["venue_namespace_assessment"]
            reasons.extend(namespace["refusal_reasons"])
            for name in ("name", "base_currency_name", "base_currency_symbol", "currency_symbol"):
                value = single(name)
                if value is not None and _text(value, 4096) is None:
                    reasons.append("malformed_optional_identity_field")
            rows.append([ordinal, row_index, ticker, composite, cls, native,
                _text(single("locale")), _text(single("market")), _text(single("type")),
                single("active") if type(single("active")) is bool else None, *optional, master_row, reasons])
        expected, previous = following, received
    ticker_groups, composite_groups, class_natives = defaultdict(set), defaultdict(set), defaultdict(set)
    for number, (peer, row) in enumerate(zip(peers, rows, strict=True)):
        for token in peer[0]:
            ticker_groups[token].add(number)
        for token in peer[1]:
            composite_groups[token].add(number)
        for token in peer[2]:
            class_natives[token].add(row[5] if not row[-1] else None)
    for peer, row in zip(peers, rows, strict=True):
        if any(len(ticker_groups[token]) > 1 for token in peer[0]):
            row[-1].append("duplicate_or_malformed_dated_ticker_peers_quarantined")
        if any(len(composite_groups[token]) > 1 for token in peer[1]):
            row[-1].append("duplicate_or_malformed_dated_composite_peers_quarantined")
        if any(len(class_natives[token]) != 1 or None in class_natives[token] for token in peer[2]):
            row[-1].append("dated_class_native_missing_or_conflicting")
        row[-1] = sorted(set(row[-1]))
        if row[-1]:
            row[5] = None
    immutable = tuple(tuple(row[:-1]) + (tuple(row[-1]),) for row in rows)
    raw = canonical_json({"schema": "si-daily-active-reference-qualified-day-draft-v1", "query_date": at,
        "day_ordinal": day_ordinal, "plan_sha256": plan.sha256, "policy_sha256": hash_payload(daily_active_policy()),
        "started_at": started_at, "retrieved_at": retrieved_at, "active_panel_only": True,
        "complete_actual_active_chain": True, "inactive_panel_captured": False,
        "master_archive_sha256": source["archive_sha256"], "master_CSV_sha256": source["CSV_sha256"],
        "page_origins": origins, "row_fields": list(ROW_FIELDS), "rows": immutable,
        "authority": _authority()}).encode()
    _require(len(raw) <= MAXIMUM_DAY_REPORT_BYTES, "bounded_private_day_report")
    result = object.__new__(DailyActiveReferenceQualification)
    anchor = (raw, immutable, plan, index)
    for name, item in (("_bytes", raw), ("_rows", immutable), ("_plan", plan), ("_index", index),
                       ("_anchor", anchor), ("_identity", anchor)):
        object.__setattr__(result, name, item)
    return result
