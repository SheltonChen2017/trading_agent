"""Separately versioned unattempted-only Calendar continuation, not a resume.

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
import errno
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

from research import insider_buying_eodhd_earnings_continuation as legacy
from research import insider_buying_eodhd_earnings_continuation3 as predecessor
from research import insider_buying_eodhd_earnings_campaign as genesis
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
ARTIFACT_PARTS = ("artifacts", "insider_buying", "eodhd_earnings_continuation4")
SCHEMA = "insider-eodhd-date-window-earnings-continuation-v4"
OWNER_DIRECTION = "owner:2026-10-13:required-historical-earnings-continuous-build"
PROFILE = "eodhd-calendar-unattempted-only-20190301-20260731-v4"
PARTIAL_CAMPAIGN_ID = "ib-eodhd-campaign-continuation3-201809-202607-20261013-once"
PARTIAL_MANIFEST_SHA256 = "0b2f211f9c7d97b71ad01c6c8f7479ba7db31d67ba21ecc410645db62bb10990"
PARTIAL_EXECUTION_HEAD = "6849dec54ba10443097f7903f4a384f688a5ca41"
PARTIAL_SOURCE_INVENTORY_SHA256 = "5721b4ecb53035763130e366ac029f519ce27fa78fda69978f266da2ee2728b7"
OBSERVED_PARTIAL_WITNESS_SHA256 = "61d8c42efd26dbc04626cbe4eaeb599437dd496dec21827d5d38a24b66f32fa1"
WITNESS_SCHEMA = "independent-partial-calendar-v3-custody-witness-candidate-v1"
WITNESS_PARTS = ("artifacts", "insider_buying", "eodhd_earnings_partial_witness",
                 "ib-eodhd-v3-partial-201809-201902-20261013-once")
MAX_WITNESS_BYTES = 8192
_WITNESS_KEYS = frozenset({"schema", "observed_at_utc", "execution_head", "manifest_sha256", "campaign_id",
    "journal_leaf_count", "consumed_scope_count", "sealed_window_count", "unsealed_started_window_count",
    "campaign_completion_present", "unattempted_suffix_windows", "next_unattempted_window", "last_unattempted_window",
    "source_inventory_sha256", "previous_v2_complete_sha256", "previous_v2_manifest_sha256", "genesis_complete_sha256",
    "journal_leaf_sha256_and_bytes", "consumed_scope_sha256", "sealed_window_counts", "raw_financial_bodies_decoded",
    "paid_metadata_rows_decoded", "credential_read", "network_write_fork_denied", "locks_shared_read_only",
    "observed_failure_cause", "aggregate_completion_manufactured"})
MAX_BODY_BYTES = 16 * 1024 * 1024
MAX_METADATA_BYTES = 256 * 1024 * 1024
MAX_CONTROL_BYTES = 1024 * 1024
MAX_CAMPAIGN_CONTROL_LEAVES = 3  # manifest, aggregate, and safe failure journal
MIN_FREE_BYTES = 4 * 1024**3
MAX_ROWS = 200_000
MAX_WINDOWS = 89
START_INTERVAL_SECONDS = 1.0


def registered_windows() -> tuple[tuple[str, str], ...]:
    """Frozen supporting envelope, not a changed study or exact event bound."""
    result = []
    for year in range(2005, 2027):
        for month in range(1, 13):
            if (year, month) < (2019, 3) or (year, month) > (2026, 7):
                continue
            result.append((date(year, month, 1).isoformat(),
                           date(year, month, calendar.monthrange(year, month)[1]).isoformat()))
    return tuple(result)


REGISTERED_WINDOWS = registered_windows()
SOURCE_FILES = (
    "research/__init__.py",
    "research/insider_buying_eodhd_earnings_continuation4.py",
    "research/insider_buying_eodhd_earnings_continuation3.py",
    "research/insider_buying_eodhd_earnings_continuation.py",
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

    def __init__(self, code: str, *, failure: dict | None = None):
        super().__init__(code)
        self.failure = failure


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise EarningsCampaignError(code)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


_FAILURE_STAGES = frozenset({"preflight_identity", "credential_loading", "previous_anchor_preflight",
    "new_root_preflight", "manifest_publication", "current_journal_check", "previous_anchor_check",
    "window_disk_preflight", "before_transport_identity", "scope_reservation", "start_publication",
    "transport", "receipt_projection", "after_transport_identity", "response_publication",
    "metadata_publication", "window_seal_publication", "aggregate_publication", "final_identity"})
_FAILURE_CODES = frozenset({"private_journal_custody_refused", "previous_custody_changed_during_continuation",
    "clean_committed_lane_required", "source_or_git_identity_operation_refused", "worst_case_capture_disk_reserve_insufficient",
    "worktree_or_source_changed_before_transport", "worktree_or_source_changed_after_transport",
    "private_token_file_changed", "partial_previous_private_custody_refused", "partial_leaf_external_pin_mismatch",
    "partial_manifest_lineage_refused", "partial_consumed_start_scope_refused", "partial_sealed_window_chain_refused",
    "external_partial_witness_pin_mismatch", "external_partial_witness_pin_required", "partial_witness_schema_refused",
    "partial_witness_lineage_refused", "partial_witness_accounting_refused", "partial_witness_disposition_refused",
    "partial_witness_hash_inventory_refused", "partial_witness_named_root_detached", "partial_witness_leaf_inventory_refused",
    "partial_witness_owner_refused", "partial_unattempted_suffix_refused", "partial_global_interval_fence_refused",
    "partial_root_completion_or_leaf_inventory_refused", "previous_external_anchor_mismatch",
    "previous_private_custody_refused", "previous_leaf_inventory_refused", "legacy_interval_fence_refused",
    "previous_metadata_producer_anchor_mismatch", "custody_leaf_refused", "custody_leaf_changed",
    "immutable_json_byte_bound_exceeded", "projected_metadata_byte_bound_exceeded", "observed_partial_witness_pin_mismatch",
    "partial_sealed_row_accounting_refused", "partial_witness_changed_during_read", "private_token_file_refused"})


def _failure_details(exc: BaseException, stage: str, index: int | None) -> dict:
    """Whitelist-only diagnostics; never call str/repr on an exception."""
    classes = {EarningsCampaignError: "continuation4_error", predecessor.EarningsCampaignError: "continuation3_error",
        legacy.EarningsCampaignError: "continuation2_error", genesis.EarningsCampaignError: "genesis_error",
        EodhdDemoError: "custody_helper_error", CalendarQualificationError: "calendar_helper_error",
        OSError: "os_error", ValueError: "value_error", TypeError: "type_error", KeyError: "key_error",
        IndexError: "index_error", json.JSONDecodeError: "json_decode_error",
        subprocess.TimeoutExpired: "subprocess_timeout", subprocess.CalledProcessError: "subprocess_error"}
    exception_class = classes.get(type(exc), "os_error" if isinstance(exc, OSError) else "unclassified_exception")
    code = exc.args[0] if len(exc.args) == 1 and type(exc.args[0]) is str else None
    code = code if code in _FAILURE_CODES else "unclassified_failure"
    errno_codes = {errno.EIO: "io_error", errno.ENOSPC: "disk_full", errno.EDQUOT: "quota_exceeded",
        errno.EACCES: "access_denied", errno.EPERM: "operation_denied", errno.ENOENT: "missing_leaf",
        errno.EEXIST: "existing_leaf", errno.EINTR: "interrupted", errno.EAGAIN: "temporarily_unavailable"}
    error_number = errno_codes.get(exc.errno, "other_os_error") if isinstance(exc, OSError) else None
    return {"stage": stage if type(stage) is str and stage in _FAILURE_STAGES else "unclassified_stage",
            "exception_class": exception_class, "errno_class": error_number, "fixed_code": code,
            "active_window_index": index if type(index) is int and 0 <= index < MAX_WINDOWS else None}


def _record_failure(details: dict, *, root: Path, parent: int | None, scopes: int | None,
                    campaigns: int | None, directory: int | None, campaign_id: str,
                    published: dict, reserved: dict, lock: int | None, manifest_sha: str | None) -> dict:
    """Seal once only if current named journal custody can still be proved."""
    result = {**details, "failure_journal_sealed": False}
    if any(fd is None for fd in (parent, scopes, campaigns, directory, lock)):
        return result
    try:
        _check_journal(root, parent, scopes, campaigns, directory, campaign_id, published, reserved, lock)
        record = {"schema": SCHEMA, "kind": "sanitized_stage_failure", "campaign_id": campaign_id,
            "manifest_sha256": manifest_sha, **details,
            "consumed_scope_count": len(reserved), "window_completions": sum(name.endswith("-complete.json") for name in published),
            "aggregate_completion_manufactured": False, "exception_text_retained": False,
            "credential_path_body_or_values_retained": False, **{name: False for name in FALSE_FLAGS}}
        digest = _publish(directory, "failure.json", record)
        published["failure.json"] = digest
        _check_journal(root, parent, scopes, campaigns, directory, campaign_id, published, reserved, lock)
        result.update(failure_journal_sealed=True, failure_journal_sha256=digest)
    except Exception:
        # The original safe diagnostic is retained in the public exception;
        # an unsafe or interrupted journal is never repaired or overwritten.
        pass
    return result


def _publish(directory: int, name: str, value: dict) -> str:
    limit = MAX_METADATA_BYTES if name.endswith("-metadata.json") else MAX_CONTROL_BYTES
    _require(len(_canonical(value)) <= limit, "immutable_json_byte_bound_exceeded")
    return _exclusive_json(directory, name, value)


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
        _require(date(2019, 3, 1) <= start <= end <= date(2026, 7, 31),
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
        _require(_sha(_read_leaf(directory, name, limit=MAX_METADATA_BYTES if name.endswith("-metadata.json") else MAX_BODY_BYTES * 4)) == digest,
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


def _witness_directory(root: Path) -> int:
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for index, name in enumerate(WITNESS_PARTS):
            child = _directory(directory, name, create=False, private=index >= 2)
            os.close(directory)
            directory = child
        _require(os.fstat(directory).st_uid == os.geteuid(), "partial_witness_owner_refused")
        return directory
    except BaseException:
        os.close(directory)
        raise


def _witness(root: Path, held: int, expected_sha256: str, *, fixture_only: bool) -> dict:
    _require(type(expected_sha256) is str and re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is not None,
             "external_partial_witness_pin_required")
    _require(fixture_only or expected_sha256 == OBSERVED_PARTIAL_WITNESS_SHA256,
             "observed_partial_witness_pin_mismatch")
    reopened = _witness_directory(root)
    try:
        old, current = os.fstat(held), os.fstat(reopened)
        _require((old.st_dev, old.st_ino) == (current.st_dev, current.st_ino),
                 "partial_witness_named_root_detached")
        _require(set(os.listdir(held)) == {"witness.json"}, "partial_witness_leaf_inventory_refused")
        _require(os.stat("witness.json", dir_fd=held, follow_symlinks=False).st_uid == os.geteuid(),
                 "partial_witness_owner_refused")
        raw = _read_leaf(held, "witness.json", limit=MAX_WITNESS_BYTES)
        _require(_sha(raw) == expected_sha256, "external_partial_witness_pin_mismatch")
        body = json.loads(raw, object_pairs_hook=_unique)
        _require(type(body) is dict and set(body) == _WITNESS_KEYS and _canonical(body) == raw,
                 "partial_witness_schema_refused")
        _require(body["schema"] == WITNESS_SCHEMA and body["campaign_id"] == PARTIAL_CAMPAIGN_ID and
                 body["execution_head"] == PARTIAL_EXECUTION_HEAD and
                 body["manifest_sha256"] == PARTIAL_MANIFEST_SHA256 and
                 body["source_inventory_sha256"] == PARTIAL_SOURCE_INVENTORY_SHA256 and
                 body["previous_v2_complete_sha256"] == predecessor.PREVIOUS_COMPLETE_SHA256 and
                 body["previous_v2_manifest_sha256"] == predecessor.PREVIOUS_MANIFEST_SHA256 and
                 body["genesis_complete_sha256"] == legacy.PREVIOUS_COMPLETE_SHA256,
                 "partial_witness_lineage_refused")
        for name, count in (("journal_leaf_count", 24), ("consumed_scope_count", 6),
                            ("sealed_window_count", 5), ("unsealed_started_window_count", 1),
                            ("unattempted_suffix_windows", 89)):
            _require(type(body[name]) is int and body[name] == count, "partial_witness_accounting_refused")
        _require(body["campaign_completion_present"] is False and body["aggregate_completion_manufactured"] is False and
                 body["raw_financial_bodies_decoded"] is False and body["paid_metadata_rows_decoded"] is False and
                 body["credential_read"] is False and body["network_write_fork_denied"] is True and
                 body["locks_shared_read_only"] is True and
                 body["observed_failure_cause"] == "not_established_by_retained_controls" and
                 body["next_unattempted_window"] == list(REGISTERED_WINDOWS[0]) and
                 body["last_unattempted_window"] == list(REGISTERED_WINDOWS[-1]) and
                 type(body["observed_at_utc"]) is str and re.fullmatch(r"[0-9TZ:.+-]{1,40}", body["observed_at_utc"]) is not None,
                 "partial_witness_disposition_refused")
        leaves, scopes = body["journal_leaf_sha256_and_bytes"], body["consumed_scope_sha256"]
        _require(type(leaves) is dict and len(leaves) == 24 and type(scopes) is dict and len(scopes) == 6,
                 "partial_witness_hash_inventory_refused")
        for name, item in leaves.items():
            _require(type(name) is str and re.fullmatch(r"(?:manifest|window-[0-9]{4}-(?:started|complete|response|metadata))\.json", name) is not None and
                     type(item) is dict and set(item) == {"sha256", "bytes"} and
                     type(item["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is not None and
                     type(item["bytes"]) is int and 0 < item["bytes"] <=
                     (MAX_METADATA_BYTES if name.endswith("-metadata.json") else MAX_BODY_BYTES if name.endswith("-response.json") else MAX_CONTROL_BYTES),
                     "partial_witness_hash_inventory_refused")
        for name, digest in scopes.items():
            _require(type(name) is str and re.fullmatch(r"[0-9a-f]{64}\.json", name) is not None and
                     type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
                     "partial_witness_hash_inventory_refused")
        return body
    finally:
        os.close(reopened)


def _previous_anchor(root: Path, windows: tuple[tuple[str, str], ...], legacy_lock: int, genesis_lock: int,
                     partial_lock: int, witness_directory: int, expected_witness_sha256: str,
                     *, fixture_only: bool) -> dict:
    """Validate the partial root without decoding old financial/metadata rows."""
    parent = campaigns = directory = scopes = None
    try:
        witness = _witness(root, witness_directory, expected_witness_sha256, fixture_only=fixture_only)
        v2_anchor = predecessor._previous_anchor(root, windows, legacy_lock, genesis_lock, fixture_only=fixture_only)
        parent = predecessor._root_directory(root, create=False)
        campaigns = _directory(parent, "campaigns", create=False)
        scopes = _directory(parent, "scopes", create=False)
        directory = _directory(campaigns, PARTIAL_CAMPAIGN_ID, create=False)
        leaves = witness["journal_leaf_sha256_and_bytes"]
        expected_names = {"manifest.json"}
        for index in range(6):
            expected_names.update({f"window-{index:04d}-" + kind + ".json" for kind in ("started", "response", "metadata")})
            if index < 5:
                expected_names.add(f"window-{index:04d}-complete.json")
        _require(set(leaves) == expected_names and set(os.listdir(directory)) == expected_names,
                 "partial_root_completion_or_leaf_inventory_refused")
        leaf_hashes = {}
        for name, item in leaves.items():
            raw = _read_leaf(directory, name, limit=MAX_METADATA_BYTES if name.endswith("-metadata.json") else MAX_BODY_BYTES)
            _require(len(raw) == item["bytes"] and _sha(raw) == item["sha256"], "partial_leaf_external_pin_mismatch")
            leaf_hashes[name] = item["sha256"]
        manifest = json.loads(_read_leaf(directory, "manifest.json", limit=MAX_CONTROL_BYTES), object_pairs_hook=_unique)
        _require(leaf_hashes["manifest.json"] == PARTIAL_MANIFEST_SHA256 and
                 manifest["schema"] == predecessor.SCHEMA and manifest["profile"] == predecessor.PROFILE and
                 manifest["campaign_id"] == PARTIAL_CAMPAIGN_ID and
                 manifest["identity"]["head"] == PARTIAL_EXECUTION_HEAD and
                 manifest["identity"]["source_inventory_sha256"] == PARTIAL_SOURCE_INVENTORY_SHA256 and
                 manifest["previous_campaign_anchor"] == v2_anchor and
                 manifest["windows"] == [list(w) for w in predecessor.REGISTERED_WINDOWS] and
                 manifest["window_scope_sha256"] == [predecessor._fingerprint(w) for w in predecessor.REGISTERED_WINDOWS] and
                 manifest["maximum_attempts_per_window"] == 1 and manifest["retry_resume_permitted"] is False and
                 (fixture_only or manifest["fixture_only"] is False) and
                 all(manifest[name] is False for name in FALSE_FLAGS),
                 "partial_manifest_lineage_refused")
        _require(REGISTERED_WINDOWS == predecessor.REGISTERED_WINDOWS[6:] and
                 all(w in REGISTERED_WINDOWS for w in windows), "partial_unattempted_suffix_refused")
        _require(predecessor._prior_scopes(scopes, windows) == witness["consumed_scope_sha256"],
                 "partial_global_interval_fence_refused")
        for index in range(6):
            prefix = f"window-{index:04d}"
            window = predecessor.REGISTERED_WINDOWS[index]
            start = json.loads(_read_leaf(directory, prefix + "-started.json", limit=MAX_CONTROL_BYTES), object_pairs_hook=_unique)
            scope_name = predecessor._fingerprint(window) + ".json"
            scope_raw = _read_leaf(scopes, scope_name, limit=MAX_CONTROL_BYTES)
            _require(_sha(scope_raw) == witness["consumed_scope_sha256"][scope_name], "partial_scope_external_pin_mismatch")
            scope = json.loads(scope_raw, object_pairs_hook=_unique)
            _require(start["schema"] == predecessor.SCHEMA and start["index"] == index and
                     start["window"] == list(window) and start["manifest_sha256"] == PARTIAL_MANIFEST_SHA256 and
                     start["maximum_attempts"] == 1 and start["scope_reservation_sha256"] == _sha(scope_raw) and
                     scope["schema"] == predecessor.SCHEMA and scope["campaign_id"] == PARTIAL_CAMPAIGN_ID and
                     scope["scope"] == predecessor._scope(window) and scope["maximum_attempts"] == 1,
                     "partial_consumed_start_scope_refused")
            if index < 5:
                done_raw = _read_leaf(directory, prefix + "-complete.json", limit=MAX_CONTROL_BYTES)
                done = json.loads(done_raw, object_pairs_hook=_unique)
                receipt = done["receipt"]
                _require(done["schema"] == predecessor.SCHEMA and done["index"] == index and
                         done["window"] == list(window) and done["manifest_sha256"] == PARTIAL_MANIFEST_SHA256 and
                         done["started_sha256"] == leaf_hashes[prefix + "-started.json"] and
                         done["scope_reservation_sha256"] == _sha(scope_raw) and
                         receipt["http_status"] == 200 and receipt["transport_invocation_count"] == 1 and
                         receipt["calendar_window_observed"] is True and receipt["response_body_retained"] is True and
                         receipt["body_sha256"] == leaf_hashes[prefix + "-response.json"] and
                         receipt["body_size_bytes"] == leaves[prefix + "-response.json"]["bytes"] and
                         receipt["metadata_sha256"] == leaf_hashes[prefix + "-metadata.json"] and
                         all(receipt[name] is False for name in FALSE_FLAGS), "partial_sealed_window_chain_refused")
                expected_count = {"index": index, "window": list(window), "complete_sha256": _sha(done_raw),
                    **{name: receipt[name] for name in ("sample_rows", "metadata_accepted_rows", "quarantined_rows")}}
                _require(witness["sealed_window_counts"][index] == expected_count and
                         all(type(receipt[name]) is int and receipt[name] >= 0 for name in
                             ("sample_rows", "metadata_accepted_rows", "quarantined_rows")) and
                         receipt["metadata_accepted_rows"] + receipt["quarantined_rows"] == receipt["sample_rows"],
                         "partial_sealed_row_accounting_refused")
        _require(type(witness["sealed_window_counts"]) is list and len(witness["sealed_window_counts"]) == 5,
                 "partial_sealed_row_accounting_refused")
        predecessor._check_journal(root, parent, scopes, campaigns, directory, PARTIAL_CAMPAIGN_ID,
                                   leaf_hashes, witness["consumed_scope_sha256"], partial_lock)
        _require(_witness(root, witness_directory, expected_witness_sha256, fixture_only=fixture_only) == witness,
                 "partial_witness_changed_during_read")
        return {"partial_witness_sha256": expected_witness_sha256, "campaign_id": PARTIAL_CAMPAIGN_ID,
            "manifest_sha256": PARTIAL_MANIFEST_SHA256, "execution_head": PARTIAL_EXECUTION_HEAD,
            "source_inventory_sha256": PARTIAL_SOURCE_INVENTORY_SHA256,
            "journal_leaf_sha256_and_bytes": leaves, "scope_sha256": witness["consumed_scope_sha256"],
            "consumed_window_starts": 6, "sealed_windows": 5, "unsealed_started_windows": 1,
            "aggregate_completion_present": False, "historical_failure_cause_established": False,
            "registered_unattempted_windows": [list(w) for w in REGISTERED_WINDOWS],
            "previous_v2_campaign_anchor": v2_anchor,
            "old_root_resumed_or_written": False, "old_raw_financial_or_metadata_rows_decoded": False}
    except EarningsCampaignError:
        raise
    except (OSError, ValueError, TypeError, KeyError, IndexError, EodhdDemoError):
        # Let the outer whitelist classifier retain low-level class/errno.
        raise
    finally:
        for fd in (directory, scopes, campaigns, parent):
            if fd is not None:
                os.close(fd)

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
            reasons = []
            metadata = {"source_row_ordinal": ordinal, "metadata_accepted": False,
                "quarantine_reasons": reasons, "code": None, "report_date": None,
                "fiscal_date": None, "before_after_market": None,
                "current_provider_reported_status": "unknown"}
            if type(row) is not dict:
                reasons.append("source_row_not_object")
                projection.append(metadata)
                continue
            if set(row) != _ROW_FIELDS:
                reasons.append("source_row_field_shape_unknown")
            code = row.get("code")
            if type(code) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}\.[A-Za-z0-9]{1,12}", code) is not None:
                metadata["code"] = code
            else:
                reasons.append("source_code_unknown")
            report = fiscal = None
            for source_name, projected_name in (("report_date", "report_date"), ("date", "fiscal_date")):
                try:
                    parsed = _date(row.get(source_name))
                    metadata[projected_name] = parsed.isoformat()
                    if source_name == "report_date":
                        report = parsed
                    else:
                        fiscal = parsed
                except CalendarQualificationError:
                    reasons.append("source_" + projected_name + "_unknown")
            if report is not None and not date.fromisoformat(window[0]) <= report <= date.fromisoformat(window[1]):
                reasons.append("report_date_outside_registered_scope")
            if fiscal is not None and report is not None and fiscal > report:
                reasons.append("fiscal_date_after_report_date")
            timing = row.get("before_after_market")
            if type(timing) is str and timing in {"BeforeMarket", "AfterMarket"}:
                metadata["before_after_market"] = timing
            else:
                reasons.append("source_timing_unknown")
            if any(name not in row or (row[name] is not None and row[name] is not _NUMBER) for name in _FINANCIAL):
                reasons.append("source_financial_shape_unknown")
            if row.get("actual") is _NUMBER:
                metadata["current_provider_reported_status"] = "reported"
            else:
                reasons.append("current_provider_reported_status_unknown")
            # Currency is not part of either prescribed earnings diagnostic.
            # Its unprojected value is never validated, converted or inferred.
            metadata["metadata_accepted"] = not reasons
            projection.append(metadata)
        # Preserve exact source order/ordinal, including every invalid row.
        return projection
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
        if row["code"] is not None and row["fiscal_date"] is not None:
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
        "metadata_sha256": None,  # Bound only after exclusive publication.
        "body_size_bytes": len(response.body) if success else None,
        "response_body_retained": success, "untrusted_error_body_hashed_or_retained": False,
        "financial_values_evaluated_or_projected": False,
        "sample_rows": len(projection) if success else None,
        "metadata_accepted_rows": sum(row["metadata_accepted"] for row in projection) if success else None,
        "quarantined_rows": sum(not row["metadata_accepted"] for row in projection) if success else None,
        "all_rows_retained_in_source_order": success,
        "nonessential_currency_projected_or_inferred": False,
        "duplicate_fiscal_period_rows": duplicate_rows if success else None,
        "metadata_conflicting_fiscal_periods": conflicting_periods if success else None,
        "duplicate_or_conflicting_rows_deduplicated": False,
        "reported_rows": sum(row["current_provider_reported_status"] == "reported" for row in projection) if success else None,
        "unknown_status_rows": sum(row["current_provider_reported_status"] == "unknown" for row in projection) if success else None,
        "timing_unknown_rows": sum(row["before_after_market"] is None for row in projection) if success else None,
        "empty_result_is_coverage_evidence": False, **{name: False for name in FALSE_FLAGS}}, projection


def _read_window_bounded(stream, status: int) -> ProviderMetadataResponse:
    """Versioned 16MiB bound; older executed transport bytes are untouched."""
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


def _disk_reserve(directory: int, remaining_windows: int) -> dict:
    campaign_controls = MAX_CAMPAIGN_CONTROL_LEAVES * MAX_CONTROL_BYTES
    budget = remaining_windows * (MAX_BODY_BYTES + MAX_METADATA_BYTES + 3 * MAX_CONTROL_BYTES) + campaign_controls
    info = os.fstatvfs(directory)
    available = info.f_bavail * info.f_frsize
    _require(available >= MIN_FREE_BYTES + budget, "worst_case_capture_disk_reserve_insufficient")
    return {"worst_case_remaining_capture_bytes": budget, "minimum_free_bytes": MIN_FREE_BYTES,
            "campaign_control_headroom_bytes": campaign_controls,
            "available_bytes_at_preflight": available}


def run_continuation(campaign_id: str, expected_head: str, token_path: Path, *, windows: tuple | None = None,
                 owner_acknowledged_rotated_token: bool, expected_partial_witness_sha256: str, root: Path = LANE_ROOT,
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
    _require(type(expected_partial_witness_sha256) is str and
             re.fullmatch(r"[0-9a-f]{64}", expected_partial_witness_sha256) is not None,
             "external_partial_witness_pin_required")
    _require(transport is not _default_transport and
             (transport is not None or (identity is _identity and root == LANE_ROOT)),
             "real_transport_requires_real_lane_identity")
    _require(transport is not None or windows == REGISTERED_WINDOWS,
             "real_transport_requires_exact_frozen_monthly_manifest")
    parent = scopes = campaigns = directory = lock = legacy_lock = legacy_parent = genesis_lock = genesis_parent = partial_parent = partial_lock = witness_directory = None
    stage, active_index, published, reserved, manifest_sha = "preflight_identity", None, {}, {}, None
    try:
        baseline = identity(expected_head, root=root)
        stage = "credential_loading"
        token = _credential_file(token_path)
        genesis_parent = genesis._root_directory(root, create=False)
        genesis_lock = os.open("campaign.lock", os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=genesis_parent)
        try:
            fcntl.flock(genesis_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise EarningsCampaignError("genesis_concurrent_campaign_refused") from None
        legacy_parent = legacy._root_directory(root, create=False)
        legacy_lock = os.open("campaign.lock", os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=legacy_parent)
        try:
            fcntl.flock(legacy_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise EarningsCampaignError("legacy_concurrent_campaign_refused") from None
        partial_parent = predecessor._root_directory(root, create=False)
        partial_lock = os.open("campaign.lock", os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=partial_parent)
        try:
            fcntl.flock(partial_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise EarningsCampaignError("partial_concurrent_campaign_refused") from None
        witness_directory = _witness_directory(root)
        stage = "previous_anchor_preflight"
        previous = _previous_anchor(root, windows, legacy_lock, genesis_lock, partial_lock, witness_directory,
                                    expected_partial_witness_sha256, fixture_only=transport is not None)
        stage = "new_root_preflight"
        _disk_reserve(legacy_parent, len(windows))
        parent = _root_directory(root, create=True)
        disk = _disk_reserve(parent, len(windows))
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
            "previous_campaign_anchor": previous,
            "window_scope_sha256": [_fingerprint(window) for window in windows],
            "owner_direction": OWNER_DIRECTION, "owner_acknowledged_rotated_token": True,
            "rotation_independently_verified": False, "fixture_only": transport is not None,
            "maximum_attempts_per_window": 1, "retry_resume_permitted": False,
            "maximum_body_bytes_per_window": MAX_BODY_BYTES, "maximum_rows_per_window": MAX_ROWS,
            "maximum_metadata_bytes_per_window": MAX_METADATA_BYTES,
            "maximum_control_bytes_per_leaf": MAX_CONTROL_BYTES, "disk_preflight": disk,
            "timeout_seconds": TIMEOUT_SECONDS, "minimum_start_interval_seconds": START_INTERVAL_SECONDS,
            "financial_values_evaluated_or_projected": False,
            "credential_or_path_or_hash_retained": False, **{name: False for name in FALSE_FLAGS}}
        stage = "manifest_publication"
        manifest_sha = _publish(directory, "manifest.json", manifest)
        published = {"manifest.json": manifest_sha}
        def check():
            nonlocal stage
            stage = "current_journal_check"
            _check_journal(root, parent, scopes, campaigns, directory, campaign_id, published, reserved, lock)
            stage = "previous_anchor_check"
            _require(_previous_anchor(root, windows, legacy_lock, genesis_lock, partial_lock, witness_directory, expected_partial_witness_sha256, fixture_only=transport is not None) == previous,
                     "previous_custody_changed_during_continuation")
        check()
        results, prior_transport_finished = [], None
        for index, window in enumerate(windows):
            active_index, stage = index, "window_disk_preflight"
            _disk_reserve(parent, len(windows) - index)
            # A full interval after prior transport completion is stronger than
            # merely spacing caller entry; Git preflight latency cannot erode it.
            if transport is None and prior_transport_finished is not None:
                wait = START_INTERVAL_SECONDS - (time.monotonic() - prior_transport_finished)
                if wait > 0:
                    time.sleep(wait)
            stage = "before_transport_identity"
            _require(identity(expected_head, root=root) == baseline, "worktree_or_source_changed_before_transport")
            _require(_credential_file(token_path) == token, "private_token_file_changed")
            scope_name = _fingerprint(window) + ".json"
            stage = "scope_reservation"
            try:
                scope_sha = _publish(scopes, scope_name, {"schema": SCHEMA,
                    "scope": _scope(window), "campaign_id": campaign_id,
                    "reserved_at_utc": clock(), "maximum_attempts": 1})
            except FileExistsError:
                raise EarningsCampaignError("completed_or_ambiguous_window_cannot_repeat") from None
            reserved[scope_name] = scope_sha
            prefix = f"window-{index:04d}"
            stage = "start_publication"
            start_sha = _publish(directory, prefix + "-started.json", {"schema": SCHEMA,
                "window": list(window), "index": index, "started_at_utc": clock(),
                "manifest_sha256": manifest_sha, "scope_reservation_sha256": scope_sha,
                "maximum_attempts": 1})
            published[prefix + "-started.json"] = start_sha
            check()
            stage = "before_transport_identity"
            _require(identity(expected_head, root=root) == baseline, "worktree_or_source_changed_before_transport")
            _require(_credential_file(token_path) == token, "private_token_file_changed")
            try:
                stage = "transport"
                response = transport(window) if transport is not None else _default_transport(window,
                    expected_head=expected_head, baseline=baseline, check=check, directory=directory,
                    index=index, manifest_sha=manifest_sha, scope_sha=scope_sha, token_path=token_path, token=token)
            except Exception:
                response = ProviderMetadataResponse(None, b"", False, "transport-error")
            prior_transport_finished = time.monotonic()
            check()
            stage = "receipt_projection"
            receipt, projection = _receipt(response, window, token=token)
            stage = "after_transport_identity"
            _require(identity(expected_head, root=root) == baseline, "worktree_or_source_changed_after_transport")
            if projection is not None:
                stage = "response_publication"
                name = prefix + "-response.json"
                fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(response.body)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.fsync(directory)
                published[name] = receipt["body_sha256"]
                metadata = {
                    "schema": SCHEMA, "body_sha256": receipt["body_sha256"], "rows": projection,
                    "metadata_acceptance_is_source_coverage_or_identity_admission": False}
                _require(len(_canonical(metadata)) <= MAX_METADATA_BYTES, "projected_metadata_byte_bound_exceeded")
                stage = "metadata_publication"
                published[prefix + "-metadata.json"] = _publish(directory, prefix + "-metadata.json", metadata)
                receipt["metadata_sha256"] = published[prefix + "-metadata.json"]
                check()
            completed = {"schema": SCHEMA, "window": list(window), "index": index,
                "completed_at_utc": clock(), "manifest_sha256": manifest_sha,
                "started_sha256": start_sha, "scope_reservation_sha256": scope_sha, "receipt": receipt}
            stage = "window_seal_publication"
            published[prefix + "-complete.json"] = _publish(directory, prefix + "-complete.json", completed)
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
            "previous_campaign_anchor": previous,
            "planned_windows": len(windows), "transport_invocation_count": len(results),
            "observed_windows": sum(item["receipt"]["calendar_window_observed"] for item in results),
            "refused_or_ambiguous_windows": sum(not item["receipt"]["calendar_window_observed"] for item in results),
            "unattempted_windows": [list(window) for window in windows[len(results):]],
            "all_registered_windows_observed": len(results) == len(windows) and
                all(item["receipt"]["calendar_window_observed"] for item in results),
            "window_results": results, "credential_or_path_or_hash_retained": False,
            "source_rows": sum(item["receipt"]["sample_rows"] or 0 for item in results),
            "metadata_accepted_rows": sum(item["receipt"]["metadata_accepted_rows"] or 0 for item in results),
            "quarantined_rows": sum(item["receipt"]["quarantined_rows"] or 0 for item in results),
            "looks_jobs_backtests": [0, 0, 0], **{name: False for name in FALSE_FLAGS}}
        stage = "aggregate_publication"
        published["complete.json"] = _publish(directory, "complete.json", summary)
        check()
        stage = "final_identity"
        _require(identity(expected_head, root=root) == baseline, "worktree_or_source_changed_after_transport")
        # Public result omits row-level metadata, raw/financial values and secrets.
        return {"campaign_id": campaign_id, "complete_sha256": published["complete.json"],
            "fixture_only": transport is not None, "planned_windows": len(windows),
            "transport_invocation_count": len(results), "observed_windows": summary["observed_windows"],
            "refused_or_ambiguous_windows": summary["refused_or_ambiguous_windows"],
            "unattempted_windows_count": len(windows) - len(results),
            "all_registered_windows_observed": summary["all_registered_windows_observed"],
            "source_rows": sum(item["receipt"]["sample_rows"] or 0 for item in results),
            "metadata_accepted_rows": summary["metadata_accepted_rows"],
            "quarantined_rows": summary["quarantined_rows"],
            "previous_partial_witness_sha256": expected_partial_witness_sha256,
            **{name: False for name in FALSE_FLAGS}}
    except Exception as exc:
        failure = _record_failure(_failure_details(exc, stage, active_index), root=root, parent=parent,
            scopes=scopes, campaigns=campaigns, directory=directory, campaign_id=campaign_id,
            published=published, reserved=reserved, lock=lock, manifest_sha=manifest_sha)
        raise EarningsCampaignError("continuation_stage_failure", failure=failure) from None
    finally:
        for fd in (directory, campaigns, scopes, lock, parent, legacy_lock, legacy_parent, genesis_lock, genesis_parent, partial_lock, partial_parent, witness_directory):
            if fd is not None:
                os.close(fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--token-file", required=True, type=Path)
    parser.add_argument("--expected-partial-witness-sha256", required=True)
    parser.add_argument("--owner-acknowledged-rotated-token", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run_continuation(args.campaign_id, args.expected_head, args.token_file,
            owner_acknowledged_rotated_token=args.owner_acknowledged_rotated_token,
            expected_partial_witness_sha256=args.expected_partial_witness_sha256,
            progress=lambda result: print(json.dumps({"campaign_progress": result}, sort_keys=True), flush=True))
    except EarningsCampaignError as exc:
        # Outside-actor argument refusals are fixed local codes too; never
        # expose arbitrary exception strings from inside the acquisition.
        code = exc.args[0] if type(exc.args[0]) is str else "unclassified_failure"
        print(json.dumps({"campaign_refused": code, "sanitized_failure": exc.failure}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["all_registered_windows_observed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
