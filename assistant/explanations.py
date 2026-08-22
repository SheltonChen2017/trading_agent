"""
"Why was X flagged?" — the explain-a-signal feature from the assistant
design (2026-07). Reports whether a ticker is currently flagged by any
of this project's per-ticker signals, what this project's OWN research
says about that signal family's track record (never omitted or
softened — every signal family tested so far is REJECTED, and this
function says so plainly), whether it's currently held, and today's
market regime context.

Cross-sectional signals (momentum, relative-scanner) need the full
universe as ranking context, not just one ticker, so they aren't re-run
here — their overall track record still shows up via historical_evidence
regardless of today's trigger status.
"""
from __future__ import annotations

from assistant.context_builder import KNOWN_FINDINGS, build_market_regime
from assistant.research_registry import underfilled_dataset_warning
from assistant.schemas import MarketRegime, PortfolioSnapshot
from data.research_results import (
    ResearchResultContractError,
    TickerSignalResearchResult,
)


class MissingResearchResultError(RuntimeError):
    """The composition layer omitted the read-only signal result."""


def explain_ticker(
    ticker: str,
    portfolio: PortfolioSnapshot | None = None,
    market_regime: MarketRegime | None = None,
    *,
    signal_result: TickerSignalResearchResult | None = None,
) -> dict:
    """
    Returns a plain, JSON-serializable dict explaining a ticker's current
    signal status: which per-ticker rules fire on it TODAY (if any), this
    project's own historical evidence for those rule families, whether
    it's currently held, and the broad market regime.

    Pass `market_regime` (e.g. reused from the same DecisionPacket) to
    avoid an extra benchmark data fetch when explaining several tickers
    in one session — computed fresh via build_market_regime() otherwise.

    `signal_result` is an immutable, display-only result produced by the
    research product and supplied by the composition layer. This assistant
    module never imports or executes a scanner. Missing or wrong-ticker
    results fail closed instead of silently showing "no signal".
    """
    ticker = ticker.upper()
    if signal_result is None:
        raise MissingResearchResultError(
            "ticker explanation requires a read-only research result from "
            "the product composition layer"
        )
    if signal_result.ticker != ticker:
        raise ResearchResultContractError(
            f"research result is for {signal_result.ticker}, not {ticker}"
        )
    triggered = [trigger.to_dict() for trigger in signal_result.triggers]

    relevant_findings = [
        e for e in KNOWN_FINDINGS
        if not e.relevant_tickers or ticker in (t.upper() for t in e.relevant_tickers)
    ]

    held_position = None
    if portfolio is not None:
        held_position = next((p for p in portfolio.positions if p.ticker.upper() == ticker), None)

    regime = market_regime if market_regime is not None else build_market_regime()

    return {
        "ticker": ticker,
        "triggered_today": triggered,
        "historical_evidence": [
            {
                "label": e.label, "claim": e.claim, "status": e.status.value, "detail": e.detail, "source": e.source,
                "ticker_specific": bool(e.relevant_tickers),
                # display_status/production_authoritative (GPT review,
                # 2026-07-29): a confirmed/promising finding not yet
                # re-verified since the fetch_historical lookback-days
                # fix must never be shown as an unqualified "confirmed"
                # result -- callers must use display_status, not status,
                # for anything user-facing.
                "display_status": e.display_status,
                "production_authoritative": e.production_authoritative,
                "dataset_warning": underfilled_dataset_warning(e.provenance) if e.provenance is not None else None,
            }
            for e in relevant_findings
        ],
        "currently_held": (
            {"shares": held_position.shares, "market_value": held_position.market_value,
             "unrealized_pnl_pct": held_position.unrealized_pnl_pct}
            if held_position is not None else None
        ) if portfolio is not None else "not_checked",
        "market_regime": {
            "benchmark": regime.benchmark_ticker, "trend": regime.trend,
            "volatility_regime": regime.volatility_regime,
        },
        "note": "Cross-sectional signals (momentum, relative-scanner) need the full universe as ranking "
        "context and aren't re-run per-ticker here — see historical_evidence for their overall track record.",
    }
