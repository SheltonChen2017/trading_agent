"""One paid Calendar qualification, not historical corpus or outcome research.

Only AAPL.US report dates in 2006Q1 are registered. The provider has no field
projection: successful raw bytes may contain financial columns and are kept
privately, but numeric lexemes are never evaluated, projected or printed.
Actual-nonnull is a current provider-reported status, not original-publication,
PIT, revision, identity, archive completeness, rights or backtest authority.
Import is inert. All tests require OS process-tree network denial.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date
import json
import os
from pathlib import Path
import re
import ssl
import stat
import subprocess
from typing import Callable
from urllib import error, request
from urllib.parse import quote

from research.insider_buying_eodhd_earnings_demo import (
    EodhdDemoError, FALSE_FLAGS, _git, _read_leaf, _sha,
)
from research.insider_buying_provider_metadata_audit import _exclusive_json, _now
from research.insider_buying_provider_metadata_transport import (
    MAX_BODY_BYTES, TIMEOUT_SECONDS, ProviderMetadataResponse, _DenyRedirect, _read_bounded,
)

LANE_ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying")
LANE_BRANCH = "codex/strategy-insider-buying"
ARTIFACT_PARTS = ("artifacts", "insider_buying", "eodhd_calendar_qualification")
SCHEMA = "insider-eodhd-calendar-qualification-one-shot-v1"
PROFILE = "eodhd-calendar-aapl-us-2006q1-v1"
REDACTED_URL = ("https://eodhd.com/api/calendar/earnings?symbols=AAPL.US"
                "&from=2006-01-01&to=2006-03-31&fmt=json&api_token=<redacted>")
SOURCE_FILES = (
    "research/__init__.py",
    "research/insider_buying_eodhd_calendar_qualification.py",
    "research/insider_buying_eodhd_earnings_demo.py",
    "research/insider_buying_provider_metadata_audit.py",
    "research/insider_buying_provider_metadata_transport.py",
    "research/quantconnect.py",
)
_NUMBER = object()
_FINANCIAL = frozenset({"actual", "estimate", "difference", "percent"})
_ROW_FIELDS = _FINANCIAL | {"code", "report_date", "date", "before_after_market", "currency"}
_TRANSPORT_CODES = frozenset({
    "unsupported-content-encoding", "invalid-content-length", "oversized-response",
    "truncated-response", "partial-read", "redirect-refused", "invalid-http-status",
    "response-origin-mismatch", "transport-timeout", "transport-error",
})


class CalendarQualificationError(ValueError):
    """A sanitized fixed refusal code; no credential, path or upstream text."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise CalendarQualificationError(code)


@dataclass(frozen=True, slots=True)
class _Token:
    value: str = field(repr=False)

    def __repr__(self) -> str:
        return "_Token(<credential redacted>)"


