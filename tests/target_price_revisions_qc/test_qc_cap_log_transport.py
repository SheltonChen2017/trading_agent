"""Synthetic transport integrity only; no market, cloud or operator inputs."""
import base64
import copy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import random
import string
import zlib

import pytest
from research.target_price_revisions_qc import cap_log_transport as codec


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def envelope(*lines):
    return {"success": True, "logs": list(lines), "length": len(lines)}


def wire(raw, kind="SUMMARY", compressed=None, digest=None):
    return ("MATCHED_Z " + kind + " " + (digest or hashlib.sha256(raw).hexdigest())
            + " " + base64.b64encode(zlib.compress(raw) if compressed is None else compressed).decode("ascii"))


@pytest.mark.parametrize("kind", ["NAV", "COVERAGE", "SUMMARY"])
def test_round_trip_exact_values_unknown_fields_and_source_unchanged(kind):
    record = {"session": "2025-01-02", "nested": {"future": [None, False, 0, "0", 1.5, "é", "雪"]},
              "hash": "a" * 64, "fraction": "1/60", "extra": {"k": [1, 2]}}
    original = copy.deepcopy(record)
    encoded = codec.encode_record(kind, record)
    prefix = "2025-01-02 00:00:00 : "
    response = {**envelope("native notice", prefix + encoded), "opaque_extra": {"future": True}}
    bound = canonical(response)
    decoded = codec.decode_logs(response)
    assert record == original and canonical(response) == bound
    assert decoded is not response and decoded["logs"] is not response["logs"]
    assert decoded["opaque_extra"] == response["opaque_extra"]
    assert decoded["logs"] == ["native notice", prefix + "MATCHED_" + kind + " " + canonical(record).decode("ascii")]
    recovered = json.loads(decoded["logs"][1].split("MATCHED_" + kind + " ", 1)[1])
    assert recovered == original
    assert hashlib.sha256(canonical(response)).hexdigest() != hashlib.sha256(canonical(decoded)).hexdigest()


def test_full_synthetic_census_lossless_with_quota_headroom():
    records = []
    day = date(2025, 1, 2)
    for number in range(60):
        records.append(("NAV", {"session": (day + timedelta(days=number)).isoformat(),
                        "nav": "100000", "cash": "100000", "gross_exposure": "0"}))
    for number in range(14):
        records.append(("COVERAGE", {"session": (day + timedelta(days=number * 6)).isoformat(),
            "sleeves": {name: {"state_counts": {"known": 10, "missing": 2}, "input_hash": hashlib.sha256(name.encode()).hexdigest(),
                "selected_hash": "b" * 64, "unknown_extension": {"padding": "x" * 1000}}
                for name in ("SPY", "XLV", "XLE", "QQQ", "SOXX", "REMX")}}))
    records.append(("SUMMARY", {"decisions": 14, "valuation_days": 60, "canonical_admission": False}))
    lines = [codec.encode_record(kind, record) for kind, record in records]
    assert sum(map(len, lines)) < codec.MAX_RUN_WIRE_CHARS
    decoded = codec.decode_logs(envelope(*lines))
    assert len(decoded["logs"]) == 75
    assert [json.loads(line.split(" ", 1)[1]) for line in decoded["logs"]] == [record for _, record in records]
    assert all("MATCHED_Z" not in line for line in decoded["logs"])


@pytest.mark.parametrize("kind", [None, 1, True, [], {}, "nav", "UNKNOWN", "NAV SUMMARY"])
def test_encoder_refuses_unknown_kind(kind):
    with pytest.raises(codec.TransportError):
        codec.encode_record(kind, {"session": "2025-01-02"})


@pytest.mark.parametrize("record", [None, [], "x", 1, {1: "coerced"}, {"x": (1, 2)}, {"x": object()},
    {"x": float("nan")}, {"x": float("inf")}, {"x": float("-inf")}, {"x": {False: "coerced"}}])
def test_encoder_refuses_coercion_or_nonfinite(record):
    with pytest.raises(codec.TransportError):
        codec.encode_record("SUMMARY", record)


@pytest.mark.parametrize("session", [None, 1, "", "20250102", "2025-1-2", "2025-02-30", "2025-01-02T00:00:00"])
@pytest.mark.parametrize("kind", ["NAV", "COVERAGE"])
def test_encoder_and_decoder_require_canonical_session_identity(kind, session):
    record = {"session": session}
    with pytest.raises(codec.TransportError):
        codec.encode_record(kind, record)
    with pytest.raises(codec.TransportError):
        codec.decode_logs(envelope(wire(canonical(record), kind)))


