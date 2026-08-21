"""GR-0: make "complete" a measurement instead of a feeling.

Five dimensions, each scored independently and **never** averaged. An
average lets a strong dimension hide a fatal one, which is the specific
failure this report exists to prevent.

Three deviations from docs/Plan/GENERAL_READINESS_IMPLEMENTATION_PLAN.md
section 5, all because the plan predates code that now exists. They are
deliberate; see docs/operations/GENERAL_READINESS_STATUS.md.

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

Data integrity is derived from GR-4's recorded provider-fetch evidence.
GR-0 still exposes no boolean escape hatch that lets a caller assert those
facts.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from assistant.operations import operational_health
from assistant.mandate import PortfolioMandate
from assistant.paper_evidence import (
    REQUIRED_PROMOTION_DRILLS,
    PaperEvidenceError,
    paper_evidence_summary,
)
from assistant.policy import TradingPolicy
from assistant.research_registry import load_research_findings, registry_version
from assistant.schemas import EvidenceStatus
from assistant.storage import AssistantStore

READY = "ready"
DEGRADED = "degraded"
BLOCKED = "blocked"
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

# The complete inventory currently emitted by transaction_readiness() plus
# the canonical portfolio-ledger reconciliation emitted by
# operational_health(). Missing checks are explicit blockers. This matters for
# --offline: skipping the broker call must not turn "unverified" into ready.
_EXPECTED_EXECUTION_CHECKS = frozenset({
    "database_integrity",
    "ambiguous_broker_outcomes",
    "environment_kill_switch",
    "persistent_kill_switch",
    "policy",
    "policy_execution_mode",
    "reconciliation_freshness",
    "stranded_pre_broker_claims",
    "broker_account",
    "broker_open_order_budget",
    "active_order_budget",
    "daily_submission_budget",
    "portfolio_ledger_reconciliation",
})

_EXECUTION_CATEGORIES = frozenset({
    "transaction_readiness",
    "portfolio_accounting",
})


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


def _unavailable_dimension(
    name: str,
    *,
    check_name: str,
    source: str,
    detail: str,
) -> DimensionReadiness:
    return _dimension(
        name,
        [
            ReadinessCheck(
                name=check_name,
                ok=False,
                detail=detail,
                mandatory=True,
                source=source,
            )
        ],
    )


def _adapt_operations_check(raw: Mapping[str, Any], *, mandatory: bool) -> ReadinessCheck:
    """Adapt assistant/operations.py's five-key shape."""
    if not isinstance(raw, Mapping) or "name" not in raw or "ok" not in raw:
        raise PlatformReadinessError(f"malformed operational check: {raw!r}")
    return ReadinessCheck(
        name=raw["name"],
        ok=raw["ok"],
        detail=raw["detail"],
        mandatory=mandatory,
        source="operational_health",
    )


