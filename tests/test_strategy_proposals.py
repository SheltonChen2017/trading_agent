"""Tests for assistant/strategy_proposals.py -- the SOXX/SOXL wide-band
rebalance proposal generator. Uses hand-injected market_data (no
network) so results are deterministic and independently verifiable
against the same underlying regime/vol-target functions the generator
itself calls."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from assistant.context_builder import build_portfolio_snapshot, build_risk_exposure
from assistant.policy import TradingPolicy
from assistant.schemas import DecisionPacket, EvidenceStatus, FindingProvenance, MarketRegime, SignalEvidence
import assistant.strategy_proposals as strategy_proposals
from assistant.strategy_proposals import (
    LEVERAGED_TICKER,
    PRODUCTION_PARAMS,
    STABLE_TICKER,
    generate_soxx_soxl_rebalance_proposals,
)
from market_analytics import classify_trend
from signals.regime import compute_trailing_market_volatility
from strategies.vol_target_rotation import compute_target_leveraged_weight


def _price_history(days: int = 260, seed: int = 0, drift: float = 0.001, vol: float = 0.02) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(loc=drift, scale=vol, size=days)
    close = 50 * np.cumprod(1 + returns)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
    return pd.DataFrame(
        {"open": close, "high": close * 1.001, "low": close * 0.999, "close": close, "volume": np.full(days, 1_000_000.0)},
        index=dates,
    )


def _market_data(days: int = 260):
    return {STABLE_TICKER: _price_history(days=days, seed=1, drift=0.0015), LEVERAGED_TICKER: _price_history(days=days, seed=2, drift=0.001)}


def _expected_target(market_data: dict) -> tuple[float, pd.Timestamp]:
    stable_close = market_data[STABLE_TICKER]["close"]
    leveraged_close = market_data[LEVERAGED_TICKER]["close"]
    as_of = min(stable_close.index[-1], leveraged_close.index[-1])
    trend = classify_trend(stable_close, as_of, lookback_days=PRODUCTION_PARAMS["trend_lookback_days"])
    if trend == "downtrend":
        return 0.0, as_of
    vol = compute_trailing_market_volatility(
        pd.DataFrame({"close": leveraged_close}), as_of, lookback_days=PRODUCTION_PARAMS["vol_lookback_days"]
    )
    return compute_target_leveraged_weight(
        vol, PRODUCTION_PARAMS["target_vol_pct"], PRODUCTION_PARAMS["max_leveraged_weight"]
    ), as_of


def _packet(positions: list[dict], cash: float = 5_000.0) -> DecisionPacket:
    snapshot = build_portfolio_snapshot(positions, cash=cash)
    return DecisionPacket(
        generated_at="2026-07-26T12:00:00+00:00",
        portfolio=snapshot,
        risk=build_risk_exposure(snapshot),
        regime=MarketRegime(
            benchmark_ticker="QQQ", trend="uptrend", volatility_regime="low_vol",
            trailing_volatility_pct=1.0, as_of="2026-07-25",
        ),
        signals=[], upcoming_events=[], warnings=[], policy_version="test",
    )


def _policy(max_order_value: float = 50_000.0) -> TradingPolicy:
    return TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=1.0, max_total_exposure_pct=1.0, max_basket_pct=1.0,
        max_leveraged_etf_pct=1.0, min_cash_reserve_pct=0.0, max_order_value=max_order_value,
    )


def test_returns_nothing_when_leveraged_leg_not_held():
    packet = _packet([{"ticker": STABLE_TICKER, "shares": 100, "entry_price": 50.0, "current_price": 50.0}])
    proposals = generate_soxx_soxl_rebalance_proposals(packet, _policy(), market_data=_market_data())
    assert proposals == []


def test_returns_nothing_when_stable_leg_not_held():
    packet = _packet([{"ticker": LEVERAGED_TICKER, "shares": 100, "entry_price": 20.0, "current_price": 20.0}])
    proposals = generate_soxx_soxl_rebalance_proposals(packet, _policy(), market_data=_market_data())
    assert proposals == []


def test_returns_nothing_when_within_band():
    market_data = _market_data()
    target, _ = _expected_target(market_data)
    combined = 10_000.0
    leveraged_value = combined * target  # exactly on target -> zero drift
    stable_value = combined - leveraged_value
    packet = _packet(
        [
            {"ticker": STABLE_TICKER, "shares": stable_value / 50.0, "entry_price": 50.0, "current_price": 50.0},
            {"ticker": LEVERAGED_TICKER, "shares": leveraged_value / 20.0 if leveraged_value else 0.0, "entry_price": 20.0, "current_price": 20.0},
        ]
    )
    proposals = generate_soxx_soxl_rebalance_proposals(packet, _policy(), market_data=market_data)
    assert proposals == []


def test_proposes_sell_when_overweight_leveraged():
    market_data = _market_data()
    target, _ = _expected_target(market_data)
    overweight = min(target + 0.30, 0.95)
    combined = 10_000.0
    leveraged_value = combined * overweight
    stable_value = combined - leveraged_value
    leveraged_price = 20.0
    packet = _packet(
        [
            {"ticker": STABLE_TICKER, "shares": stable_value / 50.0, "entry_price": 50.0, "current_price": 50.0},
            {"ticker": LEVERAGED_TICKER, "shares": leveraged_value / leveraged_price, "entry_price": leveraged_price, "current_price": leveraged_price},
        ]
    )
    proposals = generate_soxx_soxl_rebalance_proposals(packet, _policy(), market_data=market_data)
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.intent.ticker == LEVERAGED_TICKER
    assert proposal.intent.side == "sell"
    assert proposal.intent.shares > 0
    assert proposal.evidence_status == "promising_unconfirmed_strategy"
    # Never claim this beats buy-and-hold -- that's an established REJECTED claim.
    assert any("buy-and-hold" in u for u in proposal.uncertainties)


def test_sell_proposal_is_capped_by_max_order_value():
    # GPT review, 2026-07-31: the sell branch used to size against the
    # FULL excess with no max_order_value cap at all, unlike the buy
    # branch -- since the execution gate's MAX_ORDER_VALUE check applies
    # to sells too, an uncapped sell proposal for a large excess would
    # always be rejected at approval time and (being fully deterministic)
    # regenerate identically forever.
    market_data = _market_data()
    target, _ = _expected_target(market_data)
    overweight = min(target + 0.30, 0.95)
    combined = 1_000_000.0  # large account -> large dollar excess
    leveraged_value = combined * overweight
    stable_value = combined - leveraged_value
    leveraged_price = 20.0
    tiny_max_order_value = 1_000.0  # far smaller than the real dollar excess
    packet = _packet(
        [
            {"ticker": STABLE_TICKER, "shares": stable_value / 50.0, "entry_price": 50.0, "current_price": 50.0},
            {"ticker": LEVERAGED_TICKER, "shares": leveraged_value / leveraged_price, "entry_price": leveraged_price, "current_price": leveraged_price},
        ]
    )
    policy = _policy(max_order_value=tiny_max_order_value)
    proposals = generate_soxx_soxl_rebalance_proposals(packet, policy, market_data=market_data)
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.intent.side == "sell"
    assert proposal.intent.shares > 0
    notional = proposal.intent.shares * proposal.reference_price
    assert notional <= tiny_max_order_value + 1e-6, "sell notional must respect policy.max_order_value"


def test_proposes_buy_when_underweight_leveraged():
    market_data = _market_data()
    target, _ = _expected_target(market_data)
    if target <= 0.05:
        return  # downtrend/near-zero target -> underweight case isn't meaningful here
    underweight = max(target - 0.30, 0.0)
    combined = 10_000.0
    leveraged_value = combined * underweight
    stable_value = combined - leveraged_value
    leveraged_price = 20.0
    packet = _packet(
        [
            {"ticker": STABLE_TICKER, "shares": stable_value / 50.0, "entry_price": 50.0, "current_price": 50.0},
            {"ticker": LEVERAGED_TICKER, "shares": leveraged_value / leveraged_price if leveraged_value else 1.0, "entry_price": leveraged_price, "current_price": leveraged_price},
        ],
        cash=20_000.0,
    )
    proposals = generate_soxx_soxl_rebalance_proposals(packet, _policy(), market_data=market_data)
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.intent.ticker == LEVERAGED_TICKER
    assert proposal.intent.side == "buy"
    assert proposal.intent.shares > 0


def test_evidence_status_is_never_confirmed():
    # Hard guard against ever silently upgrading this to "confirmed" --
    # the frozen production params were selected on full history, not an
    # out-of-sample split, and the mechanism itself has no confirmed CAGR
    # edge over buy-and-hold on this pair.
    market_data = _market_data()
    target, _ = _expected_target(market_data)
    overweight = min(target + 0.30, 0.95)
    combined = 10_000.0
    leveraged_value = combined * overweight
    stable_value = combined - leveraged_value
    packet = _packet(
        [
            {"ticker": STABLE_TICKER, "shares": stable_value / 50.0, "entry_price": 50.0, "current_price": 50.0},
            {"ticker": LEVERAGED_TICKER, "shares": leveraged_value / 20.0, "entry_price": 20.0, "current_price": 20.0},
        ]
    )
    proposals = generate_soxx_soxl_rebalance_proposals(packet, _policy(), market_data=market_data)
    assert proposals
    for proposal in proposals:
        assert proposal.evidence_status != "confirmed"


# --- Research-authority disclosure (GPT review, 2026-07-29): this
# module relies on 2 CONFIRMED findings for its wide-band mechanism --
# reliance on their current production authority must be an explicit,
# checked fact surfaced in `uncertainties`, not just docstring prose.

def _overweight_packet_and_market_data():
    market_data = _market_data()
    target, _ = _expected_target(market_data)
    overweight = min(target + 0.30, 0.95)
    combined = 10_000.0
    leveraged_value = combined * overweight
    stable_value = combined - leveraged_value
    packet = _packet(
        [
            {"ticker": STABLE_TICKER, "shares": stable_value / 50.0, "entry_price": 50.0, "current_price": 50.0},
            {"ticker": LEVERAGED_TICKER, "shares": leveraged_value / 20.0, "entry_price": 20.0, "current_price": 20.0},
        ]
    )
    return packet, market_data


def test_discloses_non_authoritative_relied_upon_findings_against_the_real_registry():
    # Current honest state of the real registry (research_findings.json):
    # both relied-upon findings have reproduced_after_data_loader_fix=false
    # -- the disclosure must therefore be present.
    packet, market_data = _overweight_packet_and_market_data()
    proposals = generate_soxx_soxl_rebalance_proposals(packet, _policy(), market_data=market_data)
    assert proposals
    for proposal in proposals:
        assert any(
            "NOT currently production-authoritative" in u for u in proposal.uncertainties
        )


def test_disclosure_absent_once_relied_upon_findings_are_reproduced():
    packet, market_data = _overweight_packet_and_market_data()
    authoritative_findings = [
        SignalEvidence(
            label=label, claim="...", status=EvidenceStatus.CONFIRMED, detail="...", source="test",
            relevant_tickers=["SOXX", "SOXL"],
            provenance=FindingProvenance(
                actual_start_date="2019-07-22", actual_end_date="2026-07-28", actual_row_count=1764,
                entry_timing="next_open", data_fetched_at="2026-07-28T00:00:00+00:00",
                reproduced_after_data_loader_fix=True,
            ),
        )
        for label in strategy_proposals._RELIED_UPON_FINDING_LABELS
    ]
    original = strategy_proposals.KNOWN_FINDINGS
    strategy_proposals.KNOWN_FINDINGS = authoritative_findings
    try:
        proposals = generate_soxx_soxl_rebalance_proposals(packet, _policy(), market_data=market_data)
        assert proposals
        for proposal in proposals:
            assert not any(
                "NOT currently production-authoritative" in u for u in proposal.uncertainties
            )
    finally:
        strategy_proposals.KNOWN_FINDINGS = original


# --- Missing research dependency (GPT review, 2026-07-30): a MISSING
# finding (no matching registry entry at all) must be treated as a
# STRONGER integrity failure than a present-but-unreproduced one --
# never silently indistinguishable from "everything is authoritative".

def test_one_required_finding_missing_raises_and_generates_no_proposal():
    packet, market_data = _overweight_packet_and_market_data()
    remaining_label = strategy_proposals._RELIED_UPON_FINDING_LABELS[1]
    findings_with_one_missing = [
        SignalEvidence(
            label=remaining_label, claim="...", status=EvidenceStatus.CONFIRMED, detail="...", source="test",
            relevant_tickers=["SOXX", "SOXL"],
            provenance=FindingProvenance(
                actual_start_date="2019-07-22", actual_end_date="2026-07-28", actual_row_count=1764,
                entry_timing="next_open", data_fetched_at="2026-07-28T00:00:00+00:00",
                reproduced_after_data_loader_fix=True,
            ),
        )
    ]
    original = strategy_proposals.KNOWN_FINDINGS
    strategy_proposals.KNOWN_FINDINGS = findings_with_one_missing
    try:
        try:
            generate_soxx_soxl_rebalance_proposals(packet, _policy(), market_data=market_data)
            assert False, "expected a missing relied-upon finding to raise"
        except strategy_proposals.MissingResearchDependencyError as exc:
            missing_label = strategy_proposals._RELIED_UPON_FINDING_LABELS[0]
            assert missing_label in str(exc)
    finally:
        strategy_proposals.KNOWN_FINDINGS = original


def test_entire_registry_empty_raises_and_generates_no_proposal():
    packet, market_data = _overweight_packet_and_market_data()
    original = strategy_proposals.KNOWN_FINDINGS
    strategy_proposals.KNOWN_FINDINGS = []
    try:
        try:
            generate_soxx_soxl_rebalance_proposals(packet, _policy(), market_data=market_data)
            assert False, "expected an empty registry to raise, not silently produce a proposal"
        except strategy_proposals.MissingResearchDependencyError as exc:
            for label in strategy_proposals._RELIED_UPON_FINDING_LABELS:
                assert label in str(exc)
    finally:
        strategy_proposals.KNOWN_FINDINGS = original


def test_renamed_label_no_longer_resolves_raises():
    # A label rename (e.g. a registry migration that reworded a finding's
    # label) must be treated exactly like a deletion -- the hard-coded
    # dependency in _RELIED_UPON_FINDING_LABELS no longer matches anything.
    packet, market_data = _overweight_packet_and_market_data()
    renamed_findings = [
        SignalEvidence(
            label=label + " (renamed)", claim="...", status=EvidenceStatus.CONFIRMED, detail="...", source="test",
            relevant_tickers=["SOXX", "SOXL"],
            provenance=FindingProvenance(
                actual_start_date="2019-07-22", actual_end_date="2026-07-28", actual_row_count=1764,
                entry_timing="next_open", data_fetched_at="2026-07-28T00:00:00+00:00",
                reproduced_after_data_loader_fix=True,
            ),
        )
        for label in strategy_proposals._RELIED_UPON_FINDING_LABELS
    ]
    original = strategy_proposals.KNOWN_FINDINGS
    strategy_proposals.KNOWN_FINDINGS = renamed_findings
    try:
        try:
            generate_soxx_soxl_rebalance_proposals(packet, _policy(), market_data=market_data)
            assert False, "expected renamed labels to no longer resolve and raise"
        except strategy_proposals.MissingResearchDependencyError:
            pass
    finally:
        strategy_proposals.KNOWN_FINDINGS = original


def test_relied_upon_finding_reclassified_to_rejected_raises_not_silently_accepted():
    # GPT review, 2026-07-31, independently reproduced: SignalEvidence.
    # production_authoritative intentionally returns True for a REJECTED
    # finding (rejected/exploratory/unavailable make no positive claim
    # worth distrusting -- correct for display), which the OLD dependency
    # checker relied on exclusively. Setting both relied-upon findings to
    # "rejected" made the old checker report (missing=[], non_
    # authoritative=[]) -- indistinguishable from "every dependency is
    # fine". The dependency checker must require the SPECIFIC status
    # (CONFIRMED) this strategy actually depends on, not just "some
    # status that isn't obviously distrustful".
    packet, market_data = _overweight_packet_and_market_data()
    rejected_findings = [
        SignalEvidence(
            label=label, claim="...", status=EvidenceStatus.REJECTED, detail="...", source="test",
            relevant_tickers=["SOXX", "SOXL"], provenance=None,
        )
        for label in strategy_proposals._RELIED_UPON_FINDING_LABELS
    ]
    original = strategy_proposals.KNOWN_FINDINGS
    strategy_proposals.KNOWN_FINDINGS = rejected_findings
    try:
        broken, non_authoritative = strategy_proposals._relied_upon_findings_status()
        assert sorted(broken) == sorted(strategy_proposals._RELIED_UPON_FINDING_LABELS)
        assert non_authoritative == []  # not "non-authoritative" -- BROKEN, a stronger failure
        try:
            generate_soxx_soxl_rebalance_proposals(packet, _policy(), market_data=market_data)
            assert False, "expected a rejected relied-upon finding to raise, not be silently accepted"
        except strategy_proposals.MissingResearchDependencyError as exc:
            for label in strategy_proposals._RELIED_UPON_FINDING_LABELS:
                assert label in str(exc)
    finally:
        strategy_proposals.KNOWN_FINDINGS = original


def test_relied_upon_finding_exploratory_status_also_raises():
    packet, market_data = _overweight_packet_and_market_data()
    exploratory_findings = [
        SignalEvidence(
            label=label, claim="...", status=EvidenceStatus.EXPLORATORY, detail="...", source="test",
            relevant_tickers=["SOXX", "SOXL"], provenance=None,
        )
        for label in strategy_proposals._RELIED_UPON_FINDING_LABELS
    ]
    original = strategy_proposals.KNOWN_FINDINGS
    strategy_proposals.KNOWN_FINDINGS = exploratory_findings
    try:
        try:
            generate_soxx_soxl_rebalance_proposals(packet, _policy(), market_data=market_data)
            assert False, "expected an exploratory-status relied-upon finding to raise"
        except strategy_proposals.MissingResearchDependencyError:
            pass
    finally:
        strategy_proposals.KNOWN_FINDINGS = original


def test_relied_upon_finding_confirmed_and_reproduced_is_not_broken_or_non_authoritative():
    prov_reproduced = FindingProvenance(
        actual_start_date="2019-07-22", actual_end_date="2026-07-28", actual_row_count=1764,
        entry_timing="next_open", data_fetched_at="2026-07-28T00:00:00+00:00",
        reproduced_after_data_loader_fix=True,
    )
    confirmed_findings = [
        SignalEvidence(
            label=label, claim="...", status=EvidenceStatus.CONFIRMED, detail="...", source="test",
            relevant_tickers=["SOXX", "SOXL"], provenance=prov_reproduced,
        )
        for label in strategy_proposals._RELIED_UPON_FINDING_LABELS
    ]
    original = strategy_proposals.KNOWN_FINDINGS
    strategy_proposals.KNOWN_FINDINGS = confirmed_findings
    try:
        broken, non_authoritative = strategy_proposals._relied_upon_findings_status()
        assert broken == []
        assert non_authoritative == []
    finally:
        strategy_proposals.KNOWN_FINDINGS = original


# --- store=... wiring (docs/ALLOCATION_SERVICE_DESIGN.md, 2026-08-01):
# records "this strategy was evaluated" regardless of whether a proposal
# actually fired.

def test_records_a_strategy_evaluation_when_no_proposal_fires():
    import tempfile

    from assistant.storage import AssistantStore

    market_data = _market_data()
    target, _ = _expected_target(market_data)
    combined = 10_000.0
    leveraged_value = combined * target  # on target -> zero drift, no proposal
    stable_value = combined - leveraged_value
    packet = _packet(
        [
            {"ticker": STABLE_TICKER, "shares": stable_value / 50.0, "entry_price": 50.0, "current_price": 50.0},
            {"ticker": LEVERAGED_TICKER, "shares": leveraged_value / 20.0 if leveraged_value else 0.0, "entry_price": 20.0, "current_price": 20.0},
        ]
    )
    with tempfile.TemporaryDirectory() as tmp:
        store = AssistantStore(Path(tmp) / "assistant.db")
        proposals = generate_soxx_soxl_rebalance_proposals(packet, _policy(), market_data=market_data, store=store)
        assert proposals == []
        result = store.get_last_strategy_evaluation("soxx_soxl_rebalance")
        assert result is not None
        assert result["last_result"] == {"fired": False, "proposal_count": 0}


def test_records_a_strategy_evaluation_when_a_proposal_fires():
    import tempfile

    from assistant.storage import AssistantStore

    market_data = _market_data()
    target, _ = _expected_target(market_data)
    overweight = min(target + 0.30, 0.95)
    combined = 10_000.0
    leveraged_value = combined * overweight
    stable_value = combined - leveraged_value
    leveraged_price = 20.0
    packet = _packet(
        [
            {"ticker": STABLE_TICKER, "shares": stable_value / 50.0, "entry_price": 50.0, "current_price": 50.0},
            {"ticker": LEVERAGED_TICKER, "shares": leveraged_value / leveraged_price, "entry_price": leveraged_price, "current_price": leveraged_price},
        ]
    )
    with tempfile.TemporaryDirectory() as tmp:
        store = AssistantStore(Path(tmp) / "assistant.db")
        proposals = generate_soxx_soxl_rebalance_proposals(packet, _policy(), market_data=market_data, store=store)
        assert len(proposals) == 1
        result = store.get_last_strategy_evaluation("soxx_soxl_rebalance")
        assert result["last_result"] == {"fired": True, "proposal_count": 1}


def test_no_store_given_does_not_raise():
    # store is optional -- default None must behave exactly as before this change.
    market_data = _market_data()
    packet = _packet([])
    assert generate_soxx_soxl_rebalance_proposals(packet, _policy(), market_data=market_data) == []


if __name__ == "__main__":
    test_returns_nothing_when_leveraged_leg_not_held()
    test_returns_nothing_when_stable_leg_not_held()
    test_returns_nothing_when_within_band()
    test_proposes_sell_when_overweight_leveraged()
    test_sell_proposal_is_capped_by_max_order_value()
    test_proposes_buy_when_underweight_leveraged()
    test_evidence_status_is_never_confirmed()
    test_discloses_non_authoritative_relied_upon_findings_against_the_real_registry()
    test_disclosure_absent_once_relied_upon_findings_are_reproduced()
    test_one_required_finding_missing_raises_and_generates_no_proposal()
    test_entire_registry_empty_raises_and_generates_no_proposal()
    test_renamed_label_no_longer_resolves_raises()
    test_relied_upon_finding_reclassified_to_rejected_raises_not_silently_accepted()
    test_relied_upon_finding_exploratory_status_also_raises()
    test_relied_upon_finding_confirmed_and_reproduced_is_not_broken_or_non_authoritative()
    test_records_a_strategy_evaluation_when_no_proposal_fires()
    test_records_a_strategy_evaluation_when_a_proposal_fires()
    test_no_store_given_does_not_raise()
    print("All strategy_proposals tests passed.")
