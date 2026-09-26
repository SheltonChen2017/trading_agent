"""Explicit, offline, noncanonical IB-1A/IB-1B pilot composition.

Importing this module performs no I/O. Do not invoke it on real bytes until
Claude has independently reviewed this preparation and Codex counter-reviewed
that review. ``reviewed_preparation`` is a caller acknowledgement, not an
authenticated review or authority receipt. The public entry point has no
synthetic-mode or source/profile override.

The historical intake timestamp is a filesystem observation, NOT verified
retrieval evidence. As in record section 80.3, the existing IB-1A source field
receives its normalized datetime representation solely for legacy composition.
The operational report preserves the original seven-digit observation and
labels both that representation and its provenance limitations explicitly.
No resulting raw or parsed snapshot is canonical evidence or point-in-time
proof. No original timestamp is silently upgraded to verified retrieval.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import io
import os
from pathlib import Path
import re
import stat
import time
import uuid
import zipfile

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying.sec_bulk_snapshot import (
    ALLOWED_SEC_TABLES,
    MAX_ARCHIVE_BYTES,
    SecBulkSnapshotError,
    SecBulkSource,
    _read_regular_bytes,
    load_sec_bulk_snapshot,
    write_sec_bulk_snapshot,
)
from research.insider_buying.sec_bulk_parsed_snapshot import (
    MAX_TOTAL_PARSED_INPUT_BYTES,
    SecBulkParsedSnapshotError,
    build_sec_bulk_parsed_snapshot,
    load_sec_bulk_parsed_snapshot,
)
from research.insider_buying.sec_ib1b_pilot_profile import (
    PILOT_PERIODS,
    PILOT_SCHEMA_PROFILE_SHA256,
    approved_ib1b_archive_bindings,
    approved_ib1b_schema_profile,
    Ib1bPilotProfileError,
    verify_approved_ib1b_archive_bindings,
    verify_approved_ib1b_schema_profile,
)
from research.insider_buying.sec_noncanonical_pilot_contracts import (
    PilotZeroAuthority,
)


REPORT_KIND = "sec-insider-noncanonical-ib1b-pilot-operational-report"
REPORT_VERSION = 1
MAX_REPORT_BYTES = 128 * 1024
_KNOWN_FORMS = ("3", "3/A", "4", "4/A", "5", "5/A")


class Ib1bPilotError(ValueError):
    """A bounded pilot was refused; no complete success report was published."""


def _require_plain_path(value: str | Path, *, label: str) -> Path:
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise Ib1bPilotError(f"REFUSED: {label} must be an absolute non-traversing path")
    for component in (*reversed(path.parents), path):
        try:
            status = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(status.st_mode) or getattr(status, "st_file_attributes", 0) & 0x400:
            raise Ib1bPilotError(f"REFUSED: {label} cannot traverse a redirect")
        if not stat.S_ISDIR(status.st_mode):
            raise Ib1bPilotError(f"REFUSED: {label} components must be directories")
    return path


def _overlap(first: Path, second: Path) -> bool:
    return first == second or first in second.parents or second in first.parents


def _validate_roots(input_root: str | Path, output_root: str | Path) -> tuple[Path, Path]:
    source = _require_plain_path(input_root, label="input root")
    destination = _require_plain_path(output_root, label="output root")
    if not source.is_dir():
        raise Ib1bPilotError("REFUSED: input root must exist")
    repository_root = Path(__file__).resolve().parents[1]
    if _overlap(source, destination) or _overlap(repository_root, destination):
        raise Ib1bPilotError("REFUSED: output root cannot overlap inputs or the repository")
    if destination.exists() and any(destination.iterdir()):
        raise Ib1bPilotError("REFUSED: output root must be fresh or empty; no overwrite")
    return source, destination


def _check_archive(raw: bytes, binding, profile) -> None:
    if len(raw) != binding.archive_size_bytes or hash_bytes(raw) != binding.archive_sha256:
        raise Ib1bPilotError("REFUSED: pilot archive differs from its exact hash/size binding")
    receipts = binding.header_receipts
    if tuple(item.table_name for item in receipts) != ALLOWED_SEC_TABLES:
        raise Ib1bPilotError("REFUSED: pilot requires all eight header receipts in canonical order")
    if sum(item.expanded_size_bytes for item in receipts) > MAX_TOTAL_PARSED_INPUT_BYTES:
        raise Ib1bPilotError("REFUSED: table expansion exceeds the unchanged IB-1B limit")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for receipt in receipts:
                variant = profile.variant_for(receipt.table_name, binding.year, binding.quarter)
                if receipt.headers != variant.headers:
                    raise Ib1bPilotError("REFUSED: header receipt differs from the approved profile")
                info = archive.getinfo(receipt.table_name)
                if info.file_size != receipt.expanded_size_bytes:
                    raise Ib1bPilotError("REFUSED: expanded table size differs from the header receipt")
                with archive.open(info) as handle:
                    header = handle.readline(receipt.header_line_size_bytes + 1)
                if (
                    len(header) != receipt.header_line_size_bytes
                    or hash_bytes(header) != receipt.header_line_sha256
                    or header.rstrip(b"\r\n").decode("utf-8").split("\t") != list(variant.headers)
                ):
                    raise Ib1bPilotError("REFUSED: physical header differs from the approved receipt")
    except (KeyError, UnicodeDecodeError, zipfile.BadZipFile) as exc:
        raise Ib1bPilotError("REFUSED: archive has no exact approved header inventory") from exc


def _read_bound_archive(source: Path, binding, profile) -> bytes:
    raw = _read_regular_bytes(
        source / binding.filename,
        label="owner-supplied pilot ZIP",
        max_bytes=min(binding.archive_size_bytes, MAX_ARCHIVE_BYTES),
    )
    _check_archive(raw, binding, profile)
    return raw


def _quarter_report(raw, parsed, loaded, binding, elapsed_ns: int) -> dict[str, object]:
    forms = Counter(item.document_type for item in loaded.accessions)
    form_counts = {name: forms.get(name, 0) for name in _KNOWN_FORMS}
    form_counts["OTHER"] = sum(value for key, value in forms.items() if key not in _KNOWN_FORMS)
    return {
        "year": binding.year,
        "quarter": binding.quarter,
        "operational_outcome": "ACCEPTED",
        "source_binding": binding.to_payload(),
        "timestamp_evidence": {
            "original_local_last_write_utc": binding.local_last_write_utc,
            "basis": "filesystem_last_write_unverified",
            "source_provenance_verified": False,
            "legacy_ib1a_retrieved_at_utc_representation": raw.retrieved_at_utc,
            "legacy_field_is_verified_retrieval": False,
            "legacy_fractional_precision_digits": 6,
        },
        "ib1a": {
            "snapshot_id": raw.snapshot_id,
            "lineage_sha256": raw.lineage_hash,
            "archive_sha256": raw.archive_sha256,
            "archive_size_bytes": raw.archive_size_bytes,
            "members": [item.to_payload() for item in raw.members],
            "auxiliary_members": [item.to_payload() for item in raw.auxiliary_members],
        },
        "ib1b": {
            "snapshot_id": parsed.snapshot_id,
            "lineage_sha256": parsed.lineage_hash,
            "raw_snapshot_id": parsed.raw_snapshot_id,
            "raw_lineage_sha256": parsed.raw_lineage_hash,
            "raw_manifest_sha256": parsed.raw_manifest_sha256,
            "schema_profile_sha256": parsed.schema_profile_hash,
            "parser_git_commit": parsed.parser_git_commit,
            "tables": [item.to_payload() for item in parsed.tables],
            "artifacts": [item.to_payload() for item in parsed.artifacts],
        },
        "counts": {
            "rows": len(loaded.rows),
            "accessions": len(loaded.accessions),
            "document_forms": form_counts,
        },
        "resources": {
            "archive_bytes": raw.archive_size_bytes,
            "expanded_table_bytes": sum(item.size_bytes for item in raw.members),
            "parsed_artifact_bytes": sum(item.size_bytes for item in parsed.artifacts),
            "elapsed_nanoseconds": elapsed_ns,
        },
    }


def _publish_report(destination: Path, payload: dict[str, object]) -> Path:
    digest = hash_payload(payload)
    envelope = {"payload": payload, "payload_sha256": digest}
    content = (canonical_json(envelope) + "\n").encode("utf-8")
    if len(content) > MAX_REPORT_BYTES:
        raise Ib1bPilotError("REFUSED: operational report exceeds its byte-size cap")
    target = destination / f"ib1b-pilot-report-{digest}.json"
    temporary_name = f".ib1b-pilot-report-{uuid.uuid4().hex}.tmp"
    directory_fd = _open_directory_anchor(destination)
    created_temporary = False
    temporary_identity = None
    try:
        descriptor = os.open(
            temporary_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600, dir_fd=directory_fd,
        )
        created_temporary = True
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_identity = os.fstat(handle.fileno())
        # Exclusive linking publishes complete bytes without an overwrite race.
        _require_plain_path(destination, label="report output root")
        anchored = os.fstat(directory_fd)
        current = destination.lstat()
        if (anchored.st_dev, anchored.st_ino) != (current.st_dev, current.st_ino):
            raise Ib1bPilotError("REFUSED: report output root changed during publication")
        current_temporary = os.stat(temporary_name, dir_fd=directory_fd, follow_symlinks=False)
        if not _same_regular_file(temporary_identity, current_temporary):
            raise Ib1bPilotError("REFUSED: report temporary changed before publication")
        os.link(
            temporary_name, target.name,
            src_dir_fd=directory_fd, dst_dir_fd=directory_fd,
            follow_symlinks=False,
        )
        published = os.stat(target.name, dir_fd=directory_fd, follow_symlinks=False)
        if not _same_regular_file(temporary_identity, published):
            raise Ib1bPilotError("REFUSED: report publication differs from its complete temporary")
        os.fsync(directory_fd)
        _require_plain_path(destination, label="report output root")
        current = destination.lstat()
        if (anchored.st_dev, anchored.st_ino) != (current.st_dev, current.st_ino):
            raise Ib1bPilotError("REFUSED: report output root changed during publication")
    except OSError as exc:
        raise Ib1bPilotError("REFUSED: complete operational report could not be published") from exc
    finally:
        try:
            if created_temporary:
                current_temporary = os.stat(temporary_name, dir_fd=directory_fd, follow_symlinks=False)
                if temporary_identity is None or not _same_regular_file(temporary_identity, current_temporary):
                    raise Ib1bPilotError("REFUSED: replaced report temporary is not cleaned up")
                os.unlink(temporary_name, dir_fd=directory_fd)
        finally:
            os.close(directory_fd)
    return target


def _open_directory_anchor(path: Path) -> int:
    """Walk every component without redirects; writes remain descriptor-bound."""
    _require_publication_capability()
    _require_plain_path(path, label="report output root")
    descriptor = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in path.parts[1:]:
            next_descriptor = os.open(
                component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _same_regular_file(first, second) -> bool:
    return (
        stat.S_ISREG(second.st_mode)
        and (first.st_dev, first.st_ino, first.st_size, first.st_mtime_ns)
        == (second.st_dev, second.st_ino, second.st_size, second.st_mtime_ns)
    )


def _require_publication_capability() -> None:
    if (
        not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW")
        or not {os.open, os.link, os.unlink}.issubset(os.supports_dir_fd)
    ):
        raise Ib1bPilotError("REFUSED: platform lacks descriptor-anchored report publication")


def _run_ib1b_pilot(input_root, output_root, parser_git_commit, *, bindings, profile, _approved=False) -> Path:
    """Private composition core; synthetic tests substitute only their ZIP receipts."""
    if type(parser_git_commit) is not str or re.fullmatch(r"[0-9a-f]{40}", parser_git_commit) is None:
        raise Ib1bPilotError("REFUSED: parser Git commit must be a full lowercase SHA-1")
    verify_approved_ib1b_schema_profile(profile)
    if tuple((item.year, item.quarter) for item in bindings) != PILOT_PERIODS:
        raise Ib1bPilotError("REFUSED: pilot requires exactly the approved two-quarter window")
    binding_digest = hash_payload([item.to_payload() for item in bindings])
    _require_publication_capability()
    source, destination = _validate_roots(input_root, output_root)
    # Preflight both exact sources before creating any stage output. Reread each
    # quarter for execution, so a changed source cannot pass a stale preflight.
    for binding in bindings:
        raw_bytes = _read_bound_archive(source, binding, profile)
        del raw_bytes
    # The preflight can take time; do not inherit somebody else's output that
    # appeared while it ran.
    _validate_roots(input_root, output_root)
    destination.mkdir(parents=True, exist_ok=True)
    _require_plain_path(destination, label="output root")
    lock = destination / ".ib1b-pilot.running"
    try:
        lock_handle = lock.open("xb")
        lock_identity = os.fstat(lock_handle.fileno())
    except OSError as exc:
        raise Ib1bPilotError("REFUSED: pilot output root is already claimed") from exc
    quarters = []
    try:
        for binding in bindings:
            _require_plain_path(source, label="input root")
            _require_plain_path(destination, label="output root")
            started = time.monotonic_ns()
            raw_bytes = _read_bound_archive(source, binding, profile)
            legacy_source = SecBulkSource(
                year=binding.year,
                quarter=binding.quarter,
                source_url=binding.source_url,
                git_commit=binding.capture_git_commit,
                retrieved_at=datetime.fromisoformat(binding.local_last_write_utc),
            )
            raw = write_sec_bulk_snapshot(raw_bytes, legacy_source, destination / "ib1a")
            del raw_bytes
            raw_directory = destination / "ib1a" / raw.snapshot_id
            replayed_raw = load_sec_bulk_snapshot(raw_directory)
            if replayed_raw.identity != raw:
                raise Ib1bPilotError("REFUSED: IB-1A replay identity differs from publication")
            del replayed_raw
            parsed = build_sec_bulk_parsed_snapshot(
                raw_directory,
                destination / "ib1b",
                schema_profile=profile,
                parser_git_commit=parser_git_commit,
            )
            loaded = load_sec_bulk_parsed_snapshot(
                destination / "ib1b" / parsed.snapshot_id,
                raw_snapshot_directory=raw_directory,
            )
            if (
                loaded.identity != parsed
                or parsed.absent_tables
                or tuple(item.table_name for item in parsed.tables) != ALLOWED_SEC_TABLES
                or parsed.schema_profile_hash != PILOT_SCHEMA_PROFILE_SHA256
            ):
                raise Ib1bPilotError("REFUSED: IB-1B replay is not the exact complete approved profile")
            quarters.append(_quarter_report(raw, parsed, loaded, binding, time.monotonic_ns() - started))
            # No cross-quarter accumulation of row-bearing objects or ZIP bytes.
            del loaded, parsed, raw
        verify_approved_ib1b_schema_profile(profile)
        if _approved:
            verify_approved_ib1b_archive_bindings(bindings)
        if binding_digest != hash_payload([item.to_payload() for item in bindings]):
            raise Ib1bPilotError("REFUSED: source receipts changed during processing")
        payload = {
            "kind": REPORT_KIND,
            "report_version": REPORT_VERSION,
            "canonical": False,
            "point_in_time_data": False,
            "corpus_completeness_claimed": False,
            "review_acknowledgement_authenticated": False,
            "scope": "OFFLINE_IB1A_IB1B_ONLY",
            "schema_profile_sha256": PILOT_SCHEMA_PROFILE_SHA256,
            "source_binding_inventory_sha256": binding_digest,
            "periods": [list(item) for item in PILOT_PERIODS],
            "archive_counts": {"accepted": 2, "refused": 0, "quarantined": 0},
            "authority": PilotZeroAuthority().to_payload(),
            "quarters": quarters,
        }
        return _publish_report(destination, payload)
    finally:
        # Retain the open inode throughout execution. Refuse rather than
        # deleting a foreign replacement, including after complete publication.
        # Late failure may leave complete immutable artifacts, but no successful
        # return accepts that run and no partial success report is produced.
        try:
            _require_plain_path(destination, label="output root")
            current_lock = lock.lstat()
            if not _same_regular_file(lock_identity, current_lock) or current_lock.st_nlink != 1:
                raise Ib1bPilotError("REFUSED: replaced pilot marker is not cleaned up")
            lock.unlink()
        finally:
            lock_handle.close()


def run_approved_ib1b_pilot(
    input_root: str | Path,
    output_root: str | Path,
    parser_git_commit: str,
    *,
    reviewed_preparation: bool = False,
) -> Path:
    """Run only the fixed, owner-selected two-quarter sources after review."""
    if type(reviewed_preparation) is not bool or not reviewed_preparation:
        raise Ib1bPilotError("REFUSED: independently reviewed preparation must be acknowledged before I/O")
    bindings = approved_ib1b_archive_bindings()
    verify_approved_ib1b_archive_bindings(bindings)
    return _run_ib1b_pilot(
        input_root, output_root, parser_git_commit,
        bindings=bindings,
        profile=approved_ib1b_schema_profile(),
        _approved=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--parser-git-commit", required=True)
    parser.add_argument("--reviewed-preparation", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        report = run_approved_ib1b_pilot(
            arguments.input_root, arguments.output_root, arguments.parser_git_commit,
            reviewed_preparation=arguments.reviewed_preparation,
        )
    except (Ib1bPilotError, Ib1bPilotProfileError, SecBulkSnapshotError, SecBulkParsedSnapshotError, OSError) as exc:
        parser.exit(2, f"{exc}\n")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
