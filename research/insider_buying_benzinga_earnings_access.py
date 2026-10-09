"""One owner-authorized Earnings product-access/source-schema GET, not a look.

https://massive.com/docs/rest/partners/benzinga/earnings documents date filters,
limit, ``date.asc`` sorting, and history beginning 2010-04-30. It does not
provide a field projection or an original-publication/revision archive. The
one fixed response can contain financial figures: bytes may be transferred
and retained privately, but figures are never evaluated or published here.
Only source-schema presence and schedule dates/update timestamps are reported.
Owner-reported purchase is distinct from observed access, full coverage, PIT
knowledge, licence interpretation and local/QC processing permission.

Import is inert. Core Insider code must not import this network runner. A
durable started record precedes credential loading. There is no pagination,
retry, redirect, proxy environment, resume, upload, compile, job, price join,
research-look registration, backtest or trading operation.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import stat
import subprocess
from typing import Callable, Mapping
from urllib import error, request
from urllib.parse import parse_qsl, urlsplit

from research.insider_buying_provider_metadata_audit import _exclusive_json
from research.insider_buying_provider_metadata_transport import (
    ProviderMetadataResponse, _credential, _DenyRedirect, _read_bounded,
)


LANE_ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying")
LANE_BRANCH = "codex/strategy-insider-buying"
ARTIFACT_PARTS = ("artifacts", "insider_buying", "benzinga_earnings_access")
SCHEMA = "insider-benzinga-earnings-one-shot-access-v1"
REQUEST_PROFILE = "massive-benzinga-earnings-20100430-one-page-v1"
REQUEST_URL = "https://api.massive.com/benzinga/v1/earnings?date.gte=2010-04-30&date.lte=2010-04-30&limit=1&sort=date.asc"
MAX_BODY_BYTES = 1024 * 1024
TIMEOUT_SECONDS = 15
SOURCE_FILES = ("research/insider_buying_benzinga_earnings_access.py",
    "research/insider_buying_provider_metadata_audit.py", "research/insider_buying_provider_metadata_transport.py",
    "research/quantconnect.py")
_NUMBER = object()
_ZERO = object()
_ONE = object()
_FINANCIAL_FIELDS = frozenset({"actual_eps", "actual_revenue", "eps_surprise", "eps_surprise_percent",
    "estimated_eps", "estimated_revenue", "previous_eps", "previous_revenue", "revenue_surprise", "revenue_surprise_percent"})
_ROW_FIELDS = _FINANCIAL_FIELDS | {"benzinga_id", "company_name", "currency", "date", "date_status", "eps_method",
    "fiscal_period", "fiscal_year", "importance", "last_updated", "notes", "revenue_method", "ticker", "time"}
_TRANSPORT_FAILURES = frozenset({"unsupported-content-encoding", "invalid-content-length", "oversized-response",
    "truncated-response", "partial-read", "redirect-refused", "invalid-http-status", "response-origin-mismatch",
    "transport-timeout", "transport-error"})


class EarningsAccessAuditError(ValueError):
    """Sanitized refusal; never interpolate credentials, rows or provider text."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise EarningsAccessAuditError(code)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _utc(text: object) -> str:
    _require(type(text) is str and len(text) <= 64 and re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", text) is not None,
        "timestamp-schema-refused")
    try:
        instant = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise EarningsAccessAuditError("timestamp-schema-refused") from None
    _require(instant.utcoffset() is not None, "timestamp-schema-refused")
    return instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class EarningsAccessRequest:
    url: str
    headers: tuple[tuple[str, str], ...] = field(repr=False)
    method: str = "GET"
    timeout_seconds: int = TIMEOUT_SECONDS

    def __repr__(self) -> str:
        return "EarningsAccessRequest(<fixed profile; credential redacted>)"


def _validate_request(item: EarningsAccessRequest) -> None:
    _require(type(item) is EarningsAccessRequest and type(item.url) is str and item.url == REQUEST_URL
             and type(item.method) is str and item.method == "GET" and type(item.timeout_seconds) is int
             and item.timeout_seconds == TIMEOUT_SECONDS, "fixed-request-profile-refused")
    _require(type(item.headers) is tuple and all(type(row) is tuple and len(row) == 2
        and all(type(value) is str for value in row) for row in item.headers), "request-headers-refused")
    headers = dict(item.headers)
    _require(len(headers) == len(item.headers) and set(headers) == {"Accept", "Accept-Encoding", "Authorization"}
        and headers["Accept"] == "application/json" and headers["Accept-Encoding"] == "identity"
        and re.fullmatch(r"Bearer [!-~]{1,4096}", headers["Authorization"]) is not None, "request-headers-refused")


