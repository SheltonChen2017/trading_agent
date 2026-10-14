"""Pure lossless aggregates, not authority. Hash the ORIGINAL response first.

Missing/truncated evidence stays missing. Caller enforces run quota headroom.
"""
import base64
from datetime import date
import hashlib
import json
import math
import re
import zlib

MAX_RECORD_BYTES = 16384
MAX_WIRE_CHARS = 8192
MAX_LOG_LINES = 1000
MAX_RUN_WIRE_CHARS = 75000
_PREFIX_LIMIT = 256
_KINDS = {"NAV", "COVERAGE", "SUMMARY"}
_WIRE = re.compile(r"MATCHED_Z (NAV|COVERAGE|SUMMARY) ([0-9a-f]{64}) ([A-Za-z0-9+/]+={0,2})")
_MARKER = re.compile(r"MATCHED_[A-Z][A-Z_]*")


class TransportError(ValueError):
    """Fixed, payload-free refusal; no licensed rows are copied to errors."""


def _refuse():
    raise TransportError("invalid bounded aggregate transport") from None


def _json_value(value):
    kind = type(value)
    if kind is dict:
        for key, item in value.items():
            if type(key) is not str:
                _refuse()
            _json_value(item)
    elif kind is list:
        for item in value:
            _json_value(item)
    elif kind is float:
        if not math.isfinite(value):
            _refuse()
    elif kind not in (str, int, bool, type(None)):
        _refuse()


def _canonical(record):
    if type(record) is not dict:
        _refuse()
    try:
        _json_value(record)
        raw = json.dumps(record, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, OverflowError, RecursionError):
        _refuse()
    if not 0 < len(raw) <= MAX_RECORD_BYTES:
        _refuse()
    return raw


def _identity(kind, record):
    if kind not in _KINDS:
        _refuse()
    if kind == "SUMMARY":
        return kind, None
    session = record.get("session")
    try:
        if type(session) is not str or date.fromisoformat(session).isoformat() != session:
            _refuse()
    except (ValueError, TypeError):
        _refuse()
    return kind, session


def encode_record(kind, record):
    """Return one ASCII wire line; unsupported/coerced JSON values refuse."""
    if type(kind) is not str:
        _refuse()
    raw = _canonical(record)
    _identity(kind, record)
    token = base64.b64encode(zlib.compress(raw, 9)).decode("ascii")
    wire = "MATCHED_Z " + kind + " " + hashlib.sha256(raw).hexdigest() + " " + token
    if len(wire) > MAX_WIRE_CHARS:
        _refuse()
    return wire


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            _refuse()
        result[key] = value
    return result


def _inflate(token, digest):
    try:
        compressed = base64.b64decode(token, validate=True)
        if base64.b64encode(compressed).decode("ascii") != token:
            _refuse()
        decoder = zlib.decompressobj()
        raw = decoder.decompress(compressed, MAX_RECORD_BYTES + 1)
        if (len(raw) > MAX_RECORD_BYTES or decoder.unconsumed_tail
                or decoder.unused_data or not decoder.eof
                or hashlib.sha256(raw).hexdigest() != digest):
            _refuse()
        record = json.loads(raw.decode("ascii"), object_pairs_hook=_pairs,
                            parse_constant=lambda unused: _refuse())
        if _canonical(record) != raw:
            _refuse()
    except (ValueError, TypeError, UnicodeError, zlib.error, RecursionError, OverflowError):
        _refuse()
    return record, raw.decode("ascii")


def decode_logs(response):
    """New envelope, exact new records only; missing census still fails audit."""
    if type(response) is not dict or response.get("success") is not True:
        _refuse()
    lines = response.get("logs")
    if (type(lines) is not list or len(lines) > MAX_LOG_LINES
            or type(response.get("length")) is not int or response["length"] != len(lines)):
        _refuse()
    seen, decoded = set(), []
    for line in lines:
        if (type(line) is not str or len(line) > MAX_WIRE_CHARS + _PREFIX_LIMIT
                or "\n" in line or "\r" in line):
            _refuse()
        markers = _MARKER.findall(line)
        if not markers:
            decoded.append(line)
            continue
        if markers != ["MATCHED_Z"]:
            _refuse()
        offset = line.index("MATCHED_Z")
        wire = line[offset:]
        match = _WIRE.fullmatch(wire)
        if offset > _PREFIX_LIMIT or len(wire) > MAX_WIRE_CHARS or match is None:
            _refuse()
        kind, digest, token = match.groups()
        record, raw = _inflate(token, digest)
        identity = _identity(kind, record)
        if identity in seen:
            _refuse()
        seen.add(identity)
        decoded.append(line[:offset] + "MATCHED_" + kind + " " + raw)
    return {**response, "logs": decoded}
