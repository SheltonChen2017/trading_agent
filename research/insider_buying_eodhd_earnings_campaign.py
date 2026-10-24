"""Bounded, one-attempt date-window Calendar custody, not archive admission.

Explicit nonoverlapping windows only. No symbol inference, retry, pagination,
resume, EPS conversion, outcome join, original-availability or rights claim.
Each successful raw response is private; only metadata is interpreted.
Run only a clean committed designated lane; tests deny process-tree network.
"""
from __future__ import annotations

import argparse
import calendar
from datetime import date
import fcntl
import json
import os
from pathlib import Path
import re
import ssl
import stat
import subprocess
import time
from typing import Callable
from urllib import error, request
from urllib.parse import quote

from research.insider_buying_eodhd_calendar_qualification import (
    CalendarQualificationError, _Token, _credential_file, _date,
    _unique, _number, _constant, _NUMBER, _FINANCIAL, _ROW_FIELDS,
)
from research.insider_buying_eodhd_earnings_demo import (
    EodhdDemoError, FALSE_FLAGS, _git, _read_leaf, _sha,
)
from research.insider_buying_provider_metadata_audit import _exclusive_json, _now
from research.insider_buying_provider_metadata_transport import (
    TIMEOUT_SECONDS, ProviderMetadataResponse, _DenyRedirect,
)

LANE_ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying")
LANE_BRANCH = "codex/strategy-insider-buying"
ARTIFACT_PARTS = ("artifacts", "insider_buying", "eodhd_earnings_campaign")
SCHEMA = "insider-eodhd-date-window-earnings-campaign-v1"
OWNER_DIRECTION = "owner:2026-10-13:required-historical-earnings-continuous-build"
PROFILE = "eodhd-calendar-monthly-support-envelope-20051201-20260731-v1"
MAX_BODY_BYTES = 4 * 1024 * 1024
MAX_ROWS = 50_000
MAX_WINDOWS = 248
START_INTERVAL_SECONDS = 1.0


def registered_windows() -> tuple[tuple[str, str], ...]:
    """Frozen supporting envelope, not a changed study or exact event bound."""
    result = []
    for year in range(2005, 2027):
        for month in range(1, 13):
            if (year, month) < (2005, 12) or (year, month) > (2026, 7):
                continue
            result.append((date(year, month, 1).isoformat(),
                           date(year, month, calendar.monthrange(year, month)[1]).isoformat()))
    return tuple(result)


REGISTERED_WINDOWS = registered_windows()
SOURCE_FILES = (
    "research/__init__.py",
    "research/insider_buying_eodhd_earnings_campaign.py",
    "research/insider_buying_eodhd_calendar_qualification.py",
    "research/insider_buying_eodhd_earnings_demo.py",
    "research/insider_buying_provider_metadata_audit.py",
    "research/insider_buying_provider_metadata_transport.py",
    "research/quantconnect.py",
)
_TRANSPORT_CODES = frozenset({
    "unsupported-content-encoding", "invalid-content-length", "oversized-response",
    "truncated-response", "partial-read", "redirect-refused", "invalid-http-status",
    "response-origin-mismatch", "transport-timeout", "transport-error",
})


