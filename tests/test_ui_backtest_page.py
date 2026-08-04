"""UI-3: the Backtest page's behavior through the real Streamlit app.

The synthetic data source is deterministic (fixed seed) and never touches
the network, so these tests run a REAL end-to-end walk-forward backtest on
a small basket/lookback and assert on the rendered result.

Run with: python -m pytest tests/test_ui_backtest_page.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.interactive import (
    BacktestDataCoverage,
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
        pd.testing.assert_frame_equal(
            run["results_by_horizon"][horizon],
            expected[horizon],
            obj=(
                "UI backtest result on identical deterministic inputs -- "
                "the page must run the exact experiment it displays"
            ),
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


def test_stored_real_result_carries_the_exploratory_caveat_without_refetching():
    signal = signal_for_key("dips_and_ups")
    app = AppTest.from_file(str(_APP_PATH), default_timeout=180)
    app.session_state["nav_page"] = "Backtest"
    app.session_state["backtest_run"] = {
        "signal_key": signal.key,
        "signal_label": signal.label,
        "param_values": {p.name: p.default for p in signal.params},
        "source": "real",
        "scope": _SCOPE,
        "ticker_count": 2,
        "data_coverage": BacktestDataCoverage(
            requested_ticker_count=3,
            loaded_ticker_count=2,
            complete_ticker_count=1,
            missing_tickers=("CCC",),
            underfilled_tickers=(("BBB", 80),),
        ),
        "lookback_days": _LOOKBACK,
        "hold_days_options": tuple(_HORIZONS),
        "entry_timing": "next_open",
        "slippage_pct": SLIPPAGE_PCT,
        "results_by_horizon": _expected_default_run(),
        "ran_at": "2026-08-04T12:00:00+00:00",
    }
    app.run()
    assert not app.exception

    warnings = " ".join(str(w.value) for w in app.warning)
    assert EXPLORATORY_CAVEATS in warnings
    assert SYNTHETIC_CAVEAT not in warnings
    assert "Incomplete market-data coverage" in warnings
    assert "loaded 2 of 3 requested tickers" in warnings
    assert "missing: CCC" in warnings
    assert "short history: BBB (80)" in warnings

    captions = " ".join(str(c.value) for c in app.caption)
    assert "(2 tickers)" in captions


def test_data_loaders_validate_coverage_inside_the_cached_body():
    """Counter-review CRUI3-001: st.cache_data caches return values but
    never exceptions. If coverage were validated OUTSIDE the cached
    loaders, a transient empty/failed fetch would return {} and be cached
    for the full TTL -- every retry inside the hour would replay the empty
    response even after the network recovered. The inspect_data_coverage
    call must therefore sit inside each cached loader body, so a failed
    fetch raises and nothing is cached. Source-level check because only a
    live provider failure could exercise this behaviorally."""
    import ast

    tree = ast.parse(_APP_PATH.read_text(encoding="utf-8"))
    loader_names = {
        "_load_backtest_synthetic_data",
        "_load_backtest_real_data",
    }
    loaders = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in loader_names
    }
    assert set(loaders) == loader_names
    for name, fn_node in loaders.items():
        calls = [
            node
            for node in ast.walk(fn_node)
            if isinstance(node, ast.Call)
            and (
                getattr(node.func, "id", None) == "inspect_data_coverage"
                or getattr(node.func, "attr", None) == "inspect_data_coverage"
            )
        ]
        assert calls, (
            f"{name} must call inspect_data_coverage inside its cached "
            "body (CRUI3-001) so a failed fetch raises instead of caching "
            "an empty provider response"
        )


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
    assert "hold horizons [1, 5]" in captions
    assert "slippage 0.15% per leg" in captions


def test_the_page_has_no_action_shaped_controls():
    """The research boundary: no button on this page may lead toward a
    proposal, approval, submission, or cancellation."""
    app = _run_default_signal(_backtest_app())
    button_labels = [str(b.label).lower() for b in app.button]
    for forbidden in ("approve", "submit", "cancel", "propose", "order"):
        assert not any(forbidden in label for label in button_labels), (
            f"Backtest page renders a {forbidden!r}-shaped control"
        )
