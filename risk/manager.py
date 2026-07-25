"""
Risk manager: turns scored signals into position sizes and stop-losses.

Sizing logic, in order:
1. Base size = account_equity * MAX_POSITION_PCT (never more than this on
   one name, regardless of how confident the model is).
2. If the signal carries a `win_probability` (from ml.model.score_signals),
   scale the base size down by confidence: anything at or below
   MIN_WIN_PROBABILITY gets zero size (not worth trading), scaling up
   linearly to full size at 100% probability. No model score at all means
   full base size (the scanner's threshold is treated as the only filter).
3. Across all signals scanned together, total allocation is capped at
   MAX_TOTAL_EXPOSURE_PCT of equity — sized signals are trimmed
   proportionally, highest-confidence first, if they'd otherwise blow
   through the cap.

This module only computes sizes/prices — it never places orders. That's
execution/alpaca_broker.py's job, kept deliberately separate so risk logic
can be tested and reasoned about without touching a broker.
"""
from __future__ import annotations

import pandas as pd

from config import (
    INITIAL_CAPITAL,
    MAX_POSITION_PCT,
    MAX_TOTAL_EXPOSURE_PCT,
    MIN_WIN_PROBABILITY,
    STOP_LOSS_PCT,
)


def _confidence_scale(win_probability: float | None) -> float:
    """Map a win probability to a [0, 1] sizing multiplier. No score at
    all (None/NaN) means "not model-scored yet" -> trade at full size."""
    if win_probability is None or pd.isna(win_probability):
        return 1.0
    if win_probability <= MIN_WIN_PROBABILITY:
        return 0.0
    return min(1.0, (win_probability - MIN_WIN_PROBABILITY) / (1.0 - MIN_WIN_PROBABILITY))


def size_position(
    signal: pd.Series,
    account_equity: float = INITIAL_CAPITAL,
    max_position_pct: float = MAX_POSITION_PCT,
    stop_loss_pct: float = STOP_LOSS_PCT,
) -> dict:
    """
    Size a single signal. Assumes a long entry at `signal["close"]`
    (see backtest/engine.py docstring for why every signal is treated as
    a long candidate). Returns zero shares/dollars when the model's
    win_probability is at or below MIN_WIN_PROBABILITY.
    """
    win_probability = signal.get("win_probability") if hasattr(signal, "get") else None
    scale = _confidence_scale(win_probability)

    entry_price = float(signal["close"])
    dollar_amount = round(account_equity * max_position_pct * scale, 2)
    shares = int(dollar_amount // entry_price) if entry_price > 0 else 0
    dollar_amount = round(shares * entry_price, 2)  # re-derive from whole shares actually sized

    return {
        "ticker": signal["ticker"],
        "direction": signal["direction"],
        "entry_price": entry_price,
        "shares": shares,
        "dollar_amount": dollar_amount,
        "stop_loss_price": round(entry_price * (1 - stop_loss_pct), 2),
        "win_probability": None if win_probability is None or pd.isna(win_probability) else round(float(win_probability), 3),
    }


def allocate(
    signals: pd.DataFrame,
    account_equity: float = INITIAL_CAPITAL,
    max_position_pct: float = MAX_POSITION_PCT,
    max_total_exposure_pct: float = MAX_TOTAL_EXPOSURE_PCT,
    stop_loss_pct: float = STOP_LOSS_PCT,
) -> pd.DataFrame:
    """
    Size every signal in a scanner/model-scored DataFrame, then enforce a
    portfolio-level cap: if per-signal sizes would sum past
    MAX_TOTAL_EXPOSURE_PCT of equity, trim lowest-confidence signals first
    (dropping shares to 0) until the total fits.

    Returns a DataFrame with one row per input signal (ticker, direction,
    entry_price, shares, dollar_amount, stop_loss_price, win_probability),
    sorted by win_probability descending (highest confidence sized first).
    """
    columns = ["ticker", "direction", "entry_price", "shares", "dollar_amount", "stop_loss_price", "win_probability"]
    if signals.empty:
        return pd.DataFrame(columns=columns)

    sized = pd.DataFrame(
        [
            size_position(row, account_equity, max_position_pct, stop_loss_pct)
            for _, row in signals.iterrows()
        ]
    )
    # Unscored (None) and top-confidence signals sort first; keep them.
    sized = sized.sort_values("win_probability", ascending=False, na_position="first").reset_index(drop=True)

    max_total_dollars = account_equity * max_total_exposure_pct
    running_total = 0.0
    for i, row in sized.iterrows():
        if running_total + row["dollar_amount"] > max_total_dollars:
            remaining = max(0.0, max_total_dollars - running_total)
            shares = int(remaining // row["entry_price"]) if row["entry_price"] > 0 else 0
            sized.at[i, "shares"] = shares
            sized.at[i, "dollar_amount"] = round(shares * row["entry_price"], 2)
        running_total += sized.at[i, "dollar_amount"]

    return sized[columns]


def check_stop_loss(entry_price: float, current_price: float, stop_loss_pct: float = STOP_LOSS_PCT) -> bool:
    """True if `current_price` has fallen far enough from `entry_price`
    (a long position) to trigger the stop-loss exit."""
    if entry_price <= 0:
        return False
    return (entry_price - current_price) / entry_price >= stop_loss_pct
