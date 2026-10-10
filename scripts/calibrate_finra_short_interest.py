"""Capture the frozen, outcome-free FINRA historical/symbology calibration.

One shared source-POST allowance covers every panel and pagination attempt.
This latest-revised diagnostic admits neither symbol aliases nor PIT sources,
and is not an empirical runner. Credentials and tokens never enter artifacts.
"""
from __future__ import annotations

import argparse
import base64
from collections.abc import Callable
from decimal import Decimal
import re
from pathlib import Path
import urllib.error
import urllib.request

from data.hashing import canonical_json, hash_bytes
from research.short_interest_etf import finra_source_calibration as calibration
from scripts.qualify_finra_short_interest import (
    BRANCH, DATA_URL, FIELDS, METADATA_URL, TOKEN_URL, CaptureRefusal,
    _decode, _git, _guard_lane, _integer_header, _NoRedirect,
    _prepare_capture_directory, _publish, _publish_json, _read_credentials,
    _request, _utc_now, _validate_metadata,
)

PROTOCOL_SHA256 = calibration.PROTOCOL_SHA256
CAPTURE_PARENT = Path("artifacts/short_interest/finra_source_calibration")
TRANSPORT_HEADERS = (
    "Record-Total", "Record-Offset", "Record-Limit", "Record-Max-Limit",
    "Total-Records-On-Page", "Data-Version",
)


class _SourceHTTPRefusal(CaptureRefusal):
    """Refuse a source response while retaining only its numeric HTTP status."""

    def __init__(self, status: int):
        if type(status) is not int or not 100 <= status <= 599:
            raise CaptureRefusal("source_http_status_invalid")
        super().__init__("source_http_not_200")
        self.status = status


def _source_request(opener, request, maximum: int):
    """Bound a 200 response or a verified, genuinely empty 204 response.

    A 204 is a zero-record transport observation only, not fabricated JSON
    rows or evidence of source/coverage/alias admission. Other responses refuse.
    """
    with opener.open(request, timeout=30) as response:
        status = response.status
        if type(status) is not int or not 100 <= status <= 599:
            raise CaptureRefusal("source_http_status_invalid")
        if status != 200:
            if status != 204:
                raise _SourceHTTPRefusal(status)
            try:
                zero_contract = (
                    _integer_header(response.headers, "Record-Total") == 0
                    and _integer_header(response.headers, "Record-Offset") == 0
                    and _integer_header(response.headers, "Record-Limit") == 100
                    and _integer_header(response.headers, "Record-Max-Limit") >= 100
                    and response.headers.get("Data-Version") == "1"
                    and (response.headers.get("Total-Records-On-Page") is None
                         or _integer_header(response.headers, "Total-Records-On-Page") == 0)
                )
            except CaptureRefusal:
                raise _SourceHTTPRefusal(status) from None
            if not zero_contract:
                raise _SourceHTTPRefusal(status)
        raw = response.read(maximum + 1)
        if status == 204 and raw != b"":
            raise _SourceHTTPRefusal(status)
        if len(raw) > maximum:
            raise CaptureRefusal("response_size_limit")
        return raw, response.headers, status


def _budget(value: int) -> int:
    if type(value) is not int or not 1 <= value <= 8:
        raise CaptureRefusal("invalid_source_request_budget")
    return value


