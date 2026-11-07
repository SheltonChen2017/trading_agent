"""Generalized source-derived dated class evidence, never execution admission.

Exact SI cells and explicitly chosen anchors are distinct prospective query
plans. No anchor frequency is chosen here. Requested as-of dates and actual
receipt clocks remain separate; no effective interval or historical available
date is fabricated. Current master categories never replace dated source
classifications. Raw responses stay in original private captures.
"""
from __future__ import annotations

from collections import defaultdict
import dataclasses
import hashlib
import json
import re
from urllib.parse import quote

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf.contracts import parse_utc_timestamp
import research.short_interest_etf.massive_class_denominator as lexical
import research.short_interest_etf.native_population_class_matrix as matrices
import research.short_interest_etf.sharadar_securities_master as master

SCHEMA = "si-native-dated-class-reference-v1"
_FIGI = re.compile(r"BBG[0-9A-Z]{9}\Z")


class NativeDatedClassError(ValueError):
    """Fixed refusal codes, never private ticker/body/identifier text."""


def _require(value, reason):
    if not value:
        raise NativeDatedClassError("REFUSED: " + reason)


def _authority():
    return {"source_reference_only": True, "latest_revised_only": True,
            "source_admitted": False, "historical_identity_admitted": False,
            "historical_availability_verified": False, "denominator_admitted": False,
            "actual_input_execution_admitted": False, "outcome_access_authorized": False,
            "qc_authorized": False, "trading_authority": False,
            "actual_outcome_looks": 0, "allocated_alpha": 0, "qc_attempts": 0}


def reference_policy():
    return {"schema": SCHEMA + "-protocol", "query_modes": ["exact_cells", "explicit_anchors"],
            "anchor_frequency_selected": None,
            "population": "source_matrix_valid_tickers_no_caller_symbol_or_active_selection",
            "date_rule": "retain_query_asof_and_actual_receipt_no_fabricated_availability_or_intervals",
            "classification": "dated_type_CS_locale_us_market_stocks_not_backdated_master_or_domicile_claim",
            "denominator": "particular_class_positive_integral_JSON_number_never_weighted_or_issuer_transfer",
            "join": "exact_separate_composite_to_class_to_unique_unchanged_native_permaticker",
            "collision": "all_identifiable_master_and_malformed_response_ID_peers_refusal_only_trim",
            "duplicate_JSON": "all_identifiable_results_ID_values_retained_negatively_no_positive_selection",
            "request_budget": "plan_query_count_requires_later_prospective_runtime_freeze_no_requests_here",
            "authority": _authority()}


def _date(value):
    try:
        return lexical._date(value)
    except lexical.MassiveClassDenominatorError:
        raise NativeDatedClassError("REFUSED: canonical_query_date_required") from None


def _figi(value, *, refusal_only=False):
    if type(value) is not str:
        return None
    token = value.strip() if refusal_only else value
    return token if _FIGI.fullmatch(token) else None


