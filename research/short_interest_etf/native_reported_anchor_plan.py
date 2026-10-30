"""Ignored compact source-only draft; no signal, outcome or provider access.

One dated identity report is decoded at a time. Original matrix ordinals and
packed cell/anchor arrays replace millions of repeated dictionaries. Source
pins retain custody; no source object, caller flag or fixture grants admission.
"""
from __future__ import annotations

from array import array
from collections import defaultdict
import csv
import dataclasses
from datetime import date
import hashlib
import io
import json
import struct

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.native_population_class_matrix as matrices
import research.short_interest_etf.native_dated_identity as identities
import research.short_interest_etf.native_dated_class_reference as references
import research.short_interest_etf.sharadar_securities_master as master
import research.short_interest_etf.native_listed_venue_namespace as venues

SCHEMA = "si-native-reported-anchor-draft-v2"
MAXIMUM_AGE_DAYS = 95
_CELL = struct.Struct("<iiI")  # selected-anchor index, class-label index, refusal flags
_ANCHOR = struct.Struct("<IIIIIII")  # original ordinal,date,class,composite,refresh flags,identity page,row
_MISSING_IDENTITY, _STALE, _UNQUALIFIED_VENUE, _INACTIVE_LISTING = 1, 2, 4, 8
_REFRESH = ("quarter_first_or_first_seen_class", "observed_native_class_transition",
            "first_valid_identity_after_gap", "source_split_refresh",
            "unresolved_source_split_refresh_fence")


class AnchorError(ValueError):
    pass


def _require(value, reason):
    if not value:
        raise AnchorError("REFUSED: " + reason)


def _authority():
    return {"source_only": True, "source_admitted": False,
            "historical_availability_known": False, "original_vintage_PIT": False,
            "actual_input_execution_admitted": False, "outcome_looks": 0,
            "qc_attempts": 0, "trading_authority": False}


def anchor_policy():
    return {"schema": SCHEMA + "-policy", "decision": "SI-DEC-20261013-23",
            "listing_namespace_policy_sha256": hash_payload(venues.venue_policy()),
            "listing_namespace": "exact_dated_source_primary_exchange_before_query_budget_no_current_venue_backdating",
            "selection": list(_REFRESH), "same_class_count": "positive_integral_particular_class_only",
            "carry_days": MAXIMUM_AGE_DAYS, "future_records_revoke_prior_cells": False,
            "split": "refresh_only_no_ratio_transfer_or_payment_or_effective_timestamp_inference",
            "queries": "original_matrix_ordinals_one_per_native_class_date_no_adaptive_retry",
            "clock": "query_asof_and_actual_receipt_separate_no_fabricated_available_date",
            "storage": {"cell_width": _CELL.size, "anchor_width": _ANCHOR.size,
                        "identity": "one_decoded_date_at_a_time_no_retained_date_maps",
                        "responses": "stream_once_raw_bodies_not_retained",
                        "diagnostics": "lazy_rows_summary_payload_only"},
            "authority": _authority()}


def reported_anchor_age_ok(anchor_date, settlement_date):
    difference = (date.fromisoformat(settlement_date) - date.fromisoformat(anchor_date)).days
    return 0 <= difference <= MAXIMUM_AGE_DAYS


