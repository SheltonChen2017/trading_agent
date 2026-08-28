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
import warnings

import config
from assistant.storage import AssistantStore
from data.financial_primitives import decimal_text

_MODEL = "claude-opus-5"
_REVIEW_ALLOCATION_PROMPT_VERSION = "review_allocation_plan.v4"
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
#   1. Unambiguous transactional verbs (buy/sell/purchase/exit/liquidate/
#      replace/rebalance/rotate/overweight/underweight) -- these are never
#      used descriptively in an allocation-review context, so a bare word
#      match is safe regardless of context.
#   2. Advice/recommendation markers (should, consider, prefer, deserve,
#      recommend, "better to", "makes sense to", ...) -- these only ever
#      appear when the model is giving advice, not describing a fact.
#   3. Modal/passive constructions ("we can increase NVDA", "AMD could be
#      reduced", "we could gradually add NVDA") -- these carry no noun/
#      comparative/percentage/ticker trigger immediately adjacent, so tiers
#      4/5 below never see them; the modal+verb combination alone is
#      inherently advisory. A generous window after the modal word tolerates
#      an intervening adverb or "be".
#   4. Context-sensitive size-change verbs (allocate/increase/reduce/target/
#      add/raise/boost/grow/enlarge/trim/cut/lower/decrease/remove/drop/
#      shift/move) -- these ARE used descriptively ("increased volatility",
#      "reduced diversification", "the volatility target", "NVDA raised its
#      revenue guidance"), so they're only rejected when they appear near an
#      actual allocation-change object (a position/weight/exposure/holding/
#      stake/capital/funds noun, a comparative like "more"/"larger", or a
#      percentage) -- i.e. an actual proposed change, not a description of
#      the current state or of the underlying company's own business.
#   5. One of those same size-change verbs directly governing one of the
#      ALLOWED tickers as its object ("Increase NVDA.", "Target NVDA at
#      60%.", lowercase "Increase nvda.") -- tier 4's trigger nouns don't
#      include ticker symbols, so a bare "Increase NVDA." carries no
#      recognized trigger at all. This is ticker-scoped and uses a SHORT
#      (~20-char) forward window specifically to distinguish "reduce AMD"
#      (AMD is the direct object) from "AMD has reduced correlation with
#      NVDA over the sampled period" (NVDA is many characters away, inside
#      an unrelated prepositional phrase) -- widening this window to tier
#      4's 40 chars would reject that second, legitimate sentence. Ticker
#      matching here is case-INSENSITIVE for ordinary multi-character
#      tickers (LLM output doesn't reliably preserve ticker capitalization --
#      "Increase nvda." must be rejected exactly like "Increase NVDA."), but
#      a ticker of length <=2 (this project's own UNIVERSE has several: V,
#      D, T, C, SO, GS, ...) is ambiguous with ordinary short words and only
#      counts if written in genuine uppercase or with a $ prefix -- see
#      _find_scoped_ticker_mention.
_UNAMBIGUOUS_ACTION_VERBS = (
    r"buy|buying|bought|sell|selling|sold|purchase|purchasing|purchased|"
    r"exit|exiting|exited|liquidate|liquidating|liquidated|"
    r"rebalance|rebalancing|rebalanced|replace|replacing|replaced|"
    r"rotate|rotating|rotated|"
    r"overweight|overweighting|overweighted|underweight|underweighting|underweighted|"
    # Independent adversarial probe, 2026-07-29: these all leaked through
    # every other layer ("You might want to offload some NVDA.", "NVDA looks
    # like a candidate for downsizing."). Unlike the size-change verbs below
    # they need no corroborating object, because none of them has a
    # descriptive reading in a portfolio review -- an "offload"/"divest"/
    # "downsize" of a HOLDING is always a proposed action.
    r"offload|offloading|offloaded|divest|divesting|divested|"
    r"downsize|downsizing|downsized|upsize|upsizing|upsized"
)
_UNAMBIGUOUS_ACTION_PATTERN = re.compile(r"\b(" + _UNAMBIGUOUS_ACTION_VERBS + r")\b", re.IGNORECASE)
_ADVICE_PATTERN = re.compile(
    r"\b(should|ought\s+to|consider(?:ing)?|prefer(?:red|s|ring|able)?|"
    r"favor(?:ed|s|ing)?|deserv(?:e|es|ed|ing)|recommend(?:ed|s|ing)?|"
    r"better\s+to|makes?\s+sense\s+to|would\s+be\s+better|"
    # Independent adversarial probe, 2026-07-29: advisability adjectives and
    # "warrants" carried the recommendation with no action verb the other
    # layers recognized ("NVDA warrants a bigger slice of the portfolio.",
    # "A tilt toward AMD is advisable.", "Scaling into AMD is sensible.").
    # None of these has a neutral descriptive use in a concentration/
    # volatility observation.
    # "sensible" is deliberately NOT here: the phrasing that motivated it
    # ("Scaling into AMD is sensible.") is already caught by the
    # size-change/ticker-directed layer, so it added no coverage while
    # over-blocking descriptive text like "a sensible-sounding plan".
    r"warrant(?:s|ed|ing)?|prudent|advisable|inadvisable|"
    r"worth\s+(?:considering|evaluating|exploring|reviewing)|"
    r"could\s+improve\s+the\s+portfolio\s+by)\b",
    re.IGNORECASE,
)
# "Take some profits in NVDA." -- a two-word action phrase no single verb in
# the lists above covers (independent adversarial probe, 2026-07-29).
_PROFIT_TAKING_PATTERN = re.compile(
    r"\btak(?:e|es|en|ing)\b[^.]{0,20}?\bprofits?\b", re.IGNORECASE
)
_SIZE_CHANGE_VERBS = (
    r"allocate|allocating|allocated|increase|increasing|increased|"
    r"reduce|reducing|reduced|target|targeting|targeted|"
    r"add|adding|added|raise|raising|raised|boost|boosting|boosted|"
    r"grow|growing|grew|grown|enlarge|enlarging|enlarged|"
    r"trim|trimming|trimmed|cut|cutting|lower|lowering|lowered|"
    r"decrease|decreasing|decreased|remove|removing|removed|"
    r"drop|dropping|dropped|shift|shifting|shifted|move|moving|moved|"
    # Independent adversarial probe, 2026-07-29: "Dial back NVDA.",
    # "scale back NVDA", "A tilt toward AMD". Safe to widen here (rather
    # than in the unambiguous list) because every consumer of this group
    # additionally requires a modal, a change-object noun, or the ticker
    # itself as the verb's direct object -- so a descriptive "NVDA has
    # scaled its operations" still passes.
    r"scale|scaling|scaled|tilt|tilting|tilted|"
    r"dial|dialing|dialled|dialed|pare|paring|pared"
)
_MODAL_ACTION_PATTERN = re.compile(
    r"\b(?:can|could|would|might|may)\b.{0,40}?\b(?:" + _SIZE_CHANGE_VERBS +
    r"|" + _UNAMBIGUOUS_ACTION_VERBS + r")\b",
    re.IGNORECASE,
)
_ALLOCATION_CHANGE_TRIGGER = (
    r"\b(?:positions?|holdings?|weight|allocation|exposure|shares?|stake|"
    r"capital|funds|amount invested|portfolio percentage|"
    r"more|less|additional|greater|smaller|larger)\b"
    r"|\d+(?:\.\d+)?\s*%"  # no trailing \b -- "%" is not a word char, so a
    # \b right after it never matches (the reported boundary bug)
)
_ALLOCATION_ACTION_PATTERN = re.compile(
    r"\b(?:" + _SIZE_CHANGE_VERBS + r")\b"
    r".{0,40}?(?:" + _ALLOCATION_CHANGE_TRIGGER + r")",
    re.IGNORECASE,
)
_EXPOSURE_ADVICE_PATTERN = re.compile(
    r"\b(?:more|less|additional|greater|smaller|larger)\s+"
    r"(?:exposure|weight|allocation|position|share|stake)\b(?!\s+than\b)"
    r"|better mix"
    r"|benefit(?:s|ed|ting)?\s+from",
    re.IGNORECASE,
)
_AMBIGUOUS_TICKER_MAX_LEN = 2
_TICKER_TOKEN_SCAN_PATTERN = re.compile(r"\$?[A-Za-z]{1,10}\b")


