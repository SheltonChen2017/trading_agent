"""Two one-shot Sharadar reference-file status requests, not archive ingestion.

The owner supplied the Sharadar Keychain service/account on 2026-10-13 and
directed continued lane building. These fixed metadata-only scopes measure
current TICKERS status and provider-reported full-history ACTIONS availability.
They request no source table rows, fundamentals, price data or outcomes. Neither
successful status nor credential presence establishes entitlement, applicable
rights, historical identity/PIT, corpus completion, QC or backtest readiness.

The production CLI requires a clean exact committed lane, inventories every
reachable internal source, reserves both scopes globally before reading the
Keychain, and seals starts before dispatch. No retry, resume, redirect, proxy or
fallback source exists. Tests must deny the entire process-tree network and use
invented credential readers/transports; injected runs cannot claim production.

The owner's separate 2026-10-24 investigation selects --diagnostic: one new
fixed successor scope, binding the preserved section203 refusal. It does not
reset v1. A rejected complete HTTP200 body may yield only bounded structural
types/counts/fixed enums after credential screening; no rejected raw body,
arbitrary key/value text or body hash is published. Success stays strict.
The separately preregistered --verify-correction mode binds both consumed
predecessors in a third fixed namespace and admits the observed one-file
TICKERS wrapper only with an exact validated snapshot descriptor. No mode
can resume another mode's reservation or select a URL/provider/credential.
After that exact-descriptor candidate also refused, --verify-final uses one
fourth fixed scope: the four core snapshot fields remain mandatory, and
each of the three known ancillary fields is optional but strictly checked
when present. No absent history or availability is synthesized. Earlier
modes retain their preceding contracts; all consumed publications are pinned.
The separately registered --verify-catalogue scope additionally validates
only the official public bulk client's key/canDownload fields. A key must
be a safe relative lookup path ending in the canonical filename, never a
URL or API credential, and is never emitted by the projection. No presign,
download or arbitrary-extra-field acceptance exists.
Finally, --verify-actions registers only the still-unqualified ACTIONS
inventory request. It reuses the sealed successful TICKERS observation,
validates every advertised history and selects exactly one full-history
file, crosschecking any top-level selected-file metadata. It never repeats
the successful TICKERS request or falls back to a shorter history.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import ssl
import stat
import subprocess
from types import MappingProxyType
from typing import Callable
from urllib import error, request
from urllib.parse import unquote, unquote_plus

from research.insider_buying_eodhd_earnings_demo import EodhdDemoError, FALSE_FLAGS, _git, _read_leaf, _sha
from research.insider_buying_keychain_credentials import KeychainCredential, KeychainCredentialError, read_keychain_credential
from research.insider_buying_provider_metadata_audit import _exclusive_json, _now
from research.insider_buying_provider_metadata_transport import (
    MAX_BODY_BYTES, TIMEOUT_SECONDS, ProviderMetadataResponse, _DenyRedirect, _read_bounded,
)


LANE_ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying")
LANE_BRANCH = "codex/strategy-insider-buying"
ARTIFACT_PARTS = ("artifacts", "insider_buying", "sharadar_reference_qualification")
SCHEMA = "insider-sharadar-reference-status-one-shot-v1"
OWNER_DIRECTION = "owner:2026-10-13:keychain-provider-configuration-and-continuous-lane-build"
DIAGNOSTIC_ARTIFACT_PARTS = ("artifacts", "insider_buying", "sharadar_reference_diagnostic_v2")
DIAGNOSTIC_SCHEMA = "insider-sharadar-reference-status-diagnostic-v2"
DIAGNOSTIC_OWNER_DIRECTION = "owner:2026-10-24:investigate-sharadar-format-and-continue-coverage-audit-no-qc"
PREDECESSOR_AUDIT = "ib-sharadar-reference-20261024-access-once"
PREDECESSOR_COMPLETE_SHA = "d0da5b96b9c41bfd66f89d19c0c7979dac4f4f1bcab1ecf1fe784531a8d85594"
PREDECESSOR_SCOPE_SHA = "ed5045a36be8db8478d8da1d66b362e33ac4e41796f5982bafd3341b9add19c2"
CORRECTION_ARTIFACT_PARTS = ("artifacts", "insider_buying", "sharadar_reference_correction_v3")
CORRECTION_SCHEMA = "insider-sharadar-reference-status-correction-v3"
DIAGNOSTIC_COMPLETE_SHA = "59a3031b18848b5c1d78e7090b7078f086d3bded71dbf215b1be0bdae06fbfb2"
DIAGNOSTIC_SCOPE_SHA = "78d9f9c93b659af2cd69508edc79b7b195e97910150bc2390c184795187dd9ed"
FINAL_ARTIFACT_PARTS = ("artifacts", "insider_buying", "sharadar_reference_final_v4")
FINAL_SCHEMA = "insider-sharadar-reference-status-final-v4"
CORRECTION_COMPLETE_SHA = "bec43f96fc970f135339cd70d749bff163b1493a3d8f34e1108397ff0fe5eab1"
CORRECTION_SCOPE_SHA = "2fd418c8603c7cbe1b1e16980acd60ef575128e2bdfbb974e2b9f4812064fa69"
CATALOGUE_ARTIFACT_PARTS = ("artifacts", "insider_buying", "sharadar_reference_catalogue_v5")
CATALOGUE_SCHEMA = "insider-sharadar-reference-status-catalogue-v5"
FINAL_COMPLETE_SHA = "d29b614ca4b0a72c52f68c3d26aa52904fce8520a1e380dd4e8398e608912001"
FINAL_SCOPE_SHA = "54a70900190a1d236dce0755febd41c1402dfe831294e56694d17fc54c268c63"
ACTIONS_ARTIFACT_PARTS = ("artifacts", "insider_buying", "sharadar_actions_inventory_v6")
ACTIONS_SCHEMA = "insider-sharadar-actions-inventory-status-v6"
CATALOGUE_COMPLETE_SHA = "1ef40d4657dd726b05fb3d8b369cab3a4f62b5f4f880da5345d14cd245f1e576"
CATALOGUE_SCOPE_SHA = "cf6aa3d7d302bb0de78f7b4060e295e52c3dc615b165f15982ffe3fda9c6ae69"
PROFILES = MappingProxyType({
    "tickers": ("sharadar-tickers-current-reference-file-status-v1",
                "https://api.sharadar.com/v1.0/data/tickers?status=True"),
    "actions": ("sharadar-actions-full-history-reference-file-status-v1",
                "https://api.sharadar.com/v1.0/data/actions?status=True&years=full"),
})
SOURCE_FILES = (
    "research/__init__.py",
    "research/insider_buying_sharadar_reference_qualification.py",
    "research/insider_buying_keychain_credentials.py",
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
_KEYCHAIN_CODES = frozenset({
    "keychain_provider_refused", "macos_keychain_required", "keychain_process_factory_refused",
    "keychain_process_refused", "keychain_read_timeout", "keychain_item_missing",
    "keychain_access_unavailable", "keychain_read_refused", "keychain_output_oversized",
    "keychain_credential_refused", "keychain_operation_refused", "keychain_process_cleanup_refused",
})
_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)\Z")
_SIZE_LABEL = re.compile(r"[0-9]{1,20}(?:\.[0-9]{1,2})? (?:B|KB|MB|GB|TB)\Z")
MAX_CREDENTIAL_DECODE_STEPS = 8


class SharadarReferenceQualificationError(ValueError):
    """Fixed local refusal codes; never supplied names, secrets or HTTP text."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise SharadarReferenceQualificationError(code)


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
        raise SharadarReferenceQualificationError("source_or_git_identity_operation_refused") from None
    encoded = json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()
    return {"root": actual_root, "branch": branch, "head": head, "source_sha256": inventory,
            "source_inventory_sha256": _sha(encoded), "clean": True}


