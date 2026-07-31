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

import streamlit as st

import scripts.personal_assistant_ui as ui
from assistant.context_builder import build_portfolio_snapshot, build_risk_exposure
from assistant.policy import DEFAULT_POLICY_PATH, TradingPolicy, compute_policy_fingerprint
from assistant.proposal_status import STATUSES
from assistant.schemas import DecisionPacket, MarketRegime
from scripts.personal_assistant_ui import (
    _allocation_input_signature,
    _cache_committee_result,
    _clear_confirmation_state_if_digest_changed,
    _committee_result_for_input,
    _load_packet,
    _portfolio_context_payload,
    _proposal_content_digest,
    _proposal_status_category,
)


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


# --- _portfolio_context_payload() / _proposal_content_digest() (GPT
# review, 2026-07-30): ordinary Selling/Propose & Approve/Watchlist
# proposal cards had NO portfolio-state binding at all -- a typed
# "approve" or override could remain armed, and displayed impact/
# violations could go stale, after cash/positions/buying_power/open
# orders changed underneath an unchanged card.

def _proposal(reference_price=150.0, shares=10, ticker="AAPL", side="buy", expires_at="2026-07-30T00:00:00+00:00"):
    return {
        "proposal_id": "tp_test",
        "intent": {"ticker": ticker, "side": side, "shares": shares, "order_type": "market", "limit_price": None},
        "reference_price": reference_price,
        "expires_at": expires_at,
    }


def _digest(proposal, packet, policy=None):
    policy = policy or _policy()
    return _proposal_content_digest(
        proposal, compute_policy_fingerprint(policy), _portfolio_context_payload(packet.portfolio),
    )


def test_portfolio_context_payload_unaffected_by_current_price_or_market_value_alone():
    # GPT review, 2026-07-31: current_price/market_value move continuously
    # with live quotes during market hours even with zero real account
    # change -- binding to them exactly made a typed confirmation
    # intermittently or continuously impossible to complete. Same shares,
    # same (banded) cash -- only current_price/market_value differ -- must
    # NOT change the payload.
    packet_a = _packet([{"ticker": "AAPL", "shares": 10, "entry_price": 100.0, "current_price": 150.0}])
    packet_b = _packet([{"ticker": "AAPL", "shares": 10, "entry_price": 100.0, "current_price": 175.0}])
    assert _portfolio_context_payload(packet_a.portfolio) == _portfolio_context_payload(packet_b.portfolio)


def test_portfolio_context_payload_bands_small_cash_fluctuations_away():
    # A few dollars of noise (well under the $100 band) must not
    # invalidate confirmation -- this is the whole point of banding.
    packet_a = _packet([], cash=10_000.0)
    packet_b = _packet([], cash=10_030.0)
    assert _portfolio_context_payload(packet_a.portfolio) == _portfolio_context_payload(packet_b.portfolio)


def test_portfolio_context_payload_still_invalidates_across_a_cash_band_boundary():
    packet_a = _packet([], cash=10_000.0)
    packet_b = _packet([], cash=10_200.0)  # a real $200 change -- crosses the $100 band
    assert _portfolio_context_payload(packet_a.portfolio) != _portfolio_context_payload(packet_b.portfolio)


def test_portfolio_context_payload_stable_across_reordered_positions_and_orders():
    positions = [
        {"ticker": "AAPL", "shares": 10, "entry_price": 100.0, "current_price": 150.0},
        {"ticker": "MSFT", "shares": 5, "entry_price": 200.0, "current_price": 300.0},
    ]
    orders = [
        {"order_id": "o1", "ticker": "AAPL", "side": "buy", "shares": 5, "type": "market"},
        {"order_id": "o2", "ticker": "MSFT", "side": "sell", "shares": 3, "type": "market"},
    ]
    packet_a = _packet(positions, open_orders=orders)
    packet_b = _packet(list(reversed(positions)), open_orders=list(reversed(orders)))
    assert _portfolio_context_payload(packet_a.portfolio) == _portfolio_context_payload(packet_b.portfolio)


