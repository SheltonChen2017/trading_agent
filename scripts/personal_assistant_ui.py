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

import streamlit as st

from assistant.context_builder import build_decision_packet, build_portfolio_snapshot_from_alpaca
from assistant.execution_service import execute_approved_paper_proposal
from assistant.policy import DEFAULT_POLICY_PATH, load_policy
from assistant.proposals import generate_risk_reduction_proposals
from assistant.sample_portfolio import SAMPLE_CASH, SAMPLE_POSITIONS
from assistant.storage import AssistantStore
from assistant.strategy_proposals import generate_soxx_soxl_rebalance_proposals
from execution.alpaca_broker import is_configured

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

tab_briefing, tab_propose, tab_history = st.tabs(["Briefing", "Propose & Approve", "History"])

with tab_briefing:
    if st.button("Refresh briefing", key="refresh_briefing"):
        st.cache_data.clear()
    policy, packet = _load_packet(policy_path, include_events)
    store.save_decision_packet(packet)

    col1, col2, col3 = st.columns(3)
    col1.metric("Total equity", f"${packet.portfolio.total_equity:,.2f}")
    col2.metric("Cash", f"${packet.portfolio.cash:,.2f}")
    col3.metric("Positions", packet.analytics["position_count"])

    st.subheader(f"Market regime ({packet.regime.benchmark_ticker})")
    st.write(f"Trend: **{packet.regime.trend or 'unavailable'}** / Volatility: **{packet.regime.volatility_regime or 'unavailable'}**")

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
        )

    if packet.signals:
        st.subheader("Research evidence relevant to your holdings")
        for finding in packet.signals:
            st.write(f"**[{finding.status.value}]** {finding.label} -- {finding.claim}")
            st.caption(finding.detail)

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

    proposals = st.session_state.get("current_proposals", [])
    if not proposals:
        st.info("No proposals yet -- click \"Check for proposals\" above.")

    for proposal in proposals:
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
