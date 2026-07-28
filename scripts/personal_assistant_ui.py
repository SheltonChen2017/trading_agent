"""
Click-around Streamlit front end for the personal trading assistant.

This is ONLY a different presentation layer over
scripts/run_personal_assistant.py's exact same underlying functions
(build_decision_packet, generate_risk_reduction_proposals,
generate_soxx_soxl_rebalance_proposals, execute_approved_paper_proposal).
No financial logic lives here -- every number and every safety check is
still computed by the same deterministic code the CLI uses.

Safety note: the CLI's core protection is that you must TYPE the exact
phrase "APPROVE <proposal_id>" before an order can be submitted -- this
prevents a stray click from ever placing a real (paper) trade. This UI
preserves that same friction: each proposal has a text box you must type
the exact phrase into, not a one-click "Approve" button. The Submit
button stays disabled until the typed text matches exactly.

Run with:
    streamlit run scripts/personal_assistant_ui.py
"""
from __future__ import annotations

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
from assistant.context_builder import build_decision_packet, build_portfolio_snapshot_from_alpaca
from assistant.execution_service import (
    PolicyOverridableBlockError,
    execute_approved_paper_proposal,
    reconcile_submission,
)
from assistant.explanations import explain_ticker
from assistant.news_summary import fetch_recent_news, is_ai_summary_configured, summarize_news_for_ticker
from assistant.policy import DEFAULT_POLICY_PATH, compute_policy_fingerprint, load_policy
from assistant.proposal_status import STATUSES, UNRESOLVED_BROKER_STATE_STATUSES
from assistant.proposals import generate_risk_reduction_proposals
from assistant.sample_portfolio import SAMPLE_CASH, SAMPLE_POSITIONS
from assistant.stock_lookup import (
    compute_blended_volatility,
    historical_hold_period_range,
    inverse_volatility_weights,
    latest_price_targets_by_firm,
)
from assistant.storage import AssistantStore
from assistant.strategy_proposals import generate_soxx_soxl_rebalance_proposals
from config import LEVERAGED_ETF_TICKERS, PAPER_TRADING, UNIVERSE
from data.event_data import fetch_upcoming_earnings
from data.market_data import fetch_historical
from execution.alpaca_broker import is_configured
from strategies.trend_vol_rotation import classify_trend

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


def _load_packet(policy_path: str, include_events: bool):
    policy = load_policy(policy_path)
    packet = build_decision_packet(
        SAMPLE_POSITIONS,
        SAMPLE_CASH,
        use_live_alpaca=is_configured(),
        include_live_events=include_events,
        policy=policy,
    )
    return policy, packet


