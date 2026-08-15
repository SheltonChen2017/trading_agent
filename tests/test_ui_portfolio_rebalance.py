"""The Portfolio Rebalancing page (REBAL-1 Stage 1).

Stage 1 is a report. The risks pinned here are all about what the page must
NOT do or show:

* it must never render a share count, a buy/sell side, or an approval
  control -- a read-only page that grows an action control is how a
  measurement quietly becomes an instruction;
* unassigned holdings must be visible on the page itself, not just in the
  underlying report, because the screen is where "absent from the profile"
  could be misread as "should not be held"; and
* when any authoritative value is unusable the page must show no sleeve
  percentage at all, since one bad value moves every sleeve's number.

Staleness is handled structurally in Stage 1: the report is recomputed on
every rerun and nothing is stored in session state, so there is no retained
card that a profile or snapshot change could leave standing.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

_APP_PATH = Path(__file__).resolve().parents[1] / "scripts" / "personal_assistant_ui.py"


@pytest.fixture()
def _offline(monkeypatch):
    import streamlit as st

    st.cache_data.clear()
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)

    import assistant.data_integrity as data_integrity

    monkeypatch.setattr(data_integrity, "fetch_daily_bars_recorded", lambda *a, **k: {})

    import data.event_data as event_data

    monkeypatch.setattr(
        event_data, "fetch_upcoming_earnings", lambda *a, **k: [], raising=False
    )


def _rebalancing(**session) -> AppTest:
    app = AppTest.from_file(str(_APP_PATH), default_timeout=180)
    app.session_state["nav_page"] = "Portfolio Rebalancing"
    for key, value in session.items():
        app.session_state[key] = value
    app.run()
    return app


def _text(app) -> str:
    parts = []
    for collection in (
        app.caption, app.warning, app.error, app.info, app.success,
        app.markdown, app.subheader,
    ):
        for element in collection:
            parts.append(str(getattr(element, "value", "")))
    return "\n".join(parts)


def test_the_page_is_reachable_and_renders(_offline):
    app = _rebalancing()
    assert not app.exception, app.exception
    assert "Portfolio Rebalancing" in app.radio(key="nav_page").options


def test_it_names_the_profile_version_and_fingerprint_it_measured_against(
    _offline,
):
    """A drift number is meaningless without the targets it was measured
    against, and the fingerprint is what makes a later profile change
    visible rather than silent."""
    from assistant.rebalance_profile import (
        OWNER_APPROVED_PROFILE,
        compute_profile_fingerprint,
    )

    rendered = _text(_rebalancing())
    assert OWNER_APPROVED_PROFILE.version in rendered
    assert compute_profile_fingerprint(OWNER_APPROVED_PROFILE)[:12] in rendered


def test_it_says_the_targets_are_preference_not_a_research_result(_offline):
    """The one confirmed wide-band finding was measured on the SOXX/SOXL
    vol-targeting pair. Presenting it as evidence about this portfolio's
    shape would be the claim this project most needs not to make."""
    rendered = _text(_rebalancing())
    assert "SOXX/SOXL" in rendered
    assert "not a research result" in rendered


def test_unassigned_holdings_appear_on_the_page_itself(_offline, monkeypatch):
    import assistant.context_builder as context_builder

    real_builder = context_builder.build_portfolio_snapshot

    def _with_unassigned(positions, cash, **kwargs):
        return real_builder(
            list(positions) + [
                {
                    "ticker": "RIOT", "shares": 10,
                    "entry_price": 100.0, "current_price": 100.0,
                }
            ],
            cash=cash, **kwargs
        )

    monkeypatch.setattr(
        context_builder, "build_portfolio_snapshot", _with_unassigned
    )
    rendered = _text(_rebalancing())
    assert "RIOT" in rendered
    assert "not a reason to sell" in rendered


def test_an_unusable_value_shows_no_sleeve_percentage_at_all(
    _offline, monkeypatch
):
    import assistant.context_builder as context_builder

    real_builder = context_builder.build_portfolio_snapshot

    def _with_corrupt_holding(positions, cash, **kwargs):
        snapshot = real_builder(
            list(positions) + [
                {
                    "ticker": "JEPQ", "shares": 100,
                    "entry_price": 50.0, "current_price": 50.0,
                }
            ],
            cash=cash, **kwargs
        )
        broken = [
            dataclasses.replace(
                p, market_value=float("nan"), market_value_exact=None
            ) if p.ticker == "JEPQ" else p
            for p in snapshot.positions
        ]
        return dataclasses.replace(snapshot, positions=broken)

    monkeypatch.setattr(
        context_builder, "build_portfolio_snapshot", _with_corrupt_holding
    )
    app = _rebalancing()
    assert not app.exception, app.exception
    rendered = _text(app)
    assert "JEPQ" in rendered
    assert "moves every sleeve's percentage" in rendered
    assert not app.dataframe, "no drift table may be shown on unusable data"


# --- the Stage 1 scope boundary ---------------------------------------------


def test_the_page_offers_no_action_control(_offline):
    """A read-only page that grows a button is how a measurement quietly
    becomes an instruction."""
    app = _rebalancing()
    labels = [str(b.label).lower() for b in app.button]
    for forbidden in ("buy", "sell", "propose", "approve", "rebalance now",
                      "submit", "create"):
        assert not any(forbidden in label for label in labels), (forbidden, labels)
    # Scoped to what the assertion actually means. The sidebar's "Policy
    # file" box is global chrome present on every page, so banning all text
    # inputs would fail on unrelated navigation rather than on this page
    # growing an approval control.
    approval_inputs = [
        t for t in app.text_input
        if any(
            word in str(t.label).lower()
            for word in ("approve", "phrase", "confirm")
        )
    ]
    assert not approval_inputs, [t.label for t in approval_inputs]


def _page_sections() -> tuple[str, str]:
    """The Stage 1 report section and the Stage 2 steering section.

    Stage 2 now shares this page, so a single whole-page ban would forbid
    exactly the machinery Stage 2 is supposed to have. The boundary that
    still matters is per section: the report half stays read-only, and the
    steering half only ever buys.
    """
    source = _APP_PATH.read_text(encoding="utf-8")
    page = source.split('if page == "Portfolio Rebalancing":', 1)[1].split(
        'if page == "Propose & Approve":', 1
    )[0]
    marker = "# --- Stage 2: buy-only cash steering"
    assert marker in page, "the Stage 2 section marker moved"
    report_half, steering_half = page.split(marker, 1)
    return report_half, steering_half


def test_the_stage_one_report_section_emits_no_shares_or_sides(_offline):
    report_half, _ = _page_sections()
    for forbidden in (
        "generate_", "save_proposal", "_render_proposal_approval",
        "TradeIntent", "shares",
    ):
        assert forbidden not in report_half, forbidden


def test_the_steering_section_never_sells_and_has_no_submit_all(_offline):
    """Stage 2 is buy-only by design. Selling to rebalance is Stage 3 and
    needs separate authorization; a submit-all would turn a multi-sleeve
    correction into one click that can partly fill."""
    _, steering_half = _page_sections()
    for forbidden in ('"sell"', "'sell'", "submit all", "Submit all",
                      "generate_user_directed_sell_proposal",
                      "execute_allocation_batch"):
        assert forbidden not in steering_half, forbidden


def test_exact_money_is_not_rounded_through_binary_float(_offline):
    """Broker-preserved exact text must stay decimal through presentation."""
    source = _APP_PATH.read_text(encoding="utf-8")
    page = source.split('if page == "Portfolio Rebalancing":', 1)[1].split(
        'if page == "Propose & Approve":', 1
    )[0]
    for field in (
        "total_equity_exact", "pending_value_exact", "gap_to_target_exact"
    ):
        assert f"float(_rb_report.{field})" not in page
        assert f"float(_row.{field})" not in page


def test_nothing_is_retained_in_session_state_between_reruns(_offline):
    """Stage 1's staleness rule is structural: with no stored analysis there
    is no card for a profile or snapshot change to leave standing."""
    app = _rebalancing()
    assert not app.exception
    retained = [
        key for key in app.session_state.filtered_state
        if str(key).startswith("_rb") or "rebalance" in str(key).lower()
    ]
    assert not retained, retained


def test_an_infeasible_target_is_its_own_column_not_the_status(_offline):
    """REBAL1CR-001. Against the owner's approved profile and active policy
    every invested sleeve has an unreachable target. If that occupied the
    Status column it would hide the drift the page exists to show, so
    feasibility gets its own column and Status keeps the band state."""
    app = _rebalancing()
    assert not app.exception, app.exception
    table = app.dataframe[0].value
    columns = list(table[0].keys()) if isinstance(table, list) else list(table)
    assert "Target reachable" in columns, columns
    assert "Status" in columns, columns


def test_the_breach_headline_counts_every_band_breach(_offline):
    """The metric a reader trusts at a glance must not be quietly reduced by
    sleeves whose targets are also infeasible."""
    from assistant.policy import load_policy
    from assistant.portfolio_rebalance import evaluate_portfolio_rebalance
    from assistant.rebalance_profile import OWNER_APPROVED_PROFILE

    app = _rebalancing()
    metrics = {m.label: m.value for m in app.metric}
    assert "Bands breached" in metrics

    import assistant.context_builder as context_builder

    report = evaluate_portfolio_rebalance(
        context_builder.build_portfolio_snapshot([], cash=10_000.0),
        OWNER_APPROVED_PROFILE,
        policy=load_policy(),
    )
    outside = sum(
        1 for r in report.rows
        if not (r.lower_edge_pct <= r.projected_pct <= r.upper_edge_pct)
    )
    assert report.breached_count == outside, (
        report.breached_count, outside,
        [(r.sleeve, r.status, r.projected_pct) for r in report.rows],
    )


# --- Stage 2 on the same page -----------------------------------------------


def test_the_steering_controls_appear_only_when_a_sleeve_is_under_its_band(
    _offline,
):
    """With an empty book several sleeves are under their bands, so the
    budget control is offered."""
    app = _rebalancing()
    assert not app.exception, app.exception
    assert any(n.label == "New-money budget ($)" for n in app.number_input), (
        [n.label for n in app.number_input]
    )


def test_no_proposal_is_created_until_the_owner_asks(_offline):
    """Loading the page must never write a proposal. The budget starts at
    zero and the check button is disabled until money and a ticker are
    chosen."""
    app = _rebalancing()
    check = [b for b in app.button if b.key == "rb_steer"]
    assert check, [b.key for b in app.button]
    assert check[0].disabled, "a zero budget with no ticker cannot be sized"


def test_the_owner_must_pick_the_ticker_within_each_sleeve(_offline):
    """The selectbox defaults to a non-choice, so the app never picks a
    name inside a sleeve on the owner's behalf."""
    app = _rebalancing()
    pickers = [s for s in app.selectbox if str(s.key).startswith("rb_pick_")]
    assert pickers, [s.key for s in app.selectbox]
    for picker in pickers:
        assert picker.value == "-- choose --"


def test_the_steering_section_offers_no_submit_all_control(_offline):
    app = _rebalancing()
    labels = [str(b.label).lower() for b in app.button]
    assert not any("submit all" in label for label in labels), labels
    assert not any("sell" in label for label in labels), labels
