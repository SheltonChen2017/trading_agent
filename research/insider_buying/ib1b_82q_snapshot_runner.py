"""Offline IB-1A/IB-1B publication for the exact retained 82-quarter ZIP set.

The public entry accepts only the retained census and observed header profile.
It preflights all 82 ZIPs before writing, then publishes one immutable raw and
parsed snapshot at a time. A per-quarter receipt permits an interrupted run to
verify and reuse complete snapshots; the aggregate report is published only
after all 82 receipts have been replayed. This is noncanonical source work:
local last-write stamps are not SEC acceptance or retrieval evidence, and no
outcome, QuantConnect, broker, or trading authority is conferred.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import uuid
from collections import Counter
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from data.hashing import canonical_json, hash_bytes, hash_payload
from data.runtime_identity import RuntimeIdentityError, current_commit
from research.insider_buying.ib1b_82q_offline_runner import (
    RETAINED_82Q_CENSUS_SHA256,
    _preflight_ib1b_82q_headers,
    _quarter_headers,
)
from research.insider_buying.ib1b_pilot_runner import (
    Ib1bPilotError,
    _open_directory_anchor,
    _overlap,
    _require_plain_path,
    _require_publication_capability,
    _same_regular_file,
)
from research.insider_buying.sec_bulk_parsed_snapshot import (
    build_sec_bulk_parsed_snapshot,
    load_sec_bulk_parsed_snapshot,
)
from research.insider_buying.sec_bulk_snapshot import (
    ALLOWED_SEC_TABLES,
    SecBulkSource,
    load_sec_bulk_snapshot,
    write_sec_bulk_snapshot,
)
from research.insider_buying.sec_ib1b_82q_schema_profile import (
    RETAINED_82Q_SCHEMA_PROFILE_SHA256,
    build_retained_82q_schema_profile_candidate,
    verify_retained_82q_schema_profile,
)
from research.insider_buying.sec_noncanonical_pilot_contracts import PilotZeroAuthority
from research.insider_buying.sec_zip_corpus_census import (
    SecZipCorpusCensus,
    _CAPTURE_COMMIT,
    _PinnedZipRoot,
    _plain_root,
    census_retained_sec_zip_corpus,
)


RUN_KIND = "sec-insider-noncanonical-ib1b-82q-publication"
RUN_VERSION = 1
_PARSER_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_RAW_ID = re.compile(r"sec-insider-bulk-20[0-9]{2}q[1-4]-[0-9a-f]{16}\Z")
_PARSED_ID = re.compile(r"sec-insider-parsed-20[0-9]{2}q[1-4]-[0-9a-f]{16}\Z")
_FORMS = ("3", "3/A", "4", "4/A", "5", "5/A")
_MAX_QUARTER_RECEIPT_BYTES = 16 * 1024
_MAX_AGGREGATE_BYTES = 512 * 1024
_BINDING_NAME = "run-binding.json"
_REPORT_NAME = "ib1b-82q-completion.json"


class Ib1b82qSnapshotError(ValueError):
    """The complete offline publication or its recovery refused."""


def _refuse(message: str) -> None:
    raise Ib1b82qSnapshotError(f"REFUSED: {message}")


def _validate_roots(input_root: str | Path, output_root: str | Path) -> tuple[Path, Path]:
    try:
        source = _require_plain_path(input_root, label="IB-1B input root")
        destination = _require_plain_path(output_root, label="IB-1B output root")
        repository = Path(__file__).resolve().parents[2]
        if not source.is_dir() or _overlap(source, destination) or _overlap(repository, destination):
            _refuse("output must be outside both the retained source and repository")
        return _plain_root(source), destination
    except Ib1bPilotError as exc:
        raise Ib1b82qSnapshotError(str(exc)) from exc


def _check_directory_anchor(directory: Path, descriptor: int) -> None:
    """A name swap cannot turn a pinned receipt into another output root."""
    try:
        named = directory.lstat()
        opened = os.fstat(descriptor)
    except OSError as exc:
        raise Ib1b82qSnapshotError("REFUSED: receipt directory became unreadable") from exc
    if (
        not stat.S_ISDIR(named.st_mode)
        or not stat.S_ISDIR(opened.st_mode)
        or (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino)
    ):
        _refuse("receipt directory changed during publication or replay")


def _verify_retained_parser_commit(commit: str) -> None:
    """A retained receipt cannot be stamped with a caller-invented commit."""
    repository = Path(__file__).resolve().parents[2]
    try:
        root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], cwd=repository,
            stderr=subprocess.DEVNULL, text=True,
        ).strip()
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=repository,
            stderr=subprocess.DEVNULL, text=True,
        ).strip()
        if root != str(repository) or branch != "codex/strategy-insider-buying":
            _refuse("parser commit requires the designated Insider lane")
        current_commit(
            require_clean=True, repository=repository, expected_commit=commit,
        )
    except (OSError, subprocess.CalledProcessError, RuntimeIdentityError) as exc:
        raise Ib1b82qSnapshotError(
            "REFUSED: parser commit is not the clean designated HEAD"
        ) from exc


@contextmanager
def _exclusive_output_lock(destination: Path):
    """Lock only an exact empty single-link leaf in the pinned output root."""
    anchor = _open_directory_anchor(destination)
    leaf: int | None = None
    locked = False
    try:
        _check_directory_anchor(destination, anchor)
        leaf = os.open(
            ".ib1b-82q.lock",
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
            0o600,
            dir_fd=anchor,
        )
        opened = os.fstat(leaf)
        named = os.stat(".ib1b-82q.lock", dir_fd=anchor, follow_symlinks=False)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_size != 0
            or not _same_regular_file(opened, named)
        ):
            _refuse("output lock is not an exact empty single-link file")
        import fcntl

        fcntl.flock(leaf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        locked = True
        _check_directory_anchor(destination, anchor)
        os.fsync(anchor)
        yield
    except Ib1b82qSnapshotError:
        raise
    except (OSError, ImportError) as exc:
        raise Ib1b82qSnapshotError("REFUSED: output lock is unsafe or in use") from exc
    finally:
        if leaf is not None:
            if locked:
                fcntl.flock(leaf, fcntl.LOCK_UN)
            os.close(leaf)
        os.close(anchor)


def _read_anchored(
    directory: Path, name: str, *, max_bytes: int, require_single_link: bool = True
) -> bytes:
    """Read a single-link committed receipt through a pinned directory."""
    descriptor = _open_directory_anchor(directory)
    try:
        _check_directory_anchor(directory, descriptor)
        before = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        if (
            not stat.S_ISREG(before.st_mode)
            or (require_single_link and before.st_nlink != 1)
            or not 0 < before.st_size <= max_bytes
        ):
            _refuse("receipt is not a bounded regular single-link file")
        leaf = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=descriptor)
        try:
            opened = os.fstat(leaf)
            if not _same_regular_file(before, opened):
                _refuse("receipt changed before its read")
            raw = bytearray()
            while len(raw) <= max_bytes:
                part = os.read(leaf, min(64 * 1024, max_bytes + 1 - len(raw)))
                if not part:
                    break
                raw.extend(part)
            after = os.fstat(leaf)
        finally:
            os.close(leaf)
        named_after = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        _check_directory_anchor(directory, descriptor)
        if (
            not _same_regular_file(opened, after)
            or not _same_regular_file(after, named_after)
            or (require_single_link and named_after.st_nlink != 1)
            or len(raw) != after.st_size
            or len(raw) > max_bytes
        ):
            _refuse("receipt changed during its bounded read")
        return bytes(raw)
    except Ib1b82qSnapshotError:
        raise
    except OSError as exc:
        raise Ib1b82qSnapshotError("REFUSED: committed receipt is missing or unreadable") from exc
    finally:
        os.close(descriptor)


def _envelope_bytes(payload: dict[str, object], *, max_bytes: int) -> bytes:
    envelope = {"payload": payload, "payload_sha256": hash_payload(payload)}
    raw = (canonical_json(envelope) + "\n").encode("utf-8")
    if len(raw) > max_bytes:
        _refuse("immutable receipt exceeds its byte cap")
    return raw


def _parse_envelope(raw: bytes) -> dict[str, object]:
    try:
        envelope = json.loads(raw)
        if (
            type(envelope) is not dict
            or set(envelope) != {"payload", "payload_sha256"}
            or type(envelope["payload"]) is not dict
            or type(envelope["payload_sha256"]) is not str
            or hash_payload(envelope["payload"]) != envelope["payload_sha256"]
            or raw != (canonical_json(envelope) + "\n").encode("utf-8")
        ):
            _refuse("immutable receipt content or digest is invalid")
    except (UnicodeError, TypeError, ValueError) as exc:
        if isinstance(exc, Ib1b82qSnapshotError):
            raise
        raise Ib1b82qSnapshotError("REFUSED: immutable receipt is not canonical JSON") from exc
    return envelope["payload"]


def _recover_receipt_temporaries(
    directory: Path, name: str, *, max_bytes: int, expected_raw: bytes | None = None
) -> None:
    """Remove only verified publisher residue after an interrupted link/write."""
    anchor = _open_directory_anchor(directory)
    try:
        _check_directory_anchor(directory, anchor)
        pattern = re.compile(rf"\.{re.escape(name)}\.[0-9a-f]{{32}}\.tmp\Z")
        temporaries = sorted(item for item in os.listdir(anchor) if pattern.fullmatch(item))
        if not temporaries:
            return
        try:
            final_status = os.stat(name, dir_fd=anchor, follow_symlinks=False)
        except FileNotFoundError:
            final_status = None
        if final_status is not None:
            final_raw = _read_anchored(
                directory, name, max_bytes=max_bytes, require_single_link=False
            )
            _parse_envelope(final_raw)
            if expected_raw is not None and final_raw != expected_raw:
                _refuse("committed receipt conflicts with attempted recovery")
        else:
            final_raw = expected_raw
        if final_raw is None:
            _refuse("uncommitted receipt temporary has no expected bytes")
        verified: list[str] = []
        for temporary in temporaries:
            status = os.stat(temporary, dir_fd=anchor, follow_symlinks=False)
            if not stat.S_ISREG(status.st_mode):
                _refuse("receipt temporary is not a regular file")
            raw = (
                b"" if status.st_size == 0 else
                _read_anchored(
                    directory, temporary, max_bytes=max_bytes,
                    require_single_link=False,
                )
            )
            if not final_raw.startswith(raw):
                _refuse("receipt temporary differs from expected publication")
            if final_status is not None and (
                (status.st_dev, status.st_ino) == (final_status.st_dev, final_status.st_ino)
                and raw != final_raw
            ):
                _refuse("linked receipt temporary is incomplete")
            verified.append(temporary)
        _check_directory_anchor(directory, anchor)
        for temporary in verified:
            os.unlink(temporary, dir_fd=anchor)
        os.fsync(anchor)
        _check_directory_anchor(directory, anchor)
    except Ib1b82qSnapshotError:
        raise
    except OSError as exc:
        raise Ib1b82qSnapshotError("REFUSED: receipt temporary recovery failed") from exc
    finally:
        os.close(anchor)


def _read_envelope(directory: Path, name: str, *, max_bytes: int) -> dict[str, object]:
    _recover_receipt_temporaries(directory, name, max_bytes=max_bytes)
    raw = _read_anchored(directory, name, max_bytes=max_bytes)
    return _parse_envelope(raw)


def _publish_envelope(directory: Path, name: str, payload: dict[str, object], *, max_bytes: int) -> Path:
    """Link complete fsynced bytes under an exclusive name, never replace."""
    raw = _envelope_bytes(payload, max_bytes=max_bytes)
    _require_plain_path(directory, label="IB-1B receipt directory")
    _recover_receipt_temporaries(directory, name, max_bytes=max_bytes, expected_raw=raw)
    anchor = _open_directory_anchor(directory)
    temporary = f".{name}.{uuid.uuid4().hex}.tmp"
    temp_created = False
    temp_identity = None
    try:
        _check_directory_anchor(directory, anchor)
        try:
            os.stat(name, dir_fd=anchor, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            if _read_anchored(directory, name, max_bytes=max_bytes) != raw:
                _refuse("immutable receipt conflicts with an existing publication")
            _check_directory_anchor(directory, anchor)
            return directory / name
        leaf = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=anchor)
        temp_created = True
        with os.fdopen(leaf, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
            temp_identity = os.fstat(handle.fileno())
        _require_plain_path(directory, label="IB-1B receipt directory")
        if not _same_regular_file(temp_identity, os.stat(temporary, dir_fd=anchor, follow_symlinks=False)):
            _refuse("receipt temporary changed before publication")
        os.link(temporary, name, src_dir_fd=anchor, dst_dir_fd=anchor, follow_symlinks=False)
        if not _same_regular_file(temp_identity, os.stat(name, dir_fd=anchor, follow_symlinks=False)):
            _refuse("published receipt differs from its complete temporary")
        os.fsync(anchor)
        _require_plain_path(directory, label="IB-1B receipt directory")
        _check_directory_anchor(directory, anchor)
    except Ib1b82qSnapshotError:
        raise
    except OSError as exc:
        raise Ib1b82qSnapshotError("REFUSED: immutable receipt publication failed") from exc
    finally:
        try:
            if temp_created:
                current = os.stat(temporary, dir_fd=anchor, follow_symlinks=False)
                if temp_identity is None or not _same_regular_file(temp_identity, current):
                    _refuse("replaced receipt temporary is not cleaned up")
                os.unlink(temporary, dir_fd=anchor)
        finally:
            os.close(anchor)
    return directory / name


def _context(census: SecZipCorpusCensus, profile: object) -> None:
    if type(census) is not SecZipCorpusCensus:
        _refuse("82-quarter source census is not exact")
    census.__post_init__()
    verify_retained_82q_schema_profile(profile)
    if census.scope == "retained_noncanonical_zip_census" and census.sha256 != RETAINED_82Q_CENSUS_SHA256:
        _refuse("retained census digest changed")


def _quarter_payload(
    census_quarter, raw, parsed, loaded, parser_git_commit: str,
    *, parser_commit_verified: bool,
) -> dict[str, object]:
    year, quarter = int(census_quarter.period[:4]), int(census_quarter.period[-1])
    expected_time = datetime.fromisoformat(
        census_quarter.local_last_write_utc_unverified[:-1] + "+00:00"
    ).isoformat()
    if (
        (raw.year, raw.quarter) != (year, quarter)
        or raw.archive_sha256 != census_quarter.zip_sha256
        or raw.archive_size_bytes != census_quarter.zip_size_bytes
        or raw.source_url != census_quarter.source_url_from_retained_manifest
        or raw.git_commit != _CAPTURE_COMMIT
        or raw.retrieved_at_utc != expected_time
        or (parsed.year, parsed.quarter) != (year, quarter)
        or parsed.raw_snapshot_id != raw.snapshot_id
        or parsed.raw_lineage_hash != raw.lineage_hash
        or parsed.raw_archive_sha256 != raw.archive_sha256
        or parsed.schema_profile_hash != RETAINED_82Q_SCHEMA_PROFILE_SHA256
        or parsed.parser_git_commit != parser_git_commit
        or parsed.absent_tables
        or tuple(item.table_name for item in parsed.tables) != ALLOWED_SEC_TABLES
        or loaded.identity != parsed
    ):
        _refuse("quarter snapshot replay differs from bound source and schema")
    forms = Counter(item.document_type for item in loaded.accessions)
    expected_forms = dict(zip(_FORMS, census_quarter.form_counts, strict=True))
    if (
        len(loaded.accessions) != census_quarter.submission_accessions
        or any(forms.get(form, 0) != count for form, count in expected_forms.items())
        or set(forms) - set(_FORMS)
    ):
        _refuse("parsed accession counts disagree with source-bound census")
    return {
        "kind": "sec-insider-noncanonical-ib1b-82q-quarter",
        "period": census_quarter.period,
        "census_quarter_sha256": hash_payload(census_quarter.to_payload()),
        "source_zip_sha256": census_quarter.zip_sha256,
        "source_zip_size_bytes": census_quarter.zip_size_bytes,
        "source_timestamp_basis": "filesystem_last_write_unverified",
        "original_local_last_write_utc": census_quarter.local_last_write_utc_unverified,
        "legacy_ib1a_retrieved_at_utc_representation": raw.retrieved_at_utc,
        "legacy_field_is_verified_retrieval": False,
        "raw_snapshot_id": raw.snapshot_id,
        "raw_lineage_sha256": raw.lineage_hash,
        "parsed_snapshot_id": parsed.snapshot_id,
        "parsed_lineage_sha256": parsed.lineage_hash,
        "schema_profile_sha256": parsed.schema_profile_hash,
        "parser_git_commit": parser_git_commit,
        "parser_git_commit_verified": parser_commit_verified,
        "row_count": len(loaded.rows),
        "accession_count": len(loaded.accessions),
        "document_forms": expected_forms,
    }


def _replay_quarter(
    destination: Path, receipt: dict[str, object], census_quarter,
    parser_git_commit: str, *, parser_commit_verified: bool,
) -> dict[str, object]:
    raw_id, parsed_id = receipt.get("raw_snapshot_id"), receipt.get("parsed_snapshot_id")
    if (
        type(raw_id) is not str or _RAW_ID.fullmatch(raw_id) is None
        or type(parsed_id) is not str or _PARSED_ID.fullmatch(parsed_id) is None
    ):
        _refuse("quarter receipt snapshot identifiers are invalid")
    raw_directory = destination / "ib1a" / raw_id
    raw_loaded = load_sec_bulk_snapshot(raw_directory)
    parsed_loaded = load_sec_bulk_parsed_snapshot(
        destination / "ib1b" / parsed_id, raw_snapshot_directory=raw_directory
    )
    expected = _quarter_payload(
        census_quarter, raw_loaded.identity, parsed_loaded.identity,
        parsed_loaded, parser_git_commit,
        parser_commit_verified=parser_commit_verified,
    )
    if receipt != expected:
        _refuse("quarter receipt differs from replayed immutable snapshots")
    return expected


def _run_bound_ib1b_82q(
    input_root: str | Path,
    output_root: str | Path,
    parser_git_commit: str,
    *,
    census: SecZipCorpusCensus,
    profile: object,
) -> Path:
    """Private synthetic seam; retained scope is issued only by the public entry."""
    if type(parser_git_commit) is not str or _PARSER_COMMIT.fullmatch(parser_git_commit) is None:
        _refuse("parser Git commit must be a full lowercase SHA-1")
    if census.scope == "retained_noncanonical_zip_census":
        _verify_retained_parser_commit(parser_git_commit)
    _context(census, profile)
    _require_publication_capability()
    source, destination = _validate_roots(input_root, output_root)
    preflight = _preflight_ib1b_82q_headers(source, census, profile)
    if (
        preflight.census_sha256 != census.sha256
        or preflight.schema_profile_sha256 != RETAINED_82Q_SCHEMA_PROFILE_SHA256
        or tuple((item.period, item.zip_sha256, item.zip_size_bytes)
                 for item in preflight.quarters)
        != tuple((item.period, item.zip_sha256, item.zip_size_bytes)
                 for item in census.quarters)
    ):
        _refuse("complete header preflight differs from source-bound census")
    _validate_roots(input_root, output_root)
    destination.mkdir(parents=True, exist_ok=True)
    _require_plain_path(destination, label="IB-1B output root")
    binding = {
        "kind": RUN_KIND,
        "version": RUN_VERSION,
        "scope": census.scope,
        "census_sha256": census.sha256,
        "header_preflight_sha256": preflight.sha256,
        "schema_profile_sha256": RETAINED_82Q_SCHEMA_PROFILE_SHA256,
        "parser_git_commit": parser_git_commit,
        "parser_git_commit_verified": census.scope == "retained_noncanonical_zip_census",
        "periods": [item.period for item in census.quarters],
    }
    with _exclusive_output_lock(destination):
        _validate_roots(input_root, output_root)
        names = {item.name for item in destination.iterdir()}
        allowed = {".ib1b-82q.lock", _BINDING_NAME, "journal", "ib1a", "ib1b", _REPORT_NAME}
        if names - allowed or (_BINDING_NAME not in names and names != {".ib1b-82q.lock"}):
            _refuse("output root contains an unbound or unexpected publication")
        _publish_envelope(destination, _BINDING_NAME, binding, max_bytes=_MAX_QUARTER_RECEIPT_BYTES)
        for name in ("journal", "ib1a", "ib1b"):
            folder = destination / name
            folder.mkdir(exist_ok=True)
            _require_plain_path(folder, label="IB-1B publication directory")
        journal = destination / "journal"
        expected_journals = {f"quarter-{item.period}.json" for item in census.quarters}
        for name in os.listdir(journal):
            if name not in expected_journals and not re.fullmatch(
                r"\.quarter-20[0-9]{2}Q[1-4]\.json\.[0-9a-f]{32}\.tmp", name
            ):
                _refuse("journal contains an unexpected entry")
        quarters: list[dict[str, object]] = []
        with _PinnedZipRoot(source) as pinned:
            expected_zips = {f"{item.period.lower()}_form345.zip" for item in census.quarters}
            if {name for name in pinned.names() if name.endswith(".zip")} != expected_zips:
                _refuse("source ZIP inventory changed after preflight")
            for item, header_receipt in zip(census.quarters, preflight.quarters, strict=True):
                _validate_roots(input_root, output_root)
                journal_name = f"quarter-{item.period}.json"
                if journal_name in os.listdir(journal):
                    receipt = _read_envelope(journal, journal_name, max_bytes=_MAX_QUARTER_RECEIPT_BYTES)
                    quarters.append(_replay_quarter(
                        destination, receipt, item, parser_git_commit,
                        parser_commit_verified=census.scope == "retained_noncanonical_zip_census",
                    ))
                    continue
                raw_bytes = pinned.read(f"{item.period.lower()}_form345.zip", max_bytes=item.zip_size_bytes)
                if len(raw_bytes) != item.zip_size_bytes or hash_bytes(raw_bytes) != item.zip_sha256:
                    _refuse("source ZIP changed after complete preflight")
                if _quarter_headers(raw_bytes, item.period, profile) != header_receipt:
                    _refuse("source header receipt changed before parsing")
                source_metadata = SecBulkSource(
                    year=int(item.period[:4]), quarter=int(item.period[-1]),
                    source_url=item.source_url_from_retained_manifest,
                    git_commit=_CAPTURE_COMMIT,
                    retrieved_at=datetime.fromisoformat(
                        item.local_last_write_utc_unverified[:-1] + "+00:00"
                    ),
                )
                raw = write_sec_bulk_snapshot(raw_bytes, source_metadata, destination / "ib1a")
                del raw_bytes
                raw_directory = destination / "ib1a" / raw.snapshot_id
                replayed_raw = load_sec_bulk_snapshot(raw_directory)
                if replayed_raw.identity != raw:
                    _refuse("raw snapshot replay differs from publication")
                del replayed_raw
                parsed = build_sec_bulk_parsed_snapshot(
                    raw_directory, destination / "ib1b",
                    schema_profile=profile, parser_git_commit=parser_git_commit,
                )
                loaded = load_sec_bulk_parsed_snapshot(
                    destination / "ib1b" / parsed.snapshot_id,
                    raw_snapshot_directory=raw_directory,
                )
                receipt = _quarter_payload(
                    item, raw, parsed, loaded, parser_git_commit,
                    parser_commit_verified=census.scope == "retained_noncanonical_zip_census",
                )
                _publish_envelope(journal, journal_name, receipt, max_bytes=_MAX_QUARTER_RECEIPT_BYTES)
                quarters.append(receipt)
                del loaded, parsed, raw
        _context(census, profile)
        if census.scope == "retained_noncanonical_zip_census":
            _verify_retained_parser_commit(parser_git_commit)
        if tuple(item["period"] for item in quarters) != tuple(item.period for item in census.quarters):
            _refuse("completed quarter sequence differs from source census")
        report = {
            "kind": RUN_KIND,
            "version": RUN_VERSION,
            "scope": census.scope,
            "census_sha256": census.sha256,
            "header_preflight_sha256": preflight.sha256,
            "schema_profile_sha256": RETAINED_82Q_SCHEMA_PROFILE_SHA256,
            "parser_git_commit": parser_git_commit,
            "parser_git_commit_verified": census.scope == "retained_noncanonical_zip_census",
            "periods": [item.period for item in census.quarters],
            "archive_counts": {"accepted": 82, "refused": 0, "quarantined": 0},
            "canonical": False,
            "point_in_time_data": False,
            "corpus_completeness_claimed": False,
            "source_provenance_verified": False,
            "acceptance_metadata_verified": False,
            "authority": PilotZeroAuthority().to_payload(),
            "quarters": quarters,
        }
        result = _publish_envelope(destination, _REPORT_NAME, report, max_bytes=_MAX_AGGREGATE_BYTES)
        if _read_envelope(destination, _REPORT_NAME, max_bytes=_MAX_AGGREGATE_BYTES) != report:
            _refuse("aggregate report failed committed replay")
        return result


def run_retained_ib1b_82q(
    input_root: str | Path, output_root: str | Path, parser_git_commit: str
) -> Path:
    """Publish only the exact retained ZIP census; no source/profile override."""
    _verify_retained_parser_commit(parser_git_commit)
    census = census_retained_sec_zip_corpus(input_root)
    if census.scope != "retained_noncanonical_zip_census" or census.sha256 != RETAINED_82Q_CENSUS_SHA256:
        _refuse("retained ZIP census identity is not approved")
    return _run_bound_ib1b_82q(
        input_root, output_root, parser_git_commit,
        census=census, profile=build_retained_82q_schema_profile_candidate(),
    )


__all__ = ["Ib1b82qSnapshotError", "run_retained_ib1b_82q"]