def _native_collision(value):
    if type(value) is str and re.fullmatch(r"[0-9]+", value.strip()):
        return value.strip().lstrip("0") or "0"
    return None


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class NativeClassQueryPlan:
    _matrix: matrices.NativePopulationClassMatrix = dataclasses.field(repr=False)
    _json: str = dataclasses.field(repr=False)
    _digest: str
    _anchor: tuple = dataclasses.field(repr=False)
    _anchor_identity: tuple = dataclasses.field(repr=False)

    def __init__(self):
        raise NativeDatedClassError("REFUSED: plan_requires_source_factory")

    def _guard(self):
        _require(type(self) is NativeClassQueryPlan and self._anchor is self._anchor_identity
                 and self._matrix is self._anchor[0] and self._json is self._anchor[1]
                 and self._digest is self._anchor[2], "sealed_class_plan_changed")
        self._matrix._guard()

    def to_payload(self):
        self._guard()
        return json.loads(self._json)

    @property
    def sha256(self):
        self._guard()
        return self._digest

    def iter_queries(self):
        self._guard()
        spec = self.to_payload()
        if spec["mode"] == "exact_cells":
            values = ((row["ticker"], row["settlement_date"], row["source_origin"])
                      for row in self._matrix.iter_queries())
        elif spec["selected_query_ordinals"] is not None:
            header, qbytes = self._matrix.header(), self._matrix.parts()[1]
            def selected():
                for original_ordinal in spec["selected_query_ordinals"]:
                    symbol, at, page, row = matrices._QUERY.unpack_from(qbytes, (original_ordinal - 1) * matrices._QUERY.size)
                    yield header["symbols"][symbol], header["settlements"][at], {
                        "page_ordinal": page, "row_index": row,
                        "source_file_sha256": header["page_origins"][page - 1]["raw_sha256"]}
            values = selected()
        else:
            values = ((row["ticker"], at, row["source_origin"])
                      for row in spec["source_tickers"] for at in spec["anchor_dates"])
        for ordinal, (ticker, at, origin) in enumerate(values, 1):
            self._guard()
            descriptor = {"method": "GET", "url": "https://api.massive.com/v3/reference/tickers/" + quote(ticker, safe=""),
                          "params": {"date": at}, "authentication": "Bearer_header_not_recorded"}
            payload = {"query_ordinal": ordinal, "ticker": ticker, "query_asof_date": at,
                       "mode": spec["mode"], "source_matrix_sha256": spec["source_matrix_sha256"],
                       "source_origin": origin, "request": descriptor,
                       "request_sha256": hash_payload(descriptor), "plan_sha256": self.sha256}
            encoded = canonical_json(payload)
            ticket = object.__new__(NativeDatedClassQuery)
            anchor = (self, encoded)
            for name, value in (("_plan", self), ("_json", encoded), ("_anchor", anchor), ("_anchor_identity", anchor)):
                object.__setattr__(ticket, name, value)
            yield ticket


