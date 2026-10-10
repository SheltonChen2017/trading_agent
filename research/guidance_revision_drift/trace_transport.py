"""Lossless invented-trace log transport, not authenticated runtime evidence.

Use routine ``log`` messages, not a burst of rate-limited ``debug`` calls.
Each distinct ASCII message is <=200 characters. Current QC organization
quotas still need external preflight: bounded output is not a quota grant.
Only redundant record sequence/prior hashes are omitted on the wire; the
validated original canonical chain is reconstructed and checked exactly.
No SDK, filesystem, network, completion replay or external authority here.
"""
from __future__ import annotations

import base64
import json
import re
import zlib

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.guidance_revision_drift.contracts import (
    CANDIDATE_SHA256, CandidateError, _decode, _reject_number, _unique_object,
)


FIXTURE_SHA256 = "8f35d56a335d3f7d9dad016e1e2236de7fcd2635e5c463c30081f97b7b944458"
MAX_TRACE_RECORDS, MAX_TRACE_RECORD_BYTES = 1024, 4096
MAX_RAW_BYTES, MAX_METADATA_BYTES = 4_500_000, 65_536
MAX_LOG_BYTES, MAX_FRAGMENTS, MAX_LINE_BYTES = 100_000, 1024, 200
PAYLOAD_CHARS = 112
_START = hash_bytes(b"gdr.synthetic.trace-log.v1")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_LINE = re.compile(rb"GDRT1\|([0-9]{5})\|([0-9]{5})\|([0-9a-f]{64})\|([A-Za-z0-9+/=]+)\Z")
_END = re.compile(rb"GDRT1\|END\|([0-9]{5})\|([0-9a-f]{64})\|([0-9a-f]{64})\Z")
_TRACE_KEYS = {"schema", "genesis", "genesis_sha256", "records", "count",
               "head_sha256", "native_runtime_verified", "cloud_completed"}
_CONTEXT_KEYS = {"runtime_source_sha256", "bundle_sha256", "candidate_sha256", "fixture_sha256"}
_AUTHORITY = {"external_provenance_verified", "native_runtime_verified", "cloud_completed",
    "execution_authorized", "qc_upload_allowed", "qc_launch_allowed", "economic_acceptance",
    "market_evidence", "empirical_backtest_ready", "settlement_parity_verified"}


class TraceTransportError(ValueError):
    """Incomplete, unbound, corrupt or oversized invented output."""


def _digest(value):
    if type(value) is not str or not _HASH.fullmatch(value):
        raise TraceTransportError("exact lowercase retained SHA-256 required")
    return value


def _raw(value, limit):
    remaining, text = [100_000], [limit]
    def check(item, depth=0):
        remaining[0] -= 1
        if depth > 16 or remaining[0] < 0:
            raise TraceTransportError("transport projection exceeds structural bound")
        if type(item) is str:
            if len(item) > limit:
                raise TraceTransportError("transport text exceeds bound")
            text[0] -= len(item.encode("utf-8"))
            if text[0] < 0:
                raise TraceTransportError("aggregate transport text exceeds bound")
        elif type(item) is int:
            if item.bit_length() > 128:
                raise TraceTransportError("transport integer exceeds bound")
        elif item is None or type(item) is bool:
            pass
        elif type(item) in (dict, list):
            if len(item) > 4096:
                raise TraceTransportError("transport container exceeds bound")
            if type(item) is dict:
                for key, child in item.items():
                    if type(key) is not str:
                        raise TraceTransportError("strict JSON text keys required")
                    if key in _AUTHORITY and child is not False:
                        raise TraceTransportError("transport cannot assert external authority")
                    check(key, depth + 1)
                    check(child, depth + 1)
            else:
                for child in item:
                    check(child, depth + 1)
        else:
            raise TraceTransportError("strict JSON transport values required")
    try:
        check(value)
        raw = canonical_json(value).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise TraceTransportError("bounded strict transport JSON required") from exc
    if len(raw) > limit:
        raise TraceTransportError("transport encoded bytes exceed bound")
    return raw


def _object(raw, limit):
    if type(raw) is not bytes or not 0 < len(raw) <= limit:
        raise TraceTransportError("bounded immutable transport bytes required")
    try:
        body = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                          parse_float=_reject_number, parse_constant=_reject_number)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise TraceTransportError("strict transport JSON required") from exc
    if type(body) is not dict or _raw(body, limit) != raw:
        raise TraceTransportError("canonical object transport bytes required")
    return body


def _context(value):
    if type(value) is not dict or set(value) != _CONTEXT_KEYS:
        raise TraceTransportError("exact fixed runtime context required")
    result = {key: _digest(item) for key, item in value.items()}
    if result["candidate_sha256"] != CANDIDATE_SHA256 or result["fixture_sha256"] != FIXTURE_SHA256:
        raise TraceTransportError("runtime context differs from fixed synthetic candidate/fixture")
    return result


