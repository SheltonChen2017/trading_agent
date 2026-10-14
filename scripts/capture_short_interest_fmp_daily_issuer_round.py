"""Prospective bounded FMP v2 capture/replay, not issuer/class admission.

All source/capture closure pins remain PENDING. No operational CLI exists.
The unchanged v1 route/parser is reused, not handed a relabelled v2 plan.
"""
from dataclasses import dataclass, field
import json
import re
from urllib.request import Request

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf import fmp_daily_issuer_cap as daily
from research.short_interest_etf import fmp_company_context as context
from scripts import capture_short_interest_fmp_company_context as route
from scripts import short_interest_lane_batch_guard as lane
from scripts.continue_short_interest_native_identity import _OwnedOutput
from scripts.qualify_finra_short_interest import _require_capture_platform
from scripts.qualify_sharadar_companion import SharadarCaptureRefusal, _utc_now
from scripts.short_interest_keychain import KeychainSecret, read_named_keychain

MAXIMUM_REQUESTS = 2000
MAXIMUM_BYTES = 3 * 1024 ** 3
SOURCE_CLOSURE_SHA256 = "PENDING"
DAILY_INDEX_SHA256 = "PENDING"
INDEXED_PLAN_SHA256 = "PENDING"
RUNTIME_PLAN_SHA256 = "PENDING"
PROTOCOL_SHA256 = "PENDING"


def require(value, reason):
    context._require(value, reason)


