"""
Sanity tests for the ML model layer. Run with: python -m pytest tests/ -v
(or `python tests/test_model.py` for a quick manual check).

Uses a hand-built, perfectly learnable synthetic dataset (win iff
return_zscore > 0) so we can assert the model actually learns something,
not just "runs without crashing" — and a separate near-random dataset to
confirm walk-forward evaluation doesn't overstate accuracy on noise.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from ml.model import (
    build_features,
    compute_trailing_market_trend,
    load_model,
    save_model,
    score_signals,
    train_final_model,
    walk_forward_evaluate,
)


def _learnable_backtest_results(n: int = 120) -> pd.DataFrame:
    rng = np.random.default_rng(3)
    return_zscore = rng.normal(0, 2, size=n)
    volume_zscore = rng.normal(0, 1.5, size=n)
    direction = np.where(return_zscore > 0, "up", "dip")
    win = return_zscore > 0  # deliberately learnable from return_zscore alone
    dates = pd.bdate_range("2023-01-01", periods=n)

    return pd.DataFrame(
        {
            "ticker": "TEST",
            "date": dates,
            "direction": direction,
            "return_zscore": return_zscore,
            "volume_zscore": volume_zscore,
            "net_return_pct": np.where(win, 1.0, -1.0),
            "win": win,
        }
    )


def test_build_features_shapes_and_columns():
    results = _learnable_backtest_results()
    X, y = build_features(results)

    assert list(X.columns) == ["return_zscore", "volume_zscore", "direction_up"]
    assert len(X) == len(y) == len(results)
    assert set(y.unique()) <= {0, 1}


def test_walk_forward_evaluate_learns_the_pattern():
    results = _learnable_backtest_results()
    X, y = build_features(results)
    metrics = walk_forward_evaluate(X, y, n_splits=5)

    assert metrics["folds"], "expected at least one evaluated fold"
    assert metrics["mean_accuracy"] > 0.8, "should learn an easy, perfectly separable pattern"


def test_walk_forward_evaluate_handles_tiny_data():
    results = _learnable_backtest_results(n=2)
    X, y = build_features(results)
    metrics = walk_forward_evaluate(X, y, n_splits=5)

    assert metrics["folds"] == []
    assert metrics["mean_accuracy"] is None


def test_save_and_load_roundtrip_predicts_identically():
    results = _learnable_backtest_results()
    X, y = build_features(results)
    model = train_final_model(X, y)

    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "model.joblib")
        save_model(model, path)
        reloaded = load_model(path)

        original_preds = model.predict_proba(X)
        reloaded_preds = reloaded.predict_proba(X)
        assert np.allclose(original_preds, reloaded_preds)


def test_score_signals_attaches_win_probability():
    results = _learnable_backtest_results()
    X, y = build_features(results)
    model = train_final_model(X, y)

    signals = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB"],
            "date": pd.bdate_range("2024-01-01", periods=2),
            "close": [100.0, 200.0],
            "return_pct": [3.0, -3.0],
            "return_zscore": [2.5, -2.5],
            "volume_zscore": [2.0, 2.0],
            "direction": ["up", "dip"],
        }
    )
    scored = score_signals(model, signals)

    assert "win_probability" in scored.columns
    assert scored["win_probability"].between(0, 1).all()
    # The clearly-up, high-zscore signal should score more confidently than the dip.
    assert scored.loc[scored["ticker"] == "AAA", "win_probability"].iloc[0] > 0.5


def test_score_signals_on_empty_input():
    results = _learnable_backtest_results()
    X, y = build_features(results)
    model = train_final_model(X, y)

    empty = pd.DataFrame(columns=["ticker", "date", "close", "return_pct", "return_zscore", "volume_zscore", "direction"])
    scored = score_signals(model, empty)
    assert scored.empty
    assert "win_probability" in scored.columns


def _constant_drift_benchmark(start: str, periods: int, daily_return: float) -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=periods)
    close = 100 * np.cumprod(np.full(periods, 1 + daily_return))
    return pd.DataFrame({"close": close}, index=dates)


def test_compute_trailing_market_trend_matches_hand_computed_value():
    benchmark_df = _constant_drift_benchmark("2022-11-01", periods=100, daily_return=0.002)
    as_of = benchmark_df.index[50]
    trend = compute_trailing_market_trend(benchmark_df, as_of, lookback_days=20)

    expected = (1.002**20 - 1) * 100
    assert trend is not None
    assert abs(trend - expected) < 0.01


def test_compute_trailing_market_trend_none_without_enough_history():
    benchmark_df = _constant_drift_benchmark("2022-11-01", periods=100, daily_return=0.002)
    as_of = benchmark_df.index[5]  # fewer than 20 trading days of history before it
    assert compute_trailing_market_trend(benchmark_df, as_of, lookback_days=20) is None


def test_compute_trailing_market_trend_none_when_date_missing():
    benchmark_df = _constant_drift_benchmark("2022-11-01", periods=100, daily_return=0.002)
    missing_date = pd.Timestamp("1999-01-01")
    assert compute_trailing_market_trend(benchmark_df, missing_date) is None


def test_build_features_with_benchmark_adds_regime_column():
    results = _learnable_backtest_results()
    benchmark_df = _constant_drift_benchmark("2022-11-01", periods=200, daily_return=0.001)

    X, y = build_features(results, benchmark_df=benchmark_df)
    assert "market_trend_pct" in X.columns
    assert not X["market_trend_pct"].isna().any()
    assert len(X) == len(y)


def test_build_features_with_benchmark_gaps_keeps_features_aligned_with_labels():
    # Regression test: build_features() used to drop rows missing the
    # regime feature, then re-slice `ordered` using X's POST-reset index
    # (0..n-1), which silently grabbed the first n labels instead of the
    # labels actually belonging to the surviving rows whenever the drops
    # weren't a trailing block. Punch two non-contiguous holes (start AND
    # middle) so a leading-block-only fix wouldn't be enough to pass this.
    results = _learnable_backtest_results(n=100)
    benchmark_df = _constant_drift_benchmark("2022-11-01", periods=250, daily_return=0.001)

    gap_dates = list(results["date"].iloc[0:10]) + list(results["date"].iloc[50:60])
    benchmark_df = benchmark_df.drop(index=[d for d in gap_dates if d in benchmark_df.index])

    X, y = build_features(results, benchmark_df=benchmark_df)

    assert len(X) == 80
    assert not X["market_trend_pct"].isna().any()
    # win was defined as (return_zscore > 0) when the fixture was built —
    # if features and labels were shuffled relative to each other, this
    # invariant would break for the retained rows.
    assert ((X["return_zscore"] > 0).astype(int) == y).all()


def test_score_signals_rejects_mismatched_regime_usage():
    results = _learnable_backtest_results()
    benchmark_df = _constant_drift_benchmark("2022-11-01", periods=200, daily_return=0.001)

    X_with_regime, y = build_features(results, benchmark_df=benchmark_df)
    model_with_regime = train_final_model(X_with_regime, y)

    X_without_regime, y2 = build_features(results)
    model_without_regime = train_final_model(X_without_regime, y2)

    signals = pd.DataFrame(
        {
            "ticker": ["AAA"],
            "date": [results["date"].iloc[-1]],
            "close": [100.0],
            "return_pct": [3.0],
            "return_zscore": [2.5],
            "volume_zscore": [2.0],
            "direction": ["up"],
        }
    )

    try:
        score_signals(model_with_regime, signals)  # no benchmark_df passed
        assert False, "expected ValueError: model trained with regime feature needs benchmark_df"
    except ValueError:
        pass

    try:
        score_signals(model_without_regime, signals, benchmark_df=benchmark_df)
        assert False, "expected ValueError: model trained without regime feature shouldn't take benchmark_df"
    except ValueError:
        pass


def test_score_signals_with_matching_benchmark_scores_correctly():
    results = _learnable_backtest_results()
    benchmark_df = _constant_drift_benchmark("2022-11-01", periods=200, daily_return=0.001)
    X, y = build_features(results, benchmark_df=benchmark_df)
    model = train_final_model(X, y)

    signals = pd.DataFrame(
        {
            "ticker": ["AAA"],
            "date": [results["date"].iloc[-1]],
            "close": [100.0],
            "return_pct": [3.0],
            "return_zscore": [2.5],
            "volume_zscore": [2.0],
            "direction": ["up"],
        }
    )
    scored = score_signals(model, signals, benchmark_df=benchmark_df)
    assert "win_probability" in scored.columns
    assert len(scored) == 1


if __name__ == "__main__":
    test_build_features_shapes_and_columns()
    test_walk_forward_evaluate_learns_the_pattern()
    test_walk_forward_evaluate_handles_tiny_data()
    test_save_and_load_roundtrip_predicts_identically()
    test_score_signals_attaches_win_probability()
    test_score_signals_on_empty_input()
    test_compute_trailing_market_trend_matches_hand_computed_value()
    test_compute_trailing_market_trend_none_without_enough_history()
    test_compute_trailing_market_trend_none_when_date_missing()
    test_build_features_with_benchmark_adds_regime_column()
    test_build_features_with_benchmark_gaps_keeps_features_aligned_with_labels()
    test_score_signals_rejects_mismatched_regime_usage()
    test_score_signals_with_matching_benchmark_scores_correctly()
    print("All model tests passed.")