def freeze_native_class_query_plan(matrix, *, mode, anchor_dates=None, selected_query_ordinals=None):
    _require(type(matrix) is matrices.NativePopulationClassMatrix, "exact_source_matrix_required")
    _require(type(mode) is str and mode in {"exact_cells", "explicit_anchors"}, "explicit_query_mode_required")
    header = matrix.header()
    source_tickers = []
    if mode == "exact_cells":
        _require(anchor_dates is None and selected_query_ordinals is None, "exact_cells_cannot_silently_add_anchors")
        count = header["query_count"]
    elif selected_query_ordinals is not None:
        _require(anchor_dates is None and type(selected_query_ordinals) is tuple and bool(selected_query_ordinals)
                 and all(type(value) is int and 1 <= value <= header["query_count"] for value in selected_query_ordinals)
                 and selected_query_ordinals == tuple(sorted(set(selected_query_ordinals))),
                 "explicit_source_cell_anchors_required")
        count = len(selected_query_ordinals)
    else:
        _require(type(anchor_dates) is tuple and bool(anchor_dates), "explicit_prospective_anchor_dates_required")
        dates = tuple(_date(at) for at in anchor_dates)
        _require(dates == tuple(sorted(set(dates))) and all(at <= "2026-08-31" for at in dates),
                 "anchor_dates_order_or_protected_period_refused")
        # Read compact index directly, not millions of URL dictionaries.
        previous = None
        for symbol, at, page, row in matrices._QUERY.iter_unpack(matrix.parts()[1]):
            if symbol != previous:
                source_tickers.append({"ticker": header["symbols"][symbol],
                    "source_origin": {"page_ordinal": page, "row_index": row,
                                      "source_file_sha256": header["page_origins"][page - 1]["raw_sha256"]}})
            previous = symbol
        count = len(source_tickers) * len(dates)
        anchor_dates = dates
    payload = {"schema": SCHEMA + "-query-plan", "mode": mode,
               "source_matrix_sha256": matrix.sha256, "format_policy_sha256": hash_payload(reference_policy()),
               "query_count": count, "anchor_dates": None if anchor_dates is None else list(anchor_dates),
               "selected_query_ordinals": None if selected_query_ordinals is None else list(selected_query_ordinals),
               "source_tickers": source_tickers, "authority": _authority()}
    encoded = canonical_json(payload)
    obj = object.__new__(NativeClassQueryPlan)
    digest = hash_bytes(encoded.encode())
    anchor = (matrix, encoded, digest)
    for name, value in (("_matrix", matrix), ("_json", encoded), ("_digest", digest),
                         ("_anchor", anchor), ("_anchor_identity", anchor)):
        object.__setattr__(obj, name, value)
    return obj


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class NativeDatedClassQuery:
    _plan: NativeClassQueryPlan = dataclasses.field(repr=False)
    _json: str = dataclasses.field(repr=False)
    _anchor: tuple = dataclasses.field(repr=False)
    _anchor_identity: tuple = dataclasses.field(repr=False)

    def __init__(self):
        raise NativeDatedClassError("REFUSED: query_requires_source_factory")

    def to_payload(self):
        _require(type(self) is NativeDatedClassQuery and self._anchor is self._anchor_identity
                 and self._plan is self._anchor[0] and self._json is self._anchor[1], "sealed_source_query_changed")
        self._plan._guard()
        return json.loads(self._json)


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class CapturedNativeDatedClassResponse:
    _query: NativeDatedClassQuery = dataclasses.field(repr=False)
    _raw: bytes = dataclasses.field(repr=False)
    _meta: str = dataclasses.field(repr=False)
    _anchor: tuple = dataclasses.field(repr=False)
    _anchor_identity: tuple = dataclasses.field(repr=False)

    def __init__(self):
        raise NativeDatedClassError("REFUSED: response_requires_source_factory")

    def _guard(self):
        _require(type(self) is CapturedNativeDatedClassResponse and self._anchor is self._anchor_identity
                 and self._query is self._anchor[0] and self._raw is self._anchor[1]
                 and self._meta is self._anchor[2], "sealed_class_response_changed")
        self._query.to_payload()


def capture_native_dated_class_response(query, *, raw, raw_sha256, request_sha256, received_at,
                                        http_status, content_type, body_observed):
    _require(type(query) is NativeDatedClassQuery, "exact_source_query_required")
    ticket = query.to_payload()
    _require(type(raw) is bytes and len(raw) <= lexical.MAXIMUM_RESPONSE_BYTES
             and type(raw_sha256) is str and raw_sha256 == hash_bytes(raw)
             and type(request_sha256) is str and request_sha256 == ticket["request_sha256"], "bound_response_bytes_or_request_changed")
    _require(type(http_status) is int and 100 <= http_status <= 599 and type(body_observed) is bool
             and (body_observed or (not raw and http_status != 200)), "response_status_or_observation_refused")
    _require(type(content_type) is str and len(content_type) <= 4096
             and all(32 <= ord(char) <= 126 for char in content_type), "response_media_refused")
    try:
        parse_utc_timestamp(received_at, "received_at")
    except (TypeError, ValueError):
        raise NativeDatedClassError("REFUSED: response_clock_refused") from None
    meta = canonical_json({"query_ordinal": ticket["query_ordinal"], "request_sha256": request_sha256,
             "raw_sha256": raw_sha256, "received_at": received_at, "http_status": http_status,
             "content_type": content_type, "body_observed": body_observed})
    obj = object.__new__(CapturedNativeDatedClassResponse)
    anchor = (query, raw, meta)
    for name, value in (("_query", query), ("_raw", raw), ("_meta", meta),
                       ("_anchor", anchor), ("_anchor_identity", anchor)):
        object.__setattr__(obj, name, value)
    return obj


