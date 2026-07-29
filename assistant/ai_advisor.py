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
_REVIEW_ALLOCATION_PROMPT_VERSION = "review_allocation_plan.v3"
_SUGGEST_SIMILAR_PROMPT_VERSION = "suggest_similar_tickers.v1"
_CURATE_RECOMMENDED_PROMPT_VERSION = "curate_recommended_tickers.v1"

_ALLOWED_OBSERVATION_TYPES = ("concentration", "basket_overlap", "volatility", "diversification")
_ALLOWED_SEVERITIES = ("low", "medium", "high")
_PERCENT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_DOLLAR_PATTERN = re.compile(r"\$\s*[\d,]+(?:\.\d+)?")
_NUMBER_TOLERANCE_PCT = 1.0  # allows "60%" to match an actual weight of 60.3% without treating it as a fabricated number
_TICKER_TOKEN_PATTERN = re.compile(r"\b[A-Z]{1,5}\b")
# Common all-caps acronyms that are NOT tickers -- everything else that
# looks ticker-shaped and isn't explicitly allowed gets rejected (see
# _mentions_unknown_ticker: independent review found that scoping the
# reject-list to config.UNIVERSE membership let a real-but-out-of-universe
# ticker, a newly-listed ticker, or an outright hallucinated symbol like
# "RDDT" all slip through silently, since UNIVERSE is a curated research
# list and can never be a complete security master).
_SAFE_ACRONYMS = frozenset({"ETF", "USD", "AI", "CEO", "CFO", "SEC", "IPO", "NYSE", "IRS", "GDP", "CPI", "FED", "US"})
# Independent review, third pass: the second pass's blanket `\w*` stems
# (allocat\w*, target\w*, increas\w*, reduc\w*) rejected ordinary descriptive
# prose too -- "This allocation is concentrated in semiconductors.", "The
# target volatility is elevated.", "NVDA has increased volatility." all
# matched and were wrongly dropped. Action language is now split into tiers
# instead of one blanket word list:
#   1. Unambiguous transactional verbs (buy/sell/rebalance/replace) -- these
#      are never used descriptively in an allocation-review context, so a
#      bare word match is safe.
#   2. Advice/recommendation markers (should, consider, prefer, deserve, ...)
#      -- these only ever appear when the model is giving advice, not
#      describing a fact.
#   3. Modal/passive constructions ("we can increase NVDA", "AMD could be
#      reduced") -- fourth pass: these carry no noun/comparative/percentage
#      trigger at all, so tier 4 below never saw them; the modal+verb
#      combination alone is inherently advisory regardless of what follows.
#   4. Context-sensitive verbs (allocate/increase/reduce/target) -- these ARE
#      used descriptively ("increased volatility", "reduced diversification",
#      "the volatility target"), so they're only rejected when they appear
#      near an actual allocation-change object (a position/weight/exposure
#      noun, a comparative like "more"/"larger", or a percentage) -- i.e. an
#      actual proposed change, not a description of the current state.
#   5. A context-sensitive verb directly governing one of the ALLOWED
#      tickers as its object ("Increase NVDA.", "Target NVDA at 60%.") --
#      fourth pass: tier 4's trigger nouns don't include ticker symbols, so a
#      bare "Increase NVDA." carried no recognized trigger at all. This is
#      ticker-scoped and uses a SHORT (~15-char) forward window specifically
#      to distinguish "reduce AMD" (AMD is the direct object) from "AMD has
#      reduced correlation with NVDA over the sampled period" (NVDA is many
#      characters away, inside an unrelated prepositional phrase) --
#      widening this window to tier 4's 40 chars would reject that second,
#      legitimate sentence. Ticker matching is deliberately NOT case-folded
#      (unlike the verb match) for the same reason _mentions_unknown_ticker
#      matches original-case text: a genuine ticker mention is written in
#      real caps, so this only fires on an actual ticker mention, not an
#      incidental lowercase word that happens to share letters with one.
_UNAMBIGUOUS_ACTION_PATTERN = re.compile(
    r"\b(buy|buying|bought|sell|selling|sold|"
    r"rebalance|rebalancing|rebalanced|replace|replacing|replaced)\b",
    re.IGNORECASE,
)
_ADVICE_PATTERN = re.compile(
    r"\b(should|ought\s+to|consider(?:ing)?|prefer(?:red|s|ring)?|"
    r"favor(?:ed|s|ing)?|deserv(?:e|es|ed|ing)|recommend(?:ed|s|ing)?)\b",
    re.IGNORECASE,
)
_ALLOCATION_ACTION_VERBS = (
    r"allocate|allocating|allocated|increase|increasing|increased|"
    r"reduce|reducing|reduced|target|targeting|targeted"
)
_MODAL_ACTION_PATTERN = re.compile(
    r"\b(?:can|could|would|might|may)\s+(?:be\s+)?(?:" + _ALLOCATION_ACTION_VERBS +
    r"|rebalance|rebalanced|replace|replaced|buy|bought|sell|sold)\b",
    re.IGNORECASE,
)
_ALLOCATION_CHANGE_TRIGGER = (
    r"\b(?:position|weight|share|exposure|holding|allocation|"
    r"more|less|additional|greater|smaller|larger)\b"
    r"|\d+(?:\.\d+)?\s*%"  # no trailing \b -- "%" is not a word char, so a
    # \b right after it never matches (the reported boundary bug)
)
_ALLOCATION_ACTION_PATTERN = re.compile(
    r"\b(?:" + _ALLOCATION_ACTION_VERBS + r")\b"
    r".{0,40}?(?:" + _ALLOCATION_CHANGE_TRIGGER + r")",
    re.IGNORECASE,
)
_EXPOSURE_ADVICE_PATTERN = re.compile(
    r"\b(?:more|less|additional|greater|smaller|larger)\s+"
    r"(?:exposure|weight|allocation|position|share)\b"
    r"|better mix"
    r"|benefit(?:s|ed|ting)?\s+from",
    re.IGNORECASE,
)


