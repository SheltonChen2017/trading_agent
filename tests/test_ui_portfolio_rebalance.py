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


def test_feasibility_is_separate_from_status_and_readable_without_scrolling():
    """REBAL1CR-001 and its follow-up.

    Feasibility must not occupy Status, or it hides the drift the page
    exists to show. It must also not depend on the reader reaching the last
    of nine columns: the owner reported the column simply was not reachable,
    with no horizontal scrollbar, so the one fact saying whether the targets
    can be met at all was unreadable in the real app. It is now stated in
    full below the table, where width cannot hide it.
    """


def test_the_drift_table_keeps_status_and_a_reachable_column(_offline):
    app = _rebalancing()
    assert not app.exception, app.exception
    table = app.dataframe[0].value
    columns = list(table[0].keys()) if isinstance(table, list) else list(table)
    assert "Status" in columns, columns
    assert "Reachable" in columns, columns


def test_feasibility_is_stated_below_the_table_whatever_the_width(_offline):
    """The width-independent statement, which is what the owner actually
    reads. With the approved profile and the active policy every target is
    reachable, so the page must say so positively rather than leaving the
    reader to infer it from an absent warning."""
    rendered = _text(_rebalancing())
    assert (
        "Every sleeve target is reachable under the active policy" in rendered
        or "TARGETS NOT REACHABLE UNDER THE ACTIVE POLICY" in rendered
    ), rendered[-600:]

def test_an_unreachable_target_is_named_in_full_below_the_table(
    _offline, monkeypatch
):
    """The conflict branch, driven through the real conflict rule.

    The operational policy caps total exposure at 50%, against a profile
    whose invested target is 90%. Under that policy the targets are not
    reachable, and the page must SAY SO in full text -- sleeve and reason --
    rather than only in a table column that a narrow window truncates.
    """
    import dataclasses
    import assistant.policy as policy_module

    _real = policy_module.load_policy

    def _tight(*args, **kwargs):
        return dataclasses.replace(
            _real(*args, **kwargs), max_total_exposure_pct=0.50
        )

    monkeypatch.setattr(policy_module, "load_policy", _tight)
    rendered = _text(_rebalancing())
    assert "TARGETS NOT REACHABLE UNDER THE ACTIVE POLICY" in rendered
    assert "total-exposure cap" in rendered, rendered[-800:]
    # Naming the sleeve is load-bearing: the total-exposure conflict
    # applies to EVERY funded sleeve, so an unlabelled list is the same
    # sentence repeated with no way to tell which sleeve it is about.
    # "**Growth**" also distinguishes this block from the raw-key
    # disclosure warning ("growth: ...") the report already emits.
    assert "**Growth**" in rendered, rendered[-800:]
    assert (
        "Every sleeve target is reachable" not in rendered
    ), "the positive statement must not appear alongside a conflict"


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


# --- Stage 3 on the same page -----------------------------------------------


def test_the_trim_section_appears_only_when_a_sleeve_is_overweight(
    _offline, monkeypatch
):
    """When nothing trimmable is overweight the app says so and offers no
    sell control at all.

    The book is FORCED rather than assumed: without Alpaca credentials the
    app falls back to the sample portfolio, whose growth sleeve sits at 61%
    and is genuinely overweight. An earlier version of this test assumed an
    empty book and would have passed for the wrong reason.
    """
    import assistant.context_builder as context_builder

    real_builder = context_builder.build_portfolio_snapshot

    def _growth_on_target(positions, cash, **kwargs):
        # $4,000 of growth in a $10,000 book is exactly the 40% target, so
        # the only overweight sleeve is cash, which is never trimmable.
        return real_builder(
            [{"ticker": "MSFT", "shares": 400,
              "entry_price": 8.0, "current_price": 10.0}],
            cash=6_000.0, **kwargs
        )

    monkeypatch.setattr(
        context_builder, "build_portfolio_snapshot", _growth_on_target
    )
    app = _rebalancing()
    assert not app.exception, app.exception
    rendered = _text(app)
    # REBAL3V-001: this assertion used to read `"nothing to trim" in
    # rendered`, which the page satisfied with the sentence "No sleeve
    # is above its upper band" -- false here, since cash IS above its
    # band and is merely untrimmable. The test pinned the false
    # message rather than the true refusal.
    assert "No sleeve is above its upper band" not in rendered
    assert "Nothing here can be trimmed" in rendered, rendered[-900:]
    assert "Cash" in rendered
    assert not [b for b in app.button if b.key == "rb_trim_check"]


