"""One immutable public-demo reportDate feasibility request; import is inert.

This profile requests only AAPL.US's fiscal-2005-12-31 reportDate scalar.
It never requests earnings values, prices, other fields, tickers or windows.
A scalar observation establishes no archive coverage, timing/status/revision
lineage, identity, PIT, rights, canonical, QC or backtesting readiness.
The process-tree network must be denied for tests; fixture injection is not
acquisition authorization. The CLI requires an already committed clean lane.
"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import stat
import subprocess
from typing import Callable
from urllib import error, request

from research.insider_buying_provider_metadata_audit import _exclusive_json, _now
from research.insider_buying_provider_metadata_transport import (
    MAX_BODY_BYTES, TIMEOUT_SECONDS, ProviderMetadataResponse, _DenyRedirect, _read_bounded,
)

LANE_ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying")
LANE_BRANCH = "codex/strategy-insider-buying"
ARTIFACT_PARTS = ("artifacts", "insider_buying", "eodhd_earnings_demo")
SCHEMA = "insider-eodhd-reportdate-demo-one-shot-v1"
PROFILE = "eodhd-aapl-us-fiscal-2005-12-31-reportdate-demo-v1"
URL = ("https://eodhd.com/api/v1.1/fundamentals/AAPL.US"
       "?filter=Earnings::History::2005-12-31::reportDate&api_token=demo&fmt=json")
SOURCE_FILES = (
    "research/__init__.py",
    "research/insider_buying_eodhd_earnings_demo.py",
    "research/insider_buying_provider_metadata_audit.py",
    "research/insider_buying_provider_metadata_transport.py",
    "research/quantconnect.py",
)
FALSE_FLAGS = (
    "historical_coverage_verified", "actual_release_archive_verified",
    "timing_status_revision_lineage_verified", "historical_dead_reused_ticker_coverage_verified",
    "identity_verified", "pit_verified", "rights_verified", "canonical_ready",
    "qc_entitlement_verified", "outcome_access_authorized", "backtest_authorized",
    "research_ready", "backtesting_ready", "execution_authorized",
)
_TRANSPORT_CODES = frozenset({
    "unsupported-content-encoding", "invalid-content-length", "oversized-response",
    "truncated-response", "partial-read", "redirect-refused", "invalid-http-status",
    "response-origin-mismatch", "transport-timeout", "transport-error",
})


class EodhdDemoError(ValueError):
    """A typed sanitized refusal; never include supplied or upstream text."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise EodhdDemoError(code)


def _git(root: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(("/usr/bin/git", *args), cwd=root, capture_output=True,
                                check=False, timeout=10, env={"PATH": "/usr/bin:/bin"})
    except (OSError, subprocess.SubprocessError):
        raise EodhdDemoError("git_identity_unavailable") from None
    _require(result.returncode == 0, "git_identity_unavailable")
    return result.stdout


def _version(info) -> tuple:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _regular_leaf(info, *, limit: int, private: bool) -> None:
    _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and
             (not private or stat.S_IMODE(info.st_mode) == 0o600) and
             0 <= info.st_size <= limit, "custody_leaf_refused")


def _read_leaf(directory: int, name: str, *, limit: int, private: bool = True) -> bytes:
    named_before = os.stat(name, dir_fd=directory, follow_symlinks=False)
    _regular_leaf(named_before, limit=limit, private=private)
    # O_NONBLOCK prevents a regular-to-FIFO race from blocking before fstat.
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        _regular_leaf(info, limit=limit, private=private)
        _require(_version(info) == _version(named_before), "custody_leaf_changed")
        raw = stream.read(limit + 1)
        final = os.fstat(stream.fileno())
        named_after = os.stat(name, dir_fd=directory, follow_symlinks=False)
        _regular_leaf(final, limit=limit, private=private)
        _regular_leaf(named_after, limit=limit, private=private)
        _require(len(raw) == info.st_size and _version(info) == _version(final) == _version(named_after),
                 "custody_leaf_changed")
        return raw


