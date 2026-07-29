"""
Click-around Streamlit front end for the personal trading assistant.

This is ONLY a different presentation layer over
scripts/run_personal_assistant.py's exact same underlying functions
(build_decision_packet, generate_risk_reduction_proposals,
generate_leveraged_pair_rebalance_proposals, execute_approved_paper_proposal).
No financial logic lives here -- every number and every safety check is
still computed by the same deterministic code the CLI uses.

Safety note: every proposal still requires deliberate typed confirmation.
The user must type the exact phrase "approve" in the specific proposal card
before its submit button is enabled -- this prevents a stray click from
ever placing a real (paper) trade. The proposal identity is bound by that
card and by the proposal content digest, which covers the displayed
proposal content, the active policy, and the material portfolio state
(cash, positions, buying power, open orders) as of this render; typed
confirmation (and any typed override phrase) is cleared whenever any of
that changes. The digest is bound to the proposal's displayed reference
price, not a freshly-refetched live quote -- the execution service
independently re-fetches and revalidates a fresh quote at submission time
regardless of what was displayed. A policy override additionally requires
the separate order-specific phrase "OVERRIDE <SIDE> <SHARES> <TICKER>", and
is only authorized if the violations at submission time exactly match what
was shown when the override was first offered -- a changed violation set
(new severity, a new violation, or a different one) forces a fresh review
instead of silently authorizing against different conditions.

Run with:
    streamlit run scripts/personal_assistant_ui.py
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from assistant.allocation_batch import (
    BATCH_STOPPED_UNKNOWN,
    execute_allocation_batch,
    new_batch_id,
    preflight_allocation_batch,
)
from assistant.allocation_proposals import (
    build_allocation_plan,
    estimate_pending_buy_value_by_ticker,
    generate_allocation_buy_proposals,
)
from assistant.context_builder import build_decision_packet, build_portfolio_snapshot_from_alpaca, get_upcoming_events
from assistant.execution_service import (
    PolicyOverridableBlockError,
    execute_approved_paper_proposal,
    reconcile_submission,
)
from assistant.explanations import explain_ticker
from assistant.ai_advisor import (
    curate_recommended_tickers,
    is_ai_advisor_configured,
    review_allocation_plan,
    suggest_similar_tickers,
)
from assistant.news_summary import fetch_recent_news, is_ai_summary_configured, summarize_news_for_ticker
from assistant.recommended_stocks import build_recommended_tickers, is_ipo_calendar_configured
from assistant.similarity_evidence import compute_similarity_evidence, format_evidence_summary
from assistant.ticker_verification import partition_by_universe, verify_tickers
from assistant.policy import DEFAULT_POLICY_PATH, compute_policy_fingerprint, load_policy
from assistant.proposal_status import (
    ACTIVE_BROKER_ORDER_STATUSES,
    BLOCKED,
    BROKER_EXPIRED,
    BROKER_REJECTED,
    CANCELED,
    EXPIRED,
    FILLED,
    MANUAL_RECONCILIATION_STATUSES,
    POLICY_OVERRIDE_AVAILABLE,
    PROPOSED,
    STATUSES,
    SUBMISSION_FAILED,
    UNRESOLVED_BROKER_STATE_STATUSES,
    VALIDATION_FAILED,
)
from assistant.proposals import generate_risk_reduction_proposals
from assistant.research_registry import summarize_evidence_authority, underfilled_dataset_warning
from assistant.risk_copilot import (
    check_concentration,
    check_policy_compliance,
    estimate_stress_impact,
    find_correlated_clusters,
)
from assistant.sample_portfolio import SAMPLE_CASH, SAMPLE_POSITIONS
from assistant.stock_lookup import (
    compute_blended_volatility,
    historical_hold_period_range,
    inverse_volatility_weights,
    latest_price_targets_by_firm,
)
from assistant.storage import AssistantStore
from assistant.strategy_proposals import (
    CONFIGURED_LEVERAGED_PAIRS,
    MissingResearchDependencyError,
    generate_leveraged_pair_rebalance_proposals,
)
from config import BASKETS, LEVERAGED_ETF_TICKERS, PAPER_TRADING, UNIVERSE
from data.event_data import fetch_upcoming_earnings
from data.market_data import fetch_historical
from execution.alpaca_broker import is_configured
from market_analytics import classify_trend

st.set_page_config(page_title="Personal Trading Assistant", layout="wide")


def _now_eastern() -> datetime:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        return datetime.now(timezone(timedelta(hours=-4)))


@st.cache_resource
def _store() -> AssistantStore:
    return AssistantStore()


_PACKET_CACHE_TTL_SECONDS = 15
_RECOMMENDED_STOCKS_CACHE_TTL_SECONDS = 900


@st.cache_data(ttl=_PACKET_CACHE_TTL_SECONDS)
def _load_base_packet(policy_path: str):
    """Builds the ONE shared account/positions/open-orders/market-regime
    snapshot for this cache window -- NEVER includes live earnings events
    (see _load_packet() below for that).

    Cached (GPT review, 2026-07-31, independently reproduced twice: first
    that this wasn't decorated with @st.cache_data at all despite the
    Briefing tab's "Refresh briefing" button already calling
    `st.cache_data.clear()` as if it were; second, after adding caching,
    that `include_events` was still part of the cache key, so a tab
    wanting live events and a tab that didn't were separately-cached,
    separately-fetched calls -- meaning two tabs in the SAME rerun could
    still see two DIFFERENT account/position/open-order snapshots from
    two different instants). Splitting the cache key down to JUST
    `policy_path` (event enrichment is layered on afterward by
    _load_packet(), never re-fetching this base snapshot) guarantees
    every tab shares the exact same portfolio/account/regime view for
    the whole cache window, regardless of whether that tab also wants
    events. A short TTL (not an unbounded cache) keeps the account/
    regime view honestly close to real-time for a manually-driven UI,
    while collapsing the redundant same-instant duplicate fetches a
    single rerun makes. "Refresh briefing" still forces an immediate
    live re-fetch via `st.cache_data.clear()`."""
    policy = load_policy(policy_path)
    packet = build_decision_packet(
        SAMPLE_POSITIONS,
        SAMPLE_CASH,
        use_live_alpaca=is_configured(),
        include_live_events=False,
        policy=policy,
    )
    return policy, packet


@st.cache_data(ttl=_PACKET_CACHE_TTL_SECONDS)
def _load_live_events_for_tickers(tickers: tuple[str, ...]) -> list:
    """Optional live-earnings enrichment ONLY -- never rebuilds the
    portfolio/account/regime snapshot (GPT review, 2026-07-31). Cached
    separately (and much more cheaply -- this is a single earnings-
    calendar lookup, not an account/quote/regime fetch) so requesting
    events never triggers a second account fetch."""
    return get_upcoming_events(list(tickers), fetch_live=True)


@st.cache_data(ttl=_RECOMMENDED_STOCKS_CACHE_TTL_SECONDS)
def _load_recommended_tickers(held_tickers: tuple[str, ...]):
    """Composes yf.screen (most-actives) + Finnhub (IPO calendar, if
    configured) + a Claude ticker-suggestion call + a verification pass over
    every candidate -- genuinely expensive to run on every Briefing rerun
    (which happens on every widget interaction anywhere in this tab), so this
    gets its OWN, much longer TTL than the account/regime packet cache. Use
    `_load_recommended_tickers.clear()` (this function's own cache, not the
    blanket `st.cache_data.clear()` the "Refresh briefing" button uses) so
    refreshing recommendations doesn't also force an account re-fetch.

    `held_tickers` is part of the cache key (a tuple, not a list, so it's
    hashable) -- this is deliberate: a fresh set of positions must recompute
    recommendations rather than reusing a stale exclusion/similarity basis.

    Bundles the curation call (curate_recommended_tickers) into this SAME
    cached function rather than calling it separately per rerun -- it's a
    third Claude call layered on top of the other two data sources, and
    firing it on every widget interaction anywhere in this tab would be a
    real, avoidable cost."""
    recommended, dropped = build_recommended_tickers(list(held_tickers), store=store)
    curated_note = curate_recommended_tickers(recommended, store=store) if recommended else None
    return recommended, dropped, curated_note


def _load_packet(policy_path: str, include_events: bool):
    """Returns (policy, packet) -- `packet` is always derived from the
    SAME cached base packet (see _load_base_packet()) for this cache
    window, with live earnings events layered on top ONLY if requested.
    Every call site keeps its existing (policy_path, include_events)
    signature; the base account/regime snapshot is simply never rebuilt
    just because a different tab's `include_events` differs (GPT review,
    2026-07-31)."""
    policy, base_packet = _load_base_packet(policy_path)
    if not include_events:
        return policy, base_packet
    tickers = tuple(p.ticker for p in base_packet.portfolio.positions)
    events = _load_live_events_for_tickers(tickers)
    enriched = dataclasses.replace(base_packet, upcoming_events=events)
    return policy, enriched


# Coarse rounding granularity for cash/equity/buying_power in the
# portfolio-context payload (GPT review, 2026-07-31) -- see
# _portfolio_context_payload()'s docstring for why these are banded
# rather than bound exactly.
_CASH_BAND_SIZE = 100.0


def _banded(value: float) -> float:
    return round(value / _CASH_BAND_SIZE) * _CASH_BAND_SIZE


def _portfolio_context_payload(portfolio) -> dict:
    """Normalized, JSON-ready snapshot of the STABLE portfolio facts a
    displayed proposal card's summary/impact was computed against --
    open-order availability, plus normalized, SORTED position share
    counts and open orders (sorted so merely re-fetching the same
    holdings/orders in a different order can never spuriously invalidate
    an otherwise-unchanged signature), and cash/equity/buying_power
    rounded to a coarse $100 band. Shared by BOTH _proposal_content_
    digest() (ordinary Selling/Propose & Approve/per-ticker Watchlist
    cards) and _allocation_input_signature() (the Watchlist's
    multi-ticker allocation split), so the same material-state
    definition protects every proposal card in the app.

    Deliberately does NOT include each position's `current_price`,
    `market_value`, or `total_equity` -- and deliberately BANDS `cash`/
    `buying_power` rather than binding them exactly (GPT review,
    2026-07-31, independently reproduced: an earlier version bound
    current_price/market_value/total_equity exactly, but those move
    continuously with live Alpaca quotes during market hours even with
    zero real account change -- every Streamlit rerun, INCLUDING the
    rerun triggered by typing into the confirmation box itself, refetches
    a live portfolio snapshot, so a single price tick between a keystroke
    and the Submit click could silently wipe an already-typed
    confirmation, making approval intermittently or continuously
    impossible during active trading hours).

    `total_equity` is dropped ENTIRELY, not just banded: this project's
    own build_portfolio_snapshot() always computes it as `cash +
    sum(shares * current_price)`, so it is DEFINITIONALLY the most
    price-sensitive figure here -- banding alone doesn't fully insulate
    it (a big enough, or accumulated, price move still crosses a band),
    and it carries no information beyond cash + position shares (both
    already tracked here) plus live marks (which this binding must
    ignore). Position `shares` and open-order identity are kept EXACT
    since those only change on a genuine account event (a fill, a
    manually-placed order), never on a quote tick alone -- this still
    catches the case this binding exists for (a real fill or a manually-
    placed order changing the account underneath an unchanged card)
    without being sensitive to pure mark-to-market noise. `cash` (settled
    cash, not marked-to-market) and `buying_power` (which CAN be
    equity-derived for a margin account) are banded to a coarse $100
    granularity as extra insurance -- coarse enough that ordinary noise
    rarely crosses a boundary, while a real fill or transfer (this
    project's default max_order_value is $5,000) almost always does."""
    positions_payload = sorted(
        ({"ticker": p.ticker, "shares": p.shares} for p in portfolio.positions),
        key=lambda d: d["ticker"],
    )
    open_orders_payload = sorted(
        (
            {
                "order_id": order.get("order_id"),
                "ticker": order.get("ticker"),
                "side": order.get("side"),
                "shares": order.get("shares"),
                "notional": order.get("notional"),
                "type": order.get("type"),
                "limit_price": order.get("limit_price"),
            }
            for order in portfolio.open_orders
        ),
        key=lambda d: (d["order_id"] or "", d["ticker"] or "", d["side"] or ""),
    )
    return {
        "cash_band": _banded(portfolio.cash),
        "buying_power_band": _banded(portfolio.buying_power) if portfolio.buying_power is not None else None,
        "open_orders_available": portfolio.open_orders_available,
        "positions": positions_payload,
        "open_orders": open_orders_payload,
        "portfolio_as_of": portfolio.as_of,
    }


def _proposal_content_digest(proposal: dict, policy_fingerprint: str, portfolio_context: dict) -> str:
    """Fingerprint over exactly what's displayed in this proposal's
    confirmation summary, the active policy's fingerprint, AND the
    material portfolio state (see _portfolio_context_payload()) the
    displayed summary/impact was computed against. Compared against a
    stored digest so a typed confirmation/override that was started
    against ONE version of this card (a different proposal, a stale
    render, a policy that's since changed, or a portfolio that's since
    changed) is cleared rather than silently carried over onto different
    displayed content (GPT review, 2026-07-28 and 2026-07-30: "do not
    retain an override-ready UI state after proposal content, policy,
    portfolio, or quote context changes" -- portfolio state was the one
    piece of that claim not actually implemented for ordinary proposal
    cards until now).

    Deliberately bound to the proposal's own STORED `reference_price`
    (what's actually displayed), not a freshly-refetched live quote --
    this UI only fetches a fresh quote at submit time, inside
    execute_approved_paper_proposal() itself, which independently
    revalidates price/staleness/spread against that fresh quote
    regardless of what this digest matched. Claiming a live quote change
    clears confirmation here would be dishonest given the UI never
    observes that change before submission."""
    intent = proposal["intent"]
    payload = {
        "proposal_id": proposal["proposal_id"],
        "ticker": intent["ticker"],
        "side": intent["side"],
        "shares": intent["shares"],
        "order_type": intent.get("order_type"),
        "limit_price": intent.get("limit_price"),
        "reference_price": proposal["reference_price"],
        "expires_at": proposal["expires_at"],
        "policy_fingerprint": policy_fingerprint,
        "portfolio_context": portfolio_context,
    }
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _clear_confirmation_state_if_digest_changed(session_state, proposal_id: str, current_digest: str) -> bool:
    """Pure invalidation logic, factored out of _render_proposal_approval()
    so it can be unit-tested without a live Streamlit session (GPT
    review, 2026-07-30) -- `session_state` is any dict-like object
    supporting `.get`/`__setitem__`/`.pop` (a plain dict in tests; Streamlit's
    real `st.session_state` in the app). Clears the typed confirmation
    phrase, any override-available banner, AND any previously typed
    override phrase whenever the content/policy/portfolio digest for this
    proposal card has changed since it was last set -- the typed override
    phrase specifically was never cleared before, which could leave the
    override button immediately re-enabled if the override banner
    reappeared for the same intent with new violations. Returns True iff
    it actually cleared anything (the digest had changed)."""
    digest_key = f"content_digest_{proposal_id}"
    if session_state.get(digest_key) == current_digest:
        return False
    session_state[f"confirm_{proposal_id}"] = ""
    session_state.pop(f"override_available_{proposal_id}", None)
    session_state.pop(f"override_confirm_{proposal_id}", None)
    session_state[digest_key] = current_digest
    return True


def _proposal_status_category(status: str) -> str:
    """Pure categorization of a proposal status into how it should be
    rendered -- factored out so this routing is unit-testable without a
    live Streamlit session (GPT review, 2026-07-31; most of this UI's
    prior test coverage only exercised pure helper functions, never
    whether the actual approval workflow behaved correctly against a
    changed/terminal proposal). One of:
      "approvable" -- proposed / override_available: show approval controls.
      "filled"     -- terminal success: show the stored broker fill.
      "working"    -- broker accepted/partial/cancel-pending order.
      "failed"     -- terminal failure: show the stored violations/error.
      "unresolved" -- broker outcome not yet confirmed (submitting/
                      submission_unknown/reconciling): point at Reconcile.
      "in_progress"-- claimed by an approval attempt elsewhere (validating/
                      approved): never approval controls, but not terminal.
    """
    if status in (PROPOSED, POLICY_OVERRIDE_AVAILABLE):
        return "approvable"
    if status == FILLED:
        return "filled"
    if status in ACTIVE_BROKER_ORDER_STATUSES:
        return "working"
    if status in (
        BLOCKED,
        VALIDATION_FAILED,
        SUBMISSION_FAILED,
        EXPIRED,
        CANCELED,
        BROKER_REJECTED,
        BROKER_EXPIRED,
    ):
        return "failed"
    if status in UNRESOLVED_BROKER_STATE_STATUSES:
        return "unresolved"
    return "in_progress"  # VALIDATING / APPROVED


def _render_terminal_or_inflight_status(proposal: dict, status: str) -> None:
    """Renders the STORED outcome for a proposal that is no longer
    approvable (terminal) or is already claimed/in-flight from a prior
    approval attempt -- never approval controls (GPT review, 2026-07-31):
    a card rendered from a stale st.session_state snapshot used to keep
    showing approval controls even after the underlying proposal had
    already been executed/blocked/expired elsewhere."""
    category = _proposal_status_category(status)
    if category == "filled":
        order = proposal.get("broker_order") or {}
        msg = (
            f"Filled at {proposal.get('filled_at', '?')} -- broker order "
            f"{order.get('order_id', '?')} [{order.get('status', 'unknown')}]"
        )
        if proposal.get("policy_override"):
            msg += " (submitted via policy override)"
        st.success(msg)
    elif category == "working":
        order = proposal.get("broker_order") or {}
        st.info(
            f"Broker order {order.get('order_id', '?')} is {status.replace('_', ' ')}; "
            f"filled {order.get('filled_qty', 0)}/{order.get('shares', '?')} shares. "
            "Keep `monitor-orders` running (with periodic polling fallback) until terminal."
        )
    elif category == "failed":
        detail = "; ".join(proposal.get("violations") or []) or proposal.get("error") or "no detail recorded"
        st.error(f"{status.replace('_', ' ').title()}: {detail}")
    elif category == "unresolved":
        st.warning(
            f"Status: {status} -- this proposal's broker outcome is not yet confirmed. Resolve it via "
            "the History tab's Reconcile action (or `recover-stale` on the CLI if it's stuck in "
            "'reconciling') before approving an equivalent trade."
        )
    else:
        # in_progress: VALIDATING / APPROVED -- an approval attempt is
        # (or very recently was) actively claiming this proposal elsewhere.
        st.info(f"Status: {status} -- an approval attempt is currently in progress for this proposal.")


def _render_proposal_approval(proposal: dict, store: AssistantStore, policy_path: str, portfolio) -> None:
    """One proposal card with the typed-confirmation approve flow.
    Shared by the Selling, Propose & Approve, and Watchlist tabs --
    identical safety flow everywhere a proposal can be approved: type the
    exact "approve" phrase, or the submit button stays disabled. The
    confirmation phrase is intentionally simple (2026-07-28) -- what
    protects against approving the WRONG visible proposal or stale UI
    state is the immutable summary below and the content-digest binding,
    not phrase complexity (GPT review, 2026-07-28).

    `portfolio`: the CURRENT portfolio snapshot (as of this render), used
    only to bind the confirmation/override UI state to the material
    account state the displayed summary/impact reflects (GPT review,
    2026-07-30) -- NOT re-fetched or revalidated here; submission below
    always fetches its own fresh snapshot independently.

    Reloads the AUTHORITATIVE record from `store` by proposal_id before
    doing anything else (GPT review, 2026-07-31): the `proposal` dict
    passed in is often a stale snapshot cached in st.session_state from
    whenever it was generated or last rendered -- without this reload, an
    already-executed, blocked, or expired proposal kept showing live
    approval controls (and a stale confirm phrase was never cleared after
    a successful submission, since nothing ever re-checked status).
    Approval controls are shown ONLY for `proposed`/`override_available`;
    every other status renders its stored outcome instead."""
    proposal_id = proposal["proposal_id"]
    reloaded = store.get_proposal(proposal_id)
    if reloaded is None:
        st.warning(f"{proposal_id}: no longer found in storage -- it may have been removed.")
        return
    proposal = reloaded
    status = proposal["status"]
    intent = proposal["intent"]
    override_key = f"override_available_{proposal_id}"
    override_confirm_key = f"override_confirm_{proposal_id}"
    digest_key = f"content_digest_{proposal_id}"
    stale_key = f"stale_{proposal_id}"

    if _proposal_status_category(status) != "approvable":
        # Terminal or in-flight -- clear any lingering confirmation state
        # for this card (it can never silently re-arm if this proposal_id
        # somehow reappears in an approvable status later) and show the
        # stored outcome instead of approval controls.
        st.session_state.pop(f"confirm_{proposal_id}", None)
        st.session_state.pop(override_key, None)
        st.session_state.pop(override_confirm_key, None)
        st.session_state.pop(digest_key, None)
        st.session_state.pop(stale_key, None)
        with st.container(border=True):
            st.subheader(f"{intent['side'].upper()} {intent['shares']} {intent['ticker']}")
            st.caption(f"{proposal_id} -- evidence_status: {proposal.get('evidence_status', '')}")
            _render_terminal_or_inflight_status(proposal, status)
        return

    display_policy = load_policy(policy_path)
    policy_fingerprint = compute_policy_fingerprint(display_policy)
    portfolio_context = _portfolio_context_payload(portfolio)
    current_digest = _proposal_content_digest(proposal, policy_fingerprint, portfolio_context)
    previous_digest = st.session_state.get(digest_key)
    _clear_confirmation_state_if_digest_changed(st.session_state, proposal_id, current_digest)
    # A genuine change from a PREVIOUSLY stored digest (not the very
    # first render, which also has no prior digest) marks this card
    # persistently stale -- it stays stale across reruns even if the
    # digest happens to re-match later, until the caller actually
    # regenerates this proposal (producing a new proposal_id), rather
    # than silently un-invalidating on the next quiet rerun (GPT review,
    # 2026-07-31: "invalidate or regenerate the displayed proposal
    # instead of merely clearing its phrase" -- the reasons/expected
    # impact below are computed once at generation time and never
    # recomputed, so they can go stale exactly when the digest does).
    if previous_digest is not None and previous_digest != current_digest:
        st.session_state[stale_key] = True
    is_stale = st.session_state.get(stale_key, False)
    if is_stale:
        st.warning(
            "This proposal's content, policy, or portfolio context has changed since it was last "
            "displayed -- the reasons/expected-impact below were computed against the OLD context and "
            "may no longer be accurate. Approval is disabled for this card; regenerate it (use this "
            "tab's Check/refresh button) to get a current, actionable proposal."
        )

    estimated_notional = intent["shares"] * proposal["reference_price"]
    override_phrase = f"OVERRIDE {intent['side'].upper()} {intent['shares']} {intent['ticker'].upper()}"

    with st.container(border=True):
        st.subheader(f"{intent['side'].upper()} {intent['shares']} {intent['ticker']}")
        st.caption(f"{proposal_id} -- evidence_status: {proposal['evidence_status']}")

        with st.container(border=True):
            st.write("**Confirm before submitting -- this summary reflects exactly what will be sent:**")
            summary_col1, summary_col2 = st.columns(2)
            with summary_col1:
                st.write(f"Ticker: **{intent['ticker']}** -- Side: **{intent['side'].upper()}**")
                st.write(f"Shares: **{intent['shares']}** -- Order type: **{intent.get('order_type', 'market')}**")
                if intent.get("order_type") == "limit":
                    st.write(f"Limit price: **${intent.get('limit_price'):,.2f}**")
                st.write(f"Estimated notional: **${estimated_notional:,.2f}**")
            with summary_col2:
                st.write(f"Reference price: ${proposal['reference_price']:,.2f}")
                st.write(f"Policy: {display_policy.name} v{display_policy.version} ({policy_fingerprint[:8]})")
                st.write(f"Expires: {proposal['expires_at']}")

        for reason in proposal["reasons"]:
            st.write(f"- {reason}")
        impact = proposal["expected_impact"]
        st.write(
            f"Position weight: {impact['position_weight_before_pct']:.1f}% -> "
            f"{impact['position_weight_after_pct']:.1f}%"
        )
        with st.expander("Uncertainties / caveats"):
            for uncertainty in proposal["uncertainties"]:
                st.write(f"- {uncertainty}")

        st.write("To submit this order, type the exact phrase below: `approve`")
        typed = st.text_input(
            "Confirmation phrase", key=f"confirm_{proposal_id}", label_visibility="collapsed"
        )
        submit_disabled = typed.strip().lower() != "approve" or is_stale
        if st.button(
            "Submit paper order",
            key=f"submit_{proposal_id}",
            disabled=submit_disabled,
        ):
            if not is_configured():
                st.error("Alpaca paper credentials are required for approval execution.")
            else:
                try:
                    portfolio = build_portfolio_snapshot_from_alpaca()
                    order = execute_approved_paper_proposal(
                        proposal_id,
                        typed,
                        portfolio,
                        display_policy,
                        store,
                        now_et=_now_eastern(),
                        kill_switch_active=os.environ.get("TRADING_ASSISTANT_KILL_SWITCH") == "1",
                    )
                    st.session_state.pop(override_key, None)
                    st.session_state.pop(override_confirm_key, None)
                    st.success(
                        f"Submitted paper order {order['order_id']}: "
                        f"{order['side'].upper()} {order['shares']} {order['ticker']} [{order['status']}]"
                    )
                except PolicyOverridableBlockError as exc:
                    # Replace the displayed violation list with whatever
                    # is current, and clear any previously typed override
                    # phrase -- a stale phrase must not silently re-arm
                    # the override button against a NEW violation set
                    # (GPT review, 2026-07-30).
                    st.session_state[override_key] = list(exc.overridable_violations)
                    st.session_state.pop(override_confirm_key, None)
                except Exception as exc:
                    st.session_state.pop(override_key, None)
                    st.session_state.pop(override_confirm_key, None)
                    st.error(f"Order not submitted: {exc}")

        conditions_changed_key = f"override_conditions_changed_{proposal_id}"
        if st.session_state.get(override_key):
            if st.session_state.pop(conditions_changed_key, False):
                # Rendered on the FRESH rerun triggered right after the
                # exception handler below updated override_key -- shown
                # here, immediately above the (now current) violation
                # list, rather than "above" pointing at content that was
                # already drawn with the OLD list on the same script pass
                # (GPT review, 2026-07-31: a later override submission
                # replaced the list in session state AFTER this warning
                # block had already rendered once with the stale one).
                st.error(
                    "The override conditions changed since your previous review. No order was "
                    "submitted. Review the current violations below and type the override phrase "
                    "again if you still accept them."
                )
            st.warning(
                "Blocked only by risk-preference/earnings-calendar checks, not unreliable data -- "
                "the broker itself would still accept this order:\n"
                + "\n".join(f"- {v}" for v in st.session_state[override_key])
            )
            st.write(
                f"To override and submit anyway, type the exact phrase below: `{override_phrase}` "
                "(identifies this specific order so you can't accidentally override a different one)."
            )
            override_typed = st.text_input(
                "Override phrase", key=override_confirm_key, label_visibility="collapsed"
            )
            if st.button(
                "Override and submit anyway",
                key=f"override_submit_{proposal_id}",
                disabled=override_typed.strip() != override_phrase or is_stale,
            ):
                if not is_configured():
                    st.error("Alpaca paper credentials are required for approval execution.")
                else:
                    try:
                        portfolio = build_portfolio_snapshot_from_alpaca()
                        order = execute_approved_paper_proposal(
                            proposal_id,
                            "approve",
                            portfolio,
                            display_policy,
                            store,
                            now_et=_now_eastern(),
                            kill_switch_active=os.environ.get("TRADING_ASSISTANT_KILL_SWITCH") == "1",
                            override_policy_violations=True,
                        )
                        st.session_state.pop(override_key, None)
                        st.session_state.pop(override_confirm_key, None)
                        st.success(
                            f"Submitted paper order {order['order_id']} (policy override applied): "
                            f"{order['side'].upper()} {order['shares']} {order['ticker']} [{order['status']}]"
                        )
                    except PolicyOverridableBlockError as exc:
                        # The reviewed-override binding in
                        # execute_approved_paper_proposal() rejected this
                        # attempt: either this was somehow the first
                        # presentation, or (far more likely here, since an
                        # override was just explicitly typed) the
                        # violations changed since the last time this was
                        # reviewed. Never submit -- replace the displayed
                        # violations and clear the typed phrase so the
                        # user must explicitly re-review and re-type it.
                        st.session_state[override_key] = list(exc.overridable_violations)
                        st.session_state.pop(override_confirm_key, None)
                        if exc.conditions_changed:
                            # Rerun IMMEDIATELY rather than calling
                            # st.error() here: the violation-list warning
                            # block above this button already rendered
                            # ONCE this script pass, using the list as it
                            # stood BEFORE this click -- an error message
                            # printed here would sit next to that STALE
                            # list, not the fresh one just stored above
                            # (GPT review, 2026-07-31). The flag is picked
                            # up and shown right above the now-current
                            # list on the rerun this triggers.
                            st.session_state[conditions_changed_key] = True
                            st.rerun()
                        st.error(f"Order not submitted: {exc}")
                    except Exception as exc:
                        st.session_state.pop(override_key, None)
                        st.session_state.pop(override_confirm_key, None)
                        st.error(f"Order not submitted: {exc}")


def _allocation_input_signature(
    weights: dict,
    dollar_amount: float,
    prices: dict,
    price_as_of_by_ticker: dict,
    max_weight_pct: float,
    policy,
    packet,
) -> str:
    """Deterministic fingerprint over everything that determines an
    allocation plan -- cart/weights, dollar amount, prices (and their
    as-of timestamps, so a stale-but-unchanged price doesn't mask a
    refresh), the cap, the active policy's identity, AND the material
    portfolio state the displayed plan/impact is computed against.
    Compared against the signature stored alongside a generated batch of
    proposals so a changed input can be caught and the stale cards
    cleared, instead of leaving them rendered and approvable against
    inputs the user has since changed (GPT review, 2026-07-28).

    `packet.portfolio.as_of` alone (a plain ISO date) used to be the
    ONLY portfolio-derived input here -- positions, cash, equity, buying
    power, and open orders could all change intraday (a fill, a
    manually-placed order, a deposit) without moving that date at all,
    leaving a stale allocation card's confirmation/override state fully
    intact against a portfolio that no longer matches what's displayed
    (GPT review, 2026-07-29). Now reuses _portfolio_context_payload()
    (GPT review, 2026-07-30) -- the same material-state definition every
    other proposal card in the app is bound to -- for the actual material
    fields: cash/equity/buying_power, open-order availability, and
    normalized, SORTED positions/open-orders (sorted so merely
    re-fetching the same holdings/orders in a different order can never
    spuriously invalidate an otherwise-unchanged signature)."""
    payload = {
        "weights": {t: weights[t] for t in sorted(weights)},
        "dollar_amount": round(dollar_amount, 2),
        "prices": {t: prices.get(t) for t in sorted(weights)},
        "price_as_of": {t: str(price_as_of_by_ticker.get(t)) for t in sorted(weights)},
        "max_weight_pct": max_weight_pct,
        "policy_version": policy.version,
        "policy_fingerprint": compute_policy_fingerprint(policy),
        "portfolio_context": _portfolio_context_payload(packet.portfolio),
    }
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


title_col, badge_col = st.columns([4, 1])
with title_col:
    st.title("Personal Trading Assistant")
    st.caption(
        "Click-around front end over the same deterministic code the CLI uses. "
        "Nothing here computes financial numbers itself -- it only displays what "
        "assistant/*.py already computed."
    )
with badge_col:
    live_confirmed = os.environ.get("CONFIRM_LIVE_TRADING") == "I_UNDERSTAND"
    if PAPER_TRADING:
        st.success("\U0001F4C4 PAPER MONEY")
    elif live_confirmed:
        st.error("\U0001F4B0 LIVE MONEY")
    else:
        st.error("LIVE mode, unconfirmed")
    st.caption(
        "Read-only status. Switching to live trading can't be done from this app -- "
        "it requires editing config.py and setting CONFIRM_LIVE_TRADING yourself, outside the UI, "
        "on purpose: no single click here can ever enable real-money trading."
    )

with st.sidebar:
    st.header("Settings")
    policy_path = st.text_input("Policy file", value=str(DEFAULT_POLICY_PATH))
    include_events = st.checkbox("Fetch live earnings events", value=False)
    if is_configured():
        st.success("Alpaca paper credentials: connected")
    else:
        st.warning("Alpaca not configured -- using sample portfolio")

store = _store()

tab_briefing, tab_watchlist, tab_selling, tab_propose, tab_history = st.tabs(
    ["Briefing", "Watchlist", "Selling", "Propose & Approve", "History"]
)

with tab_briefing:
    if st.button("Refresh briefing", key="refresh_briefing"):
        st.cache_data.clear()
        st.toast("Refreshed against the live account.", icon="\U0001F503")
    policy, packet = _load_packet(policy_path, include_events)
    # Persist one row per genuinely NEW packet (a fresh live fetch --
    # packet.generated_at changes only when _load_packet()'s cache
    # actually re-executes), not one row per Streamlit rerun -- every
    # widget interaction anywhere in the app reruns this tab's body too,
    # and unconditionally saving here previously inserted a duplicate
    # decision packet into an unbounded table on every single click
    # (GPT review, 2026-07-31).
    if st.session_state.get("last_saved_packet_generated_at") != packet.generated_at:
        store.save_decision_packet(packet)
        st.session_state["last_saved_packet_generated_at"] = packet.generated_at

    st.caption(
        f"Source: **{packet.portfolio.source}** ({packet.portfolio.account_mode}) -- "
        f"generated {packet.generated_at} -- portfolio as of {packet.data_freshness.get('portfolio_as_of', '?')}, "
        f"regime as of {packet.data_freshness.get('market_regime_as_of', '?')}, "
        f"research registry v{packet.data_freshness.get('research_registry_version', '?')}"
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total equity", f"${packet.portfolio.total_equity:,.2f}")
    col2.metric("Cash", f"${packet.portfolio.cash:,.2f} ({packet.risk.cash_pct}%)")
    col3.metric("Positions", packet.analytics["position_count"])
    col4.metric("Open orders", packet.analytics["open_order_count"])

    st.subheader(f"Market regime ({packet.regime.benchmark_ticker})")
    st.write(f"Trend: **{packet.regime.trend or 'unavailable'}** / Volatility: **{packet.regime.volatility_regime or 'unavailable'}**"
             + (f" (trailing {packet.regime.trailing_volatility_pct}% daily std, as of {packet.regime.as_of})" if packet.regime.trailing_volatility_pct is not None else ""))

    st.subheader("Risk exposure")
    risk_col1, risk_col2, risk_col3 = st.columns(3)
    risk_col1.metric("Largest single position", f"{packet.risk.largest_single_position_pct}%")
    risk_col2.metric("Leveraged ETF exposure", f"{packet.risk.leveraged_etf_exposure_pct}%")
    risk_col3.metric("Invested", f"{packet.analytics['invested_pct']:.1f}%")
    if packet.risk.basket_exposure_pct:
        st.write("Basket exposure (overlapping, doesn't sum to 100%):")
        st.dataframe(
            [{"Basket": b, "% of equity": pct} for b, pct in sorted(packet.risk.basket_exposure_pct.items(), key=lambda kv: -kv[1])],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("No basket exposure -- no positions held.")

    for policy_violation in check_policy_compliance(packet.portfolio, policy):
        st.error(f"Policy violation: {policy_violation}")
    if not packet.risk.concentration_warnings:
        # Only show this caption in the "all clear" case -- when
        # concentration_warnings IS non-empty, its content already appears
        # once in the "Warnings" section below (packet.warnings includes
        # risk.concentration_warnings verbatim, see context_builder.py) and
        # once as a Policy violation above if it also breaches the active
        # policy; showing it a third time here via check_concentration()
        # was pure duplication (GPT review, 2026-07-28, reproduced).
        st.caption("Informational summary (not a policy-compliance check): " + check_concentration(packet.risk))
    for cluster_warning in find_correlated_clusters(packet.portfolio):
        st.warning(cluster_warning)
    with st.expander("Stress test"):
        stress_col1, stress_col2 = st.columns(2)
        stress_benchmark = stress_col1.text_input("Benchmark ticker", value="SPY", key="stress_benchmark")
        stress_move_pct = stress_col2.number_input("Hypothetical move (%)", value=-10.0, step=1.0, key="stress_move_pct")
        if st.button("Estimate impact", key="run_stress_test"):
            # Live fetch_historical() call for OLS beta -- explicitly
            # button-gated, not run on every rerun, matching this tab's
            # existing "no expensive work on every Streamlit rerun"
            # convention (see the packet-save guard above).
            stress_result = estimate_stress_impact(packet.portfolio, stress_benchmark, stress_move_pct)
            if stress_result.get("warning"):
                st.warning(stress_result["warning"])
            if stress_result["total_estimated_impact"] is not None:
                st.metric(
                    f"Estimated impact of a {stress_move_pct}% move in {stress_benchmark}",
                    f"${stress_result['total_estimated_impact']:,.2f}",
                )
            if stress_result["position_impacts"]:
                st.dataframe(stress_result["position_impacts"], use_container_width=True, hide_index=True)

    if packet.warnings:
        st.subheader("Warnings")
        for warning in packet.warnings:
            st.warning(warning)

    if packet.portfolio.positions:
        st.subheader("Positions")
        st.dataframe(
            [
                {
                    "Ticker": p.ticker,
                    "Shares": p.shares,
                    "Current price": p.current_price,
                    "Market value": p.market_value,
                    "Unrealized P&L %": p.unrealized_pnl_pct,
                    "Leveraged ETF": p.is_leveraged_etf,
                }
                for p in packet.portfolio.positions
            ],
            use_container_width=True,
            hide_index=True,
        )
        st.caption(f"Unrealized P&L: ${packet.analytics['unrealized_pnl']:,.2f}")
    else:
        st.subheader("Positions")
        st.caption("No positions held.")

    if packet.portfolio.positions:
        st.subheader("Holdings analysis")
        st.caption(
            "Per-position trend/volatility and this project's own evidence-labeled findings for each "
            "ticker you actually hold -- not a price prediction, just what's known and what currently "
            "applies to your account."
        )
        for position in packet.portfolio.positions:
            with st.container(border=True):
                st.write(f"**{position.ticker}** -- {position.shares:g} sh, ${position.market_value:,.2f} ({position.unrealized_pnl_pct:+.1f}% unrealized)")
                try:
                    ticker_data = fetch_historical([position.ticker], lookback_days=300)
                    trend, vol = None, None
                    if position.ticker in ticker_data and not ticker_data[position.ticker].empty:
                        close = ticker_data[position.ticker]["close"]
                        as_of = close.index[-1]
                        trend = classify_trend(close, as_of, lookback_days=200)
                        vol = compute_blended_volatility(close, as_of)
                    trend_str = trend or "unavailable"
                    vol_str = f"{vol:.2f}% trailing daily std" if vol is not None else "unavailable"
                    st.write(f"Trend (200-day): **{trend_str}** -- Volatility (20d/60d blend): **{vol_str}**")
                except Exception as exc:
                    st.caption(f"Could not fetch trend/volatility: {exc}")

                explanation = explain_ticker(position.ticker, portfolio=packet.portfolio, market_regime=packet.regime)
                ticker_specific = [e for e in explanation["historical_evidence"] if e["ticker_specific"]]
                if ticker_specific:
                    for e in ticker_specific:
                        st.write(f"**[{e['display_status']}]** {e['label']} -- {e['claim']}")
                        if e.get("dataset_warning"):
                            st.warning(e["dataset_warning"])
                else:
                    st.caption(f"No {position.ticker}-specific research exists in this project.")
                if explanation["triggered_today"]:
                    for trig in explanation["triggered_today"]:
                        st.caption(f"Signal firing today: {trig['rule']} ({trig['direction']})")
        st.caption("For price targets, news, and the full history/best-worst range for any holding, look it up in the Watchlist tab.")

    if packet.portfolio.open_orders:
        st.subheader("Open orders")
        st.dataframe(packet.portfolio.open_orders, use_container_width=True, hide_index=True)

    if packet.upcoming_events:
        st.subheader("Upcoming events")
        for event in sorted(packet.upcoming_events, key=lambda e: e.event_date or "~"):
            if event.event_date:
                st.write(f"**{event.ticker}**: {event.event_type} on {event.event_date} ({event.days_away} day(s)) [{event.status.value}]")
            else:
                st.caption(f"{event.ticker}: {event.event_type} date unavailable [{event.status.value}]")

    if packet.signals:
        # Historical verdicts and current authority are reported as TWO
        # separate tallies, never one aggregate (GPT review, 2026-07-30):
        # aggregating by raw `status` could print "2 confirmed" right
        # above rows that correctly show those same 2 findings as
        # non-authoritative -- contradicting itself.
        evidence_summary = summarize_evidence_authority(packet.signals)
        st.subheader(f"Research evidence relevant to your holdings ({len(packet.signals)} findings)")
        st.caption(
            "Historical verdicts: "
            + " / ".join(f"{count} {status}" for status, count in sorted(evidence_summary["verdict_counts"].items()))
        )
        if evidence_summary["non_authoritative_count"]:
            st.caption(
                f"Current authority: {evidence_summary['non_authoritative_count']} "
                "unreproduced/non-authoritative (see the qualifier on each row below)"
            )
        for finding in packet.signals:
            # display_status appends an explicit qualifier for a
            # confirmed/promising finding that isn't currently
            # production-authoritative -- never shown as a bare
            # "[confirmed]" in that case (GPT review, 2026-07-29).
            st.write(f"**[{finding.display_status}]** {finding.label} -- {finding.claim}")
            st.caption(finding.detail)
            if finding.provenance is not None:
                dataset_warning = underfilled_dataset_warning(finding.provenance)
                if dataset_warning:
                    st.warning(dataset_warning)

    st.divider()
    st.subheader("Recommended stocks to explore (not held, not a proposal)")
    st.caption(
        "Purely informational/exploratory -- these are NOT held positions and NOT trade proposals. "
        "Presence here is NOT an allocation authorization (same convention as config.DEFENSIVE_CARRY_TICKERS). "
        "\"Most actively traded\" reflects trading VOLUME and price movement, NOT buy-vs-sell order flow -- "
        "no legitimate retail-accessible data source provides true order imbalance."
    )
    if st.button("Refresh recommended stocks", key="refresh_recommended"):
        _load_recommended_tickers.clear()
    held_tickers_tuple = tuple(sorted({p.ticker.upper() for p in packet.portfolio.positions}))
    recommended_tickers, dropped_candidates, curated_note = _load_recommended_tickers(held_tickers_tuple)
    if dropped_candidates:
        st.caption(
            f"{len(dropped_candidates)} candidate ticker(s) could not be verified against real market data "
            "and were omitted."
        )
    for category, label in [
        ("most_active", "Most actively traded today"),
        ("recent_ipo", "Recent IPOs"),
        ("ai_suggested", "Claude suggestions with measured comparison (not a validated similarity recommender)"),
    ]:
        items = [r for r in recommended_tickers if r.reason_category == category]
        if not items:
            if category == "recent_ipo" and not is_ipo_calendar_configured():
                st.caption("IPO calendar unavailable -- FINNHUB_API_KEY is not set. Sign up for a free Finnhub account and set this env var to enable it.")
            elif category == "ai_suggested" and not held_tickers_tuple:
                st.caption("No current holdings to base similarity suggestions on.")
            continue
        with st.expander(f"{label} ({len(items)})"):
            st.dataframe(
                [{"Ticker": r.ticker, "Detail": r.detail} for r in items],
                use_container_width=True,
                hide_index=True,
            )

    if curated_note:
        st.caption(
            "AI commentary on the list above -- unverified prose, not a validated fact or a "
            "recommendation. Cross-check against the tables above before acting on it."
        )
        st.info(curated_note)

with tab_watchlist:
    st.caption(
        "Add tickers to your cart, then check them for: own trend/volatility, "
        "recent analyst price targets by firm, recent news, a REAL historical "
        "best/worst hold-period return range, and this project's own "
        "evidence-labeled signal history. **No probability-of-return number "
        "is shown anywhere.** This project has confirmed zero signals as real "
        "edge after rigorous out-of-sample testing (see the Briefing tab's "
        "evidence summary) -- a bare probability would either be fabricated "
        "or would dress up an already-rejected backtest as more confident "
        "than it is. When 2+ tickers are checked together, an inverse-volatility "
        "purchase split is shown -- a risk-sizing heuristic for splitting new money "
        "across tickers you've already picked, from historical data, not a return forecast."
    )

    common_options = sorted(set(UNIVERSE) | set(LEVERAGED_ETF_TICKERS) | {"QQQ", "SPY", "SOXX"})
    picked = st.multiselect("Pick from common tickers", options=common_options, key="watchlist_picked")
    typed = st.text_input(
        "Or type any other ticker(s), comma-separated (e.g. NVDL, QQQM)", key="watchlist_typed"
    )
    typed_tickers = [t.strip().upper() for t in typed.split(",") if t.strip()]
    cart = list(dict.fromkeys(picked + typed_tickers))

    if cart:
        st.write(f"**Cart:** {', '.join(cart)}")

    ai_news_available = is_ai_summary_configured()
    want_ai_summary = st.checkbox(
        "Summarize news with Claude (real API call, small real cost per ticker)",
        value=False,
        disabled=not ai_news_available,
        help=(
            "Requires ANTHROPIC_API_KEY to be set. Off by default -- headlines "
            "are shown either way; this only adds an AI-written summary of them."
            if ai_news_available
            else "ANTHROPIC_API_KEY is not set -- showing raw headlines only."
        ),
    )
    ai_advisor_available = is_ai_advisor_configured()
    want_similar_suggestions = st.checkbox(
        "Get Claude's own ticker suggestions, with measured comparison (real API call, small real cost)",
        value=False,
        disabled=not ai_advisor_available,
        help=(
            "Claude picks tickers from its own knowledge -- this is NOT a validated "
            "similarity engine. Every suggestion is checked against real market data "
            "before being shown, and paired with a measured correlation/sector-overlap "
            "column so you can see whether the data actually backs up Claude's stated reason."
            if ai_advisor_available
            else "ANTHROPIC_API_KEY is not set."
        ),
    )
    want_allocation_review = st.checkbox(
        "Get an AI review of the purchase split with Claude (real API call, small real cost)",
        value=False,
        disabled=not ai_advisor_available,
        help=(
            "Advisory commentary only -- never changes the computed weights below. "
            "Requires 2+ tickers checked together."
            if ai_advisor_available
            else "ANTHROPIC_API_KEY is not set."
        ),
    )

    check_cart_clicked = st.button("Check cart", type="primary", disabled=not cart)
    if check_cart_clicked:
        _, watchlist_packet = _load_packet(policy_path, include_events=False)
        try:
            earnings_by_ticker = fetch_upcoming_earnings(cart)
        except Exception:
            earnings_by_ticker = {}
        results = {}
        for ticker in cart:
            try:
                data = fetch_historical([ticker], lookback_days=300)
                own_trend, own_vol, current_price, price_as_of = None, None, None, None
                if ticker in data and not data[ticker].empty:
                    close = data[ticker]["close"]
                    as_of = close.index[-1]
                    own_trend = classify_trend(close, as_of, lookback_days=200)
                    own_vol = compute_blended_volatility(close, as_of)
                    current_price = float(close.iloc[-1])
                    price_as_of = str(as_of.date())
                explanation = explain_ticker(ticker, portfolio=watchlist_packet.portfolio, market_regime=watchlist_packet.regime)
                price_targets = latest_price_targets_by_firm(ticker)
                hold_range = historical_hold_period_range(ticker, data, hold_days=20)
                news = fetch_recent_news(ticker)
                news_summary = summarize_news_for_ticker(ticker, news) if want_ai_summary else None
                results[ticker] = {
                    "own_trend": own_trend,
                    "own_vol": own_vol,
                    "current_price": current_price,
                    "price_as_of": price_as_of,
                    "price_history": data[ticker]["close"] if ticker in data and not data[ticker].empty else None,
                    "explanation": explanation,
                    "price_targets": price_targets,
                    "hold_range": hold_range,
                    "news": news,
                    "news_summary": news_summary,
                    "earnings": earnings_by_ticker.get(ticker, {"available": False}),
                }
            except Exception as exc:
                results[ticker] = {"error": str(exc)}
        st.session_state["watchlist_results"] = results

        if want_similar_suggestions:
            raw_suggestions = suggest_similar_tickers(cart, store=store)
            if raw_suggestions:
                from_universe_raw, wildcard_raw = partition_by_universe(raw_suggestions, universe=UNIVERSE)
                # Universe membership is provenance ONLY -- it decides which
                # display group a suggestion falls in, never whether it's
                # eligible. Both groups go through the SAME verify_tickers()
                # eligibility check (independent review: config.UNIVERSE was
                # built for research-scan coverage, not recommendation
                # eligibility -- a member can have gone illiquid, non-equity,
                # or stale since being added; a prior version let a
                # from-universe suggestion skip this check entirely).
                from_universe, dropped = verify_tickers([c["ticker"] for c in from_universe_raw]) if from_universe_raw else ([], [])
                wildcard, wildcard_dropped = verify_tickers([c["ticker"] for c in wildcard_raw]) if wildcard_raw else ([], [])
                dropped = dropped + wildcard_dropped
                all_candidate_tickers = [v["ticker"] for v in from_universe] + [v["ticker"] for v in wildcard]
                # Measured evidence sits ALONGSIDE the LLM's stated reason, never
                # replacing it -- a real, resolvable ticker can still carry a
                # FALSE similarity claim (independent review: e.g. CAT mislabeled
                # as a semiconductor peer of NVDA passes ticker-existence
                # verification cleanly, since that only proves the symbol
                # resolves, not that the stated relationship is true).
                evidence_by_ticker = {
                    t: format_evidence_summary(compute_similarity_evidence(cart, t)) for t in all_candidate_tickers
                }
                st.session_state["watchlist_ai_suggestions"] = {
                    "from_universe": from_universe,
                    "verified": wildcard,
                    "dropped": dropped,
                    "reason_by_ticker": {c["ticker"].upper(): c["reason"] for c in raw_suggestions},
                    "evidence_by_ticker": evidence_by_ticker,
                }
            else:
                st.session_state["watchlist_ai_suggestions"] = None
        else:
            st.session_state["watchlist_ai_suggestions"] = None

    watchlist_results = st.session_state.get("watchlist_results", {})

    ai_suggestions = st.session_state.get("watchlist_ai_suggestions")
    if ai_suggestions:
        with st.expander(f"Claude's own suggestions related to {', '.join(cart)} (with measured comparison)", expanded=False):
            reason_by_ticker = ai_suggestions["reason_by_ticker"]
            evidence_by_ticker = ai_suggestions.get("evidence_by_ticker", {})
            if ai_suggestions["from_universe"]:
                st.write("**From your tracked universe:**")
                st.dataframe(
                    [
                        {
                            "Ticker": v["ticker"], "Claude's reason": reason_by_ticker.get(v["ticker"], ""),
                            "Measured similarity": evidence_by_ticker.get(v["ticker"], ""),
                        }
                        for v in ai_suggestions["from_universe"]
                    ],
                    use_container_width=True, hide_index=True,
                )
            if ai_suggestions["verified"]:
                st.write("**Other suggestions (verified against real market data):**")
                st.dataframe(
                    [
                        {
                            "Ticker": v["ticker"], "Claude's reason": reason_by_ticker.get(v["ticker"], ""),
                            "Measured similarity": evidence_by_ticker.get(v["ticker"], ""),
                        }
                        for v in ai_suggestions["verified"]
                    ],
                    use_container_width=True, hide_index=True,
                )
                st.caption(
                    "\"Measured similarity\" is computed from real price history and sector/industry "
                    "metadata -- it may or may not agree with Claude's stated reason. Trust the measured "
                    "column over the prose when they conflict."
                )
            if ai_suggestions["dropped"]:
                st.caption(
                    f"{len(ai_suggestions['dropped'])} suggestion(s) could not be verified against real "
                    "market data and were omitted."
                )
            if not ai_suggestions["from_universe"] and not ai_suggestions["verified"]:
                st.caption("Claude returned no suggestions that passed verification.")

    vols = {t: r.get("own_vol") for t, r in watchlist_results.items() if "error" not in r}
    prices = {t: r.get("current_price") for t, r in watchlist_results.items() if "error" not in r}
    price_as_of_by_ticker = {t: r.get("price_as_of") for t, r in watchlist_results.items() if "error" not in r}

    # "Eligible" = has usable volatility data (gets a nonzero inverse-vol
    # weight) AND a valid positive price (a proposal could actually be
    # generated for it). Used to bound the cap slider to a value that's
    # always mathematically feasible -- previously the slider allowed any
    # 10-100% cap regardless of cart size, e.g. a 10% cap with only 2
    # eligible tickers can never actually be satisfied (GPT review,
    # 2026-07-28).
    uncapped_weights_preview = inverse_volatility_weights(vols) if vols else {}
    eligible_tickers = [
        t for t, w in uncapped_weights_preview.items()
        if w > 0 and prices.get(t) is not None and prices[t] > 0
    ]
    n_eligible = len(eligible_tickers)

    max_weight_pct = 100.0
    if len(watchlist_results) > 1 and vols:
        min_feasible_cap = math.ceil(100 / n_eligible) if n_eligible > 0 else 10.0
        slider_min = min(100.0, max(10.0, float(min_feasible_cap)))
        # Clamp an out-of-range stored slider value BEFORE the widget is
        # created (e.g. the cart shrank since the last rerun) -- Streamlit
        # raises if a widget's stored session_state value falls outside
        # the min/max it's about to be created with.
        stored = st.session_state.get("allocation_max_weight_pct")
        if stored is not None and stored < slider_min:
            st.session_state["allocation_max_weight_pct"] = slider_min
        max_weight_pct = st.slider(
            "Max weight per ticker in the split (%)",
            min_value=slider_min,
            max_value=100.0,
            value=100.0,
            step=5.0,
            key="allocation_max_weight_pct",
            help=(
                "100% = no cap (an unusually calm ticker can otherwise take most of the split). "
                "Lowering this redistributes the excess above the cap to the other tickers in your cart. "
                f"Minimum is {slider_min:.0f}% here -- below that, your {n_eligible} eligible cart "
                "ticker(s) couldn't absorb the full split even divided evenly."
            ),
        )

    try:
        weights = inverse_volatility_weights(vols, max_weight_pct=max_weight_pct) if vols else {}
    except ValueError as exc:
        st.error(f"Could not compute the purchase split: {exc}")
        weights = {}

    if len(watchlist_results) > 1 and weights:
        st.subheader("Inverse-volatility purchase split")
        st.dataframe(
            [{"Ticker": t, "Suggested %": w} for t, w in sorted(weights.items(), key=lambda kv: -kv[1])],
            use_container_width=True,
            hide_index=True,
        )
        st.caption(
            "Splits a NEW cash contribution across your cart, weighted inversely to each ticker's own "
            "trailing volatility (blended 20d/60d) -- sizes the choppier name smaller, same principle as "
            "strategies/vol_target_rotation.py. A risk-sizing heuristic for splitting money you've already "
            "decided to spend on these tickers -- not a recommendation of which stocks to buy, and not an "
            "optimized portfolio allocation (it ignores correlation between your picks and your existing "
            "holdings elsewhere in the account)."
        )

        if check_cart_clicked and want_allocation_review:
            baskets_by_ticker = {t: [name for name, tickers in BASKETS.items() if t in tickers] for t in weights}
            st.session_state["watchlist_ai_review"] = review_allocation_plan(
                list(weights.keys()), weights, vols, baskets_by_ticker, store=store
            )
        elif not want_allocation_review:
            st.session_state["watchlist_ai_review"] = None

        ai_review = st.session_state.get("watchlist_ai_review")
        if ai_review:
            with st.expander("AI review of this split (Claude)", expanded=False):
                st.write(ai_review.summary)
                if ai_review.observations:
                    st.dataframe(
                        [
                            {
                                "Severity": o.severity, "Type": o.type,
                                "Tickers": ", ".join(o.tickers), "Claim": o.claim,
                            }
                            for o in ai_review.observations
                        ],
                        use_container_width=True, hide_index=True,
                    )
                st.caption(
                    "Advisory commentary only -- does not change the weights shown above. Every number "
                    "above is checked against the actual computed split; any claim carrying a number that "
                    "didn't match was dropped before display."
                )

    if weights:
        st.subheader("Create purchase proposals using this split")
        alloc_policy, alloc_packet = _load_packet(policy_path, include_events=False)
        available_cash = alloc_packet.portfolio.cash
        if not alloc_policy.allow_new_positions:
            st.warning(
                "Your active policy has allow_new_positions=false (the default). You can still generate "
                "proposals below, but approving them will be blocked until you set "
                '"allow_new_positions": true in your policy file.'
            )
        st.caption("This only sizes the split across your cart -- it is not a recommendation to buy these specific stocks.")

        pending_value_by_ticker, pending_unknown_tickers = estimate_pending_buy_value_by_ticker(
            alloc_packet.portfolio.open_orders
        )
        cart_pending_unknown = pending_unknown_tickers & {t.upper() for t in weights}
        if cart_pending_unknown:
            st.warning(
                f"Pending buy order value for {', '.join(sorted(cart_pending_unknown))} couldn't be "
                "determined from the order itself (a plain market order with no notional/limit price yet) "
                "-- the projection below is INCOMPLETE for these tickers; their real final position may be "
                "larger than shown."
            )

        amount_col, balance_col = st.columns(2)
        with amount_col:
            # Clamp BEFORE the widget is created, same pattern as the
            # max-weight slider above -- Streamlit raises if a widget's
            # stored session_state value falls outside the min/max it's
            # about to be created with. Without this, a previously
            # entered amount that now exceeds a since-reduced cash
            # balance (or a margin account briefly reporting negative
            # cash, which would otherwise make max_value < min_value=0)
            # could break this widget entirely (GPT review, 2026-07-31).
            safe_max_cash = max(available_cash, 0.0)
            stored_amount = st.session_state.get("allocation_dollar_amount")
            if stored_amount is not None:
                clamped = min(max(stored_amount, 0.0), safe_max_cash)
                if clamped != stored_amount:
                    st.session_state["allocation_dollar_amount"] = clamped
            dollar_amount = st.number_input(
                "Amount to invest",
                min_value=0.0,
                max_value=safe_max_cash,
                value=0.0,
                step=50.0,
                key="allocation_dollar_amount",
                help="Capped at your current available cash, pulled live from Alpaca.",
                disabled=available_cash <= 0,
            )
        st.caption(f"Available cash right now (live from Alpaca): ${available_cash:,.2f}")
        if available_cash <= 0:
            st.caption("No available cash to allocate right now -- allocation is disabled.")

        plan = (
            build_allocation_plan(
                alloc_packet, alloc_policy, weights, prices, dollar_amount,
                pending_buy_value_by_ticker=pending_value_by_ticker,
                pending_value_unknown_tickers=pending_unknown_tickers,
            )
            if dollar_amount > 0
            else []
        )
        planned_spend = sum(e.planned_notional for e in plan)

        with balance_col:
            st.metric("Remaining balance after this purchase", f"${available_cash - planned_spend:,.2f}")
            st.caption(
                "Reflects the actual whole-share plan below (rounding down, and any tickers skipped for "
                "not affording 1 share, both leave a bit more cash than a raw percentage split would)."
            )

        if plan:
            unallocated = dollar_amount - planned_spend
            st.write(
                f"Requested: **${dollar_amount:,.2f}** -- Planned spend: **${planned_spend:,.2f}** -- "
                f"Unallocated: **${unallocated:,.2f}** (cap headroom, and/or share-rounding, and/or "
                "tickers too expensive to buy even 1 share of at this amount)."
            )
            plan_rows = [
                {
                    "Ticker": e.ticker,
                    "Weight %": e.weight_pct,
                    "Shares": e.shares,
                    "Planned $": f"${e.planned_notional:,.2f}",
                    "Existing value": f"${e.existing_market_value:,.2f}",
                    "Pending buys": "unknown" if e.pending_value_unknown else f"${e.pending_buy_value:,.2f}",
                    "Projected total %": round(e.projected_pct_of_equity, 1),
                    "Policy limit %": round(e.position_limit_pct, 1),
                    "Status": f"SKIPPED: {e.skip_reason}" if e.skipped else "OK",
                }
                for e in plan
            ]
            st.write(
                "**Projected final weight if you approve this split** (matches the ACTUAL whole-share plan "
                "that would be proposed -- includes existing holdings and known pending buy orders; this is "
                "where you'd catch adding to an already-large position, or a price too high to get even 1 "
                "share at this amount):"
            )
            st.dataframe(plan_rows, use_container_width=True, hide_index=True)

        current_signature = _allocation_input_signature(
            weights, dollar_amount, prices, price_as_of_by_ticker, max_weight_pct, alloc_policy, alloc_packet,
        )
        if (
            st.session_state.get("allocation_proposals")
            and st.session_state.get("allocation_proposals_signature") != current_signature
        ):
            st.warning(
                "Your cart, weights, cap, dollar amount, prices, or policy changed since these proposals "
                "were generated, so they no longer match what's shown above -- regenerate to get current, "
                "actionable proposals."
            )
            st.session_state["allocation_proposals"] = []
            st.session_state["allocation_proposals_signature"] = None

        if st.button("Create purchase proposals using this split", type="primary", disabled=dollar_amount <= 0):
            alloc_proposals = generate_allocation_buy_proposals(
                alloc_packet, alloc_policy, weights, prices, dollar_amount,
                pending_buy_value_by_ticker=pending_value_by_ticker,
                pending_value_unknown_tickers=pending_unknown_tickers,
            )
            for p in alloc_proposals:
                store.save_proposal(p.to_dict())
            st.session_state["allocation_proposals"] = [p.to_dict() for p in alloc_proposals]
            st.session_state["allocation_proposals_signature"] = current_signature
            if not alloc_proposals:
                st.warning(
                    "No proposals generated -- the amount may be too small to buy at least 1 share of any "
                    "cart ticker at its current price."
                )

        if st.session_state.get("allocation_proposals"):
            st.subheader("Submit all proposals in this split (one at a time, not atomic)")
            st.caption(
                "Submits every proposal above SEQUENTIALLY, one order at a time -- this is NOT a single "
                "atomic transaction. Paper (and real) broker orders can't be rolled back once submitted, "
                "so this can legitimately end with some legs filled and others not (e.g. 3 of 5 submitted, "
                "a 4th blocked, a 5th never attempted). Every proposal is preflight-checked first; if ANY "
                "of them fails, nothing is submitted. Rechecks available cash fresh before each ticker so "
                "an earlier fill in this same run can't cause the next one to overspend. Safe to click "
                "again after a page refresh -- already-submitted legs are never resubmitted. This does NOT "
                "override any policy block -- a ticker blocked only by an override-eligible check (a "
                "concentration cap or the earnings blackout) stops that leg here; use that ticker's own "
                "card below to override it individually if you want to proceed with just that one."
            )
            current_proposal_ids = [p["proposal_id"] for p in st.session_state["allocation_proposals"]]
            batch_key = "allocation_batch_id"
            if (
                st.session_state.get(batch_key + "_for_signature") != current_signature
                or st.session_state.get(batch_key) is None
            ):
                st.session_state[batch_key] = None
                st.session_state[batch_key + "_for_signature"] = current_signature

            bulk_typed = st.text_input(
                'Type the exact phrase below to submit all: "I approve this transaction"',
                key="allocation_bulk_confirm",
            )
            if st.button(
                "Submit all proposals in this split",
                type="primary",
                disabled=bulk_typed.strip() != "I approve this transaction",
            ):
                if not is_configured():
                    st.error("Alpaca paper credentials are required for approval execution.")
                else:
                    approve_policy = load_policy(policy_path)
                    preflight = preflight_allocation_batch(
                        current_proposal_ids, store, approve_policy, alloc_packet.portfolio,
                        now_et=_now_eastern(),
                        kill_switch_active=os.environ.get("TRADING_ASSISTANT_KILL_SWITCH") == "1",
                    )
                    failed_preflight = {pid: v for pid, v in preflight.items() if not v.approved}
                    if failed_preflight:
                        st.error(
                            "Preflight failed for one or more proposals -- submitting NONE of them "
                            "(all-or-nothing at the start, since a partial submission with a known-bad "
                            "leg still ahead is worse than not starting):"
                        )
                        for pid, validation in failed_preflight.items():
                            ticker = next(
                                (p["intent"]["ticker"] for p in st.session_state["allocation_proposals"] if p["proposal_id"] == pid),
                                pid,
                            )
                            st.write(f"- {ticker}: " + "; ".join(validation.violations))
                    else:
                        batch_id = new_batch_id()
                        store.create_allocation_batch(batch_id, current_proposal_ids, intended_total_notional=dollar_amount)
                        st.session_state[batch_key] = batch_id

            active_batch_id = st.session_state.get(batch_key)
            if active_batch_id:
                approve_policy = load_policy(policy_path)
                batch = execute_allocation_batch(
                    active_batch_id, store, approve_policy,
                    # now_provider=_now_eastern (the function itself, not
                    # a single evaluated-once value) so each leg this
                    # batch attempts gets a genuinely fresh Eastern
                    # timestamp -- a slow batch could otherwise compare a
                    # later leg's fresh quote against an increasingly
                    # stale now_et (GPT review, 2026-07-31).
                    now_provider=_now_eastern,
                    kill_switch_active=os.environ.get("TRADING_ASSISTANT_KILL_SWITCH") == "1",
                )
                st.write(f"Batch `{active_batch_id}` -- status: **{batch['status']}**")
                if batch["status"] == BATCH_STOPPED_UNKNOWN:
                    st.warning(
                        "Stopped: a leg's broker outcome is unresolved (submission_unknown). Resolve it "
                        f"via `reconcile {{proposal_id}}` (CLI) before this batch can continue -- it will "
                        "pick back up from here once that leg is resolved."
                    )
                leg_rows = []
                for pid in current_proposal_ids:
                    leg = batch["legs"].get(pid, {"state": "unattempted", "order": None, "error": None})
                    ticker = next(
                        (p["intent"]["ticker"] for p in st.session_state["allocation_proposals"] if p["proposal_id"] == pid),
                        pid,
                    )
                    leg_rows.append({
                        "Ticker": ticker,
                        "State": leg["state"],
                        "Order ID": (leg.get("order") or {}).get("order_id", ""),
                        "Detail": leg.get("error") or "",
                    })
                st.dataframe(leg_rows, use_container_width=True, hide_index=True)

        for proposal in st.session_state.get("allocation_proposals", []):
            _render_proposal_approval(proposal, store, policy_path, alloc_packet.portfolio)

    for ticker, result in watchlist_results.items():
        with st.container(border=True):
            st.subheader(ticker)
            if "error" in result:
                st.error(f"Could not look up {ticker}: {result['error']}")
                continue

            trend_str = result["own_trend"] or "unavailable (not enough history)"
            vol_str = f"{result['own_vol']:.2f}% trailing daily std" if result["own_vol"] is not None else "unavailable"
            current_price = result.get("current_price")
            if current_price is not None:
                st.metric("Current price", f"${current_price:,.2f}", help=f"Last close, as of {result['price_as_of']}")
            st.write(f"Own trend (200-day): **{trend_str}** -- Own volatility (20d/60d blend): **{vol_str}**")

            earnings = result.get("earnings") or {"available": False}
            if earnings.get("available"):
                st.write(
                    f"Next earnings: **{earnings['event_date']}** ({earnings['days_away']:+d} day(s)) -- "
                    "trading blocked within your policy's earnings-blackout window either side of this date."
                )
            else:
                st.caption("Next earnings date: unavailable.")

            price_history = result.get("price_history")
            if price_history is not None and not price_history.empty:
                st.line_chart(price_history, height=220, use_container_width=True)
                st.caption(f"Close price, last {len(price_history)} trading days ({price_history.index[0].date()} to {price_history.index[-1].date()}).")

            explanation = result["explanation"]
            if explanation["currently_held"] not in (None, "not_checked"):
                held = explanation["currently_held"]
                st.info(f"Currently held: {held['shares']} shares, ${held['market_value']:,.2f} ({held['unrealized_pnl_pct']:+.1f}%)")

            if result["price_targets"]:
                st.write("Recent analyst price targets by firm, vs. current price:")
                rows = []
                for p in result["price_targets"]:
                    row = {"Firm": p["firm"], "Target": p["price_target"], "As of": p["as_of"]}
                    if current_price:
                        row["vs. current"] = f"{(p['price_target'] / current_price - 1) * 100:+.1f}%"
                    rows.append(row)
                st.dataframe(rows, use_container_width=True, hide_index=True)
                if not current_price:
                    st.caption("Current price unavailable -- can't compute vs.-current comparison.")
            else:
                st.caption("No recent analyst price-target data available.")

            hold_range = result["hold_range"]
            if hold_range:
                st.write(
                    f"Historical {hold_range['hold_days']}-day hold range (n={hold_range['n_periods']} periods): "
                    f"**{hold_range['worst_pct']:+.1f}%** worst -- **{hold_range['median_pct']:+.1f}%** median -- "
                    f"**{hold_range['best_pct']:+.1f}%** best"
                )
                st.caption(
                    "Real historical range from this ticker's own price history -- every day used as a "
                    "starting point, not just favorable ones. Not a prediction of future performance."
                )
            else:
                st.caption("Not enough history to compute a hold-period range.")

            if result["news"]:
                st.write("Recent news:")
                if result["news_summary"]:
                    st.info(result["news_summary"])
                    st.caption("AI-generated summary of the headlines below -- not a price prediction or recommendation.")
                elif want_ai_summary and not ai_news_available:
                    st.caption("AI summary skipped -- ANTHROPIC_API_KEY not set.")
                for item in result["news"]:
                    st.write(f"- [{item['title']}]({item['url']}) -- {item['provider']}, {item['published']}")
            else:
                st.caption("No recent news found.")

            if explanation["triggered_today"]:
                st.write("Signals firing today:")
                for trig in explanation["triggered_today"]:
                    st.write(f"- **{trig['rule']}** ({trig['direction']}): return z={trig['return_zscore']}, volume z={trig['volume_zscore']}")
            else:
                st.caption("No predefined per-ticker signal fires on this today.")

            st.write("Recommended course of action:")
            ticker_specific = [e for e in explanation["historical_evidence"] if e["ticker_specific"]]
            project_wide = [e for e in explanation["historical_evidence"] if not e["ticker_specific"]]
            if ticker_specific:
                for e in ticker_specific:
                    # display_status (GPT review, 2026-07-29): never show
                    # a bare "[confirmed]" for a finding that hasn't been
                    # re-verified since the fetch_historical lookback-days
                    # fix -- see e['production_authoritative'].
                    st.write(f"**[{e['display_status']}]** {e['label']} -- {e['claim']}")
                    st.caption(e["detail"])
                    if e.get("dataset_warning"):
                        st.warning(e["dataset_warning"])
            else:
                st.info(
                    f"No {ticker}-specific research exists in this project. None of the tested signals have "
                    "validated edge for individual-stock picks -- see the general track record below for what's "
                    "actually been tried."
                )
            if project_wide:
                with st.expander(f"General signal-testing track record ({len(project_wide)} findings -- same for every stock, not specific to {ticker})"):
                    for e in project_wide:
                        st.write(f"**[{e['display_status']}]** {e['label']} -- {e['claim']}")
                        st.caption(e["detail"])
                        if e.get("dataset_warning"):
                            st.warning(e["dataset_warning"])
            st.caption(explanation["note"])

with tab_selling:
    st.caption(
        "\"Recommended to sell\" here means one thing specifically: this position currently "
        "breaks one of your policy's risk limits (too concentrated, too much leveraged-ETF "
        "exposure, etc.), computed the same deterministic way as the Propose & Approve tab. "
        "It is NOT a price prediction -- this project has confirmed zero signals as real edge "
        "for predicting which stocks will go down, so nothing here claims to know that."
    )

    policy, packet = _load_packet(policy_path, include_events=False)

    if not packet.portfolio.positions:
        st.info("No positions held -- nothing to evaluate for selling.")
    else:
        st.subheader("Current holdings")
        st.caption(
            "Entry price is a single WEIGHTED-AVERAGE cost basis across every buy of that ticker -- "
            "this is what Alpaca itself reports (avg_entry_price), not a per-lot breakdown. If you bought "
            "the same stock at different prices on different days, you will see one blended number here, "
            "not separate rows per purchase. This project does not yet track individual tax lots."
        )
        st.dataframe(
            [
                {
                    "Ticker": p.ticker,
                    "Shares": p.shares,
                    "Avg cost basis": p.entry_price,
                    "Current price": p.current_price,
                    "Unrealized P&L %": p.unrealized_pnl_pct,
                    "Market value": p.market_value,
                    "% of portfolio": round(p.market_value / packet.portfolio.total_equity * 100, 1) if packet.portfolio.total_equity else 0.0,
                }
                for p in packet.portfolio.positions
            ],
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("Recommended sells (policy-breach based)")
        if st.button("Check for recommended sells", type="primary"):
            sell_proposals = generate_risk_reduction_proposals(packet, policy)
            for p in sell_proposals:
                store.save_proposal(p.to_dict())
            st.session_state["sell_proposals"] = [p.to_dict() for p in sell_proposals]
            st.session_state["sell_checked_at"] = datetime.now().strftime("%H:%M:%S")

        sell_checked_at = st.session_state.get("sell_checked_at")
        sell_proposals = st.session_state.get("sell_proposals")
        if sell_proposals is None:
            st.info("Click \"Check for recommended sells\" above.")
        elif not sell_proposals:
            st.success(f"Checked at {sell_checked_at} -- no positions currently breach your policy limits.")
        else:
            st.write(f"Checked at {sell_checked_at} -- {len(sell_proposals)} recommended sell(s):")
            for proposal in sell_proposals:
                _render_proposal_approval(proposal, store, policy_path, packet.portfolio)

with tab_propose:
    policy, packet = _load_packet(policy_path, include_events)

    pair_labels = ", ".join(f"{p.stable_ticker}/{p.leveraged_ticker}" for p in CONFIGURED_LEVERAGED_PAIRS)
    check_strategy = st.checkbox(
        f"Also check leveraged-pair rebalance strategies ({pair_labels})",
        value=policy.enable_strategy_proposals,
        help="Each pair's evidence_status is shown per-proposal -- none are 'confirmed' -- "
        "see assistant/strategy_proposals.py",
    )

    if st.button("Check for proposals", type="primary"):
        proposals = generate_risk_reduction_proposals(packet, policy)
        if check_strategy:
            for pair_config in CONFIGURED_LEVERAGED_PAIRS:
                try:
                    proposals = proposals + generate_leveraged_pair_rebalance_proposals(
                        packet, policy, pair_config, store=store
                    )
                except MissingResearchDependencyError as exc:
                    st.error(
                        f"{pair_config.stable_ticker}/{pair_config.leveraged_ticker} strategy check failed "
                        f"({exc}); skipping this pair."
                    )
        for proposal in proposals:
            store.save_proposal(proposal.to_dict())
        st.session_state["current_proposals"] = [p.to_dict() for p in proposals]
        st.session_state["last_checked_at"] = datetime.now().strftime("%H:%M:%S")

    last_checked_at = st.session_state.get("last_checked_at")
    proposals = st.session_state.get("current_proposals")
    if proposals is None:
        st.info("Click \"Check for proposals\" above to see if anything needs your attention.")
    elif not proposals:
        st.success(
            f"Checked at {last_checked_at} -- no policy breaches"
            + (" and no strategy rebalance needed" if check_strategy else "")
            + " right now."
        )
    else:
        st.write(f"Checked at {last_checked_at} -- {len(proposals)} proposal(s):")

    for proposal in proposals or []:
        _render_proposal_approval(proposal, store, policy_path, packet.portfolio)

with tab_history:
    proposals_col, orders_col = st.columns(2)

    with proposals_col:
        st.subheader("Proposals")
        status_filter = st.selectbox("Status filter", ["(any)"] + list(STATUSES))
        proposal_limit = st.slider("Max rows", 5, 100, 20, key="proposal_history_limit")
        stored = store.list_proposals(status=None if status_filter == "(any)" else status_filter, limit=proposal_limit)
        if not stored:
            st.info("No proposals found in history.")
        else:
            st.dataframe(
                [
                    {
                        "Proposal ID": p["proposal_id"],
                        "Status": p["status"],
                        "Side": p["intent"]["side"],
                        "Shares": p["intent"]["shares"],
                        "Ticker": p["intent"]["ticker"],
                        "Evidence": p.get("evidence_status", ""),
                        "Expires": p["expires_at"],
                    }
                    for p in stored
                ],
                use_container_width=True,
                hide_index=True,
            )

        unresolved = [p for p in stored if p["status"] in MANUAL_RECONCILIATION_STATUSES]
        if unresolved:
            st.warning(
                f"{len(unresolved)} proposal(s) have an unresolved broker submission -- their outcome "
                "couldn't be confirmed at approval time. Reconcile against your actual Alpaca account "
                "before approving an equivalent trade."
            )
            for p in unresolved:
                intent = p["intent"]
                if st.button(
                    f"Reconcile {p['proposal_id']} ({intent['side'].upper()} {intent['shares']} {intent['ticker']}, currently {p['status']})",
                    key=f"reconcile_{p['proposal_id']}",
                ):
                    try:
                        order = reconcile_submission(p["proposal_id"], store)
                        refreshed = store.get_proposal(p["proposal_id"])
                        st.success(
                            f"Reconciled: found broker order {order['order_id']} -- "
                            f"proposal is now {refreshed['status']}."
                        )
                    except Exception as exc:
                        st.error(f"Reconciliation result: {exc}")

    with orders_col:
        st.subheader("Orders")
        order_limit = st.slider("Max rows", 5, 100, 20, key="order_history_limit")
        orders = store.list_broker_orders(limit=order_limit)
        if not orders:
            st.info("No orders submitted yet.")
        else:
            st.dataframe(
                [
                    {
                        "Order ID": o["order_id"],
                        "Broker status": o.get("status", o.get("order_status", "")),
                        "Side": (o.get("intent") or {}).get("side", o.get("side", "")),
                        "Shares": (o.get("intent") or {}).get("shares", o.get("shares", "")),
                        "Ticker": (o.get("intent") or {}).get("ticker", o.get("ticker", "")),
                        "Evidence": o.get("evidence_status", ""),
                        "Submitted": o["submitted_at"],
                    }
                    for o in orders
                ],
                use_container_width=True,
                hide_index=True,
            )