def digest(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def protocol():
    return {"schema": "si-operational-FMP-daily-issuer-cap-v2", "daily_policy": daily.policy(),
        "source_closure_sha256": SOURCE_CLOSURE_SHA256, "daily_index_sha256": DAILY_INDEX_SHA256,
        "indexed_plan_sha256": INDEXED_PLAN_SHA256, "runtime_plan_sha256": RUNTIME_PLAN_SHA256,
        "maximum_requests": MAXIMUM_REQUESTS, "maximum_total_response_bytes": MAXIMUM_BYTES,
        "scope": "all_exact_source_selected_CIK_targets;oversized_plan_refuses_before_claim_and_key;no_automatic_subsample",
        "reservation": "whole_1MiB50rows_lookup_or8MiB5000rows_cap_before_START;unknown_failed_body_spends_full_reservation",
        "source_guard": "once_verified_complete_typed_daily_index;immutable_component_identity_and_held_source_FD_per_slot",
        "lane_guard": "fresh_local_every_START_and_named_publication;actual_remote_every_at_most_eight_STARTs_and24_names",
        "code_identity": "complete_current_committed_manifest_in_start_and_receipts_not_protocol_self_hash",
        "authentication": "owner_named_existing_fmp_Keychain_apikey_header_never_URL",
        "lookup_negative": "retain_exact_negative_context_and_frozen_cap_skip_no_budget_repurpose",
        "raw": "key_echo_media_and_all_date_scope_before_body_hash_or_storage",
        "proxies": False, "redirects": False, "automatic_retries": 0,
        "cap_is_never_shares": True, "authority": context._authority()}


@dataclass(frozen=True, slots=True, init=False)
class V2CapturePlan:
    _source: object = field(repr=False)
    _source_bindings: tuple = field(repr=False)
    _header: bytes = field(repr=False)
    _slots: tuple = field(repr=False)
    _digest: str
    _anchor: tuple = field(repr=False)
    _identity: tuple = field(repr=False)

    def __init__(self):
        raise context.FmpContextError("REFUSED: exact_indexed_v2_plan_factory_required")

    def guard(self):
        parts = self._source, self._source_bindings, self._header, self._slots, self._digest
        require(type(self) is V2CapturePlan and self._anchor is self._identity
                and all(a is b for a, b in zip(parts, self._anchor)), "v2_capture_plan_changed")
        source, index, base, source_anchor, index_anchor, base_anchor = self._source_bindings
        require(source is self._source and source._anchor is source._identity is source_anchor
                and source._bytes is source_anchor[0] and source._index is index is source_anchor[1]
                and source._base is base is source_anchor[2], "indexed_source_components_changed")
        require(index._anchor is index._identity is index_anchor
                and all(getattr(index, name) is old for name, old in zip(("_header", "_cells", "_pool", "_offsets",
                    "_target_bits", "_selected", "_selected_map", "_plan", "_index"), index_anchor)), "daily_index_components_changed")
        require(base._anchor is base._identity is base_anchor and base._bytes is base_anchor[0]
                and base._refs is base_anchor[1], "source_ticket_inventory_changed")
        index._plan._guard()
        index._index._guard()

    @property
    def sha256(self):
        self.guard()
        return self._digest

    def payload(self):
        self.guard()
        return json.loads(self._header)

    def slots(self):
        for slot in self._slots:
            self.guard()
            slot[2].to_bytes()  # Only this exact target, not all tickets/index.
            yield slot


def freeze_v2_capture_plan(source):
    require(type(source) is daily.IndexedCompanyCapPlan, "exact_typed_daily_indexed_plan_required")
    source._guard()  # Complete original factory guards once, before any claim/key.
    spec = source.to_payload()
    require(type(MAXIMUM_REQUESTS) is int and MAXIMUM_REQUESTS == 2000 and MAXIMUM_BYTES == daily.MAXIMUM_TOTAL_RESPONSE_BYTES
            and type(spec["maximum_requests"]) is int and 0 < spec["maximum_requests"] <= MAXIMUM_REQUESTS
            and spec["maximum_total_bytes"] == MAXIMUM_BYTES, "v2_plan_exceeds_prospective_request_or_byte_cap")
    base, slots = source.base_context_plan(), []
    for number, ticket in enumerate(base.tickets(), 1):
        for stage in ("lookup", "cap"):
            descriptor = context.request_descriptor(ticket, stage)
            slots.append((number, stage, ticket, canonical_json(descriptor).encode(), hash_payload(descriptor),
                context.MAXIMUM_LOOKUP_BYTES if stage == "lookup" else context.cap.MAXIMUM_RESPONSE_BYTES,
                context.MAXIMUM_LOOKUP_ROWS if stage == "lookup" else context.cap.LIMIT))
    require(len(slots) == spec["maximum_requests"] and all(slot[5] <= MAXIMUM_BYTES for slot in slots),
            "all_exact_frozen_stage_slots_required")
    index_sha, source_sha = source._index.sha256, source.sha256  # Large index hash exactly once.
    header = canonical_json({"schema": "si-FMP-v2-frozen-operational-plan-v1", "daily_index_sha256": index_sha,
        "indexed_plan_sha256": source_sha, "policy_sha256": hash_payload(daily.policy()),
        "maximum_requests": len(slots), "maximum_bytes": MAXIMUM_BYTES,
        "maximum_rows": spec["maximum_rows"], "slot_request_sha256s": [slot[4] for slot in slots],
        "authority": context._authority()}).encode()
    result = object.__new__(V2CapturePlan)
    bindings = source, source._index, base, source._anchor, source._index._anchor, base._anchor
    values = source, bindings, header, tuple(slots), hash_bytes(header)
    for name, value in zip(("_source", "_source_bindings", "_header", "_slots", "_digest"), values):
        object.__setattr__(result, name, value)
    object.__setattr__(result, "_anchor", values)
    object.__setattr__(result, "_identity", values)
    return result


def _registered(plan):
    require(type(plan) is V2CapturePlan, "exact_v2_operational_plan_required")
    payload = plan.payload()
    require(all(digest(pin) for pin in (SOURCE_CLOSURE_SHA256, DAILY_INDEX_SHA256, INDEXED_PLAN_SHA256,
                RUNTIME_PLAN_SHA256, PROTOCOL_SHA256))
            and payload["daily_index_sha256"] == DAILY_INDEX_SHA256
            and payload["indexed_plan_sha256"] == INDEXED_PLAN_SHA256 and plan.sha256 == RUNTIME_PLAN_SHA256
            and hash_payload(protocol()) == PROTOCOL_SHA256, "v2_prospective_source_and_protocol_pins_pending_or_changed")


def _media(value):
    return (type(value) is str and len(value) <= 256 and all(32 <= ord(char) <= 126 for char in value)
            and value.partition(";")[0].strip().lower() == "application/json")


def capture_v2(root, directory, plan, *, head, remote, code_identity_sha256, source_custody, code_custody,
        owned, guard=None, read_secret=read_named_keychain, clock=_utc_now, http=route._http):
    _require_capture_platform()
    _registered(plan)  # Oversized/unregistered scope precedes claim and key.
    require(type(owned) is _OwnedOutput and owned._anchor[0] == directory and digest(code_identity_sha256),
            "exact_owned_output_and_complete_committed_code_identity_required")
    guard = lane.LaneGuard(root, expected_head=head, expected_remote=remote) if guard is None else guard
    require(type(guard) is lane.LaneGuard and guard.binding()[:3] == (root, head, remote), "exact_v2_lane_guard")
    def local():
        guard.check()
        _registered(plan)
        source_custody()
        code_custody()
        owned.check()
    def store(items, *, refusal=False):
        require(type(items) is tuple and 1 <= len(items) <= 24 and len({name for name, raw in items}) == len(items),
                "finite_exact_named_publication_batch")
        if not refusal:
            guard.refresh()
        for name, raw in items:
            require(type(raw) is bytes, "original_bound_publication_bytes_required")
            local()
            owned.publish(name, raw)
            local()
        if not refusal:
            guard.refresh()
    local()
    guard.refresh()
    started = clock()
    previous, attempts, total_bytes, total_rows, starts_since_remote = context._utc(started), 0, 0, 0, 0
    budget = plan.payload()
    claim = {"schema": "si-FMP-v2-global-source-budget-v1", "plan_sha256": plan.sha256,
        "source_closure_sha256": SOURCE_CLOSURE_SHA256, "protocol_sha256": PROTOCOL_SHA256,
        "maximum_requests": budget["maximum_requests"], "maximum_bytes": MAXIMUM_BYTES,
        "maximum_rows": budget["maximum_rows"], "started_at": started,
        "automatic_retries": 0, "restart_allowed": False, "unused_slots_repurposable": False}
    local()
    owned.publish("budget-" + hash_payload({"source": SOURCE_CLOSURE_SHA256, "plan": plan.sha256,
            "protocol": PROTOCOL_SHA256, "policy": hash_payload(daily.policy())}) + ".json",
            canonical_json(claim).encode(), parent=True)
    local()
    store((("protocol.private.json", canonical_json(protocol()).encode()), ("started.json", canonical_json({
        "schema": "si-FMP-v2-run-start-v1", "started_at": started, "code_head": head,
        "code_identity_sha256": code_identity_sha256, "protocol_sha256": PROTOCOL_SHA256,
        "plan_sha256": plan.sha256, "source_closure_sha256": SOURCE_CLOSURE_SHA256,
        "outcome_looks": 0, "qc_attempts": 0}).encode())))
    inventory, company = [], None
    try:
        local()
        secret = read_secret("fmp")
        require(type(secret) is KeychainSecret, "exact_named_redacted_FMP_secret_required")
        local()
    except Exception:
        store((("run.refused.json", canonical_json({"schema": "si-FMP-v2-run-refused-v1", "http_attempts": 0,
            "code": "named_FMP_key_unavailable_after_claim", "refused_at": clock(), "outcome_looks": 0, "qc_attempts": 0}).encode()),), refusal=True)
        raise context.FmpContextError("REFUSED: named_FMP_key_unavailable_after_claim") from None
    opener = route.build_protected_opener()
    route._require_protected_opener(opener)
    for number, stage, ticket, descriptor_raw, request_sha, maximum, maximum_rows in plan.slots():
        prefix = f"target-{number:06d}.{stage}"
        if stage == "cap" and company.to_payload()["selected_row_index"] is None:
            skipped = {"schema": "si-FMP-v2-frozen-cap-skip-v1", "ticket_sha256": ticket.sha256,
                "lookup_report_sha256": company.sha256, "http_attempted": False, "unused_budget_repurposed": False}
            store(((prefix + ".skipped.json", canonical_json(skipped).encode()),))
            inventory.append({"target": number, "stage": stage, "status": "skipped_unresolved_context"})
            continue
        local()
        require(attempts < budget["maximum_requests"] and total_bytes + maximum <= MAXIMUM_BYTES
                and total_rows + maximum_rows <= budget["maximum_rows"], "whole_v2_page_budget_before_START")
        require(not secret.echoed_in(descriptor_raw), "credential_in_frozen_descriptor")
        descriptor = json.loads(descriptor_raw)
        url = context.clean_url(ticket, stage)
        require(not secret.echoed_in(url.encode()), "credential_in_clean_URL")
        if starts_since_remote == 0:
            guard.refresh()
        local()
        began = clock()
        require(previous <= context._utc(began), "request_start_chronology")
        attempts += 1
        starts_since_remote = (starts_since_remote + 1) % 8
        store(((prefix + ".started.json", canonical_json({"schema": "si-FMP-v2-request-start-v1", "attempt": attempts,
            "target": number, "stage": stage, "request": descriptor, "request_sha256": request_sha,
            "started_at": began, "whole_page_bytes_reserved": maximum, "whole_page_rows_reserved": maximum_rows,
            "code_head": head, "code_identity_sha256": code_identity_sha256, "protocol_sha256": PROTOCOL_SHA256}).encode()),))
        status, invoked, observed, retained = None, False, False, False
        try:
            local()
            request = Request(url, method="GET", headers={"Accept": "application/json", "apikey": secret.for_authorization_header()})
            invoked = True
            raw, media, status = http(opener, request, maximum)
            require(type(raw) is bytes and len(raw) <= maximum and type(media) is str
                    and not secret.echoed_in(raw) and not secret.echoed_in(media.encode()), "echo_or_size_refused_before_body_hash")
            observed = True
            require(type(status) is int and status == 200 and _media(media), "successful_JSON_media_required")
            received = clock()
            require(context._utc(began) <= context._utc(received), "response_chronology")
            (context.preflight_lookup_scope if stage == "lookup" else context.cap.preflight_scope)(raw)
            local()
            raw_sha = hash_bytes(raw)
            # Preserve admissible raw provenance before semantic qualification.
            receipt = {"schema": "si-FMP-v2-received-v1", "attempt": attempts, "target": number, "stage": stage,
                "request_sha256": request_sha, "received_at": received, "http_status": status, "content_type": media,
                "raw_path": prefix + ".raw", "raw_sha256": raw_sha, "raw_bytes": len(raw), "http_attempted": invoked}
            store(((prefix + ".raw", raw), (prefix + ".received.json", canonical_json(receipt).encode())))
            retained = True
            result = (context.qualify_context(ticket, raw=raw, raw_sha256=raw_sha, request_sha256=request_sha,
                started_at=began, received_at=received, http_status=status, content_type=media) if stage == "lookup" else
                context.qualify_company_cap(company, raw=raw, raw_sha256=raw_sha, request_sha256=request_sha,
                started_at=began, received_at=received, http_status=status, content_type=media))
            store(((prefix + ".qualified.private.json", result.to_bytes()),))
            total_bytes += len(raw)
            total_rows += len(result.to_payload()["rows"])
            previous = context._utc(received)
            inventory.append({"target": number, "stage": stage, "status": "source_report_retained",
                "report_sha256": result.sha256, "report_path": prefix + ".qualified.private.json"})
            if stage == "lookup":
                company = result
        except Exception as error:
            # Failed unknown/discarded bodies spend their full reserved ceiling;
            # no retry or unused-slot repurpose follows any material failure.
            status = error.http_status if type(error) is SharadarCaptureRefusal else status
            status = status if type(status) is int and 100 <= status <= 599 else None
            refused = clock()
            require(context._utc(began) <= context._utc(refused), "refusal_chronology")
            store(((prefix + ".refused.json", canonical_json({"schema": "si-FMP-v2-attempt-refused-v1",
                "attempt": attempts, "target": number, "stage": stage, "request_sha256": request_sha,
                "refused_at": refused, "http_attempted": invoked, "http_status": status, "body_observed": observed,
                "raw_retained": retained, "charged_bytes": maximum, "charged_rows": maximum_rows,
                "error_body_read": False, "code": "source_request_refused_no_retry"}).encode()),), refusal=True)
            raise context.FmpContextError("REFUSED: source_request_refused_no_retry") from None
    ended = clock()
    require(previous <= context._utc(ended) and len(inventory) == len(plan._slots), "complete_frozen_sequence_and_clocks_required")
    guard.refresh()
    final = {"schema": "si-FMP-v2-completed-inventory-v1", "plan_sha256": plan.sha256, "protocol_sha256": PROTOCOL_SHA256,
        "code_head": head, "code_identity_sha256": code_identity_sha256, "started_at": started, "completed_at": ended,
        "http_attempts": attempts, "retained_raw_bytes": total_bytes, "decoded_rows": total_rows, "stages": inventory,
        "unused_budget_repurposed": False, "authority": context._authority()}
    store((("inventory.private.json", canonical_json(final).encode()),))
    return final


def iter_replayed_company_caps(plan, *, read, boundary, expected_inventory_bytes_sha256, expected_code_head,
        expected_code_identity_sha256, budget_raw):
    """Protected caller supplies exact byte pins/read-only custody, no saved flags.

    One issuer report is rebuilt at a time. Complete semantic replay requires
    consuming this generator to exhaustion; partial iteration is not complete
    source coverage and supplies no admission/QC/outcome authority.
    """
    _registered(plan)
    require(digest(expected_inventory_bytes_sha256) and digest(expected_code_identity_sha256)
            and type(expected_code_head) is str and re.fullmatch(r"[0-9a-f]{40}", expected_code_head), "registered_replay_anchors_required")
    def get(name):
        boundary()
        raw = read(name)
        boundary()
        require(type(raw) is bytes, "original_protected_replay_bytes_required")
        return raw
    def parsed(raw):
        value = context._decode(raw)
        require(type(value) is dict and canonical_json(value).encode() == raw, "canonical_unique_replay_receipt_required")
        return value
    def exact(left, right):
        return canonical_json(left) == canonical_json(right)
    original = get("inventory.private.json")
    require(hash_bytes(original) == expected_inventory_bytes_sha256, "registered_inventory_bytes_changed")
    saved = parsed(original)
    start = parsed(get("started.json"))
    require(get("protocol.private.json") == canonical_json(protocol()).encode()
            and saved["plan_sha256"] == start["plan_sha256"] == plan.sha256
            and saved["protocol_sha256"] == start["protocol_sha256"] == PROTOCOL_SHA256
            and saved["code_head"] == start["code_head"] == expected_code_head
            and saved["code_identity_sha256"] == start["code_identity_sha256"] == expected_code_identity_sha256
            and canonical_json(saved["authority"]) == canonical_json(context._authority()), "complete_replay_source_code_binding")
    require(exact(start, {"schema": "si-FMP-v2-run-start-v1", "started_at": saved["started_at"],
            "code_head": expected_code_head, "code_identity_sha256": expected_code_identity_sha256,
            "protocol_sha256": PROTOCOL_SHA256, "plan_sha256": plan.sha256,
            "source_closure_sha256": SOURCE_CLOSURE_SHA256, "outcome_looks": 0, "qc_attempts": 0})
            and saved.get("schema") == "si-FMP-v2-completed-inventory-v1"
            and type(saved.get("stages")) is list and len(saved["stages"]) == len(plan._slots)
            and all(type(saved.get(key)) is int and saved[key] >= 0
                for key in ("http_attempts", "retained_raw_bytes", "decoded_rows")), "exact_original_enclosing_receipt_types")
    claim = parsed(budget_raw)
    require(exact(claim, {"schema": "si-FMP-v2-global-source-budget-v1", "plan_sha256": plan.sha256,
            "source_closure_sha256": SOURCE_CLOSURE_SHA256, "protocol_sha256": PROTOCOL_SHA256,
            "maximum_requests": plan.payload()["maximum_requests"], "maximum_bytes": MAXIMUM_BYTES,
            "maximum_rows": plan.payload()["maximum_rows"], "started_at": start["started_at"],
            "automatic_retries": 0, "restart_allowed": False, "unused_slots_repurposable": False}),
            "original_spent_v2_claim_required")
    previous, attempts, size, row_count, records, company = context._utc(start["started_at"]), 0, 0, 0, [], None
    for number, stage, ticket, descriptor_raw, request_sha, maximum, rows_max in plan.slots():
        prefix = f"target-{number:06d}.{stage}"
        if stage == "cap" and company.to_payload()["selected_row_index"] is None:
            skipped = parsed(get(prefix + ".skipped.json"))
            require(exact(skipped, {"schema": "si-FMP-v2-frozen-cap-skip-v1", "ticket_sha256": ticket.sha256,
                "lookup_report_sha256": company.sha256, "http_attempted": False, "unused_budget_repurposed": False}),
                "original_negative_context_frozen_cap_skip")
            records.append({"target": number, "stage": stage, "status": "skipped_unresolved_context"})
            require(exact(saved["stages"][len(records) - 1], records[-1]), "original_skipped_stage_inventory_binding")
            continue
        began, receipt, raw = parsed(get(prefix + ".started.json")), parsed(get(prefix + ".received.json")), get(prefix + ".raw")
        attempts += 1
        require(began["attempt"] == receipt["attempt"] == attempts and began["target"] == receipt["target"] == number
                and began["stage"] == receipt["stage"] == stage and canonical_json(began["request"]).encode() == descriptor_raw
                and began["request_sha256"] == receipt["request_sha256"] == request_sha
                and began["whole_page_bytes_reserved"] == maximum and began["whole_page_rows_reserved"] == rows_max
                and previous <= context._utc(began["started_at"]) <= context._utc(receipt["received_at"]), "original_stage_descriptor_budget_clock_binding")
        require(exact(began, {"schema": "si-FMP-v2-request-start-v1", "attempt": attempts, "target": number,
            "stage": stage, "request": json.loads(descriptor_raw), "request_sha256": request_sha,
            "started_at": began["started_at"], "whole_page_bytes_reserved": maximum,
            "whole_page_rows_reserved": rows_max, "code_head": expected_code_head,
            "code_identity_sha256": expected_code_identity_sha256, "protocol_sha256": PROTOCOL_SHA256}),
            "exact_original_START_code_and_integer_binding")
        require(size + maximum <= MAXIMUM_BYTES and row_count + rows_max <= plan.payload()["maximum_rows"]
                and receipt["http_attempted"] is True and receipt["http_status"] == 200
                and _media(receipt["content_type"]) and receipt["raw_path"] == prefix + ".raw"
                and type(receipt["raw_bytes"]) is int and receipt["raw_bytes"] == len(raw) <= maximum
                and receipt["raw_sha256"] == hash_bytes(raw), "original_full_page_reservations_and_raw_provenance")
        require(exact(receipt, {"schema": "si-FMP-v2-received-v1", "attempt": attempts, "target": number,
            "stage": stage, "request_sha256": request_sha, "received_at": receipt["received_at"],
            "http_status": 200, "content_type": receipt["content_type"], "raw_path": prefix + ".raw",
            "raw_sha256": receipt["raw_sha256"], "raw_bytes": len(raw), "http_attempted": True}),
            "exact_original_received_types_and_fields")
        kwargs = dict(raw=raw, raw_sha256=receipt["raw_sha256"], request_sha256=request_sha,
            started_at=began["started_at"], received_at=receipt["received_at"], http_status=200, content_type=receipt["content_type"])
        rebuilt = context.qualify_context(ticket, **kwargs) if stage == "lookup" else context.qualify_company_cap(company, **kwargs)
        require(rebuilt.to_bytes() == get(prefix + ".qualified.private.json"), "original_qualified_report_byte_replay")
        size += len(raw)
        row_count += len(rebuilt.to_payload()["rows"])
        previous = context._utc(receipt["received_at"])
        records.append({"target": number, "stage": stage, "status": "source_report_retained",
            "report_sha256": rebuilt.sha256, "report_path": prefix + ".qualified.private.json"})
        require(exact(saved["stages"][len(records) - 1], records[-1]), "original_stage_report_digest_before_yield")
        if stage == "lookup":
            company = rebuilt
        else:
            yield rebuilt  # Same-date binding remains the unchanged indexed pure function.
    require(saved["stages"] == records and saved["http_attempts"] == attempts and saved["retained_raw_bytes"] == size
            and saved["decoded_rows"] == row_count and saved["started_at"] == start["started_at"]
            and previous <= context._utc(saved["completed_at"]) and saved["unused_budget_repurposed"] is False,
            "all_frozen_stage_inventory_reconstructed_not_saved_complete_boolean")
