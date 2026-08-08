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

import pytest
import streamlit as st

import scripts.personal_assistant_ui as ui
from assistant.context_builder import build_portfolio_snapshot, build_risk_exposure
from assistant.policy import DEFAULT_POLICY_PATH, TradingPolicy, compute_policy_fingerprint
from assistant.proposal_status import STATUSES
from assistant.schemas import DecisionPacket, EvidenceStatus, MarketRegime
from assistant.proposals import generate_risk_reduction_proposals
from scripts.personal_assistant_ui import (
    _PERSISTENT_PAGE_WIDGET_KEYS,
    _allocation_input_signature,
    _cache_committee_result,
    _clear_confirmation_state_if_digest_changed,
    _committee_result_for_input,
    _load_packet,
    _portfolio_context_payload,
    _proposal_content_digest,
    _proposal_status_category,
    _preserve_page_widget_state,
    _sync_policy_editor_state,
)


def test_page_state_persistence_excludes_every_sensitive_confirmation():
    state = {
        "watchlist_picked": ["AAPL"],
        "allocation_bulk_confirm": "approve all",
        "emergency_cancel_all_confirmation": "cancel all open orders",
        "confirm_tp-1": "approve",
        "override_confirm_tp-1": "OVERRIDE BUY 1 AAPL",
        "cancel_confirmation_tp-1": "cancel",
        "dismiss_selection": ["tp-1"],
        "dismiss_reason": "unused",
        "dismiss_confirmation": "dismiss 1 proposals",
    }

    _preserve_page_widget_state(state)

    assert state["watchlist_picked"] == ["AAPL"]
    assert "watchlist_picked" in _PERSISTENT_PAGE_WIDGET_KEYS
    for sensitive_key in (
        "allocation_bulk_confirm",
        "emergency_cancel_all_confirmation",
        "confirm_tp-1",
        "override_confirm_tp-1",
        "cancel_confirmation_tp-1",
        # UI-2d: the dismissal workflow is a durable mutation -- its
        # selection/reason/confirmation must never survive navigation.
        "dismiss_selection",
        "dismiss_reason",
        "dismiss_confirmation",
    ):
        assert sensitive_key not in _PERSISTENT_PAGE_WIDGET_KEYS


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


def test_policy_editor_state_tracks_the_selected_policy_identity(tmp_path):
    false_policy = _policy(version="1.0")
    true_policy = dataclasses.replace(
        false_policy, version="1.1", allow_new_positions=True
    )
    state = {
        "policy_edit_allow_new_positions": False,
        "policy_edit_enable_strategy": False,
        "policy_edit_confirm_phrase": "UPDATE POLICY",
    }

    assert _sync_policy_editor_state(state, str(tmp_path / "first.json"), false_policy)
    state["policy_edit_allow_new_positions"] = True  # unsaved widget edit
    assert not _sync_policy_editor_state(
        state, str(tmp_path / "first.json"), false_policy
    )
    assert state["policy_edit_allow_new_positions"] is True

    assert _sync_policy_editor_state(state, str(tmp_path / "second.json"), true_policy)
    assert state["policy_edit_allow_new_positions"] is True
    assert "policy_edit_confirm_phrase" not in state

    externally_changed = dataclasses.replace(
        true_policy, version="1.2", allow_new_positions=False
    )
    assert _sync_policy_editor_state(
        state, str(tmp_path / "second.json"), externally_changed
    )
    assert state["policy_edit_allow_new_positions"] is False

    # Sidebar routing: navigating away from Settings makes Streamlit delete
    # the widget-backed editor keys while the source-identity key survives.
    # Returning must re-seed from the persisted policy (abandoning unsaved
    # edits), never render the checkboxes' False defaults for a True policy.
    state.pop("policy_edit_allow_new_positions")
    state.pop("policy_edit_enable_strategy", None)
    assert _sync_policy_editor_state(
        state, str(tmp_path / "second.json"), externally_changed
    )
    assert state["policy_edit_allow_new_positions"] is False
    assert state["policy_edit_enable_strategy"] is False


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
        # UI-2d (2026-08-04, deliberate): the archive status renders its own
        # terminal card -- never approval controls, never "in_progress".
        "dismissed": "dismissed",
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


def test_optional_event_failure_cannot_hide_risk_reduction_proposals():
    original_build = ui.build_decision_packet
    original_get_events = ui.get_upcoming_events

    def build_breached_packet(*args, **kwargs):
        snapshot = build_portfolio_snapshot(
            [{
                "ticker": "AAPL",
                "shares": 100,
                "entry_price": 100.0,
                "current_price": 100.0,
            }],
            cash=0.0,
        )
        return DecisionPacket(
            generated_at="event-failure-packet",
            portfolio=snapshot,
            risk=build_risk_exposure(snapshot),
            regime=MarketRegime(
                benchmark_ticker="QQQ",
                trend=None,
                volatility_regime=None,
                trailing_volatility_pct=None,
                as_of="2026-08-08",
            ),
            signals=[],
            upcoming_events=[],
            warnings=[],
            policy_version="test",
        )

    ui.build_decision_packet = build_breached_packet
    ui.get_upcoming_events = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        RuntimeError("provider down")
    )
    st.cache_data.clear()
    try:
        policy, packet = _load_packet(str(DEFAULT_POLICY_PATH), True)
        proposals = generate_risk_reduction_proposals(packet, policy)

        assert len(proposals) == 1
        assert proposals[0].intent.side == "sell"
        assert packet.upcoming_events
        assert all(
            event.status == EvidenceStatus.UNAVAILABLE
            for event in packet.upcoming_events
        )
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