def test_proposal_digest_changes_when_portfolio_context_changes():
    proposal = _proposal()
    packet_a = _packet([], cash=5_000.0)
    packet_b = _packet([], cash=6_000.0)
    assert _digest(proposal, packet_a) != _digest(proposal, packet_b)


def test_proposal_digest_stable_when_nothing_changes():
    proposal = _proposal()
    packet = _packet([{"ticker": "AAPL", "shares": 10, "entry_price": 100.0, "current_price": 150.0}])
    assert _digest(proposal, packet) == _digest(proposal, packet)


def test_proposal_digest_changes_with_policy_change():
    proposal = _proposal()
    packet = _packet([])
    policy_a = _policy(version="v1")
    policy_b = _policy(version="v1", max_order_value=1.0)  # same version, different fingerprint content
    assert _digest(proposal, packet, policy=policy_a) != _digest(proposal, packet, policy=policy_b)


def test_proposal_digest_changes_with_reference_price_change():
    packet = _packet([])
    proposal_a = _proposal(reference_price=150.0)
    proposal_b = _proposal(reference_price=151.0)
    assert _digest(proposal_a, packet) != _digest(proposal_b, packet)


def test_proposal_digest_changes_with_intent_shares_change():
    packet = _packet([])
    proposal_a = _proposal(shares=10)
    proposal_b = _proposal(shares=20)
    assert _digest(proposal_a, packet) != _digest(proposal_b, packet)


# --- _clear_confirmation_state_if_digest_changed() (GPT review,
# 2026-07-30): must clear BOTH the ordinary typed confirmation AND any
# previously typed override phrase -- the override phrase specifically
# was never cleared before, which could leave the override button
# immediately re-enabled if the banner reappeared for the same intent.

def test_clear_confirmation_state_clears_confirm_and_override_phrase_on_change():
    session_state = {
        "confirm_tp_1": "approve",
        "override_available_tp_1": ["some violation"],
        "override_confirm_tp_1": "OVERRIDE BUY 10 AAPL",
        "committee_result_tp_1": {"input_hash": "old", "result": object()},
        "content_digest_tp_1": "old-digest",
    }
    changed = _clear_confirmation_state_if_digest_changed(session_state, "tp_1", "new-digest")
    assert changed is True
    assert session_state["confirm_tp_1"] == ""
    assert "override_available_tp_1" not in session_state
    assert "override_confirm_tp_1" not in session_state
    assert "committee_result_tp_1" not in session_state
    assert session_state["content_digest_tp_1"] == "new-digest"


def test_clear_confirmation_state_no_op_when_digest_unchanged():
    session_state = {
        "confirm_tp_1": "approve",
        "override_confirm_tp_1": "OVERRIDE BUY 10 AAPL",
        "content_digest_tp_1": "same-digest",
    }
    changed = _clear_confirmation_state_if_digest_changed(session_state, "tp_1", "same-digest")
    assert changed is False
    assert session_state["confirm_tp_1"] == "approve"  # untouched
    assert session_state["override_confirm_tp_1"] == "OVERRIDE BUY 10 AAPL"  # untouched


def test_committee_cache_is_bound_to_exact_projected_input_hash():
    session_state = {}
    result = object()
    _cache_committee_result(session_state, "tp_1", "hash-a", result)

    assert _committee_result_for_input(session_state, "tp_1", "hash-a") is result
    assert _committee_result_for_input(session_state, "tp_1", "hash-b") is None
    assert "committee_result_tp_1" not in session_state


def test_legacy_unbound_committee_cache_is_refused():
    session_state = {"committee_result_tp_1": object()}
    assert _committee_result_for_input(session_state, "tp_1", "hash-a") is None
    assert "committee_result_tp_1" not in session_state


def test_clear_confirmation_state_handles_first_render_with_no_prior_digest():
    session_state = {}
    changed = _clear_confirmation_state_if_digest_changed(session_state, "tp_1", "first-digest")
    assert changed is True
    assert session_state["confirm_tp_1"] == ""
    assert session_state["content_digest_tp_1"] == "first-digest"