def _identity(expected_head: str, *, root: Path = LANE_ROOT) -> dict:
    _require(type(expected_head) is str and re.fullmatch(r"[0-9a-f]{40}", expected_head) is not None,
             "expected_head_format_refused")
    _require(root == LANE_ROOT and Path.cwd() == LANE_ROOT and root.resolve() == root,
             "designated_worktree_required")
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
        try:
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                raw = _read_leaf(directory, path.name, limit=4 * MAX_BODY_BYTES, private=False)
            finally:
                os.close(directory)
        except OSError:
            raise EodhdDemoError("source_leaf_operation_refused") from None
        committed = _git(root, "show", f"{head}:{name}")
        _require(raw == committed, "tracked_source_bytes_mismatch")
        inventory[name] = _sha(raw)
    # Source reads can take place while another process edits or commits.
    _require(_git(root, "rev-parse", "HEAD").decode().strip() == head and
             _git(root, "branch", "--show-current").decode().strip() == branch and
             _git(root, "status", "--porcelain=v1", "--untracked-files=all") == b"",
             "worktree_changed_during_identity")
    encoded = json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()
    return {"root": actual_root, "branch": branch, "head": head,
            "source_sha256": inventory, "source_inventory_sha256": _sha(encoded), "clean": True}


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
    def attached() -> None:
        current = _mkdir_chain(root, create=False)
        try:
            held, reopened = os.fstat(parent), os.fstat(current)
            _require((held.st_dev, held.st_ino) == (reopened.st_dev, reopened.st_ino) and
                     set(os.listdir(current)) == {"scope-reservation.json", audit_id},
                     "private_journal_custody_refused")
            leaf = os.stat(audit_id, dir_fd=current, follow_symlinks=False)
            held = os.fstat(directory)
            _require(stat.S_ISDIR(leaf.st_mode) and stat.S_IMODE(leaf.st_mode) == 0o700 and
                     (leaf.st_dev, leaf.st_ino) == (held.st_dev, held.st_ino) and
                     set(os.listdir(directory)) == set(published), "private_journal_custody_refused")
        finally:
            os.close(current)
    attached()
    _require(_sha(_read_leaf(parent, "scope-reservation.json", limit=4 * MAX_BODY_BYTES)) == latch_sha,
             "private_journal_custody_refused")
    for name, digest in published.items():
        _require(_sha(_read_leaf(directory, name, limit=4 * MAX_BODY_BYTES)) == digest,
                 "private_journal_custody_refused")
    # Held descriptors cannot authenticate a path displaced during leaf reads.
    attached()


def _default_transport(*, expected_head: str, baseline: dict, parent: int, directory: int,
                       audit_id: str, latch_sha: str, published: dict[str, str]) -> ProviderMetadataResponse:
    # The real transport independently checks the real lane and started custody
    # before constructing an opener. A fake identity passed to run_demo cannot
    # be combined with this transport, even by passing the function explicitly.
    _require(_identity(expected_head) == baseline, "real_transport_identity_refused")
    _require(set(published) == {"reservation.json", "started.json"}, "real_transport_started_journal_required")
    _check_journal(parent, directory, audit_id, latch_sha, published, root=LANE_ROOT)
    reservation = json.loads(_read_leaf(directory, "reservation.json", limit=4 * MAX_BODY_BYTES))
    started = json.loads(_read_leaf(directory, "started.json", limit=4 * MAX_BODY_BYTES))
    _require(reservation.get("identity") == baseline and reservation.get("fixture_only") is False and
             reservation.get("profile") == PROFILE and reservation.get("url") == URL and
             reservation.get("method") == "GET" and reservation.get("maximum_attempts") == 1 and
             started.get("profile") == PROFILE and started.get("maximum_attempts") == 1 and
             started.get("reservation_sha256") == published["reservation.json"],
             "real_transport_started_journal_required")
    # No caller-supplied URL, method, headers, credentials, body or scope.
    opener = request.build_opener(request.ProxyHandler({}), _DenyRedirect(),
                                 request.HTTPSHandler(context=ssl.create_default_context()))
    item = request.Request(URL, headers={"Accept": "application/json", "Accept-Encoding": "identity"},
                           method="GET")
    stream = None
    try:
        try:
            stream = opener.open(item, timeout=TIMEOUT_SECONDS)
        except error.HTTPError as exc:
            stream = exc
        status = stream.getcode()
        if type(status) is not int or not 100 <= status <= 599:
            return ProviderMetadataResponse(None, b"", False, "invalid-http-status")
        if stream.geturl() != URL:
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


