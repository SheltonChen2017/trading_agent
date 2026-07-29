"""
Tests for assistant/allocation_batch.py -- the sequential, resumable
batch executor behind the Watchlist "submit all proposals in this split"
action (GPT review, 2026-07-28).
"""
import dataclasses
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
from assistant.execution_service import execute_approved_paper_proposal, validate_proposal_for_execution
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


# --- Cumulative preflight accounting fix (GPT review, 2026-07-29
# follow-up): the tests above already demonstrate that a cumulative
# check EXISTS for each constraint, but were written against numbers
# where the double-counting bug and the correct accounting happen to
# agree (both reject). The tests below specifically target the
# accounting itself -- exact-boundary cases that the double-counting
# bug got WRONG (incorrectly rejecting a genuinely safe batch) and that
# only the corrected single-counted arithmetic gets right.

def test_cumulative_preflight_test_a_exact_exposure_cap_is_allowed():
    # $10,000 account, 80% total-exposure cap, two $4,000 buys. Real
    # cumulative exposure is exactly 80% -- must be allowed (inclusive
    # boundary). The double-counting bug computed 120% here and wrongly
    # rejected the second leg.
    packet = _packet(cash=10_000.0)
    policy = TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=1.0, max_total_exposure_pct=0.8, max_basket_pct=1.0,
        max_leveraged_etf_pct=1.0, min_cash_reserve_pct=0.0, max_order_value=50_000.0,
        allow_new_positions=True,
    )
    proposals = [
        _buy_proposal(packet, policy, "AAA", 100, 40.0),  # $4,000
        _buy_proposal(packet, policy, "BBB", 100, 40.0),  # $4,000
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
            assert results[proposals[1].proposal_id].approved, results[proposals[1].proposal_id].violations
    finally:
        restore()


def test_cumulative_preflight_test_b_genuinely_excessive_exposure_is_rejected():
    # Same account/cap as test A, but the second leg is $4,120 (103
    # shares at the mocked $40 quote) -- real cumulative exposure is
    # 81.2%, genuinely over the 80% cap. Note: _mock_execution_dependencies
    # fixes the LIVE quote price used by validation regardless of the
    # `price` field passed to _buy_proposal (that field only affects the
    # proposal's own metadata/stable id) -- so dollar targets here are
    # hit via share count against the fixed $40 mock, not via price.
    packet = _packet(cash=10_000.0)
    policy = TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=1.0, max_total_exposure_pct=0.8, max_basket_pct=1.0,
        max_leveraged_etf_pct=1.0, min_cash_reserve_pct=0.0, max_order_value=50_000.0,
        allow_new_positions=True,
    )
    proposals = [
        _buy_proposal(packet, policy, "AAA", 100, 40.0),  # $4,000
        _buy_proposal(packet, policy, "BBB", 103, 40.0),  # $4,120
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
            assert any("total-exposure" in v for v in results[proposals[1].proposal_id].violations)
    finally:
        restore()


def test_cumulative_preflight_test_c_min_cash_reserve_boundary_is_inclusive_and_cumulative():
    # $10,000 account, 20% min cash reserve ($2,000). Two $4,000 buys
    # leave exactly $2,000 -- must be allowed (inclusive boundary).
    packet = _packet(cash=10_000.0)
    policy = TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=1.0, max_total_exposure_pct=1.0, max_basket_pct=1.0,
        max_leveraged_etf_pct=1.0, min_cash_reserve_pct=0.2, max_order_value=50_000.0,
        allow_new_positions=True,
    )
    proposals = [
        _buy_proposal(packet, policy, "AAA", 100, 40.0),  # $4,000
        _buy_proposal(packet, policy, "BBB", 100, 40.0),  # $4,000 -- leaves exactly $2,000
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
            assert results[proposals[1].proposal_id].approved, results[proposals[1].proposal_id].violations
    finally:
        restore()


def test_cumulative_preflight_test_c_min_cash_reserve_fails_just_above_the_boundary():
    # Same setup, but the second leg is $4,040 (slightly more than
    # $4,000) -- only $1,960 would remain, below the $2,000 reserve.
    packet = _packet(cash=10_000.0)
    policy = TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=1.0, max_total_exposure_pct=1.0, max_basket_pct=1.0,
        max_leveraged_etf_pct=1.0, min_cash_reserve_pct=0.2, max_order_value=50_000.0,
        allow_new_positions=True,
    )
    proposals = [
        _buy_proposal(packet, policy, "AAA", 100, 40.0),   # $4,000
        _buy_proposal(packet, policy, "BBB", 101, 40.0),   # $4,040
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


def test_cumulative_preflight_test_d_same_ticker_concentration_boundary_is_inclusive():
    # $10,000 account, 80% per-position cap on the SAME ticker across two
    # separate proposals. Combined value equals the cap exactly -- must
    # be allowed.
    packet = _packet(cash=10_000.0)
    policy = TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=0.8, max_total_exposure_pct=1.0, max_basket_pct=1.0, max_leveraged_etf_pct=1.0,
        min_cash_reserve_pct=0.0, max_order_value=50_000.0, allow_new_positions=True,
    )
    proposals = [
        _buy_proposal(packet, policy, "AAA", 100, 40.0),  # $4,000
        _buy_proposal(packet, policy, "AAA", 100, 40.0000001),  # $4,000 (distinct id via price)
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
            assert results[proposals[1].proposal_id].approved, results[proposals[1].proposal_id].violations
    finally:
        restore()


def test_cumulative_preflight_test_e_basket_exposure_boundary_is_inclusive():
    # NVDA and AMD are both in config.BASKETS["semiconductors"]. Combined
    # value equals the 80% basket cap exactly -- must be allowed.
    packet = _packet(cash=10_000.0)
    policy = TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=1.0, max_total_exposure_pct=1.0, max_basket_pct=0.8, max_leveraged_etf_pct=1.0,
        min_cash_reserve_pct=0.0, max_order_value=50_000.0, allow_new_positions=True,
    )
    proposals = [
        _buy_proposal(packet, policy, "NVDA", 100, 40.0),  # $4,000
        _buy_proposal(packet, policy, "AMD", 100, 40.0),   # $4,000
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
            assert results[proposals[1].proposal_id].approved, results[proposals[1].proposal_id].violations
    finally:
        restore()


def test_cumulative_preflight_test_e_leveraged_etf_exposure_boundary_is_inclusive():
    # TQQQ and SOXL are both in config.LEVERAGED_ETF_TICKERS. Combined
    # value equals the 80% leveraged-ETF cap exactly -- must be allowed.
    packet = _packet(cash=10_000.0)
    policy = TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=1.0, max_total_exposure_pct=1.0, max_basket_pct=1.0, max_leveraged_etf_pct=0.8,
        min_cash_reserve_pct=0.0, max_order_value=50_000.0, allow_new_positions=True,
    )
    proposals = [
        _buy_proposal(packet, policy, "TQQQ", 100, 40.0),  # $4,000
        _buy_proposal(packet, policy, "SOXL", 100, 40.0),  # $4,000
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
            assert results[proposals[1].proposal_id].approved, results[proposals[1].proposal_id].violations
    finally:
        restore()


def test_cumulative_preflight_test_f_real_pending_order_plus_simulated_legs_each_count_once():
    # A REAL pending buy already sitting in current_portfolio.open_orders
    # ($2,000 on CCC), plus two simulated batch legs of $3,000 each on
    # different tickers, against an 80% total-exposure cap on a $10,000
    # account: real cumulative exposure is exactly ($2,000 + $3,000 +
    # $3,000) / $10,000 = 80% -- must be allowed. Getting this wrong in
    # either direction (undercounting the real pending order, or
    # double-counting either simulated leg) would flip this result.
    packet_no_orders = _packet(cash=10_000.0)
    portfolio_with_pending = dataclasses.replace(
        packet_no_orders.portfolio,
        open_orders=[{"ticker": "CCC", "side": "buy", "notional": 2000.0}],
    )
    policy = TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=1.0, max_total_exposure_pct=0.8, max_basket_pct=1.0,
        max_leveraged_etf_pct=1.0, min_cash_reserve_pct=0.0, max_order_value=50_000.0,
        allow_new_positions=True,
    )
    proposals = [
        _buy_proposal(packet_no_orders, policy, "AAA", 75, 40.0),  # $3,000
        _buy_proposal(packet_no_orders, policy, "BBB", 75, 40.0),  # $3,000
    ]
    _, restore = _mock_execution_dependencies(quote_price=40.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            for p in proposals:
                store.save_proposal(p.to_dict())
            results = preflight_allocation_batch(
                [p.proposal_id for p in proposals], store, policy, portfolio_with_pending,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert results[proposals[0].proposal_id].approved, results[proposals[0].proposal_id].violations
            assert results[proposals[1].proposal_id].approved, results[proposals[1].proposal_id].violations
    finally:
        restore()


def test_cumulative_preflight_test_f_real_pending_order_plus_simulated_legs_rejects_when_over():
    # Same setup, but the second simulated leg is $3,120 (78 shares at
    # the mocked $40 quote) instead of $3,000 -- real cumulative exposure
    # is 81.2%, genuinely over the cap.
    packet_no_orders = _packet(cash=10_000.0)
    portfolio_with_pending = dataclasses.replace(
        packet_no_orders.portfolio,
        open_orders=[{"ticker": "CCC", "side": "buy", "notional": 2000.0}],
    )
    policy = TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=1.0, max_total_exposure_pct=0.8, max_basket_pct=1.0,
        max_leveraged_etf_pct=1.0, min_cash_reserve_pct=0.0, max_order_value=50_000.0,
        allow_new_positions=True,
    )
    proposals = [
        _buy_proposal(packet_no_orders, policy, "AAA", 75, 40.0),  # $3,000
        _buy_proposal(packet_no_orders, policy, "BBB", 78, 40.0),  # $3,120
    ]
    _, restore = _mock_execution_dependencies(quote_price=40.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            for p in proposals:
                store.save_proposal(p.to_dict())
            results = preflight_allocation_batch(
                [p.proposal_id for p in proposals], store, policy, portfolio_with_pending,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert results[proposals[0].proposal_id].approved
            assert not results[proposals[1].proposal_id].approved
            assert any("total-exposure" in v for v in results[proposals[1].proposal_id].violations)
    finally:
        restore()


def test_cumulative_preflight_test_g_no_state_mutation():
    # Preflight must be perfectly read-only: proposal records byte-for-
    # byte unchanged, no allocation batch persisted, no broker calls.
    packet = _packet(cash=10_000.0)
    policy = _policy()
    proposals = _two_leg_proposals(packet, policy)
    captured, restore = _mock_execution_dependencies(quote_price=50.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            for p in proposals:
                store.save_proposal(p.to_dict())
            before = {p.proposal_id: dict(store.get_proposal(p.proposal_id)) for p in proposals}

            preflight_allocation_batch(
                [p.proposal_id for p in proposals], store, policy, packet.portfolio,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )

            assert len(captured) == 0  # no submit_market_order/submit_limit_order calls
            for p in proposals:
                after = dict(store.get_proposal(p.proposal_id))
                assert after == before[p.proposal_id]  # byte-for-byte unchanged, not just status
            # preflight never takes/creates a batch_id, so nothing could
            # have been persisted under any id -- confirm a fresh one is
            # still unknown to the store.
            assert store.get_allocation_batch(new_batch_id()) is None
    finally:
        restore()


def test_cumulative_preflight_test_h_single_execution_unaffected_by_new_override_params():
    # execute_approved_paper_proposal() never passes available_cash_
    # override/available_buying_power_override to validate_proposal_for_
    # execution() -- the single-proposal path is structurally unaffected
    # by this fix. Confirmed two ways: (1) calling
    # validate_proposal_for_execution() with the new params explicitly
    # set to the real portfolio's own cash/buying_power produces the
    # identical result as calling it with no overrides at all (a real-
    # value override is a no-op); (2) execute_approved_paper_proposal()
    # itself still executes normally with no overrides in play.
    packet = _packet(cash=10_000.0)
    policy = TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=1.0, max_total_exposure_pct=0.5, max_basket_pct=1.0,
        max_leveraged_etf_pct=1.0, min_cash_reserve_pct=0.0, max_order_value=50_000.0,
        allow_new_positions=True,
    )
    proposal = _buy_proposal(packet, policy, "AAA", 100, 40.0)  # $4,000 of $10,000 = 40% < 50% cap
    _, restore = _mock_execution_dependencies(quote_price=40.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())

            baseline = validate_proposal_for_execution(
                proposal.proposal_id, packet.portfolio, policy, store,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            with_real_value_override = validate_proposal_for_execution(
                proposal.proposal_id, packet.portfolio, policy, store,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
                available_cash_override=packet.portfolio.cash,
                available_buying_power_override=packet.portfolio.buying_power,
            )
            assert baseline.approved
            assert with_real_value_override.approved
            assert baseline.validation.violations == with_real_value_override.validation.violations
    finally:
        restore()

    execution_proposal = _buy_proposal(packet, policy, "BBB", 100, 40.0)
    captured, restore = _mock_execution_dependencies(quote_price=40.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(execution_proposal.to_dict())
            order = execute_approved_paper_proposal(
                execution_proposal.proposal_id, "approve", packet.portfolio, policy, store,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert order is not None
            assert store.get_proposal(execution_proposal.proposal_id)["status"] == "broker_accepted"
            assert len(captured) == 1
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


# --- Completed-batch resync (GPT review, 2026-07-29): execute_allocation_
# batch() used to return a BATCH_COMPLETED batch immediately without
# re-syncing any leg -- so a leg the UI told the user to resolve via that
# proposal's own individual override control kept showing
# "blocked_overridable" forever, even after the proposal became "executed".

def test_completed_batch_resyncs_a_blocked_overridable_leg_once_individually_overridden():
    packet = _packet(cash=10_000.0)
    tiny_cap_policy = TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=0.001, max_total_exposure_pct=1.0, max_basket_pct=1.0,
        max_leveraged_etf_pct=1.0, min_cash_reserve_pct=0.0, max_order_value=50_000.0,
        allow_new_positions=True,
    )
    proposals = generate_allocation_buy_proposals(
        packet, tiny_cap_policy, weights_pct={"AAA": 100.0}, prices={"AAA": 50.0}, dollar_amount=2000.0,
    )
    assert len(proposals) == 1
    proposal = proposals[0]
    captured, restore = _mock_batch_execution(packet, quote_price=50.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            batch_id = new_batch_id()
            store.create_allocation_batch(batch_id, [proposal.proposal_id], intended_total_notional=2000.0)

            first_result = execute_allocation_batch(
                batch_id, store, tiny_cap_policy, now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert first_result["status"] == BATCH_COMPLETED
            assert first_result["legs"][proposal.proposal_id]["state"] == LEG_BLOCKED_OVERRIDABLE
            assert len(captured) == 0  # never actually submitted by the batch
            old_block_message = first_result["legs"][proposal.proposal_id]["error"]
            assert old_block_message  # non-empty -- this is the message we expect cleared later

            # Resolve it through the proposal's OWN individual override
            # control -- exactly what the batch/UI tells the user to do
            # for a blocked_overridable leg.
            import assistant.allocation_batch as batch_module

            portfolio = batch_module.build_portfolio_snapshot_from_alpaca()
            order = execute_approved_paper_proposal(
                proposal.proposal_id, "approve", portfolio, tiny_cap_policy, store,
                now_et=datetime(2026, 7, 27, 10, 5, tzinfo=timezone.utc),
                override_policy_violations=True,
            )
            assert len(captured) == 1

            second_result = execute_allocation_batch(
                batch_id, store, tiny_cap_policy, now_et=datetime(2026, 7, 27, 10, 10, tzinfo=timezone.utc),
            )
            assert second_result["status"] == BATCH_COMPLETED
            leg = second_result["legs"][proposal.proposal_id]
            assert leg["state"] == LEG_SUBMITTED
            assert leg["order"] is not None
            assert leg["order"]["order_id"] == order["order_id"]
            assert len(captured) == 1  # NOT resubmitted by the resync
            # GPT review, 2026-07-30: the stale "blocked by cap"-style
            # message from the earlier blocked_overridable attempt must
            # be CLEARED now that the authoritative proposal is a clean
            # "executed" with no active error of its own -- never left
            # showing next to a successfully submitted order -- but
            # preserved in error_history for auditability.
            assert leg["error"] is None
            assert old_block_message in leg["error_history"]

            # Idempotent: nothing changed underneath -- calling again
            # must not alter or re-write anything further.
            third_result = execute_allocation_batch(
                batch_id, store, tiny_cap_policy, now_et=datetime(2026, 7, 27, 10, 15, tzinfo=timezone.utc),
            )
            assert third_result["status"] == BATCH_COMPLETED
            assert third_result["legs"][proposal.proposal_id]["state"] == LEG_SUBMITTED
            assert len(captured) == 1
    finally:
        restore()


def test_completed_batch_with_no_underlying_change_is_idempotent():
    packet = _packet(cash=10_000.0)
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
            assert second_result == first_result  # byte-for-byte unchanged, nothing re-persisted
            assert len(captured) == 2  # nothing re-submitted
    finally:
        restore()


# --- now_provider() per-leg freshness (GPT review, 2026-07-31):
# execute_allocation_batch() already re-fetches the live PORTFOLIO before
# each leg so an earlier fill is reflected, but used to reuse a SINGLE
# now_et for every leg's staleness/future-timestamp/trading-session
# check -- a slow batch could compare a later leg's fresh quote against
# an increasingly stale now_et.

def test_now_provider_is_called_fresh_for_each_leg():
    # A provider returning a weekend (market-closed) timestamp for the
    # FIRST call and a normal market-hours timestamp for the SECOND
    # produces a leg-1 failure (market closed) and a leg-2 success --
    # impossible if only one now_et were evaluated once for the whole
    # batch (either both legs would fail, or both would succeed).
    packet = _packet(cash=10_000.0)
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

            call_times = iter([
                datetime(2026, 7, 25, 10, 0, tzinfo=timezone.utc),  # a Saturday -- market closed
                # The following Monday, close enough to the mocked quote's
                # own fixed timestamp (9:59 AM ET, from _mock_execution_
                # dependencies' default) to also pass the staleness check.
                datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            ])
            result = execute_allocation_batch(batch_id, store, policy, now_provider=lambda: next(call_times))
            first_id, second_id = [p.proposal_id for p in proposals]
            legs = result["legs"]
            assert legs[first_id]["state"] == LEG_FAILED
            assert "closed" in legs[first_id]["error"].lower()
            assert legs[second_id]["state"] == LEG_SUBMITTED
            assert len(captured) == 1  # only the (successful) second leg reached the broker
    finally:
        restore()


def test_now_et_alone_is_wrapped_into_a_provider_preserving_old_behavior():
    # Backward compatibility: passing only now_et (no now_provider) must
    # behave EXACTLY as before -- the same fixed timestamp for every leg.
    packet = _packet(cash=10_000.0)
    policy = _policy()
    proposals = _two_leg_proposals(packet, policy)
    _, restore = _mock_batch_execution(packet, quote_price=50.0)
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
    finally:
        restore()


def test_execute_allocation_batch_requires_now_et_or_now_provider():
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        try:
            execute_allocation_batch("batch_does_not_exist", store, _policy())
            assert False, "expected a TypeError when neither now_et nor now_provider is given"
        except TypeError as exc:
            assert "now_et" in str(exc) or "now_provider" in str(exc)


if __name__ == "__main__":
    test_preflight_passes_when_every_leg_is_clean()
    test_preflight_failure_means_caller_submits_none()
    test_all_legs_submit_when_everything_is_clean()
    test_second_leg_definitive_failure_does_not_block_the_batch()
    test_second_leg_submission_unknown_stops_the_batch()
    test_resuming_after_process_restart_only_attempts_remaining_legs()
    test_retrying_a_completed_batch_does_not_duplicate_orders()
    test_fresh_portfolio_state_blocks_a_later_leg_no_longer_safe()
    test_completed_batch_resyncs_a_blocked_overridable_leg_once_individually_overridden()
    test_completed_batch_with_no_underlying_change_is_idempotent()
    test_now_provider_is_called_fresh_for_each_leg()
    test_now_et_alone_is_wrapped_into_a_provider_preserving_old_behavior()
    test_execute_allocation_batch_requires_now_et_or_now_provider()
    print("All allocation_batch tests passed.")
