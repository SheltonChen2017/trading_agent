"""Passive owner-cycle custody for the fixed base 372-frame synthetic run.

The caller retains one cycle and latest acknowledged head outside this local
directory. Review metadata and corrected packaging do not reset its failure
budget. This is not an authorization store or platform client. Losing both
history and retained anchors, or deliberately inventing a replacement owner
cycle, cannot be detected here; cross-directory/rollback custody remains the
owner's obligation. Event timestamps are supplied observations, not external
proof, and are never rewritten to accommodate later retrieval.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from data.hashing import hash_bytes, hash_payload
from research.guidance_revision_drift.contracts import CANDIDATE_SHA256
from research.guidance_revision_drift.evaluation import (
    CandidateBinding, CompileReceipt, RunReceipt, EvaluationError,
    FIXTURE_SHA256, _clock, _fields, _hash, _identifier, _receipt,
)
from research.guidance_revision_drift.persistence import (
    JournalConflict, canonical_object, decode_object, _directory, _publish, _read,
)


MAX_CYCLE_RECORDS = 32
_GENESIS = "evaluation-cycle-genesis.json"
_RECORD = re.compile(r"evaluation-cycle-([0-9]{6})\.json\Z")
_SCOPE = "fixed-base-372-synthetic-order-integration"


def content_identity(binding: CandidateBinding) -> str:
    """Stable byte-content identity, distinct from the complete review binding."""
    if type(binding) is not CandidateBinding:
        raise EvaluationError("exact candidate binding required")
    body = binding.to_dict()
    return hash_payload({"schema": "gdr.synthetic.evaluation-content.v1", **{
        name: body[name] for name in ("candidate_sha256", "fixture_sha256", "source_sha256",
                                     "project_sha256", "bundle_sha256")}})


@dataclass(frozen=True, slots=True)
class OwnerCycle:
    """Owner-supplied continuity anchor, never a claim of human authorization."""

    cycle_id: str
    candidate_sha256: str = CANDIDATE_SHA256
    fixture_sha256: str = FIXTURE_SHA256
    fixture_mode: str = "base"

    def __post_init__(self):
        _identifier(self.cycle_id)
        if (self.candidate_sha256 != CANDIDATE_SHA256 or self.fixture_sha256 != FIXTURE_SHA256
                or type(self.fixture_mode) is not str or self.fixture_mode != "base"):
            raise EvaluationError("owner cycle cannot replace the fixed base candidate/fixture")

    def to_dict(self) -> dict:
        self.__post_init__()
        return {"cycle_id": self.cycle_id, "candidate_sha256": self.candidate_sha256,
                "fixture_sha256": self.fixture_sha256, "fixture_mode": self.fixture_mode,
                "scope": _SCOPE, "max_unsuccessful_attempts": 3}

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_dict())

    @property
    def genesis_sha256(self) -> str:
        return hash_bytes(_genesis(self))


def _genesis(cycle: OwnerCycle) -> bytes:
    if type(cycle) is not OwnerCycle:
        raise EvaluationError("exact owner cycle required")
    return canonical_object({"schema": "gdr.synthetic.evaluation-cycle-genesis.v1",
                             "cycle": cycle.to_dict()})


def _event_observed(event_at: str, observed_at: str) -> None:
    if _clock(event_at) > _clock(observed_at):
        raise EvaluationError("platform event occurs after its observation")


def _apply(attempts: list[dict], operation: str, payload: dict, observed_at: str,
           previous_observed_at: str | None) -> None:
    observed = _clock(observed_at)
    if previous_observed_at is not None and observed < _clock(previous_observed_at):
        raise EvaluationError("retrieval observation clock regressed")
    if operation == "intent":
        _fields(payload, {"attempt_id", "at", "binding", "binding_sha256", "content_sha256"})
        _identifier(payload["attempt_id"], attempt=True)
        binding = _receipt(payload["binding"], CandidateBinding)
        if (payload["binding_sha256"] != binding.sha256
                or payload["content_sha256"] != content_identity(binding)):
            raise EvaluationError("intent differs from exact content/review binding")
        _event_observed(payload["at"], observed_at)
        if any(row["status"] != "failed" for row in attempts):
            raise EvaluationError("unresolved/completed cycle blocks another intent")
        if len(attempts) >= 3:
            raise EvaluationError("maximum three unsuccessful owner-cycle attempts reached")
        if any(row["attempt_id"] == payload["attempt_id"] for row in attempts):
            raise EvaluationError("attempt identity cannot be reused")
        if previous_observed_at is not None and _clock(payload["at"]) < _clock(previous_observed_at):
            raise EvaluationError("new intent precedes known prior observation")
        attempts.append({"attempt_id": payload["attempt_id"], "intent_at": payload["at"],
                         "intent_observed_at": observed_at, "binding": binding.to_dict(),
                         "binding_sha256": binding.sha256, "content_sha256": content_identity(binding),
                         "status": "pending", "compile": None, "compile_observed_at": None,
                         "run": None, "run_observed_at": None, "failure": None, "ambiguity": None,
                         "terminal_event_at": None, "terminal_observed_at": None})
        return
    if type(payload) is not dict or "attempt_id" not in payload:
        raise EvaluationError("attempt observation required")
    _identifier(payload["attempt_id"], attempt=True)
    matches = [row for row in attempts if row["attempt_id"] == payload["attempt_id"]]
    if not matches or matches[-1]["status"] in ("completed", "failed"):
        raise EvaluationError("observation requires an unresolved launch intent")
    row = matches[-1]
    if operation == "compile":
        receipt = _receipt(payload, CompileReceipt)
        if (receipt.binding_sha256 != row["binding_sha256"] or row["compile"] is not None
                or _clock(receipt.requested_at) < _clock(row["intent_at"])):
            raise EvaluationError("compile differs from exact per-intent binding/event lineage")
        _event_observed(receipt.completed_at, observed_at)
        if any(other["compile"] is not None and
               (other["compile"]["project_id"] != receipt.project_id
                or other["compile"]["compile_id"] == receipt.compile_id)
               for other in attempts if other is not row):
            raise EvaluationError("project changed or compile ID reused across owner cycle")
        row["compile"], row["compile_observed_at"] = receipt.to_dict(), observed_at
        row["status"] = "failed" if receipt.status == "compile_failed" else "compiled"
        if receipt.status == "compile_failed":
            row["terminal_event_at"], row["terminal_observed_at"] = receipt.completed_at, observed_at
    elif operation == "run":
        receipt = _receipt(payload, RunReceipt)
        compilation = row["compile"]
        if (receipt.binding_sha256 != row["binding_sha256"] or compilation is None
                or compilation["status"] != "compiled"
                or any(getattr(receipt, name) != compilation[name]
                       for name in ("project_id", "compile_id", "engine", "binding_version"))
                or _clock(receipt.started_at) < _clock(compilation["completed_at"])):
            raise EvaluationError("run differs from exact per-intent compile/event lineage")
        _event_observed(receipt.completed_at, observed_at)
        if any(other["run"] is not None and other["run"]["run_id"] == receipt.run_id
               for other in attempts if other is not row):
            raise EvaluationError("run ID reused across owner cycle")
        row["run"], row["run_observed_at"] = receipt.to_dict(), observed_at
        row["status"] = "completed" if receipt.status == "completed" else "failed"
        row["terminal_event_at"], row["terminal_observed_at"] = receipt.completed_at, observed_at
    elif operation in ("failure", "ambiguous"):
        _fields(payload, {"attempt_id", "output_sha256", "event_at"} if operation == "failure"
                else {"attempt_id", "output_sha256"})
        _hash(payload["output_sha256"])
        if operation == "failure":
            floor = row["compile"]["completed_at"] if row["compile"] else row["intent_at"]
            if _clock(payload["event_at"]) < _clock(floor):
                raise EvaluationError("terminal failure precedes attempt event lineage")
            _event_observed(payload["event_at"], observed_at)
            row["failure"] = {**payload, "observed_at": observed_at}
            row["status"] = "failed"
            row["terminal_event_at"], row["terminal_observed_at"] = payload["event_at"], observed_at
        else:
            row["ambiguity"] = {**payload, "observed_at": observed_at}
            row["status"] = "ambiguous"
    else:
        raise EvaluationError("unsupported passive owner-cycle operation")


def _replay(records: list[dict], cycle: OwnerCycle):
    if type(records) is not list or len(records) > MAX_CYCLE_RECORDS:
        raise EvaluationError("bounded complete owner-cycle records required")
    head = cycle.genesis_sha256
    heads, attempts, identities, observed_at = {head}, [], set(), None
    for sequence, record in enumerate(records, 1):
        _fields(record, {"schema", "sequence", "previous_sha256", "cycle_sha256",
                         "operation", "payload", "observed_at"})
        if (record["schema"] != "gdr.synthetic.evaluation-cycle-record.v1"
                or type(record["sequence"]) is not int or record["sequence"] != sequence
                or record["previous_sha256"] != head or record["cycle_sha256"] != cycle.sha256
                or type(record["operation"]) is not str or type(record["payload"]) is not dict):
            raise EvaluationError("broken fixed owner-cycle chain")
        identity = (record["operation"], _identifier(record["payload"].get("attempt_id"), attempt=True))
        if identity in identities:
            raise EvaluationError("reused owner-cycle observation identity")
        _apply(attempts, record["operation"], record["payload"], record["observed_at"], observed_at)
        observed_at = record["observed_at"]
        identities.add(identity)
        head = hash_bytes(canonical_object(record))
        heads.add(head)
    return head, heads, attempts, observed_at


def _summary(cycle, head, records, attempts, observed_at):
    failed = sum(row["status"] == "failed" for row in attempts)
    pending = sum(row["status"] in ("pending", "compiled", "ambiguous") for row in attempts)
    completed = any(row["status"] == "completed" for row in attempts)
    return {"schema": "gdr.synthetic.evaluation-cycle-ledger.v1", "cycle": cycle.to_dict(),
            "cycle_sha256": cycle.sha256, "genesis_sha256": cycle.genesis_sha256,
            "head_sha256": head, "last_observed_at": observed_at, "records": records,
            "attempts": attempts, "launch_intents": len(attempts), "unsuccessful_attempts": failed,
            "pending_attempts": pending, "completed_observed": completed,
            "content_identities": list(dict.fromkeys(row["content_sha256"] for row in attempts)),
            "review_bindings": list(dict.fromkeys(row["binding_sha256"] for row in attempts)),
            "next_action": ("reconcile_pending_observation" if pending else
                "stop_notify_owner_then_Mia_if_accessible" if failed == 3 else
                "completion_evidence_and_external_provenance_unverified" if completed else
                "still_requires_exact_review_and_external_authority"),
            "external_provenance_verified": False, "native_runtime_verified": False,
            "qc_launch_allowed": False, "economic_acceptance": False, "market_evidence": False}


def validate_cycle_projection(snapshot: dict, *, cycle: OwnerCycle,
                              expected_head_sha256: str) -> dict:
    """Verify the entire richer ledger; no lossy legacy-journal conversion."""
    if type(cycle) is not OwnerCycle or type(snapshot) is not dict:
        raise EvaluationError("exact cycle and complete projection required")
    retained = _hash(expected_head_sha256)
    body = decode_object(canonical_object(snapshot))
    head, _, attempts, observed_at = _replay(body.get("records"), cycle)
    if head != retained:
        raise EvaluationError("projection differs from exact retained owner-cycle head")
    expected = _summary(cycle, head, body["records"], attempts, observed_at)
    if canonical_object(body) != canonical_object(expected):
        raise EvaluationError("owner-cycle projection differs from complete replay")
    return expected


class CycleJournal:
    """Append-only local observation custody; supplied statuses grant no rights."""

    def __init__(self, directory: Path, cycle: OwnerCycle, expected_head: str):
        self.genesis_bytes = _genesis(cycle)
        self.directory, self.cycle = _directory(Path(directory)), cycle
        self._head = _hash(expected_head)

    @classmethod
    def create(cls, directory: Path, cycle: OwnerCycle, *, expected_head: str):
        # A lost directory cannot be silently replaced while the last retained
        # non-genesis head survives. No write occurs on this refusal.
        if _hash(expected_head) != hash_bytes(_genesis(cycle)):
            raise EvaluationError("creation requires the independently retained genesis head")
        value = cls(directory, cycle, expected_head)
        if (value.directory / _GENESIS).exists():
            return cls.open(directory, cycle=cycle, expected_head=expected_head)
        if next(value.directory.iterdir(), None) is not None:
            raise EvaluationError("fresh owner-cycle directory must be empty")
        _publish(value.directory, _GENESIS, value.genesis_bytes)
        value._head = value._load(expected_head)[0]
        return value

    @classmethod
    def open(cls, directory: Path, *, cycle: OwnerCycle, expected_head: str):
        value = cls(directory, cycle, expected_head)
        value._head = value._load(expected_head)[0]
        return value

    def _load(self, expected_head: str):
        _hash(expected_head)
        directory = _directory(self.directory)
        if _genesis(self.cycle) != self.genesis_bytes or _read(directory / _GENESIS) != self.genesis_bytes:
            raise EvaluationError("owner cycle/genesis changed")
        numbers = []
        for count, path in enumerate(directory.iterdir(), 1):
            if count > 3 * MAX_CYCLE_RECORDS + 32:
                raise EvaluationError("owner-cycle directory exceeds bound")
            match = _RECORD.fullmatch(path.name)
            if match:
                numbers.append(int(match[1]))
            elif path.name == _GENESIS or re.fullmatch(r"\.gdr-journal-.*\.staging", path.name):
                continue
            else:
                raise EvaluationError("unexpected owner-cycle directory entry")
        if len(numbers) > MAX_CYCLE_RECORDS or sorted(numbers) != list(range(1, len(numbers) + 1)):
            raise EvaluationError("missing/invalid owner-cycle sequence")
        records = [decode_object(_read(directory / f"evaluation-cycle-{sequence:06d}.json"))
                   for sequence in range(1, len(numbers) + 1)]
        head, heads, attempts, observed_at = _replay(records, self.cycle)
        if expected_head not in heads:
            raise EvaluationError("retained owner-cycle head missing: truncation or changed history")
        return head, records, attempts, observed_at

    def _append(self, expected_head: str, operation: str, payload: dict, observed_at: str) -> dict:
        payload = decode_object(canonical_object(payload))
        _clock(observed_at)
        head, records, attempts, previous_observed_at = self._load(expected_head)
        for sequence, old in enumerate(records, 1):
            if (old["operation"] == operation
                    and old["payload"].get("attempt_id") == payload.get("attempt_id")):
                if old["payload"] != payload or old["observed_at"] != observed_at:
                    raise JournalConflict("conflicting owner-cycle observation replay")
                _publish(self.directory, f"evaluation-cycle-{sequence:06d}.json", canonical_object(old))
                self._head = head
                return self.to_dict()
        if head != expected_head:
            raise JournalConflict("stale owner-cycle head; reload before append")
        _apply(attempts, operation, payload, observed_at, previous_observed_at)
        if len(records) >= MAX_CYCLE_RECORDS:
            raise EvaluationError("owner-cycle record capacity exhausted")
        record = {"schema": "gdr.synthetic.evaluation-cycle-record.v1", "sequence": len(records) + 1,
                  "previous_sha256": head, "cycle_sha256": self.cycle.sha256,
                  "operation": operation, "payload": payload, "observed_at": observed_at}
        raw = canonical_object(record)
        _publish(self.directory, f"evaluation-cycle-{len(records) + 1:06d}.json", raw)
        self._head = hash_bytes(raw)
        return self.to_dict()

    def record_intent(self, *, expected_head: str, attempt_id: str, binding: CandidateBinding,
                      at: str, observed_at: str) -> dict:
        identity = content_identity(binding)
        return self._append(expected_head, "intent", {"attempt_id": attempt_id, "at": at,
            "binding": binding.to_dict(), "binding_sha256": binding.sha256,
            "content_sha256": identity}, observed_at)

    def record_compile(self, *, expected_head: str, receipt: CompileReceipt, observed_at: str) -> dict:
        if type(receipt) is not CompileReceipt:
            raise EvaluationError("exact typed compile receipt required")
        return self._append(expected_head, "compile", receipt.to_dict(), observed_at)

    def record_run(self, *, expected_head: str, receipt: RunReceipt, observed_at: str) -> dict:
        if type(receipt) is not RunReceipt:
            raise EvaluationError("exact typed run receipt required")
        return self._append(expected_head, "run", receipt.to_dict(), observed_at)

    def record_failure(self, *, expected_head: str, attempt_id: str, event_at: str,
                       observed_at: str, output_sha256: str) -> dict:
        return self._append(expected_head, "failure", {"attempt_id": attempt_id,
            "event_at": event_at, "output_sha256": output_sha256}, observed_at)

    def record_ambiguous(self, *, expected_head: str, attempt_id: str,
                         observed_at: str, output_sha256: str) -> dict:
        return self._append(expected_head, "ambiguous", {"attempt_id": attempt_id,
            "output_sha256": output_sha256}, observed_at)

    @property
    def head_sha256(self) -> str:
        return self._load(self._head)[0]

    def to_dict(self) -> dict:
        head, records, attempts, observed_at = self._load(self._head)
        return _summary(self.cycle, head, records, attempts, observed_at)
