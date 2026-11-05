"""Prospective parallel receipt contract, not source or execution admission."""
from __future__ import annotations

import dataclasses
import hashlib
import json

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf.contracts import parse_utc_timestamp
from research.short_interest_etf.native_dated_class_reference import NativeClassQueryPlan
from research.short_interest_etf.massive_class_denominator import MAXIMUM_RESPONSE_BYTES

MAXIMUM_INFLIGHT = 8


class ParallelCountRefusal(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise ParallelCountRefusal("REFUSED: " + code)


def clock(value):
    try:
        return parse_utc_timestamp(value, "parallel_receipt_clock")
    except (ValueError, TypeError):
        raise ParallelCountRefusal("REFUSED: UTC_receipt_clock_required") from None


def authority():
    return {"source_only": True, "source_admitted": False, "denominator_admitted": False,
            "availability_clock_admitted": False, "actual_input_execution_admitted": False,
            "outcome_access_authorized": False, "qc_authorized": False,
            "outcome_looks": 0, "qc_attempts": 0, "trading_authority": False}


def policy():
    return {"schema": "si-parallel-count-draft-policy-v1", "maximum_inflight": MAXIMUM_INFLIGHT,
            "maximum_response_bytes": MAXIMUM_RESPONSE_BYTES, "automatic_retries": 0,
            "tickets": "exact_source_selected_explicit_anchor_plan_only",
            "reservation": "whole_page_before_START_attempt_ceiling_before_every_debit",
            "fatal": "halt_scheduling_on_403_429_other_material_HTTP_transport_or_guard_failure_drain_started",
            "404": "status_only_body_unobserved_no_empty_provider_body_assertion_no_old_count_fallback",
            "receipt_clock": "each_start_le_receipt_le_enclosing_completion_not_monotone_by_query_ordinal",
            "replay": "planned_query_ordinal_order_preserving_actual_receipt_clocks",
            "replay_reservations": "whole_page_at_each_START_release_unused_only_at_bound_receipt_charge_unknown_material_body_full",
            "claim": "one_exclusive_plan_source_policy_claim_no_restart_or_spent_budget_reset",
            "publication": "protected_exclusive_private_receipts_fixed_diagnostics_no_secret_URL_or_body_echo",
            "authority": authority()}


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class ParallelCountPlan:
    _queries: NativeClassQueryPlan = dataclasses.field(repr=False)
    _json: str = dataclasses.field(repr=False)
    _anchor: tuple = dataclasses.field(repr=False)
    _identity: tuple = dataclasses.field(repr=False)

    def __init__(self):
        raise ParallelCountRefusal("REFUSED: parallel_source_plan_factory_required")

    def guard(self):
        require(type(self) is ParallelCountPlan and self._anchor is self._identity
                and self._queries is self._anchor[0] and self._json is self._anchor[1], "parallel_plan_changed")
        self._queries._guard()

    def to_payload(self):
        self.guard()
        return json.loads(self._json)

    @property
    def sha256(self):
        self.guard()
        return hash_bytes(self._json.encode())


def freeze_parallel_count_plan(queries, *, maximum_total_response_bytes):
    require(type(queries) is NativeClassQueryPlan, "exact_sealed_source_query_plan_required")
    source = queries.to_payload()
    require(source["mode"] == "explicit_anchors" and source["selected_query_ordinals"] is not None,
            "only_explicit_source_selected_tickets_allowed")
    count = source["query_count"]
    require(type(maximum_total_response_bytes) is int
            and MAXIMUM_RESPONSE_BYTES <= maximum_total_response_bytes <= count * MAXIMUM_RESPONSE_BYTES,
            "prospective_finite_cumulative_body_budget_required")
    payload = {"schema": "si-parallel-count-draft-plan-v1", "source_query_plan_sha256": queries.sha256,
               "source_matrix_sha256": source["source_matrix_sha256"], "policy_sha256": hash_payload(policy()),
               "maximum_attempts": count, "maximum_inflight": MAXIMUM_INFLIGHT,
               "maximum_response_bytes": MAXIMUM_RESPONSE_BYTES,
               "maximum_total_response_bytes": maximum_total_response_bytes, "authority": authority()}
    value = object.__new__(ParallelCountPlan)
    parts = queries, canonical_json(payload)
    for name, item in (("_queries", parts[0]), ("_json", parts[1]), ("_anchor", parts), ("_identity", parts)):
        object.__setattr__(value, name, item)
    return value


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class ParallelCountInventory:
    _plan: ParallelCountPlan = dataclasses.field(repr=False)
    _json: str = dataclasses.field(repr=False)
    _receipts: tuple = dataclasses.field(repr=False)
    _digest: str
    _anchor: tuple = dataclasses.field(repr=False)
    _identity: tuple = dataclasses.field(repr=False)

    def __init__(self):
        raise ParallelCountRefusal("REFUSED: parallel_receipt_inventory_factory_required")

    def guard(self):
        require(type(self) is ParallelCountInventory and self._anchor is self._identity
                and type(self._anchor) is tuple and len(self._anchor) == 4
                and all(current is saved for current, saved in zip((self._plan, self._json, self._receipts, self._digest), self._anchor)),
                "parallel_inventory_changed")
        self._plan.guard()

    def to_payload(self):
        self.guard()
        return json.loads(self._json)

    @property
    def sha256(self):
        self.guard()
        return self._digest

    def iter_receipts(self):
        for raw in self._receipts:
            self.guard()
            yield json.loads(raw)

    def receipt_for_ordinal(self, ordinal):
        self.guard()
        require(type(ordinal) is int and 1 <= ordinal <= len(self._receipts), "bound_attempt_ordinal_required")
        return json.loads(self._receipts[ordinal - 1])

    def iter_private_parts(self):
        self.guard()
        yield self._json.encode()
        for receipt in self._receipts:
            self.guard()
            yield receipt.encode()


def seal_parallel_inventory(plan, receipts, *, started_at, completed_at, halted):
    require(type(plan) is ParallelCountPlan and type(receipts) is tuple and type(halted) is bool,
            "exact_parallel_plan_and_immutable_receipts_required")
    budget = plan.to_payload()
    start, end = clock(started_at), clock(completed_at)
    require(start <= end and len(receipts) <= budget["maximum_attempts"], "enclosing_parallel_time_or_budget")
    indexed, events, actual_bytes, charged_bytes, http_invocations = {}, [], 0, 0, 0
    for receipt in receipts:
        require(type(receipt) is dict and set(receipt) == {"query_ordinal", "request_sha256", "started_at", "received_at",
                "http_attempted", "http_status", "body_observed", "raw_path", "raw_sha256", "raw_bytes", "content_type", "code"},
                "exact_parallel_receipt_fields_required")
        ordinal = receipt["query_ordinal"]
        require(type(ordinal) is int and 1 <= ordinal <= budget["maximum_attempts"] and ordinal not in indexed,
                "duplicate_or_unplanned_attempt_receipt")
        began, received = clock(receipt["started_at"]), clock(receipt["received_at"])
        require(start <= began <= received <= end, "parallel_per_attempt_chronology")
        require(type(receipt["http_attempted"]) is bool and type(receipt["body_observed"]) is bool,
                "exact_observation_flags_required")
        status = receipt["http_status"]
        require(status is None or (type(status) is int and 100 <= status <= 599), "exact_HTTP_status_required")
        require(status is None or receipt["http_attempted"] is True, "HTTP_status_without_invocation")
        if receipt["body_observed"]:
            require(status == 200 and receipt["http_attempted"] is True
                    and type(receipt["raw_bytes"]) is int and 0 <= receipt["raw_bytes"] <= MAXIMUM_RESPONSE_BYTES
                    and receipt["raw_path"] == f"query-{ordinal:08d}.raw"
                    and type(receipt["raw_sha256"]) is str and len(receipt["raw_sha256"]) == 64
                    and all(c in "0123456789abcdef" for c in receipt["raw_sha256"])
                    and type(receipt["content_type"]) is str and len(receipt["content_type"]) <= 256
                    and all(32 <= ord(c) <= 126 for c in receipt["content_type"]), "bound_successful_raw_receipt_required")
            actual_bytes += receipt["raw_bytes"]
            charged_bytes += receipt["raw_bytes"]
        else:
            require(all(receipt[field] is None for field in ("raw_path", "raw_sha256", "raw_bytes", "content_type")),
                    "unobserved_error_body_must_not_be_synthetic_provider_bytes")
        require(receipt["code"] in {"received", "HTTP_404_body_unobserved", "material_request_refused"}, "fixed_parallel_status_code_required")
        if receipt["code"] == "received":
            require(receipt["body_observed"] is True and status == 200, "successful_receipt_observation_changed")
        elif receipt["code"] == "HTTP_404_body_unobserved":
            require(receipt["body_observed"] is False and status == 404 and receipt["http_attempted"] is True,
                    "404_observation_changed")
        else:
            require(halted is True, "material_failure_cannot_claim_unhalted_completion")
            if not receipt["body_observed"]:
                charged_bytes += MAXIMUM_RESPONSE_BYTES
        http_invocations += int(receipt["http_attempted"])
        events.extend(((began, 1), (received, -1)))
        indexed[ordinal] = receipt
    require(set(indexed) == set(range(1, len(indexed) + 1)), "missing_started_attempt_receipt")
    previous_start = start
    for ordinal, query in enumerate(plan._queries.iter_queries(), 1):
        if ordinal > len(indexed):
            break
        receipt = indexed[ordinal]
        require(receipt["request_sha256"] == query.to_payload()["request_sha256"], "parallel_request_ticket_binding_changed")
        began = clock(receipt["started_at"])
        require(previous_start <= began, "planned_start_order_chronology")
        previous_start = began
    # End before start at an equal instant is a legitimate completed boundary;
    # zero-duration fabricated receipts are not evidence of actual concurrency.
    events = [event for receipt in indexed.values() if clock(receipt["started_at"]) < clock(receipt["received_at"])
              for event in ((clock(receipt["started_at"]), 1), (clock(receipt["received_at"]), -1))]
    inflight = 0
    for _, change in sorted(events):
        inflight += change
        require(0 <= inflight <= MAXIMUM_INFLIGHT, "observed_inflight_ceiling_exceeded")
    # Final small bodies alone cannot prove affordable whole-page reservations
    # at START. Rebuild necessary budget bounds using the retained real clocks.
    # A zero-duration receipt is an atomic observation within clock resolution,
    # not proof of overlapping invocations. Equal-time completed requests close
    # before new starts; no actual receipt clock or query order is rewritten.
    ledger = []
    for ordinal, receipt in indexed.items():
        began, received = clock(receipt["started_at"]), clock(receipt["received_at"])
        if began == received:
            ledger.append((began, 1, ordinal, "atomic"))
        else:
            ledger.extend(((began, 2, ordinal, "start"), (received, 0, ordinal, "end")))
    spent, reserved, active = 0, 0, set()
    for _, _, ordinal, kind in sorted(ledger):
        receipt = indexed[ordinal]
        charge = (receipt["raw_bytes"] if receipt["body_observed"] else
                  MAXIMUM_RESPONSE_BYTES if receipt["code"] == "material_request_refused" else 0)
        if kind in {"start", "atomic"}:
            require(spent + reserved + MAXIMUM_RESPONSE_BYTES <= budget["maximum_total_response_bytes"],
                    "whole_page_reservation_budget_exceeded_at_START")
            if kind == "start":
                reserved += MAXIMUM_RESPONSE_BYTES
                active.add(ordinal)
            else:
                spent += charge
        else:
            require(ordinal in active, "whole_page_reservation_receipt_without_START")
            active.remove(ordinal)
            reserved -= MAXIMUM_RESPONSE_BYTES
            spent += charge
    require(not active and reserved == 0 and spent == charged_bytes,
            "whole_page_reservation_ledger_did_not_close")
    require(charged_bytes <= budget["maximum_total_response_bytes"], "cumulative_response_budget_exceeded")
    complete = len(indexed) == budget["maximum_attempts"] and not halted
    payload = {"schema": "si-parallel-count-inventory-draft-v1", "plan_sha256": plan.sha256,
               "started_at": started_at, "completed_at": completed_at, "attempts_started": len(indexed),
               "http_invocations": http_invocations, "retained_raw_bytes": actual_bytes,
               "charged_response_bytes": charged_bytes,
               "unstarted_tickets": budget["maximum_attempts"] - len(indexed), "halted": halted,
               "complete_frozen_request_sequence": complete, "authority": authority()}
    value = object.__new__(ParallelCountInventory)
    serialized = canonical_json(payload), tuple(canonical_json(indexed[i]) for i in sorted(indexed))
    digest = hashlib.sha256(b"si-parallel-count-inventory-draft-v1\0")
    for raw in (serialized[0], *serialized[1]):
        encoded = raw.encode()
        digest.update(len(encoded).to_bytes(8, "little"))
        digest.update(encoded)
    parts = plan, *serialized, digest.hexdigest()
    for name, item in zip(("_plan", "_json", "_receipts", "_digest"), parts):
        object.__setattr__(value, name, item)
    object.__setattr__(value, "_anchor", parts)
    object.__setattr__(value, "_identity", parts)
    return value


def verify_capture_receipt(inventory, capture):
    """Proposed typed registry gate; no caller chronology bypass boolean."""
    from research.short_interest_etf.native_dated_class_reference import CapturedNativeDatedClassResponse
    require(type(inventory) is ParallelCountInventory and type(capture) is CapturedNativeDatedClassResponse,
            "exact_parallel_inventory_and_capture_required")
    capture._guard()
    ticket, meta = capture._query.to_payload(), json.loads(capture._meta)
    require(capture._query._plan is inventory._plan._queries, "parallel_capture_plan_lineage_changed")
    receipt = inventory.receipt_for_ordinal(ticket["query_ordinal"])
    require(meta["request_sha256"] == receipt["request_sha256"] and meta["received_at"] == receipt["received_at"]
            and meta["http_status"] == receipt["http_status"] and meta["body_observed"] == receipt["body_observed"],
            "parallel_capture_receipt_changed")
    if receipt["body_observed"]:
        require(meta["raw_sha256"] == receipt["raw_sha256"] and len(capture._raw) == receipt["raw_bytes"]
                and meta["content_type"] == receipt["content_type"], "parallel_capture_raw_binding_changed")
    else:
        require(not capture._raw and type(receipt["http_status"]) is int and receipt["http_status"] != 200,
                "only_observed_non200_negative_capture_replays")
    return receipt
