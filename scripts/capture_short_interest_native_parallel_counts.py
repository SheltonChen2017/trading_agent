"""Ignored prospective eight-inflight source transport; no operational CLI.

Main freezes pins and supplies protected exclusive custody/publication seams.
Every started ordinal is reserved, persisted and drained once; raw data and
credentials never enter public diagnostics. Receipts retain real worker times.
"""
from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import threading
import urllib.request
from urllib.parse import urlencode

from data.hashing import hash_bytes, hash_payload
from scripts.qualify_finra_short_interest import CaptureRefusal, _require_capture_platform
from scripts.qualify_sharadar_companion import _guard, _http, _utc_now, SharadarCaptureRefusal
from scripts.short_interest_keychain import KeychainSecret, read_named_keychain
from scripts.capture_short_interest_native_grouped_market import build_protected_opener, _opener
import research.short_interest_etf.native_parallel_count_contract as contract

PLAN_SHA256 = "PENDING"
PROTOCOL_SHA256 = "PENDING"


def protocol():
    return {"schema": "si-parallel-count-transport-draft-v1", "plan_sha256": PLAN_SHA256,
            "qualification_policy": contract.policy(), "authentication": "named_existing_Massive_Bearer_memory_only",
            "source_guards": "frozen_code_original_custody_exact_HEAD_and_actual_remote_before_HTTP_and_publication",
            "budget_claim": "one_exclusive_plan_and_source_policy_claim_before_key_no_restart",
            "no_proxies": True, "no_redirects": True, "automatic_retries": 0,
            "receipt_ownership": "main_thread_protected_create_exclusive_all_attempts_including_drained_inflight",
            "receipt_replay": "ordinal_order_no_monotone_receipt_time_requirement",
            "source_only": True, "outcome_looks": 0, "qc_attempts": 0}


def validated(plan):
    contract.require(type(plan) is contract.ParallelCountPlan and plan.sha256 == PLAN_SHA256
                     and plan.to_payload()["policy_sha256"] == hash_payload(contract.policy())
                     and hash_payload(protocol()) == PROTOCOL_SHA256, "parallel_prospective_pin_pending_or_changed")


