"""UI-3: the Backtest page's behavior through the real Streamlit app.

The synthetic data source is deterministic (fixed seed) and never touches
the network, so these tests run a REAL end-to-end walk-forward backtest on
a small basket/lookback and assert on the rendered result.

Run with: python -m pytest tests/test_ui_backtest_page.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.interactive import (
    EXPLORATORY_CAVEATS,
    SYNTHETIC_CAVEAT,
    run_interactive_backtest,
    signal_for_key,
)
from config import BASKETS, SLIPPAGE_PCT
from data.market_data import generate_synthetic

_APP_PATH = Path(__file__).resolve().parents[1] / "scripts" / "personal_assistant_ui.py"

# A small, fast, deterministic configuration shared by every test here.
_BASKET = sorted(BASKETS)[0]
_SCOPE = f"Basket: {_BASKET}"
_LOOKBACK = 160
_HORIZONS = [1, 5]


def _backtest_app() -> AppTest:
    app = AppTest.from_file(str(_APP_PATH), default_timeout=180)
    app.session_state["nav_page"] = "Backtest"
    app.run()
    assert not app.exception
    return app


def _run_default_signal(app: AppTest) -> AppTest:
    app.selectbox(key="bt_scope").set_value(_SCOPE).run()
    app.number_input(key="bt_lookback_days").set_value(_LOOKBACK).run()
    app.multiselect(key="bt_horizons").set_value(_HORIZONS).run()
    app.button(key="bt_run").click().run()
    assert not app.exception
    return app


def _expected_default_run():
    """The exact result the UI must reproduce: same deterministic data,
    same engine path."""
    data = generate_synthetic(list(BASKETS[_BASKET]), days=_LOOKBACK)
    signal = signal_for_key("dips_and_ups")
    return run_interactive_backtest(
        data,
        signal_key="dips_and_ups",
        param_values={p.name: p.default for p in signal.params},
        hold_days_options=_HORIZONS,
        slippage_pct=SLIPPAGE_PCT,
    )


def test_synthetic_is_the_default_data_source():
    """Safety default: opening the page must never imply a network fetch."""
    app = _backtest_app()
    assert app.radio(key="bt_data_source").value.startswith("Synthetic")


def test_synthetic_run_completes_and_matches_the_engine():
    app = _run_default_signal(_backtest_app())

    run = app.session_state["backtest_run"]
    assert run["signal_key"] == "dips_and_ups"
    assert run["source"] == "synthetic"
    assert run["ticker_count"] == len(BASKETS[_BASKET])
    assert sorted(run["results_by_horizon"]) == _HORIZONS

    expected = _expected_default_run()
    for horizon in _HORIZONS:
        assert len(run["results_by_horizon"][horizon]) == len(expected[horizon]), (
            "UI backtest diverged from the direct engine run on identical "
            "deterministic inputs -- the page is not the same experiment."
        )

    # The deterministic seed produces flagged signals at this size, so the
    # summary table must actually render.
    assert any(len(frame) > 0 for frame in expected.values())
    summary_frames = [
        frame.value
        for frame in app.dataframe
        if hasattr(frame.value, "columns") and "win_rate_pct" in frame.value.columns
    ]
    assert summary_frames, "multi-horizon summary table did not render"


def test_synthetic_result_carries_the_synthetic_caveat():
    app = _run_default_signal(_backtest_app())
    warnings = " ".join(str(w.value) for w in app.warning)
    assert SYNTHETIC_CAVEAT in warnings
    # The exploratory (real-data) caveat belongs to real runs only; a
    # synthetic run must be labeled as plumbing, not as market evidence.
    assert EXPLORATORY_CAVEATS not in warnings


def test_results_survive_navigating_away_and_back():
    """The completed run lives in a non-widget session key: inspecting
    another page must not force the user to re-run minutes of work."""
    app = _run_default_signal(_backtest_app())

    app.radio(key="nav_page").set_value("History").run()
    assert not app.exception
    app.radio(key="nav_page").set_value("Backtest").run()
    assert not app.exception

    assert app.session_state["backtest_run"]["signal_key"] == "dips_and_ups"
    # Benign configuration widgets are whitelisted page state (UINAV-001
    # pattern): the chosen scope must survive the round trip too.
    assert app.selectbox(key="bt_scope").value == _SCOPE
    summary_frames = [
        frame.value
        for frame in app.dataframe
        if hasattr(frame.value, "columns") and "win_rate_pct" in frame.value.columns
    ]
    assert summary_frames, "summary table vanished after navigation"


def test_run_configuration_is_stated_with_the_results():
    """Results must be attributable: the page states the configuration the
    numbers came from, not whatever the widgets currently show."""
    app = _run_default_signal(_backtest_app())
    captions = " ".join(str(c.value) for c in app.caption)
    assert "Run configuration" in captions
    assert "synthetic" in captions
    assert _BASKET in captions
    assert "next_open" in captions


def test_the_page_has_no_action_shaped_controls():
    """The research boundary: no button on this page may lead toward a
    proposal, approval, submission, or cancellation."""
    app = _run_default_signal(_backtest_app())
    button_labels = [str(b.label).lower() for b in app.button]
    for forbidden in ("approve", "submit", "cancel", "propose", "order"):
        assert not any(forbidden in label for label in button_labels), (
            f"Backtest page renders a {forbidden!r}-shaped control"
        )