# --- _proposal_status_category() (GPT review, 2026-07-31): a stale
# st.session_state proposal snapshot kept showing approval controls even
# after the underlying proposal was already executed/blocked/expired
# elsewhere -- this is the pure routing logic behind reloading the
# authoritative record and gating approval controls by status.

def test_proposal_status_category_covers_every_real_status():
    # Every status this project's own STATUSES tuple actually emits must
    # route somewhere sensible -- never silently fall through unclassified.
    expected = {
        "proposed": "approvable",
        "override_available": "approvable",
        "validating": "in_progress",
        "approved": "in_progress",
        "blocked": "failed",
        "validation_failed": "failed",
        "submission_failed": "failed",
        "expired": "failed",
        "canceled": "failed",
        "broker_rejected": "failed",
        "broker_expired": "failed",
        "filled": "filled",
        "broker_accepted": "working",
        "partially_filled": "working",
        "cancel_pending": "working",
        "executed": "unresolved",
        "submitting": "unresolved",
        "submission_unknown": "unresolved",
        "reconciling": "unresolved",
    }
    assert set(expected) == set(STATUSES), "test fixture is out of sync with assistant.proposal_status.STATUSES"
    for status in STATUSES:
        assert _proposal_status_category(status) == expected[status], status


def test_proposal_status_category_unknown_status_is_never_approvable():
    assert _proposal_status_category("some_future_status") != "approvable"


# --- _load_packet() / _load_base_packet() / _load_live_events_for_tickers()
# (GPT review, 2026-07-31): `include_events` used to be part of the cache
# key for the single monolithic packet-loading function, so a tab
# wanting live events and a tab that didn't were separately-cached,
# separately-fetched calls -- two tabs in the SAME rerun could see two
# DIFFERENT account/position/open-order snapshots from two different
# instants. Mocks ui.build_decision_packet/ui.get_upcoming_events
# entirely so this test never touches the network (build_decision_packet
# always fetches real market-regime data regardless of Alpaca
# configuration).

def _fake_packet_builder(calls):
    def _build(*args, **kwargs):
        calls.append(kwargs.get("include_live_events"))
        snapshot = build_portfolio_snapshot([], cash=1234.0)
        return DecisionPacket(
            generated_at="fixed-generated-at", portfolio=snapshot, risk=build_risk_exposure(snapshot),
            regime=MarketRegime(benchmark_ticker="QQQ", trend=None, volatility_regime=None,
                                 trailing_volatility_pct=None, as_of="2026-07-31"),
            signals=[], upcoming_events=[], warnings=[], policy_version="test",
        )
    return _build


def test_load_packet_shares_the_same_base_snapshot_regardless_of_include_events():
    build_calls = []
    original_build = ui.build_decision_packet
    original_get_events = ui.get_upcoming_events
    ui.build_decision_packet = _fake_packet_builder(build_calls)
    ui.get_upcoming_events = lambda tickers, fetch_live=False: ["FAKE_EVENT"]
    st.cache_data.clear()
    try:
        policy_a, packet_a = _load_packet(str(DEFAULT_POLICY_PATH), False)
        policy_b, packet_b = _load_packet(str(DEFAULT_POLICY_PATH), True)
        # The base builder is called through the cache with
        # include_live_events=False EVERY time, and only ONCE total --
        # requesting events on the second call must not trigger a second
        # base-snapshot build.
        assert build_calls == [False]
        assert packet_a.generated_at == packet_b.generated_at == "fixed-generated-at"
        assert packet_a.portfolio.cash == packet_b.portfolio.cash == 1234.0
        assert packet_a.upcoming_events == []
        assert packet_b.upcoming_events == ["FAKE_EVENT"]
    finally:
        ui.build_decision_packet = original_build
        ui.get_upcoming_events = original_get_events
        st.cache_data.clear()


