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


def test_the_page_source_emits_no_shares_or_sides(_offline):
    source = _APP_PATH.read_text(encoding="utf-8")
    page = source.split('if page == "Portfolio Rebalancing":', 1)[1].split(
        'if page == "Propose & Approve":', 1
    )[0]
    for forbidden in (
        "generate_", "save_proposal", "_render_proposal_approval",
        "TradeIntent", "shares",
    ):
        assert forbidden not in page, forbidden


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
