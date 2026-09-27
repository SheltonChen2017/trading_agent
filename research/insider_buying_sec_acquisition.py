"""Bounded, noncanonical SEC-only Form 4/4-A acquisition pilot.

This script is outside ``research.insider_buying``'s provider-free package.
It acquires only the fixed 16-accession compatibility sample from the two
approved quarterly ZIPs. It does not call IB-1C, publish canonical evidence,
or access outcomes. Importing it performs no I/O.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timezone
import getpass
import http.client
import io
import json
import os
from pathlib import Path
import re
import stat
import time
import uuid
import xml.etree.ElementTree as ET
import zipfile

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying.sec_acquisition_preparation import (
    SecAcquisitionPreparationError,
    SecAcquisitionTarget,
    derive_sec_header_projection,
)
from research.insider_buying.sec_bulk_parsed_snapshot import _parse_table
from research.insider_buying.sec_bulk_snapshot import (
    _read_regular_bytes,
    load_sec_bulk_snapshot,
)
from research.insider_buying.sec_ib1b_pilot_profile import (
    approved_ib1b_archive_bindings,
    approved_ib1b_schema_profile,
    verify_approved_ib1b_archive_bindings,
    verify_approved_ib1b_schema_profile,
)
from research.insider_buying.sec_noncanonical_pilot_contracts import (
    PilotAccessionCandidateIdentity,
)


PILOT_VERSION = "INSETF-SEC-SIXTEEN-ACQUISITION-v1"
INDEX_ROUTE_VERSION = "sec-accession-directory-index-json-v1"
MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_ATTEMPTS = 3
MAX_DISTINCT_REQUESTS = 48
MAX_TOTAL_ATTEMPTS = 144
MIN_REQUEST_INTERVAL_SECONDS = 0.5
_CONTACT_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}\Z")
_XML_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)*\.xml\Z")
_DATE_RE = re.compile(r"([0-9]{2})-([A-Z]{3})-([0-9]{4})\Z")
_MONTHS = {name: index for index, name in enumerate(
    ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), 1
)}
_PERIODS = ((2022, 4), (2023, 1))
_RAW_IDENTITIES = {
    (2022, 4): ("sec-insider-bulk-2022q4-e34b743e2bee3381", "e34b743e2bee3381ea9395ddf64b850b409d4e635979f02f71f15734bb79a36c"),
    (2023, 1): ("sec-insider-bulk-2023q1-c8c35e859ab09342", "c8c35e859ab093425078491008428677e1e78b01843ebbf5b849357d9c6a0658"),
}
_EXPECTED_ACCESSIONS = (
    "0000002178-22-000091", "0000002178-22-000094", "0000002178-22-000095",
    "0000002178-22-000097", "0000002178-22-000099", "0000002488-22-000165",
    "0000050725-22-000079", "0000050725-22-000083",
    "0000002178-23-000019", "0000002178-23-000020", "0000002178-23-000021",
    "0000002178-23-000022", "0000002178-23-000023", "0000002178-23-000024",
    "0000016058-23-000011", "0000019745-23-000002",
)


class SecPilotError(ValueError):
    """The fixed SEC pilot refused a source, response, or publication."""


class SecPilotGlobalStop(SecPilotError):
    """Stop the entire SEC request sequence, retaining remaining rows."""


def _open_output_directory(output: Path, expected: tuple[int, int] | None = None) -> int:
    descriptor = os.open(output, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                         | getattr(os, "O_NOFOLLOW", 0))
    try:
        _check_output_directory(output, descriptor, expected)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _check_output_directory(output: Path, descriptor: int,
                            expected: tuple[int, int] | None = None) -> tuple[int, int]:
    try:
        opened = os.fstat(descriptor)
        current = output.lstat()
    except OSError as exc:
        raise OSError("REFUSED: output root changed or disappeared") from exc
    identity = (opened.st_dev, opened.st_ino)
    if (not stat.S_ISDIR(opened.st_mode) or not stat.S_ISDIR(current.st_mode)
            or identity != (current.st_dev, current.st_ino)
            or (expected is not None and identity != expected)):
        raise OSError("REFUSED: output root directory changed")
    return identity


@dataclass(frozen=True)
class SecPilotCandidate:
    period: str
    accession_number: str
    form_type: str
    filing_date_raw: str
    filing_date: str
    issuer_cik: str
    quarterly_zip_sha256: str
    submission_row_id: str
    raw_snapshot_id: str
    raw_lineage_sha256: str

    @property
    def archive_path(self) -> str:
        return ("/Archives/edgar/data/" + str(int(self.issuer_cik)) + "/"
                + self.accession_number.replace("-", "") + "/")

    def to_payload(self) -> dict[str, str]:
        return dict(self.__dict__)


def _filing_date(raw: str) -> str:
    match = _DATE_RE.fullmatch(raw) if type(raw) is str else None
    if match is None or match.group(2) not in _MONTHS:
        raise SecPilotError("REFUSED: SUBMISSION filing date has an unapproved spelling")
    day, month, year = match.groups()
    try:
        return date(int(year), _MONTHS[month], int(day)).isoformat()
    except ValueError as exc:
        raise SecPilotError("REFUSED: SUBMISSION filing date is invalid") from exc


def _plain_path(value: str | Path, *, must_exist: bool) -> Path:
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise SecPilotError("REFUSED: root must be an absolute non-traversing path")
    for component in (*reversed(path.parents), path):
        try:
            info = component.lstat()
        except FileNotFoundError:
            if must_exist or component != path:
                raise SecPilotError("REFUSED: root ancestor is missing")
            continue
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise SecPilotError("REFUSED: root traverses a redirect or non-directory")
    if must_exist and not path.is_dir():
        raise SecPilotError("REFUSED: input root is missing")
    return path


def _safe_roots(input_root: str | Path, prior_root: str | Path, output_root: str | Path) -> tuple[Path, Path, Path]:
    source = _plain_path(input_root, must_exist=True)
    prior = _plain_path(prior_root, must_exist=True)
    output = _plain_path(output_root, must_exist=False)
    lane_root = Path(__file__).resolve().parents[1]
    for existing in (source, prior, lane_root):
        if os.path.commonpath((str(output), str(existing))) == str(existing) or os.path.commonpath((str(output), str(existing))) == str(output):
            raise SecPilotError("REFUSED: output overlaps source, prior pilot, or Git lane")
        # Case-preserving spellings are not identities on the default Mac
        # volume. An existing output ancestor may be the same inode as a
        # protected root even when its path string differs by case.
        for ancestor in output.parents:
            if ancestor.exists() and os.path.samefile(ancestor, existing):
                raise SecPilotError("REFUSED: output overlaps source, prior pilot, or Git lane")
    if output.exists():
        raise SecPilotError("REFUSED: output root must not exist")
    return source, prior, output


def select_fixed_pilot(input_root: str | Path, prior_pilot_root: str | Path) -> tuple[SecPilotCandidate, ...]:
    """Replay only pinned raw ZIPs and SUBMISSION tables; never reread all 901k rows."""
    source = _plain_path(input_root, must_exist=True)
    prior = _plain_path(prior_pilot_root, must_exist=True)
    bindings = approved_ib1b_archive_bindings()
    profile = approved_ib1b_schema_profile()
    verify_approved_ib1b_archive_bindings(bindings)
    verify_approved_ib1b_schema_profile(profile)
    if tuple((b.year, b.quarter) for b in bindings) != _PERIODS:
        raise SecPilotError("REFUSED: archive bindings are not the approved two quarters")
    candidates: list[SecPilotCandidate] = []
    for binding in bindings:
        key = binding.year, binding.quarter
        raw_id, raw_lineage = _RAW_IDENTITIES[key]
        source_bytes = _read_regular_bytes(
            source / binding.filename, label="approved SEC ZIP", max_bytes=binding.archive_size_bytes,
        )
        if len(source_bytes) != binding.archive_size_bytes or hash_bytes(source_bytes) != binding.archive_sha256:
            raise SecPilotError("REFUSED: original quarterly ZIP differs from frozen binding")
        raw = load_sec_bulk_snapshot(prior / "ib1a" / raw_id)
        identity = raw.identity
        if (identity.snapshot_id != raw_id or identity.lineage_hash != raw_lineage
                or identity.archive_sha256 != binding.archive_sha256
                or raw.archive_bytes != source_bytes):
            raise SecPilotError("REFUSED: prior raw snapshot differs from the original ZIP")
        submission = next((m for m in identity.members if m.name == "SUBMISSION.tsv"), None)
        receipt = next((h for h in binding.header_receipts if h.table_name == "SUBMISSION.tsv"), None)
        if submission is None or receipt is None or submission.size_bytes != receipt.expanded_size_bytes:
            raise SecPilotError("REFUSED: approved SUBMISSION member is missing")
        with zipfile.ZipFile(io.BytesIO(source_bytes)) as archive:
            member_bytes = archive.read("SUBMISSION.tsv")
        if len(member_bytes) != submission.size_bytes or hash_bytes(member_bytes) != submission.sha256:
            raise SecPilotError("REFUSED: SUBMISSION bytes disagree with raw snapshot lineage")
        _, rows, _ = _parse_table(
            member_bytes=member_bytes, table_name="SUBMISSION.tsv", raw_member_sha256=submission.sha256,
            raw_snapshot_id=raw_id, raw_lineage_hash=raw_lineage,
            raw_archive_sha256=binding.archive_sha256,
            year=binding.year, quarter=binding.quarter, schema_profile=profile,
        )
        headers = profile.variant_for("SUBMISSION.tsv", *key).headers
        by_accession = {row.accession_number: row for row in rows}
        if len(by_accession) != len(rows):
            raise SecPilotError("REFUSED: duplicate SUBMISSION accession")
        selected = []
        for form_type, count in (("4", 6), ("4/A", 2)):
            matching = sorted((row for row in rows if row.values[headers.index("DOCUMENT_TYPE")] == form_type),
                              key=lambda row: row.accession_number)
            if len(matching) < count:
                raise SecPilotError("REFUSED: source has too few exact Form 4 or 4/A rows")
            selected.extend(matching[:count])
        for row in selected:
            values = dict(zip(headers, row.values, strict=True))
            filing_date = _filing_date(values["FILING_DATE"])
            candidate = SecPilotCandidate(
                period=f"{binding.year}Q{binding.quarter}", accession_number=row.accession_number,
                form_type=values["DOCUMENT_TYPE"], filing_date_raw=values["FILING_DATE"],
                filing_date=filing_date, issuer_cik=values["ISSUERCIK"],
                quarterly_zip_sha256=binding.archive_sha256, submission_row_id=row.row_id,
                raw_snapshot_id=raw_id, raw_lineage_sha256=raw_lineage,
            )
            PilotAccessionCandidateIdentity(
                period=candidate.period, accession_number=candidate.accession_number,
                form_type=candidate.form_type, filing_date=candidate.filing_date,
                issuer_cik=candidate.issuer_cik, quarterly_zip_sha256=candidate.quarterly_zip_sha256,
                submission_row_sha256=candidate.submission_row_id,
            )
            candidates.append(candidate)
    if len(candidates) != 16 or tuple(c.accession_number for c in candidates) != _EXPECTED_ACCESSIONS:
        raise SecPilotError("REFUSED: fixed 16-accession inventory drifted")
    return tuple(candidates)


def _json_no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise SecPilotError("REFUSED: SEC directory index repeats a JSON key")
        result[key] = value
    return result


def _primary_filename(index_bytes: bytes) -> str:
    try:
        index = json.loads(index_bytes, object_pairs_hook=_json_no_duplicate_keys)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SecPilotError("REFUSED: SEC directory index is not strict JSON") from exc
    if type(index) is not dict or type(index.get("directory")) is not dict:
        raise SecPilotError("REFUSED: SEC index has no directory object")
    items = index["directory"].get("item")
    if type(items) is not list or len(items) > 512:
        raise SecPilotError("REFUSED: SEC index has no bounded item list")
    names = []
    for item in items:
        if type(item) is not dict or type(item.get("name")) is not str:
            raise SecPilotError("REFUSED: SEC index item lacks an exact name")
        name = item["name"]
        if name.lower().endswith(".xml"):
            if len(name) > 255 or _XML_NAME_RE.fullmatch(name) is None or name.casefold().startswith("xsl"):
                raise SecPilotError("REFUSED: XML item is not a safe raw root filename")
            names.append(name)
    if len(names) != 1 or len(set(names)) != 1:
        raise SecPilotError("REFUSED: primary raw XML is absent or ambiguous in index.json")
    return names[0]


def _validate_xml(raw: bytes, candidate: SecPilotCandidate) -> None:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise SecPilotError("REFUSED: primary XML must be strict UTF-8") from exc
    # Expat honors the XML declaration and can expand internal DTD entities;
    # checking only ASCII bytes misses a UTF-16 declaration and DTD entirely.
    # Accept no alternate encoding, BOM, or misplaced/foreign declaration.
    if text.startswith("\ufeff"):
        raise SecPilotError("REFUSED: primary XML must be strict UTF-8 without BOM")
    declaration = re.match(
        r"\A<\?xml\s+version=['\"]1\.0['\"](?:\s+encoding=['\"]UTF-8['\"])?"
        r"(?:\s+standalone=['\"](?:yes|no)['\"])?\s*\?>",
        text, flags=re.IGNORECASE,
    )
    if re.search(r"<\?xml", text, flags=re.IGNORECASE) and declaration is None:
        raise SecPilotError("REFUSED: primary XML has a foreign declaration")
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise SecPilotError("REFUSED: raw XML declares a DTD or entity")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise SecPilotError("REFUSED: primary XML is malformed") from exc
    if root.tag != "ownershipDocument":
        raise SecPilotError("REFUSED: primary XML is not a Form 4 ownership document")
    if (len(root.findall("documentType")) != 1 or len(root.findall("issuer")) != 1
            or len(root.findall("issuer/issuerCik")) != 1):
        raise SecPilotError("REFUSED: primary XML identity fields are missing or ambiguous")
    form = root.findtext("documentType")
    issuer = root.findtext("issuer/issuerCik")
    if (form != candidate.form_type or issuer is None or not issuer.isascii()
            or not issuer.isdigit() or not 1 <= len(issuer) <= 10
            or int(issuer) != int(candidate.issuer_cik)):
        raise SecPilotError("REFUSED: XML form or issuer disagrees with approved source")


def _fetch_sec(path: str, user_agent: str) -> tuple[int, bytes]:
    if not re.fullmatch(r"/Archives/edgar/data/[1-9][0-9]*/[0-9]{18}/[A-Za-z0-9_.-]+", path):
        raise SecPilotError("REFUSED: URL path escaped the exact SEC accession directory")
    connection = http.client.HTTPSConnection("www.sec.gov", timeout=15)
    try:
        connection.request("GET", path, headers={
            "User-Agent": user_agent, "Accept": "*/*", "Accept-Encoding": "identity", "Connection": "close",
        })
        response = connection.getresponse()
        # An access denial or redirect is decided from status alone. Do not
        # require a body on these paths, and never follow their Location.
        if response.status != 200:
            return response.status, b""
        headers = response.getheaders()
        lengths = [value for key, value in headers if key.lower() == "content-length"]
        encodings = [value for key, value in headers if key.lower() == "content-encoding"]
        transfers = [value for key, value in headers if key.lower() == "transfer-encoding"]
        if len(lengths) != 1 or not lengths[0].isdigit() or int(lengths[0]) > MAX_BODY_BYTES:
            raise SecPilotGlobalStop("REFUSED: SEC response Content-Length is missing, duplicate or oversized")
        if len(encodings) > 1 or (encodings and encodings[0].lower() != "identity"):
            raise SecPilotGlobalStop("REFUSED: SEC response uses unsupported compression")
        if transfers:
            raise SecPilotGlobalStop("REFUSED: SEC response uses unbounded transfer encoding")
        length = int(lengths[0])
        content = response.read(length)
        if len(content) != length:
            raise SecPilotGlobalStop("REFUSED: SEC response body disagrees with its declared size")
        return response.status, content
    finally:
        connection.close()


class _Journal:
    def __init__(self, output: Path, expected_identity: tuple[int, int] | None = None) -> None:
        self.output = output
        self.directory_fd = _open_output_directory(output, expected_identity)
        self.root_identity = _check_output_directory(output, self.directory_fd)
        try:
            descriptor = os.open(
                "attempts.jsonl", os.O_WRONLY | os.O_CREAT | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=self.directory_fd,
            )
            self.handle = os.fdopen(descriptor, "wb")
            # File-content fsync alone cannot make its directory entry durable.
            os.fsync(self.directory_fd)
            _check_output_directory(output, self.directory_fd, self.root_identity)
        except BaseException:
            if hasattr(self, "handle"):
                self.handle.close()
            os.close(self.directory_fd)
            raise
        self.count = 0
        self.distinct: set[str] = set()
        self.attempts_by_path: dict[str, int] = {}
        self.last_request_at = 0.0

    def event(self, payload: dict[str, object]) -> None:
        _check_output_directory(self.output, self.directory_fd, self.root_identity)
        self.handle.write((canonical_json(payload) + "\n").encode("utf-8"))
        self.handle.flush()
        os.fsync(self.handle.fileno())
        _check_output_directory(self.output, self.directory_fd, self.root_identity)

    def fetch(self, path: str, user_agent: str) -> tuple[int, bytes]:
        if self.count >= MAX_TOTAL_ATTEMPTS:
            raise SecPilotError("REFUSED: 144-attempt ceiling reached")
        if path not in self.distinct and len(self.distinct) >= MAX_DISTINCT_REQUESTS:
            raise SecPilotError("REFUSED: 48-distinct-artifact ceiling reached")
        used = self.attempts_by_path.get(path, 0)
        if used >= MAX_ATTEMPTS:
            raise SecPilotError("REFUSED: artifact has exhausted its three attempts")
        self.distinct.add(path)
        for attempt in range(used + 1, MAX_ATTEMPTS + 1):
            if self.count >= MAX_TOTAL_ATTEMPTS:
                raise SecPilotError("REFUSED: 144-attempt ceiling reached")
            remaining = MIN_REQUEST_INTERVAL_SECONDS - (time.monotonic() - self.last_request_at)
            if remaining > 0:
                time.sleep(remaining)
            self.count += 1
            self.attempts_by_path[path] = attempt
            self.event({"kind": "attempt-reserved", "ordinal": self.count, "path": path, "attempt": attempt})
            self.last_request_at = time.monotonic()
            _check_output_directory(self.output, self.directory_fd, self.root_identity)
            try:
                status, content = _fetch_sec(path, user_agent)
            except (OSError, http.client.HTTPException) as exc:
                self.event({"kind": "attempt-network-error", "ordinal": self.count, "error_type": type(exc).__name__})
                if attempt == MAX_ATTEMPTS:
                    raise SecPilotGlobalStop("REFUSED: SEC request exhausted bounded transport retries") from exc
                time.sleep(attempt)
                continue
            except SecPilotGlobalStop as exc:
                self.event({"kind": "attempt-framing-refusal", "ordinal": self.count, "reason": str(exc)})
                raise
            self.event({"kind": "attempt-response", "ordinal": self.count, "status": status,
                        "size_bytes": len(content), "sha256": hash_bytes(content)})
            if status == 200:
                return status, content
            if status in (403, 429):
                raise SecPilotGlobalStop(f"REFUSED: SEC access stopped on HTTP {status}")
            if status in (500, 502, 503, 504) and attempt < MAX_ATTEMPTS:
                time.sleep(attempt)
                continue
            if status in (500, 502, 503, 504):
                raise SecPilotGlobalStop(f"REFUSED: SEC service remained unavailable at HTTP {status}")
            raise SecPilotError(f"REFUSED: SEC response HTTP {status}; no fallback URL")
        raise AssertionError("bounded SEC retry loop did not terminate")

    def close(self) -> None:
        try:
            self.handle.close()
        finally:
            os.close(self.directory_fd)


def _store_object(output: Path, raw: bytes,
                  expected_identity: tuple[int, int] | None = None) -> dict[str, object]:
    digest = hash_bytes(raw)
    object_dir = output / "objects"
    final_name = f"{digest}.bin"
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    root_fd = _open_output_directory(output, expected_identity)
    try:
        directory_fd = os.open("objects", flags, dir_fd=root_fd)
    except BaseException:
        os.close(root_fd)
        raise
    temporary_name = f".sec-object-{uuid.uuid4().hex}.tmp"
    created_temporary = False
    try:
        opened = os.fstat(directory_fd)
        current = object_dir.lstat()
        if not stat.S_ISDIR(current.st_mode) or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            raise SecPilotError("REFUSED: object directory changed before publication")
        try:
            existing_fd = os.open(final_name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
        except FileNotFoundError:
            existing_fd = None
        if existing_fd is not None:
            try:
                existing_info = os.fstat(existing_fd)
                if (not stat.S_ISREG(existing_info.st_mode) or existing_info.st_nlink != 1
                        or existing_info.st_size != len(raw) or os.read(existing_fd, len(raw) + 1) != raw):
                    raise SecPilotError("REFUSED: immutable content path conflicts")
            finally:
                os.close(existing_fd)
        else:
            descriptor = os.open(
                temporary_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600, dir_fd=directory_fd,
            )
            created_temporary = True
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            current = object_dir.lstat()
            if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
                raise SecPilotError("REFUSED: object directory changed before publication")
            # A complete fsynced temporary gets its immutable hash name only
            # by exclusive link. No half-written final object is visible.
            os.link(temporary_name, final_name, src_dir_fd=directory_fd,
                    dst_dir_fd=directory_fd, follow_symlinks=False)
            os.fsync(directory_fd)
        current = object_dir.lstat()
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            raise SecPilotError("REFUSED: object directory changed after publication")
        _check_output_directory(output, root_fd, expected_identity)
    finally:
        try:
            if created_temporary:
                os.unlink(temporary_name, dir_fd=directory_fd)
                os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
            os.close(root_fd)
    return {"relative_path": f"objects/{digest}.bin", "sha256": digest, "size_bytes": len(raw)}


def _write_inventory_before_request(output: Path, candidates: list[dict[str, str]],
                                    digest: str, expected_identity: tuple[int, int] | None = None) -> None:
    payload = {"kind": "sec-pilot-frozen-inventory", "version": PILOT_VERSION,
               "index_route_version": INDEX_ROUTE_VERSION,
               "inventory_sha256": digest, "candidates": candidates}
    directory_fd = _open_output_directory(output, expected_identity)
    try:
        with (output / "inventory.json").open("xb") as handle:
            handle.write((canonical_json(payload) + "\n").encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        _check_output_directory(output, directory_fd, expected_identity)
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _publish_immutable(output: Path, name: str, content: bytes,
                       expected_identity: tuple[int, int] | None) -> Path:
    directory_fd = _open_output_directory(output, expected_identity)
    temporary = f".sec-publish-{uuid.uuid4().hex}.tmp"
    created = False
    try:
        descriptor = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=directory_fd,
        )
        created = True
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        _check_output_directory(output, directory_fd, expected_identity)
        os.link(temporary, name, src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd, follow_symlinks=False)
        os.fsync(directory_fd)
        _check_output_directory(output, directory_fd, expected_identity)
    finally:
        try:
            if created:
                os.unlink(temporary, dir_fd=directory_fd)
                os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    return output / name


def _write_commit_last(output: Path, payload: dict[str, object],
                       expected_identity: tuple[int, int] | None = None) -> Path:
    report_bytes = (canonical_json(payload) + "\n").encode("utf-8")
    digest = hash_bytes(report_bytes)
    report = _publish_immutable(output, f"sec-pilot-report-{digest}.json",
                                report_bytes, expected_identity)
    commit = {"kind": "sec-pilot-commit", "report": report.name, "report_sha256": digest}
    _publish_immutable(output, "commit.json", (canonical_json(commit) + "\n").encode("utf-8"),
                       expected_identity)
    return report


def run_fixed_sec_pilot(
    input_root: str | Path, prior_pilot_root: str | Path, output_root: str | Path,
    *, contact_email: str, capture_git_commit: str,
) -> Path:
    """Execute only the approved 16-source SEC compatibility pilot.

    A refusal is retained per accession. No partial row is promoted to IB-1C.
    The contact is used only in a request header, never a persisted artifact.
    """
    if type(contact_email) is not str or len(contact_email) > 254 or _CONTACT_RE.fullmatch(contact_email) is None:
        raise SecPilotError("REFUSED: an identifying contact email is required")
    if type(capture_git_commit) is not str or re.fullmatch(r"[0-9a-f]{40}", capture_git_commit) is None:
        raise SecPilotError("REFUSED: capture commit must be a full lowercase Git SHA")
    source, prior, output = _safe_roots(input_root, prior_pilot_root, output_root)
    selected = select_fixed_pilot(source, prior)
    inventory = [candidate.to_payload() for candidate in selected]
    inventory_hash = hash_payload(inventory)
    _safe_roots(source, prior, output)
    output.mkdir(mode=0o700)
    created = output.lstat()
    output_identity = (created.st_dev, created.st_ino)
    (output / "objects").mkdir(mode=0o700)
    _write_inventory_before_request(output, inventory, inventory_hash, output_identity)
    user_agent = f"InsiderBuyingResearch/0.1 ({contact_email})"
    journal = _Journal(output, output_identity)
    rows: list[dict[str, object]] = []
    halt = False
    try:
        for candidate in selected:
            row: dict[str, object] = {"candidate": candidate.to_payload(), "status": "quarantined",
                                      "artifacts": {}, "reason": None, "primary_xml_filename": None}
            rows.append(row)
            if halt:
                row["reason"] = "not attempted after SEC access stop"
                continue
            base = candidate.archive_path
            try:
                _, index = journal.fetch(base + "index.json", user_agent)
                row["artifacts"]["index"] = _store_object(output, index, output_identity)
                filename = _primary_filename(index)
                row["primary_xml_filename"] = filename
                target = SecAcquisitionTarget(
                    period=candidate.period, accession_number=candidate.accession_number,
                    form_type=candidate.form_type, filing_date=candidate.filing_date,
                    issuer_cik=candidate.issuer_cik, quarterly_zip_sha256=candidate.quarterly_zip_sha256,
                    submission_row_id=candidate.submission_row_id, primary_xml_filename=filename,
                )
                _, header = journal.fetch(base + candidate.accession_number + ".hdr.sgml", user_agent)
                row["artifacts"]["header"] = _store_object(output, header, output_identity)
                projection = derive_sec_header_projection(
                    target, header, source_url=target.header_url,
                    retrieved_at=datetime.now(timezone.utc).replace(microsecond=0),
                    capture_git_commit=capture_git_commit,
                )
                row["header_projection"] = projection.to_payload()
                _, xml = journal.fetch(base + filename, user_agent)
                row["artifacts"]["xml"] = _store_object(output, xml, output_identity)
                _validate_xml(xml, candidate)
                row["status"] = "acquired_noncanonical"
            except (SecPilotError, SecAcquisitionPreparationError) as exc:
                row["reason"] = str(exc)
                if isinstance(exc, SecPilotGlobalStop):
                    halt = True
            except Exception as exc:
                # Unanticipated parser/transport defects are not plausible source
                # refusals. Keep the incomplete journal and do not commit success.
                raise SecPilotError("REFUSED: unexpected SEC pilot defect; incomplete journal retained") from exc
        journal.event({"kind": "pilot-finished", "attempts": journal.count,
                       "distinct_artifacts": len(journal.distinct), "inventory_sha256": inventory_hash})
    finally:
        journal.close()
    payload = {
        "kind": PILOT_VERSION, "canonical": False, "point_in_time_data": False,
        "direct_ib1c_ingest_authorized": False, "source_authenticity_verified": False,
        "official_sec_profile_verified": False, "research_looks": 0,
        "authorized_outcome_looks": 0, "consumed_outcome_looks": 0,
        "sample": "lexical-first-six-4-and-first-two-4A-per-quarter",
        "index_route_version": INDEX_ROUTE_VERSION,
        "inventory_sha256": inventory_hash, "source_zip_bindings_sha256": hash_payload([
            binding.to_payload() for binding in approved_ib1b_archive_bindings()]),
        "attempt_count": journal.count, "distinct_artifact_count": len(journal.distinct),
        "halted_on_sec_access": halt, "rows": rows,
    }
    # A partial fixed sample remains inspectable, but is not an available
    # acquisition of the owner-approved 16-accession inventory.
    payload["acquisition_available"] = (
        len(rows) == len(selected)
        and all(row["status"] == "acquired_noncanonical" for row in rows)
    )
    return _write_commit_last(output, payload, output_identity)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--prior-pilot-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--capture-git-commit", required=True)
    arguments = parser.parse_args(argv)
    contact = getpass.getpass("SEC identifying contact email (not persisted): ")
    print(run_fixed_sec_pilot(
        arguments.input_root, arguments.prior_pilot_root, arguments.output_root,
        contact_email=contact, capture_git_commit=arguments.capture_git_commit,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
