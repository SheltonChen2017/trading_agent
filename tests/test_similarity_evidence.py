"""Tests for assistant/similarity_evidence.py. Run with:
python tests/test_similarity_evidence.py"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from assistant import similarity_evidence


def _price_series(days, seed, drift=0.001, vol=0.02):
    rng = np.random.default_rng(seed)
    returns = rng.normal(loc=drift, scale=vol, size=days)
    close = 100 * np.cumprod(1 + returns)
    dates = pd.bdate_range("2026-01-01", periods=days)
    return pd.DataFrame({"close": close}, index=dates)


def _correlated_pair(days=150, seed=1, noise=0.001):
    rng = np.random.default_rng(seed)
    shared_returns = rng.normal(loc=0.001, scale=0.02, size=days)
    a_returns = shared_returns + rng.normal(0, noise, size=days)
    b_returns = shared_returns + rng.normal(0, noise, size=days)
    dates = pd.bdate_range("2026-01-01", periods=days)
    a_close = 100 * np.cumprod(1 + a_returns)
    b_close = 100 * np.cumprod(1 + b_returns)
    return (
        pd.DataFrame({"close": a_close}, index=dates),
        pd.DataFrame({"close": b_close}, index=dates),
    )


def test_compute_similarity_evidence_measures_high_correlation_for_correlated_series():
    candidate_df, source_df = _correlated_pair()
    with patch("assistant.similarity_evidence.fetch_historical", return_value={"AMD": candidate_df, "NVDA": source_df}), \
         patch("assistant.similarity_evidence._safe_ticker_info", return_value={"sector": "Technology", "industry": "Semiconductors"}):
        evidence = similarity_evidence.compute_similarity_evidence(["NVDA"], "AMD")
    assert evidence.return_correlation_pct is not None
    assert evidence.return_correlation_pct > 80.0
    assert evidence.shared_sectors == ("NVDA",)
    assert evidence.shared_industries == ("NVDA",)


def test_compute_similarity_evidence_reports_unmeasured_when_history_missing():
    with patch("assistant.similarity_evidence.fetch_historical", return_value={}), \
         patch("assistant.similarity_evidence._safe_ticker_info", return_value={}):
        evidence = similarity_evidence.compute_similarity_evidence(["NVDA"], "FAKETIX")
    assert evidence.return_correlation_pct is None
    assert evidence.shared_sectors == ()
    assert evidence.shared_industries == ()


def test_compute_similarity_evidence_does_not_fabricate_sector_match_for_a_false_claim():
    # The exact CAT-vs-NVDA scenario from the review: CAT is a real, resolvable
    # ticker with real history, but its sector/industry genuinely differ from
    # NVDA's -- the false "semiconductor" claim must not be corroborated.
    candidate_df = _price_series(150, seed=5, drift=0.0002, vol=0.015)  # industrial-like, low-vol
    source_df = _price_series(150, seed=6, drift=0.002, vol=0.04)  # semiconductor-like, high-vol, uncorrelated
    with patch("assistant.similarity_evidence.fetch_historical", return_value={"CAT": candidate_df, "NVDA": source_df}), \
         patch("assistant.similarity_evidence._safe_ticker_info", side_effect=lambda t: (
             {"sector": "Industrials", "industry": "Farm & Heavy Construction Machinery"} if t == "CAT"
             else {"sector": "Technology", "industry": "Semiconductors"}
         )):
        evidence = similarity_evidence.compute_similarity_evidence(["NVDA"], "CAT")
    assert evidence.shared_sectors == ()
    assert evidence.shared_industries == ()


def test_compute_similarity_evidence_ignores_pairs_with_too_little_overlap():
    candidate_df = _price_series(10, seed=1)  # too short to trust a correlation
    source_df = _price_series(150, seed=2)
    with patch("assistant.similarity_evidence.fetch_historical", return_value={"NEW": candidate_df, "OLD": source_df}), \
         patch("assistant.similarity_evidence._safe_ticker_info", return_value={}):
        evidence = similarity_evidence.compute_similarity_evidence(["OLD"], "NEW")
    assert evidence.return_correlation_pct is None


def test_format_evidence_summary_reports_unmeasured_and_no_match_honestly():
    evidence = similarity_evidence.SimilarityEvidence(
        source_tickers=("NVDA",), candidate_ticker="CAT", shared_sectors=(), shared_industries=(),
        return_correlation_pct=None, lookback_days=126, data_start=None, data_end=None,
    )
    summary = similarity_evidence.format_evidence_summary(evidence)
    assert "unmeasured" in summary
    assert "no shared sector/industry found" in summary


def test_format_evidence_summary_reports_measured_correlation_and_industry_match():
    evidence = similarity_evidence.SimilarityEvidence(
        source_tickers=("NVDA",), candidate_ticker="AMD", shared_sectors=("NVDA",), shared_industries=("NVDA",),
        return_correlation_pct=87.3, lookback_days=126, data_start="2026-01-01", data_end="2026-06-01",
    )
    summary = similarity_evidence.format_evidence_summary(evidence)
    assert "87%" in summary
    assert "shares industry with NVDA" in summary


if __name__ == "__main__":
    test_compute_similarity_evidence_measures_high_correlation_for_correlated_series()
    test_compute_similarity_evidence_reports_unmeasured_when_history_missing()
    test_compute_similarity_evidence_does_not_fabricate_sector_match_for_a_false_claim()
    test_compute_similarity_evidence_ignores_pairs_with_too_little_overlap()
    test_format_evidence_summary_reports_unmeasured_and_no_match_honestly()
    test_format_evidence_summary_reports_measured_correlation_and_industry_match()
    print("All similarity_evidence tests passed.")