def _packed_digest(header, anchors, cells, events):
    result = hashlib.sha256(b"si-native-reported-anchor-draft-v2\0")
    for part in (header, anchors, cells):
        result.update(len(part).to_bytes(8, "little"))
        result.update(part)
    for part in events:
        result.update(len(part).to_bytes(8, "little"))
        result.update(part)
    return result.hexdigest()


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class NativeReportedAnchorPlan:
    _matrix: object = dataclasses.field(repr=False)
    _query_plan: object = dataclasses.field(repr=False)
    _header: bytes = dataclasses.field(repr=False)
    _anchors: bytes = dataclasses.field(repr=False)
    _cells: bytes = dataclasses.field(repr=False)
    _events: tuple = dataclasses.field(repr=False)
    _archives: tuple = dataclasses.field(repr=False)
    _digest: str
    _anchor: tuple = dataclasses.field(repr=False)
    _identity: tuple = dataclasses.field(repr=False)

    def __init__(self):
        raise AnchorError("REFUSED: source_bound_anchor_factory_required")

    def _guard(self):
        parts = (self._matrix, self._query_plan, self._header, self._anchors,
                 self._cells, self._events, self._archives, self._digest)
        _require(type(self) is NativeReportedAnchorPlan and self._anchor is self._identity
                 and type(self._anchor) is tuple and len(self._anchor) == 8
                 and all(a is b for a, b in zip(parts, self._anchor)), "sealed_anchor_plan_changed")
        self._matrix._guard()
        self._query_plan._guard()
        for source, raw, table, request in self._archives:
            _require(source.raw is raw and source.table == table and source.request_sha256 == request,
                     "original_action_dictionary_changed")

    def header(self):
        self._guard()
        return json.loads(self._header)

    def to_payload(self):
        value = self.header()
        # Diagnostic summary deliberately omits pooled identifiers and all rows.
        return {key: value[key] for key in (
            "schema", "policy_sha256", "source_matrix_sha256", "source_matrix_refusal_count",
            "exact_request_budget", "cell_count", "class_label_count", "split_fence_count",
            "packed_cell_bytes", "packed_anchor_bytes", "authority")}

    def parts(self):
        self._guard()
        return self._header, self._anchors, self._cells

    def iter_parts(self):
        for part in (self._header, self._anchors, self._cells, *self._events):
            self._guard()
            yield part

    @property
    def sha256(self):
        self._guard()
        return self._digest

    @property
    def query_plan(self):
        self._guard()
        return self._query_plan

    def iter_anchors(self):
        header = self.header()
        source = self._matrix.header()
        for index, values in enumerate(_ANCHOR.iter_unpack(self._anchors)):
            self._guard()
            ordinal, day, label, composite, flags, page, row = values
            symbol = matrices._QUERY.unpack_from(self._matrix.parts()[1], (ordinal - 1) * matrices._QUERY.size)[0]
            yield {"anchor_index": index, "original_query_ordinal": ordinal,
                   "query_asof_date": source["settlements"][day], "ticker": source["symbols"][symbol],
                   "provider_security_id": header["class_labels"][label][0],
                   "share_class_figi": header["class_labels"][label][1],
                   "composite_figi": header["composites"][composite],
                   "identity_source_origin": {"page_ordinal": page, "row_index": row},
                   "refresh_reasons": [reason for bit, reason in enumerate(_REFRESH) if flags & (1 << bit)]}

    def iter_cells(self):
        header, source = self.header(), self._matrix.header()
        for index, values in enumerate(matrices._QUERY.iter_unpack(self._matrix.parts()[1])):
            self._guard()
            symbol, day, page, row = values
            anchor, label, flags = _CELL.unpack_from(self._cells, index * _CELL.size)
            reasons = []
            if flags & _MISSING_IDENTITY:
                reasons.append("dated_identity_missing_or_ambiguous")
            if flags & _STALE:
                reasons.append("reported_anchor_older_than_95_days")
            if flags & _UNQUALIFIED_VENUE:
                reasons.append("source_listing_venue_namespace_unqualified")
            if flags & _INACTIVE_LISTING:
                reasons.append("dated_source_inactive_or_unobserved_listing_status")
            native_class = (None, None) if label < 0 else header["class_labels"][label]
            anchor_ordinal = None if anchor < 0 else _ANCHOR.unpack_from(self._anchors, anchor * _ANCHOR.size)[0]
            yield {"original_query_ordinal": index + 1, "ticker": source["symbols"][symbol],
                   "settlement_date": source["settlements"][day],
                   "provider_security_id": native_class[0], "share_class_figi": native_class[1],
                   "anchor_index": anchor, "anchor_original_query_ordinal": anchor_ordinal,
                   "source_origin": {"page_ordinal": page, "row_index": row,
                       "source_file_sha256": source["page_origins"][page - 1]["raw_sha256"]},
                   "refusal_reasons": reasons}

    def iter_split_fences(self):
        self._guard()
        for raw in self._events:
            self._guard()
            yield json.loads(raw)


