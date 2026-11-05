"""Sealed native/rational source assembly, not an outcome or execution permit.

The old FIGI/integer-volume fixture contract remains untouched. This stage
retains a declared full captured master inventory, exact source quantities and
query-date class evidence. It never computes S1, eligibility, rankings, prices
times quantities, returns or orders. No caller admission/rights booleans exist.
All row-derived representations and refused bodies must remain private.
"""
from __future__ import annotations

import base64
from collections import Counter, defaultdict
import dataclasses
from datetime import date
import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf.contracts import parse_utc_timestamp
from research.short_interest_etf.latest_revised_protocol import PROTOCOL_SHA256 as ECONOMIC_SHA256
from research.short_interest_etf.sharadar_class_reference import SharadarClassReference
from research.short_interest_etf.sharadar_native_observations import SharadarNativeObservations

SCHEMA = "si-native-latest-revised-source-assembly-v1"
MAXIMUM_PAGE_BYTES = 32 * 1024 * 1024
MAXIMUM_PAGES = 32
_URL = "https://api.massive.com/stocks/v1/short-interest"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_NATIVE = re.compile(r"sharadar:permaticker:[1-9][0-9]*\Z")


class NativeLatestRevisedSourceError(ValueError):
    """Fixed codes never disclose private records or body text."""


def _refuse(reason):
    return NativeLatestRevisedSourceError("REFUSED: " + reason)


def _authority():
    return {"source_assembly_only": True, "latest_revised_only": True,
            "point_in_time_data": False, "source_admitted": False,
            "historical_identity_admitted": False, "denominator_admitted": False,
            "actual_input_execution_admitted": False, "outcome_access_authorized": False,
            "qc_authorized": False, "production_authoritative": False,
            "trading_authority": False, "actual_outcome_looks": 0,
            "allocated_alpha": 0, "qc_attempts": 0}


def assembly_protocol():
    """A detached input-format policy; it cannot allocate an actual look."""
    return {"schema": SCHEMA + "-protocol", "economic_protocol_sha256": ECONOMIC_SHA256,
            "identity": "unchanged_provider_native_ID_separate_composite_and_class_assertions",
            "number_rule": "exact_reduced_rationals_no_volume_rounding_or_issuer_share_transfer",
            "SI_rule": "current_and_immediate_prior_scheduled_settlement_source_rows_no_S1_computation",
            "class_rule": "exact_same_query_date_relation_and_own_class_count_evidence_only",
            "population_rule": "all_captured_master_rows_including_refusals_and_delisted_no_US_completeness_claim",
            "page_rule": "fixed_origin_and_path_no_ticker_filter_complete_bound_chain_or_named_refusal",
            "collision_rule": "all_identifiable_raw_ticker_settlement_and_native_settlement_peers_quarantined",
            "temporal_rule": "no_backdated_current_metadata_or_fabricated_public_availability",
            "consumer_rule": "distinct_native_source_stage_not_LatestRevisedBundle_or_actual_runner",
            "source_requests": 0, "credential_reads": 0, "authority": _authority()}


def _date(value):
    if type(value) is not str:
        raise _refuse("canonical_settlement_date_required")
    try:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except ValueError:
        raise _refuse("canonical_settlement_date_required") from None
    return value


def _rational(value, *, positive=False):
    if (type(value) is not dict or set(value) != {"numerator", "denominator"}
            or type(value["numerator"]) is not int or type(value["denominator"]) is not int
            or value["numerator"] < 0 or value["denominator"] <= 0):
        raise _refuse("exact_nonnegative_reduced_rational_required")
    from math import gcd
    if gcd(value["numerator"], value["denominator"]) != 1 or (positive and value["numerator"] == 0):
        raise _refuse("exact_nonnegative_reduced_rational_required")
    return dict(value)


