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

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from assistant.allocation_proposals import generate_allocation_buy_proposals
from assistant.context_builder import build_decision_packet, build_portfolio_snapshot_from_alpaca
from assistant.execution_service import execute_approved_paper_proposal
from assistant.explanations import explain_ticker
from assistant.news_summary import fetch_recent_news, is_ai_summary_configured, summarize_news_for_ticker
from assistant.policy import DEFAULT_POLICY_PATH, load_policy
from assistant.proposals import generate_risk_reduction_proposals
from assistant.sample_portfolio import SAMPLE_CASH, SAMPLE_POSITIONS
from assistant.stock_lookup import historical_hold_period_range, inverse_volatility_weights, latest_price_targets_by_firm
from assistant.storage import AssistantStore
from assistant.strategy_proposals import generate_soxx_soxl_rebalance_proposals
from config import LEVERAGED_ETF_TICKERS, UNIVERSE
from data.market_data import fetch_historical
from execution.alpaca_broker import is_configured
from signals.regime import compute_trailing_market_volatility
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


def _render_proposal_approval(proposal: dict, store: AssistantStore, policy_path: str) -> None:
    """One proposal card with the typed-confirmation approve flow.
    Shared by the Propose & Approve tab and the Watchlist tab's
    allocation-buy feature -- identical safety flow everywhere a
    proposal can be approved: type the exact "APPROVE <id>" phrase, or
    the submit button stays disabled."""
    intent = proposal["intent"]
    with st.container(border=True):
        st.subheader(f"{intent['side'].upper()} {intent['shares']} {intent['ticker']}")
        st.caption(f"{proposal['proposal_id']} -- evidence_status: {proposal['evidence_status']}")
        st.write(f"Reference price: ${proposal['reference_price']:,.2f}")
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

        required_phrase = f"APPROVE {proposal['proposal_id']}"
        st.write(f"To submit this order, type the exact phrase below: `{required_phrase}`")
        typed = st.text_input(
            "Confirmation phrase", key=f"confirm_{proposal['proposal_id']}", label_visibility="collapsed"
        )
        submit_disabled = typed != required_phrase
        if st.button(
            "Submit paper order",
            key=f"submit_{proposal['proposal_id']}",
            disabled=submit_disabled,
        ):
            if not is_configured():
                st.error("Alpaca paper credentials are required for approval execution.")
            else:
                try:
                    approve_policy = load_policy(policy_path)
                    portfolio = build_portfolio_snapshot_from_alpaca()
                    order = execute_approved_paper_proposal(
                        proposal["proposal_id"],
                        typed,
                        portfolio,
                        approve_policy,
                        store,
                        now_et=_now_eastern(),
                        kill_switch_active=os.environ.get("TRADING_ASSISTANT_KILL_SWITCH") == "1",
                    )
                    st.success(
                        f"Submitted paper order {order['order_id']}: "
                        f"{order['side'].upper()} {order['shares']} {order['ticker']} [{order['status']}]"
                    )
                except Exception as exc:
                    st.error(f"Order not submitted: {exc}")


st.title("Personal Trading Assistant")
st.caption(
    "Click-around front end over the same deterministic code the CLI uses. "
    "Nothing here computes financial numbers itself -- it only displays what "
    "assistant/*.py already computed."
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
        "than it is. When 2+ tickers are checked together, an inverse-"
        "volatility weight suggestion is shown -- a risk-sizing heuristic "
        "from historical data, not a return forecast."
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
        results = {}
        for ticker in cart:
            try:
                data = fetch_historical([ticker], lookback_days=300)
                own_trend, own_vol, current_price, price_as_of = None, None, None, None
                if ticker in data and not data[ticker].empty:
                    close = data[ticker]["close"]
                    as_of = close.index[-1]
                    own_trend = classify_trend(close, as_of, lookback_days=200)
                    own_vol = compute_trailing_market_volatility(pd.DataFrame({"close": close}), as_of, lookback_days=20)
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
                    "explanation": explanation,
                    "price_targets": price_targets,
                    "hold_range": hold_range,
                    "news": news,
                    "news_summary": news_summary,
                }
            except Exception as exc:
                results[ticker] = {"error": str(exc)}
        st.session_state["watchlist_results"] = results

    watchlist_results = st.session_state.get("watchlist_results", {})

    vols = {t: r.get("own_vol") for t, r in watchlist_results.items() if "error" not in r}
    weights = inverse_volatility_weights(vols) if vols else {}

    if len(watchlist_results) > 1 and weights:
        st.subheader("Suggested combination weighting (inverse-volatility)")
        st.dataframe(
            [{"Ticker": t, "Suggested %": w} for t, w in sorted(weights.items(), key=lambda kv: -kv[1])],
            use_container_width=True,
            hide_index=True,
        )
        st.caption(
            "Weights inversely proportional to each ticker's own trailing volatility -- "
            "sizes the choppier name smaller, same principle as strategies/vol_target_rotation.py. "
            "A risk heuristic, not an optimization for expected return."
        )

    if weights:
        st.subheader("Buy with recommended allocation (paper trading)")
        alloc_policy, alloc_packet = _load_packet(policy_path, include_events=False)
        available_cash = alloc_packet.portfolio.cash
        if not alloc_policy.allow_new_positions:
            st.warning(
                "Your active policy has allow_new_positions=false (the default). You can still generate "
                "proposals below, but approving them will be blocked until you set "
                '"allow_new_positions": true in your policy file.'
            )
        st.caption("This only sizes the split across your cart -- it is not a recommendation to buy these specific stocks.")
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
        with balance_col:
            st.metric("Remaining balance after this purchase", f"${available_cash - dollar_amount:,.2f}")
            st.caption("Estimate before share rounding -- shares are rounded DOWN, so actual remaining cash will be at or above this.")
        st.caption(f"Available cash right now (live from Alpaca): ${available_cash:,.2f}")
        if st.button("Buy with recommended allocation", type="primary", disabled=dollar_amount <= 0):
            prices = {t: r.get("current_price") for t, r in watchlist_results.items() if "error" not in r}
            alloc_proposals = generate_allocation_buy_proposals(
                alloc_packet, alloc_policy, weights, prices, dollar_amount,
            )
            for p in alloc_proposals:
                store.save_proposal(p.to_dict())
            st.session_state["allocation_proposals"] = [p.to_dict() for p in alloc_proposals]
            if not alloc_proposals:
                st.warning(
                    "No proposals generated -- the amount may be too small to buy at least 1 share of any "
                    "cart ticker at its current price."
                )

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
            st.write(f"Own trend (200-day): **{trend_str}** -- Own volatility (20-day): **{vol_str}**")

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
    status_filter = st.selectbox("Status filter", ["(any)", "proposed", "executed", "expired", "rejected"])
    limit = st.slider("Max rows", 5, 100, 20)
    stored = store.list_proposals(status=None if status_filter == "(any)" else status_filter, limit=limit)
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
                    "Expires": p["expires_at"],
                }
                for p in stored
            ],
            use_container_width=True,
        )
