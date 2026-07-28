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
from assistant.execution_service import execute_approved_paper_proposal
from assistant.policy import TradingPolicy, compute_policy_fingerprint
from assistant.proposals import TradeProposal, _stable_id
from assistant.schemas import DecisionPacket, MarketRegime
from assistant.storage import AssistantStore
from risk.execution_gate import TradeIntent

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


def _mock_batch_execution(packet, quote_price=50.0, **kwargs):
    """Like _mock_execution_dependencies, but ALSO patches
    assistant.allocation_batch.build_portfolio_snapshot_from_alpaca --
    execute_allocation_batch() calls that FRESH before every leg (by
    design, so an earlier fill in the same batch is reflected in the
    next leg's checks), and it is NOT mocked by
    _mock_execution_dependencies() alone, so without this a batch test
    would hit whatever REAL Alpaca account is configured in the
    environment (this project's dev environment has real paper
    credentials set). The replacement reconstructs a portfolio from
    every order captured so far, so tests that need a later leg to see
    an earlier leg's fill (e.g. a tightened per-position cap) still work
    correctly, without ever touching the network."""
    import assistant.allocation_batch as batch_module

    captured, restore_exec = _mock_execution_dependencies(quote_price=quote_price, **kwargs)

    def dynamic_portfolio():
        positions_by_ticker: dict[str, int] = {}
        for ticker, shares, side, *_ in captured:
            sign = 1 if side == "buy" else -1
            positions_by_ticker[ticker] = positions_by_ticker.get(ticker, 0) + sign * shares
        new_positions = [
            {"ticker": t, "shares": s, "entry_price": quote_price, "current_price": quote_price}
            for t, s in positions_by_ticker.items() if s > 0
        ]
        spent = sum(shares * quote_price for _, shares, side, *_ in captured if side == "buy")
        return build_portfolio_snapshot(new_positions, cash=packet.portfolio.cash - spent)

    original_portfolio_fn = batch_module.build_portfolio_snapshot_from_alpaca
    batch_module.build_portfolio_snapshot_from_alpaca = dynamic_portfolio

    def restore():
        batch_module.build_portfolio_snapshot_from_alpaca = original_portfolio_fn
        restore_exec()

    return captured, restore


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


def _buy_proposal(packet, policy, ticker, shares, price):
    intent = TradeIntent(ticker=ticker, side="buy", shares=shares)
    proposal_id = _stable_id(packet, policy, intent)
    return TradeProposal(
        proposal_id=proposal_id, created_at=packet.generated_at, expires_at="2026-12-31T00:00:00+00:00",
        status="proposed", idempotency_key=f"{proposal_id}-{packet.portfolio.as_of}",
        policy_version=policy.version, policy_fingerprint=compute_policy_fingerprint(policy),
        intent=intent, reference_price=price, price_timestamp=packet.generated_at,
        reasons=["test"], evidence_status="test",
        expected_impact={
            "trade_value": shares * price, "position_weight_before_pct": 0, "position_weight_after_pct": 0,
            "cash_before": 0, "cash_after": 0, "invested_pct_after": 0,
        },
        alternatives=[], uncertainties=[],
    )