class EarningsCampaignError(ValueError):
    """Only a fixed sanitized code, never supplied or provider text."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise EarningsCampaignError(code)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _windows(windows: object) -> tuple[tuple[str, str], ...]:
    _require(type(windows) is tuple and 1 <= len(windows) <= MAX_WINDOWS,
             "explicit_finite_windows_required")
    result, prior = [], None
    for window in windows:
        _require(type(window) is tuple and len(window) == 2, "window_schema_refused")
        try:
            start, end = _date(window[0]), _date(window[1])
        except CalendarQualificationError:
            raise EarningsCampaignError("window_date_schema_refused") from None
        _require(start <= end and (end - start).days < 31,
                 "window_order_or_31_day_limit_refused")
        _require(date(2005, 12, 1) <= start <= end <= date(2026, 7, 31),
                 "window_outside_frozen_support_envelope")
        _require(prior is None or prior < start, "windows_unsorted_or_overlapping")
        result.append((window[0], window[1]))
        prior = end
    return tuple(result)


def _url(window: tuple[str, str]) -> str:
    return ("https://eodhd.com/api/calendar/earnings?from=" + window[0] +
            "&to=" + window[1] + "&fmt=json&api_token=<redacted>")


def _scope(window: tuple[str, str]) -> dict:
    # Owner/campaign/code lineage intentionally do not change request identity.
    return {"method": "GET", "endpoint": "https://eodhd.com/api/calendar/earnings",
            "from": window[0], "to": window[1], "fmt": "json", "symbols": None}


def _fingerprint(window: tuple[str, str]) -> str:
    return _sha(_canonical(_scope(window)))


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
                raw = _read_leaf(directory, path.name, limit=MAX_BODY_BYTES, private=False)
            finally:
                os.close(directory)
            _require(raw == _git(root, "show", f"{head}:{name}"), "tracked_source_bytes_mismatch")
            inventory[name] = _sha(raw)
        _require(_git(root, "rev-parse", "HEAD").decode().strip() == head and
                 _git(root, "branch", "--show-current").decode().strip() == branch and
                 _git(root, "status", "--porcelain=v1", "--untracked-files=all") == b"",
                 "worktree_changed_during_identity")
    except (OSError, UnicodeError, EodhdDemoError, subprocess.SubprocessError):
        raise EarningsCampaignError("source_or_git_identity_operation_refused") from None
    return {"root": actual_root, "branch": branch, "head": head, "clean": True,
            "source_sha256": inventory, "source_inventory_sha256": _sha(_canonical(inventory))}


def _directory(parent: int, name: str, *, create: bool, private: bool = True) -> int:
    if create:
        try:
            os.mkdir(name, 0o700, dir_fd=parent)
            os.fsync(parent)
        except FileExistsError:
            pass
    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    try:
        info = os.fstat(child)
        _require(not private or stat.S_IMODE(info.st_mode) == 0o700, "private_directory_required")
        return child
    except BaseException:
        os.close(child)
        raise


def _root_directory(root: Path, *, create: bool) -> int:
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for index, name in enumerate(ARTIFACT_PARTS):
            child = _directory(directory, name, create=create, private=index == len(ARTIFACT_PARTS) - 1)
            os.close(directory)
            directory = child
        return directory
    except BaseException:
        os.close(directory)
        raise


def _same_directory(parent: int, name: str, held: int) -> None:
    named, opened = os.stat(name, dir_fd=parent, follow_symlinks=False), os.fstat(held)
    _require(stat.S_ISDIR(named.st_mode) and stat.S_IMODE(named.st_mode) == 0o700 and
             (named.st_dev, named.st_ino) == (opened.st_dev, opened.st_ino),
             "private_journal_custody_refused")


def _check_journal(root: Path, parent: int, scopes: int, campaigns: int,
                   directory: int, campaign_id: str, published: dict[str, str],
                   reserved: dict[str, str], lock: int) -> None:
    def attached():
        reopened = _root_directory(root, create=False)
        try:
            named, held = os.fstat(reopened), os.fstat(parent)
            _require((named.st_dev, named.st_ino) == (held.st_dev, held.st_ino) and
                     set(os.listdir(parent)) == {"campaigns", "scopes", "campaign.lock"},
                     "private_journal_custody_refused")
            _same_directory(parent, "scopes", scopes)
            _same_directory(parent, "campaigns", campaigns)
            _same_directory(campaigns, campaign_id, directory)
            _require(set(os.listdir(directory)) == set(published), "private_journal_custody_refused")
            lock_named, lock_held = os.stat("campaign.lock", dir_fd=parent, follow_symlinks=False), os.fstat(lock)
            _require(stat.S_ISREG(lock_named.st_mode) and lock_named.st_nlink == 1 and
                     stat.S_IMODE(lock_named.st_mode) == 0o600 and lock_named.st_size == 0 and
                     (lock_named.st_dev, lock_named.st_ino) == (lock_held.st_dev, lock_held.st_ino),
                     "private_journal_custody_refused")
        finally:
            os.close(reopened)
    attached()
    for name, digest in published.items():
        _require(_sha(_read_leaf(directory, name, limit=MAX_BODY_BYTES * 4)) == digest,
                 "private_journal_custody_refused")
    _require(set(os.listdir(scopes)) == set(reserved), "private_journal_custody_refused")
    for name, digest in reserved.items():
        _require(_sha(_read_leaf(scopes, name, limit=MAX_BODY_BYTES)) == digest,
                 "private_journal_custody_refused")
    attached()


def _prior_scopes(scopes: int, windows: tuple[tuple[str, str], ...]) -> dict[str, str]:
    hashes = {}
    for name in os.listdir(scopes):
        _require(re.fullmatch(r"[0-9a-f]{64}\.json", name) is not None, "scope_registry_refused")
        raw = _read_leaf(scopes, name, limit=MAX_BODY_BYTES)
        try:
            record = json.loads(raw, object_pairs_hook=_unique)
            _require(type(record) is dict and set(record) == {
                "schema", "scope", "campaign_id", "reserved_at_utc", "maximum_attempts"} and
                record["schema"] == SCHEMA and record["maximum_attempts"] == 1,
                "scope_registry_refused")
            scope = record["scope"]
            prior = _windows(((scope["from"], scope["to"]),))[0]
            _require(scope == _scope(prior) and name == _fingerprint(prior) + ".json",
                     "scope_registry_refused")
        except (ValueError, KeyError, TypeError):
            raise EarningsCampaignError("scope_registry_refused") from None
        _require(all(end < prior[0] or start > prior[1] for start, end in windows),
                 "completed_or_ambiguous_window_cannot_repeat")
        hashes[name] = _sha(raw)
    return hashes


def _projection(raw: bytes, window: tuple[str, str], *, token: _Token | None) -> list[dict]:
    if token is not None:
        _require(token.value.encode("ascii") not in raw, "credential_echo_refused")
    try:
        body = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique, parse_int=_number,
                          parse_float=_number, parse_constant=_constant)
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
        _require(type(body) is dict and set(body) == {"type", "description", "from", "to", "earnings"} and
                 body["type"] == "Earnings" and body["description"] == "Historical and upcoming Earnings" and
                 body["from"] == window[0] and body["to"] == window[1] and
                 type(body["earnings"]) is list and len(body["earnings"]) <= MAX_ROWS,
                 "source_envelope_schema_refused")
        projection = []
        for ordinal, row in enumerate(body["earnings"]):
            _require(type(row) is dict and set(row) == _ROW_FIELDS and type(row["code"]) is str and
                     re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}\.[A-Za-z0-9]{1,12}", row["code"]) is not None,
                     "source_row_schema_refused")
            report, fiscal = _date(row["report_date"]), _date(row["date"])
            _require(date.fromisoformat(window[0]) <= report <= date.fromisoformat(window[1]),
                     "report_date_outside_registered_scope")
            _require(fiscal <= report, "fiscal_date_after_report_date")
            _require(row["before_after_market"] is None or (type(row["before_after_market"]) is str and
                     row["before_after_market"] in {"BeforeMarket", "AfterMarket"}), "source_timing_schema_refused")
            _require(row["currency"] is None or (type(row["currency"]) is str and
                     re.fullmatch(r"[A-Z]{3}", row["currency"]) is not None), "source_currency_schema_refused")
            _require(all(row[name] is None or row[name] is _NUMBER for name in _FINANCIAL),
                     "source_financial_type_refused")
            projection.append({"source_row_ordinal": ordinal,
                "code": row["code"], "report_date": row["report_date"],
                "fiscal_date": row["date"], "before_after_market": row["before_after_market"],
                "current_provider_reported_status": "reported" if row["actual"] is _NUMBER else "unknown"})
        return sorted(projection, key=lambda row: (row["report_date"], row["code"],
                                                   row["fiscal_date"], row["source_row_ordinal"]))
    except CalendarQualificationError as exc:
        raise EarningsCampaignError(str(exc)) from None
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise EarningsCampaignError("source_json_schema_refused") from None


def _receipt(response: object, window: tuple[str, str], *, token: _Token) -> tuple[dict, list[dict] | None]:
    _require(type(response) is ProviderMetadataResponse and type(response.body) is bytes and
             type(response.body_complete) is bool and (response.status is None or
             (type(response.status) is int and 100 <= response.status <= 599)) and
             (response.disposition is None or type(response.disposition) is str and
              response.disposition in _TRANSPORT_CODES), "invalid_transport_result_started_preserved")
    _require(response.status is not None or (not response.body and not response.body_complete and
             response.disposition in {"transport-error", "transport-timeout", "invalid-http-status"}),
             "invalid_transport_result_started_preserved")
    disposition, projection = response.disposition, None
    if len(response.body) > MAX_BODY_BYTES:
        disposition = "oversized-response"
    elif disposition is None:
        if response.status != 200:
            disposition = "redirect-refused" if 300 <= response.status < 400 else "http-refused"
        elif not response.body_complete:
            disposition = "partial-read"
        else:
            try:
                projection = _projection(response.body, window, token=token)
                disposition = "calendar_window_observed"
            except EarningsCampaignError as exc:
                disposition = str(exc)
    success = projection is not None
    periods = {}
    for row in projection or ():
        periods.setdefault((row["code"], row["fiscal_date"]), []).append(row)
    duplicate_rows = sum(len(rows) - 1 for rows in periods.values())
    # Financial lexemes are intentionally not interpreted or compared. This
    # counts metadata disagreements only, not a certified revision history.
    conflicting_periods = sum(len({(row["report_date"], row["before_after_market"],
                                    row["current_provider_reported_status"])
                                  for row in rows}) > 1 for rows in periods.values())
    return {"http_status": response.status, "disposition": disposition,
        "calendar_window_observed": success, "transport_invocation_count": 1,
        "http_response_observed": response.status is not None,
        "body_sha256": _sha(response.body) if success else None,
        "body_size_bytes": len(response.body) if success else None,
        "response_body_retained": success, "untrusted_error_body_hashed_or_retained": False,
        "financial_values_evaluated_or_projected": False,
        "sample_rows": len(projection) if success else None,
        "duplicate_fiscal_period_rows": duplicate_rows if success else None,
        "metadata_conflicting_fiscal_periods": conflicting_periods if success else None,
        "duplicate_or_conflicting_rows_deduplicated": False,
        "reported_rows": sum(row["current_provider_reported_status"] == "reported" for row in projection) if success else None,
        "unknown_status_rows": sum(row["current_provider_reported_status"] == "unknown" for row in projection) if success else None,
        "timing_unknown_rows": sum(row["before_after_market"] is None for row in projection) if success else None,
        "empty_result_is_coverage_evidence": False, **{name: False for name in FALSE_FLAGS}}, projection


def _read_window_bounded(stream, status: int) -> ProviderMetadataResponse:
    """Versioned 4MiB bound; older one-shot transport bytes are untouched."""
    chunks, count, length = [], 0, None
    try:
        encoding = stream.headers.get("Content-Encoding")
        if encoding is not None and encoding.lower().strip() != "identity":
            return ProviderMetadataResponse(status, b"", False, "unsupported-content-encoding")
        declared = stream.headers.get("Content-Length")
        if declared is not None:
            if re.fullmatch(r"[0-9]{1,20}", declared) is None:
                return ProviderMetadataResponse(status, b"", False, "invalid-content-length")
            length = int(declared)
            if length > MAX_BODY_BYTES:
                return ProviderMetadataResponse(status, b"", False, "oversized-response")
        while count <= MAX_BODY_BYTES:
            chunk = stream.read(min(65536, MAX_BODY_BYTES + 1 - count))
            if type(chunk) is not bytes:
                return ProviderMetadataResponse(status, b"".join(chunks), False, "partial-read")
            if not chunk:
                raw = b"".join(chunks)
                if length is not None and length != count:
                    return ProviderMetadataResponse(status, raw, False, "truncated-response")
                return ProviderMetadataResponse(status, raw)
            chunk = chunk[:MAX_BODY_BYTES + 1 - count]
            chunks.append(chunk)
            count += len(chunk)
            if count > MAX_BODY_BYTES:
                return ProviderMetadataResponse(status, b"".join(chunks), False, "oversized-response")
    except Exception:
        return ProviderMetadataResponse(status, b"".join(chunks), False, "partial-read")
    return ProviderMetadataResponse(status, b"".join(chunks), False, "oversized-response")


def _default_transport(window: tuple[str, str], *, expected_head: str, baseline: dict,
                       check: Callable[[], None], directory: int, index: int,
                       manifest_sha: str, scope_sha: str, token_path: Path, token: _Token) -> ProviderMetadataResponse:
    _require(_identity(expected_head) == baseline, "real_transport_identity_refused")
    check()
    prefix = f"window-{index:04d}"
    started = json.loads(_read_leaf(directory, prefix + "-started.json", limit=MAX_BODY_BYTES))
    _require(started == {"schema": SCHEMA, "window": list(window), "index": index,
        "started_at_utc": started.get("started_at_utc"), "manifest_sha256": manifest_sha,
        "scope_reservation_sha256": scope_sha, "maximum_attempts": 1},
        "real_transport_started_journal_required")
    manifest = json.loads(_read_leaf(directory, "manifest.json", limit=MAX_BODY_BYTES))
    _require(manifest["identity"] == baseline and manifest["fixture_only"] is False and
             manifest["owner_direction"] == OWNER_DIRECTION and
             manifest["owner_acknowledged_rotated_token"] is True and
             manifest["windows"][index] == list(window), "real_transport_started_journal_required")
    _require(_credential_file(token_path) == token, "private_token_file_changed")
    actual_url = _url(window).replace("<redacted>", quote(token.value, safe=""))
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
        if status != 200:
            return ProviderMetadataResponse(status, b"", False,
                "redirect-refused" if 300 <= status < 400 else None)
        return _read_window_bounded(stream, status)
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


def _fixture_root_is_lane(root: Path) -> bool:
    """Section 194 (Claude review): continuation5's guard, missing in this version."""
    _require(isinstance(root, Path), "fixture_root_identity_refused")
    try:
        return root == LANE_ROOT or root.resolve() == LANE_ROOT or root.samefile(LANE_ROOT)
    except OSError:
        # An unverifiable fixture root never gains access to the real registry.
        raise EarningsCampaignError("fixture_root_identity_refused") from None


