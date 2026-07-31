"""Privacy-controlled projection of deterministic trading state."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import re
from typing import Any, Mapping

from assistant.llm.schemas import (
    CommitteeFact,
    CommitteeInput,
    CommitteeSubject,
    FactAvailability,
    PrivacyMode,
)
from assistant.schemas import DecisionPacket, EvidenceStatus

_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SAFE_ID_CHARACTERS = re.compile(r"[^a-z0-9_.-]+")


class ProjectionError(ValueError):
    """The deterministic input cannot safely be projected for model review."""


def _clean_text(value: Any, *, maximum: int = 1_500) -> str:
    text = _CONTROL_CHARACTERS.sub(" ", str(value))
    text = " ".join(text.split())
    return text[:maximum]


def _finite_number(value: Any, *, name: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProjectionError(f"{name} must be numeric.")
    if not math.isfinite(float(value)):
        raise ProjectionError(f"{name} must be finite.")
    return value


def _source_id(prefix: str, key: str) -> str:
    safe_key = _SAFE_ID_CHARACTERS.sub("-", key.lower()).strip("-")
    if not safe_key:
        safe_key = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}.{safe_key}"[:120]


def _packet_id(
    packet: DecisionPacket,
    privacy_mode: PrivacyMode,
    facts: tuple[CommitteeFact, ...],
) -> str:
    """Content identity over the privacy projection, never the raw packet.

    Hashing ``packet.to_dict()`` would avoid displaying account/order fields,
    but would still make the exported ID a stable derivative of data the
    selected privacy mode promised to omit.  The identity therefore covers
    only metadata and facts that are already permitted in the projection.
    """
    canonical = json.dumps(
        {
            "packet_schema_version": packet.schema_version,
            "generated_at": packet.generated_at,
            "policy_version": packet.policy_version,
            "privacy_mode": privacy_mode.value,
            "facts": [fact.to_dict() for fact in facts],
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return "dp_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def _proposal_mapping(proposal: Any) -> Mapping[str, Any]:
    if isinstance(proposal, Mapping):
        return proposal
    to_dict = getattr(proposal, "to_dict", None)
    if callable(to_dict):
        result = to_dict()
        if isinstance(result, Mapping):
            return result
    if dataclasses.is_dataclass(proposal):
        return dataclasses.asdict(proposal)
    raise ProjectionError("proposal must be a mapping or expose to_dict().")


def _rounded_dollars(value: int | float) -> float:
    # Deliberately coarse: rounded mode communicates scale while reducing the
    # chance of reconstructing exact account values.
    return float(round(float(value) / 100.0) * 100.0)


def _availability_for_signal(status: EvidenceStatus) -> FactAvailability:
    if status == EvidenceStatus.UNAVAILABLE:
        return FactAvailability.UNAVAILABLE
    return FactAvailability.AVAILABLE


def project_committee_input(
    packet: DecisionPacket,
    proposal: Any,
    *,
    privacy_mode: PrivacyMode = PrivacyMode.PERCENTAGES_ONLY,
) -> CommitteeInput:
    """Build a model-safe review input from precomputed values only.

    The function intentionally accepts only an existing risk-reducing sell
    proposal.  It never creates a proposal, computes a quantity, changes
    policy, or imports execution/broker code.  Account IDs, API metadata, raw
    broker objects, and order identifiers are omitted in every privacy mode.
    """

    if not isinstance(privacy_mode, PrivacyMode):
        try:
            privacy_mode = PrivacyMode(privacy_mode)
        except ValueError as exc:
            raise ProjectionError(f"Unsupported privacy mode: {privacy_mode!r}.") from exc

    raw_proposal = _proposal_mapping(proposal)
    proposal_id = _clean_text(raw_proposal.get("proposal_id", ""), maximum=200)
    if not proposal_id:
        raise ProjectionError("proposal.proposal_id is required.")
    evidence_status = _clean_text(
        raw_proposal.get("evidence_status", ""), maximum=200
    )
    if evidence_status != "deterministic_risk_policy":
        raise ProjectionError(
            "committee MVP accepts only deterministic risk-policy proposals."
        )
    intent = raw_proposal.get("intent")
    if not isinstance(intent, Mapping):
        raise ProjectionError("proposal.intent must be an object.")
    side = str(intent.get("side", "")).lower()
    ticker = str(intent.get("ticker", "")).upper()
    if side != "sell" or not ticker:
        raise ProjectionError(
            "committee MVP accepts only existing risk-reducing sell proposals."
        )
    impact = raw_proposal.get("expected_impact")
    if not isinstance(impact, Mapping):
        raise ProjectionError("proposal.expected_impact must be an object.")
    before = _finite_number(
        impact.get("position_weight_before_pct"),
        name="proposal.expected_impact.position_weight_before_pct",
    )
    after = _finite_number(
        impact.get("position_weight_after_pct"),
        name="proposal.expected_impact.position_weight_after_pct",
    )
    if float(after) >= float(before):
        raise ProjectionError(
            "committee MVP refuses proposals that do not reduce position weight."
        )

    facts: list[CommitteeFact] = []

    def add(
        source_id: str,
        category: str,
        label: str,
        value: str | int | float | bool | None,
        *,
        unit: str | None = None,
        as_of: str | None = None,
        availability: FactAvailability = FactAvailability.AVAILABLE,
        detail: str = "",
        tickers: tuple[str, ...] = (),
        production_authoritative: bool = True,
        critical: bool = False,
    ) -> None:
        if isinstance(value, float) and not math.isfinite(value):
            raise ProjectionError(f"{source_id} contains a non-finite value.")
        facts.append(
            CommitteeFact(
                source_id=source_id,
                category=category,
                label=_clean_text(label, maximum=200),
                value=value,
                unit=unit,
                as_of=_clean_text(as_of, maximum=100) if as_of else None,
                availability=availability,
                detail=_clean_text(detail),
                tickers=tuple(str(value).upper() for value in tickers),
                production_authoritative=production_authoritative,
                critical=critical,
            )
        )

    analytics = packet.analytics
    percent_metrics = {
        "metric.invested_pct": ("Portfolio invested", analytics.get("invested_pct")),
        "metric.unrealized_pnl_pct": (
            "Portfolio unrealized return",
            analytics.get("unrealized_pnl_pct"),
        ),
        "metric.cash_pct": ("Portfolio cash", packet.risk.cash_pct),
        "metric.largest_position_pct": (
            "Largest position",
            packet.risk.largest_single_position_pct,
        ),
        "metric.leveraged_etf_exposure_pct": (
            "Leveraged ETF exposure",
            packet.risk.leveraged_etf_exposure_pct,
        ),
    }
    for source_id, (label, value) in percent_metrics.items():
        if value is None:
            continue
        add(
            source_id,
            "portfolio_metric",
            label,
            _finite_number(value, name=source_id),
            unit="percent",
            as_of=packet.portfolio.as_of,
        )

    for ticker_key, value in sorted(
        (analytics.get("position_weights_pct") or {}).items()
    ):
        ticker_key = str(ticker_key).upper()
        add(
            _source_id("holding", f"{ticker_key}.weight_pct"),
            "holding_metric",
            f"{ticker_key} portfolio weight",
            _finite_number(value, name=f"position_weights_pct.{ticker_key}"),
            unit="percent",
            as_of=packet.portfolio.as_of,
            tickers=(ticker_key,),
        )

    for basket, value in sorted(packet.risk.basket_exposure_pct.items()):
        add(
            _source_id("basket", basket),
            "basket_metric",
            f"{basket} exposure",
            _finite_number(value, name=f"basket_exposure_pct.{basket}"),
            unit="percent",
            as_of=packet.portfolio.as_of,
        )

    add(
        "regime.trend",
        "market_regime",
        f"{packet.regime.benchmark_ticker} trend",
        packet.regime.trend if packet.regime.trend is not None else "unavailable",
        as_of=packet.regime.as_of,
        availability=(
            FactAvailability.AVAILABLE
            if packet.regime.trend is not None
            else FactAvailability.UNAVAILABLE
        ),
        tickers=(packet.regime.benchmark_ticker.upper(),),
        production_authoritative=packet.regime.trend is not None,
        critical=packet.regime.trend is None,
    )
    add(
        "regime.volatility",
        "market_regime",
        f"{packet.regime.benchmark_ticker} volatility regime",
        (
            packet.regime.volatility_regime
            if packet.regime.volatility_regime is not None
            else "unavailable"
        ),
        as_of=packet.regime.as_of,
        availability=(
            FactAvailability.AVAILABLE
            if packet.regime.volatility_regime is not None
            else FactAvailability.UNAVAILABLE
        ),
        tickers=(packet.regime.benchmark_ticker.upper(),),
        production_authoritative=packet.regime.volatility_regime is not None,
        critical=packet.regime.volatility_regime is None,
    )
    if packet.regime.trailing_volatility_pct is not None:
        add(
            "regime.trailing_volatility_pct",
            "market_regime",
            f"{packet.regime.benchmark_ticker} trailing volatility",
            _finite_number(
                packet.regime.trailing_volatility_pct,
                name="regime.trailing_volatility_pct",
            ),
            unit="percent",
            as_of=packet.regime.as_of,
            tickers=(packet.regime.benchmark_ticker.upper(),),
        )

    for index, signal in enumerate(packet.signals):
        authoritative_support = (
            signal.status
            in (EvidenceStatus.CONFIRMED, EvidenceStatus.PROMISING_UNCONFIRMED)
            and signal.production_authoritative
        )
        add(
            _source_id("research", f"{index}.{signal.label}"),
            "research",
            signal.label,
            signal.status.value,
            availability=_availability_for_signal(signal.status),
            detail=f"{signal.claim} {_clean_text(signal.detail)}",
            tickers=tuple(signal.relevant_tickers),
            production_authoritative=authoritative_support,
            critical=False,
        )

    for index, event in enumerate(packet.upcoming_events):
        available = event.status != EvidenceStatus.UNAVAILABLE
        add(
            _source_id("event", f"{index}.{event.ticker}.{event.event_type}"),
            "event",
            f"{event.ticker} {event.event_type}",
            event.event_date if event.event_date is not None else "unavailable",
            as_of=event.fetched_at,
            availability=(
                FactAvailability.AVAILABLE
                if available
                else FactAvailability.UNAVAILABLE
            ),
            detail=(
                f"days away: {event.days_away}"
                if event.days_away is not None
                else "days away unavailable"
            ),
            tickers=(event.ticker,),
            production_authoritative=available,
            critical=False,
        )

    for warning in packet.warnings:
        digest = hashlib.sha256(warning.encode("utf-8")).hexdigest()[:12]
        add(
            f"warning.{digest}",
            "warning",
            "Deterministic warning",
            "material",
            detail=warning,
            production_authoritative=True,
            critical=True,
        )

    for key, value in sorted(packet.data_freshness.items()):
        availability = (
            FactAvailability.UNAVAILABLE
            if value is None or str(value).strip().lower() in {"", "none", "unavailable"}
            else FactAvailability.AVAILABLE
        )
        add(
            _source_id("freshness", key),
            "data_freshness",
            key.replace("_", " "),
            _clean_text(value),
            availability=availability,
            production_authoritative=availability == FactAvailability.AVAILABLE,
            critical=availability != FactAvailability.AVAILABLE,
        )

    if privacy_mode != PrivacyMode.PERCENTAGES_ONLY:
        dollar_values = {
            "value.total_equity": ("Total equity", packet.portfolio.total_equity),
            "value.cash": ("Cash value", packet.portfolio.cash),
            "value.invested": ("Invested value", analytics.get("invested_value")),
            "value.unrealized_pnl": (
                "Unrealized profit or loss",
                analytics.get("unrealized_pnl"),
            ),
        }
        for source_id, (label, raw_value) in dollar_values.items():
            if raw_value is None:
                continue
            value = _finite_number(raw_value, name=source_id)
            if privacy_mode == PrivacyMode.ROUNDED_DOLLARS:
                value = _rounded_dollars(value)
            add(
                source_id,
                "portfolio_value",
                label,
                value,
                unit="USD",
                as_of=packet.portfolio.as_of,
            )

    packet_facts = tuple(facts)
    candidate_ids: list[str] = []

    def add_candidate(
        source_id: str,
        label: str,
        value: str | int | float | bool | None,
        *,
        unit: str | None = None,
        detail: str = "",
    ) -> None:
        add(
            source_id,
            "candidate",
            label,
            value,
            unit=unit,
            as_of=raw_proposal.get("created_at"),
            detail=detail,
            tickers=(ticker,),
        )
        candidate_ids.append(source_id)

    add_candidate("candidate.side", "Candidate side", side)
    add_candidate("candidate.ticker", "Candidate ticker", ticker)
    add_candidate(
        "candidate.position_weight_before_pct",
        f"{ticker} weight before candidate",
        before,
        unit="percent",
    )
    add_candidate(
        "candidate.position_weight_after_pct",
        f"{ticker} weight after candidate",
        after,
        unit="percent",
    )
    for key, value in sorted(impact.items()):
        if key in {"position_weight_before_pct", "position_weight_after_pct"}:
            continue
        if key.endswith("_pct") and isinstance(value, (int, float)) and not isinstance(value, bool):
            add_candidate(
                _source_id("candidate", key),
                key.replace("_", " "),
                _finite_number(value, name=f"candidate.{key}"),
                unit="percent",
            )
        elif (
            privacy_mode != PrivacyMode.PERCENTAGES_ONLY
            and key in {"trade_value", "cash_before", "cash_after"}
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
        ):
            number = _finite_number(value, name=f"candidate.{key}")
            if privacy_mode == PrivacyMode.ROUNDED_DOLLARS:
                number = _rounded_dollars(number)
            add_candidate(
                _source_id("candidate", key),
                key.replace("_", " "),
                number,
                unit="USD",
            )

    add_candidate(
        "candidate.evidence_status",
        "Candidate evidence status",
        evidence_status,
    )

    source_ids = [fact.source_id for fact in facts]
    if len(source_ids) != len(set(source_ids)):
        raise ProjectionError("committee projection produced duplicate source IDs.")

    portfolio_tickers = {
        position.ticker.upper() for position in packet.portfolio.positions
    }
    portfolio_tickers.add(ticker)
    portfolio_tickers.add(packet.regime.benchmark_ticker.upper())
    return CommitteeInput(
        packet_id=_packet_id(packet, privacy_mode, packet_facts),
        packet_schema_version=packet.schema_version,
        generated_at=packet.generated_at,
        policy_version=packet.policy_version,
        privacy_mode=privacy_mode,
        portfolio_tickers=tuple(sorted(portfolio_tickers)),
        facts=tuple(facts),
        subject=CommitteeSubject(
            proposal_id=proposal_id,
            action_type="risk_reduction",
            ticker=ticker,
            side=side,
            evidence_status=evidence_status,
            source_ids=tuple(candidate_ids),
        ),
    )
