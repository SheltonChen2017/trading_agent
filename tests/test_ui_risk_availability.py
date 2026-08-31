"""Behavioral UI coverage for unavailable portfolio/order evidence."""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from assistant.context_builder import build_portfolio_snapshot, build_risk_exposure
from assistant.portfolio_analytics import compute_portfolio_analytics
from assistant.schemas import DecisionPacket, MarketRegime


_APP_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "personal_assistant_ui.py"
)


def _result_row(volatility: float, price: float) -> dict:
    return {
        "own_trend": "flat",
        "own_vol": volatility,
        "current_price": price,
        "price_as_of": "2026-08-28",
        "price_history": None,
        "explanation": {
            "currently_held": None,
            "triggered_today": False,
            "historical_evidence": [],
            "note": "",
        },
        "price_targets": [],
        "hold_range": None,
        "news": [],
        "news_summary": None,
        "news_summary_reason": None,
        "earnings": {"available": False},
    }


@pytest.fixture()
def unavailable_packet_environment(monkeypatch):
    import streamlit as st

    st.cache_data.clear()
    st.cache_resource.clear()
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)

    snapshot = build_portfolio_snapshot(
        [
            {
                "ticker": "NVDA",
                "shares": "2",
                "entry_price": "100",
                "current_price": "110",
            }
        ],
        cash="780",
        open_orders=[],
        open_orders_available=False,
    )
    risk = dataclasses.replace(
        build_risk_exposure(snapshot),
        available=False,
        unavailable_reason="Portfolio integrity unavailable for test",
    )
    packet = DecisionPacket(
        generated_at="2026-08-28T12:00:00+00:00",
        portfolio=snapshot,
        risk=risk,
        regime=MarketRegime(
            benchmark_ticker="QQQ",
            trend="uptrend",
            volatility_regime="low_vol",
            trailing_volatility_pct=1.0,
            as_of="2026-08-28",
        ),
        signals=[],
        upcoming_events=[],
        warnings=[risk.unavailable_reason],
        policy_version="test",
        analytics=compute_portfolio_analytics(snapshot),
        data_freshness={
            "portfolio_as_of": snapshot.as_of,
            "market_regime_as_of": "2026-08-28",
            "research_registry_version": "test",
        },
    )

    import assistant.context_builder as context_builder
    import assistant.portfolio_history as portfolio_history
    import assistant.recommended_stocks as recommended_stocks
    import assistant.risk_copilot as risk_copilot
    import assistant.sleeve_notifications as sleeve_notifications

    monkeypatch.setattr(
        context_builder,
        "build_decision_packet",
        lambda *args, **kwargs: packet,
    )
    monkeypatch.setattr(
        recommended_stocks,
        "build_recommended_tickers",
        lambda *args, **kwargs: ([], []),
    )

    calls = {
        "history": 0,
        "clusters": 0,
        "discrete_price": 0,
    }

    def forbidden_history(*args, **kwargs):
        calls["history"] += 1
        raise AssertionError("invalid risk evidence reached history capture")

    def forbidden_clusters(*args, **kwargs):
        calls["clusters"] += 1
        raise AssertionError("invalid risk evidence reached cluster analytics")

    def forbidden_price_fetcher(*args, **kwargs):
        calls["discrete_price"] += 1
        raise AssertionError("blocked discrete buy reached price sizing")

    monkeypatch.setattr(
        portfolio_history,
        "capture_briefing_equity_snapshot",
        forbidden_history,
    )
    monkeypatch.setattr(
        risk_copilot,
        "find_correlated_clusters",
        forbidden_clusters,
    )
    monkeypatch.setattr(
        sleeve_notifications,
        "_recorded_close_fetcher",
        forbidden_price_fetcher,
    )
    return packet, calls


def _app(page: str, **session_state) -> AppTest:
    app = AppTest.from_file(str(_APP_PATH), default_timeout=180)
    app.session_state["nav_page"] = page
    for key, value in session_state.items():
        app.session_state[key] = value
    app.run()
    return app


def test_briefing_suppresses_stale_history_holdings_and_risk_analytics(
    unavailable_packet_environment,
):
    packet, calls = unavailable_packet_environment
    app = _app(
        "Briefing",
        last_saved_packet_generated_at=packet.generated_at,
        portfolio_history_report={"available": True, "total_return_pct": 999},
        portfolio_risk_decomposition={
            "available": True,
            "portfolio_beta": 999,
        },
    )

    assert not app.exception
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics["Total equity"] == "Unavailable"
    assert metrics["Cash"] == "Unavailable"
    assert metrics["Positions"] == "Unavailable"
    assert metrics["Largest single position"] == "Unavailable"
    assert metrics["Leveraged ETF exposure"] == "Unavailable"
    assert metrics["Invested"] == "Unavailable"
    assert "Holdings analysis" not in [item.value for item in app.subheader]
    assert app.button(key="run_portfolio_risk").disabled is True
    assert app.button(key="run_stress_test").disabled is True
    assert "portfolio_history_report" not in app.session_state
    assert "portfolio_risk_decomposition" not in app.session_state
    assert calls["history"] == 0
    assert calls["clusters"] == 0


