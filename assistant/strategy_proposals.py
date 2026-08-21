"""
Proposal generator for the one validated non-risk-reduction idea in this
project: continuous inverse-volatility-targeted rotation between SOXX
(stable) and SOXL (leveraged), using a WIDE (15%) rebalance band. See
assistant/research_findings.json for the underlying evidence:

  - "Wide rebalance band vs. tight/continuous vol-targeting" (CONFIRMED):
    ~89% less tax/turnover for essentially the same performance as
    continuous vol-targeting.
  - "SOXX/SOXL trend+volatility regime rotation -- drawdown" (CONFIRMED):
    the underlying rotation mechanism reduces max drawdown vs 50/50
    buy-and-hold.
  - "SOXX/SOXL trend+volatility regime rotation -- return" (REJECTED),
    and memory: project_vol_target_rotation -- NONE of the 5 pairs
    tested (including SOXX/SOXL) beat buy-and-hold on CAGR. This is a
    RISK-SHAPE trade (less drawdown, less tax drag), not an alpha claim.
    Never represent a proposal from this module as "beats buy-and-hold."

PRODUCTION_PARAMS was chosen by grid-searching Calmar ratio (CAGR /
|max drawdown|) on the FULL available SOXX/SOXL history (not a held-out
confirmation split -- there's no more history left to hold out for a
live-forward config). That makes these SPECIFIC numbers in-sample /
unconfirmed even though the underlying wide-band MECHANISM is confirmed
research. Every proposal this module generates is tagged
evidence_status="promising_unconfirmed_strategy", never "confirmed", for
exactly this reason -- see the disclosure in `uncertainties` on each
proposal.

Deliberately scoped to REBALANCING an existing SOXX+SOXL allocation
only. It never proposes opening a first position in either ticker -- if
the account doesn't already hold BOTH, this generator returns nothing.
TradingPolicy.allow_new_positions stays False project-wide; nothing here
needs or requests an exception to it. Every proposal still goes through
the same TradeProposal -> "APPROVE <id>" -> execution_gate pipeline as
risk-reduction proposals; policy limits and human confirmation are
untouched.

Single-leg per call, by design: proposes at most ONE trade (whichever
leg needs to move to close the gap to target) rather than bundling a
simultaneous two-leg rebalance. A sell's proceeds aren't reflected in
the account snapshot until settlement, so a same-pass paired buy could
be validated against stale cash. Re-running the CLI's `propose` command
after an approval naturally converges toward the target over successive
cycles -- the same pattern the risk-reduction generator already relies
on.

Also a simplification worth naming: the original backtest only checks
for a rebalance every `rebalance_check_days` (21) SIMULATED trading
days from an arbitrary start. There's no equivalent fixed counter here
-- each time a caller runs this (e.g. each `propose` invocation), that
IS the check. Running it far more often than every ~21 trading days
will trigger rebalances the backtest never actually modeled at that
frequency.
"""
from __future__ import annotations

import dataclasses
import hashlib
import math
from datetime import datetime, timedelta, timezone

import pandas as pd

from data.market_data import fetch_historical
from signals.regime import compute_trailing_market_volatility
from strategies.vol_target_rotation import compute_target_leveraged_weight
from market_analytics import classify_trend
from assistant.context_builder import KNOWN_FINDINGS
from assistant.policy import TradingPolicy, compute_policy_fingerprint
from assistant.portfolio_analytics import preview_trade_impact
from assistant.proposals import (
    TradeProposal,
    exact_position_shares,
    sellable_whole_shares,
)
from assistant.schemas import DecisionPacket, EvidenceStatus
from assistant.storage import AssistantStore
from risk.execution_gate import TradeIntent

STABLE_TICKER = "SOXX"
LEVERAGED_TICKER = "SOXL"
LOOKBACK_DAYS_FOR_SIGNAL = 300  # comfortably covers trend_lookback_days=200 plus warmup