def _archive_rows(archive, table):
    _require(type(archive) is master.CapturedSharadarMasterArchive and archive.table == table,
             "exact_original_action_dictionary_archive_required")
    master.CapturedSharadarMasterArchive.__post_init__(archive)
    raw = master.validate_archive(table, archive.raw)
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8"), newline=""), strict=True)
    aliases = master._ALIASES.get(table, {})
    headers = [aliases.get(field, field) for field in reader.fieldnames or ()]
    _require(len(headers) == len(set(headers)) and master._REQUIRED[table] <= set(headers)
             and not set(headers) - master._KNOWN[table], "exact_action_dictionary_columns")
    def stream():
        for ordinal, item in enumerate(reader):
            _require(ordinal < master.MAXIMUM_ROWS[table] and None not in item and None not in item.values(),
                     "action_dictionary_row_bound_or_width")
            yield ordinal, {aliases.get(key, key): value for key, value in item.items()}
    return stream(), {"table": table, "archive_sha256": hash_bytes(archive.raw),
                      "CSV_sha256": hash_bytes(raw), "request_sha256": archive.request_sha256}


def _split_fences(actions, dictionary):
    words, dictionary_pin = _archive_rows(dictionary, "descriptions")
    entries = [row for _, row in words if row["table"].strip() == "actiontypes"
               and row["indicator"].strip() == "split"]
    semantics = len(entries) == 1 and entries[0]["table"] == "actiontypes" \
        and entries[0]["indicator"] == "split" and "split" in entries[0]["description"].casefold()
    rows, action_pin = _archive_rows(actions, "actions")
    events, groups = [], defaultdict(list)
    for ordinal, raw in rows:
        if raw["action"].strip() != "split":
            continue
        at, token = raw["date"].strip(), raw["ticker"].strip()
        try:
            _require(date.fromisoformat(at).isoformat() == at, "split_calendar_date_unrecognizable")
        except ValueError:
            raise AnchorError("REFUSED: split_calendar_date_unrecognizable") from None
        reasons = [] if semantics else ["split_dictionary_missing_or_ambiguous"]
        try:
            normalized = master._normalize("actions", raw)
            if raw["action"] != "split" or normalized["value"] is None or normalized["value"]["numerator"] <= 0:
                reasons.append("malformed_source_split")
        except master.SharadarSecuritiesMasterError:
            reasons.append("malformed_source_split")
        event = {"source_action_date": at, "source_ticker": token, "same_date_native_class": None,
                 "source_origin": {**action_pin, "row_index": ordinal},
                 "refusal_reasons": reasons, "economic_event_admitted": False}
        groups[(at, token)].append(len(events))
        events.append(event)
    for positions in groups.values():
        if len(positions) > 1:
            for index in positions:
                events[index]["refusal_reasons"].append("duplicate_split_all_peers_refused")
    return events, (action_pin, dictionary_pin)


