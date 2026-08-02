"""GR-0: make "complete" a measurement instead of a feeling.

Five dimensions, each scored independently and **never** averaged. An
average lets a strong dimension hide a fatal one, which is the specific
failure this report exists to prevent.

Three deviations from docs/GENERAL_READINESS_IMPLEMENTATION_PLAN.md
section 5, all because the plan predates code that now exists. They are
deliberate; see docs/GENERAL_READINESS_STATUS.md.

1.  The plan says to reuse ``assistant/readiness.py``'s ``_check()``
    shape. Three incompatible shapes now exist (readiness, operations,
    ml.evidence_operations), and readiness' is a bare ``{name, ok,
    detail}`` that cannot express the three-valued status this report
    must emit. Rather than import a private helper across modules -- the
    exact drift the 2026-08-02 audit found in eleven other helpers --
    this defines one public contract and adapts the existing formats
    into it. No existing producer is modified.

2.  Severity is decided **per dimension**, never inherited. The
    operations report labels ``environment_kill_switch`` and
    ``persistent_kill_switch`` as ``warning``; inheriting that would
    report an engaged emergency stop as merely "degraded". Every
    execution-safety check is mandatory here regardless of its source
    label.

3.  The plan says strategy readiness is blocked because "zero confirmed
    findings exist -- currently and correctly zero". Two confirmed
    findings exist. Neither is production-authoritative, and thirteen
    *rejections* are. Readiness therefore requires a finding that is
    confirmed AND production-authoritative; that set is empty, so the
    verdict is unchanged but no longer depends on a false premise.

This module is strictly read-only. It calls ``operational_health()`` and
never ``run_operational_check()``, which persists alerts and heartbeat
state.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from assistant.operations import operational_health
from assistant.paper_evidence import PaperEvidenceError, paper_evidence_summary
from assistant.policy import TradingPolicy
from assistant.research_registry import load_research_findings, registry_version
from assistant.storage import AssistantStore

READY = "ready"
DEGRADED = "degraded"
BLOCKED = "blocked"
_STATUSES = (READY, DEGRADED, BLOCKED)

EXECUTION_INTEGRITY = "execution_integrity"
DATA_INTEGRITY = "data_integrity"
OPERATIONAL_READINESS = "operational_readiness"
EVIDENCE_READINESS = "evidence_readiness"
STRATEGY_READINESS = "strategy_readiness"

DIMENSIONS = (
    EXECUTION_INTEGRITY,
    DATA_INTEGRITY,
    OPERATIONAL_READINESS,
    EVIDENCE_READINESS,
    STRATEGY_READINESS,
)

# Execution-safety checks whose failure is ALWAYS blocking, whatever
# severity the producing report happens to attach. An inherited "warning"
# must never downgrade the emergency stop.
_MANDATORY_EXECUTION_CHECKS = frozenset({
    "database_integrity",
    "ambiguous_broker_outcomes",
    "environment_kill_switch",
    "persistent_kill_switch",
    "policy",
    "policy_execution_mode",
    "reconciliation_freshness",
    "stranded_claims",
    "broker_account",
})

_EXECUTION_CATEGORIES = frozenset({"transaction_readiness"})


class PlatformReadinessError(RuntimeError):
    """The readiness report cannot be built from the inputs supplied."""


@dataclasses.dataclass(frozen=True)
class ReadinessCheck:
    """One observation. ``mandatory`` is decided here, not inherited."""

    name: str
    ok: bool
    detail: str
    mandatory: bool
    source: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class AdjustmentEvidence:
    """Verified point-in-time adjustment evidence, supplied by a caller.

    ``assistant/`` may not import ``ml/``, so this report cannot reach for
    adjustment honesty itself. The input contract exists so a later
    data-layer or CLI adapter can supply verified evidence without
    changing the readiness model. Absent evidence is blocking, never
    optimistically assumed.
    """

    point_in_time_data: bool
    source_id: str
    observed_at: str

    def __post_init__(self) -> None:
        if not isinstance(self.point_in_time_data, bool):
            raise PlatformReadinessError("point_in_time_data must be a boolean")
        for field in ("source_id", "observed_at"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise PlatformReadinessError(f"{field} must be a non-empty string")


@dataclasses.dataclass(frozen=True)
class DimensionReadiness:
    dimension: str
    status: str
    checks: tuple[ReadinessCheck, ...]
    blockers: tuple[str, ...]
    degradations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "status": self.status,
            "checks": [check.to_dict() for check in self.checks],
            "blockers": list(self.blockers),
            "degradations": list(self.degradations),
        }


@dataclasses.dataclass(frozen=True)
class PlatformReadinessReport:
    checked_at: str
    dimensions: tuple[DimensionReadiness, ...]

    def to_dict(self) -> dict[str, Any]:
        # Deliberately no aggregate score, pass/fail, or count of ready
        # dimensions: any single summary number lets a fatal dimension
        # hide behind healthy ones.
        return {
            "checked_at": self.checked_at,
            "dimensions": [d.to_dict() for d in self.dimensions],
        }

    def dimension(self, name: str) -> DimensionReadiness:
        for entry in self.dimensions:
            if entry.dimension == name:
                return entry
        raise PlatformReadinessError(f"unknown dimension {name!r}")


def _derive_status(checks: Sequence[ReadinessCheck]) -> str:
    """Empty delegated output is blocked, never ready."""
    if not checks:
        return BLOCKED
    if any(not check.ok and check.mandatory for check in checks):
        return BLOCKED
    if any(not check.ok for check in checks):
        return DEGRADED
    return READY


def _dimension(name: str, checks: Sequence[ReadinessCheck]) -> DimensionReadiness:
    ordered = tuple(checks)
    return DimensionReadiness(
        dimension=name,
        status=_derive_status(ordered),
        checks=ordered,
        blockers=tuple(
            f"{c.name}: {c.detail}" for c in ordered if not c.ok and c.mandatory
        ),
        degradations=tuple(
            f"{c.name}: {c.detail}" for c in ordered if not c.ok and not c.mandatory
        ),
    )


def _adapt_operations_check(raw: Mapping[str, Any], *, mandatory: bool) -> ReadinessCheck:
    """Adapt assistant/operations.py's five-key shape."""
    if not isinstance(raw, Mapping) or "name" not in raw or "ok" not in raw:
        raise PlatformReadinessError(f"malformed operational check: {raw!r}")
    return ReadinessCheck(
        name=str(raw["name"]),
        ok=bool(raw["ok"]),
        detail=str(raw.get("detail", "")),
        mandatory=mandatory,
        source="operational_health",
    )


