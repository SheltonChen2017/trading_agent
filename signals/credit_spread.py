"""
Credit spread widening mean-reversion signal.

Sibling of signals/vix_spike.py — same mechanism, different macro
stress proxy: the LQD/HYG price ratio (investment-grade vs. high-yield
corporate bonds — see data.macro_data.build_credit_spread_proxy()),
which RISES when high-yield bonds underperform investment-grade (a
"flight to quality" that widens real credit spreads). A genuinely
different data category from every other signal in this project: bond
market risk appetite, not any ticker's own price/volume/fundamentals/
analyst data.

Same NOT-ticker-specific mechanism as VIX spike: on a day the credit-
spread proxy itself spikes beyond a z-score threshold, EVERY ticker in
the universe gets flagged simultaneously with direction="dip" (credit
stress spike, expect a broad bounce). "up" (a sharp narrowing/risk-on
move) is included for symmetry only.

Same output contract as every other signal; `return_zscore` repurposed
to hold the proxy's own return z-score (identical across every ticker
flagged on a given date, since the trigger is market-wide).

Usage:

    from functools import partial
    from data.market_data import fetch_historical
    from data.macro_data import build_credit_spread_proxy
    from signals.credit_spread import scan_credit_spread

    raw = fetch_historical(["HYG", "LQD"], lookback_days=1764)
    proxy = build_credit_spread_proxy(raw["HYG"], raw["LQD"])
    run_backtest(data, scan_fn=partial(scan_credit_spread, spread_data=proxy), scan_kwargs={})
"""
from __future__ import annotations

import pandas as pd

from config import CREDIT_SPREAD_Z_THRESHOLD
from signals.scanner import compute_features

RESULT_COLUMNS = ["ticker", "date", "close", "return_pct", "return_zscore", "volume_zscore", "direction"]


def scan_credit_spread(
    data: dict[str, pd.DataFrame],
    spread_data: pd.DataFrame,
    as_of: pd.Timestamp | None = None,
    z_threshold: float = CREDIT_SPREAD_Z_THRESHOLD,
) -> pd.DataFrame:
    """
    Flags EVERY ticker in `data` when the credit-spread proxy
    (`spread_data`, from data.macro_data.build_credit_spread_proxy())
    has an extreme trailing return z-score on `as_of`: "dip" for a
    spread-widening spike (credit stress, expect a broad bounce), "up"
    for a sharp narrowing (included for symmetry).
    """
    if as_of is None or as_of not in spread_data.index:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    features = compute_features(spread_data)
    zscore = features.loc[as_of, "return_zscore"]
    if pd.isna(zscore) or abs(zscore) < z_threshold:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    direction = "dip" if zscore > 0 else "up"

    rows = []
    for ticker, df in data.items():
        if as_of not in df.index:
            continue
        close = float(df.loc[as_of, "close"])
        rows.append(
            {
                "ticker": ticker,
                "date": as_of,
                "close": round(close, 2),
                "return_pct": 0.0,
                "return_zscore": round(float(zscore), 2),
                "volume_zscore": float("nan"),
                "direction": direction,
            }
        )

    if not rows:
        return pd.DataFrame(columns=RESULT_COLUMNS)
    return pd.DataFrame(rows, columns=RESULT_COLUMNS)
