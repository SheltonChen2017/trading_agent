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
    pwsh -NoProfile -File scripts/launch_dev_app.ps1

The launcher pins a disposable database and engages the environment kill
switch by default. Do not bypass it with a bare Streamlit command: this
checkout otherwise falls back to the operator database and shares the Alpaca
paper account with the frozen runtime. See HOW_TO_USE.md.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from assistant.kill_switch import env_kill_switch_active
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
from assistant.portfolio_rebalance import evaluate_portfolio_rebalance
from assistant.rebalance_trim import (
    generate_trim_proposal,
    overweight_sleeves as _rebalance_overweight_sleeves,
    untrimmable_overweight_sleeves as _rebalance_untrimmable_overweight,
)
from assistant.rebalance_steering import (
    eligible_sleeves as _rebalance_eligible_sleeves,
    generate_steering_proposals,
    steering_input_fingerprint as _steering_input_fingerprint,
)
from assistant.rebalance_profile import (
    OWNER_APPROVED_PROFILE,
    SLEEVE_LABELS,
    sleeve_membership as _rebalance_sleeve_membership,
)
from assistant.hedge_sleeve import (
    evaluate_hedge_sleeve,
    generate_hedge_buy_proposals,
)
from assistant.context_builder import build_decision_packet, build_portfolio_snapshot_from_alpaca, get_upcoming_events
from assistant.schemas import EvidenceStatus, UpcomingEvent
from risk.execution_gate import canonical_order_quantity
from assistant.corporate_actions import (
    tax_ledger_with_coverage,
    ticker_tax_ledger_with_coverage,
)
from assistant.execution_service import (
    PolicyOverridableBlockError,
    execute_approved_paper_proposal,
    reconcile_submission,
)
from assistant.order_reconciler import (
    cancel_all_open_orders,
    cancel_assistant_order,
)
from assistant.explanations import explain_ticker
from assistant.ai_advisor import (
    allocation_review_input_hash,
    curate_recommended_tickers,
    is_ai_advisor_configured,
    review_allocation_outcome,
    suggest_similar_tickers,
)
from assistant.news_summary import (
    fetch_recent_news,
    is_ai_summary_configured,
    summarize_news_for_ticker_with_reason,
)
from assistant.macro_context import build_descriptive_macro_context
from assistant.recommended_stocks import build_recommended_tickers, is_ipo_calendar_configured
from assistant.research_looks import (
    record_research_look,
    research_data_fingerprint,
    research_look_summary,
)
from assistant.runtime_identity import current_commit
from assistant.similarity_evidence import compute_similarity_evidence, format_evidence_summary
from assistant.ticker_verification import partition_by_universe, verify_tickers
from assistant.policy import (
    DEFAULT_POLICY_PATH,
    POLICY_PATH_ENV_VAR,
    compute_policy_fingerprint,
    load_policy,
    policy_with_updated_flags,
    resolve_policy_path,
    save_policy,
)
from assistant.llm import PrivacyMode, ProjectionError, ReviewStatus, project_committee_input
from assistant.llm.anthropic_provider import (
    AnthropicCommitteeProvider,
    is_anthropic_committee_configured,
    is_anthropic_committee_experiment_enabled,
)
from assistant.llm.committee_service import committee_input_hash, run_committee_review_and_record
from assistant.schemas import DecisionPacket
from assistant.portfolio_analytics import compute_portfolio_analytics
from assistant.proposal_status import (
    ACTIVE_BROKER_ORDER_STATUSES,
    BLOCKED,
    BROKER_EXPIRED,
    BROKER_REJECTED,
    CANCELED,
    DISMISSED,
    DISMISSIBLE_SOURCE_STATUSES,
    EXPIRED,
    FILLED,
    MANUAL_RECONCILIATION_STATUSES,
    OUTCOME_GROUPS,
    OUTCOME_OTHER_UNKNOWN,
    POLICY_OVERRIDE_AVAILABLE,
    PROPOSED,
    STATUSES,
    SUBMISSION_FAILED,
    UNRESOLVED_BROKER_STATE_STATUSES,
    VALIDATION_FAILED,
    outcome_group_for_status,
    statuses_for_outcome_groups,
)
from assistant.proposals import generate_risk_reduction_proposals
from assistant.user_directed_sell import (
    generate_user_directed_sell_proposal,
    remaining_shares_after_sale as _remaining_shares_after_sale,
    sellable_whole_shares as _sellable_whole_shares,
)
from assistant.money import decimal_or_none as _decimal_or_none
from assistant.money import decimal_text as _decimal_text
from assistant.tax_reporting import (
    TaxReportError,
    build_annual_tax_report,
    render_tax_report_csv,
    render_tax_report_json,
)
from assistant.portfolio_history import (
    capture_briefing_equity_snapshot,
    portfolio_performance_report,
)
from assistant.research_registry import summarize_evidence_authority, underfilled_dataset_warning
from assistant.risk_copilot import (
    check_concentration,
    check_policy_compliance,
    estimate_stress_impact,
    find_correlated_clusters,
    portfolio_risk_decomposition,
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
    # The two strategy exception types are deliberately no longer imported:
    # the handler below catches `Exception` (FCS-001), so naming a narrow pair
    # here would only invite someone to reinstate the narrow catch.
    generate_leveraged_pair_rebalance_proposals,
)
from config import (
    BASKETS,
    HEDGE_SLEEVE_TICKERS,
    HORIZON_LABELS,
    HORIZON_SWEEP_DAYS,
    LEVERAGED_ETF_TICKERS,
    LOOKBACK_DAYS,
    PAPER_TRADING,
    SLIPPAGE_PCT,
    UNIVERSE,
)
from backtest.engine import summarize_multi_horizon
from backtest.interactive import (
    CHART_CAPTION,
    EXPLORATORY_CAVEATS,
    INTERACTIVE_DIRECTION_CELLS,
    SIGNAL_INVENTORY,
    SYNTHETIC_CAVEAT,
    cumulative_return_frame,
    inspect_data_coverage,
    run_interactive_backtest,
)
from data.event_data import fetch_upcoming_earnings
from data.market_data import fetch_historical, generate_synthetic
from execution.alpaca_broker import is_configured
from market_analytics import classify_trend
from scripts.ui_theme import THEME_CSS

st.set_page_config(
    page_title="Trading Assistant",
    page_icon="\U0001F4C8",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Presentation only. THEME_CSS is a string constant: it cannot change a
# number, a validation, a policy decision, or an execution gate.
#
# The stylesheet itself lives in scripts/ui_theme.py, which carries the full
# rationale -- in particular WHY Alpaca's brand yellow is confined to chrome
# and never used for status, given that this page renders 38 st.warning and
# 35 st.error calls whose severity is load-bearing.
st.markdown(THEME_CSS, unsafe_allow_html=True)


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
        # GR-4: record the market-data fetch (success or failure) so
        # provider health and bar freshness are derived from evidence.
        store=_store(),
    )
    return policy, packet


@st.cache_data(ttl=_PACKET_CACHE_TTL_SECONDS)
def _load_live_events_for_tickers(tickers: tuple[str, ...]) -> list:
    """Optional live-earnings enrichment ONLY -- never rebuilds the
    portfolio/account/regime snapshot (GPT review, 2026-07-31). Cached
    separately (and much more cheaply -- this is a single earnings-
    calendar lookup, not an account/quote/regime fetch) so requesting
    events never triggers a second account fetch."""
    try:
        return get_upcoming_events(list(tickers), fetch_live=True)
    except Exception:
        # Last-resort presentation boundary. Context construction already
        # degrades known provider failures, but an unforeseen optional-event
        # bug must still not stop the Propose & Approve page before its
        # deterministic risk-reduction proposals are computed (CXL-003).
        return [
            UpcomingEvent(
                ticker=ticker,
                event_type="earnings",
                days_away=None,
                status=EvidenceStatus.UNAVAILABLE,
                source="optional_enrichment_failed",
            )
            for ticker in tickers
        ]


_HOLDING_ANALYSIS_CACHE_TTL_SECONDS = 300


@st.cache_data(ttl=_HOLDING_ANALYSIS_CACHE_TTL_SECONDS)
def _load_holding_analysis(ticker: str, regime_fields: tuple):
    """Per-holding trend/volatility + this project's own evidence for ONE
    ticker, as rendered by the Briefing tab's "Holdings analysis" panel.

    Cached for the same reason _load_recommended_tickers() is: this panel
    renders for EVERY held position, and the Briefing tab re-runs on every
    widget interaction anywhere in the app. Uncached, a 10-position
    portfolio cost ~20 yfinance round-trips per keystroke (two per
    position: one here for trend/volatility, and a second inside
    explain_ticker()). The history is now fetched ONCE and passed into
    explain_ticker(), and the whole result is cached per ticker.

    `regime_fields` is MarketRegime's primitive fields as a tuple rather
    than the dataclass itself, because MarketRegime isn't hashable and
    st.cache_data keys on arguments. Passing it through (instead of
    letting explain_ticker() default to None) is what stops explain_ticker
    from fetching benchmark data to rebuild a regime we already have.

    Returns a plain dict; `currently_held` is deliberately NOT requested
    here (the panel reads shares/market value straight off the position it
    is already iterating), so do not start reading that field from this
    cached result -- it would be "not_checked".
    """
    from assistant.schemas import MarketRegime

    benchmark_ticker, trend, volatility_regime, trailing_volatility_pct, as_of = regime_fields
    regime = MarketRegime(
        benchmark_ticker=benchmark_ticker, trend=trend, volatility_regime=volatility_regime,
        trailing_volatility_pct=trailing_volatility_pct, as_of=as_of,
    )
    history = fetch_historical([ticker], lookback_days=300)
    own_trend = own_vol = None
    if ticker in history and not history[ticker].empty:
        close = history[ticker]["close"]
        as_of_date = close.index[-1]
        own_trend = classify_trend(close, as_of_date, lookback_days=200)
        own_vol = compute_blended_volatility(close, as_of_date)
    explanation = explain_ticker(ticker, market_regime=regime, data=history)
    return {"trend": own_trend, "volatility": own_vol, "explanation": explanation}


def _regime_fields(regime) -> tuple:
    """MarketRegime as a hashable tuple, for use as a cache key."""
    return (
        regime.benchmark_ticker, regime.trend, regime.volatility_regime,
        regime.trailing_volatility_pct, regime.as_of,
    )


# Optional-AI feature preferences (docs/reference/UI_FEATURE_CONTROLS_DESIGN.md
# section 3.2). Session-state only, all default OFF (owner decision,
# 2026-08-02, recorded in docs/ACTION_PLAN_2026-08-02.md section 9). These are
# UI preferences, never authority: they decide whether an optional paid LLM
# surface is OFFERED; every call still requires the per-surface checkbox, its
# own explicit click, and a configured credential. Deterministic content is
# never affected by any of them.
_AI_MASTER_PREF_KEY = "ai_pref_master"
_AI_FEATURE_PREFS = (
    ("ai_pref_news_summaries", "Claude news summaries",
     "Summarizes displayed headlines; no proposal authority."),
    ("ai_pref_similar_tickers", "Claude similar-ticker suggestions",
     "Research candidates only; every ticker is verified against real market data."),
    ("ai_pref_allocation_commentary", "Claude allocation commentary",
     "Cannot alter deterministic weights."),
    ("ai_pref_committee", "Experimental investment committee",
     "Advisory only; ALSO requires ENABLE_EXPERIMENTAL_COMMITTEE=1 -- that "
     "release gate stays mandatory regardless of these preferences."),
)


def _ai_feature_enabled(pref_key: str) -> bool:
    """Master preference ANDed with the per-feature preference (owner
    decision d: master off means nothing AI is offered anywhere)."""
    return bool(st.session_state.get(_AI_MASTER_PREF_KEY, False)) and bool(
        st.session_state.get(pref_key, False)
    )


# Durable session preferences vs. widget state: these preference keys are
# read from pages OTHER than Settings & Features (Briefing, Buying, Propose,
# Ticker Suggestions, and the global sidebar). Under sidebar routing the
# Settings page only renders when selected, and Streamlit deletes a
# widget-backed session key on any rerun that does not render its widget --
# so if the checkboxes owned these keys directly, navigating away from
# Settings would silently reset every AI preference to off. Each checkbox
# therefore uses its own widget key, seeded from the durable key, and copies
# its value into the durable key on change.
def _pref_widget_key(pref_key: str) -> str:
    return "widget_" + pref_key


def _sync_pref_from_widget(pref_key: str) -> None:
    st.session_state[pref_key] = bool(
        st.session_state.get(_pref_widget_key(pref_key), False)
    )


# Streamlit removes a widget's key when that widget is not rendered. Sidebar
# routing therefore needs an explicit, narrow persistence boundary for benign
# page inputs that users reasonably expect to survive navigation. Self-
# assignment detaches these values from widget cleanup for the current rerun.
# Safety-sensitive confirmation text is intentionally absent: approval,
# override, bulk-submit, cancel, and emergency phrases must be retyped after
# leaving their page.
_PERSISTENT_PAGE_WIDGET_KEYS = (
    "watchlist_picked",
    "watchlist_typed",
    # Tickers added by clicking a most-active suggestion row. Benign page
    # input, exactly like the multiselect and the text box it sits beside:
    # it names candidates to research and buys nothing. The split, the
    # proposal, and the typed approval all remain separate explicit acts.
    "watchlist_from_suggestions",
    "allocation_max_weight_pct",
    "allocation_dollar_amount",
    "strategy_proposals_enabled",
    "proposal_outcome_filter",
    "proposal_status_filter",
    "proposal_history_limit",
    # UI-2d: archive-visibility checkboxes are benign filters. The
    # dismissal selection/reason/confirmation keys are deliberately absent:
    # a durable-mutation confirmation must be retyped after leaving the
    # page, exactly like approval/override/cancel phrases.
    "history_include_expired",
    "history_include_dismissed",
    "order_history_limit",
    "suggest_src_most_active",
    "suggest_src_recent_ipo",
    "suggest_src_ai",
    "suggest_seed_tickers",
    # Backtest page (UI-3): research configuration is benign page work.
    # Completed run RESULTS live in the non-widget "backtest_run" session
    # key and survive navigation without needing this whitelist.
    "bt_signal",
    "bt_data_source",
    "bt_scope",
    "bt_lookback_days",
    "bt_horizons",
) + tuple(
    # Per-signal parameter widgets, namespaced by signal so two signals
    # sharing a parameter name (with different bounds) can never collide
    # in session state.
    f"bt_param_{signal.key}_{param.name}"
    for signal in SIGNAL_INVENTORY
    for param in signal.params
)


def _preserve_page_widget_state(session_state) -> None:
    for key in _PERSISTENT_PAGE_WIDGET_KEYS:
        if key in session_state:
            session_state[key] = session_state[key]


_AI_PREF_OFF_HELP = (
    "Optional AI features are turned off. Enable them (and this specific "
    "feature) in the Settings & Features page."
)


@st.cache_data(ttl=_RECOMMENDED_STOCKS_CACHE_TTL_SECONDS)
def _load_recommended_tickers(
    held_tickers: tuple[str, ...],
    include_ai: bool = True,
    *,
    include_most_active: bool = True,
    include_recent_ipos: bool = True,
    include_ai_curation: bool = True,
):
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
    real, avoidable cost.

    `include_ai` is part of the cache key on purpose: toggling the AI
    preference must recompute rather than serve a cached result built under
    the other setting. When False, neither the suggestion call nor the
    curation call fires -- the preference prevents the paid calls, it does
    not merely hide their output."""
    recommended, dropped = build_recommended_tickers(
        list(held_tickers),
        store=store,
        include_most_active=include_most_active,
        include_recent_ipos=include_recent_ipos,
        include_ai_suggestions=include_ai,
    )
    curated_note = (
        curate_recommended_tickers(recommended, store=store)
        if recommended and include_ai and include_ai_curation
        else None
    )
    return recommended, dropped, curated_note


_POLICY_EDITOR_SOURCE_KEY = "policy_editor_source"


def _sync_policy_editor_state(session_state, policy_path: str, policy) -> bool:
    """Bind policy-editor widgets to the selected policy's exact content.

    Streamlit widget keys otherwise survive sidebar policy-path changes and
    external policy edits. That can make a true flag in the newly selected
    file render as false and look like an intentional pending change. Preserve
    an unsaved edit while the source identity is unchanged, but reset both
    controls and typed confirmation whenever the resolved path or fingerprint
    changes. Returns True when a reset occurred, for focused tests.
    """
    source = (
        str(Path(policy_path).resolve(strict=False)),
        compute_policy_fingerprint(policy),
    )
    if (
        session_state.get(_POLICY_EDITOR_SOURCE_KEY) == source
        # Under sidebar routing, Settings only renders when selected, and
        # Streamlit deletes widget-backed keys on reruns that skip them. An
        # unchanged source with missing editor keys therefore means the user
        # navigated away and back: re-seed from the persisted policy
        # (deliberately abandoning any unsaved edit) rather than letting the
        # checkboxes silently render their False defaults.
        and "policy_edit_allow_new_positions" in session_state
        and "policy_edit_enable_strategy" in session_state
        and "policy_edit_whole_shares_only" in session_state
        and "policy_edit_enforce_cash_reserve" in session_state
        and "policy_edit_cash_reserve_pct" in session_state
    ):
        return False
    session_state["policy_edit_allow_new_positions"] = policy.allow_new_positions
    session_state["policy_edit_enable_strategy"] = policy.enable_strategy_proposals
    session_state["policy_edit_whole_shares_only"] = policy.whole_shares_only
    # One authoritative number drives both controls: 0 means "no reserve".
    session_state["policy_edit_enforce_cash_reserve"] = policy.min_cash_reserve_pct > 0
    session_state["policy_edit_cash_reserve_pct"] = float(
        policy.min_cash_reserve_pct * 100 if policy.min_cash_reserve_pct > 0 else 10.0
    )
    session_state.pop("policy_edit_confirm_phrase", None)
    session_state[_POLICY_EDITOR_SOURCE_KEY] = source
    return True


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


@st.cache_data(ttl=_PACKET_CACHE_TTL_SECONDS)
def _load_readonly_portfolio():
    """Account snapshot for STRICTLY READ-ONLY reporting surfaces.

    Two constraints pull in opposite directions and both are real:

    * `_load_base_packet()` calls `build_decision_packet(store=_store())`,
      which records GR-4 `data_provider_fetches` evidence. A reporting page
      must not write, so those surfaces cannot use it (independent review,
      2026-08-06, GR7BREV-002 -- the same defect GR-7a's tax Build had).
    * But dropping the shared cache entirely reintroduces a live broker
      call on EVERY rerun of the page, and lets Reports disagree with
      Briefing about the same account in the same session -- precisely the
      invariant `_load_base_packet` was created to protect after two tabs
      were once found showing two different snapshots.

    Cached AND store-free satisfies both. It shares the packet TTL and is
    cleared by the same `st.cache_data.clear()` the Refresh buttons call,
    so a deliberate refresh still re-fetches.
    """
    from assistant.context_builder import build_portfolio_snapshot
    from assistant.sample_portfolio import SAMPLE_CASH, SAMPLE_POSITIONS
    from execution.alpaca_broker import is_configured

    if is_configured():
        return build_portfolio_snapshot_from_alpaca()
    return build_portfolio_snapshot(
        SAMPLE_POSITIONS, SAMPLE_CASH, source="manual", account_mode="manual"
    )


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
    digest() (ordinary Selling/Propose & Approve/per-ticker Buying
    cards) and _allocation_input_signature() (the Buying page's
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
    session_state.pop(f"committee_result_{proposal_id}", None)
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
      "dismissed"  -- archived by the operator (UI-2d): terminal,
                      never-broker-touched, never approval controls.
      "in_progress"-- claimed by an approval attempt elsewhere (validating/
                      approved): never approval controls, but not terminal.
    """
    if status in (PROPOSED, POLICY_OVERRIDE_AVAILABLE):
        return "approvable"
    if status == DISMISSED:
        # Must precede every fallback: a dismissed proposal rendered from a
        # stale session snapshot must never fall through to "in_progress"
        # (which reads as an active approval attempt) or show controls.
        return "dismissed"
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
            "the History page's Reconcile action (or `recover-stale` on the CLI if it's stuck in "
            "'reconciling') before approving an equivalent trade."
        )
    elif category == "dismissed":
        st.info(
            f"Dismissed {proposal.get('dismissed_at', '?')} by "
            f"{proposal.get('dismissed_by', '?')}: "
            f"{proposal.get('dismissed_reason', 'no reason recorded')}. "
            "Dismissed proposals remain in the local audit history and "
            "cannot be executed."
        )
    else:
        # in_progress: VALIDATING / APPROVED -- an approval attempt is
        # (or very recently was) actively claiming this proposal elsewhere.
        st.info(f"Status: {status} -- an approval attempt is currently in progress for this proposal.")


def _render_committee_result(result) -> None:
    """Renders one CommitteeResult -- either every CommitteeReview section, or
    an explicit "review unavailable" reason. Deliberately NOT silent on
    failure (unlike the Buying page's allocation-review checkbox): the ADR's
    own release-gate list requires a clear unavailable state in CLI/
    Streamlit, and this sits next to a sell the user may be about to
    approve, not a purchase-split comment."""
    with st.expander("Investment committee review", expanded=True):
        if result.status == ReviewStatus.REVIEW_UNAVAILABLE:
            st.warning(
                f"Review unavailable ({result.error_code}): "
                + (result.error_message or "no further detail.")
            )
            if result.issues:
                st.caption("Validation issues: " + "; ".join(str(issue) for issue in result.issues))
            return
        review = result.review
        st.write(f"**Verdict:** {review.verdict.value.replace('_', ' ')}")
        st.write(f"**Confidence:** {review.confidence_label.value} -- {review.confidence_basis.text}")
        st.write(review.summary.text)

        def _points(title: str, points) -> None:
            if points:
                st.write(f"**{title}:**")
                for point in points:
                    st.write(f"- {point.text} _(sources: {', '.join(point.source_ids)})_")

        _points("Supporting points", review.supporting_points)
        _points("Counterarguments", review.counterarguments)
        _points("Hidden risks", review.hidden_risks)
        _points("Data quality warnings", review.data_quality_warnings)
        _points("Invalidation conditions", review.invalidation_conditions)
        _points("Revision requests", review.revision_requests)
        st.caption(
            f"Provider: {result.provider_id}/{result.model_id} -- prompt {result.prompt_version}. "
            "Advisory only; does not change or block this proposal."
        )


def _cache_committee_result(
    session_state, proposal_id: str, input_hash: str, result
) -> None:
    """Bind a cached review to the exact projected facts it reviewed."""
    session_state[f"committee_result_{proposal_id}"] = {
        "input_hash": input_hash,
        "result": result,
    }


def _committee_result_for_input(
    session_state, proposal_id: str, input_hash: str
):
    """Return only a review produced for the current committee input.

    A DecisionPacket can refresh without changing proposal_id. Caching only by
    proposal ID previously displayed an old verdict beside new portfolio,
    policy, warning, or market facts. Legacy/unbound cache entries are removed
    rather than trusted.
    """
    key = f"committee_result_{proposal_id}"
    cached = session_state.get(key)
    if not isinstance(cached, dict) or cached.get("input_hash") != input_hash:
        session_state.pop(key, None)
        return None
    return cached.get("result")