class _Object(tuple):
    """Keep duplicate JSON fields for negative identifier evidence only."""


def _parse(raw):
    def nonfinite(_):
        raise NativeDatedClassError("REFUSED: nonfinite_response_JSON")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_Object,
                          parse_int=lexical._NumberToken, parse_float=lexical._NumberToken,
                          parse_constant=nonfinite)
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise NativeDatedClassError("REFUSED: response_JSON_refused") from None


def _strict(value):
    if type(value) is _Object:
        result = {}
        for key, item in value:
            _require(key not in result, "duplicate_response_JSON_key")
            result[key] = _strict(item)
        return result
    if type(value) is list:
        return [_strict(item) for item in value]
    return value


def _identifiers(parsed):
    composites, classes = set(), set()
    if type(parsed) is _Object:
        for key, value in parsed:
            candidates = value if type(value) is list else [value]
            if key == "results":
                for row in candidates:
                    if type(row) is _Object:
                        for name, item in row:
                            token = _figi(item, refusal_only=True)
                            if token is not None and name in {"composite_figi", "share_class_figi"}:
                                (composites if name == "composite_figi" else classes).add(token)
    return sorted(composites), sorted(classes)


def _response(capture):
    capture._guard()
    ticket, meta = capture._query.to_payload(), json.loads(capture._meta)
    result = {"query_ordinal": ticket["query_ordinal"], "ticker": ticket["ticker"],
              "query_asof_date": ticket["query_asof_date"], "actual_observation_at": meta["received_at"],
              "origin": meta, "source_composites": [], "source_classes": [],
              "normalized": None, "reason": None}
    parsed = None
    if meta["body_observed"] and capture._raw:
        try:
            parsed = _parse(capture._raw)
            result["source_composites"], result["source_classes"] = _identifiers(parsed)
        except NativeDatedClassError as error:
            result["reason"] = str(error).removeprefix("REFUSED: ")
    if meta["http_status"] != 200:
        result["reason"] = "HTTP_missing_or_refused"
        return result
    try:
        _require(meta["body_observed"] and capture._raw and parsed is not None, "response_body_missing_or_refused")
        _require(meta["content_type"].split(";", 1)[0].strip().lower() == "application/json", "response_not_JSON_media")
        envelope = _strict(parsed)
        _require(type(envelope) is dict and type(envelope.get("status")) is str and envelope["status"] == "OK"
                 and envelope.get("next_url") is None, "response_envelope_or_paging_refused")
        _require(not set(envelope) - {"status", "results", "count", "request_id", "next_url"}, "unknown_response_envelope_field")
        if "count" in envelope:
            _require(lexical._small_integer(envelope["count"]) == 1, "single_result_count_required")
        row = envelope.get("results")
        _require(type(row) is dict and type(row.get("ticker")) is str and row["ticker"] == ticket["ticker"],
                 "exact_dated_ticker_result_required")
        composite, class_figi = _figi(row.get("composite_figi")), _figi(row.get("share_class_figi"))
        _require(composite is not None and class_figi is not None and composite != class_figi, "separate_composite_and_class_required")
        count = lexical._shares(row.get("share_class_shares_outstanding"))
        _require(all(type(row.get(name)) is str for name in ("type", "locale", "market")), "dated_source_classification_missing")
        _require((row["type"], row["locale"], row["market"]) == ("CS", "us", "stocks"), "outside_dated_US_market_common_stock")
        result["normalized"] = {"composite_figi": composite, "share_class_figi": class_figi,
            "same_class_count": count, "source_classification": {key: row[key] for key in ("type", "locale", "market")},
            "primary_exchange": lexical._optional_text(row, "primary_exchange"),
            "country_domicile_assertion": None, "date_semantic": "requested_SEC_period_filter_not_filing_or_availability"}
    except (NativeDatedClassError, lexical.MassiveClassDenominatorError) as error:
        result["reason"] = str(error).removeprefix("REFUSED: ")
    return result


