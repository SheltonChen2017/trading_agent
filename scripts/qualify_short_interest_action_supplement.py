"""One committed, prospective Massive source supplement and private v2 binding.

No prices, returns, strategy evaluation or QC request. Only the specifically
named existing environment key is read; it is never printed or persisted.
The previous immutable Sharadar source capture is rebuilt, not re-requested.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import urllib.parse
import urllib.request

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.massive_action_supplement as supplement
import research.short_interest_etf.sharadar_companion_qualification as sharadar
from research.short_interest_etf.sharadar_actual_input_binding import bind_sharadar_companion
from scripts.qualify_finra_short_interest import (
    CapturePlatformRefusal, CaptureRefusal, _NoRedirect, _git,
    _prepare_capture_directory, _publish, _publish_json, _require_capture_platform,
)
from scripts.qualify_sharadar_companion import (
    SharadarCaptureRefusal, _guard, _http, _refuse_credential_echo,
)

CAPTURE_PARENT = Path("artifacts/short_interest/massive_action_supplement")
SHARADAR_SOURCE = Path("artifacts/short_interest/sharadar_companion_qualification/sharadar-companion-20261011T194406Z")
SHARADAR_CODE_HEAD = "71f0a62de1ecfa07e1c1f91bd34ec94361eb207a"
SHARADAR_REPORT_FILE_SHA256 = "4c0cb3fcb47a76a57214cf957daf89bc97186a514959ddf863427b8c04344663"
SHARADAR_START_FILE_SHA256 = "1ea19b65dfb1fd2bc5e65471ba9305dedc4680f703b8a2b926fa307a162be2f4"
MAXIMUM_BYTES = 2 * 1024 * 1024
MAXIMUM_REQUESTS = 62


class ActionSupplementCaptureRefusal(CaptureRefusal):
    def __init__(self, code: str, *, status: int | None = None):
        super().__init__(code)
        self.code = code
        self.http_status = status if type(status) is int and 100 <= status <= 599 else None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _run_id(started_at: str) -> str:
    return "massive-actions-" + _clock(started_at).strftime("%Y%m%dT%H%M%SZ")


def _clock(value) -> datetime:
    try:
        if type(value) is not str or not value.endswith("Z"):
            raise ValueError
        clock = datetime.fromisoformat(value[:-1] + "+00:00")
        if clock.tzinfo is None or clock.utcoffset().total_seconds() != 0:
            raise ValueError
    except (TypeError, ValueError, AttributeError):
        raise ActionSupplementCaptureRefusal("invalid_receipt_clock") from None
    return clock


def _existing_key() -> str:
    _require_capture_platform()
    # No environment dump, file search, new secret entry or fallback credential.
    key = os.environ.get("MASSIVE_API_KEY")
    if (type(key) is not str or not 16 <= len(key) <= 512
            or any(not 32 < ord(char) < 127 for char in key)):
        raise ActionSupplementCaptureRefusal("existing_massive_key_unavailable")
    return key


def _protected_bytes(path: Path, maximum: int) -> bytes:
    _require_capture_platform()
    if path.absolute() != path.resolve():
        raise ActionSupplementCaptureRefusal("source_symlink")
    parent = path.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700:
        raise ActionSupplementCaptureRefusal("source_directory_protection")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > maximum):
            raise ActionSupplementCaptureRefusal("source_file_protection")
        raw = handle.read(maximum + 1)
    if len(raw) > maximum:
        raise ActionSupplementCaptureRefusal("source_size_limit")
    return raw


def _pairs(items):
    result = {}
    for name, value in items:
        if name in result:
            raise ActionSupplementCaptureRefusal("source_duplicate_json_key")
        result[name] = value
    return result


def _constant(_):
    raise ActionSupplementCaptureRefusal("source_nonfinite_json")


def _parse_receipt(raw: bytes) -> dict:
    value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    if type(value) is not dict:
        raise ActionSupplementCaptureRefusal("source_receipt_shape")
    return value


def _receipt(path: Path) -> dict:
    return _parse_receipt(_protected_bytes(path, 65536))


def _rebuild_sharadar(root: Path):
    """Read only the named, already completed capture, with exact byte binding."""
    _require_capture_platform()
    directory = root / SHARADAR_SOURCE
    start_raw = _protected_bytes(directory / "started.json", 65536)
    if hash_bytes(start_raw) != SHARADAR_START_FILE_SHA256:
        raise ActionSupplementCaptureRefusal("source_start_hash_mismatch")
    # Parse exactly the bytes just hashed, not a second potentially changed read.
    start = _parse_receipt(start_raw)
    if (start.get("schema") != "si-sharadar-qualification-start-v1"
            or start.get("code_head") != SHARADAR_CODE_HEAD
            or start.get("protocol_sha256") != sharadar.PROTOCOL_SHA256):
        raise ActionSupplementCaptureRefusal("source_code_protocol_mismatch")
    previous_clock = _clock(start.get("started_at"))
    protocol = _receipt(directory / "protocol.json")
    if protocol != sharadar.qualification_protocol():
        raise ActionSupplementCaptureRefusal("source_protocol_mismatch")
    captures = []
    for ordinal, request_id in enumerate(sharadar.REQUEST_IDS, 1):
        prefix = f"attempt-{ordinal:02d}"
        started = _receipt(directory / (prefix + ".started.json"))
        received = _receipt(directory / (prefix + ".received.json"))
        raw_name = prefix + ".raw"
        raw = _protected_bytes(directory / raw_name, MAXIMUM_BYTES)
        digest = sharadar.request_sha256(request_id)
        if (started.get("schema") != "si-sharadar-request-start-v1"
                or received.get("schema") != "si-sharadar-response-receipt-v1"
                or type(started.get("attempt")) is not int or started["attempt"] != ordinal
                or started.get("request_id") != request_id
                or started.get("request_sha256") != digest
                or started.get("request") != sharadar.sharadar_request(request_id)
                or started.get("code_head") != SHARADAR_CODE_HEAD
                or started.get("protocol_sha256") != sharadar.PROTOCOL_SHA256
                or type(received.get("attempt")) is not int or received["attempt"] != ordinal
                or received.get("request_id") != request_id
                or received.get("request_sha256") != digest or received.get("raw_path") != raw_name
                or received.get("raw_sha256") != hash_bytes(raw)
                or type(received.get("raw_bytes")) is not int or received["raw_bytes"] != len(raw)):
            raise ActionSupplementCaptureRefusal("source_response_binding")
        request_clock, response_clock = _clock(started.get("started_at")), _clock(received.get("received_at"))
        if not previous_clock <= request_clock <= response_clock:
            raise ActionSupplementCaptureRefusal("source_receipt_chronology")
        previous_clock = response_clock
        captures.append(sharadar.CapturedSharadarResponse(
            request_id=request_id, request_sha256=digest, raw=raw,
            http_status=received.get("http_status"), content_type=received.get("content_type")))
    stored = _protected_bytes(directory / "qualification.private.json", 8 * MAXIMUM_BYTES)
    if hash_bytes(stored) != SHARADAR_REPORT_FILE_SHA256:
        raise ActionSupplementCaptureRefusal("source_report_hash_mismatch")
    # Read the known report only internally; no rows or fitness flags are emitted.
    saved = _parse_receipt(stored)
    if _clock(saved.get("retrieved_at")) < previous_clock:
        raise ActionSupplementCaptureRefusal("source_receipt_chronology")
    qualified = sharadar.qualify_sharadar_companion(tuple(captures), retrieved_at=saved["retrieved_at"])
    if (canonical_json(qualified.to_payload()) + "\n").encode() != stored:
        raise ActionSupplementCaptureRefusal("source_report_rebuild_mismatch")
    return qualified


def _validated_protocol() -> dict:
    value = supplement.supplement_protocol()
    if (type(value) is not dict or hash_payload(value) != supplement.PROTOCOL_SHA256
            or value.get("maximum_requests") != MAXIMUM_REQUESTS
            or tuple(value.get("request_ids", ())) != supplement.REQUEST_IDS
            or len(supplement.REQUEST_IDS) != MAXIMUM_REQUESTS
            or value.get("requests") != [supplement.massive_request(rid) for rid in supplement.REQUEST_IDS]):
        raise ActionSupplementCaptureRefusal("frozen_request_inventory")
    return value


def _claim_budget(directory: Path, *, expected_head: str, expected_remote: str, started_at: str) -> None:
    _require_capture_platform()
    # Scope is independent of invocation time and code HEAD: another directory
    # or commit cannot silently reopen this fixed source/protocol allowance.
    name = "budget-" + supplement.PROTOCOL_SHA256 + "-" + SHARADAR_REPORT_FILE_SHA256 + ".json"
    try:
        _publish_json(directory.parent, name, {
            "schema": "si-massive-action-whole-round-budget-v1", "run_id": directory.name,
            "started_at": started_at, "code_head": expected_head, "remote_head": expected_remote,
            "protocol_sha256": supplement.PROTOCOL_SHA256,
            "prior_sharadar_report_file_sha256": SHARADAR_REPORT_FILE_SHA256,
            "maximum_attempts": MAXIMUM_REQUESTS, "resumption_or_restart_allowed": False,
        })
    except (CaptureRefusal, FileExistsError):
        raise ActionSupplementCaptureRefusal("whole_round_budget_already_claimed") from None


def _capture(root: Path, directory: Path, key: str, opener, qualification, *, expected_head: str,
             expected_remote: str) -> dict:
    _require_capture_platform()
    protocol = _validated_protocol()
    captures = []
    for ordinal, request_id in enumerate(supplement.REQUEST_IDS, 1):
        _guard(root, expected_head, expected_remote)
        if ordinal > MAXIMUM_REQUESTS:
            raise ActionSupplementCaptureRefusal("request_budget")
        spec = supplement.massive_request(request_id)
        digest = supplement.request_sha256(request_id)
        if spec != protocol["requests"][ordinal - 1] or hash_payload(spec) != digest:
            raise ActionSupplementCaptureRefusal("request_binding")
        parsed = urllib.parse.urlsplit(spec["url"])
        if (spec["method"] != "GET" or parsed.scheme != "https" or parsed.netloc != "api.massive.com"
                or parsed.path not in {"/v3/reference/tickers", "/stocks/v1/dividends", "/stocks/v1/splits"}
                or parsed.query or parsed.fragment):
            raise ActionSupplementCaptureRefusal("request_origin")
        url = spec["url"] + "?" + urllib.parse.urlencode(spec["params"])
        request = urllib.request.Request(url, headers={"Accept": "application/json", "Authorization": "Bearer " + key}, method="GET")
        prefix = f"attempt-{ordinal:02d}"
        _publish_json(directory, prefix + ".started.json", {
            "schema": "si-massive-action-request-start-v1", "attempt": ordinal,
            "request_id": request_id, "request": spec, "request_sha256": digest,
            "protocol_sha256": supplement.PROTOCOL_SHA256,
            "code_head": expected_head, "started_at": _utc_now(),
        })
        status = None
        try:
            _guard(root, expected_head, expected_remote)
            raw, content_type, status = _http(opener, request, MAXIMUM_BYTES)
            _refuse_credential_echo(raw, content_type, key, status)
            _publish(directory, prefix + ".raw", raw)
            _publish_json(directory, prefix + ".received.json", {
                "schema": "si-massive-action-response-receipt-v1", "attempt": ordinal,
                "request_id": request_id, "request_sha256": digest, "http_status": status,
                "content_type": content_type, "raw_path": prefix + ".raw",
                "raw_bytes": len(raw), "raw_sha256": hash_bytes(raw), "received_at": _utc_now(),
            })
            item = supplement.CapturedMassiveActionResponse(
                request_id=request_id, request_sha256=digest, raw=raw,
                http_status=status, content_type=content_type)
            supplement.validate_massive_response(item)
            captures.append(item)
        except (CaptureRefusal, ValueError) as exc:
            code = exc.code if type(exc) is SharadarCaptureRefusal else "response_contract_or_guard_refused"
            observed = exc.http_status if type(exc) is SharadarCaptureRefusal else status
            _publish_json(directory, prefix + ".refused.json", {
                "schema": "si-massive-action-request-refusal-v1", "attempt": ordinal,
                "request_id": request_id, "code": code, "http_status": observed,
                "refused_at": _utc_now(),
            })
            raise ActionSupplementCaptureRefusal(code, status=observed) from None
    report = supplement.qualify_massive_action_supplement(tuple(captures), retrieved_at=_utc_now())
    _publish_json(directory, "supplement.private.json", report.to_payload())
    binding = bind_sharadar_companion(qualification, report)
    _publish_json(directory, "binding.private.json", binding.to_payload())
    _guard(root, expected_head, expected_remote)
    result = {
        "schema": "si-massive-action-capture-completion-v1", "status": "capture_complete",
        "code_head": expected_head, "protocol_sha256": supplement.PROTOCOL_SHA256,
        "http_attempts": len(captures), "private_report_sha256": report.sha256,
        "private_binding_sha256": binding.sha256, "completed_at": _utc_now(),
        "outcome_looks_consumed": 0, "qc_launch_attempts": 0, "backtest_result_exists": False,
    }
    _publish_json(directory, "completed.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-remote", required=True)
    args = parser.parse_args(argv)
    directory = None
    try:
        _require_capture_platform()
        root = Path.cwd().resolve()
        _guard(root, args.expected_head, args.expected_remote)
        protocol = _validated_protocol()
        started_at = _utc_now()
        run_id = _run_id(started_at)
        target = root / CAPTURE_PARENT / run_id
        if _git(root, "check-ignore", str(target)) != str(target):
            raise ActionSupplementCaptureRefusal("capture_not_ignored")
        qualification = _rebuild_sharadar(root)
        # A real existing source rebuild is useful even if new access refuses.
        binding = bind_sharadar_companion(qualification)
        key = _existing_key()
        directory = _prepare_capture_directory(target)
        _claim_budget(directory, expected_head=args.expected_head, expected_remote=args.expected_remote,
                      started_at=started_at)
        _publish_json(directory, "protocol.json", protocol)
        _publish_json(directory, "started.json", {
            "schema": "si-massive-action-capture-start-v1", "run_id": run_id,
            "started_at": started_at, "code_head": args.expected_head,
            "remote_head": args.expected_remote, "protocol_sha256": supplement.PROTOCOL_SHA256,
            "maximum_attempts": MAXIMUM_REQUESTS, "source_only": True,
            "prior_sharadar_report_file_sha256": SHARADAR_REPORT_FILE_SHA256,
            "outcome_looks_consumed": 0, "qc_launch_attempts": 0,
        })
        _publish_json(directory, "binding.before_supplement.private.json", binding.to_payload())
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        result = _capture(root, directory, key, opener, qualification,
                          expected_head=args.expected_head, expected_remote=args.expected_remote)
    except (CaptureRefusal, ValueError, OSError, UnicodeError, KeyError) as exc:
        # Never expose external errors, raw rows, account identifiers or secrets.
        safe = type(exc) in (CapturePlatformRefusal, ActionSupplementCaptureRefusal)
        code = exc.code if safe else "local_preflight_refused"
        status = exc.http_status if safe else None
        if directory is not None:
            _publish_json(directory, "refused.json", {
                "schema": "si-massive-action-capture-refusal-v1", "status": "capture_refused",
                "code": code, "http_status": status,
                "refused_at": _utc_now(), "outcome_looks_consumed": 0,
                "qc_launch_attempts": 0, "backtest_result_exists": False,
            })
        result = {"status": "capture_refused", "code": code, "http_status": status,
                  "backtest_result_exists": False}
        if type(exc) is CapturePlatformRefusal:
            result["ready_for_empirical_backtest"] = False
        print(json.dumps(result, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
