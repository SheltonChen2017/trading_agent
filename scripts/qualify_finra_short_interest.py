"""Capture one frozen, outcome-free FINRA source-qualification sample.

This is not an empirical runner, a Massive comparison, or PIT source admission.
Credentials and tokens never enter artifacts or diagnostics. Run only from the
designated clean lane at the prospectively committed protocol/code snapshot.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import urllib.error
import urllib.request

from data.hashing import canonical_json, hash_bytes
from ml.immutable_io import publish_immutable_bytes
from research.short_interest_etf.finra_source_qualification import (
    PROTOCOL_SHA256,
    qualification_protocol,
    qualify_finra_snapshot,
)

TOKEN_URL = "https://ews.fip.finra.org/fip/rest/ews/oauth2/access_token?grant_type=client_credentials"
METADATA_URL = "https://api.finra.org/metadata/group/otcmarket/name/consolidatedShortInterest"
DATA_URL = "https://api.finra.org/data/group/otcmarket/name/consolidatedShortInterest"
BRANCH = "codex/strategy-short-interest"
CAPTURE_PARENT = Path("artifacts/short_interest/finra_source_qualification")
FIELDS = (
    "symbolCode", "settlementDate", "currentShortPositionQuantity",
    "previousShortPositionQuantity", "revisionFlag", "stockSplitFlag",
    "marketClassCode", "issuerServicesGroupExchangeCode", "issueName",
)


class CaptureRefusal(ValueError):
    """Named refusal; no external exception text is emitted."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CaptureRefusal("duplicate_json_key")
        result[key] = value
    return result


def _constant_refusal(value):
    raise CaptureRefusal("nonfinite_json")


def _decode(raw: bytes):
    return json.loads(raw, object_pairs_hook=_unique_object,
                      parse_float=Decimal, parse_constant=_constant_refusal)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True,
                            text=True, check=False)
    if result.returncode:
        raise CaptureRefusal("git_guard_failed")
    return result.stdout.strip()


def _guard_lane(root: Path, expected_head: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", expected_head):
        raise CaptureRefusal("invalid_expected_head")
    if root != Path.cwd().resolve() or root != Path(__file__).resolve().parents[1]:
        raise CaptureRefusal("wrong_physical_root")
    if Path(_git(root, "rev-parse", "--show-toplevel")).resolve() != root:
        raise CaptureRefusal("wrong_git_root")
    if _git(root, "branch", "--show-current") != BRANCH:
        raise CaptureRefusal("wrong_branch")
    if _git(root, "rev-parse", "HEAD") != expected_head:
        raise CaptureRefusal("head_changed")
    if _git(root, "status", "--porcelain"):
        raise CaptureRefusal("dirty_worktree")


def _read_credentials(path: Path) -> tuple[str, str]:
    path = path.absolute()
    if path.resolve() != path:
        raise CaptureRefusal("credential_symlink")
    parent = path.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700:
        raise CaptureRefusal("credential_directory_protection")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "r", encoding="utf-8") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 16384:
            raise CaptureRefusal("credential_file_protection")
        values = {}
        for line in handle.read().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                raise CaptureRefusal("credential_fields")
            name, value = (part.strip() for part in line.split("=", 1))
            if name not in ("FINRA_API_CLIENT_ID", "FINRA_API_SECRET") or name in values:
                raise CaptureRefusal("credential_fields")
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            if not value or any(char in value for char in ("\r", "\n", "\x00")):
                raise CaptureRefusal("credential_value")
            values[name] = value
    if set(values) != {"FINRA_API_CLIENT_ID", "FINRA_API_SECRET"} or ":" in values["FINRA_API_CLIENT_ID"]:
        raise CaptureRefusal("credential_fields")
    return values["FINRA_API_CLIENT_ID"], values["FINRA_API_SECRET"]


def _publish(directory: Path, name: str, raw: bytes) -> None:
    target = directory / name
    if target.exists():
        raise CaptureRefusal("artifact_already_exists")
    publish_immutable_bytes(target, raw)
    info = target.stat()
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise CaptureRefusal("artifact_protection")


def _publish_json(directory: Path, name: str, value) -> None:
    _publish(directory, name, (canonical_json(value) + "\n").encode())


def _prepare_capture_directory(target: Path) -> Path:
    # Resolve before mkdir, including every existing ancestor. Git's lexical
    # ignore match alone cannot prove where a symlink would store licensed rows.
    if target.resolve() != target or target.parent.resolve() != target.parent:
        raise CaptureRefusal("capture_symlink")
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    parent_info = target.parent.lstat()
    if not stat.S_ISDIR(parent_info.st_mode) or parent_info.st_uid != os.getuid() or stat.S_IMODE(parent_info.st_mode) != 0o700:
        raise CaptureRefusal("capture_directory_protection")
    target.mkdir(mode=0o700)
    info = target.lstat()
    if target.resolve() != target or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise CaptureRefusal("capture_directory_protection")
    return target


