"""Contract, privacy, grounding, and isolation tests for the committee MVP."""
from __future__ import annotations

import ast
import dataclasses
import json
from pathlib import Path

import pytest

from assistant.llm.committee import run_committee_review
from assistant.llm.projection import ProjectionError, project_committee_input
from assistant.llm.schemas import (
    CommitteeReview,
    CommitteeSchemaError,
    PrivacyMode,
    ReviewStatus,
)
from assistant.llm.validators import validate_committee_review
from assistant.schemas import (
    DecisionPacket,
    EvidenceStatus,
    MarketRegime,
    PortfolioPosition,
    PortfolioSnapshot,
    RiskExposure,
    SignalEvidence,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _packet(*, warnings=(), signals=()) -> DecisionPacket:
    return DecisionPacket(
        generated_at="2026-07-30T15:00:00+00:00",
        portfolio=PortfolioSnapshot(
            positions=[
                PortfolioPosition(
                    ticker="NVDA",
                    shares=10,
                    entry_price=100.0,
                    current_price=200.0,
                    market_value=2_000.0,
                    unrealized_pnl_pct=100.0,
                    is_leveraged_etf=False,
                )
            ],
            cash=2_000.0,
            total_equity=4_000.0,
            as_of="2026-07-30T14:59:00+00:00",
            buying_power=2_000.0,
            source="alpaca",
            account_mode="paper",
            account_id="sensitive-account-id",
        ),
        risk=RiskExposure(
            basket_exposure_pct={"semiconductors": 50.0},
            leveraged_etf_exposure_pct=50.0,
            cash_pct=50.0,
            largest_single_position_pct=50.0,
            concentration_warnings=[],
        ),
        regime=MarketRegime(
            benchmark_ticker="QQQ",
            trend="uptrend",
            volatility_regime="low_vol",
            trailing_volatility_pct=18.0,
            as_of="2026-07-30",
        ),
        signals=list(signals),
        upcoming_events=[],
        warnings=list(warnings),
        policy_version="paper-v1",
        analytics={
            "available": True,
            "position_count": 1,
            "invested_value": 2_000.0,
            "invested_pct": 50.0,
            "cash_value": 2_000.0,
            "unrealized_pnl": 1_000.0,
            "unrealized_pnl_pct": 100.0,
            "position_weights_pct": {"NVDA": 50.0},
            "open_order_count": 0,
        },
        data_freshness={
            "portfolio_as_of": "2026-07-30T14:59:00+00:00",
            "market_regime_as_of": "2026-07-30",
        },
    )


def _proposal(*, side="sell", before=50.0, after=25.0) -> dict:
    return {
        "proposal_id": "tp_test",
        "created_at": "2026-07-30T15:00:00+00:00",
        "evidence_status": "deterministic_risk_policy",
        "intent": {
            "ticker": "NVDA",
            "side": side,
            "shares": 5,
            "order_type": "market",
            "rationale": "risk reduction",
        },
        "reference_price": 200.0,
        "expected_impact": {
            "trade_value": 1_000.0,
            "position_weight_before_pct": before,
            "position_weight_after_pct": after,
            "cash_before": 2_000.0,
            "cash_after": 3_000.0,
            "invested_pct_after": 25.0,
        },
    }


def _valid_raw_review() -> dict:
    return {
        "verdict": "support_with_caution",
        "summary": {
            "text": (
                "The current leveraged ETF exposure is 50 percent; NVDA weight "
                "is 50 percent before and 25 percent after the existing candidate."
            ),
            "source_ids": [
                "metric.leveraged_etf_exposure_pct",
                "candidate.position_weight_before_pct",
                "candidate.position_weight_after_pct",
            ],
        },
        "supporting_points": [
            {
                "text": "NVDA weight is 50 percent before and 25 percent after the candidate.",
                "source_ids": [
                    "candidate.position_weight_before_pct",
                    "candidate.position_weight_after_pct",
                ],
            }
        ],
        "counterarguments": [
            {
                "text": "QQQ is in an uptrend.",
                "source_ids": ["regime.trend"],
            }
        ],
        "hidden_risks": [],
        "data_quality_warnings": [],
        "invalidation_conditions": [
            {
                "text": "This view no longer applies if the cited 50 percent exposure is stale.",
                "source_ids": ["metric.leveraged_etf_exposure_pct"],
            }
        ],
        "revision_requests": [],
        "confidence_label": "moderate",
        "confidence_basis": {
            "text": "The cited portfolio metrics are available.",
            "source_ids": ["metric.leveraged_etf_exposure_pct"],
        },
    }


def _codes(report) -> set[str]:
    return {issue.code for issue in report.issues}


def test_percentages_only_projection_omits_account_and_exact_values():
    projected = project_committee_input(_packet(), _proposal())
    serialized = json.dumps(projected.to_dict(), sort_keys=True)

    assert projected.privacy_mode == PrivacyMode.PERCENTAGES_ONLY
    assert "sensitive-account-id" not in serialized
    assert "account_id" not in serialized
    assert '"shares"' not in serialized
    assert '"reference_price"' not in serialized
    assert all(
        fact.category not in {"portfolio_value"}
        for fact in projected.facts
    )
    assert "candidate.trade_value" not in projected.fact_by_id


def test_exact_mode_exposes_selected_values_but_never_account_metadata():
    projected = project_committee_input(
        _packet(), _proposal(), privacy_mode=PrivacyMode.EXACT_DOLLARS
    )
    serialized = json.dumps(projected.to_dict(), sort_keys=True)

    assert projected.fact_by_id["value.total_equity"].value == 4_000.0
    assert projected.fact_by_id["candidate.trade_value"].value == 1_000.0
    assert "sensitive-account-id" not in serialized
    assert "account_id" not in serialized


def test_packet_identity_is_stable_and_content_addressed():
    first = project_committee_input(_packet(), _proposal())
    same = project_committee_input(_packet(), _proposal())
    changed = project_committee_input(
        dataclasses.replace(_packet(), policy_version="paper-v2"), _proposal()
    )

    assert first.packet_id == same.packet_id
    assert first.packet_id != changed.packet_id


def test_percentages_only_packet_identity_does_not_derive_from_account_id():
    first_packet = _packet()
    other_account = dataclasses.replace(
        first_packet,
        portfolio=dataclasses.replace(
            first_packet.portfolio, account_id="a-different-sensitive-account"
        ),
    )
    first = project_committee_input(first_packet, _proposal())
    second = project_committee_input(other_account, _proposal())
    assert first.packet_id == second.packet_id


def test_projection_refuses_buys_and_non_reducing_sells():
    with pytest.raises(ProjectionError, match="risk-reducing sell"):
        project_committee_input(_packet(), _proposal(side="buy"))
    with pytest.raises(ProjectionError, match="do not reduce"):
        project_committee_input(_packet(), _proposal(before=50.0, after=50.0))


def test_projection_rejects_non_finite_financial_values():
    packet = dataclasses.replace(
        _packet(),
        risk=dataclasses.replace(_packet().risk, cash_pct=float("nan")),
    )
    with pytest.raises(ProjectionError, match="finite"):
        project_committee_input(packet, _proposal())


def test_valid_grounded_review_is_accepted():
    committee_input = project_committee_input(_packet(), _proposal())
    review = CommitteeReview.from_mapping(_valid_raw_review())
    report = validate_committee_review(committee_input, review)
    assert report.accepted, report.issues


def test_number_must_appear_in_the_exact_sources_cited_by_the_point():
    raw = _valid_raw_review()
    raw["supporting_points"][0] = {
        "text": "Cash is 25 percent.",
        "source_ids": ["metric.cash_pct"],
    }
    report = validate_committee_review(
        project_committee_input(_packet(), _proposal()),
        CommitteeReview.from_mapping(raw),
    )
    assert "unsupported_number" in _codes(report)


def test_unknown_source_and_ticker_fail_closed():
    raw = _valid_raw_review()
    raw["counterarguments"][0] = {
        "text": "TSLA is in an uptrend.",
        "source_ids": ["regime.trend"],
    }
    raw["confidence_basis"]["source_ids"] = ["invented.source"]
    report = validate_committee_review(
        project_committee_input(_packet(), _proposal()),
        CommitteeReview.from_mapping(raw),
    )
    assert {"unknown_source_id", "unsupported_ticker_or_acronym"} <= _codes(report)


def test_rejected_research_cannot_support_an_endorsement():
    signal = SignalEvidence(
        label="Rejected alpha claim",
        claim="This signal predicts excess return.",
        status=EvidenceStatus.REJECTED,
        detail="The claim failed validation.",
        source="research_findings.json",
        relevant_tickers=["NVDA"],
    )
    committee_input = project_committee_input(
        _packet(signals=[signal]), _proposal()
    )
    research_id = next(
        fact.source_id for fact in committee_input.facts if fact.category == "research"
    )
    raw = _valid_raw_review()
    raw["supporting_points"][0] = {
        "text": "The research claim failed validation.",
        "source_ids": [research_id],
    }
    report = validate_committee_review(
        committee_input, CommitteeReview.from_mapping(raw)
    )
    assert "non_authoritative_support" in _codes(report)

    raw = _valid_raw_review()
    raw["summary"] = {
        "text": "The research claim failed validation.",
        "source_ids": [research_id],
    }
    report = validate_committee_review(
        committee_input, CommitteeReview.from_mapping(raw)
    )
    assert "non_authoritative_support" in _codes(report)


def test_critical_warning_must_be_visible_in_data_quality_warnings():
    committee_input = project_committee_input(
        _packet(warnings=["Open-order state is unavailable."]), _proposal()
    )
    report = validate_committee_review(
        committee_input, CommitteeReview.from_mapping(_valid_raw_review())
    )
    assert "concealed_critical_warning" in _codes(report)

    warning_id = next(
        fact.source_id for fact in committee_input.facts if fact.category == "warning"
    )
    raw = _valid_raw_review()
    raw["data_quality_warnings"] = [
        {
            "text": "Open-order state is unavailable.",
            "source_ids": [warning_id],
        }
    ]
    assert validate_committee_review(
        committee_input, CommitteeReview.from_mapping(raw)
    ).accepted


def test_unavailable_event_fact_is_critical_and_must_be_visible():
    # Independent review, 2026-07-31 (P2 #7): event facts (earnings/
    # ex-dividend) used to be hardcoded critical=False regardless of
    # availability, unlike regime.trend/regime.volatility/data_freshness
    # facts -- an unavailable event date could be silently omitted from
    # data_quality_warnings without tripping this same fail-closed check.
    from assistant.schemas import UpcomingEvent

    packet = dataclasses.replace(
        _packet(),
        upcoming_events=[
            UpcomingEvent(
                ticker="NVDA",
                event_type="earnings",
                days_away=None,
                status=EvidenceStatus.UNAVAILABLE,
            )
        ],
    )
    committee_input = project_committee_input(packet, _proposal())
    event_fact = next(
        fact for fact in committee_input.facts if fact.category == "event"
    )
    assert event_fact.critical is True

    report = validate_committee_review(
        committee_input, CommitteeReview.from_mapping(_valid_raw_review())
    )
    assert "concealed_critical_warning" in _codes(report)

    raw = _valid_raw_review()
    raw["data_quality_warnings"] = [
        {"text": "Earnings date is unavailable.", "source_ids": [event_fact.source_id]}
    ]
    assert validate_committee_review(
        committee_input, CommitteeReview.from_mapping(raw)
    ).accepted


def test_portfolio_change_language_is_rejected_even_when_sources_are_real():
    raw = _valid_raw_review()
    raw["summary"]["text"] = "Sell NVDA because its current weight is 50 percent."
    report = validate_committee_review(
        project_committee_input(_packet(), _proposal()),
        CommitteeReview.from_mapping(raw),
    )
    assert "forbidden_action_language" in _codes(report)


def test_schema_rejects_additional_fields_and_malformed_points():
    raw = _valid_raw_review()
    raw["winner"] = "model"
    with pytest.raises(CommitteeSchemaError, match="extra"):
        CommitteeReview.from_mapping(raw)

    raw = _valid_raw_review()
    raw["summary"] = "not a cited point"
    with pytest.raises(CommitteeSchemaError):
        CommitteeReview.from_mapping(raw)


class _FakeProvider:
    provider_id = "fake"
    model_id = "fake-v1"

    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = 0

    def complete_json(self, **kwargs):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.response


def test_committee_service_accepts_only_validated_output():
    provider = _FakeProvider(_valid_raw_review())
    result = run_committee_review(
        project_committee_input(_packet(), _proposal()), provider
    )
    assert result.status == ReviewStatus.ACCEPTED
    assert result.accepted
    assert provider.calls == 1

    bad = _valid_raw_review()
    bad["summary"]["text"] = "NVDA weight is 99 percent."
    result = run_committee_review(
        project_committee_input(_packet(), _proposal()), _FakeProvider(bad)
    )
    assert result.status == ReviewStatus.REVIEW_UNAVAILABLE
    assert result.error_code == "validation_rejected"
    assert result.review is None


def test_committee_service_maps_provider_and_timeout_failures_to_unavailable():
    committee_input = project_committee_input(_packet(), _proposal())
    failed = run_committee_review(
        committee_input, _FakeProvider(error=TimeoutError("late"))
    )
    assert failed.status == ReviewStatus.REVIEW_UNAVAILABLE
    assert failed.error_code == "provider_error"

    invalid_timeout = run_committee_review(
        committee_input, _FakeProvider(_valid_raw_review()), timeout_seconds=float("nan")
    )
    assert invalid_timeout.error_code == "invalid_timeout"


def test_llm_package_has_no_direct_execution_or_proposal_authority_imports():
    forbidden = {
        "execution",
        "risk",
        "assistant.execution_service",
        "assistant.proposals",
        "assistant.strategy_proposals",
        "assistant.allocation_proposals",
        "assistant.policy",
    }
    offenders = []
    for path in (REPO_ROOT / "assistant" / "llm").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if any(name == item or name.startswith(item + ".") for item in forbidden):
                    offenders.append(f"{path.name}: {name}")
    assert not offenders, offenders
