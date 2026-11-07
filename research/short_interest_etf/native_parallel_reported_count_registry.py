"""Exact typed parallel-clock extension; the original serial branch is untouched.

Parallel receipts retain their actual clocks. No boolean disables chronology,
and missing/transport/unstarted slots never turn into invented provider bodies,
HTTP 404s, counts or full-source coverage. All lineage remains source-only.
"""
from collections import defaultdict
from bisect import bisect_left
from dataclasses import dataclass, field
import hashlib
import json

from data.hashing import canonical_json, hash_payload
import research.short_interest_etf.native_dated_class_reference as references
import research.short_interest_etf.native_reported_anchor_plan as reported

# Share the producer's exact module/type, rather than loading another copy of
# the nominally same dataclass under a different import name.
import research.short_interest_etf.native_parallel_count_contract as parallel


class ParallelRegistryRefusal(ValueError):
    pass


def require(value, reason):
    if not value:
        raise ParallelRegistryRefusal(reason)


@dataclass(frozen=True, slots=True, init=False)
class ParallelReportedCountRegistry:
    _registry: object = field(repr=False)
    _inventory: object = field(repr=False)
    _digest: str
    _anchor: tuple = field(repr=False)
    _identity: tuple = field(repr=False)

    def __init__(self):
        raise ParallelRegistryRefusal("parallel_registry_factory_required")

    def guard(self):
        require(type(self) is ParallelReportedCountRegistry and self._anchor is self._identity
                and type(self._anchor) is tuple and len(self._anchor) == 3
                and all(current is saved for current, saved in zip(
                    (self._registry, self._inventory, self._digest), self._anchor)), "parallel_registry_changed")
        self._registry._guard()
        self._inventory.guard()

    def to_payload(self):
        self.guard()
        inventory = self._inventory.to_payload()
        return {**self._registry.to_payload(), "schema": "si-typed-parallel-reported-count-registry-v1",
                "parallel_inventory_sha256": self._inventory.sha256,
                "parallel_plan_sha256": self._inventory._plan.sha256,
                "parallel_started_at": inventory["started_at"], "parallel_completed_at": inventory["completed_at"],
                "parallel_attempts_started": inventory["attempts_started"], "parallel_halted": inventory["halted"],
                "parallel_unstarted_tickets": inventory["unstarted_tickets"],
                "complete_frozen_request_sequence": inventory["complete_frozen_request_sequence"],
                "full_provider_coverage_admitted": False,
                "receipt_clock_rule": "bound_each_start_le_actual_receipt_le_completion_not_query_ordinal_monotonic"}

    def _guard(self):
        self.guard()

    @property
    def _plan(self):
        self.guard()
        return self._registry._plan

    @property
    def _records(self):
        self.guard()
        return self._registry._records

    @property
    def _flags(self):
        self.guard()
        return self._registry._flags

    @property
    def sha256(self):
        self.guard()
        return self._digest

    def iter_records(self):
        self.guard()
        selected = self._registry._plan.query_plan.to_payload()["selected_query_ordinals"]
        for record in self._registry.iter_records():
            self.guard()
            # Per-request start evidence is retained, not invented from the
            # query ordinal or enclosing run boundary.
            index = bisect_left(selected, record["original_query_ordinal"])
            require(index < len(selected) and selected[index] == record["original_query_ordinal"],
                    "record_original_query_binding_changed")
            receipt = self._inventory.receipt_for_ordinal(index + 1)
            require(receipt["request_sha256"] == record["source_origin"]["request_sha256"],
                    "record_parallel_receipt_binding_changed")
            record["parallel_request_started_at"] = receipt["started_at"]
            record["parallel_inventory_sha256"] = self._inventory.sha256
            yield record

    def iter_cells(self):
        self.guard()
        for cell in self._registry.iter_cells():
            self.guard()
            cell["parallel_inventory_sha256"] = self._inventory.sha256
            yield cell

    def iter_parts(self):
        self.guard()
        yield canonical_json(self.to_payload()).encode()
        underlying = self._registry.iter_parts()
        next(underlying)  # Header replaced with exact inventory/clock lineage.
        for part in underlying:
            self.guard()
            yield part