def _default_transport(item: EarningsAccessRequest) -> ProviderMetadataResponse:
    _validate_request(item)
    opener = request.build_opener(request.ProxyHandler({}), _DenyRedirect(),
                                 request.HTTPSHandler(context=ssl.create_default_context()))
    req = request.Request(item.url, headers=dict(item.headers), method="GET")
    stream = None
    try:
        try:
            stream = opener.open(req, timeout=TIMEOUT_SECONDS)
        except error.HTTPError as exc:
            stream = exc
        status = stream.getcode()
        if type(status) is not int or not 100 <= status <= 599:
            return ProviderMetadataResponse(None, b"", False, "invalid-http-status")
        if stream.geturl() != REQUEST_URL:
            return ProviderMetadataResponse(status, b"", False, "response-origin-mismatch")
        response = _read_bounded(stream, status)
        if 300 <= status < 400:
            return ProviderMetadataResponse(status, response.body, response.body_complete, "redirect-refused")
        return response
    except TimeoutError:
        return ProviderMetadataResponse(None, b"", False, "transport-timeout")
    except error.URLError as exc:
        code = "transport-timeout" if isinstance(exc.reason, TimeoutError) else "transport-error"
        return ProviderMetadataResponse(None, b"", False, code)
    except Exception:
        return ProviderMetadataResponse(None, b"", False, "transport-error")
    finally:
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate-source-json-key")
        result[key] = value
    return result


def _number(text: str):
    # Validate lexical finiteness/bounds without evaluating financial values.
    _require(len(text) <= 128, "source-number-oversized")
    # Only metadata count needs the exact zero/one integer distinction. No
    # financial token's numeric value or lexeme is retained in the parse tree.
    return _ZERO if text == "0" else _ONE if text == "1" else _NUMBER


def _refuse_constant(_):
    raise EarningsAccessAuditError("nonfinite-source-number-refused")


def _schedule_schema(raw: bytes, *, credential: str | None) -> dict:
    if credential is not None:
        _require(credential.encode("ascii") not in raw, "credential-echo-refused")
    try:
        body = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique, parse_int=_number,
                          parse_float=_number, parse_constant=_refuse_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise EarningsAccessAuditError("source-json-schema-refused") from None
    if credential is not None:
        pending = [body]
        while pending:
            value = pending.pop()
            if type(value) is str:
                _require(credential not in value, "credential-echo-refused")
            elif type(value) is dict:
                pending.extend(value.keys())
                pending.extend(value.values())
            elif type(value) is list:
                pending.extend(value)
    _require(type(body) is dict and {"status", "results"} <= set(body)
        and set(body) <= {"status", "results", "request_id", "count", "next_url"}
        and body["status"] == "OK" and type(body["status"]) is str, "source-envelope-schema-refused")
    _require(type(body["results"]) is list and len(body["results"]) <= 1, "one-row-limit-refused")
    if "request_id" in body:
        _require(any(body["request_id"] is marker for marker in (_NUMBER, _ZERO, _ONE)) or (type(body["request_id"]) is str
            and re.fullmatch(r"[A-Za-z0-9._-]{1,128}", body["request_id"]) is not None), "request-id-schema-refused")
    if "count" in body:
        _require(body["count"] is (_ZERO if not body["results"] else _ONE), "count-schema-refused")
    if "next_url" in body:
        next_url = body["next_url"]
        _require(type(next_url) is str and len(next_url) <= 8192, "next-url-schema-refused")
        parts = urlsplit(next_url)
        query = parse_qsl(parts.query, keep_blank_values=True)
        if credential is not None:
            _require(all(credential not in key and credential not in value for key, value in query),
                     "credential-echo-refused")
        _require(parts.scheme == "https" and parts.netloc == "api.massive.com"
            and parts.path == "/benzinga/v1/earnings" and not parts.fragment
            and len(query) == 1 and query[0][0] == "cursor" and bool(query[0][1]), "next-url-credential-or-origin-refused")
    columns, dates, instants, time_present, financial_columns = set(), [], [], False, set()
    for row in body["results"]:
        _require(type(row) is dict and set(row) <= _ROW_FIELDS and row, "source-row-schema-refused")
        columns.update(row)
        financial_columns.update(set(row) & _FINANCIAL_FIELDS)
        for name, value in row.items():
            if name in _FINANCIAL_FIELDS | {"fiscal_year", "importance"}:
                _require(any(value is marker for marker in (_NUMBER, _ZERO, _ONE)) or value is None,
                         "numeric-source-field-schema-refused")
            else:
                _require(value is None or (type(value) is str and len(value) <= 16384
                    and not any(ord(char) < 32 for char in value)), "text-source-field-schema-refused")
        if row.get("date") is not None:
            _require(row["date"] == "2010-04-30", "source-date-outside-fixed-query")
            dates.append(row["date"])
        if row.get("last_updated") is not None:
            instants.append(_utc(row["last_updated"]))
        if row.get("date_status") is not None:
            _require(row["date_status"] in {"projected", "confirmed"}, "date-status-schema-refused")
        if row.get("time") is not None:
            _require(re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]", row["time"]) is not None,
                     "schedule-time-schema-refused")
            time_present = True
    return {"results_count": len(body["results"]), "source_column_presence": sorted(columns),
        "schedule_dates": dates, "last_updated_instants_utc": instants, "schedule_time_present": time_present,
        "schedule_time_timezone_interpretation": "UNMEASURED-documents-say-EST",
        "financial_column_presence": sorted(financial_columns), "financial_values_evaluated_or_reported": False,
        "pagination_present_not_followed": "next_url" in body}