def _capture(directory: Path, credentials: tuple[str, str], opener, *,
             source_request_budget: int = 8,
             before_data_request: Callable[[], None] | None = None):
    """Capture once; every attempted source request has a prior durable receipt.

    The CLI supplies a fresh lane guard immediately before every source POST.
    The injectable callback also permits fabricated-only transport tests.
    There is no retry, per-panel counter reset, or resume of an existing run.
    """
    source_request_budget = _budget(source_request_budget)
    if any(directory.glob("attempt-*-start.json")):
        raise CaptureRefusal("capture_already_started")
    protocol = calibration.calibration_protocol()
    if tuple(protocol["requested_fields"]) != FIELDS:
        raise CaptureRefusal("request_field_drift")
    queries = protocol["queries"]

    basic = base64.b64encode((credentials[0] + ":" + credentials[1]).encode()).decode()
    token_raw, _ = _request(opener, urllib.request.Request(
        TOKEN_URL, data=b"", method="POST",
        headers={"Authorization": "Basic " + basic, "Accept": "application/json"}), 65536)
    token_result = _decode(token_raw)
    if not isinstance(token_result, dict):
        raise CaptureRefusal("token_schema")
    token = token_result.get("access_token")
    if not isinstance(token, str) or not token or any(char in token for char in ("\r", "\n")) or str(token_result.get("token_type", "")).lower() != "bearer":
        raise CaptureRefusal("token_schema")
    expires = Decimal(str(token_result.get("expires_in", "0")))
    if not expires.is_finite() or expires < 600:
        raise CaptureRefusal("token_lifetime")
    # Never publish the token response, credentials or Authorization headers.
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json", "Data-Version": "1"}
    metadata_raw, metadata_headers = _request(opener, urllib.request.Request(METADATA_URL, headers=headers), 1048576)
    _validate_metadata(_decode(metadata_raw), metadata_headers)
    _publish(directory, "production_metadata.json", metadata_raw)
    _publish_json(directory, "metadata-transport.json", {
        "http_status": 200, "data_version": metadata_headers.get("Data-Version"),
        "response_raw_sha256": hash_bytes(metadata_raw),
    })

    pages, receipts = [], []
    source_requests = 0
    for query in queries:
        query_id = query["query_id"]
        offset, total, seen = 0, None, set()
        for page_number in range(2):
            body = calibration.calibration_request(query_id, offset)
            request_raw = canonical_json(body).encode()
            request_sha = hash_bytes(request_raw)
            request = urllib.request.Request(DATA_URL, data=request_raw, method="POST",
                                             headers={**headers, "Content-Type": "application/json"})
            if source_requests >= source_request_budget:
                raise CaptureRefusal("source_request_budget_exhausted")
            source_requests += 1
            started = _utc_now()
            attempt = f"attempt-{source_requests:02d}"
            _publish(directory, attempt + "-request.json", request_raw)
            _publish_json(directory, attempt + "-start.json", {
                "source_request_number": source_requests, "query_id": query_id,
                "offset": offset, "page_number": page_number,
                "request_sha256": request_sha, "request_started_utc": started,
                "maximum_source_requests": source_request_budget,
                "scope": "outcome_free_latest_revised_finra_calibration",
            })
            # A receipt exists even if the guard or HTTP fails. Failed attempts
            # consume the same whole-round allowance, and are never retried.
            if before_data_request is not None:
                before_data_request()
            try:
                raw, response_headers, http_status = _source_request(opener, request, 1048576)
            except Exception as error:
                failure = {"source_request_number": source_requests, "query_id": query_id,
                           "offset": offset, "request_sha256": request_sha,
                           "response_completed_utc": _utc_now(), "error_type": type(error).__name__,
                           "response_body_withheld": True}
                if isinstance(error, urllib.error.HTTPError):
                    failure["http_status"] = error.code
                elif isinstance(error, _SourceHTTPRefusal):
                    failure["http_status"] = error.status
                _publish_json(directory, attempt + "-failure.json", failure)
                raise
            completed = _utc_now()
            name = f"{query_id}-page-{page_number:02d}.json"
            _publish(directory, name, raw)
            # Whitelist transport evidence before any page refusal; never copy
            # arbitrary provider headers or externally supplied exception text.
            pagination_headers = {name: response_headers.get(name) for name in TRANSPORT_HEADERS}
            _publish_json(directory, attempt + "-transport.json", {
                "source_request_number": source_requests, "query_id": query_id,
                "request_sha256": request_sha, "response_raw_sha256": hash_bytes(raw),
                "request_started_utc": started, "response_completed_utc": completed,
                "http_status": http_status, "pagination_headers": pagination_headers,
            })
            rows = [] if http_status == 204 else _decode(raw)
            if not isinstance(rows, list):
                raise CaptureRefusal("pagination_contract")
            count = len(rows)
            page_count_origin = "verified_empty_204_transport" if http_status == 204 else "exact_json_array_length"
            if response_headers.get("Total-Records-On-Page") is not None:
                if _integer_header(response_headers, "Total-Records-On-Page") != count:
                    raise CaptureRefusal("pagination_contract")
                if http_status == 200:
                    page_count_origin = "header_verified_against_exact_json_array_length"
            found = _integer_header(response_headers, "Record-Total")
            reported_offset = _integer_header(response_headers, "Record-Offset")
            limit = _integer_header(response_headers, "Record-Limit")
            maximum = _integer_header(response_headers, "Record-Max-Limit")
            if count > 100 or limit != 100 or maximum < limit or reported_offset != offset or found > 200 or found < offset + count or response_headers.get("Data-Version") != "1":
                raise CaptureRefusal("pagination_contract")
            for row in rows:
                if isinstance(row, dict) and (
                    isinstance(row.get("settlementDate"), str) and row["settlementDate"] != query["settlement_date"]
                    or isinstance(row.get("symbolCode"), str) and row["symbolCode"] not in query["raw_symbols"]
                ):
                    raise CaptureRefusal("response_query_mismatch")
            if total is not None and found != total:
                raise CaptureRefusal("pagination_total_changed")
            total = found
            digest = hash_bytes(raw)
            if digest in seen or (count == 0 and offset < total):
                raise CaptureRefusal("pagination_no_progress")
            seen.add(digest)
            pages.append(calibration.CapturedFinraCalibrationPage(
                query_id=query_id, offset=offset, total=total, limit=limit,
                max_limit=maximum, data_version="1", request_sha256=request_sha, raw=raw,
                http_status=http_status))
            receipts.append({
                "file": name, "raw_sha256": digest, "request_sha256": request_sha,
                "source_request_number": source_requests, "query_id": query_id,
                "request_started_utc": started, "response_completed_utc": completed,
                "settlement_date": query["settlement_date"], "offset": offset,
                "records": count, "total": total, "data_version": "1",
                "http_status": http_status, "page_count_origin": page_count_origin,
            })
            offset += count
            if offset == total:
                break
        else:
            raise CaptureRefusal("pagination_page_bound")
    return tuple(pages), receipts, hash_bytes(metadata_raw), source_requests


