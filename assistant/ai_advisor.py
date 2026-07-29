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

import dataclasses
import hashlib
import json
import os
import re
import time

import config
from assistant.storage import AssistantStore

_MODEL = "claude-opus-5"
_REVIEW_ALLOCATION_PROMPT_VERSION = "review_allocation_plan.v1"
_SUGGEST_SIMILAR_PROMPT_VERSION = "suggest_similar_tickers.v1"
_CURATE_RECOMMENDED_PROMPT_VERSION = "curate_recommended_tickers.v1"

_ALLOWED_OBSERVATION_TYPES = ("concentration", "basket_overlap", "volatility", "diversification")
_ALLOWED_SEVERITIES = ("low", "medium", "high")
_PERCENT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_DOLLAR_PATTERN = re.compile(r"\$\s*[\d,]+(?:\.\d+)?")
_NUMBER_TOLERANCE_PCT = 1.0  # allows "60%" to match an actual weight of 60.3% without treating it as a fabricated number

ALLOCATION_REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "observations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": list(_ALLOWED_OBSERVATION_TYPES)},
                    "severity": {"type": "string", "enum": list(_ALLOWED_SEVERITIES)},
                    "claim": {"type": "string"},
                    "tickers": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["type", "severity", "claim", "tickers"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "observations"],
    "additionalProperties": False,
}


@dataclasses.dataclass(frozen=True)
class AllocationObservation:
    type: str
    severity: str
    claim: str
    tickers: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class AllocationReview:
    summary: str
    observations: tuple[AllocationObservation, ...]


def _contains_disallowed_number(text: str, allowed_weights_pct: list[float]) -> bool:
    """The instruction "don't propose a revised weight" is prompt-only and
    not otherwise enforced -- this is the actual enforcement. ANY dollar
    figure is disallowed outright (this function is never given a dollar
    amount as input, so one appearing in the response can only be
    invented). A percentage is disallowed unless it's within
    _NUMBER_TOLERANCE_PCT of one of the ACTUAL input weights -- close
    enough to be "the same number, differently rounded/phrased," not a
    proposed alternative."""
    if _DOLLAR_PATTERN.search(text):
        return True
    for match in _PERCENT_PATTERN.finditer(text):
        value = float(match.group(1))
        if not any(abs(value - allowed) <= _NUMBER_TOLERANCE_PCT for allowed in allowed_weights_pct):
            return True
    return False


def _validate_allocation_review(raw: dict, cart_tickers: list[str], weights_pct: dict[str, float]) -> AllocationReview | None:
    """Enforces, in code, what the system prompt only asks for in prose:
    every observation's `type`/`severity` is allowlisted (schema validation
    already guarantees this if the model followed the schema, but this is
    checked again defensively rather than trusted), every ticker mentioned
    was actually in the input cart, and no claim (or the summary) contains
    a number that isn't one of the actual input weights. The summary
    failing this check rejects the WHOLE response (returns None) --  an
    individual observation failing it is just dropped, since the rest of
    the response may still be trustworthy."""
    cart_set = {t.upper() for t in cart_tickers}
    allowed_weights = list(weights_pct.values())

    summary = raw.get("summary")
    if not isinstance(summary, str) or _contains_disallowed_number(summary, allowed_weights):
        return None

    kept_observations = []
    for obs in raw.get("observations", []):
        if not isinstance(obs, dict):
            continue
        obs_type = obs.get("type")
        severity = obs.get("severity")
        claim = obs.get("claim")
        tickers = obs.get("tickers")
        if obs_type not in _ALLOWED_OBSERVATION_TYPES or severity not in _ALLOWED_SEVERITIES:
            continue
        if not isinstance(claim, str) or not isinstance(tickers, list):
            continue
        if not tickers or not all(isinstance(t, str) and t.upper() in cart_set for t in tickers):
            continue
        if _contains_disallowed_number(claim, allowed_weights):
            continue
        kept_observations.append(
            AllocationObservation(type=obs_type, severity=severity, claim=claim, tickers=tuple(t.upper() for t in tickers))
        )

    return AllocationReview(summary=summary, observations=tuple(kept_observations))


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


def _input_hash(*parts) -> str:
    canonical = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _record_run(
    store: AssistantStore | None,
    function_name: str,
    prompt_version: str,
    input_hash: str,
    start: float,
    response: object = None,
    error: str | None = None,
) -> None:
    """Best-effort audit logging (independent review: AI runs weren't
    persisted anywhere -- no model, prompt version, input hash, latency, or
    response was recorded, making this layer unauditable after the fact).
    `store` is optional, matching this project's existing convention (e.g.
    generate_soxx_soxl_rebalance_proposals's own `store` param) -- callers
    that don't have a store on hand simply don't get a persisted record.
    A persistence failure must never break the actual advisory feature, so
    this swallows its own exceptions rather than propagating them."""
    if store is None:
        return
    latency_ms = (time.monotonic() - start) * 1000
    try:
        store.record_ai_run(
            function_name=function_name,
            model=_MODEL,
            prompt_version=prompt_version,
            input_hash=input_hash,
            latency_ms=latency_ms,
            success=error is None,
            response=response,
            error=error,
        )
    except Exception:
        pass


