"""
Tests for the pure/deterministic helper functions in
scripts/personal_assistant_ui.py -- specifically _allocation_input_
signature() (GPT review, 2026-07-29: it used to bind only to
packet.portfolio.as_of, a plain ISO date, so cash/positions/buying_power/
open_orders could all change intraday without invalidating a stale
allocation card's confirmation/override state).

Importing this module directly runs it in Streamlit "bare mode" (no
ScriptRunContext) -- this prints harmless warnings but does not crash,
and is the only way to reach its pure helper functions without spinning
up a real Streamlit server. Run with: python -m pytest tests/test_personal_assistant_ui.py
"""
import copy
import dataclasses
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.context_builder import build_portfolio_snapshot, build_risk_exposure
from assistant.policy import TradingPolicy
from assistant.schemas import DecisionPacket, MarketRegime
from scripts.personal_assistant_ui import _allocation_input_signature


def _policy(version: str = "test", max_order_value: float = 5_000.0) -> TradingPolicy:
    return TradingPolicy(version=version, name="test", execution_mode="paper", max_order_value=max_order_value)


def _packet(positions: list[dict], cash: float = 5_000.0, buying_power: float | None = None, open_orders=None) -> DecisionPacket:
    snapshot = build_portfolio_snapshot(
        positions, cash=cash, buying_power=buying_power, open_orders=open_orders or [],
    )
    return DecisionPacket(
        generated_at="2026-07-29T12:00:00+00:00",
        portfolio=snapshot,
        risk=build_risk_exposure(snapshot),
        regime=MarketRegime(benchmark_ticker="QQQ", trend="uptrend", volatility_regime="low_vol", trailing_volatility_pct=1.0, as_of="2026-07-29"),
        signals=[], upcoming_events=[], warnings=[], policy_version="test",
    )


_WEIGHTS = {"AAPL": 60.0, "MSFT": 40.0}
_PRICES = {"AAPL": 150.0, "MSFT": 300.0}
_PRICE_AS_OF = {"AAPL": "2026-07-29", "MSFT": "2026-07-29"}


def _signature(packet, policy=None, dollar_amount=1000.0, max_weight_pct=100.0):
    return _allocation_input_signature(
        _WEIGHTS, dollar_amount, _PRICES, _PRICE_AS_OF, max_weight_pct, policy or _policy(), packet,
    )


def test_unchanged_snapshot_produces_a_stable_signature():
    packet = _packet([{"ticker": "AAPL", "shares": 10, "entry_price": 100.0, "current_price": 150.0}])
    assert _signature(packet) == _signature(packet)


def test_changing_cash_invalidates_the_signature():
    packet_a = _packet([], cash=5_000.0)
    packet_b = _packet([], cash=6_000.0)
    assert _signature(packet_a) != _signature(packet_b)


def test_changing_a_held_position_invalidates_the_signature():
    packet_a = _packet([{"ticker": "AAPL", "shares": 10, "entry_price": 100.0, "current_price": 150.0}])
    packet_b = _packet([{"ticker": "AAPL", "shares": 20, "entry_price": 100.0, "current_price": 150.0}])
    assert _signature(packet_a) != _signature(packet_b)


def test_changing_buying_power_invalidates_the_signature():
    packet_a = _packet([], cash=5_000.0, buying_power=5_000.0)
    packet_b = _packet([], cash=5_000.0, buying_power=1_000.0)
    assert _signature(packet_a) != _signature(packet_b)


def test_adding_an_open_order_invalidates_the_signature():
    packet_a = _packet([], open_orders=[])
    packet_b = _packet(
        [], open_orders=[{"order_id": "o1", "ticker": "AAPL", "side": "buy", "shares": 5, "type": "market"}],
    )
    assert _signature(packet_a) != _signature(packet_b)


def test_changing_an_open_order_invalidates_the_signature():
    packet_a = _packet(
        [], open_orders=[{"order_id": "o1", "ticker": "AAPL", "side": "buy", "shares": 5, "type": "market"}],
    )
    packet_b = _packet(
        [], open_orders=[{"order_id": "o1", "ticker": "AAPL", "side": "buy", "shares": 50, "type": "market"}],
    )
    assert _signature(packet_a) != _signature(packet_b)


def test_removing_an_open_order_invalidates_the_signature():
    packet_a = _packet(
        [], open_orders=[{"order_id": "o1", "ticker": "AAPL", "side": "buy", "shares": 5, "type": "market"}],
    )
    packet_b = _packet([], open_orders=[])
    assert _signature(packet_a) != _signature(packet_b)


def test_reordering_identical_positions_does_not_invalidate_the_signature():
    positions = [
        {"ticker": "AAPL", "shares": 10, "entry_price": 100.0, "current_price": 150.0},
        {"ticker": "MSFT", "shares": 5, "entry_price": 200.0, "current_price": 300.0},
    ]
    packet_a = _packet(positions)
    packet_b = _packet(list(reversed(positions)))
    assert _signature(packet_a) == _signature(packet_b)


def test_reordering_identical_open_orders_does_not_invalidate_the_signature():
    orders = [
        {"order_id": "o1", "ticker": "AAPL", "side": "buy", "shares": 5, "type": "market"},
        {"order_id": "o2", "ticker": "MSFT", "side": "sell", "shares": 3, "type": "market"},
    ]
    packet_a = _packet([], open_orders=orders)
    packet_b = _packet([], open_orders=list(reversed(orders)))
    assert _signature(packet_a) == _signature(packet_b)


def test_open_orders_available_flag_invalidates_the_signature():
    packet_a = _packet([])
    packet_b = _packet([])
    packet_b = dataclasses.replace(packet_b, portfolio=dataclasses.replace(packet_b.portfolio, open_orders_available=False))
    assert _signature(packet_a) != _signature(packet_b)


def test_policy_change_still_invalidates_the_signature():
    packet = _packet([])
    policy_a = _policy(version="v1")
    policy_b = _policy(version="v1", max_order_value=1.0)  # same version, different fingerprint content
    assert _signature(packet, policy=policy_a) != _signature(packet, policy=policy_b)


def test_price_change_still_invalidates_the_signature():
    packet = _packet([])
    sig_a = _allocation_input_signature(_WEIGHTS, 1000.0, _PRICES, _PRICE_AS_OF, 100.0, _policy(), packet)
    other_prices = dict(_PRICES)
    other_prices["AAPL"] = 999.0
    sig_b = _allocation_input_signature(_WEIGHTS, 1000.0, other_prices, _PRICE_AS_OF, 100.0, _policy(), packet)
    assert sig_a != sig_b


if __name__ == "__main__":
    test_unchanged_snapshot_produces_a_stable_signature()
    test_changing_cash_invalidates_the_signature()
    test_changing_a_held_position_invalidates_the_signature()
    test_changing_buying_power_invalidates_the_signature()
    test_adding_an_open_order_invalidates_the_signature()
    test_changing_an_open_order_invalidates_the_signature()
    test_removing_an_open_order_invalidates_the_signature()
    test_reordering_identical_positions_does_not_invalidate_the_signature()
    test_reordering_identical_open_orders_does_not_invalidate_the_signature()
    test_open_orders_available_flag_invalidates_the_signature()
    test_policy_change_still_invalidates_the_signature()
    test_price_change_still_invalidates_the_signature()
    print("All personal_assistant_ui tests passed.")
