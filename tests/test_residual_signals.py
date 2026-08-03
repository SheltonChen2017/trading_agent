"""
Tests for the residual and volatility-scaled momentum candidate signals.

The property that actually matters here is CAUSALITY. These scanners are
the first in this project to fit a regression rather than read a rolling
moment, and a regression is exactly the kind of construction where a
future row can leak into a past estimate without anything crashing or
even looking wrong. So the central test appends future data to a history
and asserts that not one already-computed row moves.

Everything else — the residual of a stock that perfectly tracks the
market being zero, a market-wide crash producing no idiosyncratic
signal, direction semantics, degenerate inputs — is asserted against
hand-built series with a known planted answer, not just "runs without
crashing".
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import pytest

from signals.residual import (
    build_residual_frames,
    compute_residual_features,
    scan_residual_momentum,
    scan_residual_reversal,
)
from signals.vol_scaled_momentum import scan_vol_scaled_momentum


def _frame(close: np.ndarray, volume: np.ndarray | None = None) -> pd.DataFrame:
    days = len(close)
    if volume is None:
        volume = np.full(days, 1_000_000.0)
    dates = pd.bdate_range(end=pd.Timestamp("2026-01-02"), periods=days)
    return pd.DataFrame(
        {
            "open": close, "high": close * 1.001, "low": close * 0.999,
            "close": close, "volume": volume,
        },
        index=dates,
    )


def _market(days: int, seed: int = 0, scale: float = 0.01) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(loc=0.0004, scale=scale, size=days)
    return _frame(100 * np.cumprod(1 + returns))


# --------------------------------------------------------------------------
# Causality — the test this module exists for
# --------------------------------------------------------------------------

def test_residual_features_are_causal_when_future_rows_are_appended():
    """
    Compute features on 300 days, then on the same 300 days plus 60 more,
    and assert every originally-computed row is bit-for-bit unchanged.

    If the rolling regression ever saw forward data, the appended rows
    would shift the earlier betas and residuals and this comparison would
    fail. This is the check that a look-ahead bug cannot survive.
    """
    days = 360
    market = _market(days, seed=1)
    rng = np.random.default_rng(2)
    stock_returns = 1.3 * market["close"].pct_change().fillna(0).to_numpy() + rng.normal(0, 0.008, days)
    stock = _frame(100 * np.cumprod(1 + stock_returns))

    truncated = compute_residual_features(stock.iloc[:300], market.iloc[:300])
    full = compute_residual_features(stock, market)

    shared = truncated.index
    for column in ("beta", "residual", "residual_zscore", "residual_momentum", "volume_zscore"):
        pd.testing.assert_series_equal(
            truncated[column], full.loc[shared, column], check_names=False,
            obj=f"{column} changed when future rows were appended (look-ahead leak)",
        )


def test_precomputed_frames_flag_the_same_rows_as_on_the_fly():
    """
    build_residual_frames() is a speed optimization only. Precomputing
    over full history must flag exactly what computing per-date does —
    otherwise the fast path used for the real backtest would be testing
    a different signal than the one the tests cover.
    """
    days = 400
    market = _market(days, seed=3)
    data = {}
    for i, beta in enumerate((0.8, 1.0, 1.4, 0.5, 1.1, 1.7)):
        rng = np.random.default_rng(10 + i)
        returns = beta * market["close"].pct_change().fillna(0).to_numpy() + rng.normal(0, 0.01, days)
        data[f"T{i}"] = _frame(100 * np.cumprod(1 + returns))

    frames = build_residual_frames(data, market)
    as_of = data["T0"].index[-1]

    precomputed = scan_residual_momentum(data, as_of=as_of, residual_frames=frames)
    on_the_fly = scan_residual_momentum(data, as_of=as_of, benchmark_df=market)

    pd.testing.assert_frame_equal(precomputed, on_the_fly)


# --------------------------------------------------------------------------
# Residual correctness
# --------------------------------------------------------------------------

def test_stock_that_exactly_tracks_the_market_has_near_zero_residual():
    days = 200
    market = _market(days, seed=4)
    # Same returns as the market, exactly — beta 1, alpha 0, no idiosyncratic move.
    stock = _frame(market["close"].to_numpy() * 2.0)

    features = compute_residual_features(stock, market)
    settled = features["residual"].dropna()

    assert not settled.empty, "expected residuals once the trailing window fills"
    assert settled.abs().max() < 1e-9, (
        f"a stock that exactly tracks the market should have ~zero residual, "
        f"got max |residual| = {settled.abs().max()}"
    )


def test_market_wide_crash_produces_no_idiosyncratic_signal():
    """
    The whole point of residualizing: a stock that falls hard ONLY
    because the market fell hard is not news. The raw z-score scanner
    would flag it; this one must not.
    """
    days = 200
    rng = np.random.default_rng(5)
    market_returns = rng.normal(0, 0.004, days)
    market_returns[-1] = -0.07  # market-wide crash on the last day

    stock_returns = market_returns.copy()  # moves one-for-one with the market
    # Real volume always has trailing variance; a perfectly constant
    # series would give a zero-std window, which compute_residual_features
    # deliberately fails closed on (see its docstring).
    volume = np.random.default_rng(99).normal(1_000_000, 80_000, days)
    volume[-1] = 5_000_000.0  # panic volume, so the volume gate cannot be what saves us

    market = _frame(100 * np.cumprod(1 + market_returns))
    stock = _frame(100 * np.cumprod(1 + stock_returns), volume=volume)

    result = scan_residual_reversal({"TRACKER": stock}, benchmark_df=market)

    assert result.empty, (
        "a purely market-driven crash has no idiosyncratic component and must not be "
        f"flagged as a reversal candidate; got:\n{result}"
    )


def test_benchmark_tracking_name_cannot_produce_a_spurious_zscore():
    """
    Regression test for RESIDUAL_STD_FLOOR.

    A name that moves one-for-one with the benchmark has residual ~0 and
    residual std ~0, so without a volatility floor its z-score is
    floating-point noise over floating-point noise and reaches absurd
    magnitudes (|z| = 13.7 as first written) on a stock with literally no
    idiosyncratic movement. Drop the floor back to `> 0` and this fails.
    """
    days = 200
    market = _market(days, seed=40)
    tracker = _frame(market["close"].to_numpy() * 3.0)  # identical returns, different price level

    features = compute_residual_features(tracker, market)
    settled = features["residual_zscore"].dropna()

    assert settled.empty or settled.abs().max() < 1.0, (
        "a benchmark-tracking name must not generate large residual z-scores; got max "
        f"|z| = {settled.abs().max() if not settled.empty else float('nan')}"
    )


def test_idiosyncratic_crash_on_a_flat_market_is_flagged_as_dip():
    days = 200
    rng = np.random.default_rng(6)
    market_returns = rng.normal(0, 0.004, days)
    market_returns[-1] = 0.001  # market barely moves

    stock_returns = market_returns + rng.normal(0, 0.002, days)
    stock_returns[-1] = -0.09  # company-specific disaster
    # Real volume always has trailing variance; a perfectly constant
    # series would give a zero-std window, which compute_residual_features
    # deliberately fails closed on (see its docstring).
    volume = np.random.default_rng(99).normal(1_000_000, 80_000, days)
    volume[-1] = 5_000_000.0

    market = _frame(100 * np.cumprod(1 + market_returns))
    stock = _frame(100 * np.cumprod(1 + stock_returns), volume=volume)

    result = scan_residual_reversal({"BLOWUP": stock}, benchmark_df=market)

    assert len(result) == 1, f"expected the injected idiosyncratic crash to be flagged, got:\n{result}"
    assert result.iloc[0]["direction"] == "dip"
    assert result.iloc[0]["return_zscore"] <= -2.0


def test_reversal_requires_volume_confirmation():
    days = 200
    rng = np.random.default_rng(7)
    market_returns = rng.normal(0, 0.004, days)
    market_returns[-1] = 0.001
    stock_returns = market_returns + rng.normal(0, 0.002, days)
    stock_returns[-1] = -0.09

    market = _frame(100 * np.cumprod(1 + market_returns))
    # Ordinary volume noise with NO spike on the shock day: the z-score is
    # well-defined (so this tests the threshold itself, not the zero-std
    # fail-closed path) but sits below the confirmation bar.
    volume = np.random.default_rng(98).normal(1_000_000, 80_000, days)
    stock = _frame(100 * np.cumprod(1 + stock_returns), volume=volume)

    result = scan_residual_reversal({"QUIET": stock}, benchmark_df=market)

    assert result.empty, f"an unconfirmed move must not be flagged, got:\n{result}"


# --------------------------------------------------------------------------
# Cross-sectional ranking
# --------------------------------------------------------------------------

def test_residual_momentum_ranks_the_strongest_idiosyncratic_winner_top():
    days = 400
    market = _market(days, seed=8)
    market_returns = market["close"].pct_change().fillna(0).to_numpy()

    data = {}
    # Every name has beta 1 to the market; only the idiosyncratic drift differs,
    # so the ranking must be driven purely by the residual component.
    for name, drift in (("WINNER", 0.0015), ("MID", 0.0), ("LOSER", -0.0015)):
        rng = np.random.default_rng(hash(name) % 1000)
        returns = market_returns + drift + rng.normal(0, 0.004, days)
        data[name] = _frame(100 * np.cumprod(1 + returns))
    for i in range(4):  # padding so the cross-section is wide enough to rank
        rng = np.random.default_rng(50 + i)
        data[f"PAD{i}"] = _frame(100 * np.cumprod(1 + market_returns + rng.normal(0, 0.004, days)))

    # 7 names: a 0.2 quintile would emit a single name per leg, which
    # tests luck rather than ordering. 0.3 gives two per leg.
    result = scan_residual_momentum(data, benchmark_df=market, top_pct=0.3, bottom_pct=0.3)

    assert not result.empty
    ups = result[result["direction"] == "up"]["ticker"].tolist()
    dips = result[result["direction"] == "dip"]["ticker"].tolist()
    assert "WINNER" in ups, f"expected the idiosyncratic winner in the long leg, got up={ups}"
    assert "LOSER" in dips, f"expected the idiosyncratic loser in the short leg, got dip={dips}"


def test_persistent_idiosyncratic_drift_is_not_absorbed_by_rolling_alpha():
    """
    Regression test for the defect the idea was specified with.

    If residual_momentum accumulates FULL OLS residuals, a rolling alpha
    refit on a window shorter than the accumulation window swallows
    exactly the steady company-specific drift the signal is meant to
    detect, and this stock's residual momentum collapses toward zero.
    Accumulating market-adjusted returns instead keeps it. Revert
    compute_residual_features() to sum `residual` and this fails.
    """
    days = 400
    market = _market(days, seed=30)
    market_returns = market["close"].pct_change().fillna(0).to_numpy()
    rng = np.random.default_rng(31)
    # Pure, steady idiosyncratic underperformance on top of beta-1 market
    # exposure — no noise in the drift itself, so the expected cumulative
    # idiosyncratic return over the 126-day window is unambiguous.
    drift = -0.0015
    returns = market_returns + drift + rng.normal(0, 0.002, days)
    stock = _frame(100 * np.cumprod(1 + returns))

    features = compute_residual_features(stock, market)
    observed = features["residual_momentum"].dropna().iloc[-1]

    expected = drift * 126  # ~-18.9% cumulative idiosyncratic return
    assert observed < expected / 2, (
        f"a steady {drift:.2%}/day idiosyncratic drift should accumulate to roughly "
        f"{expected:.3f} of residual momentum, but got {observed:.3f} — the rolling "
        f"alpha absorbed the drift instead of leaving it in the signal"
    )


def test_vol_scaled_momentum_prefers_the_calmer_of_two_equal_returns():
    """
    Two stocks end at the same 12-1 return; one got there smoothly, the
    other violently. Vol-scaling must rank the calm one higher — that is
    the entire premise of the signal.
    """
    days = 400
    rng = np.random.default_rng(9)

    def path(noise_scale: float, seed: int) -> np.ndarray:
        r = np.random.default_rng(seed).normal(0, noise_scale, days)
        r -= r.mean()  # centre the noise so the drift alone sets the total return
        return r + 0.0008

    calm = _frame(100 * np.cumprod(1 + path(0.004, 11)))
    wild = _frame(100 * np.cumprod(1 + path(0.020, 12)))
    data = {"CALM": calm, "WILD": wild}
    for i in range(6):
        data[f"PAD{i}"] = _frame(100 * np.cumprod(1 + rng.normal(0.0002, 0.010, days)))

    # Rank the whole cross-section so both names land in a leg and the
    # comparison is about ordering, not about quintile width.
    result = scan_vol_scaled_momentum(data, top_pct=0.5, bottom_pct=0.5)
    scores = result.set_index("ticker")["return_zscore"]

    assert "CALM" in scores.index and "WILD" in scores.index, (
        f"both test names should be ranked into a leg; got {scores.index.tolist()}"
    )
    assert scores["CALM"] > scores["WILD"], (
        f"vol-scaling should favour the calmer path at equal return "
        f"(CALM={scores['CALM']}, WILD={scores['WILD']})"
    )


def test_vol_scaled_momentum_is_causal():
    days = 400
    data = {}
    for i in range(8):
        rng = np.random.default_rng(60 + i)
        data[f"T{i}"] = _frame(100 * np.cumprod(1 + rng.normal(0.0003, 0.01, days + 40)))

    as_of = data["T0"].index[days - 1]
    truncated = {t: df.iloc[:days] for t, df in data.items()}

    from_truncated = scan_vol_scaled_momentum(truncated, as_of=as_of)
    from_full = scan_vol_scaled_momentum(data, as_of=as_of)

    pd.testing.assert_frame_equal(
        from_truncated, from_full,
        obj="vol-scaled momentum changed when future rows became available (look-ahead leak)",
    )


# --------------------------------------------------------------------------
# Degenerate and hostile inputs
# --------------------------------------------------------------------------

def test_insufficient_history_returns_empty_not_garbage():
    days = 30  # far short of the 90-day beta window
    market = _market(days, seed=13)
    stock = _frame(100 * np.cumprod(1 + np.random.default_rng(14).normal(0, 0.01, days)))

    assert scan_residual_reversal({"NEW": stock}, benchmark_df=market).empty
    assert scan_residual_momentum({"NEW": stock}, benchmark_df=market).empty


def test_flat_benchmark_yields_no_beta_rather_than_infinite_residual():
    days = 200
    market = _frame(np.full(days, 100.0))  # zero variance: beta is undefined
    stock = _frame(100 * np.cumprod(1 + np.random.default_rng(15).normal(0, 0.01, days)))

    features = compute_residual_features(stock, market)

    assert features["beta"].dropna().empty, "a zero-variance benchmark must not produce a beta"
    assert features["residual"].dropna().empty, "no beta means no residual, not an infinite one"
    assert scan_residual_reversal({"X": stock}, benchmark_df=market).empty


def test_benchmark_gap_does_not_borrow_a_neighbouring_days_market_move():
    days = 200
    market = _market(days, seed=16)
    stock_returns = market["close"].pct_change().fillna(0).to_numpy()
    stock = _frame(100 * np.cumprod(1 + stock_returns))
    # Drop a benchmark date the stock still trades on.
    gapped_market = market.drop(market.index[-5])

    features = compute_residual_features(stock, gapped_market)

    assert pd.isna(features["residual"].iloc[-5]), (
        "a missing benchmark day must produce NaN, not a residual computed against "
        "some other day's market return"
    )


def test_ticker_absent_on_as_of_date_is_skipped():
    days = 400
    market = _market(days, seed=17)
    data = {}
    for i in range(6):
        rng = np.random.default_rng(70 + i)
        data[f"T{i}"] = _frame(100 * np.cumprod(1 + rng.normal(0.0003, 0.01, days)))
    late_ipo = data["T0"].iloc[-10:].copy()
    data["IPO"] = late_ipo

    early_date = data["T0"].index[200]
    result = scan_residual_momentum(data, as_of=early_date, benchmark_df=market)

    assert "IPO" not in result["ticker"].tolist(), (
        "a ticker with no row on the as-of date must be skipped, not forward/back-filled"
    )


def test_no_ticker_is_emitted_in_both_legs():
    days = 400
    market = _market(days, seed=18)
    data = {}
    for i in range(5):  # small cross-section, where top and bottom can collide
        rng = np.random.default_rng(80 + i)
        data[f"T{i}"] = _frame(100 * np.cumprod(1 + rng.normal(0.0003, 0.01, days)))

    result = scan_residual_momentum(data, benchmark_df=market, top_pct=0.6, bottom_pct=0.6)

    assert result["ticker"].is_unique, (
        f"a ticker must never appear in both legs with contradictory directions:\n{result}"
    )


def test_invalid_windows_are_rejected():
    market = _market(50, seed=19)
    stock = _frame(100 * np.cumprod(1 + np.random.default_rng(20).normal(0, 0.01, 50)))

    with pytest.raises(ValueError):
        compute_residual_features(stock, market, beta_window=1)
    with pytest.raises(ValueError):
        compute_residual_features(stock, market, momentum_skip_days=-1)
    with pytest.raises(ValueError):
        scan_vol_scaled_momentum({"X": stock}, vol_window=1)


def test_scan_requires_either_frames_or_benchmark():
    stock = _frame(100 * np.cumprod(1 + np.random.default_rng(21).normal(0, 0.01, 200)))
    with pytest.raises(ValueError, match="residual_frames"):
        scan_residual_momentum({"X": stock})


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
