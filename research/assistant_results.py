"""Research-owned builders for read-only assistant-facing results.

This module may use strategy and signal implementations. It returns only the
neutral immutable contracts in :mod:`data.research_results`; it never imports
the assistant, creates a proposal, or acquires execution authority.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from data.research_results import (
    LeveragedPairResearchResult,
    SignalTriggerResult,
    TickerSignalResearchResult,
    close_series_sha256,
    research_parameters_sha256,
)
from market_analytics import classify_trend
from signals.breakout import scan_52_week_breakout
from signals.regime import compute_trailing_market_volatility
from signals.scanner import scan_dips_and_ups
from strategies.vol_target_rotation import compute_target_leveraged_weight


_PER_TICKER_SCANNERS = (
    ("z-score dip/up scanner", scan_dips_and_ups),
    ("52-week breakout", scan_52_week_breakout),
)


def build_ticker_signal_result(
    ticker: str,
    data: Mapping[str, pd.DataFrame],
) -> TickerSignalResearchResult:
    """Evaluate the existing per-ticker scanners and return display-only rows."""
    canonical_ticker = ticker.upper()
    frame = data.get(canonical_ticker)
    triggers: list[SignalTriggerResult] = []
    as_of: str | None = None
    if isinstance(frame, pd.DataFrame) and not frame.empty:
        last_index = frame.index[-1]
        as_of = (
            last_index.isoformat()
            if hasattr(last_index, "isoformat")
            else str(last_index)
        )
        for name, scanner in _PER_TICKER_SCANNERS:
            result = scanner({canonical_ticker: frame})
            if result.empty:
                continue
            latest = result.iloc[-1]
            date_value = latest["date"]
            date_text = (
                date_value.date().isoformat()
                if hasattr(date_value, "date")
                else str(date_value)
            )
            triggers.append(
                SignalTriggerResult(
                    rule=name,
                    direction=latest["direction"],
                    date=date_text,
                    return_zscore=float(latest["return_zscore"]),
                    volume_zscore=float(latest["volume_zscore"]),
                )
            )
    return TickerSignalResearchResult(
        ticker=canonical_ticker,
        as_of=as_of,
        triggers=tuple(triggers),
    )


def build_leveraged_pair_research_result(
    *,
    stable_ticker: str,
    leveraged_ticker: str,
    market_data: Mapping[str, pd.DataFrame],
    production_params: Mapping[str, Any],
) -> LeveragedPairResearchResult:
    """Compute the old trend/volatility target and bind it to exact inputs."""
    stable_ticker = stable_ticker.upper()
    leveraged_ticker = leveraged_ticker.upper()
    stable_close = market_data[stable_ticker]["close"]
    leveraged_close = market_data[leveraged_ticker]["close"]
    as_of = min(stable_close.index[-1], leveraged_close.index[-1])
    stable_used = stable_close.loc[:as_of]
    leveraged_used = leveraged_close.loc[:as_of]

    trend = classify_trend(
        stable_used,
        as_of,
        lookback_days=int(production_params["trend_lookback_days"]),
    )
    if trend is None:
        target: float | None = None
        label = "insufficient_trend_history"
    elif trend == "downtrend":
        target = 0.0
        label = "downtrend_defensive"
    else:
        realized_volatility = compute_trailing_market_volatility(
            pd.DataFrame({"close": leveraged_used}),
            as_of,
            lookback_days=int(production_params["vol_lookback_days"]),
        )
        if realized_volatility is None:
            target = None
            label = "insufficient_volatility_history"
        else:
            target = compute_target_leveraged_weight(
                realized_volatility,
                float(production_params["target_vol_pct"]),
                float(production_params["max_leveraged_weight"]),
            )
            label = f"uptrend_vol_target(realized={realized_volatility:.2f}%)"

    return LeveragedPairResearchResult(
        stable_ticker=stable_ticker,
        leveraged_ticker=leveraged_ticker,
        as_of=(as_of.isoformat() if hasattr(as_of, "isoformat") else str(as_of)),
        target_leveraged_weight=target,
        label=label,
        stable_close_sha256=close_series_sha256(stable_used),
        leveraged_close_sha256=close_series_sha256(leveraged_used),
        parameters_sha256=research_parameters_sha256(production_params),
    )


__all__ = [
    "build_leveraged_pair_research_result",
    "build_ticker_signal_result",
]