def _submission_outcome_is_unresolved(store: AssistantStore, proposal_id: str) -> bool:
    """Did this attempt leave the broker outcome genuinely UNKNOWN? (FCS-018)

    Read from the durable status the kernel already wrote, never parsed out
    of the exception text -- `docs/SESSION_HANDOFF.md` and
    `execution_service`'s own history both make broker reconciliation the
    authority for an ambiguous submission, and a message string is not that.

    Fails toward "unresolved" when the proposal cannot be re-read: if we
    cannot tell, the operator must not be told the order definitely did not
    reach the broker.
    """
    try:
        current = store.get_proposal(proposal_id)
    except Exception:
        return True
    if current is None:
        return True
    return current.get("status") in UNRESOLVED_BROKER_STATE_STATUSES


def _render_submission_failure(
    store: AssistantStore, proposal_id: str, exc: Exception
) -> None:
    """Report a raising submit without over-claiming what the broker did."""
    if _submission_outcome_is_unresolved(store, proposal_id):
        st.error(
            f"**Order outcome UNKNOWN — do not resubmit.** {exc}"
        )
        st.warning(
            "The submission raised, but that does not prove the broker "
            "rejected it: the response can be lost after an order was "
            "accepted. This proposal is held in an unresolved state with its "
            "budget still reserved, and it keeps this ticker/side locked "
            "against a duplicate order. Reconcile it (Operations tab, or "
            "`reconcile-submission`) before taking any further action, and "
            "check the broker directly before placing this trade by hand."
        )
        return
    st.error(f"Order not submitted: {exc}")


