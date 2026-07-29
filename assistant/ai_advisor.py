"""
AI-assisted advisory layer for the Watchlist's computed allocation split and
ticker suggestions. Same opt-in/fallback contract as assistant/news_summary.py:
gated on ANTHROPIC_API_KEY, returns None (or an empty list) on ANY failure, and
is NEVER a source of any number that reaches AllocationPlanEntry/TradeProposal/
TradingPolicy -- every dollar amount, share count, and weight percentage is
already computed by assistant/stock_lookup.py / assistant/allocation_proposals.py
before this module ever sees it. This module's only job is to comment on, and
suggest tickers alongside, numbers it never touches.

Ticker suggestions use a two-tier trust model: the model is asked to prefer
tickers from config.UNIVERSE (already-vetted by this project), but may also
freely suggest tickers outside that list. The split is decided by deterministic
Python (assistant.ticker_verification.partition_by_universe), never by the
model's own claim -- "AI never computes/classifies, only narrates". Wildcard
suggestions must be verified (assistant.ticker_verification.verify_tickers)
before ever being shown; from-universe suggestions need no extra verification,
since they're already tickers this project uses everywhere.
"""
from __future__ import annotations

import json
import os

import config

SUGGESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["ticker", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["suggestions"],
    "additionalProperties": False,
}


def is_ai_advisor_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def review_allocation_plan(
    cart_tickers: list[str],
    weights_pct: dict[str, float],
    volatilities: dict[str, float | None],
    baskets_by_ticker: dict[str, list[str]],
) -> str | None:
    """2-4 sentence advisory commentary on the ALREADY-COMPUTED weights_pct --
    concentration, basket overlap, volatility character, diversification.
    Never returns a number that could be mistaken for a revised weight.
    Returns None (never raises) if unconfigured or the call fails."""
    if not cart_tickers or not is_ai_advisor_configured():
        return None

    import anthropic

    client = anthropic.Anthropic()
    lines = []
    for ticker in cart_tickers:
        vol = volatilities.get(ticker)
        vol_str = f"{vol:.2f}%" if vol is not None else "unknown"
        baskets = ", ".join(baskets_by_ticker.get(ticker, [])) or "none"
        lines.append(f"- {ticker}: weight={weights_pct.get(ticker, 0.0):.1f}%, volatility={vol_str}, baskets=[{baskets}]")
    detail_block = "\n".join(lines)

    try:
        response = client.messages.create(
            model="claude-opus-5",
            max_tokens=600,
            thinking={"type": "disabled"},
            system=(
                "You comment on an ALREADY-COMPUTED inverse-volatility portfolio split, in "
                "2-4 sentences. Discuss concentration, basket/sector overlap, and volatility "
                "character. Do not propose a different split, do not state a revised weight "
                "or dollar amount for any ticker, and do not give price predictions or "
                "buy/sell recommendations -- the weights shown are fixed and already decided. "
                "Do not include internal or system XML tags in your response."
            ),
            messages=[{"role": "user", "content": f"Computed split:\n{detail_block}"}],
        )
        return next((block.text for block in response.content if block.type == "text"), None)
    except Exception:
        return None


def suggest_similar_tickers(cart_tickers: list[str], max_suggestions: int = 8) -> list[dict] | None:
    """Structured {"ticker","reason"} suggestions related to cart_tickers, drawn
    from the model's own knowledge. Prefers tickers from config.UNIVERSE but may
    also suggest tickers outside it. Returns the RAW list (not yet partitioned
    or verified) -- caller MUST run assistant.ticker_verification.partition_by_universe()
    (and verify_tickers() on the wildcard remainder) before display. Returns
    None (never raises) if unconfigured or the call fails."""
    if not cart_tickers or not is_ai_advisor_configured():
        return None

    import anthropic

    client = anthropic.Anthropic()
    universe_list = ", ".join(sorted(config.UNIVERSE))
    try:
        response = client.messages.create(
            model="claude-opus-5",
            max_tokens=1024,
            thinking={"type": "disabled"},
            output_config={"format": {"type": "json_schema", "schema": SUGGESTION_SCHEMA}},
            system=(
                "You suggest publicly-traded US tickers related to a given set of tickers, "
                "for a user to independently research -- not a recommendation to buy or sell. "
                f"Prefer tickers from this known list when relevant: {universe_list}. You may "
                "also suggest additional tickers outside this list if you are confident they "
                "are real, correctly spelled, and genuinely relevant -- every ticker you name "
                "will be checked against real market data before being shown, so if you are not "
                "confident a ticker is real, do not include it. "
                f"Return at most {max_suggestions} suggestions."
            ),
            messages=[{"role": "user", "content": f"Tickers already in the cart: {', '.join(cart_tickers)}"}],
        )
        text = next((block.text for block in response.content if block.type == "text"), None)
        if not text:
            return None
        suggestions = json.loads(text)["suggestions"]
        return suggestions[:max_suggestions]
    except Exception:
        return None


def curate_recommended_tickers(candidates: list) -> str | None:
    """Takes an already-verified list of RecommendedTicker-shaped objects
    (ticker + reason_category + detail, no numbers) and returns free-text
    prose prioritizing/explaining them for the Briefing tab. Strictly
    downstream of verification -- never sees an unverified ticker. Returns
    None (never raises) if unconfigured, candidates is empty, or the call
    fails."""
    if not candidates or not is_ai_advisor_configured():
        return None

    import anthropic

    client = anthropic.Anthropic()
    lines = [f"- {c.ticker} ({c.reason_category}): {c.detail}" for c in candidates]
    try:
        response = client.messages.create(
            model="claude-opus-5",
            max_tokens=600,
            thinking={"type": "disabled"},
            system=(
                "You help a user prioritize a short list of tickers surfaced for exploration "
                "(not held, not a trade proposal). In 2-4 sentences, note which look most "
                "worth a closer look and why, based only on the categories/details given -- "
                "do not add price predictions, trading recommendations, or facts not present "
                "in the list. Do not include internal or system XML tags in your response."
            ),
            messages=[{"role": "user", "content": "Candidates:\n" + "\n".join(lines)}],
        )
        return next((block.text for block in response.content if block.type == "text"), None)
    except Exception:
        return None
