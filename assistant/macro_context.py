"""Descriptive macro context from proxies whose predictive claims were rejected.

Credit-spread and yield-curve signals remain rejected in
``research_findings.json``. This module reports only what the proxies have
done (level/change/z-score); it never maps them to expected returns, trade
direction, or proposal generation.
"""
from __future__ import annotations

import math
from typing import Callable

import numpy as np
import pandas as pd

from data.macro_data import (
    build_credit_spread_proxy,
    build_yield_curve_proxy,
)
from data.market_data import fetch_historical


def _describe_series(
    series: pd.Series,
    *,
    label: str,
    rising_text: str,
    falling_text: str,
    lookback: int = 20,
) -> dict:
    clean = (
        pd.to_numeric(series, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    if len(clean) < lookback + 1:
        return {
            "available": False,
            "label": label,
            "reason": f"needs at least {lookback + 1} finite observations",
        }
    latest = float(clean.iloc[-1])
    prior = float(clean.iloc[-(lookback + 1)])
    change = latest - prior
    window = clean.iloc[-min(60, len(clean)) :]
    std = float(window.std(ddof=1))
    z_score = (
        (latest - float(window.mean())) / std
        if math.isfinite(std) and std > 0
        else None
    )
    return {
        "available": True,
        "label": label,
        "as_of": str(clean.index[-1]),
        "level": round(latest, 6),
        "change_20_sessions": round(change, 6),
        "direction": (
            rising_text
            if change > 0
            else falling_text if change < 0 else "unchanged"
        ),
        "z_score_60_sessions": (
            round(float(z_score), 4)
            if z_score is not None and math.isfinite(z_score)
            else None
        ),
    }


def build_descriptive_macro_context(
    *,
    lookback_days: int = 90,
    fetcher: Callable[..., dict] = fetch_historical,
) -> dict:
    tickers = ["HYG", "LQD", "^IRX", "^TNX"]
    try:
        data = fetcher(tickers, lookback_days=lookback_days)
    except Exception as exc:
        return {
            "available": False,
            "reason": str(exc),
            "predictive": False,
        }
    missing = [ticker for ticker in tickers if ticker not in data]
    if missing:
        return {
            "available": False,
            "reason": "missing proxy inputs: " + ", ".join(missing),
            "predictive": False,
        }
    try:
        credit = build_credit_spread_proxy(data["HYG"], data["LQD"])
        curve = build_yield_curve_proxy(data["^IRX"], data["^TNX"])
        indicators = [
            _describe_series(
                credit["close"],
                label="LQD/HYG credit-stress proxy",
                rising_text="widening / more credit stress",
                falling_text="narrowing / less credit stress",
            ),
            _describe_series(
                curve["close"],
                label="3-month minus 10-year yield proxy",
                rising_text="flattening or inverting",
                falling_text="steepening",
            ),
        ]
    except (KeyError, TypeError, ValueError) as exc:
        return {
            "available": False,
            "reason": str(exc),
            "predictive": False,
        }
    return {
        "available": all(item["available"] for item in indicators),
        "predictive": False,
        "evidence_status": "descriptive_only_predictive_claim_rejected",
        "indicators": indicators,
        "disclaimer": (
            "Descriptive context only. These proxies failed confirmation as "
            "return predictors and cannot influence trade proposals."
        ),
    }
