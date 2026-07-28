"""
Sanity tests for signals/residual_returns.py (shared by signals/idio_vol.py
and signals/residual_momentum.py). Run with: python -m pytest tests/ -v.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from signals.residual_returns import compute_residual_returns


def test_residual_returns_are_near_zero_when_stock_tracks_benchmark_exactly():
    rng = np.random.default_rng(0)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=200)
    benchmark_returns = rng.normal(0.0003, 0.006, size=200)
    benchmark_close = pd.Series(100 * np.cumprod(1 + benchmark_returns), index=dates)
    stock_close = benchmark_close.copy()  # identical to the benchmark -- beta=1, residual should be ~0

    residuals = compute_residual_returns(stock_close, benchmark_close, beta_window=60)
    assert residuals.iloc[-20:].abs().max() < 1e-8


def test_residual_returns_capture_excess_drift_not_explained_by_benchmark():
    rng = np.random.default_rng(1)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=200)
    benchmark_returns = rng.normal(0.0003, 0.006, size=200)
    benchmark_close = pd.Series(100 * np.cumprod(1 + benchmark_returns), index=dates)

    extra_drift = 0.002
    stock_returns = benchmark_returns + extra_drift
    stock_close = pd.Series(100 * np.cumprod(1 + stock_returns), index=dates)

    residuals = compute_residual_returns(stock_close, benchmark_close, beta_window=60)
    # beta ~= 1 here (identical noise, just shifted by a constant), so the
    # residual should closely track the constant excess drift.
    assert abs(residuals.iloc[-20:].mean() - extra_drift) < 0.0005


if __name__ == "__main__":
    test_residual_returns_are_near_zero_when_stock_tracks_benchmark_exactly()
    test_residual_returns_capture_excess_drift_not_explained_by_benchmark()
    print("All residual_returns tests passed.")
