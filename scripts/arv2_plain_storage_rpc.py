"""Bounded binary framing for two inherited, unidirectional storage pipes.

Only framing is provided: the caller must validate its exact application
schemas, source/inventory pins, dispatch order and budget before any contact.
Payloads are opaque bytes, never interpreted, printed, logged or serialized as
JSON. This module has no operational entrypoint, network or credential access.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import select
import stat
import struct
import time


SCHEMA = "arv2-plain-storage-rpc-v1"
MAGIC = b"ARV2RPC1"
MAX_HEADER_BYTES = 32 * 1024
MAX_PAYLOAD_BYTES = 32 * 1024 * 1024 + 4096
MAX_HEADER_DEPTH = 16
MAX_HEADER_NODES = 4096
PREFIX = struct.Struct("!8sIQ")
MAX_FRAME_BYTES = PREFIX.size + MAX_HEADER_BYTES + MAX_PAYLOAD_BYTES
_FIELDS = frozenset(("schema", "header", "payload_byte_count", "payload_sha256"))
_CODES = frozenset(("header", "header_bound", "header_schema", "payload", "payload_hash",
    "prefix", "frame_bound", "trailing", "descriptor", "deadline", "eof", "io", "pending"))


class PlainStorageRPCError(ValueError):
    """Finite category only; never includes source bytes or exception text."""


def _require(condition, code):
    if not condition:
        raise PlainStorageRPCError(code)


def finite_failure(error):
    if type(error) is PlainStorageRPCError:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in _CODES:
            return args[0]
    return "unknown_exception"


def _fields(value):
    _require(type(value) in (set, frozenset)
        and len(value) <= MAX_HEADER_NODES
        and all(type(key) is str and 0 < len(key) <= 128 for key in value), "header_schema")
    return frozenset(value)


def _json_tree(value):
    pending, count = [(value, 0)], 0
    while pending:
        item, depth = pending.pop()
        count += 1
        _require(count <= MAX_HEADER_NODES and depth <= MAX_HEADER_DEPTH, "header_bound")
        kind = type(item)
        if item is None or kind is bool:
            continue
        if kind is int:
            _require(-(2 ** 63) <= item < 2 ** 63, "header")
        elif kind is str:
            _require(len(item) <= MAX_HEADER_BYTES, "header_bound")
        elif kind is list:
            _require(len(item) <= MAX_HEADER_NODES, "header_bound")
            pending.extend((child, depth + 1) for child in item)
        elif kind is dict:
            _require(len(item) <= MAX_HEADER_NODES
                and all(type(key) is str and len(key) <= 128 for key in item), "header")
            pending.extend((child, depth + 1) for child in item.values())
        else:
            raise PlainStorageRPCError("header")


def _canonical(value):
    _json_tree(value)
    try:
        result = json.dumps(value, ensure_ascii=True, allow_nan=False,
            sort_keys=True, separators=(",", ":")).encode("ascii")
    except (ValueError, UnicodeError, RecursionError):
        raise PlainStorageRPCError("header") from None
    _require(0 < len(result) <= MAX_HEADER_BYTES, "header_bound")
    return result


def _header(value, fields):
    _require(type(value) is dict, "header_schema")
    _json_tree(value)
    _require(set(value) == fields, "header_schema")


def _parts(header, payload, header_fields):
    fields = _fields(header_fields)
    _header(header, fields)
    _require(type(payload) is bytes and len(payload) <= MAX_PAYLOAD_BYTES, "payload")
    envelope = _canonical({"schema": SCHEMA, "header": header,
        "payload_byte_count": len(payload), "payload_sha256": hashlib.sha256(payload).hexdigest()})
    return PREFIX.pack(MAGIC, len(envelope), len(payload)), envelope, payload


def encode_frame(header, payload, *, header_fields):
    """Pure encoder, principally useful for synthetic protocol tests."""
    return b"".join(_parts(header, payload, header_fields))


def _prefix(raw):
    _require(type(raw) is bytes and len(raw) == PREFIX.size, "prefix")
    magic, header_size, payload_size = PREFIX.unpack(raw)
    _require(magic == MAGIC, "prefix")
    _require(0 < header_size <= MAX_HEADER_BYTES and payload_size <= MAX_PAYLOAD_BYTES,
        "frame_bound")
    return header_size, payload_size


def _pairs(items):
    value = {}
    for key, child in items:
        _require(key not in value, "header")
        value[key] = child
    return value


def _number(_value):
    raise PlainStorageRPCError("header")


def _envelope(raw, payload_size, fields):
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_HEADER_BYTES, "header_bound")
    try:
        value = json.loads(raw.decode("ascii"), object_pairs_hook=_pairs,
            parse_float=_number, parse_constant=_number)
    except (ValueError, UnicodeError, RecursionError) as error:
        if type(error) is PlainStorageRPCError:
            raise
        raise PlainStorageRPCError("header") from None
    _require(type(value) is dict and set(value) == _FIELDS and value["schema"] == SCHEMA,
        "header_schema")
    _require(type(value["payload_byte_count"]) is int
        and value["payload_byte_count"] == payload_size, "header_schema")
    digest = value["payload_sha256"]
    _require(type(digest) is str and len(digest) == 64
        and all(char in "0123456789abcdef" for char in digest), "header_schema")
    _header(value["header"], fields)
    _require(_canonical(value) == raw, "header")
    return value


def _result(envelope, payload):
    _require(hashlib.sha256(payload).hexdigest() == envelope["payload_sha256"], "payload_hash")
    return envelope["header"], payload


def decode_frame(raw, *, header_fields):
    """Decode exactly one frame; any trailing byte is a refusal."""
    fields = _fields(header_fields)
    _require(type(raw) is bytes and PREFIX.size <= len(raw) <= MAX_FRAME_BYTES, "frame_bound")
    header_size, payload_size = _prefix(raw[:PREFIX.size])
    expected = PREFIX.size + header_size + payload_size
    _require(len(raw) <= expected, "trailing")
    _require(len(raw) == expected, "frame_bound")
    envelope = _envelope(raw[PREFIX.size:PREFIX.size + header_size], payload_size, fields)
    return _result(envelope, raw[PREFIX.size + header_size:])


def _remaining(deadline):
    _require(type(deadline) in (int, float), "deadline")
    try:
        _require(math.isfinite(deadline), "deadline")
    except OverflowError:
        raise PlainStorageRPCError("deadline") from None
    value = deadline - time.monotonic()
    _require(value > 0, "deadline")
    return value


def _pipe(fd):
    # No standard streams, regular files or sockets can carry these frames.
    _require(type(fd) is int and 3 <= fd < 2 ** 31, "descriptor")
    try:
        _require(stat.S_ISFIFO(os.fstat(fd).st_mode), "descriptor")
        os.set_blocking(fd, False)
    except OSError:
        raise PlainStorageRPCError("descriptor") from None


def _wait(fd, writing, deadline):
    while True:
        left = _remaining(deadline)
        try:
            readable, writable, _ = select.select([] if writing else [fd], [fd] if writing else [], [], left)
        except InterruptedError:
            continue
        except (OSError, ValueError):
            raise PlainStorageRPCError("io") from None
        _remaining(deadline)
        if (writable if writing else readable):
            return


def _read_exact(fd, length, deadline):
    chunks, remaining = [], length
    while remaining:
        _wait(fd, False, deadline)
        try:
            part = os.read(fd, min(remaining, 65536))
        except (BlockingIOError, InterruptedError):
            continue
        except OSError:
            raise PlainStorageRPCError("io") from None
        _require(bool(part), "eof")
        chunks.append(part)
        remaining -= len(part)
    _remaining(deadline)
    return b"".join(chunks)


def _write_all(fd, raw, deadline):
    view, offset = memoryview(raw), 0
    while offset < len(raw):
        _wait(fd, True, deadline)
        try:
            size = os.write(fd, view[offset:offset + 65536])
        except (BlockingIOError, InterruptedError):
            continue
        except OSError:
            raise PlainStorageRPCError("io") from None
        _require(size > 0, "io")
        offset += size
    _remaining(deadline)


def send_frame(fd, header, payload, deadline, *, header_fields):
    """Write one bounded frame to an inherited pipe, never stdout/stderr."""
    _remaining(deadline)
    parts = _parts(header, payload, header_fields)
    _remaining(deadline)
    _pipe(fd)
    for part in parts:
        _write_all(fd, part, deadline)


def receive_frame(fd, deadline, *, header_fields):
    """Read one frame; application protocol owns whether another may follow."""
    fields = _fields(header_fields)
    _remaining(deadline)
    _pipe(fd)
    header_size, payload_size = _prefix(_read_exact(fd, PREFIX.size, deadline))
    envelope = _envelope(_read_exact(fd, header_size, deadline), payload_size, fields)
    payload = _read_exact(fd, payload_size, deadline)
    result = _result(envelope, payload)
    _remaining(deadline)
    return result


def reject_pending(fd, deadline):
    """At a protocol turn boundary, reject extra data; clean EOF is permitted.

    This is an instantaneous check, not proof that a peer cannot write later.
    Only use it when the application protocol forbids another message now.
    """
    _remaining(deadline)
    _pipe(fd)
    try:
        readable, _, _ = select.select([fd], [], [], 0)
        if readable:
            try:
                _require(os.read(fd, 1) == b"", "pending")
            except BlockingIOError:
                pass
    except (OSError, ValueError) as error:
        if type(error) is PlainStorageRPCError:
            raise
        raise PlainStorageRPCError("io") from None
    _remaining(deadline)