def _report(source, previous, master_pin):
    _require(type(source) is identities.DatedIdentityQualification, "exact_dated_identity_qualification_required")
    raw = source.to_bytes()
    payload = json.loads(raw)
    at = payload["query_date"]
    _require(previous is None or previous < at, "identity_dates_sorted_unique")
    _require(payload["row_fields"] == list(identities.ROW_FIELDS)
             and payload["policy_sha256"] == hash_payload(identities.identity_policy()),
             "dated_identity_row_contract")
    pin = {"query_date": at, "source_sha256": hash_bytes(raw),
           "master_archive_sha256": payload["master_archive_sha256"],
           "master_CSV_sha256": payload["master_CSV_sha256"]}
    current_master = pin["master_archive_sha256"], pin["master_CSV_sha256"]
    _require(master_pin is None or current_master == master_pin,
             "consistent_original_master_identity_sources_required")
    rows = defaultdict(list)
    for values in payload["rows"]:
        row = dict(zip(identities.ROW_FIELDS, values))
        # Keep the sealed source bytes/origins untouched; this separate
        # structural assessment cannot fabricate continuous listing history.
        row = venues.qualify_venue_namespace(row)
        row["refusal_reasons"] = sorted(set(row["refusal_reasons"] +
            row["venue_namespace_assessment"]["refusal_reasons"]))
        if type(row["ticker"]) is str:
            rows[row["ticker"].strip()].append(row)
    return at, rows, pin, current_master


