"""Passive fixed-synthetic QC evidence custody; no platform actuator/approval.

Supplied review anchors, IDs and terminal statuses are observations, not proof
of external provenance. The owner controls journal directories and retains a
head separately; losing both the history and retained head is not detectable
rollback. Source differences are quarantined, never imported or ported here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.guidance_revision_drift.contracts import CANDIDATE_SHA256
from research.guidance_revision_drift.persistence import (
    JournalError, JournalConflict, canonical_object, decode_object, digest,
    _directory, _publish, _read,
)


FIXTURE_SHA256 = "8f35d56a335d3f7d9dad016e1e2236de7fcd2635e5c463c30081f97b7b944458"
MAX_RECORDS = 32
MAX_CLOUD_FILES = 64
MAX_CLOUD_FILE_BYTES = 32_000
_GENESIS = "evaluation-genesis.json"
_RECORD = re.compile(r"evaluation-([0-9]{6})\.json\Z")
_PYTHON_PATH = re.compile(r"[A-Za-z0-9_./-]+\.py\Z")


class EvaluationError(ValueError):
    """Invalid, conflicting or incomplete fixed synthetic observations."""


def _hash(value: object) -> str:
    try:
        return digest(value)
    except JournalError as exc:
        raise EvaluationError("exact lowercase SHA-256 required") from exc


def _identifier(value: object, *, attempt: bool = False) -> str:
    pattern = r"SYN-QC-[A-Za-z0-9_-]{1,48}" if attempt else r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}"
    if type(value) is not str or re.fullmatch(pattern, value) is None:
        raise EvaluationError("bounded exact observation ID required")
    return value


def _clock(value: object) -> datetime:
    if type(value) is not str or len(value) > 64:
        raise EvaluationError("explicit-offset timestamp text required")
    try:
        at = datetime.fromisoformat(value)
    except ValueError as exc:
        raise EvaluationError("invalid observation timestamp") from exc
    if at.tzinfo is None or at.utcoffset() is None or at.isoformat() != value:
        raise EvaluationError("canonical aware observation timestamp required")
    return at.astimezone(timezone.utc)


def _version(value: object) -> None:
    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9_.+:/-]{1,96}", value) is None:
        raise EvaluationError("bounded explicit engine/binding label required")


def _projection(value) -> dict:
    value.__post_init__()
    return {name: getattr(value, name) for name in value.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class CandidateBinding:
    source_sha256: str
    project_sha256: str
    bundle_sha256: str
    fixture_sha256: str
    source_commit: str
    review_commit: str
    review_record_sha256: str
    candidate_sha256: str = CANDIDATE_SHA256

    def __post_init__(self):
        for value in (self.source_sha256, self.project_sha256, self.bundle_sha256,
                      self.fixture_sha256, self.review_record_sha256, self.candidate_sha256):
            _hash(value)
        for value in (self.source_commit, self.review_commit):
            if type(value) is not str or re.fullmatch(r"[0-9a-f]{40}", value) is None:
                raise EvaluationError("exact source/review commit SHA required")
        if self.candidate_sha256 != CANDIDATE_SHA256 or self.fixture_sha256 != FIXTURE_SHA256:
            raise EvaluationError("only the fixed original candidate and 372-frame fixture are supported")

    def to_dict(self) -> dict:
        return _projection(self)

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_dict())


def _receipt_identity(receipt) -> None:
    _hash(receipt.binding_sha256)
    _identifier(receipt.attempt_id, attempt=True)
    if type(receipt.project_id) is not int or not 1 <= receipt.project_id < 2 ** 63:
        raise EvaluationError("positive exact integer project ID required")
    _identifier(receipt.compile_id)
    _version(receipt.engine)
    _version(receipt.binding_version)
    _hash(receipt.output_sha256)


@dataclass(frozen=True, slots=True)
class CompileReceipt:
    binding_sha256: str
    attempt_id: str
    project_id: int
    compile_id: str
    requested_at: str
    completed_at: str
    status: str
    engine: str
    binding_version: str
    output_sha256: str

    def __post_init__(self):
        _receipt_identity(self)
        if type(self.status) is not str or self.status not in ("compiled", "compile_failed"):
            raise EvaluationError("unknown terminal compile status")
        if _clock(self.completed_at) < _clock(self.requested_at):
            raise EvaluationError("compile completion precedes request")

    def to_dict(self) -> dict:
        return _projection(self)

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_dict())


@dataclass(frozen=True, slots=True)
class RunReceipt:
    binding_sha256: str
    attempt_id: str
    project_id: int
    compile_id: str
    run_id: str
    started_at: str
    completed_at: str
    status: str
    engine: str
    binding_version: str
    output_sha256: str

    def __post_init__(self):
        _receipt_identity(self)
        _identifier(self.run_id)
        if (type(self.status) is not str
                or self.status not in ("completed", "runtime_error", "cancelled", "other_failed")):
            raise EvaluationError("unknown terminal run status")
        if _clock(self.completed_at) < _clock(self.started_at):
            raise EvaluationError("run completion precedes start")

    def to_dict(self) -> dict:
        return _projection(self)

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_dict())


def _fields(body: object, fields: set[str]) -> dict:
    if type(body) is not dict or set(body) != fields:
        raise EvaluationError("unknown or missing evaluation fields")
    return body


def _receipt(body: dict, cls):
    _fields(body, set(cls.__dataclass_fields__))
    try:
        return cls(**body)
    except TypeError as exc:
        raise EvaluationError("invalid receipt projection") from exc


def _observation_floor(row):
    # There is no separate observed_at clock: an older terminal receipt cannot
    # silently clear later uncertainty. Do not rewrite historical platform
    # times to fit; that recovery needs an explicitly reviewed richer contract.
    clocks = [_clock(row["intent_at"])]
    if row["compile"]:
        clocks.append(_clock(row["compile"]["completed_at"]))
    if row["ambiguity"]:
        clocks.append(_clock(row["ambiguity"]["at"]))
    return max(clocks)


def _apply(attempts: list[dict], binding: CandidateBinding, operation: str, payload: dict) -> None:
    if operation == "intent":
        _fields(payload, {"attempt_id", "at"})
        _identifier(payload["attempt_id"], attempt=True)
        _clock(payload["at"])
        if (any(row["status"] in ("pending", "ambiguous", "compiled") for row in attempts)
                or any(row["status"] == "completed" for row in attempts)):
            raise EvaluationError("pending/ambiguous/completed observation blocks another intent")
        if len(attempts) >= 3 or sum(row["status"] == "failed" for row in attempts) >= 3:
            raise EvaluationError("maximum three unsuccessful candidate attempts reached")
        if any(row["attempt_id"] == payload["attempt_id"] for row in attempts):
            raise EvaluationError("attempt identity cannot be reused")
        if attempts and _clock(payload["at"]) < _clock(attempts[-1]["terminal_at"]):
            raise EvaluationError("new intent precedes previous terminal observation")
        attempts.append({"attempt_id": payload["attempt_id"], "intent_at": payload["at"],
                         "status": "pending", "compile": None, "run": None,
                         "failure": None, "ambiguity": None, "terminal_at": None})
        return
    if type(payload) is not dict or "attempt_id" not in payload:
        raise EvaluationError("attempt observation required")
    matches = [row for row in attempts if row["attempt_id"] == payload["attempt_id"]]
    if not matches or matches[-1]["status"] in ("completed", "failed"):
        raise EvaluationError("observation requires one unresolved launch intent")
    row = matches[-1]
    if operation == "compile":
        receipt = _receipt(payload, CompileReceipt)
        if (receipt.binding_sha256 != binding.sha256 or row["compile"] is not None
                or _clock(receipt.requested_at) < _clock(row["intent_at"])
                or _clock(receipt.completed_at) < _observation_floor(row)):
            raise EvaluationError("compile differs from exact candidate/intent")
        if any(other["compile"] is not None and
               (other["compile"]["project_id"] != receipt.project_id
                or other["compile"]["compile_id"] == receipt.compile_id)
               for other in attempts if other is not row):
            raise EvaluationError("project changed or compile ID reused across attempts")
        row["compile"] = receipt.to_dict()
        row["status"] = "failed" if receipt.status == "compile_failed" else "compiled"
        if receipt.status == "compile_failed":
            row["terminal_at"] = receipt.completed_at
    elif operation == "run":
        receipt = _receipt(payload, RunReceipt)
        compilation = row["compile"]
        if (receipt.binding_sha256 != binding.sha256 or compilation is None
                or compilation["status"] != "compiled"
                or any(getattr(receipt, name) != compilation[name]
                       for name in ("project_id", "compile_id", "engine", "binding_version"))
                or _clock(receipt.started_at) < _clock(compilation["completed_at"])
                or _clock(receipt.completed_at) < _observation_floor(row)):
            raise EvaluationError("run differs from candidate/compile lineage")
        if any(other["run"] is not None and other["run"]["run_id"] == receipt.run_id
               for other in attempts if other is not row):
            raise EvaluationError("run ID reused across attempts")
        row["run"] = receipt.to_dict()
        row["status"] = "completed" if receipt.status == "completed" else "failed"
        row["terminal_at"] = receipt.completed_at
    elif operation in ("failure", "ambiguous"):
        _fields(payload, {"attempt_id", "at", "output_sha256"})
        _hash(payload["output_sha256"])
        if _clock(payload["at"]) < _observation_floor(row):
            raise EvaluationError("observation precedes recorded attempt state")
        row["failure" if operation == "failure" else "ambiguity"] = dict(payload)
        row["status"] = "failed" if operation == "failure" else "ambiguous"
        if operation == "failure":
            row["terminal_at"] = payload["at"]
    else:
        raise EvaluationError("unsupported passive evaluation operation")


def _replay_records(records: list[dict], binding: CandidateBinding, genesis: str):
    if type(records) is not list or len(records) > MAX_RECORDS:
        raise EvaluationError("bounded evaluation record list required")
    head, heads, attempts, identities = genesis, {genesis}, [], set()
    for sequence, record in enumerate(records, 1):
        _fields(record, {"schema", "sequence", "previous_sha256", "binding_sha256", "operation", "payload"})
        if (record["schema"] != "gdr.synthetic.evaluation-record.v1"
                or type(record["sequence"]) is not int or record["sequence"] != sequence
                or record["previous_sha256"] != head or record["binding_sha256"] != binding.sha256
                or type(record["operation"]) is not str or type(record["payload"]) is not dict):
            raise EvaluationError("broken candidate evaluation chain")
        identity = (record["operation"], _identifier(record["payload"].get("attempt_id"), attempt=True))
        if identity in identities:
            raise EvaluationError("reused evaluation observation identity")
        _apply(attempts, binding, record["operation"], record["payload"])
        identities.add(identity)
        head = hash_bytes(canonical_object(record))
        heads.add(head)
    return head, heads, attempts


def _summary(binding, genesis, head, records, attempts):
    failed = sum(row["status"] == "failed" for row in attempts)
    pending = sum(row["status"] in ("pending", "compiled", "ambiguous") for row in attempts)
    completed = any(row["status"] == "completed" for row in attempts)
    return {"schema": "gdr.synthetic.evaluation-ledger.v1", "binding": binding.to_dict(),
            "binding_sha256": binding.sha256, "genesis_sha256": genesis,
            "head_sha256": head, "records": records, "attempts": attempts,
            "launch_intents": len(attempts), "unsuccessful_attempts": failed,
            "pending_attempts": pending, "completed_observed": completed,
            "next_action": ("reconcile_pending_observation" if pending else
                "stop_notify_owner_then_Mia_if_accessible" if failed == 3 else
                "completion_evidence_and_external_provenance_unverified" if completed else
                "still_requires_exact_review_and_external_authority"),
            "external_provenance_verified": False, "native_runtime_verified": False,
            "qc_launch_allowed": False, "economic_acceptance": False, "market_evidence": False}


def validate_journal_projection(snapshot: dict, *, binding: CandidateBinding,
                                expected_head_sha256: str) -> dict:
    """Replay the entire private snapshot against the exact retained head."""
    if type(binding) is not CandidateBinding or type(snapshot) is not dict:
        raise EvaluationError("exact binding and journal projection required")
    retained = _hash(expected_head_sha256)
    body = decode_object(canonical_object(snapshot))
    genesis = hash_bytes(canonical_object({"schema": "gdr.synthetic.evaluation-genesis.v1",
                                          "binding": binding.to_dict()}))
    head, _, attempts = _replay_records(body.get("records"), binding, genesis)
    if head != retained:
        raise EvaluationError("projection differs from exact retained evaluation head")
    expected = _summary(binding, genesis, head, body["records"], attempts)
    if canonical_object(body) != canonical_object(expected):
        raise EvaluationError("journal projection differs from complete replay")
    return expected


class ReceiptJournal:
    """Candidate-specific append-only local receipts, not a permission store."""

    def __init__(self, directory: Path, binding: CandidateBinding, expected_head: str):
        if type(binding) is not CandidateBinding:
            raise EvaluationError("exact synthetic candidate binding required")
        binding.__post_init__()
        self.directory = _directory(Path(directory))
        self.binding = binding
        self.genesis_bytes = canonical_object({"schema": "gdr.synthetic.evaluation-genesis.v1",
                                               "binding": binding.to_dict()})
        self.genesis_sha256 = hash_bytes(self.genesis_bytes)
        self._head = _hash(expected_head)

    @classmethod
    def create(cls, directory: Path, binding: CandidateBinding):
        if type(binding) is not CandidateBinding:
            raise EvaluationError("exact synthetic candidate binding required")
        genesis = canonical_object({"schema": "gdr.synthetic.evaluation-genesis.v1",
                                    "binding": binding.to_dict()})
        value = cls(directory, binding, hash_bytes(genesis))
        _publish(value.directory, _GENESIS, value.genesis_bytes)
        value._head = value._load(value._head)[0]
        return value

    @classmethod
    def open(cls, directory: Path, *, binding: CandidateBinding, expected_head: str):
        value = cls(directory, binding, expected_head)
        value._head = value._load(expected_head)[0]
        return value

    def _load(self, expected_head: str) -> tuple[str, list[dict], list[dict]]:
        _hash(expected_head)
        if (type(self.binding) is not CandidateBinding
                or canonical_object({"schema": "gdr.synthetic.evaluation-genesis.v1",
                                     "binding": self.binding.to_dict()}) != self.genesis_bytes):
            raise EvaluationError("journal binding changed after construction")
        directory = _directory(self.directory)
        if _read(directory / _GENESIS) != self.genesis_bytes:
            raise EvaluationError("journal differs from retained candidate binding")
        numbers = []
        for count, path in enumerate(directory.iterdir(), 1):
            if count > 3 * MAX_RECORDS + 32:
                raise EvaluationError("evaluation directory exceeds bound")
            match = _RECORD.fullmatch(path.name)
            if match:
                numbers.append(int(match[1]))
            elif path.name == _GENESIS or re.fullmatch(r"\.gdr-journal-.*\.staging", path.name):
                continue
            else:
                raise EvaluationError("unexpected evaluation directory entry")
        if len(numbers) > MAX_RECORDS or sorted(numbers) != list(range(1, len(numbers) + 1)):
            raise EvaluationError("missing/invalid evaluation sequence")
        records = [decode_object(_read(directory / f"evaluation-{sequence:06d}.json"))
                   for sequence in range(1, len(numbers) + 1)]
        head, heads, attempts = _replay_records(records, self.binding, self.genesis_sha256)
        if expected_head not in heads:
            raise EvaluationError("retained evaluation head missing: truncation or changed history")
        return head, records, attempts

    def _append(self, expected_head: str, operation: str, payload: dict) -> dict:
        # Canonical decoding snapshots the supplied projection before I/O.
        payload = decode_object(canonical_object(payload))
        head, records, attempts = self._load(expected_head)
        for sequence, old in enumerate(records, 1):
            if (old["operation"] == operation
                    and old["payload"].get("attempt_id") == payload.get("attempt_id")):
                if old["payload"] != payload:
                    raise JournalConflict("conflicting evaluation observation replay")
                _publish(self.directory, f"evaluation-{sequence:06d}.json", canonical_object(old))
                self._head = head
                return self.to_dict()
        if head != expected_head:
            raise JournalConflict("stale evaluation head; reload before append")
        _apply(attempts, self.binding, operation, payload)
        if len(records) >= MAX_RECORDS:
            raise EvaluationError("evaluation record capacity exhausted")
        record = {"schema": "gdr.synthetic.evaluation-record.v1", "sequence": len(records) + 1,
                  "previous_sha256": head, "binding_sha256": self.binding.sha256,
                  "operation": operation, "payload": payload}
        raw = canonical_object(record)
        _publish(self.directory, f"evaluation-{len(records) + 1:06d}.json", raw)
        self._head = hash_bytes(raw)
        return self.to_dict()

    def record_intent(self, *, expected_head: str, attempt_id: str, at: str) -> dict:
        return self._append(expected_head, "intent", {"attempt_id": attempt_id, "at": at})

    def record_compile(self, *, expected_head: str, receipt: CompileReceipt) -> dict:
        if type(receipt) is not CompileReceipt:
            raise EvaluationError("exact compile receipt required")
        return self._append(expected_head, "compile", receipt.to_dict())

    def record_run(self, *, expected_head: str, receipt: RunReceipt) -> dict:
        if type(receipt) is not RunReceipt:
            raise EvaluationError("exact run receipt required")
        return self._append(expected_head, "run", receipt.to_dict())

    def record_failure(self, *, expected_head: str, attempt_id: str, at: str, output_sha256: str) -> dict:
        return self._append(expected_head, "failure", {"attempt_id": attempt_id, "at": at,
                                                       "output_sha256": output_sha256})

    def record_ambiguous(self, *, expected_head: str, attempt_id: str, at: str, output_sha256: str) -> dict:
        return self._append(expected_head, "ambiguous", {"attempt_id": attempt_id, "at": at,
                                                         "output_sha256": output_sha256})

    @property
    def head_sha256(self) -> str:
        return self._load(self._head)[0]

    def to_dict(self) -> dict:
        head, records, attempts = self._load(self._head)
        return _summary(self.binding, self.genesis_sha256, head, records, attempts)


def _snapshot_files(files: dict[str, bytes]) -> dict[str, bytes]:
    if type(files) is not dict or len(files) > MAX_CLOUD_FILES:
        raise EvaluationError("bounded complete Python file map required")
    try:
        snapshot = dict(files)
    except RuntimeError as exc:
        raise EvaluationError("file map changed during snapshot") from exc
    if len(snapshot) > MAX_CLOUD_FILES:
        raise EvaluationError("file map exceeds bound")
    for name, raw in snapshot.items():
        if (type(name) is not str or len(name) > 256 or not _PYTHON_PATH.fullmatch(name)
                or any(part in ("", ".", "..") for part in name.split("/"))
                or type(raw) is not bytes or len(raw) >= MAX_CLOUD_FILE_BYTES):
            raise EvaluationError("safe bounded immutable Python file bytes required")
    return snapshot


def project_file_inventory(files: dict[str, bytes]) -> dict:
    snapshot = _snapshot_files(files)
    return {name: {"bytes": len(raw), "sha256": hash_bytes(raw)} for name, raw in sorted(snapshot.items())}


def compare_cloud_source(expected_files: dict[str, bytes], returned_files: dict[str, bytes], *,
                         expected_project_sha256: str, expected_returned_sha256: str,
                         verify_current: bool = False) -> dict:
    expected, returned = _snapshot_files(expected_files), _snapshot_files(returned_files)
    if not expected or "main.py" not in expected or type(verify_current) is not bool:
        raise EvaluationError("complete retained local root project required")
    from research.guidance_revision_drift.qc_project import QCProjectError, _bounded_files
    try:
        _bounded_files(expected)
    except QCProjectError as exc:
        raise EvaluationError("complete retained Python carrier inventory required") from exc
    before, after = project_file_inventory(expected), project_file_inventory(returned)
    if (hash_payload(before) != _hash(expected_project_sha256)
            or hash_payload(after) != _hash(expected_returned_sha256)):
        raise EvaluationError("cloud/local map differs from caller-retained identity")
    if verify_current:
        from research.guidance_revision_drift.qc_project import verify_qc_project
        verify_qc_project(expected, expected_sha256=expected_project_sha256)
    changes = []
    for name in sorted(set(before) | set(after)):
        status = ("extra" if name not in before else "missing" if name not in after else
                  "changed" if expected[name] != returned[name] else "unchanged")
        changes.append({"name": name, "status": status, "expected": before.get(name), "returned": after.get(name)})
    changed = any(row["status"] != "unchanged" for row in changes)
    return {"schema": "gdr.synthetic.cloud-source-comparison.v1",
            "status": "quarantined_pending_manual_review" if changed else "byte_identical_observation_only",
            "expected_project_sha256": expected_project_sha256,
            "returned_project_sha256": expected_returned_sha256,
            "expected_files": before, "returned_files": after, "changes": changes,
            "change_manifest_sha256": hash_payload(changes), "quarantined": changed,
            "current_local_content_checked": verify_current,
            "external_provenance_verified": False, "automatic_port_allowed": False,
            "economic_acceptance": False, "qc_launch_allowed": False, "market_evidence": False}
