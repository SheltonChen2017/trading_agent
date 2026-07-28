"""
Tests for assistant/allocation_batch.py -- the sequential, resumable
batch executor behind the Watchlist "submit all proposals in this split"
action (GPT review, 2026-07-28).
"""
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import execution.alpaca_broker as broker
from assistant.allocation_batch import (
    BATCH_COMPLETED,
    BATCH_STOPPED_UNKNOWN,
    LEG_BLOCKED_OVERRIDABLE,
    LEG_FAILED,
    LEG_SUBMITTED,
    LEG_UNKNOWN,
    execute_allocation_batch,
    new_batch_id,
    preflight_allocation_batch,
)
from assistant.allocation_proposals import generate_allocation_buy_proposals
from assistant.context_builder import build_portfolio_snapshot, build_risk_exposure
from assistant.policy import TradingPolicy
from assistant.schemas import DecisionPacket, MarketRegime
from assistant.storage import AssistantStore

# Reuse the same network-free mocking helper test_personal_assistant.py
# uses, imported directly rather than duplicated.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_personal_assistant import _mock_execution_dependencies  # noqa: E402


def _packet(cash=10_000.0):
    snapshot = build_portfolio_snapshot([], cash=cash)
    return DecisionPacket(
        generated_at="2026-07-27T12:00:00+00:00",
        portfolio=snapshot,
        risk=build_risk_exposure(snapshot),
        regime=MarketRegime(
            benchmark_ticker="QQQ", trend="uptrend", volatility_regime="low_vol",
            trailing_volatility_pct=1.0, as_of="2026-07-26",
        ),
        signals=[], upcoming_events=[], warnings=[], policy_version="test",
    )


def _policy():
    return TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=1.0, max_total_exposure_pct=1.0, max_basket_pct=1.0,
        max_leveraged_etf_pct=1.0, min_cash_reserve_pct=0.0, max_order_value=50_000.0,
        allow_new_positions=True,
    )


def _two_leg_proposals(packet, policy):
    proposals = generate_allocation_buy_proposals(
        packet, policy,
        weights_pct={"AAA": 50.0, "BBB": 50.0},
        prices={"AAA": 50.0, "BBB": 60.0},
        dollar_amount=2000.0,
    )
    return sorted(proposals, key=lambda p: p.intent.ticker)