def _credential_file(path: Path) -> _Token:
    """Only the exact caller-named file; never environment/discovery/hash/log.

    Every ancestor is opened without symlink following and reattached after
    the secure named/FD leaf read. A terminal newline is permitted, not any
    embedded whitespace. Input validation does not consume a provider attempt.
    """
    _require(type(path) is Path or isinstance(path, Path), "private_token_file_refused")
    _require(path.is_absolute() and path.parts[0] == "/" and
             all(part not in {"", ".", ".."} for part in path.parts[1:]) and
             path != Path("/"), "private_token_file_refused")
    descriptors = []
    try:
        directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(directory)
        for part in path.parts[1:-1]:
            directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=directory)
            descriptors.append(directory)
        raw = _read_leaf(directory, path.name, limit=4097)
        # Reopen the whole named ancestry rather than trusting displaced FDs.
        current = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part, held in zip(path.parts[1:-1], descriptors[1:]):
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
                os.close(current)
                current = child
                info, anchor = os.fstat(current), os.fstat(held)
                _require((info.st_dev, info.st_ino) == (anchor.st_dev, anchor.st_ino),
                         "private_token_file_refused")
            _require(_read_leaf(current, path.name, limit=4097) == raw, "private_token_file_changed")
        finally:
            os.close(current)
        if raw.endswith(b"\n"):
            raw = raw[:-1]
        _require(16 <= len(raw) <= 4096 and re.fullmatch(rb"[A-Za-z0-9._-]+", raw) is not None,
                 "private_token_file_refused")
        return _Token(raw.decode("ascii"))
    except CalendarQualificationError:
        raise
    except (OSError, UnicodeError, EodhdDemoError):
        raise CalendarQualificationError("private_token_file_refused") from None
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _identity(expected_head: str, *, root: Path = LANE_ROOT) -> dict:
    _require(type(expected_head) is str and re.fullmatch(r"[0-9a-f]{40}", expected_head) is not None,
             "expected_head_format_refused")
    _require(root == LANE_ROOT and Path.cwd() == LANE_ROOT and root.resolve() == root,
             "designated_worktree_required")
    try:
        actual_root = _git(root, "rev-parse", "--show-toplevel").decode().strip()
        branch = _git(root, "branch", "--show-current").decode().strip()
        head = _git(root, "rev-parse", "HEAD").decode().strip()
        _require(actual_root == str(root) and branch == LANE_BRANCH and head == expected_head,
                 "worktree_branch_head_mismatch")
        _require(_git(root, "status", "--porcelain=v1", "--untracked-files=all") == b"",
                 "clean_committed_lane_required")
        inventory = {}
        for name in SOURCE_FILES:
            path = root / name
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                raw = _read_leaf(directory, path.name, limit=4 * MAX_BODY_BYTES, private=False)
            finally:
                os.close(directory)
            _require(raw == _git(root, "show", f"{head}:{name}"), "tracked_source_bytes_mismatch")
            inventory[name] = _sha(raw)
        _require(_git(root, "rev-parse", "HEAD").decode().strip() == head and
                 _git(root, "branch", "--show-current").decode().strip() == branch and
                 _git(root, "status", "--porcelain=v1", "--untracked-files=all") == b"",
                 "worktree_changed_during_identity")
    except (OSError, UnicodeError, EodhdDemoError, subprocess.SubprocessError):
        raise CalendarQualificationError("source_or_git_identity_operation_refused") from None
    encoded = json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()
    return {"root": actual_root, "branch": branch, "head": head, "source_sha256": inventory,
            "source_inventory_sha256": _sha(encoded), "clean": True}


def _mkdir_chain(root: Path, *, create: bool = True) -> int:
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for name in ARTIFACT_PARTS:
            if create:
                try:
                    os.mkdir(name, 0o700, dir_fd=directory)
                    os.fsync(directory)
                except FileExistsError:
                    pass
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        _require(stat.S_IMODE(os.fstat(directory).st_mode) == 0o700, "private_scope_directory_required")
        return directory
    except BaseException:
        os.close(directory)
        raise


def _check_journal(parent: int, directory: int, audit_id: str, latch_sha: str,
                   published: dict[str, str], *, root: Path) -> None:
    def attached():
        current = _mkdir_chain(root, create=False)
        try:
            held, reopened = os.fstat(parent), os.fstat(current)
            _require((held.st_dev, held.st_ino) == (reopened.st_dev, reopened.st_ino) and
                     stat.S_IMODE(reopened.st_mode) == 0o700 and
                     set(os.listdir(current)) == {"scope-reservation.json", audit_id},
                     "private_journal_custody_refused")
            named, held = os.stat(audit_id, dir_fd=current, follow_symlinks=False), os.fstat(directory)
            _require(stat.S_ISDIR(named.st_mode) and stat.S_IMODE(named.st_mode) == 0o700 and
                     (named.st_dev, named.st_ino) == (held.st_dev, held.st_ino) and
                     set(os.listdir(directory)) == set(published), "private_journal_custody_refused")
        finally:
            os.close(current)
    attached()
    _require(_sha(_read_leaf(parent, "scope-reservation.json", limit=4 * MAX_BODY_BYTES)) == latch_sha,
             "private_journal_custody_refused")
    for name, digest in published.items():
        _require(_sha(_read_leaf(directory, name, limit=4 * MAX_BODY_BYTES)) == digest,
                 "private_journal_custody_refused")
    attached()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate_source_json_key")
        result[key] = value
    return result


def _number(text: str):
    _require(len(text) <= 128, "source_number_oversized")
    return _NUMBER


def _constant(_):
    raise CalendarQualificationError("nonfinite_source_number_refused")


def _date(value: object) -> date:
    _require(type(value) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None,
             "source_date_schema_refused")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise CalendarQualificationError("source_date_schema_refused") from None