def _inputs(native, classes):
    if type(native) is not SharadarNativeObservations or type(classes) is not SharadarClassReference:
        raise _refuse("exact_sealed_native_and_class_sources_required")
    original = native.to_payload()
    master = native.native_index.to_payload()
    references = classes.to_payload()
    if master["master_archive_sha256"] != references["master_archive_sha256"]:
        raise _refuse("native_and_class_master_archive_mismatch")
    return original, master, references


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class NativeAssemblyPlan:
    _json: str = dataclasses.field(repr=False)
    _digest: str
    _anchor: tuple = dataclasses.field(repr=False)

    def __init__(self):
        raise _refuse("assembly_plan_requires_anchored_factory")

    def to_payload(self):
        if (type(self) is not NativeAssemblyPlan or type(self._anchor) is not tuple
                or self._anchor != (self._json, self._digest)
                or hash_bytes(self._json.encode()) != self._digest):
            raise _refuse("sealed_assembly_plan_changed")
        return json.loads(self._json)

    @property
    def sha256(self):
        self.to_payload()
        return self._digest


def freeze_native_assembly_plan(*, settlement_dates, native_observations, class_reference, requested_range=None):
    original, master, references = _inputs(native_observations, class_reference)
    if type(settlement_dates) is not tuple or (requested_range is None and len(settlement_dates) < 2):
        raise _refuse("ordered_current_and_prior_schedule_required")
    dates = tuple(_date(value) for value in settlement_dates)
    if dates != tuple(sorted(set(dates))):
        raise _refuse("unique_increasing_settlement_schedule_required")
    if requested_range is None:
        requested_range = (dates[0], dates[-1])
    if type(requested_range) is not tuple or len(requested_range) != 2:
        raise _refuse("exact_requested_settlement_range_required")
    start, end = (_date(value) for value in requested_range)
    if start > end or any(not start <= at <= end for at in dates):
        raise _refuse("schedule_outside_frozen_request_range")
    payload = {"schema": SCHEMA + "-plan", "format_policy_sha256": hash_payload(assembly_protocol()),
               "economic_protocol_sha256": ECONOMIC_SHA256, "settlement_dates": list(dates),
               "calendar_semantic": "prospective_supplied_schedule_not_authenticated_publication_clock",
               "requested_settlement_range": [start, end],
               "maximum_pages": MAXIMUM_PAGES, "maximum_page_bytes": MAXIMUM_PAGE_BYTES,
               "native_observations_sha256": original["binding_sha256"],
               "native_index_sha256": master["index_sha256"],
               "master_archive_sha256": master["master_archive_sha256"],
               "class_reference_sha256": references["report_sha256"],
               "short_interest_request": {"method": "GET", "url": _URL,
                    "params": {"settlement_date.gte": start, "settlement_date.lte": end,
                               "limit": 50000, "sort": "settlement_date.asc,ticker.asc"}},
               "authority": _authority()}
    encoded = canonical_json(payload)
    obj = object.__new__(NativeAssemblyPlan)
    for key, value in (("_json", encoded), ("_digest", hash_bytes(encoded.encode())),
                       ("_anchor", (encoded, hash_bytes(encoded.encode())))):
        object.__setattr__(obj, key, value)
    obj.to_payload()
    return obj


def native_si_request(plan):
    if type(plan) is not NativeAssemblyPlan:
        raise _refuse("exact_assembly_plan_required")
    descriptor = plan.to_payload()["short_interest_request"]
    # Match the transport receipt descriptor without replacing its digest.
    params = descriptor["params"]
    query = [(key, params[key]) for key in ("settlement_date.gte", "settlement_date.lte", "limit", "sort")]
    return {"method": "GET", "url": descriptor["url"] + "?" + urlencode(query),
            "authentication": "Bearer_header_not_recorded"}