def replay_supplied_earnings_schema(raw: bytes, expected_body_sha256: str) -> dict:
    """Pure independent replay of exact supplied retained successful bytes.

    An externally supplied digest verifies bytes, not service authenticity,
    entitlement, original publication, schedule completeness or permissions.
    Credential-echo defense belongs to the original capture, not this replay.
    """
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_BODY_BYTES and type(expected_body_sha256) is str
        and re.fullmatch(r"[0-9a-f]{64}", expected_body_sha256) is not None
        and _sha(raw) == expected_body_sha256, "supplied-body-root-refused")
    return _schedule_schema(raw, credential=None)


def _receipt(response: ProviderMetadataResponse | None, disposition: str, facts: dict | None = None) -> dict:
    return {"schema": "insider-benzinga-earnings-access-receipt-v1", "request_profile": REQUEST_PROFILE,
        "http_status": None if response is None else response.status,
        "body_sha256": None if response is None else _sha(response.body),
        "body_size_bytes": 0 if response is None else len(response.body),
        "body_complete": False if response is None else response.body_complete, "disposition": disposition,
        "source_schema": facts, "owner_purchase_classification": "OWNER-REPORTED",
        "full_history_coverage_verified": False, "original_publication_or_pit_verified": False,
        "rights_verified": False, "qc_entitlement_verified": False, "research_ready": False,
        "strategy_outcome_access_authorized": False, "qc_backtest_authorized": False,
        "source_pit_rights_look_qc_backtest_execution_authority": False}


def _observe(environ: Mapping[str, str], transport: Callable) -> tuple[dict, bytes | None]:
    try:
        credential = _credential(environ, "MASSIVE_API_KEY")
    except Exception:
        return _receipt(None, "credentials-unavailable-or-invalid"), None
    item = EarningsAccessRequest(REQUEST_URL, (("Accept", "application/json"), ("Accept-Encoding", "identity"),
                                             ("Authorization", "Bearer " + credential)))
    _validate_request(item)
    try:
        response = transport(item)
    except Exception:
        return _receipt(None, "transport-error"), None
    if (type(response) is not ProviderMetadataResponse or type(response.body) is not bytes
        or type(response.body_complete) is not bool or (response.status is not None
            and (type(response.status) is not int or not 100 <= response.status <= 599))
        or not (response.disposition is None or type(response.disposition) is str
                and response.disposition in _TRANSPORT_FAILURES)):
        return _receipt(None, "transport-result-refused"), None
    if len(response.body) > MAX_BODY_BYTES:
        bounded = ProviderMetadataResponse(response.status, response.body[:MAX_BODY_BYTES + 1], False)
        return _receipt(bounded, "oversized-response"), None
    if response.disposition is not None or response.status is None or response.body_complete is False:
        return _receipt(response, response.disposition or "partial-read"), None
    if 300 <= response.status < 400:
        return _receipt(response, "redirect-refused"), None
    if response.status in {401, 403}:
        return _receipt(response, "configured-product-request-refused"), None
    if response.status == 429:
        return _receipt(response, "rate-limited-no-retry"), None
    if not 200 <= response.status < 300:
        return _receipt(response, "http-error"), None
    try:
        facts = _schedule_schema(response.body, credential=credential)
    except EarningsAccessAuditError as exc:
        return _receipt(response, str(exc)), None
    except Exception:
        return _receipt(response, "source-schema-refused"), None
    return _receipt(response, "product-access-source-schema-observed", facts), response.body


