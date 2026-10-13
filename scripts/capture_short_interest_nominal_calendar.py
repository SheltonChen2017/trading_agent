"""Capture five frozen public nominal-calendar PDFs; no data or credentials.

Capture completion is not visual transcription completion. Old calendar grids
require rendered-page verification before any nominal date binding. This
capture cannot qualify FINRA vintage availability or launch a backtest.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import urllib.request

from data.hashing import hash_bytes, hash_payload
import research.short_interest_etf.nominal_publication_calendar as calendar
from scripts.qualify_finra_short_interest import (
    CapturePlatformRefusal, CaptureRefusal, _NoRedirect, _git,
    _prepare_capture_directory, _publish, _publish_json, _require_capture_platform,
)
from scripts.qualify_sharadar_companion import _guard, _http, _utc_now
from scripts.qualify_short_interest_action_supplement import _clock

PARENT = Path("artifacts/short_interest/nominal_publication_calendar")
CODE_FILES = (
    "data/hashing.py", "ml/immutable_io.py",
    "research/short_interest_etf/contracts.py",
    "research/short_interest_etf/nominal_publication_calendar.py",
    "scripts/qualify_finra_short_interest.py", "scripts/qualify_sharadar_companion.py",
    "scripts/qualify_short_interest_action_supplement.py",
    "scripts/capture_short_interest_nominal_calendar.py",
)


class NominalCalendarCaptureRefusal(CaptureRefusal):
    """Only fixed safe failure codes leave this runtime."""


def _require(condition, reason):
    if not condition:
        raise NominalCalendarCaptureRefusal(reason)


def protocol():
    return {"schema": "si-nominal-calendar-capture-protocol-v1",
            "source_protocol_sha256": calendar.PROTOCOL_SHA256,
            "source_protocol": calendar.calendar_protocol(), "parent": str(PARENT),
            "code_files": list(CODE_FILES),
            "maximum_attempts": 5, "retries": 0, "restart_or_resume": False,
            "authentication": "none_no_environment_Keychain_or_credential_reads",
            "transport": "fixed5_https_GET_no_proxy_redirect_or_pagination",
            "post_capture": "separate_digest_bound_render_visual_transcription_required",
            "publication": "protected_exclusive_ignored_raw_and_receipts",
            "calendar_only": True, "credential_reads": 0, "market_row_requests": 0,
            "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False}


PROTOCOL_SHA256 = "2008466397d0eb1e49fdb72105e2de9459c59d38ca054bd776ccff371255170f"


def _checked_protocol():
    value = protocol()
    _require(hash_payload(value) == PROTOCOL_SHA256, "calendar_capture_protocol_pending_or_changed")
    _require(calendar.MAXIMUM_REQUESTS == 5 and len(calendar.REQUEST_IDS) == 5,
             "calendar_capture_fixed5_inventory")
    return value


def capture_pdfs(root, directory, opener, *, head, remote, started_at):
    _require_capture_platform()
    frozen = _checked_protocol()
    previous, captures, receipts = _clock(started_at), [], []

    def publish(name, payload, raw=False):
        _guard(root, head, remote)
        (_publish if raw else _publish_json)(directory, name, payload)

    for ordinal, request_id in enumerate(calendar.REQUEST_IDS, 1):
        _require(_checked_protocol() == frozen, "calendar_capture_scope_changed")
        spec = calendar.calendar_request(request_id)
        _require(spec == frozen["source_protocol"]["requests"][ordinal - 1]
                 and ordinal <= 5, "calendar_capture_request_binding")
        digest = hash_payload(spec)
        began = _utc_now()
        _require(previous <= _clock(began), "calendar_request_chronology")
        prefix = f"request-{ordinal:02d}"
        publish(prefix + ".started.json", {"schema": "si-nominal-calendar-request-start-v1",
                "ordinal": ordinal, "request": spec, "request_sha256": digest,
                "protocol_sha256": PROTOCOL_SHA256, "code_head": head, "started_at": began})
        status = None
        try:
            _guard(root, head, remote)
            request = urllib.request.Request(spec["url"], method="GET", headers={"Accept": "application/pdf"})
            raw, media, status = _http(opener, request, calendar.MAXIMUM_RESPONSE_BYTES)
            _require(type(raw) is bytes and len(raw) <= calendar.MAXIMUM_RESPONSE_BYTES
                     and type(media) is str and len(media) <= 256, "calendar_response_size_or_type")
            received = _utc_now()
            _require(_clock(began) <= _clock(received), "calendar_response_chronology")
            publish(prefix + ".raw.pdf", raw, raw=True)
            receipt = {"schema": "si-nominal-calendar-response-receipt-v1", "ordinal": ordinal,
                       "request_id": request_id, "request_sha256": digest, "http_status": status,
                       "content_type": media, "raw_path": prefix + ".raw.pdf",
                       "raw_sha256": hash_bytes(raw), "raw_bytes": len(raw), "received_at": received,
                       "error_body_read": False}
            publish(prefix + ".received.json", receipt)
            capture = calendar.CapturedNominalCalendarPDF(request_id, digest, raw, media, status, received)
            captures.append(capture)
            receipts.append(receipt)
            previous = _clock(received)
        except (CaptureRefusal, ValueError, TypeError, OSError, KeyError) as error:
            status = status if type(status) is int else getattr(error, "http_status", None)
            publish(prefix + ".refused.json", {"schema": "si-nominal-calendar-request-refusal-v1",
                    "ordinal": ordinal, "request_id": request_id, "request_sha256": digest,
                    "http_status": status, "error_body_read": False,
                    "code": "calendar_request_or_response_refused", "refused_at": _utc_now()})
            raise
    retrieved = _utc_now()
    _require(previous <= _clock(retrieved), "calendar_inventory_chronology")
    _require(_checked_protocol() == frozen and len(captures) == 5, "calendar_capture_final_inventory")
    inventory = {"schema": "si-nominal-calendar-source-inventory-v1", "protocol_sha256": PROTOCOL_SHA256,
                 "source_protocol_sha256": calendar.PROTOCOL_SHA256, "code_head": head,
                 "retrieved_at": retrieved, "captures": receipts, "http_attempts": 5,
                 "capture_complete": True, "visual_transcriptions_pending": True,
                 "nominal_schedule_qualified": False, "historical_FINRA_calendar_admitted": False,
                 "availability_clock_admitted": False, "credential_reads": 0, "market_row_requests": 0,
                 "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False}
    inventory["inventory_sha256"] = hash_payload(inventory)
    publish("inventory.private.json", inventory)
    completed = _utc_now()
    _require(_clock(retrieved) <= _clock(completed), "calendar_completion_chronology")
    result = {"schema": "si-nominal-calendar-capture-complete-v1", "status": "calendar_PDF_capture_complete",
              "protocol_sha256": PROTOCOL_SHA256, "inventory_sha256": inventory["inventory_sha256"],
              "code_head": head, "http_attempts": 5, "capture_path": str(directory.relative_to(root)),
              "completed_at": completed, "visual_transcriptions_pending": True,
              "credential_reads": 0, "market_row_requests": 0, "outcome_looks": 0,
              "qc_attempts": 0, "backtest_result_exists": False}
    publish("completed.json", result)
    return result


def run(root, *, head, remote):
    _require_capture_platform()
    _guard(root, head, remote)
    frozen = _checked_protocol()
    began = _utc_now()
    target = root / PARENT / ("nominal-calendar-" + _clock(began).strftime("%Y%m%dT%H%M%SZ"))
    _require(_git(root, "check-ignore", str(target)) == str(target), "calendar_capture_not_ignored")
    _guard(root, head, remote)
    directory = _prepare_capture_directory(target)

    def publish(owner, name, payload):
        _guard(root, head, remote)
        _publish_json(owner, name, payload)

    try:
        publish(directory.parent, "budget-" + PROTOCOL_SHA256 + ".json", {
            "schema": "si-nominal-calendar-budget-v1", "protocol_sha256": PROTOCOL_SHA256,
            "code_head": head, "remote_head": remote, "run_id": directory.name,
            "maximum_attempts": 5, "started_at": began, "restart_or_resume": False})
        publish(directory, "protocol.json", frozen)
        files = []
        for name in CODE_FILES:
            _guard(root, head, remote)
            files.append({"path": name, "sha256": hash_bytes((root / name).read_bytes())})
        publish(directory, "started.json", {"schema": "si-nominal-calendar-start-v1",
                "code_head": head, "remote_head": remote, "code_files": files,
                "code_identity_sha256": hash_payload({"git_commit": head, "files": files}),
                "protocol_sha256": PROTOCOL_SHA256, "started_at": began, "maximum_attempts": 5,
                "credential_reads": 0, "market_row_requests": 0, "outcome_looks": 0, "qc_attempts": 0})
        _guard(root, head, remote)
        _require(_checked_protocol() == frozen, "calendar_capture_scope_changed")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        return capture_pdfs(root, directory, opener, head=head, remote=remote, started_at=began)
    except (CaptureRefusal, ValueError, TypeError, OSError, KeyError):
        publish(directory, "refused.json", {"schema": "si-nominal-calendar-capture-refusal-v1",
                "status": "calendar_PDF_capture_refused", "refused_at": _utc_now(),
                "credential_reads": 0, "market_row_requests": 0, "outcome_looks": 0,
                "qc_attempts": 0, "backtest_result_exists": False})
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-remote", required=True)
    args = parser.parse_args(argv)
    try:
        result = run(Path.cwd().resolve(), head=args.expected_head, remote=args.expected_remote)
    except (CaptureRefusal, ValueError, TypeError, OSError, KeyError) as error:
        result = {"status": "calendar_PDF_capture_refused", "code": "calendar_capture_refused",
                  "credential_reads": 0, "market_row_requests": 0, "outcome_looks": 0,
                  "qc_attempts": 0, "backtest_result_exists": False}
        if type(error) is CapturePlatformRefusal:
            result["code"] = error.code
        print(json.dumps(result, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
