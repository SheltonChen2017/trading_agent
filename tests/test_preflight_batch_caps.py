"""
Batch preflight must simulate the two caps that EVERY submitted leg
consumes, not just the cash-spending ones.

preflight_allocation_batch() documents an all-or-nothing guarantee: "if any
proposal fails preflight, default to submitting none". It held that up by
carrying cash and pending-buy exposure forward across legs -- but the
open-order count was CONSTANT across every leg, and the persistent daily
submission budget (reserve_execution_budget, called only at submit time) was
not consulted at all. So a batch could pass preflight in full and then have
its later legs rejected by the real path, which is exactly the partial
submission the guarantee promises cannot happen (independent review,
2026-07-30).

Both caps are consumed by sells as well as buys, unlike the cash reservation
-- test_a_sell_leg_also_consumes_a_slot pins that asymmetry.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from assistant.allocation_batch import preflight_allocation_batch  # noqa: E402
from assistant.context_builder import build_portfolio_snapshot  # noqa: E402
from assistant.policy import TradingPolicy, compute_policy_fingerprint  # noqa: E402
from assistant.proposals import TradeProposal, _stable_id  # noqa: E402
from assistant.storage import AssistantStore  # noqa: E402
from risk.execution_gate import TradeIntent  # noqa: E402
from test_allocation_batch import _buy_proposal, _packet  # noqa: E402
from test_personal_assistant import _mock_execution_dependencies  # noqa: E402

NOW_ET = datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc)
TRADING_DAY = NOW_ET.date().isoformat()


def _policy(**overrides) -> TradingPolicy:
    base = dict(
        version="test", name="test", execution_mode="paper",
        max_position_pct=1.0, max_total_exposure_pct=1.0, max_basket_pct=1.0,
        max_leveraged_etf_pct=1.0, min_cash_reserve_pct=0.0, max_order_value=50_000.0,
        allow_new_positions=True,
    )
    base.update(overrides)
    return TradingPolicy(**base)


def _sell_proposal(packet, policy, ticker, shares, price):
    intent = TradeIntent(ticker=ticker, side="sell", shares=shares)
    proposal_id = _stable_id(packet, policy, intent)
    return TradeProposal(
        proposal_id=proposal_id, created_at=packet.generated_at,
        expires_at="2026-12-31T00:00:00+00:00", status="proposed",
        idempotency_key=f"{proposal_id}-{packet.portfolio.as_of}",
        policy_version=policy.version, policy_fingerprint=compute_policy_fingerprint(policy),
        intent=intent, reference_price=price, price_timestamp=packet.generated_at,
        reasons=["test"], evidence_status="test",
        expected_impact={
            "trade_value": shares * price, "position_weight_before_pct": 0,
            "position_weight_after_pct": 0, "cash_before": 0, "cash_after": 0,
            "invested_pct_after": 0,
        },
        alternatives=[], uncertainties=[],
    )


def _run_preflight(proposals, policy, packet, *, seed_store=None, quote_price=40.0):
    _, restore = _mock_execution_dependencies(quote_price=quote_price)
    try:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            for proposal in proposals:
                store.save_proposal(proposal.to_dict())
            if seed_store is not None:
                seed_store(store)
            return preflight_allocation_batch(
                [p.proposal_id for p in proposals], store, policy,
                packet.portfolio, now_et=NOW_ET,
            )
    finally:
        restore()


def _approvals(results, proposals):
    return [results[p.proposal_id].approved for p in proposals]


def test_the_open_order_cap_counts_earlier_legs_of_the_same_batch():
    """THE regression: three legs against a cap of 2 used to pass preflight
    entirely, because every leg saw the same empty open-orders list."""
    packet = _packet(cash=100_000.0)
    policy = _policy(max_open_orders=2)
    proposals = [
        _buy_proposal(packet, policy, "AAA", 10, 40.0),
        _buy_proposal(packet, policy, "BBB", 10, 40.0),
        _buy_proposal(packet, policy, "CCC", 10, 40.0),
    ]
    results = _run_preflight(proposals, policy, packet)

    assert _approvals(results, proposals) == [True, True, False]
    assert any("Open-order cap" in v for v in results[proposals[2].proposal_id].violations)


def test_the_open_order_cap_counts_orders_already_at_the_broker():
    """The simulated count is ADDED to the real one, not used instead of it."""
    packet = _packet(cash=100_000.0)
    policy = _policy(max_open_orders=2)
    packet.portfolio.open_orders = [
        {"ticker": "ZZZ", "side": "buy", "shares": 1},
    ]
    proposals = [
        _buy_proposal(packet, policy, "AAA", 10, 40.0),
        _buy_proposal(packet, policy, "BBB", 10, 40.0),
    ]
    results = _run_preflight(proposals, policy, packet)

    assert _approvals(results, proposals) == [True, False]


def test_the_daily_order_count_budget_is_simulated_across_legs():
    """max_daily_order_count lives in reserve_execution_budget(), which
    preflight never called -- so it was invisible until submit time."""
    packet = _packet(cash=100_000.0)
    policy = _policy(max_daily_order_count=2, max_open_orders=99)
    proposals = [
        _buy_proposal(packet, policy, "AAA", 10, 40.0),
        _buy_proposal(packet, policy, "BBB", 10, 40.0),
        _buy_proposal(packet, policy, "CCC", 10, 40.0),
    ]
    results = _run_preflight(proposals, policy, packet)

    assert _approvals(results, proposals) == [True, True, False]
    assert results[proposals[2].proposal_id].violation_codes == ("daily_execution_budget",)


def test_the_daily_notional_budget_is_simulated_across_legs():
    packet = _packet(cash=100_000.0)
    # Each leg is $400 of gross submitted notional; a $900 cap fits two.
    policy = _policy(max_daily_submitted_notional=900.0, max_open_orders=99)
    proposals = [
        _buy_proposal(packet, policy, "AAA", 10, 40.0),
        _buy_proposal(packet, policy, "BBB", 10, 40.0),
        _buy_proposal(packet, policy, "CCC", 10, 40.0),
    ]
    results = _run_preflight(proposals, policy, packet)

    assert _approvals(results, proposals) == [True, True, False]
    assert any("Daily submitted notional" in v
               for v in results[proposals[2].proposal_id].violations)


def test_budget_already_consumed_today_reduces_the_headroom():
    """Preflight must start from the PERSISTED usage, not from zero."""
    packet = _packet(cash=100_000.0)
    policy = _policy(max_daily_order_count=3, max_open_orders=99)
    proposals = [
        _buy_proposal(packet, policy, "AAA", 10, 40.0),
        _buy_proposal(packet, policy, "BBB", 10, 40.0),
    ]

    def seed(store):
        for index in range(2):
            store.reserve_execution_budget(
                f"earlier-{index}", trading_day=TRADING_DAY, notional=100.0,
                max_daily_notional=1_000_000.0, max_daily_orders=10,
            )

    results = _run_preflight(proposals, policy, packet, seed_store=seed)

    # Two already submitted today + one leg == the cap of 3; the second leg
    # would be the fourth submission.
    assert _approvals(results, proposals) == [True, False]


def test_a_sell_leg_also_consumes_a_slot():
    """Sells reserve no cash, but they still create an open order and still
    consume a daily submission. Counting only buys would under-simulate."""
    packet = _packet(cash=100_000.0)
    # A sell is only valid against a real holding.
    packet.portfolio = build_portfolio_snapshot(
        [{"ticker": "AAA", "shares": 20, "entry_price": 40.0, "current_price": 40.0}],
        cash=100_000.0,
    )
    policy = _policy(max_daily_order_count=1, max_open_orders=99)
    proposals = [
        _sell_proposal(packet, policy, "AAA", 5, 40.0),
        _buy_proposal(packet, policy, "BBB", 10, 40.0),
    ]
    results = _run_preflight(proposals, policy, packet)

    assert results[proposals[0].proposal_id].approved
    assert not results[proposals[1].proposal_id].approved
    assert results[proposals[1].proposal_id].violation_codes == ("daily_execution_budget",)


def test_a_sell_leg_consumes_an_open_order_slot():
    """The open-order half of the same asymmetry, pinned separately: a
    mutation that skipped ONLY the open-order increment for sells survived a
    version of this file that checked sells against the daily budget alone."""
    packet = _packet(cash=100_000.0)
    packet.portfolio = build_portfolio_snapshot(
        [{"ticker": "AAA", "shares": 20, "entry_price": 40.0, "current_price": 40.0}],
        cash=100_000.0,
    )
    policy = _policy(max_open_orders=1, max_daily_order_count=99)
    proposals = [
        _sell_proposal(packet, policy, "AAA", 5, 40.0),
        _buy_proposal(packet, policy, "BBB", 10, 40.0),
    ]
    results = _run_preflight(proposals, policy, packet)

    assert results[proposals[0].proposal_id].approved
    assert not results[proposals[1].proposal_id].approved
    assert any("Open-order cap" in v for v in results[proposals[1].proposal_id].violations)


def test_a_clean_batch_within_every_cap_still_passes():
    """The guard must reject only what the real path would reject."""
    packet = _packet(cash=100_000.0)
    policy = _policy(max_open_orders=5, max_daily_order_count=5,
                     max_daily_submitted_notional=100_000.0)
    proposals = [
        _buy_proposal(packet, policy, "AAA", 10, 40.0),
        _buy_proposal(packet, policy, "BBB", 10, 40.0),
    ]
    results = _run_preflight(proposals, policy, packet)

    assert all(r.approved for r in results.values())


def test_a_negative_simulated_count_is_refused_rather_than_loosening_a_cap():
    """Direct call: a bad extra_open_order_count must fail closed."""
    from assistant.execution_service import validate_proposal_for_execution

    packet = _packet(cash=100_000.0)
    policy = _policy()
    proposal = _buy_proposal(packet, policy, "AAA", 10, 40.0)
    _, restore = _mock_execution_dependencies(quote_price=40.0)
    try:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            outcome = validate_proposal_for_execution(
                proposal.proposal_id, packet.portfolio, policy, store,
                now_et=NOW_ET, extra_open_order_count=-5,
            )
            assert outcome.error is not None
            assert "extra_open_order_count" in outcome.error
    finally:
        restore()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