def _identity(expected_head: str, *, root: Path = LANE_ROOT) -> dict:
    _require(type(expected_head) is str and re.fullmatch(r"[0-9a-f]{40}", expected_head) is not None, "head-format-refused")
    _require(root == LANE_ROOT and Path.cwd().resolve() == LANE_ROOT and not root.is_symlink(), "designated-worktree-required")
    def git(*args):
        result = subprocess.run(("/usr/bin/git", *args), cwd=root, capture_output=True, check=False,
                                timeout=10, env={"PATH": "/usr/bin:/bin"})
        _require(result.returncode == 0, "git-identity-unavailable")
        return result.stdout.decode("utf-8").strip()
    actual_root, branch, head = git("rev-parse", "--show-toplevel"), git("branch", "--show-current"), git("rev-parse", "HEAD")
    _require(actual_root == str(LANE_ROOT) and branch == LANE_BRANCH and head == expected_head, "lane-identity-differs")
    inventory = {}
    for name in SOURCE_FILES:
        path = root / name
        _require(not path.is_symlink() and path.is_file(), "source-identity-unavailable")
        inventory[name] = _sha(path.read_bytes())
    return {"root": actual_root, "branch": branch, "head": head,
        "status_sha256": _sha(git("status", "--porcelain=v1", "--untracked-files=all").encode()), "source_sha256": inventory}


def _parent(root: Path, *, create: bool) -> int:
    _require(type(root) is Path or isinstance(root, Path), "root-path-invalid")
    _require(root.is_absolute() and root.resolve() == root, "root-path-refused")
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in ARTIFACT_PARTS:
            if create:
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                    os.fsync(fd)
                except FileExistsError:
                    pass
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def _exclusive_raw(directory: int, name: str, raw: bytes) -> str:
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.fsync(directory)
    return _sha(raw)


def _version(info) -> tuple:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _regular_private_leaf(info) -> None:
    _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o600
        and 0 < info.st_size <= MAX_BODY_BYTES + 1, "journal-leaf-custody-refused")


def _custody(parent: int, directory: int, audit_id: str, published: dict[str, str], root: Path) -> None:
    current = _parent(root, create=False)
    try:
        _require((os.fstat(current).st_dev, os.fstat(current).st_ino) ==
            (os.fstat(parent).st_dev, os.fstat(parent).st_ino), "journal-ancestor-custody-refused")
        leaf = os.stat(audit_id, dir_fd=current, follow_symlinks=False)
        held = os.fstat(directory)
        _require(stat.S_ISDIR(leaf.st_mode) and stat.S_IMODE(leaf.st_mode) == 0o700
            and (leaf.st_dev, leaf.st_ino) == (held.st_dev, held.st_ino)
            and set(os.listdir(directory)) == set(published), "journal-directory-custody-refused")
        for name, digest in published.items():
            named_before = os.stat(name, dir_fd=directory, follow_symlinks=False)
            _regular_private_leaf(named_before)
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                _regular_private_leaf(info)
                _require(_version(info) == _version(named_before), "journal-named-leaf-custody-refused")
                raw = stream.read(info.st_size + 1)
                after = os.fstat(stream.fileno())
                named_after = os.stat(name, dir_fd=directory, follow_symlinks=False)
                _regular_private_leaf(after)
                _regular_private_leaf(named_after)
                _require(_version(info) == _version(after) == _version(named_after), "journal-named-leaf-custody-refused")
                _require(len(raw) == info.st_size and _sha(raw) == digest, "journal-byte-custody-refused")
        # Reopen the full name chain again after reads; old held descriptors
        # must not authenticate an ancestor/leaf displaced during verification.
        final_parent = _parent(root, create=False)
        try:
            _require((os.fstat(final_parent).st_dev, os.fstat(final_parent).st_ino) ==
                (os.fstat(parent).st_dev, os.fstat(parent).st_ino), "journal-ancestor-custody-refused")
            final_leaf = os.stat(audit_id, dir_fd=final_parent, follow_symlinks=False)
            _require(stat.S_ISDIR(final_leaf.st_mode) and stat.S_IMODE(final_leaf.st_mode) == 0o700
                and (final_leaf.st_dev, final_leaf.st_ino) == (held.st_dev, held.st_ino)
                and set(os.listdir(directory)) == set(published), "journal-directory-custody-refused")
        finally:
            os.close(final_parent)
    finally:
        os.close(current)


