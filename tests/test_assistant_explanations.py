"""
Sanity tests for assistant/explanations.py. Run with:
python tests/test_assistant_explanations.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

import assistant.explanations as explanations
from assistant.context_builder import build_portfolio_snapshot
from assistant.explanations import explain_ticker
from assistant.schemas import MarketRegime

_FIXED_REGIME = MarketRegime(
    benchmark_ticker="QQQ", trend="uptrend", volatility_regime="low_vol",
    trailing_volatility_pct=1.0, as_of="2026-01-01",
)


def _dip_series(days: int = 60) -> pd.DataFrame:
    """Quiet history, then a sharp dip with a volume spike on the LAST
    day, so scan_dips_and_ups fires when `as_of` defaults to the latest
    date."""
    rng = np.random.default_rng(0)
    returns = rng.normal(0.0, 0.002, size=days)
    returns[-1] = -0.08
    volume = 1_000_000.0 * (1 + rng.normal(0.0, 0.02, size=days))
    volume[-1] = 4_000_000.0

    close = 100 * np.cumprod(1 + returns)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
    return pd.DataFrame(
        {"open": close, "high": close * 1.001, "low": close * 0.999, "close": close, "volume": volume},
        index=dates,
    )


def test_explain_ticker_reports_a_triggered_signal():
    original_fetch = explanations.fetch_historical
    try:
        explanations.fetch_historical = lambda tickers, lookback_days=300: {"AAA": _dip_series()}
        result = explain_ticker("AAA", market_regime=_FIXED_REGIME)
        assert result["ticker"] == "AAA"
        assert result["market_regime"]["trend"] == "uptrend"
        rules_fired = {t["rule"] for t in result["triggered_today"]}
        assert "z-score dip/up scanner" in rules_fired
        dip_entry = next(t for t in result["triggered_today"] if t["rule"] == "z-score dip/up scanner")
        assert dip_entry["direction"] == "dip"
    finally:
        explanations.fetch_historical = original_fetch


def test_explain_ticker_includes_historical_evidence_for_ticker_specific_findings():
    original_fetch = explanations.fetch_historical
    try:
        explanations.fetch_historical = lambda tickers, lookback_days=300: {}
        result = explain_ticker("SOXX", market_regime=_FIXED_REGIME)
        labels = {e["label"] for e in result["historical_evidence"]}
        assert any("SOXX/SOXL" in label for label in labels)
        # project-wide findings (no ticker restriction) should always appear too
        assert any(e["claim"] == "Beats a random-day baseline out-of-sample" for e in result["historical_evidence"])
    finally:
        explanations.fetch_historical = original_fetch


def test_explain_ticker_flags_ticker_specific_vs_project_wide_findings():
    # A caller (e.g. the Watchlist UI) needs to tell "this finding is
    # specifically about SOXX" apart from "this is a generic project-wide
    # result that shows up for every ticker" -- otherwise every stock's
    # evidence list looks identical and useless.
    original_fetch = explanations.fetch_historical
    try:
        explanations.fetch_historical = lambda tickers, lookback_days=300: {}
        result = explain_ticker("SOXX", market_regime=_FIXED_REGIME)
        by_label = {e["label"]: e["ticker_specific"] for e in result["historical_evidence"]}
        soxx_specific = next(v for k, v in by_label.items() if "SOXX/SOXL" in k)
        assert soxx_specific is True
        project_wide = next(v for k, v in by_label.items() if "z-score dip/up scanner" in k)
        assert project_wide is False
    finally:
        explanations.fetch_historical = original_fetch


def test_explain_ticker_reports_currently_held_status():
    original_fetch = explanations.fetch_historical
    try:
        explanations.fetch_historical = lambda tickers, lookback_days=300: {}
        snapshot = build_portfolio_snapshot(
            [{"ticker": "AAA", "shares": 10, "entry_price": 100.0, "current_price": 110.0}], cash=0.0,
        )
        held = explain_ticker("AAA", portfolio=snapshot, market_regime=_FIXED_REGIME)
        not_held = explain_ticker("ZZZ", portfolio=snapshot, market_regime=_FIXED_REGIME)
        never_checked = explain_ticker("AAA", portfolio=None, market_regime=_FIXED_REGIME)

        assert held["currently_held"]["shares"] == 10
        assert not_held["currently_held"] is None
        assert never_checked["currently_held"] == "not_checked"
    finally:
        explanations.fetch_historical = original_fetch


def test_explain_ticker_flags_non_authoritative_confirmed_findings_with_display_status():
    # GPT review, 2026-07-29: a confirmed/promising finding that hasn't
    # been re-verified since the fetch_historical lookback-days fix must
    # be visibly distinguishable, not shown as an unqualified "confirmed".
    original_fetch = explanations.fetch_historical
    try:
        explanations.fetch_historical = lambda tickers, lookback_days=300: {}
        result = explain_ticker("SOXX", market_regime=_FIXED_REGIME)
        soxx_drawdown = next(
            e for e in result["historical_evidence"] if "SOXX/SOXL" in e["label"] and e["status"] == "confirmed"
        )
        # Historical status label must be preserved, not destroyed...
        assert soxx_drawdown["status"] == "confirmed"
        # ...but display_status/production_authoritative must reflect the
        # real (currently unreproduced) authority state of the real registry.
        assert soxx_drawdown["production_authoritative"] is False
        assert "NOT CURRENTLY PRODUCTION-AUTHORITATIVE" in soxx_drawdown["display_status"]
    finally:
        explanations.fetch_historical = original_fetch


def test_explain_ticker_handles_missing_data_gracefully():
    original_fetch = explanations.fetch_historical
    try:
        explanations.fetch_historical = lambda tickers, lookback_days=300: {}
        result = explain_ticker("NODATA", market_regime=_FIXED_REGIME)
        assert result["triggered_today"] == []
    finally:
        explanations.fetch_historical = original_fetch


if __name__ == "__main__":
    test_explain_ticker_reports_a_triggered_signal()
    test_explain_ticker_includes_historical_evidence_for_ticker_specific_findings()
    test_explain_ticker_reports_currently_held_status()
    test_explain_ticker_flags_non_authoritative_confirmed_findings_with_display_status()
    test_explain_ticker_handles_missing_data_gracefully()
    print("All assistant explanations tests passed.")


def test_pre_fetched_data_is_used_and_no_redundant_fetch_happens():
    # The Streamlit Briefing tab already fetches each holding's history for
    # its own trend/volatility figures; without the `data` parameter
    # explain_ticker() fetched the SAME history again, costing two yfinance
    # round-trips per held position on every rerun (independent review,
    # 2026-07-29).
    fetch_calls = []
    original_fetch = explanations.fetch_historical
    explanations.fetch_historical = lambda tickers, lookback_days=300: (
        fetch_calls.append(tickers) or {"AAA": _dip_series()}
    )
    try:
        supplied = {"AAA": _dip_series()}
        fetch_calls.clear()
        result = explain_ticker("AAA", market_regime=_FIXED_REGIME, data=supplied)
        assert fetch_calls == [], "explain_ticker must not fetch when data is supplied"
        assert result["ticker"] == "AAA"
        assert "historical_evidence" in result and "triggered_today" in result

        # Without `data` it still fetches, exactly as before.
        fetch_calls.clear()
        explain_ticker("AAA", market_regime=_FIXED_REGIME)
        assert len(fetch_calls) == 1
    finally:
        explanations.fetch_historical = original_fetch
