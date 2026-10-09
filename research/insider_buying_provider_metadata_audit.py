"""One-shot Insider-only provider capability audit; never a data/job launcher.

The owner placed QC/Massive credentials and a retained Sharadar capture in
scope on 2026-10-06. This runner records a durable reservation BEFORE loading
credentials or invoking any fixed metadata transport. Its private journal is
not a subscription, licence, PIT, research-look or execution authorization.
No response body, credential, auth header, billing/project identifier or raw
upstream error is published. Completed and ambiguous audits cannot resume.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import stat
import csv
import io
import zipfile
from datetime import datetime, timezone
from typing import Callable, Mapping

from research.insider_buying_provider_metadata_transport import (
    ProviderMetadataReceipt, parse_provider_metadata, probe_provider_metadata,
)

LANE_ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying")
LANE_BRANCH = "codex/strategy-insider-buying"
ARTIFACT_PARTS = ("artifacts", "insider_buying", "provider_metadata")
PROVIDERS = ("quantconnect", "massive", "sharadar")
SOURCE_FILES = (
    "research/insider_buying_provider_metadata_audit.py",
    "research/insider_buying_provider_metadata_transport.py",
    "research/quantconnect.py",
)
SCHEMA = "insider-provider-metadata-one-shot-audit-v1"


class ProviderMetadataAuditError(ValueError):
    """Sanitized local refusal; never include secret or upstream messages."""


def _bytes(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def inspect_supplied_sharadar_capture_metadata(capture: Path, expected_manifest_sha256: str) -> dict:
    """Inspect the owner-supplied *existing* reference capture, not a key.

    Read only its manifest, TICKERS ZIP envelope and first CSV header. Never
    open ACTIONS/FUNDAMENTALS or interpret any TICKERS row; never copy another checkout,
    invoke another lane, interpret first-price as first-listing, or discover
    credentials. Archive/member hashes here bind present bytes, not historical
    knowledge, source authentication or applicable rights. The caller separately
    pins the manifest it actually observed rather than accepting self-hashes.
    """
    if (type(expected_manifest_sha256) is not str
            or not re.fullmatch(r"[0-9a-f]{64}", expected_manifest_sha256)):
        raise ProviderMetadataAuditError("supplied_capture_manifest_anchor_refused")
    if not capture.is_absolute() or capture.resolve() != capture or capture.is_symlink():
        raise ProviderMetadataAuditError("supplied_capture_path_refused")
    def read_leaf(name: str, limit: int) -> bytes:
        path = capture / name
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= limit:
                raise ProviderMetadataAuditError("supplied_capture_leaf_refused")
            raw = handle.read(limit + 1)
            if len(raw) != info.st_size:
                raise ProviderMetadataAuditError("supplied_capture_read_changed")
            return raw
    try:
        raw = read_leaf("manifest.json", 1024 * 1024)
        if _sha(raw) != expected_manifest_sha256:
            raise ProviderMetadataAuditError("supplied_capture_manifest_anchor_mismatch")
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ProviderMetadataAuditError("supplied_capture_duplicate_json_key")
                result[key] = value
            return result
        manifest = json.loads(raw, object_pairs_hook=pairs)
        if (type(manifest) is not dict or manifest.get("schema") != "arv2-sharadar-source-capture-artifact-v2"
                or manifest.get("api_key_persisted") is not False
                or manifest.get("redirect_url_persisted") is not False
                or manifest.get("tickers_availability_semantics") != "capture_time_current_snapshot_active_and_delisted_not_point_in_time"
                or type(manifest.get("archives")) is not list):
            raise ProviderMetadataAuditError("supplied_capture_reference_profile_refused")
        entries = [a for a in manifest["archives"] if type(a) is dict and a.get("dataset") == "tickers"]
        if len(entries) != 1 or entries[0].get("archive_file") != "01-tickers-years-full.zip":
            raise ProviderMetadataAuditError("supplied_capture_tickers_inventory_refused")
        entry = entries[0]
        archive = read_leaf("01-tickers-years-full.zip", 128 * 1024 * 1024)
        if (_sha(archive) != entry.get("archive_sha256") or len(archive) != entry.get("archive_byte_count")):
            raise ProviderMetadataAuditError("supplied_capture_tickers_archive_mismatch")
        with zipfile.ZipFile(io.BytesIO(archive)) as envelope:
            members = envelope.infolist()
            if (len(members) != 1 or members[0].filename != "tickers.csv" or members[0].flag_bits & 1
                    or not 0 < members[0].file_size <= 128 * 1024 * 1024
                    or members[0].file_size != entry.get("uncompressed_byte_count")):
                raise ProviderMetadataAuditError("supplied_capture_tickers_envelope_refused")
            with envelope.open(members[0]) as stream:
                header = stream.readline(32769)
            if not header.endswith(b"\n") or len(header) > 32768:
                raise ProviderMetadataAuditError("supplied_capture_tickers_header_refused")
            columns = next(csv.reader([header.decode("utf-8-sig").rstrip("\r\n")], strict=True))
            if (not columns or len(columns) != len(set(columns))
                    or any(not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", c) for c in columns)):
                raise ProviderMetadataAuditError("supplied_capture_tickers_header_refused")
        return {"schema": "insider-supplied-sharadar-capture-metadata-v1",
                "manifest_sha256": _sha(raw), "tickers_archive_sha256": _sha(archive),
                "tickers_archive_byte_count": len(archive), "tickers_member_byte_count": members[0].file_size,
                "tickers_header_sha256": _sha(header), "tickers_columns": columns,
                "credentials_persisted_by_supplied_manifest": False,
                "tickers_rows_interpreted": 0, "tickers_header_only_consumed": True,
                "actions_fundamentals_bodies_read": 0,
                "current_snapshot_only": True, "rights_verified": False,
                "historical_pit_listing_identity_verified": False, "research_ready": False}
    except ProviderMetadataAuditError:
        raise
    except Exception:
        raise ProviderMetadataAuditError("supplied_capture_metadata_inspection_refused") from None


def _identity(expected_head: str, *, root: Path = LANE_ROOT) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", expected_head):
        raise ProviderMetadataAuditError("expected_head_format_refused")
    if root != LANE_ROOT or Path.cwd().resolve() != LANE_ROOT or root.is_symlink():
        raise ProviderMetadataAuditError("designated_worktree_required")
    def git(*args: str) -> str:
        result = subprocess.run(("/usr/bin/git", *args), cwd=root, capture_output=True, check=False,
                                timeout=10, env={"PATH": "/usr/bin:/bin"})
        if result.returncode:
            raise ProviderMetadataAuditError("git_identity_unavailable")
        return result.stdout.decode("utf-8").strip()
    actual_root = git("rev-parse", "--show-toplevel")
    branch = git("branch", "--show-current")
    head = git("rev-parse", "HEAD")
    if actual_root != str(LANE_ROOT) or branch != LANE_BRANCH or head != expected_head:
        raise ProviderMetadataAuditError("worktree_branch_head_mismatch")
    source_inventory = {}
    for name in SOURCE_FILES:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ProviderMetadataAuditError("audit_source_missing_or_symlinked")
        source_inventory[name] = _sha(path.read_bytes())
    return {"root": actual_root, "branch": branch, "head": head,
            "status_sha256": _sha(git("status", "--porcelain=v1", "--untracked-files=all").encode()),
            "source_sha256": source_inventory}


def _mkdir_chain(root: Path, *, create: bool = True) -> int:
    """Anchor every parent with O_NOFOLLOW; callers cannot choose another root."""
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for name in ARTIFACT_PARTS:
            if create:
                try:
                    os.mkdir(name, 0o700, dir_fd=directory)
                    os.fsync(directory)
                except FileExistsError:
                    pass
            next_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = next_fd
        return directory
    except BaseException:
        os.close(directory)
        raise


def _exclusive_json(directory: int, name: str, value: dict) -> str:
    raw = _bytes(value)
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    os.fsync(directory)
    return _sha(raw)


def _check_journal(parent: int, directory: int, audit_id: str, published: dict[str, str], *, root: Path) -> None:
    """Recheck actual anchored immutable leaves, not just receipt SHA literals."""
    try:
        # An open FD can survive a rename out of the designated path. Reopen
        # every ancestor without creating anything and require its same inode.
        current_parent = _mkdir_chain(root, create=False)
        try:
            current, held_parent = os.fstat(current_parent), os.fstat(parent)
            if (current.st_dev, current.st_ino) != (held_parent.st_dev, held_parent.st_ino):
                raise ProviderMetadataAuditError("private_journal_custody_refused")
        finally:
            os.close(current_parent)
        leaf = os.stat(audit_id, dir_fd=parent, follow_symlinks=False)
        held = os.fstat(directory)
        if (not stat.S_ISDIR(leaf.st_mode) or stat.S_IMODE(leaf.st_mode) != 0o700
                or (leaf.st_dev, leaf.st_ino) != (held.st_dev, held.st_ino)
                or set(os.listdir(directory)) != set(published)):
            raise ProviderMetadataAuditError("private_journal_custody_refused")
        for name, digest in published.items():
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                        or stat.S_IMODE(info.st_mode) != 0o600 or not 0 < info.st_size <= 4 * 1024 * 1024):
                    raise ProviderMetadataAuditError("private_journal_custody_refused")
                raw = stream.read(info.st_size + 1)
                if len(raw) != info.st_size or _sha(raw) != digest:
                    raise ProviderMetadataAuditError("private_journal_custody_refused")
    except ProviderMetadataAuditError:
        raise
    except OSError:
        raise ProviderMetadataAuditError("private_journal_custody_refused") from None


def _validated_receipt(value: object, provider: str) -> dict:
    """Refuse reconstructed unsafe facts before any private-journal publication."""
    try:
        if type(value) is not ProviderMetadataReceipt or type(value._facts) is not bytes:
            raise ValueError
        receipt = value.to_dict()
        profile = {"quantconnect": "qc-authenticate-v1", "massive": "massive-marketstatus-now-v1",
                   "sharadar": "sharadar-tickers-bulk-status-v1"}[provider]
        status, digest, size = receipt["http_status"], receipt["body_sha256"], receipt["body_size_bytes"]
        false_flags = ("entitlement_verified", "rights_verified", "historical_coverage_verified", "research_ready",
                       "qc_backtest_authorized", "outcome_access_authorized")
        if (receipt["kind"] != "insider-provider-metadata-receipt-v1" or receipt["provider"] != provider
                or receipt["request_profile"] != profile or type(receipt["body_complete"]) is not bool
                or type(size) is not int or not 0 <= size <= 1024 * 1024 + 1
                or (status is not None and (type(status) is not int or not 100 <= status <= 599))
                or (digest is not None and (type(digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", digest)))
                or (digest is None and (size != 0 or status is not None or receipt["body_complete"]))
                or any(receipt[flag] is not False for flag in false_flags)):
            raise ValueError
        failures = {"authentication-refused", "authentication-http-refused", "rate-limited", "http-error",
                    "invalid-metadata-schema", "credentials-missing", "credentials-invalid", "clock-invalid",
                    "request-refused", "unsupported-content-encoding", "invalid-content-length", "oversized-response",
                    "truncated-response", "partial-read", "redirect-refused", "invalid-http-status",
                    "response-origin-mismatch", "transport-timeout", "transport-error", "invalid-transport-result"}
        success = {"quantconnect": "qc-authentication-observed", "massive": "public-market-status-observed",
                   "sharadar": "bulk-status-metadata-observed"}[provider]
        disposition, facts = receipt["disposition"], receipt["facts"]
        if type(disposition) is not str or type(facts) is not dict:
            raise ValueError
        if disposition == success or (provider == "quantconnect" and disposition == "authentication-refused"):
            if not (type(status) is int and 200 <= status < 300 and receipt["body_complete"] and size > 0):
                raise ValueError
            # Re-parse only whitelisted projected facts, never raw upstream body.
            projected = dict(facts)
            if provider == "sharadar":
                projected["sizeLabel"] = "0 B"  # discarded cosmetic field; no invented source fact
            parsed = parse_provider_metadata(provider, status, _bytes(projected)).to_dict()
            if parsed["facts"] != facts or parsed["disposition"] != disposition:
                raise ValueError
        elif disposition not in failures or facts:
            raise ValueError
        if (type(receipt["http_access_observed"]) is not bool
                or receipt["http_access_observed"] != (status is not None)
                or type(receipt["authentication_observed"]) is not bool
                or receipt["authentication_observed"] != (provider == "quantconnect" and disposition == success)):
            raise ValueError
        return receipt
    except Exception:
        raise ProviderMetadataAuditError("private_receipt_profile_refused") from None


def run_metadata_audit(audit_id: str, providers: tuple[str, ...], expected_head: str, *,
                       environ: Mapping[str, str] | None = None,
                       probe: Callable = probe_provider_metadata,
                       identity: Callable = _identity,
                       root: Path = LANE_ROOT,
                       clock: Callable[[], str] = _now) -> dict:
    """Reserve, invoke once per selected fixed profile, then seal private facts.

    Missing local credentials consume no HTTP request. A killed/ambiguous
    invocation retains its started file and audit directory; there is no
    retry/resume/overwrite option. Injection exists for offline tests only.
    """
    if not re.fullmatch(r"ib-provider-metadata-[a-z0-9-]{1,80}", audit_id):
        raise ProviderMetadataAuditError("audit_id_format_refused")
    if (type(providers) is not tuple or not providers or len(providers) > 3
            or len(set(providers)) != len(providers) or any(p not in PROVIDERS for p in providers)):
        raise ProviderMetadataAuditError("fixed_unique_provider_selection_required")
    baseline = identity(expected_head, root=root)
    try:
        parent = _mkdir_chain(root)
    except OSError:
        raise ProviderMetadataAuditError("private_journal_operation_refused") from None
    directory = None
    try:
        try:
            os.mkdir(audit_id, 0o700, dir_fd=parent)
        except FileExistsError:
            raise ProviderMetadataAuditError("existing_completed_or_ambiguous_audit_refused") from None
        os.fsync(parent)
        directory = os.open(audit_id, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        reservation = {"schema": SCHEMA, "audit_id": audit_id, "reserved_at_utc": clock(),
                       "identity": baseline, "providers": list(providers),
                       "max_transport_attempts_per_provider": 1, "retry_resume_permitted": False,
                       "scope": "fixed-metadata-only-no-source-rows-outcomes-uploads-compiles-jobs",
                       "owner_direction": "2026-10-06-provider-credentials-and-lane-build",
                       "source_pit_rights_look_qc_backtest_execution_authority": False}
        reservation_sha = _exclusive_json(directory, "reservation.json", reservation)
        published = {"reservation.json": reservation_sha}
        _check_journal(parent, directory, audit_id, published, root=root)
        receipts = []
        for index, provider in enumerate(providers, 1):
            if identity(expected_head, root=root) != baseline:
                raise ProviderMetadataAuditError("worktree_or_source_changed_before_probe")
            start = {"schema": SCHEMA, "provider": provider, "reserved_at_utc": clock(),
                     "reservation_sha256": reservation_sha, "maximum_attempts": 1}
            start_sha = _exclusive_json(directory, f"{index:02d}-{provider}-started.json", start)
            published[f"{index:02d}-{provider}-started.json"] = start_sha
            _check_journal(parent, directory, audit_id, published, root=root)
            # Start is durably committed before even calling a credential loader.
            try:
                supplied_receipt = probe(provider, environ=environ)
            except Exception:
                # Preserve the reservation rather than leaking arbitrary exception
                # messages or calling a potentially ambiguous probe again.
                raise ProviderMetadataAuditError("probe_failed_started_reservation_preserved") from None
            _check_journal(parent, directory, audit_id, published, root=root)
            receipt = _validated_receipt(supplied_receipt, provider)
            end = {"schema": SCHEMA, "provider": provider, "completed_at_utc": clock(),
                   "started_sha256": start_sha, "receipt": receipt}
            end_sha = _exclusive_json(directory, f"{index:02d}-{provider}-completed.json", end)
            published[f"{index:02d}-{provider}-completed.json"] = end_sha
            _check_journal(parent, directory, audit_id, published, root=root)
            receipts.append({"provider": provider, "completed_sha256": end_sha, "receipt": receipt})
            if identity(expected_head, root=root) != baseline:
                raise ProviderMetadataAuditError("worktree_or_source_changed_after_probe")
        complete = {"schema": SCHEMA, "audit_id": audit_id, "completed_at_utc": clock(),
                    "reservation_sha256": reservation_sha, "identity": baseline, "receipts": receipts,
                    "raw_response_bodies_persisted": False,
                    "secrets_headers_upstream_errors_persisted": False,
                    "looks_jobs_backtests": [0, 0, 0],
                    "rights_entitlement_pit_research_readiness_established": False}
        _check_journal(parent, directory, audit_id, published, root=root)
        complete_sha = _exclusive_json(directory, "complete.json", complete)
        published["complete.json"] = complete_sha
        _check_journal(parent, directory, audit_id, published, root=root)
        return {"audit_id": audit_id, "complete_sha256": complete_sha, "receipts": receipts,
                "rights_entitlement_pit_research_readiness_established": False}
    except (OSError, ValueError) as exc:
        if isinstance(exc, ProviderMetadataAuditError):
            raise
        raise ProviderMetadataAuditError("private_journal_operation_refused") from None
    finally:
        if directory is not None:
            os.close(directory)
        os.close(parent)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-id", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--providers", nargs="+", required=True, choices=PROVIDERS)
    args = parser.parse_args(argv)
    try:
        result = run_metadata_audit(args.audit_id, tuple(args.providers), args.expected_head)
    except ProviderMetadataAuditError as exc:
        print(json.dumps({"audit_refused": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