def _projection(raw: bytes, *, token: _Token | None) -> list[dict]:
    if token is not None:
        _require(token.value.encode("ascii") not in raw, "credential_echo_refused")
    try:
        body = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique, parse_int=_number,
                          parse_float=_number, parse_constant=_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise CalendarQualificationError("source_json_schema_refused") from None
    if token is not None:
        pending = [body]
        while pending:
            value = pending.pop()
            if type(value) is str:
                _require(token.value not in value, "credential_echo_refused")
            elif type(value) is dict:
                pending.extend(value.keys())
                pending.extend(value.values())
            elif type(value) is list:
                pending.extend(value)
    _require(type(body) is dict and set(body) == {"type", "description", "symbols", "earnings"} and
             body["type"] == "Earnings" and body["description"] == "Historical and upcoming Earnings" and
             body["symbols"] == "AAPL.US" and type(body["earnings"]) is list and len(body["earnings"]) <= 92,
             "source_envelope_schema_refused")
    projection, periods = [], set()
    for row in body["earnings"]:
        _require(type(row) is dict and set(row) == _ROW_FIELDS and row["code"] == "AAPL.US",
                 "source_row_schema_refused")
        report_date, fiscal_date = _date(row["report_date"]), _date(row["date"])
        _require(date(2006, 1, 1) <= report_date <= date(2006, 3, 31), "report_date_outside_registered_scope")
        _require(fiscal_date <= report_date, "fiscal_date_after_report_date")
        _require(row["date"] not in periods, "duplicate_fiscal_period_refused")
        periods.add(row["date"])
        _require(row["before_after_market"] is None or
                 (type(row["before_after_market"]) is str and
                  row["before_after_market"] in {"BeforeMarket", "AfterMarket"}), "source_timing_schema_refused")
        _require(row["currency"] is None or (type(row["currency"]) is str and
                 re.fullmatch(r"[A-Z]{3}", row["currency"]) is not None), "source_currency_schema_refused")
        _require(all(row[name] is None or row[name] is _NUMBER for name in _FINANCIAL),
                 "source_financial_type_refused")
        projection.append({"code": row["code"], "report_date": row["report_date"],
            "fiscal_date": row["date"], "before_after_market": row["before_after_market"],
            "current_provider_reported_status": "reported" if row["actual"] is _NUMBER else "unknown"})
    return sorted(projection, key=lambda row: (row["report_date"], row["fiscal_date"]))


def _receipt(response: object, *, token: _Token) -> tuple[dict, list[dict] | None]:
    _require(type(response) is ProviderMetadataResponse and type(response.body) is bytes and
             type(response.body_complete) is bool and (response.status is None or
             (type(response.status) is int and 100 <= response.status <= 599)) and
             (response.disposition is None or type(response.disposition) is str and
              response.disposition in _TRANSPORT_CODES), "invalid_transport_result_started_reservation_preserved")
    _require(response.status is not None or (not response.body and not response.body_complete and
             response.disposition in {"transport-error", "transport-timeout", "invalid-http-status"}),
             "invalid_transport_result_started_reservation_preserved")
    disposition, projection = response.disposition, None
    if len(response.body) > MAX_BODY_BYTES:
        disposition = "oversized-response"
    elif disposition is None:
        if response.status != 200:
            disposition = "redirect-refused" if response.status is not None and 300 <= response.status < 400 else "http-refused"
        elif not response.body_complete:
            disposition = "partial-read"
        else:
            try:
                projection = _projection(response.body, token=token)
                disposition = "calendar_sample_observed"
            except CalendarQualificationError as exc:
                disposition = str(exc)
    success = projection is not None
    # No hash of an untrusted error or credential-echo body is permitted.
    receipt = {"schema": SCHEMA, "profile": PROFILE, "http_status": response.status,
        "disposition": disposition, "calendar_sample_observed": success,
        "transport_invocation_count": 1, "http_response_observed": response.status is not None,
        "body_sha256": _sha(response.body) if success else None,
        "body_size_bytes": len(response.body) if success else None,
        "response_body_retained": success, "untrusted_error_body_hashed_or_retained": False,
        "financial_values_evaluated_or_projected": False,
        "sample_rows": None if not success else len(projection),
        "reported_rows": None if not success else sum(row["current_provider_reported_status"] == "reported" for row in projection),
        "unknown_status_rows": None if not success else sum(row["current_provider_reported_status"] == "unknown" for row in projection),
        "timing_unknown_rows": None if not success else sum(row["before_after_market"] is None for row in projection),
        "empty_result_is_coverage_evidence": False,
        **{name: False for name in FALSE_FLAGS}}
    return receipt, projection