def _build_ticker_directed_action_pattern(allowed_tickers: set[str]) -> re.Pattern | None:
    tickers = sorted({t for t in allowed_tickers if t})
    if not tickers:
        return None
    ticker_alt = "|".join(re.escape(t) for t in tickers)
    return re.compile(
        r"(?i:\b(?:" + _ALLOCATION_ACTION_VERBS + r")\b)"
        r".{0,15}?\b(?:" + ticker_alt + r")\b"
    )
_MAX_SUMMARY_LENGTH = 500
_MAX_CLAIM_LENGTH = 300

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


def _contains_disallowed_number(text: str, allowed_values_pct: list[float]) -> bool:
    """The instruction "don't propose a revised weight" is prompt-only and
    not otherwise enforced -- this is the actual enforcement. ANY dollar
    figure is disallowed outright (this function is never given a dollar
    amount as input, so one appearing in the response can only be
    invented). A percentage is disallowed unless it's within
    _NUMBER_TOLERANCE_PCT of one of the values it's actually allowed to
    restate (the CALLER decides what's in scope -- e.g. only the specific
    ticker(s) an observation is about, not every weight in the whole cart;
    see _validate_allocation_review) -- close enough to be "the same
    number, differently rounded/phrased," not a proposed alternative."""
    if _DOLLAR_PATTERN.search(text):
        return True
    for match in _PERCENT_PATTERN.finditer(text):
        value = float(match.group(1))
        if not any(abs(value - allowed) <= _NUMBER_TOLERANCE_PCT for allowed in allowed_values_pct):
            return True
    return False