def _master(archive):
    _require(type(archive) is master.CapturedSharadarMasterArchive and archive.table == "tickers", "exact_original_TICKERS_archive_required")
    parsed = master._parsed(archive)
    natives, composites = defaultdict(list), defaultdict(list)
    rows = {}
    for item in parsed["rows"]:
        raw = master._raw_row(parsed, item)
        if raw["table"].strip() not in {"stocks", "SEP"}:
            continue
        ordinal = item["origin"]["row_index"]
        native, composite = _native_collision(raw.get("permaticker")), _figi(raw.get("figi"), refusal_only=True)
        if native is not None:
            natives[native].append(ordinal)
        if composite is not None:
            composites[composite].append(ordinal)
        rows[ordinal] = item
    owners = {}
    for composite, matches in composites.items():
        if len(matches) != 1:
            continue
        item = rows[matches[0]]
        normalized = item["normalized"]
        if normalized is not None and len(natives[normalized["permaticker"]]) == 1:
            owners[composite] = normalized["provider_security_id"]
    return parsed, owners


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class NativeDatedClassReference:
    _plan: NativeClassQueryPlan = dataclasses.field(repr=False)
    _archive: master.CapturedSharadarMasterArchive = dataclasses.field(repr=False)
    _header: bytes = dataclasses.field(repr=False)
    _records: tuple = dataclasses.field(repr=False)
    _digest: str
    _anchor: tuple = dataclasses.field(repr=False)
    _anchor_identity: tuple = dataclasses.field(repr=False)

    def __init__(self):
        raise NativeDatedClassError("REFUSED: reference_requires_source_factory")

    def _guard(self):
        _require(type(self) is NativeDatedClassReference and self._anchor is self._anchor_identity
                 and all(current is expected for current, expected in zip(
                    (self._plan, self._archive, self._archive.raw, self._archive.table,
                     self._archive.request_sha256, self._header, self._records, self._digest), self._anchor)),
                 "sealed_dated_reference_changed")
        self._plan._guard()

    def header(self):
        self._guard()
        return json.loads(self._header)

    @property
    def sha256(self):
        self._guard()
        return self._digest

    def iter_relations(self):
        self._guard()
        for encoded in self._records:
            self._guard()
            yield json.loads(encoded)

    def iter_parts(self):
        self._guard()
        yield self._header + b"\n"
        for encoded in self._records:
            self._guard()
            yield encoded.encode() + b"\n"


