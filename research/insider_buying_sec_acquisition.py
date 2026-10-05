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
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET
import zipfile

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying.sec_acquisition_preparation import (
    MAX_SEC_HEADER_BYTES,
    SecAcquisitionPreparationError,
    SecAcquisitionTarget,
    _eastern_timestamp,
    derive_sec_header_projection,
)
from research.insider_buying.sec_edgar_acceptance_snapshot import (
    SecEdgarAcceptanceSnapshotError,
    SecEdgarAvailabilityRecord,
    SecEdgarAvailabilityRule,
    SecEdgarAvailabilityTier,
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
CONTINUATION_VERSION = "INSETF-SEC-SIXTEEN-XML-CONTINUATION-v1"
FIRST_PASS_REPORT_SHA256 = "410bbb079f9cec25733e798d3aceaea179c0d47d657743d199a041922d81f642"
FIRST_PASS_CODE_COMMIT = "f5430fff9b09a963b5cb0307c9e87b28a69c4767"
FIRST_PASS_ATTEMPTS = 32
MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_ATTEMPTS = 3
MAX_DISTINCT_REQUESTS = 48
MAX_TOTAL_ATTEMPTS = 144
MIN_REQUEST_INTERVAL_SECONDS = 0.5
_CONTACT_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}\Z")
_XML_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)*\.xml\Z")
_DATE_RE = re.compile(r"([0-9]{2})-([A-Z]{3})-([0-9]{4})\Z")
_ASCII_DECIMAL_RE = re.compile(r"[0-9]{1,19}\Z")
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


def _ascii_decimal(value: object) -> bool:
    """True only for ASCII digits.

    ``str.isdigit()`` also accepts characters such as "\u00b2" that ``int()``
    rejects, and digits from other scripts that ``int()`` silently converts.
    http.client decodes header bytes as Latin-1, so both can reach a
    Content-Length check; neither may escape as ValueError or be accepted.
    """
    return type(value) is str and _ASCII_DECIMAL_RE.fullmatch(value) is not None


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


def _refuse_output_overlap(output: Path, protected: Path) -> None:
    if (os.path.commonpath((str(output), str(protected))) in (str(output), str(protected))
            or any(ancestor.exists() and os.path.samefile(ancestor, protected)
                   for ancestor in output.parents)):
        raise SecPilotError("REFUSED: continuation output overlaps the first SEC pass")