def _validated_checks(health: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Validate every delegated check BEFORE any of them are filtered.

    Validating after the category filter would silently discard a
    malformed check instead of refusing it -- a delegated report could be
    partly garbage and this report would quietly score the remainder.
    """
    raw_checks = health.get("checks")
    if not isinstance(raw_checks, list):
        raise PlatformReadinessError("operational health report has no checks list")
    for raw in raw_checks:
        if (
            not isinstance(raw, Mapping)
            or "name" not in raw
            or "ok" not in raw
            or "category" not in raw
        ):
            raise PlatformReadinessError(f"malformed operational check: {raw!r}")
    return raw_checks


def build_execution_integrity(health: Mapping[str, Any]) -> DimensionReadiness:
    checks = [
        _adapt_operations_check(
            raw, mandatory=str(raw.get("name")) in _MANDATORY_EXECUTION_CHECKS
        )
        for raw in _validated_checks(health)
        if str(raw.get("category")) in _EXECUTION_CATEGORIES
    ]
    return _dimension(EXECUTION_INTEGRITY, checks)


def build_operational_readiness(health: Mapping[str, Any]) -> DimensionReadiness:
    checks = [
        # Outside execution, the producing report's own critical/warning
        # split is the right signal: a stale backup is a real deficiency
        # but does not make the platform unsafe to operate.
        _adapt_operations_check(raw, mandatory=str(raw.get("severity")) == "critical")
        for raw in _validated_checks(health)
        if str(raw.get("category")) not in _EXECUTION_CATEGORIES
    ]
    return _dimension(OPERATIONAL_READINESS, checks)


def build_data_integrity(
    evidence: AdjustmentEvidence | None,
) -> DimensionReadiness:
    if evidence is None:
        return _dimension(
            DATA_INTEGRITY,
            [
                ReadinessCheck(
                    name="adjustment_honesty",
                    ok=False,
                    detail=(
                        "blocked: verified point-in-time adjustment evidence was "
                        "not supplied. assistant/ may not import ml/, so this "
                        "report refuses rather than assuming."
                    ),
                    mandatory=True,
                    source="caller",
                )
            ],
        )
    return _dimension(
        DATA_INTEGRITY,
        [
            ReadinessCheck(
                name="adjustment_honesty",
                ok=evidence.point_in_time_data,
                detail=(
                    f"{evidence.source_id} reports point_in_time_data="
                    f"{str(evidence.point_in_time_data).lower()} as of "
                    f"{evidence.observed_at}"
                ),
                mandatory=True,
                source="adjustment_evidence",
            )
        ],
    )


def build_evidence_readiness(store: AssistantStore) -> DimensionReadiness:
    """Absent evidence and invalid evidence are both blocking, distinctly.

    Collapsing them would report a corrupt epoch the same way as a machine
    that has simply not started collecting yet -- two situations needing
    completely different responses.
    """
    try:
        epoch = store.get_active_paper_evidence_epoch()
    except Exception as exc:  # storage-level failure is unattributable evidence
        return _dimension(
            EVIDENCE_READINESS,
            [
                ReadinessCheck(
                    name="evidence_epoch",
                    ok=False,
                    detail=f"evidence is unreadable: {type(exc).__name__}: {exc}",
                    mandatory=True,
                    source="storage",
                )
            ],
        )
    if epoch is None:
        return _dimension(
            EVIDENCE_READINESS,
            [
                ReadinessCheck(
                    name="evidence_epoch",
                    ok=False,
                    detail="evidence is absent: no active paper evidence epoch",
                    mandatory=True,
                    source="storage",
                )
            ],
        )
    try:
        summary = paper_evidence_summary(store, epoch["evidence_epoch"])
    except PaperEvidenceError as exc:
        return _dimension(
            EVIDENCE_READINESS,
            [
                ReadinessCheck(
                    name="evidence_epoch",
                    ok=False,
                    detail=(
                        f"evidence is invalid for epoch {epoch['evidence_epoch']!r}: "
                        f"{exc}"
                    ),
                    mandatory=True,
                    source="paper_evidence_summary",
                )
            ],
        )
    sessions = summary.get("paper_sessions")
    checks = [
        ReadinessCheck(
            name="evidence_epoch",
            ok=True,
            detail=f"active epoch {epoch['evidence_epoch']}",
            mandatory=True,
            source="storage",
        ),
        ReadinessCheck(
            name="paper_sessions",
            ok=bool(sessions),
            detail=f"{sessions} recorded paper session(s)",
            mandatory=True,
            source="paper_evidence_summary",
        ),
        ReadinessCheck(
            name="coverage_complete",
            ok=bool(summary.get("coverage_complete")),
            detail=(
                "every expected session is present"
                if summary.get("coverage_complete")
                else "sessions are missing from the epoch"
            ),
            mandatory=True,
            source="paper_evidence_summary",
        ),
        ReadinessCheck(
            name="lineage_consistent",
            ok=bool(summary.get("lineage_consistent")),
            detail=(
                "every observation matches the epoch lineage"
                if summary.get("lineage_consistent")
                else "an observation does not match the epoch lineage"
            ),
            mandatory=True,
            source="paper_evidence_summary",
        ),
    ]
    return _dimension(EVIDENCE_READINESS, checks)


def build_strategy_readiness(findings: Sequence[Any] | None = None) -> DimensionReadiness:
    """Ready requires a finding that is confirmed AND production-authoritative.

    A rejection can be production-authoritative -- thirteen currently are --
    so authority alone says nothing about whether a strategy is ready. The
    two confirmed findings are not authoritative, so the eligible set is
    empty.
    """
    if findings is None:
        findings = load_research_findings()
    eligible = [
        finding
        for finding in findings
        if getattr(getattr(finding, "status", None), "value", None) == "confirmed"
        and bool(getattr(finding, "production_authoritative", False))
    ]
    confirmed = sum(
        1
        for finding in findings
        if getattr(getattr(finding, "status", None), "value", None) == "confirmed"
    )
    return _dimension(
        STRATEGY_READINESS,
        [
            ReadinessCheck(
                name="confirmed_and_authoritative_finding",
                ok=bool(eligible),
                detail=(
                    f"{len(eligible)} finding(s) are both confirmed and "
                    f"production-authoritative ({confirmed} confirmed overall, "
                    f"registry {registry_version()}). A platform being excellent "
                    "does not make a strategy ready."
                ),
                mandatory=True,
                source="research_registry",
            )
        ],
    )


def build_platform_readiness(
    store: AssistantStore,
    policy: TradingPolicy,
    *,
    now: datetime | None = None,
    broker_module=None,
    check_broker: bool = True,
    adjustment_evidence: AdjustmentEvidence | None = None,
    findings: Sequence[Any] | None = None,
    **health_options: Any,
) -> PlatformReadinessReport:
    """Read-only readiness across five independent dimensions."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise PlatformReadinessError("now must be timezone-aware")
    # operational_health(), never run_operational_check(): the latter
    # persists alerts and heartbeat state, and this report must not write.
    health = operational_health(
        store,
        policy,
        broker_module=broker_module,
        now=now,
        check_broker=check_broker,
        **health_options,
    )
    dimensions = (
        build_execution_integrity(health),
        build_data_integrity(adjustment_evidence),
        build_operational_readiness(health),
        build_evidence_readiness(store),
        build_strategy_readiness(findings),
    )
    assert {d.dimension for d in dimensions} == set(DIMENSIONS)
    return PlatformReadinessReport(
        checked_at=now.astimezone(timezone.utc).isoformat(),
        dimensions=dimensions,
    )