def _default_transport(*, expected_head: str, baseline: dict, parent: int, directory: int,
                       audit_id: str, latch_sha: str, published: dict[str, str],
                       token_path: Path, token: _Token) -> ProviderMetadataResponse:
    _require(_identity(expected_head) == baseline, "real_transport_identity_refused")
    _require(set(published) == {"reservation.json", "started.json"}, "real_transport_started_journal_required")
    _check_journal(parent, directory, audit_id, latch_sha, published, root=LANE_ROOT)
    reservation = json.loads(_read_leaf(directory, "reservation.json", limit=4 * MAX_BODY_BYTES))
    started = json.loads(_read_leaf(directory, "started.json", limit=4 * MAX_BODY_BYTES))
    _require(reservation.get("identity") == baseline and reservation.get("fixture_only") is False and
             reservation.get("profile") == PROFILE and reservation.get("url") == REDACTED_URL and
             reservation.get("method") == "GET" and reservation.get("maximum_attempts") == 1 and
             reservation.get("owner_acknowledged_rotated_token") is True and
             started.get("profile") == PROFILE and started.get("maximum_attempts") == 1 and
             started.get("reservation_sha256") == published["reservation.json"],
             "real_transport_started_journal_required")
    _require(_credential_file(token_path) == token, "private_token_file_changed")
    actual_url = REDACTED_URL.replace("<redacted>", quote(token.value, safe=""))
    opener = request.build_opener(request.ProxyHandler({}), _DenyRedirect(),
                                 request.HTTPSHandler(context=ssl.create_default_context()))
    item = request.Request(actual_url, headers={"Accept": "application/json", "Accept-Encoding": "identity"}, method="GET")
    stream = None
    try:
        try:
            stream = opener.open(item, timeout=TIMEOUT_SECONDS)
        except error.HTTPError as exc:
            stream = exc
        status = stream.getcode()
        if type(status) is not int or not 100 <= status <= 599:
            return ProviderMetadataResponse(None, b"", False, "invalid-http-status")
        if stream.geturl() != actual_url:
            return ProviderMetadataResponse(status, b"", False, "response-origin-mismatch")
        # Error bodies can echo credentials. Never even consume those bodies.
        if status != 200:
            return ProviderMetadataResponse(status, b"", False,
                "redirect-refused" if 300 <= status < 400 else None)
        return _read_bounded(stream, status)
    except TimeoutError:
        return ProviderMetadataResponse(None, b"", False, "transport-timeout")
    except error.URLError as exc:
        return ProviderMetadataResponse(None, b"", False,
            "transport-timeout" if isinstance(exc.reason, TimeoutError) else "transport-error")
    except Exception:
        return ProviderMetadataResponse(None, b"", False, "transport-error")
    finally:
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass


