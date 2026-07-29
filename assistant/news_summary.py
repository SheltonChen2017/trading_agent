"""
Recent news headlines for a ticker, and optional AI summarization of them.

Headline fetching is free (yfinance's Ticker.news, no API key) and always
available. AI summarization is a SEPARATE, explicit, opt-in step: it
requires ANTHROPIC_API_KEY and makes a real per-call Claude API request
with a real (small) cost. It is never silently substituted for the raw
headlines -- callers must check is_ai_summary_configured() or handle a
None return from summarize_news_for_ticker() and fall back to showing
the headlines themselves.

The summarization prompt is deliberately restricted to synthesizing what
the headlines themselves say -- explicitly told not to add price
predictions or recommendations of its own. This is a different, much
narrower use of Claude than the interactive assistant session that
built this project: it is the APPLICATION calling the API on its own,
autonomously, every time a user checks a ticker.
"""
from __future__ import annotations

import os


def fetch_recent_news(ticker: str, limit: int = 5) -> list[dict]:
    """Real, recent headlines via yfinance -- no API key needed. Returns
    [] on any fetch failure or if the ticker has no news, never raises."""
    import yfinance as yf

    try:
        raw = yf.Ticker(ticker).news or []
    except Exception:
        return []

    headlines = []
    for item in raw[:limit]:
        content = item.get("content", item)  # yfinance's news shape has changed before; be defensive
        provider = content.get("provider") or {}
        canonical = content.get("canonicalUrl") or {}
        headlines.append(
            {
                "title": content.get("title", ""),
                "summary": content.get("summary") or content.get("description") or "",
                "provider": provider.get("displayName", "unknown"),
                "published": content.get("pubDate", ""),
                "url": canonical.get("url", ""),
            }
        )
    return [h for h in headlines if h["title"]]


def is_ai_summary_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def summarize_news_for_ticker(ticker: str, headlines: list[dict]) -> str | None:
    """AI-generated 2-3 sentence summary of what the headlines say might
    affect the ticker's price. Returns None (never raises) if
    ANTHROPIC_API_KEY isn't set, there are no headlines, the API call fails,
    or the response fails the deterministic output guard -- callers should
    fall back to displaying the raw headlines.

    The guard (ai_advisor._reject_unsafe_prose) is the same one the other
    free-text AI surfaces use. This function previously returned the model's
    text unchanged, so a response like "You should buy NVDA now." would have
    been displayed verbatim despite the prompt forbidding exactly that -- a
    prompt is not an enforcement mechanism (GPT review, 2026-07-29).

    Grounding is checked against the SUPPLIED headlines, which are trusted
    deterministic source data: allowed tickers are this ticker plus any
    ticker-shaped token appearing in the headlines, and every number in the
    summary must appear in the headlines too. Non-numeric fabricated claims
    remain undetectable -- see _reject_unsafe_prose's own limitations note --
    which is why the raw headlines stay the primary UI surface and this
    summary is only ever an addition to them."""
    if not headlines or not is_ai_summary_configured():
        return None

    import anthropic

    client = anthropic.Anthropic()
    headline_block = "\n".join(
        f"- [{h['provider']}, {h['published']}] {h['title']}: {h['summary']}" for h in headlines
    )
    try:
        response = client.messages.create(
            model="claude-opus-5",
            max_tokens=600,
            thinking={"type": "disabled"},
            system=(
                "Summarize recent news headlines about a stock in 2-3 sentences, "
                "focused on what might affect its price. State only what the "
                "headlines actually say -- do not add price predictions, "
                "trading recommendations, or your own opinion about the stock. "
                "Do not include internal or system XML tags in your response."
            ),
            messages=[{"role": "user", "content": f"Ticker: {ticker}\n\n{headline_block}"}],
        )
        text = next((block.text for block in response.content if block.type == "text"), None)
    except Exception:
        return None

    if not text:
        return None
    # Imported here rather than at module scope to keep this module's
    # "headline fetching needs no API key and no heavy imports" property.
    import re

    from assistant.ai_advisor import _reject_unsafe_prose

    allowed_tickers = {ticker.upper()} | set(re.findall(r"\b[A-Z]{1,5}\b", headline_block))
    if _reject_unsafe_prose(text, allowed_tickers, source_text=headline_block) is not None:
        return None
    return text