def _safe_url(value):
    if type(value) is not str or len(value) > 16384:
        raise _refuse("fixed_public_SI_route_required")
    try:
        parsed = urlsplit(value)
    except ValueError:
        raise _refuse("fixed_public_SI_route_required") from None
    if (parsed.scheme != "https" or parsed.netloc != "api.massive.com"
            or parsed.path != "/stocks/v1/short-interest" or parsed.fragment
            or parsed.username is not None or parsed.password is not None):
        raise _refuse("fixed_public_SI_route_required")
    try:
        query = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        raise _refuse("malformed_SI_query") from None
    if (len({key for key, _ in query}) != len(query)
            or any(key not in {"cursor", "limit", "sort", "settlement_date.gte", "settlement_date.lte"}
                   or not val for key, val in query)):
        raise _refuse("SI_secret_or_population_filter_forbidden")
    cursors = [val for key, val in query if key == "cursor"]
    if cursors and (len(cursors[0]) > 8192 or any(not 33 <= ord(char) <= 126 for char in cursors[0])):
        raise _refuse("bounded_ASCII_SI_cursor_required")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class CapturedNativeShortInterestPage:
    request_url: str = dataclasses.field(repr=False)
    request_sha256: str
    raw: bytes = dataclasses.field(repr=False)
    source_file_sha256: str
    received_at: str
    http_status: int

    def __post_init__(self):
        if type(self) is not CapturedNativeShortInterestPage:
            raise _refuse("exact_SI_capture_required")
        _safe_url(self.request_url)
        if (type(self.raw) is not bytes or len(self.raw) > MAXIMUM_PAGE_BYTES
                or self.request_sha256 != hash_payload({"method": "GET", "url": self.request_url,
                                                       "authentication": "Bearer_header_not_recorded"})
                or type(self.source_file_sha256) is not str or not _SHA.fullmatch(self.source_file_sha256)
                or self.source_file_sha256 != hash_bytes(self.raw)
                or type(self.http_status) is not int or not 100 <= self.http_status <= 599):
            raise _refuse("SI_capture_bytes_or_request_changed")
        try:
            parse_utc_timestamp(self.received_at, "received_at")
        except (TypeError, ValueError):
            raise _refuse("canonical_SI_capture_clock_required") from None


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise _refuse("duplicate_JSON_key")
        result[key] = value
    return result


def _json(raw):
    def nonfinite(_):
        raise _refuse("nonfinite_JSON_number")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_float=str, parse_constant=nonfinite)
    except (UnicodeError, json.JSONDecodeError):
        raise _refuse("unusable_SI_JSON") from None


def _slot(row):
    if type(row) is dict and type(row.get("ticker")) is str and row["ticker"].strip():
        try:
            return row["ticker"].strip(), _date(row.get("settlement_date"))
        except NativeLatestRevisedSourceError:
            pass
    return None


