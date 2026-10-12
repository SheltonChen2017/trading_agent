"""Readable fixed-fixture record commitments, never raw/native provenance.

Messages are ordinary canonical ASCII JSON. No source or evidence is encoded,
compressed, packed or split into opaque character fragments. Every accepted
record is committed by its full canonical SHA-256; exceptional native IDs and
receipts, valuation rows and reflective observations remain readable values.
Reconstruction uses the fixed software and the supplied native receipt inputs,
then checks every record commitment. It is digest-reconciled local
reconstruction, not a lossless transport of observed raw transcript bytes.
No SDK, filesystem, network, platform operation or authority promotion.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from data.financial_primitives import exact_decimal_sum, to_decimal
from data.hashing import canonical_json, hash_bytes, hash_payload
from research.guidance_revision_drift.contracts import CANDIDATE_SHA256, CandidateError, _decode
from research.guidance_revision_drift.lean_bridge import (
    BridgeError, MAX_TRACE_RECORD_BYTES, MAX_TRACE_RECORDS, SyntheticOrderBridge, fixture_frames,
)
from research.guidance_revision_drift.native_observation import (
    FIXTURE_SHA256, ObservationError, validate_native_metadata,
)


SCHEMA = "gdr.synthetic.readable-evidence.v1"
PROVENANCE = "digest-reconciled local reconstruction"
MAX_LOG_BYTES, MAX_MESSAGES, MAX_LINE_BYTES = 100_000, 1024, 200
MAX_METADATA_BYTES = 65_536
_TRACE_KEYS = {"schema", "genesis", "genesis_sha256", "records", "count",
               "head_sha256", "native_runtime_verified", "cloud_completed"}
_CONTEXT_KEYS = {"runtime_source_sha256", "bundle_sha256", "candidate_sha256", "fixture_sha256"}
_EVENT_KINDS = {"binding", "fill_issue", "acknowledgement"}
_AUTHORITY = {"external_provenance_verified", "native_runtime_verified", "cloud_completed",
    "execution_authorized", "qc_upload_allowed", "qc_launch_allowed", "economic_acceptance",
    "market_evidence", "empirical_backtest_ready", "empirical_readiness", "empirical_evidence",
    "settlement_parity_verified", "native_binding_verified", "cloud_completion_verified"}


class ReadableTransportError(ValueError):
    """Incomplete, changed, non-readable or oversized fixed-fixture evidence."""


def _digest(value):
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ReadableTransportError("exact lowercase retained SHA-256 required")
    return value


def _plain(value, limit):
    remaining, text_budget = [100_000], [limit]
    def visit(item, depth=0):
        remaining[0] -= 1
        if depth > 16 or remaining[0] < 0:
            raise ReadableTransportError("readable evidence exceeds structural bound")
        if item is None or type(item) is bool:
            return
        if type(item) is int:
            if item.bit_length() > 128:
                raise ReadableTransportError("readable integer exceeds bound")
        elif type(item) is str:
            if len(item) > limit:
                raise ReadableTransportError("readable text exceeds bound")
            text_budget[0] -= len(item.encode("utf-8"))
            if text_budget[0] < 0:
                raise ReadableTransportError("aggregate readable text exceeds bound")
        elif type(item) in (dict, list):
            if len(item) > 4096:
                raise ReadableTransportError("readable container exceeds bound")
            if type(item) is dict:
                for key, child in item.items():
                    if type(key) is not str or (key in _AUTHORITY and child is not False):
                        raise ReadableTransportError("readable evidence cannot assert authority")
                    visit(key, depth + 1)
                    visit(child, depth + 1)
            else:
                for child in item:
                    visit(child, depth + 1)
        else:
            raise ReadableTransportError("exact JSON values required")
    visit(value)
    return value


def _raw(value, limit):
    try:
        raw = canonical_json(_plain(value, limit)).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, ReadableTransportError):
            raise
        raise ReadableTransportError("bounded readable JSON required") from exc
    if len(raw) > limit:
        raise ReadableTransportError("readable evidence bytes exceed bound")
    return raw


def _object(raw, limit):
    if type(raw) is not bytes or not 0 < len(raw) <= limit:
        raise ReadableTransportError("bounded immutable readable bytes required")
    try:
        body = _decode(raw)
    except CandidateError as exc:
        raise ReadableTransportError("strict readable JSON object required") from exc
    if _raw(body, limit) != raw:
        raise ReadableTransportError("canonical readable JSON required")
    return body


def _line(body):
    raw = _raw(body, MAX_LINE_BYTES)
    try:
        raw.decode("ascii")
    except UnicodeError as exc:
        raise ReadableTransportError("atomic readable JSON values must be ASCII") from exc
    return raw


def _lines(value):
    if (type(value) is not tuple or not 7 <= len(value) <= MAX_MESSAGES + 1
            or any(type(raw) is not bytes or not 0 < len(raw) <= MAX_LINE_BYTES for raw in value)
            or sum(len(raw) + 1 for raw in value) > MAX_LOG_BYTES):
        raise ReadableTransportError("bounded complete immutable readable messages required")
    for raw in value:
        try:
            raw.decode("ascii")
        except UnicodeError as exc:
            raise ReadableTransportError("readable messages must be ASCII") from exc
        _object(raw, MAX_LINE_BYTES)
    return value


def _context(value):
    if type(value) is not dict or set(value) != _CONTEXT_KEYS:
        raise ReadableTransportError("exact fixed runtime context required")
    result = {key: _digest(item) for key, item in value.items()}
    if result["candidate_sha256"] != CANDIDATE_SHA256 or result["fixture_sha256"] != FIXTURE_SHA256:
        raise ReadableTransportError("context differs from fixed candidate/fixture")
    return result


def _trace(value):
    if (type(value) is not dict or set(value) != _TRACE_KEYS
            or value["schema"] != "gdr.lean.protocol-trace.v1"
            or type(value["count"]) is not int or type(value["records"]) is not list
            or not 0 <= value["count"] <= MAX_TRACE_RECORDS
            or value["count"] != len(value["records"])
            or value["native_runtime_verified"] is not False or value["cloud_completed"] is not False):
        raise ReadableTransportError("bounded nonpromoting protocol projection required")
    genesis = _object(_raw(value["genesis"], MAX_TRACE_RECORD_BYTES), MAX_TRACE_RECORD_BYTES)
    if (set(genesis) != {"schema", "mode", "fixture_sha256", "native_runtime_verified"}
            or genesis["schema"] != "gdr.lean.protocol-genesis.v1"
            or type(genesis["mode"]) is not str or genesis["mode"] not in {"base", "stress"}
            or genesis["fixture_sha256"] != FIXTURE_SHA256
            or genesis["native_runtime_verified"] is not False):
        raise ReadableTransportError("fixed synthetic genesis required")
    prior = hash_bytes(_raw(genesis, MAX_TRACE_RECORD_BYTES))
    if value["genesis_sha256"] != prior:
        raise ReadableTransportError("genesis anchor differs")
    rows = []
    for sequence, row in enumerate(value["records"]):
        checked = _object(_raw(row, MAX_TRACE_RECORD_BYTES), MAX_TRACE_RECORD_BYTES)
        if (set(checked) != {"sequence", "previous_sha256", "kind", "payload"}
                or type(checked["sequence"]) is not int or checked["sequence"] != sequence
                or checked["previous_sha256"] != prior or type(checked["kind"]) is not str
                or checked["kind"] not in _EVENT_KINDS | {"frame", "account_checkpoint"}
                or type(checked["payload"]) is not dict):
            raise ReadableTransportError("protocol record chain differs")
        prior = hash_bytes(_raw(checked, MAX_TRACE_RECORD_BYTES))
        rows.append(checked)
    if _digest(value["head_sha256"]) != prior:
        raise ReadableTransportError("protocol head differs")
    return dict(value, genesis=genesis, records=rows)


def _fields(value, path=()):
    """Readable atomic JSON fields, not opaque fragments of encoded text."""
    if type(value) is dict and value:
        for key in sorted(value):
            yield from _fields(value[key], path + (key,))
    elif type(value) is list and value:
        for index, child in enumerate(value):
            yield from _fields(child, path + (index,))
    else:
        yield list(path), value


def _restore(fields):
    result = {}
    seen = set()
    for path, value in fields:
        if (type(path) is not list or not 1 <= len(path) <= 16
                or type(path[0]) is not str
                or any((type(part) is not str or not part or len(part) > 128)
                       and (type(part) is not int or not 0 <= part < 4096) for part in path)):
            raise ReadableTransportError("bounded readable field path required")
        identity = tuple(path)
        if identity in seen or any(identity[:index] in seen for index in range(1, len(identity))):
            raise ReadableTransportError("duplicate or overlapping readable field")
        seen.add(identity)
        node = result
        for index, part in enumerate(path):
            final = index == len(path) - 1
            if type(node) is dict:
                if type(part) is not str or part in node and final:
                    raise ReadableTransportError("inconsistent readable object field")
                if final:
                    node[part] = value
                else:
                    wanted = [] if type(path[index + 1]) is int else {}
                    if part not in node:
                        node[part] = wanted
                    elif type(node[part]) is not type(wanted):
                        raise ReadableTransportError("inconsistent readable field container")
                    node = node[part]
            elif type(node) is list:
                if type(part) is not int or part > len(node) or (part < len(node) and final):
                    raise ReadableTransportError("noncontiguous readable list field")
                if final:
                    node.append(value)
                else:
                    wanted = [] if type(path[index + 1]) is int else {}
                    if part == len(node):
                        node.append(wanted)
                    elif type(node[part]) is not type(wanted):
                        raise ReadableTransportError("inconsistent readable list container")
                    node = node[part]
            else:
                raise ReadableTransportError("readable field overlaps scalar")
    return result


def readable_evidence_anchor(lines):
    """Retain externally; this ordered-content anchor is not authentication."""
    return hash_payload([hash_bytes(raw) for raw in _lines(lines)])


def export_readable_evidence(trace, *, runtime_context, metadata):
    """Prepare the complete bounded output before callers emit any message."""
    body, context = _trace(trace), _context(runtime_context)
    try:
        extra = validate_native_metadata(_object(_raw(metadata, MAX_METADATA_BYTES), MAX_METADATA_BYTES), body)
    except (ObservationError, KeyError, TypeError, ValueError) as exc:
        raise ReadableTransportError("native metadata differs from transcript") from exc
    if extra["status"] == "complete" and (body["count"] != 752 or body["genesis"]["mode"] != "base"):
        raise ReadableTransportError("complete fixed synthetic trace requires all base records")
    result = [_line({"schema": SCHEMA, "status": extra["status"], "record_count": body["count"],
                     "head_sha256": body["head_sha256"]}),
              _line({"mode": body["genesis"]["mode"], "genesis_sha256": body["genesis_sha256"]})]
    result.extend(_line({"context": key, "sha256": context[key]}) for key in sorted(context))
    valuations = iter(extra["valuation_rows"])
    for row in body["records"]:
        commitment = {"record": row["sequence"], "sha256": hash_bytes(_raw(row, MAX_TRACE_RECORD_BYTES))}
        if row["kind"] == "account_checkpoint":
            commitment["valuation"] = next(valuations)
        result.append(_line(commitment))
    for row in body["records"]:
        if row["kind"] in _EVENT_KINDS:
            result.extend(_line({"event": row["sequence"], "kind": row["kind"], "path": path, "value": value})
                          for path, value in _fields(row["payload"]))
    result.extend(_line({"metadata": path, "value": value}) for path, value in _fields(
        {key: value for key, value in extra.items() if key != "valuation_rows"}))
    result.append(_line({"end": SCHEMA, "line_count": len(result),
                         "sha256": hash_payload([hash_bytes(raw) for raw in result])}))
    return _lines(tuple(result))


def _instant(value):
    if type(value) is not str or len(value) > 128:
        raise ReadableTransportError("exact bounded UTC event clock required")
    try:
        at = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ReadableTransportError("invalid supplied event clock") from exc
    if at.tzinfo != timezone.utc or at.isoformat() != value:
        raise ReadableTransportError("exact canonical UTC event clock required")
    return at


def _rebuild(mode, commitments, events, *, complete):
    bridge = SyntheticOrderBridge(mode)
    frames, frame_index, index, valuations = fixture_frames(), 0, 0, []
    try:
        while index < len(commitments):
            prior_count = len(bridge.protocol_trace()["records"])
            if index in events:
                kind, payload = events[index]
                if kind == "binding":
                    bridge.bind(payload["order_id"], payload["native_id"])
                elif kind == "fill_issue":
                    if bridge.issue_fill(payload["native_id"], _instant(payload["at"])) is None:
                        raise ReadableTransportError("supplied fill has no pending receipt")
                else:
                    bridge.order_event(native_id=payload["native_id"], event_id=payload["event_id"],
                        status=payload["status"], at=_instant(payload["at"]), quantity=payload["quantity"],
                        price=to_decimal(payload["price"]), fee=to_decimal(payload["fee"]))
                emitted = bridge.protocol_trace()["records"][prior_count:]
                if len(emitted) != 1 or emitted[0]["kind"] != kind or emitted[0]["payload"] != payload:
                    raise ReadableTransportError("supplied exceptional payload differs from reconstruction")
            else:
                if frame_index >= len(frames):
                    raise ReadableTransportError("extra fixed frame commitment")
                state = bridge.engine.snapshot()
                bridge.step(frames[frame_index], native_quantity=Decimal(sum(p["quantity"] for p in state["positions"])),
                    native_cash=exact_decimal_sum((Decimal(state["settled_cash"]),
                        *(Decimal(row["amount"]) for row in state["receivables"]))))
                emitted = bridge.protocol_trace()["records"][prior_count:]
                frame_index += 1
                if len(emitted) != 2:
                    raise ReadableTransportError("fixed frame/checkpoint reconstruction differs")
            if index + len(emitted) > len(commitments):
                raise ReadableTransportError("partial frame/checkpoint pair")
            for row in emitted:
                committed = commitments[index]
                if committed["sha256"] != hash_bytes(_raw(row, MAX_TRACE_RECORD_BYTES)):
                    raise ReadableTransportError("canonical reconstructed record differs from supplied digest")
                checkpoint = row["kind"] == "account_checkpoint"
                if ("valuation" in committed) is not checkpoint:
                    raise ReadableTransportError("valuation must accompany exactly its checkpoint commitment")
                if checkpoint:
                    valuations.append(committed["valuation"])
                index += 1
        if complete:
            report = bridge.finish()
            if frame_index != 372 or report["native_account_checkpoints"] != 372:
                raise ReadableTransportError("complete fixed frame/account evidence required")
    except (BridgeError, KeyError, TypeError, ValueError, ArithmeticError) as exc:
        if isinstance(exc, ReadableTransportError):
            raise
        raise ReadableTransportError("fixed supplied native events did not reconcile") from exc
    return bridge.protocol_trace(), valuations


def reconstruct_readable_evidence(lines, *, expected_sha256, expected_runtime_context):
    """Reconcile commitments, not recover an independently observed raw trace.

    The offline dossier must additionally run unchanged TraceEvidence/replay
    and authenticated receipt/cycle gates. A failed output is diagnostics only.
    """
    lines = _lines(lines)
    if readable_evidence_anchor(lines) != _digest(expected_sha256):
        raise ReadableTransportError("readable messages differ from retained anchor")
    rows = [_object(raw, MAX_LINE_BYTES) for raw in lines]
    header, genesis, end = rows[0], rows[1], rows[-1]
    if (set(header) != {"schema", "status", "record_count", "head_sha256"} or header["schema"] != SCHEMA
            or type(header["status"]) is not str or header["status"] not in {"complete", "failed"}
            or type(header["record_count"]) is not int
            or not 0 <= header["record_count"] <= MAX_TRACE_RECORDS
            or set(genesis) != {"mode", "genesis_sha256"} or type(genesis["mode"]) is not str
            or genesis["mode"] not in {"base", "stress"}
            or set(end) != {"end", "line_count", "sha256"} or end["end"] != SCHEMA
            or type(end["line_count"]) is not int or end["line_count"] != len(lines) - 1
            or end["sha256"] != hash_payload([hash_bytes(raw) for raw in lines[:-1]])):
        raise ReadableTransportError("exact complete readable envelope required")
    _digest(header["head_sha256"])
    _digest(genesis["genesis_sha256"])
    context = {}
    for row in rows[2:6]:
        if (set(row) != {"context", "sha256"} or type(row["context"]) is not str
                or row["context"] not in _CONTEXT_KEYS or row["context"] in context):
            raise ReadableTransportError("exact unique runtime context rows required")
        context[row["context"]] = _digest(row["sha256"])
    if _context(context) != _context(expected_runtime_context):
        raise ReadableTransportError("readable context differs from retained source")
    count = header["record_count"]
    commitments = []
    for index, row in enumerate(rows[6:6 + count]):
        if (set(row) not in ({"record", "sha256"}, {"record", "sha256", "valuation"})
                or type(row["record"]) is not int or row["record"] != index):
            raise ReadableTransportError("missing, extra or reordered record commitment")
        _digest(row["sha256"])
        commitments.append(row)
    if len(commitments) != count:
        raise ReadableTransportError("incomplete readable commitments")
    event_fields, metadata_fields = {}, []
    for row in rows[6 + count:-1]:
        if set(row) == {"event", "kind", "path", "value"}:
            identity = row["event"]
            if (type(identity) is not int or not 0 <= identity < count or type(row["kind"]) is not str
                    or row["kind"] not in _EVENT_KINDS):
                raise ReadableTransportError("bounded supplied exceptional record required")
            kind, fields = event_fields.setdefault(identity, (row["kind"], []))
            if kind != row["kind"]:
                raise ReadableTransportError("exceptional record kind differs")
            fields.append((row["path"], row["value"]))
        elif set(row) == {"metadata", "value"}:
            metadata_fields.append((row["metadata"], row["value"]))
        else:
            raise ReadableTransportError("unknown readable field row")
    events = {identity: (kind, _restore(fields)) for identity, (kind, fields) in event_fields.items()}
    metadata = _restore(metadata_fields)
    if "valuation_rows" in metadata or metadata.get("status") != header["status"]:
        raise ReadableTransportError("readable metadata status/valuation source differs")
    complete = header["status"] == "complete"
    if complete and (count != 752 or genesis["mode"] != "base"):
        raise ReadableTransportError("complete fixed synthetic trace requires all base records")
    trace, valuations = _rebuild(genesis["mode"], commitments, events, complete=complete)
    if trace["count"] != count or trace["head_sha256"] != header["head_sha256"] or trace["genesis_sha256"] != genesis["genesis_sha256"]:
        raise ReadableTransportError("reconstructed count/genesis/head differs")
    metadata["valuation_rows"] = valuations
    try:
        metadata = validate_native_metadata(_object(_raw(metadata, MAX_METADATA_BYTES), MAX_METADATA_BYTES), trace)
    except (ObservationError, KeyError, TypeError, ValueError) as exc:
        raise ReadableTransportError("readable native metadata did not reconcile") from exc
    if export_readable_evidence(trace, runtime_context=context, metadata=metadata) != lines:
        raise ReadableTransportError("noncanonical, missing or reordered readable field rows")
    return {"schema": "gdr.synthetic.readable-reconstructed.v1", "trace": trace,
        "runtime_context": context, "metadata": metadata, "trace_sha256": hash_payload(trace),
        "raw_fragment_sha256": expected_sha256, "raw_fragment_hashes": [hash_bytes(raw) for raw in lines],
        "evidence_provenance": PROVENANCE, "raw_transcript_transported": False,
        "external_provenance_verified": False, "native_runtime_verified": False, "cloud_completed": False,
        "empirical_backtest_ready": False, "qc_upload_allowed": False, "qc_launch_allowed": False}


def readable_transport_manifest(lines):
    """Exact ordered output identities and budgets; never a quota grant."""
    lines = _lines(lines)
    return {"schema": "gdr.synthetic.readable-log-manifest.v1", "line_count": len(lines),
        "log_bytes_including_lf": sum(len(raw) + 1 for raw in lines),
        "line_hashes": [hash_bytes(raw) for raw in lines], "sha256": readable_evidence_anchor(lines),
        "max_line_bytes": max(map(len, lines)), "route": "log", "quota_verified": False,
        "evidence_provenance": PROVENANCE, "raw_transcript_transported": False,
        "external_provenance_verified": False, "native_runtime_verified": False, "cloud_completed": False,
        "empirical_backtest_ready": False, "qc_upload_allowed": False, "qc_launch_allowed": False}
