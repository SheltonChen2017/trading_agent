"""Prospective source-only count driver for one exact protected cached plan.

No CLI or provider invocation is enabled while the literal pins are PENDING.
Main supplies its once-verified cache with held inode-custody checks. No raw
112-date replay, packed-plan hash, or remote lookup occurs per file chunk.
"""
from concurrent.futures import ThreadPoolExecutor
from itertools import islice
import json
import re
import urllib.request
from urllib.parse import urlencode

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.native_reported_anchor_plan as anchors
import research.short_interest_etf.native_parallel_count_contract as parallel
from scripts import short_interest_lane_batch_guard as lane
from scripts import capture_short_interest_native_parallel_counts as transport
from scripts.continue_short_interest_native_identity import _OwnedOutput
from scripts.qualify_finra_short_interest import _require_capture_platform
from scripts.qualify_sharadar_companion import _utc_now, SharadarCaptureRefusal
from scripts.short_interest_keychain import KeychainSecret, read_named_keychain

ANCHOR_PLAN_SHA256 = "d58b2b3d006319899e6af9cd06a2fef17128c391513ea0ee99c987c483d2af3b"
CACHE_CLOSURE_SHA256 = "51190cff010622a7c8422c54dd8be6084caa07a2c748444631655844e9f46d56"
PARALLEL_PLAN_SHA256 = "d1c9d08b939022bf5eafa2cdde47f9555fe1bbd04c28e7650fb6bdb4d5a5ee56"
PROTOCOL_SHA256 = "45a554213ed8fb12ac6f334bb0b87053b0d1a899603e093bdc4bfe06daf47354"
MAXIMUM_TOTAL_RESPONSE_BYTES = 4 * 1024 * 1024 * 1024


def protocol():
    return {"schema": "si-exact-cache-parallel-count-capture-v1", "anchor_plan_sha256": ANCHOR_PLAN_SHA256,
            "cache_closure_sha256": CACHE_CLOSURE_SHA256, "parallel_plan_sha256": PARALLEL_PLAN_SHA256,
            "code_identity": "complete_current_committed_manifest_registered_in_start_not_self_referential", "policy": parallel.policy(),
            "maximum_total_response_bytes": MAXIMUM_TOTAL_RESPONSE_BYTES,
            "guard": "fresh_two_Git_local_before_every_HTTP_start_and_named_publication;actual_matching_remote_per_at_most_eight_HTTP_batch_and_24_publications",
            "custody": "held_owned0700_directory_FDs;exclusive0600_no_follow_single_link_outputs;source_and_code_immutable_identity_each_slot",
            "claim": "one_exclusive_source_plan_protocol_claim_before_named_key;not_runtime_head_or_clock_dependent;no_restart",
            "start_evidence": "prevalidate_all_at_most_eight_descriptors_and_clocks_before_any_debit;missing_debited_receipt_is_refusal_not_undercounted_inventory",
            "remote_advance": "stop_new_starts;drain_only_started_at_most_eight;fixed_refusal_no_Completed",
            "authentication": "owner_named_existing_Massive_Keychain_Bearer_header_memory_only",
            "proxies": False, "redirects": False, "automatic_retries": 0,
            "source_only": True, "source_admitted": False, "outcome_looks": 0, "qc_attempts": 0,
            "backtest_result_exists": False}


def _require(value, reason):
    parallel.require(value, reason)


def _bound(source, plan, code_identity_sha256):
    _require(type(source) is anchors.NativeReportedAnchorPlan and type(plan) is parallel.ParallelCountPlan,
             "exact_cached_anchor_and_parallel_plan_required")
    source._guard()
    plan.guard()
    _require(plan._queries is source.query_plan and source.sha256 == ANCHOR_PLAN_SHA256
            and plan.sha256 == PARALLEL_PLAN_SHA256
            and type(code_identity_sha256) is str and re.fullmatch(r"[0-9a-f]{64}", code_identity_sha256)
            and all(type(pin) is str and re.fullmatch(r"[0-9a-f]{64}", pin)
                for pin in (CACHE_CLOSURE_SHA256, PARALLEL_PLAN_SHA256, PROTOCOL_SHA256))
            and hash_payload(protocol()) == PROTOCOL_SHA256
            and plan.to_payload()["maximum_total_response_bytes"] == MAXIMUM_TOTAL_RESPONSE_BYTES,
            "prospective_cache_code_protocol_pins_pending_or_changed")