def _find_scoped_ticker_mention(text: str, allowed_tickers: set[str]) -> bool:
    """True if `text` mentions one of `allowed_tickers` as a complete
    token, matched case-insensitively for ordinary tickers. A ticker of
    length <= _AMBIGUOUS_TICKER_MAX_LEN (e.g. "V", "T", "C", "SO", "GS" --
    all real entries in this project's own UNIVERSE) collides with common
    short English words, so it only counts when written in genuine
    uppercase or with a leading "$" -- lowercase/mixed-case "so" or "it"
    must never be treated as a ticker mention."""
    for match in _TICKER_TOKEN_SCAN_PATTERN.finditer(text):
        raw = match.group(0)
        has_dollar = raw.startswith("$")
        token = raw[1:] if has_dollar else raw
        upper = token.upper()
        if upper not in allowed_tickers:
            continue
        if len(upper) <= _AMBIGUOUS_TICKER_MAX_LEN and not has_dollar and token != upper:
            continue
        return True
    return False


def _ticker_directed_action_detected(text: str, allowed_tickers: set[str]) -> bool:
    """True if a size-change verb directly governs one of `allowed_tickers`
    within a short forward window ("Increase NVDA.", "Reduce amd.", "Raise
    Nvda."). The short window (~20 chars, enough for a short filler phrase
    like "the ", "our ", "more to ") is what distinguishes a direct object
    from an unrelated later mention, e.g. "AMD has reduced correlation with
    NVDA over the sampled period" -- NVDA there is well outside this window
    and inside an unrelated prepositional phrase."""
    if not allowed_tickers:
        return False
    for match in re.finditer(r"\b(?:" + _SIZE_CHANGE_VERBS + r")\b", text, re.IGNORECASE):
        window = text[match.end():match.end() + 20]
        if _find_scoped_ticker_mention(window, allowed_tickers):
            return True
    return False