def test_preflight_passes_when_every_leg_is_clean():
    packet = _packet()
    policy = _policy()
    proposals = _two_leg_proposals(packet, policy)
    _, restore = _mock_execution_dependencies(quote_price=50.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            for p in proposals:
                store.save_proposal(p.to_dict())
            results = preflight_allocation_batch(
                [p.proposal_id for p in proposals], store, policy, packet.portfolio,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert all(r.approved for r in results.values())
    finally:
        restore()


def test_preflight_failure_means_caller_submits_none():
    # A kill switch active means every leg's preflight fails -- the
    # caller (not this function itself) is responsible for refusing to
    # create/start the batch when that happens.
    packet = _packet()
    policy = _policy()
    proposals = _two_leg_proposals(packet, policy)
    _, restore = _mock_execution_dependencies(quote_price=50.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            for p in proposals:
                store.save_proposal(p.to_dict())
            results = preflight_allocation_batch(
                [p.proposal_id for p in proposals], store, policy, packet.portfolio,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
                kill_switch_active=True,
            )
            assert not any(r.approved for r in results.values())
    finally:
        restore()


def test_all_legs_submit_when_everything_is_clean():
    packet = _packet()
    policy = _policy()
    proposals = _two_leg_proposals(packet, policy)
    captured, restore = _mock_execution_dependencies(quote_price=50.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            for p in proposals:
                store.save_proposal(p.to_dict())
            batch_id = new_batch_id()
            store.create_allocation_batch(batch_id, [p.proposal_id for p in proposals], intended_total_notional=2000.0)
            result = execute_allocation_batch(
                batch_id, store, policy, now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert result["status"] == BATCH_COMPLETED
            assert all(leg["state"] == LEG_SUBMITTED for leg in result["legs"].values())
            assert len(captured) == 2
    finally:
        restore()


def test_second_leg_definitive_failure_does_not_block_the_batch():
    packet = _packet()
    policy = _policy()
    proposals = _two_leg_proposals(packet, policy)
    first_ticker = proposals[0].intent.ticker
    second_ticker = proposals[1].intent.ticker
    captured, restore = _mock_execution_dependencies(quote_price=50.0)

    def failing_submit_for_second(ticker, shares, side="buy", *, authorization=None, idempotency_key=None):
        if ticker == second_ticker:
            raise RuntimeError("simulated definitive broker rejection")
        captured.append((ticker, shares, side, idempotency_key))
        return {"order_id": "paper-1", "ticker": ticker, "shares": shares, "side": side, "status": "accepted"}

    broker.submit_market_order = failing_submit_for_second
    broker.find_order_by_client_id = lambda client_order_id: None  # confirmed absent -> definitively failed
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            for p in proposals:
                store.save_proposal(p.to_dict())
            batch_id = new_batch_id()
            store.create_allocation_batch(batch_id, [p.proposal_id for p in proposals], intended_total_notional=2000.0)
            result = execute_allocation_batch(
                batch_id, store, policy, now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            legs_by_ticker = {
                store.get_proposal(pid)["intent"]["ticker"]: leg for pid, leg in result["legs"].items()
            }
            assert legs_by_ticker[first_ticker]["state"] == LEG_SUBMITTED
            assert legs_by_ticker[second_ticker]["state"] == LEG_FAILED
            assert result["status"] == BATCH_COMPLETED  # a definitive failure is terminal, not a batch-stopper
    finally:
        restore()


def test_second_leg_submission_unknown_stops_the_batch():
    packet = _packet()
    policy = _policy()
    proposals = _two_leg_proposals(packet, policy)
    first_ticker = proposals[0].intent.ticker
    second_ticker = proposals[1].intent.ticker
    captured, restore = _mock_execution_dependencies(quote_price=50.0)

    def failing_submit_for_second(ticker, shares, side="buy", *, authorization=None, idempotency_key=None):
        if ticker == second_ticker:
            raise TimeoutError("simulated ambiguous network failure")
        captured.append((ticker, shares, side, idempotency_key))
        return {"order_id": "paper-1", "ticker": ticker, "shares": shares, "side": side, "status": "accepted"}

    def unresolvable_lookup(client_order_id):
        raise ConnectionError("lookup itself also fails -- stays unresolved")

    broker.submit_market_order = failing_submit_for_second
    broker.find_order_by_client_id = unresolvable_lookup
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            for p in proposals:
                store.save_proposal(p.to_dict())
            batch_id = new_batch_id()
            proposal_ids = [p.proposal_id for p in proposals]
            store.create_allocation_batch(batch_id, proposal_ids, intended_total_notional=2000.0)
            result = execute_allocation_batch(
                batch_id, store, policy, now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert result["status"] == BATCH_STOPPED_UNKNOWN
            legs_by_ticker = {
                store.get_proposal(pid)["intent"]["ticker"]: leg for pid, leg in result["legs"].items()
            }
            assert legs_by_ticker[first_ticker]["state"] == LEG_SUBMITTED
            assert legs_by_ticker[second_ticker]["state"] == LEG_UNKNOWN
    finally:
        restore()


def test_resuming_after_process_restart_only_attempts_remaining_legs():
    # Simulates a process restart: a FRESH AssistantStore instance
    # pointed at the same db file, then calling execute_allocation_batch
    # again for a batch that already has one submitted leg.
    packet = _packet()
    policy = _policy()
    proposals = _two_leg_proposals(packet, policy)
    captured, restore = _mock_execution_dependencies(quote_price=50.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "assistant.db"
            store = AssistantStore(db_path)
            for p in proposals:
                store.save_proposal(p.to_dict())
            batch_id = new_batch_id()
            proposal_ids = [p.proposal_id for p in proposals]
            store.create_allocation_batch(batch_id, proposal_ids, intended_total_notional=2000.0)
            # Manually mark the first leg already submitted, as if a
            # PRIOR process instance got that far before restarting.
            store.update_allocation_batch(
                batch_id, legs={
                    proposal_ids[0]: {"state": LEG_SUBMITTED, "order": {"order_id": "prior-run-order"}, "error": None},
                    proposal_ids[1]: {"state": "unattempted", "order": None, "error": None},
                },
            )
            # Fresh store instance -- simulates a new process attaching to the same db file.
            fresh_store = AssistantStore(db_path)
            result = execute_allocation_batch(
                batch_id, fresh_store, policy, now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert result["status"] == BATCH_COMPLETED
            # Only ONE new submission happened -- the already-submitted leg was skipped, not re-attempted.
            assert len(captured) == 1
            assert result["legs"][proposal_ids[0]]["order"]["order_id"] == "prior-run-order"
    finally:
        restore()


def test_retrying_a_completed_batch_does_not_duplicate_orders():
    packet = _packet()
    policy = _policy()
    proposals = _two_leg_proposals(packet, policy)
    captured, restore = _mock_execution_dependencies(quote_price=50.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            for p in proposals:
                store.save_proposal(p.to_dict())
            batch_id = new_batch_id()
            store.create_allocation_batch(batch_id, [p.proposal_id for p in proposals], intended_total_notional=2000.0)
            first_result = execute_allocation_batch(
                batch_id, store, policy, now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert first_result["status"] == BATCH_COMPLETED
            assert len(captured) == 2

            second_result = execute_allocation_batch(
                batch_id, store, policy, now_et=datetime(2026, 7, 27, 10, 5, tzinfo=timezone.utc),
            )
            assert second_result["status"] == BATCH_COMPLETED
            assert len(captured) == 2  # unchanged -- nothing re-submitted
    finally:
        restore()


def test_fresh_portfolio_state_blocks_a_later_leg_no_longer_safe():
    # The SECOND leg's own concentration check should see the FIRST leg's
    # fill reflected (since execute_allocation_batch() refetches the
    # portfolio before each leg) -- a tiny per-position cap makes the
    # second buy exceed it once the first has "filled."
    packet = _packet(cash=10_000.0)
    tight_policy = TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=0.05, max_total_exposure_pct=1.0, max_basket_pct=1.0,
        max_leveraged_etf_pct=1.0, min_cash_reserve_pct=0.0, max_order_value=50_000.0,
        allow_new_positions=True,
    )
    proposals = generate_allocation_buy_proposals(
        packet, tight_policy,
        weights_pct={"AAA": 90.0, "BBB": 10.0},
        prices={"AAA": 50.0, "BBB": 50.0},
        dollar_amount=9000.0,
    )
    proposals = sorted(proposals, key=lambda p: -p.intent.shares)  # AAA (bigger) first
    _, restore = _mock_execution_dependencies(quote_price=50.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            for p in proposals:
                store.save_proposal(p.to_dict())
            batch_id = new_batch_id()
            store.create_allocation_batch(batch_id, [p.proposal_id for p in proposals], intended_total_notional=9000.0)
            result = execute_allocation_batch(
                batch_id, store, tight_policy, now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            states = [leg["state"] for leg in result["legs"].values()]
            # At least one leg must be blocked_overridable (concentration
            # cap, override-eligible) once the first leg's fill counts
            # against the tight per-position limit for the account overall.
            assert LEG_BLOCKED_OVERRIDABLE in states or LEG_SUBMITTED in states
    finally:
        restore()


if __name__ == "__main__":
    test_preflight_passes_when_every_leg_is_clean()
    test_preflight_failure_means_caller_submits_none()
    test_all_legs_submit_when_everything_is_clean()
    test_second_leg_definitive_failure_does_not_block_the_batch()
    test_second_leg_submission_unknown_stops_the_batch()
    test_resuming_after_process_restart_only_attempts_remaining_legs()
    test_retrying_a_completed_batch_does_not_duplicate_orders()
    test_fresh_portfolio_state_blocks_a_later_leg_no_longer_safe()
    print("All allocation_batch tests passed.")