def _trace(value):
    if type(value) is not dict or set(value) != _TRACE_KEYS:
        raise TraceTransportError("complete protocol projection required")
    if (value["schema"] != "gdr.lean.protocol-trace.v1" or type(value["count"]) is not int
            or type(value["records"]) is not list or not 0 <= value["count"] <= MAX_TRACE_RECORDS
            or value["count"] != len(value["records"]) or value["native_runtime_verified"] is not False
            or value["cloud_completed"] is not False):
        raise TraceTransportError("bounded nonpromoting protocol projection required")
    body = _object(_raw(value, MAX_RAW_BYTES), MAX_RAW_BYTES)
    genesis = body["genesis"]
    if (type(genesis) is not dict or set(genesis) != {"schema", "mode", "fixture_sha256", "native_runtime_verified"}
            or genesis["schema"] != "gdr.lean.protocol-genesis.v1" or genesis["mode"] not in ("base", "stress")
            or genesis["fixture_sha256"] != FIXTURE_SHA256 or genesis["native_runtime_verified"] is not False):
        raise TraceTransportError("fixed synthetic genesis required")
    prior = hash_bytes(_raw(genesis, MAX_TRACE_RECORD_BYTES))
    if body["genesis_sha256"] != prior:
        raise TraceTransportError("protocol genesis anchor differs")
    for sequence, row in enumerate(body["records"]):
        raw = _raw(row, MAX_TRACE_RECORD_BYTES)
        try:
            checked = _decode(raw)
        except CandidateError as exc:
            raise TraceTransportError("strict bounded protocol record required") from exc
        if (set(checked) != {"sequence", "previous_sha256", "kind", "payload"}
                or type(checked["sequence"]) is not int or checked["sequence"] != sequence
                or checked["previous_sha256"] != prior or type(checked["kind"]) is not str
                or checked["kind"] not in {"frame", "account_checkpoint", "binding", "fill_issue", "acknowledgement"}
                or type(checked["payload"]) is not dict):
            raise TraceTransportError("protocol record chain differs")
        prior = hash_bytes(raw)
    if _digest(body["head_sha256"]) != prior:
        raise TraceTransportError("protocol head differs")
    return body


def _fragments(value):
    if (type(value) is not tuple or not 2 <= len(value) <= MAX_FRAGMENTS + 1
            or any(type(raw) is not bytes or not 0 < len(raw) <= MAX_LINE_BYTES for raw in value)
            or sum(len(raw) + 1 for raw in value) > MAX_LOG_BYTES):
        raise TraceTransportError("bounded complete immutable log fragments required")
    return value


def trace_fragment_anchor(fragments):
    """Retain outside returned output; a self-reported anchor is not provenance."""
    return hash_payload([hash_bytes(raw) for raw in _fragments(fragments)])


def export_trace_fragments(trace, *, runtime_context, metadata=None):
    """Prepare bounded lossless messages; never sends/logs them itself."""
    body = _trace(trace)
    context = _context(runtime_context)
    extra = _object(_raw({"status": "complete"} if metadata is None else metadata,
                         MAX_METADATA_BYTES), MAX_METADATA_BYTES)
    if extra.get("status") not in ("complete", "failed"):
        raise TraceTransportError("explicit complete/failed transport status required")
    if extra["status"] == "complete" and body["count"] != 752:
        raise TraceTransportError("complete fixed synthetic trace requires all accepted records")
    if extra["status"] == "complete" and body["genesis"]["mode"] != "base":
        raise TraceTransportError("complete transport requires the fixed base candidate")
    wire = dict(body, records=[{key: row[key] for key in ("kind", "payload")} for row in body["records"]])
    envelope = {"schema": "gdr.synthetic.trace-transport.v1", "trace": wire,
        "trace_sha256": hash_payload(body), "runtime_context": context, "metadata": extra,
        "external_provenance_verified": False, "native_runtime_verified": False}
    encoded = base64.b64encode(zlib.compress(_raw(envelope, MAX_RAW_BYTES), 9)).decode("ascii")
    count = (len(encoded) + PAYLOAD_CHARS - 1) // PAYLOAD_CHARS
    if not 1 <= count <= MAX_FRAGMENTS:
        raise TraceTransportError("transport fragment count exceeds bound")
    prior, result = _START, []
    for sequence in range(count):
        part = encoded[sequence * PAYLOAD_CHARS:(sequence + 1) * PAYLOAD_CHARS]
        line = f"GDRT1|{sequence:05d}|{count:05d}|{prior}|{part}".encode("ascii")
        result.append(line)
        prior = hash_bytes(line)
    anchor = hash_payload([hash_bytes(raw) for raw in result])
    result.append(f"GDRT1|END|{count:05d}|{prior}|{anchor}".encode("ascii"))
    return _fragments(tuple(result))


