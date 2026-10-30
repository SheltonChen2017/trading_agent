"""Ignored injected draft: one protected grouped raw-bar GET/XNYS session.

No operational CLI and PENDING prospective pins. Calendar facts are public
metadata; source bytes/currency/identity/processing qualification and research
look registration are separate, and this capture derives no signal/outcome.
"""
from __future__ import annotations

from datetime import date
from importlib.metadata import version
from pathlib import Path
import ssl
import urllib.request
from urllib.parse import urlencode

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts.qualify_finra_short_interest import CaptureRefusal, _NoRedirect, _require_capture_platform
from scripts.qualify_sharadar_companion import _guard, _http, _utc_now
from scripts.short_interest_keychain import KeychainSecret, read_named_keychain
from scripts.short_interest_keychain import ShortInterestKeychainError
from scripts.continue_short_interest_native_identity import failure_metadata
import research.short_interest_etf.native_grouped_market_source as contract

PROTOCOL_SHA256 = "PENDING"
PLAN_SHA256 = "PENDING"
CALENDAR_SHA256 = "PENDING"


class GroupedCaptureError(CaptureRefusal):
    pass


def _require(value, code):
    if not value:
        raise GroupedCaptureError(code)


def shared_calendar_source():
    """Only established local calendar code; no market data or provider call."""
    from data.exchange_calendar import _schedule
    schedule = _schedule(date.fromisoformat(contract.FROM), date.fromisoformat(contract.TO))
    rows = []
    for index, row in schedule.iterrows():
        rows.append({"session": index.date().isoformat(), "XNYS_open_UTC": row["market_open"].isoformat(),
                     "XNYS_close_UTC": row["market_close"].isoformat()})
    value = {"schema": "si-grouped-market-XNYS-calendar-draft-v1", "from": contract.FROM, "to": contract.TO,
             "source": "data.exchange_calendar._schedule", "library": "pandas_market_calendars",
             "library_version": version("pandas_market_calendars"), "sessions": rows}
    return canonical_json(value).encode()


def freeze_shared_calendar_plan():
    import json
    raw = shared_calendar_source()
    source = json.loads(raw)
    return contract.freeze_grouped_session_plan(tuple(row["session"] for row in source["sessions"]),
                                               calendar_sha256=hash_bytes(raw))


def protocol():
    return {"schema": "si-grouped-market-capture-draft-protocol-v1", "policy": contract.policy(),
            "plan_sha256": PLAN_SHA256, "calendar_sha256": CALENDAR_SHA256,
            "authentication": "named_existing_Massive_secret_Bearer_header_memory_only",
            "storage": "protected_exclusive_ignored_raw_and_one_private_report_per_session",
            "claim": "global_exact_plan_exclusive_before_key_no_restart_or_remaining_budget_repurpose",
            "proxies": False, "redirects": False, "automatic_retries": 0,
            "failures": "retain_bounded_nonsecret_successful_body_before_shape_refusal_fixed_receipt_first_failure_halts_no_retry",
            "protected_date_scope": "recognizable_window_t_outside_query_day_boundaries_refused_before_body_hash_or_persistence",
            "source_only": True, "outcome_looks": 0, "qc_attempts": 0}


def build_protected_opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def _opener(opener):
    allowed = {urllib.request.HTTPHandler, urllib.request.HTTPSHandler, urllib.request.HTTPDefaultErrorHandler,
               urllib.request.UnknownHandler, urllib.request.FileHandler, urllib.request.FTPHandler,
               urllib.request.DataHandler, urllib.request.HTTPErrorProcessor, urllib.request.ProxyHandler, _NoRedirect}
    _require(type(opener) is urllib.request.OpenerDirector and any(type(h) is _NoRedirect for h in opener.handlers)
             and all(type(h) in allowed for h in opener.handlers)
             and all(not h.proxies for h in opener.handlers if type(h) is urllib.request.ProxyHandler)
             and all(h._debuglevel == 0 for h in opener.handlers if type(h) in {urllib.request.HTTPHandler, urllib.request.HTTPSHandler})
             and all((h._context is None or (type(h._context) is ssl.SSLContext
                    and h._context.verify_mode == ssl.CERT_REQUIRED and h._context.check_hostname is True))
                    and getattr(h, "_check_hostname", None) in {None, True}
                    for h in opener.handlers if type(h) is urllib.request.HTTPSHandler), "protected_transport_required")