def qualify_parallel_reported_counts(plan, captures, *, inventory):
    require(type(plan) is reported.NativeReportedAnchorPlan
            and type(inventory) is parallel.ParallelCountInventory, "exact_source_plan_and_parallel_inventory_required")
    plan._guard()
    inventory.guard()
    require(inventory._plan._queries is plan.query_plan, "exact_parallel_source_query_plan_instance_required")
    header, anchors = plan.header(), tuple(reported._ANCHOR.iter_unpack(plan._anchors))
    query_spec, source_header = plan.query_plan.to_payload(), plan._matrix.header()
    index_by_ordinal = {entry[0]: index for index, entry in enumerate(anchors)}
    receipts = tuple(inventory.iter_receipts())
    # A transport or unstarted slot has no known HTTP status and cannot become
    # a CapturedNativeDatedClassResponse; it remains an absent negative anchor.
    expected_observations = tuple(receipt["query_ordinal"] for receipt in receipts
            if type(receipt["http_status"]) is int
            and (receipt["body_observed"] is True or receipt["http_status"] != 200))
    used, previous_ordinal = [], 0
    records, flags = [None] * len(anchors), bytearray([1] * len(anchors))
    classes, counts, negatives = defaultdict(set), defaultdict(set), set()
    source_classes = []
    for capture in captures:
        require(type(capture) is references.CapturedNativeDatedClassResponse, "exact_bound_count_capture_required")
        receipt = parallel.verify_capture_receipt(inventory, capture)
        ticket = capture._query.to_payload()
        ordinal = ticket["query_ordinal"]
        require(type(ordinal) is int and previous_ordinal < ordinal <= header["exact_request_budget"]
                and capture._query._plan is plan.query_plan, "parallel_capture_order_or_plan_changed")
        previous_ordinal = ordinal
        used.append(ordinal)
        original = query_spec["selected_query_ordinals"][ordinal - 1]
        index = index_by_ordinal[original]
        _, day, label, composite_index, _, _, _ = anchors[index]
        expected_class, expected_composite = header["class_labels"][label][1], header["composites"][composite_index]
        record = references._response(capture)
        # The sealed inventory already proved this exact receipt's UTC clock
        # relative to its real START and enclosing completion (and <=8 overlap).
        require(record["actual_observation_at"] == receipt["received_at"], "actual_parallel_receipt_clock_changed")
        at, normalized = record["query_asof_date"], record["normalized"]
        require(at == source_header["settlements"][day], "count_asof_date_binding_changed")
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
        ids = None if normalized is None else (normalized["composite_figi"], normalized["share_class_figi"])
        source_classes.append((index, at, ids))
        records[index] = canonical_json({"original_query_ordinal": original, "query_asof_date": at,
                "actual_receipt_UTC": record["actual_observation_at"], "source_origin": record["origin"],
                "same_class_count": None if normalized is None else normalized["same_class_count"],
                "refusal_reasons": reasons}).encode()
        del capture, ticket, record, normalized
    require(tuple(used) == expected_observations, "every_observed_parallel_capture_once_required")
    for index, at, ids in source_classes:
        record = json.loads(records[index])
        if ids is not None:
            composite, class_id = ids
            if (class_id, at) in negatives or len(counts[(class_id, at)]) != 1:
                record["refusal_reasons"].append("same_class_same_asof_count_conflict_or_malformed_peer")
            if len(classes[(composite, at)]) != 1:
                record["refusal_reasons"].append("same_date_composite_class_conflict")
        record["refusal_reasons"] = sorted(set(record["refusal_reasons"]))
        flags[index] = int(bool(record["refusal_reasons"]))
        records[index] = canonical_json(record).encode()
    records, flags = tuple(records), bytes(flags)
    digest = hashlib.sha256((plan.sha256 + "\n").encode() + flags)
    for raw in records:
        digest.update(b"null\n" if raw is None else raw + b"\n")
    # Use the unchanged serial registry's cell semantics, not a new economic
    # representation. Only verified transport chronology differs above.
    underlying = object.__new__(reported.NativeReportedCountRegistry)
    parts = plan, records, flags, digest.hexdigest()
    for name, value in zip(("_plan", "_records", "_flags", "_digest"), parts):
        object.__setattr__(underlying, name, value)
    object.__setattr__(underlying, "_anchor", parts)
    object.__setattr__(underlying, "_identity", parts)
    result = object.__new__(ParallelReportedCountRegistry)
    wrapper = underlying, inventory, hash_payload({"count_registry_sha256": underlying.sha256,
            "parallel_inventory_sha256": inventory.sha256, "parallel_plan_sha256": inventory._plan.sha256,
            "schema": "si-typed-parallel-reported-count-registry-v1"})
    for name, value in (("_registry", wrapper[0]), ("_inventory", inventory), ("_digest", wrapper[2]),
                        ("_anchor", wrapper), ("_identity", wrapper)):
        object.__setattr__(result, name, value)
    result.guard()
    return result
