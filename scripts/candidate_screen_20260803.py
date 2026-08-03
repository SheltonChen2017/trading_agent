"""Shared evidence contract for the frozen 2026-08-03 candidate screen.

The price-signal and PEAD runners are two executables for one statistical
family.  Keeping the family size here prevents one report from using a more
lenient Bonferroni denominator than the other, and keeping primary-row
selection here makes a missing engine column a refusal rather than a license
to treat every sensitivity row as evidence.
"""
from __future__ import annotations

import pandas as pd


CANDIDATE_SIGNAL_NAMES = (
    "residual_momentum",
    "vol_scaled_momentum",
    "residual_reversal",
    "pead_persistence",
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