def run_earnings_access_audit(audit_id: str, expected_head: str, *, environ: Mapping[str, str] | None = None,
                            transport: Callable | None = None, identity: Callable = _identity,
                            root: Path = LANE_ROOT, clock: Callable = _now) -> dict:
    """One fixed access observation with no completed/ambiguous restart option.

    Injection/root override is only for network-denied fixtures. The actual
    default transport requires the designated root and exact real identity
    function. An injected response is not authenticated provider evidence.
    """
    _require(type(audit_id) is str and re.fullmatch(r"ib-earnings-access-[a-z0-9-]{1,80}", audit_id) is not None,
             "audit-id-refused")
    _require(type(expected_head) is str and re.fullmatch(r"[0-9a-f]{40}", expected_head) is not None, "head-format-refused")
    _require(transport is not None or (root == LANE_ROOT and identity is _identity), "real-transport-designated-identity-required")
    parent = directory = None
    try:
        baseline = identity(expected_head, root=root)
        parent = _parent(root, create=True)
        try:
            os.mkdir(audit_id, 0o700, dir_fd=parent)
        except FileExistsError:
            raise EarningsAccessAuditError("existing-completed-or-ambiguous-audit-refused") from None
        os.fsync(parent)
        directory = os.open(audit_id, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        reservation = {"schema": SCHEMA, "audit_id": audit_id, "reserved_at_utc": _utc(clock()), "identity": baseline,
            "request_profile": REQUEST_PROFILE, "fixed_url_without_credentials": REQUEST_URL,
            "maximum_transport_attempts": 1, "pagination_retry_resume_permitted": False,
            "scope": "one-source-page-access-and-schedule-schema-no-strategy-outcomes-prices-or-jobs",
            "owner_purchase_classification": "OWNER-REPORTED", "raw_financial_fields_may_be_transferred_privately": True,
            "source_pit_rights_look_qc_backtest_execution_authority": False}
        reservation_sha = _exclusive_json(directory, "reservation.json", reservation)
        published = {"reservation.json": reservation_sha}
        _custody(parent, directory, audit_id, published, root)
        _require(identity(expected_head, root=root) == baseline, "lane-identity-changed")
        started_sha = _exclusive_json(directory, "started.json", {"schema": SCHEMA, "started_at_utc": _utc(clock()),
            "reservation_sha256": reservation_sha, "maximum_transport_attempts": 1})
        published["started.json"] = started_sha
        _custody(parent, directory, audit_id, published, root)
        # Credential lookup and the only possible transport occur after fsync.
        receipt, successful_raw = _observe(os.environ if environ is None else environ,
                                          _default_transport if transport is None else transport)
        _require(identity(expected_head, root=root) == baseline, "lane-identity-changed")
        _custody(parent, directory, audit_id, published, root)
        raw_sha = None
        if successful_raw is not None:
            raw_sha = _exclusive_raw(directory, "successful-response.json", successful_raw)
            published["successful-response.json"] = raw_sha
            _custody(parent, directory, audit_id, published, root)
        complete = {"schema": SCHEMA, "audit_id": audit_id, "completed_at_utc": _utc(clock()), "identity": baseline,
            "reservation_sha256": reservation_sha, "started_sha256": started_sha, "receipt": receipt,
            "successful_response_sha256": raw_sha, "error_response_body_persisted": False,
            "raw_response_retained_privately": raw_sha is not None, "injected_transport": transport is not None,
            "no_strategy_prices_returns_or_outcomes_joined": True, "looks_jobs_backtests": [0, 0, 0],
            "source_pit_rights_look_qc_backtest_execution_authority": False}
        _require(identity(expected_head, root=root) == baseline, "lane-identity-changed")
        complete_sha = _exclusive_json(directory, "complete.json", complete)
        published["complete.json"] = complete_sha
        _custody(parent, directory, audit_id, published, root)
        return {"audit_id": audit_id, "complete_sha256": complete_sha, "receipt": receipt,
                "successful_response_sha256": raw_sha, "looks_jobs_backtests": [0, 0, 0], "research_ready": False}
    except EarningsAccessAuditError:
        raise
    except Exception:
        raise EarningsAccessAuditError("private-audit-operation-refused") from None
    finally:
        if directory is not None:
            os.close(directory)
        if parent is not None:
            os.close(parent)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-id", required=True)
    parser.add_argument("--expected-head", required=True)
    args = parser.parse_args()
    try:
        result = run_earnings_access_audit(args.audit_id, args.expected_head)
    except EarningsAccessAuditError as exc:
        print(json.dumps({"disposition": "REFUSED", "code": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