def run_campaign(campaign_id: str, expected_head: str, token_path: Path, *, windows: tuple | None = None,
                 owner_acknowledged_rotated_token: bool, root: Path = LANE_ROOT,
                 identity: Callable = _identity, transport: Callable | None = None,
                 clock: Callable[[], str] = _now, progress: Callable[[dict], None] | None = None) -> dict:
    """No repeat of a completed/ambiguous window, even under another ID.

    Fixture callbacks receive only public date bounds. A failure stops further
    windows; the immutable manifest preserves all remaining unattempted ones.
    """
    _require(type(campaign_id) is str and re.fullmatch(r"ib-eodhd-campaign-[a-z0-9-]{1,80}", campaign_id) is not None,
             "campaign_id_format_refused")
    windows = _windows(REGISTERED_WINDOWS if windows is None else windows)
    _require(owner_acknowledged_rotated_token is True, "owner_rotated_token_acknowledgement_required")
    _require(transport is not _default_transport and
             (transport is not None or (identity is _identity and root == LANE_ROOT)),
             "real_transport_requires_real_lane_identity")
    _require(transport is not None or windows == REGISTERED_WINDOWS,
             "real_transport_requires_exact_frozen_monthly_manifest")
    # Section 194 (Claude review): a fixture transport aimed at the real lane would
    # write fixture scopes into the real registry that later versions pin exactly.
    _require(transport is None or not _fixture_root_is_lane(root), "fixture_transport_actual_lane_root_refused")
    parent = scopes = campaigns = directory = lock = None
    try:
        baseline = identity(expected_head, root=root)
        token = _credential_file(token_path)
        parent = _root_directory(root, create=True)
        scopes = _directory(parent, "scopes", create=True)
        campaigns = _directory(parent, "campaigns", create=True)
        lock = os.open("campaign.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=parent)
        info = os.fstat(lock)
        _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and
                 stat.S_IMODE(info.st_mode) == 0o600 and info.st_size == 0, "private_lock_refused")
        os.fsync(lock)
        os.fsync(parent)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise EarningsCampaignError("concurrent_campaign_refused") from None
        reserved = _prior_scopes(scopes, windows)
        try:
            os.mkdir(campaign_id, 0o700, dir_fd=campaigns)
            os.fsync(campaigns)
        except FileExistsError:
            raise EarningsCampaignError("campaign_cannot_resume") from None
        directory = _directory(campaigns, campaign_id, create=False)
        manifest = {"schema": SCHEMA, "profile": PROFILE, "campaign_id": campaign_id, "registered_at_utc": clock(),
            "identity": baseline, "windows": [list(window) for window in windows],
            "window_scope_sha256": [_fingerprint(window) for window in windows],
            "owner_direction": OWNER_DIRECTION, "owner_acknowledged_rotated_token": True,
            "rotation_independently_verified": False, "fixture_only": transport is not None,
            "maximum_attempts_per_window": 1, "retry_resume_permitted": False,
            "maximum_body_bytes_per_window": MAX_BODY_BYTES, "maximum_rows_per_window": MAX_ROWS,
            "timeout_seconds": TIMEOUT_SECONDS, "minimum_start_interval_seconds": START_INTERVAL_SECONDS,
            "financial_values_evaluated_or_projected": False,
            "credential_or_path_or_hash_retained": False, **{name: False for name in FALSE_FLAGS}}
        manifest_sha = _exclusive_json(directory, "manifest.json", manifest)
        published = {"manifest.json": manifest_sha}
        def check():
            _check_journal(root, parent, scopes, campaigns, directory, campaign_id, published, reserved, lock)
        check()
        results, prior_transport_finished = [], None
        for index, window in enumerate(windows):
            # A full interval after prior transport completion is stronger than
            # merely spacing caller entry; Git preflight latency cannot erode it.
            if transport is None and prior_transport_finished is not None:
                wait = START_INTERVAL_SECONDS - (time.monotonic() - prior_transport_finished)
                if wait > 0:
                    time.sleep(wait)
            _require(identity(expected_head, root=root) == baseline, "worktree_or_source_changed_before_transport")
            _require(_credential_file(token_path) == token, "private_token_file_changed")
            scope_name = _fingerprint(window) + ".json"
            try:
                scope_sha = _exclusive_json(scopes, scope_name, {"schema": SCHEMA,
                    "scope": _scope(window), "campaign_id": campaign_id,
                    "reserved_at_utc": clock(), "maximum_attempts": 1})
            except FileExistsError:
                raise EarningsCampaignError("completed_or_ambiguous_window_cannot_repeat") from None
            reserved[scope_name] = scope_sha
            prefix = f"window-{index:04d}"
            start_sha = _exclusive_json(directory, prefix + "-started.json", {"schema": SCHEMA,
                "window": list(window), "index": index, "started_at_utc": clock(),
                "manifest_sha256": manifest_sha, "scope_reservation_sha256": scope_sha,
                "maximum_attempts": 1})
            published[prefix + "-started.json"] = start_sha
            check()
            _require(identity(expected_head, root=root) == baseline, "worktree_or_source_changed_before_transport")
            _require(_credential_file(token_path) == token, "private_token_file_changed")
            try:
                response = transport(window) if transport is not None else _default_transport(window,
                    expected_head=expected_head, baseline=baseline, check=check, directory=directory,
                    index=index, manifest_sha=manifest_sha, scope_sha=scope_sha, token_path=token_path, token=token)
            except Exception:
                response = ProviderMetadataResponse(None, b"", False, "transport-error")
            prior_transport_finished = time.monotonic()
            check()
            receipt, projection = _receipt(response, window, token=token)
            _require(identity(expected_head, root=root) == baseline, "worktree_or_source_changed_after_transport")
            if projection is not None:
                name = prefix + "-response.json"
                fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(response.body)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.fsync(directory)
                published[name] = receipt["body_sha256"]
                published[prefix + "-metadata.json"] = _exclusive_json(directory, prefix + "-metadata.json", {
                    "schema": SCHEMA, "body_sha256": receipt["body_sha256"], "rows": projection})
                check()
            completed = {"schema": SCHEMA, "window": list(window), "index": index,
                "completed_at_utc": clock(), "manifest_sha256": manifest_sha,
                "started_sha256": start_sha, "scope_reservation_sha256": scope_sha, "receipt": receipt}
            published[prefix + "-complete.json"] = _exclusive_json(directory, prefix + "-complete.json", completed)
            results.append({"index": index, "window": list(window), "receipt": receipt,
                            "complete_sha256": published[prefix + "-complete.json"]})
            check()
            if progress is not None and (index + 1) % 10 == 0:
                progress({"completed_windows": len(results),
                    "observed_windows": sum(item["receipt"]["calendar_window_observed"] for item in results),
                    "source_rows": sum(item["receipt"]["sample_rows"] or 0 for item in results)})
            if not receipt["calendar_window_observed"]:
                break
        summary = {"schema": SCHEMA, "campaign_id": campaign_id, "completed_at_utc": clock(),
            "manifest_sha256": manifest_sha, "identity": baseline, "fixture_only": transport is not None,
            "planned_windows": len(windows), "transport_invocation_count": len(results),
            "observed_windows": sum(item["receipt"]["calendar_window_observed"] for item in results),
            "refused_or_ambiguous_windows": sum(not item["receipt"]["calendar_window_observed"] for item in results),
            "unattempted_windows": [list(window) for window in windows[len(results):]],
            "all_registered_windows_observed": len(results) == len(windows) and
                all(item["receipt"]["calendar_window_observed"] for item in results),
            "window_results": results, "credential_or_path_or_hash_retained": False,
            "looks_jobs_backtests": [0, 0, 0], **{name: False for name in FALSE_FLAGS}}
        published["complete.json"] = _exclusive_json(directory, "complete.json", summary)
        check()
        _require(identity(expected_head, root=root) == baseline, "worktree_or_source_changed_after_transport")
        # Public result omits row-level metadata, raw/financial values and secrets.
        return {"campaign_id": campaign_id, "complete_sha256": published["complete.json"],
            "fixture_only": transport is not None, "planned_windows": len(windows),
            "transport_invocation_count": len(results), "observed_windows": summary["observed_windows"],
            "refused_or_ambiguous_windows": summary["refused_or_ambiguous_windows"],
            "unattempted_windows_count": len(windows) - len(results),
            "all_registered_windows_observed": summary["all_registered_windows_observed"],
            "source_rows": sum(item["receipt"]["sample_rows"] or 0 for item in results),
            **{name: False for name in FALSE_FLAGS}}
    except EarningsCampaignError:
        raise
    except CalendarQualificationError as exc:
        raise EarningsCampaignError(str(exc)) from None
    except (OSError, ValueError, EodhdDemoError, subprocess.SubprocessError):
        raise EarningsCampaignError("private_journal_or_identity_operation_refused") from None
    finally:
        for fd in (directory, campaigns, scopes, lock, parent):
            if fd is not None:
                os.close(fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--token-file", required=True, type=Path)
    parser.add_argument("--owner-acknowledged-rotated-token", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run_campaign(args.campaign_id, args.expected_head, args.token_file,
            owner_acknowledged_rotated_token=args.owner_acknowledged_rotated_token,
            progress=lambda result: print(json.dumps({"campaign_progress": result}, sort_keys=True), flush=True))
    except EarningsCampaignError as exc:
        print(json.dumps({"campaign_refused": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["all_registered_windows_observed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