def _verify_continuation_code_commit(commit: str) -> None:
    """Bind the current runner file to exact local HEAD; no network or write."""
    if type(commit) is not str or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise SecPilotError("REFUSED: continuation code SHA must be a full lowercase Git commit")
    root = Path(__file__).resolve().parents[1]
    try:
        top = subprocess.check_output(("git", "rev-parse", "--show-toplevel"), cwd=root, stderr=subprocess.DEVNULL).decode().strip()
        branch = subprocess.check_output(("git", "branch", "--show-current"), cwd=root, stderr=subprocess.DEVNULL).decode().strip()
        actual = subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=root, stderr=subprocess.DEVNULL).decode().strip()
        dirty = subprocess.check_output(("git", "status", "--porcelain=v1", "--untracked-files=all"),
                                        cwd=root, stderr=subprocess.DEVNULL)
        committed = subprocess.check_output(("git", "show", f"{commit}:research/insider_buying_sec_acquisition.py"),
                                            cwd=root, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as exc:
        raise SecPilotError("REFUSED: continuation Git source could not be verified") from exc
    if (top != str(root) or branch != "codex/strategy-insider-buying" or dirty
            or actual != commit or hash_bytes(committed) != hash_bytes(Path(__file__).read_bytes())):
        raise SecPilotError("REFUSED: continuation code SHA requires this exact clean committed lane source")


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


def _validate_tag_header(raw: bytes, target: SecAcquisitionTarget) -> dict[str, object]:
    """Validate the observed tag-line dialect, without changing frozen v1.

    Its acceptance timezone interpretation remains caller-declared and
    unverified. A valid receipt is only noncanonical compatibility evidence.
    """
    target.to_payload()
    if type(raw) is not bytes or not raw or len(raw) > MAX_SEC_HEADER_BYTES:
        raise SecPilotError("REFUSED: tag header is not an exact bounded byte image")
    if any(byte < 32 and byte not in (9, 10, 13) for byte in raw) or b"\x00" in raw:
        raise SecPilotError("REFUSED: tag header contains unsupported control bytes")
    try:
        text = raw.decode("ascii", errors="strict").replace("\r\n", "\n")
    except UnicodeDecodeError as exc:
        raise SecPilotError("REFUSED: tag header is not ASCII") from exc
    if "\r" in text:
        raise SecPilotError("REFUSED: tag header has unsupported line endings")
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    expected_open = (f"<SEC-HEADER>{target.accession_number}.hdr.sgml : "
                     f"{target.filing_date.replace('-', '')}")
    if (len(lines) < 8 or lines[0] != expected_open or lines[-1] != "</SEC-HEADER>"
            or sum(line.startswith("<SEC-HEADER>") for line in lines) != 1
            or lines.count("</SEC-HEADER>") != 1):
        raise SecPilotError("REFUSED: tag header envelope disagrees with target")
    body = lines[1:-1]
    roles = [index for index, line in enumerate(body) if line in ("<REPORTING-OWNER>", "<ISSUER>")]
    if not roles:
        raise SecPilotError("REFUSED: tag header has no role sections")
    if any(body.count(marker) != 1 for marker in (
        "<REPORTING-OWNER>", "</REPORTING-OWNER>", "<ISSUER>", "</ISSUER>",
    )):
        raise SecPilotError("REFUSED: tag header has missing or repeated root roles")
    owner_open = body.index("<REPORTING-OWNER>")
    owner_close = body.index("</REPORTING-OWNER>")
    issuer_open = body.index("<ISSUER>")
    issuer_close = body.index("</ISSUER>")
    if (owner_open != roles[0] or not owner_open < owner_close
            or issuer_open != owner_close + 1 or issuer_close != len(body) - 1
            or issuer_open >= issuer_close):
        raise SecPilotError("REFUSED: tag header role topology is invalid")
    preamble = body[:roles[0]]
    allowed_preamble = {
        "ACCEPTANCE-DATETIME", "ACCESSION-NUMBER", "TYPE",
        "PUBLIC-DOCUMENT-COUNT", "PERIOD", "FILING-DATE",
        "DATE-OF-FILING-DATE-CHANGE",
    }
    for line in preamble:
        match = re.fullmatch(r"<([A-Z][A-Z0-9-]*)>([^<>]+)", line)
        if match is None or match.group(1) not in allowed_preamble:
            raise SecPilotError("REFUSED: tag header preamble has nested or foreign fields")

    def field(scope: list[str], tag: str, *, global_unique: bool = False) -> str:
        prefix = f"<{tag}>"
        matching = [line[len(prefix):] for line in scope if line.startswith(prefix)]
        if len(matching) != 1 or not matching[0] or matching[0] != matching[0].strip():
            raise SecPilotError(f"REFUSED: missing or ambiguous tag header {tag}")
        if global_unique and sum(line.startswith(prefix) for line in body) != 1:
            raise SecPilotError(f"REFUSED: duplicate tag header {tag} outside preamble")
        return matching[0]

    accession = field(preamble, "ACCESSION-NUMBER", global_unique=True)
    form = field(preamble, "TYPE", global_unique=True)
    filing_raw = field(preamble, "FILING-DATE", global_unique=True)
    accepted_raw = field(preamble, "ACCEPTANCE-DATETIME", global_unique=True)
    issuer = body[issuer_open + 1:issuer_close]
    if (not issuer or issuer[0] != "<COMPANY-DATA>"
            or issuer.count("<COMPANY-DATA>") != 1
            or issuer.count("</COMPANY-DATA>") != 1):
        raise SecPilotError("REFUSED: issuer COMPANY-DATA is missing or not first")
    company_end = issuer.index("</COMPANY-DATA>")
    company = issuer[1:company_end]
    if any(re.fullmatch(r"<[A-Z][A-Z0-9-]*>[^<>]+", line) is None for line in company):
        raise SecPilotError("REFUSED: issuer COMPANY-DATA contains a nested or empty field")
    issuer_cik = field(company, "CIK")
    if sum(line.startswith("<CIK>") for line in issuer) != 1:
        raise SecPilotError("REFUSED: issuer CIK is ambiguous outside COMPANY-DATA")
    if (accession != target.accession_number or form != target.form_type
            or filing_raw != target.filing_date.replace("-", "")
            or re.fullmatch(r"[0-9]{1,10}", issuer_cik) is None
            or int(issuer_cik) == 0 or issuer_cik.zfill(10) != target.issuer_cik
            or re.fullmatch(r"[0-9]{14}", accepted_raw) is None):
        raise SecPilotError("REFUSED: tag header identity disagrees with frozen source")
    try:
        accepted = _eastern_timestamp(accepted_raw)
        SecEdgarAvailabilityRecord(
            accession_number=target.accession_number, document_type=target.form_type,
            submission_row_id=target.submission_row_id,
            filing_date=date.fromisoformat(target.filing_date),
            availability_tier=SecEdgarAvailabilityTier.EXACT_ACCEPTANCE_TIMESTAMP,
            next_open_rule=SecEdgarAvailabilityRule.NEXT_OPEN_AFTER_ACCEPTANCE,
            accepted_at=accepted, primary_document_url=target.primary_xml_url,
            metadata_source_sha256=hash_bytes(raw),
        )
    except (SecAcquisitionPreparationError, SecEdgarAcceptanceSnapshotError) as exc:
        raise SecPilotError(str(exc)) from exc
    return {
        "version": "sec-header-tag-line-compat-v1",
        "raw_header_sha256": hash_bytes(raw), "raw_header_size_bytes": len(raw),
        "source_url": target.header_url,
        "source_fields": {
            "accession_number": accession, "form_type": form,
            "filing_date_raw": filing_raw, "accepted_at_raw": accepted_raw,
            "issuer_cik_raw": issuer_cik,
        },
        "accepted_at_interpretation": accepted.isoformat(timespec="seconds"),
        "timezone_interpretation_verified": False,
        "retrieval_timestamp_unavailable": True,
        "official_sec_profile_verified": False,
        "direct_ib1c_ingest_authorized": False,
        "canonical": False,
    }


@dataclass(frozen=True)
class _ReplayedSource:
    candidate: SecPilotCandidate
    target: SecAcquisitionTarget
    index_bytes: bytes
    header_bytes: bytes
    tag_receipt: dict[str, object]
    first_pass_reason: str


@dataclass(frozen=True)
class _FirstPassReplay:
    sources: tuple[_ReplayedSource, ...]
    report_sha256: str
    inventory_sha256: str
    journal_sha256: str
    prior_paths: frozenset[str]


def _canonical_object(raw: bytes, *, label: str) -> dict[str, object]:
    try:
        value = json.loads(raw, object_pairs_hook=_json_no_duplicate_keys)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SecPilotError(f"REFUSED: {label} is not strict JSON") from exc
    if type(value) is not dict or (canonical_json(value) + "\n").encode("utf-8") != raw:
        raise SecPilotError(f"REFUSED: {label} is not canonical JSON plus one LF")
    return value


def _read_first_object(root: Path, descriptor: object) -> bytes:
    if (type(descriptor) is not dict or set(descriptor) != {"relative_path", "sha256", "size_bytes"}
            or type(descriptor["sha256"]) is not str
            or re.fullmatch(r"[0-9a-f]{64}", descriptor["sha256"]) is None
            or type(descriptor["size_bytes"]) is not int
            or not 0 < descriptor["size_bytes"] <= MAX_BODY_BYTES
            or descriptor["relative_path"] != f'objects/{descriptor["sha256"]}.bin'):
        raise SecPilotError("REFUSED: first-pass object descriptor is malformed")
    raw = _read_regular_bytes(root / descriptor["relative_path"],
                              label="first-pass SEC object", max_bytes=MAX_BODY_BYTES,
                              require_single_link=True)
    if len(raw) != descriptor["size_bytes"] or hash_bytes(raw) != descriptor["sha256"]:
        raise SecPilotError("REFUSED: first-pass object hash or size disagrees")
    return raw


def replay_first_sec_pass(first_root: str | Path, candidates: tuple[SecPilotCandidate, ...],
                          *, prior_code_commit: str) -> _FirstPassReplay:
    """Fully replay the exact committed 32-object pass, without source writes."""
    if type(prior_code_commit) is not str or prior_code_commit != FIRST_PASS_CODE_COMMIT:
        raise SecPilotError("REFUSED: first-pass code SHA attestation is not the exact operator value")
    root = _plain_path(first_root, must_exist=True)
    report_name = f"sec-pilot-report-{FIRST_PASS_REPORT_SHA256}.json"
    required = {"attempts.jsonl", "inventory.json", "commit.json", "objects", report_name}
    if {child.name for child in root.iterdir()} != required:
        raise SecPilotError("REFUSED: first-pass publication inventory is not exact")
    objects_root = _plain_path(root / "objects", must_exist=True)
    commit = _canonical_object(_read_regular_bytes(root / "commit.json", label="first-pass commit",
                                                  max_bytes=4096, require_single_link=True), label="first-pass commit")
    if commit != {"kind": "sec-pilot-commit", "report": report_name,
                  "report_sha256": FIRST_PASS_REPORT_SHA256}:
        raise SecPilotError("REFUSED: first-pass commit marker disagrees")
    report_bytes = _read_regular_bytes(root / report_name, label="first-pass report",
                                       max_bytes=MAX_BODY_BYTES, require_single_link=True)
    if hash_bytes(report_bytes) != FIRST_PASS_REPORT_SHA256:
        raise SecPilotError("REFUSED: first-pass report digest is not the pinned exact pass")
    report = _canonical_object(report_bytes, label="first-pass report")
    inventory_bytes = _read_regular_bytes(root / "inventory.json", label="first-pass inventory",
                                          max_bytes=128 * 1024, require_single_link=True)
    inventory = _canonical_object(inventory_bytes, label="first-pass inventory")
    candidate_payloads = [candidate.to_payload() for candidate in candidates]
    inventory_hash = hash_payload(candidate_payloads)
    if (inventory != {"kind": "sec-pilot-frozen-inventory", "version": PILOT_VERSION,
                      "index_route_version": INDEX_ROUTE_VERSION,
                      "inventory_sha256": inventory_hash, "candidates": candidate_payloads}
            or report.get("kind") != PILOT_VERSION
            or report.get("inventory_sha256") != inventory_hash
            or report.get("index_route_version") != INDEX_ROUTE_VERSION
            or report.get("source_zip_bindings_sha256") != hash_payload([
                item.to_payload() for item in approved_ib1b_archive_bindings()])
            or report.get("attempt_count") != FIRST_PASS_ATTEMPTS
            or report.get("distinct_artifact_count") != FIRST_PASS_ATTEMPTS
            or report.get("halted_on_sec_access") is not False
            or report.get("acquisition_available") is not False
            or any(report.get(flag) is not False for flag in (
                "canonical", "point_in_time_data", "direct_ib1c_ingest_authorized",
                "source_authenticity_verified", "official_sec_profile_verified"))
            or any(report.get(look) != 0 for look in (
                "research_looks", "authorized_outcome_looks", "consumed_outcome_looks"))):
        raise SecPilotError("REFUSED: first-pass inventory, scope, or authority disagrees")
    rows = report.get("rows")
    if type(rows) is not list or len(rows) != 16 or len(candidates) != 16:
        raise SecPilotError("REFUSED: first-pass row count is not 16")
    journal_bytes = _read_regular_bytes(root / "attempts.jsonl", label="first-pass journal",
                                        max_bytes=128 * 1024, require_single_link=True)
    if not journal_bytes.endswith(b"\n"):
        raise SecPilotError("REFUSED: first-pass journal is not complete JSONL")
    events = [_canonical_object(line + b"\n", label="first-pass journal event")
              for line in journal_bytes.splitlines()]
    if len(events) != FIRST_PASS_ATTEMPTS * 2 + 1 or events[-1] != {
        "kind": "pilot-finished", "attempts": FIRST_PASS_ATTEMPTS,
        "distinct_artifacts": FIRST_PASS_ATTEMPTS, "inventory_sha256": inventory_hash,
    }:
        raise SecPilotError("REFUSED: first-pass journal count or terminal event disagrees")
    sources: list[_ReplayedSource] = []
    paths: list[str] = []
    object_names: set[str] = set()
    for index, (candidate, row) in enumerate(zip(candidates, rows, strict=True)):
        if (type(row) is not dict or row.get("candidate") != candidate.to_payload()
                or row.get("status") != "quarantined"
                or type(row.get("reason")) is not str
                or "header_projection" in row or type(row.get("artifacts")) is not dict
                or set(row["artifacts"]) != {"index", "header"}):
            raise SecPilotError("REFUSED: first-pass row is not the exact quarantined pair")
        raw_index = _read_first_object(objects_root.parent, row["artifacts"]["index"])
        raw_header = _read_first_object(objects_root.parent, row["artifacts"]["header"])
        for role in ("index", "header"):
            object_names.add(row["artifacts"][role]["sha256"] + ".bin")
        filename = _primary_filename(raw_index)
        if filename != row.get("primary_xml_filename"):
            raise SecPilotError("REFUSED: first-pass index filename replay drifted")
        target = SecAcquisitionTarget(
            period=candidate.period, accession_number=candidate.accession_number,
            form_type=candidate.form_type, filing_date=candidate.filing_date,
            issuer_cik=candidate.issuer_cik, quarterly_zip_sha256=candidate.quarterly_zip_sha256,
            submission_row_id=candidate.submission_row_id, primary_xml_filename=filename,
        )
        tag_receipt = _validate_tag_header(raw_header, target)
        sources.append(_ReplayedSource(candidate, target, raw_index, raw_header,
                                       tag_receipt, row["reason"]))
        for role, suffix in (("index", "index.json"),
                             ("header", candidate.accession_number + ".hdr.sgml")):
            path = candidate.archive_path + suffix
            ordinal = index * 2 + (1 if role == "index" else 2)
            descriptor = row["artifacts"][role]
            expected_reservation = {"kind": "attempt-reserved", "ordinal": ordinal,
                                    "path": path, "attempt": 1}
            expected_response = {"kind": "attempt-response", "ordinal": ordinal,
                                 "status": 200, "size_bytes": descriptor["size_bytes"],
                                 "sha256": descriptor["sha256"]}
            if events[2 * (ordinal - 1):2 * ordinal] != [expected_reservation, expected_response]:
                raise SecPilotError("REFUSED: first-pass journal path or response replay drifted")
            paths.append(path)
    if len(set(paths)) != FIRST_PASS_ATTEMPTS or {child.name for child in objects_root.iterdir()} != object_names:
        raise SecPilotError("REFUSED: first-pass path or object inventory is not exact")
    return _FirstPassReplay(tuple(sources), FIRST_PASS_REPORT_SHA256, inventory_hash,
                            hash_bytes(journal_bytes), frozenset(paths))


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
        if len(lengths) != 1 or not _ascii_decimal(lengths[0]) or int(lengths[0]) > MAX_BODY_BYTES:
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
        self.prior_paths: frozenset[str] = frozenset()
        self.last_request_at = 0.0

    def seed_verified_first_pass(self, replay: _FirstPassReplay) -> None:
        if (self.count != 0 or self.distinct or self.attempts_by_path
                or len(replay.prior_paths) != FIRST_PASS_ATTEMPTS):
            raise SecPilotError("REFUSED: first-pass counters cannot be seeded twice")
        self.prior_paths = replay.prior_paths
        self.distinct = set(replay.prior_paths)
        self.attempts_by_path = {path: 1 for path in replay.prior_paths}
        self.count = FIRST_PASS_ATTEMPTS
        self.event({"kind": "verified-first-pass-replayed",
                    "prior_attempts": FIRST_PASS_ATTEMPTS,
                    "prior_distinct_artifacts": FIRST_PASS_ATTEMPTS,
                    "prior_report_sha256": replay.report_sha256,
                    "prior_journal_sha256": replay.journal_sha256})

    def event(self, payload: dict[str, object]) -> None:
        _check_output_directory(self.output, self.directory_fd, self.root_identity)
        self.handle.write((canonical_json(payload) + "\n").encode("utf-8"))
        self.handle.flush()
        os.fsync(self.handle.fileno())
        _check_output_directory(self.output, self.directory_fd, self.root_identity)

    def fetch(self, path: str, user_agent: str) -> tuple[int, bytes]:
        if path in self.prior_paths:
            raise SecPilotError("REFUSED: continuation may not rerequest a first-pass artifact")
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
                                    digest: str, expected_identity: tuple[int, int] | None = None,
                                    continuation: dict[str, object] | None = None) -> None:
    payload = {"kind": "sec-pilot-frozen-inventory", "version": PILOT_VERSION,
               "index_route_version": INDEX_ROUTE_VERSION,
               "inventory_sha256": digest, "candidates": candidates}
    if continuation is not None:
        payload["continuation"] = continuation
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


