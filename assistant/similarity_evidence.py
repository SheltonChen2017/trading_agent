"""
Deterministic (non-LLM) evidence for "is candidate_ticker actually similar to
source_tickers" -- computed from real price history and yfinance identity
metadata, displayed ALONGSIDE every AI-suggested ticker's stated reason so
that reason is checkable against measured data rather than trusted on its
own (independent review: a real, resolvable ticker -- e.g. CAT -- can carry
a FALSE similarity claim, such as "a semiconductor company similar to NVDA",
and still pass assistant.ticker_verification.verify_tickers() cleanly, since
that function only proves the symbol resolves to a real security, never that
the stated relationship is true).

Deliberately does NOT replace the LLM's freedom to suggest a ticker from its
own knowledge -- that two-tier (prefer config.UNIVERSE, allow verified
wildcards) design was an explicit project decision. This module adds a
SECOND, measured signal next to the first; the user sees both and can judge
whether they agree, rather than the LLM's prose being the only signal shown.
"""
from __future__ import annotations

import dataclasses

import pandas as pd

from assistant.ticker_verification import _safe_ticker_info
from data.market_data import fetch_historical

_MIN_OVERLAPPING_SESSIONS = 20  # below this, a correlation is noise, not signal -- report unmeasured instead


@dataclasses.dataclass(frozen=True)
class SimilarityEvidence:
    source_tickers: tuple[str, ...]
    candidate_ticker: str
    shared_sectors: tuple[str, ...]
    shared_industries: tuple[str, ...]
    return_correlation_pct: float | None  # mean pairwise daily-return correlation vs source_tickers, as a percentage
    lookback_days: int
    data_start: str | None
    data_end: str | None


def compute_similarity_evidence(
    source_tickers: list[str], candidate_ticker: str, lookback_days: int = 126
) -> SimilarityEvidence:
    """Real correlation + sector/industry overlap between candidate_ticker
    and source_tickers over the trailing `lookback_days` (default ~6 trading
    months). Never raises; an absence of evidence (missing history, missing
    identity metadata) is reported as None/empty ("unmeasured"), never
    fabricated as 0% or a false match."""
    try:
        data = fetch_historical(list(dict.fromkeys([candidate_ticker] + source_tickers)), lookback_days=lookback_days)
    except Exception:
        data = {}

    correlation = None
    data_start = data_end = None
    if candidate_ticker in data and not data[candidate_ticker].empty:
        candidate_close = data[candidate_ticker]["close"]
        candidate_returns = candidate_close.pct_change().dropna()
        pairwise_correlations = []
        for source in source_tickers:
            if source not in data or data[source].empty:
                continue
            source_returns = data[source]["close"].pct_change().dropna()
            aligned = pd.concat([candidate_returns, source_returns], axis=1, join="inner").dropna()
            if len(aligned) < _MIN_OVERLAPPING_SESSIONS:
                continue
            pairwise_correlations.append(aligned.iloc[:, 0].corr(aligned.iloc[:, 1]))
        if pairwise_correlations:
            correlation = round(float(sum(pairwise_correlations) / len(pairwise_correlations)) * 100, 1)
        data_start = str(candidate_close.index[0].date())
        data_end = str(candidate_close.index[-1].date())

    candidate_info = _safe_ticker_info(candidate_ticker)
    candidate_sector = candidate_info.get("sector")
    candidate_industry = candidate_info.get("industry")
    shared_sectors: list[str] = []
    shared_industries: list[str] = []
    for source in source_tickers:
        source_info = _safe_ticker_info(source)
        if candidate_sector and candidate_sector == source_info.get("sector"):
            shared_sectors.append(source)
        if candidate_industry and candidate_industry == source_info.get("industry"):
            shared_industries.append(source)

    return SimilarityEvidence(
        source_tickers=tuple(source_tickers),
        candidate_ticker=candidate_ticker,
        shared_sectors=tuple(dict.fromkeys(shared_sectors)),
        shared_industries=tuple(dict.fromkeys(shared_industries)),
        return_correlation_pct=correlation,
        lookback_days=lookback_days,
        data_start=data_start,
        data_end=data_end,
    )


def format_evidence_summary(evidence: SimilarityEvidence) -> str:
    """Short human-readable summary meant to sit NEXT TO the LLM's own
    stated reason, e.g. in a table column -- lets a user see whether the
    measured evidence actually backs up the claim."""
    parts = []
    if evidence.return_correlation_pct is not None:
        parts.append(f"{evidence.return_correlation_pct:.0f}% return correlation ({evidence.lookback_days}d)")
    else:
        parts.append("correlation unmeasured (insufficient overlapping history)")
    if evidence.shared_industries:
        parts.append(f"shares industry with {', '.join(evidence.shared_industries)}")
    elif evidence.shared_sectors:
        parts.append(f"shares sector with {', '.join(evidence.shared_sectors)}")
    else:
        parts.append("no shared sector/industry found")
    return "; ".join(parts)