def _mkdir_chain(root: Path, *, create: bool = True, diagnostic: bool = False,
                 correction: bool = False, final: bool = False, catalogue: bool = False,
                 actions_only: bool = False) -> int:
    _require(type(diagnostic) is bool, "diagnostic_mode_refused")
    _require(type(correction) is bool and (not correction or diagnostic), "correction_mode_refused")
    _require(type(final) is bool and (not final or correction), "final_mode_refused")
    _require(type(catalogue) is bool and (not catalogue or final), "catalogue_mode_refused")
    _require(type(actions_only) is bool and (not actions_only or catalogue), "actions_mode_refused")
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parts = ACTIONS_ARTIFACT_PARTS if actions_only else CATALOGUE_ARTIFACT_PARTS if catalogue else FINAL_ARTIFACT_PARTS if final else CORRECTION_ARTIFACT_PARTS if correction else DIAGNOSTIC_ARTIFACT_PARTS if diagnostic else ARTIFACT_PARTS
        for name in parts:
            if create:
                try:
                    os.mkdir(name, 0o700, dir_fd=descriptor)
                    os.fsync(descriptor)
                except FileExistsError:
                    pass
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        info = os.fstat(descriptor)
        _require(stat.S_IMODE(info.st_mode) == 0o700 and info.st_uid == os.geteuid(),
                 "private_scope_directory_required")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _check_journal(parent: int, directory: int, audit_id: str, latch_sha: str,
                   published: dict[str, str], *, root: Path, diagnostic: bool = False,
                   correction: bool = False, final: bool = False, catalogue: bool = False,
                   actions_only: bool = False) -> None:
    def attached():
        current = _mkdir_chain(root, create=False, diagnostic=diagnostic, correction=correction, final=final,
                                catalogue=catalogue, actions_only=actions_only)
        try:
            named_parent, held_parent = os.fstat(current), os.fstat(parent)
            _require((named_parent.st_dev, named_parent.st_ino) == (held_parent.st_dev, held_parent.st_ino)
                     and set(os.listdir(current)) == {"scope-reservation.json", audit_id},
                     "private_journal_custody_refused")
            named = os.stat(audit_id, dir_fd=current, follow_symlinks=False)
            held = os.fstat(directory)
            _require(stat.S_ISDIR(named.st_mode) and stat.S_IMODE(named.st_mode) == 0o700
                     and named.st_uid == os.geteuid()
                     and (named.st_dev, named.st_ino) == (held.st_dev, held.st_ino)
                     and set(os.listdir(directory)) == set(published), "private_journal_custody_refused")
        finally:
            os.close(current)
    try:
        attached()
        _require(_sha(_read_leaf(parent, "scope-reservation.json", limit=4 * MAX_BODY_BYTES)) == latch_sha,
                 "private_journal_custody_refused")
        for name, digest in published.items():
            _require(_sha(_read_leaf(directory, name, limit=4 * MAX_BODY_BYTES)) == digest,
                     "private_journal_custody_refused")
        attached()
    except (OSError, EodhdDemoError):
        raise SharadarReferenceQualificationError("private_journal_custody_refused") from None


def _custody_identity(parent: int, directory: int, published: dict) -> dict:
    def fingerprint(info):
        return [info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_nlink,
                info.st_size, info.st_mtime_ns, info.st_ctime_ns]
    return {"parent": fingerprint(os.fstat(parent)), "directory": fingerprint(os.fstat(directory)),
            "scope-reservation.json": fingerprint(os.stat("scope-reservation.json", dir_fd=parent,
                                                           follow_symlinks=False)),
            **{name: fingerprint(os.stat(name, dir_fd=directory, follow_symlinks=False)) for name in published}}


