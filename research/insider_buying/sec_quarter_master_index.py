"""Pure, bounded parsing of caller-supplied SEC quarterly ``master.idx`` bytes.

The index's ``Filename`` is the archive locator.  In particular, its CIK
path component must never be reconstructed from a bulk-table issuer or owner
CIK: a filing agent can have a different CIK.  This module does no I/O and
does not authenticate SEC origin, establish point-in-time availability, or
grant canonical, outcome, QC, broker, or trading authority.

The exact-inventory join compares the *entire* Form 4/4-A portion of one
index with a caller inventory.  The subset lookup is intentionally a weaker
compatibility operation for a fixed sample and makes no quarter-completeness
claim.  Neither operation proves that the caller's index was complete or
official at a historical decision time.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from data.hashing import hash_bytes, hash_payload


MASTER_INDEX_PARSER_VERSION = "insider-buying-sec-quarter-master-idx-v1"
MAX_MASTER_INDEX_BYTES = 64 * 1024 * 1024
MAX_MASTER_INDEX_ROWS = 1_000_000
MAX_MASTER_INDEX_LINE_BYTES = 2048
MAX_MASTER_INDEX_HEADER_LINES = 16
_COLUMNS = b"CIK|Company Name|Form Type|Date Filed|Filename"
_HEADER_FIELD_RE = re.compile(rb"[A-Za-z][A-Za-z0-9 -]{0,39}: [\x20-\x7e]{1,1000}\Z")
_DIVIDER_RE = re.compile(rb"-{10,255}\Z")
_CIK_RE = re.compile(r"[0-9]{1,10}\Z")
_ACCESSION_RE = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z")
_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_PATH_RE = re.compile(
    r"edgar/data/(?P<archive_cik>[0-9]{1,10})/"
    r"(?P<accession>[0-9]{10}-[0-9]{2}-[0-9]{6})\.txt\Z"
)
_FORM_RE = re.compile(r"[A-Z0-9][A-Z0-9 /.-]{0,63}\Z")
_HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
_TARGET_FORMS = frozenset(("4", "4/A"))


class SecQuarterMasterIndexError(ValueError):
    """The supplied index or its declared inventory fails closed."""


def _quarter_bounds(year: int, quarter: int) -> tuple[date, date]:
    if type(year) is not int or not 1994 <= year <= 2100:
        raise SecQuarterMasterIndexError("REFUSED: master index year is invalid")
    if type(quarter) is not int or quarter not in (1, 2, 3, 4):
        raise SecQuarterMasterIndexError("REFUSED: master index quarter is invalid")
    first_month = (quarter - 1) * 3 + 1
    start = date(year, first_month, 1)
    end = date(year + 1, 1, 1) if quarter == 4 else date(year, first_month + 3, 1)
    return start, end


def _filing_date(value: str, start: date, end: date) -> None:
    if type(value) is not str or _DATE_RE.fullmatch(value) is None:
        raise SecQuarterMasterIndexError("REFUSED: master index filing date is not ISO")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise SecQuarterMasterIndexError("REFUSED: master index filing date is invalid") from exc
    if not start <= parsed < end:
        raise SecQuarterMasterIndexError("REFUSED: master index filing date is outside quarter")


@dataclass(frozen=True)
class SecMasterIndexExpectedRow:
    accession_number: str
    form_type: str
    filing_date: str

    def __post_init__(self) -> None:
        if (
            type(self.accession_number) is not str
            or _ACCESSION_RE.fullmatch(self.accession_number) is None
            or type(self.form_type) is not str
            or self.form_type not in _TARGET_FORMS
            or type(self.filing_date) is not str
            or _DATE_RE.fullmatch(self.filing_date) is None
        ):
            raise SecQuarterMasterIndexError("REFUSED: expected accession tuple is invalid")
        try:
            date.fromisoformat(self.filing_date)
        except ValueError as exc:
            raise SecQuarterMasterIndexError("REFUSED: expected filing date is invalid") from exc


@dataclass(frozen=True)
class SecMasterIndexRow:
    accession_number: str
    form_type: str
    filing_date: str
    archive_path: str

    def __post_init__(self) -> None:
        if (
            type(self.accession_number) is not str
            or _ACCESSION_RE.fullmatch(self.accession_number) is None
            or type(self.form_type) is not str
            or self.form_type not in _TARGET_FORMS
            or type(self.filing_date) is not str
            or _DATE_RE.fullmatch(self.filing_date) is None
            or type(self.archive_path) is not str
        ):
            raise SecQuarterMasterIndexError("REFUSED: Form 4 index row is invalid")
        match = _PATH_RE.fullmatch(self.archive_path)
        if (
            match is None
            or int(match.group("archive_cik")) == 0
            or match.group("accession") != self.accession_number
        ):
            raise SecQuarterMasterIndexError("REFUSED: index archive path contradicts accession")
        try:
            date.fromisoformat(self.filing_date)
        except ValueError as exc:
            raise SecQuarterMasterIndexError("REFUSED: Form 4 filing date is invalid") from exc

    def to_payload(self) -> dict[str, str]:
        return {
            "accession_number": self.accession_number,
            "form_type": self.form_type,
            "filing_date": self.filing_date,
            "archive_path": self.archive_path,
        }


@dataclass(frozen=True)
class SecQuarterMasterIndexReceipt:
    year: int
    quarter: int
    source_sha256: str
    source_size_bytes: int
    all_filing_row_count: int
    rows: tuple[SecMasterIndexRow, ...]
    receipt_sha256: str

    def __post_init__(self) -> None:
        start, end = _quarter_bounds(self.year, self.quarter)
        if (
            type(self.source_sha256) is not str
            or _HASH_RE.fullmatch(self.source_sha256) is None
            or type(self.source_size_bytes) is not int
            or not 0 < self.source_size_bytes <= MAX_MASTER_INDEX_BYTES
            or type(self.all_filing_row_count) is not int
            or not 0 <= self.all_filing_row_count <= MAX_MASTER_INDEX_ROWS
            or type(self.rows) is not tuple
            or type(self.receipt_sha256) is not str
            or _HASH_RE.fullmatch(self.receipt_sha256) is None
            or len(self.rows) > self.all_filing_row_count
        ):
            raise SecQuarterMasterIndexError("REFUSED: master index receipt scalars are invalid")
        accessions: list[str] = []
        paths: set[str] = set()
        for row in self.rows:
            if type(row) is not SecMasterIndexRow:
                raise SecQuarterMasterIndexError("REFUSED: master index row type is invalid")
            row.__post_init__()
            _filing_date(row.filing_date, start, end)
            accessions.append(row.accession_number)
            if row.archive_path in paths:
                raise SecQuarterMasterIndexError("REFUSED: duplicate Form 4 archive path")
            paths.add(row.archive_path)
        if accessions != sorted(set(accessions)):
            raise SecQuarterMasterIndexError("REFUSED: Form 4 accessions are duplicate or unordered")
        if hash_payload(self._identity_payload()) != self.receipt_sha256:
            raise SecQuarterMasterIndexError("REFUSED: master index receipt fingerprint mismatch")

    def _identity_payload(self) -> dict[str, object]:
        return {
            "parser_version": MASTER_INDEX_PARSER_VERSION,
            "year": self.year,
            "quarter": self.quarter,
            "source_sha256": self.source_sha256,
            "source_size_bytes": self.source_size_bytes,
            "all_filing_row_count": self.all_filing_row_count,
            "rows": [row.to_payload() for row in self.rows],
        }

    def to_payload(self) -> dict[str, object]:
        return {**self._identity_payload(), "receipt_sha256": self.receipt_sha256}


def _line_vector(raw_bytes: bytes) -> list[bytes]:
    if type(raw_bytes) is not bytes or not 0 < len(raw_bytes) <= MAX_MASTER_INDEX_BYTES:
        raise SecQuarterMasterIndexError("REFUSED: master index byte budget or type is invalid")
    if not raw_bytes.endswith(b"\n") or raw_bytes.startswith((b"\xef\xbb\xbf", b"\xff\xfe")):
        raise SecQuarterMasterIndexError("REFUSED: master index envelope is invalid")
    # Count in the raw byte buffer before split() allocates one object per
    # line. A 64 MiB stream of newlines would otherwise create millions of
    # Python objects despite the later body-row budget.
    if raw_bytes.count(b"\n") > MAX_MASTER_INDEX_HEADER_LINES + 2 + MAX_MASTER_INDEX_ROWS:
        raise SecQuarterMasterIndexError("REFUSED: master index pre-split line count exceeds budget")
    lines = raw_bytes.split(b"\n")[:-1]
    if any(len(line) > MAX_MASTER_INDEX_LINE_BYTES for line in lines):
        raise SecQuarterMasterIndexError("REFUSED: master index line exceeds byte budget")
    endings = {line.endswith(b"\r") for line in lines}
    if len(endings) != 1:
        raise SecQuarterMasterIndexError("REFUSED: master index mixes newline conventions")
    if endings == {True}:
        lines = [line[:-1] for line in lines]
    if any(b"\r" in line or b"\x00" in line for line in lines):
        raise SecQuarterMasterIndexError("REFUSED: master index contains control bytes")
    return lines


def _body_start(lines: list[bytes]) -> int:
    try:
        column_index = lines.index(_COLUMNS)
    except ValueError as exc:
        raise SecQuarterMasterIndexError("REFUSED: master index columns are absent") from exc
    if not 1 <= column_index <= MAX_MASTER_INDEX_HEADER_LINES or column_index + 1 >= len(lines):
        raise SecQuarterMasterIndexError("REFUSED: master index header is unbounded or incomplete")
    preamble = lines[:column_index]
    if preamble[-1] == b"":
        preamble = preamble[:-1]
    if not preamble or any(not _HEADER_FIELD_RE.fullmatch(line) for line in preamble):
        raise SecQuarterMasterIndexError("REFUSED: master index preamble is malformed")
    keys = [line.split(b": ", 1)[0] for line in preamble]
    if len(keys) != len(set(keys)) or keys[0] != b"Description":
        raise SecQuarterMasterIndexError("REFUSED: master index preamble keys are invalid")
    if b"Master Index" not in preamble[0]:
        raise SecQuarterMasterIndexError("REFUSED: master index description is not master")
    if _DIVIDER_RE.fullmatch(lines[column_index + 1]) is None:
        raise SecQuarterMasterIndexError("REFUSED: master index divider is malformed")
    return column_index + 2


def parse_sec_quarter_master_index(
    raw_bytes: bytes, *, year: int, quarter: int
) -> SecQuarterMasterIndexReceipt:
    """Parse exact caller bytes, retaining only Form 4/4-A locator rows.

    The SHA-256 identifies supplied bytes; it is not an SEC signature.  A
    caller must independently establish source URL, retrieval provenance,
    completeness and historical availability before using this in evidence.
    """
    start, end = _quarter_bounds(year, quarter)
    lines = _line_vector(raw_bytes)
    body_start = _body_start(lines)
    if body_start == len(lines):
        raise SecQuarterMasterIndexError("REFUSED: master index has no filing rows")
    if len(lines) - body_start > MAX_MASTER_INDEX_ROWS:
        raise SecQuarterMasterIndexError("REFUSED: master index row count exceeds budget")
    rows: list[SecMasterIndexRow] = []
    seen_accessions: set[str] = set()
    seen_paths: set[str] = set()
    for line in lines[body_start:]:
        try:
            fields = line.decode("latin-1").split("|")
        except UnicodeDecodeError as exc:  # latin-1 is total; retained as a defensive boundary
            raise SecQuarterMasterIndexError("REFUSED: master index row decoding failed") from exc
        if len(fields) != 5:
            raise SecQuarterMasterIndexError("REFUSED: master index row field count is invalid")
        cik, company, form, filed, path = fields
        if _CIK_RE.fullmatch(cik) is None or int(cik) == 0:
            raise SecQuarterMasterIndexError("REFUSED: master index CIK is invalid")
        if (
            not 0 < len(company) <= 1024
            or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in company)
            or _FORM_RE.fullmatch(form) is None
        ):
            raise SecQuarterMasterIndexError("REFUSED: master index row fields are malformed")
        _filing_date(filed, start, end)
        path_match = _PATH_RE.fullmatch(path)
        if path_match is None or int(path_match.group("archive_cik")) == 0:
            raise SecQuarterMasterIndexError("REFUSED: master index archive path is malformed")
        accession = path_match.group("accession")
        if accession in seen_accessions or path in seen_paths:
            raise SecQuarterMasterIndexError("REFUSED: master index repeats an accession or path")
        seen_accessions.add(accession)
        seen_paths.add(path)
        if form in _TARGET_FORMS:
            rows.append(SecMasterIndexRow(accession, form, filed, path))
        elif form.replace(" ", "").casefold() in {"4", "4/a"}:
            raise SecQuarterMasterIndexError("REFUSED: Form 4 spelling is not canonical")
    ordered_rows = tuple(sorted(rows, key=lambda row: row.accession_number))
    source_sha256 = hash_bytes(raw_bytes)
    payload = {
        "parser_version": MASTER_INDEX_PARSER_VERSION,
        "year": year,
        "quarter": quarter,
        "source_sha256": source_sha256,
        "source_size_bytes": len(raw_bytes),
        "all_filing_row_count": len(lines) - body_start,
        "rows": [row.to_payload() for row in ordered_rows],
    }
    return SecQuarterMasterIndexReceipt(
        year=year,
        quarter=quarter,
        source_sha256=source_sha256,
        source_size_bytes=len(raw_bytes),
        all_filing_row_count=len(lines) - body_start,
        rows=ordered_rows,
        receipt_sha256=hash_payload(payload),
    )


def _expected_map(
    receipt: SecQuarterMasterIndexReceipt,
    expected_rows: tuple[SecMasterIndexExpectedRow, ...],
) -> dict[str, SecMasterIndexExpectedRow]:
    if type(receipt) is not SecQuarterMasterIndexReceipt:
        raise SecQuarterMasterIndexError("REFUSED: master index receipt type is not exact")
    # Re-run immutable receipt validation: a frozen object can still be forged
    # through object.__setattr__, so no join trusts only construction time.
    receipt.__post_init__()
    if (
        type(expected_rows) is not tuple
        or not expected_rows
        or len(expected_rows) > MAX_MASTER_INDEX_ROWS
    ):
        raise SecQuarterMasterIndexError("REFUSED: expected inventory is invalid")
    start, end = _quarter_bounds(receipt.year, receipt.quarter)
    by_accession: dict[str, SecMasterIndexExpectedRow] = {}
    for expected in expected_rows:
        if type(expected) is not SecMasterIndexExpectedRow:
            raise SecQuarterMasterIndexError("REFUSED: expected inventory row type is not exact")
        expected.__post_init__()
        _filing_date(expected.filing_date, start, end)
        if expected.accession_number in by_accession:
            raise SecQuarterMasterIndexError("REFUSED: expected inventory repeats an accession")
        by_accession[expected.accession_number] = expected
    return by_accession


def select_sec_master_index_subset(
    receipt: SecQuarterMasterIndexReceipt,
    expected_rows: tuple[SecMasterIndexExpectedRow, ...],
) -> tuple[SecMasterIndexRow, ...]:
    """Resolve every requested accession without claiming quarter completeness.

    Unrequested Form 4/4-A rows in the index are allowed, so this is suitable
    for a fixed small compatibility sample but *not* an exact corpus audit.
    """
    expected = _expected_map(receipt, expected_rows)
    found = {row.accession_number: row for row in receipt.rows if row.accession_number in expected}
    if set(found) != set(expected):
        raise SecQuarterMasterIndexError("REFUSED: master index is missing requested accessions")
    for accession, row in found.items():
        check = expected[accession]
        if row.form_type != check.form_type or row.filing_date != check.filing_date:
            raise SecQuarterMasterIndexError("REFUSED: master index contradicts requested form or date")
    return tuple(found[expected.accession_number] for expected in expected_rows)


def join_exact_sec_master_inventory(
    receipt: SecQuarterMasterIndexReceipt,
    expected_rows: tuple[SecMasterIndexExpectedRow, ...],
) -> tuple[SecMasterIndexRow, ...]:
    """Match exactly all Form 4/4-A rows in this supplied quarter index.

    This checks inventory equality relative to *these bytes* only.  It does
    not prove the index itself complete, authentic, or point-in-time.
    """
    selected = select_sec_master_index_subset(receipt, expected_rows)
    if len(selected) != len(receipt.rows):
        raise SecQuarterMasterIndexError("REFUSED: master index has extra Form 4 accessions")
    return selected
