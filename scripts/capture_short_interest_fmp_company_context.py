"""Ignored injected context/cap transport; no operational entrypoint.

Main must integrate independent protected source/code custody, pin the exact
selected plan and prospectively commit the budget before this can be used.
Both fixed documented routes use an apikey HEADER, never a secret URL.
"""
from __future__ import annotations

import ssl
import urllib.request
from urllib.request import Request

from data.hashing import hash_bytes, hash_payload
from scripts.qualify_finra_short_interest import CaptureRefusal, _NoRedirect, _require_capture_platform
from scripts.qualify_sharadar_companion import SharadarCaptureRefusal, _guard, _http, _utc_now
from scripts.short_interest_keychain import KeychainSecret, read_named_keychain
import research.short_interest_etf.fmp_company_context as contract

PROTOCOL_SHA256 = "PENDING"
SELECTED_PLAN_SHA256 = "PENDING"


class FmpContextCaptureError(CaptureRefusal):
    pass


def _require(value, reason):
    if not value:
        raise FmpContextCaptureError(reason)


def protocol():
    return {"schema": "si-fmp-company-context-runtime-draft-v1", "policy": contract.policy(),
            "selected_plan_sha256": SELECTED_PLAN_SHA256,
            "key": "existing_owner_named_fmp_login_Keychain_apikey_header_only",
            "proxy": False, "redirect": False, "automatic_retries": 0,
            "claim": "exclusive_global_exact_plan_before_key_no_reset_or_budget_repurpose",
            "guards": "protected_host_root_HEAD_actual_remote_source_code_protocol_before_each_attempt_hash_publication",
            "lookup_negative": "retain_negative_qualified_lookup_skip_cap_no_first_symbol_fallback",
            "failure": "safe_status_only_no_HTTP_error_body_headers_or_exception_text",
            "source_only": True, "outcome_looks": 0, "qc_attempts": 0}


def build_protected_opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def _require_protected_opener(opener):
    allowed = {urllib.request.HTTPHandler, urllib.request.HTTPSHandler,
               urllib.request.HTTPDefaultErrorHandler, urllib.request.UnknownHandler,
               urllib.request.FileHandler, urllib.request.FTPHandler, urllib.request.DataHandler,
               urllib.request.HTTPErrorProcessor, urllib.request.ProxyHandler, _NoRedirect}
    _require(type(opener) is urllib.request.OpenerDirector
        and any(type(handler) is _NoRedirect for handler in opener.handlers)
        and all(type(handler) in allowed for handler in opener.handlers)
        and all(not handler.proxies for handler in opener.handlers if type(handler) is urllib.request.ProxyHandler)
        and all(handler._debuglevel == 0 for handler in opener.handlers
                if type(handler) in {urllib.request.HTTPHandler, urllib.request.HTTPSHandler})
        and all((handler._context is None or (type(handler._context) is ssl.SSLContext
            and handler._context.verify_mode == ssl.CERT_REQUIRED and handler._context.check_hostname is True))
            and getattr(handler, "_check_hostname", None) in {None, True}
            for handler in opener.handlers if type(handler) is urllib.request.HTTPSHandler),
        "protected_no_proxy_no_redirect_opener_required")