def _code_hashes() -> dict[str, str]:
    return {
        "capture_script": hash_bytes(Path(__file__).read_bytes()),
        "pure_calibration_module": hash_bytes(Path(calibration.__file__).read_bytes()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-frozen-protocol", action="store_true", required=True)
    parser.add_argument("--expected-worktree", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-protocol-sha256", required=True)
    parser.add_argument("--credential-file", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-request-budget", type=int, default=8,
                        help="remaining shared whole-round source POST allowance, one through eight")
    args = parser.parse_args(argv)
    directory = None
    stage = "preflight"
    try:
        root = args.expected_worktree.absolute()
        _guard_lane(root, args.expected_head)
        if args.expected_protocol_sha256 != PROTOCOL_SHA256:
            raise CaptureRefusal("protocol_hash_mismatch")
        if re.fullmatch(r"finra-calibration-[0-9]{8}T[0-9]{6}Z", args.run_id) is None:
            raise CaptureRefusal("invalid_run_id")
        _budget(args.source_request_budget)
        protocol = calibration.calibration_protocol()
        if tuple(protocol["requested_fields"]) != FIELDS:
            raise CaptureRefusal("request_field_drift")
        target = root / CAPTURE_PARENT / args.run_id
        if _git(root, "check-ignore", str(target / "protocol.json")) != str(target / "protocol.json"):
            raise CaptureRefusal("capture_not_ignored")
        directory = _prepare_capture_directory(target)
        _publish_json(directory, "protocol.json", protocol)
        code_hashes = _code_hashes()
        _publish_json(directory, "start.json", {
            "started_utc": _utc_now(), "code_head": args.expected_head,
            "code_file_sha256": code_hashes, "code_set_sha256": hash_bytes(canonical_json(code_hashes).encode()),
            "protocol_sha256": PROTOCOL_SHA256,
            "scope": "outcome_free_latest_revised_finra_calibration",
            "no_outcomes": True, "symbol_alias_admission": False,
            "ready_for_empirical_backtest": False,
            "maximum_source_requests": args.source_request_budget,
        })
        credentials = _read_credentials(args.credential_file)
        _guard_lane(root, args.expected_head)
        stage = "authenticated_capture"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        pages, receipts, metadata_sha, attempts = _capture(
            directory, credentials, opener, source_request_budget=args.source_request_budget,
            before_data_request=lambda: _guard_lane(root, args.expected_head))
        stage = "source_calibration"
        report = calibration.calibrate_finra_sources(
            pages, expected_protocol_sha256=PROTOCOL_SHA256).to_payload()
        _publish_json(directory, "transport.json", {
            "code_head": args.expected_head, "code_file_sha256": code_hashes,
            "protocol_sha256": PROTOCOL_SHA256, "metadata_sha256": metadata_sha,
            "pages": receipts, "source_requests_attempted": attempts,
            "retrieval_complete": True,
        })
        _publish_json(directory, "calibration.json", report)
        _guard_lane(root, args.expected_head)
        print(canonical_json({
            "status": "source_calibration_complete", "protocol_sha256": PROTOCOL_SHA256,
            "calibration_file_sha256": hash_bytes((directory / "calibration.json").read_bytes()),
            "market_data_pages": len(pages), "source_requests_attempted": attempts,
            "scope": "outcome_free_latest_revised_finra_calibration",
            "symbol_alias_admission": False, "ready_for_empirical_backtest": False,
            "report": report,
        }))
        return 0
    except Exception as error:
        failure = {
            "status": "refused", "stage": stage,
            "reason": str(error) if isinstance(error, CaptureRefusal) else type(error).__name__,
            "ready_for_empirical_backtest": False, "response_body_withheld": True,
        }
        if isinstance(error, urllib.error.HTTPError):
            failure["http_status"] = error.code
        elif isinstance(error, _SourceHTTPRefusal):
            failure["http_status"] = error.status
        if directory is not None:
            failure["source_requests_attempted"] = len(tuple(directory.glob("attempt-*-start.json")))
            try:
                _publish_json(directory, "failure.json", failure)
            except Exception:
                pass
        print(canonical_json(failure))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
