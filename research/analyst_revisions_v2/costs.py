"""Authenticated, dimensionally coherent Analyst V2 transaction costs."""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Iterable

from data.financial_primitives import to_decimal

from .canonical import (
    CanonicalEvidenceError,
    require_canonical_json_bytes,
    require_exact_keys,
)
from .formulas import (
    FormulaError,
    ResearchSourceKind,
    VerifiedAnalystPolicy,
    analyst_decimal_context,
    require_registered_source_bytes,
    require_verified_analyst_policy,
)


class CostModelError(ValueError):
    """A cost input is unauthenticated, non-PIT, or dimensionally invalid."""


_TERMINAL_EVIDENCE_TOKEN = object()
_TRADE_COST_EVIDENCE_TOKEN = object()
_TERMINAL_SOURCE_SCHEMA = "arv2-terminal-exit-source-v1"
_TRADE_COST_SOURCE_SCHEMA = "arv2-trade-cost-source-v1"
_TERMINAL_SOURCE_KEYS = frozenset(
    {
        "schema",
        "source_id",
        "evidence_epoch_id",
        "security_id",
        "terminal_event_id",
        "event_kind",
        "position_snapshot_id",
        "current_long_position_dollars",
        "effective_at",
        "available_at",
        "decision_at",
    }
)
_TRADE_COST_SOURCE_KEYS = frozenset(
    {
        "schema",
        "source_id",
        "evidence_epoch_id",
        "policy_sha256",
        "security_id",
        "effective_at",
        "available_at",
        "decision_at",
        "commission_rate",
        "half_spread_rate",
        "impact_coefficient",
        "adv_dollars",
    }
)


def _d(value: object, name: str) -> Decimal:
    if isinstance(value, bool):
        raise CostModelError(f"{name} must be finite, not bool")
    try:
        parsed = to_decimal(value, name=name)  # type: ignore[arg-type]
    except ValueError as exc:
        raise CostModelError(f"{name} must be finite") from exc
    return parsed


def _stable_decimal_sum(values: Iterable[Decimal]) -> Decimal:
    return sum(
        sorted(values, key=lambda value: (abs(value), value)), Decimal("0")
    )


def _source_decimal(value: object, name: str) -> Decimal:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CostModelError(f"{name} must be a canonical exact decimal string")
    parsed = _d(value, name)
    canonical = format(parsed, "f")
    if "." in canonical:
        canonical = canonical.rstrip("0").rstrip(".")
    if parsed == 0:
        canonical = "0"
    if value != canonical:
        raise CostModelError(f"{name} must use canonical decimal spelling")
    return parsed


def _canonical_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CostModelError(f"{name} must be canonical and non-empty")
    return value