def test_budgeted_buy_disables_controls_and_clears_stale_batch_state(
    unavailable_packet_environment,
):
    app = _app(
        "Budgeted Buying",
        watchlist_results={
            "NVDA": _result_row(2.0, 100.0),
            "AMD": _result_row(4.0, 50.0),
        },
        watchlist_results_cart=["AMD", "NVDA"],
        watchlist_typed="NVDA, AMD",
        allocation_dollar_amount=100.0,
        allocation_proposals=[{"stale": True}],
        allocation_proposals_signature="stale",
        allocation_batch_id="stale-batch",
        allocation_batch_id_for_signature="stale",
        allocation_bulk_confirm="I approve this transaction",
    )

    assert not app.exception
    errors = "\n".join(element.value for element in app.error)
    assert "No buy proposal was created" in errors
    assert app.number_input(key="allocation_dollar_amount").disabled is True
    create = next(
        button
        for button in app.button
        if button.label == "Create purchase proposals using this split"
    )
    assert create.disabled is True
    assert app.session_state["allocation_proposals"] == []
    assert app.session_state["allocation_proposals_signature"] is None
    assert "allocation_batch_id" not in app.session_state
    assert "allocation_bulk_confirm" not in app.session_state


def test_discrete_buy_blocks_sizing_and_save_before_fetching_a_price(
    unavailable_packet_environment,
):
    _, calls = unavailable_packet_environment
    app = _app(
        "Discrete Buying",
        discrete_buy_ticker="NVDA",
        discrete_buy_proposal={"stale": True},
    )

    assert not app.exception
    errors = "\n".join(element.value for element in app.error)
    assert "No buy proposal was created" in errors
    assert app.button(key="discrete_buy_create").disabled is True
    assert "discrete_buy_proposal" not in app.session_state
    assert calls["discrete_price"] == 0


def test_briefing_does_not_render_infinite_pnl_when_analytics_are_unavailable(
    monkeypatch,
):
    import streamlit as st

    st.cache_data.clear()
    st.cache_resource.clear()
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)

    snapshot = build_portfolio_snapshot(
        [
            {
                "ticker": "NVDA",
                "shares": "1",
                "entry_price": "1",
                "current_price": "2",
            }
        ],
        cash="8",
        open_orders=[],
        open_orders_available=True,
    )
    snapshot.positions = [
        dataclasses.replace(
            snapshot.positions[0],
            unrealized_pnl_pct=float("inf"),
        )
    ]
    packet = DecisionPacket(
        generated_at="2026-08-28T13:00:00+00:00",
        portfolio=snapshot,
        risk=build_risk_exposure(snapshot),
        regime=MarketRegime(
            benchmark_ticker="QQQ",
            trend="uptrend",
            volatility_regime="low_vol",
            trailing_volatility_pct=1.0,
            as_of="2026-08-28",
        ),
        signals=[],
        upcoming_events=[],
        warnings=["Portfolio analytics unavailable for test"],
        policy_version="test",
        analytics={
            "available": False,
            "unavailable_reason": "derived P&L cannot be represented",
        },
        data_freshness={
            "portfolio_as_of": snapshot.as_of,
            "market_regime_as_of": "2026-08-28",
            "research_registry_version": "test",
        },
    )

    import assistant.context_builder as context_builder
    import assistant.recommended_stocks as recommended_stocks
    import assistant.risk_copilot as risk_copilot
    import data.market_data as market_data
    import scripts.product_composition as product_composition

    monkeypatch.setattr(
        context_builder,
        "build_decision_packet",
        lambda *args, **kwargs: packet,
    )
    monkeypatch.setattr(
        recommended_stocks,
        "build_recommended_tickers",
        lambda *args, **kwargs: ([], []),
    )
    monkeypatch.setattr(
        risk_copilot,
        "find_correlated_clusters",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        market_data,
        "fetch_historical",
        lambda *args, **kwargs: {},
    )
    monkeypatch.setattr(
        product_composition,
        "explain_ticker_with_research",
        lambda *args, **kwargs: {
            "historical_evidence": [],
            "triggered_today": [],
        },
    )

    app = _app(
        "Briefing",
        last_saved_packet_generated_at=packet.generated_at,
    )

    assert not app.exception
    position_table = next(
        element.value
        for element in app.dataframe
        if "Unrealized P&L %" in element.value.columns
    )
    assert position_table.iloc[0]["Unrealized P&L %"] == "Unavailable"
    rendered_text = "\n".join(
        str(element.value)
        for collection in (app.markdown, app.caption, app.dataframe)
        for element in collection
    ).lower()
    assert "inf%" not in rendered_text