def run_qualification(audit_id: str, expected_head: str, token_path: Path, *,
                      owner_acknowledged_rotated_token: bool, root: Path = LANE_ROOT,
                      identity: Callable = _identity, transport: Callable | None = None,
                      clock: Callable[[], str] = _now) -> dict:
    """One immutable profile, no retry/resume, even with another audit ID.

    Owner acknowledgement is input provenance, not manufactured cryptographic
    proof of rotation. The CLI never supports injected identity or transport.
    """
    _require(type(audit_id) is str and re.fullmatch(r"ib-eodhd-calendar-[a-z0-9-]{1,80}", audit_id) is not None,
             "audit_id_format_refused")
    _require(owner_acknowledged_rotated_token is True, "owner_rotated_token_acknowledgement_required")
    _require(transport is not _default_transport and
             (transport is not None or (identity is _identity and root == LANE_ROOT)),
             "real_transport_requires_real_lane_identity")
    parent = directory = None
    try:
        baseline = identity(expected_head, root=root)
        token = _credential_file(token_path)
        parent = _mkdir_chain(root)
        _require(not os.listdir(parent), "completed_or_ambiguous_scope_cannot_repeat")
        latch = {"schema": SCHEMA, "profile": PROFILE, "audit_id": audit_id,
                 "reserved_at_utc": clock(), "maximum_attempts": 1, "retry_resume_permitted": False}
        try:
            latch_sha = _exclusive_json(parent, "scope-reservation.json", latch)
        except FileExistsError:
            raise CalendarQualificationError("completed_or_ambiguous_scope_cannot_repeat") from None
        os.mkdir(audit_id, 0o700, dir_fd=parent)
        os.fsync(parent)
        directory = os.open(audit_id, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        reservation = {**latch, "identity": baseline, "url": REDACTED_URL, "method": "GET",
            "timeout_seconds": TIMEOUT_SECONDS, "maximum_body_bytes": MAX_BODY_BYTES,
            "owner_direction": "2026-10-13-continuous-build-delegated-bounded-source-qualification",
            "owner_acknowledged_rotated_token": True, "rotation_independently_verified": False,
            "fixture_only": transport is not None, "credential_or_path_or_hash_retained": False,
            **{name: False for name in FALSE_FLAGS}}
        reservation_sha = _exclusive_json(directory, "reservation.json", reservation)
        published = {"reservation.json": reservation_sha}
        _check_journal(parent, directory, audit_id, latch_sha, published, root=root)
        _require(identity(expected_head, root=root) == baseline, "worktree_or_source_changed_before_transport")
        _require(_credential_file(token_path) == token, "private_token_file_changed")
        start_sha = _exclusive_json(directory, "started.json", {"schema": SCHEMA, "profile": PROFILE,
            "started_at_utc": clock(), "reservation_sha256": reservation_sha, "maximum_attempts": 1})
        published["started.json"] = start_sha
        _check_journal(parent, directory, audit_id, latch_sha, published, root=root)
        _require(identity(expected_head, root=root) == baseline, "worktree_or_source_changed_before_transport")
        _require(_credential_file(token_path) == token, "private_token_file_changed")
        try:
            response = transport() if transport is not None else _default_transport(
                expected_head=expected_head, baseline=baseline, parent=parent, directory=directory,
                audit_id=audit_id, latch_sha=latch_sha, published=published, token_path=token_path, token=token)
        except Exception:
            raise CalendarQualificationError("transport_failed_started_reservation_preserved") from None
        _check_journal(parent, directory, audit_id, latch_sha, published, root=root)
        receipt, projection = _receipt(response, token=token)
        _require(identity(expected_head, root=root) == baseline, "worktree_or_source_changed_after_transport")
        if projection is not None:
            fd = os.open("response.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            with os.fdopen(fd, "wb") as stream:
                stream.write(response.body)
                stream.flush()
                os.fsync(stream.fileno())
            os.fsync(directory)
            published["response.json"] = receipt["body_sha256"]
            published["metadata.json"] = _exclusive_json(directory, "metadata.json", {
                "schema": SCHEMA, "profile": PROFILE, "body_sha256": receipt["body_sha256"], "rows": projection})
            _check_journal(parent, directory, audit_id, latch_sha, published, root=root)
        complete = {"schema": SCHEMA, "audit_id": audit_id, "profile": PROFILE,
            "completed_at_utc": clock(), "reservation_sha256": reservation_sha, "started_sha256": start_sha,
            "identity": baseline, "receipt": receipt, "fixture_only": transport is not None,
            "credential_or_path_or_hash_retained": False, "looks_jobs_backtests": [0, 0, 0]}
        complete_sha = _exclusive_json(directory, "complete.json", complete)
        published["complete.json"] = complete_sha
        _check_journal(parent, directory, audit_id, latch_sha, published, root=root)
        _require(identity(expected_head, root=root) == baseline, "worktree_or_source_changed_after_transport")
        return {"audit_id": audit_id, "complete_sha256": complete_sha,
                "fixture_only": transport is not None, "receipt": receipt}
    except CalendarQualificationError:
        raise
    except (OSError, ValueError, EodhdDemoError, subprocess.SubprocessError):
        raise CalendarQualificationError("private_journal_or_identity_operation_refused") from None
    finally:
        if directory is not None:
            os.close(directory)
        if parent is not None:
            os.close(parent)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-id", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--token-file", required=True, type=Path)
    parser.add_argument("--owner-acknowledged-rotated-token", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run_qualification(args.audit_id, args.expected_head, args.token_file,
            owner_acknowledged_rotated_token=args.owner_acknowledged_rotated_token)
    except CalendarQualificationError as exc:
        print(json.dumps({"qualification_refused": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["receipt"]["calendar_sample_observed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