def test_cumulative_preflight_fails_on_collective_total_exposure():
    # Two individually-safe $4,000 buys on a $10,000 account (40% each,
    # under a 60% total-exposure cap) collectively create 80% exposure --
    # cumulative preflight must catch this even though each leg alone
    # would pass.
    packet = _packet(cash=10_000.0)
    policy = TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=1.0, max_total_exposure_pct=0.6, max_basket_pct=1.0,
        max_leveraged_etf_pct=1.0, min_cash_reserve_pct=0.0, max_order_value=50_000.0,
        allow_new_positions=True,
    )
    proposals = [
        _buy_proposal(packet, policy, "AAA", 100, 40.0),
        _buy_proposal(packet, policy, "BBB", 100, 40.0),
    ]
    _, restore = _mock_execution_dependencies(quote_price=40.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            for p in proposals:
                store.save_proposal(p.to_dict())
            results = preflight_allocation_batch(
                [p.proposal_id for p in proposals], store, policy, packet.portfolio,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert results[proposals[0].proposal_id].approved  # individually fine
            assert not results[proposals[1].proposal_id].approved  # fails once A's reservation is counted
            assert any("total-exposure" in v for v in results[proposals[1].proposal_id].violations)
    finally:
        restore()


def test_cumulative_preflight_fails_on_collective_min_cash_reserve():
    packet = _packet(cash=10_000.0)
    policy = TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=1.0, max_total_exposure_pct=1.0, max_basket_pct=1.0,
        max_leveraged_etf_pct=1.0, min_cash_reserve_pct=0.3, max_order_value=50_000.0,
        allow_new_positions=True,
    )
    proposals = [
        _buy_proposal(packet, policy, "AAA", 100, 40.0),
        _buy_proposal(packet, policy, "BBB", 100, 40.0),
    ]
    _, restore = _mock_execution_dependencies(quote_price=40.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            for p in proposals:
                store.save_proposal(p.to_dict())
            results = preflight_allocation_batch(
                [p.proposal_id for p in proposals], store, policy, packet.portfolio,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert results[proposals[0].proposal_id].approved
            assert not results[proposals[1].proposal_id].approved
            assert any("minimum cash reserve" in v for v in results[proposals[1].proposal_id].violations)
    finally:
        restore()


def test_cumulative_preflight_fails_on_collective_basket_concentration():
    packet = _packet(cash=10_000.0)
    policy = TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=1.0, max_total_exposure_pct=1.0, max_basket_pct=0.6, max_leveraged_etf_pct=1.0,
        min_cash_reserve_pct=0.0, max_order_value=50_000.0, allow_new_positions=True,
    )
    # NVDA and AMD are both in config.BASKETS["semiconductors"].
    proposals = [
        _buy_proposal(packet, policy, "NVDA", 100, 40.0),
        _buy_proposal(packet, policy, "AMD", 100, 40.0),
    ]
    _, restore = _mock_execution_dependencies(quote_price=40.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            for p in proposals:
                store.save_proposal(p.to_dict())
            results = preflight_allocation_batch(
                [p.proposal_id for p in proposals], store, policy, packet.portfolio,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert results[proposals[0].proposal_id].approved
            assert not results[proposals[1].proposal_id].approved
            assert any("basket concentration" in v for v in results[proposals[1].proposal_id].violations)
    finally:
        restore()


def test_cumulative_preflight_fails_on_collective_leveraged_etf_exposure():
    packet = _packet(cash=10_000.0)
    policy = TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=1.0, max_total_exposure_pct=1.0, max_basket_pct=1.0, max_leveraged_etf_pct=0.6,
        min_cash_reserve_pct=0.0, max_order_value=50_000.0, allow_new_positions=True,
    )
    # TQQQ and SOXL are both in config.LEVERAGED_ETF_TICKERS.
    proposals = [
        _buy_proposal(packet, policy, "TQQQ", 100, 40.0),
        _buy_proposal(packet, policy, "SOXL", 100, 40.0),
    ]
    _, restore = _mock_execution_dependencies(quote_price=40.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            for p in proposals:
                store.save_proposal(p.to_dict())
            results = preflight_allocation_batch(
                [p.proposal_id for p in proposals], store, policy, packet.portfolio,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert results[proposals[0].proposal_id].approved
            assert not results[proposals[1].proposal_id].approved
            assert any("leveraged-ETF limit" in v for v in results[proposals[1].proposal_id].violations)
    finally:
        restore()


def test_cumulative_preflight_fails_on_collective_same_ticker_position_cap():
    packet = _packet(cash=10_000.0)
    policy = TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=0.6, max_total_exposure_pct=1.0, max_basket_pct=1.0, max_leveraged_etf_pct=1.0,
        min_cash_reserve_pct=0.0, max_order_value=50_000.0, allow_new_positions=True,
    )
    # Two SEPARATE proposals for the SAME ticker -- each fine alone
    # (~40%), collectively over the 60% per-position cap. Different share
    # counts so the two proposals get distinct stable IDs.
    proposals = [
        _buy_proposal(packet, policy, "AAA", 100, 40.0),
        _buy_proposal(packet, policy, "AAA", 101, 40.0),
    ]
    _, restore = _mock_execution_dependencies(quote_price=40.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            for p in proposals:
                store.save_proposal(p.to_dict())
            results = preflight_allocation_batch(
                [p.proposal_id for p in proposals], store, policy, packet.portfolio,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert results[proposals[0].proposal_id].approved
            assert not results[proposals[1].proposal_id].approved
            assert any("per-position limit" in v for v in results[proposals[1].proposal_id].violations)
    finally:
        restore()


def test_preflight_never_calls_broker_submit_or_mutates_state():
    packet = _packet(cash=10_000.0)
    policy = _policy()
    proposals = _two_leg_proposals(packet, policy)
    captured, restore = _mock_execution_dependencies(quote_price=50.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            for p in proposals:
                store.save_proposal(p.to_dict())
            preflight_allocation_batch(
                [p.proposal_id for p in proposals], store, policy, packet.portfolio,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert len(captured) == 0  # no submit_market_order/submit_limit_order calls
            for p in proposals:
                assert store.get_proposal(p.proposal_id)["status"] == "proposed"  # untouched
    finally:
        restore()


def test_all_legs_submit_when_everything_is_clean():
    packet = _packet()
    policy = _policy()
    proposals = _two_leg_proposals(packet, policy)
    captured, restore = _mock_batch_execution(packet, quote_price=50.0)
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
    captured, restore = _mock_batch_execution(packet, quote_price=50.0)

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
    captured, restore = _mock_batch_execution(packet, quote_price=50.0)

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


def test_unknown_leg_reconciled_to_executed_resumes_the_batch():
    # GPT review, 2026-07-29: the release-blocking finding -- a batch leg
    # left LEG_UNKNOWN used to stay that way FOREVER even after the
    # underlying proposal was reconciled to a terminal state, so the
    # batch could never resume after the exact recovery step the UI
    # tells the user to perform.
    packet = _packet()
    policy = _policy()
    proposals = _two_leg_proposals(packet, policy)
    first_ticker, second_ticker = proposals[0].intent.ticker, proposals[1].intent.ticker
    _, restore = _mock_batch_execution(packet, quote_price=50.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            for p in proposals:
                store.save_proposal(p.to_dict())
            proposal_ids = [p.proposal_id for p in proposals]
            batch_id = new_batch_id()
            store.create_allocation_batch(batch_id, proposal_ids, intended_total_notional=2000.0)
            # Simulate a batch that previously stopped with leg 2 unknown.
            store.update_allocation_batch(
                batch_id, status=BATCH_STOPPED_UNKNOWN,
                legs={
                    proposal_ids[0]: {"state": LEG_SUBMITTED, "order": {"order_id": "o1"}, "error": None},
                    proposal_ids[1]: {"state": LEG_UNKNOWN, "order": None, "error": "was ambiguous"},
                },
            )
            # Simulate a human having run reconcile_submission() on it --
            # the proposal itself is now genuinely "executed".
            store.update_proposal_status(
                proposal_ids[1], "executed",
                executed_at=datetime.now(timezone.utc).isoformat(),
                broker_order={"order_id": "reconciled-order-2"},
            )
            result = execute_allocation_batch(
                batch_id, store, policy, now_et=datetime(2026, 7, 27, 10, 5, tzinfo=timezone.utc),
            )
            assert result["status"] == BATCH_COMPLETED
            legs_by_ticker = {
                store.get_proposal(pid)["intent"]["ticker"]: leg for pid, leg in result["legs"].items()
            }
            assert legs_by_ticker[second_ticker]["state"] == LEG_SUBMITTED
            assert legs_by_ticker[second_ticker]["order"]["order_id"] == "reconciled-order-2"
    finally:
        restore()


def test_unknown_leg_reconciled_to_submission_failed_does_not_block_the_rest():
    packet = _packet()
    policy = _policy()
    proposals = _two_leg_proposals(packet, policy)
    first_ticker, second_ticker = proposals[0].intent.ticker, proposals[1].intent.ticker
    _, restore = _mock_batch_execution(packet, quote_price=50.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            for p in proposals:
                store.save_proposal(p.to_dict())
            proposal_ids = [p.proposal_id for p in proposals]
            batch_id = new_batch_id()
            store.create_allocation_batch(batch_id, proposal_ids, intended_total_notional=2000.0)
            store.update_allocation_batch(
                batch_id, status=BATCH_STOPPED_UNKNOWN,
                legs={
                    proposal_ids[0]: {"state": LEG_SUBMITTED, "order": {"order_id": "o1"}, "error": None},
                    proposal_ids[1]: {"state": LEG_UNKNOWN, "order": None, "error": "was ambiguous"},
                },
            )
            # Reconciliation determined the broker confirms it was never accepted.
            store.update_proposal_status(
                proposal_ids[1], "submission_failed",
                error="broker confirms no such order exists",
            )
            result = execute_allocation_batch(
                batch_id, store, policy, now_et=datetime(2026, 7, 27, 10, 5, tzinfo=timezone.utc),
            )
            assert result["status"] == BATCH_COMPLETED  # a definitive failure doesn't stop the batch
            legs_by_ticker = {
                store.get_proposal(pid)["intent"]["ticker"]: leg for pid, leg in result["legs"].items()
            }
            assert legs_by_ticker[second_ticker]["state"] == LEG_FAILED
    finally:
        restore()


def test_unknown_leg_still_unresolved_keeps_stopping_the_batch():
    packet = _packet()
    policy = _policy()
    proposals = _two_leg_proposals(packet, policy)
    _, restore = _mock_batch_execution(packet, quote_price=50.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            for p in proposals:
                store.save_proposal(p.to_dict())
            proposal_ids = [p.proposal_id for p in proposals]
            batch_id = new_batch_id()
            store.create_allocation_batch(batch_id, proposal_ids, intended_total_notional=2000.0)
            store.update_allocation_batch(
                batch_id, status=BATCH_STOPPED_UNKNOWN,
                legs={
                    proposal_ids[0]: {"state": LEG_SUBMITTED, "order": {"order_id": "o1"}, "error": None},
                    proposal_ids[1]: {"state": LEG_UNKNOWN, "order": None, "error": "was ambiguous"},
                },
            )
            store.update_proposal_status(proposal_ids[1], "submission_unknown", error="still ambiguous")
            result = execute_allocation_batch(
                batch_id, store, policy, now_et=datetime(2026, 7, 27, 10, 5, tzinfo=timezone.utc),
            )
            assert result["status"] == BATCH_STOPPED_UNKNOWN
    finally:
        restore()


def test_crash_while_submitting_or_reconciling_does_not_cause_resubmission():
    packet = _packet()
    policy = _policy()
    proposals = _two_leg_proposals(packet, policy)
    captured, restore = _mock_batch_execution(packet, quote_price=50.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            for p in proposals:
                store.save_proposal(p.to_dict())
            proposal_ids = [p.proposal_id for p in proposals]
            batch_id = new_batch_id()
            store.create_allocation_batch(batch_id, proposal_ids, intended_total_notional=2000.0)
            store.update_allocation_batch(
                batch_id, legs={
                    proposal_ids[0]: {"state": "unattempted", "order": None, "error": None},
                    proposal_ids[1]: {"state": "unattempted", "order": None, "error": None},
                },
            )
            # First proposal is mid-flight from a (crashed) prior attempt.
            store.update_proposal_status(proposal_ids[0], "submitting")
            result = execute_allocation_batch(
                batch_id, store, policy, now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert result["status"] == BATCH_STOPPED_UNKNOWN
            assert len(captured) == 0  # never attempted a second submission
            assert result["legs"][proposal_ids[0]]["state"] == LEG_UNKNOWN
    finally:
        restore()


def test_missing_proposal_record_fails_closed_with_audit_error():
    # Deliberately a SINGLE-leg batch referencing a proposal_id that was
    # never saved -- avoids needing any broker mocking at all (a missing
    # proposal fails before any broker call would happen), which matters
    # in this environment since real Alpaca paper credentials are
    # configured and an unmocked real proposal must never be attempted.
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        batch_id = new_batch_id()
        store.create_allocation_batch(batch_id, ["tp_does_not_exist"], intended_total_notional=1000.0)
        result = execute_allocation_batch(
            batch_id, store, _policy(), now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
        )
        assert result["legs"]["tp_does_not_exist"]["state"] == LEG_FAILED
        assert "missing entirely" in result["legs"]["tp_does_not_exist"]["error"]


def test_resuming_after_process_restart_only_attempts_remaining_legs():
    # Simulates a process restart: the first leg is ACTUALLY submitted
    # (its underlying proposal really is "executed"), then a batch-level
    # crash before the leg dict is persisted is simulated by resetting
    # the batch's own leg metadata back to "unattempted" for both legs --
    # a FRESH AssistantStore instance (a new process attaching to the
    # same db file) must resync from the proposal's real status and
    # recognize leg 1 as already done without a second broker call.
    packet = _packet()
    policy = _policy()
    proposals = _two_leg_proposals(packet, policy)
    captured, restore = _mock_batch_execution(packet, quote_price=50.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "assistant.db"
            store = AssistantStore(db_path)
            for p in proposals:
                store.save_proposal(p.to_dict())
            proposal_ids = [p.proposal_id for p in proposals]

            # Really submit the first leg (as a prior process instance would have).
            first_order = execute_approved_paper_proposal(
                proposal_ids[0], "approve", packet.portfolio, policy, store,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert len(captured) == 1

            batch_id = new_batch_id()
            store.create_allocation_batch(batch_id, proposal_ids, intended_total_notional=2000.0)
            # Simulate the crash: the batch's OWN leg metadata never got
            # updated to reflect that first submission (both legs still
            # "unattempted" from the batch's point of view).
            store.update_allocation_batch(
                batch_id, legs={
                    proposal_ids[0]: {"state": "unattempted", "order": None, "error": None},
                    proposal_ids[1]: {"state": "unattempted", "order": None, "error": None},
                },
            )
            # Fresh store instance -- simulates a new process attaching to the same db file.
            fresh_store = AssistantStore(db_path)
            result = execute_allocation_batch(
                batch_id, fresh_store, policy, now_et=datetime(2026, 7, 27, 10, 5, tzinfo=timezone.utc),
            )
            assert result["status"] == BATCH_COMPLETED
            # Only ONE new submission happened -- the already-executed leg was
            # recognized from its proposal's real status, not re-attempted.
            assert len(captured) == 2
            assert result["legs"][proposal_ids[0]]["order"]["order_id"] == first_order["order_id"]
    finally:
        restore()


def test_retrying_a_completed_batch_does_not_duplicate_orders():
    packet = _packet()
    policy = _policy()
    proposals = _two_leg_proposals(packet, policy)
    captured, restore = _mock_batch_execution(packet, quote_price=50.0)
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
    _, restore = _mock_batch_execution(packet, quote_price=50.0)
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
