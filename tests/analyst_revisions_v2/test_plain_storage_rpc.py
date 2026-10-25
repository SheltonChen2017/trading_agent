"""Synthetic binary pipes only; no provider, private corpus or credentials."""
import ast
import hashlib
import json
import os
from pathlib import Path
import threading
import time

import pytest

from scripts import arv2_plain_storage_rpc as m


FIELDS = frozenset(("kind", "ordinal", "facts"))
HEADER = {"kind": "synthetic_request", "ordinal": 0,
    "facts": {"enabled": False, "count": 2, "items": [None, "public-synthetic"]}}


def encode(header=HEADER, payload=b"synthetic\x00payload"):
    return m.encode_frame(header, payload, header_fields=FIELDS)


def decode(raw):
    return m.decode_frame(raw, header_fields=FIELDS)


def envelope(raw):
    _magic, header_size, _payload_size = m.PREFIX.unpack(raw[:m.PREFIX.size])
    return json.loads(raw[m.PREFIX.size:m.PREFIX.size + header_size]), raw[m.PREFIX.size + header_size:]


def raw_frame(value, payload=b"", *, header_raw=None, magic=m.MAGIC,
              declared_header=None, declared_payload=None):
    raw = header_raw if header_raw is not None else json.dumps(value,
        ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
    return m.PREFIX.pack(magic, len(raw) if declared_header is None else declared_header,
        len(payload) if declared_payload is None else declared_payload) + raw + payload


@pytest.fixture
def pipe():
    read_fd, write_fd = os.pipe()
    yield read_fd, write_fd
    for fd in (read_fd, write_fd):
        try:
            os.close(fd)
        except OSError:
            pass


@pytest.mark.parametrize("payload", [b"", b"x", b"\x00\xff\r\n", b"a" * 65536])
def test_pure_roundtrip_is_opaque_and_canonical(payload):
    raw = encode(payload=payload)
    header, returned = decode(raw)
    assert header == HEADER and returned == payload
    value, body = envelope(raw)
    assert set(value) == {"schema", "header", "payload_byte_count", "payload_sha256"}
    assert value["schema"] == m.SCHEMA
    assert value["payload_byte_count"] == len(payload)
    assert value["payload_sha256"] == hashlib.sha256(body).hexdigest()
    assert header is not HEADER and header["facts"] is not HEADER["facts"]


def test_empty_field_inventory_is_explicit():
    raw = m.encode_frame({}, b"", header_fields=set())
    assert m.decode_frame(raw, header_fields=frozenset()) == ({}, b"")


@pytest.mark.parametrize("fields", [None, [], (), "kind", {1}, {""}, {"x" * 129}])
def test_exact_field_inventory_required(fields):
    with pytest.raises(m.PlainStorageRPCError, match="^header_schema$"):
        m.encode_frame(HEADER, b"", header_fields=fields)


@pytest.mark.parametrize("header", [{}, {**HEADER, "unknown": 0},
    {key: value for key, value in HEADER.items() if key != "ordinal"}, [], None])
def test_unknown_missing_and_nonmapping_header_refused(header):
    with pytest.raises(m.PlainStorageRPCError, match="^header_schema$"):
        encode(header=header)


@pytest.mark.parametrize("item", [1.0, float("nan"), float("inf"), (1,), {1}, object(), 2 ** 63,
    -(2 ** 63) - 1, {1: "invalid-key"}])
def test_only_exact_bounded_json_header_values(item):
    with pytest.raises(m.PlainStorageRPCError, match="^header$"):
        encode(header={**HEADER, "facts": item})


@pytest.mark.parametrize("item", [-(2 ** 63), 2 ** 63 - 1, True, False, None, "unicode-\u2603"])
def test_finite_header_primitive_boundaries(item):
    header = {**HEADER, "facts": item}
    assert decode(encode(header=header))[0] == header


def test_subclasses_never_invoke_custom_behavior():
    class HostileDict(dict):
        def items(self):
            raise AssertionError("must not inspect hostile items")
    class HostileInt(int):
        def __int__(self):
            raise AssertionError("must not coerce")
    class HostileBytes(bytes):
        def __bytes__(self):
            raise AssertionError("must not coerce")
    for header, payload in [(HostileDict(HEADER), b""),
            ({**HEADER, "ordinal": HostileInt(0)}, b""), (HEADER, HostileBytes(b""))]:
        with pytest.raises(m.PlainStorageRPCError):
            encode(header, payload)


@pytest.mark.parametrize("case", ["depth", "nodes", "bytes", "cycle"])
def test_header_resource_bounds(case):
    if case == "depth":
        value = 0
        for _ in range(m.MAX_HEADER_DEPTH + 1):
            value = [value]
    elif case == "nodes":
        value = [0] * m.MAX_HEADER_NODES
    elif case == "bytes":
        value = "x" * m.MAX_HEADER_BYTES
    else:
        value = []
        value.append(value)
    with pytest.raises(m.PlainStorageRPCError, match="^header_bound$"):
        encode(header={**HEADER, "facts": value})


def test_exact_header_byte_boundary():
    empty = {**HEADER, "facts": ""}
    overhead = len(encode(header=empty, payload=b"")) - m.PREFIX.size
    header = {**empty, "facts": "x" * (m.MAX_HEADER_BYTES - overhead)}
    raw = encode(header=header, payload=b"")
    assert len(raw) == m.PREFIX.size + m.MAX_HEADER_BYTES
    assert decode(raw) == (header, b"")
    with pytest.raises(m.PlainStorageRPCError, match="^header_bound$"):
        encode(header={**header, "facts": header["facts"] + "x"}, payload=b"")


def test_payload_bound_and_exact_type():
    for value in (bytearray(b"x"), memoryview(b"x"), "x", None, b"x" * (m.MAX_PAYLOAD_BYTES + 1)):
        with pytest.raises(m.PlainStorageRPCError, match="^payload$"):
            encode(payload=value)


def test_maximum_payload_roundtrips_without_text_conversion():
    payload = b"\x00\xfe" * (m.MAX_PAYLOAD_BYTES // 2)
    assert decode(encode(payload=payload))[1] == payload


@pytest.mark.parametrize("name,value", [("extra", 0), ("schema", "other"),
    ("payload_byte_count", True), ("payload_byte_count", 999), ("payload_sha256", "0" * 63),
    ("payload_sha256", "A" * 64), ("payload_sha256", 1), ("header", {**HEADER, "extra": 0})])
def test_envelope_exact_schema(name, value):
    item, payload = envelope(encode())
    item[name] = value
    with pytest.raises(m.PlainStorageRPCError, match="^header_schema$"):
        decode(raw_frame(item, payload))


def test_envelope_missing_field():
    item, payload = envelope(encode())
    del item["payload_sha256"]
    with pytest.raises(m.PlainStorageRPCError, match="^header_schema$"):
        decode(raw_frame(item, payload))


@pytest.mark.parametrize("variant", ["duplicate", "space", "newline", "float", "nan", "nonascii", "broken"])
def test_exact_canonical_header_bytes(variant):
    item, payload = envelope(encode())
    raw = json.dumps(item, sort_keys=True, separators=(",", ":")).encode("ascii")
    if variant == "duplicate":
        raw = raw.replace(b'"ordinal":0', b'"ordinal":0,"ordinal":0')
    elif variant == "space":
        raw = raw.replace(b'"ordinal":0', b'"ordinal": 0')
    elif variant == "newline":
        raw += b"\n"
    elif variant == "float":
        raw = raw.replace(b'"ordinal":0', b'"ordinal":0.0')
    elif variant == "nan":
        raw = raw.replace(b'"ordinal":0', b'"ordinal":NaN')
    elif variant == "nonascii":
        raw += b"\xff"
    else:
        raw = b"{"
    with pytest.raises(m.PlainStorageRPCError, match="^header$"):
        decode(raw_frame(item, payload, header_raw=raw))


def test_payload_hash_is_not_merely_length_checked():
    raw = encode()
    with pytest.raises(m.PlainStorageRPCError, match="^payload_hash$"):
        decode(raw[:-1] + bytes((raw[-1] ^ 1,)))


@pytest.mark.parametrize("suffix", [b"x", b"\n", encode()])
def test_trailing_bytes_and_duplicate_frames_refused_by_pure_decoder(suffix):
    with pytest.raises(m.PlainStorageRPCError, match="^trailing$"):
        decode(encode() + suffix)


@pytest.mark.parametrize("cut", [0, 1, m.PREFIX.size - 1, m.PREFIX.size, m.PREFIX.size + 1, -1])
def test_truncation_refused(cut):
    with pytest.raises(m.PlainStorageRPCError, match="^frame_bound$"):
        decode(encode()[:cut])


@pytest.mark.parametrize("header_size,payload_size", [(0, 0), (m.MAX_HEADER_BYTES + 1, 0),
    (1, m.MAX_PAYLOAD_BYTES + 1), (2 ** 32 - 1, 2 ** 64 - 1)])
def test_declared_lengths_refused_before_body_read(pipe, header_size, payload_size):
    read_fd, write_fd = pipe
    os.write(write_fd, m.PREFIX.pack(m.MAGIC, header_size, payload_size))
    with pytest.raises(m.PlainStorageRPCError, match="^frame_bound$"):
        m.receive_frame(read_fd, time.monotonic() + 1, header_fields=FIELDS)


def test_wrong_magic_refused():
    raw = encode()
    with pytest.raises(m.PlainStorageRPCError, match="^prefix$"):
        decode(b"BADMAGIC" + raw[8:])


@pytest.mark.parametrize("deadline", [None, True, False, "later", float("nan"), float("inf"),
    -float("inf"), 0, 2 ** 10000])
def test_bad_deadline_refuses_without_fd_mutation(monkeypatch, deadline):
    monkeypatch.setattr(m, "_pipe", lambda _fd: pytest.fail("deadline checked first"))
    with pytest.raises(m.PlainStorageRPCError, match="^deadline$"):
        m.send_frame(123, HEADER, b"", deadline, header_fields=FIELDS)
    with pytest.raises(m.PlainStorageRPCError, match="^deadline$"):
        m.receive_frame(123, deadline, header_fields=FIELDS)


@pytest.mark.parametrize("fd", [0, 1, 2, -1, True, None, "3", 2 ** 100])
def test_only_inherited_nonstandard_pipe_descriptors(fd):
    with pytest.raises(m.PlainStorageRPCError, match="^descriptor$"):
        m.receive_frame(fd, time.monotonic() + 1, header_fields=FIELDS)


def test_regular_file_and_closed_pipe_refused(tmp_path):
    path = tmp_path / "synthetic"
    with path.open("w+b") as stream:
        with pytest.raises(m.PlainStorageRPCError, match="^descriptor$"):
            m.receive_frame(stream.fileno(), time.monotonic() + 1, header_fields=FIELDS)
    read_fd, write_fd = os.pipe()
    os.close(read_fd)
    os.close(write_fd)
    with pytest.raises(m.PlainStorageRPCError, match="^descriptor$"):
        m.receive_frame(read_fd, time.monotonic() + 1, header_fields=FIELDS)


def test_real_pipe_roundtrip_with_fragmented_reads(pipe):
    read_fd, write_fd = pipe
    payload, errors = b"\x00\xff" * 40000, []
    def writer():
        try:
            m.send_frame(write_fd, HEADER, payload, time.monotonic() + 2, header_fields=FIELDS)
        except BaseException as error:
            errors.append(error)
    thread = threading.Thread(target=writer)
    thread.start()
    result = m.receive_frame(read_fd, time.monotonic() + 2, header_fields=FIELDS)
    thread.join(2)
    assert not thread.is_alive() and errors == []
    assert result == (HEADER, payload)
    assert os.get_blocking(read_fd) is False and os.get_blocking(write_fd) is False


def test_two_sequential_messages_are_not_mistaken_for_trailing_bytes(pipe):
    read_fd, write_fd = pipe
    os.write(write_fd, encode(payload=b"one") + encode(payload=b"two"))
    assert m.receive_frame(read_fd, time.monotonic() + 1, header_fields=FIELDS)[1] == b"one"
    assert m.receive_frame(read_fd, time.monotonic() + 1, header_fields=FIELDS)[1] == b"two"


@pytest.mark.parametrize("cut", [0, 1, m.PREFIX.size, -1])
def test_real_pipe_partial_eof_refuses(pipe, cut):
    read_fd, write_fd = pipe
    os.write(write_fd, encode()[:cut])
    os.close(write_fd)
    with pytest.raises(m.PlainStorageRPCError, match="^eof$"):
        m.receive_frame(read_fd, time.monotonic() + 1, header_fields=FIELDS)


def test_read_deadline_is_effective_on_initially_blocking_pipe(pipe):
    before = time.monotonic()
    with pytest.raises(m.PlainStorageRPCError, match="^deadline$"):
        m.receive_frame(pipe[0], before + 0.03, header_fields=FIELDS)
    assert time.monotonic() - before < 1


def test_write_deadline_is_effective_when_pipe_fills(pipe):
    before = time.monotonic()
    with pytest.raises(m.PlainStorageRPCError, match="^deadline$"):
        m.send_frame(pipe[1], HEADER, b"x" * (1024 * 1024), before + 0.03, header_fields=FIELDS)
    assert time.monotonic() - before < 1


def test_broken_pipe_is_finite_failure(pipe):
    read_fd, write_fd = pipe
    os.close(read_fd)
    with pytest.raises(m.PlainStorageRPCError, match="^io$"):
        m.send_frame(write_fd, HEADER, b"x", time.monotonic() + 1, header_fields=FIELDS)


def test_interrupted_select_retries_with_same_deadline(pipe, monkeypatch):
    original, calls = m.select.select, []
    def interrupt_once(*args):
        calls.append(True)
        if len(calls) == 1:
            raise InterruptedError()
        return original(*args)
    monkeypatch.setattr(m.select, "select", interrupt_once)
    os.write(pipe[1], encode(payload=b"ok"))
    assert m.receive_frame(pipe[0], time.monotonic() + 1, header_fields=FIELDS)[1] == b"ok"
    assert len(calls) > 1


def test_nonblocking_read_race_retries(pipe, monkeypatch):
    original, calls = m.os.read, []
    def raced_once(*args):
        calls.append(True)
        if len(calls) == 1:
            raise BlockingIOError()
        return original(*args)
    monkeypatch.setattr(m.os, "read", raced_once)
    os.write(pipe[1], encode(payload=b"ok"))
    assert m.receive_frame(pipe[0], time.monotonic() + 1, header_fields=FIELDS)[1] == b"ok"


def test_nonblocking_write_race_retries(pipe, monkeypatch):
    original, calls = m.os.write, []
    def raced_once(*args):
        calls.append(True)
        if len(calls) == 1:
            raise BlockingIOError()
        return original(*args)
    monkeypatch.setattr(m.os, "write", raced_once)
    m.send_frame(pipe[1], HEADER, b"ok", time.monotonic() + 1, header_fields=FIELDS)
    assert m.receive_frame(pipe[0], time.monotonic() + 1, header_fields=FIELDS)[1] == b"ok"


@pytest.mark.parametrize("state", ["empty", "eof", "extra"])
def test_pending_check_accepts_clean_eof_but_refuses_extra_data(pipe, state):
    read_fd, write_fd = pipe
    if state == "eof":
        os.close(write_fd)
    elif state == "extra":
        os.write(write_fd, b"x")
    if state == "extra":
        with pytest.raises(m.PlainStorageRPCError, match="^pending$"):
            m.reject_pending(read_fd, time.monotonic() + 1)
    else:
        assert m.reject_pending(read_fd, time.monotonic() + 1) is None


def test_failure_classifier_never_stringifies_hostile_exception():
    class Hostile(ValueError):
        def __str__(self):
            raise AssertionError("must not stringify")
    assert m.finite_failure(Hostile("secret")) == "unknown_exception"
    assert m.finite_failure(m.PlainStorageRPCError("payload_hash")) == "payload_hash"
    assert m.finite_failure(m.PlainStorageRPCError("untrusted-value")) == "unknown_exception"


def test_no_output_or_operational_imports(capsys):
    assert decode(encode()) == (HEADER, b"synthetic\x00payload")
    assert capsys.readouterr() == ("", "")
    tree = ast.parse(Path(m.__file__).read_text())
    imports = {node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import)}
    assert imports == {"hashlib", "json", "math", "os", "select", "stat", "struct", "time"}
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id in {"print", "eval", "exec", "__import__", "open"} for node in ast.walk(tree))
