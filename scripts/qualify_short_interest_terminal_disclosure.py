"""Capture one prospectively pinned, private four-request filing pilot.

The class capture is reconstructed first. Its exact issuer assertions select
two fixed disclosure windows, never current-symbol fallback or outcome-based
selection. No parsed phrase becomes payment economics or backtest authority.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import urllib.parse
import urllib.request

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.massive_class_denominator as classes
import research.short_interest_etf.terminal_disclosure_evidence as disclosures
import scripts.qualify_short_interest_class_denominator as class_reader
from scripts.qualify_finra_short_interest import (
    CapturePlatformRefusal, CaptureRefusal, _NoRedirect, _git,
    _prepare_capture_directory, _publish, _publish_json, _require_capture_platform,
)
from scripts.qualify_sharadar_companion import (
    SharadarCaptureRefusal, _guard, _http, _refuse_credential_echo, _utc_now,
)
from scripts.qualify_short_interest_action_supplement import (
    _clock, _existing_key, _parse_receipt, _protected_bytes,
)

# Pin only after the actual preceding source-only capture. PENDING is a
# refusal, not permission to find the newest capture or infer a source hash.
CLASS_SOURCE = Path("artifacts/short_interest/massive_class_denominator/PENDING")
CLASS_HEAD = "PENDING"
CLASS_REPORT_BYTES_SHA256 = "PENDING"
CLASS_REPORT_SHA256 = "PENDING"
DISCLOSURE_PROTOCOL_SHA256 = "PENDING"
CAPTURE_PARENT = Path("artifacts/short_interest/terminal_disclosure")
MAXIMUM_REQUESTS = 4
MAXIMUM_BYTES = 4 * 1024 * 1024


class TerminalDisclosureCaptureRefusal(CaptureRefusal):
    def __init__(self, code: str, *, status=None):
        super().__init__(code)
        self.code = code
        self.http_status = status if type(status) is int and 100 <= status <= 599 else None


def _require(condition, reason):
    if not condition:
        raise TerminalDisclosureCaptureRefusal(reason)


def _source(root: Path) -> dict:
    """Rebuild all exact class responses, including status-only missing cells."""
    _require_capture_platform()
    _require("PENDING" not in str(CLASS_SOURCE) and len(CLASS_HEAD) == 40
             and all(len(value) == 64 for value in
                     (CLASS_REPORT_BYTES_SHA256, CLASS_REPORT_SHA256)), "source_freeze_pending")
    directory = root / CLASS_SOURCE
    protocol = _parse_receipt(_protected_bytes(directory / "protocol.json", 131072))
    _require(canonical_json(protocol) == canonical_json(class_reader.capture_protocol()),
             "class_source_protocol")
    start = _parse_receipt(_protected_bytes(directory / "started.json", 65536))
    end = _parse_receipt(_protected_bytes(directory / "completed.json", 65536))
    _require(start.get("schema") == "si-massive-class-capture-start-v1"
             and start.get("code_head") == CLASS_HEAD
             and start.get("run_id") == directory.name
             and start.get("code_identity_sha256") == class_reader._code_identity(root, CLASS_HEAD)
             and start.get("source_pins") == class_reader._source_pins()
             and start.get("capture_protocol_sha256") == hash_payload(protocol)
             and end.get("schema") == "si-massive-class-capture-completion-v1"
             and end.get("status") == "capture_complete"
             and end.get("code_head") == CLASS_HEAD
             and end.get("private_report_sha256") == CLASS_REPORT_SHA256
             and end.get("private_report_bytes_sha256") == CLASS_REPORT_BYTES_SHA256,
             "class_source_receipts")
    for receipt in (start, end):
        _require(receipt.get("source_only") is True
                 and type(receipt.get("outcome_looks")) is int and receipt["outcome_looks"] == 0
                 and type(receipt.get("qc_attempts")) is int and receipt["qc_attempts"] == 0,
                 "class_source_closed_counters")
    claim = _parse_receipt(_protected_bytes(directory.parent / class_reader._budget_name(), 65536))
    _require(canonical_json(claim) == canonical_json({
        "schema": "si-massive-class-whole-round-budget-v1", "run_id": directory.name,
        "started_at": start.get("started_at"), "code_head": CLASS_HEAD,
        "remote_head": start.get("remote_head"),
        "qualification_protocol_sha256": classes.PROTOCOL_SHA256,
        "source_pins": class_reader._source_pins(), "maximum_attempts": 30,
        "resumption_or_restart_allowed": False}), "class_source_consumed_budget")
    previous = _clock(start.get("started_at"))
    inventory = {"protocol.json", "started.json", "completed.json", "qualification.private.json"}
    captures = []
    for ordinal, request_id in enumerate(classes.REQUEST_IDS, 1):
        prefix = f"attempt-{ordinal:02d}"
        began = _parse_receipt(_protected_bytes(directory / (prefix + ".started.json"), 65536))
        received = _parse_receipt(_protected_bytes(directory / (prefix + ".received.json"), 65536))
        digest = classes.request_sha256(request_id)
        _require(canonical_json(began) == canonical_json({
            "schema": "si-massive-class-request-start-v1", "attempt": ordinal,
            "request_id": request_id, "request": classes.massive_request(request_id),
            "request_sha256": digest, "qualification_protocol_sha256": classes.PROTOCOL_SHA256,
            "code_head": CLASS_HEAD, "started_at": began.get("started_at")}),
            "class_source_request")
        observed = received.get("body_observed")
        _require(type(observed) is bool, "class_source_body_observation")
        raw = (_protected_bytes(directory / (prefix + ".raw"), class_reader.MAXIMUM_BYTES)
               if observed else b"")
        _require(canonical_json(received) == canonical_json({
            "schema": "si-massive-class-response-receipt-v1", "attempt": ordinal,
            "request_id": request_id, "request_sha256": digest,
            "http_status": received.get("http_status"),
            "content_type": received.get("content_type") if observed else None,
            "body_observed": observed, "error_body_read": False,
            "raw_path": prefix + ".raw" if observed else None,
            "raw_bytes": len(raw) if observed else None,
            "raw_sha256": hash_bytes(raw) if observed else None,
            "received_at": received.get("received_at")}), "class_source_response")
        request_at, received_at = _clock(began["started_at"]), _clock(received["received_at"])
        _require(previous <= request_at <= received_at, "class_source_chronology")
        previous = received_at
        inventory.update((prefix + ".started.json", prefix + ".received.json"))
        if observed:
            inventory.add(prefix + ".raw")
        captures.append(classes.CapturedMassiveClassResponse(
            request_id, digest, raw, received["received_at"], hash_bytes(raw),
            received["http_status"], received["content_type"] if observed else "", observed))
    _require({item.name for item in directory.iterdir()} == inventory, "class_source_inventory")
    raw = _protected_bytes(directory / "qualification.private.json", 64 * 1024 * 1024)
    _require(hash_bytes(raw) == CLASS_REPORT_BYTES_SHA256, "class_source_report_bytes")
    saved = _parse_receipt(raw)
    _require(previous <= _clock(saved.get("retrieved_at")) <= _clock(end.get("completed_at")),
             "class_source_completion_chronology")
    report = classes.qualify_massive_class_denominator(tuple(captures), retrieved_at=saved["retrieved_at"])
    _require(report.sha256 == CLASS_REPORT_SHA256 and report.to_bytes() == raw, "class_source_rebuild")
    return report.to_payload()


def _protocol(source: dict):
    ciks = []
    for ticker, _, _ in disclosures.WINDOWS:
        candidates = {row["normalized"]["cik"].zfill(10) for row in source["responses"]
                      if row["status"] in {"present", "incomplete"}
                      and row["normalized"] is not None
                      and row["normalized"].get("ticker") == ticker
                      and row["normalized"].get("cik") is not None}
        _require(len(candidates) == 1, "issuer_assertion_missing_or_ambiguous")
        ciks.append(next(iter(candidates)))
    return disclosures.freeze_disclosure_protocol(tuple(ciks), source_class_report_sha256=CLASS_REPORT_SHA256)


def _capture(root, directory, protocol, key, opener, *, head, remote, started_at=None):
    _require_capture_platform()
    captures = []
    previous = _clock(started_at)
    for ordinal, request_id in enumerate(disclosures.REQUEST_IDS, 1):
        _guard(root, head, remote)
        spec = protocol.request(request_id)
        digest = protocol.request_sha256(request_id)
        parsed = urllib.parse.urlsplit(spec["url"])
        _require(spec["method"] == "GET" and parsed.scheme == "https"
                 and parsed.netloc == "api.massive.com" and not parsed.query and not parsed.fragment
                 and parsed.path in {"/stocks/filings/vX/index", "/stocks/filings/8-K/vX/text"}
                 and hash_payload(spec) == digest and ordinal <= MAXIMUM_REQUESTS,
                 "fixed_disclosure_request")
        prefix = f"attempt-{ordinal:02d}"
        started_at = _utc_now()
        _require(previous is None or previous <= _clock(started_at), "capture_clock_reversed")
        _publish_json(directory, prefix + ".started.json", {
            "schema": "si-terminal-disclosure-request-start-v1", "attempt": ordinal,
            "request_id": request_id, "request": spec, "request_sha256": digest,
            "code_head": head, "protocol_sha256": protocol.sha256, "started_at": started_at})
        request = urllib.request.Request(spec["url"] + "?" + urllib.parse.urlencode(spec["params"]),
            headers={"Accept": "application/json", "Authorization": "Bearer " + key}, method="GET")
        try:
            _guard(root, head, remote)
            raw, media, status = _http(opener, request, MAXIMUM_BYTES)
            _refuse_credential_echo(raw, media, key, status)
            received_at = _utc_now()
            _require(_clock(started_at) <= _clock(received_at), "capture_clock_reversed")
            _guard(root, head, remote)
            _publish(directory, prefix + ".raw", raw)
            _publish_json(directory, prefix + ".received.json", {
                "schema": "si-terminal-disclosure-response-v1", "attempt": ordinal,
                "request_id": request_id, "request_sha256": digest,
                "http_status": status, "content_type": media, "raw_path": prefix + ".raw",
                "raw_sha256": hash_bytes(raw), "raw_bytes": len(raw), "received_at": received_at})
            captured = disclosures.CapturedDisclosureResponse(request_id, digest, raw, received_at, status, media)
            disclosures.validate_disclosure_response(protocol, captured)
            captures.append(captured)
            previous = _clock(received_at)
        except (CaptureRefusal, ValueError, TypeError, OSError):
            _guard(root, head, remote)
            _publish_json(directory, prefix + ".refused.json", {
                "schema": "si-terminal-disclosure-request-refusal-v1", "attempt": ordinal,
                "request_id": request_id, "code": "request_or_transport_refused",
                "refused_at": _utc_now()})
            raise
    retrieved_at = _utc_now()
    _require(previous <= _clock(retrieved_at), "capture_clock_reversed")
    report = disclosures.qualify_terminal_disclosure(protocol, tuple(captures), retrieved_at=retrieved_at)
    _guard(root, head, remote)
    _publish_json(directory, "evidence.private.json", report.to_payload())
    completed_at = _utc_now()
    _require(_clock(retrieved_at) <= _clock(completed_at), "capture_clock_reversed")
    result = {"schema": "si-terminal-disclosure-completion-v1", "status": "capture_complete",
              "code_head": head, "protocol_sha256": protocol.sha256, "http_attempts": len(captures),
              "private_report_sha256": report.sha256, "completed_at": completed_at,
              "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False}
    _guard(root, head, remote)
    _publish_json(directory, "completed.json", result)
    return result


def _run(root, *, head, remote):
    _require_capture_platform()
    _guard(root, head, remote)
    source = _source(root)
    protocol = _protocol(source)
    _require(protocol.sha256 == DISCLOSURE_PROTOCOL_SHA256, "disclosure_freeze_pending_or_changed")
    started_at = _utc_now()
    _require(_clock(source.get("retrieved_at")) <= _clock(started_at), "capture_clock_reversed")
    target = root / CAPTURE_PARENT / ("terminal-disclosure-" + _clock(started_at).strftime("%Y%m%dT%H%M%SZ"))
    _require(_git(root, "check-ignore", str(target)) == str(target), "capture_not_ignored")
    key = _existing_key()
    _guard(root, head, remote)
    directory = _prepare_capture_directory(target)
    try:
        _publish_json(directory.parent, "budget-" + protocol.sha256 + ".json", {
            "schema": "si-terminal-disclosure-budget-v1", "code_head": head, "remote_head": remote,
            "run_id": directory.name, "protocol_sha256": protocol.sha256, "maximum_attempts": 4,
            "started_at": started_at, "resumption_or_restart_allowed": False})
        _guard(root, head, remote)
        _publish_json(directory, "protocol.private.json", protocol.to_payload())
        code_files = class_reader._CODE_FILES + (
            "research/short_interest_etf/terminal_disclosure_evidence.py",
            "scripts/qualify_short_interest_terminal_disclosure.py")
        code_identity = hash_payload({"git_commit": head, "files": [
            {"path": name, "sha256": hash_bytes((root / name).read_bytes())} for name in code_files]})
        _publish_json(directory, "started.json", {
            "schema": "si-terminal-disclosure-start-v1", "code_head": head, "remote_head": remote,
            "code_identity_sha256": code_identity, "protocol_sha256": protocol.sha256,
            "source_class_report_sha256": CLASS_REPORT_SHA256, "started_at": started_at,
            "maximum_attempts": 4, "outcome_looks": 0, "qc_attempts": 0})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        return _capture(root, directory, protocol, key, opener, head=head, remote=remote, started_at=started_at)
    except (CaptureRefusal, ValueError, TypeError, OSError, KeyError, UnicodeError):
        _guard(root, head, remote)
        _publish_json(directory, "refused.json", {
            "schema": "si-terminal-disclosure-refusal-v1", "status": "capture_refused",
            "code": "owned_disclosure_capture_refused", "refused_at": _utc_now(),
            "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False})
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-remote", required=True)
    args = parser.parse_args(argv)
    try:
        _require_capture_platform()
        result = _run(Path.cwd().resolve(), head=args.expected_head, remote=args.expected_remote)
    except (CaptureRefusal, ValueError, TypeError, OSError, KeyError, UnicodeError) as exc:
        safe = type(exc) in (TerminalDisclosureCaptureRefusal, CapturePlatformRefusal, SharadarCaptureRefusal)
        result = {"status": "capture_refused", "code": exc.code if safe else "local_preflight_refused",
                  "http_status": exc.http_status if safe else None,
                  "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False}
        print(json.dumps(result, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