def _request(opener, request, maximum: int):
    with opener.open(request, timeout=30) as response:
        if response.status != 200:
            raise CaptureRefusal("http_not_200")
        raw = response.read(maximum + 1)
        if len(raw) > maximum:
            raise CaptureRefusal("response_size_limit")
        return raw, response.headers


def _integer_header(headers, name: str) -> int:
    text = headers.get(name)
    if not isinstance(text, str) or re.fullmatch(r"[0-9]+", text) is None:
        raise CaptureRefusal("missing_or_invalid_pagination_header")
    return int(text)


def _validate_metadata(metadata, headers) -> None:
    if not isinstance(metadata, dict) or headers.get("Data-Version") != "1":
        raise CaptureRefusal("metadata_version")
    if str(metadata.get("datasetGroup", "")).lower() != "otcmarket" or str(metadata.get("datasetName", "")).lower() != "consolidatedshortinterest":
        raise CaptureRefusal("metadata_dataset")
    if metadata.get("partitionFields") != ["settlementDate"]:
        raise CaptureRefusal("metadata_partition")
    expected = {name: "String" for name in FIELDS}
    expected.update(settlementDate="Date", currentShortPositionQuantity="Number", previousShortPositionQuantity="Number")
    actual = {}
    for field in metadata.get("fields", []):
        if not isinstance(field, dict) or field.get("name") in actual:
            raise CaptureRefusal("metadata_fields")
        actual[field.get("name")] = field.get("type")
    if any(actual.get(name) != kind for name, kind in expected.items()):
        raise CaptureRefusal("metadata_fields")