# Owner decision 2026-08-12: the former _MAX_SUMMARY_LENGTH / _MAX_CLAIM_LENGTH
# caps are gone. See _validate_allocation_review for why length was never a
# safety property here.

# Why a review was not shown, in the user's words rather than the code's. The
# UI renders exactly one of these instead of leaving the screen blank, because
# "Claude reviewed this and had nothing to say", "the call failed", and "you
# never asked" are three different facts that used to look identical.
REVIEW_REJECTED_SUMMARY = (
    "Claude's opening summary failed its own checks -- it may not contain a "
    "percentage, a dollar figure, a ticker outside your cart, or advice "
    "language."
)
REVIEW_REJECTED_ALL_OBSERVATIONS = (
    "Every individual point Claude made failed a check -- most often a number "
    "that does not match your actual split, or a number attributed to the "
    "wrong ticker. The summary alone was withheld because on its own it would "
    "have read as 'reviewed, nothing to flag'."
)
REVIEW_REJECTED_UNPARSEABLE = "Claude's response could not be read as a valid review."
REVIEW_REJECTED_NO_TEXT = "Claude's response arrived empty."
REVIEW_REJECTED_CALL_FAILED = "The call to Claude did not complete ({error_type})."
REVIEW_REJECTED_UNCONFIGURED = "No Anthropic credential is configured."
REVIEW_REJECTED_NO_INPUT = "No allocation split was available to review."

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


@dataclasses.dataclass(frozen=True)
class AllocationReviewOutcome:
    """A review, or the reason there isn't one -- never just absence.

    `review` is None exactly when `rejection_reason` is set. Both being None
    would mean "nothing happened and we don't know why", which is the state
    this type exists to make unrepresentable.
    """

    review: AllocationReview | None
    rejection_reason: str | None
    input_hash: str

    def __post_init__(self) -> None:
        if (self.review is None) == (self.rejection_reason is None):
            raise ValueError(
                "exactly one of review and rejection_reason must be provided"
            )
        if not isinstance(self.input_hash, str) or not self.input_hash:
            raise ValueError("input_hash must be a non-empty string")


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