def _validated_checks(health: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Validate every delegated check BEFORE any of them are filtered.

    Validating after the category filter would silently discard a
    malformed check instead of refusing it -- a delegated report could be
    partly garbage and this report would quietly score the remainder.
    """
    if not isinstance(health, Mapping):
        raise PlatformReadinessError("operational health report must be a mapping")
    raw_checks = health.get("checks")
    if not isinstance(raw_checks, list):
        raise PlatformReadinessError("operational health report has no checks list")
    seen: set[str] = set()
    for raw in raw_checks:
        if (
            not isinstance(raw, Mapping)
            or not isinstance(raw.get("name"), str)
            or not raw["name"].strip()
            or not isinstance(raw.get("ok"), bool)
            or not isinstance(raw.get("detail"), str)
            or not isinstance(raw.get("category"), str)
            or not raw["category"].strip()
            or raw.get("severity") not in {"critical", "warning"}
        ):
            raise PlatformReadinessError(f"malformed operational check: {raw!r}")
        if raw["name"] in seen:
            raise PlatformReadinessError(
                f"duplicate operational check name: {raw['name']!r}"
            )
        seen.add(raw["name"])
    return raw_checks


def build_execution_integrity(health: Mapping[str, Any]) -> DimensionReadiness:
    checks: list[ReadinessCheck] = [
        _adapt_operations_check(
            # Every check delegated to execution_integrity controls whether
            # the platform can safely submit or account for another order.
            # Capacity exhaustion is temporary, but it still means execution
            # is blocked now rather than merely impaired.
            raw, mandatory=True
        )
        for raw in _validated_checks(health)
        if raw["category"] in _EXECUTION_CATEGORIES
    ]
    present = {check.name for check in checks}
    for missing in sorted(_EXPECTED_EXECUTION_CHECKS - present):
        checks.append(
            ReadinessCheck(
                name=missing,
                ok=False,
                detail="required execution check was unavailable",
                mandatory=True,
                source="operational_health",
            )
        )
    return _dimension(EXECUTION_INTEGRITY, checks)


def build_operational_readiness(
    health: Mapping[str, Any], store: AssistantStore | None = None
) -> DimensionReadiness:
    checks = [
        # Outside execution, the producing report's own critical/warning
        # split is the right signal: a stale backup is a real deficiency
        # but does not make the platform unsafe to operate.
        _adapt_operations_check(raw, mandatory=str(raw.get("severity")) == "critical")
        for raw in _validated_checks(health)
        if raw["category"] not in _EXECUTION_CATEGORIES
    ]
    if store is not None:
        checks.extend(build_alert_delivery_checks(store))
    return _dimension(OPERATIONAL_READINESS, checks)


def build_alert_delivery_checks(store: AssistantStore) -> tuple[ReadinessCheck, ...]:
    """GR-5: is anything actually reaching the operator?

    Deliberately reported HERE rather than as an ``operational_health``
    check: that producer persists an alert for every failing check, so an
    "undelivered critical alerts exist" check would raise a critical alert
    that is itself undelivered, and each cycle would manufacture another.
    This report is strictly read-only, so the same fact is surfaced without
    the feedback loop.

    An undelivered critical alert is mandatory (the operator was not told
    about a platform-halting condition). A stale channel self-test degrades:
    the channel may still work, it has merely not been proven this week.
    """
    from assistant.alert_delivery import (
        self_test_freshness,
        undelivered_critical_alerts,
    )

    undelivered = undelivered_critical_alerts(store)
    freshness = self_test_freshness(store)
    # Counter-review CRGR4-001: the delegated freshness report used to be
    # coerced with bool(...), the exact laundering GR4REV-003 removed from
    # the data-layer checks (and the 2026-08-02 GR-0 review removed from
    # operational checks) -- a malformed {"ok": "false"} read as a healthy
    # self-test. Validate structurally; a malformed report fails the check
    # with an explicit reason instead of guessing.
    freshness_ok = (
        isinstance(freshness, Mapping)
        and isinstance(freshness.get("ok"), bool)
        and isinstance(freshness.get("detail"), str)
        and bool(str(freshness.get("detail")).strip())
    )
    if not freshness_ok:
        self_test_check = ReadinessCheck(
            name="alert_channel_self_test",
            ok=False,
            detail=(
                "self-test freshness report is malformed; refusing to "
                "treat an unreadable report as a passing self-test"
            ),
            mandatory=False,
            source="alert_delivery",
        )
    else:
        self_test_check = ReadinessCheck(
            name="alert_channel_self_test",
            ok=freshness["ok"],
            detail=freshness["detail"],
            mandatory=False,
            source="alert_delivery",
        )
    return (
        ReadinessCheck(
            name="critical_alert_delivery",
            ok=not undelivered,
            detail=(
                "every open critical alert has a recorded delivery"
                if not undelivered
                else f"{len(undelivered)} critical alert(s) never delivered: "
                + ", ".join(sorted(a["fingerprint"] for a in undelivered))[:200]
            ),
            mandatory=True,
            source="alert_delivery",
        ),
        self_test_check,
    )


def build_data_integrity(
    store: AssistantStore | None = None,
    *,
    now: datetime | None = None,
) -> DimensionReadiness:
    """GR-4: derive the three GR-0 data checks from recorded fetches.

    The pre-GR-4 API let any caller set ``point_in_time_data=True`` and used
    that assertion to make this dimension ready. A claim is not evidence, so
    the checks now come from ``assistant.data_integrity``'s derivation over
    the append-only ``data_provider_fetches`` records -- and there is still
    no caller-settable boolean. A machine with no store (or no recorded
    fetches, or an unreadable record table) stays blocked with an explicit
    reason; readiness must never improve because evidence became
    unavailable.

    When ``now`` is supplied (as ``build_platform_readiness`` does), bar
    freshness uses that same pinned instant so the report's ``checked_at``
    and the freshness SLA cannot disagree.
    """
    if store is not None and not isinstance(store, AssistantStore):
        # The pre-GR-4 escape hatch was a caller passing
        # point_in_time_data=True; the store parameter must never become a
        # new place to smuggle an assertion. Only a real store (evidence)
        # or None (explicitly blocked) is meaningful.
        raise TypeError(
            "build_data_integrity takes an AssistantStore or None; a "
            "boolean assertion cannot make data integrity ready"
        )
    if store is None:
        return _dimension(
            DATA_INTEGRITY,
            tuple(
                ReadinessCheck(
                    name=name,
                    ok=False,
                    detail=(
                        "no store supplied; data-layer evidence cannot be "
                        "derived from recorded provider fetches"
                    ),
                    mandatory=True,
                    source="data_layer",
                )
                for name in (
                    "price_freshness",
                    "provider_health",
                    "adjustment_honesty",
                )
            ),
        )
    from assistant.data_integrity import build_data_layer_evidence

    try:
        evidence = build_data_layer_evidence(store, now=now)
    except Exception as exc:
        return _dimension(
            DATA_INTEGRITY,
            tuple(
                ReadinessCheck(
                    name=name,
                    ok=False,
                    detail=(
                        "data-layer evidence derivation failed "
                        f"({type(exc).__name__}); refusing to guess"
                    ),
                    mandatory=True,
                    source="data_layer",
                )
                for name in (
                    "price_freshness",
                    "provider_health",
                    "adjustment_honesty",
                )
            ),
        )
    names = ("price_freshness", "provider_health", "adjustment_honesty")
    malformed_reason: str | None = None
    if not isinstance(evidence, Mapping):
        malformed_reason = "data-layer evidence is not a mapping"
    else:
        for name in names:
            raw = evidence.get(name)
            if (
                not isinstance(raw, Mapping)
                or not isinstance(raw.get("ok"), bool)
                or not isinstance(raw.get("detail"), str)
            ):
                malformed_reason = (
                    f"data-layer evidence for {name} is malformed"
                )
                break
    if malformed_reason is not None:
        return _dimension(
            DATA_INTEGRITY,
            tuple(
                ReadinessCheck(
                    name=name,
                    ok=False,
                    detail=malformed_reason,
                    mandatory=True,
                    source="data_layer",
                )
                for name in names
            ),
        )
    return _dimension(
        DATA_INTEGRITY,
        tuple(
            ReadinessCheck(
                name=name,
                ok=evidence[name]["ok"],
                detail=evidence[name]["detail"],
                mandatory=True,
                source="data_layer",
            )
            for name in names
        ),
    )


def _load_paper_summary(
    store: AssistantStore,
) -> tuple[Mapping[str, Any] | None, DimensionReadiness | None]:
    """Load one evidence snapshot or return a precise blocked dimension."""
    try:
        epoch = store.get_active_paper_evidence_epoch()
    except Exception as exc:
        return None, _unavailable_dimension(
            EVIDENCE_READINESS,
            check_name="evidence_epoch",
            source="storage",
            detail=f"evidence is unreadable: {type(exc).__name__}: {exc}",
        )
    if epoch is None:
        return None, _unavailable_dimension(
            EVIDENCE_READINESS,
            check_name="evidence_epoch",
            source="storage",
            detail="evidence is absent: no active paper evidence epoch",
        )
    if not isinstance(epoch, Mapping):
        return None, _unavailable_dimension(
            EVIDENCE_READINESS,
            check_name="evidence_epoch",
            source="storage",
            detail="evidence is invalid: active epoch is malformed",
        )
    evidence_epoch = epoch.get("evidence_epoch")
    if not isinstance(evidence_epoch, str) or not evidence_epoch.strip():
        return None, _unavailable_dimension(
            EVIDENCE_READINESS,
            check_name="evidence_epoch",
            source="storage",
            detail="evidence is invalid: active epoch has no valid identity",
        )
    try:
        summary = paper_evidence_summary(store, evidence_epoch)
    except PaperEvidenceError as exc:
        return None, _unavailable_dimension(
            EVIDENCE_READINESS,
            check_name="evidence_epoch",
            source="paper_evidence_summary",
            detail=f"evidence is invalid for epoch {evidence_epoch!r}: {exc}",
        )
    except Exception as exc:
        # This is deliberately distinct from absence. Storage corruption,
        # malformed persisted JSON, and a broken delegated report must produce
        # a visible blocker rather than terminate the readiness command.
        return None, _unavailable_dimension(
            EVIDENCE_READINESS,
            check_name="evidence_epoch",
            source="paper_evidence_summary",
            detail=(
                f"evidence is unreadable for epoch {evidence_epoch!r}: "
                f"{type(exc).__name__}: {exc}"
            ),
        )
    if not isinstance(summary, Mapping):
        return None, _unavailable_dimension(
            EVIDENCE_READINESS,
            check_name="evidence_summary",
            source="paper_evidence_summary",
            detail="evidence summary is malformed: expected a mapping",
        )
    return summary, None


def _nonnegative_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PlatformReadinessError(
            f"paper evidence {field} must be a non-negative integer"
        )
    return value


def _required_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise PlatformReadinessError(f"paper evidence {field} must be a boolean")
    return value


def _build_evidence_from_summary(
    summary: Mapping[str, Any], mandate: PortfolioMandate
) -> DimensionReadiness:
    try:
        evidence_epoch = summary["evidence_epoch"]
        if not isinstance(evidence_epoch, str) or not evidence_epoch.strip():
            raise PlatformReadinessError(
                "paper evidence evidence_epoch must be a non-empty string"
            )
        sessions = _nonnegative_int(summary.get("paper_sessions"), "paper_sessions")
        orders = summary.get("paper_orders")
        if not isinstance(orders, Mapping):
            raise PlatformReadinessError("paper evidence paper_orders must be a mapping")
        order_count = _nonnegative_int(orders.get("count"), "paper_orders.count")
        coverage_complete = _required_bool(
            summary.get("coverage_complete"), "coverage_complete"
        )
        lineage_consistent = _required_bool(
            summary.get("lineage_consistent"), "lineage_consistent"
        )
    except (KeyError, PlatformReadinessError) as exc:
        return _unavailable_dimension(
            EVIDENCE_READINESS,
            check_name="evidence_summary",
            source="paper_evidence_summary",
            detail=f"evidence summary is malformed: {exc}",
        )

    checks = [
        ReadinessCheck(
            name="evidence_epoch",
            ok=True,
            detail=f"active epoch {evidence_epoch}",
            mandatory=True,
            source="paper_evidence_summary",
        ),
        ReadinessCheck(
            name="paper_sessions",
            ok=sessions >= mandate.min_paper_sessions,
            detail=f"{sessions}/{mandate.min_paper_sessions} required paper sessions",
            mandatory=True,
            source="paper_evidence_summary",
        ),
        ReadinessCheck(
            name="paper_orders",
            ok=order_count >= mandate.min_paper_orders,
            detail=f"{order_count}/{mandate.min_paper_orders} required paper orders",
            mandatory=True,
            source="paper_evidence_summary",
        ),
        ReadinessCheck(
            name="coverage_complete",
            ok=coverage_complete,
            detail=(
                "every expected session is present"
                if coverage_complete
                else "sessions are missing from the epoch"
            ),
            mandatory=True,
            source="paper_evidence_summary",
        ),
        ReadinessCheck(
            name="lineage_consistent",
            ok=lineage_consistent,
            detail=(
                "every observation matches the epoch lineage"
                if lineage_consistent
                else "an observation does not match the epoch lineage"
            ),
            mandatory=True,
            source="paper_evidence_summary",
        ),
    ]
    return _dimension(EVIDENCE_READINESS, checks)


def _operational_drill_checks(
    summary: Mapping[str, Any] | None,
) -> tuple[ReadinessCheck, ...]:
    if summary is None:
        return (
            ReadinessCheck(
                name="operational_drills",
                ok=False,
                detail="paper evidence is unavailable, so drill results cannot be verified",
                mandatory=True,
                source="paper_evidence_summary",
            ),
        )
    raw_drills = summary.get("required_drills")
    if not isinstance(raw_drills, Mapping):
        return (
            ReadinessCheck(
                name="operational_drills",
                ok=False,
                detail="paper evidence required_drills is malformed or unavailable",
                mandatory=True,
                source="paper_evidence_summary",
            ),
        )
    checks: list[ReadinessCheck] = []
    for drill_type in REQUIRED_PROMOTION_DRILLS:
        raw = raw_drills.get(drill_type)
        passed = raw.get("passed") if isinstance(raw, Mapping) else None
        if not isinstance(passed, bool):
            checks.append(
                ReadinessCheck(
                    name=f"drill_{drill_type}",
                    ok=False,
                    detail="required drill result is unavailable or malformed",
                    mandatory=True,
                    source="paper_evidence_summary",
                )
            )
            continue
        checks.append(
            ReadinessCheck(
                name=f"drill_{drill_type}",
                ok=passed,
                detail="latest recorded result passed" if passed else "no passing result recorded",
                mandatory=True,
                source="paper_evidence_summary",
            )
        )
    return tuple(checks)


def build_evidence_readiness(
    store: AssistantStore, mandate: PortfolioMandate
) -> DimensionReadiness:
    """Absent evidence and invalid evidence are both blocking, distinctly.

    Collapsing them would report a corrupt epoch the same way as a machine
    that has simply not started collecting yet -- two situations needing
    completely different responses.
    """
    mandate.validate()
    summary, failure = _load_paper_summary(store)
    if failure is not None:
        return failure
    assert summary is not None
    return _build_evidence_from_summary(summary, mandate)


def build_strategy_readiness(findings: Sequence[Any] | None = None) -> DimensionReadiness:
    """Ready requires a finding that is confirmed AND production-authoritative.

    A rejection can be production-authoritative -- thirteen currently are --
    so authority alone says nothing about whether a strategy is ready. The
    two confirmed findings are not authoritative, so the eligible set is
    empty.
    """
    try:
        if findings is None:
            findings = load_research_findings()
        version = registry_version()
    except Exception as exc:
        return _unavailable_dimension(
            STRATEGY_READINESS,
            check_name="research_registry",
            source="research_registry",
            detail=f"research registry is unreadable: {type(exc).__name__}: {exc}",
        )
    allowed_statuses = {status.value for status in EvidenceStatus}
    for finding in findings:
        status = getattr(getattr(finding, "status", None), "value", None)
        authority = getattr(finding, "production_authoritative", None)
        if status not in allowed_statuses or not isinstance(authority, bool):
            return _unavailable_dimension(
                STRATEGY_READINESS,
                check_name="research_registry",
                source="research_registry",
                detail="research registry contains a malformed finding",
            )
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
                    f"registry {version}). A platform being excellent "
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
    mandate: PortfolioMandate,
    *,
    now: datetime | None = None,
    broker_module=None,
    check_broker: bool = True,
    **health_options: Any,
) -> PlatformReadinessReport:
    """Read-only readiness across five independent dimensions."""
    explicit_now = now
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise PlatformReadinessError("now must be timezone-aware")
    # operational_health(), never run_operational_check(): the latter
    # persists alerts and heartbeat state, and this report must not write.
    mandate.validate()
    try:
        health = operational_health(
            store,
            policy,
            broker_module=broker_module,
            # AP-11: forward the CALLER's clock, not the entry clock
            # manufactured above -- a mid-chain "explicit" clock freezes the
            # nested AP-7 post-read freshness clocks and re-arms the
            # concurrent-write race. `now` (manufactured) is still correct
            # for build_data_integrity below, which documents that it wants
            # one fixed evaluation clock, and for this report's checked_at.
            now=explicit_now,
            check_broker=check_broker,
            **health_options,
        )
        try:
            execution = build_execution_integrity(health)
        except PlatformReadinessError as exc:
            execution = _unavailable_dimension(
                EXECUTION_INTEGRITY,
                check_name="operational_health",
                source="operational_health",
                detail=f"execution checks are malformed: {exc}",
            )
        try:
            operations = build_operational_readiness(health, store)
        except PlatformReadinessError as exc:
            operations = _unavailable_dimension(
                OPERATIONAL_READINESS,
                check_name="operational_health",
                source="operational_health",
                detail=f"operational checks are malformed: {exc}",
            )
    except Exception as exc:
        failure = f"operational health is unavailable: {type(exc).__name__}: {exc}"
        execution = _unavailable_dimension(
            EXECUTION_INTEGRITY,
            check_name="operational_health",
            source="operational_health",
            detail=failure,
        )
        operations = _unavailable_dimension(
            OPERATIONAL_READINESS,
            check_name="operational_health",
            source="operational_health",
            detail=failure,
        )

    summary, evidence_failure = _load_paper_summary(store)
    if evidence_failure is not None:
        evidence = evidence_failure
    else:
        assert summary is not None
        evidence = _build_evidence_from_summary(summary, mandate)
    operations = _dimension(
        OPERATIONAL_READINESS,
        (*operations.checks, *_operational_drill_checks(summary)),
    )
    dimensions = (
        execution,
        build_data_integrity(store, now=now),
        operations,
        evidence,
        build_strategy_readiness(),
    )
    assert {d.dimension for d in dimensions} == set(DIMENSIONS)
    return PlatformReadinessReport(
        checked_at=now.astimezone(timezone.utc).isoformat(),
        dimensions=dimensions,
    )
