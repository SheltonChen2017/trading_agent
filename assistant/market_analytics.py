"""Assistant-owned, deterministic market-display calculations.

These implementations are intentionally private to the trading-assistant
product. The research repository owns the root ``market_analytics`` module
and its hypothesis/control-group meaning; importing that module from the
assistant would recreate a product-to-product dependency after extraction.
The integration boundary test holds the duplicated arithmetic and refusal
behavior equal while keeping production imports one-direction-free.
"""
from __future__ import annotations

import math

import pandas as pd

from config import (
    BACKTEST_HOLD_DAYS,
    REGIME_VOLATILITY_LOOKBACK_DAYS,
    SLIPPAGE_PCT,
)


def classify_trend(
    close: pd.Series,
    as_of: pd.Timestamp,
    lookback_days: int = 200,
) -> str | None:
    """Classify an assistant display trend from supplied closing prices."""
    if isinstance(lookback_days, bool) or not isinstance(lookback_days, int):
        raise ValueError(f"lookback_days must be an int, got {lookback_days!r}")
    if lookback_days < 1:
        raise ValueError(f"lookback_days must be at least 1, got {lookback_days}")
    if as_of not in close.index:
        return None
    idx = close.index.get_loc(as_of)
    if idx < lookback_days - 1:
        return None
    window = close.iloc[idx - lookback_days + 1 : idx + 1]
    sma = window.mean()
    return "uptrend" if close.loc[as_of] >= sma else "downtrend"


def compute_trailing_market_volatility(
    benchmark_df: pd.DataFrame,
    as_of: pd.Timestamp,
    lookback_days: int = REGIME_VOLATILITY_LOOKBACK_DAYS,
) -> float | None:
    """Return trailing daily-return volatility in percentage points."""
    if as_of not in benchmark_df.index:
        return None
    idx = benchmark_df.index.get_loc(as_of)
    start_idx = idx - lookback_days
    if start_idx < 0:
        return None

    window = benchmark_df["close"].iloc[start_idx : idx + 1]
    daily_returns = window.pct_change().dropna()
    if len(daily_returns) < 2:
        return None
    return float(daily_returns.std() * 100)


def classify_volatility_regime(
    benchmark_df: pd.DataFrame,
    as_of: pd.Timestamp,
    threshold_pct: float,
    lookback_days: int = REGIME_VOLATILITY_LOOKBACK_DAYS,
) -> str | None:
    """Classify a caller-supplied display threshold without owning policy."""
    volatility = compute_trailing_market_volatility(
        benchmark_df, as_of, lookback_days
    )
    if volatility is None:
        return None
    return "high_vol" if volatility > threshold_pct else "low_vol"


def calibrate_volatility_threshold(
    benchmark_df: pd.DataFrame,
    discovery_end_date: pd.Timestamp,
    lookback_days: int = REGIME_VOLATILITY_LOOKBACK_DAYS,
) -> float:
    """Fit the median supplied-history volatility through a fixed cutoff."""
    discovery_dates = benchmark_df.index[
        benchmark_df.index <= discovery_end_date
    ]
    volatilities = [
        value
        for date in discovery_dates
        if (
            value := compute_trailing_market_volatility(
                benchmark_df, date, lookback_days
            )
        )
        is not None
    ]
    if not volatilities:
        raise ValueError(
            "Not enough discovery-period history to calibrate a regime threshold."
        )
    return float(pd.Series(volatilities).median())


def compute_historical_forward_returns(
    data: dict[str, pd.DataFrame],
    hold_days: int = BACKTEST_HOLD_DAYS,
    slippage_pct: float = SLIPPAGE_PCT,
    entry_timing: str = "next_open",
) -> pd.DataFrame:
    """Compute assistant historical ranges without importing research code.

    This is backward-looking display arithmetic, not a signal, forecast, or
    evidence claim. Its implementation stays behavior-identical to research's
    baseline helper because the watchlist historically used that calculation.
    """
    if entry_timing not in ("same_close", "next_open", "same_day_open_to_close"):
        raise ValueError(
            "entry_timing must be 'same_close', 'next_open', or "
            f"'same_day_open_to_close', got {entry_timing!r}"
        )
    if entry_timing != "same_day_open_to_close":
        if isinstance(hold_days, bool) or not isinstance(hold_days, int):
            raise ValueError(f"hold_days must be an int, got {hold_days!r}")
        if hold_days < 1:
            raise ValueError(f"hold_days must be at least 1, got {hold_days}")
    if (
        isinstance(slippage_pct, bool)
        or not isinstance(slippage_pct, (int, float))
        or not math.isfinite(slippage_pct)
        or slippage_pct < 0
    ):
        raise ValueError(
            "slippage_pct must be a non-negative finite number, "
            f"got {slippage_pct!r}"
        )

    frames = []
    for ticker, df in data.items():
        if entry_timing == "same_close":
            entry_price = df["close"]
            forward_price = df["close"].shift(-hold_days)
        elif entry_timing == "same_day_open_to_close":
            entry_price = df["open"]
            forward_price = df["close"]
        else:
            entry_price = df["open"].shift(-1)
            forward_price = df["open"].shift(-(1 + hold_days))
        if entry_timing != "same_day_open_to_close" and len(df) <= hold_days:
            continue
        raw_return_pct = (forward_price - entry_price) / entry_price * 100
        net_return_pct = raw_return_pct - 2 * slippage_pct * 100
        frame = pd.DataFrame(
            {
                "ticker": ticker,
                "date": df.index,
                "net_return_pct": net_return_pct,
            }
        )
        frames.append(frame.dropna(subset=["net_return_pct"]))

    if not frames:
        return pd.DataFrame(columns=["ticker", "date", "net_return_pct"])
    return pd.concat(frames, ignore_index=True)