def _predecessor(root: Path) -> dict:
    """Recheck the preserved failed scope, never resume or write it.

    Production pins are section203's actual bytes. Invented outside-lane
    fixtures instead exercise the same closed-journal/hash-chain checks.
    """
    parent = directory = None
    try:
        parent = _mkdir_chain(root, create=False)
        latch_raw = _read_leaf(parent, "scope-reservation.json", limit=4 * MAX_BODY_BYTES)
        latch = _json(latch_raw)
        audit = latch["audit_id"]
        _require(type(audit) is str and re.fullmatch(r"ib-sharadar-reference-[a-z0-9-]{1,80}", audit) is not None,
                 "predecessor_custody_refused")
        directory = os.open(audit, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        raw = _read_leaf(directory, "complete.json", limit=4 * MAX_BODY_BYTES)
        complete = _json(raw)
        latch_sha, complete_sha = _sha(latch_raw), _sha(raw)
        production = root == LANE_ROOT
        _require(not production or (audit == PREDECESSOR_AUDIT and complete_sha == PREDECESSOR_COMPLETE_SHA
                                   and latch_sha == PREDECESSOR_SCOPE_SHA), "predecessor_custody_refused")
        _require(complete["schema"] == SCHEMA and complete["audit_id"] == audit
                 and complete["fixture_only"] is (not production)
                 and complete["disposition"] == "stopped-status-qualification"
                 and complete["transport_invocation_count"] == 1
                 and complete["observed_status_metadata_count"] == 0
                 and complete["scope_reservation_sha256"] == latch_sha
                 and complete["receipts"][0]["http_status"] == 200
                 and complete["receipts"][0]["disposition"] == "source_envelope_schema_refused"
                 and complete["receipts"][1]["transport_invocation_count"] == 0,
                 "predecessor_custody_refused")
        published = dict(complete["published_leaf_sha256"])
        published["complete.json"] = complete_sha
        _require(set(published) == {"reservation.json", "credential-read-started.json",
                 "credential-read-completed.json", "01-tickers-started.json", "01-tickers-completed.json",
                 "complete.json"}, "predecessor_custody_refused")
        _check_journal(parent, directory, audit, latch_sha, published, root=root)
        custody = _custody_identity(parent, directory, published)
        _check_journal(parent, directory, audit, latch_sha, published, root=root)
        return {"audit_id": audit, "complete_sha256": complete_sha, "scope_reservation_sha256": latch_sha,
                "published_leaf_sha256": published, "custody_identity": custody}
    except (OSError, KeyError, TypeError, ValueError, EodhdDemoError):
        raise SharadarReferenceQualificationError("predecessor_custody_refused") from None
    finally:
        if directory is not None:
            os.close(directory)
        if parent is not None:
            os.close(parent)


def _diagnostic_predecessor(root: Path) -> dict:
    """Bind the consumed shape diagnostic before prospective correction verification."""
    parent = directory = None
    try:
        parent = _mkdir_chain(root, create=False, diagnostic=True)
        latch_raw = _read_leaf(parent, "scope-reservation.json", limit=4 * MAX_BODY_BYTES)
        latch = _json(latch_raw)
        audit = latch["audit_id"]
        _require(type(audit) is str and re.fullmatch(r"ib-sharadar-reference-[a-z0-9-]{1,80}", audit) is not None,
                 "diagnostic_predecessor_custody_refused")
        directory = os.open(audit, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        raw = _read_leaf(directory, "complete.json", limit=4 * MAX_BODY_BYTES)
        complete = _json(raw)
        latch_sha, complete_sha = _sha(latch_raw), _sha(raw)
        production = root == LANE_ROOT
        _require(not production or (audit == "ib-sharadar-reference-20261024-format-diagnostic-v2-once"
                 and complete_sha == DIAGNOSTIC_COMPLETE_SHA and latch_sha == DIAGNOSTIC_SCOPE_SHA),
                 "diagnostic_predecessor_custody_refused")
        shape = complete["receipts"][0]["safe_shape"]
        _require(complete["schema"] == DIAGNOSTIC_SCHEMA and complete["audit_id"] == audit
                 and complete["fixture_only"] is (not production)
                 and complete["disposition"] == "stopped-status-qualification"
                 and complete["transport_invocation_count"] == 1 and complete["observed_status_metadata_count"] == 0
                 and complete["scope_reservation_sha256"] == latch_sha
                 and complete["receipts"][0]["http_status"] == 200
                 and complete["receipts"][0]["disposition"] == "source_envelope_schema_refused"
                 and complete["receipts"][1]["transport_invocation_count"] == 0
                 and shape["root_type"] == "object" and shape["table_value_class"] == "lower-tickers"
                 and shape["field_types"] == {"table": "string", "files": "array"}
                 and shape["files_count"] == 1 and shape["unknown_field_count"] == 0
                 and shape["provider_error_class"] == "unclassified-or-absent"
                 and complete["predecessor"] == _predecessor(root), "diagnostic_predecessor_custody_refused")
        published = dict(complete["published_leaf_sha256"])
        published["complete.json"] = complete_sha
        _require(set(published) == {"reservation.json", "credential-read-started.json",
                 "credential-read-completed.json", "01-tickers-started.json", "01-tickers-completed.json",
                 "complete.json"}, "diagnostic_predecessor_custody_refused")
        _check_journal(parent, directory, audit, latch_sha, published, root=root, diagnostic=True)
        custody = _custody_identity(parent, directory, published)
        _check_journal(parent, directory, audit, latch_sha, published, root=root, diagnostic=True)
        return {"audit_id": audit, "complete_sha256": complete_sha, "scope_reservation_sha256": latch_sha,
                "published_leaf_sha256": published, "custody_identity": custody}
    except (OSError, KeyError, TypeError, ValueError, EodhdDemoError):
        raise SharadarReferenceQualificationError("diagnostic_predecessor_custody_refused") from None
    finally:
        if directory is not None:
            os.close(directory)
        if parent is not None:
            os.close(parent)


def _correction_predecessor(root: Path) -> dict:
    """Preserve the still-refused exact-descriptor verification, without resuming it."""
    parent = directory = None
    try:
        parent = _mkdir_chain(root, create=False, diagnostic=True, correction=True)
        latch_raw = _read_leaf(parent, "scope-reservation.json", limit=4 * MAX_BODY_BYTES)
        audit = _json(latch_raw)["audit_id"]
        _require(type(audit) is str and re.fullmatch(r"ib-sharadar-reference-[a-z0-9-]{1,80}", audit) is not None,
                 "correction_predecessor_custody_refused")
        directory = os.open(audit, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        raw = _read_leaf(directory, "complete.json", limit=4 * MAX_BODY_BYTES)
        complete, latch_sha, complete_sha = _json(raw), _sha(latch_raw), _sha(raw)
        production = root == LANE_ROOT
        _require(not production or (audit == "ib-sharadar-reference-20261024-wrapper-correction-v3-once"
                 and complete_sha == CORRECTION_COMPLETE_SHA and latch_sha == CORRECTION_SCOPE_SHA),
                 "correction_predecessor_custody_refused")
        _require(complete["schema"] == CORRECTION_SCHEMA and complete["fixture_only"] is (not production)
                 and complete["audit_id"] == audit and complete["scope_reservation_sha256"] == latch_sha
                 and complete["disposition"] == "stopped-status-qualification"
                 and complete["transport_invocation_count"] == 1 and complete["observed_status_metadata_count"] == 0
                 and complete["receipts"][0]["http_status"] == 200
                 and complete["receipts"][0]["disposition"] == "source_file_schema_refused"
                 and complete["receipts"][1]["transport_invocation_count"] == 0
                 and complete["predecessor"] == _predecessor(root)
                 and complete["diagnostic_predecessor"] == _diagnostic_predecessor(root),
                 "correction_predecessor_custody_refused")
        published = dict(complete["published_leaf_sha256"])
        published["complete.json"] = complete_sha
        _require(set(published) == {"reservation.json", "credential-read-started.json",
                 "credential-read-completed.json", "01-tickers-started.json", "01-tickers-completed.json",
                 "complete.json"}, "correction_predecessor_custody_refused")
        _check_journal(parent, directory, audit, latch_sha, published, root=root, diagnostic=True, correction=True)
        custody = _custody_identity(parent, directory, published)
        _check_journal(parent, directory, audit, latch_sha, published, root=root, diagnostic=True, correction=True)
        return {"audit_id": audit, "complete_sha256": complete_sha, "scope_reservation_sha256": latch_sha,
                "published_leaf_sha256": published, "custody_identity": custody}
    except (OSError, KeyError, TypeError, ValueError, EodhdDemoError):
        raise SharadarReferenceQualificationError("correction_predecessor_custody_refused") from None
    finally:
        if directory is not None:
            os.close(directory)
        if parent is not None:
            os.close(parent)


def _final_predecessor(root: Path) -> dict:
    """Pin the observed one-extra-field refusal; never reinterpret it as accepted."""
    parent = directory = None
    try:
        parent = _mkdir_chain(root, create=False, diagnostic=True, correction=True, final=True)
        latch_raw = _read_leaf(parent, "scope-reservation.json", limit=4 * MAX_BODY_BYTES)
        audit = _json(latch_raw)["audit_id"]
        _require(type(audit) is str and re.fullmatch(r"ib-sharadar-reference-[a-z0-9-]{1,80}", audit) is not None,
                 "final_predecessor_custody_refused")
        directory = os.open(audit, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        raw = _read_leaf(directory, "complete.json", limit=4 * MAX_BODY_BYTES)
        complete, latch_sha, complete_sha = _json(raw), _sha(latch_raw), _sha(raw)
        production = root == LANE_ROOT
        _require(not production or (audit == "ib-sharadar-reference-20261024-final-snapshot-v4-once"
                 and complete_sha == FINAL_COMPLETE_SHA and latch_sha == FINAL_SCOPE_SHA), "final_predecessor_custody_refused")
        shape = complete["receipts"][0]["safe_shape"]
        _require(complete["schema"] == FINAL_SCHEMA and complete["fixture_only"] is (not production)
                 and complete["audit_id"] == audit and complete["scope_reservation_sha256"] == latch_sha
                 and complete["disposition"] == "stopped-status-qualification"
                 and complete["transport_invocation_count"] == 1 and complete["observed_status_metadata_count"] == 0
                 and complete["receipts"][0]["http_status"] == 200
                 and complete["receipts"][0]["disposition"] == "source_file_schema_refused"
                 and complete["receipts"][1]["transport_invocation_count"] == 0
                 and shape["descriptor_unknown_field_count"] == 1
                 and shape["descriptor_name_class"] == "tickers"
                 and complete["predecessor"] == _predecessor(root)
                 and complete["diagnostic_predecessor"] == _diagnostic_predecessor(root)
                 and complete["correction_predecessor"] == _correction_predecessor(root), "final_predecessor_custody_refused")
        published = dict(complete["published_leaf_sha256"])
        published["complete.json"] = complete_sha
        _require(set(published) == {"reservation.json", "credential-read-started.json",
                 "credential-read-completed.json", "01-tickers-started.json", "01-tickers-completed.json",
                 "complete.json"}, "final_predecessor_custody_refused")
        _check_journal(parent, directory, audit, latch_sha, published, root=root, diagnostic=True, correction=True, final=True)
        custody = _custody_identity(parent, directory, published)
        _check_journal(parent, directory, audit, latch_sha, published, root=root, diagnostic=True, correction=True, final=True)
        return {"audit_id": audit, "complete_sha256": complete_sha, "scope_reservation_sha256": latch_sha,
                "published_leaf_sha256": published, "custody_identity": custody}
    except (OSError, KeyError, TypeError, ValueError, EodhdDemoError):
        raise SharadarReferenceQualificationError("final_predecessor_custody_refused") from None
    finally:
        if directory is not None:
            os.close(directory)
        if parent is not None:
            os.close(parent)


def _catalogue_predecessor(root: Path) -> dict:
    """Reuse the accepted TICKERS observation, never dispatch it again."""
    parent = directory = None
    try:
        parent = _mkdir_chain(root, create=False, diagnostic=True, correction=True, final=True, catalogue=True)
        latch_raw = _read_leaf(parent, "scope-reservation.json", limit=4 * MAX_BODY_BYTES)
        audit = _json(latch_raw)["audit_id"]
        _require(type(audit) is str and re.fullmatch(r"ib-sharadar-reference-[a-z0-9-]{1,80}", audit) is not None,
                 "catalogue_predecessor_custody_refused")
        directory = os.open(audit, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        raw = _read_leaf(directory, "complete.json", limit=4 * MAX_BODY_BYTES)
        complete, latch_sha, complete_sha = _json(raw), _sha(latch_raw), _sha(raw)
        production = root == LANE_ROOT
        _require(not production or (audit == "ib-sharadar-reference-20261024-public-catalogue-v5-once"
                 and complete_sha == CATALOGUE_COMPLETE_SHA and latch_sha == CATALOGUE_SCOPE_SHA),
                 "catalogue_predecessor_custody_refused")
        _require(complete["schema"] == CATALOGUE_SCHEMA and complete["fixture_only"] is (not production)
                 and complete["audit_id"] == audit and complete["scope_reservation_sha256"] == latch_sha
                 and complete["disposition"] == "stopped-status-qualification"
                 and complete["transport_invocation_count"] == 2 and complete["observed_status_metadata_count"] == 1
                 and complete["receipts"][0]["http_status"] == 200
                 and complete["receipts"][0]["status_metadata_observed"] is True
                 and complete["receipts"][1]["http_status"] == 200
                 and complete["receipts"][1]["disposition"] == "source_envelope_schema_refused"
                 and complete["predecessor"] == _predecessor(root)
                 and complete["diagnostic_predecessor"] == _diagnostic_predecessor(root)
                 and complete["correction_predecessor"] == _correction_predecessor(root)
                 and complete["final_predecessor"] == _final_predecessor(root), "catalogue_predecessor_custody_refused")
        published = dict(complete["published_leaf_sha256"])
        published["complete.json"] = complete_sha
        _require(set(published) == {"reservation.json", "credential-read-started.json", "credential-read-completed.json",
                 "01-tickers-started.json", "01-tickers-response.json", "01-tickers-metadata.json", "01-tickers-completed.json",
                 "02-actions-started.json", "02-actions-completed.json", "complete.json"}, "catalogue_predecessor_custody_refused")
        _check_journal(parent, directory, audit, latch_sha, published, root=root,
                       diagnostic=True, correction=True, final=True, catalogue=True)
        custody = _custody_identity(parent, directory, published)
        _check_journal(parent, directory, audit, latch_sha, published, root=root,
                       diagnostic=True, correction=True, final=True, catalogue=True)
        return {"audit_id": audit, "complete_sha256": complete_sha, "scope_reservation_sha256": latch_sha,
                "published_leaf_sha256": published, "custody_identity": custody}
    except (OSError, KeyError, TypeError, ValueError, EodhdDemoError):
        raise SharadarReferenceQualificationError("catalogue_predecessor_custody_refused") from None
    finally:
        if directory is not None:
            os.close(directory)
        if parent is not None:
            os.close(parent)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate_source_json_key")
        result[key] = value
    return result


def _refuse_float(_):
    raise SharadarReferenceQualificationError("source_numeric_schema_refused")


def _json(raw: bytes) -> dict:
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                            parse_float=_refuse_float, parse_constant=_refuse_float)
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        if type(exc) is SharadarReferenceQualificationError:
            raise
        raise SharadarReferenceQualificationError("source_json_refused") from None
    _require(type(result) is dict, "source_envelope_schema_refused")
    return result


def _screen_credential(raw: bytes, body: dict, credential: KeychainCredential) -> None:
    _require(credential.value.encode("ascii") not in raw, "credential_echo_refused")
    pending = [body]
    while pending:
        value = pending.pop()
        if type(value) is str:
            # Claude review section 201: one unquote pass let nested encodings
            # through. Same bounded two-track screen as the Benzinga capture:
            # the plain track keeps a literal '+' in the key, the plus track
            # decodes form-encoded spaces, and an encoding still changing at
            # the bound refuses the body rather than passing it.
            plain = plus = value
            for step in range(MAX_CREDENTIAL_DECODE_STEPS + 1):
                _require(credential.value not in plain and credential.value not in plus,
                         "credential_echo_refused")
                decoded_plain, decoded_plus = unquote(plain), unquote_plus(plus)
                if decoded_plain == plain and decoded_plus == plus:
                    break
                _require(step < MAX_CREDENTIAL_DECODE_STEPS, "credential_echo_refused")
                plain, plus = decoded_plain, decoded_plus
        elif type(value) is dict:
            pending.extend(value.keys())
            pending.extend(value.values())
        elif type(value) is list:
            pending.extend(value)


def _file_descriptor(row: object, *, actions: bool, full_snapshot: bool = False,
                     optional_metadata: bool = False, catalogue_fields: bool = False,
                     history_profile: str = "full", selected_actions: bool = False) -> dict:
    _require(type(full_snapshot) is bool, "snapshot_mode_refused")
    _require(type(history_profile) is str and history_profile in {"5y", "10y", "full"}
             and (actions or history_profile == "full"), "source_full_history_schema_refused")
    _require(type(selected_actions) is bool and (not selected_actions or actions and optional_metadata and history_profile == "full"),
             "snapshot_mode_refused")
    _require(type(optional_metadata) is bool and (not optional_metadata or (not actions or selected_actions) and not full_snapshot),
             "snapshot_mode_refused")
    _require(type(catalogue_fields) is bool, "catalogue_mode_refused")
    _require(type(row) is dict, "source_file_schema_refused")
    expected_name, expected_label = ({"5y": ("actions-5Y.csv.zip", "5 Years"),
        "10y": ("actions-10Y.csv.zip", "10 Years"), "full": ("actions.csv.zip", "Full History")}[history_profile]
        if actions else ("tickers.csv.zip", "Full History"))
    download_allowed = None
    if catalogue_fields:
        # The official public bulk client treats key as a storage lookup, NOT
        # an API credential/URL. Never output it or follow/presign anything.
        if "key" in row:
            key = row["key"]
            _require(type(key) is str and re.fullmatch(r"[A-Za-z0-9_./-]{1,512}", key) is not None
                     and all(part not in {"", ".", ".."} for part in key.split("/"))
                     and (key == expected_name or key.endswith("/" + expected_name)), "source_storage_key_refused")
        if "canDownload" in row:
            _require(type(row["canDownload"]) is bool, "source_download_flag_refused")
            download_allowed = row["canDownload"]
        row = {field: value for field, value in row.items() if field not in {"key", "canDownload"}}
    fields = {"name", "size", "sizeLabel", "modified"}
    if actions and not selected_actions or full_snapshot:
        fields |= {"history", "historyLabel", "available"}
    _require(type(row) is dict, "source_file_schema_refused")
    if optional_metadata:
        _require(fields <= set(row) <= fields | {"history", "historyLabel", "available"}, "source_file_schema_refused")
        _require("history" not in row or type(row["history"]) is str and row["history"] == history_profile,
                 "source_full_history_schema_refused")
        _require("historyLabel" not in row or type(row["historyLabel"]) is str and row["historyLabel"] == expected_label,
                 "source_full_history_schema_refused")
        _require("available" not in row or type(row["available"]) is bool, "source_full_history_schema_refused")
    else:
        _require(set(row) == fields, "source_file_schema_refused")
    _require(row["name"] == expected_name
             and type(row["name"]) is str and type(row["size"]) is int
             and 0 <= row["size"] <= 2**63 - 1
             and type(row["sizeLabel"]) is str and _SIZE_LABEL.fullmatch(row["sizeLabel"]) is not None,
             "source_file_schema_refused")
    _require(type(row["modified"]) is str and _UTC.fullmatch(row["modified"]) is not None,
             "source_modified_schema_refused")
    try:
        instant = datetime.fromisoformat(row["modified"].replace("Z", "+00:00"))
    except ValueError:
        raise SharadarReferenceQualificationError("source_modified_schema_refused") from None
    _require(instant.tzinfo == timezone.utc, "source_modified_schema_refused")
    if actions and not selected_actions or full_snapshot:
        _require(row["history"] == history_profile and type(row["history"]) is str
                 and row["historyLabel"] == expected_label and type(row["historyLabel"]) is str
                 and type(row["available"]) is bool, "source_full_history_schema_refused")
    result = {key: row[key] for key in ("name", "size", "modified")}
    if actions and not selected_actions or full_snapshot:
        result.update(history=history_profile, available=row["available"])
    if optional_metadata:
        result.update({field: row[field] for field in ("history", "available") if field in row})
    if download_allowed is not None:
        result["canDownload"] = download_allowed
    return result


def _projection(table: str, raw: bytes, credential: KeychainCredential, *,
                wrapped_snapshot: bool = False, optional_snapshot_metadata: bool = False,
                catalogue_fields: bool = False) -> dict:
    _require(type(wrapped_snapshot) is bool, "snapshot_mode_refused")
    _require(type(optional_snapshot_metadata) is bool and (not optional_snapshot_metadata or wrapped_snapshot),
             "snapshot_mode_refused")
    _require(type(catalogue_fields) is bool and (not catalogue_fields or wrapped_snapshot), "catalogue_mode_refused")
    body = _json(raw)
    _screen_credential(raw, body, credential)
    if table == "tickers":
        if wrapped_snapshot and set(body) == {"table", "files"}:
            _require(body["table"] == "tickers" and type(body["table"]) is str
                     and type(body["files"]) is list and len(body["files"]) == 1
                     and type(body["files"][0]) is dict, "source_envelope_schema_refused")
            row = body["files"][0]
            # The observed v2 shape establishes the one-file wrapper, not its
            # inner values. These two exact descriptor variants remain strict
            # compatibility candidates until actual prospective verification.
            descriptor_fields = set(row) - {"key", "canDownload"} if catalogue_fields else set(row)
            full_snapshot = descriptor_fields == {"name", "size", "sizeLabel", "modified", "history", "historyLabel", "available"}
            descriptor = _file_descriptor(row, actions=False, full_snapshot=full_snapshot and not optional_snapshot_metadata,
                                          optional_metadata=optional_snapshot_metadata, catalogue_fields=catalogue_fields)
        else:
            _require(set(body) == {"table", "name", "size", "sizeLabel", "modified"}
                     and body["table"] == "tickers" and type(body["table"]) is str,
                     "source_envelope_schema_refused")
            descriptor = _file_descriptor({key: value for key, value in body.items() if key != "table"}, actions=False)
    else:
        _require(set(body) == {"table", "files"} and body["table"] == "actions"
                 and type(body["table"]) is str and type(body["files"]) is list and len(body["files"]) == 1,
                 "source_envelope_schema_refused")
        descriptor = _file_descriptor(body["files"][0], actions=True, catalogue_fields=catalogue_fields)
    return {"table": table, "file": descriptor, "provider_reported_metadata_only": True}


def _action_inventory_projection(raw: bytes, credential: KeychainCredential) -> dict:
    """Validate every advertised history, select only the requested full file."""
    body = _json(raw)
    _screen_credential(raw, body, credential)
    descriptor_fields = {"name", "size", "sizeLabel", "modified", "history", "historyLabel", "available", "key", "canDownload"}
    _require({"table", "files"} <= set(body) <= {"table", "files"} | descriptor_fields
             and body["table"] == "actions" and type(body["table"]) is str
             and type(body["files"]) is list and 1 <= len(body["files"]) <= 3, "source_envelope_schema_refused")
    inventory, source_rows = {}, {}
    for row in body["files"]:
        _require(type(row) is dict and type(row.get("history")) is str
                 and row["history"] in {"5y", "10y", "full"} and row["history"] not in inventory,
                 "source_history_inventory_refused")
        history = row["history"]
        inventory[history] = _file_descriptor(row, actions=True, catalogue_fields=True, history_profile=history)
        source_rows[history] = row
    _require("full" in inventory, "source_full_history_missing")
    selected = inventory["full"]
    flat = {key: value for key, value in body.items() if key not in {"table", "files"}}
    if flat:
        flat_projection = _file_descriptor(flat, actions=True, catalogue_fields=True,
                                           optional_metadata=True, selected_actions=True)
        _require(all(key in selected and selected[key] == value for key, value in flat_projection.items()),
                 "source_selected_full_mismatch")
        _require(all(key in source_rows["full"] and source_rows["full"][key] == value
                     for key, value in flat.items() if key != "key"), "source_selected_full_mismatch")
        _require("key" not in flat or "key" not in source_rows["full"] or flat["key"] == source_rows["full"]["key"],
                 "source_selected_full_mismatch")
    return {"table": "actions", "file": selected, "inventory_histories": list(inventory),
            "provider_reported_metadata_only": True}


def _diagnostic_shape(raw: bytes, credential: KeychainCredential, *, descriptor: bool = False) -> dict:
    """Publish a fixed structural vocabulary, never supplier text or values."""
    _require(type(descriptor) is bool, "diagnostic_mode_refused")
    _require(type(raw) is bytes and len(raw) <= MAX_BODY_BYTES, "diagnostic_resource_refused")
    try:
        body = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                          parse_float=_refuse_float, parse_constant=_refuse_float)
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        if type(exc) is SharadarReferenceQualificationError:
            raise
        raise SharadarReferenceQualificationError("source_json_refused") from None
    pending, nodes = [(body, 0)], 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        _require(nodes <= 4096 and depth <= 24, "diagnostic_resource_refused")
        if type(value) is str:
            _require(len(value) <= 8192, "diagnostic_resource_refused")
        elif type(value) is dict:
            _require(len(value) <= 128, "diagnostic_resource_refused")
            pending.extend((item, depth + 1) for pair in value.items() for item in pair)
        elif type(value) is list:
            _require(len(value) <= 4096, "diagnostic_resource_refused")
            pending.extend((item, depth + 1) for item in value)
    _screen_credential(raw, body, credential)
    kinds = {dict: "object", list: "array", str: "string", int: "integer", bool: "boolean", type(None): "null"}
    allowed = ("table", "name", "size", "sizeLabel", "modified", "files", "error", "message", "success",
               "code", "status", "detail", "data", "result", "results")
    fields = body if type(body) is dict else {}
    table_class = {"tickers": "lower-tickers", "actions": "lower-actions",
                   "TICKERS": "upper-tickers", "ACTIONS": "upper-actions"}
    error_classes = {"missing api key": "missing-api-key", "api key is missing": "missing-api-key",
        "invalid api key": "invalid-api-key", "api key is invalid": "invalid-api-key",
        "unauthorized": "unauthorized", "exceeds free tier": "free-tier",
        "subscription required": "subscription-required"}
    error_class = "unclassified-or-absent"
    for field in ("error", "message", "detail"):
        value = fields.get(field)
        if type(value) is str and value.casefold().strip() in error_classes:
            error_class = error_classes[value.casefold().strip()]
            break
    table_value = fields.get("table")
    shape = {"root_type": kinds[type(body)],
        "field_types": {key: kinds[type(fields[key])] for key in allowed if key in fields},
        "unknown_field_count": sum(key not in allowed for key in fields),
        "files_count": len(fields["files"]) if type(fields.get("files")) is list else None,
        "table_value_class": table_class.get(table_value, "other-or-absent") if type(table_value) is str else "other-or-absent",
        "provider_error_class": error_class}
    if descriptor:
        files = fields.get("files")
        row = files[0] if type(files) is list and files and type(files[0]) is dict else {}
        allowed_row = ("name", "size", "sizeLabel", "modified", "history", "historyLabel", "available")
        def classification(key, exact):
            return "absent" if key not in row else "full" if type(row[key]) is str and row[key] == exact else "other"
        name = row.get("name")
        shape.update(descriptor_types={key: kinds[type(row[key])] for key in allowed_row if key in row},
            descriptor_unknown_field_count=sum(key not in allowed_row for key in row),
            descriptor_name_class=("tickers" if name == "tickers.csv.zip" else "actions" if name == "actions.csv.zip"
                                   else "other-or-absent"),
            descriptor_history_class=classification("history", "full"),
            descriptor_label_class=classification("historyLabel", "Full History"),
            descriptor_available_class=("absent" if "available" not in row else "true" if row["available"] is True
                                        else "false" if row["available"] is False else "other"))
    return shape


def _receipt(table: str, response: object, credential: KeychainCredential, *,
             diagnostic: bool = False, correction: bool = False, final: bool = False,
             catalogue: bool = False, actions_only: bool = False) -> tuple[dict, dict | None]:
    _require(type(diagnostic) is bool, "diagnostic_mode_refused")
    _require(type(correction) is bool and (not correction or diagnostic), "correction_mode_refused")
    _require(type(final) is bool and (not final or correction), "final_mode_refused")
    _require(type(catalogue) is bool and (not catalogue or final), "catalogue_mode_refused")
    _require(type(actions_only) is bool and (not actions_only or catalogue and table == "actions"), "actions_mode_refused")
    _require(type(response) is ProviderMetadataResponse and type(response.body) is bytes
             and type(response.body_complete) is bool and (response.status is None or
             (type(response.status) is int and 100 <= response.status <= 599))
             and (response.disposition is None or (type(response.disposition) is str
                  and response.disposition in _TRANSPORT_CODES)), "invalid_transport_result_started_reservation_preserved")
    _require(response.status is not None or (not response.body and not response.body_complete
             and response.disposition in {"transport-error", "transport-timeout", "invalid-http-status"}),
             "invalid_transport_result_started_reservation_preserved")
    projection = None
    disposition = response.disposition
    if response.status != 200:
        disposition = disposition or ("redirect-refused" if response.status is not None
                                      and 300 <= response.status < 400 else "http-refused")
    elif len(response.body) > MAX_BODY_BYTES:
        disposition = "oversized-response"
    elif disposition is None:
        if not response.body_complete:
            disposition = "partial-read"
        else:
            try:
                projection = (_action_inventory_projection(response.body, credential) if actions_only else
                              _projection(table, response.body, credential, wrapped_snapshot=correction,
                                          optional_snapshot_metadata=final, catalogue_fields=catalogue))
                disposition = ("full-history-available-status-observed" if table == "actions" and projection["file"].get("available") is True
                               else "full-history-unavailable-status-observed" if table == "actions"
                               else "current-reference-file-status-observed")
            except SharadarReferenceQualificationError as exc:
                disposition = str(exc)
    observed = projection is not None
    receipt = {"schema": SCHEMA, "table": table, "profile": PROFILES[table][0],
        "http_status": response.status, "disposition": disposition, "status_metadata_observed": observed,
        "transport_invocation_count": 1, "http_response_observed": response.status is not None,
        "body_sha256": _sha(response.body) if observed else None,
        "body_size_bytes": len(response.body) if observed else None,
        "response_body_retained": observed, "untrusted_error_body_hashed_or_retained": False,
        "provider_reported_full_history_available": None if not observed or table != "actions" else projection["file"]["available"],
        "source_table_rows_requested_or_downloaded": False, "price_or_fundamental_values_evaluated": False,
        **{flag: False for flag in FALSE_FLAGS}}
    if diagnostic:
        receipt["schema"] = ACTIONS_SCHEMA if actions_only else CATALOGUE_SCHEMA if catalogue else FINAL_SCHEMA if final else CORRECTION_SCHEMA if correction else DIAGNOSTIC_SCHEMA
        if catalogue:
            receipt["provider_reported_download_allowed"] = None if projection is None else projection["file"].get("canDownload")
        receipt["safe_shape"] = None
        if (not observed and response.status == 200 and response.body_complete
                and response.disposition is None and len(response.body) <= MAX_BODY_BYTES
                and disposition != "credential_echo_refused"):
            try:
                receipt["safe_shape"] = _diagnostic_shape(response.body, credential, descriptor=final)
            except SharadarReferenceQualificationError:
                # Failed screening/parsing never releases even structural data.
                pass
    return receipt, projection


def _default_transport(table: str, credential: KeychainCredential, *, expected_head: str, baseline: dict,
                       parent: int, directory: int, audit_id: str, latch_sha: str,
                       published: dict[str, str], diagnostic: bool = False,
                       correction: bool = False, final: bool = False, catalogue: bool = False,
                       actions_only: bool = False) -> ProviderMetadataResponse:
    _require(type(diagnostic) is bool, "diagnostic_mode_refused")
    _require(type(correction) is bool and (not correction or diagnostic), "correction_mode_refused")
    _require(type(final) is bool and (not final or correction), "final_mode_refused")
    _require(type(catalogue) is bool and (not catalogue or final), "catalogue_mode_refused")
    _require(type(actions_only) is bool and (not actions_only or catalogue and table == "actions"), "actions_mode_refused")
    schema = ACTIONS_SCHEMA if actions_only else CATALOGUE_SCHEMA if catalogue else FINAL_SCHEMA if final else CORRECTION_SCHEMA if correction else DIAGNOSTIC_SCHEMA if diagnostic else SCHEMA
    owner = DIAGNOSTIC_OWNER_DIRECTION if diagnostic else OWNER_DIRECTION
    _require(type(table) is str and table in PROFILES and type(credential) is KeychainCredential
             and credential.provider == "sharadar" and credential.fixture_only is False,
             "real_transport_profile_refused")
    _require(_identity(expected_head) == baseline, "real_transport_identity_refused")
    _check_journal(parent, directory, audit_id, latch_sha, published, root=LANE_ROOT,
                   diagnostic=diagnostic, correction=correction, final=final, catalogue=catalogue, actions_only=actions_only)
    reservation = json.loads(_read_leaf(directory, "reservation.json", limit=4 * MAX_BODY_BYTES))
    ordinal = 1 if actions_only or table == "tickers" else 2
    start_name = f"{ordinal:02d}-{table}-started.json"
    expected_leaves = {"reservation.json", "credential-read-started.json", "credential-read-completed.json",
                       start_name}
    if table == "actions" and not actions_only:
        expected_leaves |= {"01-tickers-response.json", "01-tickers-metadata.json",
                            "01-tickers-completed.json", "01-tickers-started.json"}
    _require(set(published) == expected_leaves, "real_transport_started_journal_required")
    credential_completed = json.loads(_read_leaf(directory, "credential-read-completed.json", limit=4 * MAX_BODY_BYTES))
    _require(credential_completed["schema"] == schema and credential_completed["fixture_only"] is False
             and credential_completed["credential_read_observed"] is True
             and credential_completed["disposition"] == "configured-keychain-credential-read"
             and credential_completed["started_sha256"] == published["credential-read-started.json"],
             "real_transport_started_journal_required")
    started = json.loads(_read_leaf(directory, start_name, limit=4 * MAX_BODY_BYTES))
    _require(reservation["identity"] == baseline and reservation["fixture_only"] is False
             and reservation["owner_direction"] == owner
             and reservation["requests"] == [{"table": name, "profile": profile, "method": "GET", "url": url,
                  "maximum_attempts": 1} for name, (profile, url) in PROFILES.items() if not actions_only or name == "actions"]
             and started["profile"] == PROFILES[table][0] and started["url"] == PROFILES[table][1]
             and started["maximum_attempts"] == 1 and started["reservation_sha256"] == published["reservation.json"],
             "real_transport_started_journal_required")
    if diagnostic:
        _require(reservation["predecessor"] == _predecessor(LANE_ROOT), "predecessor_custody_refused")
    if correction:
        _require(reservation["diagnostic_predecessor"] == _diagnostic_predecessor(LANE_ROOT),
                 "diagnostic_predecessor_custody_refused")
    if final:
        _require(reservation["correction_predecessor"] == _correction_predecessor(LANE_ROOT),
                 "correction_predecessor_custody_refused")
    if catalogue:
        _require(reservation["final_predecessor"] == _final_predecessor(LANE_ROOT), "final_predecessor_custody_refused")
    if actions_only:
        _require(reservation["catalogue_predecessor"] == _catalogue_predecessor(LANE_ROOT), "catalogue_predecessor_custody_refused")
    url = PROFILES[table][1]
    opener = request.build_opener(request.ProxyHandler({}), _DenyRedirect(),
                                 request.HTTPSHandler(context=ssl.create_default_context()))
    item = request.Request(url, headers={"Accept": "application/json", "Accept-Encoding": "identity",
                                        "x-api-key": credential.value}, method="GET")
    stream = None
    try:
        try:
            stream = opener.open(item, timeout=TIMEOUT_SECONDS)
        except error.HTTPError as exc:
            stream = exc
        status = stream.getcode()
        if type(status) is not int or not 100 <= status <= 599:
            return ProviderMetadataResponse(None, b"", False, "invalid-http-status")
        if stream.geturl() != url:
            return ProviderMetadataResponse(status, b"", False, "response-origin-mismatch")
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


def _exclusive_body(directory: int, name: str, raw: bytes) -> str:
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_BODY_BYTES, "response_body_profile_refused")
    descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.fsync(directory)
    return _sha(raw)


def _outside_lane(root) -> bool:
    """True only for a root that neither is, contains, nor lies inside the lane."""
    try:
        requested, actual = Path(root).resolve(), LANE_ROOT.resolve()
    except (OSError, RuntimeError, TypeError, ValueError):
        return False
    lane, other = str(actual).casefold(), str(requested).casefold()
    return lane != other and not other.startswith(lane + "/") and not lane.startswith(other + "/")


def run_qualification(audit_id: str, expected_head: str, *, root: Path = LANE_ROOT,
                      identity: Callable = _identity, transport: Callable | None = None,
                      credential_reader: Callable | None = None, clock: Callable = _now,
                      diagnostic: bool = False, correction: bool = False, final: bool = False,
                      catalogue: bool = False, actions_only: bool = False) -> dict:
    """Consume both globally fixed scopes once; stop after the first refusal.

    No production function parameter chooses providers, URLs, service/account,
    windows, keys or retry policy. Fixture seams require both an invented
    credential reader and transport; they cannot fall through to real access.
    """
    _require(type(diagnostic) is bool, "diagnostic_mode_refused")
    _require(type(correction) is bool and (not correction or diagnostic), "correction_mode_refused")
    _require(type(final) is bool and (not final or correction), "final_mode_refused")
    _require(type(catalogue) is bool and (not catalogue or final), "catalogue_mode_refused")
    _require(type(actions_only) is bool and (not actions_only or catalogue), "actions_mode_refused")
    schema = ACTIONS_SCHEMA if actions_only else CATALOGUE_SCHEMA if catalogue else FINAL_SCHEMA if final else CORRECTION_SCHEMA if correction else DIAGNOSTIC_SCHEMA if diagnostic else SCHEMA
    owner = DIAGNOSTIC_OWNER_DIRECTION if diagnostic else OWNER_DIRECTION
    profiles = {"actions": PROFILES["actions"]} if actions_only else PROFILES
    _require(type(audit_id) is str and re.fullmatch(r"ib-sharadar-reference-[a-z0-9-]{1,80}", audit_id) is not None,
             "audit_id_format_refused")
    fixture = root != LANE_ROOT or identity is not _identity or transport is not None or credential_reader is not None or clock is not _now
    _require(not fixture or credential_reader is not None, "fixture_requires_invented_credential_reader")
    _require(not fixture or transport is not None, "fixture_requires_invented_transport")
    if fixture:
        # Section 194 (Claude review): a fixture run must never create this lane's
        # real namespace (that would consume the one-shot scope for good) or hand
        # the real Keychain reader or transport to injected code.
        _require(credential_reader is not read_keychain_credential and transport is not _default_transport,
                 "fixture_real_callback_refused")
        _require(_outside_lane(root), "fixture_root_overlaps_lane_refused")
    baseline = identity(expected_head, root=root)
    predecessor = _predecessor(root) if diagnostic else None
    diagnostic_predecessor = _diagnostic_predecessor(root) if correction else None
    correction_predecessor = _correction_predecessor(root) if final else None
    final_predecessor = _final_predecessor(root) if catalogue else None
    catalogue_predecessor = _catalogue_predecessor(root) if actions_only else None
    parent = directory = None
    published = {}
    try:
        parent = _mkdir_chain(root, diagnostic=diagnostic, correction=correction, final=final,
                              catalogue=catalogue, actions_only=actions_only)
        _require(not os.listdir(parent), "existing_completed_or_ambiguous_scope_refused")
        scopes = [{"table": table, "profile": profile, "method": "GET", "url": url, "maximum_attempts": 1}
                  for table, (profile, url) in profiles.items()]
        latch_sha = _exclusive_json(parent, "scope-reservation.json", {"schema": schema,
            "audit_id": audit_id, "requests": scopes, "reserved_at_utc": clock(), "retry_resume_permitted": False})
        os.mkdir(audit_id, 0o700, dir_fd=parent)
        os.fsync(parent)
        directory = os.open(audit_id, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        def check():
            _require(identity(expected_head, root=root) == baseline, "worktree_changed_during_qualification")
            if diagnostic:
                _require(_predecessor(root) == predecessor, "predecessor_custody_refused")
            if correction:
                _require(_diagnostic_predecessor(root) == diagnostic_predecessor, "diagnostic_predecessor_custody_refused")
            if final:
                _require(_correction_predecessor(root) == correction_predecessor, "correction_predecessor_custody_refused")
            if catalogue:
                _require(_final_predecessor(root) == final_predecessor, "final_predecessor_custody_refused")
            if actions_only:
                _require(_catalogue_predecessor(root) == catalogue_predecessor, "catalogue_predecessor_custody_refused")
            _check_journal(parent, directory, audit_id, latch_sha, published, root=root,
                           diagnostic=diagnostic, correction=correction, final=final, catalogue=catalogue, actions_only=actions_only)
        def publish(name, value):
            check()
            published[name] = _exclusive_json(directory, name, value)
            check()
        publish("reservation.json", {"schema": schema, "audit_id": audit_id, "identity": baseline,
            "owner_direction": owner, "fixture_only": fixture, "requests": scopes,
            "scope_reservation_sha256": latch_sha, "reserved_at_utc": clock(),
            "keychain_service": "trading-agent-sharadar", "keychain_account": "sharadar",
            "retry_resume_permitted": False, "source_table_rows_requested_or_downloaded": False,
            **({"predecessor": predecessor} if diagnostic else {}),
            **({"diagnostic_predecessor": diagnostic_predecessor} if correction else {}),
            **({"correction_predecessor": correction_predecessor} if final else {}),
            **({"final_predecessor": final_predecessor} if catalogue else {}),
            **({"catalogue_predecessor": catalogue_predecessor} if actions_only else {}),
            **{flag: False for flag in FALSE_FLAGS}})
        publish("credential-read-started.json", {"schema": schema, "started_at_utc": clock(),
            "reservation_sha256": published["reservation.json"], "maximum_credential_reads": 1})
        reader = read_keychain_credential if credential_reader is None else credential_reader
        credential = None
        credential_disposition = "configured-keychain-credential-read"
        try:
            credential = reader("sharadar")
            _require(type(credential) is KeychainCredential and credential.provider == "sharadar"
                     and type(credential.fixture_only) is bool and (fixture or credential.fixture_only is False)
                     and type(credential.value) is str and 1 <= len(credential.value) <= 4096
                     and re.fullmatch(r"[!-~]+", credential.value) is not None
                     and credential.value.lower() != "test-api-key", "credential_read_refused")
        except KeychainCredentialError as exc:
            credential = None
            credential_disposition = (exc.args[0] if len(exc.args) == 1 and type(exc.args[0]) is str
                                      and exc.args[0] in _KEYCHAIN_CODES else "credential_read_refused")
        except Exception:
            credential = None
            credential_disposition = "credential_read_refused"
        publish("credential-read-completed.json", {"schema": schema, "completed_at_utc": clock(),
            "started_sha256": published["credential-read-started.json"], "disposition": credential_disposition,
            "credential_read_observed": credential is not None, "fixture_only": fixture})
        receipts, stopped = [], credential is None
        for ordinal, (table, (profile, url)) in enumerate(profiles.items(), 1):
            if stopped:
                receipts.append({"table": table, "profile": profile, "transport_invocation_count": 0,
                                 "disposition": "not-attempted-after-prior-refusal", "status_metadata_observed": False})
                continue
            start_name = f"{ordinal:02d}-{table}-started.json"
            publish(start_name, {"schema": schema, "profile": profile, "url": url, "maximum_attempts": 1,
                "started_at_utc": clock(), "reservation_sha256": published["reservation.json"]})
            check()
            if fixture:
                try:
                    response = transport(table, credential)
                except Exception:
                    # An injected exception can impersonate this module's
                    # typed error and carry secret text. It is never trusted.
                    response = ProviderMetadataResponse(None, b"", False, "transport-error")
            else:
                try:
                    response = _default_transport(table, credential, expected_head=expected_head, baseline=baseline,
                        parent=parent, directory=directory, audit_id=audit_id, latch_sha=latch_sha, published=published,
                        diagnostic=diagnostic, correction=correction, final=final, catalogue=catalogue, actions_only=actions_only)
                except SharadarReferenceQualificationError:
                    raise
                except Exception:
                    response = ProviderMetadataResponse(None, b"", False, "transport-error")
            check()
            receipt, projection = _receipt(table, response, credential, diagnostic=diagnostic,
                                            correction=correction, final=final, catalogue=catalogue, actions_only=actions_only)
            if projection is not None:
                body_name = f"{ordinal:02d}-{table}-response.json"
                check()
                published[body_name] = _exclusive_body(directory, body_name, response.body)
                check()
                publish(f"{ordinal:02d}-{table}-metadata.json", projection)
            publish(f"{ordinal:02d}-{table}-completed.json", {"schema": schema, "completed_at_utc": clock(),
                "started_sha256": published[start_name], "receipt": receipt})
            receipts.append(receipt)
            stopped = projection is None
        observed = sum(row["status_metadata_observed"] for row in receipts)
        complete = {"schema": schema, "audit_id": audit_id, "fixture_only": fixture,
            "completed_at_utc": clock(), "identity": baseline, "owner_direction": owner,
            **({"predecessor": predecessor} if diagnostic else {}),
            **({"diagnostic_predecessor": diagnostic_predecessor} if correction else {}),
            **({"correction_predecessor": correction_predecessor} if final else {}),
            **({"final_predecessor": final_predecessor} if catalogue else {}),
            **({"catalogue_predecessor": catalogue_predecessor} if actions_only else {}),
            "credential_disposition": credential_disposition, "planned_status_requests": len(profiles),
            "transport_invocation_count": sum(row["transport_invocation_count"] for row in receipts),
            "observed_status_metadata_count": observed, "receipts": receipts,
            "disposition": "completed-status-qualification" if observed == len(profiles) else "stopped-status-qualification",
            "published_leaf_sha256": dict(published), "scope_reservation_sha256": latch_sha,
            "source_table_rows_requested_or_downloaded": False, "research_looks": 0, "qc_jobs": 0, "backtests": 0,
            **{flag: False for flag in FALSE_FLAGS}}
        publish("complete.json", complete)
        check()
        return complete
    except SharadarReferenceQualificationError:
        raise
    except (OSError, UnicodeError, EodhdDemoError, subprocess.SubprocessError):
        raise SharadarReferenceQualificationError("private_qualification_operation_refused") from None
    finally:
        if directory is not None:
            os.close(directory)
        if parent is not None:
            os.close(parent)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-id", required=True)
    parser.add_argument("--expected-head", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--diagnostic", action="store_true",
                        help="New fixed successor scope; preserves and binds section203's failed attempt")
    mode.add_argument("--verify-correction", action="store_true",
                      help="New fixed strict wrapper-compatibility verification; binds both consumed predecessors")
    mode.add_argument("--verify-final", action="store_true",
                      help="New fixed snapshot-ancillary-metadata verification; preserves all three predecessors")
    mode.add_argument("--verify-catalogue", action="store_true",
                      help="New fixed public-catalogue-field verification; preserves all four predecessors")
    mode.add_argument("--verify-actions", action="store_true",
                      help="One ACTIONS inventory verification; reuses, never redispatches, accepted TICKERS")
    args = parser.parse_args(argv)
    try:
        result = (run_qualification(args.audit_id, args.expected_head, diagnostic=True, correction=True, final=True,
                                   catalogue=True, actions_only=True) if args.verify_actions
                  else run_qualification(args.audit_id, args.expected_head, diagnostic=True, correction=True, final=True, catalogue=True) if args.verify_catalogue
                  else run_qualification(args.audit_id, args.expected_head, diagnostic=True, correction=True, final=True) if args.verify_final
                  else run_qualification(args.audit_id, args.expected_head, diagnostic=True, correction=True) if args.verify_correction
                  else run_qualification(args.audit_id, args.expected_head, diagnostic=True) if args.diagnostic
                  else run_qualification(args.audit_id, args.expected_head))
    except SharadarReferenceQualificationError as exc:
        print(json.dumps({"qualification_refused": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["disposition"] == "completed-status-qualification" else 2


if __name__ == "__main__":
    raise SystemExit(main())