def _json_media(value):
    return (type(value) is str and 1 <= len(value) <= 256 and all(32 <= ord(c) <= 126 for c in value)
            and value.partition(";")[0].strip().lower() in {"application/json", "application/vnd.api+json"})


def _wire_request(query, secret):
    ticket = query.to_payload()
    spec = ticket["request"]
    _require(not secret.echoed_in(canonical_json(ticket).encode()), "request_descriptor_secret_echo_refused")
    return urllib.request.Request(spec["url"] + "?" + urlencode(spec["params"]), method="GET",
            headers={"Accept": "application/json", "Authorization": "Bearer " + secret.for_authorization_header()})


def capture_loaded_source(root, directory, source, plan, *, head, remote, code_identity_sha256,
        source_custody, code_custody, owned, read_secret=read_named_keychain, clock=_utc_now,
        guard=None, http=transport._http):
    """Actual operational seams, but only after Main registers all literal pins.

    ``source`` must originate in the registered protected cache factory. Its
    exact query-plan instance is retained. Custody callbacks check held FDs and
    immutable committed code identity; their return values never admit facts.
    ``owned`` is the new exclusive output inode, not an arbitrary publisher.
    """
    _require_capture_platform()  # Before source/key/ignored output access.
    _require(type(owned) is _OwnedOutput and owned._anchor[0] == directory, "exact_new_owned_output_required")
    _bound(source, plan, code_identity_sha256)
    guard = lane.LaneGuard(root, expected_head=head, expected_remote=remote) if guard is None else guard
    _require(type(guard) is lane.LaneGuard and guard.binding()[:3] == (root, head, remote), "fixed_operational_lane_guard")
    gate = lane.BoundedBatchGate(guard, plan)
    frozen = tuple((name, globals()[name]) for name in ("ANCHOR_PLAN_SHA256", "CACHE_CLOSURE_SHA256",
            "PARALLEL_PLAN_SHA256", "PROTOCOL_SHA256", "MAXIMUM_TOTAL_RESPONSE_BYTES"))
    def custody():
        _require(all(globals()[name] == value for name, value in frozen), "operational_scope_changed")
        # Rebind the small protocol/plan policy, including imported response
        # limits. The large immutable matrix/packed parts are identity checked
        # only; neither is rehashed per source slot or publication chunk.
        _bound(source, plan, code_identity_sha256)
        source_custody()
        code_custody()
        owned.check()
    def local():
        guard.check()
        custody()
    def publish_batch(items, *, drain=False):
        # Drain permits no new request/success authority; every name remains
        # fixed to the already-started bounded batch or its final refusal.
        _require(type(items) is tuple and 1 <= len(items) <= 24
                and len({name for name, raw in items}) == len(items), "finite_named_publication_batch")
        if not drain:
            gate.open_publication_batch(tuple(name for name, raw in items))
        for name, raw in items:
            _require(type(raw) is bytes, "original_publication_bytes_required")
            if drain:
                _require(name == "run.refused.json" or re.fullmatch(r"query-[0-9]{8}\.(raw|received\.json)", name),
                        "drain_only_original_result_or_refusal_name")
                if name != "run.refused.json":
                    _require(int(name[6:14]) in gate._state["started"], "only_started_slot_may_publish_after_halt")
            else:
                gate.authorize_publication(name)
            local()
            owned.publish(name, raw)
            local()
        if not drain:
            gate.close_publication_batch()
    local()
    guard.refresh()
    began = clock()
    start = parallel.clock(began)
    # The whole frozen protocol, not runtime timestamp/head, owns one claim.
    claim = {"schema": "si-cache-parallel-count-global-claim-v1", "protocol_sha256": PROTOCOL_SHA256,
            "anchor_plan_sha256": ANCHOR_PLAN_SHA256, "cache_closure_sha256": CACHE_CLOSURE_SHA256,
            "parallel_plan_sha256": plan.sha256, "started_at": began,
            "maximum_attempts": plan.to_payload()["maximum_attempts"],
            "maximum_total_response_bytes": MAXIMUM_TOTAL_RESPONSE_BYTES, "restart_allowed": False}
    local()
    owned.publish("budget-" + hash_payload(protocol()) + ".json", canonical_json(claim).encode(), parent=True)
    local()
    publish_batch((("protocol.private.json", canonical_json(protocol()).encode()),
        ("started.json", canonical_json({"schema": "si-cache-parallel-count-start-v1", "started_at": began,
            "code_head": head, "remote_head": remote, "protocol_sha256": PROTOCOL_SHA256,
            "code_identity_sha256": code_identity_sha256, "outcome_looks": 0, "qc_attempts": 0}).encode())))
    receipts, attempted, charged, previous_start, fatal = [], 0, 0, start, False
    def refused(reason):
        end = clock()
        _require(previous_start <= parallel.clock(end), "refusal_clock_backdated")
        publish_batch((("run.refused.json", canonical_json({"schema": "si-cache-parallel-count-refused-v1",
                "code": reason, "refused_at": end, "attempts_started": attempted,
                "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False}).encode()),), drain=True)
    try:
        local()
        secret = read_secret("massive")
        _require(type(secret) is KeychainSecret, "exact_existing_redacted_Massive_key_required")
        local()
    except Exception:
        refused("named_key_or_custody_unavailable_after_claim")
        raise parallel.ParallelCountRefusal("REFUSED: named_key_or_custody_unavailable_after_claim") from None
    def worker(query, request, at):
        invoked, status, raw, media, observed, code = False, None, None, None, False, "material_request_refused"
        try:
            local()  # Fresh invariant immediately before this authorized HTTP.
            opener = transport.build_protected_opener()
            transport._opener(opener)
            invoked = True
            raw, media, status = http(opener, request, parallel.MAXIMUM_RESPONSE_BYTES)
            _require(type(raw) is bytes and len(raw) <= parallel.MAXIMUM_RESPONSE_BYTES
                    and type(media) is str and not secret.echoed_in(raw) and not secret.echoed_in(media.encode()),
                    "response_echo_or_size_refused_before_digest_or_publication")
            _require(type(status) is int and status == 200 and _json_media(media), "successful_JSON_media_required")
            observed, code = True, "received"
        except SharadarCaptureRefusal as error:
            status = error.http_status if type(error.http_status) is int and 100 <= error.http_status <= 599 else None
            raw, media = None, None
            if status == 404 and invoked:
                code = "HTTP_404_body_unobserved"
        except Exception:
            raw, media = None, None
        ended = clock()
        if parallel.clock(ended) < parallel.clock(at):
            raise parallel.ParallelCountRefusal("REFUSED: worker_receipt_clock_backdated")
        ordinal = query.to_payload()["query_ordinal"]
        return {"query_ordinal": ordinal, "request_sha256": query.to_payload()["request_sha256"],
                "started_at": at, "received_at": ended, "http_attempted": invoked, "http_status": status,
                "body_observed": observed, "raw_path": None, "raw_sha256": None, "raw_bytes": None,
                "content_type": media if observed else None, "code": code}, raw
    queries = iter(plan._queries.iter_queries())
    with ThreadPoolExecutor(max_workers=parallel.MAXIMUM_INFLIGHT) as pool:
        while attempted < plan.to_payload()["maximum_attempts"] and not fatal:
            slots = min(8, (MAXIMUM_TOTAL_RESPONSE_BYTES - charged) // parallel.MAXIMUM_RESPONSE_BYTES)
            if slots == 0:
                fatal = True
                break
            tickets = tuple(islice(queries, slots))
            _require(tickets, "missing_frozen_query_ticket")
            pending, results, starts, ready = [], [], [], []
            try:
                gate.open_HTTP_batch(tickets)
                for query in tickets:
                    request = _wire_request(query, secret)  # Echo BEFORE any descriptor persistence.
                    at = clock()
                    _require(previous_start <= parallel.clock(at), "request_start_clock_backdated")
                    previous_start = parallel.clock(at)
                    ready.append((query, request, at))
                for query, request, at in ready:
                    gate.authorize_start(query)
                    attempted += 1
                    ordinal = query.to_payload()["query_ordinal"]
                    _require(ordinal == attempted, "next_frozen_ticket_ordinal_changed")
                    starts.append((f"query-{ordinal:08d}.started.json", canonical_json({
                            "schema": "si-parallel-count-request-start-v1", "query_ordinal": ordinal,
                            "request": query.to_payload()["request"], "request_sha256": query.to_payload()["request_sha256"],
                            "started_at": at, "plan_sha256": plan.sha256, "code_head": head,
                            "whole_page_bytes_reserved": parallel.MAXIMUM_RESPONSE_BYTES}).encode()))
                # A finite eight-name batch persists every debit BEFORE the
                # first worker invocation. No remote query per individual
                # response chunk or per started receipt is necessary.
                publish_batch(tuple(starts))
                for query, request, at in ready:
                    pending.append((query, pool.submit(worker, query, request, at)))
            except Exception:
                fatal = True
            # All submitted workers drain even if scheduling stopped. No retry.
            for query, future in pending:
                receipt, raw = future.result()
                gate.drain(query)
                ordinal = receipt["query_ordinal"]
                if raw is not None:
                    digest = hash_bytes(raw)  # Bounded key-echo checks already passed.
                    receipt.update(raw_path=f"query-{ordinal:08d}.raw", raw_sha256=digest, raw_bytes=len(raw))
                    charged += len(raw)
                    results.append((f"query-{ordinal:08d}.raw", raw))
                elif receipt["code"] == "material_request_refused":
                    charged += parallel.MAXIMUM_RESPONSE_BYTES
                    fatal = True
                results.append((f"query-{ordinal:08d}.received.json", canonical_json(receipt).encode()))
                receipts.append(receipt)
            try:
                if fatal:
                    gate._state["halted"] = True
                gate.close_HTTP_batch()
            except lane.LaneBatchRefusal:
                fatal = True
            if results:
                try:
                    publish_batch(tuple(results), drain=fatal)
                except lane.LaneBatchRefusal:
                    fatal = True
                    # Only if no result inode exists. Any exclusive partial
                    # prefix is immutable; never overwrite/retry a publication.
                    if all(not (directory / name).exists() for name, raw in results):
                        publish_batch(tuple(results), drain=True)
                    else:
                        raise parallel.ParallelCountRefusal("REFUSED: immutable_partial_publication_prefix") from None
    if fatal:
        if attempted != len(gate._state["started"]) or {r["query_ordinal"] for r in receipts} != gate._state["started"]:
            attempted = len(gate._state["started"])
            refused("started_debit_without_bound_receipt")
            raise parallel.ParallelCountRefusal("REFUSED: started_debit_without_bound_receipt") from None
        refused("started_prefix_drained_no_completed_source_capture")
        return parallel.seal_parallel_inventory(plan, tuple(receipts), started_at=began, completed_at=clock(), halted=True)
    _require(attempted == plan.to_payload()["maximum_attempts"] and next(queries, None) is None,
             "full_frozen_sequence_not_completed")
    ended = clock()
    inventory = parallel.seal_parallel_inventory(plan, tuple(receipts), started_at=began, completed_at=ended, halted=False)
    gate.completion_evidence()
    publish_batch((("inventory.private.json", canonical_json(inventory.to_payload()).encode()),
        ("completed.json", canonical_json({"schema": "si-cache-parallel-count-complete-v1", "completed_at": ended,
            "code_head": head, "protocol_sha256": PROTOCOL_SHA256, "inventory_sha256": inventory.sha256,
            "outcome_looks": 0, "qc_attempts": 0, "source_admitted": False, "backtest_result_exists": False}).encode())))
    return inventory