def _contains_misattributed_multi_ticker_number(
    text: str,
    tickers: set[str],
    weights_pct: dict[str, float],
    volatilities: dict[str, float | None],
) -> bool:
    """Reject percentages attached to the wrong ticker in a multi-name claim.

    A union of all named tickers' legitimate values proves that a number is
    real, but not that it is attributed to the right security.  Associate
    each percentage with the nearest explicit ticker token and fail closed on
    ties/ambiguity.  The ordinary generated form ("NVDA is 60% while AMD is
    40%") remains supported; constructions whose attribution cannot be
    established locally should be split into separate observations.
    """
    ticker_matches = [
        match
        for match in _TICKER_TOKEN_PATTERN.finditer(text)
        if match.group(0) in tickers
    ]
    if len({match.group(0) for match in ticker_matches}) < 2:
        return False
    for number_match in _PERCENT_PATTERN.finditer(text):
        distances: dict[str, int] = {}
        for ticker_match in ticker_matches:
            if ticker_match.end() <= number_match.start():
                distance = number_match.start() - ticker_match.end()
            elif number_match.end() <= ticker_match.start():
                distance = ticker_match.start() - number_match.end()
            else:
                distance = 0
            ticker = ticker_match.group(0)
            distances[ticker] = min(distances.get(ticker, distance), distance)
        nearest_distance = min(distances.values())
        nearest = [
            ticker
            for ticker, distance in distances.items()
            if distance == nearest_distance
        ]
        if len(nearest) != 1:
            return True
        ticker = nearest[0]
        allowed = [weights_pct[ticker]] if ticker in weights_pct else []
        volatility = volatilities.get(ticker)
        if volatility is not None:
            allowed.append(volatility)
        value = float(number_match.group(1))
        if not any(
            abs(value - candidate) <= _NUMBER_TOLERANCE_PCT
            for candidate in allowed
        ):
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
    raw: dict,
    cart_tickers: list[str],
    weights_pct: dict[str, float],
    volatilities: dict[str, float | None] | None = None,
    *,
    rejection_out: list[str] | None = None,
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
    cart -- and for a MULTI-ticker observation, further scopes to only
    the ticker(s) the claim text itself names when it names any, so a
    claim entirely about ticker A can't cite ticker B's real number just
    because B is also in the observation's ticker list (independent
    review, 2026-07-31); (5) treats volatility values as legitimate restatable numbers
    too, not just weights; (6) applies every content check to the complete
    model text, whose upstream size is bounded by max_tokens; (7) drops exact-
    duplicate observations; (8) refuses to show a false "all clear" -- if
    the model proposed observations but every single one failed
    validation, the whole response is rejected rather than displaying just
    the summary as if nothing was flagged."""
    volatilities = volatilities or {}
    cart_set = {t.upper() for t in cart_tickers}

    summary = raw.get("summary")
    # Length is deliberately NOT a rejection reason (owner decision,
    # 2026-08-12). It never protected anything: the checks that do the real
    # work -- percentages, dollar figures, unknown tickers, advice language,
    # per-ticker number attribution -- read the whole string regardless of how
    # long it is, so a longer summary gets more scrutiny, not less. The old
    # 500-character cap was an undocumented, untested magic number, and it
    # discarded two complete real reviews on 2026-08-12 at 554 and 670
    # characters whose every observation passed every content check. The real
    # bound is max_tokens on the call itself. The UI renders whatever length
    # arrives.
    if (
        not isinstance(summary, str)
        or _PERCENT_PATTERN.search(summary)
        or _DOLLAR_PATTERN.search(summary)
        or _mentions_unknown_ticker(summary, cart_set)
        or _contains_action_language(summary, cart_set)
    ):
        # `rejection_out` is an optional out-collector rather than a changed
        # return type on purpose: 28 existing test call sites depend on this
        # function returning AllocationReview | None, and the rule that decides
        # a rejection must stay in exactly one place. A caller that wants the
        # reason passes a list; every other caller is unaffected.
        if rejection_out is not None:
            rejection_out.append(REVIEW_REJECTED_SUMMARY)
        return None

    raw_observations = raw.get("observations", [])
    # Counter-review AP9CR-001: AP9R-003 guarded the JSON *root* shape, but a
    # well-typed root carrying a malformed field walked straight past it --
    # `observations: null` or a number raised TypeError at the loop below,
    # the caller's broad except caught it, and the user was told "The call to
    # Claude did not complete (TypeError)". Same dishonesty, one level down:
    # the call completed fine; the response shape was wrong. An absent key
    # still defaults to [] (a summary-only review is valid).
    if not isinstance(raw_observations, list):
        if rejection_out is not None:
            rejection_out.append(REVIEW_REJECTED_UNPARSEABLE)
        return None
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
        # Same reasoning as the summary above: a long claim is dropped by the
        # content checks if it earns it, not for its length. Dropping on length
        # here is worse than on the summary, because a single over-long claim
        # silently removes one observation, and if it was the only one the
        # whole review is rejected by the all-observations-failed rule below.
        if not isinstance(claim, str) or not isinstance(tickers, list):
            continue
        if not tickers or not all(isinstance(t, str) and t.upper() in cart_set for t in tickers):
            continue
        obs_tickers = tuple(t.upper() for t in tickers)
        # Independent review, 2026-07-31 (P2 #8): for a multi-ticker
        # observation, this used to union every ticker's own numbers into
        # one allowed set for the WHOLE claim -- so a claim entirely about
        # ticker A could cite ticker B's real weight/volatility just
        # because B was also in this observation's ticker list, with no
        # check that the claim actually attributes the number to the
        # RIGHT ticker. Scope the allowed numbers to only the ticker(s)
        # the claim text itself names (the same ticker-token pattern
        # _mentions_unknown_ticker uses below); fall back to the full
        # observation ticker set only when the claim names none of them
        # explicitly, so a legitimate ticker-less claim isn't newly
        # over-rejected.
        claim_named_tickers = {
            match.group(0)
            for match in _TICKER_TOKEN_PATTERN.finditer(claim)
            if match.group(0) in obs_tickers
        }
        scoped_tickers = claim_named_tickers or set(obs_tickers)
        obs_allowed_numbers = [weights_pct[t] for t in scoped_tickers if t in weights_pct] + [
            volatilities[t] for t in scoped_tickers if volatilities.get(t) is not None
        ]
        if _contains_disallowed_number(claim, obs_allowed_numbers):
            continue
        if _contains_misattributed_multi_ticker_number(
            claim,
            set(obs_tickers),
            weights_pct,
            volatilities,
        ):
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
        if rejection_out is not None:
            rejection_out.append(REVIEW_REJECTED_ALL_OBSERVATIONS)
        return None

    return AllocationReview(summary=summary, observations=tuple(kept_observations))


def _contains_action_language(text: str, allowed_tickers: set[str]) -> bool:
    """Rejects buy/sell/purchase/exit/liquidate/replace/rebalance/rotate/
    over-or-underweight language outright (never used descriptively here),
    advice/recommendation markers (should/consider/prefer/deserve/"better
    to"/"makes sense to"/...), modal/passive constructions ("we can increase
    NVDA", "AMD could be reduced", "we could gradually add NVDA"), a size-
    change verb (allocate/increase/reduce/target/add/raise/boost/trim/cut/
    lower/...) when it appears near an actual change-object (a position/
    weight/exposure/holding/stake/capital/funds noun, a comparative like
    "more"/"larger", or a percentage), AND a size-change verb when one of
    `allowed_tickers` appears as its direct object within a short window,
    matched case-insensitively ("Increase NVDA.", "Increase nvda.", "Target
    NVDA at 60%.") -- so "Sell NVDA and replace it with cash" is still
    caught with no number present, "We can increase NVDA." is caught with no
    trigger noun present, "Raise NVDA." / "Trim AMD." / "Increase nvda." are
    caught with no ticker-independent trigger at all, while "NVDA has
    increased volatility", "AMD has reduced correlation with NVDA over the
    sampled period", and "NVDA raised its revenue guidance" are not (the
    ticker/verb ordering or distance there means the ticker is never the
    verb's direct object within the short window)."""
    return bool(
        _UNAMBIGUOUS_ACTION_PATTERN.search(text)
        or _ADVICE_PATTERN.search(text)
        or _MODAL_ACTION_PATTERN.search(text)
        or _ALLOCATION_ACTION_PATTERN.search(text)
        or _EXPOSURE_ADVICE_PATTERN.search(text)
        or _PROFIT_TAKING_PATTERN.search(text)
        or _ticker_directed_action_detected(text, allowed_tickers)
    )


# Dates are extracted and compared as ATOMIC tokens, before plain numbers, so
# a source date like "2026-07-28" does not quietly license unrelated claims
# using 2026, 7, or 28 as free-standing figures.
_DATE_TOKEN_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
# Optional leading sign, but only where a minus is genuinely a sign rather than
# a hyphen inside a token: the lookbehind stops "5-10" from yielding "-10".
# The `\.\d+` alternative matches a leading-dot decimal (".05"); without it a
# source written that way contributed NO number at all, so a summary correctly
# restating it as "0.05" was flagged as invented -- a false positive found by
# this module's own tests, not by the review.
_NUMERIC_CLAIM_PATTERN = re.compile(r"(?<![\w-])-?(?:\d+(?:[.,]\d+)*|\.\d+)")


def _canonical_number(token: str) -> str | None:
    """
    A value-preserving canonical form for a numeric token, or None when it
    cannot be parsed safely.

    Commas are dropped as thousands separators; the decimal point is NOT,
    because deleting it changes the value. The previous implementation did
    `.replace(".", "").lstrip("0")`, which made 3.05 equal to 305 and 0.05
    equal to 5 -- so a model could turn a real figure into a fabricated one and
    still pass the source check -- while ALSO flagging 3.050 against a source
    3.05 as invented (independent review, 2026-07-29; the false-positive half
    was found while reproducing the false-negative half).

    Decimal, not float, so 0.1 + 0.2 style representation error can never make
    two genuinely different figures compare equal. Trailing zeros are
    normalized (3.050 == 3.05) and leading zeros are harmless (0.05 == .05),
    both of which are pure formatting. Sign is significant: -3.05 does not
    match 3.05.
    """
    cleaned = token.replace(",", "")
    try:
        return decimal_text(cleaned)
    except ValueError:
        return None


def _unsupported_numbers(text: str, source_text: str) -> list[str]:
    """
    Numbers in `text` that do not appear in `source_text`.

    Deterministic and therefore trustworthy, unlike general fact-checking:
    every figure in a grounded summary must have come from the source data.
    This is what catches invented revenue/earnings figures, percentages, and
    dates -- the fabrication category with the most potential to mislead a
    financial decision.

    Explicit rules, so nothing is inferred by accident:

    * Thousands separators are formatting: "30,000" matches "30000".
    * Decimal value is preserved: "3.05" does NOT match "305".
    * Sign is significant: "-3.05" does NOT match "3.05".
    * Percentages are compared as the NUMERAL WRITTEN. "5%" does not match a
      source "0.05" -- no unit conversion is attempted, because guessing that
      a bare 0.05 meant 5% is exactly the kind of inference this guard exists
      to avoid. A summary must restate the figure as the source wrote it.
    * Whole dates are atomic: a source "2026-07-28" does not make 2026, 7 or 28
      available as free-standing numbers.
    * A token that cannot be parsed as a number is reported as unsupported
      (fail closed), never silently ignored.
    """
    text_dates = _DATE_TOKEN_PATTERN.findall(text)
    source_dates = set(_DATE_TOKEN_PATTERN.findall(source_text))
    unsupported = [date for date in text_dates if date not in source_dates]

    # Strip dates before scanning for plain numbers so their components are
    # never treated as independently grounded figures.
    text_without_dates = _DATE_TOKEN_PATTERN.sub(" ", text)
    source_without_dates = _DATE_TOKEN_PATTERN.sub(" ", source_text)

    source_numbers = set()
    for token in _NUMERIC_CLAIM_PATTERN.findall(source_without_dates):
        canonical = _canonical_number(token)
        if canonical is not None:
            source_numbers.add(canonical)

    for token in _NUMERIC_CLAIM_PATTERN.findall(text_without_dates):
        canonical = _canonical_number(token)
        if canonical is None or canonical not in source_numbers:
            unsupported.append(token)
    return unsupported


def _reject_unsafe_prose(
    text: str, allowed_tickers: set[str], *, source_text: str
) -> str | None:
    """
    Deterministic guard for the free-text (non-allocation) AI surfaces:
    recommended-stock curation, similar-ticker reasons, news summaries.

    Returns a short reason string when `text` must NOT be shown, or None when
    it passes. These surfaces were previously PROMPT-guarded only -- the system
    prompt asks the model not to give recommendations or invent facts, but
    nothing checked the output, unlike review_allocation_plan() which runs the
    full denylist (GPT review, 2026-07-29).

    Three deterministic checks, in increasing order of what they can promise:

    1. The action/advice-language denylist -- the SAME one the allocation path
       uses, not a weaker second rulebook.
    2. The unknown-ticker check: any ticker outside the verified set is
       ungrounded by construction, since these callers only pass
       already-verified tickers.
    3. Every NUMBER in the output must appear in `source_text`. See
       _unsupported_numbers().

    `source_text` is REQUIRED and keyword-only, deliberately. It used to
    default to None, which silently skipped check 3 -- and two of the three
    callers (similar-ticker reasons, recommended-ticker curation) omitted it,
    so the system prompt's promise that "every number you write will be checked
    against the input and discarded if it doesn't match" was simply false on
    those surfaces (independent review, 2026-07-30). Making it required means a
    new prose surface that forgets grounding fails with a TypeError at import
    of the first call rather than shipping an unchecked number to the user. A
    caller with genuinely no source passes "" -- which grounds nothing and so
    rejects every number, the correct fail-closed reading of "no source".

    WHAT THIS DOES NOT DO -- deliberately named `_reject_unsafe_prose`, not
    "ungrounded", because it cannot verify factual grounding in general. A
    fabricated NON-numeric claim about an allowed ticker ("NVDA announced an
    acquisition") is not deterministically detectable and will pass. There is
    no regex for "is this true". The honest mitigations are the ones this
    codebase already prefers: keep the model's role synthesis-only over
    supplied source text, pass `source_text` so at least invented figures are
    caught, and display deterministic source-derived content (the raw
    headlines, the verified candidate rows) as the primary surface with model
    prose as a clearly secondary addition -- never as the only thing shown.
    An earlier version of this docstring claimed to guard "ungrounded prose"
    while checking neither grounding nor numbers, which overstated it.

    Fails CLOSED: callers all treat None as "show the deterministic content
    instead", so suppressing a borderline-but-harmless sentence costs a
    nicety, while showing a borderline-but-harmful one is the failure this
    module exists to prevent. See memory: project_ai_advice_guardrail -- the
    denylist is a regex surface and has leaked twice before.
    """
    if _contains_action_language(text, allowed_tickers):
        return "contains trade-action/advice language"
    if _mentions_unknown_ticker(text, allowed_tickers):
        return "mentions a ticker outside the verified candidate set"
    unsupported = _unsupported_numbers(text, source_text)
    if unsupported:
        # Fixed label only -- never interpolate the unsupported tokens.
        # Those tokens are extracted from the rejected model text; putting
        # them in a UI- or log-facing reason would partially surface the
        # fabrication this check exists to suppress (CNEWS-001, 2026-08-07).
        return "cites number(s) absent from the source data"
    return None


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


def allocation_review_input_hash(
    cart_tickers: list[str],
    weights_pct: dict[str, float],
    volatilities: dict[str, float | None],
    baskets_by_ticker: dict[str, list[str]],
) -> str:
    """Stable identity for the exact allocation inputs an AI review covers.

    The Buying page compares this identity on every rerun so commentary
    validated against an old split can never appear beneath a changed one.
    """
    return _input_hash(cart_tickers, weights_pct, volatilities, baskets_by_ticker)


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
    this swallows its own exceptions rather than propagating them -- but it
    does not swallow them SILENTLY. A bare `except Exception: pass` here
    meant the audit log could be broken indefinitely while every AI call
    looked successful, which defeats the point of having an audit log at
    all. The exception is still not propagated; it is made audible."""
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
    except Exception as exc:
        # Deliberately still non-fatal (see docstring), but never silent.
        warnings.warn(
            f"AI audit log write failed for {function_name!r}; this call is "
            f"unaudited: {type(exc).__name__}: {exc}",
            RuntimeWarning,
            stacklevel=2,
        )


def review_allocation_plan(
    cart_tickers: list[str],
    weights_pct: dict[str, float],
    volatilities: dict[str, float | None],
    baskets_by_ticker: dict[str, list[str]],
    store: AssistantStore | None = None,
) -> AllocationReview | None:
    """Backwards-compatible wrapper: the review, or None. Callers that need to
    TELL THE USER why nothing appeared should use review_allocation_outcome()
    instead -- a blank screen is not an acceptable way to report a failure."""
    return review_allocation_outcome(
        cart_tickers, weights_pct, volatilities, baskets_by_ticker, store=store
    ).review


def review_allocation_outcome(
    cart_tickers: list[str],
    weights_pct: dict[str, float],
    volatilities: dict[str, float | None],
    baskets_by_ticker: dict[str, list[str]],
    store: AssistantStore | None = None,
) -> AllocationReviewOutcome:
    """Structured advisory commentary on the ALREADY-COMPUTED weights_pct --
    concentration, basket overlap, volatility character, diversification.

    The "don't propose a revised weight/dollar amount" instruction is NOT
    prompt-only: every observation's type/severity is schema-constrained,
    every ticker mentioned is checked against cart_tickers, and the summary
    plus every observation's claim is scanned for a number that isn't one
    of the actual input weights (assistant.ai_advisor._validate_allocation_review) --
    a claim or summary that fails this is dropped/rejected rather than
    trusted and displayed. Never raises: every failure path returns an outcome
    whose `review` is None and whose `rejection_reason` says, in plain words,
    what happened -- unconfigured, the call failed, the response did not parse,
    the summary failed validation, or every observation did. The caller is
    expected to SHOW that reason; rendering nothing at all is what made a
    real 2026-08-12 rejection indistinguishable from a feature that was
    switched off."""
    input_hash = allocation_review_input_hash(
        cart_tickers, weights_pct, volatilities, baskets_by_ticker
    )
    if not cart_tickers:
        return AllocationReviewOutcome(None, REVIEW_REJECTED_NO_INPUT, input_hash)
    if not is_ai_advisor_configured():
        return AllocationReviewOutcome(None, REVIEW_REJECTED_UNCONFIGURED, input_hash)

    import anthropic

    client = anthropic.Anthropic()
    lines = []
    for ticker in cart_tickers:
        vol = volatilities.get(ticker)
        vol_str = f"{vol:.2f}%" if vol is not None else "unknown"
        baskets = ", ".join(baskets_by_ticker.get(ticker, [])) or "none"
        lines.append(f"- {ticker}: weight={weights_pct.get(ticker, 0.0):.1f}%, volatility={vol_str}, baskets=[{baskets}]")
    detail_block = "\n".join(lines)
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
            return AllocationReviewOutcome(None, REVIEW_REJECTED_NO_TEXT, input_hash)
        try:
            raw = json.loads(text)
        except ValueError:
            _record_run(store, "review_allocation_plan", _REVIEW_ALLOCATION_PROMPT_VERSION, input_hash, start, error="response was not valid JSON")
            return AllocationReviewOutcome(None, REVIEW_REJECTED_UNPARSEABLE, input_hash)
        if not isinstance(raw, dict):
            _record_run(
                store,
                "review_allocation_plan",
                _REVIEW_ALLOCATION_PROMPT_VERSION,
                input_hash,
                start,
                response=raw,
                error="response JSON root was not an object",
            )
            return AllocationReviewOutcome(None, REVIEW_REJECTED_UNPARSEABLE, input_hash)
        rejections: list[str] = []
        result = _validate_allocation_review(
            raw, cart_tickers, weights_pct, volatilities, rejection_out=rejections
        )
        _record_run(
            store, "review_allocation_plan", _REVIEW_ALLOCATION_PROMPT_VERSION, input_hash, start,
            response=raw, error=None if result is not None else "failed post-hoc validation",
        )
        if result is not None:
            return AllocationReviewOutcome(result, None, input_hash)
        # A None result always has a reason; fall back rather than hand the UI
        # an empty explanation, which would reintroduce the blank screen.
        return AllocationReviewOutcome(
            None,
            rejections[0] if rejections else REVIEW_REJECTED_UNPARSEABLE,
            input_hash,
        )
    except Exception as exc:
        _record_run(store, "review_allocation_plan", _REVIEW_ALLOCATION_PROMPT_VERSION, input_hash, start, error=str(exc))
        # The exception TYPE only. Its message can carry request context, and
        # this string is rendered straight into the page.
        return AllocationReviewOutcome(
            None,
            REVIEW_REJECTED_CALL_FAILED.format(error_type=type(exc).__name__),
            input_hash,
        )


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
    # Built once and used BOTH as the model's input and as the grounding source
    # for its output, so the two can never drift apart.
    cart_prompt = f"Tickers already in the cart: {', '.join(cart_tickers)}"
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
            messages=[{"role": "user", "content": cart_prompt}],
        )
        text = next((block.text for block in response.content if block.type == "text"), None)
        if not text:
            _record_run(store, "suggest_similar_tickers", _SUGGEST_SIMILAR_PROMPT_VERSION, input_hash, start, error="no text block in response")
            return None
        suggestions = json.loads(text)["suggestions"][:max_suggestions]
        # Each suggestion's `reason` is free-form model prose and was
        # previously unchecked, same gap as curate_recommended_tickers. A
        # suggestion whose reason fails the guard is dropped ENTIRELY rather
        # than shown with the reason stripped -- a bare ticker with no stated
        # rationale invites the user to assume one, which is worse than
        # showing nothing. The suggested ticker itself is added to the allowed
        # set because it is legitimately the subject of its own reason (it is
        # separately verified against real market data downstream).
        cart_upper = {str(t).upper() for t in cart_tickers}
        kept = []
        for suggestion in suggestions:
            allowed = cart_upper | {str(suggestion.get("ticker", "")).upper()}
            # source_text was previously omitted here, so _unsupported_numbers()
            # never ran and a reason could state any figure it liked ("AMD grew
            # revenue 45% last quarter") while the system prompt promised every
            # number was checked (independent review, 2026-07-30). The cart
            # prompt contains no figures, so in practice this rejects ANY number
            # in a similarity rationale -- which is correct: nothing in this
            # call's input could support one.
            rejection = _reject_unsafe_prose(
                str(suggestion.get("reason", "")), allowed, source_text=cart_prompt,
            )
            if rejection is None:
                kept.append(suggestion)
        _record_run(
            store, "suggest_similar_tickers", _SUGGEST_SIMILAR_PROMPT_VERSION, input_hash, start,
            response=kept,
            error=None if len(kept) == len(suggestions)
            else f"output guard suppressed {len(suggestions) - len(kept)} of {len(suggestions)} suggestion(s)",
        )
        return kept
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
    # As in suggest_similar_tickers: one string, used as both the prompt and the
    # grounding source, so the guard checks against exactly what the model saw.
    candidate_block = "Candidates:\n" + "\n".join(lines)
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
            messages=[{"role": "user", "content": candidate_block}],
        )
        text = next((block.text for block in response.content if block.type == "text"), None)
        if text:
            rejection = _reject_unsafe_prose(
                text, {str(c.ticker).upper() for c in candidates},
                source_text=candidate_block,
            )
            if rejection:
                _record_run(
                    store, "curate_recommended_tickers", _CURATE_RECOMMENDED_PROMPT_VERSION,
                    input_hash, start, error=f"suppressed by output guard: {rejection}",
                )
                return None
        _record_run(store, "curate_recommended_tickers", _CURATE_RECOMMENDED_PROMPT_VERSION, input_hash, start, response=text, error=None if text else "no text block in response")
        return text
    except Exception as exc:
        _record_run(store, "curate_recommended_tickers", _CURATE_RECOMMENDED_PROMPT_VERSION, input_hash, start, error=str(exc))
        return None
