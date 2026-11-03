"""Lossless supplied-byte REMX daily repair candidate, never input admission.

The original member and every row stay reconstructible. Exact positive
integral decimal volume representations may be normalized; genuinely
fractional quantities remain quarantined. Pre-inception rows are a separate
unknown-identity partition, not guessed historical issuer observations.
No file opener, provider, QC/Safari access, or financial execution exists.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
import base64
import csv
from decimal import Decimal
import hashlib
import json
import re

from data.financial_primitives import decimal_effective_scale, to_decimal
from . import firstrate_20261103 as strict

SCHEMA = "tpr-remx-lossless-daily-repair-v1"
SOURCE_EPOCH = "TPR-REMX-LOCAL-REPAIR-20261103-v1"
SOURCE_MEMBER = "REMX_full_1day_UNADJUSTED.txt"
IDENTITY_BOUNDARY = date(2010, 10, 27)
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_ROWS = 10_000
MAX_LINE_BYTES = 512
MAX_TOKEN_CHARS = 64
MAX_VOLUME = Decimal("999999999999999999")
MAX_EXPORT_BYTES = 16 * 1024 * 1024
_VOLUME = re.compile(r"\+?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]{1,3})?\Z")
_CANONICAL_VOLUME = re.compile(r"[1-9][0-9]{0,17}\Z")
_HEADERS = frozenset((
    ("date", "open", "high", "low", "close", "volume"),
    ("datetime", "open", "high", "low", "close", "volume"),
))
_POST_USABLE = frozenset(("post_inception_unchanged", "post_inception_integral_volume_normalized"))


class RepairRefusal(ValueError):
    """Fixed body, non-sensitive reason; never echo a supplied observation."""

    def __init__(self, reason):
        self.reason = reason
        super().__init__("bounded REMX repair candidate refused")


def _fail(reason):
    raise RepairRefusal(reason) from None


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _wire(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


def _volume(text):
    """No rounding: conversion to int follows a proof of exact integrality."""
    if not text:
        return None, "volume_missing"
    if text.startswith("-"):
        return None, "volume_negative"
    if len(text) > MAX_TOKEN_CHARS or _VOLUME.fullmatch(text) is None:
        return None, "volume_lexeme"
    try:
        value = to_decimal(text)
        if value <= 0:
            return None, "volume_not_positive"
        if value > MAX_VOLUME:
            return None, "volume_bound"
        if decimal_effective_scale(value) != 0:
            return None, "volume_fractional"
        # The value is finite, positive, integral and within18digits BEFORE int.
        return str(int(value)), None
    except (ValueError, ArithmeticError):
        return None, "volume_lexeme"


def _body_ending(raw):
    if raw.endswith(b"\r\n"):
        return raw[:-2], b"\r\n"
    if raw.endswith(b"\n") or raw.endswith(b"\r"):
        return raw[:-1], raw[-1:]
    return raw, b""


def _canonical_line(raw_line, volume):
    """Rewrite only the final CSV lexeme, preserving other bytes and ending."""
    body, ending = _body_ending(raw_line)
    separators, quoted, cursor = [], False, 0
    while cursor < len(body):
        char = body[cursor]
        if char == 34:
            if quoted and cursor + 1 < len(body) and body[cursor + 1] == 34:
                cursor += 2
                continue
            quoted = not quoted
        elif char == 44 and not quoted:
            separators.append(cursor)
        cursor += 1
    if quoted or len(separators) != 5:
        _fail("candidate_csv")
    return body[:separators[-1] + 1] + volume.encode("ascii") + ending


@dataclass(frozen=True)
class RepairRow:
    ordinal: int
    raw_line: bytes
    raw_line_sha256: str
    original_fields: tuple[str, ...]
    session_date: date | None
    disposition: str
    reasons: tuple[str, ...]
    canonical_volume: str | None
    candidate_line: bytes | None


@dataclass(frozen=True)
class RepairResult:
    source_raw: bytes
    source_sha256: str
    rows: tuple[RepairRow, ...]
    candidate_bytes: bytes


def _draft(raw_line, ordinal):
    body, _ = _body_ending(raw_line)
    value = {"raw_line": raw_line, "fields": (), "day": None, "header": False,
             "reasons": [], "volume": None}
    if len(raw_line) > MAX_LINE_BYTES:
        value["reasons"].append("line_bound")
        return value
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        value["reasons"].append("encoding")
        return value
    if ordinal == 1 and text.startswith("\ufeff"):
        text = text[1:]
    if "\ufeff" in text or "\0" in text or "\r" in text or "\n" in text:
        value["reasons"].append("row_framing")
        return value
    try:
        parsed = list(csv.reader([text], strict=True))
    except csv.Error:
        value["reasons"].append("csv")
        return value
    if len(parsed) != 1 or len(parsed[0]) != 6:
        value["reasons"].append("field_count")
        return value
    fields = tuple(parsed[0])
    if any(len(cell) > MAX_TOKEN_CHARS for cell in fields):
        value["reasons"].append("token_bound")
        return value
    value["fields"] = fields
    if ordinal == 1 and tuple(cell.casefold() for cell in fields) in _HEADERS:
        value["header"] = True
        return value
    try:
        value["day"] = strict._interval(fields[0], "daily")[0].date()
    except strict.FirstRateRefusal:
        value["reasons"].append("date")
    try:
        opening, high, low, close = (strict._price(cell) for cell in fields[1:5])
        if low > min(opening, close) or high < max(opening, close) or low > high:
            value["reasons"].append("ohlc_geometry")
    except strict.FirstRateRefusal:
        value["reasons"].append("price")
    value["volume"], reason = _volume(fields[5])
    if reason is not None:
        value["reasons"].append(reason)
    return value


def repair_remx_daily(raw, *, expected_sha256):
    """Produce a partial local candidate plus a complete immutable row ledger.

    Caller-supplied hashes prove byte equality only. There is no identity-cutoff,
    zero-volume, fractional-rounding or financial-admission override parameter.
    """
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_SOURCE_BYTES:
        _fail("source_bound")
    if (type(expected_sha256) is not str or
            re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None or
            _sha(raw) != expected_sha256):
        _fail("source_hash")
    lines = raw.splitlines(keepends=True)
    if not 0 < len(lines) <= MAX_ROWS + 1:
        _fail("row_bound")
    drafts = [_draft(line, ordinal) for ordinal, line in enumerate(lines, 1)]
    if sum(not row["header"] for row in drafts) > MAX_ROWS:
        _fail("row_bound")
    counts = Counter(row["day"] for row in drafts if row["day"] is not None)
    sequence = [row["day"] for row in drafts if row["day"] is not None]
    ordering_fault = any(after < before for before, after in zip(sequence, sequence[1:]))
    rows, candidate = [], []
    for ordinal, draft in enumerate(drafts, 1):
        day, fields, reasons = draft["day"], draft["fields"], list(draft["reasons"])
        if day is not None and counts[day] > 1:
            reasons.append("duplicate_date")
        if ordering_fault and not draft["header"]:
            reasons.append("source_out_of_order")
        candidate_line = None
        if draft["header"]:
            disposition = "source_header"
        elif day is not None and day < IDENTITY_BOUNDARY:
            disposition = "pre_inception_identity_quarantine"
        elif reasons == ["volume_fractional"]:
            disposition = "fractional_volume_quarantine"
        elif reasons:
            disposition = "invalid_row_quarantine"
        elif fields and _CANONICAL_VOLUME.fullmatch(fields[5]):
            disposition = "post_inception_unchanged"
            candidate_line = draft["raw_line"]
        else:
            disposition = "post_inception_integral_volume_normalized"
            candidate_line = _canonical_line(draft["raw_line"], draft["volume"])
        if candidate_line is not None:
            candidate.append(candidate_line)
        rows.append(RepairRow(ordinal, draft["raw_line"], _sha(draft["raw_line"]),
            fields, day, disposition, tuple(reasons), draft["volume"], candidate_line))
    candidate_raw = b"".join(candidate)
    if candidate_raw:
        try:
            strict.parse_ohlcv(candidate_raw, expected_sha256=_sha(candidate_raw), symbol="REMX",
                timeframe="daily", member_name=SOURCE_MEMBER, instrument_kind="etf")
        except strict.FirstRateRefusal:
            _fail("candidate_validation")
    result = RepairResult(raw, expected_sha256, tuple(rows), candidate_raw)
    _check_result(result)
    return result


def _check_result(result, *, regenerate=False):
    if (type(result) is not RepairResult or type(result.source_raw) is not bytes
            or not 0 < len(result.source_raw) <= MAX_SOURCE_BYTES
            or type(result.candidate_bytes) is not bytes or type(result.rows) is not tuple
            or not 0 < len(result.rows) <= MAX_ROWS + 1
            or any(type(row) is not RepairRow or type(row.raw_line) is not bytes
                   or (row.candidate_line is not None and type(row.candidate_line) is not bytes)
                   for row in result.rows)):
        _fail("result_integrity")
    if (_sha(result.source_raw) != result.source_sha256
            or b"".join(row.raw_line for row in result.rows) != result.source_raw
            or tuple(row.ordinal for row in result.rows) != tuple(range(1, len(result.rows) + 1))
            or any(_sha(row.raw_line) != row.raw_line_sha256 for row in result.rows)
            or b"".join(row.candidate_line for row in result.rows if row.candidate_line is not None) != result.candidate_bytes):
        _fail("result_integrity")
    if regenerate and repair_remx_daily(result.source_raw,
            expected_sha256=result.source_sha256) != result:
        _fail("result_integrity")


def export_blobs(result):
    """Return bytes for a separately claimed private writer; never open a path.

    The ledger contains licensed original lexemes and rows. Keep all returned
    artifacts private; only the manifest's aggregate counts/hash metadata is
    suitable for a public handoff. Exported candidates remain unadmitted.
    """
    _check_result(result, regenerate=True)
    rows = result.rows
    ledger = b"".join(_wire({
        "ordinal": row.ordinal, "raw_line_base64": base64.b64encode(row.raw_line).decode("ascii"),
        "raw_line_sha256": row.raw_line_sha256, "original_fields": list(row.original_fields),
        "session_date": row.session_date.isoformat() if row.session_date else None,
        "disposition": row.disposition, "reasons": list(row.reasons),
        "canonical_volume": row.canonical_volume,
        "candidate_line_sha256": _sha(row.candidate_line) if row.candidate_line is not None else None,
    }) for row in rows)
    blobs = {
        "source_original.csv": result.source_raw,
        "candidate_post_inception.csv": result.candidate_bytes,
        "quarantine_pre_inception.csv": b"".join(row.raw_line for row in rows if row.disposition == "pre_inception_identity_quarantine"),
        "quarantine_fractional_volume.csv": b"".join(row.raw_line for row in rows if row.disposition == "fractional_volume_quarantine"),
        "quarantine_invalid_rows.csv": b"".join(row.raw_line for row in rows if row.disposition == "invalid_row_quarantine"),
        "row_ledger.jsonl": ledger,
    }
    data_rows = [row for row in rows if row.disposition != "source_header"]
    post_dates = {row.session_date for row in data_rows if row.session_date is not None and row.session_date >= IDENTITY_BOUNDARY}
    usable = [row for row in rows if row.disposition in _POST_USABLE]
    candidate_dates = {row.session_date for row in usable}
    gap_dates = sorted(post_dates - candidate_dates)
    manifest = {
        "schema": SCHEMA, "source_epoch": SOURCE_EPOCH, "source_member": SOURCE_MEMBER,
        "source_sha256": result.source_sha256, "source_bytes": len(result.source_raw),
        "source_rows": len(data_rows), "source_physical_records": len(rows),
        "identity_boundary": IDENTITY_BOUNDARY.isoformat(),
        "identity_boundary_source": strict.REMX_INCEPTION_SOURCE,
        "disposition_counts": dict(sorted(Counter(row.disposition for row in data_rows).items())),
        "quality_reason_counts": dict(sorted(Counter(reason for row in data_rows for reason in row.reasons).items())),
        "candidate_rows": len(usable), "candidate_strict_parser_valid": bool(result.candidate_bytes),
        "post_inception_source_dates": len(post_dates), "candidate_dates": len(candidate_dates),
        "missing_post_inception_source_dates": [day.isoformat() for day in gap_dates],
        "unknown_date_rows": sum(row.session_date is None for row in data_rows),
        "full_source_preserved": True, "all_rows_accounted_for": True,
        "fractional_volumes_rounded_or_truncated": False, "gap_fill_performed": False,
        "source_origin_authenticated": False, "permanent_sid_bound": False,
        "point_in_time_data": False, "source_rights_verified": False,
        "native_qc_mark": False, "source_inputs_admitted": False,
        "full_coverage_verified": False, "backtesting_ready": False,
        "financial_acceptance": False, "canonical_admission": False, "trading_authority": False,
        "outputs": {name: {"bytes": len(raw), "sha256": _sha(raw)} for name, raw in sorted(blobs.items())},
    }
    blobs["manifest.json"] = _wire(manifest)
    if sum(len(raw) for raw in blobs.values()) > MAX_EXPORT_BYTES:
        _fail("export_bound")
    return blobs