# The two findings this module's mechanism (wide-band rotation) actually
# relies on, mapped to the SPECIFIC status this strategy depends on --
# see assistant/research_findings.json. Checked live at proposal-
# generation time (GPT review, 2026-07-29: "any proposal-generation
# decision that relies on one of these findings must check current
# authority explicitly") rather than trusted from the module docstring's
# prose alone, which can go stale silently.
#
# Requiring an EXPLICIT expected status (not just "present and
# authoritative") matters (GPT review, 2026-07-31, independently
# reproduced): SignalEvidence.production_authoritative intentionally
# returns True for REJECTED/EXPLORATORY/UNAVAILABLE findings, since those
# statuses make no positive claim worth distrusting -- correct for
# DISPLAY, but wrong for a STRATEGY DEPENDENCY. Setting both of these
# findings' status to "rejected" in the registry used to leave the old
# missing/non-authoritative check reporting (missing=[],
# non_authoritative=[]) -- indistinguishable from "every dependency is
# fine" -- because it never actually checked the value of `status`.
_RELIED_UPON_FINDINGS: dict[str, EvidenceStatus] = {
    "SOXX/SOXL trend+volatility regime rotation — drawdown": EvidenceStatus.CONFIRMED,
    "Wide rebalance band vs. tight/continuous vol-targeting": EvidenceStatus.CONFIRMED,
}
_RELIED_UPON_FINDING_LABELS = tuple(_RELIED_UPON_FINDINGS)


@dataclasses.dataclass(frozen=True)
class LeveragedPairConfig:
    """Bundles everything that used to be SOXX/SOXL-specific module state,
    so generate_leveraged_pair_rebalance_proposals() below can serve any
    stable/leveraged pair. A new pair needs its OWN relied_upon_findings
    (see SOXX_SOXL_PAIR's docstring-level discussion in this module's
    header) and its OWN grid-searched production_params -- never assume
    another pair's frozen numbers transfer, even if the mechanism is the
    same (docs/architecture/ARCHITECTURE_DEBT.md-style discipline: don't overclaim)."""

    stable_ticker: str
    leveraged_ticker: str
    strategy_key: str
    production_params: dict
    relied_upon_finding_labels: dict[str, EvidenceStatus]
    evidence_status: str
    lookback_days_for_signal: int = LOOKBACK_DAYS_FOR_SIGNAL


class StrategyMarketDataError(RuntimeError):
    """Base refusal for unavailable or stale strategy market data."""


class MarketDataUnavailableError(StrategyMarketDataError):
    """The provider did not return the bars required by the strategy."""


class StrategyPositionDataError(StrategyMarketDataError):
    """A held leg carries no usable price, so a rebalance cannot be sized.

    FCS-001. Sizing divides by ``position.current_price`` at four sites. A
    zero, negative, or non-finite price made those raise ZeroDivisionError or
    ``ValueError: cannot convert float NaN to integer`` -- exceptions this
    module never declares, so the Streamlit caller (which caught only
    ``MissingResearchDependencyError`` and ``StrategyMarketDataError``) let
    them escape its handler and never rendered the RISK-REDUCTION proposals it
    had already computed in the same block. An optional strategy check must
    never be able to suppress a risk-reducing sell.

    ``assistant/proposals.py`` has guarded the identical idiom since
    2026-07-29; that guard was simply never generalized to this module.

    Deliberately a ``StrategyMarketDataError`` subclass so both existing
    callers already catch it -- a new top-level exception type would be a new
    escape of exactly the kind this fixes. Raised loudly rather than returning
    ``[]``: "we could not check" is not "no rebalance needed", the same
    distinction GR-4 draws for missing bars.
    """


