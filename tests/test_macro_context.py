from __future__ import annotations

import numpy as np
import pandas as pd

from assistant.macro_context import build_descriptive_macro_context


def _frame(values, dates):
    return pd.DataFrame({"close": values}, index=dates)


def test_macro_context_is_aligned_finite_and_explicitly_non_predictive():
    dates = pd.bdate_range("2026-01-01", periods=90)
    lqd = np.linspace(100, 101, len(dates))
    hyg = np.linspace(100, 90, len(dates))
    irx = np.linspace(4, 5, len(dates))
    tnx = np.linspace(4.5, 4.5, len(dates))
    # A provider NaN and mismatched start must be handled explicitly.
    lqd[20] = np.nan
    data = {
        "LQD": _frame(lqd, dates),
        "HYG": _frame(hyg[5:], dates[5:]),
        "^IRX": _frame(irx, dates),
        "^TNX": _frame(tnx, dates),
    }

    context = build_descriptive_macro_context(
        fetcher=lambda tickers, lookback_days=90: data
    )

    assert context["available"]
    assert context["predictive"] is False
    assert "rejected" in context["evidence_status"]
    assert context["indicators"][0]["direction"].startswith("widening")
    assert context["indicators"][1]["direction"].startswith("flattening")
    assert "cannot influence trade proposals" in context["disclaimer"]


def test_macro_context_reports_missing_inputs_instead_of_guessing():
    context = build_descriptive_macro_context(
        fetcher=lambda tickers, lookback_days=90: {"LQD": pd.DataFrame()}
    )
    assert not context["available"]
    assert "missing proxy inputs" in context["reason"]