def test_the_trim_section_never_chooses_any_owner_decision(
    _offline, monkeypatch
):
    import assistant.context_builder as context_builder

    real_builder = context_builder.build_portfolio_snapshot

    def _overweight_growth(positions, cash, **kwargs):
        return real_builder(
            list(positions) + [
                {"ticker": "MSFT", "shares": 900,
                 "entry_price": 8.0, "current_price": 10.0}
            ],
            cash=1_000.0, **kwargs
        )

    monkeypatch.setattr(
        context_builder, "build_portfolio_snapshot", _overweight_growth
    )
    app = _rebalancing()
    assert not app.exception, app.exception

    keys = {str(s.key): s for s in app.selectbox}
    assert "rb_trim_sleeve" in keys
    assert keys["rb_trim_sleeve"].value == "-- choose --"
    assert "rb_trim_ticker" in keys and "rb_trim_strategy" in keys
    assert keys["rb_trim_ticker"].value == "-- choose --"
    assert keys["rb_trim_strategy"].value == "-- choose --"
    shares = [n for n in app.number_input if n.key == "rb_trim_shares"]
    assert shares and shares[0].value == 0.0
    check = [b for b in app.button if b.key == "rb_trim_check"]
    assert check and check[0].disabled, (
        "nothing may be sized until the owner has chosen all four"
    )


def test_fractional_trim_uses_exact_text_instead_of_binary_float(
    _offline, monkeypatch
):
    import dataclasses

    import assistant.context_builder as context_builder
    import assistant.policy as policy_module

    real_load = policy_module.load_policy
    fractional_policy = dataclasses.replace(
        real_load(policy_module.DEFAULT_POLICY_PATH), whole_shares_only=False
    )
    monkeypatch.setattr(policy_module, "load_policy", lambda _path: fractional_policy)

    real_builder = context_builder.build_portfolio_snapshot

    def _overweight_growth(positions, cash, **kwargs):
        return real_builder(
            list(positions) + [
                {"ticker": "MSFT", "shares": 900,
                 "entry_price": 8.0, "current_price": 10.0}
            ],
            cash=1_000.0, **kwargs
        )

    monkeypatch.setattr(
        context_builder, "build_portfolio_snapshot", _overweight_growth
    )
    app = _rebalancing()

    assert not app.exception, app.exception
    assert [t for t in app.text_input if t.key == "rb_trim_fractional_shares"]
    assert not [n for n in app.number_input if n.key == "rb_trim_shares"]


def test_the_page_still_offers_no_submit_all_after_stage_three(_offline):
    app = _rebalancing()
    labels = [str(b.label).lower() for b in app.button]
    assert not any("submit all" in label for label in labels), labels


def test_the_trim_section_says_it_is_the_only_app_originated_sell(_offline):
    """The page must not let a rebalancing sell look like every other sell
    here, which is either a policy breach or the owner naming a holding."""
    rendered = _text(_rebalancing())
    assert "only place in the app where a rebalancing SELL" in rendered
    assert "realized gain before you approve" in rendered