def _proposal_content_digest(proposal: dict, policy_fingerprint: str) -> str:
    """Fingerprint over exactly what's displayed in this proposal's
    confirmation summary, plus the active policy's fingerprint. Compared
    against a stored digest so a typed confirmation/override that was
    started against ONE version of this card (a different proposal, a
    stale render, or a policy that's since changed) is cleared rather
    than silently carried over onto different displayed content (GPT
    review, 2026-07-28: "do not retain an override-ready UI state after
    proposal content, policy, portfolio, or quote context changes")."""
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
    }
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _render_proposal_approval(proposal: dict, store: AssistantStore, policy_path: str) -> None:
    """One proposal card with the typed-confirmation approve flow.
    Shared by the Propose & Approve tab and the Watchlist tab's
    allocation-buy feature -- identical safety flow everywhere a
    proposal can be approved: type the exact "approve" phrase, or
    the submit button stays disabled. The confirmation phrase is
    intentionally simple (2026-07-28) -- what protects against
    approving the WRONG visible proposal or stale UI state is the
    immutable summary below and the content-digest binding, not
    phrase complexity (GPT review, 2026-07-28)."""
    intent = proposal["intent"]
    proposal_id = proposal["proposal_id"]
    override_key = f"override_available_{proposal_id}"
    digest_key = f"content_digest_{proposal_id}"

    display_policy = load_policy(policy_path)
    policy_fingerprint = compute_policy_fingerprint(display_policy)
    current_digest = _proposal_content_digest(proposal, policy_fingerprint)
    if st.session_state.get(digest_key) != current_digest:
        # Displayed content or the active policy changed since any prior
        # typed confirmation/override for this card -- clear both rather
        # than let a stale confirmation silently apply to new content.
        st.session_state[f"confirm_{proposal_id}"] = ""
        st.session_state.pop(override_key, None)
        st.session_state[digest_key] = current_digest

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
        submit_disabled = typed.strip().lower() != "approve"
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
                    st.success(
                        f"Submitted paper order {order['order_id']}: "
                        f"{order['side'].upper()} {order['shares']} {order['ticker']} [{order['status']}]"
                    )
                except PolicyOverridableBlockError as exc:
                    st.session_state[override_key] = list(exc.overridable_violations)
                except Exception as exc:
                    st.session_state.pop(override_key, None)
                    st.error(f"Order not submitted: {exc}")

        if st.session_state.get(override_key):
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
                "Override phrase", key=f"override_confirm_{proposal_id}", label_visibility="collapsed"
            )
            if st.button(
                "Override and submit anyway",
                key=f"override_submit_{proposal_id}",
                disabled=override_typed.strip() != override_phrase,
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
                        st.success(
                            f"Submitted paper order {order['order_id']} (policy override applied): "
                            f"{order['side'].upper()} {order['shares']} {order['ticker']} [{order['status']}]"
                        )
                    except Exception as exc:
                        st.session_state.pop(override_key, None)
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
    refresh), the cap, and the active policy's identity. Compared
    against the signature stored alongside a generated batch of
    proposals so a changed input can be caught and the stale cards
    cleared, instead of leaving them rendered and approvable against
    inputs the user has since changed (GPT review, 2026-07-28)."""
    payload = {
        "weights": {t: weights[t] for t in sorted(weights)},
        "dollar_amount": round(dollar_amount, 2),
        "prices": {t: prices.get(t) for t in sorted(weights)},
        "price_as_of": {t: str(price_as_of_by_ticker.get(t)) for t in sorted(weights)},
        "max_weight_pct": max_weight_pct,
        "policy_version": policy.version,
        "policy_fingerprint": compute_policy_fingerprint(policy),
        "portfolio_as_of": packet.portfolio.as_of,
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
    store.save_decision_packet(packet)

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
                        st.write(f"**[{e['status']}]** {e['label']} -- {e['claim']}")
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
        status_counts: dict[str, int] = {}
        for finding in packet.signals:
            status_counts[finding.status.value] = status_counts.get(finding.status.value, 0) + 1
        st.subheader(f"Research evidence relevant to your holdings ({len(packet.signals)} findings)")
        st.caption(" / ".join(f"{count} {status}" for status, count in sorted(status_counts.items())))
        for finding in packet.signals:
            st.write(f"**[{finding.status.value}]** {finding.label} -- {finding.claim}")
            st.caption(finding.detail)

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

    if st.button("Check cart", type="primary", disabled=not cart):
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

    watchlist_results = st.session_state.get("watchlist_results", {})

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
            dollar_amount = st.number_input(
                "Amount to invest",
                min_value=0.0,
                max_value=float(available_cash),
                value=0.0,
                step=50.0,
                key="allocation_dollar_amount",
                help="Capped at your current available cash, pulled live from Alpaca.",
            )
        st.caption(f"Available cash right now (live from Alpaca): ${available_cash:,.2f}")

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
                    active_batch_id, store, approve_policy, now_et=_now_eastern(),
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
            _render_proposal_approval(proposal, store, policy_path)

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
                    st.write(f"**[{e['status']}]** {e['label']} -- {e['claim']}")
                    st.caption(e["detail"])
            else:
                st.info(
                    f"No {ticker}-specific research exists in this project. None of the tested signals have "
                    "validated edge for individual-stock picks -- see the general track record below for what's "
                    "actually been tried."
                )
            if project_wide:
                with st.expander(f"General signal-testing track record ({len(project_wide)} findings -- same for every stock, not specific to {ticker})"):
                    for e in project_wide:
                        st.write(f"**[{e['status']}]** {e['label']} -- {e['claim']}")
                        st.caption(e["detail"])
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
                _render_proposal_approval(proposal, store, policy_path)

with tab_propose:
    policy, packet = _load_packet(policy_path, include_events)

    check_strategy = st.checkbox(
        "Also check SOXX/SOXL strategy proposals",
        value=policy.enable_strategy_proposals,
        help="evidence_status=promising_unconfirmed_strategy, not confirmed -- see assistant/strategy_proposals.py",
    )

    if st.button("Check for proposals", type="primary"):
        proposals = generate_risk_reduction_proposals(packet, policy)
        if check_strategy:
            try:
                proposals = proposals + generate_soxx_soxl_rebalance_proposals(packet, policy)
            except Exception as exc:
                st.error(f"SOXX/SOXL strategy proposal check failed ({exc}); showing risk-reduction proposals only.")
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
        _render_proposal_approval(proposal, store, policy_path)

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

        unresolved = [p for p in stored if p["status"] in UNRESOLVED_BROKER_STATE_STATUSES]
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
                        st.success(f"Reconciled: found broker order {order['order_id']} -- marked executed.")
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
