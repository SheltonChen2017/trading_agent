"""Ignored compact source-only bridge; no S1, price/outcome join or execution.

Original SI pages are replayed once against the complete compact matrix.
Current/immediate-prior same-native/class source references are paired with
small per-class date maps, never a quadratic peer scan or a legacy 32-page cap.
"""
from __future__ import annotations

from array import array
from collections import defaultdict
import dataclasses
import hashlib
import json
import struct

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf.contracts import parse_utc_timestamp
from research.short_interest_etf.nominal_publication_calendar import QualifiedNominalCalendar
import research.short_interest_etf.native_population_class_matrix as matrices
import research.short_interest_etf.native_reported_anchor_plan as anchors
import research.short_interest_etf.native_grouped_market_source as grouped
import research.short_interest_etf.native_parallel_reported_count_registry as parallel
import research.short_interest_etf.native_count_recovery_registry as recovery

SCHEMA = "si-compact-native-source-draft-v1"
_CELL = struct.Struct("<IIIIQiiIIi")
# symbol,date,page,row,quantity,class-label,anchor,registry-reason-set,pair-flags,prior-cell
_REGISTRY_REFUSED, _UNSCHEDULED, _FIRST, _MISSING, _COLLISION, _PRIOR_REFUSED, _CALENDAR_REFUSED = (1, 2, 4, 8, 16, 32, 64)
_PAIR_REASONS = ((1, "current_native_class_or_count_source_refused"),
                 (2, "observed_settlement_not_in_bound_schedule"),
                 (4, "first_bound_schedule_date_no_prior"),
                 (8, "immediate_prior_same_native_class_source_missing_or_ambiguous"),
                 (16, "duplicate_same_native_class_settlement_all_peers_quarantined"),
                 (32, "immediate_prior_native_class_or_count_source_refused"),
                 (64, "nominal_calendar_pair_refused_no_timing_default"))


class CompactSourceError(ValueError):
    pass


def _require(value, reason):
    if not value:
        raise CompactSourceError("REFUSED: " + reason)


def _authority():
    return {"source_only": True, "latest_revised_only": True, "source_admitted": False,
            "historical_identity_admitted": False, "denominator_admitted": False,
            "daily_price_identity_admitted": False, "USD_currency_admitted": False,
            "original_vintage_PIT": False, "availability_clock_admitted": False,
            "actual_input_execution_admitted": False, "outcome_access_authorized": False,
            "qc_authorized": False, "ready_for_backtesting": False, "trading_authority": False,
            "outcome_looks": 0, "allocated_alpha": 0, "qc_attempts": 0}


def policy():
    return {"schema": SCHEMA + "-policy", "source": "existing_complete_sealed_population_matrix_original_pages_and_corrected_reported_count_registry",
            "replay": "one_original_page_at_a_time_exact_page_SHA_ordinal_request_chain_matrix_row_origins",
            "quantity": "exact_nonnegative_JSON_integer_only_no_subtraction_division_or_S1",
            "pair": "bound_schedule_immediately_prior_exact_native_and_shareclass_no_leapfrog_or_class_transfer",
            "collision": "all_native_class_date_peers_retained_and_refused_no_arbitrary_winner",
            "storage": "pooled_identifiers_reasons_origins_and_fixed_width_cells_no_million_dictionary_report",
            "refusals": "original_matrix_refusal_bytes_and_every_registry_and_pair_refusal_retained",
            "calendar": "bound_nominal_calendar_only_no_authenticated_FINRA_or_availability_claim",
            "daily_bars": "separate_one_report_stream_no_daily_identity_USD_or_alias_interval_inference",
            "cell_bytes": _CELL.size, "authority": _authority()}


