"""
Yield curve flattening/inversion mean-reversion signal.

Sibling of signals/vix_spike.py and signals/credit_spread.py — same
mechanism, different macro stress proxy: the short-minus-long yield
spread (^IRX 13-week T-bill minus ^TNX 10-year note — see
data.macro_data.build_yield_curve_proxy()), which RISES as the curve
flattens/inverts further (the classic recession-fear signal; this is
the same 3-month/10-year spread the NY Fed's own recession-probability
model uses). A genuinely different data category from every other
signal in this project: rates-market recession expectations, not any
ticker's own price/volume/fundamentals/analyst data.

Same NOT-ticker-specific mechanism as VIX spike and credit spread: on a
day the yield-curve proxy itself spikes beyond a z-score threshold,
EVERY ticker in the universe gets flagged simultaneously with
direction="dip" (sharp further inversion, expect a broad bounce). "up"
(a sharp steepening) is included for symmetry only.

Same output contract as every other signal; `return_zscore` repurposed
to hold the proxy's own return z-score (identical across every ticker
flagged on a given date, since the trigger is market-wide).

Usage:

    from functools import partial
    from data.market_data import fetch_historical
    from data.macro_data import build_yield_curve_proxy
    from signals.yield_curve import scan_yield_curve

    raw = fetch_historical(["^IRX", "^TNX"], lookback_days=1764)
    proxy = build_yield_curve_proxy(raw["^IRX"], raw["^TNX"])
    run_backtest(data, scan_fn=partial(scan_yield_curve, curve_data=proxy), scan_kwargs={})
"""
from __future__ import annotations

import pandas as pd

from config import YIELD_CURVE_Z_THRESHOLD
from signals.scanner import compute_features

RESULT_COLUMNS = ["ticker", "date", "close", "return_pct", "return_zscore", "volume_zscore", "direction"]


def scan_yield_curve(
    data: dict[str, pd.DataFrame],
    curve_data: pd.DataFrame,
    as_of: pd.Timestamp | None = None,
    z_threshold: float = YIELD_CURVE_Z_THRESHOLD,
) -> pd.DataFrame:
    """
    Flags EVERY ticker in `data` when the yield-curve proxy
    (`curve_data`, from data.macro_data.build_yield_curve_proxy()) has
    an extreme trailing return z-score on `as_of`: "dip" for a sharp
    further inversion (recession-fear spike, expect a broad bounce),
    "up" for a sharp steepening (included for symmetry).
    """
    if as_of is None or as_of not in curve_data.index:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    features = compute_features(curve_data)
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