def _mentions_unknown_ticker(text: str, allowed_tickers: set[str]) -> bool:
    """Flags ANY ticker-shaped token (1-5 uppercase letters) that is NOT in
    `allowed_tickers`, except the small _SAFE_ACRONYMS allowlist -- e.g.
    "Buy TSLA" in a summary about NVDA/AMD, or "RDDT would diversify" (a
    real ticker that's simply not in the cart, or an outright hallucinated
    symbol). Independent review, second pass: an earlier version only
    rejected a token if it was ALSO a config.UNIVERSE member -- but
    UNIVERSE is a curated ~90-ticker research list, never a complete
    security master, so a real-but-out-of-universe ticker (or a newly
    listed one, or a hallucinated one) slipped through as if it were an
    innocent acronym. Being strict by default (reject unless explicitly
    allowed or explicitly safe) is the correct default here, not being
    lenient unless proven unsafe.

    Deliberately matches against the ORIGINAL text, not text.upper() --
    uppercasing first would turn every short, ordinary lowercase word
    ("is", "in", "of", "on", "at", "to") into a false ticker-shaped match.
    A genuine ticker mention in financial prose is written in real caps
    ("NVDA", "RDDT"); this only flags tokens that are ALREADY all-caps in
    what the model actually wrote."""
    for match in _TICKER_TOKEN_PATTERN.finditer(text):
        token = match.group(0)
        if token in _SAFE_ACRONYMS:
            continue
        if token not in allowed_tickers:
            return True
    return False


def _validate_allocation_review(
    raw: dict, cart_tickers: list[str], weights_pct: dict[str, float], volatilities: dict[str, float | None] | None = None,
) -> AllocationReview | None:
    """Enforces, in code, what the system prompt only asks for in prose.
    Beyond the original type/severity/ticker-field/number checks, this also:
    (1) scans free text (summary AND claim) for ANY ticker-shaped token not
    in the allowed scope -- not just ones that happen to be config.UNIVERSE
    members (independent review, second pass: a real-but-out-of-universe
    ticker, or an outright hallucinated one like "RDDT", used to slip
    through as if it were an innocent acronym); (2) rejects action/advice
    language outright (buy/sell/replace/allocate/reduce/increase/target/
    rebalance/should/ought/prefer/favor/deserve/consider/"better mix"/
    "benefit from"/"more or less exposure"), regardless of whether a
    number is present; (3) the SUMMARY may not contain a percentage or
    dollar figure AT ALL (independent review, second pass: allowing a
    percentage that merely matched SOME input weight let a real weight
    belonging to one ticker be re-stated as if it applied to a different
    one, e.g. "NVDA should be 40%" using AMD's actual 40% weight) --
    percentages are only ever trustworthy when scoped to a specific
    ticker, which only an observation's own `tickers` field can establish;
    (4) scopes an OBSERVATION's allowed percentages to ONLY the weights/
    volatilities of ITS OWN tickers, never every weight anywhere in the
    cart; (5) treats volatility values as legitimate restatable numbers
    too, not just weights; (6) caps string lengths; (7) drops exact-
    duplicate observations; (8) refuses to show a false "all clear" -- if
    the model proposed observations but every single one failed
    validation, the whole response is rejected rather than displaying just
    the summary as if nothing was flagged."""
    volatilities = volatilities or {}
    cart_set = {t.upper() for t in cart_tickers}

    summary = raw.get("summary")
    if (
        not isinstance(summary, str)
        or len(summary) > _MAX_SUMMARY_LENGTH
        or _PERCENT_PATTERN.search(summary)
        or _DOLLAR_PATTERN.search(summary)
        or _mentions_unknown_ticker(summary, cart_set)
        or _contains_action_language(summary, cart_set)
    ):
        return None

    raw_observations = raw.get("observations", [])
    kept_observations = []
    seen = set()
    for obs in raw_observations:
        if not isinstance(obs, dict):
            continue
        obs_type = obs.get("type")
        severity = obs.get("severity")
        claim = obs.get("claim")
        tickers = obs.get("tickers")
        if obs_type not in _ALLOWED_OBSERVATION_TYPES or severity not in _ALLOWED_SEVERITIES:
            continue
        if not isinstance(claim, str) or not isinstance(tickers, list) or len(claim) > _MAX_CLAIM_LENGTH:
            continue
        if not tickers or not all(isinstance(t, str) and t.upper() in cart_set for t in tickers):
            continue
        obs_tickers = tuple(t.upper() for t in tickers)
        obs_allowed_numbers = [weights_pct[t] for t in obs_tickers if t in weights_pct] + [
            volatilities[t] for t in obs_tickers if volatilities.get(t) is not None
        ]
        if _contains_disallowed_number(claim, obs_allowed_numbers):
            continue
        if _mentions_unknown_ticker(claim, set(obs_tickers)):
            continue
        if _contains_action_language(claim, set(obs_tickers)):
            continue
        dedup_key = (obs_type, severity, obs_tickers, claim)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        kept_observations.append(AllocationObservation(type=obs_type, severity=severity, claim=claim, tickers=obs_tickers))

    if raw_observations and not kept_observations:
        # Every proposed observation failed validation -- showing just the
        # summary here would read as "reviewed, nothing to flag" when the
        # truth is "the model's actual observations were all rejected."
        return None

    return AllocationReview(summary=summary, observations=tuple(kept_observations))