class StaleMarketDataError(StrategyMarketDataError):
    """GR-4: refuse to size a strategy rebalance from stale bars.

    A stale bar past its SLA blocks the strategy proposals that depend on
    it -- and ONLY them: risk-reduction proposals derive from policy and
    the live portfolio snapshot, never from these bars, so a data outage
    can never obstruct a legitimate risk-reducing sell. Raised loudly
    (not a silent empty return) so the caller's surface names the refusal.
    """


class MissingResearchDependencyError(RuntimeError):
    """Raised when a finding this module's proposal generation relies on
    has NO matching entry in the research registry at all, OR no longer
    carries the SPECIFIC status this strategy depends on (see
    _RELIED_UPON_FINDINGS) -- an accidental registry deletion, a label
    rename, a partial/malformed migration, a stale hard-coded label, a
    future refactor that changes the evidence identity, or the finding
    being reclassified to rejected/exploratory/unavailable. Deliberately
    distinct from (and a STRONGER integrity failure than) a present-
    with-the-expected-status-but-unreproduced finding, which still
    generates a proposal with an explicit uncertainty disclosure instead
    (GPT review, 2026-07-30/31, independently reproduced twice: first
    that a missing label was silently indistinguishable from
    "authoritative", then that a REJECTED finding was too, since
    production_authoritative alone doesn't check `status`). Missing or
    wrong-status evidence must never be interpreted as trusted evidence,
    so this fails closed -- no proposal is generated -- rather than
    silently proceeding. Both CLI callers (scripts/run_personal_assistant.py's
    command_propose) and the UI's Propose & Approve tab already catch and
    prominently display an exception from this function, so raising here
    surfaces the integrity failure instead of looking identical to an
    ordinary "nothing needs rebalancing" result."""


def _relied_upon_findings_status(
    relied_upon_findings: dict[str, EvidenceStatus] | None = None,
) -> tuple[list[str], list[str]]:
    """Returns (broken_labels, non_authoritative_present_labels) for
    `relied_upon_findings` (defaults to _RELIED_UPON_FINDINGS, i.e. the
    SOXX/SOXL pair -- kept as a default rather than a required parameter
    so existing bare `_relied_upon_findings_status()` callers, including
    tests/test_strategy_proposals.py, keep working unchanged) against the
    current KNOWN_FINDINGS registry. `broken_labels` covers BOTH a missing
    registry entry AND one present with the WRONG status (not the specific
    status this strategy requires) -- both are the SAME, stronger
    integrity failure (see MissingResearchDependencyError), unlike a
    present-with-the-expected-status-but-unreproduced finding, which is
    the softer `non_authoritative_present` case and still allows a
    proposal with an explicit disclosure."""
    if relied_upon_findings is None:
        relied_upon_findings = _RELIED_UPON_FINDINGS
    by_label = {f.label: f for f in KNOWN_FINDINGS}
    broken = []
    non_authoritative_present = []
    for label, expected_status in relied_upon_findings.items():
        finding = by_label.get(label)
        if finding is None or finding.status != expected_status:
            broken.append(label)
            continue
        if not finding.production_authoritative:
            non_authoritative_present.append(label)
    return broken, non_authoritative_present

PRODUCTION_PARAMS = {
    "target_vol_pct": 0.5,
    "max_leveraged_weight": 0.6,
    "band_pct": 15.0,
    "trend_lookback_days": 200,
    "vol_lookback_days": 20,
}

EVIDENCE_STATUS = "promising_unconfirmed_strategy"

SOXX_SOXL_PAIR = LeveragedPairConfig(
    stable_ticker=STABLE_TICKER,
    leveraged_ticker=LEVERAGED_TICKER,
    strategy_key="soxx_soxl_rebalance",
    production_params=PRODUCTION_PARAMS,
    relied_upon_finding_labels=_RELIED_UPON_FINDINGS,
    evidence_status=EVIDENCE_STATUS,
    lookback_days_for_signal=LOOKBACK_DAYS_FOR_SIGNAL,
)