def _SI(pages, plan):
    rows, receipts, reasons = [], [], []
    expected_url = native_si_request(plan)["url"]
    frozen = plan.to_payload()
    start, end = frozen["requested_settlement_range"]
    if len(pages) > frozen["maximum_pages"]:
        raise _refuse("frozen_SI_page_budget_exceeded")
    last_clock = None
    seen_urls = set()
    for page_index, page in enumerate(pages):
        CapturedNativeShortInterestPage.__post_init__(page)
        clock = parse_utc_timestamp(page.received_at, "received_at")
        if (page.request_url != expected_url or page.request_url in seen_urls
                or (last_clock is not None and clock < last_clock)):
            raise _refuse("SI_page_chain_or_chronology_mismatch")
        seen_urls.add(page.request_url)
        last_clock = clock
        receipt = {"page_index": page_index, "request_sha256": page.request_sha256,
                   "source_file_sha256": page.source_file_sha256, "received_at": page.received_at,
                   "http_status": page.http_status, "raw_body_base64": base64.b64encode(page.raw).decode(),
                   "status": "captured", "refusal_reason": None}
        receipts.append(receipt)
        try:
            value = _json(page.raw)
            if (page.http_status != 200 or type(value) is not dict or value.get("status") != "OK"
                    or type(value.get("results")) is not list
                    or ("count" in value and (type(value["count"]) is not int or value["count"] != len(value["results"])))):
                raise _refuse("unsuccessful_or_malformed_SI_envelope")
            next_url = value.get("next_url")
            if next_url is not None:
                _safe_url(next_url)
                next_params = dict(parse_qsl(urlsplit(next_url).query))
                if "cursor" not in next_params:
                    raise _refuse("next_page_requires_bound_cursor")
                for key, expected in frozen["short_interest_request"]["params"].items():
                    if key in next_params and next_params[key] != str(expected):
                        raise _refuse("next_page_changed_frozen_population_or_sort")
            expected_url = next_url
            for row_index, raw in enumerate(value["results"]):
                row = {"origin": {"page_index": page_index, "row_index": row_index,
                                   "source_file_sha256": page.source_file_sha256,
                                   "raw_record_sha256": hash_payload(raw)},
                       "raw_record": raw, "normalized": None, "refusal_reasons": []}
                rows.append(row)
                try:
                    if type(raw) is not dict or any(key in raw for key in ("short_volume", "short_sale_volume", "trade_date")):
                        raise _refuse("not_open_short_position_snapshot")
                    ticker = raw.get("ticker")
                    if type(ticker) is not str or not ticker or ticker != ticker.strip() or len(ticker) > 128:
                        raise _refuse("canonical_raw_SI_ticker_required")
                    settlement = _date(raw.get("settlement_date"))
                    if not start <= settlement <= end:
                        raise _refuse("SI_outside_frozen_request_range")
                    quantity = raw.get("short_interest")
                    if type(quantity) is not int or not 0 <= quantity <= 10**18:
                        raise _refuse("exact_integer_open_short_quantity_required")
                    row["normalized"] = {"ticker": ticker, "settlement_date": settlement,
                                         "short_interest": quantity}
                except NativeLatestRevisedSourceError as exc:
                    row["refusal_reasons"].append(str(exc).removeprefix("REFUSED: "))
        except (NativeLatestRevisedSourceError, ValueError) as exc:
            receipt.update(status="refused", refusal_reason=(str(exc).removeprefix("REFUSED: ")
                           if isinstance(exc, NativeLatestRevisedSourceError) else "malformed_next_page_route"))
            reasons.append("refused_SI_page")
            expected_url = None
            if page_index + 1 != len(pages):
                raise _refuse("cannot_continue_refused_SI_page")
    if not pages:
        reasons.append("short_interest_capture_missing")
    elif expected_url is not None:
        reasons.append("short_interest_page_chain_incomplete")
    collisions = Counter(_slot(row["raw_record"]) for row in rows if _slot(row["raw_record"]) is not None)
    for row in rows:
        if collisions.get(_slot(row["raw_record"]), 0) > 1:
            row["normalized"] = None
            row["refusal_reasons"].append("duplicate_raw_ticker_settlement_all_copies_quarantined")
    return rows, receipts, sorted(set(reasons))