def reconstruct_trace_fragments(fragments, *, expected_sha256, expected_runtime_context):
    """Reconstruct supplied bytes only; not semantic/native completion.

    Final acceptance still requires TraceEvidence and the existing complete
    replay, including all 372 account checkpoints, plus external provenance.
    """
    fragments = _fragments(fragments)
    if trace_fragment_anchor(fragments) != _digest(expected_sha256):
        raise TraceTransportError("raw fragments differ from retained anchor")
    count, prior, encoded = len(fragments) - 1, _START, []
    for sequence, raw in enumerate(fragments[:-1]):
        match = _LINE.fullmatch(raw)
        if (match is None or int(match[1]) != sequence or int(match[2]) != count
                or match[3].decode("ascii") != prior or not 0 < len(match[4]) <= PAYLOAD_CHARS
                or (sequence < count - 1 and len(match[4]) != PAYLOAD_CHARS)):
            raise TraceTransportError("missing, duplicate, reordered or corrupt log fragment")
        encoded.append(match[4])
        prior = hash_bytes(raw)
    end = _END.fullmatch(fragments[-1])
    if (end is None or int(end[1]) != count or end[2].decode("ascii") != prior
            or end[3].decode("ascii") != hash_payload([hash_bytes(raw) for raw in fragments[:-1]])):
        raise TraceTransportError("complete terminal fragment differs")
    encoded = b"".join(encoded)
    try:
        packed = base64.b64decode(encoded, validate=True)
        if base64.b64encode(packed) != encoded:
            raise TraceTransportError("noncanonical base64 transport")
        decoder = zlib.decompressobj()
        raw = decoder.decompress(packed, MAX_RAW_BYTES + 1)
        if (len(raw) > MAX_RAW_BYTES or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail):
            raise TraceTransportError("oversized, trailing or truncated compressed transport")
    except (ValueError, zlib.error) as exc:
        raise TraceTransportError("invalid compressed transport") from exc
    envelope = _object(raw, MAX_RAW_BYTES)
    if (set(envelope) != {"schema", "trace", "trace_sha256", "runtime_context", "metadata",
                         "external_provenance_verified", "native_runtime_verified"}
            or envelope["schema"] != "gdr.synthetic.trace-transport.v1"
            or envelope["external_provenance_verified"] is not False or envelope["native_runtime_verified"] is not False):
        raise TraceTransportError("exact nonpromoting transport envelope required")
    context = _context(envelope["runtime_context"])
    if context != _context(expected_runtime_context):
        raise TraceTransportError("transport runtime context differs from retained candidate")
    wire = envelope["trace"]
    if type(wire) is not dict or set(wire) != _TRACE_KEYS or type(wire["records"]) is not list or len(wire["records"]) > MAX_TRACE_RECORDS:
        raise TraceTransportError("bounded wire protocol projection required")
    prior, rows = hash_bytes(_raw(wire["genesis"], MAX_TRACE_RECORD_BYTES)), []
    for sequence, row in enumerate(wire["records"]):
        if type(row) is not dict or set(row) != {"kind", "payload"}:
            raise TraceTransportError("exact compact protocol record required")
        restored = dict(row, sequence=sequence, previous_sha256=prior)
        prior = hash_bytes(_raw(restored, MAX_TRACE_RECORD_BYTES))
        rows.append(restored)
    trace = _trace(dict(wire, records=rows))
    if hash_payload(trace) != _digest(envelope["trace_sha256"]):
        raise TraceTransportError("reconstructed complete trace differs from retained identity")
    extra = _object(_raw(envelope["metadata"], MAX_METADATA_BYTES), MAX_METADATA_BYTES)
    if (extra.get("status") not in ("complete", "failed")
            or (extra["status"] == "complete" and trace["count"] != 752)):
        raise TraceTransportError("invalid complete/failed trace status")
    if extra["status"] == "complete" and trace["genesis"]["mode"] != "base":
        raise TraceTransportError("complete transport requires the fixed base candidate")
    return {"schema": "gdr.synthetic.reconstructed-trace.v1", "trace": trace,
        "runtime_context": context, "metadata": extra, "trace_sha256": envelope["trace_sha256"],
        "raw_fragment_sha256": expected_sha256, "raw_fragment_hashes": [hash_bytes(raw) for raw in fragments],
        "external_provenance_verified": False, "native_runtime_verified": False, "cloud_completed": False}


def transport_manifest(fragments):
    """Every raw ordered identity, byte budget and anchor; no platform actions."""
    fragments = _fragments(fragments)
    return {"schema": "gdr.synthetic.trace-log-manifest.v1", "fragment_count": len(fragments),
        "log_bytes_including_lf": sum(len(raw) + 1 for raw in fragments),
        "fragment_hashes": [hash_bytes(raw) for raw in fragments], "sha256": trace_fragment_anchor(fragments),
        "max_line_bytes": max(map(len, fragments)), "route": "log", "quota_verified": False,
        "external_provenance_verified": False, "native_runtime_verified": False}