def _render_proposal_approval(proposal: dict, store: AssistantStore, policy_path: str, portfolio, packet: DecisionPacket) -> None:
    """One proposal card with the typed-confirmation approve flow.
    Shared by the Selling, Propose & Approve, and Buying pages --
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
        st.session_state.pop(f"committee_result_{proposal_id}", None)
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
        st.session_state.pop(f"committee_result_{proposal_id}", None)
    is_stale = st.session_state.get(stale_key, False)
    if is_stale:
        st.session_state.pop(f"committee_result_{proposal_id}", None)
        st.warning(
            "This proposal's content, policy, or portfolio context has changed since it was last "
            "displayed -- the reasons/expected-impact below were computed against the OLD context and "
            "may no longer be accurate. Approval is disabled for this card; regenerate it (use this "
            "page's Check/refresh button) to get a current, actionable proposal."
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
        if not impact.get("projection_complete", True):
            unknown = ", ".join(impact.get("pending_buy_unknown_tickers", []))
            st.warning(
                "Pending buy value is unavailable"
                + (f" for {unknown}" if unknown else "")
                + "; actual cash may be lower and exposure may be higher."
            )

        # Independent review, 2026-07-31: assistant/llm/ (the "investment
        # committee" AI reviewer) was fully built, tested, and governed by
        # docs/ADR_INVESTMENT_COMMITTEE_BOUNDARY.md, but had zero real usage
        # anywhere -- no provider adapter, no persistence, no UI surface.
        # The committee is architecturally restricted (both by the ADR and
        # by project_committee_input()'s own hard checks) to exactly this
        # proposal shape: a deterministic risk-reduction sell. Gating on
        # that here, inside the shared function, means the button appears
        # correctly at all 3 call sites with no per-call-site duplication --
        # including "for free" correctness on Buying-page buy proposals
        # (never eligible) and the Propose & Approve tab's mixed sell/
        # strategy proposals (only the sells qualify).
        is_committee_eligible = (
            proposal.get("evidence_status") == "deterministic_risk_policy"
            and intent.get("side") == "sell"
        )
        if is_committee_eligible:
            committee_input = None
            committee_projection_error = None
            if not is_stale:
                try:
                    committee_input = project_committee_input(
                        packet, proposal, privacy_mode=PrivacyMode.PERCENTAGES_ONLY
                    )
                except ProjectionError as exc:
                    committee_projection_error = str(exc)
                except Exception:
                    committee_projection_error = (
                        "Committee input preparation failed unexpectedly."
                    )
            current_committee_hash = (
                committee_input_hash(committee_input)
                if committee_input is not None
                else None
            )
            provider_configured = is_anthropic_committee_configured()
            experiment_enabled = is_anthropic_committee_experiment_enabled()
            committee_pref_on = _ai_feature_enabled("ai_pref_committee")
            committee_available = (
                provider_configured
                and experiment_enabled
                and committee_pref_on
                and committee_input is not None
                and not is_stale
            )
            want_committee_review = st.checkbox(
                "Get an experimental investment committee review of this sell "
                "(real API call, real cost)",
                value=False,
                key=f"want_committee_{proposal_id}",
                disabled=not committee_available,
                help=(
                    "Advisory only -- cites only the deterministic facts already shown above; "
                    "never proposes a different trade."
                    if committee_available
                    else (
                        committee_projection_error
                        or (
                            "This proposal is stale; regenerate it before requesting a review."
                            if is_stale
                            else (
                                # The env release gate outranks the UI
                                # preference in this message chain: a user
                                # who has not set the gate should be told
                                # about the gate, not sent to Settings.
                                "The committee remains release-gated until its frozen replay "
                                "corpus is complete. Set ENABLE_EXPERIMENTAL_COMMITTEE=1 only "
                                "for supervised experimental use."
                                if provider_configured and not experiment_enabled
                                else (
                                    _AI_PREF_OFF_HELP
                                    if provider_configured and not committee_pref_on
                                    else "ANTHROPIC_API_KEY is not set."
                                )
                            )
                        )
                    )
                ),
            )
            if st.button(
                "Get committee review",
                key=f"committee_button_{proposal_id}",
                disabled=not want_committee_review or not committee_available,
            ):
                try:
                    result = run_committee_review_and_record(
                        committee_input,
                        AnthropicCommitteeProvider(),
                        store=store,
                        # Larger than run_committee_review()'s own 30.0
                        # default: this provider's response budget (16000
                        # tokens) is much bigger than ai_advisor.py's
                        # existing structured-output calls.
                        timeout_seconds=60.0,
                    )
                    _cache_committee_result(
                        st.session_state,
                        proposal_id,
                        current_committee_hash,
                        result,
                    )
                except Exception:
                    st.session_state[f"committee_result_{proposal_id}"] = None
                    st.error("Could not complete the committee review.")

            committee_result = (
                _committee_result_for_input(
                    st.session_state, proposal_id, current_committee_hash
                )
                if current_committee_hash is not None
                else None
            )
            if committee_result is not None:
                _render_committee_result(committee_result)

        tax_advisory = impact.get("tax_lot_advisory", {})
        with st.expander("Tax-lot advisory (never blocks this sell)"):
            if tax_advisory.get("available"):
                st.dataframe(
                    [
                        {
                            "Method": method.upper(),
                            "Realized P&L": detail["realized_pnl"],
                            "Short-term P&L": detail["short_term_pnl"],
                            "Long-term P&L": detail["long_term_pnl"],
                        }
                        for method, detail in tax_advisory["methods"].items()
                        if "error" not in detail
                    ],
                    width="stretch",
                    hide_index=True,
                )
                st.caption(
                    "Advisory bookkeeping only; your broker's tax records "
                    "and Form 1099-B are authoritative."
                )
            else:
                st.caption(
                    "Unavailable: "
                    + str(
                        tax_advisory.get(
                            "reason", "complete lot history is unavailable"
                        )
                    )
                    + ". The risk-reducing sell remains fully actionable."
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
                        kill_switch_active=env_kill_switch_active(),
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
                    # FCS-018. "Order not submitted" is a claim about the
                    # BROKER, and this handler cannot make it: a raising
                    # submit may mean the order was rejected, or it may mean
                    # the response was lost after the broker accepted it. The
                    # kernel is scrupulous about that distinction -- it leaves
                    # the proposal in `submission_unknown`, keeps the
                    # reservation, and raises a message that literally begins
                    # "Could not confirm whether the order ... was accepted".
                    # Prefixing that with "Order not submitted:" re-asserted
                    # the very thing nineteen review rounds refused to assert,
                    # in the one sentence a human actually reads before
                    # deciding what to do next.
                    #
                    # The durable status is the authority, not the exception
                    # text: the kernel has already written it before raising.
                    _render_submission_failure(store, proposal_id, exc)

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
                            kill_switch_active=env_kill_switch_active(),
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
                        # Correct as a definite negative: PolicyOverridableBlockError
                        # is raised by the gate BEFORE any broker contact.
                        st.error(f"Order not submitted: {exc}")
                    except Exception as exc:
                        st.session_state.pop(override_key, None)
                        st.session_state.pop(override_confirm_key, None)
                        # FCS-018, second site. The override submit path can
                        # reach the broker exactly like the ordinary one, so
                        # it can end ambiguous exactly like the ordinary one.
                        _render_submission_failure(store, proposal_id, exc)


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
    st.title("Trading Assistant")
    st.caption(
        "Deterministic portfolio research, proposal review, and paper-trading "
        "controls in one workspace."
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
        "Mode is read-only here. Live trading still requires an intentional "
        "configuration change outside the app."
    )

# Sidebar navigation (UI-2c) with the Watchlist tab renamed to "Buying"
# (UI-2a). This is a render-control change, not styling: under st.tabs every
# tab body executed on every rerun; under this routing only the selected
# page's body executes. Cross-page state must therefore live in non-widget
# session keys (see the durable-preference helpers), because Streamlit
# deletes a widget's session-state key on any rerun that does not render it.
_PAGE_LABELS = (
    "Briefing",
    "Budgeted Buying",
    "Discrete Buying",
    "Policy Based Selling",
    "Discrete Selling",
    "Hedging",
    "Portfolio Rebalancing",
    "Propose & Approve",
    "History",
    "Ticker Suggestions",
    "Backtest",
    "Reports",
    "Operations",
    "Settings & Features",
)

# Preserve the page an already-open browser was showing across the two label
# changes in TRADE-1. Streamlit otherwise replaces an option that no longer
# exists with the first radio item (Briefing), which makes a harmless deploy
# look as though the user's workflow disappeared. This runs before the widget
# is instantiated, so it is a safe session-state migration rather than a
# forbidden post-widget mutation.
_LEGACY_PAGE_LABELS = {
    "Buying": "Budgeted Buying",
    "Selling": "Policy Based Selling",
}
if st.session_state.get("nav_page") in _LEGACY_PAGE_LABELS:
    st.session_state["nav_page"] = _LEGACY_PAGE_LABELS[st.session_state["nav_page"]]

_preserve_page_widget_state(st.session_state)

with st.sidebar:
    st.header("Navigation")
    page = st.radio(
        "Page",
        _PAGE_LABELS,
        key="nav_page",
        label_visibility="collapsed",
    )
    st.divider()
    # Policy context is deliberately separated from navigation: choosing a
    # page never changes which policy file governs proposals, and vice versa.
    st.header("Settings")
    # Seeded from resolve_policy_path() so the owner's own policy loads
    # without retyping it every session. The resolved file is NAMED below
    # rather than merely applied: a default that silently decides which
    # policy governs proposals would be a hidden financial default, and
    # this policy is the more permissive of the two.
    try:
        _resolved_policy_path = resolve_policy_path()
        _policy_resolution_error = None
    except FileNotFoundError as exc:
        # A stray TRADING_ASSISTANT_POLICY must not make the app unloadable.
        # Continue the implicit chain (personal -> committed default) rather
        # than hard-coding the committed baseline and skipping my_policy.
        # use_env=False rather than popping the variable: os.environ is
        # process-global and shared across Streamlit's per-session threads.
        _policy_resolution_error = str(exc)
        _resolved_policy_path = resolve_policy_path(use_env=False)
    policy_path = st.text_input("Policy file", value=str(_resolved_policy_path))
    if _policy_resolution_error is not None:
        st.warning(
            f"{_policy_resolution_error} Falling back to "
            f"`{Path(_resolved_policy_path).name}`."
        )
    st.caption(f"Active file: `{Path(policy_path).name}`")
    # Default seeded from the Settings & Features preference; the per-run
    # choice here still wins once touched (design section 3.1: expose the
    # default centrally while retaining a per-run choice).
    include_events = st.checkbox(
        "Fetch live earnings events",
        value=bool(st.session_state.get("pref_include_events_default", False)),
    )
    if is_configured():
        st.success("Alpaca paper credentials: connected")
    else:
        st.warning("Alpaca not configured -- using sample portfolio")

store = _store()

# One compact, native page header keeps the visual hierarchy identical on
# every route. Detailed safety and evidence language remains in each page's
# own caption below; this layer only answers "where am I and what lives here?"
_PAGE_DESCRIPTIONS = {
    "Briefing": "Portfolio status, risk checks, evidence, and operational warnings.",
    "Budgeted Buying": "Research a ticker cart and split one budget by inverse volatility.",
    "Discrete Buying": "Create one owner-directed buy proposal by shares or dollar budget.",
    "Policy Based Selling": "Review sell proposals created only by policy breaches.",
    "Discrete Selling": "Create one owner-directed sell proposal by shares or dollar amount.",
    "Hedging": "Size a defensive ETF allocation toward a hedge target you set.",
    "Portfolio Rebalancing": "Read-only sleeve drift against the targets you approved.",
    "Propose & Approve": "Review deterministic proposals and apply the typed approval gate.",
    "History": "Inspect proposal and order outcomes without changing them.",
    "Ticker Suggestions": "Explore verified market-screen candidates with source disclosures.",
    "Backtest": "Run exploratory historical tests with explicit evidence limits.",
    "Reports": "Review portfolio, tax, and evidence reports.",
    "Operations": "Inspect reconciliation, readiness, and recovery state.",
    "Settings & Features": "Manage preferences and protected policy controls.",
}
with st.container(border=True):
    st.caption("TRADING WORKSPACE")
    st.header(page)
    st.caption(_PAGE_DESCRIPTIONS[page])

if page == "Briefing":
    if st.button("Refresh briefing", key="refresh_briefing"):
        st.cache_data.clear()
        st.toast("Refreshed against the live account.", icon="\U0001F503")
    # GR-5 severity routing (owner decision 2026-08-03): warnings batch into
    # the daily briefing instead of interrupting via desktop notification --
    # which makes THIS surface their delivery point, not an optional extra.
    from assistant.alert_delivery import pending_briefing_alerts as _briefing_alerts

    _batched_warnings = _briefing_alerts(_store())
    if _batched_warnings:
        with st.expander(
            f"⚠️ {len(_batched_warnings)} open operational warning(s) "
            "(batched here by policy)",
            expanded=False,
        ):
            for _warning_alert in _batched_warnings:
                st.warning(
                    f"[{_warning_alert['category']}] {_warning_alert['message']} "
                    f"(x{_warning_alert['occurrences']}, "
                    f"last {_warning_alert['last_seen_at'][:19]})"
                )
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
        try:
            captured_history = capture_briefing_equity_snapshot(
                store,
                packet.portfolio,
                captured_at=packet.generated_at,
            )
            st.session_state["portfolio_history_report"] = (
                portfolio_performance_report(
                    store, captured_history["account_key"]
                )
            )
            st.session_state.pop("portfolio_history_error", None)
        except Exception as exc:
            # A benchmark/history problem must never make the live account
            # briefing unavailable.
            st.session_state["portfolio_history_error"] = str(exc)
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
    history_report = st.session_state.get("portfolio_history_report")
    if isinstance(history_report, dict) and history_report.get("available"):
        benchmark_bits = [
            (
                f"{ticker} {details['total_return_pct']:+.2f}% "
                f"(excess {details['excess_return_pct']:+.2f} pp)"
            )
            for ticker, details in history_report.get("benchmarks", {}).items()
            if details.get("available")
        ]
        st.caption(
            f"Account total return since {history_report['start_session']}: "
            f"**{history_report['total_return_pct']:+.2f}%**; "
            f"max drawdown **{history_report['max_drawdown_pct']:.2f}%**"
            + (f"; {'; '.join(benchmark_bits)}" if benchmark_bits else "")
        )
    elif st.session_state.get("portfolio_history_error"):
        st.caption(
            "Portfolio history unavailable: "
            + st.session_state["portfolio_history_error"]
        )

    with st.container(border=True):
        st.subheader(f"Market regime ({packet.regime.benchmark_ticker})")
        st.write(f"Trend: **{packet.regime.trend or 'unavailable'}** / Volatility: **{packet.regime.volatility_regime or 'unavailable'}**"
                 + (f" (trailing {packet.regime.trailing_volatility_pct}% daily std, as of {packet.regime.as_of})" if packet.regime.trailing_volatility_pct is not None else ""))

    with st.container(border=True):
        st.subheader("Risk exposure")
        risk_col1, risk_col2, risk_col3 = st.columns(3)
        risk_col1.metric("Largest single position", f"{packet.risk.largest_single_position_pct}%")
        risk_col2.metric("Leveraged ETF exposure", f"{packet.risk.leveraged_etf_exposure_pct}%")
        risk_col3.metric("Invested", f"{packet.analytics['invested_pct']:.1f}%")
        if packet.risk.basket_exposure_pct:
            st.write("Basket exposure (overlapping, doesn't sum to 100%):")
            st.dataframe(
                [{"Basket": b, "% of equity": pct} for b, pct in sorted(packet.risk.basket_exposure_pct.items(), key=lambda kv: -kv[1])],
                width="stretch",
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
    with st.expander("Descriptive macro context"):
        st.caption(
            "Credit/yield proxies are shown as context only. Their predictive "
            "signal claims are rejected and cannot influence proposals."
        )
        if st.button("Load macro context", key="load_macro_context"):
            st.session_state["macro_context"] = (
                build_descriptive_macro_context()
            )
        macro_context = st.session_state.get("macro_context")
        if isinstance(macro_context, dict):
            if not macro_context.get("available"):
                st.warning(macro_context.get("reason", "Unavailable"))
            else:
                for indicator in macro_context["indicators"]:
                    st.write(
                        f"**{indicator['label']}**: "
                        f"{indicator['direction']} "
                        f"(20-session change "
                        f"{indicator['change_20_sessions']:+.4f}, "
                        f"60-session z-score "
                        f"{indicator['z_score_60_sessions']})"
                    )
    with st.expander("Empirical portfolio risk decomposition"):
        st.caption(
            "Uses explicitly date-aligned finite daily returns. Positive "
            "correlation clusters identify holdings behaving like one bet."
        )
        if st.button("Compute portfolio risk", key="run_portfolio_risk"):
            st.session_state["portfolio_risk_decomposition"] = (
                portfolio_risk_decomposition(packet.portfolio)
            )
        decomposition = st.session_state.get(
            "portfolio_risk_decomposition"
        )
        if isinstance(decomposition, dict):
            if not decomposition.get("available"):
                st.warning(decomposition.get("reason", "Unavailable"))
            else:
                risk_a, risk_b, risk_c = st.columns(3)
                risk_a.metric(
                    "Portfolio beta",
                    (
                        f"{decomposition['portfolio_beta']:.2f}"
                        if decomposition["portfolio_beta"] is not None
                        else "n/a"
                    ),
                )
                risk_b.metric(
                    "Annualized volatility",
                    f"{decomposition['annualized_volatility_pct']:.2f}%",
                )
                risk_c.metric(
                    "Aligned observations",
                    decomposition["common_observations"],
                )
                st.dataframe(
                    decomposition["contributions"],
                    width="stretch",
                    hide_index=True,
                )
                for cluster in decomposition["correlated_clusters"]:
                    st.warning(
                        f"Empirical correlated cluster: "
                        f"{', '.join(cluster['tickers'])} "
                        f"({cluster['combined_weight_pct']:.2f}% of equity)."
                    )
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
                st.dataframe(stress_result["position_impacts"], width="stretch", hide_index=True)

    # GR-4 definition of done: stale data must render as a VISIBLE
    # degradation banner, never as confident numbers. The packet builder
    # prefixes every data-staleness warning with "DATA DEGRADED:", which
    # is the contract this banner keys on.
    _degraded = [w for w in packet.warnings if w.startswith("DATA DEGRADED:")]
    if _degraded:
        for _degradation in _degraded:
            st.error(f"🚨 {_degradation}")

    if packet.warnings:
        with st.container(border=True):
            st.subheader("Warnings")
            for warning in packet.warnings:
                st.warning(warning)

    with st.container(border=True):
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
                width="stretch",
                hide_index=True,
            )
            st.caption(f"Unrealized P&L: ${packet.analytics['unrealized_pnl']:,.2f}")
        else:
            st.subheader("Positions")
            st.caption("No positions held.")

    if packet.portfolio.positions:
        with st.container(border=True):
            st.subheader("Holdings analysis")
            st.caption(
                "Per-position trend/volatility and this project's own evidence-labeled findings for each "
                "ticker you actually hold -- not a price prediction, just what's known and what currently "
                "applies to your account."
            )
            for position in packet.portfolio.positions:
                with st.container(border=True):
                    st.write(f"**{position.ticker}** -- {position.shares:g} sh, ${position.market_value:,.2f} ({position.unrealized_pnl_pct:+.1f}% unrealized)")
                    # One cached call per ticker for BOTH the trend/volatility
                    # figures and the evidence lookup -- see
                    # _load_holding_analysis() for why this must not re-fetch on
                    # every rerun.
                    try:
                        analysis = _load_holding_analysis(position.ticker, _regime_fields(packet.regime))
                    except Exception as exc:
                        st.caption(f"Could not load trend/volatility/evidence: {exc}")
                        continue
                    trend_str = analysis["trend"] or "unavailable"
                    vol = analysis["volatility"]
                    vol_str = f"{vol:.2f}% trailing daily std" if vol is not None else "unavailable"
                    st.write(f"Trend (200-day): **{trend_str}** -- Volatility (20d/60d blend): **{vol_str}**")

                    explanation = analysis["explanation"]
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
            st.caption("For price targets, news, and the full history/best-worst range for any holding, look it up in the Buying page.")

    if packet.portfolio.open_orders:
        with st.container(border=True):
            st.subheader("Open orders")
            st.dataframe(packet.portfolio.open_orders, width="stretch", hide_index=True)

    if packet.upcoming_events:
        with st.container(border=True):
            st.subheader("Upcoming events")
            for event in sorted(packet.upcoming_events, key=lambda e: e.event_date or "~"):
                if event.event_date:
                    st.write(f"**{event.ticker}**: {event.event_type} on {event.event_date} ({event.days_away} day(s)) [{event.status.value}]")
                else:
                    st.caption(f"{event.ticker}: {event.event_type} date unavailable [{event.status.value}]")

    if packet.signals:
        with st.container(border=True):
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
    with st.container(border=True):
        st.subheader("Recommended stocks to explore (not held, not a proposal)")
        st.caption(
            "Purely informational/exploratory -- these are NOT held positions and NOT trade proposals. "
            "Presence here is NOT an allocation authorization (same convention as config.DEFENSIVE_CARRY_TICKERS). "
            "\"Most actively traded\" reflects trading VOLUME and price movement, NOT buy-vs-sell order flow -- "
            "no legitimate retail-accessible data source provides true order imbalance."
        )
        st.caption(
            "Verification: every ticker shown resolved against real market data "
            "as a named US-listed equity. Rows are NOT screened on size, age, "
            "price, or liquidity (owner decision, 2026-08-12); unavailable or "
            "below-usual measurements are disclosed on the row instead."
        )
        if st.button("Refresh recommended stocks", key="refresh_recommended"):
            _load_recommended_tickers.clear()
        held_tickers_tuple = tuple(sorted({p.ticker.upper() for p in packet.portfolio.positions}))
        briefing_ai_on = _ai_feature_enabled("ai_pref_similar_tickers")
        recommended_tickers, dropped_candidates, curated_note = _load_recommended_tickers(
            held_tickers_tuple, briefing_ai_on
        )
        if dropped_candidates:
            # Name them. A bare count could not distinguish "we filtered out
            # junk" from "we filtered out the day's second most-traded stock"
            # -- which is exactly how the 2026-08-12 SPCX omission stayed
            # invisible until the owner diffed this list against yfinance by
            # hand. Screening here is identity only (see
            # SUGGESTION_DISCLOSURE_POLICY), so a drop is now a real failure
            # to identify the symbol, not a judgment about its size.
            st.caption(
                f"{len(dropped_candidates)} candidate ticker(s) omitted -- could "
                "not be verified at this time as a named US-listed equity: "
                + ", ".join(sorted(set(dropped_candidates)))
                + "."
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
                elif category == "ai_suggested" and not briefing_ai_on:
                    st.caption(
                        "Claude suggestions are off (optional AI features are disabled -- "
                        "enable them in Settings & Features)."
                    )
                elif category == "ai_suggested" and not held_tickers_tuple:
                    st.caption("No current holdings to base similarity suggestions on.")
                continue
            with st.expander(f"{label} ({len(items)})"):
                st.dataframe(
                    [{"Ticker": r.ticker, "Detail": r.detail} for r in items],
                    width="stretch",
                    hide_index=True,
                )

        if curated_note:
            st.caption(
                "AI commentary on the list above -- unverified prose, not a validated fact or a "
                "recommendation. Cross-check against the tables above before acting on it."
            )
            st.info(curated_note)

if page == "Budgeted Buying":
    st.caption(
        "Add tickers to your cart, then check them for: own trend/volatility, "
        "recent analyst price targets by firm, recent news, a REAL historical "
        "best/worst hold-period return range, and this project's own "
        "evidence-labeled signal history. **No probability-of-return number "
        "is shown anywhere.** This project has confirmed zero signals as real "
        "edge after rigorous out-of-sample testing (see the Briefing page's "
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

    # --- Third cart source: pick from the most-active screen ---------------
    # Owner request 2026-08-13. The same verified most-active rows the Ticker
    # Suggestions tab shows, made clickable here so a candidate can go
    # straight into the cart.
    #
    # Two properties this section must keep, because it moves a DISCLOSURE
    # surface into a buying flow:
    #
    # 1. Network calls happen only on an explicit click, never on page load —
    #    the same rule the Ticker Suggestions tab states for itself. The
    #    shared cached loader is reused, so a run just made on that tab costs
    #    nothing here.
    # 2. Every row's `detail` is rendered NEXT TO its own Add button. That
    #    text carries the AP-8 eligibility disclosures (below the usual
    #    60-session, $5.00, or $1M median-dollar-volume floors) which exist
    #    precisely because the owner asked to see these names rather than
    #    have them screened out. Hiding them at the moment of choosing would
    #    quietly convert "here is what the market did" into "here is what to
    #    buy", which is the one thing this surface must never become.
    _suggestion_picks = list(st.session_state.get("watchlist_from_suggestions", []))
    with st.expander("Or pick from ticker suggestions (most-active screen)"):
        st.caption(
            "The same verified most-active rows as the Ticker Suggestions "
            "tab, split by today's price direction. Adding one puts it in "
            "your cart to research -- it buys nothing, and this project is "
            "not recommending it. Volume is not a buy/sell split: every share "
            "traded was bought by someone and sold by someone else, and no "
            "strategy here has confirmed predictive evidence."
        )
        if st.button(
            "Show most-active suggestions",
            key="watchlist_suggestions_run",
            help="Runs the market screen and verification pass. Network calls "
            "happen only when you click this -- never on page load.",
        ):
            try:
                # This page has no module-level `packet` -- that name belongs
                # to the Briefing block, which does not execute when Buying is
                # the selected page. Load it here, the same way the rest of
                # this page does.
                _, _sug_packet = _load_packet(policy_path, include_events=False)
                _sug_rows, _sug_dropped, _ = _load_recommended_tickers(
                    tuple(
                        sorted(
                            {p.ticker.upper() for p in _sug_packet.portfolio.positions}
                        )
                    ),
                    include_ai=False,
                    include_most_active=True,
                    include_recent_ipos=False,
                    include_ai_curation=False,
                )
                st.session_state["watchlist_suggestion_rows"] = [
                    r for r in _sug_rows if r.reason_category == "most_active"
                ]
                st.session_state["watchlist_suggestion_dropped"] = list(_sug_dropped)
                st.session_state["watchlist_suggestion_ran_at"] = datetime.now(
                    timezone.utc
                ).isoformat(timespec="seconds")
            except Exception as _sug_exc:
                st.session_state["watchlist_suggestion_rows"] = None
                st.error(
                    "Could not load suggestions "
                    f"({type(_sug_exc).__name__}). Nothing was added to your cart."
                )

        _sug_rows_state = st.session_state.get("watchlist_suggestion_rows")
        if _sug_rows_state is None:
            st.caption('Click "Show most-active suggestions" to load them.')
        elif not _sug_rows_state:
            st.caption("No most-active candidate passed verification on that run.")
        else:
            _row_fetch_times = sorted(
                {
                    str(getattr(_row, "fetched_at", "")).strip()
                    for _row in _sug_rows_state
                    if str(getattr(_row, "fetched_at", "")).strip()
                }
            )
            if len(_row_fetch_times) == 1:
                _source_time = f"Source data fetched at {_row_fetch_times[0]}. "
            elif _row_fetch_times:
                _source_time = (
                    "Source rows were fetched between "
                    f"{_row_fetch_times[0]} and {_row_fetch_times[-1]}. "
                )
            else:
                _source_time = "No verified row carries a source fetch time. "
            st.caption(
                _source_time
                + f"Displayed at {st.session_state.get('watchlist_suggestion_ran_at')}. "
                "Provider data may be cached for up to "
                f"{_RECOMMENDED_STOCKS_CACHE_TTL_SECONDS // 60} minutes, so prices "
                "and volumes may lag the live market."
            )
            _up = [r for r in _sug_rows_state if r.price_direction == "advancing"]
            _down = [r for r in _sug_rows_state if r.price_direction == "declining"]
            _flat = [r for r in _sug_rows_state if r.price_direction == "unchanged"]
            _unknown = [r for r in _sug_rows_state if r.price_direction is None]

            def _render_suggestion_add_row(_row) -> None:
                """Keep disclosure and the corresponding cart control together."""
                _in_cart = _row.ticker in _suggestion_picks
                if st.button(
                    f"Add {_row.ticker}" if not _in_cart else f"{_row.ticker} in cart",
                    key=f"watchlist_sug_add_{_row.ticker}",
                    disabled=_in_cart,
                ):
                    _suggestion_picks.append(_row.ticker)
                    st.session_state["watchlist_from_suggestions"] = list(
                        dict.fromkeys(_suggestion_picks)
                    )
                    st.rerun()
                st.caption(f"{_row.ticker}: {_row.detail}")

            _left, _right = st.columns(2)
            for _col, _subset, _heading in (
                (_left, _up, "Most active — price up today"),
                (_right, _down, "Most active — price down today"),
            ):
                with _col:
                    st.markdown(f"**{_heading}** ({len(_subset)})")
                    if not _subset:
                        st.caption("None on this run.")
                    for _row in _subset:
                        _render_suggestion_add_row(_row)
            for _subset, _heading in (
                (_flat, "Most active — price unchanged today"),
                (_unknown, "Most active — price change unavailable"),
            ):
                if _subset:
                    st.markdown(f"**{_heading}** ({len(_subset)})")
                    for _row in _subset:
                        _render_suggestion_add_row(_row)
            _dropped = st.session_state.get("watchlist_suggestion_dropped") or []
            if _dropped:
                st.caption(
                    f"{len(_dropped)} candidate(s) could not be verified at this "
                    "time and are not shown: " + ", ".join(sorted(_dropped)) + "."
                )

    cart = list(dict.fromkeys(picked + typed_tickers + _suggestion_picks))

    if cart:
        st.write(f"**Cart:** {', '.join(cart)}")
        if _suggestion_picks:
            # Name the provenance in the cart itself. Once a ticker is a bare
            # symbol in a list it is indistinguishable from one the owner
            # chose deliberately, and these arrived from a screen that
            # deliberately does NOT apply the project's usual size, age, and
            # liquidity floors.
            st.caption(
                "From the most-active screen: "
                + ", ".join(_suggestion_picks)
                + " -- that screen is not filtered on size, age, price, or "
                "liquidity, so re-read each row's detail above before buying."
            )
            if st.button(
                "Clear suggestion picks", key="watchlist_suggestions_clear"
            ):
                st.session_state["watchlist_from_suggestions"] = []
                st.rerun()

    ai_news_available = is_ai_summary_configured() and _ai_feature_enabled(
        "ai_pref_news_summaries"
    )
    want_ai_summary = st.checkbox(
        "Summarize news with Claude (real API call, small real cost per ticker)",
        value=False,
        disabled=not ai_news_available,
        help=(
            "Requires ANTHROPIC_API_KEY to be set. Off by default -- headlines "
            "are shown either way; this only adds an AI-written summary of them."
            if ai_news_available
            else (
                _AI_PREF_OFF_HELP
                if is_ai_summary_configured()
                else "ANTHROPIC_API_KEY is not set -- showing raw headlines only."
            )
        ),
    )
    ai_advisor_configured = is_ai_advisor_configured()
    similar_available = ai_advisor_configured and _ai_feature_enabled(
        "ai_pref_similar_tickers"
    )
    want_similar_suggestions = st.checkbox(
        "Get Claude's own ticker suggestions, with measured comparison (real API call, small real cost)",
        value=False,
        disabled=not similar_available,
        help=(
            "Claude picks tickers from its own knowledge -- this is NOT a validated "
            "similarity engine. Every suggestion is checked against real market data "
            "before being shown, and paired with a measured correlation/sector-overlap "
            "column so you can see whether the data actually backs up Claude's stated reason."
            if similar_available
            else (
                _AI_PREF_OFF_HELP
                if ai_advisor_configured
                else "ANTHROPIC_API_KEY is not set."
            )
        ),
    )
    allocation_review_available = ai_advisor_configured and _ai_feature_enabled(
        "ai_pref_allocation_commentary"
    )
    want_allocation_review = st.checkbox(
        "Get an AI review of the purchase split with Claude (real API call, small real cost)",
        value=False,
        disabled=not allocation_review_available,
        help=(
            "Advisory commentary only -- never changes the computed weights below. "
            "Requires 2+ tickers checked together."
            if allocation_review_available
            else (
                _AI_PREF_OFF_HELP
                if ai_advisor_configured
                else "ANTHROPIC_API_KEY is not set."
            )
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
                # `data=data` reuses the history fetched just above rather
                # than making explain_ticker() fetch the same bars again --
                # halves the yfinance round-trips for a multi-ticker cart
                # check (independent review, 2026-07-29).
                explanation = explain_ticker(
                    ticker, portfolio=watchlist_packet.portfolio,
                    market_regime=watchlist_packet.regime, data=data,
                )
                price_targets = latest_price_targets_by_firm(ticker)
                hold_range = historical_hold_period_range(ticker, data, hold_days=20)
                news = fetch_recent_news(ticker)
                news_summary, news_summary_reason = (
                    summarize_news_for_ticker_with_reason(ticker, news)
                    if want_ai_summary
                    else (None, None)
                )
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
                    "news_summary_reason": news_summary_reason,
                    "earnings": earnings_by_ticker.get(ticker, {"available": False}),
                }
            except Exception as exc:
                results[ticker] = {"error": str(exc)}
        st.session_state["watchlist_results"] = results
        # Bind every deterministic result, split, and proposal input below to
        # the exact cart that was checked.  The cart can change on any rerun
        # (including an Add button in the suggestion picker), while the
        # expensive result dict otherwise persists in session state.
        st.session_state["watchlist_results_cart"] = sorted(
            {ticker.upper() for ticker in cart}
        )

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
                    # The exact cart these suggestions and their measured
                    # evidence were computed against (counter-review
                    # AP9CR-002) -- compared on every rerun below.
                    "cart": sorted({t.upper() for t in cart}),
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
    _current_cart_identity = sorted({ticker.upper() for ticker in cart})
    if (
        watchlist_results
        and st.session_state.get("watchlist_results_cart")
        != _current_cart_identity
    ):
        # Fail closed for legacy state with no identity as well as an ordinary
        # cart edit.  Otherwise old prices/volatilities can keep producing a
        # split and approve-gated proposals for a ticker the current cart no
        # longer contains, or omit a ticker the cart now claims to analyze.
        st.warning(
            "The cart changed since you checked it. The old analysis, split, "
            "and proposal controls are hidden because they describe the "
            "previous cart. Click **Check cart** to refresh them."
        )
        st.session_state["watchlist_results"] = {}
        st.session_state["watchlist_results_cart"] = None
        watchlist_results = {}

    ai_suggestions = st.session_state.get("watchlist_ai_suggestions")
    # Counter-review AP9CR-002 -- the same stale-state defect AP9R-001 fixed
    # one block below, in the block directly above it: these suggestions and
    # their measured-evidence columns were computed against the cart at
    # Check-cart time, but the expander header interpolates the CURRENT cart.
    # Edit the cart without re-clicking and old evidence renders under a
    # header naming tickers it was never measured against. A stored state
    # with no cart key (legacy) fails safe as stale.
    if ai_suggestions and ai_suggestions.get("cart") != sorted({t.upper() for t in cart}):
        st.warning(
            "The cart changed since Claude suggested these tickers. The old "
            "suggestions are hidden because their measured comparisons were "
            "computed against the previous cart. Click **Check cart** to "
            "request fresh suggestions."
        )
        ai_suggestions = None
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
                    width="stretch", hide_index=True,
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
                    width="stretch", hide_index=True,
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
            width="stretch",
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

        baskets_by_ticker = {
            t: [name for name, tickers in BASKETS.items() if t in tickers]
            for t in weights
        }
        current_review_input_hash = allocation_review_input_hash(
            list(weights.keys()), weights, vols, baskets_by_ticker
        )
        if check_cart_clicked and want_allocation_review:
            st.session_state["watchlist_ai_review_outcome"] = review_allocation_outcome(
                list(weights.keys()), weights, vols, baskets_by_ticker, store=store
            )
        elif not want_allocation_review:
            st.session_state["watchlist_ai_review_outcome"] = None

        outcome = st.session_state.get("watchlist_ai_review_outcome")
        # Owner-reported 2026-08-12: this used to render NOTHING when the
        # review came back rejected -- identical to never having asked. Two
        # real reviews were discarded that afternoon (554- and 670-character
        # summaries against an undocumented 500-character cap, since removed)
        # and the page stayed blank both times, so the feature was
        # indistinguishable from one that was switched off. Say what happened.
        outcome_matches_split = (
            outcome is not None
            and getattr(outcome, "input_hash", None) == current_review_input_hash
        )
        if outcome is not None and not outcome_matches_split:
            st.warning(
                "The split changed since Claude reviewed it. The old review is "
                "hidden because its checked numbers no longer describe the split "
                "above. Click **Check cart** to request a fresh review."
            )
        elif outcome is not None and outcome.review is None:
            st.warning(
                "Claude's review of this split was requested but is not being "
                f"shown. {outcome.rejection_reason} The split above is "
                "unaffected -- it is computed by this project's own code and "
                "never depended on the AI review."
            )
        ai_review = outcome.review if outcome_matches_split else None
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
                        width="stretch", hide_index=True,
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
        allocation_granularity = (
            "whole-share" if alloc_policy.whole_shares_only
            else "fractional-share (up to 9 decimals)"
        )

        with balance_col:
            st.metric("Remaining balance after this purchase", f"${available_cash - planned_spend:,.2f}")
            st.caption(
                f"Reflects the actual {allocation_granularity} plan below. Quantity rounding and any "
                "ticker whose allocation cannot buy the minimum quantity can leave more cash than a "
                "raw percentage split would."
            )

        if plan:
            unallocated = dollar_amount - planned_spend
            st.write(
                f"Requested: **${dollar_amount:,.2f}** -- Planned spend: **${planned_spend:,.2f}** -- "
                f"Unallocated: **${unallocated:,.2f}** (cap headroom, quantity rounding, and/or a "
                "ticker allocation below the minimum permitted quantity)."
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
                f"**Projected final weight if you approve this split** (matches the ACTUAL {allocation_granularity} plan "
                "that would be proposed -- includes existing holdings and known pending buy orders; this is "
                "where you'd catch adding to an already-large position, or an allocation too small to buy "
                "the minimum permitted quantity):"
            )
            st.dataframe(plan_rows, width="stretch", hide_index=True)

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
                minimum_label = (
                    "1 whole share"
                    if alloc_policy.whole_shares_only
                    else "the 0.000000001-share minimum"
                )
                st.warning(
                    f"No proposals generated -- the amount may be too small to buy {minimum_label} of any "
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
                        kill_switch_active=env_kill_switch_active(),
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
                    kill_switch_active=env_kill_switch_active(),
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
                st.dataframe(leg_rows, width="stretch", hide_index=True)

        for proposal in st.session_state.get("allocation_proposals", []):
            _render_proposal_approval(proposal, store, policy_path, alloc_packet.portfolio, alloc_packet)

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
                st.line_chart(price_history, height=220, width="stretch")
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
                st.dataframe(rows, width="stretch", hide_index=True)
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
                elif result.get("news_summary_reason"):
                    # A refusal must SAY it refused. Showing nothing made
                    # "disabled", "call failed" and "the output guard withheld
                    # this" indistinguishable, so a working control read as a
                    # broken feature (owner report, 2026-08-07). The reason is
                    # a fixed label; the withheld prose is never shown.
                    st.caption(f"AI summary unavailable -- {result['news_summary_reason']}.")
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

    # --- Three-sleeve M3: dividend-funded reinvestment (earmarked) ----------
    # Rendering is READ-ONLY (derived dispositions only); durable earmark
    # transitions and the proposal write happen exclusively inside the
    # button handler. Every proposal still goes through the identical
    # approve-gated pipeline -- this section never submits anything.
    with st.expander("Dividend reinvestment (three-sleeve M3)"):
        from assistant.sleeve_reinvest import (
            SleeveReinvestError as _SleeveReinvestError,
        )
        from assistant.sleeve_reinvest import (
            dividend_reinvest_status as _dividend_reinvest_status,
        )
        from assistant.sleeve_reinvest import (
            generate_dividend_reinvest_proposal as _generate_reinvest_proposal,
        )
        from assistant.sleeve_reinvest import (
            reconcile_dividend_earmarks as _reconcile_dividend_earmarks,
        )

        st.caption(
            "Confirmed dividend income can fund one approve-gated purchase "
            "proposal at a time: pending decline-review adds first, an "
            "owner-chosen leveraged reinvest candidate only when nothing is "
            "pending (plan section 1.1). Owner preference, not research. "
            "Nothing is bought until you approve the proposal yourself."
        )
        _reinvest_status = None
        try:
            _reinvest_status = _dividend_reinvest_status(store)
        except _SleeveReinvestError as _reinvest_exc:
            st.warning(f"Dividend pool unavailable: {_reinvest_exc}")
        except Exception as _reinvest_exc:
            st.warning(
                "Dividend pool unavailable "
                f"({type(_reinvest_exc).__name__})."
            )
        if _reinvest_status is not None:
            _col_a, _col_b, _col_c = st.columns(3)
            _col_a.metric("Available", f"${_reinvest_status['available_total']}")
            _col_b.metric(
                "Confirmed income", f"${_reinvest_status['confirmed_income_total']}"
            )
            _col_c.metric("Route", _reinvest_status["route"])
            st.caption(_reinvest_status["note"])
            for _pending in _reinvest_status["pending_decline_reviews"]:
                st.write(
                    f"- Pending dip-add: **{_pending['ticker']}** "
                    f"({_pending['kind']})"
                )
            for _earmark in _reinvest_status["earmarks"]:
                _drift = (
                    ""
                    if _earmark["effective_disposition"] == _earmark["status"]
                    else (
                        f" -- effective: {_earmark['effective_disposition']} "
                        "(awaiting reconcile)"
                    )
                )
                st.caption(
                    f"Earmark {_earmark['proposal_id']}: "
                    f"${_earmark['amount_text']} {_earmark['route']} "
                    f"{_earmark['ticker']} -- {_earmark['status']}{_drift}"
                )

            _eligible = _reinvest_status["eligible_tickers"]
            _available_float = float(_reinvest_status["available_total"])
            if not _eligible:
                st.info("No eligible ticker right now.")
            elif _available_float <= 0:
                st.info("The dividend pool has no available dollars right now.")
            else:
                _reinvest_ticker = st.selectbox(
                    "Eligible ticker", _eligible, key="sleeve_reinvest_ticker"
                )
                _reinvest_amount = st.number_input(
                    "Amount from the dividend pool ($)",
                    min_value=0.0,
                    max_value=_available_float,
                    value=0.0,
                    step=1.0,
                    key="sleeve_reinvest_amount",
                )
                if st.button(
                    "Create dividend-funded purchase proposal",
                    disabled=_reinvest_amount <= 0,
                    key="sleeve_reinvest_create",
                ):
                    from assistant.sleeve_notifications import (
                        _recorded_close_fetcher as _sleeve_close_fetcher,
                    )

                    try:
                        for _transition in _reconcile_dividend_earmarks(store):
                            st.caption(
                                f"Earmark {_transition['proposal_id']}: "
                                f"{_transition['action']} ({_transition['reason']})"
                            )
                        _close_by_ticker = _sleeve_close_fetcher(store)(
                            [_reinvest_ticker]
                        )
                        _reinvest_price = _close_by_ticker.get(_reinvest_ticker)
                        if _reinvest_price is None:
                            st.error(
                                "No fresh recorded close is available for "
                                f"{_reinvest_ticker}; not proposing blind."
                            )
                        else:
                            _reinvest_policy, _reinvest_packet = _load_packet(
                                policy_path, include_events=False
                            )
                            _reinvest_result = _generate_reinvest_proposal(
                                _reinvest_packet, _reinvest_policy,
                                store, ticker=_reinvest_ticker,
                                amount=str(_reinvest_amount),
                                price=_reinvest_price,
                            )
                            if _reinvest_result["created"]:
                                _created = _reinvest_result["proposal"]
                                st.success(
                                    f"Proposed {_created.intent.shares} shares of "
                                    f"{_created.intent.ticker} "
                                    f"(${_reinvest_result['earmark_amount_text']} "
                                    "earmarked). Approve it on the Propose & "
                                    "Approve page -- nothing has been bought."
                                )
                            else:
                                st.error(f"Refused: {_reinvest_result['reason']}")
                    except _SleeveReinvestError as _reinvest_exc:
                        st.error(f"Refused: {_reinvest_exc}")
                    except Exception as _reinvest_exc:
                        st.error(
                            "Proposal creation failed "
                            f"({type(_reinvest_exc).__name__})."
                        )

if page == "Policy Based Selling":
    st.caption(
        "\"Recommended to sell\" here means one thing specifically: this position currently "
        "breaks one of your policy's risk limits (too concentrated, too much leveraged-ETF "
        "exposure, etc.), computed the same deterministic way as the Propose & Approve page. "
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
            "the same stock at different prices on different days, you will see one blended number here. "
            "When the app's fill history fully reconciles to current shares, recommended sells show a "
            "separate advisory FIFO/LIFO/HIFO tax-lot comparison."
        )
        # Independent review, 2026-07-31 (P2 #9): this used to compute
        # "% of portfolio" inline instead of sourcing it from
        # assistant/portfolio_analytics.py -- the one arithmetic
        # expression in the Selling tab not sourced from assistant/*.py,
        # which is what the "no separate logic between CLI and UI" design
        # otherwise guarantees everywhere else.
        position_weights_pct = compute_portfolio_analytics(packet.portfolio)["position_weights_pct"]
        st.dataframe(
            [
                {
                    "Ticker": p.ticker,
                    "Shares": p.shares,
                    "Avg cost basis": p.entry_price,
                    "Current price": p.current_price,
                    "Unrealized P&L %": p.unrealized_pnl_pct,
                    "Market value": p.market_value,
                    "% of portfolio": position_weights_pct.get(p.ticker, 0.0),
                }
                for p in packet.portfolio.positions
            ],
            width="stretch",
            hide_index=True,
        )

        st.subheader("Recommended sells (policy-breach based)")
        if st.button("Check for recommended sells", type="primary"):
            tax_ledger, tax_coverage = tax_ledger_with_coverage(
                store, packet.portfolio
            )
            sell_proposals = generate_risk_reduction_proposals(
                packet,
                policy,
                tax_lot_ledger=tax_ledger,
                tax_lot_coverage=tax_coverage,
            )
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
                _render_proposal_approval(proposal, store, policy_path, packet.portfolio, packet)

# ---------------------------------------------------------------------------
# Discrete trading (owner request 2026-08-14)
#
# "Budgeted Buying" splits ONE budget across a cart by inverse volatility;
# "Policy Based Selling" acts only on a computed policy breach. These two
# pages are the owner's own single-name decisions, and they are deliberately
# SEPARATE pages rather than sections of those, so an owner-directed order
# never inherits the framing of a budget split or a computed breach.
#
# Both offer the same two sizing modes. The active policy determines whether
# the exact share quantity must be whole or may have up to nine decimal places.
# Dollar mode remains a BUDGET, not a broker-notional order: it is converted
# once, in exact Decimal, by assistant.discrete_trade, rounded down at the
# active granularity, and any unspent remainder is stated.
#
# Neither page submits anything: each creates one ordinary proposal that
# still needs the typed approval phrase and a fresh execution-gate pass.
# ---------------------------------------------------------------------------


def _discrete_reference_price(store, ticker: str):
    """Fresh recorded close for one ticker, through the GR-4 lineage path.

    Returns (price_decimal, error_text). A missing or stale close is an
    explicit refusal, never a guess: sizing a trade against an unknown price
    is exactly how a dollar amount turns into the wrong share count.
    """
    from assistant.sleeve_notifications import _recorded_close_fetcher

    try:
        prices = _recorded_close_fetcher(store)([ticker])
    except Exception as exc:  # provider/network failure must not crash the page
        return None, f"Could not fetch a price for {ticker} ({type(exc).__name__})."
    price = prices.get(ticker)
    if price is None:
        return None, (
            f"No fresh recorded close is available for {ticker}, so this trade "
            "cannot be priced. Nothing was proposed."
        )
    return price, None


def _select_discrete_buy_ticker(ticker: str) -> None:
    """Fill the ticker widget from a suggestion before Streamlit reruns.

    A normal ``if st.button(): session_state[widget_key] = ...`` handler runs
    after the text input with that key has already been created and Streamlit
    rejects the mutation. Button callbacks run first, which makes the picker
    reliable while preserving the ordinary editable text input.
    """
    st.session_state["discrete_buy_ticker"] = ticker


def _render_discrete_sizing(
    mode_key: str,
    amount_key: str,
    price,
    *,
    max_shares=None,
    whole_shares_only: bool = True,
):
    """Shared shares/dollars control pair. Returns (shares, note) or (None, None).

    One helper for both pages so the two tabs cannot drift into describing
    the same arithmetic differently.
    """
    from assistant.discrete_trade import notional_for_shares, size_by_dollar_amount
    from risk.execution_gate import canonical_order_quantity, order_quantity_decimal

    mode = st.segmented_control(
        "Size this trade by",
        ("Share count", "Dollar amount"),
        default="Share count",
        key=mode_key,
        width="stretch",
    )
    if mode is None:
        # Counter-review TRADE1CR-001: st.segmented_control lets the user
        # DESELECT the active option, so this can be None -- a state the
        # st.radio it replaced could not produce. Falling through would
        # render the dollar input while the control showed nothing selected,
        # i.e. the page behaving as one mode while claiming none. Size
        # nothing until a mode is chosen.
        st.caption("Choose how to size this trade to continue.")
        return None, None

    if mode == "Share count":
        if whole_shares_only:
            shares = int(st.number_input(
                "Shares",
                min_value=1,
                max_value=int(max_shares) if max_shares else None,
                value=1,
                step=1,
                key=amount_key + "_shares",
            ))
        else:
            raw_shares = st.text_input(
                "Shares",
                value="1",
                key=amount_key + "_fractional_shares",
                help="Enter an exact quantity with at most 9 decimal places.",
            )
            shares = canonical_order_quantity(
                raw_shares, whole_shares_only=False
            )
            if shares is None:
                st.error(
                    "Enter a positive share quantity with at most 9 decimal places."
                )
                return None, None
            if max_shares is not None:
                requested = order_quantity_decimal(
                    shares, whole_shares_only=False
                )
                held = _decimal_or_none(max_shares)
                if held is None or requested > held:
                    st.warning(
                        f"You hold {_decimal_text(held or 0)} share(s). "
                        "Nothing is proposed because the requested quantity would short the position."
                    )
                    return None, None
        priced = notional_for_shares(
            shares, price, whole_shares_only=whole_shares_only
        )
        if not priced["ok"]:
            st.error(priced["reason"])
            return None, None
        return shares, (
            f"{shares} share(s) at ${float(price):,.2f} = "
            f"**${float(priced['notional_text']):,.2f}**."
        )

    dollars = st.number_input(
        "Dollar amount ($)", min_value=0.0, value=0.0, step=50.0, key=amount_key + "_dollars"
    )
    if dollars <= 0:
        return None, None
    sized = size_by_dollar_amount(
        str(dollars), price, whole_shares_only=whole_shares_only
    )
    if not sized["ok"]:
        st.warning(sized["reason"])
        return None, None
    sizing = sized["sizing"]
    sized_quantity = order_quantity_decimal(
        sizing.shares, whole_shares_only=whole_shares_only
    )
    held_quantity = _decimal_or_none(max_shares) if max_shares is not None else None
    if max_shares is not None and (
        held_quantity is None or sized_quantity > held_quantity
    ):
        st.warning(
            f"${dollars:,.2f} is more than you hold. Capping at {_decimal_text(held_quantity or 0)} "
            "share(s) would change the amount you asked for, so nothing is "
            "proposed -- lower the amount or switch to share count."
        )
        return None, None
    granularity = "whole share(s)" if whole_shares_only else "share(s)"
    note = (
        f"${dollars:,.2f} buys **{sizing.shares} {granularity}** at "
        f"${float(sizing.reference_price_text):,.2f} = "
        f"${float(sizing.notional_text):,.2f}. "
        f"**${float(sizing.unallocated_text):,.2f} is left over**. "
        + (
            "Whole-share mode rounds down, so a dollar amount is a budget, not a broker-notional order."
            if whole_shares_only
            else "Fractional mode rounds down to Alpaca's 9-decimal quantity limit; this remains a quantity order, not a broker-notional order."
        )
    )
    return sizing.shares, note


if page == "Discrete Buying":
    st.caption(
        "Buy one ticker you choose, sized by share count or by dollar budget. "
        "This project is NOT recommending anything here and does not predict "
        "prices -- it has confirmed zero signals as real edge for "
        "individual-stock selection. Nothing is bought until you approve the "
        "proposal by typing the phrase, and your policy limits are re-checked "
        "at that moment."
    )
    _db_policy, _db_packet = _load_packet(policy_path, include_events=False)

    _db_ticker = st.text_input(
        "Ticker to buy", key="discrete_buy_ticker", placeholder="e.g. NVDA"
    ).strip().upper()

    # Same suggestion mechanism as Budgeted Buying (BUY-1): explicit click,
    # shared cached verification pipeline, each row's AP-8 disclosure shown
    # beside its own button.
    with st.expander("Or pick from ticker suggestions (most-active screen)"):
        st.caption(
            "The same verified most-active rows as the Ticker Suggestions tab. "
            "Picking one only fills the ticker box above -- it buys nothing. "
            "Volume is not a buy/sell split, and this screen is NOT filtered "
            "on size, age, price, or liquidity."
        )
        if st.button(
            "Show most-active suggestions",
            key="discrete_buy_suggestions_run",
            help="Network calls happen only when you click this.",
        ):
            try:
                _db_rows, _db_dropped, _ = _load_recommended_tickers(
                    tuple(sorted({p.ticker.upper() for p in _db_packet.portfolio.positions})),
                    include_ai=False,
                    include_most_active=True,
                    include_recent_ipos=False,
                    include_ai_curation=False,
                )
                st.session_state["discrete_buy_suggestions"] = [
                    r for r in _db_rows if r.reason_category == "most_active"
                ]
                st.session_state["discrete_buy_suggestion_dropped"] = list(
                    _db_dropped
                )
                st.session_state["discrete_buy_suggestion_ran_at"] = datetime.now(
                    timezone.utc
                ).isoformat(timespec="seconds")
            except Exception as _db_exc:
                st.session_state["discrete_buy_suggestions"] = None
                st.error(
                    f"Could not load suggestions ({type(_db_exc).__name__}). "
                    "Nothing was selected."
                )
        _db_sugs = st.session_state.get("discrete_buy_suggestions")
        if _db_sugs is None:
            st.caption('Click "Show most-active suggestions" to load them.')
        elif not _db_sugs:
            st.caption("No most-active candidate passed verification on that run.")
        else:
            _db_fetch_times = sorted(
                {
                    str(getattr(_row, "fetched_at", "")).strip()
                    for _row in _db_sugs
                    if str(getattr(_row, "fetched_at", "")).strip()
                }
            )
            if len(_db_fetch_times) == 1:
                _db_source_time = f"Source data fetched at {_db_fetch_times[0]}. "
            elif _db_fetch_times:
                _db_source_time = (
                    "Source rows were fetched between "
                    f"{_db_fetch_times[0]} and {_db_fetch_times[-1]}. "
                )
            else:
                _db_source_time = "No verified row carries a source fetch time. "
            st.caption(
                _db_source_time
                + "Displayed at "
                f"{st.session_state.get('discrete_buy_suggestion_ran_at')}. "
                "Provider data may be cached for up to "
                f"{_RECOMMENDED_STOCKS_CACHE_TTL_SECONDS // 60} minutes, so "
                "prices and volumes may lag the live market."
            )
            _db_up = [r for r in _db_sugs if r.price_direction == "advancing"]
            _db_down = [r for r in _db_sugs if r.price_direction == "declining"]
            _db_other = [
                r for r in _db_sugs if r.price_direction not in ("advancing", "declining")
            ]
            _dbl, _dbr = st.columns(2)
            for _dbcol, _dbsubset, _dbhead in (
                (_dbl, _db_up, "Most active — price up today"),
                (_dbr, _db_down, "Most active — price down today"),
            ):
                with _dbcol:
                    st.markdown(f"**{_dbhead}** ({len(_dbsubset)})")
                    if not _dbsubset:
                        st.caption("None on this run.")
                    for _dbrow in _dbsubset:
                        st.button(
                            f"Use {_dbrow.ticker}",
                            key=f"discrete_buy_pick_{_dbrow.ticker}",
                            on_click=_select_discrete_buy_ticker,
                            args=(_dbrow.ticker,),
                        )
                        st.caption(f"{_dbrow.ticker}: {_dbrow.detail}")
            for _dbrow in _db_other:
                st.button(
                    f"Use {_dbrow.ticker}",
                    key=f"discrete_buy_pick_{_dbrow.ticker}",
                    on_click=_select_discrete_buy_ticker,
                    args=(_dbrow.ticker,),
                )
                st.caption(f"{_dbrow.ticker}: {_dbrow.detail}")
            _db_dropped = st.session_state.get(
                "discrete_buy_suggestion_dropped"
            ) or []
            if _db_dropped:
                st.caption(
                    f"{len(_db_dropped)} candidate(s) could not be verified at "
                    "this time and are not shown: "
                    + ", ".join(sorted(_db_dropped))
                    + "."
                )

    if not _db_ticker:
        st.info("Enter a ticker above, or pick one from the suggestions.")
    else:
        _db_price, _db_price_error = _discrete_reference_price(store, _db_ticker)
        if _db_price_error:
            st.error(_db_price_error)
        else:
            st.caption(
                f"Reference price for {_db_ticker}: ${float(_db_price):,.2f} "
                "(latest recorded close, freshness-checked)."
            )
            _db_shares, _db_note = _render_discrete_sizing(
                "discrete_buy_mode", "discrete_buy", _db_price,
                whole_shares_only=_db_policy.whole_shares_only,
            )
            if _db_note:
                st.markdown(_db_note)
            if st.button(
                f"Create buy proposal for {_db_ticker}",
                type="primary",
                disabled=not _db_shares,
                key="discrete_buy_create",
            ):
                from assistant.allocation_proposals import generate_discrete_buy_proposal

                _db_result = generate_discrete_buy_proposal(
                    _db_packet, _db_policy, ticker=_db_ticker,
                    shares=_db_shares, price=_db_price,
                )
                if _db_result["created"]:
                    store.save_proposal(_db_result["proposal"].to_dict())
                    st.session_state["discrete_buy_proposal"] = _db_result[
                        "proposal"
                    ].to_dict()
                else:
                    st.session_state.pop("discrete_buy_proposal", None)
                    st.error(_db_result["reason"])

            _db_proposal = st.session_state.get("discrete_buy_proposal")
            if _db_proposal:
                # Bind the stored proposal to the current ticker AND size, the
                # same stale-state rule AP-9/SELL-1 established: an actionable
                # card must never look synchronized with inputs it does not
                # represent.
                if (
                    _db_proposal["intent"]["ticker"] != _db_ticker
                    or _db_shares is None
                    or _db_proposal["intent"]["shares"] != _db_shares
                ):
                    _db_current_selection = (
                        "the current controls do not describe a valid trade"
                        if _db_shares is None
                        else (
                            f"the current {_db_shares}-share selection for "
                            f"{_db_ticker}"
                        )
                    )
                    st.info(
                        f"A buy proposal for {_db_proposal['intent']['shares']} "
                        f"share(s) of {_db_proposal['intent']['ticker']} is waiting "
                        "on the Propose & Approve page. It does not match "
                        f"{_db_current_selection}; create a new proposal to see "
                        "it here."
                    )
                else:
                    _render_proposal_approval(
                        _db_proposal, store, policy_path,
                        _db_packet.portfolio, _db_packet,
                    )


if page == "Discrete Selling":
    st.caption(
        "Sell part or all of one holding, for your own reasons, sized by share "
        "count or by dollar amount. This project is NOT recommending it and "
        "does not predict price declines -- it has confirmed zero signals as "
        "real edge for that. This is also NOT the policy-breach path: nothing "
        "here says a rule was broken. The sale becomes an ordinary proposal "
        "that you approve by typing the phrase, and your policy limits are "
        "re-checked at that moment."
    )
    _ds_policy, _ds_packet = _load_packet(policy_path, include_events=False)

    if not _ds_packet.portfolio.positions:
        st.info("No positions held -- there is nothing to sell.")
    else:
        _ds_held_quantity = {
            p.ticker: p.shares_exact if p.shares_exact is not None else p.shares
            for p in _ds_packet.portfolio.positions
        }
        _ds_sellable = {
            ticker: (
                _sellable_whole_shares(quantity)
                if _ds_policy.whole_shares_only
                else _decimal_or_none(quantity)
            )
            for ticker, quantity in _ds_held_quantity.items()
        }
        _ds_options = [
            t for t, n in _ds_sellable.items() if n is not None and n > 0
        ]
        # SET1CR-001: under "Whole shares only" the sellable quantity is
        # FLOORED, so a holding of 0.5 shares floors to 0 and disappears from
        # this page entirely -- no row, no warning, no way to sell it. Stock
        # you own must never silently vanish from the one page that sells it.
        # The remedy is authorized and already exists (turn the setting off),
        # so the honest thing is to name both the holding and the remedy.
        _ds_hidden = [
            (ticker, _decimal_or_none(quantity))
            for ticker, quantity in _ds_held_quantity.items()
            if ticker not in _ds_options
            and _decimal_or_none(quantity) is not None
            and _decimal_or_none(quantity) > 0
        ]
        if _ds_hidden:
            st.warning(
                "Held below one whole share and therefore not sellable while "
                "**Whole shares only** is on: "
                + ", ".join(
                    f"{ticker} ({_decimal_text(quantity)})"
                    for ticker, quantity in _ds_hidden
                )
                + ". Turn that setting off in Settings & Features to close "
                "these positions."
            )
        if not _ds_options:
            st.info("No holding currently has a policy-permitted share quantity available to sell.")
        else:
            _ds_ticker = st.selectbox(
                "Holding to sell", _ds_options, key="discrete_sell_ticker"
            )
            _ds_max = _ds_sellable[_ds_ticker]
            _ds_position = next(
                p for p in _ds_packet.portfolio.positions if p.ticker == _ds_ticker
            )
            _ds_quantity_label = (
                f"{_ds_max} whole share(s)"
                if _ds_policy.whole_shares_only
                else f"{_decimal_text(_ds_max)} sellable share(s)"
            )
            st.caption(
                f"You hold {_ds_quantity_label} of {_ds_ticker} at a current "
                f"price of ${float(_ds_position.current_price):,.2f}."
            )
            # SET1CR-001: the same floor, one level down. With 10.5 held the
            # line above says "10 whole share(s)", which is not what the owner
            # holds. Selling all 10 then reports "closes the position" while
            # 0.5 remains. State the remainder and how to release it.
            _ds_exact_held = _decimal_or_none(_ds_held_quantity[_ds_ticker])
            _ds_stranded = (
                _ds_exact_held - _ds_max
                if _ds_policy.whole_shares_only
                and _ds_exact_held is not None
                and _ds_exact_held > _ds_max
                else None
            )
            if _ds_stranded:
                st.caption(
                    f"A further {_decimal_text(_ds_stranded)} share(s) are "
                    "held but cannot be sold while **Whole shares only** is "
                    "on. Turn that setting off in Settings & Features to "
                    "close the position completely."
                )
            _ds_price = (
                _ds_position.current_price_exact
                if _ds_position.current_price_exact is not None
                else _ds_position.current_price
            )
            _ds_shares, _ds_note = _render_discrete_sizing(
                "discrete_sell_mode", "discrete_sell",
                _ds_price, max_shares=_ds_max,
                whole_shares_only=_ds_policy.whole_shares_only,
            )
            if _ds_note:
                st.markdown(_ds_note)
            if _ds_shares:
                _ds_remaining = _remaining_shares_after_sale(
                    _ds_held_quantity[_ds_ticker], _ds_shares,
                    whole_shares_only=_ds_policy.whole_shares_only,
                )
                st.caption(
                    "Selling this quantity closes the position."
                    if _ds_remaining == 0
                    else f"{_decimal_text(_ds_remaining)} share(s) would remain."
                )
            if st.button(
                f"Create sell proposal for {_ds_ticker}",
                type="primary",
                disabled=not _ds_shares,
                key="discrete_sell_create",
            ):
                _ds_ledger, _ds_coverage = tax_ledger_with_coverage(
                    store, _ds_packet.portfolio
                )
                _ds_result = generate_user_directed_sell_proposal(
                    _ds_packet, _ds_policy, ticker=_ds_ticker, shares=_ds_shares,
                    tax_lot_ledger=_ds_ledger, tax_lot_coverage=_ds_coverage,
                )
                if _ds_result["created"]:
                    store.save_proposal(_ds_result["proposal"].to_dict())
                    st.session_state["discrete_sell_proposal"] = _ds_result[
                        "proposal"
                    ].to_dict()
                else:
                    st.session_state.pop("discrete_sell_proposal", None)
                    st.error(_ds_result["reason"])

            _ds_proposal = st.session_state.get("discrete_sell_proposal")
            if _ds_proposal:
                if (
                    _ds_proposal["intent"]["ticker"] != _ds_ticker
                    or _ds_shares is None
                    or _ds_proposal["intent"]["shares"] != _ds_shares
                ):
                    _ds_current_selection = (
                        "the current controls do not describe a valid trade"
                        if _ds_shares is None
                        else (
                            f"the current {_ds_shares}-share selection for "
                            f"{_ds_ticker}"
                        )
                    )
                    st.info(
                        f"A sell proposal for {_ds_proposal['intent']['shares']} "
                        f"share(s) of {_ds_proposal['intent']['ticker']} is waiting "
                        "on the Propose & Approve page. It does not match "
                        f"{_ds_current_selection}; create a new proposal to see "
                        "it here."
                    )
                else:
                    _render_proposal_approval(
                        _ds_proposal, store, policy_path,
                        _ds_packet.portfolio, _ds_packet,
                    )


def _hedge_reference_prices(store, tickers):
    """Fresh recorded closes for the hedge basket, plus what is missing.

    Returns ``(prices, unavailable)``. A missing or malformed close is
    DISCLOSED and blocks the selected basket, never guessed at -- dropping a
    leg and redistributing its allocation would silently change the owner's
    chosen basket.
    """
    from assistant.sleeve_notifications import _recorded_close_fetcher

    names = list(tickers)
    if not names:
        return {}, []
    try:
        fetched = _recorded_close_fetcher(store)(names)
    except Exception as exc:  # provider/network failure must not crash the page
        return {}, [f"{name} ({type(exc).__name__})" for name in names]
    prices = {}
    unavailable = []
    for name in names:
        price = _decimal_or_none(fetched.get(name))
        if price is None or price <= 0:
            unavailable.append(name)
        else:
            prices[name] = price
    return prices, unavailable


if page == "Hedging":
    st.caption(
        "Size a DEFENSIVE allocation toward a hedge target you set, using "
        "long-only ETFs your broker already supports. This project has NOT "
        "confirmed that this basket reduces drawdown, and a hedge that is "
        "held costs money whether or not a decline arrives. Nothing is bought "
        "until you approve each proposal by typing the phrase, and your "
        "policy limits are re-checked at that moment."
    )
    _hd_policy, _hd_packet = _load_packet(policy_path, include_events=False)

    _hd_selected = st.multiselect(
        "Hedge instruments",
        options=list(HEDGE_SLEEVE_TICKERS),
        default=list(HEDGE_SLEEVE_TICKERS),
        key="hedge_instruments",
        help=(
            "Long-only ETFs. Membership is a recorded preference, not a "
            "validated finding."
        ),
    )
    _hd_target = st.number_input(
        "Hedge target (% of total equity)",
        min_value=0.0, max_value=100.0, value=0.0, step=0.5,
        key="hedge_target_pct",
        help=(
            "The share of total equity you want held in the selected "
            "instruments. Leave at 0 to only read the current position."
        ),
    )

    # A zero on the number input means "no target set yet", which is the
    # page's own default state -- report-only, not an invalid entry. Passing
    # 0 through as a target would greet every first visit with a red error.
    _hd_target_or_none = _hd_target if _hd_target > 0 else None
    _hd_report = evaluate_hedge_sleeve(
        _hd_packet.portfolio,
        target_pct=_hd_target_or_none,
        tickers=_hd_selected,
    )
    for _hd_disclosure in _hd_report.disclosures:
        st.warning(_hd_disclosure)

    if _hd_report.rows:
        st.subheader("Current defensive position")
        st.dataframe(
            [
                {
                    "Instrument": _row.ticker,
                    "Held": "yes" if _row.held else "no",
                    "Shares": (
                        _row.shares_exact if _row.value_available else "unreadable"
                    ),
                    "Market value": (
                        f"${float(_row.market_value_exact):,.2f}"
                        if _row.value_available
                        else "unreadable"
                    ),
                    "% of equity": (
                        f"{_row.pct_of_equity:.2f}%"
                        if _row.value_available
                        else "--"
                    ),
                    "Daily reset": "yes" if _row.daily_reset else "no",
                }
                for _row in _hd_report.rows
            ],
            hide_index=True,
            width="stretch",
        )

    if _hd_report.refusals:
        for _hd_refusal in _hd_report.refusals:
            st.error(_hd_refusal)
        st.info(
            "No hedge purchase is sized while any of the above is unresolved. "
            "An unreadable holding makes the current hedge look smaller than "
            "it is, which would oversize the purchase."
        )
    else:
        st.metric(
            "Hedge sleeve",
            f"{_hd_report.current_pct:.2f}% of equity",
            delta=(
                f"projected {_hd_report.projected_pct:.2f}% including pending; "
                f"target {_hd_report.target_pct:.2f}%"
                if float(_hd_report.pending_buy_value_exact) > 0
                else f"target {_hd_report.target_pct:.2f}%"
            ),
            delta_color="off",
        )
        if _hd_report.has_shortfall:
            _hd_shortfall = float(_hd_report.shortfall_dollars_exact)
            st.caption(
                f"Remaining shortfall to target after pending buys: "
                f"${_hd_shortfall:,.2f}, split equally across every selected "
                "instrument. Equal weight is "
                "deliberate: inverse-volatility weighting would put the most "
                "money in whichever defensive name moves least."
            )
            _hd_prices, _hd_missing = _hedge_reference_prices(
                store, _hd_report.tickers
            )
            if _hd_missing:
                st.warning(
                    "No usable fresh recorded close for "
                    + ", ".join(sorted(_hd_missing))
                    + ". The whole selected basket is blocked until every "
                    "leg has a usable price."
                )
            _hd_signature = (
                f"{sorted(_hd_report.tickers)}|{_hd_report.target_pct}|"
                f"{_hd_report.shortfall_dollars_exact}|"
                f"{_hd_report.pending_buy_value_exact}|"
                f"{_hd_packet.portfolio.as_of}"
            )
            if st.button(
                "Create hedge buy proposals",
                type="primary",
                disabled=bool(_hd_missing) or not _hd_prices,
                key="hedge_create",
            ):
                _hd_result = generate_hedge_buy_proposals(
                    _hd_packet, _hd_policy, _hd_prices,
                    target_pct=_hd_target_or_none,
                    tickers=_hd_report.tickers,
                )
                if _hd_result["created"]:
                    for _hd_proposal in _hd_result["proposals"]:
                        store.save_proposal(_hd_proposal.to_dict())
                    st.session_state["hedge_proposals"] = [
                        _hd_proposal.to_dict()
                        for _hd_proposal in _hd_result["proposals"]
                    ]
                    st.session_state["hedge_proposals_signature"] = _hd_signature
                else:
                    st.session_state.pop("hedge_proposals", None)
                    st.session_state.pop("hedge_proposals_signature", None)
                    st.error(_hd_result["reason"])

            _hd_stored = st.session_state.get("hedge_proposals")
            if _hd_stored:
                # Same stale-binding rule as every other proposal surface: an
                # actionable card must never look synchronized with inputs it
                # does not represent.
                if (
                    st.session_state.get("hedge_proposals_signature")
                    != _hd_signature
                ):
                    st.info(
                        f"{len(_hd_stored)} hedge proposal(s) are waiting on "
                        "the Propose & Approve page, but they do not match the "
                        "current instruments, target, and shortfall. Create "
                        "new proposals to act here."
                    )
                else:
                    st.subheader("Approve each leg separately")
                    st.caption(
                        "Each instrument is approved on its own, one typed "
                        "phrase at a time. There is deliberately no "
                        "submit-all button here: a partly-filled hedge is a "
                        "different position from the one you sized, and it "
                        "should be a decision you make leg by leg."
                    )
                    for _hd_proposal in _hd_stored:
                        _render_proposal_approval(
                            _hd_proposal, store, policy_path,
                            _hd_packet.portfolio, _hd_packet,
                        )
        elif _hd_report.target_pct > 0:
            st.success(
                f"The hedge sleeve is at {_hd_report.current_pct:.2f}% against "
                f"your {_hd_report.target_pct:.2f}% target, "
                f"${float(_hd_report.surplus_dollars_exact):,.2f} above it. "
                "Nothing to buy. This page never sells to rebalance a hedge "
                "down -- use Discrete Selling for that, deliberately."
            )
        else:
            st.info(
                "Set a hedge target above 0% to size a purchase. At 0% this "
                "page only reports what you already hold."
            )


if page == "Portfolio Rebalancing":
    st.caption(
        "Read-only. This page reports what your portfolio IS against the "
        "sleeve targets you approved -- it proposes nothing, sizes nothing, "
        "and names no buy or sell. Targets and band width are your stated "
        "preference, not a research result."
    )
    _rb_policy, _rb_packet = _load_packet(policy_path, include_events=False)
    _rb_report = evaluate_portfolio_rebalance(
        _rb_packet.portfolio, OWNER_APPROVED_PROFILE, policy=_rb_policy
    )

    # Stage 1 has no stored analysis: the report is recomputed from the
    # current snapshot on every rerun and nothing is written to session
    # state. A stale card cannot survive a profile or snapshot change if no
    # card is ever retained, which is the simplest form of the staleness
    # rule the later proposal stages will need to implement explicitly.
    st.caption(
        f"Profile `{_rb_report.profile_version}` "
        f"(`{_rb_report.profile_fingerprint[:12]}`), "
        f"band +/-{_rb_report.band_fraction:.0%} relative, "
        f"snapshot {_rb_report.as_of}. Recomputed on every rerun; nothing "
        "here is retained between views."
    )

    for _rb_disclosure in _rb_report.disclosures:
        st.warning(_rb_disclosure)

    if _rb_report.refusals:
        for _rb_refusal in _rb_report.refusals:
            st.error(_rb_refusal)
        st.info(
            "No sleeve percentage is shown while any of the above is "
            "unresolved. Sleeve weights share one equity denominator, so a "
            "single unusable value moves every sleeve's percentage -- "
            "including sleeves whose own holdings read fine."
        )
    else:
        _rb_a, _rb_b, _rb_c, _rb_d = st.columns(4)
        _rb_a.metric(
            "Total equity", f"${Decimal(_rb_report.total_equity_exact):,.2f}"
        )
        _rb_b.metric("Invested", f"{_rb_report.invested_pct:.2f}%")
        _rb_c.metric("Cash", f"{_rb_report.cash_pct:.2f}%")
        _rb_d.metric("Bands breached", f"{_rb_report.breached_count}")

        with st.container(border=True):
            st.caption("SLEEVE ALLOCATION")
            st.bar_chart(
                {
                    "Current %": {
                        SLEEVE_LABELS[r.sleeve]: r.current_pct
                        for r in _rb_report.rows
                    },
                    "Target %": {
                        SLEEVE_LABELS[r.sleeve]: r.target_pct
                        for r in _rb_report.rows
                    },
                },
                height=260,
            )

        _rb_status_labels = {
            "inside_band": "Inside band",
            "underweight": "Underweight",
            "overweight": "Overweight",
            "unassigned_holdings": "Unassigned holdings",
            "pending_value_unknown": "Pending value unknown",
            "data_unavailable": "Data unavailable",
            "policy_conflict": "Policy conflict",
        }
        st.dataframe(
            [
                {
                    "Sleeve": SLEEVE_LABELS[_row.sleeve],
                    "Target": f"{_row.target_pct:.2f}%",
                    "Band": (
                        f"{_row.lower_edge_pct:.2f}% - "
                        f"{_row.upper_edge_pct:.2f}%"
                    ),
                    "Current": f"{_row.current_pct:.2f}%",
                    "Pending": f"${Decimal(_row.pending_value_exact):,.2f}",
                    "Projected": f"{_row.projected_pct:.2f}%",
                    "Gap to target": (
                        f"${Decimal(_row.gap_to_target_exact):,.2f}"
                    ),
                    "Status": _rb_status_labels.get(_row.status, _row.status),
                    # REBAL1CR-001: feasibility is its own column. It used
                    # to occupy Status and hide the band state, so a page
                    # measuring drift reported almost none of it.
                    "Reachable": (
                        "no"
                        if _row.policy_conflict_reason
                        else "yes"
                    ),
                }
                for _row in _rb_report.rows
            ],
            hide_index=True,
            width="stretch",
        )
        st.caption(
            "Gap to target is the projected distance after measurable "
            "working orders, not an instruction: it names how far a sleeve "
            "would sit from its target in dollars, with no share count, no "
            "side, and no ordering of what to act on."
        )

        # REBAL1CR-001 follow-up: feasibility used to be the LAST column of
        # a nine-column table, which on a normal window is cut off with no
        # horizontal scrollbar -- so the one fact telling the owner whether
        # the targets are reachable at all was unreadable. It is now stated
        # in full below the table, where width cannot hide it.
        _rb_conflicts = [
            _row for _row in _rb_report.rows if _row.policy_conflict_reason
        ]
        if _rb_conflicts:
            with st.container(border=True):
                st.caption("TARGETS NOT REACHABLE UNDER THE ACTIVE POLICY")
                for _rb_conflict in _rb_conflicts:
                    _rb_name = SLEEVE_LABELS.get(
                        _rb_conflict.sleeve, _rb_conflict.sleeve
                    )
                    st.write(
                        f"**{_rb_name}**: "
                        f"{_rb_conflict.policy_conflict_reason}."
                    )
                st.caption(
                    "A cap is not a target, but a target above a cap cannot "
                    "be reached, so the band around it is fiction until "
                    "either the profile or the policy moves."
                )
        else:
            st.caption(
                "Every sleeve target is reachable under the active policy "
                f"(`{Path(policy_path).name}`)."
            )

        if _rb_report.unassigned_tickers:
            with st.container(border=True):
                st.caption("CURRENT OR PENDING EXPOSURE OUTSIDE EVERY SLEEVE")
                st.write(", ".join(_rb_report.unassigned_tickers))
                st.caption(
                    "These are shown because the allocation profile does not "
                    "cover them. That is a gap in the profile, not a verdict "
                    "on the holding or order, and it is not a reason to sell."
                )
        # --- Stage 2: buy-only cash steering ------------------------------
        st.divider()
        st.subheader("Steer new money toward under-band sleeves")
        st.caption(
            "Buy only. An overweight sleeve receives nothing here -- not even "
            "a smaller buy -- because trimming would be this app selling on "
            "its own initiative. Nothing is bought until you approve each "
            "proposal by typing the phrase."
        )

        _rb_eligible = _rebalance_eligible_sleeves(_rb_report)
        if not _rb_eligible:
            st.info(
                "No sleeve is below its lower band, so there is nothing to "
                "steer new money toward."
            )
        else:
            _rb_membership = _rebalance_sleeve_membership()
            _rb_budget = st.number_input(
                "New-money budget ($)",
                min_value=0.0, value=0.0, step=100.0,
                key="rb_budget",
                help=(
                    "Money you are adding, not money moved between holdings. "
                    "This page never sells to fund a purchase."
                ),
            )
            _rb_selections = {}
            for _rb_sleeve in _rb_eligible:
                _rb_choices = sorted(
                    t for t, s in _rb_membership.items() if s == _rb_sleeve
                )
                _rb_selections[_rb_sleeve] = st.selectbox(
                    f"Ticker for {SLEEVE_LABELS.get(_rb_sleeve, _rb_sleeve)}",
                    options=["-- choose --", *_rb_choices],
                    key=f"rb_pick_{_rb_sleeve}",
                    help=(
                        "This app does not pick which name to buy inside a "
                        "sleeve."
                    ),
                )
            _rb_chosen = {
                s: t for s, t in _rb_selections.items() if t != "-- choose --"
            }

            # The shared helper covers the complete snapshot plus profile,
            # policy, ticker choices, and exact budget. In particular, a
            # same-day price rotation cannot leave an old card standing just
            # because total equity and pending orders happen to be unchanged.
            _rb_signature = _steering_input_fingerprint(
                _rb_packet,
                _rb_report,
                _rb_policy,
                selections=_rb_chosen,
                budget=_rb_budget,
            )

            if st.button(
                "Check what this budget would do",
                type="primary",
                disabled=_rb_budget <= 0 or not _rb_chosen,
                key="rb_steer",
            ):
                _rb_prices, _rb_missing = _hedge_reference_prices(
                    store, sorted(_rb_chosen.values())
                )
                if _rb_missing:
                    st.warning(
                        "No usable fresh recorded close for "
                        + ", ".join(sorted(_rb_missing))
                        + ". Those sleeves cannot be sized."
                    )
                _rb_result = generate_steering_proposals(
                    _rb_packet, OWNER_APPROVED_PROFILE, _rb_policy,
                    budget=_rb_budget, selections=_rb_chosen,
                    prices=_rb_prices,
                )
                if _rb_result["created"]:
                    for _rb_proposal in _rb_result["proposals"]:
                        store.save_proposal(_rb_proposal.to_dict())
                    st.session_state["rb_proposals"] = [
                        _rb_proposal.to_dict()
                        for _rb_proposal in _rb_result["proposals"]
                    ]
                    st.session_state["rb_proposals_signature"] = _rb_signature
                    st.session_state["rb_plan_unallocated"] = _rb_result[
                        "plan"
                    ].unallocated_exact
                    st.session_state["rb_plan_disclosures"] = list(
                        _rb_result["plan"].disclosures
                    )
                else:
                    st.session_state.pop("rb_proposals", None)
                    st.session_state.pop("rb_proposals_signature", None)
                    st.error(_rb_result["reason"])

            _rb_stored = st.session_state.get("rb_proposals")
            if _rb_stored:
                if st.session_state.get("rb_proposals_signature") != _rb_signature:
                    st.info(
                        f"{len(_rb_stored)} steering proposal(s) are waiting on "
                        "the Propose & Approve page, but they no longer match "
                        "the current profile, snapshot, working orders, ticker "
                        "choices, or budget. Check again to size new ones."
                    )
                else:
                    for _rb_note in st.session_state.get(
                        "rb_plan_disclosures", []
                    ):
                        st.warning(_rb_note)
                    st.caption(
                        "Unallocated and left as cash: $"
                        f"{Decimal(st.session_state.get('rb_plan_unallocated', '0')):,.2f}"
                    )
                    st.caption(
                        "Approve each sleeve separately. There is deliberately "
                        "no submit-all: a partly filled multi-sleeve correction "
                        "is a different portfolio from the one you sized."
                    )
                    for _rb_proposal in _rb_stored:
                        _render_proposal_approval(
                            _rb_proposal, store, policy_path,
                            _rb_packet.portfolio, _rb_packet,
                        )
        # --- Stage 3: tax-aware trims -------------------------------------
        st.divider()
        st.subheader("Trim an overweight sleeve")
        st.caption(
            "This is the only place in the app where a rebalancing SELL is "
            "prepared from the app's own arithmetic. It shows the realized "
            "gain before you approve, refuses to sell past your target, and "
            "refuses entirely when the tax lots are incomplete. You choose "
            "the sleeve, ticker, amount, and lot strategy."
        )

        _rb_over = _rebalance_overweight_sleeves(_rb_report)
        if not _rb_over:
            # An empty trimmable list has two very different causes,
            # and reporting the wrong one contradicts the breach count
            # in the headline above: a reader told "no sleeve is above
            # its upper band" while the page also reports six breaches
            # has to conclude one of the two is broken.
            _rb_over_untrimmable = _rebalance_untrimmable_overweight(
                _rb_report
            )
            if _rb_over_untrimmable:
                _rb_names = ", ".join(
                    SLEEVE_LABELS.get(s, s) for s in _rb_over_untrimmable
                )
                st.info(
                    f"Nothing here can be trimmed. {_rb_names} "
                    f"{'is' if len(_rb_over_untrimmable) == 1 else 'are'} "
                    "above the upper band, but this workflow never trims "
                    "either one: cash is not a holding, and the residual "
                    "is the set of positions your profile does not "
                    "describe -- absence from the profile is never a "
                    "reason to sell. Every sleeve the profile DOES "
                    "describe is inside or below its band."
                )
            else:
                st.info(
                    "No sleeve is above its upper band, so there is "
                    "nothing to trim."
                )
        else:
            _rb_trim_sleeve = st.selectbox(
                "Overweight sleeve",
                options=[
                    "-- choose --",
                    *[SLEEVE_LABELS.get(s, s) for s in _rb_over],
                ],
                key="rb_trim_sleeve",
            )
            _rb_sleeve_key = next(
                (
                    s for s in _rb_over
                    if SLEEVE_LABELS.get(s, s) == _rb_trim_sleeve
                ),
                None,
            )
            _rb_held = sorted(
                p.ticker.upper() for p in _rb_packet.portfolio.positions
                if _rebalance_sleeve_membership().get(p.ticker.upper())
                == _rb_sleeve_key
            )
            _rb_trim_ticker = st.selectbox(
                "Ticker to trim",
                options=["-- choose --", *_rb_held],
                key="rb_trim_ticker",
                help="This app does not choose which holding to sell.",
            )
            _rb_trim_strategy = st.selectbox(
                "Lot strategy",
                options=["-- choose --", "fifo", "lifo", "hifo"],
                key="rb_trim_strategy",
                help=(
                    "HIFO sells the highest-cost lots first and realizes the "
                    "least gain. This app records your choice; it does not "
                    "instruct the broker."
                ),
            )
            if _rb_policy.whole_shares_only:
                _rb_trim_shares = st.number_input(
                    "Shares to sell",
                    min_value=0.0, value=0.0, step=1.0,
                    key="rb_trim_shares",
                )
                _rb_shares_arg = (
                    int(_rb_trim_shares) if _rb_trim_shares > 0 else None
                )
            else:
                _rb_trim_shares = st.text_input(
                    "Shares to sell",
                    value="",
                    key="rb_trim_fractional_shares",
                    help="Enter an exact quantity with at most 9 decimal places.",
                )
                _rb_shares_arg = canonical_order_quantity(
                    _rb_trim_shares, whole_shares_only=False
                )
                if _rb_trim_shares and _rb_shares_arg is None:
                    st.error(
                        "Enter a positive share quantity with at most 9 "
                        "decimal places."
                    )

            _rb_ready = (
                _rb_sleeve_key is not None
                and _rb_trim_ticker != "-- choose --"
                and _rb_trim_strategy != "-- choose --"
                and _rb_shares_arg is not None
            )
            if st.button(
                "Check what this trim would realize",
                type="primary",
                disabled=not _rb_ready,
                key="rb_trim_check",
            ):
                # Stage 3 sells ONE ticker, so it asks the per-ticker
                # question. The portfolio-wide provider withholds the
                # ledger entirely when any other holding is unreconciled,
                # which made every trim impossible on a real book.
                _rb_ledger, _rb_coverage = ticker_tax_ledger_with_coverage(
                    store, _rb_packet.portfolio, _rb_trim_ticker
                )
                _rb_trim_result = generate_trim_proposal(
                    _rb_packet, OWNER_APPROVED_PROFILE, _rb_policy,
                    sleeve=_rb_sleeve_key, ticker=_rb_trim_ticker,
                    shares=_rb_shares_arg, lot_strategy=_rb_trim_strategy,
                    tax_lot_ledger=_rb_ledger, tax_lot_coverage=_rb_coverage,
                )
                _rb_trim_plan = _rb_trim_result["plan"]
                if _rb_trim_result["created"]:
                    store.save_proposal(_rb_trim_result["proposal"].to_dict())
                    st.session_state["rb_trim_proposal"] = _rb_trim_result[
                        "proposal"
                    ].to_dict()
                    st.session_state["rb_trim_signature"] = (
                        _steering_input_fingerprint(
                            _rb_packet, _rb_report, _rb_policy,
                            selections={_rb_sleeve_key: _rb_trim_ticker},
                            budget=_rb_shares_arg,
                        ) + f"|{_rb_trim_strategy}"
                    )
                    st.session_state["rb_trim_plan"] = {
                        "excess": _rb_trim_plan.excess_above_band_exact,
                        "restoration": _rb_trim_plan.restoration_to_target_exact,
                        "pending_sell": _rb_trim_plan.pending_sell_value_exact,
                        "gain": _rb_trim_plan.realized_gain_exact,
                        "short": _rb_trim_plan.realized_short_term_exact,
                        "long": _rb_trim_plan.realized_long_term_exact,
                        "remaining": _rb_trim_plan.remaining_shares_exact,
                        "lots": [
                            {
                                "Lot": lot.lot_id,
                                "Acquired": lot.acquired_at[:10],
                                "Term": lot.term_if_sold_now,
                                "Days to long-term": lot.days_to_long_term,
                                "Shares sold": lot.quantity_taken,
                                "Cost/share": f"${Decimal(lot.cost_per_share):,.2f}",
                                "Realized": f"${Decimal(lot.realized_gain_exact):,.2f}",
                            }
                            for lot in _rb_trim_plan.lots
                        ],
                        "disclosures": list(_rb_trim_plan.disclosures),
                    }
                else:
                    st.session_state.pop("rb_trim_proposal", None)
                    st.session_state.pop("rb_trim_signature", None)
                    st.session_state.pop("rb_trim_plan", None)
                    st.error(_rb_trim_result["reason"])

            _rb_trim_stored = st.session_state.get("rb_trim_proposal")
            if _rb_trim_stored:
                _rb_trim_now = (
                    _steering_input_fingerprint(
                        _rb_packet, _rb_report, _rb_policy,
                        selections=(
                            {_rb_sleeve_key: _rb_trim_ticker}
                            if _rb_sleeve_key is not None else {}
                        ),
                        budget=_rb_shares_arg,
                    ) + f"|{_rb_trim_strategy}"
                )
                if st.session_state.get("rb_trim_signature") != _rb_trim_now:
                    st.info(
                        "A trim proposal is waiting on the Propose & Approve "
                        "page, but it no longer matches the current profile, "
                        "snapshot, working orders, ticker, amount, or lot "
                        "strategy. Check again to size a new one."
                    )
                else:
                    _rb_shown = st.session_state.get("rb_trim_plan", {})
                    for _rb_note in _rb_shown.get("disclosures", []):
                        st.warning(_rb_note)
                    _rb_t1, _rb_t2, _rb_t3, _rb_t4 = st.columns(4)
                    _rb_t1.metric(
                        "Above band",
                        f"${Decimal(_rb_shown.get('excess', '0')):,.2f}",
                    )
                    _rb_t2.metric(
                        "Restores target",
                        f"${Decimal(_rb_shown.get('restoration', '0')):,.2f}",
                    )
                    _rb_t3.metric(
                        "Working sells",
                        f"${Decimal(_rb_shown.get('pending_sell', '0')):,.2f}",
                    )
                    _rb_t4.metric(
                        "Realized gain",
                        f"${Decimal(_rb_shown.get('gain', '0')):,.2f}",
                        delta=(
                            f"${Decimal(_rb_shown.get('short', '0')):,.2f} "
                            "short-term"
                        ),
                        delta_color="inverse",
                    )
                    if _rb_shown.get("lots"):
                        st.caption("LOTS THIS SALE WOULD REALIZE")
                        st.dataframe(
                            _rb_shown["lots"], hide_index=True, width="stretch"
                        )
                    st.caption(
                        "Shares remaining after this sale: "
                        f"{_rb_shown.get('remaining', '0')}"
                    )
                    _render_proposal_approval(
                        _rb_trim_stored, store, policy_path,
                        _rb_packet.portfolio, _rb_packet,
                    )






if page == "Propose & Approve":
    policy, packet = _load_packet(policy_path, include_events)

    pair_labels = ", ".join(f"{p.stable_ticker}/{p.leveraged_ticker}" for p in CONFIGURED_LEVERAGED_PAIRS)
    check_strategy = st.checkbox(
        f"Also check leveraged-pair rebalance strategies ({pair_labels})",
        value=policy.enable_strategy_proposals,
        key="strategy_proposals_enabled",
        help="Each pair's evidence_status is shown per-proposal -- none are 'confirmed' -- "
        "see assistant/strategy_proposals.py",
    )

    if st.button("Check for proposals", type="primary"):
        tax_ledger, tax_coverage = tax_ledger_with_coverage(
            store, packet.portfolio
        )
        proposals = generate_risk_reduction_proposals(
            packet,
            policy,
            tax_lot_ledger=tax_ledger,
            tax_lot_coverage=tax_coverage,
        )
        if check_strategy:
            for pair_config in CONFIGURED_LEVERAGED_PAIRS:
                try:
                    proposals = proposals + generate_leveraged_pair_rebalance_proposals(
                        packet, policy, pair_config, store=store
                    )
                # FCS-001: `Exception`, matching the CLI's own handler, NOT the
                # two declared strategy error types. `proposals` already holds
                # the RISK-REDUCTION sells computed above; anything escaping
                # here aborts the whole block, so they are never written to
                # session state and never saved -- an optional strategy check
                # silently suppressing a risk-reducing sell. That is exactly
                # what a ZeroDivisionError from an unpriced leg did. The
                # narrower tuple only ever protected against the failures
                # somebody had already predicted, which is the wrong set.
                except Exception as exc:
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
        _render_proposal_approval(proposal, store, policy_path, packet.portfolio, packet)

if page == "History":
    with st.expander("Emergency order controls", expanded=False):
        st.warning(
            "Cancel-all activates the persistent kill switch first, then "
            "requests cancellation for every open Alpaca order—including "
            "orders not created by this app. Verify the broker directly if "
            "any request fails."
        )
        emergency_reason = st.text_input(
            "Incident reason",
            key="emergency_cancel_all_reason",
        )
        emergency_confirmation = st.text_input(
            'Type "cancel all open orders" to confirm',
            key="emergency_cancel_all_confirmation",
        )
        if st.button(
            "Activate kill switch and cancel all open orders",
            type="primary",
            disabled=(
                not emergency_reason.strip()
                or emergency_confirmation.strip().lower()
                != "cancel all open orders"
            ),
        ):
            try:
                result = cancel_all_open_orders(
                    store, reason=emergency_reason
                )
                if result["errors"]:
                    st.error(
                        "Cancel-all completed with failures. Keep the kill "
                        "switch active and verify Alpaca directly."
                    )
                else:
                    st.success(
                        "Kill switch active; cancellation requested for "
                        f"{result['cancel_requested_count']} open order(s)."
                    )
                st.json(result)
            except Exception as exc:
                st.error(
                    "Emergency cancel-all failed. The persistent kill switch "
                    f"may still be active; verify Alpaca directly: {exc}"
                )

    proposals_col, orders_col = st.columns(2)

    with proposals_col:
        st.subheader("Proposals")
        dismissal_notice = st.session_state.pop("dismissal_notice", None)
        if dismissal_notice:
            st.success(dismissal_notice)
        outcome_filter = st.multiselect(
            "Outcome filter",
            list(OUTCOME_GROUPS),
            key="proposal_outcome_filter",
            help=(
                "Groups every lifecycle status by what it means for the "
                "trade. \"Broker working / unresolved\" includes legacy "
                "\"executed\" rows (broker accepted, fill not confirmed); "
                "\"Other / unknown\" catches any status this app version "
                "does not recognize. Empty selection shows all outcomes."
            ),
        )
        with st.expander("Advanced: exact status filter"):
            status_filter = st.selectbox(
                "Exact status",
                ["(any)"] + list(STATUSES),
                key="proposal_status_filter",
                help=(
                    "Combines with the outcome filter by intersection: "
                    "rows must match both."
                ),
            )
        proposal_limit = st.slider("Max rows", 5, 100, 20, key="proposal_history_limit")

        # UI-2d visibility (archive classes hidden by default). These flags
        # govern ONLY the unfiltered default view: explicitly selecting an
        # outcome group or exact status always shows that selection's rows,
        # so a hidden visibility flag can never contradict an explicit
        # filter into a misleading empty result.
        include_expired = st.checkbox(
            "Include expired proposals",
            value=False,
            key="history_include_expired",
        )
        include_dismissed = st.checkbox(
            "Include dismissed proposals",
            value=False,
            key="history_include_dismissed",
        )

        exact_status = None if status_filter == "(any)" else status_filter
        # Both filters constrain the DATABASE query domain, not merely the
        # fetched page: each path returns the newest `proposal_limit` rows of
        # the filtered kind. When both filters are set they intersect -- and
        # because every status belongs to exactly one outcome group, that
        # intersection is either the exact-status rows or nothing.
        if exact_status is not None:
            stored = store.list_proposals(status=exact_status, limit=proposal_limit)
            if outcome_filter:
                stored = [
                    p
                    for p in stored
                    if outcome_group_for_status(p["status"]) in outcome_filter
                ]
        elif outcome_filter:
            stored = store.list_proposals_for_outcomes(
                statuses=statuses_for_outcome_groups(outcome_filter),
                include_unknown_statuses=OUTCOME_OTHER_UNKNOWN in outcome_filter,
                limit=proposal_limit,
            )
        else:
            stored = store.list_proposals(
                status=None,
                limit=proposal_limit,
                include_dismissed=include_dismissed,
                include_expired=include_expired,
            )

        active_filter_parts = []
        if outcome_filter:
            active_filter_parts.append(
                "outcomes = " + ", ".join(outcome_filter)
            )
        if exact_status is not None:
            active_filter_parts.append(f"exact status = {exact_status}")
        if active_filter_parts:
            caption = (
                "Active filters: "
                + "; ".join(active_filter_parts)
                + ". When both filters are set, a row must match both "
                "(intersection)."
            )
            if exact_status in (EXPIRED, DISMISSED):
                caption += (
                    f" Selecting the {exact_status} status shows those rows "
                    "even while their include-checkbox is off."
                )
            st.caption(caption)
        elif not (include_expired and include_dismissed):
            hidden_classes = [
                label
                for flag, label in (
                    (include_expired, "expired"),
                    (include_dismissed, "dismissed"),
                )
                if not flag
            ]
            st.caption(
                f"Hiding {' and '.join(hidden_classes)} proposals -- use the "
                "checkboxes above (or an outcome/status filter) to show them."
            )

        if not stored:
            if active_filter_parts:
                st.info("No proposals match the active filters.")
            else:
                st.info("No proposals found in history.")
        else:
            st.dataframe(
                [
                    {
                        "Proposal ID": p["proposal_id"],
                        "Status": p["status"],
                        "Outcome": outcome_group_for_status(p["status"]),
                        "Side": p["intent"]["side"],
                        "Shares": p["intent"]["shares"],
                        "Ticker": p["intent"]["ticker"],
                        "Evidence": p.get("evidence_status", ""),
                        "Expires": p["expires_at"],
                    }
                    for p in stored
                ],
                width="stretch",
                hide_index=True,
            )

        # --- UI-2d: dismiss/archive unused proposals -----------------------
        # Archive, never delete: the row, payload, and idempotency key all
        # remain; only pristine never-broker-touched proposed/expired rows
        # qualify, enforced by the storage layer (the UI reproduces no
        # eligibility rule of its own).
        with st.expander("Manage unused proposals"):
            st.caption(
                "Dismiss unused Watchlist/Buying experiments to declutter "
                "History. Dismissed proposals remain in the local audit "
                "history and cannot be executed. Only never-broker-touched "
                "proposed/expired rows qualify; nothing here can call the "
                "broker or delete a record."
            )
            manage_candidates = store.list_proposals_for_outcomes(
                statuses=DISMISSIBLE_SOURCE_STATUSES, limit=200
            )
            if not manage_candidates:
                st.caption("No proposed or expired rows to manage.")
            else:
                candidate_preview = store.proposal_dismissal_eligibility(
                    [p["proposal_id"] for p in manage_candidates]
                )
                dismissible_rows = [
                    row for row in candidate_preview.rows if row.dismissible
                ]
                blocked_rows = [
                    row for row in candidate_preview.rows if not row.dismissible
                ]
                if blocked_rows:
                    st.caption(
                        f"{len(blocked_rows)} proposed/expired row(s) are not "
                        "dismissible (they touched validation, batching, "
                        "reservation, or the broker) and stay in History."
                    )
                if not dismissible_rows:
                    st.caption("No currently dismissible proposals.")
                else:
                    row_by_id = {row.proposal_id: row for row in dismissible_rows}
                    # A rerun can shrink the dismissible set (another
                    # process dismissed or claimed a row); a stale selection
                    # outside the current options would error the widget.
                    if "dismiss_selection" in st.session_state:
                        st.session_state["dismiss_selection"] = [
                            pid
                            for pid in st.session_state["dismiss_selection"]
                            if pid in row_by_id
                        ]
                    selection = st.multiselect(
                        "Proposals to dismiss",
                        list(row_by_id),
                        key="dismiss_selection",
                        format_func=lambda pid: (
                            f"{pid} ({row_by_id[pid].side.upper()} "
                            f"{row_by_id[pid].shares} {row_by_id[pid].ticker}, "
                            f"{row_by_id[pid].status})"
                        ),
                    )
                    if selection:
                        selection_preview = store.proposal_dismissal_eligibility(
                            selection
                        )
                        st.dataframe(
                            [
                                {
                                    "Proposal ID": row.proposal_id,
                                    "Ticker": row.ticker,
                                    "Side": row.side,
                                    "Shares": row.shares,
                                    "Status": row.status,
                                    "Created": row.created_at,
                                    "Expires": row.expires_at,
                                }
                                for row in selection_preview.rows
                            ],
                            width="stretch",
                            hide_index=True,
                        )
                        dismiss_reason = st.text_input(
                            "Dismissal reason (required)",
                            key="dismiss_reason",
                        )
                        dismiss_phrase = f"dismiss {len(selection)} proposals"
                        dismiss_confirmation = st.text_input(
                            f'Type "{dismiss_phrase}" to enable the button',
                            key="dismiss_confirmation",
                        )
                        if st.button(
                            "Dismiss selected proposals",
                            key="dismiss_button",
                            disabled=(
                                not dismiss_reason.strip()
                                or dismiss_confirmation.strip() != dismiss_phrase
                                or tuple(selection)
                                != selection_preview.dismissible_ids
                            ),
                        ):
                            try:
                                dismissal = store.dismiss_proposals(
                                    selection,
                                    dismissed_by="local_operator",
                                    reason=dismiss_reason,
                                    expected_preview_hash=(
                                        selection_preview.preview_hash
                                    ),
                                )
                            except ValueError as exc:
                                st.error(f"Dismissal refused: {exc}")
                            else:
                                # Stale per-proposal approval/override/cancel
                                # state must die with the dismissal so no
                                # snapshot can re-offer controls for these IDs.
                                for pid in (
                                    dismissal.dismissed_ids
                                    + dismissal.already_dismissed_ids
                                ):
                                    for stale_key in (
                                        f"confirm_{pid}",
                                        f"override_available_{pid}",
                                        f"override_confirm_{pid}",
                                        f"committee_result_{pid}",
                                        f"content_digest_{pid}",
                                        f"cancel_confirmation_{pid}",
                                    ):
                                        st.session_state.pop(stale_key, None)
                                for own_key in (
                                    "dismiss_selection",
                                    "dismiss_reason",
                                    "dismiss_confirmation",
                                ):
                                    st.session_state.pop(own_key, None)
                                # The success message must survive the
                                # refresh rerun, so it travels via a
                                # non-widget session key.
                                st.session_state["dismissal_notice"] = (
                                    f"Dismissed "
                                    f"{len(dismissal.dismissed_ids)} "
                                    "proposal(s). They remain in the local "
                                    "audit history and cannot be executed."
                                )
                                st.rerun()

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

        cancelable = [
            p
            for p in stored
            if p["status"] in UNRESOLVED_BROKER_STATE_STATUSES
        ]
        if cancelable:
            st.write("Cancel a working or unresolved assistant order")
            st.caption(
                "The service follows Alpaca replacement links and cancels "
                "the current authoritative order, not a superseded order."
            )
            for p in cancelable:
                intent = p["intent"]
                confirmation = st.text_input(
                    f'Type "cancel" for {p["proposal_id"]}',
                    key=f"cancel_confirmation_{p['proposal_id']}",
                )
                if st.button(
                    (
                        f"Cancel {intent['side'].upper()} "
                        f"{intent['shares']} {intent['ticker']} "
                        f"({p['proposal_id']})"
                    ),
                    key=f"cancel_order_{p['proposal_id']}",
                    disabled=confirmation.strip().lower() != "cancel",
                ):
                    try:
                        result = cancel_assistant_order(
                            store, p["proposal_id"]
                        )
                        st.success(
                            "Cancellation requested for broker order "
                            f"{result['order_id']}."
                        )
                    except Exception as exc:
                        st.error(f"Cancellation result: {exc}")

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
                width="stretch",
                hide_index=True,
            )

# ---------------------------------------------------------------------------
# Ticker Suggestions -- dedicated research-only surface
# (docs/reference/UI_FEATURE_CONTROLS_DESIGN.md section 4). The Briefing and
# Buying keep their existing embedded suggestion features (owner decision c,
# 2026-08-02); this tab consolidates the same verified pipeline behind explicit
# source toggles, explicit seed selection, and an explicit run button, so every
# network call is a deliberate act rather than a side effect of rendering.
# ---------------------------------------------------------------------------

if page == "Ticker Suggestions":
    st.error(
        "**Research only — not a proposal or allocation authorization.** "
        "Nothing on this page can create, size, approve, or submit an order. "
        "Adding a ticker to the Buying cart, generating a proposal, and "
        "approving it remain separate, explicit actions governed by policy, "
        "fresh data, deterministic risk checks, and exact human approval."
    )
    _, suggestions_packet = _load_packet(policy_path, include_events=False)
    suggestions_held = tuple(
        sorted({p.ticker.upper() for p in suggestions_packet.portfolio.positions})
    )

    def _render_most_active_by_direction(rows: list) -> None:
        """Split one most-actives list into advancing / declining columns.

        Owner request (2026-08-10) was two columns, "most actively bought"
        and "most actively sold". That split is not present in this source
        and is NOT built here: every share traded was bought by someone and
        sold by someone else, so volume is one symmetric number and this
        screener does not decompose it into classified order flow. (The rule is
        stated at assistant/recommended_stocks.fetch_most_active_tickers:
        never label this "most bought" in code, comments, or UI copy.)

        What IS reported separately is the direction the price moved, which
        distinguishes heavily traded names whose prices rose from heavily
        traded names whose prices fell.
        Candidates whose provider row carried no usable change value are
        listed separately instead of being folded into either column.
        """
        advancing = [r for r in rows if r.price_direction == "advancing"]
        declining = [r for r in rows if r.price_direction == "declining"]
        # "flat" and "unknown" are different facts and must not share a
        # caption: a name that printed exactly 0.00% DID report a change, it
        # just did not move. Folding it into "not reported" would understate
        # what the provider actually gave us.
        flat = [r for r in rows if r.price_direction == "unchanged"]
        unknown = [r for r in rows if r.price_direction is None]
        st.caption(
            "Not a buy/sell split -- every share traded was both bought and "
            "sold, and this source does not report classified order flow. These "
            "are the same most-active names separated by today's price "
            "direction. It describes what already happened and is not a "
            "signal: no strategy in this project has confirmed predictive "
            "evidence."
        )
        left, right = st.columns(2)
        for column, subset, heading in (
            (left, advancing, "Most active — price up today"),
            (right, declining, "Most active — price down today"),
        ):
            with column:
                st.markdown(f"**{heading}** ({len(subset)})")
                if subset:
                    st.dataframe(
                        [
                            {
                                "Ticker": r.ticker,
                                "Detail (volume and price change)": r.detail,
                            }
                            for r in subset
                        ],
                        width="stretch",
                        hide_index=True,
                    )
                else:
                    st.caption("None on this run.")
        # Counter-review BUY1CR-001: direction decides where a row is
        # displayed, never how much of its AP-8 disclosure the reader gets.
        # A flat or unreported-change candidate is still a verified
        # most-active row, so its measurement detail renders like the
        # directional columns' -- while the two buckets keep their separate
        # captions, because a real +0.00% print is not missing data.
        for subset, sentence in (
            (flat, "closed exactly flat"),
            (unknown, "reported no usable price change"),
        ):
            if not subset:
                continue
            st.caption(
                f"{len(subset)} verified candidate(s) "
                + sentence
                + " and are in neither column: "
                + ", ".join(sorted(r.ticker for r in subset))
                + "."
            )
            st.dataframe(
                [
                    {
                        "Ticker": r.ticker,
                        "Detail (volume and price change)": r.detail,
                    }
                    for r in subset
                ],
                width="stretch",
                hide_index=True,
            )

    st.subheader("Sources")
    # Defaults are seeded into session state ONCE (before widget creation),
    # then the widgets own their keys -- passing value= and key= together
    # makes Streamlit warn about two sources of truth after the first
    # interaction.
    ipo_configured = is_ipo_calendar_configured()
    st.session_state.setdefault("suggest_src_most_active", True)
    st.session_state.setdefault("suggest_src_recent_ipo", ipo_configured)
    source_col1, source_col2, source_col3 = st.columns(3)
    with source_col1:
        want_most_active = st.checkbox(
            "Most-active market screen",
            key="suggest_src_most_active",
            help="yfinance most-actives. Reflects trading VOLUME and price movement, "
            "NOT buy-vs-sell order flow.",
        )
    with source_col2:
        want_recent_ipo = st.checkbox(
            "Recent IPO calendar",
            key="suggest_src_recent_ipo",
            disabled=not ipo_configured,
            help=(
                "Finnhub IPO calendar."
                if ipo_configured
                else "FINNHUB_API_KEY is not set."
            ),
        )
    with source_col3:
        suggestions_ai_pref = _ai_feature_enabled("ai_pref_similar_tickers")
        suggestions_ai_available = is_ai_advisor_configured() and suggestions_ai_pref
        want_ai_source = st.checkbox(
            "Claude suggestions (real API call, small real cost)",
            key="suggest_src_ai",
            disabled=not suggestions_ai_available,
            help=(
                "NOT a validated similarity engine -- every suggestion is verified "
                "against real market data and shown with measured evidence."
                if suggestions_ai_available
                else (
                    _AI_PREF_OFF_HELP
                    if is_ai_advisor_configured()
                    else "ANTHROPIC_API_KEY is not set."
                )
            ),
        )

    seed_options = sorted(set(suggestions_held) | set(UNIVERSE) | set(LEVERAGED_ETF_TICKERS))
    seed_tickers = st.multiselect(
        "Seed tickers (similarity basis for Claude suggestions; every lane excludes them from results)",
        options=seed_options,
        default=[t for t in suggestions_held],
        key="suggest_seed_tickers",
    )

    run_suggestions = st.button(
        "Run suggestions",
        type="primary",
        disabled=not (want_most_active or want_recent_ipo or want_ai_source),
        help="Network calls happen only when you click this -- never on page load.",
    )
    if run_suggestions:
        # The shared cached loader is deliberately reused (same verification
        # pipeline, same TTL); the source toggles filter its output below. The
        # AI lane fires only when its toggle AND preference AND credential all
        # allow it -- passing include_ai=False prevents the paid calls.
        suggestion_rows, suggestion_dropped, _suggestion_note = _load_recommended_tickers(
            tuple(sorted({t.upper() for t in seed_tickers})),
            include_ai=want_ai_source and suggestions_ai_available,
            include_most_active=want_most_active,
            include_recent_ipos=want_recent_ipo,
            # The dedicated tab does not render the Briefing's separate
            # Claude curation note, so do not make and discard that paid call.
            include_ai_curation=False,
        )
        st.session_state["ticker_suggestions_result"] = {
            "rows": suggestion_rows,
            "dropped": suggestion_dropped,
            "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sources": {
                "most_active": want_most_active,
                "recent_ipo": want_recent_ipo,
                "ai_suggested": want_ai_source and suggestions_ai_available,
            },
        }

    suggestions_result = st.session_state.get("ticker_suggestions_result")
    if suggestions_result:
        row_fetch_times = sorted(
            {
                str(getattr(row, "fetched_at", "")).strip()
                for row in suggestions_result["rows"]
                if str(getattr(row, "fetched_at", "")).strip()
            }
        )
        if len(row_fetch_times) == 1:
            source_time = f"Source data fetched at {row_fetch_times[0]}. "
        elif row_fetch_times:
            source_time = (
                "Source rows were fetched between "
                f"{row_fetch_times[0]} and {row_fetch_times[-1]}. "
            )
        else:
            source_time = "No verified row carries a source fetch time. "
        st.caption(
            source_time
            + f"Displayed at {suggestions_result['ran_at']}. The source loader may "
            f"return results cached for up to {_RECOMMENDED_STOCKS_CACHE_TTL_SECONDS // 60} minutes. "
            # Counter-review AP8CR-001: review corrected the Briefing copy on
            # two points -- identity now includes a company name, and a
            # provider outage is observationally identical to an unidentifiable
            # symbol, so omission copy must not assert the security itself is
            # invalid. Both corrections apply verbatim here, on the page AP-8
            # is actually about; they were fixed on one consumer only.
            "Verification: every ticker shown resolved against real market "
            "data as a named US-listed equity. Rows are NOT screened on size, "
            "age, price, or liquidity (owner decision, 2026-08-12) -- where a "
            "row falls below this project's usual floors, or a measurement is "
            "unavailable, the row says so instead of being hidden. Judgment is "
            "yours; nothing here is a recommendation, and no listing carries "
            "any execution authority."
            + (
                f" {len(suggestions_result['dropped'])} candidate(s) could not be "
                "verified at this time and were omitted: "
                + ", ".join(sorted(set(suggestions_result["dropped"])))
                + "."
                if suggestions_result["dropped"]
                else ""
            )
        )
        source_labels = {
            "most_active": (
                "Most actively traded, split by today's price direction "
                "(source: yfinance screen — volume and price move, not order flow)"
            ),
            "recent_ipo": "Recent IPOs (source: Finnhub calendar)",
            "ai_suggested": "Claude suggestions with measured comparison (source: LLM, verified)",
        }
        for category, label in source_labels.items():
            if not suggestions_result["sources"].get(category):
                continue
            items = [
                r for r in suggestions_result["rows"] if r.reason_category == category
            ]
            with st.expander(f"{label} ({len(items)})", expanded=bool(items)):
                if category == "most_active":
                    _render_most_active_by_direction(items)
                elif items:
                    st.dataframe(
                        [
                            {
                                "Ticker": r.ticker,
                                "Source": category,
                                "Detail / stated reason & measured evidence": r.detail,
                                "Fetched at": r.fetched_at,
                            }
                            for r in items
                        ],
                        width="stretch",
                        hide_index=True,
                    )
                else:
                    st.caption("No verified candidates from this source on this run.")
        st.caption(
            "Research only — to act on any of these, add the ticker to the Buying "
            "cart yourself and go through the normal check/propose/approve workflow."
        )

# ---------------------------------------------------------------------------
# Backtest -- UI-3's read-only research surface. Composes the SAME
# backtest/engine.py walk-forward the CLI research scripts use, through the
# frozen inventory in backtest/interactive.py. It has no path to proposals,
# approvals, orders, or policy. QC-2 adds an audit-only research-look write;
# it cannot gate the run or lead toward action. A good-looking chart still
# leads nowhere. Confirmatory significance deliberately does NOT run here
# (see EXPLORATORY_CAVEATS).
# ---------------------------------------------------------------------------

_WHOLE_UNIVERSE_SCOPE = f"Entire universe ({len(UNIVERSE)} tickers)"


@st.cache_data(show_spinner=False)
def _load_backtest_synthetic_data(tickers: tuple[str, ...], days: int):
    """Deterministic (fixed-seed) synthetic OHLCV -- cache keyed by the
    ticker tuple and day count so widget interactions never regenerate.
    Returns (data, coverage); see _load_backtest_real_data for why the
    coverage check runs inside the cached body."""
    data = generate_synthetic(list(tickers), days=days)
    return data, inspect_data_coverage(
        data, requested_tickers=tickers, requested_sessions=days
    )


@st.cache_data(ttl=3600, show_spinner=False)
def _load_backtest_real_data(tickers: tuple[str, ...], lookback_days: int):
    """Real yfinance history, cached for an hour so parameter tweaks rerun
    the backtest without re-fetching the network data.

    The coverage check runs INSIDE this cached function on purpose
    (counter-review CRUI3-001): st.cache_data caches return values but
    never exceptions, so a failed/empty fetch raises here and nothing is
    cached -- the next attempt re-fetches instead of replaying an empty
    provider response for the rest of the TTL. Validating outside would
    leave the empty dict cached and every retry inside the hour would
    fail against it even after the network recovered."""
    data = fetch_historical(list(tickers), lookback_days=lookback_days)
    return data, inspect_data_coverage(
        data, requested_tickers=tickers, requested_sessions=lookback_days
    )


if page == "Backtest":
    st.caption(
        "Research-only walk-forward backtesting of the project's signal "
        "scanners -- the same engine the CLI research scripts use. Nothing "
        "here can propose, approve, or submit a trade."
    )

    signal_by_label = {signal.label: signal for signal in SIGNAL_INVENTORY}
    chosen_label = st.selectbox(
        "Signal",
        list(signal_by_label),
        key="bt_signal",
    )
    bt_signal = signal_by_label[chosen_label]
    st.caption(bt_signal.description)

    param_values: dict[str, float] = {}
    param_columns = st.columns(2)
    for index, spec in enumerate(bt_signal.params):
        with param_columns[index % 2]:
            if spec.kind == "int":
                value = st.number_input(
                    spec.label,
                    min_value=int(spec.min_value),
                    max_value=int(spec.max_value),
                    value=int(spec.default),
                    step=int(spec.step),
                    key=f"bt_param_{bt_signal.key}_{spec.name}",
                    help=spec.help,
                )
            else:
                value = st.number_input(
                    spec.label,
                    min_value=float(spec.min_value),
                    max_value=float(spec.max_value),
                    value=float(spec.default),
                    step=float(spec.step),
                    key=f"bt_param_{bt_signal.key}_{spec.name}",
                    help=spec.help,
                )
        param_values[spec.name] = value

    source_choice = st.radio(
        "Data source",
        (
            "Synthetic (plumbing check, seconds)",
            "Real market data (yfinance; minutes on first fetch)",
        ),
        key="bt_data_source",
        help=(
            "Synthetic random-walk data proves the pipeline works and is "
            "the safe default; only real history can say anything about "
            "edge -- and even then only as an exploratory look."
        ),
    )
    use_real_data = source_choice.startswith("Real")

    scope_choice = st.selectbox(
        "Universe scope",
        [_WHOLE_UNIVERSE_SCOPE] + [f"Basket: {name}" for name in sorted(BASKETS)],
        key="bt_scope",
    )
    if scope_choice == _WHOLE_UNIVERSE_SCOPE:
        bt_tickers = tuple(UNIVERSE)
    else:
        bt_tickers = tuple(BASKETS[scope_choice.removeprefix("Basket: ")])

    bt_lookback = st.number_input(
        "History length (trading days)",
        min_value=120,
        max_value=LOOKBACK_DAYS,
        value=504,
        step=21,
        key="bt_lookback_days",
        help=(
            f"Walk-forward window. The scanner pipeline's own config uses "
            f"{LOOKBACK_DAYS} days (~7 years); shorter runs are faster but "
            f"produce fewer, luck-dominated signals."
        ),
    )
    bt_horizons = st.multiselect(
        "Hold horizons",
        HORIZON_SWEEP_DAYS,
        default=HORIZON_SWEEP_DAYS,
        format_func=lambda days: HORIZON_LABELS.get(days, f"{days}d"),
        key="bt_horizons",
        help=(
            "Each selected horizon runs its own walk-forward pass. An edge "
            "that only appears at one arbitrary exit timing is suspect."
        ),
    )
    st.caption(
        f"Entry timing: next_open (executable; fixed -- the legacy "
        f"same-close timing is not offered here). Slippage: "
        f"{SLIPPAGE_PCT * 100:.2f}% per leg, deducted round-trip."
    )

    if st.button("Run backtest", type="primary", key="bt_run"):
        if not bt_horizons:
            st.error("Select at least one hold horizon.")
        else:
            try:
                with st.spinner(
                    "Fetching real history and walking forward -- first "
                    "fetch can take minutes..."
                    if use_real_data
                    else "Running the walk-forward backtest..."
                ):
                    bt_data, data_coverage = (
                        _load_backtest_real_data(bt_tickers, int(bt_lookback))
                        if use_real_data
                        else _load_backtest_synthetic_data(
                            bt_tickers, int(bt_lookback)
                        )
                    )
                    # Fetch first so identity binds the exact dated bars, then
                    # record BEFORE the engine reveals a result. Widget labels
                    # alone are not a repeat: real history grows/corrects and
                    # synthetic dates move. Recording never gates research.
                    try:
                        look_record = record_research_look(
                            _store(),
                            surface="ui_backtest",
                            signal_key=bt_signal.key,
                            configuration={
                                "params": dict(param_values),
                                "scope": scope_choice,
                                "lookback_days": int(bt_lookback),
                                "hold_days_options": sorted(bt_horizons),
                                "entry_timing": "next_open",
                                "slippage_pct": SLIPPAGE_PCT,
                            },
                            data_source="real" if use_real_data else "synthetic",
                            data_fingerprint=research_data_fingerprint(bt_data),
                            code_commit=current_commit(require_clean=True),
                            hypothesis_count=(
                                len(bt_horizons)
                                * len(INTERACTIVE_DIRECTION_CELLS)
                            ),
                        )
                        look_error = None
                    except Exception as exc:  # research must not be blocked
                        look_record, look_error = None, str(exc)
                    results_by_horizon = run_interactive_backtest(
                        bt_data,
                        signal_key=bt_signal.key,
                        param_values=param_values,
                        hold_days_options=sorted(bt_horizons),
                        slippage_pct=SLIPPAGE_PCT,
                    )
                st.session_state["backtest_run"] = {
                    "signal_key": bt_signal.key,
                    "signal_label": bt_signal.label,
                    "param_values": dict(param_values),
                    "source": "real" if use_real_data else "synthetic",
                    "scope": scope_choice,
                    "ticker_count": data_coverage.loaded_ticker_count,
                    "data_coverage": data_coverage,
                    "lookback_days": int(bt_lookback),
                    "hold_days_options": tuple(sorted(bt_horizons)),
                    "entry_timing": "next_open",
                    "slippage_pct": SLIPPAGE_PCT,
                    "results_by_horizon": results_by_horizon,
                    "ran_at": datetime.now(timezone.utc).isoformat(),
                    "look_record": look_record,
                    "look_error": look_error,
                }
            except Exception as exc:
                st.error(f"Backtest failed: {exc}")

    completed_run = st.session_state.get("backtest_run")
    if completed_run is None:
        st.info("Configure a signal above and click Run backtest.")
    else:
        st.subheader(f"Results -- {completed_run['signal_label']}")
        # QC-2: show the multiplicity denominator next to the result, so a
        # good-looking p-value is read in the context of how many
        # configurations were tried to find it.
        if completed_run.get("look_error"):
            st.warning(
                "This run was NOT recorded in the research-look registry "
                f"({completed_run['look_error']}). The multiplicity count "
                "below therefore understates how many hypotheses have been "
                "examined."
            )
        if completed_run.get("source") == "real":
            try:
                look_summary = research_look_summary(
                    _store(), surface="ui_backtest", data_source="real"
                )
            except Exception as exc:
                look_summary = None
                st.warning(f"Research-look registry unavailable: {exc}")
        else:
            look_summary = None
            st.caption(
                "Synthetic plumbing runs are logged for audit but excluded "
                "from the real-market hypothesis denominator."
            )
        if look_summary is not None:
            repeat_note = ""
            record = completed_run.get("look_record")
            if record is not None and not record.get("is_new_look", True):
                repeat_note = (
                    f" This exact configuration had already been examined "
                    f"{record['repeat_count'] - 1} time(s), so it did not add "
                    "a new test."
                )
            st.caption(
                f"**Multiplicity:** {look_summary['interpretation']}"
                + repeat_note
            )
        run_params = ", ".join(
            f"{name}={value}"
            for name, value in sorted(completed_run["param_values"].items())
        )
        stored_horizons = list(
            completed_run.get(
                "hold_days_options",
                sorted(completed_run["results_by_horizon"]),
            )
        )
        stored_entry_timing = completed_run.get("entry_timing", "next_open")
        stored_slippage = completed_run.get("slippage_pct", SLIPPAGE_PCT)
        st.caption(
            f"Run configuration: {completed_run['source']} data, "
            f"{completed_run['scope']} ({completed_run['ticker_count']} "
            f"tickers), {completed_run['lookback_days']} trading days, "
            f"hold horizons {stored_horizons}, {run_params}, "
            f"entry {stored_entry_timing}, "
            f"slippage {stored_slippage * 100:.2f}% per leg, "
            f"ran {completed_run['ran_at']}. "
            "Results reflect this configuration, not any widget changed "
            "since."
        )
        if completed_run["source"] == "synthetic":
            st.warning(SYNTHETIC_CAVEAT)
        else:
            st.warning(EXPLORATORY_CAVEATS)

        data_coverage = completed_run.get("data_coverage")
        if data_coverage is not None and data_coverage.has_gaps:
            coverage_parts = [
                f"loaded {data_coverage.loaded_ticker_count} of "
                f"{data_coverage.requested_ticker_count} requested tickers",
                f"{data_coverage.complete_ticker_count} had the full "
                f"{completed_run['lookback_days']}-session history",
            ]
            if data_coverage.missing_tickers:
                coverage_parts.append(
                    "missing: " + ", ".join(data_coverage.missing_tickers)
                )
            if data_coverage.underfilled_tickers:
                coverage_parts.append(
                    "short history: "
                    + ", ".join(
                        f"{ticker} ({sessions})"
                        for ticker, sessions in data_coverage.underfilled_tickers
                    )
                )
            st.warning(
                "Incomplete market-data coverage -- results describe only "
                "the rows actually loaded: " + "; ".join(coverage_parts) + "."
            )

        summary = summarize_multi_horizon(
            completed_run["results_by_horizon"],
            entry_timing=stored_entry_timing,
        )
        if summary.empty:
            st.info(
                "No signals were flagged anywhere in this window -- "
                "nothing to score."
            )
        else:
            st.dataframe(summary, width="stretch", hide_index=True)

            horizons_with_rows = [
                horizon
                for horizon, frame in sorted(
                    completed_run["results_by_horizon"].items()
                )
                if not frame.empty
            ]
            if horizons_with_rows:
                # A previous run may have offered different horizons; a
                # stale selection outside the current options would make
                # the selectbox error out.
                if st.session_state.get("bt_chart_horizon") not in horizons_with_rows:
                    st.session_state.pop("bt_chart_horizon", None)
                chart_horizon = st.selectbox(
                    "Chart hold horizon",
                    horizons_with_rows,
                    format_func=lambda days: HORIZON_LABELS.get(
                        days, f"{days}d"
                    ),
                    key="bt_chart_horizon",
                )
                st.line_chart(
                    cumulative_return_frame(
                        completed_run["results_by_horizon"][chart_horizon]
                    ),
                    height=280,
                )
                st.caption(CHART_CAPTION)


# ---------------------------------------------------------------------------
# Reports -- GR-7's owner-facing reporting surface. STRICTLY READ-ONLY: it
# renders records the platform already holds and never proposes, approves,
# sizes, or submits anything. GR-7a fills it with the annual realized-gain
# export; GR-7b/GR-7c (idle cash, performance attribution) land here too
# rather than each inventing a new page.
# ---------------------------------------------------------------------------

if page == "Reports":
    st.caption(
        "Read-only reporting over records this app already holds. Nothing "
        "here places, approves, or changes a trade. Coverage verification "
        "uses a live broker snapshot only when Alpaca is configured; it "
        "never treats the sample portfolio as the broker."
    )

    with st.expander("Annual realized gains (tax year)", expanded=True):
        st.caption(
            "Built from this app's recorded fills and journal-confirmed "
            "corporate actions only. It is a reconciliation aid -- **not tax "
            "advice** and not a substitute for your broker's 1099-B."
        )
        tax_year = st.number_input(
            "Tax year",
            min_value=2000,
            max_value=2100,
            value=_now_eastern().year,
            step=1,
            key="tax_report_year",
        )
        if st.button("Build report", key="tax_report_build"):
            from execution.alpaca_broker import is_configured as _alpaca_configured
            from assistant.context_builder import (
                build_portfolio_snapshot_from_alpaca as _live_portfolio,
            )

            coverage_portfolio = None
            coverage_note = None
            coverage_unavailable_reason = None
            if _alpaca_configured():
                try:
                    coverage_portfolio = _live_portfolio()
                except Exception as exc:
                    # A data/broker outage must degrade the coverage CLAIM,
                    # not break the export (GR-4 discipline applied to
                    # reporting). Do not fall back to SAMPLE_POSITIONS.
                    coverage_unavailable_reason = (
                        f"Coverage could not be verified ({type(exc).__name__}); "
                        "the report is marked unverified."
                    )
                    coverage_note = coverage_unavailable_reason
            else:
                coverage_unavailable_reason = (
                    "no live broker configured; share coverage was not "
                    "verified against a broker snapshot"
                )
                coverage_note = coverage_unavailable_reason
            try:
                st.session_state["tax_report"] = build_annual_tax_report(
                    store,
                    int(tax_year),
                    portfolio=coverage_portfolio,
                    coverage_unavailable_reason=coverage_unavailable_reason,
                )
                st.session_state["tax_report_note"] = coverage_note
            except TaxReportError as exc:
                st.session_state.pop("tax_report", None)
                st.session_state.pop("tax_report_note", None)
                st.error(f"Tax report unavailable: {exc}")

        _tax_report = st.session_state.get("tax_report")
        if _tax_report is not None and _tax_report.tax_year != int(tax_year):
            st.info(
                f"Built report is for tax year {_tax_report.tax_year}. "
                "Click Build report to refresh for the selected year."
            )
            _tax_report = None
        if _tax_report is not None:
            if st.session_state.get("tax_report_note"):
                st.warning(st.session_state["tax_report_note"])
            if _tax_report.complete:
                st.success(
                    "Coverage COMPLETE: recorded lots match the broker's "
                    "share counts."
                )
            elif _tax_report.coverage.get("verified"):
                st.error(
                    "Coverage INCOMPLETE -- recorded lots do not match the "
                    "broker's share counts. "
                    f"{_tax_report.coverage.get('reason')}"
                )
            else:
                st.warning(
                    "Coverage UNVERIFIED -- this report was not checked "
                    "against a live broker snapshot."
                )

            st.dataframe(
                [
                    {
                        "Bucket": label,
                        "Sales": totals.sale_count,
                        "Proceeds": str(totals.proceeds),
                        "Cost basis": str(totals.cost_basis),
                        "Realized P&L": str(totals.realized_pnl),
                    }
                    for label, totals in (
                        ("Short-term", _tax_report.short_term),
                        ("Long-term", _tax_report.long_term),
                        ("Total", _tax_report.total),
                    )
                ],
                width="stretch",
                hide_index=True,
            )
            st.caption(
                f"{_tax_report.wash_sale_flagged_count} wash-sale flag(s) — "
                "advisory only; cost basis is never adjusted here because the "
                "rule spans accounts this app cannot see."
            )

            if _tax_report.rows:
                st.dataframe(
                    [row.to_dict() for row in _tax_report.rows],
                    width="stretch",
                    hide_index=True,
                )
            else:
                st.info(
                    f"No realized sales recorded in tax year "
                    f"{_tax_report.tax_year}."
                )

            st.download_button(
                "Download CSV",
                data=render_tax_report_csv(_tax_report),
                file_name=f"realized-gains-{_tax_report.tax_year}.csv",
                mime="text/csv",
                key="tax_report_csv",
            )
            st.download_button(
                "Download JSON",
                data=render_tax_report_json(_tax_report),
                file_name=f"realized-gains-{_tax_report.tax_year}.json",
                mime="application/json",
                key="tax_report_json",
            )

    # GR-7b. Renders on load rather than behind a button: idle cash is a
    # standing condition, not a report you ask for, and the whole point is
    # that it was previously invisible. No button here can place a trade.
    # Portfolio comes from a live Alpaca snapshot (or sample) — never
    # _load_packet, which records GR-4 provider-fetch rows and would break
    # this page's read-only contract the same way tax Build used to.
    with st.expander("Idle cash vs policy and mandate", expanded=True):
        from assistant.cash_reporting import CashReportError, evaluate_idle_cash
        from assistant.mandate import load_mandate as _load_mandate

        try:
            _cash_policy = load_policy(policy_path)
            # Cached and store-free: read-only like the review required,
            # without a live broker call on every rerun of this page or a
            # snapshot that disagrees with Briefing. See
            # _load_readonly_portfolio().
            _cash_portfolio = _load_readonly_portfolio()
            _cash = evaluate_idle_cash(
                _cash_portfolio, _cash_policy, _load_mandate()
            )
        except CashReportError as _cash_error:
            st.warning(f"Idle-cash report unavailable: {_cash_error}")
        except Exception as _cash_error:
            st.warning(
                f"Idle-cash report unavailable ({type(_cash_error).__name__}): "
                f"{_cash_error}"
            )
        else:
            _totals = _cash["totals"]
            _bounds = _cash["policy_bounds"]
            _objective = _cash["mandate_objective"]

            if not _cash["exact_numerics"]:
                st.caption(
                    "Figures derive from display-rounded values rather than "
                    "exact broker decimals."
                )
            _left, _middle, _right = st.columns(3)
            _left.metric("Cash", f"${float(_totals['cash']):,.0f}", f"{_totals['cash_pct']}%")
            _middle.metric(
                "Invested", f"${float(_totals['invested']):,.0f}", f"{_totals['invested_pct']}%"
            )
            if _bounds["policy_headroom"] is None:
                _right.metric("Policy headroom", "Unavailable")
            else:
                _right.metric(
                    "Policy headroom", f"${float(_bounds['policy_headroom']):,.0f}"
                )

            if _bounds["reserve_floor_breached"]:
                st.error(
                    "Cash is BELOW the policy reserve floor of "
                    f"${float(_bounds['reserve_floor']):,.0f}."
                )
            if _bounds["binding_constraint"] is None:
                st.warning(
                    "Exact policy headroom is unavailable: "
                    f"{_bounds['policy_headroom_unavailable_reason']}."
                )
            else:
                st.caption(
                    f"Headroom is limited by **{_bounds['binding_constraint'].replace('_', ' ')}** "
                    "— the room the policy leaves, not a suggestion to use it."
                )

            _band = (
                f"{_objective['target_annualized_volatility_min_pct']}–"
                f"{_objective['target_annualized_volatility_max_pct']}%"
            )
            _measured = _objective["measured"]
            if _measured["available"]:
                _verdict = "inside" if _measured["within_mandate_band"] else "outside"
                st.write(
                    f"Mandate volatility band {_band}: measured "
                    f"{_measured['annualized_volatility_pct']}% is **{_verdict}** the band."
                )
            else:
                st.write(
                    f"Mandate volatility band {_band}: "
                    f"{_measured['unavailable_reason']}."
                )
            if _objective["required_invested_volatility_pct"] is not None:
                st.write(
                    f"At {_totals['invested_pct']}% invested, holdings would need "
                    f"**{_objective['required_invested_volatility_pct']}%** annualized "
                    "volatility to reach the mandate floor"
                    + (
                        f" — and **{_objective['required_invested_volatility_at_policy_ceiling_pct']}%** "
                        "even at the policy's own exposure ceiling."
                        if _objective["required_invested_volatility_at_policy_ceiling_pct"]
                        else "."
                    )
                )
            else:
                st.write(
                    "Required-volatility figure unavailable: "
                    f"{_objective['required_unavailable_reason']}."
                )
            st.caption(_objective["required_assumption"])

    # Three-sleeve engine, M1 (docs/reference/THREE_SLEEVE_ENGINE_PLAN.md).
    # Renders on load like idle cash: sleeve drift and threshold crossings
    # are standing conditions, not reports you ask for. Same read-only
    # contract -- fills and journal postings are records this app already
    # holds, and the portfolio comes from _load_readonly_portfolio(), never
    # a packet rebuild that writes provider-fetch rows.
    with st.expander("Three-sleeve engine status", expanded=True):
        from assistant.corporate_actions import (
            fills_with_confirmed_splits as _engine_fills,
        )
        from assistant.sleeve_report import (
            SleeveReportError as _SleeveReportError,
            evaluate_sleeves as _evaluate_sleeves,
        )
        from assistant.tax_lots import (
            TaxLotError as _EngineLotError,
            build_ledger as _build_lot_ledger,
        )

        st.caption(
            "Measures the portfolio against the owner's stated three-sleeve "
            "preference (dividend income floor, per-lot growth review "
            "thresholds, dividend-to-leveraged reinvestment). A preference "
            "on record, **not validated research** — and nothing here "
            "places, approves, or changes a trade."
        )
        try:
            _sleeve_portfolio = _load_readonly_portfolio()
            _sleeve_ledger = _build_lot_ledger(_engine_fills(store))
            _sleeves = _evaluate_sleeves(
                _sleeve_portfolio, _sleeve_ledger, store.list_journal_postings()
            )
        except _SleeveReportError as _sleeve_error:
            st.warning(f"Sleeve report unavailable: {_sleeve_error}")
        except (_EngineLotError, ValueError, KeyError) as _sleeve_error:
            st.warning(
                "Sleeve report unavailable: recorded fills cannot be replayed "
                f"into lots ({_sleeve_error})"
            )
        except Exception as _sleeve_error:
            st.warning(
                f"Sleeve report unavailable ({type(_sleeve_error).__name__}): "
                f"{_sleeve_error}"
            )
        else:
            _dividend = _sleeves["dividend_sleeve"]
            _growth = _sleeves["growth_sleeve"]
            _reinvest = _sleeves["reinvest_sleeve"]
            _income = _sleeves["dividend_income"]
            _engine = _sleeves["engine"]

            _c1, _c2, _c3, _c4, _c5 = st.columns(5)
            _c1.metric(
                "Dividend sleeve",
                f"{_dividend['pct_of_equity']}%",
                f"floor {_engine['floor_pct']}%",
            )
            _c2.metric(
                "Lots at gain review",
                _growth["lots_at_gain_review"],
                (
                    f"LT-gated trim {_engine['gain_review_trim_fraction']}"
                    if _engine["gain_review_requires_long_term"]
                    else f"trim {_engine['gain_review_trim_fraction']}"
                ),
                delta_color="off",
            )
            _c3.metric(
                "Awaiting long-term",
                _growth["lots_awaiting_long_term"],
                "above threshold, gate holds",
                delta_color="off",
            )
            _c4.metric(
                "Lots at decline review", _growth["lots_at_decline_review"]
            )
            _c5.metric("Reinvest sleeve", f"{_reinvest['pct_of_equity']}%")

            if _dividend["floor_status"] == "below_floor":
                st.warning(
                    f"Dividend sleeve ({_dividend['pct_of_equity']}% of "
                    "equity) is BELOW the stated floor of "
                    f"{_engine['floor_pct']}%."
                )
            for _position in _growth["positions"]:
                if _position["lot_coverage"] != "full":
                    st.warning(
                        f"{_position['ticker']}: lot coverage is "
                        f"{_position['lot_coverage']} — "
                        f"{_position['coverage_reason']}"
                    )
            def _review_label(lot) -> str | None:
                if lot["crossed_gain_review_threshold"]:
                    return (
                        f"gain — trim {_engine['gain_review_trim_fraction']}"
                    )
                if lot["gain_threshold_met_awaiting_long_term"]:
                    return "gain met — awaiting long-term"
                if lot["crossed_decline_review_threshold"]:
                    return "decline"
                return None

            _flagged = [
                (_position["ticker"], _lot, _label)
                for _position in _growth["positions"]
                for _lot in _position["lots"]
                if (_label := _review_label(_lot)) is not None
            ]
            if _flagged:
                st.write("Lots at or near a review threshold (per-lot basis):")
                st.dataframe(
                    [
                        {
                            "Ticker": _ticker,
                            "Lot": _lot["lot_id"],
                            "Unrealized %": _lot["unrealized_pnl_pct"],
                            "Unrealized $": _lot["unrealized_pnl"],
                            "Review": _label,
                            "Term if disposed now": _lot["term_if_sold_now"],
                            "Days to long-term": _lot["days_to_long_term"],
                            "First long-term date": _lot["first_long_term_date"],
                        }
                        for _ticker, _lot, _label in _flagged
                    ],
                    width="stretch",
                )
                st.caption(
                    "Revision 2: the long-term gate is part of the rule — a "
                    "lot above the price threshold but still short-term has "
                    "NOT crossed gain review; its countdown shows when the "
                    "gate opens. The recorded rule's trim fraction is "
                    f"{_engine['gain_review_trim_fraction']}; this panel only "
                    "reports the state. Classification and dates only; no "
                    "bracket is estimated and no trade is proposed."
                )
            else:
                st.caption("No lot is at or near a review threshold right now.")
            st.write(
                f"Confirmed dividend income ${_income['confirmed_total']} "
                f"across {_income['posting_count']} posting(s). "
                f"{_income['note']}."
            )
            for _overlap in _sleeves["single_issuer_overlap"]:
                st.warning(
                    f"Single-issuer overlap on {_overlap['issuer']}: "
                    + "; ".join(_overlap["routes"])
                )


# ---------------------------------------------------------------------------
# Operations -- GR-5's single operator dashboard. STRICTLY READ-ONLY except
# the two explicit alert-delivery buttons: it never proposes, approves,
# sizes, submits, or cancels anything, and it never edits policy. Every
# number comes from the enforcing function or the durable record, never a
# re-implementation.
# ---------------------------------------------------------------------------

if page == "Operations":
    st.caption(
        "One place to see whether the platform is healthy and whether anything "
        "is trying to reach you. Read-only: nothing here can place, approve, or "
        "cancel a trade."
    )

    from assistant.alert_delivery import (
        RecordingChannel,
        WindowsToastChannel,
        deliver_pending_alerts,
        pending_briefing_alerts,
        run_channel_self_test,
        self_test_freshness,
        undelivered_critical_alerts,
    )

    ops_store = _store()

    with st.container(border=True):
        st.subheader("Critical alert delivery")
        undelivered = undelivered_critical_alerts(ops_store)
        freshness = self_test_freshness(ops_store)
        delivery_columns = st.columns(2)
        with delivery_columns[0]:
            if undelivered:
                st.error(
                    f"{len(undelivered)} critical alert(s) have NOT been delivered: "
                    + ", ".join(sorted(a["fingerprint"] for a in undelivered))
                )
            else:
                st.success("Every open critical alert has a recorded delivery.")
        with delivery_columns[1]:
            (st.success if freshness["ok"] else st.warning)(
                f"Channel self-test: {freshness['detail']}"
            )

        action_columns = st.columns(2)
        with action_columns[0]:
            if st.button("Deliver pending critical alerts", key="ops_deliver"):
                report = deliver_pending_alerts(ops_store, WindowsToastChannel())
                if report["healthy"]:
                    st.success(f"Delivered {len(report['delivered'])} alert(s).")
                else:
                    st.error(
                        f"{len(report['failed'])} delivery failure(s): "
                        + report["failed"][0]["detail"][:200]
                    )
                st.rerun()
        with action_columns[1]:
            if st.button("Run channel self-test (sends a real toast)", key="ops_selftest"):
                result = run_channel_self_test(ops_store, WindowsToastChannel())
                if result["passed"]:
                    st.success("Self-test delivered and verified from the delivery record.")
                else:
                    st.error(f"Self-test FAILED: {result['delivery']['detail'][:200]}")
                st.rerun()

    with st.container(border=True):
        st.subheader("Open alerts")
        open_alerts = ops_store.list_operational_alerts(status="open", limit=50)
        if not open_alerts:
            st.success("No open operational alerts.")
        else:
            st.dataframe(
                [
                    {
                        "severity": alert["severity"],
                        "category": alert["category"],
                        "message": alert["message"][:120],
                        "occurrences": alert["occurrences"],
                        "last seen": alert["last_seen_at"],
                        "delivered": bool(
                            ops_store.latest_successful_delivery(
                                alert["fingerprint"],
                                min_occurrences=alert["occurrences"],
                            )
                        ),
                    }
                    for alert in open_alerts
                ],
                width="stretch",
                hide_index=True,
            )
        batched = pending_briefing_alerts(ops_store)
        st.caption(
            f"{len(batched)} warning-level alert(s) are batched for the daily "
            "briefing rather than interrupting you (owner routing decision)."
        )

    with st.container(border=True):
        st.subheader("Recent delivery attempts")
        deliveries = ops_store.list_alert_deliveries(limit=20)
        if not deliveries:
            st.info("No delivery attempt has been recorded yet.")
        else:
            st.dataframe(
                [
                    {
                        "outcome": record["outcome"],
                        "channel": record["channel"],
                        "severity": record["severity"],
                        "fingerprint": record["fingerprint"],
                        "attempted": record["attempted_at"],
                        "detail": record["detail"][:80],
                    }
                    for record in deliveries
                ],
                width="stretch",
                hide_index=True,
            )

    with st.container(border=True):
        st.subheader("Platform readiness")
        try:
            from assistant.mandate import load_mandate
            from assistant.platform_readiness import build_platform_readiness

            readiness_report = build_platform_readiness(
                ops_store,
                load_policy(policy_path),
                load_mandate(),
                check_broker=False,
            ).to_dict()
            st.dataframe(
                [
                    {
                        "dimension": dimension["name"],
                        "status": dimension["status"],
                        "explanation": dimension["explanation"][:160],
                    }
                    for dimension in readiness_report["dimensions"]
                ],
                width="stretch",
                hide_index=True,
            )
            st.caption(
                "Offline evaluation (no broker calls). Dimensions are scored "
                "independently and never averaged."
            )
        except Exception as exc:  # readiness must never break the dashboard
            st.warning(f"Readiness report unavailable: {exc}")

    with st.container(border=True):
        st.subheader("Operational state")
        heartbeat = ops_store.get_system_state("operations_heartbeat", default={})
        last_backup = ops_store.get_system_state("last_database_backup", default={})
        epoch = ops_store.get_active_paper_evidence_epoch()
        state_columns = st.columns(3)
        with state_columns[0]:
            st.metric(
                "Last health heartbeat",
                (heartbeat or {}).get("at", "never")[:19],
                help="Written by the operations watchdog/cycle.",
            )
        with state_columns[1]:
            st.metric(
                "Last verified backup",
                (last_backup or {}).get("completed_at", "never")[:19],
            )
        with state_columns[2]:
            st.metric(
                "Active evidence epoch",
                epoch["evidence_epoch"] if epoch else "none",
                help="A formal paper-evidence epoch is required for promotion evidence.",
            )
        drills = ops_store.list_operational_drills(limit=10)
        if drills:
            st.caption("Most recent operational drills")
            st.dataframe(
                [
                    {
                        "drill": drill["drill_type"],
                        "passed": bool(drill["passed"]),
                        "performed": drill["performed_at"][:19],
                        "epoch": drill.get("evidence_epoch") or "verification-only",
                    }
                    for drill in drills
                ],
                width="stretch",
                hide_index=True,
            )


    # ---------------------------------------------------------------------------
    # Settings & Features -- three distinct control classes
    # (docs/reference/UI_FEATURE_CONTROLS_DESIGN.md sections 2-3): UI preferences
    # (session-state toggles), authoritative trading policy (protected workflow,
    # typed confirmation, new fingerprint), and read-only credential/safety status
    # (never editable here, never shows a secret value).
    # ---------------------------------------------------------------------------

if page == "Settings & Features":
    st.caption(
        "Three kinds of controls live here and they are deliberately not equal: "
        "**UI preferences** (plain toggles, this session only), **authoritative "
        "trading policy** (protected workflow with typed confirmation and a new "
        "policy fingerprint), and **read-only status** (cannot be changed here at "
        "all). No control on this page can enable live trading, edit a secret, or "
        "approve an order."
    )

    # ------------------------------------------------------------------ #
    # 1. Authoritative trading policy (protected workflow)               #
    # ------------------------------------------------------------------ #
    with st.container(border=True):
        st.subheader("Trading policy (authoritative — protected workflow)")
        try:
            settings_policy = load_policy(policy_path)
            settings_policy_error = None
        except Exception as exc:
            settings_policy = None
            settings_policy_error = str(exc)
        if settings_policy is None:
            st.error(f"The selected policy file could not be loaded: {settings_policy_error}")
        else:
            active_fingerprint = compute_policy_fingerprint(settings_policy)
            _sync_policy_editor_state(st.session_state, policy_path, settings_policy)
            st.caption(
                f"Active policy: **{settings_policy.name}** v{settings_policy.version} "
                f"({settings_policy.execution_mode}) — fingerprint `{active_fingerprint[:16]}…` — "
                f"file: `{policy_path}`"
            )
            update_notice = st.session_state.pop("policy_update_notice", None)
            if update_notice is not None:
                st.success(
                    f"Policy updated and saved: v{update_notice['old_version']} → "
                    f"v{update_notice['new_version']}, fingerprint "
                    f"`{update_notice['old_fingerprint'][:16]}…` → "
                    f"`{update_notice['new_fingerprint'][:16]}…`."
                )
                st.warning(
                    "Proposals created before this change can no longer execute. "
                    "Regenerate anything you still want on the Selling or "
                    "Propose & Approve page."
                )
            proposed_allow_new = st.checkbox(
                "Allow new positions (exposure-increasing buys become policy-eligible)",
                key="policy_edit_allow_new_positions",
                help="Authoritative policy, not a preference. Changing it requires the "
                "typed confirmation below. It does NOT bypass position, exposure, cash, "
                "freshness, earnings, duplicate-order, kill-switch, or approval controls "
                "-- it only stops the blanket refusal of buys that would open a new position.",
            )
            proposed_enable_strategy = st.checkbox(
                "Enable leveraged-pair strategy proposals by default",
                key="policy_edit_enable_strategy",
                help="Sets the durable default for the Propose & Approve page's per-run "
                "checkbox. Configured leveraged-pair strategies carry NO confirmed, "
                "production-authoritative evidence -- enabling only allows the "
                "deterministic generator to be checked; it approves nothing.",
            )
            proposed_whole_shares = st.toggle(
                "Whole shares only",
                key="policy_edit_whole_shares_only",
                help="Authoritative policy, on by default. While ON, every order "
                "quantity must be a whole number of shares -- enforced independently "
                "by the risk gate and by the broker adapter, so a code path that "
                "forgets to ask still refuses. Turning it OFF permits fractional "
                "quantities up to 9 decimal places on broker-marked fractionable "
                "assets; it does not relax any "
                "position, exposure, cash, freshness, duplicate-order, kill-switch, "
                "or approval control.",
            )
            proposed_enforce_reserve = st.toggle(
                "Enforce a minimum cash reserve",
                key="policy_edit_enforce_cash_reserve",
                help="Unchecking writes a reserve of 0%. That removes the BUFFER, "
                "not the solvency check: an order that would take your cash negative "
                "is still refused. There is deliberately no separate on/off field -- "
                "0 already means 'no reserve', and one rule with two sources of truth "
                "eventually disagrees with itself.",
            )
            if proposed_enforce_reserve:
                proposed_reserve_pct = st.number_input(
                    "Minimum cash reserve (% of equity)",
                    min_value=0.0, max_value=100.0, step=1.0,
                    key="policy_edit_cash_reserve_pct",
                )
                proposed_reserve_fraction = float(proposed_reserve_pct) / 100
            else:
                proposed_reserve_fraction = 0.0
                st.caption(
                    "No cash reserve will be required. Orders still cannot take your "
                    "cash balance negative."
                )
            pending_policy_change = (
                proposed_allow_new != settings_policy.allow_new_positions
                or proposed_enable_strategy != settings_policy.enable_strategy_proposals
                or proposed_whole_shares != settings_policy.whole_shares_only
                or proposed_reserve_fraction != float(settings_policy.min_cash_reserve_pct)
            )
            if pending_policy_change:
                st.warning(
                    "Applying this change writes the policy file atomically, bumps the "
                    "policy version, and produces a NEW policy fingerprint. **Every "
                    "pending proposal created under the current fingerprint will refuse "
                    "to execute and must be regenerated.** That refusal is deliberate: "
                    "an approval given under one policy must not authorize execution "
                    "under another."
                )
                policy_confirm_phrase = st.text_input(
                    'Type exactly "UPDATE POLICY" to enable the apply button',
                    key="policy_edit_confirm_phrase",
                )
                if st.button(
                    "Apply policy change",
                    type="primary",
                    disabled=policy_confirm_phrase.strip() != "UPDATE POLICY",
                ):
                    try:
                        updated_policy = policy_with_updated_flags(
                            settings_policy,
                            allow_new_positions=proposed_allow_new,
                            enable_strategy_proposals=proposed_enable_strategy,
                            whole_shares_only=proposed_whole_shares,
                            min_cash_reserve_pct=proposed_reserve_fraction,
                        )
                        save_policy(
                            updated_policy,
                            policy_path,
                            expected_fingerprint=active_fingerprint,
                            expected_version=settings_policy.version,
                        )
                    except Exception as exc:
                        st.error(f"Policy update refused; the file was not changed: {exc}")
                    else:
                        st.cache_data.clear()
                        new_fingerprint = compute_policy_fingerprint(updated_policy)
                        st.session_state["policy_update_notice"] = {
                            "old_version": settings_policy.version,
                            "new_version": updated_policy.version,
                            "old_fingerprint": active_fingerprint,
                            "new_fingerprint": new_fingerprint,
                        }
                        # Earlier parts of this page (editor seed, status panel)
                        # already rendered against the old policy. Rerun
                        # immediately so the editor, proposal defaults, and
                        # read-only status all agree with the policy that was
                        # just persisted.
                        st.rerun()
            else:
                st.caption("No policy change selected — the values above match the active policy.")

        # ------------------------------------------------------------------ #
        # 2. UI preferences (session-state; never authority)                 #
        # ------------------------------------------------------------------ #
        st.divider()
    with st.container(border=True):
        st.subheader("UI preferences (this session)")
        st.checkbox(
            "Fetch live earnings events by default",
            key=_pref_widget_key("pref_include_events_default"),
            value=bool(st.session_state.get("pref_include_events_default", False)),
            on_change=_sync_pref_from_widget,
            args=("pref_include_events_default",),
            help="Seeds the sidebar checkbox's default. The sidebar's per-run choice "
            "still wins once you touch it. Missing event data is always shown as "
            "honestly unavailable, never guessed.",
        )

    with st.container(border=True):
        st.subheader("Optional AI features (this session; every call still needs its own click)")
        anthropic_configured = is_ai_advisor_configured()
        st.caption(
            f"Anthropic credential: **{'Configured' if anthropic_configured else 'Not configured'}** "
            "(presence only — the key value is never displayed, stored, or accepted here). "
            "Credential presence makes features available; it never triggers a call by itself."
        )
        st.checkbox(
            "Enable optional AI features (master)",
            key=_pref_widget_key(_AI_MASTER_PREF_KEY),
            value=bool(st.session_state.get(_AI_MASTER_PREF_KEY, False)),
            on_change=_sync_pref_from_widget,
            args=(_AI_MASTER_PREF_KEY,),
            help="Master gate over every optional LLM surface. Off means no AI control "
            "is offered anywhere; deterministic content is completely unaffected either way.",
        )
        master_on = bool(st.session_state.get(_AI_MASTER_PREF_KEY, False))
        for pref_key, pref_label, pref_boundary in _AI_FEATURE_PREFS:
            st.checkbox(
                pref_label,
                key=_pref_widget_key(pref_key),
                value=bool(st.session_state.get(pref_key, False)),
                on_change=_sync_pref_from_widget,
                args=(pref_key,),
                disabled=not master_on,
                help=pref_boundary
                + (" (Enable the master toggle above first.)" if not master_on else ""),
            )

        # ------------------------------------------------------------------ #
        # 3. Read-only status (data sources + safety)                        #
        # ------------------------------------------------------------------ #
        st.divider()
    with st.container(border=True):
        st.subheader("Data-source status (read-only)")
        provider_rows = [
            {
                "Provider": "Alpaca paper trading",
                "Status": "Configured" if is_configured() else "Not configured",
                "Notes": "Portfolio, quotes, and paper order routing. Unconfigured = sample portfolio.",
            },
            {
                "Provider": "Finnhub IPO calendar",
                "Status": "Configured" if is_ipo_calendar_configured() else "Not configured",
                "Notes": "Recent-IPO suggestion lane (FINNHUB_API_KEY).",
            },
            {
                "Provider": "Databento research ingestion",
                "Status": "Configured" if os.environ.get("DATABENTO_API_KEY") else "Not configured",
                "Notes": "Licensed research data. Availability here never starts a download -- "
                "downloads remain explicit CLI commands with a cost estimate and cap.",
            },
            {
                "Provider": "Anthropic optional AI",
                "Status": "Configured" if anthropic_configured else "Not configured",
                "Notes": "Optional advisory features only (ANTHROPIC_API_KEY). No proposal authority.",
            },
        ]
        st.dataframe(provider_rows, width="stretch", hide_index=True)

    with st.container(border=True):
        st.subheader("Safety status (read-only — sourced from the enforcing code, not re-computed here)")
        # Each row reads the SAME function/state the execution path enforces with,
        # so this panel cannot disagree with enforcement (the platform-readiness /
        # fake-staleness lessons: a status display that re-implements its check
        # eventually drifts from the check).
        persistent_kill = store.get_kill_switch()
        env_kill = env_kill_switch_active()
        safety_rows = [
            {
                "Control": "Trading mode (config.PAPER_TRADING)",
                "State": "PAPER" if PAPER_TRADING else "LIVE (verify immediately)",
                "Detail": "Cannot be changed from this app, deliberately.",
            },
            {
                "Control": "Environment kill switch",
                "State": "ENGAGED" if env_kill else "off",
                "Detail": "assistant.kill_switch.env_kill_switch_active() -- the same "
                "call execution makes.",
            },
            {
                "Control": "Persistent kill switch",
                "State": "ENGAGED" if persistent_kill.get("active") else "off",
                "Detail": (
                    f"Reason: {persistent_kill.get('reason') or '—'} "
                    "(store.get_kill_switch(), the same read execution makes)."
                ),
            },
            {
                "Control": "Active policy",
                "State": (
                    f"{settings_policy.name} v{settings_policy.version} "
                    f"({settings_policy.execution_mode})"
                    if settings_policy is not None
                    else "UNLOADABLE — see error above"
                ),
                "Detail": (
                    f"Fingerprint {compute_policy_fingerprint(settings_policy)[:16]}… "
                    "(compute_policy_fingerprint, the same function approval binds to)."
                    if settings_policy is not None
                    else "Fix the policy file before trading."
                ),
            },
            {
                "Control": "Per-order human approval",
                "State": "REQUIRED (structural)",
                "Detail": "Typed approval phrase per proposal; overrides need the separate "
                "order-specific phrase. No batch or autonomous approval exists.",
            },
        ]
        st.dataframe(safety_rows, width="stretch", hide_index=True)
        if (env_kill or persistent_kill.get("active")):
            st.error(
                "A kill switch is ENGAGED — execution will refuse orders until it is "
                "cleared through the CLI kill-switch workflow."
            )