def build_native_reported_anchor_plan(matrix, identity_dates, actions, dictionary):
    _require(type(matrix) is matrices.NativePopulationClassMatrix, "exact_sealed_source_matrix_required")
    source_header, query_bytes = matrix.header(), matrix.parts()[1]
    buckets = defaultdict(lambda: array("I"))
    for ordinal, (_, day, _, _) in enumerate(matrices._QUERY.iter_unpack(query_bytes), 1):
        buckets[day].append(ordinal)
    date_indices = {at: index for index, at in enumerate(source_header["settlements"])}
    archives = tuple((item, item.raw, item.table, item.request_sha256) for item in (actions, dictionary)
                     if type(item) is master.CapturedSharadarMasterArchive)
    _require(len(archives) == 2, "exact_original_action_dictionary_archive_required")
    events, action_pins = _split_fences(actions, dictionary)
    fence_tickers, fence_dates = defaultdict(list), defaultdict(list)
    for index, event in enumerate(events):
        fence_tickers[event["source_ticker"]].append(index)
        fence_dates[event["source_action_date"]].append(index)
    class_labels, class_indices, composites, composite_indices = [], {}, [], {}
    cell_bytes = bytearray(_CELL.pack(-1, -1, _MISSING_IDENTITY) * source_header["query_count"])
    anchors, current_anchors, selected_ordinals = [], {}, []
    last_identity, had_gap, class_gaps = {}, set(), set()
    negative_fences, positive_fences = defaultdict(set), defaultdict(set)
    consumed_events, seen_quarter, quarter = set(), set(), None
    source_pins, processed_dates, previous, master_pin = [], set(), None, None
    for source in identity_dates:
        at, rows, pin, master_pin = _report(source, previous, master_pin)
        previous = at
        source_pins.append(pin)
        # Bind only exact same-source query date; no action-date alias invention.
        for event_index in fence_dates.get(at, ()):
            event = events[event_index]
            peers = rows.get(event["source_ticker"], ())
            positive = [row for row in peers if not row["refusal_reasons"]]
            if len(peers) == len(positive) == 1 and not event["refusal_reasons"]:
                event["same_date_native_class"] = [positive[0]["provider_security_id"], positive[0]["share_class_figi"]]
                positive_fences[tuple(event["same_date_native_class"])].add(event_index)
        day = date_indices.get(at)
        if day not in buckets:
            del rows, source
            continue
        processed_dates.add(day)
        this_quarter = at[:4], (date.fromisoformat(at).month - 1) // 3
        if this_quarter != quarter:
            seen_quarter.clear()
            quarter = this_quarter
        refreshes, representatives, valid_cells = defaultdict(int), {}, []
        # Fence the last known class before considering any current-date alias.
        # Original ordinal order may put a valid renamed alias before the
        # ambiguous old symbol. Clear this fence only when a fresh anchor has
        # actually been selected for that class, never by alias appearance.
        for ordinal in buckets[day]:
            symbol, _, _, _ = matrices._QUERY.unpack_from(query_bytes, (ordinal - 1) * matrices._QUERY.size)
            peers = rows.get(source_header["symbols"][symbol], ())
            if len(peers) != 1 or peers[0]["refusal_reasons"]:
                flags = _MISSING_IDENTITY
                if any(any(reason.startswith("dated_primary_") for reason in
                       row["venue_namespace_assessment"]["refusal_reasons"]) for row in peers):
                    flags |= _UNQUALIFIED_VENUE
                if any(row["active"] is not True for row in peers):
                    flags |= _INACTIVE_LISTING
                _CELL.pack_into(cell_bytes, (ordinal - 1) * _CELL.size, -1, -1, flags)
                had_gap.add(symbol)
                if symbol in last_identity:
                    class_gaps.add(last_identity[symbol])
        for ordinal in buckets[day]:
            symbol, _, _, _ = matrices._QUERY.unpack_from(query_bytes, (ordinal - 1) * matrices._QUERY.size)
            token = source_header["symbols"][symbol]
            peers = rows.get(token, ())
            good = [row for row in peers if not row["refusal_reasons"]]
            if len(peers) != 1 or len(good) != 1:
                had_gap.add(symbol)
                continue
            row = good[0]
            key = row["provider_security_id"], row["share_class_figi"]
            if key not in class_indices:
                class_indices[key] = len(class_labels)
                class_labels.append(key)
            label = class_indices[key]
            negative_fences[label].update(positive_fences.get(key, ()))
            for event_index in fence_tickers.get(token, ()):
                negative_fences[label].add(event_index)
            flags = 0
            if label not in seen_quarter:
                flags |= 1
                seen_quarter.add(label)
            if symbol in last_identity and last_identity[symbol] != label:
                flags |= 2
            if symbol in had_gap or label in class_gaps:
                flags |= 4
                had_gap.discard(symbol)
            last_identity[symbol] = label
            for event_index in negative_fences[label]:
                event = events[event_index]
                if (event_index, label) in consumed_events or event["source_action_date"] > at:
                    continue
                flags |= 8 if event["same_date_native_class"] == list(key) else 16
                consumed_events.add((event_index, label))
            refreshes[label] |= flags
            if label not in representatives:  # buckets are original ordinal order: deterministic ticker selection
                representatives[label] = ordinal, row
            valid_cells.append((ordinal, label))
        for label, flags in refreshes.items():
            if not flags:
                continue
            ordinal, row = representatives[label]
            composite = row["composite_figi"]
            if composite not in composite_indices:
                composite_indices[composite] = len(composites)
                composites.append(composite)
            index = len(anchors)
            anchors.append((ordinal, day, label, composite_indices[composite], flags,
                            row["page_ordinal"], row["row_index"]))
            current_anchors[label] = index, at
            selected_ordinals.append(ordinal)
            class_gaps.discard(label)
        for ordinal, label in valid_cells:
            index, anchor_date = current_anchors[label]
            flags = 0 if reported_anchor_age_ok(anchor_date, at) else _STALE
            _CELL.pack_into(cell_bytes, (ordinal - 1) * _CELL.size, index, label, flags)
        # Explicitly release all decoded row maps before advancing source iterator.
        del rows, refreshes, representatives, valid_cells, source
    _require(set(buckets) == processed_dates, "every_valid_query_settlement_identity_required")
    _require(bool(anchors), "no_source_qualified_anchor_candidates")
    for event in events:
        if event["same_date_native_class"] is None:
            event["refusal_reasons"].append("split_native_class_not_authenticated_on_action_date")
        event["refusal_reasons"] = sorted(set(event["refusal_reasons"]))
    # Query tickets preserve original matrix ordinals, not chronological storage indices.
    query_plan = references.freeze_native_class_query_plan(matrix, mode="explicit_anchors",
                                                          selected_query_ordinals=tuple(sorted(selected_ordinals)))
    anchor_bytes = b"".join(_ANCHOR.pack(*values) for values in anchors)
    cells, event_bytes = bytes(cell_bytes), tuple(canonical_json(event).encode() for event in events)
    header = {"schema": SCHEMA, "policy_sha256": hash_payload(anchor_policy()),
              "source_matrix_sha256": matrix.sha256, "source_matrix_refusal_count": source_header["refusal_count"],
              "identity_source_pins": source_pins, "action_source_pins": list(action_pins),
              "exact_request_budget": len(anchors), "cell_count": source_header["query_count"],
              "class_label_count": len(class_labels), "split_fence_count": len(events),
              "class_labels": class_labels, "composites": composites,
              "packed_cell_bytes": len(cells), "packed_anchor_bytes": len(anchor_bytes),
              "underlying_query_plan_sha256": query_plan.sha256, "authority": _authority()}
    raw = canonical_json(header).encode()
    for item, original_raw, original_table, original_request in archives:
        _require(item.raw is original_raw and item.table == original_table
                 and item.request_sha256 == original_request, "original_action_dictionary_changed")
    digest = _packed_digest(raw, anchor_bytes, cells, event_bytes)
    obj = object.__new__(NativeReportedAnchorPlan)
    parts = matrix, query_plan, raw, anchor_bytes, cells, event_bytes, archives, digest
    names = ("_matrix", "_query_plan", "_header", "_anchors", "_cells", "_events", "_archives", "_digest")
    for name, value in zip(names, parts):
        object.__setattr__(obj, name, value)
    object.__setattr__(obj, "_anchor", parts)
    object.__setattr__(obj, "_identity", parts)
    return obj


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class NativeReportedCountRegistry:
    _plan: object = dataclasses.field(repr=False)
    _records: tuple = dataclasses.field(repr=False)
    _flags: bytes = dataclasses.field(repr=False)
    _digest: str
    _anchor: tuple = dataclasses.field(repr=False)
    _identity: tuple = dataclasses.field(repr=False)

    def __init__(self):
        raise AnchorError("REFUSED: source_bound_count_registry_factory_required")

    def _guard(self):
        parts = self._plan, self._records, self._flags, self._digest
        _require(type(self) is NativeReportedCountRegistry and self._anchor is self._identity
                 and type(self._anchor) is tuple and len(self._anchor) == 4
                 and all(a is b for a, b in zip(parts, self._anchor)), "sealed_count_registry_changed")
        self._plan._guard()

    def to_payload(self):
        self._guard()
        return {"schema": SCHEMA + "-registry", "anchor_plan_sha256": self._plan.sha256,
                "planned_anchor_count": len(self._flags),
                "captured_anchor_count": sum(record is not None for record in self._records),
                "authority": _authority()}

    @property
    def sha256(self):
        self._guard()
        return self._digest

    def iter_records(self):
        self._guard()
        for index, raw in enumerate(self._records):
            self._guard()
            if raw is not None:
                record = json.loads(raw)
                record["anchor_index"] = index
                yield record

    def iter_cells(self):
        self._guard()
        for cell in self._plan.iter_cells():
            self._guard()
            index = cell["anchor_index"]
            raw = None if index < 0 else self._records[index]
            record = None if raw is None else json.loads(raw)
            reasons = list(cell["refusal_reasons"])
            if not reasons and (record is None or self._flags[index]):
                reasons.append("planned_anchor_count_missing_or_refused_no_old_count_fallback")
            cell.update(refusal_reasons=reasons,
                        same_class_count=None if reasons else record["same_class_count"],
                        query_asof_date=None if record is None else record["query_asof_date"],
                        actual_receipt_UTC=None if record is None else record["actual_receipt_UTC"],
                        historical_available_date=None, effective_intervals=[], authority=_authority())
            yield cell

    def iter_parts(self):
        yield canonical_json(self.to_payload()).encode()
        self._guard()
        yield self._flags
        for record in self._records:
            self._guard()
            yield b"null" if record is None else record