def _digest(header, cells):
    value = hashlib.sha256(b"si-compact-native-source-draft-v1\0")
    for part in (header, cells):
        value.update(len(part).to_bytes(8, "little"))
        value.update(part)
    return value.hexdigest()


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class CompactNativeSource:
    _matrix: object = dataclasses.field(repr=False)
    _registry: object = dataclasses.field(repr=False)
    _calendar: object = dataclasses.field(repr=False)
    _header: bytes = dataclasses.field(repr=False)
    _cells: bytes = dataclasses.field(repr=False)
    _digest: str
    _calendar_pin: tuple = dataclasses.field(repr=False)
    _anchor: tuple = dataclasses.field(repr=False)
    _identity: tuple = dataclasses.field(repr=False)

    def __init__(self):
        raise CompactSourceError("REFUSED: bound_compact_source_factory_required")

    def _guard(self):
        parts = self._matrix, self._registry, self._calendar, self._header, self._cells, self._digest, self._calendar_pin
        _require(type(self) is CompactNativeSource and self._anchor is self._identity
                 and type(self._anchor) is tuple and len(self._anchor) == len(parts)
                 and all(a is b for a, b in zip(parts, self._anchor)), "sealed_compact_source_changed")
        self._matrix._guard()
        self._registry._guard()
        _require(all(current is original for current, original in zip(
                    (self._calendar._raw, self._calendar._sha256, self._calendar._original, self._calendar._seal),
                    self._calendar_pin)), "bound_nominal_calendar_changed")

    @property
    def sha256(self):
        self._guard()
        return self._digest

    def header(self):
        self._guard()
        return json.loads(self._header)

    def to_payload(self):
        value = self.header()
        return {key: value[key] for key in ("schema", "policy_sha256", "source_matrix_sha256",
                "count_registry_sha256", "nominal_calendar_sha256", "cell_count", "source_refusal_count",
                "packed_cell_bytes", "bound_original_page_count", "authority")}

    def iter_cells(self):
        header = self.header()
        for ordinal, values in enumerate(_CELL.iter_unpack(self._cells), 1):
            self._guard()
            symbol, day, page, row, quantity, label, anchor, reasons, flags, prior = values
            native_class = (None, None) if label < 0 else header["class_labels"][label]
            record = None if anchor < 0 else self._registry._records[anchor]
            denominator = None if record is None else json.loads(record)
            source_reasons = header["registry_reason_sets"][reasons]
            prior_values = None if prior < 0 else _CELL.unpack_from(self._cells, prior * _CELL.size)
            prior_anchor = -1 if prior_values is None else prior_values[6]
            prior_record = None if prior_anchor < 0 else self._registry._records[prior_anchor]
            prior_denominator = None if prior_record is None else json.loads(prior_record)
            prior_reasons = [] if prior_values is None else header["registry_reason_sets"][prior_values[7]]
            def denominator_reference(index, value, refused):
                result = None if refused or value is None else {
                    "registry_sha256": header["count_registry_sha256"], "anchor_index": index,
                    "source_count": value["same_class_count"], "query_asof_date": value["query_asof_date"],
                    "actual_receipt_UTC": value["actual_receipt_UTC"], "source_origin": value["source_origin"]}
                if result is not None and type(self._registry) is recovery.CountRecoveryRegistry:
                    result["count_recovery_reference"] = {name: value[name] for name in (
                        "original_count_position", "source_segment", "segment_query_ordinal", "source_epoch")}
                return result
            yield {"cell_ordinal": ordinal, "ticker": header["symbols"][symbol],
                   "settlement_date": header["settlements"][day], "source_short_quantity": quantity,
                   "provider_security_id": native_class[0], "share_class_figi": native_class[1],
                   "SI_origin": {"page_ordinal": page, "row_index": row,
                                 "source_file_sha256": header["page_origins"][page - 1]["raw_sha256"]},
                   "same_class_denominator_reference": denominator_reference(anchor, denominator, source_reasons),
                   "immediate_prior_cell_ordinal": None if prior < 0 else prior + 1,
                   "immediate_prior_source_short_quantity": None if prior_values is None else prior_values[4],
                   "immediate_prior_denominator_reference": denominator_reference(prior_anchor, prior_denominator, prior_reasons),
                   "registry_refusal_reasons": source_reasons,
                   "pair_refusal_reasons": [reason for bit, reason in _PAIR_REASONS if flags & bit],
                   "authority": _authority()}

    def iter_refusals(self):
        for row in self._matrix.iter_refusals():
            self._guard()
            yield row

    def iter_private_parts(self):
        self._guard()
        yield self._header
        self._guard()
        yield self._cells
        self._guard()
        yield self._matrix.parts()[2]

    def execution_inputs(self):
        self._guard()
        raise CompactSourceError("REFUSED: source_compiler_not_execution_admission")