def _build(plan, native, classes, pages):
    if type(plan) is not NativeAssemblyPlan or type(pages) is not tuple or any(
            type(page) is not CapturedNativeShortInterestPage for page in pages):
        raise _refuse("exact_plan_and_immutable_capture_inventory_required")
    original, master, references = _inputs(native, classes)
    frozen = plan.to_payload()
    if (frozen["format_policy_sha256"] != hash_payload(assembly_protocol())
            or frozen["economic_protocol_sha256"] != ECONOMIC_SHA256):
        raise _refuse("prospectively_frozen_format_policy_changed")
    for key, value in (("native_observations_sha256", original["binding_sha256"]),
                       ("native_index_sha256", master["index_sha256"]),
                       ("master_archive_sha256", master["master_archive_sha256"]),
                       ("class_reference_sha256", references["report_sha256"])):
        if frozen[key] != value:
            raise _refuse("prospectively_frozen_source_pin_changed")
    rows, receipts, page_refusals = _SI(pages, plan)
    dates = frozen["settlement_dates"]
    relations = defaultdict(list)
    response_by_id = {row["request_id"]: row for row in references["class_responses"]}
    for row in references["relations"]:
        response = response_by_id[row["request_id"]]
        normalized = response.get("normalized")
        if normalized is not None:
            relations[(normalized["ticker"], row["query_date"])].append(row)
    binding_rows = []
    for row in rows:
        record = {"SI_origin": row["origin"], "source_observation": row["normalized"],
                  "provider_security_id": None, "share_class_figi": None,
                  "class_relation_origin": None, "same_class_count_evidence": None,
                  "prior_settlement_date": None, "prior_source_origins": [],
                  "refusal_reasons": list(row["refusal_reasons"])}
        observation = row["normalized"]
        if observation is not None:
            candidates = relations.get((observation["ticker"], observation["settlement_date"]), [])
            if len(candidates) != 1 or candidates[0]["status"] != "query_date_source_relation_candidate":
                record["refusal_reasons"].append("same_date_raw_ticker_to_native_class_evidence_missing_or_ambiguous")
            else:
                candidate = candidates[0]
                record.update(provider_security_id=candidate["provider_security_id"],
                              share_class_figi=candidate["source_share_class_figi"],
                              class_relation_origin=candidate["response_origin"],
                              same_class_count_evidence=candidate["denominator_source_evidence"])
                if record["same_class_count_evidence"] is None:
                    record["refusal_reasons"].append("own_class_count_source_evidence_missing")
        binding_rows.append(record)
    native_slots = Counter((row["provider_security_id"], row["source_observation"]["settlement_date"])
                           for row in binding_rows if row["provider_security_id"] is not None)
    for row in binding_rows:
        current = row["source_observation"]
        if current is None:
            continue
        if current["settlement_date"] not in dates:
            row["refusal_reasons"].append("observed_settlement_calendar_relation_not_qualified")
            continue
        index = dates.index(current["settlement_date"])
        if index == 0:
            row["refusal_reasons"].append("first_schedule_row_no_prior_settlement")
        else:
            row["prior_settlement_date"] = dates[index - 1]
        native = row["provider_security_id"]
        if native is not None and native_slots[(native, current["settlement_date"])] != 1:
            row["refusal_reasons"].append("duplicate_native_settlement_all_copies_quarantined")
    # Pair source origins only. No subtraction/division or price join occurs.
    for row in binding_rows:
        native, prior = row["provider_security_id"], row["prior_settlement_date"]
        if native is not None and prior is not None:
            peers = [old for old in binding_rows if old["provider_security_id"] == native
                     and old["source_observation"] is not None
                     and old["source_observation"]["settlement_date"] == prior
                     and "duplicate_native_settlement_all_copies_quarantined" not in old["refusal_reasons"]]
            row["prior_source_origins"] = [old["SI_origin"] for old in peers]
            if len(peers) != 1 or peers[0]["same_class_count_evidence"] is None:
                row["refusal_reasons"].append("immediate_prior_same_native_class_count_evidence_missing_or_ambiguous")
        row["refusal_reasons"] = sorted(set(row["refusal_reasons"]))
        row["status"] = "source_binding_refused" if row["refusal_reasons"] else "source_binding_candidate"
    bars = []
    for observation in original["observations"]:
        if observation["table"] != "stocks":
            continue
        raw = observation["source_observation"]["normalized"]
        if observation["provider_dataset_key_bound"]:
            identifier = observation["provider_security_id"]
            if type(identifier) is not str or not _NATIVE.fullmatch(identifier):
                raise _refuse("canonical_native_identity_required")
            bars.append({"provider_security_id": identifier, "session": raw["session"],
                         **{key: _rational(raw[key], positive=key != "raw_volume")
                            for key in ("raw_open", "raw_high", "raw_low", "raw_close", "raw_volume")},
                         "origin": {key: observation["source_observation"][key]
                                    for key in ("row_index", "raw_record_sha256", "source_file_sha256")}})
    payload = {"schema": SCHEMA, "plan_sha256": plan.sha256,
               "economic_protocol_sha256": ECONOMIC_SHA256, "format_policy_sha256": hash_payload(assembly_protocol()),
               "publication_scope": "private_only_no_provider_fitness_or_rows_publication",
               "source_pins": {key: frozen[key] for key in ("native_observations_sha256", "native_index_sha256",
                              "master_archive_sha256", "class_reference_sha256")},
               "settlement_dates": dates, "native_master_rows": master["rows"],
               "requested_settlement_range": frozen["requested_settlement_range"],
               "observed_settlement_dates": sorted({row["normalized"]["settlement_date"]
                                                     for row in rows if row["normalized"] is not None}),
               "all_captured_master_rows_retained": True,
               "population_scope": "full_captured_provider_master_inventory_not_full_US_market_or_study_coverage",
               "SI_pages": receipts, "SI_rows": rows, "native_SI_source_bindings": binding_rows,
               "native_rational_bar_candidates": bars, "original_native_observations": original["observations"],
               "original_native_source_tables": original["source_tables"],
               "all_class_source_relations": references["relations"],
               "pre_entry_source_refusals": [row for row in binding_rows if row["refusal_reasons"]],
               "coverage": {"SI_page_chain_complete": not page_refusals, "page_refusals": page_refusals,
                    "SI_missing_scheduled_settlements": [at for at in dates if not any(
                        row["normalized"] is not None and row["normalized"]["settlement_date"] == at for row in rows)],
                    "native_observation_population_scope": original["population_scope"],
                    "reference_gaps": references["public_known_gaps"],
                    "calendar_qualification_pending": True,
                    "eligibility_history_not_checked_at_source_assembly": True},
               "execution_refusal_reasons": ["source_assembly_not_qualified_actual_bundle",
                    "calendar_reference_cashflow_and_full_study_coverage_not_qualified",
                    "actual_look_registry_and_processing_representation_not_bound"],
               "signals_computed": False, "price_signal_or_outcome_join_performed": False,
               "authority": _authority()}
    payload["assembly_sha256"] = hash_payload(payload)
    return canonical_json(payload).encode(), payload["assembly_sha256"]


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class NativeLatestRevisedSource:
    _plan: NativeAssemblyPlan = dataclasses.field(repr=False)
    _native: SharadarNativeObservations = dataclasses.field(repr=False)
    _classes: SharadarClassReference = dataclasses.field(repr=False)
    _pages: tuple = dataclasses.field(repr=False)
    _bytes: bytes = dataclasses.field(repr=False)
    _digest: str
    _anchor: tuple = dataclasses.field(repr=False)

    def __init__(self):
        raise _refuse("native_source_requires_anchored_factory")

    def to_bytes(self):
        if type(self) is not NativeLatestRevisedSource:
            raise _refuse("exact_native_source_required")
        try:
            anchor = self._anchor
            if (type(anchor) is not tuple or len(anchor) != 6
                    or any(current is not expected for current, expected in zip(
                        (self._plan, self._native, self._classes, self._pages, self._bytes, self._digest), anchor))):
                raise _refuse("sealed_native_source_changed")
            expected, digest = _build(self._plan, self._native, self._classes, self._pages)
            if self._bytes != expected or self._digest != digest:
                raise _refuse("sealed_native_source_changed")
        except AttributeError:
            raise _refuse("uninitialized_native_source") from None
        return self._bytes

    def to_payload(self):
        return json.loads(self.to_bytes())

    @property
    def sha256(self):
        self.to_bytes()
        return self._digest

    def execution_inputs(self):
        self.to_bytes()
        raise _refuse("source_assembly_not_actual_execution_admission")


def assemble_native_latest_revised_source(plan, native_observations, class_reference, pages):
    raw, digest = _build(plan, native_observations, class_reference, pages)
    value = object.__new__(NativeLatestRevisedSource)
    fields = (plan, native_observations, class_reference, pages, raw, digest)
    for key, item in zip(("_plan", "_native", "_classes", "_pages", "_bytes", "_digest"), fields):
        object.__setattr__(value, key, item)
    object.__setattr__(value, "_anchor", fields)
    value.to_bytes()
    return value