def _validated(plan):
    _require(type(plan) is contract.GroupedSessionPlan and plan.sha256 == PLAN_SHA256
             and plan.to_payload()["calendar_sha256"] == CALENDAR_SHA256
             and hash_payload(protocol()) == PROTOCOL_SHA256, "prospective_grouped_protocol_or_plan_pending_or_changed")


def capture_with_seams(root, directory, plan, opener, *, head, remote, started_at,
                       verify_calendar, claim_budget, publish, publish_json,
                       read_secret=read_named_keychain, clock=_utc_now):
    """Injected skeleton; main must integrate custody and protected exclusive I/O."""
    _require_capture_platform()
    _guard(root, head, remote)
    _validated(plan)
    _opener(opener)
    verify_calendar(plan)  # Must reconstruct exact frozen shared calendar, not a caller flag.
    previous = contract._clock(started_at)
    budget = plan.to_payload()
    claim_budget({"schema": "si-grouped-market-budget-claim-draft-v1", "plan_sha256": plan.sha256,
                  "protocol_sha256": PROTOCOL_SHA256, "maximum_requests": len(plan.sessions()), "started_at": started_at})
    attempts, raw_bytes, row_count, manifests = 0, 0, 0, []

    def store(name, value, raw=False):
        _guard(root, head, remote)
        # A failed frozen-scope check cannot authorize source publication or
        # completion. Its fixed refusal may still document the spent claim.
        if name != "refused.json" and not name.endswith(".refused.json"):
            _validated(plan)
        (publish if raw else publish_json)(directory, name, value)

    store("protocol.private.json", protocol())
    store("started.json", {"schema": "si-grouped-market-start-v1", "protocol_sha256": PROTOCOL_SHA256,
          "plan_sha256": plan.sha256, "code_head": head, "started_at": started_at,
          "outcome_looks": 0, "qc_attempts": 0})
    try:
        _guard(root, head, remote)
        _validated(plan)
        secret = read_secret("massive")
        _require(type(secret) is KeychainSecret, "redacted_Massive_secret_required")
        _validated(plan)
    except (CaptureRefusal, ShortInterestKeychainError, ValueError, TypeError, OSError) as error:
        failed = clock()
        _require(previous <= contract._clock(failed), "key_refusal_chronology")
        category, status = failure_metadata(error)
        store("refused.json", {"schema": "si-grouped-market-refused-v1", "http_attempts": 0,
              "failure_category": category, "http_status": status, "refused_at": failed,
              "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False})
        raise GroupedCaptureError("grouped_key_refused_zero_HTTP_no_retry") from None

    for ordinal, at in enumerate(plan.sessions(), 1):
        _validated(plan)
        _require(attempts < budget["request_count"]
                 and budget["maximum_total_bytes"] - raw_bytes >= contract.MAXIMUM_RESPONSE_BYTES
                 and budget["maximum_rows"] - row_count >= contract.MAXIMUM_ROWS, "whole_page_budget_reservation")
        descriptor = contract.request_descriptor(plan, ordinal)
        digest, began = hash_payload(descriptor), clock()
        _require(previous <= contract._clock(began), "request_start_chronology")
        attempts += 1
        prefix = f"session-{ordinal:04d}"
        store(prefix + ".started.json", {"schema": "si-grouped-market-request-start-v1", "attempt": attempts,
              "request": descriptor, "request_sha256": digest, "protocol_sha256": PROTOCOL_SHA256,
              "code_head": head, "started_at": began})
        status, observed_receipt = None, None
        try:
            _guard(root, head, remote)
            url = descriptor["url"] + "?" + urlencode(descriptor["params"])
            request = urllib.request.Request(url, method="GET", headers={"Accept": "application/json",
                      "Authorization": "Bearer " + secret.for_authorization_header()})
            raw, media, status = _http(opener, request, contract.MAXIMUM_RESPONSE_BYTES)
            _require(type(raw) is bytes and len(raw) <= contract.MAXIMUM_RESPONSE_BYTES and type(media) is str
                     and len(media) <= 256 and type(status) is int and status == 200, "bounded_successful_response_required")
            _require(not secret.echoed_in(raw) and not secret.echoed_in(media.encode()), "credential_echo_refused")
            received = clock()
            _require(contract._clock(began) <= contract._clock(received), "response_receipt_chronology")
            observed_receipt = contract._clock(received)
            contract.guard_recognizable_window_dates(plan, ordinal, raw)
            # Shape/ticker metadata inspection is not source admission. Raw t
            # remains the provider window-end field, never a fabricated price
            # observation clock or a protected-period availability assertion.
            raw_digest = hash_bytes(raw)
            store(prefix + ".raw", raw, raw=True)
            store(prefix + ".received.json", {"schema": "si-grouped-market-received-v1", "query_session": at,
                  "request_sha256": digest, "raw_path": prefix + ".raw", "raw_sha256": raw_digest,
                  "raw_bytes": len(raw), "http_status": status, "content_type": media, "received_at": received})
            # Failed shape/count/pagination results remain private raw source
            # evidence, without following an advertised URL or admitting rows.
            envelope = contract._decode(raw)
            result = contract.qualify_grouped_response(plan, ordinal, raw=raw, raw_sha256=raw_digest,
                    request_sha256=digest, started_at=began, received_at=received,
                    http_status=status, content_type=media)
            report = result.to_bytes()
            store(prefix + ".qualified.private.json", report, raw=True)
            manifests.append({"session": at, "report_path": prefix + ".qualified.private.json",
                              "report_sha256": hash_bytes(report), "received_at": received})
            raw_bytes += len(raw)
            row_count += len(envelope["results"])
            previous = contract._clock(received)
            del raw, envelope, result, report
        except (CaptureRefusal, contract.GroupedMarketError, ValueError, TypeError, OSError) as error:
            failed = clock()
            _require(max(contract._clock(began), observed_receipt or contract._clock(began))
                     <= contract._clock(failed), "failure_receipt_chronology")
            category, observed_status = failure_metadata(error, status)
            store(prefix + ".refused.json", {"schema": "si-grouped-market-request-refused-v1", "attempt": attempts,
                  "query_session": at, "http_status": observed_status, "failure_category": category,
                  "code": "grouped_request_refused_no_retry", "refused_at": failed})
            raise GroupedCaptureError("grouped_request_refused_no_retry") from None
    done = clock()
    _require(previous <= contract._clock(done), "capture_completion_chronology")
    _validated(plan)
    value = {"schema": "si-grouped-market-inventory-draft-v1", "plan_sha256": plan.sha256,
             "protocol_sha256": PROTOCOL_SHA256, "started_at": started_at, "completed_at": done,
             "http_attempts": attempts, "raw_bytes": raw_bytes, "decoded_rows": row_count, "reports": manifests,
             "complete_frozen_request_sequence": True, "source_admitted": False, "price_volume_admitted": False,
             "historical_identity_admitted": False, "USD_currency_admitted": False,
             "outcome_looks": 0, "qc_attempts": 0, "ready_for_empirical_backtest": False}
    store("inventory.private.json", value)
    return value


def main():
    raise GroupedCaptureError("ignored_draft_has_no_operational_entrypoint")