def _receipt(response: object) -> dict:
    if (type(response) is not ProviderMetadataResponse or type(response.body) is not bytes or
            type(response.body_complete) is not bool or
            (response.status is not None and
             (type(response.status) is not int or not 100 <= response.status <= 599)) or
            (response.disposition is not None and
             (type(response.disposition) is not str or response.disposition not in _TRANSPORT_CODES))):
        raise EodhdDemoError("invalid_transport_result_started_reservation_preserved")
    if response.status is None and (response.body or response.body_complete or
            response.disposition not in {"transport-error", "transport-timeout", "invalid-http-status"}):
        raise EodhdDemoError("invalid_transport_result_started_reservation_preserved")
    raw = response.body[:MAX_BODY_BYTES + 1]
    disposition = response.disposition
    if len(response.body) > MAX_BODY_BYTES:
        disposition = "oversized-response"
    elif disposition is None:
        if not response.body_complete:
            disposition = "partial-read"
        elif response.status != 200:
            disposition = "redirect-refused" if response.status is not None and 300 <= response.status < 400 else "http-refused"
        else:
            try:
                parsed = json.loads(raw.decode("utf-8"))
                valid = type(parsed) is str and re.fullmatch(r"2006-\d{2}-\d{2}", parsed) is not None
                valid = valid and date(2006, 1, 1) <= date.fromisoformat(parsed) <= date(2006, 3, 31)
                disposition = "date-field-observed" if valid else "reportdate-schema-refused"
            except (UnicodeError, ValueError, TypeError):
                disposition = "reportdate-schema-refused"
    success = disposition == "date-field-observed"
    return {"schema": SCHEMA, "profile": PROFILE, "http_status": response.status,
            "body_sha256": _sha(raw), "body_size_bytes": len(raw),
            "body_complete": response.body_complete and len(response.body) <= MAX_BODY_BYTES,
            "disposition": disposition, "date_field_observed": success,
            "transport_invocation_count": 1, "http_response_observed": response.status is not None,
            "response_body_retained": success,
            **{name: False for name in FALSE_FLAGS}}


