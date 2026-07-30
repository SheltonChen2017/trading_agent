"""Tests for assistant/proposals.py -- generate_risk_reduction_proposals()
and its total-exposure remediation (GPT review, 2026-07-31)."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.context_builder import build_portfolio_snapshot, build_risk_exposure
from assistant.policy import TradingPolicy
from assistant.proposals import generate_risk_reduction_proposals
from assistant.schemas import DecisionPacket, MarketRegime
from assistant.tax_lots import Fill, build_ledger


def _packet(positions: list[dict], cash: float) -> DecisionPacket:
    snapshot = build_portfolio_snapshot(positions, cash=cash)
    return DecisionPacket(
        generated_at="2026-07-31T12:00:00+00:00",
        portfolio=snapshot,
        risk=build_risk_exposure(snapshot),
        regime=MarketRegime(
            benchmark_ticker="QQQ", trend="uptrend", volatility_regime="low_vol",
            trailing_volatility_pct=1.0, as_of="2026-07-31",
        ),
        signals=[], upcoming_events=[], warnings=[], policy_version="test",
    )


def _permissive_policy(max_total_exposure_pct: float = 1.0, max_basket_pct: float = 1.0,
                        max_position_pct: float = 1.0, max_leveraged_etf_pct: float = 1.0,
                        max_order_value: float = 100_000.0) -> TradingPolicy:
    return TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=max_position_pct, max_total_exposure_pct=max_total_exposure_pct,
        max_basket_pct=max_basket_pct, max_leveraged_etf_pct=max_leveraged_etf_pct,
        min_cash_reserve_pct=0.0, max_order_value=max_order_value,
    )


# --- Total-exposure remediation (P1, GPT review, 2026-07-31):
# generate_risk_reduction_proposals() never checked policy.
# max_total_exposure_pct at all -- a diversified portfolio well over the
# cap, with every individual position/basket/leveraged check passing,
# got ZERO remediation proposals.

def test_total_exposure_breach_with_no_individual_violations_produces_a_proposal():
    # 3 positions at $30k each (30% of equity individually, well under
    # a 100% per-position cap) -> $90k invested = 90% of a $100k account,
    # against a 50% total-exposure cap. No position/basket/leveraged
    # check fires (all set to 100%/permissive) -- only the total-exposure
    # check should.
    positions = [
        {"ticker": "AAA", "shares": 300, "entry_price": 100.0, "current_price": 100.0},
        {"ticker": "BBB", "shares": 300, "entry_price": 100.0, "current_price": 100.0},
        {"ticker": "CCC", "shares": 300, "entry_price": 100.0, "current_price": 100.0},
    ]
    packet = _packet(positions, cash=10_000.0)
    assert packet.portfolio.total_equity == 100_000.0
    policy = _permissive_policy(max_total_exposure_pct=0.50)

    proposals = generate_risk_reduction_proposals(packet, policy)
    assert proposals, "expected at least one total-exposure remediation proposal"
    assert all(p.intent.side == "sell" for p in proposals)
    assert any("total invested exposure" in r.lower() for p in proposals for r in p.reasons)


def test_total_exposure_breach_does_not_fire_when_within_cap():
    positions = [
        {"ticker": "AAA", "shares": 100, "entry_price": 100.0, "current_price": 100.0},
    ]
    packet = _packet(positions, cash=90_000.0)  # 10% invested
    policy = _permissive_policy(max_total_exposure_pct=0.50)
    proposals = generate_risk_reduction_proposals(packet, policy)
    assert proposals == []


def test_total_exposure_remediation_accounts_for_already_planned_reductions():
    # A tight per-position cap already forces most of AAA's excess to be
    # sold; the total-exposure remediation must not ALSO independently
    # demand the full total-exposure gap from AAA on top of that (which
    # would over-sell it) -- it should only ask for whatever's left after
    # crediting the position-cap reduction already planned.
    positions = [
        {"ticker": "AAA", "shares": 500, "entry_price": 100.0, "current_price": 100.0},  # $50k, 50% of equity
        {"ticker": "BBB", "shares": 300, "entry_price": 100.0, "current_price": 100.0},  # $30k, 30% of equity
    ]
    packet = _packet(positions, cash=20_000.0)  # total equity = $100k, invested = $80k (80%)
    policy = _permissive_policy(
        max_position_pct=0.20,  # AAA (50%) way over -> forces a big AAA sell
        max_total_exposure_pct=0.50,  # 80% invested is also over this
        max_order_value=100_000.0,
    )
    proposals = generate_risk_reduction_proposals(packet, policy)
    by_ticker = {p.intent.ticker: p for p in proposals}
    assert "AAA" in by_ticker
    # AAA's reduction must satisfy BOTH the position cap (down to $20k,
    # i.e. sell $30k = 300 shares) AND, combined with any BBB sell,
    # close the total-exposure gap ($80k - $50k = $30k excess) -- selling
    # 300 AAA shares ($30k) alone already closes the total-exposure gap
    # exactly, so BBB should need no additional sell.
    assert by_ticker["AAA"].intent.shares >= 300
    total_sold_value = sum(p.intent.shares * p.reference_price for p in proposals)
    assert total_sold_value >= 30_000.0 - 1.0  # closes (at least) the real exposure gap


# --- Basket-cap rounding fix (P1, GPT review, 2026-07-31): the basket
# check used to compare packet.risk.basket_exposure_pct (a value ALREADY
# rounded to 1 decimal for display) against the cap, so a true exposure
# just above the boundary (e.g. 40.04%) could round down to exactly the
# limit (40.0%) and silently evade proposal generation.

def test_basket_breach_just_above_the_rounding_boundary_still_fires():
    # NVDA + AMD (both in config.BASKETS["semiconductors"]) at exactly
    # 40.04% of a $100k account -- rounds to "40.0%" for DISPLAY, which
    # the old buggy comparison (`pct <= cap*100` using the rounded value)
    # would have treated as within a 40% cap.
    positions = [
        {"ticker": "NVDA", "shares": 1, "entry_price": 25_040.0, "current_price": 25_040.0},
        {"ticker": "AMD", "shares": 1, "entry_price": 15_000.0, "current_price": 15_000.0},
    ]
    packet = _packet(positions, cash=59_960.0)
    assert packet.portfolio.total_equity == 100_000.0
    basket_pct_rounded = packet.risk.basket_exposure_pct["semiconductors"]
    assert basket_pct_rounded == 40.0  # confirms the display value rounds down to exactly the cap

    policy = _permissive_policy(max_basket_pct=0.40)
    proposals = generate_risk_reduction_proposals(packet, policy)
    assert proposals, "expected the basket breach to fire despite rounding down to exactly the cap for display"
    assert any("semiconductors" in r.lower() for p in proposals for r in p.reasons)


def test_basket_breach_genuinely_within_cap_does_not_fire():
    positions = [
        {"ticker": "NVDA", "shares": 1, "entry_price": 10_000.0, "current_price": 10_000.0},
    ]
    packet = _packet(positions, cash=90_000.0)  # 10% -- well under a 40% basket cap
    policy = _permissive_policy(max_basket_pct=0.40)
    proposals = generate_risk_reduction_proposals(packet, policy)
    assert proposals == []


# --- Regression: pre-existing position/leveraged-ETF checks still work.

def test_position_cap_breach_still_produces_a_proposal():
    positions = [{"ticker": "AAA", "shares": 100, "entry_price": 100.0, "current_price": 100.0}]
    packet = _packet(positions, cash=0.0)  # 100% in one position
    policy = _permissive_policy(max_position_pct=0.05)
    proposals = generate_risk_reduction_proposals(packet, policy)
    assert proposals
    assert any("position exceeds" in r.lower() for p in proposals for r in p.reasons)


def test_sell_proposal_includes_advisory_lot_method_comparison():
    positions = [
        {
            "ticker": "AAA",
            "shares": 100,
            "entry_price": 100.0,
            "current_price": 100.0,
        }
    ]
    packet = _packet(positions, cash=0)
    policy = _permissive_policy(max_position_pct=0.50)
    now = datetime.now(timezone.utc)
    ledger = build_ledger(
        [
            Fill(
                "AAA",
                "buy",
                50,
                80,
                now - timedelta(days=500),
                fill_id="old-low",
            ),
            Fill(
                "AAA",
                "buy",
                50,
                120,
                now - timedelta(days=10),
                fill_id="new-high",
            ),
        ]
    )

    proposal = generate_risk_reduction_proposals(
        packet, policy, tax_lot_ledger=ledger
    )[0]
    advisory = proposal.expected_impact["tax_lot_advisory"]

    assert advisory["available"]
    assert advisory["advisory_only"]
    assert advisory["methods"]["fifo"]["long_term_pnl"] > 0
    assert advisory["methods"]["hifo"]["short_term_pnl"] < 0


def test_missing_tax_coverage_never_blocks_or_changes_risk_reduction():
    packet = _packet(
        [
            {
                "ticker": "AAA",
                "shares": 100,
                "entry_price": 100.0,
                "current_price": 100.0,
            }
        ],
        cash=0,
    )
    policy = _permissive_policy(max_position_pct=0.50)
    baseline = generate_risk_reduction_proposals(packet, policy)[0]
    with_missing_tax = generate_risk_reduction_proposals(
        packet,
        policy,
        tax_lot_ledger=None,
        tax_lot_coverage={
            "complete": False,
            "reason": "pre-app fills missing",
        },
    )[0]

    assert with_missing_tax.intent == baseline.intent
    advisory = with_missing_tax.expected_impact["tax_lot_advisory"]
    assert not advisory["available"]
    assert advisory["advisory_only"]
    assert "pre-app fills missing" in advisory["reason"]


def test_leveraged_etf_cap_breach_still_produces_a_proposal():
    positions = [{"ticker": "TQQQ", "shares": 100, "entry_price": 100.0, "current_price": 100.0}]
    packet = _packet(positions, cash=0.0)  # 100% leveraged
    policy = _permissive_policy(max_leveraged_etf_pct=0.20)
    proposals = generate_risk_reduction_proposals(packet, policy)
    assert proposals
    assert any("leveraged-etf exposure" in r.lower() for p in proposals for r in p.reasons)


def test_duplicate_ticker_rows_aggregate_exposure_still_produces_a_position_cap_proposal():
    # Independent review reproduction: two AAPL lots that each individually
    # sit under a 5% max_position_pct cap but jointly exceed it used to
    # produce no remediation at all, since generate_risk_reduction_
    # proposals() iterates snapshot.positions and position_by_ticker
    # silently collapsed duplicate keys. build_portfolio_snapshot() now
    # aggregates duplicate rows at ingestion, so this sees one $600 row.
    positions = [
        {"ticker": "AAPL", "shares": 1, "entry_price": 300.0, "current_price": 300.0},
        {"ticker": "AAPL", "shares": 1, "entry_price": 300.0, "current_price": 300.0},
    ]
    packet = _packet(positions, cash=9_400.0)  # AAPL = 600/10000 = 6%
    assert len(packet.portfolio.positions) == 1
    policy = _permissive_policy(max_position_pct=0.05)
    proposals = generate_risk_reduction_proposals(packet, policy)
    assert proposals
    assert any(p.intent.ticker == "AAPL" for p in proposals)
    assert any("position exceeds" in r.lower() for p in proposals for r in p.reasons)


def test_lowercase_ticker_basket_breach_still_produces_a_proposal():
    # Independent review reproduction: a manually-supplied lowercase
    # "aapl" used to be invisible to this generator's case-sensitive
    # basket membership check.
    positions = [{"ticker": "aapl", "shares": 50, "entry_price": 100.0, "current_price": 100.0}]
    packet = _packet(positions, cash=5_000.0)  # AAPL = 5000/10000 = 50%
    policy = _permissive_policy(max_basket_pct=0.40)
    proposals = generate_risk_reduction_proposals(packet, policy)
    assert proposals
    assert any(p.intent.ticker == "AAPL" for p in proposals)
    assert any("tech" in r.lower() for p in proposals for r in p.reasons)


if __name__ == "__main__":
    test_total_exposure_breach_with_no_individual_violations_produces_a_proposal()
    test_total_exposure_breach_does_not_fire_when_within_cap()
    test_total_exposure_remediation_accounts_for_already_planned_reductions()
    test_basket_breach_just_above_the_rounding_boundary_still_fires()
    test_basket_breach_genuinely_within_cap_does_not_fire()
    test_position_cap_breach_still_produces_a_proposal()
    test_leveraged_etf_cap_breach_still_produces_a_proposal()
    test_duplicate_ticker_rows_aggregate_exposure_still_produces_a_position_cap_proposal()
    test_lowercase_ticker_basket_breach_still_produces_a_proposal()
    print("All proposals tests passed.")
