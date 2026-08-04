"""Shared evidence contract for the 2026-08-03 (second) candidate screen.

The first 2026-08-03 screen (residual_momentum, vol_scaled_momentum,
residual_reversal, pead_persistence -- see candidate_screen_20260803.py)
has already been run and its results observed. This is a SEPARATE,
independently pre-registered family for two new candidates sourced from
a fresh literature search that day, so it gets its own N_TESTS /
Bonferroni denominator rather than silently reusing or inflating the
first family's.

Both candidates are well-established, heavily-replicated academic
anomalies with no prior presence in this codebase:

  high52_proximity  -- George & Hwang (2004), 52-week-high proximity
  idio_vol          -- Ang, Hodrick, Xing & Zhang (2006), idiosyncratic
                        volatility anomaly

2 signals x 2 directions = 4 pre-registered cells; every Bonferroni
threshold is alpha/4.
"""
from __future__ import annotations

import pandas as pd


CANDIDATE_SIGNAL_NAMES = (
    "high52_proximity",
    "idio_vol",
)
DIRECTIONS = ("dip", "up")
N_TESTS = len(CANDIDATE_SIGNAL_NAMES) * len(DIRECTIONS)


def confirmation_primary_rows(table: pd.DataFrame) -> pd.DataFrame:
    """Return only confirmation-period primary rows, failing closed on drift."""
    required = {"period", "direction", "primary", "significant"}
    missing = sorted(required - set(table.columns))
    if missing:
        raise ValueError(
            "Significance output is missing required evidence column(s): "
            + ", ".join(missing)
        )
    for column in ("primary", "significant"):
        if not pd.api.types.is_bool_dtype(table[column].dtype):
            raise ValueError(
                f"Significance output column {column!r} must be boolean, "
                f"got dtype {table[column].dtype}."
            )
    return table.loc[
        table["period"].eq("confirmation") & table["primary"]
    ].copy()
