"""Claimed local REMX source partition/export; no provider or native access.

Invoke from the designated lane root after this complete source closure is
committed. The only argument names a fresh immutable operation. The fixed USB
member is read once; originals and all quarantines remain private. A partial
candidate never grants full coverage, financial input or trading admission.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import time
import zipfile

from . import remx_repair_20261103 as repair

ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__target_price_revisions")
BRANCH = "codex/strategy-target-price-revisions"
RECORD = "docs/Strategy Description/TARGET_PRICE_REVISION_IMPLEMENTATION_RECORD.md"
MODULE = "research/target_price_revisions_qc/remx_prepare_20261103.py"
REQUIRED_SOURCES = frozenset((
    "AGENTS.md", "CLAUDE.md", "research/__init__.py",
    "research/target_price_revisions_qc/__init__.py", "data/__init__.py",
    MODULE, "research/target_price_revisions_qc/remx_repair_20261103.py",
    "research/target_price_revisions_qc/firstrate_20261103.py",
    "data/financial_primitives.py",
))
DESTINATION = "artifacts/target_price_remx_20261103"
USB_ROOT = Path("/Volumes/SANDISK/firstrate")
ARCHIVE = "market/ETF-Complete_5000+_Tickers/Tickers_R_Day_Unadjusted_Full_Dataset.zip"
MEMBER = "REMX_full_1day_UNADJUSTED.txt"
MEMBER_BYTES = 181222
MEMBER_SHA256 = "b8c54990689501ddc55183e6bb28c8eb7cd47a8817c04153480a6ef613b1de5e"
OWNER_INSTRUCTION = ("investigate and fix the REMX data issues locally. keep QC and Safari untouched, "
                     "skip Claude review, and push only once when done.")
OWNER_SHA256 = hashlib.sha256(OWNER_INSTRUCTION.encode()).hexdigest()
MAX_LIFETIME_SECONDS = 300
MAX_ARCHIVE_BYTES = 4 * 1024 * 1024 * 1024 - 1
MAX_CENTRAL_BYTES = 8 * 1024 * 1024
MAX_ZIP_MEMBERS = 50000
OUTPUT_NAMES = frozenset(("source_original.csv", "candidate_post_inception.csv",
    "quarantine_pre_inception.csv", "quarantine_fractional_volume.csv",
    "quarantine_invalid_rows.csv", "row_ledger.jsonl", "manifest.json"))


class PreparationRefusal(ValueError):
    """Fixed message only; no input, exception or private path disclosure."""


def _fail():
    raise PreparationRefusal("local REMX preparation refused") from None


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _wire(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


def _git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT,
        stderr=subprocess.DEVNULL, timeout=15)


def _context():
    if (Path.cwd() != ROOT or
            Path(_git("rev-parse", "--show-toplevel").decode().strip()) != ROOT or
            _git("branch", "--show-current").decode().strip() != BRANCH):
        _fail()
    head = _git("rev-parse", "HEAD").decode().strip()
    if re.fullmatch("[0-9a-f]{40}", head) is None:
        _fail()
    if _git("diff", "--name-only", "-z").decode().strip("\0") not in ("", RECORD):
        _fail()
    if _git("diff", "--cached", "--name-only", "-z"):
        _fail()
    return head


def _parent(path):
    try:
        parts = path.relative_to(ROOT).parts
    except ValueError:
        _fail()
    if not parts or any(part in ("", ".", "..") for part in parts):
        _fail()
    fd = os.open(".", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        actual, named = os.fstat(fd), os.stat(ROOT, follow_symlinks=False)
        if (Path.cwd() != ROOT or not stat.S_ISDIR(named.st_mode) or
                (actual.st_dev, actual.st_ino) != (named.st_dev, named.st_ino)):
            _fail()
        for index, part in enumerate(parts[:-1]):
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            status = os.fstat(fd)
            if status.st_uid != os.getuid():
                _fail()
            if parts[0] == "artifacts" and index >= 1 and status.st_mode & 0o077:
                _fail()
    except BaseException:
        os.close(fd)
        raise
    return fd, parts[-1]


def _directory(path, *, exclusive=False):
    parent, leaf = _parent(path)
    try:
        try:
            os.mkdir(leaf, mode=0o700, dir_fd=parent)
        except FileExistsError:
            if exclusive:
                raise
        fd = os.open(leaf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            status = os.fstat(fd)
            if status.st_uid != os.getuid():
                _fail()
            if len(path.relative_to(ROOT).parts) > 1 and status.st_mode & 0o077:
                _fail()
        finally:
            os.close(fd)
        os.fsync(parent)
    finally:
        os.close(parent)


def _regular(path, maximum):
    parent, leaf = _parent(path)
    try:
        named = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISREG(named.st_mode) or not 0 <= named.st_size <= maximum:
            _fail()
        fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    finally:
        os.close(parent)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if _snapshot(named) != _snapshot(before):
            _fail()
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    if (_snapshot(before) != _snapshot(after) or len(raw) != before.st_size):
        _fail()
    return raw


def _retain(path, raw):
    parent, leaf = _parent(path)
    try:
        fd = os.open(leaf, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(parent)
    finally:
        os.close(parent)
    return {"name": path.name, "bytes": len(raw), "sha256": _sha(raw)}


def _note(message):
    parent, leaf = _parent(ROOT / RECORD)
    try:
        named = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISREG(named.st_mode) or named.st_uid != os.getuid():
            _fail()
        fd = os.open(leaf, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    finally:
        os.close(parent)
    with os.fdopen(fd, "a", encoding="utf-8") as stream:
        if _snapshot(named) != _snapshot(os.fstat(stream.fileno())):
            _fail()
        stream.write("\n" + message.rstrip() + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _snapshot(status):
    return (status.st_dev, status.st_ino, status.st_size,
            status.st_mtime_ns, status.st_ctime_ns)


def _usb_stream():
    path = USB_ROOT / ARCHIVE
    if not path.is_absolute() or any(part in ("", ".", "..") for part in path.parts[1:]):
        _fail()
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        named = os.stat(path.name, dir_fd=fd, follow_symlinks=False)
        if not stat.S_ISREG(named.st_mode) or not 22 <= named.st_size <= MAX_ARCHIVE_BYTES:
            _fail()
        leaf = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        if _snapshot(named) != _snapshot(os.fstat(leaf)):
            os.close(leaf)
            _fail()
    finally:
        os.close(fd)
    return os.fdopen(leaf, "rb")


def _central_bound(stream, size):
    # Bound the central directory BEFORE ZipFile materializes its records.
    stream.seek(max(0, size - 65557))
    tail = stream.read(min(size, 65557))
    offset = tail.rfind(b"PK\x05\x06")
    if offset < 0 or len(tail) - offset < 22:
        _fail()
    _, disk, central_disk, disk_count, count, central_size, central_at, comment = struct.unpack(
        "<4s4H2LH", tail[offset:offset + 22])
    end_at = size - len(tail) + offset
    if (disk != 0 or central_disk != 0 or disk_count != count or
            not 0 < count <= MAX_ZIP_MEMBERS or count == 65535 or
            not 0 < central_size <= MAX_CENTRAL_BYTES or
            central_at + central_size != end_at or offset + 22 + comment != len(tail)):
        _fail()
    stream.seek(0)


def _read_member():
    with _usb_stream() as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 22 <= before.st_size <= MAX_ARCHIVE_BYTES:
            _fail()
        _central_bound(stream, before.st_size)
        with zipfile.ZipFile(stream) as archive:
            members = archive.infolist()
            if not 0 < len(members) <= MAX_ZIP_MEMBERS:
                _fail()
            selected = [item for item in members if item.filename == MEMBER]
            if len(selected) != 1:
                _fail()
            info = selected[0]
            if (info.is_dir() or info.flag_bits & 1 or info.file_size != MEMBER_BYTES or
                    not 0 < info.compress_size <= MEMBER_BYTES or
                    info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                _fail()
            with archive.open(info, "r") as member:
                raw = member.read(MEMBER_BYTES + 1)
                if len(raw) != MEMBER_BYTES or member.read(1):
                    _fail()
        after = os.fstat(stream.fileno())
    if _snapshot(before) != _snapshot(after) or _sha(raw) != MEMBER_SHA256:
        _fail()
    return raw, {"archive_bytes": before.st_size, "archive_sha256": None,
        "archive_hash_not_computed": True, "archive_stat_stable": True,
        "member": MEMBER, "member_bytes": len(raw), "member_sha256": _sha(raw),
        "member_crc32": info.CRC, "member_compressed_bytes": info.compress_size,
        "archive_member_count": len(members)}


def prepare_workspace(operation_id):
    """Consume one fresh claim; spent operations and partial files never retry."""
    if type(operation_id) is not str or re.fullmatch("REMX-20261103-EXPORT-[A-Z0-9-]{1,40}", operation_id) is None:
        _fail()
    head = _context()
    sources = {}
    for name in sorted(REQUIRED_SOURCES):
        raw = _regular(ROOT / name, 131072)
        if _git("show", head + ":" + name) != raw:
            _fail()
        sources[name] = _sha(raw)
    history = _regular(ROOT / RECORD, 8 * 1024 * 1024)
    _directory(ROOT / "artifacts")
    _directory(ROOT / DESTINATION)
    destination = ROOT / DESTINATION / operation_id
    _directory(destination, exclusive=True)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=MAX_LIFETIME_SECONDS)
    monotonic_limit = time.monotonic() + MAX_LIFETIME_SECONDS
    claim = {"schema": "tpr-remx-local-export-claim-v1", "operation_id": operation_id,
        "worktree": str(ROOT), "branch": BRANCH, "git_head": head,
        "created_utc": now.isoformat(), "expires_utc": expires.isoformat(),
        "owner_instruction_sha256": OWNER_SHA256,
        "authority": "LOCAL_REMX_DATA_INVESTIGATION_AND_DERIVATION_ONLY",
        "source_hashes": sources, "prior_record_sha256": _sha(history),
        "private_source": {"usb_root": str(USB_ROOT), "archive": ARCHIVE,
            "member": MEMBER, "bytes": MEMBER_BYTES, "sha256": MEMBER_SHA256},
        "max_member_reads": 1, "max_archive_bytes": MAX_ARCHIVE_BYTES,
        "max_central_bytes": MAX_CENTRAL_BYTES, "max_zip_members": MAX_ZIP_MEMBERS,
        "max_output_bytes": repair.MAX_EXPORT_BYTES, "max_receipt_bytes": 131072,
        "output_names": sorted(OUTPUT_NAMES),
        "reserved_attempt": None, "financial_outcome_look": None,
        "input_quality_look": operation_id, "qc_requests": 0, "safari_requests": 0,
        "provider_requests": 0, "financial_runs": 0, "original_source_writes": 0}
    claimed = _retain(destination / "claim.json", _wire(claim))
    _note("Fresh REMX export claim " + operation_id + "; HEAD" + head +
        "; manifestSHA" + claimed["sha256"] + " fsynced BEFORE the one fixed USB member read. "
        "Local private derivation only; QC0/Safari0/provider0/backtests0; originals retained.")

    def live():
        if (_context() != head or datetime.now(timezone.utc) >= expires or
                time.monotonic() >= monotonic_limit):
            _fail()
        for name, digest in sources.items():
            if _sha(_regular(ROOT / name, 131072)) != digest:
                _fail()

    status, inventory, source_proof = "refused", {}, None
    try:
        live()
        raw, source_proof = _read_member()
        live()
        blobs = repair.export_blobs(repair.repair_remx_daily(raw, expected_sha256=MEMBER_SHA256))
        if set(blobs) != OUTPUT_NAMES or sum(map(len, blobs.values())) > repair.MAX_EXPORT_BYTES:
            _fail()
        # Retain the exact source before every derived/quarantine output.
        for name in ["source_original.csv", *sorted(OUTPUT_NAMES - {"source_original.csv"})]:
            live()
            inventory[name] = _retain(destination / name, blobs[name])
        live()
        status = "prepared_partial_local_candidate"
    except Exception:
        # Retain a body-free refusal and every partial artifact. Never retry this ID.
        status = "refused"
    receipt = {"schema": "tpr-remx-local-export-receipt-v1", "operation_id": operation_id,
        "git_head": head, "owner_instruction_sha256": OWNER_SHA256,
        "claim_sha256": claimed["sha256"], "status": status,
        "source_proof": source_proof, "outputs": inventory,
        "qc_requests": 0, "safari_requests": 0, "provider_requests": 0,
        "financial_runs": 0, "source_original_modified": False,
        "full_coverage_verified": False, "backtesting_ready": False,
        "financial_acceptance": False, "trading_authority": False}
    receipt_raw = _wire(receipt)
    if len(receipt_raw) > 131072:
        _fail()
    descriptor = _retain(destination / "receipt.json", receipt_raw)
    _note("REMX local export " + operation_id + " status" + status +
        "; receiptSHA" + descriptor["sha256"] +
        "; original/quarantine/row-ledger evidence remains private. "
        "QC0/Safari0/provider0/backtests0; full coverage and financial acceptance FALSE.")
    return receipt, descriptor


def main():
    parser = argparse.ArgumentParser(description="Prepare the fixed REMX local partial candidate")
    parser.add_argument("operation_id")
    arguments = parser.parse_args()
    try:
        receipt, descriptor = prepare_workspace(arguments.operation_id)
    except Exception:
        print(json.dumps({"status": "refused", "qc_requests": 0, "safari_requests": 0}))
        return 2
    print(json.dumps({"status": receipt["status"], "receipt": descriptor,
        "qc_requests": 0, "safari_requests": 0, "backtesting_ready": False}, sort_keys=True))
    return 0 if receipt["status"] == "prepared_partial_local_candidate" else 2


if __name__ == "__main__":
    raise SystemExit(main())
