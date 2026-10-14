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
from urllib.parse import unquote

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


def _mkdir_chain(root: Path, *, create: bool = True) -> int:
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for name in ARTIFACT_PARTS:
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
                   published: dict[str, str], *, root: Path) -> None:
    def attached():
        current = _mkdir_chain(root, create=False)
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
            _require(credential.value not in value and credential.value not in unquote(value),
                     "credential_echo_refused")
        elif type(value) is dict:
            pending.extend(value.keys())
            pending.extend(value.values())
        elif type(value) is list:
            pending.extend(value)


def _file_descriptor(row: object, *, actions: bool) -> dict:
    fields = {"name", "size", "sizeLabel", "modified"}
    if actions:
        fields |= {"history", "historyLabel", "available"}
    _require(type(row) is dict and set(row) == fields, "source_file_schema_refused")
    _require(row["name"] == ("actions.csv.zip" if actions else "tickers.csv.zip")
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
    if actions:
        _require(row["history"] == "full" and type(row["history"]) is str
                 and row["historyLabel"] == "Full History" and type(row["historyLabel"]) is str
                 and type(row["available"]) is bool, "source_full_history_schema_refused")
    result = {key: row[key] for key in ("name", "size", "modified")}
    if actions:
        result.update(history="full", available=row["available"])
    return result


def _projection(table: str, raw: bytes, credential: KeychainCredential) -> dict:
    body = _json(raw)
    _screen_credential(raw, body, credential)
    if table == "tickers":
        _require(set(body) == {"table", "name", "size", "sizeLabel", "modified"}
                 and body["table"] == "tickers" and type(body["table"]) is str,
                 "source_envelope_schema_refused")
        descriptor = _file_descriptor({key: value for key, value in body.items() if key != "table"}, actions=False)
    else:
        _require(set(body) == {"table", "files"} and body["table"] == "actions"
                 and type(body["table"]) is str and type(body["files"]) is list and len(body["files"]) == 1,
                 "source_envelope_schema_refused")
        descriptor = _file_descriptor(body["files"][0], actions=True)
    return {"table": table, "file": descriptor, "provider_reported_metadata_only": True}


def _receipt(table: str, response: object, credential: KeychainCredential) -> tuple[dict, dict | None]:
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
                projection = _projection(table, response.body, credential)
                disposition = ("full-history-available-status-observed" if projection["file"].get("available") is True
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
    return receipt, projection


def _default_transport(table: str, credential: KeychainCredential, *, expected_head: str, baseline: dict,
                       parent: int, directory: int, audit_id: str, latch_sha: str,
                       published: dict[str, str]) -> ProviderMetadataResponse:
    _require(type(table) is str and table in PROFILES and type(credential) is KeychainCredential
             and credential.provider == "sharadar" and credential.fixture_only is False,
             "real_transport_profile_refused")
    _require(_identity(expected_head) == baseline, "real_transport_identity_refused")
    _check_journal(parent, directory, audit_id, latch_sha, published, root=LANE_ROOT)
    reservation = json.loads(_read_leaf(directory, "reservation.json", limit=4 * MAX_BODY_BYTES))
    ordinal = 1 if table == "tickers" else 2
    start_name = f"{ordinal:02d}-{table}-started.json"
    expected_leaves = {"reservation.json", "credential-read-started.json", "credential-read-completed.json",
                       "01-tickers-started.json"}
    if table == "actions":
        expected_leaves |= {"01-tickers-response.json", "01-tickers-metadata.json",
                            "01-tickers-completed.json", "02-actions-started.json"}
    _require(set(published) == expected_leaves, "real_transport_started_journal_required")
    credential_completed = json.loads(_read_leaf(directory, "credential-read-completed.json", limit=4 * MAX_BODY_BYTES))
    _require(credential_completed["schema"] == SCHEMA and credential_completed["fixture_only"] is False
             and credential_completed["credential_read_observed"] is True
             and credential_completed["disposition"] == "configured-keychain-credential-read"
             and credential_completed["started_sha256"] == published["credential-read-started.json"],
             "real_transport_started_journal_required")
    started = json.loads(_read_leaf(directory, start_name, limit=4 * MAX_BODY_BYTES))
    _require(reservation["identity"] == baseline and reservation["fixture_only"] is False
             and reservation["owner_direction"] == OWNER_DIRECTION
             and reservation["requests"] == [{"table": name, "profile": profile, "method": "GET", "url": url,
                  "maximum_attempts": 1} for name, (profile, url) in PROFILES.items()]
             and started["profile"] == PROFILES[table][0] and started["url"] == PROFILES[table][1]
             and started["maximum_attempts"] == 1 and started["reservation_sha256"] == published["reservation.json"],
             "real_transport_started_journal_required")
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
                      credential_reader: Callable | None = None, clock: Callable = _now) -> dict:
    """Consume both globally fixed scopes once; stop after the first refusal.

    No production function parameter chooses providers, URLs, service/account,
    windows, keys or retry policy. Fixture seams require both an invented
    credential reader and transport; they cannot fall through to real access.
    """
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
    parent = directory = None
    published = {}
    try:
        parent = _mkdir_chain(root)
        _require(not os.listdir(parent), "existing_completed_or_ambiguous_scope_refused")
        scopes = [{"table": table, "profile": profile, "method": "GET", "url": url, "maximum_attempts": 1}
                  for table, (profile, url) in PROFILES.items()]
        latch_sha = _exclusive_json(parent, "scope-reservation.json", {"schema": SCHEMA,
            "audit_id": audit_id, "requests": scopes, "reserved_at_utc": clock(), "retry_resume_permitted": False})
        os.mkdir(audit_id, 0o700, dir_fd=parent)
        os.fsync(parent)
        directory = os.open(audit_id, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        def check():
            _require(identity(expected_head, root=root) == baseline, "worktree_changed_during_qualification")
            _check_journal(parent, directory, audit_id, latch_sha, published, root=root)
        def publish(name, value):
            check()
            published[name] = _exclusive_json(directory, name, value)
            check()
        publish("reservation.json", {"schema": SCHEMA, "audit_id": audit_id, "identity": baseline,
            "owner_direction": OWNER_DIRECTION, "fixture_only": fixture, "requests": scopes,
            "scope_reservation_sha256": latch_sha, "reserved_at_utc": clock(),
            "keychain_service": "trading-agent-sharadar", "keychain_account": "sharadar",
            "retry_resume_permitted": False, "source_table_rows_requested_or_downloaded": False,
            **{flag: False for flag in FALSE_FLAGS}})
        publish("credential-read-started.json", {"schema": SCHEMA, "started_at_utc": clock(),
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
        publish("credential-read-completed.json", {"schema": SCHEMA, "completed_at_utc": clock(),
            "started_sha256": published["credential-read-started.json"], "disposition": credential_disposition,
            "credential_read_observed": credential is not None, "fixture_only": fixture})
        receipts, stopped = [], credential is None
        for ordinal, (table, (profile, url)) in enumerate(PROFILES.items(), 1):
            if stopped:
                receipts.append({"table": table, "profile": profile, "transport_invocation_count": 0,
                                 "disposition": "not-attempted-after-prior-refusal", "status_metadata_observed": False})
                continue
            start_name = f"{ordinal:02d}-{table}-started.json"
            publish(start_name, {"schema": SCHEMA, "profile": profile, "url": url, "maximum_attempts": 1,
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
                        parent=parent, directory=directory, audit_id=audit_id, latch_sha=latch_sha, published=published)
                except SharadarReferenceQualificationError:
                    raise
                except Exception:
                    response = ProviderMetadataResponse(None, b"", False, "transport-error")
            check()
            receipt, projection = _receipt(table, response, credential)
            if projection is not None:
                body_name = f"{ordinal:02d}-{table}-response.json"
                check()
                published[body_name] = _exclusive_body(directory, body_name, response.body)
                check()
                publish(f"{ordinal:02d}-{table}-metadata.json", projection)
            publish(f"{ordinal:02d}-{table}-completed.json", {"schema": SCHEMA, "completed_at_utc": clock(),
                "started_sha256": published[start_name], "receipt": receipt})
            receipts.append(receipt)
            stopped = projection is None
        observed = sum(row["status_metadata_observed"] for row in receipts)
        complete = {"schema": SCHEMA, "audit_id": audit_id, "fixture_only": fixture,
            "completed_at_utc": clock(), "identity": baseline, "owner_direction": OWNER_DIRECTION,
            "credential_disposition": credential_disposition, "planned_status_requests": 2,
            "transport_invocation_count": sum(row["transport_invocation_count"] for row in receipts),
            "observed_status_metadata_count": observed, "receipts": receipts,
            "disposition": "completed-status-qualification" if observed == 2 else "stopped-status-qualification",
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
    args = parser.parse_args(argv)
    try:
        result = run_qualification(args.audit_id, args.expected_head)
    except SharadarReferenceQualificationError as exc:
        print(json.dumps({"qualification_refused": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["disposition"] == "completed-status-qualification" else 2


if __name__ == "__main__":
    raise SystemExit(main())