def _replay_quantities(matrix, pages):
    source = matrix.header()
    queries, refusals = matrix.parts()[1:]
    count, page_count = source["query_count"], len(source["page_origins"])
    # A compact dense page-row scatter map, not millions of tuple-key dicts.
    origins = array("i", [-1]) * (page_count * 50000)
    quantities = array("Q", [0]) * count
    _require(origins.itemsize == 4 and quantities.itemsize == 8, "compact_integer_platform_required")
    for index, (_, _, page, row) in enumerate(matrices._QUERY.iter_unpack(queries)):
        slot = (page - 1) * 50000 + row
        _require(origins[slot] == -1, "duplicate_matrix_origin")
        origins[slot] = index
    for index, (_, _, page, row, _, _) in enumerate(matrices._REFUSAL.iter_unpack(refusals)):
        slot = (page - 1) * 50000 + row
        _require(origins[slot] == -1, "duplicate_matrix_origin")
        origins[slot] = -2 - index
    expected_url, previous, seen, observed_rows = matrices.INITIAL_URL, None, set(), 0
    iterator = iter(pages)
    for expected in source["page_origins"]:
        matrix._guard()
        try:
            page = next(iterator)
        except StopIteration:
            raise CompactSourceError("REFUSED: original_source_page_missing") from None
        _require(type(page) is matrices.CapturedNativePopulationPage, "exact_original_sealed_page_required")
        meta = page.metadata()
        _require(all(meta[key] == expected[key] for key in ("ordinal", "segment", "request_sha256", "raw_sha256", "received_at"))
                 and meta["request"]["url"] == expected_url and expected_url not in seen,
                 "original_page_lineage_or_chain_changed")
        raw = page.raw_bytes()
        _require(hash_bytes(raw) == expected["raw_sha256"] and len(raw) == meta["raw_bytes"], "original_page_bytes_changed")
        received = parse_utc_timestamp(meta["received_at"], "received_at")
        _require(previous is None or previous <= received, "original_page_chronology")
        previous = received
        seen.add(expected_url)
        body = matrices._json(raw)
        _require(type(body) is dict and body.get("status") == "OK" and type(body.get("results")) is list
                 and len(body["results"]) <= 50000, "original_page_envelope_changed")
        if "count" in body:
            _require(type(body["count"]) is int and body["count"] == len(body["results"]), "original_page_count_changed")
        expected_url = body.get("next_url")
        if expected_url is not None:
            matrices._url(expected_url, continuation=True)
        for row_index, row in enumerate(body["results"]):
            number = origins[(meta["ordinal"] - 1) * 50000 + row_index]
            _require(number != -1, "unbound_original_source_row")
            identifiable, reason = matrices._identifiable(row), matrices._row_reason(row)
            if number >= 0:
                symbol, day, expected_page, expected_row = matrices._QUERY.unpack_from(queries, number * matrices._QUERY.size)
                _require(reason == 0 and identifiable == (source["symbols"][symbol], source["settlements"][day])
                         and (expected_page, expected_row) == (meta["ordinal"], row_index), "query_source_row_changed")
                quantities[number] = row["short_interest"]
            else:
                symbol, day, expected_page, expected_row, primary, original = matrices._REFUSAL.unpack_from(refusals, (-2 - number) * matrices._REFUSAL.size)
                expected_slot = None if symbol < 0 else (source["symbols"][symbol], source["settlements"][day])
                _require(identifiable == expected_slot and reason == original
                         and (expected_page, expected_row) == (meta["ordinal"], row_index)
                         and (primary == 7 or primary == reason), "refused_source_row_changed")
            observed_rows += 1
        del raw, body, page
    try:
        next(iterator)
    except StopIteration:
        pass
    else:
        raise CompactSourceError("REFUSED: unbound_extra_original_page")
    _require(expected_url is None and observed_rows == source["source_row_count"], "original_page_chain_or_row_inventory_incomplete")
    return quantities