def test_record_boundary_and_wire_boundary_are_inclusive(monkeypatch):
    record = {"padding": ""}
    record["padding"] = "x" * (codec.MAX_RECORD_BYTES - len(canonical(record)))
    assert len(canonical(record)) == 16384
    encoded = codec.encode_record("SUMMARY", record)
    assert json.loads(codec.decode_logs(envelope(encoded))["logs"][0].split(" ", 1)[1]) == record
    record["padding"] += "x"
    with pytest.raises(codec.TransportError):
        codec.encode_record("SUMMARY", record)
    with pytest.raises(codec.TransportError):
        codec.decode_logs(envelope(wire(canonical(record))))
    simple = {"x": 1}
    encoded = codec.encode_record("SUMMARY", simple)
    monkeypatch.setattr(codec, "MAX_WIRE_CHARS", len(encoded))
    assert codec.encode_record("SUMMARY", simple) == encoded
    assert codec.decode_logs(envelope(encoded))["length"] == 1
    monkeypatch.setattr(codec, "MAX_WIRE_CHARS", len(encoded) - 1)
    with pytest.raises(codec.TransportError):
        codec.encode_record("SUMMARY", simple)
    with pytest.raises(codec.TransportError):
        codec.decode_logs(envelope(encoded))


def test_valid_size_but_incompressible_record_refuses_wire_overflow():
    randomizer = random.Random(20261009)
    record = {"padding": "".join(randomizer.choices(string.ascii_letters + string.digits, k=10000))}
    assert len(canonical(record)) < codec.MAX_RECORD_BYTES
    assert len(wire(canonical(record))) > codec.MAX_WIRE_CHARS
    with pytest.raises(codec.TransportError):
        codec.encode_record("SUMMARY", record)


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":{"b":1,"b":2}}', b'{"x":NaN}', b'{"x":Infinity}',
    b'{"x":-Infinity}', b'{"x":1e999}', b'[]', b'null', b'"x"', b'1', b'{"x":}', b'{ "x":1}',
    b'{"z":1,"a":2}', b'{"x":-0}', b'{"x":"\xc3\xa9"}', b'\xff'])
def test_decoder_refuses_ambiguous_noncanonical_invalid_or_nonfinite_json(raw):
    with pytest.raises(codec.TransportError):
        codec.decode_logs(envelope(wire(raw)))


@pytest.mark.parametrize("mode", ["bad_hash", "uppercase_hash", "short_hash", "invalid_base64", "noncanonical_base64",
    "truncated_base64", "truncated_zlib", "trailing_zlib", "concatenated_zlib", "invalid_zlib", "bomb", "non_ascii"])
def test_decoder_refuses_corrupt_transport(mode):
    raw = canonical({"x": 1})
    encoded = wire(raw)
    if mode == "bad_hash": encoded = wire(raw, digest="f" * 64)
    elif mode == "uppercase_hash": encoded = encoded.replace(hashlib.sha256(raw).hexdigest(), "F" * 64)
    elif mode == "short_hash": encoded = encoded.replace(hashlib.sha256(raw).hexdigest(), "f" * 63)
    elif mode == "invalid_base64": encoded = encoded[:-1] + "!"
    elif mode == "noncanonical_base64":
        for size in range(30):
            encoded = wire(canonical({"x": "x" * size}))
            if encoded.endswith("="):
                break
        head, token = encoded.rsplit(" ", 1)
        padding = len(token) - len(token.rstrip("="))
        position = len(token) - padding - 1
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
        replacement = alphabet[alphabet.index(token[position]) | 1]
        altered = token[:position] + replacement + token[position + 1:]
        assert altered != token and base64.b64decode(altered, validate=True) == base64.b64decode(token, validate=True)
        encoded = head + " " + altered
    elif mode == "truncated_base64": encoded = encoded[:-1]
    elif mode == "truncated_zlib": encoded = wire(raw, compressed=zlib.compress(raw)[:-1])
    elif mode == "trailing_zlib": encoded = wire(raw, compressed=zlib.compress(raw) + b"x")
    elif mode == "concatenated_zlib": encoded = wire(raw, compressed=zlib.compress(raw) * 2)
    elif mode == "invalid_zlib": encoded = wire(raw, compressed=b"not zlib")
    elif mode == "bomb": encoded = wire(b"x" * 1000000)
    else: encoded = encoded[:-1] + "é"
    with pytest.raises(codec.TransportError):
        codec.decode_logs(envelope(encoded))