def capture_with_seams(root, directory, plan, *, head, remote, started_at,
                       verify_sources, verify_code, claim_budget, publish, publish_json,
                       read_secret=read_named_keychain, clock=_utc_now):
    _require_capture_platform()
    budget = plan.to_payload()
    start = contract.clock(started_at)
    fatal = threading.Event()
    receipts, pending = {}, {}
    attempted, charged_bytes, reserved = 0, 0, 0

    def guard():
        validated(plan)
        _guard(root, head, remote)
        verify_code(plan)
        verify_sources(plan)

    def store(name, value, raw=False):
        guard()
        (publish if raw else publish_json)(directory, name, value)

    guard()
    claim_budget({"schema": "si-parallel-count-spent-claim-draft-v1", "plan_sha256": plan.sha256,
                  "protocol_sha256": PROTOCOL_SHA256, "started_at": started_at,
                  "maximum_attempts": budget["maximum_attempts"], "maximum_inflight": contract.MAXIMUM_INFLIGHT,
                  "maximum_total_response_bytes": budget["maximum_total_response_bytes"], "restart_allowed": False})
    try:
        guard()
        secret = read_secret("massive")
        contract.require(type(secret) is KeychainSecret, "redacted_existing_Massive_key_required")
    except Exception:
        ended = clock()
        contract.require(start <= contract.clock(ended), "key_refusal_chronology")
        store("run.refused.json", {"schema": "si-parallel-count-preflight-refused-v1", "code": "key_or_guard_unavailable_after_claim",
                                  "started_at": started_at, "refused_at": ended, "attempts_started": 0, "http_invocations": 0})
        raise contract.ParallelCountRefusal("REFUSED: key_or_guard_unavailable_after_claim") from None

    def worker(query, began):
        ordinal = query.to_payload()["query_ordinal"]
        status, invoked, raw, media, body, code = None, False, None, None, False, "material_request_refused"
        try:
            guard()
            ticket = query.to_payload()
            request_spec = ticket["request"]
            opener = build_protected_opener()
            _opener(opener)
            request = urllib.request.Request(request_spec["url"] + "?" + urlencode(request_spec["params"]), method="GET",
                headers={"Accept": "application/json", "Authorization": "Bearer " + secret.for_authorization_header()})
            invoked = True
            raw, media, status = _http(opener, request, contract.MAXIMUM_RESPONSE_BYTES)
            contract.require(type(raw) is bytes and len(raw) <= contract.MAXIMUM_RESPONSE_BYTES
                             and type(media) is str and len(media) <= 256 and type(status) is int and status == 200,
                             "bounded_successful_class_response_required")
            contract.require(not secret.echoed_in(raw) and not secret.echoed_in(media.encode()), "secret_echo_refused")
            body, code = True, "received"
        except SharadarCaptureRefusal as error:
            status = error.http_status
            raw, media = None, None
            if status == 404:
                code = "HTTP_404_body_unobserved"
            else:
                fatal.set()
        except Exception:
            raw, media = None, None
            fatal.set()
        received = clock()
        if contract.clock(received) < contract.clock(began):
            fatal.set()
            raw, media, body, code = None, None, False, "material_request_refused"
        return ordinal, {"query_ordinal": ordinal, "request_sha256": query.to_payload()["request_sha256"],
              "started_at": began, "received_at": received, "http_attempted": invoked,
              "http_status": status, "body_observed": body, "raw_path": None, "raw_sha256": None,
              "raw_bytes": None, "content_type": media if body else None, "code": code}, raw

    queries = iter(plan._queries.iter_queries())
    exhausted, previous_start = False, start
    terminal_error = None
    with ThreadPoolExecutor(max_workers=contract.MAXIMUM_INFLIGHT) as pool:
        while pending or not exhausted:
            while not fatal.is_set() and not exhausted and len(pending) < contract.MAXIMUM_INFLIGHT:
                guard()
                if fatal.is_set():
                    break
                if attempted == budget["maximum_attempts"]:
                    contract.require(next(queries, None) is None, "extra_unplanned_query_ticket")
                    exhausted = True
                    break
                if budget["maximum_total_response_bytes"] - charged_bytes - reserved < contract.MAXIMUM_RESPONSE_BYTES:
                    if not pending:
                        fatal.set()
                    break
                try:
                    query = next(queries)
                except StopIteration:
                    exhausted = True
                    break
                ticket = query.to_payload()
                contract.require(ticket["query_ordinal"] == attempted + 1, "planned_ticket_order_changed")
                began = clock()
                contract.require(previous_start <= contract.clock(began), "planned_start_clock_backdated")
                previous_start = contract.clock(began)
                attempted += 1
                reserved += contract.MAXIMUM_RESPONSE_BYTES
                prefix = f"query-{attempted:08d}"
                store(prefix + ".started.json", {"schema": "si-parallel-count-request-start-v1",
                    "query_ordinal": attempted, "request": ticket["request"], "request_sha256": ticket["request_sha256"],
                    "started_at": began, "plan_sha256": plan.sha256, "code_head": head,
                    "whole_page_bytes_reserved": contract.MAXIMUM_RESPONSE_BYTES})
                pending[pool.submit(worker, query, began)] = attempted
            if not pending:
                break
            completed, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
            for future in sorted(completed, key=lambda value: pending[value]):
                ordinal = pending.pop(future)
                reserved -= contract.MAXIMUM_RESPONSE_BYTES
                try:
                    got, receipt, raw = future.result()
                    contract.require(got == ordinal, "worker_ordinal_changed")
                    guard()
                    if raw is not None:
                        # Secret checks happened in worker before hashes or I/O.
                        digest = hash_bytes(raw)
                        store(f"query-{ordinal:08d}.raw", raw, raw=True)
                        receipt.update(raw_path=f"query-{ordinal:08d}.raw", raw_sha256=digest, raw_bytes=len(raw))
                        charged_bytes += len(raw)
                    elif receipt["code"] == "material_request_refused":
                        # A rejected/unknown-size body spends its full reserved
                        # ceiling; it is not released into a fresh request budget.
                        charged_bytes += contract.MAXIMUM_RESPONSE_BYTES
                    store(f"query-{ordinal:08d}.received.json", receipt)
                    receipts[ordinal] = receipt
                except Exception:
                    fatal.set()
                    terminal_error = "guarded_result_publication_or_clock_failed_after_drain"
            if fatal.is_set():
                exhausted = True  # Existing futures still drain; no new schedule.
    contract.require(not pending and reserved == 0, "started_requests_not_drained")
    if terminal_error is not None:
        raise contract.ParallelCountRefusal("REFUSED: " + terminal_error)
    ended = clock()
    inventory = contract.seal_parallel_inventory(plan, tuple(receipts.values()), started_at=started_at,
                                                 completed_at=ended, halted=fatal.is_set())
    guard()
    store("inventory.private.json", inventory.to_payload())
    return inventory


def main():
    raise contract.ParallelCountRefusal("REFUSED: ignored_parallel_draft_has_no_operational_entrypoint")