def review_allocation_plan(
    cart_tickers: list[str],
    weights_pct: dict[str, float],
    volatilities: dict[str, float | None],
    baskets_by_ticker: dict[str, list[str]],
    store: AssistantStore | None = None,
) -> AllocationReview | None:
    """Structured advisory commentary on the ALREADY-COMPUTED weights_pct --
    concentration, basket overlap, volatility character, diversification.

    The "don't propose a revised weight/dollar amount" instruction is NOT
    prompt-only: every observation's type/severity is schema-constrained,
    every ticker mentioned is checked against cart_tickers, and the summary
    plus every observation's claim is scanned for a number that isn't one
    of the actual input weights (assistant.ai_advisor._validate_allocation_review) --
    a claim or summary that fails this is dropped/rejected rather than
    trusted and displayed. Returns None (never raises) if unconfigured, the
    call fails, the response doesn't parse, or the summary itself fails
    validation."""
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
    input_hash = _input_hash(cart_tickers, weights_pct, volatilities, baskets_by_ticker)
    start = time.monotonic()

    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=800,
            thinking={"type": "disabled"},
            output_config={"format": {"type": "json_schema", "schema": ALLOCATION_REVIEW_SCHEMA}},
            system=(
                "You comment on an ALREADY-COMPUTED inverse-volatility portfolio split. Return a "
                "short summary plus 0-4 structured observations, each with a type "
                f"({'/'.join(_ALLOWED_OBSERVATION_TYPES)}), a severity ({'/'.join(_ALLOWED_SEVERITIES)}), "
                "a one-sentence claim, and the ticker(s) it's about. ONLY reference tickers and "
                "weight percentages EXACTLY as given below -- never state a revised weight, a "
                "different split, a dollar amount, or a buy/sell recommendation; every number you "
                "write will be checked against the input and discarded if it doesn't match."
            ),
            messages=[{"role": "user", "content": f"Computed split:\n{detail_block}"}],
        )
        text = next((block.text for block in response.content if block.type == "text"), None)
        if not text:
            _record_run(store, "review_allocation_plan", _REVIEW_ALLOCATION_PROMPT_VERSION, input_hash, start, error="no text block in response")
            return None
        raw = json.loads(text)
        result = _validate_allocation_review(raw, cart_tickers, weights_pct)
        _record_run(
            store, "review_allocation_plan", _REVIEW_ALLOCATION_PROMPT_VERSION, input_hash, start,
            response=raw, error=None if result is not None else "failed post-hoc validation",
        )
        return result
    except Exception as exc:
        _record_run(store, "review_allocation_plan", _REVIEW_ALLOCATION_PROMPT_VERSION, input_hash, start, error=str(exc))
        return None


def suggest_similar_tickers(
    cart_tickers: list[str], max_suggestions: int = 8, store: AssistantStore | None = None
) -> list[dict] | None:
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
    input_hash = _input_hash(cart_tickers, max_suggestions)
    start = time.monotonic()
    try:
        response = client.messages.create(
            model=_MODEL,
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
            _record_run(store, "suggest_similar_tickers", _SUGGEST_SIMILAR_PROMPT_VERSION, input_hash, start, error="no text block in response")
            return None
        suggestions = json.loads(text)["suggestions"][:max_suggestions]
        _record_run(store, "suggest_similar_tickers", _SUGGEST_SIMILAR_PROMPT_VERSION, input_hash, start, response=suggestions)
        return suggestions
    except Exception as exc:
        _record_run(store, "suggest_similar_tickers", _SUGGEST_SIMILAR_PROMPT_VERSION, input_hash, start, error=str(exc))
        return None


def curate_recommended_tickers(candidates: list, store: AssistantStore | None = None) -> str | None:
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
    input_hash = _input_hash([c.ticker for c in candidates])
    start = time.monotonic()
    try:
        response = client.messages.create(
            model=_MODEL,
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
        text = next((block.text for block in response.content if block.type == "text"), None)
        _record_run(store, "curate_recommended_tickers", _CURATE_RECOMMENDED_PROMPT_VERSION, input_hash, start, response=text, error=None if text else "no text block in response")
        return text
    except Exception as exc:
        _record_run(store, "curate_recommended_tickers", _CURATE_RECOMMENDED_PROMPT_VERSION, input_hash, start, error=str(exc))
        return None