# --------------------------------------------------------------------------
# FCS-018: an ambiguous submission must never be reported as a definite
# non-submission.
#
# The execution kernel is scrupulous about this: a raising submit does NOT
# prove the broker rejected the order, so it leaves the proposal in
# `submission_unknown`, keeps the reservation, and raises a message that
# begins "Could not confirm whether the order ... was accepted". The UI then
# prefixed that with "Order not submitted:", re-asserting in the sentence a
# human reads the very thing the kernel refuses to assert.
# --------------------------------------------------------------------------

class _StubStore:
    def __init__(self, status):
        self._status = status
        self.raise_on_read = False

    def get_proposal(self, proposal_id):
        if self.raise_on_read:
            raise RuntimeError("database unavailable")
        return None if self._status is None else {"status": self._status}


@pytest.mark.parametrize(
    "status",
    ["submitting", "submission_unknown", "reconciling", "broker_accepted",
     "partially_filled", "cancel_pending", "executed"],
)
def test_an_unresolved_broker_state_is_reported_as_unknown(status):
    assert ui._submission_outcome_is_unresolved(_StubStore(status), "tp_1") is True


@pytest.mark.parametrize(
    "status", ["blocked", "validation_failed", "submission_failed", "expired"]
)
def test_a_genuinely_failed_attempt_is_not_reported_as_unknown(status):
    assert ui._submission_outcome_is_unresolved(_StubStore(status), "tp_1") is False


def test_an_unreadable_proposal_fails_toward_unknown():
    """If we cannot tell, we must not claim the order did not reach the broker."""
    store = _StubStore("submission_failed")
    store.raise_on_read = True
    assert ui._submission_outcome_is_unresolved(store, "tp_1") is True
    assert ui._submission_outcome_is_unresolved(_StubStore(None), "tp_1") is True


def test_the_unknown_branch_never_claims_the_order_was_not_submitted(monkeypatch):
    """The exact string that misled: 'Order not submitted' on an unknown outcome."""
    shown: list[tuple[str, str]] = []
    monkeypatch.setattr(ui.st, "error", lambda m, **k: shown.append(("error", m)))
    monkeypatch.setattr(ui.st, "warning", lambda m, **k: shown.append(("warning", m)))

    kernel_message = (
        "Could not confirm whether the order for tp_abc was accepted after "
        "the submission raised (Timeout)."
    )
    ui._render_submission_failure(
        _StubStore("submission_unknown"), "tp_abc", RuntimeError(kernel_message)
    )
    rendered = " ".join(text for _, text in shown)
    assert "UNKNOWN" in rendered
    assert "do not resubmit" in rendered.lower()
    assert "not submitted" not in rendered.lower(), (
        "an ambiguous submission must not be described as a non-submission "
        "(FCS-018)"
    )
    assert kernel_message in rendered, "the kernel's own wording must survive"


def test_a_real_failure_still_says_the_order_was_not_submitted(monkeypatch):
    """The fix must not blur the honest negative in the other direction."""
    shown: list[str] = []
    monkeypatch.setattr(ui.st, "error", lambda m, **k: shown.append(m))
    monkeypatch.setattr(ui.st, "warning", lambda m, **k: shown.append(m))
    ui._render_submission_failure(
        _StubStore("blocked"), "tp_abc", RuntimeError("Execution gate blocked it")
    )
    assert any("Order not submitted" in m for m in shown)


def test_both_submit_paths_route_through_the_honest_reporter():
    """The override path reaches the broker too, so it can end ambiguous too.

    Source-level because both call sites live inside a Streamlit render
    function that a unit test cannot cheaply drive; the reporter's own
    behaviour is covered behaviourally above. The ordinary and override
    buttons diverged once already, which is the whole finding.
    """
    import ast

    source = (
        Path(__file__).resolve().parent.parent
        / "scripts" / "personal_assistant_ui.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        body = ast.unparse(node.body)
        if "execute_approved_paper_proposal" not in body:
            continue
        for handler in node.handlers:
            caught = ast.unparse(handler.type) if handler.type else "bare"
            # Only the broad handler matters: the narrow
            # PolicyOverridableBlockError one is a pre-broker refusal and may
            # honestly say "not submitted".
            if caught not in ("Exception", "bare"):
                continue
            rendered = ast.unparse(handler.body)
            if "_render_submission_failure" not in rendered:
                offenders.append(f"line {handler.lineno}: {rendered[:80]}")

    assert not offenders, (
        "a broad handler around execute_approved_paper_proposal must report "
        "through _render_submission_failure -- claiming 'Order not submitted' "
        "on an ambiguous outcome can send the operator to place the trade by "
        "hand at the broker (FCS-018): " + "; ".join(offenders)
    )