def compile_native_source(matrix, registry, pages, calendar):
    _require(type(matrix) is matrices.NativePopulationClassMatrix
             and type(registry) in (anchors.NativeReportedCountRegistry, parallel.ParallelReportedCountRegistry,
                                   recovery.CountRecoveryRegistry)
             and type(calendar) is QualifiedNominalCalendar, "exact_sealed_compiler_sources_required")
    registry._guard()
    _require(registry._plan._matrix is matrix, "count_registry_matrix_lineage_changed")
    source, anchor_header, nominal = matrix.header(), registry._plan.header(), calendar.to_payload()
    quantities = _replay_quantities(matrix, pages)
    count = source["query_count"]
    calendar_rows = {row["settlement_date"]: row for row in nominal["rows"]}
    schedule = tuple(calendar_rows)
    _require(schedule == tuple(sorted(set(schedule))), "bound_schedule_order_changed")
    predecessor = {day: (None if index == 0 else schedule[index - 1]) for index, day in enumerate(schedule)}
    observed_day_indices = {at: index for index, at in enumerate(source["settlements"])}
    classes = anchor_header["class_labels"]
    labels = {tuple(value): index for index, value in enumerate(classes)}
    _require(len(labels) == len(classes), "duplicate_native_class_label")
    cells, buckets, reason_pool = bytearray(count * _CELL.size), defaultdict(lambda: array("I")), {(): 0}
    registry_cells = iter(registry.iter_cells())
    for index, (symbol, day, page, row) in enumerate(matrices._QUERY.iter_unpack(matrix.parts()[1])):
        matrix._guard()
        registry._guard()
        try:
            evidence = next(registry_cells)
        except StopIteration:
            raise CompactSourceError("REFUSED: count_registry_cell_missing") from None
        at, ticker = source["settlements"][day], source["symbols"][symbol]
        _require(evidence["original_query_ordinal"] == index + 1 and evidence["ticker"] == ticker
                 and evidence["settlement_date"] == at and evidence["source_origin"] ==
                    {"page_ordinal": page, "row_index": row, "source_file_sha256": source["page_origins"][page - 1]["raw_sha256"]},
                 "registry_cell_matrix_origin_changed")
        native_class = evidence["provider_security_id"], evidence["share_class_figi"]
        label = -1 if native_class == (None, None) else labels.get(native_class, -1)
        reasons = tuple(sorted(set(evidence["refusal_reasons"])))
        reason_index = reason_pool.setdefault(reasons, len(reason_pool))
        flags = _REGISTRY_REFUSED if reasons or label < 0 else 0
        if at not in predecessor:
            flags |= _UNSCHEDULED
        elif predecessor[at] is None:
            flags |= _FIRST
        if at in calendar_rows and calendar_rows[at]["refusal_reasons"]:
            flags |= _CALENDAR_REFUSED
        anchor = evidence["anchor_index"]
        _require(type(anchor) is int and -1 <= anchor < len(registry._records), "registry_anchor_index_changed")
        _CELL.pack_into(cells, index * _CELL.size, symbol, day, page, row, quantities[index], label, anchor, reason_index, flags, -1)
        if label >= 0:
            buckets[label].append(index)
        del evidence
    try:
        next(registry_cells)
    except StopIteration:
        pass
    else:
        raise CompactSourceError("REFUSED: unbound_extra_registry_cell")
    # Each class has at most the schedule's date keys; cells remain packed.
    for indices in buckets.values():
        slots = {}
        for index in indices:
            day = _CELL.unpack_from(cells, index * _CELL.size)[1]
            slots[day] = index if day not in slots else -1
        for index in indices:
            values = list(_CELL.unpack_from(cells, index * _CELL.size))
            day, flags = values[1], values[8]
            at = source["settlements"][day]
            if slots[day] < 0:
                flags |= _COLLISION
            prior_date = predecessor.get(at)
            if prior_date is not None:
                prior_day = observed_day_indices.get(prior_date)
                prior = -1 if prior_day is None else slots.get(prior_day, -1)
                if prior < 0:
                    flags |= _MISSING
                else:
                    values[9] = prior
                    prior_flags = _CELL.unpack_from(cells, prior * _CELL.size)[8]
                    if prior_flags & (_REGISTRY_REFUSED | _UNSCHEDULED | _CALENDAR_REFUSED):
                        flags |= _PRIOR_REFUSED
            values[8] = flags
            _CELL.pack_into(cells, index * _CELL.size, *values)
    registry._guard()
    matrix._guard()
    header = {"schema": SCHEMA, "policy_sha256": hash_payload(policy()), "source_matrix_sha256": matrix.sha256,
              "count_registry_sha256": registry.sha256, "nominal_calendar_sha256": calendar.sha256,
              "cell_count": count, "source_refusal_count": source["refusal_count"], "packed_cell_bytes": len(cells),
              "bound_original_page_count": len(source["page_origins"]), "symbols": source["symbols"],
              "settlements": source["settlements"], "bound_schedule": list(schedule), "class_labels": classes,
              "registry_reason_sets": [list(reasons) for reasons in reason_pool], "page_origins": source["page_origins"],
              "quantity_arithmetic_performed": False, "daily_bar_identity_intervals_invented": False,
              "daily_bars_joined": False, "authority": _authority()}
    if type(registry) is parallel.ParallelReportedCountRegistry:
        lineage = registry.to_payload()
        header["parallel_count_lineage"] = {key: lineage[key] for key in (
            "parallel_inventory_sha256", "parallel_plan_sha256", "parallel_started_at", "parallel_completed_at",
            "parallel_attempts_started", "parallel_halted", "parallel_unstarted_tickets",
            "complete_frozen_request_sequence", "full_provider_coverage_admitted", "receipt_clock_rule")}
        _require(header["count_registry_sha256"] == registry.sha256
                 and header["parallel_count_lineage"]["full_provider_coverage_admitted"] is False,
                 "typed_parallel_compiler_lineage_changed")
    elif type(registry) is recovery.CountRecoveryRegistry:
        lineage = registry.to_payload()
        _require(lineage["schema"] == "si-native-count-recovery-registry-v1"
                 and lineage["complete_composite_source_sequence"] is True
                 and lineage["original_round_complete"] is False
                 and lineage["full_provider_coverage_admitted"] is False,
                 "typed_recovery_compiler_lineage_changed")
        header["count_recovery_lineage"] = {key: lineage[key] for key in (
            "schema", "economic_evidence_epoch", "source_epoch", "anchor_plan_sha256",
            "parent_inventory_sha256", "child_inventory_sha256", "mapping_sha256",
            "parent_file_manifest_sha256", "child_file_manifest_sha256",
            "child_marker_sha256", "child_closure_sha256", "complete_composite_source_sequence",
            "original_round_complete", "full_provider_coverage_admitted", "cumulative_starts",
            "cumulative_http_invocations", "cumulative_charged_response_bytes")}
    raw, packed = canonical_json(header).encode(), bytes(cells)
    value = object.__new__(CompactNativeSource)
    calendar.to_bytes()  # Initial complete digest/seal verification, never per-cell rebuild.
    calendar_pin = calendar._raw, calendar._sha256, calendar._original, calendar._seal
    parts = matrix, registry, calendar, raw, packed, _digest(raw, packed), calendar_pin
    for name, item in zip(("_matrix", "_registry", "_calendar", "_header", "_cells", "_digest", "_calendar_pin"), parts):
        object.__setattr__(value, name, item)
    object.__setattr__(value, "_anchor", parts)
    object.__setattr__(value, "_identity", parts)
    return value


def iter_daily_grouped_source_reports(plan, reports):
    """Independent lazy side stream; deliberately not a native price join."""
    _require(type(plan) is grouped.GroupedSessionPlan, "exact_daily_bar_plan_required")
    iterator = iter(reports)
    for ordinal, at in enumerate(plan.sessions(), 1):
        plan._guard()
        try:
            report = next(iterator)
        except StopIteration:
            raise CompactSourceError("REFUSED: daily_grouped_report_missing") from None
        _require(type(report) is grouped.GroupedMarketQualification and report._plan is plan,
                 "exact_daily_grouped_report_lineage_required")
        payload = report.to_payload()
        _require(payload["query_session"] == at and payload["request_ordinal"] == ordinal,
                 "daily_grouped_report_order_changed")
        raw = report.to_bytes()
        del payload, report
        yield {"session": at, "ordinal": ordinal, "private_report_bytes": raw,
               "private_report_sha256": hash_bytes(raw), "native_price_binding": None,
               "USD_currency_binding": None, "authority": _authority()}
    try:
        next(iterator)
    except StopIteration:
        pass
    else:
        raise CompactSourceError("REFUSED: unbound_extra_daily_grouped_report")
