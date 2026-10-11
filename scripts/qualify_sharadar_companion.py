"""Capture one prospective direct-Sharadar companion qualification.

The bounded qualification is not an outcome join or backtest. Responses and
data-usability conclusions remain in protected ignored storage. Public output
contains capture status and digests only. Never upload these files to QC.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import urllib.error
import urllib.parse
import urllib.request

from data.hashing import hash_bytes, hash_payload
from research.short_interest_etf.sharadar_companion_qualification import (
    PROTOCOL_SHA256,
    REQUEST_IDS,
    CapturedSharadarResponse,
    qualification_protocol,
    qualify_sharadar_companion,
    request_sha256,
    sharadar_request,
    validate_sharadar_metadata,
    validate_sharadar_schema,
)
from scripts.qualify_finra_short_interest import (
    CaptureRefusal,
    _NoRedirect,
    _git,
    _guard_lane,
    _prepare_capture_directory,
    _publish,
    _publish_json,
)

CAPTURE_PARENT = Path("artifacts/short_interest/sharadar_companion_qualification")
CREDENTIAL_PATH = Path.home() / ".config" / "trading-agent" / "sharadar.env"
REMOTE_REF = "refs/heads/codex/strategy-short-interest"
MAX_ATTEMPTS = 16
MAXIMUM_BYTES = {"metadata": 65536, "schema": 131072, "rows": 2097152}


class SharadarCaptureRefusal(CaptureRefusal):
    """Safe fixed-code failure; never external exception text or row values."""

    def __init__(self, code: str, *, status: int | None = None):
        super().__init__(code)
        self.code = code
        self.http_status = status if type(status) is int and 100 <= status <= 599 else None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _validated_protocol() -> dict:
    protocol = qualification_protocol()
    if (type(protocol) is not dict or hash_payload(protocol) != PROTOCOL_SHA256
            or type(protocol.get("request_ids")) is not list
            or tuple(protocol["request_ids"]) != REQUEST_IDS
            or len(REQUEST_IDS) != MAX_ATTEMPTS
            or protocol.get("maximum_requests") != MAX_ATTEMPTS
            or type(protocol.get("requests")) is not list
            or len(protocol["requests"]) != MAX_ATTEMPTS):
        raise SharadarCaptureRefusal("request_inventory")
    return protocol


def _refuse_credential_echo(raw: bytes, content_type: str, key: str, status: int) -> None:
    if key.encode("utf-8") in raw or key in urllib.parse.unquote(content_type):
        raise SharadarCaptureRefusal("credential_echo", status=status)
    # Scan every JSON string token, including duplicate object keys, before
    # persistence. A byte-only check misses Unicode/slash-escaped key echoes.
    # This scan does not turn malformed JSON into an accepted response.
    try:
        decoded = raw.decode("utf-8")
        tokens = re.finditer(r'"(?:[^"\\\x00-\x1f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"', decoded)
        for token in tokens:
            if key in json.loads(token.group()):
                raise SharadarCaptureRefusal("credential_echo", status=status)
    except UnicodeError:
        raise SharadarCaptureRefusal("response_contract_refused", status=status) from None


def _read_key(path: Path) -> str:
    if path.absolute() != CREDENTIAL_PATH or path.resolve() != path.absolute():
        raise SharadarCaptureRefusal("credential_location_or_symlink")
    parent = path.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700:
        raise SharadarCaptureRefusal("credential_directory_protection")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "r", encoding="utf-8") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 4096:
            raise SharadarCaptureRefusal("credential_file_protection")
        values = {}
        for line in handle.read().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name, separator, value = line.partition("=")
            if separator != "=" or name.strip() != "SHARADAR_API_KEY" or values:
                raise SharadarCaptureRefusal("credential_fields")
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            if not value or len(value) > 512 or any(not 32 < ord(char) < 127 for char in value) or value == "test-api-key":
                raise SharadarCaptureRefusal("credential_value")
            values[name.strip()] = value
    if set(values) != {"SHARADAR_API_KEY"}:
        raise SharadarCaptureRefusal("credential_fields")
    return values["SHARADAR_API_KEY"]


def _guard_remote(root: Path, expected_remote: str) -> None:
    if re.fullmatch(r"[0-9a-f]{40}", expected_remote) is None:
        raise SharadarCaptureRefusal("invalid_expected_remote")
    observed = _git(root, "ls-remote", "origin", REMOTE_REF).split()
    if observed != [expected_remote, REMOTE_REF]:
        raise SharadarCaptureRefusal("remote_advanced_or_ambiguous")


def _guard(root: Path, expected_head: str, expected_remote: str) -> None:
    _guard_lane(root, expected_head)
    _guard_remote(root, expected_remote)


def _http(opener, request, maximum: int) -> tuple[bytes, str, int]:
    try:
        with opener.open(request, timeout=30) as response:
            status = response.status
            if type(status) is not int or status != 200:
                raise SharadarCaptureRefusal("http_not_200", status=status if type(status) is int else None)
            raw = response.read(maximum + 1)
            if len(raw) > maximum:
                raise SharadarCaptureRefusal("response_size_limit", status=status)
            content_type = response.headers.get("Content-Type", "")
            if type(content_type) is not str or len(content_type) > 256:
                raise SharadarCaptureRefusal("content_type", status=status)
            return raw, content_type, status
    except urllib.error.HTTPError as exc:
        # Do not read error bodies, Location, headers, URLs or exception text:
        # the response may echo a credential, and redirects are never followed.
        raise SharadarCaptureRefusal("http_not_200", status=exc.code) from None
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        raise SharadarCaptureRefusal("network_failure") from None


def _capture(root: Path, directory: Path, key: str, opener, *, expected_head: str,
             expected_remote: str) -> dict:
    protocol = _validated_protocol()
    ids = protocol["request_ids"]
    captures = []
    attempts = 0
    for request_id in ids:
        _guard(root, expected_head, expected_remote)
        if attempts >= MAX_ATTEMPTS:
            raise SharadarCaptureRefusal("attempt_budget")
        spec = sharadar_request(request_id)
        digest = request_sha256(request_id)
        if spec != protocol["requests"][attempts] or hash_payload(spec) != digest:
            raise SharadarCaptureRefusal("request_binding")
        kind = request_id.split("-", 1)[0]
        maximum = MAXIMUM_BYTES[kind]
        if spec["method"] != "GET" or not spec["url"].startswith("https://api.sharadar.com/v1.0/"):
            raise SharadarCaptureRefusal("request_origin")
        url = spec["url"] + "?" + urllib.parse.urlencode(spec["params"])
        # The key appears only in the header sent to this single HTTPS origin.
        # Public schema calls carry no authentication, no proxies or redirects.
        headers = {"Accept": "text/plain" if kind == "schema" else "application/json"}
        if kind != "schema":
            headers["x-api-key"] = key
        request = urllib.request.Request(url, headers=headers, method="GET")
        attempts += 1
        attempt_name = f"attempt-{attempts:02d}"
        _publish_json(directory, attempt_name + ".started.json", {
            "schema": "si-sharadar-request-start-v1", "attempt": attempts,
            "request_id": request_id, "request": spec,
            "request_sha256": digest, "protocol_sha256": PROTOCOL_SHA256,
            "code_head": expected_head, "started_at": _utc_now(),
        })
        status = None
        try:
            _guard(root, expected_head, expected_remote)
            raw, content_type, status = _http(opener, request, maximum)
            _refuse_credential_echo(raw, content_type, key, status)
            raw_name = attempt_name + ".raw"
            _publish(directory, raw_name, raw)
            capture = CapturedSharadarResponse(
                request_id=request_id, request_sha256=digest, raw=raw,
                content_type=content_type, http_status=status,
            )
            _publish_json(directory, attempt_name + ".received.json", {
                "schema": "si-sharadar-response-receipt-v1", "attempt": attempts,
                "request_id": request_id, "request_sha256": digest,
                "http_status": status, "content_type": content_type,
                "raw_path": raw_name, "raw_sha256": hash_bytes(raw),
                "raw_bytes": len(raw), "received_at": _utc_now(),
            })
            if kind == "metadata":
                validate_sharadar_metadata(capture, retrieved_at=_utc_now())
            elif kind == "schema":
                validate_sharadar_schema(capture)
            captures.append(capture)
        except SharadarCaptureRefusal as exc:
            _publish_json(directory, attempt_name + ".refused.json", {
                "schema": "si-sharadar-request-refusal-v1", "attempt": attempts,
                "request_id": request_id, "code": exc.code,
                "http_status": exc.http_status, "refused_at": _utc_now(),
            })
            raise
        except CaptureRefusal:
            _publish_json(directory, attempt_name + ".refused.json", {
                "schema": "si-sharadar-request-refusal-v1", "attempt": attempts,
                "request_id": request_id, "code": "lane_guard_refused",
                "http_status": status, "refused_at": _utc_now(),
            })
            raise
        except ValueError:
            # Exact private qualification errors are not public data-fitness
            # conclusions; preserve received bytes and a fixed safe refusal.
            _publish_json(directory, attempt_name + ".refused.json", {
                "schema": "si-sharadar-request-refusal-v1", "attempt": attempts,
                "request_id": request_id, "code": "response_contract_refused",
                "http_status": status, "refused_at": _utc_now(),
            })
            raise SharadarCaptureRefusal("response_contract_refused", status=status) from None
    report = qualify_sharadar_companion(
        tuple(captures), retrieved_at=_utc_now(), expected_protocol_sha256=PROTOCOL_SHA256,
    )
    payload = report.to_payload()
    _publish_json(directory, "qualification.private.json", payload)
    result = {
        "schema": "si-sharadar-capture-completion-v1",
        "status": "capture_complete", "protocol_sha256": PROTOCOL_SHA256,
        "code_head": expected_head, "http_attempts": attempts,
        "private_report_sha256": report.sha256, "completed_at": _utc_now(),
        "outcome_looks_consumed": 0, "qc_launch_attempts": 0,
        "backtest_result_exists": False,
    }
    _publish_json(directory, "completed.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credential-file", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-remote", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    root = Path.cwd().resolve()
    directory = None
    try:
        _guard(root, args.expected_head, args.expected_remote)
        if re.fullmatch(r"sharadar-companion-[0-9]{8}T[0-9]{6}Z", args.run_id) is None:
            raise SharadarCaptureRefusal("invalid_run_id")
        protocol = _validated_protocol()
        target = root / CAPTURE_PARENT / args.run_id
        if _git(root, "check-ignore", str(target)) != str(target):
            raise SharadarCaptureRefusal("capture_not_ignored")
        key = _read_key(args.credential_file)
        directory = _prepare_capture_directory(target)
        _publish_json(directory, "protocol.json", protocol)
        _publish_json(directory, "started.json", {
            "schema": "si-sharadar-qualification-start-v1",
            "run_id": args.run_id, "protocol_sha256": PROTOCOL_SHA256,
            "code_head": args.expected_head, "remote_head": args.expected_remote,
            "started_at": _utc_now(), "maximum_attempts": MAX_ATTEMPTS,
            "credential_protected": True, "source_only": True,
            "outcome_looks_consumed": 0, "qc_launch_attempts": 0,
        })
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        result = _capture(root, directory, key, opener,
                          expected_head=args.expected_head, expected_remote=args.expected_remote)
    except (CaptureRefusal, ValueError, OSError, UnicodeError) as exc:
        code = exc.code if type(exc) is SharadarCaptureRefusal else "local_preflight_refused"
        status = exc.http_status if type(exc) is SharadarCaptureRefusal else None
        if directory is not None:
            _publish_json(directory, "refused.json", {
                "schema": "si-sharadar-capture-refusal-v1", "status": "capture_refused",
                "code": code, "http_status": status, "refused_at": _utc_now(),
                "outcome_looks_consumed": 0, "qc_launch_attempts": 0,
            })
        print(json.dumps({"status": "capture_refused", "code": code,
                          "http_status": status, "backtest_result_exists": False}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
