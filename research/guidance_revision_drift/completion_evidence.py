"""Passive fixed-fixture trace transport/replay, never native authenticity.

The chunks carry complete bounded evidence without weakening the 64-KiB
decoder. Reconciliation proves consistency with the fixed source protocol;
caller-supplied platform receipts cannot prove that an engine actually ran.
No SDK, credential, network, cloud action or authority promotion exists here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import re

from data.financial_primitives import to_decimal
from data.hashing import canonical_json, hash_bytes, hash_payload
from research.guidance_revision_drift.contracts import CandidateError, _decode
from research.guidance_revision_drift.lean_bridge import (
    BridgeError, MAX_TRACE_RECORDS, MAX_TRACE_RECORD_BYTES, SyntheticOrderBridge,
    fixture_frames, fixture_stream,
)


CHUNK_RECORDS = 8
MAX_CHUNK_BYTES = 65_536
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_TRACE_KEYS = {"schema", "genesis", "genesis_sha256", "records", "count",
               "head_sha256", "native_runtime_verified", "cloud_completed"}
_CHUNK_KEYS = {"schema", "sequence", "chunk_count", "trace_sha256", "genesis",
               "genesis_sha256", "head_sha256", "record_count", "records"}


class EvidenceError(ValueError):
    """Malformed, incomplete, changed or unbound synthetic evidence."""


def _digest(value):
    if type(value) is not str or not _DIGEST.fullmatch(value):
        raise EvidenceError("exact lowercase retained SHA-256 required")
    return value


def _raw(body):
    # Caller projections are not already bounded bytes. Refuse large/deep or
    # non-JSON trees before the serializer allocates their complete encoding.
    remaining, text_budget = [8192], [MAX_CHUNK_BYTES]
    def check(value, depth=0):
        remaining[0] -= 1
        if depth > 16 or remaining[0] < 0:
            raise EvidenceError("evidence projection exceeds structural bounds")
        if type(value) is str:
            if len(value) > MAX_CHUNK_BYTES:
                raise EvidenceError("evidence text exceeds bound")
            text_budget[0] -= len(value.encode("utf-8"))
            if text_budget[0] < 0:
                raise EvidenceError("aggregate evidence text exceeds bound")
        elif type(value) is int:
            if value.bit_length() > 128:
                raise EvidenceError("evidence integer exceeds bound")
        elif value is None or type(value) is bool:
            pass
        elif type(value) in (dict, list):
            if len(value) > 8192:
                raise EvidenceError("evidence container exceeds bound")
            if type(value) is dict:
                for key, item in value.items():
                    if type(key) is not str:
                        raise EvidenceError("exact JSON text keys required")
                    check(key, depth + 1)
                    check(item, depth + 1)
            else:
                for item in value:
                    check(item, depth + 1)
        else:
            raise EvidenceError("exact JSON scalars/containers required")
    try:
        check(body)
        encoded = canonical_json(body).encode("utf-8")
        if len(encoded) > MAX_CHUNK_BYTES:
            raise EvidenceError("canonical evidence projection exceeds byte bound")
        return encoded
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise EvidenceError("bounded strict canonical evidence required") from exc


def _body(raw, limit):
    if type(raw) is not bytes or not 0 < len(raw) <= limit:
        raise EvidenceError("evidence bytes outside bound")
    try:
        body = _decode(raw)
    except CandidateError as exc:
        raise EvidenceError("invalid strict evidence JSON") from exc
    if _raw(body) != raw:
        raise EvidenceError("noncanonical evidence bytes")
    return body


@dataclass(frozen=True, slots=True)
class TraceEvidence:
    """Immutable record bytes; hashes are consistency anchors, not credentials."""

    genesis: bytes
    records: tuple[bytes, ...]
    head_sha256: str

    def __post_init__(self):
        genesis = _body(self.genesis, MAX_TRACE_RECORD_BYTES)
        if (set(genesis) != {"schema", "mode", "fixture_sha256", "native_runtime_verified"}
                or genesis["schema"] != "gdr.lean.protocol-genesis.v1"
                or type(genesis["mode"]) is not str or genesis["mode"] not in ("base", "stress")
                or genesis["fixture_sha256"] != hash_bytes(fixture_stream())
                or genesis["native_runtime_verified"] is not False):
            raise EvidenceError("genesis is not the fixed synthetic fixture")
        if type(self.records) is not tuple or len(self.records) > MAX_TRACE_RECORDS:
            raise EvidenceError("immutable bounded trace-record tuple required")
        prior = hash_bytes(self.genesis)
        for sequence, raw in enumerate(self.records):
            record = _body(raw, MAX_TRACE_RECORD_BYTES)
            if (set(record) != {"sequence", "previous_sha256", "kind", "payload"}
                    or type(record["sequence"]) is not int or record["sequence"] != sequence
                    or record["previous_sha256"] != prior or type(record["kind"]) is not str
                    or record["kind"] not in {"frame", "account_checkpoint", "binding", "fill_issue", "acknowledgement"}
                    or type(record["payload"]) is not dict):
                raise EvidenceError("broken or unsupported complete protocol trace")
            prior = hash_bytes(raw)
        if _digest(self.head_sha256) != prior:
            raise EvidenceError("trace head differs from exact record chain")

    @classmethod
    def from_trace(cls, trace):
        if type(trace) is not dict or set(trace) != _TRACE_KEYS:
            raise EvidenceError("exact complete protocol projection required")
        if (trace["schema"] != "gdr.lean.protocol-trace.v1"
                or trace["native_runtime_verified"] is not False
                or trace["cloud_completed"] is not False
                or type(trace["records"]) is not list
                or len(trace["records"]) > MAX_TRACE_RECORDS
                or type(trace["count"]) is not int
                or trace["count"] != len(trace["records"])):
            raise EvidenceError("protocol projection cannot assert native completion")
        result = cls(_raw(trace["genesis"]), tuple(_raw(row) for row in trace["records"]), trace["head_sha256"])
        if trace["genesis_sha256"] != hash_bytes(result.genesis):
            raise EvidenceError("genesis anchor differs from supplied bytes")
        return result

    @property
    def sha256(self):
        self.__post_init__()
        return hash_payload({"schema": "gdr.synthetic.trace-evidence.v1",
            "genesis_sha256": hash_bytes(self.genesis), "head_sha256": self.head_sha256,
            "record_hashes": [hash_bytes(raw) for raw in self.records]})

    def to_chunks(self):
        self.__post_init__()
        count = max(1, (len(self.records) + CHUNK_RECORDS - 1) // CHUNK_RECORDS)
        anchor = self.sha256
        chunks = []
        for index in range(count):
            raw = _raw({"schema": "gdr.synthetic.trace-chunk.v1", "sequence": index,
                "chunk_count": count, "trace_sha256": anchor,
                "genesis": _body(self.genesis, MAX_TRACE_RECORD_BYTES),
                "genesis_sha256": hash_bytes(self.genesis), "head_sha256": self.head_sha256,
                "record_count": len(self.records),
                "records": [_body(row, MAX_TRACE_RECORD_BYTES)
                    for row in self.records[index * CHUNK_RECORDS:(index + 1) * CHUNK_RECORDS]]})
            if len(raw) > MAX_CHUNK_BYTES:
                raise EvidenceError("chunk exceeds unchanged decoder bound")
            chunks.append(raw)
        return tuple(chunks)

    @classmethod
    def from_chunks(cls, chunks, *, expected_sha256):
        _digest(expected_sha256)
        if (type(chunks) is not tuple or not 1 <= len(chunks)
                <= (MAX_TRACE_RECORDS + CHUNK_RECORDS - 1) // CHUNK_RECORDS):
            raise EvidenceError("complete immutable bounded chunk tuple required")
        bodies = tuple(_body(raw, MAX_CHUNK_BYTES) for raw in chunks)
        first = bodies[0]
        for sequence, body in enumerate(bodies):
            if (set(body) != _CHUNK_KEYS or body["schema"] != "gdr.synthetic.trace-chunk.v1"
                    or type(body["sequence"]) is not int or body["sequence"] != sequence
                    or type(body["chunk_count"]) is not int or body["chunk_count"] != len(chunks)
                    or body["trace_sha256"] != expected_sha256
                    or type(body["record_count"]) is not int
                    or not 0 <= body["record_count"] <= MAX_TRACE_RECORDS
                    or type(body["records"]) is not list or len(body["records"]) > CHUNK_RECORDS
                    or any(body[key] != first[key] for key in ("genesis", "genesis_sha256", "head_sha256", "record_count"))):
                raise EvidenceError("incomplete, reordered or inconsistent trace chunks")
        result = cls(_raw(first["genesis"]), tuple(_raw(row) for body in bodies for row in body["records"]), first["head_sha256"])
        if (hash_bytes(result.genesis) != first["genesis_sha256"]
                or len(result.records) != first["record_count"]
                or result.sha256 != expected_sha256 or result.to_chunks() != chunks):
            raise EvidenceError("chunks differ from retained complete trace identity")
        return result


def export_trace(bridge):
    if type(bridge) is not SyntheticOrderBridge:
        raise EvidenceError("exact fixed synthetic bridge required")
    return TraceEvidence.from_trace(bridge.protocol_trace())


def _utc(value):
    if type(value) is not str or len(value) > 64:
        raise EvidenceError("bounded UTC receipt clock required")
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise EvidenceError("invalid receipt clock") from exc
    if result.tzinfo is None or result.utcoffset() != timezone.utc.utcoffset(result):
        raise EvidenceError("UTC receipt clock required")
    return result


def _compare_append(bridge, records, start, width):
    # Public detached projection only; no mutation of bridge internals.
    emitted = bridge.protocol_trace()["records"]
    if (len(emitted) != start + width
            or tuple(_raw(row) for row in emitted[start:]) != records[start:start + width]):
        raise EvidenceError("receipt payload differs from actual protocol reconstruction")


def replay_completion(evidence, *, expected_sha256):
    """Replay every observed record against fixed software, no SDK required."""
    if type(evidence) is not TraceEvidence or evidence.sha256 != _digest(expected_sha256):
        raise EvidenceError("trace differs from caller-retained evidence anchor")
    bridge = SyntheticOrderBridge(_body(evidence.genesis, MAX_TRACE_RECORD_BYTES)["mode"])
    if _raw(bridge.protocol_trace()["genesis"]) != evidence.genesis:
        raise EvidenceError("genesis does not reconstruct from current fixture")
    index = 0
    try:
        while index < len(evidence.records):
            record = _body(evidence.records[index], MAX_TRACE_RECORD_BYTES)
            payload, kind = record["payload"], record["kind"]
            width = 1
            if kind == "account_checkpoint":
                if index + 1 >= len(evidence.records):
                    raise EvidenceError("account checkpoint has no subsequent frame")
                frame_record = _body(evidence.records[index + 1], MAX_TRACE_RECORD_BYTES)
                if frame_record["kind"] != "frame":
                    raise EvidenceError("account checkpoint must immediately precede its frame")
                bridge.step(frame_record["payload"], native_quantity=to_decimal(payload["quantity"]),
                            native_cash=to_decimal(payload["immediate_cash"]))
                width = 2
            elif kind == "frame":
                raise EvidenceError("fixed native evidence requires one account checkpoint per frame")
            elif kind == "binding":
                bridge.bind(payload["order_id"], payload["native_id"])
            elif kind == "fill_issue":
                if bridge.issue_fill(payload["native_id"], _utc(payload["at"])) is None:
                    raise EvidenceError("fill issuance has no matching pending receipt")
            elif kind == "acknowledgement":
                bridge.order_event(native_id=payload["native_id"], event_id=payload["event_id"],
                    status=payload["status"], at=_utc(payload["at"]), quantity=payload["quantity"],
                    price=to_decimal(payload["price"]), fee=to_decimal(payload["fee"]))
            else:
                raise EvidenceError("unsupported protocol record")
            _compare_append(bridge, evidence.records, index, width)
            index += width
        report = bridge.finish()
    except (BridgeError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, EvidenceError):
            raise
        raise EvidenceError("fixed synthetic protocol did not reconcile") from exc
    if (report["native_account_checkpoints"] != len(fixture_frames())
            or report["protocol_trace_head_sha256"] != evidence.head_sha256):
        raise EvidenceError("complete fixed checkpoint/calendar evidence required")
    return {"schema": "gdr.synthetic.replayed-completion.v1", "trace_sha256": evidence.sha256,
        "trace_head_sha256": evidence.head_sha256, "record_count": len(evidence.records),
        "account_checkpoints": report["native_account_checkpoints"],
        "strategy_sha256": hash_payload(report["strategy"]), "strategy": report["strategy"],
        "protocol_reconciled": True, "external_provenance_verified": False,
        "native_runtime_verified": False, "cloud_completed": False,
        "empirical_evidence": False, "settlement_parity_verified": False}


def completion_output(evidence, *, binding_sha256):
    """Canonical supplied-output envelope; generating it is not execution.

    A real job's retrieved normalized output must independently agree with
    these bytes. The envelope binds every complete trace chunk to one binding;
    it is never an authenticated platform receipt or permission certificate.
    """
    if type(evidence) is not TraceEvidence:
        raise EvidenceError("exact immutable complete trace required")
    return _raw({"schema": "gdr.synthetic.supplied-completion-output.v1",
        "binding_sha256": _digest(binding_sha256), "trace_sha256": evidence.sha256,
        "head_sha256": evidence.head_sha256, "record_count": len(evidence.records),
        "chunk_hashes": [hash_bytes(chunk) for chunk in evidence.to_chunks()],
        "external_provenance_verified": False, "native_runtime_verified": False})


def completion_dossier(evidence, *, expected_sha256, binding, compile_receipt,
                       run_receipt, run_output, journal_snapshot, expected_journal_head_sha256):
    """Link passive receipts and a replay without converting assertions to proof.

    Type/schema guards are owned by the evaluation contracts. A successful
    dossier remains unverified external provenance even with matching IDs.
    """
    from research.guidance_revision_drift.evaluation import (
        CandidateBinding, CompileReceipt, RunReceipt, EvaluationError,
        validate_journal_projection,
    )
    from research.guidance_revision_drift.qc_project import qc_project_manifest

    if (type(binding) is not CandidateBinding or type(compile_receipt) is not CompileReceipt
            or type(run_receipt) is not RunReceipt):
        raise EvidenceError("exact passive binding and receipt contracts required")
    binding.__post_init__()
    compile_receipt.__post_init__()
    run_receipt.__post_init__()
    if (type(evidence) is not TraceEvidence
            or _body(evidence.genesis, MAX_TRACE_RECORD_BYTES)["mode"] != "base"):
        raise EvidenceError("approved fixed candidate requires the base synthetic trace")
    candidate = binding.to_dict()
    compiled, ran = compile_receipt.to_dict(), run_receipt.to_dict()
    current = qc_project_manifest()
    for field, manifest_field in (("source_sha256", "source_manifest_sha256"),
            ("project_sha256", "project_sha256"), ("bundle_sha256", "bundle_sha256"),
            ("fixture_sha256", "fixture_sha256"), ("candidate_sha256", "candidate_sha256")):
        if candidate[field] != current[manifest_field]:
            raise EvidenceError("completion dossier is not bound to current exact source/project/fixture")
    if (compiled["binding_sha256"] != binding.sha256 or ran["binding_sha256"] != binding.sha256
            or compiled["status"] != "compiled" or ran["status"] != "completed"
            or any(compiled[key] != ran[key] for key in ("attempt_id", "project_id", "compile_id", "engine", "binding_version"))):
        raise EvidenceError("compile/run receipts do not describe one successful candidate attempt")
    _body(run_output, MAX_CHUNK_BYTES)
    if (hash_bytes(run_output) != ran["output_sha256"]
            or run_output != completion_output(evidence, binding_sha256=binding.sha256)):
        raise EvidenceError("run output differs from retained receipt/complete trace binding")
    # Snapshot the full caller projection into canonical immutable bytes first.
    snapshot = _body(_raw(journal_snapshot), MAX_CHUNK_BYTES)
    try:
        snapshot = validate_journal_projection(snapshot, binding=binding,
            expected_head_sha256=expected_journal_head_sha256)
    except EvaluationError as exc:
        raise EvidenceError("complete retained attempt journal does not reconcile") from exc
    attempts = snapshot.get("attempts")
    if type(attempts) is not list:
        raise EvidenceError("complete attempt journal projection required")
    matches = [row for row in attempts if type(row) is dict and row.get("attempt_id") == ran["attempt_id"]]
    if (len(matches) != 1 or matches[0].get("compile") != compiled or matches[0].get("run") != ran):
        raise EvidenceError("complete matching compile/run receipts absent from attempt journal")
    replay = replay_completion(evidence, expected_sha256=expected_sha256)
    return {"schema": "gdr.synthetic.completion-dossier.v1", "binding_sha256": binding.sha256,
        "trace_sha256": evidence.sha256, "receipt_sha256": hash_payload({"compile": compiled, "run": ran}),
        "journal_snapshot_sha256": hash_bytes(_raw(snapshot)), "run_output_sha256": hash_bytes(run_output), "replay": replay,
        "platform_status_observed": "completed", "external_provenance_verified": False,
        "native_runtime_verified": False, "cloud_completed": False,
        "empirical_backtest_ready": False, "qc_upload_allowed": False, "qc_launch_allowed": False,
        "note": "Matching supplied records establish software consistency, not authenticated engine execution."}