@pytest.mark.parametrize("mode", ["duplicate_nav", "conflicting_nav", "duplicate_coverage", "duplicate_summary",
    "mixed", "plain_only", "multiple_z", "marker_in_prefix", "unknown_kind", "unknown_marker", "trailing_text", "two_spaces"])
def test_decoder_refuses_duplicate_conflicting_mixed_or_ambiguous_markers(mode):
    nav = codec.encode_record("NAV", {"session": "2025-01-02", "x": 1})
    lines = [nav]
    if mode == "duplicate_nav": lines.append(nav)
    elif mode == "conflicting_nav": lines.append(codec.encode_record("NAV", {"session": "2025-01-02", "x": 2}))
    elif mode == "duplicate_coverage": lines = [codec.encode_record("COVERAGE", {"session": "2025-01-02"})] * 2
    elif mode == "duplicate_summary": lines = [codec.encode_record("SUMMARY", {"x": 1})] * 2
    elif mode == "mixed": lines.append('MATCHED_NAV {"session":"2025-01-03"}')
    elif mode == "plain_only": lines = ['MATCHED_SUMMARY {}']
    elif mode == "multiple_z": lines = [nav + " " + nav]
    elif mode == "marker_in_prefix": lines = ["MATCHED_NAV " + nav]
    elif mode == "unknown_kind": lines = [nav.replace("MATCHED_Z NAV", "MATCHED_Z UNKNOWN")]
    elif mode == "unknown_marker": lines = ["MATCHED_UNKNOWN {}"]
    elif mode == "trailing_text": lines = [nav + " trailing"]
    else: lines = [nav.replace("MATCHED_Z NAV", "MATCHED_Z  NAV")]
    with pytest.raises(codec.TransportError):
        codec.decode_logs(envelope(*lines))


@pytest.mark.parametrize("response", [None, [], {"success": False, "logs": [], "length": 0},
    {"success": 1, "logs": [], "length": 0}, {"success": True, "logs": (), "length": 0},
    {"success": True, "logs": [], "length": False}, {"success": True, "logs": ["notice"], "length": 0},
    {"success": True, "logs": [None], "length": 1}, {"success": True, "logs": ["a\nb"], "length": 1},
    {"success": True, "logs": ["a\rb"], "length": 1}])
def test_decoder_refuses_unavailable_incomplete_or_not_line_inventory(response):
    with pytest.raises(codec.TransportError):
        codec.decode_logs(response)


def test_inventory_and_timestamp_prefix_limits_exact():
    assert codec.decode_logs(envelope(*(["notice"] * 1000)))["length"] == 1000
    with pytest.raises(codec.TransportError):
        codec.decode_logs(envelope(*(["notice"] * 1001)))
    encoded = codec.encode_record("SUMMARY", {"x": 1})
    assert codec.decode_logs(envelope(" " * 256 + encoded))["length"] == 1
    with pytest.raises(codec.TransportError):
        codec.decode_logs(envelope(" " * 257 + encoded))
    with pytest.raises(codec.TransportError):
        codec.decode_logs(envelope("x" * (8192 + 257)))


def test_missing_census_stays_missing_and_errors_never_echo_payload():
    response = envelope("native notice")
    assert codec.decode_logs(response) == response
    with pytest.raises(codec.TransportError) as error:
        codec.decode_logs(envelope(wire(b'{"sensitive":"synthetic-secret"}', digest="f" * 64)))
    assert str(error.value) == "invalid bounded aggregate transport"
    assert "synthetic-secret" not in str(error.value)


def test_inflate_enforces_output_limit_before_allocating_full_payload(monkeypatch):
    original = codec.zlib.decompressobj
    limits = []
    class Limited:
        def __init__(self):
            self.delegate = original()
        def decompress(self, data, max_length=0):
            limits.append(max_length)
            return self.delegate.decompress(data, max_length)
        def __getattr__(self, name):
            return getattr(self.delegate, name)
    monkeypatch.setattr(codec.zlib, "decompressobj", Limited)
    codec.decode_logs(envelope(codec.encode_record("SUMMARY", {"x": 1})))
    assert limits == [16385]


def test_source_is_pure_and_has_no_external_or_execution_imports():
    import ast
    path = Path(codec.__file__)
    tree = ast.parse(path.read_text())
    imports = {node.module if isinstance(node, ast.ImportFrom) else alias.name
               for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
               for alias in node.names}
    assert imports == {"base64", "datetime", "hashlib", "json", "math", "re", "zlib"}
    calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert not calls & {"open", "eval", "exec", "compile", "__import__"}