def run_fixed_sec_xml_continuation(
    input_root: str | Path, prior_pilot_root: str | Path,
    first_sec_root: str | Path, output_root: str | Path, *,
    contact_email: str, prior_code_commit: str, continuation_code_commit: str,
) -> Path:
    """Replay the exact first pass, then request only its 16 index-named XMLs.

    The earlier code SHA is explicitly operator-attested, not artifact-proven.
    The current SHA is checked against local HEAD/source. Neither pass is an
    IB-1C input, authenticated SEC source, canonical result or research look.
    """
    if (type(contact_email) is not str or len(contact_email) > 254
            or _CONTACT_RE.fullmatch(contact_email) is None):
        raise SecPilotError("REFUSED: an identifying contact email is required")
    if type(prior_code_commit) is not str or prior_code_commit != FIRST_PASS_CODE_COMMIT:
        raise SecPilotError("REFUSED: first-pass code SHA attestation is not exact")
    _verify_continuation_code_commit(continuation_code_commit)
    source, prior, output = _safe_roots(input_root, prior_pilot_root, output_root)
    first = _plain_path(first_sec_root, must_exist=True)
    _refuse_output_overlap(output, first)
    selected = select_fixed_pilot(source, prior)
    replay = replay_first_sec_pass(first, selected, prior_code_commit=prior_code_commit)
    # All 16 index/header objects, journal paths and tag identities have been
    # revalidated before creating the new root or issuing any request.
    _safe_roots(source, prior, output)
    _refuse_output_overlap(output, first)
    output.mkdir(mode=0o700)
    created = output.lstat()
    output_identity = (created.st_dev, created.st_ino)
    (output / "objects").mkdir(mode=0o700)
    inventory = [candidate.to_payload() for candidate in selected]
    continuation = {
        "version": CONTINUATION_VERSION,
        "first_pass_report_sha256": replay.report_sha256,
        "first_pass_journal_sha256": replay.journal_sha256,
        "first_pass_attempts": FIRST_PASS_ATTEMPTS,
        "first_pass_code_commit_operator_attested": prior_code_commit,
        "prior_code_sha_artifact_verified": False,
        "continuation_code_commit_verified": continuation_code_commit,
        "requests": [source_item.target.primary_xml_url for source_item in replay.sources],
    }
    _write_inventory_before_request(output, inventory, replay.inventory_sha256,
                                    output_identity, continuation=continuation)
    # Retain a standalone immutable copy of all 32 prior raw byte images.
    # The first root is only read, never updated or relinked.
    prior_objects = []
    for source_item in replay.sources:
        prior_objects.append({
            "index": _store_object(output, source_item.index_bytes, output_identity),
            "header": _store_object(output, source_item.header_bytes, output_identity),
        })
    journal = _Journal(output, output_identity)
    journal.seed_verified_first_pass(replay)
    user_agent = f"InsiderBuyingResearch/0.1 ({contact_email})"
    rows: list[dict[str, object]] = []
    halt = False
    try:
        for source_item, objects in zip(replay.sources, prior_objects, strict=True):
            row: dict[str, object] = {
                "candidate": source_item.candidate.to_payload(),
                "primary_xml_filename": source_item.target.primary_xml_filename,
                "status": "quarantined", "reason": None,
                "first_pass_reason": source_item.first_pass_reason,
                "artifacts": dict(objects),
                "tag_header_validation": source_item.tag_receipt,
            }
            rows.append(row)
            if halt:
                row["reason"] = "not attempted after SEC access stop"
                continue
            path = source_item.candidate.archive_path + source_item.target.primary_xml_filename
            if "https://www.sec.gov" + path != source_item.target.primary_xml_url:
                raise SecPilotError("REFUSED: continuation XML path drifted from frozen index")
            try:
                _, xml = journal.fetch(path, user_agent)
                row["artifacts"]["xml"] = _store_object(output, xml, output_identity)
                _validate_xml(xml, source_item.candidate)
                row["status"] = "acquired_noncanonical"
            except SecPilotGlobalStop as exc:
                row["reason"] = str(exc)
                halt = True
            except SecPilotError as exc:
                row["reason"] = str(exc)
        journal.event({"kind": "continuation-finished", "cumulative_attempts": journal.count,
                       "cumulative_distinct_artifacts": len(journal.distinct),
                       "new_attempts": journal.count - FIRST_PASS_ATTEMPTS,
                       "first_pass_report_sha256": replay.report_sha256})
    finally:
        journal.close()
    payload = {
        "kind": CONTINUATION_VERSION, "canonical": False,
        "point_in_time_data": False, "direct_ib1c_ingest_authorized": False,
        "source_authenticity_verified": False, "official_sec_profile_verified": False,
        "timezone_interpretation_verified": False,
        "research_looks": 0, "authorized_outcome_looks": 0, "consumed_outcome_looks": 0,
        "inventory_sha256": replay.inventory_sha256,
        "index_route_version": INDEX_ROUTE_VERSION,
        "first_pass_report_sha256": replay.report_sha256,
        "first_pass_journal_sha256": replay.journal_sha256,
        "first_pass_code_commit_operator_attested": prior_code_commit,
        "prior_code_sha_artifact_verified": False,
        "continuation_code_commit_verified": continuation_code_commit,
        "cumulative_attempt_count": journal.count,
        "cumulative_distinct_artifact_count": len(journal.distinct),
        "new_attempt_count": journal.count - FIRST_PASS_ATTEMPTS,
        "halted_on_sec_access": halt, "rows": rows,
        "acquisition_available": len(rows) == 16 and all(
            row["status"] == "acquired_noncanonical" for row in rows),
    }
    return _write_commit_last(output, payload, output_identity)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--prior-pilot-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--capture-git-commit", required=True)
    parser.add_argument("--continue-from", help="Exact committed first SEC pass; XML-only mode")
    parser.add_argument("--prior-code-commit", help="Explicit operator attestation of first-pass code")
    arguments = parser.parse_args(argv)
    contact = getpass.getpass("SEC identifying contact email (not persisted): ")
    if arguments.continue_from:
        print(run_fixed_sec_xml_continuation(
            arguments.input_root, arguments.prior_pilot_root, arguments.continue_from,
            arguments.output_root, contact_email=contact,
            prior_code_commit=arguments.prior_code_commit,
            continuation_code_commit=arguments.capture_git_commit,
        ))
    else:
        if arguments.prior_code_commit is not None:
            parser.error("--prior-code-commit requires --continue-from")
        print(run_fixed_sec_pilot(
            arguments.input_root, arguments.prior_pilot_root, arguments.output_root,
            contact_email=contact, capture_git_commit=arguments.capture_git_commit,
        ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