def qualify_native_dated_class_reference(plan, tickers, captures, *, retrieved_at):
    _require(type(plan) is NativeClassQueryPlan, "exact_source_query_plan_required")
    spec = plan.to_payload()
    _require(spec["format_policy_sha256"] == hash_payload(reference_policy()), "class_reference_policy_changed")
    _require(type(tickers) is master.CapturedSharadarMasterArchive and tickers.table == "tickers",
             "exact_original_TICKERS_archive_required")
    archive_snapshot = (tickers.raw, tickers.table, tickers.request_sha256)
    parsed, owners = _master(tickers)
    end = parse_utc_timestamp(retrieved_at, "retrieved_at")
    records, composite_classes, class_natives = [], defaultdict(set), defaultdict(set)
    counts, blocked_counts = defaultdict(set), set()
    previous = None
    for ordinal, capture in enumerate(captures, 1):
        _require(spec["format_policy_sha256"] == hash_payload(reference_policy()), "class_reference_policy_changed")
        _require(tickers.raw is archive_snapshot[0] and tickers.table == archive_snapshot[1]
                 and tickers.request_sha256 == archive_snapshot[2], "original_master_changed_during_qualification")
        _require(type(capture) is CapturedNativeDatedClassResponse, "exact_bound_class_capture_required")
        ticket = capture._query.to_payload()
        _require(capture._query._plan.sha256 == plan.sha256 and ticket["query_ordinal"] == ordinal
                 and ordinal <= spec["query_count"], "capture_plan_order_or_budget_changed")
        record = _response(capture)
        received = parse_utc_timestamp(record["actual_observation_at"], "received_at")
        _require(received <= end and (previous is None or previous <= received), "class_capture_chronology")
        previous = received
        records.append(record)
        for composite in record["source_composites"]:
            composite_classes[composite].update(record["source_classes"])
            if composite in owners:
                for class_figi in record["source_classes"]:
                    class_natives[class_figi].add(owners[composite])
        for class_figi in record["source_classes"]:
            if record["normalized"] is None:
                blocked_counts.add((class_figi, record["query_asof_date"]))
        normalized = record["normalized"]
        if normalized is not None:
            counts[(normalized["share_class_figi"], record["query_asof_date"])].add(normalized["same_class_count"]["numerator"])
    _require(spec["format_policy_sha256"] == hash_payload(reference_policy()), "class_reference_policy_changed")
    _require(tickers.raw is archive_snapshot[0] and tickers.table == archive_snapshot[1]
             and tickers.request_sha256 == archive_snapshot[2], "original_master_changed_during_qualification")
    encoded_records = []
    for record in records:
        normalized = record["normalized"]
        reasons = [] if record["reason"] is None else [record["reason"]]
        native = None
        if normalized is not None:
            composite, class_figi = normalized["composite_figi"], normalized["share_class_figi"]
            native = owners.get(composite)
            if native is None:
                reasons.append("native_master_owner_missing_malformed_or_ambiguous")
            if len(composite_classes[composite]) != 1:
                reasons.append("composite_to_class_conflict_across_source_dates")
            if len(class_natives[class_figi]) != 1:
                reasons.append("class_to_native_conflict_across_source_dates")
            count_key = class_figi, record["query_asof_date"]
            if count_key in blocked_counts or len(counts[count_key]) != 1:
                reasons.append("same_class_asof_count_missing_malformed_or_conflicting_peer")
        record.update(status="dated_native_class_source_candidate" if not reasons else "source_reference_refused",
                      provider_security_id=native if not reasons else None,
                      refusal_reasons=sorted(set(reasons)), historical_effective_intervals=[],
                      historical_available_date=None, authority=_authority())
        encoded_records.append(canonical_json(record))
    header = {"schema": SCHEMA, "plan_sha256": plan.sha256, "source_matrix_sha256": spec["source_matrix_sha256"],
              "format_policy_sha256": hash_payload(reference_policy()), "query_mode": spec["mode"],
              "anchor_dates": spec["anchor_dates"], "master_archive_sha256": parsed["archive_sha256"],
              "master_request_sha256": archive_snapshot[2],
              "master_CSV_sha256": parsed["CSV_sha256"], "all_master_rows_retained_in_original_archive": True,
              "expected_query_count": spec["query_count"], "captured_query_count": len(records),
              "uncaptured_query_count": spec["query_count"] - len(records),
              "complete_planned_capture_inventory": len(records) == spec["query_count"],
              "retrieved_at": retrieved_at, "source_rights_and_actual_registry_processing_separate": True,
              "historical_available_date": None, "effective_intervals": [], "authority": _authority()}
    hbytes, encoded_records = canonical_json(header).encode(), tuple(encoded_records)
    digest = hashlib.sha256(hbytes + b"\n")
    for record in encoded_records:
        digest.update(record.encode() + b"\n")
    value = object.__new__(NativeDatedClassReference)
    for name, item in (("_plan", plan), ("_archive", tickers), ("_header", hbytes),
                       ("_records", encoded_records), ("_digest", digest.hexdigest())):
        object.__setattr__(value, name, item)
    anchor = (plan, tickers, tickers.raw, tickers.table, tickers.request_sha256,
              hbytes, encoded_records, value._digest)
    object.__setattr__(value, "_anchor", anchor)
    object.__setattr__(value, "_anchor_identity", anchor)
    value._guard()
    return value
