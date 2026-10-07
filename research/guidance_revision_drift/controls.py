"""Synthetic run lineage and unconditional external-access refusals.

These are consistency records, not credentials or research authorizations.
Changing a hash cannot turn a fixture run into empirical evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.guidance_revision_drift.contracts import CANDIDATE_SHA256, _decode


class ResearchControlError(ValueError):
    """Invalid fixture lineage or prohibited external activity."""


def _digest(value: object) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ResearchControlError("expected an exact lowercase SHA-256")
    return value


def _run_id(value: object) -> str:
    if type(value) is not str or re.fullmatch(r"fixture-[a-z0-9-]{1,48}", value) is None:
        raise ResearchControlError("run ID must name a bounded synthetic fixture")
    return value


@dataclass(frozen=True, slots=True)
class FixtureEpoch:
    source_sha256: str
    calendar_sha256: str
    code_sha256: str
    candidate_sha256: str = CANDIDATE_SHA256

    def __post_init__(self) -> None:
        _digest(self.source_sha256)
        _digest(self.calendar_sha256)
        _digest(self.code_sha256)
        _digest(self.candidate_sha256)
        if self.candidate_sha256 != CANDIDATE_SHA256:
            raise ResearchControlError("unknown candidate epoch")

    def to_dict(self) -> dict:
        self.__post_init__()
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_dict())


@dataclass(frozen=True, slots=True)
class FixtureReceipt:
    sequence: int
    previous_sha256: str
    epoch_sha256: str
    run_id: str
    kind: str
    status: str
    input_sha256: str
    output_sha256: str | None

    def __post_init__(self) -> None:
        if type(self.sequence) is not int or not 1 <= self.sequence <= 64:
            raise ResearchControlError("receipt sequence outside bounded ledger")
        for item in (self.previous_sha256, self.epoch_sha256, self.input_sha256):
            _digest(item)
        _run_id(self.run_id)
        if type(self.kind) is not str or self.kind not in ("base", "stress"):
            raise ResearchControlError("fixture kind must be base or stress")
        if type(self.status) is not str or self.status not in ("started", "completed", "failed"):
            raise ResearchControlError("unknown fixture disposition")
        if self.status == "started":
            if self.output_sha256 is not None:
                raise ResearchControlError("start cannot contain an outcome")
        else:
            _digest(self.output_sha256)

    def to_dict(self) -> dict:
        self.__post_init__()
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_dict())


@dataclass(frozen=True, slots=True)
class FixtureLedger:
    epoch: FixtureEpoch
    receipts: tuple[FixtureReceipt, ...] = ()

    def __post_init__(self) -> None:
        if type(self.epoch) is not FixtureEpoch:
            raise ResearchControlError("exact fixture epoch required")
        if type(self.receipts) is not tuple or len(self.receipts) > 64:
            raise ResearchControlError("immutable bounded receipt tuple required")
        prior = self.epoch.sha256
        runs: dict[str, FixtureReceipt] = {}
        for sequence, receipt in enumerate(self.receipts, 1):
            if type(receipt) is not FixtureReceipt:
                raise ResearchControlError("exact fixture receipt required")
            receipt.__post_init__()
            if (receipt.sequence != sequence or receipt.previous_sha256 != prior
                    or receipt.epoch_sha256 != self.epoch.sha256):
                raise ResearchControlError("broken receipt chain or changed evidence epoch")
            previous = runs.get(receipt.run_id)
            if receipt.status == "started":
                if previous is not None:
                    raise ResearchControlError("a fixture run ID cannot be reused")
            elif (previous is None or previous.status != "started"
                  or previous.kind != receipt.kind or previous.input_sha256 != receipt.input_sha256):
                raise ResearchControlError("terminal receipt must match one unclosed start")
            runs[receipt.run_id] = receipt
            prior = receipt.sha256

    def _append(self, run_id: str, kind: str, status: str, input_sha256: str,
                output_sha256: str | None) -> FixtureLedger:
        self.__post_init__()
        receipt = FixtureReceipt(
            len(self.receipts) + 1,
            self.receipts[-1].sha256 if self.receipts else self.epoch.sha256,
            self.epoch.sha256, run_id, kind, status, input_sha256, output_sha256,
        )
        return FixtureLedger(self.epoch, self.receipts + (receipt,))

    def start(self, run_id: str, kind: str, input_sha256: str) -> FixtureLedger:
        return self._append(run_id, kind, "started", input_sha256, None)

    def finish(self, run_id: str, *, output_sha256: str, failed: bool = False) -> FixtureLedger:
        self.__post_init__()
        if type(failed) is not bool:
            raise ResearchControlError("failed must be a boolean")
        _run_id(run_id)
        matches = [r for r in self.receipts if r.run_id == run_id]
        if not matches:
            raise ResearchControlError("run was not started")
        previous = matches[-1]
        return self._append(run_id, previous.kind, "failed" if failed else "completed",
                            previous.input_sha256, output_sha256)

    def to_dict(self) -> dict:
        self.__post_init__()
        return {
            "schema": "gdr.synthetic.look-ledger.v1", "epoch": self.epoch.to_dict(),
            "receipts": [r.to_dict() for r in self.receipts],
            "empirical_looks": 0, "qc_attempts": 0, "point_in_time_data": False,
        }

    def to_bytes(self) -> bytes:
        return canonical_json(self.to_dict()).encode("utf-8")

    @classmethod
    def from_bytes(cls, raw: bytes) -> FixtureLedger:
        try:
            body = _decode(raw)
            if set(body) != {"schema", "epoch", "receipts", "empirical_looks", "qc_attempts", "point_in_time_data"}:
                raise ResearchControlError("unknown or missing ledger field")
            if type(body["epoch"]) is not dict or type(body["receipts"]) is not list:
                raise ResearchControlError("invalid ledger containers")
            if any(type(r) is not dict for r in body["receipts"]):
                raise ResearchControlError("receipt must be an object")
            value = cls(FixtureEpoch(**body["epoch"]), tuple(FixtureReceipt(**r) for r in body["receipts"]))
            # Canonical comparison also distinguishes false from 0, omitted
            # defaults, schema mutations and caller-asserted authority.
            if canonical_json(body).encode("utf-8") != value.to_bytes():
                raise ResearchControlError("ledger projection differs from its contract")
            return value
        except (TypeError, ValueError, KeyError, RecursionError) as exc:
            raise ResearchControlError("invalid synthetic ledger") from exc

    @property
    def sha256(self) -> str:
        return hash_bytes(self.to_bytes())


def refuse_external_action(action: str, *, start: date | None = None, end: date | None = None) -> None:
    """There is deliberately no approved/permission override in this batch."""
    if type(action) is not str or not action or len(action) > 80:
        raise ResearchControlError("invalid requested action")
    if (start is None) != (end is None):
        raise ResearchControlError("both window endpoints are required")
    if start is not None:
        if type(start) is not date or type(end) is not date or start > end:
            raise ResearchControlError("invalid evidence window")
        if end >= date(2026, 9, 1):
            raise ResearchControlError("protected outcome dates are closed")
    raise ResearchControlError(f"{action}: external access is not authorized; synthetic fixtures only")


def qc_recovery_disposition(unsuccessful_attempts: int) -> str:
    """Explain the attempt ceiling; no return value grants launch authority."""
    if type(unsuccessful_attempts) is not int or not 0 <= unsuccessful_attempts <= 3:
        raise ResearchControlError("invalid unsuccessful-attempt count")
    return ("stop_notify_owner_then_Mia_if_accessible" if unsuccessful_attempts == 3
            else "still_requires_separate_launch_authority")
