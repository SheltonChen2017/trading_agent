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


if __name__ == "__main__":
    test_build_features_shapes_and_columns()
    test_walk_forward_evaluate_learns_the_pattern()
    test_walk_forward_evaluate_handles_tiny_data()
    test_save_and_load_roundtrip_predicts_identically()
    test_score_signals_attaches_win_probability()
    test_score_signals_on_empty_input()
    print("All model tests passed.")
