"""
Market regime classification.

Built to test a specific finding (2026-07): momentum's edge showed a
real, statistically significant sign-flip between two multi-year eras of
the project's ~7-year test window (discovery: -0.15pp edge, p=0.000;
confirmation: +0.25pp edge, p=0.000 — both independently significant,
opposite signs). This matches the documented "momentum crashes"
phenomenon (Daniel & Moskowitz, 2016): momentum tends to perform
reasonably in steady trending markets but suffers sharp, real reversals
following periods of elevated market volatility (e.g. after a crash and
violent recovery).

`compute_trailing_market_volatility()` is purely backward-looking (only
ever uses data up to and including `as_of`), consistent with every other
feature in this project — safe to use without introducing look-ahead
bias.

The high/low-volatility THRESHOLD is deliberately not a fixed constant.
`calibrate_threshold_from_discovery()` fits it from the discovery
period's OWN volatility distribution only, so that when the same fixed
threshold is later applied to classify confirmation-period dates, the
confirmation period stays honestly out-of-sample — the threshold itself
was never tuned using confirmation data. This mirrors the same
discovery/confirmation discipline `backtest/engine.py`'s out-of-sample
functions already enforce for signal edges.
"""
from market_analytics import (
    calibrate_volatility_threshold as calibrate_threshold_from_discovery,
    classify_volatility_regime as classify_regime,
    compute_trailing_market_volatility,
)

__all__ = [
    "calibrate_threshold_from_discovery",
    "classify_regime",
    "compute_trailing_market_volatility",
]
