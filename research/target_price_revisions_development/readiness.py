"""Pure synthetic pre-backtest contracts, never evidence admission or execution.

This software candidate is not actual TPR-D3 admission or backtest readiness.
An inventory hash/fixture label cannot prove rights, review or public timing.
Append-only transitions protect the supplied history and expected checkpoint;
without durable external custody they do not prove rollback/fork resistance.
No file, provider, outcome, engine, QuantConnect or operator path exists here.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any


D0_PLAN_SHA256 = "15e0b00978d4060ae3d6b827474e320df2003c9ceee529c8a8436b31570b7bcb"
D0_REPORT_SHA256 = "fbe99ce620689c61052330a220b9f989b29a8ea732a45204d88b02e6f5648148"
AUTHORITY_KEYS = ("additional_data", "provider", "retained_rows", "outcomes", "qc",
                  "broker", "trading", "point_in_time", "canonical_admission", "d0_audit_renewed")
REQUIRED_RISKS = ("synthetic-not-evidence-or-admission", "zero-outcome-access", "spent-d0-not-renewable")
REQUIREMENTS = ("reviewed_candidate", "target_source_rights", "derived_processing_rights",
                "price_source_rights", "permanent_identity", "public_version_capture_clocks",
                "horizon_currency_share_basis", "cost_inputs", "reviewed_structural_manifests",
                "look_authority", "order_engine_completion", "exact_outcome_access_scope")
QC_REQUIREMENTS = ("qc_transfer_rights", "exact_qc_processing_launch_scope")
_TARGETS = ("synthetic-local-order-based", "synthetic-qc-order-based")
_LINEAGE = {"candidate_sha256", "code_sha256", "data_sha256", "config_sha256", "fold_sha256"}
_SPEC_KEYS = {"schema", "run_id", "target", "created_at_utc", "expires_at_utc", "lineage",
              "plan_sha256", "d0_report_sha256", "synthetic_outcome_window", "accepted_risks", "authority",
              "d0_audit", "evaluation_policy"}
_GENESIS = "0" * 64
_MAX_RECORDS = 128
_MAX_BYTES = 32768
_MAX_LEDGER_BYTES = 1048576


class ReadinessError(ValueError):
    """Closed-contract refusal; fixed messages never expose caller content."""


@dataclass(frozen=True)
class FrozenFixtureRunSpec:
    payload: bytes
    sha256: str


@dataclass(frozen=True)
class FixtureReceipt:
    payload: bytes
    sha256: str


@dataclass(frozen=True)
class RequirementDisposition:
    requirement_id: str
    status: str
    fixture_ids: tuple[str, ...]


@dataclass(frozen=True)
class FixtureReadiness:
    run_spec_sha256: str
    requirements: tuple[RequirementDisposition, ...]
    blockers: tuple[str, ...]
    mia_recovery_required: bool
    payload: bytes
    sha256: str
    real_backtest_ready: bool = False
    independent_review_required: bool = True
    actual_qc_attempts: int = 0
    actual_outcome_reads: int = 0
    authority: tuple[tuple[str, bool], ...] = tuple((key, False) for key in AUTHORITY_KEYS)
    mode: str = "synthetic-contract-only-not-TPR-D3-admission"


def _keys(value: Any, expected: set[str], label: str) -> None:
    if (type(value) is not dict or len(value) != len(expected)
            or any(type(key) is not str for key in value) or set(value) != expected):
        raise ReadinessError("invalid " + label + " schema")


def _hash(value: Any) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ReadinessError("invalid content identity")
    return value


def _id(value: Any) -> str:
    if type(value) is not str or len(value) > 128 or re.fullmatch(r"SYNTHETIC-[A-Z0-9][A-Z0-9_-]*", value) is None:
        raise ReadinessError("invalid synthetic identity")
    return value


def _clock(value: Any) -> datetime:
    if type(value) is not str or len(value) > 64:
        raise ReadinessError("invalid synthetic clock")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError
        return result.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise ReadinessError("invalid synthetic clock") from None


def _date(value: Any) -> date:
    if type(value) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise ReadinessError("invalid synthetic window")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ReadinessError("invalid synthetic window") from None


def _canonical(value: Any) -> bytes:
    def check(item: Any, depth: int = 0) -> None:
        if depth > 8:
            raise ReadinessError("artifact nesting exceeds bound")
        if item is None or type(item) is bool:
            return
        if type(item) is str and len(item) <= 256:
            return
        if type(item) is int and item.bit_length() <= 64:
            return
        if type(item) is list and len(item) <= 128:
            for child in item:
                check(child, depth + 1)
            return
        if (type(item) is dict and len(item) <= 128
                and all(type(key) is str and len(key) <= 64 for key in item)):
            for child in item.values():
                check(child, depth + 1)
            return
        raise ReadinessError("artifact requires bounded JSON primitives")
    check(value)
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                          allow_nan=False) + "\n").encode("utf-8")
    if len(payload) > _MAX_BYTES:
        raise ReadinessError("artifact exceeds byte bound")
    return payload


def _parse(payload: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ReadinessError("duplicate artifact key")
            result[key] = value
        return result
    def refuse_number(_value):
        raise ReadinessError("float or nonfinite artifact number")
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=unique,
                           parse_float=refuse_number, parse_constant=refuse_number)
        if type(value) is not dict or _canonical(value) != payload:
            raise ReadinessError("artifact is not canonical LF JSON")
        return value
    except (UnicodeError, ValueError, RecursionError):
        raise ReadinessError("invalid canonical artifact") from None


def _artifact_body(artifact: Any, cls: type) -> dict:
    if type(artifact) is not cls or type(artifact.payload) is not bytes or len(artifact.payload) > _MAX_BYTES:
        raise ReadinessError("invalid frozen artifact")
    identity = _hash(artifact.sha256)
    if hashlib.sha256(artifact.payload).hexdigest() != identity:
        raise ReadinessError("artifact digest mismatch")
    return _parse(artifact.payload)


def _validate_spec(body: dict) -> None:
    _keys(body, _SPEC_KEYS, "run spec")
    _id(body["run_id"])
    if type(body["schema"]) is not str or body["schema"] != "tpr-synthetic-run-spec-v1":
        raise ReadinessError("invalid run spec schema")
    if type(body["target"]) is not str or body["target"] not in _TARGETS:
        raise ReadinessError("invalid synthetic evaluation target")
    if _clock(body["expires_at_utc"]) <= _clock(body["created_at_utc"]):
        raise ReadinessError("invalid run spec validity window")
    _keys(body["lineage"], _LINEAGE, "lineage")
    for value in body["lineage"].values():
        _hash(value)
    if _hash(body["plan_sha256"]) != D0_PLAN_SHA256:
        raise ReadinessError("run spec does not bind the frozen D0 plan")
    if _hash(body["d0_report_sha256"]) != D0_REPORT_SHA256:
        raise ReadinessError("run spec does not bind the frozen D0 aggregate")
    _keys(body["authority"], set(AUTHORITY_KEYS), "authority")
    if any(value is not False for value in body["authority"].values()):
        raise ReadinessError("synthetic scope cannot grant authority")
    if type(body["d0_audit"]) is not str or body["d0_audit"] != "spent-not-renewable":
        raise ReadinessError("spent audit cannot be renewed")
    risks = body["accepted_risks"]
    if type(risks) is not list or any(type(item) is not str for item in risks) or tuple(risks) != REQUIRED_RISKS:
        raise ReadinessError("run spec risk contract differs")
    policy = body["evaluation_policy"]
    _keys(policy, {"mode", "max_qc_attempts", "after_three_unsuccessful"}, "evaluation policy")
    if (type(policy["mode"]) is not str or policy["mode"] != "order-based"
            or type(policy["max_qc_attempts"]) is not int or policy["max_qc_attempts"] != 3
            or type(policy["after_three_unsuccessful"]) is not str
            or policy["after_three_unsuccessful"] != "mia-recovery-required"):
        raise ReadinessError("evaluation policy differs from frozen fixture contract")
    window = body["synthetic_outcome_window"]
    _keys(window, {"start", "end"}, "synthetic window")
    start, end = _date(window["start"]), _date(window["end"])
    if start > end or (end - start).days > 3660:
        raise ReadinessError("invalid synthetic window")
    if start <= date(2029, 8, 31) and end >= date(2027, 9, 1):
        raise ReadinessError("reserved shared holdout remains unavailable")


def freeze_fixture_run_spec(raw: Any) -> FrozenFixtureRunSpec:
    """Freeze bounded lineage/zero-authority metadata, not an execution permit."""
    _validate_spec(raw)
    payload = _canonical(raw)
    return FrozenFixtureRunSpec(payload, hashlib.sha256(payload).hexdigest())


def _spec_body(spec: Any) -> dict:
    body = _artifact_body(spec, FrozenFixtureRunSpec)
    _validate_spec(body)
    return body


def _replay(ledger: Any) -> tuple[dict, dict, str, datetime | None]:
    if type(ledger) is not tuple or len(ledger) > _MAX_RECORDS:
        raise ReadinessError("invalid bounded fixture ledger")
    previous, last_clock, byte_count = _GENESIS, None, 0
    attempts, counts = {}, {}
    common = {"schema", "kind", "sequence", "previous_sha256", "attempt_id", "at_utc"}
    for sequence, receipt in enumerate(ledger, 1):
        body = _artifact_body(receipt, FixtureReceipt)
        byte_count += len(receipt.payload)
        if byte_count > _MAX_LEDGER_BYTES:
            raise ReadinessError("fixture ledger exceeds byte bound")
        kind = body.get("kind")
        if type(kind) is not str or kind not in ("reservation", "terminal"):
            raise ReadinessError("invalid receipt kind")
        extra = ({"run_spec", "run_spec_sha256", "attempt_ordinal"} if kind == "reservation"
                 else {"reservation_sha256", "status"})
        _keys(body, common | extra, "receipt")
        if type(body["schema"]) is not str or body["schema"] != "tpr-synthetic-look-receipt-v1":
            raise ReadinessError("invalid receipt schema")
        if type(body["sequence"]) is not int or body["sequence"] != sequence:
            raise ReadinessError("receipt sequence is not contiguous")
        if _hash(body["previous_sha256"]) != previous:
            raise ReadinessError("receipt history chain differs")
        clock = _clock(body["at_utc"])
        if body["at_utc"] != clock.isoformat() or (last_clock is not None and clock < last_clock):
            raise ReadinessError("receipt clock is not monotone")
        attempt = _id(body["attempt_id"])
        if kind == "reservation":
            if attempt in attempts:
                raise ReadinessError("attempt identity was already reserved")
            run = body["run_spec"]
            _validate_spec(run)
            if _hash(body["run_spec_sha256"]) != hashlib.sha256(_canonical(run)).hexdigest():
                raise ReadinessError("reservation run-spec lineage differs")
            if not _clock(run["created_at_utc"]) <= clock <= _clock(run["expires_at_utc"]):
                raise ReadinessError("run spec is not current for reservation")
            candidate = run["lineage"]["candidate_sha256"]
            if any(item["candidate"] == candidate and item["status"] is None for item in attempts.values()):
                raise ReadinessError("candidate has a pending reservation")
            key = (candidate, run["target"])
            ordinal = counts.get(key, 0) + 1
            if type(body["attempt_ordinal"]) is not int or body["attempt_ordinal"] != ordinal:
                raise ReadinessError("candidate attempt ordinal differs")
            if run["target"] == "synthetic-qc-order-based" and ordinal > 3:
                raise ReadinessError("three synthetic QC attempts exhausted")
            counts[key] = ordinal
            attempts[attempt] = {"candidate": candidate, "target": run["target"], "status": None,
                                 "reservation_sha256": receipt.sha256}
            pending = sum(item["status"] is None for item in attempts.values())
            if sequence + pending > _MAX_RECORDS:
                raise ReadinessError("fixture ledger lacks terminal capacity")
        else:
            if attempt not in attempts:
                raise ReadinessError("terminal has no earlier reservation")
            state = attempts[attempt]
            if state["status"] is not None:
                raise ReadinessError("terminal cannot overwrite a prior terminal")
            if _hash(body["reservation_sha256"]) != state["reservation_sha256"]:
                raise ReadinessError("terminal reservation binding differs")
            status = body["status"]
            if type(status) is not str or status not in ("completed", "failed", "interrupted"):
                raise ReadinessError("invalid synthetic terminal status")
            state["status"] = status
        previous, last_clock = receipt.sha256, clock
    return attempts, counts, previous, last_clock


def ledger_head(ledger: tuple[FixtureReceipt, ...]) -> str:
    return _replay(ledger)[2]


def load_fixture_ledger(ledger: Any, *, expected_head_sha256: str) -> tuple[FixtureReceipt, ...]:
    """Validate a supplied immutable history against its caller-held checkpoint."""
    if _replay(ledger)[2] != _hash(expected_head_sha256):
        raise ReadinessError("fixture ledger checkpoint differs")
    return ledger


def _append(ledger: tuple, body: dict) -> tuple[FixtureReceipt, ...]:
    payload = _canonical(body)
    result = ledger + (FixtureReceipt(payload, hashlib.sha256(payload).hexdigest()),)
    _replay(result)
    return result


def reserve_fixture_attempt(spec: FrozenFixtureRunSpec, ledger: tuple, *, attempt_id: str,
                            at_utc: str, expected_head_sha256: str) -> tuple[FixtureReceipt, ...]:
    """Append a synthetic reservation before a pretend attempt; no look is spent."""
    run = _spec_body(spec)
    load_fixture_ledger(ledger, expected_head_sha256=expected_head_sha256)
    _, counts, previous, _ = _replay(ledger)
    key = (run["lineage"]["candidate_sha256"], run["target"])
    return _append(ledger, {"schema": "tpr-synthetic-look-receipt-v1", "kind": "reservation",
                           "sequence": len(ledger) + 1, "previous_sha256": previous,
                           "attempt_id": _id(attempt_id), "at_utc": _clock(at_utc).isoformat(),
                           "run_spec": run, "run_spec_sha256": spec.sha256,
                           "attempt_ordinal": counts.get(key, 0) + 1})


def close_fixture_attempt(ledger: tuple, *, attempt_id: str, status: str, at_utc: str,
                          expected_head_sha256: str) -> tuple[FixtureReceipt, ...]:
    """Append, never replace, a synthetic terminal record after its reservation."""
    load_fixture_ledger(ledger, expected_head_sha256=expected_head_sha256)
    attempts, _, previous, _ = _replay(ledger)
    attempt = _id(attempt_id)
    if attempt not in attempts:
        raise ReadinessError("terminal has no earlier reservation")
    return _append(ledger, {"schema": "tpr-synthetic-look-receipt-v1", "kind": "terminal",
                           "sequence": len(ledger) + 1, "previous_sha256": previous,
                           "attempt_id": attempt, "at_utc": _clock(at_utc).isoformat(),
                           "reservation_sha256": attempts[attempt]["reservation_sha256"], "status": status})


def evaluate_fixture_readiness(spec: FrozenFixtureRunSpec, inventory: Any, ledger: tuple = (), *,
                               as_of_utc: str) -> FixtureReadiness:
    """Inventory software prerequisites; synthetic claims never admit real input."""
    run = _spec_body(spec)
    now = _clock(as_of_utc)
    attempts, _, head, last_clock = _replay(ledger)
    if last_clock is not None and last_clock > now:
        raise ReadinessError("fixture ledger is later than assessment clock")
    required = REQUIREMENTS + (QC_REQUIREMENTS if run["target"] == "synthetic-qc-order-based" else ())
    if type(inventory) not in (list, tuple) or len(inventory) > len(required):
        raise ReadinessError("invalid bounded synthetic inventory")
    fixtures = {}
    for item in inventory:
        _keys(item, {"requirement_id", "fixture_id", "fixture_sha256"}, "inventory")
        requirement = item["requirement_id"]
        if type(requirement) is not str or requirement not in required or requirement in fixtures:
            raise ReadinessError("invalid synthetic inventory requirement")
        fixtures[requirement] = (_id(item["fixture_id"]), _hash(item["fixture_sha256"]))
    dispositions = tuple(RequirementDisposition(item, "synthetic-not-admission" if item in fixtures else "missing",
                                               (fixtures[item][0],) if item in fixtures else ()) for item in required)
    blockers = tuple(("synthetic_not_admitted:" if item in fixtures else "missing:") + item for item in required)
    blockers += ("owner_scope_for_data_outcomes_qc_missing", "spent_d0_audit_not_renewable",
                 "independent_software_review_required")
    if not _clock(run["created_at_utc"]) <= now <= _clock(run["expires_at_utc"]):
        blockers += ("run_spec_not_current",)
    candidate = run["lineage"]["candidate_sha256"]
    qc = tuple(item for item in attempts.values()
               if item["candidate"] == candidate and item["target"] == "synthetic-qc-order-based")
    mia = len(qc) == 3 and all(item["status"] in ("failed", "interrupted") for item in qc)
    if mia:
        blockers += ("synthetic_qc_attempts_exhausted_mia_recovery_required",)
    # Inventory identities are caller-supplied SYNTHETIC claims, never evidence
    # admission. Retain them so the dossier binds its exact declared context.
    bound_inventory = [{"requirement_id": item, "fixture_id": fixtures[item][0],
                        "fixture_sha256": fixtures[item][1]} for item in required if item in fixtures]
    dossier = {
        "schema": "tpr-synthetic-readiness-dossier-v1", "run_spec_sha256": spec.sha256,
        "as_of_utc": now.isoformat(), "ledger_head_sha256": head, "inventory": bound_inventory,
        "requirements": [{"requirement_id": item.requirement_id, "status": item.status,
                          "fixture_ids": list(item.fixture_ids)} for item in dispositions],
        "blockers": list(blockers), "mia_recovery_required": mia,
        "real_backtest_ready": False, "independent_review_required": True,
        "actual_qc_attempts": 0, "actual_outcome_reads": 0,
        "authority": {key: False for key in AUTHORITY_KEYS},
        "mode": "synthetic-contract-only-not-TPR-D3-admission",
    }
    payload = _canonical(dossier)
    return FixtureReadiness(spec.sha256, dispositions, blockers, mia, payload,
                            hashlib.sha256(payload).hexdigest())
