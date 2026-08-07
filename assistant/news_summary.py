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


def _known_tickers() -> set[str]:
    """Every ticker this project recognizes, for validating headline tokens.

    Imported lazily for the same reason the guard is: this module's headline
    fetching must stay free of heavy imports.
    """
    from config import BASKETS, LEVERAGED_ETF_TICKERS, UNIVERSE

    known = {str(t).upper() for t in UNIVERSE}
    known |= {str(t).upper() for t in LEVERAGED_ETF_TICKERS}
    for members in BASKETS.values():
        known |= {str(t).upper() for t in members}
    return known


def summarize_news_for_ticker(ticker: str, headlines: list[dict]) -> str | None:
    """Backward-compatible wrapper: the summary, or None.

    Prefer `summarize_news_for_ticker_with_reason` in any UI. Returning a
    bare None makes "disabled", "call failed" and "the guard withheld it"
    indistinguishable, which is exactly how a working feature came to look
    broken (owner report, 2026-08-07).
    """
    return summarize_news_for_ticker_with_reason(ticker, headlines)[0]


def summarize_news_for_ticker_with_reason(
    ticker: str, headlines: list[dict]
) -> tuple[str | None, str | None]:
    """AI-generated 2-3 sentence summary of what the headlines say might
    affect the ticker's price.

    Returns ``(summary, None)`` on success, or ``(None, reason)`` when the
    summary is unavailable -- never raises. Reasons are fixed labels (no
    withheld model prose, no provider exception text). Callers should fall
    back to displaying the raw headlines.

    The guard (ai_advisor._reject_unsafe_prose) is the same one the other
    free-text AI surfaces use. This function previously returned the model's
    text unchanged, so a response like "You should buy NVDA now." would have
    been displayed verbatim despite the prompt forbidding exactly that -- a
    prompt is not an enforcement mechanism (GPT review, 2026-07-29).

    Grounding is checked against the SUPPLIED headlines. Those headlines are
    NOT trusted input -- an earlier version of this docstring called them
    "trusted deterministic source data", which was wrong: they come from
    yfinance, i.e. a third party, and are therefore attacker-influenceable.
    This is a genuine indirect-prompt-injection surface (independent review,
    2026-07-30). What the guard can promise given untrusted source text:

    * Allowed tickers are this ticker plus headline tokens that are ALSO in
      this project's known ticker set -- not any ticker-shaped token, which
      would have let an injected headline authorize its own invented symbol.
    * Every number in the summary must appear in the headlines. Note the
      limit of this under injection: a number injected INTO a headline is
      grounded by definition. The mitigation is not the guard, it is that the
      raw headline is displayed alongside, so the user sees the same claim in
      its original form rather than only as AI prose.
    * Explicit buy/sell/trim language is rejected regardless of source, so an
      injected headline cannot turn the summary into advice.

    Non-numeric fabricated claims remain undetectable -- see
    _reject_unsafe_prose's own limitations note -- which is why the raw
    headlines stay the primary UI surface and this summary is only ever an
    addition to them."""
    if not headlines:
        return None, "no headlines were available to summarize"
    if not is_ai_summary_configured():
        return None, "ANTHROPIC_API_KEY is not set"

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
    except Exception as exc:
        # The exception TYPE only: a provider message can echo attacker-
        # influenceable headline text back into the UI.
        return None, f"the model call failed ({type(exc).__name__})"

    if not text:
        return None, "the model returned no text"
    # Imported here rather than at module scope to keep this module's
    # "headline fetching needs no API key and no heavy imports" property.
    import re

    from assistant.ai_advisor import _reject_unsafe_prose

    # Headline-derived tokens are intersected with the tickers this project
    # actually knows, rather than accepted wholesale. Promoting every all-caps
    # token to "allowed ticker" made the unknown-ticker check depend on
    # attacker-influenceable text: news arrives from a third party, so a
    # headline containing a ticker-shaped token was enough to let the model
    # name it as though it had been verified (independent review, 2026-07-30).
    # The requested ticker is always allowed -- it is the subject of the query
    # and is verified upstream.
    known = _known_tickers()
    headline_tokens = set(re.findall(r"\b[A-Z]{1,5}\b", headline_block))
    allowed_tickers = {ticker.upper()} | (headline_tokens & known)
    verdict = _reject_unsafe_prose(text, allowed_tickers, source_text=headline_block)
    if verdict is not None:
        # The VERDICT travels, never the rejected prose -- surfacing the text
        # the guard refused would defeat the guard. The verdict strings are
        # fixed, model-independent labels.
        #
        # This is the common case for a portfolio held outside
        # `config.UNIVERSE`: `allowed_tickers` is built from that research
        # universe, so a summary naming any peer company is withheld. Measured
        # 2026-08-07 on the owner's own holdings: 7 of 8 tickers withheld,
        # while AAPL/MSFT passed 10/10. Silence made that look like a broken
        # feature rather than a working control.
        return None, f"withheld by the output guard: {verdict}"
    return text, None