def _contains_action_language(text: str, allowed_tickers: set[str]) -> bool:
    """Rejects buy/sell/replace/rebalance language outright (never used
    descriptively here), advice/recommendation markers (should/consider/
    prefer/deserve/...), modal/passive constructions ("we can increase NVDA",
    "AMD could be reduced"), allocate/increase/reduce/target when they appear
    near an actual change-object (a position/weight/exposure noun, a
    comparative like "more"/"larger", or a percentage), AND allocate/
    increase/reduce/target when one of `allowed_tickers` appears as its
    direct object within a short window ("Increase NVDA.", "Target NVDA at
    60%.") -- so "Sell NVDA and replace it with cash" is still caught with
    no number present, "We can increase NVDA." is caught with no trigger
    noun present, "Increase NVDA." is caught with no ticker-independent
    trigger at all, while "NVDA has increased volatility" and "AMD has
    reduced correlation with NVDA over the sampled period" are not (the
    ticker there is far enough from the verb, inside an unrelated
    prepositional phrase, that the short direct-object window excludes it)."""
    if (
        _UNAMBIGUOUS_ACTION_PATTERN.search(text)
        or _ADVICE_PATTERN.search(text)
        or _MODAL_ACTION_PATTERN.search(text)
        or _ALLOCATION_ACTION_PATTERN.search(text)
        or _EXPOSURE_ADVICE_PATTERN.search(text)
    ):
        return True
    ticker_pattern = _build_ticker_directed_action_pattern(allowed_tickers)
    return bool(ticker_pattern and ticker_pattern.search(text))


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
                "a one-sentence claim, and the ticker(s) it's about (must be one of the tickers listed "
                "below).\n\n"
                "The summary must contain: no ticker symbols; no percentages; no dollar amounts; no "
                "advice or portfolio-change language (nothing like buy/sell/rebalance/replace, "
                "should/consider/prefer/deserve/recommend, or a suggested larger/smaller/increased/"
                "reduced position, weight, or exposure). Describe the split in general terms only.\n\n"
                "Each observation must: reference only the ticker(s) listed in its own `tickers` field; "
                "restate only the supplied weight or volatility for those exact tickers, worded as a "
                "fact about the CURRENT split, never a different number; describe the current "
                "allocation (concentration, basket overlap, volatility character, diversification); "
                "and never propose a change, an alternative weight, a purchase, a sale, or a rebalance. "
                "Every number you write will be checked against the input and discarded if it doesn't "
                "match; every response with advice/portfolio-change language will be discarded outright."
            ),
            messages=[{"role": "user", "content": f"Computed split:\n{detail_block}"}],
        )
        text = next((block.text for block in response.content if block.type == "text"), None)
        if not text:
            _record_run(store, "review_allocation_plan", _REVIEW_ALLOCATION_PROMPT_VERSION, input_hash, start, error="no text block in response")
            return None
        raw = json.loads(text)
        result = _validate_allocation_review(raw, cart_tickers, weights_pct, volatilities)
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