def capture_with_seams(root, directory, plan, opener, *, head, remote, started_at,
                       verify_sources, verify_code, claim_budget, publish, publish_json,
                       read_secret=read_named_keychain, clock=_utc_now):
    """Source/custody verifiers raise on unresolved facts; booleans ignored."""
    def guard():
        _require_capture_platform()
        _guard(root, head, remote)
        _require(type(plan) is contract.ContextPlan and plan.sha256 == SELECTED_PLAN_SHA256
                 and hash_payload(protocol()) == PROTOCOL_SHA256,
                 "prospective_context_plan_or_protocol_pending_or_changed")
        verify_sources(plan)
        verify_code()
    guard()
    _require_protected_opener(opener)
    previous = contract._utc(started_at)
    budget = plan.to_payload()
    claim_budget({"schema": "si-fmp-company-context-budget-draft-v1", "plan_sha256": plan.sha256,
        "protocol_sha256": PROTOCOL_SHA256, "maximum_requests": budget["maximum_requests"],
        "maximum_total_bytes": budget["maximum_total_bytes"], "maximum_rows": budget["maximum_rows"],
        "started_at": started_at})
    attempts, total_bytes, total_rows, reports = 0, 0, 0, []

    def store(name, value, *, raw=False):
        guard()
        (publish if raw else publish_json)(directory, name, value)

    try:
        guard()
        secret = read_secret("fmp")
        _require(type(secret) is KeychainSecret, "redacted_named_FMP_secret_required")
    except Exception:
        failed = clock()
        _require(previous <= contract._utc(failed), "key_failure_clock_chronology")
        store("key.refused.private.json", {"schema": "si-fmp-context-key-refusal-v1",
            "http_attempts": 0, "code": "named_FMP_key_unavailable", "refused_at": failed})
        raise FmpContextCaptureError("named_FMP_key_unavailable") from None

    for ordinal, ticket in enumerate(plan.tickets(), 1):
        context = None
        for stage in ("lookup", "cap"):
            if stage == "cap" and context.to_payload()["selected_row_index"] is None:
                store(f"target-{ordinal:06d}.cap.skipped.json", {
                    "schema": "si-fmp-cap-skipped-v1", "code": "request_target_company_unresolved",
                    "ticket_sha256": ticket.sha256, "lookup_report_sha256": context.sha256,
                    "http_attempted": False, "unused_budget_repurposed": False})
                reports.append({"ticket_sha256": ticket.sha256, "cap_status": "skipped_unresolved_context"})
                continue
            guard()
            maximum = contract.MAXIMUM_LOOKUP_BYTES if stage == "lookup" else contract.cap.MAXIMUM_RESPONSE_BYTES
            rows_maximum = contract.MAXIMUM_LOOKUP_ROWS if stage == "lookup" else contract.cap.LIMIT
            _require(attempts < budget["maximum_requests"]
                     and budget["maximum_total_bytes"] - total_bytes >= maximum
                     and budget["maximum_rows"] - total_rows >= rows_maximum,
                     "whole_page_budget_reservation")
            descriptor = contract.request_descriptor(ticket, stage)
            url = contract.clean_url(ticket, stage)
            _require(not secret.echoed_in(url.encode()), "credential_in_clean_descriptor")
            digest = hash_payload(descriptor)
            began = clock()
            _require(previous <= contract._utc(began), "request_start_chronology")
            attempts += 1
            prefix = f"target-{ordinal:06d}.{stage}"
            store(prefix + ".started.json", {"schema": "si-fmp-context-request-start-v1",
                "attempt": attempts, "request": descriptor, "request_sha256": digest,
                "started_at": began, "code_head": head, "protocol_sha256": PROTOCOL_SHA256})
            status = None
            body_observed, raw_retained = False, False
            try:
                guard()
                request = Request(url, method="GET", headers={"Accept": "application/json",
                    "apikey": secret.for_authorization_header()})
                raw, media, status = _http(opener, request, maximum)
                body_observed = True
                _require(type(raw) is bytes and len(raw) <= maximum and type(media) is str and len(media) <= 256
                         and type(status) is int and status == 200, "bounded_successful_JSON_response_required")
                _require(not secret.echoed_in(raw) and not secret.echoed_in(media.encode()), "credential_echo_refused")
                received = clock()
                _require(contract._utc(began) <= contract._utc(received), "response_receipt_chronology")
                guard()
                if stage == "lookup":
                    contract.preflight_lookup_scope(raw)
                else:
                    contract.cap.preflight_scope(raw)
                raw_sha = hash_bytes(raw)
                kwargs = {"raw": raw, "raw_sha256": raw_sha, "request_sha256": digest,
                          "started_at": began, "received_at": received,
                          "http_status": status, "content_type": media}
                result = (contract.qualify_context(ticket, **kwargs) if stage == "lookup" else
                          contract.qualify_company_cap(context, **kwargs))
                encoded = result.to_bytes()
                store(prefix + ".raw", raw, raw=True)
                raw_retained = True
                store(prefix + ".received.json", {"schema": "si-fmp-context-response-v1", "attempt": attempts,
                    "raw_path": prefix + ".raw", "raw_sha256": raw_sha, "raw_bytes": len(raw),
                    "request_sha256": digest, "received_at": received, "http_status": status, "content_type": media})
                store(prefix + ".qualified.private.json", encoded, raw=True)
                total_bytes += len(raw)
                total_rows += len(result.to_payload()["rows"])
                previous = contract._utc(received)
                if stage == "lookup":
                    context = result
                else:
                    reports.append({"ticket_sha256": ticket.sha256, "context_sha256": context.sha256,
                        "cap_sha256": result.sha256, "cap_path": prefix + ".qualified.private.json",
                        "cap_status": "source_candidate_only"})
            except Exception as exc:
                failed = clock()
                _require(contract._utc(began) <= contract._utc(failed), "request_refusal_chronology")
                # Never invoke attributes/descriptors on an unknown exception;
                # even its diagnostic properties can contain credential text.
                observed_status = exc.http_status if type(exc) is SharadarCaptureRefusal else status
                store(prefix + ".refused.json", {"schema": "si-fmp-context-request-refusal-v1",
                    "attempt": attempts, "request_sha256": digest, "refused_at": failed,
                    "http_status": observed_status if type(observed_status) is int and 100 <= observed_status <= 599 else None,
                    "body_observed": body_observed, "error_body_read": False,
                    "raw_path": prefix + ".raw" if raw_retained else None,
                    "code": "source_request_refused_no_retry"})
                raise FmpContextCaptureError("source_request_refused_no_retry") from None
    finished = clock()
    _require(previous <= contract._utc(finished), "capture_completion_chronology")
    value = {"schema": "si-fmp-company-context-inventory-draft-v1", "plan_sha256": plan.sha256,
        "protocol_sha256": PROTOCOL_SHA256, "started_at": started_at, "completed_at": finished,
        "http_attempts": attempts, "raw_bytes": total_bytes, "decoded_rows": total_rows,
        "reports": reports, "frozen_sequence_complete": True, "unused_budget_repurposed": False,
        "source_admitted": False, "historical_identity_admitted": False, "market_cap_admitted": False,
        "outcome_looks": 0, "qc_attempts": 0, "ready_for_empirical_backtest": False}
    store("inventory.private.json", value)
    return value


def main():
    raise FmpContextCaptureError("ignored_draft_has_no_operational_entrypoint")