def test_the_trim_refusal_never_contradicts_the_breach_headline(
    _offline, monkeypatch
):
    """REBAL3V-001, reported by the owner exercising the development app.

    The page showed "Bands breached: 6" in its headline and, three sections
    lower, "No sleeve is above its upper band". The second statement was
    false: cash and the residual WERE above their upper bands, they are
    simply never trimmable. A reader who notices the contradiction has to
    decide which half of the page to distrust, and one who does not notice
    learns something untrue about their own portfolio.

    The book is FORCED to the reported shape -- a residual holding and
    surplus cash, with every profiled sleeve empty -- rather than assumed,
    because the sample portfolio's growth sleeve IS trimmably overweight
    and would make this pass for the wrong reason.
    """
    import assistant.context_builder as context_builder
    from assistant.rebalance_trim import (
        overweight_sleeves,
        untrimmable_overweight_sleeves,
    )

    real_builder = context_builder.build_portfolio_snapshot

    def _residual_only(positions, cash, **kwargs):
        # AAPL belongs to no sleeve, so it lands in the residual. Both it
        # and cash sit far above their bands; nothing profiled is over.
        return real_builder(
            [{"ticker": "AAPL", "shares": 100,
              "entry_price": 150.0, "current_price": 200.0}],
            cash=20_000.0, **kwargs
        )

    monkeypatch.setattr(
        context_builder, "build_portfolio_snapshot", _residual_only
    )
    app = _rebalancing()
    assert not app.exception, app.exception
    rendered = _text(app)

    from assistant.policy import load_policy
    from assistant.portfolio_rebalance import evaluate_portfolio_rebalance
    from assistant.rebalance_profile import OWNER_APPROVED_PROFILE

    report = evaluate_portfolio_rebalance(
        _residual_only([], 0.0), OWNER_APPROVED_PROFILE, policy=load_policy()
    )
    # Guard against a vacuous pass: the book must really be over its bands
    # in exactly the untrimmable places.
    assert not overweight_sleeves(report)
    assert untrimmable_overweight_sleeves(report) == [
        "cash", "other_unassigned",
    ], untrimmable_overweight_sleeves(report)

    assert "No sleeve is above its upper band" not in rendered, (
        "the page denies a breach it reports in its own headline"
    )
    assert "Nothing here can be trimmed" in rendered, rendered[-900:]
    assert "absence from the profile is never a reason to sell" in rendered
    assert not [b for b in app.button if b.key == "rb_trim_check"]



def test_a_book_with_nothing_overweight_still_says_exactly_that(
    _offline, monkeypatch
):
    """The OTHER cause of an empty trimmable list.

    Separating the two causes is only worth anything if each one keeps its
    own message. A mutation that reported the untrimmable-sleeve reason for
    every empty case survived the first version of these tests: it would
    have told an owner whose book is perfectly on target that cash and the
    residual are above their bands. That merely moves the false statement
    from one case to the other.
    """
    import assistant.context_builder as context_builder
    from assistant.rebalance_trim import (
        overweight_sleeves,
        untrimmable_overweight_sleeves,
    )

    real_builder = context_builder.build_portfolio_snapshot

    def _on_target(positions, cash, **kwargs):
        # Exactly the approved profile: 10/15/40/15/10/10 of a $10,000 book.
        return real_builder(
            [
                {"ticker": "JEPI", "shares": 150, "entry_price": 10.0,
                 "current_price": 10.0},
                {"ticker": "MSFT", "shares": 400, "entry_price": 10.0,
                 "current_price": 10.0},
                {"ticker": "NVDL", "shares": 150, "entry_price": 10.0,
                 "current_price": 10.0},
                {"ticker": "GLD", "shares": 100, "entry_price": 10.0,
                 "current_price": 10.0},
                {"ticker": "AAPL", "shares": 100, "entry_price": 10.0,
                 "current_price": 10.0},
            ],
            cash=1_000.0, **kwargs
        )

    monkeypatch.setattr(
        context_builder, "build_portfolio_snapshot", _on_target
    )
    app = _rebalancing()
    assert not app.exception, app.exception
    rendered = _text(app)

    from assistant.policy import load_policy
    from assistant.portfolio_rebalance import evaluate_portfolio_rebalance
    from assistant.rebalance_profile import OWNER_APPROVED_PROFILE

    report = evaluate_portfolio_rebalance(
        _on_target([], 0.0), OWNER_APPROVED_PROFILE, policy=load_policy()
    )
    assert not overweight_sleeves(report)
    assert not untrimmable_overweight_sleeves(report), (
        "fixture is no longer on target: "
        + str(untrimmable_overweight_sleeves(report))
    )

    assert "No sleeve is above its upper band" in rendered, rendered[-900:]
    assert "Nothing here can be trimmed" not in rendered
    assert not [b for b in app.button if b.key == "rb_trim_check"]