def qualify_native_reported_counts(plan, captures):
    _require(type(plan) is NativeReportedAnchorPlan, "exact_source_bound_anchor_plan_required")
    header, anchors = plan.header(), tuple(_ANCHOR.iter_unpack(plan._anchors))
    query_plan_payload, source_header = plan.query_plan.to_payload(), plan._matrix.header()
    # Selected anchors only, not the multi-million source cell inventory.
    index_by_ordinal = {item[0]: index for index, item in enumerate(anchors)}
    records, flags = [None] * len(anchors), bytearray([1] * len(anchors))
    classes, counts, negatives = defaultdict(set), defaultdict(set), set()
    previous_receipt, source_classes = None, []
    for ordinal, capture in enumerate(captures, 1):
        _require(ordinal <= header["exact_request_budget"], "count_capture_budget_exceeded")
        _require(type(capture) is references.CapturedNativeDatedClassResponse,
                 "exact_bound_count_response_required")
        ticket = capture._query.to_payload()
        _require(ticket["query_ordinal"] == ordinal and capture._query._plan.sha256 == plan.query_plan.sha256,
                 "count_capture_plan_or_order_changed")
        original = query_plan_payload["selected_query_ordinals"][ordinal - 1]
        index, anchor = index_by_ordinal[original], anchors[index_by_ordinal[original]]
        _, day, label, composite_index, _, _, _ = anchor
        expected_class, expected_composite = header["class_labels"][label][1], header["composites"][composite_index]
        record = references._response(capture)
        received = references.parse_utc_timestamp(record["actual_observation_at"], "received_at")
        _require(previous_receipt is None or previous_receipt <= received, "count_response_chronology_refused")
        previous_receipt = received
        at, normalized = record["query_asof_date"], record["normalized"]
        _require(at == source_header["settlements"][day], "count_asof_date_binding_changed")
        for composite in record["source_composites"]:
            classes[(composite, at)].update(record["source_classes"])
        for class_id in record["source_classes"]:
            if normalized is None:
                negatives.add((class_id, at))
        reasons = [] if record["reason"] is None else [record["reason"]]
        if normalized is not None:
            if normalized["share_class_figi"] != expected_class:
                reasons.append("count_class_does_not_match_dated_identity")
            if normalized["composite_figi"] != expected_composite:
                reasons.append("count_composite_does_not_match_dated_identity")
            counts[(normalized["share_class_figi"], at)].add(normalized["same_class_count"]["numerator"])
        normalized_ids = None if normalized is None else (normalized["composite_figi"], normalized["share_class_figi"])
        source_classes.append((index, at, normalized_ids))
        compact = {"original_query_ordinal": original, "query_asof_date": at,
                   "actual_receipt_UTC": record["actual_observation_at"],
                   "source_origin": record["origin"],
                   "same_class_count": None if normalized is None else normalized["same_class_count"],
                   "refusal_reasons": reasons}
        records[index] = canonical_json(compact).encode()
        del capture, ticket, record, normalized
    for index, at, ids in source_classes:
        record = json.loads(records[index])
        if ids is not None:
            composite, class_id = ids
            if (class_id, at) in negatives or len(counts[(class_id, at)]) != 1:
                record["refusal_reasons"].append("same_class_same_asof_count_conflict_or_malformed_peer")
            if len(classes[(composite, at)]) != 1:
                record["refusal_reasons"].append("same_date_composite_class_conflict")
        record["refusal_reasons"] = sorted(set(record["refusal_reasons"]))
        flags[index] = 1 if record["refusal_reasons"] else 0
        records[index] = canonical_json(record).encode()
    records, flags = tuple(records), bytes(flags)
    digest = hashlib.sha256((plan.sha256 + "\n").encode() + flags)
    for raw in records:
        digest.update(b"null\n" if raw is None else raw + b"\n")
    obj = object.__new__(NativeReportedCountRegistry)
    parts = plan, records, flags, digest.hexdigest()
    for name, value in zip(("_plan", "_records", "_flags", "_digest"), parts):
        object.__setattr__(obj, name, value)
    object.__setattr__(obj, "_anchor", parts)
    object.__setattr__(obj, "_identity", parts)
    return obj