def run_demo(audit_id: str, expected_head: str, *, root: Path = LANE_ROOT,
             identity: Callable = _identity, transport: Callable | None = None,
             clock: Callable[[], str] = _now) -> dict:
    """Exactly one request for this entire immutable profile, with no resume.

    A global exclusive scope reservation prevents a second audit ID from
    repeating a completed or ambiguous request. Fixture roots/identities require
    an explicit injected transport. The real CLI never accepts those inputs.
    """
    _require(type(audit_id) is str and re.fullmatch(r"ib-eodhd-demo-[a-z0-9-]{1,80}", audit_id) is not None,
             "audit_id_format_refused")
    _require(transport is not _default_transport and
             (transport is not None or (identity is _identity and root == LANE_ROOT)),
             "real_transport_requires_real_lane_identity")
    try:
        baseline = identity(expected_head, root=root)
    except (OSError, subprocess.SubprocessError):
        raise EodhdDemoError("identity_operation_refused") from None
    parent = directory = None
    try:
        parent = _mkdir_chain(root)
        _require(not os.listdir(parent), "completed_or_ambiguous_scope_cannot_repeat")
        latch = {"schema": SCHEMA, "profile": PROFILE, "audit_id": audit_id,
                 "reserved_at_utc": clock(), "maximum_attempts": 1, "retry_resume_permitted": False}
        try:
            latch_sha = _exclusive_json(parent, "scope-reservation.json", latch)
        except FileExistsError:
            raise EodhdDemoError("completed_or_ambiguous_scope_cannot_repeat") from None
        os.mkdir(audit_id, 0o700, dir_fd=parent)
        os.fsync(parent)
        directory = os.open(audit_id, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        reservation = {**latch, "identity": baseline, "url": URL, "method": "GET",
                       "timeout_seconds": TIMEOUT_SECONDS, "maximum_body_bytes": MAX_BODY_BYTES,
                       "owner_direction": "2026-10-13-continuous-build-delegated-bounded-source-qualification",
                       "public_demo_only": True, "credentials_read": False, "fixture_only": transport is not None,
                       **{name: False for name in FALSE_FLAGS}}
        reservation_sha = _exclusive_json(directory, "reservation.json", reservation)
        published = {"reservation.json": reservation_sha}
        _check_journal(parent, directory, audit_id, latch_sha, published, root=root)
        _require(identity(expected_head, root=root) == baseline, "worktree_or_source_changed_before_transport")
        start_sha = _exclusive_json(directory, "started.json", {
            "schema": SCHEMA, "profile": PROFILE, "started_at_utc": clock(),
            "reservation_sha256": reservation_sha, "maximum_attempts": 1})
        published["started.json"] = start_sha
        _check_journal(parent, directory, audit_id, latch_sha, published, root=root)
        _require(identity(expected_head, root=root) == baseline, "worktree_or_source_changed_before_transport")
        try:
            response = (transport() if transport is not None else _default_transport(
                expected_head=expected_head, baseline=baseline, parent=parent, directory=directory,
                audit_id=audit_id, latch_sha=latch_sha, published=published))
        except Exception:
            raise EodhdDemoError("transport_failed_started_reservation_preserved") from None
        _check_journal(parent, directory, audit_id, latch_sha, published, root=root)
        receipt = _receipt(response)
        _require(identity(expected_head, root=root) == baseline, "worktree_or_source_changed_after_transport")
        if receipt["date_field_observed"]:
            fd = os.open("response.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory)
            with os.fdopen(fd, "wb") as stream:
                stream.write(response.body)
                stream.flush()
                os.fsync(stream.fileno())
            os.fsync(directory)
            published["response.json"] = receipt["body_sha256"]
            _check_journal(parent, directory, audit_id, latch_sha, published, root=root)
        complete = {"schema": SCHEMA, "audit_id": audit_id, "profile": PROFILE,
                    "completed_at_utc": clock(), "reservation_sha256": reservation_sha,
                    "started_sha256": start_sha, "identity": baseline, "receipt": receipt,
                    "fixture_only": transport is not None, "untrusted_error_bodies_retained": False,
                    "looks_jobs_backtests": [0, 0, 0]}
        complete_sha = _exclusive_json(directory, "complete.json", complete)
        published["complete.json"] = complete_sha
        _check_journal(parent, directory, audit_id, latch_sha, published, root=root)
        _require(identity(expected_head, root=root) == baseline, "worktree_or_source_changed_after_transport")
        return {"audit_id": audit_id, "complete_sha256": complete_sha,
                "fixture_only": transport is not None, "receipt": receipt}
    except EodhdDemoError:
        raise
    except (OSError, ValueError, subprocess.SubprocessError):
        raise EodhdDemoError("private_journal_or_identity_operation_refused") from None
    finally:
        if directory is not None:
            os.close(directory)
        if parent is not None:
            os.close(parent)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-id", required=True)
    parser.add_argument("--expected-head", required=True)
    args = parser.parse_args(argv)
    try:
        result = run_demo(args.audit_id, args.expected_head)
    except EodhdDemoError as exc:
        print(json.dumps({"probe_refused": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["receipt"]["date_field_observed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