def _sha256(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise CostModelError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _instant(value: object, name: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CostModelError(f"{name} must be a canonical UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise CostModelError(f"{name} must be a canonical UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CostModelError(f"{name} must be timezone-aware")
    parsed = parsed.astimezone(timezone.utc)
    if value != parsed.isoformat():
        raise CostModelError(f"{name} must use canonical UTC ISO-8601 spelling")
    return parsed


def _source_record(source_bytes: bytes, *, terminal: bool) -> dict[str, object]:
    label = "terminal source" if terminal else "trade-cost source"
    expected_keys = _TERMINAL_SOURCE_KEYS if terminal else _TRADE_COST_SOURCE_KEYS
    try:
        raw = require_canonical_json_bytes(source_bytes, label)
        if not isinstance(raw, dict):
            raise CostModelError(f"{label} must be a JSON object")
        require_exact_keys(raw, expected_keys, label)
    except CanonicalEvidenceError as exc:
        raise CostModelError(f"{label} is not canonical evidence") from exc
    return raw


def _pit_times(raw: dict[str, object], label: str) -> tuple[str, str, str]:
    effective = _instant(raw["effective_at"], f"{label}.effective_at")
    available = _instant(raw["available_at"], f"{label}.available_at")
    decision = _instant(raw["decision_at"], f"{label}.decision_at")
    if not effective <= available <= decision:
        raise CostModelError(
            f"{label} must satisfy effective_at <= available_at <= decision_at"
        )
    return effective.isoformat(), available.isoformat(), decision.isoformat()


class TerminalEventKind(str, Enum):
    DELISTING = "delisting"
    BANKRUPTCY = "bankruptcy"
    LIQUIDATION = "liquidation"


def _parse_terminal_source(
    source_bytes: bytes,
) -> tuple[
    str,
    str,
    str,
    str,
    TerminalEventKind,
    str,
    Decimal,
    str,
    str,
    str,
]:
    raw = _source_record(source_bytes, terminal=True)
    if raw["schema"] != _TERMINAL_SOURCE_SCHEMA:
        raise CostModelError("terminal source schema is unsupported")
    try:
        event_kind = TerminalEventKind(raw["event_kind"])
    except (TypeError, ValueError) as exc:
        raise CostModelError("terminal event kind is invalid") from exc
    position = _source_decimal(
        raw["current_long_position_dollars"],
        "terminal current_long_position_dollars",
    )
    if position <= 0:
        raise CostModelError(
            "terminal source must prove a positive current long position"
        )
    return (
        _canonical_text(raw["source_id"], "terminal source_id"),
        _canonical_text(raw["evidence_epoch_id"], "terminal evidence_epoch_id"),
        _canonical_text(raw["security_id"], "terminal security_id"),
        _canonical_text(raw["terminal_event_id"], "terminal_event_id"),
        event_kind,
        _canonical_text(raw["position_snapshot_id"], "position_snapshot_id"),
        position,
        *_pit_times(raw, "terminal source"),
    )


@dataclasses.dataclass(frozen=True, init=False)
class VerifiedTerminalExitEvidence:
    source_bytes: bytes = dataclasses.field(repr=False, compare=False)
    source_sha256: str
    source_id: str
    evidence_epoch_id: str
    security_id: str
    terminal_event_id: str
    event_kind: TerminalEventKind
    position_snapshot_id: str
    current_long_position_dollars: Decimal
    effective_at: str
    available_at: str
    decision_at: str
    _token: object = dataclasses.field(repr=False, compare=False)


def verify_terminal_exit_evidence(
    *, source_bytes: bytes
) -> VerifiedTerminalExitEvidence:
    """Refuse until a reviewed external terminal-event authority exists."""
    try:
        immutable_source, source_digest = require_registered_source_bytes(
            ResearchSourceKind.TERMINAL_EVENT, source_bytes
        )
    except FormulaError as exc:
        raise CostModelError("terminal-event source authority is zero-access") from exc
    (
        source_id,
        epoch,
        security,
        event_id,
        kind,
        position_snapshot_id,
        current_position,
        effective,
        available,
        decision,
    ) = _parse_terminal_source(immutable_source)
    value = object.__new__(VerifiedTerminalExitEvidence)
    for name, item in {
        "source_bytes": immutable_source,
        "source_sha256": source_digest,
        "source_id": source_id,
        "evidence_epoch_id": epoch,
        "security_id": security,
        "terminal_event_id": event_id,
        "event_kind": kind,
        "position_snapshot_id": position_snapshot_id,
        "current_long_position_dollars": current_position,
        "effective_at": effective,
        "available_at": available,
        "decision_at": decision,
        "_token": _TERMINAL_EVIDENCE_TOKEN,
    }.items():
        object.__setattr__(value, name, item)
    return require_terminal_exit_evidence(value)


def require_terminal_exit_evidence(value: object) -> VerifiedTerminalExitEvidence:
    if (
        type(value) is not VerifiedTerminalExitEvidence
        or getattr(value, "_token", None) is not _TERMINAL_EVIDENCE_TOKEN
    ):
        raise CostModelError("forced terminal exit requires verified terminal evidence")
    try:
        source_bytes, source_digest = require_registered_source_bytes(
            ResearchSourceKind.TERMINAL_EVENT, value.source_bytes
        )
    except FormulaError as exc:
        raise CostModelError("terminal-event source authority is zero-access") from exc
    parsed = _parse_terminal_source(source_bytes)
    expected = (
        value.source_id,
        value.evidence_epoch_id,
        value.security_id,
        value.terminal_event_id,
        value.event_kind,
        value.position_snapshot_id,
        value.current_long_position_dollars,
        value.effective_at,
        value.available_at,
        value.decision_at,
    )
    if value.source_sha256 != source_digest or parsed != expected:
        raise CostModelError("terminal evidence differs from registered source bytes")
    return value


def _parse_trade_cost_source(
    source_bytes: bytes,
) -> tuple[
    str,
    str,
    str,
    str,
    str,
    str,
    str,
    Decimal,
    Decimal,
    Decimal,
    Decimal | None,
]:
    raw = _source_record(source_bytes, terminal=False)
    if raw["schema"] != _TRADE_COST_SOURCE_SCHEMA:
        raise CostModelError("trade-cost source schema is unsupported")
    source_id = _canonical_text(raw["source_id"], "trade-cost source_id")
    epoch = _canonical_text(raw["evidence_epoch_id"], "trade-cost evidence_epoch_id")
    policy_sha = _sha256(raw["policy_sha256"], "trade-cost policy_sha256")
    security = _canonical_text(raw["security_id"], "trade-cost security_id")
    effective, available, decision = _pit_times(raw, "trade-cost source")
    commission = _source_decimal(raw["commission_rate"], "commission_rate")
    spread = _source_decimal(raw["half_spread_rate"], "half_spread_rate")
    impact = _source_decimal(raw["impact_coefficient"], "impact_coefficient")
    adv = (
        None
        if raw["adv_dollars"] is None
        else _source_decimal(raw["adv_dollars"], "adv_dollars")
    )
    if any(value < 0 for value in (commission, spread, impact)):
        raise CostModelError("trade-cost rates must be non-negative")
    if adv is not None and adv <= 0:
        raise CostModelError("known PIT ADV must be positive")
    return (
        source_id,
        epoch,
        policy_sha,
        security,
        effective,
        available,
        decision,
        commission,
        spread,
        impact,
        adv,
    )


@dataclasses.dataclass(frozen=True, init=False)
class VerifiedTradeCostEvidence:
    source_bytes: bytes = dataclasses.field(repr=False, compare=False)
    source_sha256: str
    source_id: str
    evidence_epoch_id: str
    policy_sha256: str
    security_id: str
    effective_at: str
    available_at: str
    decision_at: str
    commission_rate: Decimal
    half_spread_rate: Decimal
    impact_coefficient: Decimal
    adv_dollars: Decimal | None
    _token: object = dataclasses.field(repr=False, compare=False)


def verify_trade_cost_evidence(
    *, source_bytes: bytes, policy: VerifiedAnalystPolicy
) -> VerifiedTradeCostEvidence:
    """Authenticate PIT spread, impact, commission, and ADV assumptions."""
    try:
        verified_policy = require_verified_analyst_policy(policy)
        immutable_source, source_digest = require_registered_source_bytes(
            ResearchSourceKind.TRADE_COST, source_bytes
        )
    except FormulaError as exc:
        raise CostModelError("trade-cost source authority is zero-access") from exc
    parsed = _parse_trade_cost_source(immutable_source)
    if parsed[2] != verified_policy.evidence_sha256:
        raise CostModelError("trade-cost evidence belongs to another policy")
    value = object.__new__(VerifiedTradeCostEvidence)
    names = (
        "source_id",
        "evidence_epoch_id",
        "policy_sha256",
        "security_id",
        "effective_at",
        "available_at",
        "decision_at",
        "commission_rate",
        "half_spread_rate",
        "impact_coefficient",
        "adv_dollars",
    )
    for name, item in {
        "source_bytes": immutable_source,
        "source_sha256": source_digest,
        **dict(zip(names, parsed, strict=True)),
        "_token": _TRADE_COST_EVIDENCE_TOKEN,
    }.items():
        object.__setattr__(value, name, item)
    return require_trade_cost_evidence(value, policy=verified_policy)


def require_trade_cost_evidence(
    value: object, *, policy: VerifiedAnalystPolicy
) -> VerifiedTradeCostEvidence:
    if (
        type(value) is not VerifiedTradeCostEvidence
        or getattr(value, "_token", None) is not _TRADE_COST_EVIDENCE_TOKEN
    ):
        raise CostModelError("trade cost requires verified PIT cost evidence")
    try:
        verified_policy = require_verified_analyst_policy(policy)
        source_bytes, source_digest = require_registered_source_bytes(
            ResearchSourceKind.TRADE_COST, value.source_bytes
        )
    except FormulaError as exc:
        raise CostModelError("trade-cost source authority is zero-access") from exc
    parsed = _parse_trade_cost_source(source_bytes)
    actual = (
        value.source_id,
        value.evidence_epoch_id,
        value.policy_sha256,
        value.security_id,
        value.effective_at,
        value.available_at,
        value.decision_at,
        value.commission_rate,
        value.half_spread_rate,
        value.impact_coefficient,
        value.adv_dollars,
    )
    if (
        value.source_sha256 != source_digest
        or parsed != actual
        or value.policy_sha256 != verified_policy.evidence_sha256
    ):
        raise CostModelError("trade-cost evidence differs from registered source/policy")
    return value


@dataclasses.dataclass(frozen=True)
class TradeCostInput:
    trade_id: str
    security_id: str
    delta_dollars: Decimal | str | int | float
    cost_evidence: VerifiedTradeCostEvidence
    terminal_exit_evidence: VerifiedTerminalExitEvidence | None = None

    def __post_init__(self) -> None:
        _canonical_text(self.trade_id, "trade_id")
        security = _canonical_text(self.security_id, "security_id")
        delta = _d(self.delta_dollars, "delta_dollars")
        if type(self.cost_evidence) is not VerifiedTradeCostEvidence:
            raise CostModelError("trade requires typed PIT cost evidence")
        if self.cost_evidence.security_id != security:
            raise CostModelError("trade-cost evidence belongs to another security")
        terminal = self.terminal_exit_evidence
        if terminal is not None:
            terminal = require_terminal_exit_evidence(terminal)
            if terminal.security_id != security:
                raise CostModelError("terminal evidence belongs to another security")
            if delta >= 0:
                raise CostModelError(
                    "terminal evidence applies only to a nonzero risk-reducing exit"
                )
            if delta != terminal.current_long_position_dollars.copy_negate():
                raise CostModelError(
                    "terminal exit delta must exactly liquidate the authenticated long position"
                )
            if (
                terminal.decision_at != self.cost_evidence.decision_at
                or terminal.evidence_epoch_id != self.cost_evidence.evidence_epoch_id
            ):
                raise CostModelError(
                    "terminal and cost evidence must share decision and evidence epoch"
                )
        object.__setattr__(self, "delta_dollars", delta)
        object.__setattr__(self, "terminal_exit_evidence", terminal)


@dataclasses.dataclass(frozen=True)
class CostResult:
    dollars: Decimal
    portfolio_return: Decimal
    one_way_turnover: Decimal


def portfolio_transaction_cost(
    trades: Iterable[TradeCostInput],
    *,
    nav_dollars: object,
    policy: VerifiedAnalystPolicy,
    cost_scenario_bps: object,
    decision_at: str,
    evidence_epoch_id: str,
) -> CostResult:
    """Cost net security target changes in dollars, then divide once by NAV."""
    try:
        verified_policy = require_verified_analyst_policy(policy)
    except FormulaError as exc:
        raise CostModelError("transaction cost requires verified ARV2 policy") from exc
    nav = _d(nav_dollars, "nav_dollars")
    scenario = _d(cost_scenario_bps, "cost_scenario_bps")
    if nav <= 0:
        raise CostModelError("NAV must be positive")
    if scenario not in verified_policy.cost_scenario_bps:
        raise CostModelError("cost scenario is not preregistered in the verified policy")
    expected_decision = _instant(decision_at, "decision_at").isoformat()
    expected_epoch = _canonical_text(evidence_epoch_id, "evidence_epoch_id")

    materialized = tuple(trades)
    seen: set[str] = set()
    by_security: dict[
        str,
        tuple[
            list[Decimal],
            VerifiedTradeCostEvidence,
            VerifiedTerminalExitEvidence | None,
        ],
    ] = {}
    common_context: tuple[str, str] | None = None
    for index, trade in enumerate(materialized):
        if type(trade) is not TradeCostInput:
            raise CostModelError(f"trades[{index}] has the wrong type")
        if trade.trade_id in seen:
            raise CostModelError("trade_id must be unique")
        seen.add(trade.trade_id)
        evidence = require_trade_cost_evidence(
            trade.cost_evidence, policy=verified_policy
        )
        if evidence.security_id != trade.security_id:
            raise CostModelError("trade-cost evidence belongs to another security")
        context = (evidence.evidence_epoch_id, evidence.decision_at)
        if context != (expected_epoch, expected_decision):
            raise CostModelError(
                "trade-cost evidence does not match the requested decision and evidence epoch"
            )
        if common_context is None:
            common_context = context
        elif context != common_context:
            raise CostModelError(
                "all trade-cost evidence must share one decision and evidence epoch"
            )
        terminal = trade.terminal_exit_evidence
        if terminal is not None:
            terminal = require_terminal_exit_evidence(terminal)
            if (
                terminal.security_id != trade.security_id
                or (terminal.evidence_epoch_id, terminal.decision_at) != context
            ):
                raise CostModelError(
                    "terminal evidence must match security, decision, and evidence epoch"
                )
        delta = _d(trade.delta_dollars, "delta_dollars")
        prior = by_security.get(trade.security_id)
        if prior is None:
            by_security[trade.security_id] = ([delta], evidence, terminal)
        else:
            prior_deltas, prior_evidence, prior_terminal = prior
            if (
                prior_evidence.source_sha256 != evidence.source_sha256
                or prior_terminal != terminal
            ):
                raise CostModelError(
                    "split rows for one security must use identical authenticated assumptions"
                )
            nonzero_prior = next(
                (value for value in prior_deltas if value != 0), None
            )
            if (
                nonzero_prior is not None
                and delta != 0
                and (nonzero_prior > 0) != (delta > 0)
            ):
                raise CostModelError(
                    "opposing buy/sell rows cannot be netted out of modeled cost"
                )
            prior_deltas.append(delta)

    with analyst_decimal_context():
        total_cost = Decimal("0")
        turnover_dollars = Decimal("0")
        scenario_rate = scenario / Decimal("10000")
        for security_id in sorted(by_security):
            deltas, evidence, terminal = by_security[security_id]
            delta_signed = _stable_decimal_sum(deltas)
            delta = abs(delta_signed)
            if delta == 0:
                continue
            adv = evidence.adv_dollars
            base_rate = (
                evidence.commission_rate
                + evidence.half_spread_rate
                + scenario_rate
            )
            if adv is None:
                if terminal is None:
                    raise CostModelError(
                        "nonzero trades with missing PIT ADV require authenticated terminal evidence"
                    )
                variable = delta * max(
                    Decimal("1"), base_rate + evidence.impact_coefficient
                )
            else:
                participation = delta / adv
                if (
                    participation > verified_policy.maximum_participation
                    and terminal is None
                ):
                    raise CostModelError(
                        "trade exceeds the verified-policy participation cap"
                    )
                variable = delta * (
                    base_rate + evidence.impact_coefficient * participation.sqrt()
                )
            total_cost += max(verified_policy.minimum_fee_dollars, variable)
            turnover_dollars += delta
        return CostResult(
            dollars=total_cost,
            portfolio_return=total_cost / nav,
            one_way_turnover=turnover_dollars / nav,
        )