def test_load_packet_no_events_never_calls_the_live_events_function():
    events_calls = []
    original_build = ui.build_decision_packet
    original_get_events = ui.get_upcoming_events
    ui.build_decision_packet = _fake_packet_builder([])
    ui.get_upcoming_events = lambda tickers, fetch_live=False: (events_calls.append(tickers), [])[1]
    st.cache_data.clear()
    try:
        _load_packet(str(DEFAULT_POLICY_PATH), False)
        assert events_calls == []
    finally:
        ui.build_decision_packet = original_build
        ui.get_upcoming_events = original_get_events
        st.cache_data.clear()


# --- Briefing tab persistence audit fidelity (GPT review, 2026-08-01):
# scripts/personal_assistant_ui.py:712-721 saves whatever _load_packet()
# returns -- base or event-enriched, depending on that session's
# "Fetch live earnings events" checkbox -- keyed only by
# packet.generated_at, which dataclasses.replace() preserves across
# enrichment. Confirms the actual save call site's output is no longer
# insertion-order-dependent now that AssistantStore keys on
# (generated_at, payload_hash).

def _row_count_for(db_path, generated_at: str) -> int:
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM decision_packets WHERE generated_at = ?", (generated_at,)
        ).fetchone()[0]
    finally:
        conn.close()


def test_briefing_tab_persists_both_base_and_enriched_variants_regardless_of_order():
    import tempfile

    from assistant.storage import AssistantStore

    build_calls = []
    original_build = ui.build_decision_packet
    original_get_events = ui.get_upcoming_events
    ui.build_decision_packet = _fake_packet_builder(build_calls)
    ui.get_upcoming_events = lambda tickers, fetch_live=False: ["FAKE_EVENT"]
    st.cache_data.clear()
    try:
        _, base_packet = _load_packet(str(DEFAULT_POLICY_PATH), False)
        _, enriched_packet = _load_packet(str(DEFAULT_POLICY_PATH), True)
        assert base_packet.generated_at == enriched_packet.generated_at  # the exact collision precondition

        # Order A: a non-event session saves first, an event-enabled
        # session saves second.
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "assistant.db"
            store = AssistantStore(db_path)
            store.save_decision_packet(base_packet)
            store.save_decision_packet(enriched_packet)
            assert _row_count_for(db_path, base_packet.generated_at) == 2

        # Order B: reversed -- must not matter which variant arrives first.
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "assistant.db"
            store = AssistantStore(db_path)
            store.save_decision_packet(enriched_packet)
            store.save_decision_packet(base_packet)
            assert _row_count_for(db_path, base_packet.generated_at) == 2
    finally:
        ui.build_decision_packet = original_build
        ui.get_upcoming_events = original_get_events
        st.cache_data.clear()


if __name__ == "__main__":
    test_proposal_status_category_covers_every_real_status()
    test_proposal_status_category_unknown_status_is_never_approvable()
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
    test_portfolio_context_payload_unaffected_by_current_price_or_market_value_alone()
    test_portfolio_context_payload_bands_small_cash_fluctuations_away()
    test_portfolio_context_payload_still_invalidates_across_a_cash_band_boundary()
    test_portfolio_context_payload_stable_across_reordered_positions_and_orders()
    test_proposal_digest_changes_when_portfolio_context_changes()
    test_proposal_digest_stable_when_nothing_changes()
    test_proposal_digest_changes_with_policy_change()
    test_proposal_digest_changes_with_reference_price_change()
    test_proposal_digest_changes_with_intent_shares_change()
    test_clear_confirmation_state_clears_confirm_and_override_phrase_on_change()
    test_clear_confirmation_state_no_op_when_digest_unchanged()
    test_clear_confirmation_state_handles_first_render_with_no_prior_digest()
    test_load_packet_shares_the_same_base_snapshot_regardless_of_include_events()
    test_load_packet_no_events_never_calls_the_live_events_function()
    test_briefing_tab_persists_both_base_and_enriched_variants_regardless_of_order()
    print("All personal_assistant_ui tests passed.")