# Pairs a caller (UI/CLI) should offer a rebalance check for. SPY/UPRO is
# deliberately NOT here yet: its PRODUCTION_PARAMS have never been
# finalized from a committed grid-search result (scripts/run_vol_target_
# rotation_spy_upro.py prints "Best by Calmar" at runtime but nothing is
# recorded in this repo) -- adding it with guessed numbers would overclaim
# exactly what this module's docstring warns against. Re-run that script's
# grid search (via the real-data-check skill) and record its winning
# params here before adding SPY_UPRO_PAIR.
CONFIGURED_LEVERAGED_PAIRS: list[LeveragedPairConfig] = [SOXX_SOXL_PAIR]


def _stable_id(packet: DecisionPacket, policy: TradingPolicy, intent: TradeIntent, strategy_key: str) -> str:
    # See assistant/proposals.py's _stable_id for why generated_at (a full
    # timestamp) is used instead of portfolio.as_of (just a date) -- a
    # same-day regeneration must not collide with a stale/expired row.
    raw = (
        f"{strategy_key}|{packet.generated_at}|{policy.version}|{intent.ticker.upper()}|"
        f"{intent.side}|{intent.shares}"
    )
    return "tp_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _target_leveraged_weight(
    stable_close: pd.Series, leveraged_close: pd.Series, as_of: pd.Timestamp, production_params: dict
) -> tuple[float | None, str]:
    """Returns (target_leveraged_weight, label). None if not computable
    (insufficient history) -- caller should skip generating a proposal."""
    trend = classify_trend(stable_close, as_of, lookback_days=production_params["trend_lookback_days"])
    if trend is None:
        return None, "insufficient_trend_history"
    if trend == "downtrend":
        return 0.0, "downtrend_defensive"

    leveraged_df = pd.DataFrame({"close": leveraged_close})
    realized_vol = compute_trailing_market_volatility(leveraged_df, as_of, lookback_days=production_params["vol_lookback_days"])
    if realized_vol is None:
        return None, "insufficient_volatility_history"

    target = compute_target_leveraged_weight(
        realized_vol, production_params["target_vol_pct"], production_params["max_leveraged_weight"]
    )
    return target, f"uptrend_vol_target(realized={realized_vol:.2f}%)"


def generate_leveraged_pair_rebalance_proposals(
    packet: DecisionPacket,
    policy: TradingPolicy,
    pair_config: LeveragedPairConfig,
    ttl_minutes: int = 15,
    market_data: dict[str, pd.DataFrame] | None = None,
    store: AssistantStore | None = None,
) -> list[TradeProposal]:
    """
    At most one proposal: rebalance `pair_config`'s stable/leveraged pair
    toward the target leveraged weight if drift exceeds its configured
    band. Returns [] if either ticker isn't currently held, if history is
    insufficient to compute a target, or if the account is already within
    the band.

    `market_data` lets a caller/test inject price history instead of
    hitting the network; production callers can omit it.

    `store`, if given, records this evaluation via
    AssistantStore.record_strategy_evaluation() under `pair_config.strategy_key`
    -- closing a gap this module previously only documented: the backtest
    assumed a fixed ~21-trading-day check counter, but the live version
    had no equivalent memory of when it was last evaluated
    (docs/Archive/Plans/ALLOCATION_SERVICE_DESIGN.md, 2026-07-28). Recorded on every
    NORMAL return (proposal or empty list) but NOT when
    MissingResearchDependencyError is raised below -- a refused evaluation
    is a distinct case, deliberately not conflated with "evaluated, no
    drift" here; no enforcement reads this data yet.

    Raises MissingResearchDependencyError (fails closed, no proposal) if
    a finding this strategy relies on has no matching entry in the
    research registry at all, OR is present but no longer carries the
    specific status this strategy requires (e.g. reclassified to
    rejected/exploratory/unavailable) -- see that error's docstring.
    """
    proposals = _generate_leveraged_pair_rebalance_proposals(
        packet,
        policy,
        pair_config,
        ttl_minutes,
        market_data,
        store=store,
    )
    if store is not None:
        store.record_strategy_evaluation(
            pair_config.strategy_key,
            datetime.now(timezone.utc).isoformat(),
            {"fired": bool(proposals), "proposal_count": len(proposals)},
        )
    return proposals


