"""Compatibility facade for canonical, product-neutral portfolio metrics.

The implementation moved to :mod:`data.portfolio_metrics` during SEP-1 so
the paper-evidence reader does not import the research product. Existing
research imports retain exact function identity through these aliases.
"""
from data.portfolio_metrics import (
    downside_capture_pct,
    expected_shortfall_pct,
    max_drawdown_pct,
    time_under_water,
    upside_capture_pct,
)

__all__ = [
    "downside_capture_pct",
    "expected_shortfall_pct",
    "max_drawdown_pct",
    "time_under_water",
    "upside_capture_pct",
]