def _capture(directory: Path, credentials: tuple[str, str], opener, *, tickers: list[str], dates: list[str], source_request_budget: int = 8):
    if type(source_request_budget) is not int or not 1 <= source_request_budget <= 8:
        raise CaptureRefusal("invalid_source_request_budget")
    basic = base64.b64encode((credentials[0] + ":" + credentials[1]).encode()).decode()
    token_raw, _ = _request(opener, urllib.request.Request(
        TOKEN_URL, data=b"", method="POST",
        headers={"Authorization": "Basic " + basic, "Accept": "application/json"}), 65536)
    token_result = _decode(token_raw)
    token = token_result.get("access_token")
    if not isinstance(token, str) or not token or any(char in token for char in ("\r", "\n")) or str(token_result.get("token_type", "")).lower() != "bearer":
        raise CaptureRefusal("token_schema")
    expires = Decimal(str(token_result.get("expires_in", "0")))
    if not expires.is_finite() or expires < 600:
        raise CaptureRefusal("token_lifetime")
    # No token response, Authorization header, client ID or secret is persisted.
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json", "Data-Version": "1"}
    metadata_raw, metadata_headers = _request(opener, urllib.request.Request(METADATA_URL, headers=headers), 1048576)
    _validate_metadata(_decode(metadata_raw), metadata_headers)
    _publish(directory, "production_metadata.json", metadata_raw)
    pages, receipts = [], []
    source_requests = 0
    for settlement in dates:
        offset, total, seen = 0, None, set()
        for page_number in range(2):
            body = {"fields": list(FIELDS), "compareFilters": [{"fieldName": "settlementDate", "fieldValue": settlement, "compareType": "equal"}],
                    "domainFilters": [{"fieldName": "symbolCode", "values": tickers}],
                    "sortFields": ["symbolCode"], "limit": 100, "offset": offset, "async": False}
            request = urllib.request.Request(DATA_URL, data=canonical_json(body).encode(), method="POST", headers={**headers, "Content-Type": "application/json"})
            if source_requests >= source_request_budget:
                raise CaptureRefusal("source_request_budget_exhausted")
            source_requests += 1
            started = _utc_now()
            raw, response_headers = _request(opener, request, 1048576)
            completed = _utc_now()
            name = f"{settlement}-page-{page_number:02d}.json"
            _publish(directory, name, raw)
            # Keep whitelist-only transport evidence even if validation refuses
            # the page. Never persist Authorization or other credential headers.
            pagination_headers = {name: response_headers.get(name) for name in (
                "Record-Total", "Record-Offset", "Record-Limit", "Record-Max-Limit",
                "Total-Records-On-Page", "Data-Version",
            )}
            _publish_json(directory, f"{settlement}-page-{page_number:02d}-transport.json",
                          {"request_sha256": hash_bytes(canonical_json(body).encode()),
                           "response_raw_sha256": hash_bytes(raw), "request_started_utc": started,
                           "response_completed_utc": completed, "http_status": 200,
                           "pagination_headers": pagination_headers, "source_request_number": source_requests})
            rows = _decode(raw)
            if not isinstance(rows, list):
                raise CaptureRefusal("pagination_contract")
            # FINRA documents that response headers *may* include a page count;
            # observed production omits it. Exact array length is independently
            # cross-checked against required total/offset/limit and any supplied
            # page-count header. Its absence never implies retrieval completion.
            count = len(rows)
            page_count_origin = "exact_json_array_length"
            if response_headers.get("Total-Records-On-Page") is not None:
                if _integer_header(response_headers, "Total-Records-On-Page") != count:
                    raise CaptureRefusal("pagination_contract")
                page_count_origin = "header_verified_against_exact_json_array_length"
            found = _integer_header(response_headers, "Record-Total")
            reported_offset = _integer_header(response_headers, "Record-Offset")
            limit = _integer_header(response_headers, "Record-Limit")
            maximum = _integer_header(response_headers, "Record-Max-Limit")
            if count > 100 or limit != 100 or maximum < limit or reported_offset != offset or found > 200 or found < offset + count or response_headers.get("Data-Version") != "1":
                raise CaptureRefusal("pagination_contract")
            for row in rows:
                if isinstance(row, dict) and (
                    isinstance(row.get("settlementDate"), str) and row["settlementDate"] != settlement
                    or isinstance(row.get("symbolCode"), str) and row["symbolCode"] not in tickers
                ):
                    raise CaptureRefusal("response_query_mismatch")
            if total is not None and found != total:
                raise CaptureRefusal("pagination_total_changed")
            total = found
            digest = hash_bytes(raw)
            if digest in seen or (count == 0 and offset < total):
                raise CaptureRefusal("pagination_no_progress")
            seen.add(digest)
            pages.append(raw)
            receipts.append({"file": name, "raw_sha256": digest, "request_sha256": hash_bytes(canonical_json(body).encode()),
                             "request_started_utc": started, "response_completed_utc": completed,
                             "settlement_date": settlement, "offset": offset, "records": count, "total": total, "data_version": "1",
                             "page_count_origin": page_count_origin})
            offset += count
            if offset == total:
                break
        else:
            raise CaptureRefusal("pagination_page_bound")
    return tuple(pages), receipts, hash_bytes(metadata_raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-frozen-protocol", action="store_true", required=True)
    parser.add_argument("--expected-worktree", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-protocol-sha256", required=True)
    parser.add_argument("--credential-file", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-request-budget", type=int, default=8,
                        help="remaining whole-round source POST budget, at most eight")
    args = parser.parse_args(argv)
    directory = None
    stage = "preflight"
    try:
        root = args.expected_worktree.absolute()
        _guard_lane(root, args.expected_head)
        if args.expected_protocol_sha256 != PROTOCOL_SHA256:
            raise CaptureRefusal("protocol_hash_mismatch")
        if re.fullmatch(r"finra-source-[0-9]{8}T[0-9]{6}Z", args.run_id) is None:
            raise CaptureRefusal("invalid_run_id")
        if not 1 <= args.source_request_budget <= 8:
            raise CaptureRefusal("invalid_source_request_budget")
        protocol = qualification_protocol()
        if tuple(protocol["requested_fields"]) != FIELDS:
            raise CaptureRefusal("request_field_drift")
        target = root / CAPTURE_PARENT / args.run_id
        if _git(root, "check-ignore", str(target / "protocol.json")) != str(target / "protocol.json"):
            raise CaptureRefusal("capture_not_ignored")
        directory = _prepare_capture_directory(target)
        _publish_json(directory, "protocol.json", protocol)
        _publish_json(directory, "start.json", {"started_utc": _utc_now(), "code_head": args.expected_head,
                                               "protocol_sha256": PROTOCOL_SHA256, "scope": "finra_only_si_source_qualification", "no_outcomes": True,
                                               "maximum_source_requests": args.source_request_budget})
        credentials = _read_credentials(args.credential_file)
        _guard_lane(root, args.expected_head)
        stage = "authenticated_capture"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        pages, receipts, metadata_sha = _capture(directory, credentials, opener,
                                               tickers=protocol["tickers"], dates=protocol["settlement_dates"],
                                               source_request_budget=args.source_request_budget)
        stage = "source_qualification"
        report = qualify_finra_snapshot(pages, expected_protocol_sha256=PROTOCOL_SHA256).to_payload()
        _publish_json(directory, "transport.json", {"code_head": args.expected_head, "protocol_sha256": PROTOCOL_SHA256,
                                                   "metadata_sha256": metadata_sha, "pages": receipts, "retrieval_complete": True})
        _publish_json(directory, "qualification.json", report)
        _guard_lane(root, args.expected_head)
        print(canonical_json({"status": "source_qualification_complete", "protocol_sha256": PROTOCOL_SHA256,
                              "qualification_file_sha256": hash_bytes((directory / "qualification.json").read_bytes()),
                              "market_data_pages": len(pages), "report": report}))
        return 0
    except Exception as error:
        failure = {"status": "refused", "stage": stage, "reason": str(error) if isinstance(error, CaptureRefusal) else type(error).__name__,
                   "ready_for_empirical_backtest": False, "response_body_withheld": True}
        if isinstance(error, urllib.error.HTTPError):
            failure["http_status"] = error.code
        if directory is not None:
            try:
                _publish_json(directory, "failure.json", failure)
            except Exception:
                pass
        print(canonical_json(failure))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