def generate_soxx_soxl_rebalance_proposals(
    packet: DecisionPacket,
    policy: TradingPolicy,
    ttl_minutes: int = 15,
    market_data: dict[str, pd.DataFrame] | None = None,
    store: AssistantStore | None = None,
) -> list[TradeProposal]:
    """Thin backward-compatible wrapper around
    generate_leveraged_pair_rebalance_proposals(..., SOXX_SOXL_PAIR) --
    kept so existing callers/tests that import this function by name need
    no changes. See that function's docstring for full behavior."""
    return generate_leveraged_pair_rebalance_proposals(packet, policy, SOXX_SOXL_PAIR, ttl_minutes, market_data, store)


def _generate_leveraged_pair_rebalance_proposals(
    packet: DecisionPacket,
    policy: TradingPolicy,
    pair_config: LeveragedPairConfig,
    ttl_minutes: int = 15,
    market_data: dict[str, pd.DataFrame] | None = None,
    *,
    store: AssistantStore | None = None,
) -> list[TradeProposal]:
    stable_ticker = pair_config.stable_ticker
    leveraged_ticker = pair_config.leveraged_ticker
    production_params = pair_config.production_params

    broken_dependencies, _ = _relied_upon_findings_status(pair_config.relied_upon_finding_labels)
    if broken_dependencies:
        raise MissingResearchDependencyError(
            "Cannot verify this strategy's research dependencies -- the following relied-upon "
            "finding(s) are missing from the research registry entirely, or no longer carry the "
            f"specific status this strategy requires: {', '.join(broken_dependencies)}. Refusing to "
            "generate a proposal until this is resolved (an accidental deletion, a label rename, a "
            "malformed migration, or a genuine reclassification of the underlying research)."
        )

    snapshot = packet.portfolio
    position_by_ticker = {p.ticker.upper(): p for p in snapshot.positions}
    stable_position = position_by_ticker.get(stable_ticker)
    leveraged_position = position_by_ticker.get(leveraged_ticker)
    if stable_position is None or leveraged_position is None:
        return []

    combined_value = stable_position.market_value + leveraged_position.market_value
    if combined_value <= 0:
        return []

    # FCS-001: validate BOTH legs' prices before any sizing arithmetic.
    # `combined_value` guards market_value, not current_price -- and those are
    # separate broker fields, so a halted or unpriced leg can carry a stale
    # non-zero market_value alongside a zero/NaN price. math.isfinite, not just
    # `<= 0`: every ordered comparison against NaN is False, so a bare
    # positivity check passes it straight through to `int(x / NaN)`.
    for position in (stable_position, leveraged_position):
        price = position.current_price
        if not isinstance(price, (int, float)) or isinstance(price, bool) or (
            not math.isfinite(price) or price <= 0
        ):
            raise StrategyPositionDataError(
                f"{position.ticker} has no usable current price ({price!r}); "
                "refusing to size a rebalance from an unpriced or halted leg"
            )

    if market_data is None:
        if store is not None:
            from assistant.data_integrity import fetch_daily_bars_recorded

            market_data = fetch_daily_bars_recorded(
                store,
                [stable_ticker, leveraged_ticker],
                pair_config.lookback_days_for_signal,
            )
        else:
            try:
                market_data = fetch_historical(
                    [stable_ticker, leveraged_ticker],
                    lookback_days=pair_config.lookback_days_for_signal,
                )
            except Exception as exc:
                raise MarketDataUnavailableError(
                    f"{stable_ticker}/{leveraged_ticker} market data is "
                    f"unavailable ({type(exc).__name__}); refusing to treat "
                    "a provider failure as no rebalance"
                ) from None
    if stable_ticker not in market_data or leveraged_ticker not in market_data:
        missing = sorted(
            {
                stable_ticker,
                leveraged_ticker,
            }
            - set(market_data)
        )
        raise MarketDataUnavailableError(
            f"{stable_ticker}/{leveraged_ticker} market data is unavailable "
            f"for {', '.join(missing)}; refusing to treat missing bars as "
            "no rebalance"
        )
    stable_frame = market_data[stable_ticker]
    leveraged_frame = market_data[leveraged_ticker]
    if (
        not isinstance(stable_frame, pd.DataFrame)
        or not isinstance(leveraged_frame, pd.DataFrame)
        or "close" not in stable_frame
        or "close" not in leveraged_frame
    ):
        raise MarketDataUnavailableError(
            f"{stable_ticker}/{leveraged_ticker} market data is unavailable "
            "or malformed; refusing to treat unusable bars as no rebalance"
        )
    stable_close = stable_frame["close"]
    leveraged_close = leveraged_frame["close"]
    if stable_close.empty or leveraged_close.empty:
        raise MarketDataUnavailableError(
            f"{stable_ticker}/{leveraged_ticker} market data is unavailable "
            "because one or both bar series are empty; refusing to treat "
            "empty bars as no rebalance"
        )
    as_of = min(stable_close.index[-1], leveraged_close.index[-1])

    # GR-4 staleness SLA: a rebalance sized from bars that miss the latest
    # completed NYSE session would trade current dollars on old prices.
    # Refuse loudly; the caller catches per-pair and risk-reduction
    # proposals remain unaffected (they never consult these bars).
    from data.price_source import evaluate_bar_freshness

    freshness = evaluate_bar_freshness(as_of.date().isoformat())
    if not freshness.fresh:
        raise StaleMarketDataError(
            f"{stable_ticker}/{leveraged_ticker} bars are stale "
            f"({freshness.detail}); refusing to size a rebalance from "
            "stale market data"
        )

    target_leveraged_weight, label = _target_leveraged_weight(stable_close, leveraged_close, as_of, production_params)
    if target_leveraged_weight is None:
        return []

    current_leveraged_weight = leveraged_position.market_value / combined_value
    drift_pct = abs(current_leveraged_weight - target_leveraged_weight) * 100
    if drift_pct <= production_params["band_pct"]:
        return []

    target_leveraged_value = combined_value * target_leveraged_weight
    now = datetime.now(timezone.utc)

    if leveraged_position.market_value > target_leveraged_value:
        excess_value = leveraged_position.market_value - target_leveraged_value
        # Capped at max_order_shares exactly like the buy branch below --
        # the execution gate's MAX_ORDER_VALUE check applies to sells
        # too, not just buys, so an uncapped sell proposal for a large
        # excess would always be rejected at approval time, and since
        # this generator is fully deterministic, regenerating would
        # produce the identical unexecutable proposal every time (GPT
        # review, 2026-07-31). Sized against the policy's per-order cap
        # -- may only partially close the gap in one pass, same as the
        # buy branch already discloses.
        max_order_shares = int(policy.max_order_value / leveraged_position.current_price)
        # SELCR-001: exact floor on the held side (see
        # assistant.proposals.sellable_whole_shares) -- a float-rounded
        # fractional holding produced a proposal the gate must refuse, which
        # would strand this rebalance sell permanently.
        shares = min(
            sellable_whole_shares(exact_position_shares(leveraged_position)),
            max_order_shares,
            int(excess_value / leveraged_position.current_price),
        )
        side = "sell"
        reason = (
            f"{leveraged_ticker} is {current_leveraged_weight * 100:.1f}% of the {stable_ticker}+{leveraged_ticker} "
            f"allocation, {drift_pct:.1f} points outside the {production_params['band_pct']:.0f}% band around the "
            f"{target_leveraged_weight * 100:.1f}% target ({label}). Sized against the policy's max order "
            "value -- may only partially close the gap in one pass."
        )
    else:
        shortfall_value = target_leveraged_value - leveraged_position.market_value
        max_order_shares = int(policy.max_order_value / leveraged_position.current_price)
        shares = min(max_order_shares, int(shortfall_value / leveraged_position.current_price))
        side = "buy"
        reason = (
            f"{leveraged_ticker} is {current_leveraged_weight * 100:.1f}% of the {stable_ticker}+{leveraged_ticker} "
            f"allocation, {drift_pct:.1f} points below the {production_params['band_pct']:.0f}% band around the "
            f"{target_leveraged_weight * 100:.1f}% target ({label}). Sized against currently available "
            f"cash/order-value limits -- may only partially close the gap in one pass."
        )

    if shares <= 0:
        return []

    # Missing findings already raised above -- only "present but
    # unreproduced" reaches here, which still generates a proposal with
    # this explicit disclosure rather than being blocked.
    _, non_authoritative = _relied_upon_findings_status(pair_config.relied_upon_finding_labels)
    uncertainties = [
        f"production_params (target_vol_pct={production_params['target_vol_pct']}, "
        f"max_leveraged_weight={production_params['max_leveraged_weight']}) were selected via "
        "full-history grid search, not an out-of-sample confirmation split -- these specific "
        "numbers are unconfirmed even though the wide-band mechanism itself may be confirmed research.",
        f"This strategy has NOT been shown to beat {stable_ticker}/{leveraged_ticker} buy-and-hold on CAGR "
        "in any tested configuration -- it is a risk-shape (drawdown/tax) trade, not an alpha claim.",
        f"Single-leg proposal: only {leveraged_ticker} is adjusted this pass. {stable_ticker}'s own weight "
        "will look correspondingly off-target until cash/proceeds settle and a later `propose` run "
        "rebalances it.",
        "Market orders can fill away from the displayed reference price.",
    ]
    if non_authoritative:
        # Explicit, checked-at-generation-time disclosure (GPT review,
        # 2026-07-29) -- this module still generates proposals despite
        # relying on findings that haven't been re-verified since the
        # fetch_historical lookback-days fix; evidence_status is always
        # a "promising_unconfirmed*" label (never "confirmed"), so this
        # never overclaims, but the reliance itself must be surfaced,
        # not just assumed from the module docstring.
        uncertainties.append(
            "This strategy relies on research findings that are NOT currently production-authoritative "
            "(unreproduced since the fetch_historical lookback-days fix): "
            + "; ".join(non_authoritative) + "."
        )

    intent = TradeIntent(
        ticker=leveraged_ticker,
        side=side,
        shares=shares,
        order_type="market",
        rationale=reason,
    )
    proposal_id = _stable_id(packet, policy, intent, pair_config.strategy_key)
    return [
        TradeProposal(
            proposal_id=proposal_id,
            created_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=ttl_minutes)).isoformat(),
            status="proposed",
            idempotency_key=f"{proposal_id}-{packet.portfolio.as_of}",
            policy_version=policy.version,
            policy_fingerprint=compute_policy_fingerprint(policy),
            intent=intent,
            reference_price=leveraged_position.current_price,
            price_timestamp=now.isoformat(),
            reasons=[reason],
            evidence_status=pair_config.evidence_status,
            expected_impact=preview_trade_impact(
                snapshot, leveraged_ticker, side, shares, leveraged_position.current_price
            ),
            alternatives=[
                "Take no action -- drift outside the band costs tax-efficiency, not immediate risk.",
                "Rebalance manually to a different target than this strategy's frozen production parameters.",
                "Re-run the grid search on updated history before trusting these exact parameters again.",
            ],
            uncertainties=uncertainties,
        )
    ]
