"""Read-only sleeve drift against the allocation profile (REBAL-1 Stage 1).

Two properties carry most of the safety here.

**One unusable holding refuses everything.** Sleeve weights share a single
equity denominator, so a corrupt value does not stay local: it moves every
other sleeve's percentage and can manufacture a phantom breach on a sleeve
whose own holdings all read fine. Dropping the bad row is therefore the
dangerous choice, not the cautious one.

**Unassigned holdings never disappear.** Being outside the profile is a gap
in the profile, not a verdict on the holding. A report that quietly omitted
them would understate the residual and, in a later stage, could read as
authorization to sell something the owner deliberately holds.

Stage 1 also has a hard scope boundary: it reports. No share counts, no
buy/sell sides, no proposals, no ordering of what to trade first.
"""
from __future__ import annotations

import dataclasses
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from assistant.context_builder import build_portfolio_snapshot
from assistant.policy import TradingPolicy
from assistant.portfolio_rebalance import (
    STATUS_DATA_UNAVAILABLE,
    STATUS_INSIDE,
    STATUS_OVERWEIGHT,
    STATUS_PENDING_UNKNOWN,
    STATUS_POLICY_CONFLICT,
    STATUS_UNASSIGNED,
    STATUS_UNDERWEIGHT,
    evaluate_portfolio_rebalance,
)
from assistant.rebalance_profile import (
    OWNER_APPROVED_PROFILE,
    SLEEVE_CASH,
    SLEEVE_DIVIDEND,
    SLEEVE_GROWTH,
    SLEEVE_HEDGE,
    SLEEVE_LEVERAGED,
    SLEEVE_ORDER,
    SLEEVE_OTHER,
    AllocationProfile,
    AllocationProfileError,
    compute_profile_fingerprint,
    sleeve_membership,
    validate_profile,
)


def _held(ticker, shares, price):
    return {
        "ticker": ticker, "shares": shares,
        "entry_price": price, "current_price": price,
    }


def _snapshot(positions=None, cash=0.0, **kwargs):
    return build_portfolio_snapshot(positions or [], cash=cash, **kwargs)


def _report(snapshot, profile=OWNER_APPROVED_PROFILE, **kwargs):
    return evaluate_portfolio_rebalance(snapshot, profile, **kwargs)


def _row(report, sleeve):
    return next(r for r in report.rows if r.sleeve == sleeve)


def _profile(**overrides):
    targets = dict(OWNER_APPROVED_PROFILE.targets)
    targets.update(overrides.pop("targets", {}))
    return dataclasses.replace(OWNER_APPROVED_PROFILE, targets=targets, **overrides)


# --- the profile ------------------------------------------------------------


def test_the_owner_approved_profile_is_valid_and_totals_exactly_one_hundred():
    validate_profile(OWNER_APPROVED_PROFILE)
    total = sum(
        Decimal(OWNER_APPROVED_PROFILE.targets[s]) for s in SLEEVE_ORDER
    )
    assert total == 100


@pytest.mark.parametrize(
    "targets",
    [
        {SLEEVE_CASH: "9"},        # totals 99
        {SLEEVE_CASH: "11"},       # totals 101
        {SLEEVE_CASH: "-1"},
        {SLEEVE_CASH: "abc"},
        {SLEEVE_CASH: "NaN"},
        {SLEEVE_CASH: "Infinity"},
    ],
)
def test_targets_that_do_not_total_exactly_one_hundred_are_refused(targets):
    """99 or 101 makes every percentage quietly mean something other than
    share-of-equity."""
    with pytest.raises(AllocationProfileError):
        validate_profile(_profile(targets=targets))


def test_a_missing_sleeve_is_refused_including_the_residual():
    partial = {
        k: v for k, v in OWNER_APPROVED_PROFILE.targets.items()
        if k != SLEEVE_OTHER
    }
    with pytest.raises(AllocationProfileError):
        validate_profile(
            dataclasses.replace(OWNER_APPROVED_PROFILE, targets=partial)
        )


@pytest.mark.parametrize("band", ["0", "-0.1", "0.005", "1.5", "abc", "NaN"])
def test_an_unusable_band_is_refused(band):
    with pytest.raises(AllocationProfileError):
        validate_profile(_profile(band_fraction=band))


def test_the_band_is_relative_not_percentage_points():
    """25% relative is +/-10 points on a 40% target and +/-2.5 on a 10% one."""
    lower, upper = OWNER_APPROVED_PROFILE.band_edges(SLEEVE_GROWTH)
    assert (upper - Decimal("40")) == Decimal("10")
    lower, upper = OWNER_APPROVED_PROFILE.band_edges(SLEEVE_HEDGE)
    assert (upper - Decimal("10")) == Decimal("2.5")


def test_changing_any_target_or_the_band_changes_the_fingerprint():
    """A changed profile must make prior analysis stale rather than being
    silently re-interpreted against numbers the reader never saw."""
    base = compute_profile_fingerprint(OWNER_APPROVED_PROFILE)
    moved = compute_profile_fingerprint(
        _profile(targets={SLEEVE_CASH: "11", SLEEVE_OTHER: "9"})
    )
    widened = compute_profile_fingerprint(_profile(band_fraction="0.3"))
    assert base != moved
    assert base != widened
    assert moved != widened


def test_editing_only_the_notes_does_not_change_the_fingerprint():
    """Notes are explanatory and change no behaviour, mirroring
    compute_policy_fingerprint's exclusion of the same field."""
    assert compute_profile_fingerprint(OWNER_APPROVED_PROFILE) == (
        compute_profile_fingerprint(
            dataclasses.replace(OWNER_APPROVED_PROFILE, notes="reworded")
        )
    )


def test_profile_copies_and_freezes_caller_owned_targets():
    targets = dict(OWNER_APPROVED_PROFILE.targets)
    profile = dataclasses.replace(OWNER_APPROVED_PROFILE, targets=targets)
    targets[SLEEVE_CASH] = "99"
    assert profile.targets[SLEEVE_CASH] == "10"
    with pytest.raises(TypeError):
        profile.targets[SLEEVE_CASH] = "99"  # type: ignore[index]


def test_fingerprint_rejects_the_wrong_object_with_the_domain_error():
    with pytest.raises(AllocationProfileError):
        compute_profile_fingerprint(object())  # type: ignore[arg-type]


def test_a_ticker_in_two_sleeves_is_refused_rather_than_assigned(monkeypatch):
    """An ambiguous classification moves every other sleeve's weight through
    the shared denominator, so first-wins would be a hidden allocation
    decision."""
    monkeypatch.setattr(config, "GROWTH_ROTATION_TICKERS", ["MSFT", "SOXL"])
    monkeypatch.setattr(config, "DIVIDEND_REINVEST_TICKERS", ["SOXL"])
    with pytest.raises(AllocationProfileError) as caught:
        sleeve_membership()
    assert "SOXL" in str(caught.value)


@pytest.mark.parametrize("bad_member", ["", "   ", None, True, 123])
def test_corrupt_configured_sleeve_members_are_refused(monkeypatch, bad_member):
    monkeypatch.setattr(config, "GROWTH_ROTATION_TICKERS", [bad_member])
    with pytest.raises(AllocationProfileError):
        sleeve_membership()


def test_the_configured_sleeves_do_not_currently_overlap():
    membership = sleeve_membership()
    assert membership["JEPQ"] == SLEEVE_DIVIDEND
    assert membership["MSFT"] == SLEEVE_GROWTH
    assert membership["SOXL"] == SLEEVE_LEVERAGED
    assert membership["SH"] == SLEEVE_HEDGE


# --- band boundaries --------------------------------------------------------


def test_a_sleeve_exactly_on_its_edge_is_inside_the_band():
    """Inclusive boundaries. A rule that breaches on equality churns every
    time a price rounds onto the edge."""
    # Hedge target 10%, band 25% -> upper edge exactly 12.5%.
    snapshot = _snapshot([_held("GLD", 125, 10.0)], cash=8_750.0)
    report = _report(snapshot)
    hedge = _row(report, SLEEVE_HEDGE)
    assert hedge.current_pct == pytest.approx(12.5)
    assert hedge.status == STATUS_INSIDE


def test_just_past_the_edge_breaches():
    snapshot = _snapshot([_held("GLD", 126, 10.0)], cash=8_750.0)
    report = _report(snapshot)
    assert _row(report, SLEEVE_HEDGE).status == STATUS_OVERWEIGHT


def test_a_sleeve_exactly_on_its_LOWER_edge_is_also_inside():
    """Both boundaries, not just the upper one. An earlier version of this
    suite pinned only the upper edge, so making the lower comparison
    exclusive went undetected -- and the lower edge is the one that decides
    whether a sleeve reads as underweight and, in a later stage, gets bought.
    """
    # Hedge target 10%, band 25% -> lower edge exactly 7.5%.
    snapshot = _snapshot([_held("GLD", 75, 10.0)], cash=9_250.0)
    report = _report(snapshot)
    hedge = _row(report, SLEEVE_HEDGE)
    assert hedge.current_pct == pytest.approx(7.5)
    assert hedge.status == STATUS_INSIDE


def test_just_below_the_lower_edge_breaches():
    snapshot = _snapshot([_held("GLD", 74, 10.0)], cash=9_250.0)
    report = _report(snapshot)
    assert _row(report, SLEEVE_HEDGE).status == STATUS_UNDERWEIGHT


def test_an_empty_sleeve_reads_underweight_not_missing():
    report = _report(_snapshot(cash=10_000.0))
    assert _row(report, SLEEVE_HEDGE).status == STATUS_UNDERWEIGHT
    assert _row(report, SLEEVE_GROWTH).status == STATUS_UNDERWEIGHT


# --- the failure direction --------------------------------------------------


def test_one_unreadable_holding_refuses_the_whole_report():
    snapshot = _snapshot([_held("MSFT", 10, 400.0), _held("JEPQ", 100, 50.0)])
    positions = [
        dataclasses.replace(
            p, market_value=float("nan"), market_value_exact=None
        ) if p.ticker == "MSFT" else p
        for p in snapshot.positions
    ]
    snapshot = dataclasses.replace(snapshot, positions=positions)

    report = _report(snapshot)
    assert not report.usable
    assert any("MSFT" in r for r in report.refusals)
    # every row must fall back to data-unavailable, including sleeves whose
    # own holdings are perfectly readable
    assert {r.status for r in report.rows} == {STATUS_DATA_UNAVAILABLE}
    assert report.breached_count == 0


def test_a_malformed_exact_value_does_not_fall_back_to_the_float():
    snapshot = _snapshot([_held("JEPQ", 100, 50.0)], cash=5_000.0)
    positions = [
        dataclasses.replace(
            p, market_value=5_000.0, market_value_exact="not-a-number"
        )
        for p in snapshot.positions
    ]
    snapshot = dataclasses.replace(snapshot, positions=positions)
    assert not _report(snapshot).usable


def test_a_positive_quantity_worth_nothing_refuses_as_impossible():
    snapshot = _snapshot([_held("JEPQ", 100, 50.0)], cash=5_000.0)
    positions = [
        dataclasses.replace(p, market_value=0.0, market_value_exact="0")
        for p in snapshot.positions
    ]
    snapshot = dataclasses.replace(snapshot, positions=positions)
    report = _report(snapshot)
    assert not report.usable
    assert any("impossible" in r for r in report.refusals)


@pytest.mark.parametrize("equity", [0.0, -1.0, float("nan"), float("inf")])
def test_unusable_equity_refuses(equity):
    snapshot = dataclasses.replace(
        _snapshot([_held("JEPQ", 100, 50.0)], cash=5_000.0),
        total_equity=equity, total_equity_exact=None,
    )
    report = _report(snapshot)
    assert not report.usable
    assert {r.status for r in report.rows} == {STATUS_DATA_UNAVAILABLE}


def test_unusable_cash_refuses():
    snapshot = dataclasses.replace(
        _snapshot([_held("JEPQ", 100, 50.0)], cash=5_000.0),
        cash=float("nan"), cash_exact=None,
    )
    assert not _report(snapshot).usable


def test_duplicate_position_rows_are_summed_not_replaced():
    """Two rows for one ticker are a real broker shape. Keeping only one
    understates that sleeve AND every other sleeve's share of the
    denominator.

    The positions are built DIRECTLY rather than through
    `build_portfolio_snapshot`, which aggregates duplicates itself. Going
    through the builder made an earlier version of this test unable to reach
    this module's own aggregation at all: replacing the sum with an
    assignment left it green. Any other producer of a snapshot -- including
    the Alpaca path -- must still be handled here.
    """
    snapshot = _snapshot(cash=0.0)
    duplicated = build_portfolio_snapshot(
        [_held("JEPQ", 100, 50.0)], cash=0.0
    ).positions[0]
    snapshot = dataclasses.replace(
        snapshot,
        positions=[duplicated, duplicated],
        cash=0.0, cash_exact="0",
        total_equity=10_000.0, total_equity_exact="10000",
    )
    report = _report(snapshot)
    dividend = _row(report, SLEEVE_DIVIDEND)
    assert Decimal(dividend.market_value_exact) == Decimal("10000"), (
        "duplicate rows must sum; keeping one would report $5,000"
    )
    assert dividend.current_pct == pytest.approx(100.0)


# --- unassigned holdings ----------------------------------------------------


def test_unassigned_holdings_are_always_surfaced():
    snapshot = _snapshot(
        [_held("AAPL", 10, 100.0), _held("RIOT", 10, 100.0)], cash=8_000.0
    )
    report = _report(snapshot)
    assert set(report.unassigned_tickers) == {"AAPL", "RIOT"}
    other = _row(report, SLEEVE_OTHER)
    assert other.status == STATUS_UNASSIGNED
    assert set(other.tickers) == {"AAPL", "RIOT"}


def test_the_residual_is_flagged_unassigned_even_when_inside_its_band():
    """Its band position is real but secondary; a reader must never take the
    residual for a tidy sleeve that merely drifted."""
    snapshot = _snapshot([_held("AAPL", 10, 100.0)], cash=9_000.0)
    report = _report(snapshot)
    other = _row(report, SLEEVE_OTHER)
    assert other.current_pct == pytest.approx(10.0)  # exactly on target
    assert other.status == STATUS_UNASSIGNED


def test_the_report_says_absence_from_the_profile_is_not_a_sell_signal():
    report = _report(_snapshot([_held("AAPL", 10, 100.0)], cash=9_000.0))
    joined = " ".join(report.disclosures)
    assert "not a reason to sell it" in joined


# --- pending exposure -------------------------------------------------------


def test_a_measurable_pending_buy_moves_the_projected_weight_only():
    snapshot = _snapshot(
        [_held("GLD", 50, 10.0)], cash=9_500.0,
        open_orders=[{"ticker": "SH", "side": "buy", "notional": 500.0}],
    )
    report = _report(snapshot)
    hedge = _row(report, SLEEVE_HEDGE)
    assert hedge.current_pct == pytest.approx(5.0)
    assert hedge.projected_pct == pytest.approx(10.0)
    assert Decimal(hedge.pending_value_exact) == Decimal("500")
    cash = _row(report, SLEEVE_CASH)
    assert Decimal(cash.pending_value_exact) == Decimal("-500")
    assert cash.projected_pct == pytest.approx(90.0)
    assert hedge.status == STATUS_INSIDE
    assert Decimal(hedge.gap_to_target_exact) == Decimal("0")
    assert SLEEVE_HEDGE not in report.breached


def test_a_measurable_pending_sell_reduces_the_projected_weight():
    snapshot = _snapshot(
        [_held("GLD", 200, 10.0)], cash=8_000.0,
        open_orders=[{"ticker": "GLD", "side": "sell", "notional": 500.0}],
    )
    report = _report(snapshot)
    hedge = _row(report, SLEEVE_HEDGE)
    assert hedge.current_pct == pytest.approx(20.0)
    assert hedge.projected_pct == pytest.approx(15.0)
    assert Decimal(hedge.pending_value_exact) == Decimal("-500")
    cash = _row(report, SLEEVE_CASH)
    assert Decimal(cash.pending_value_exact) == Decimal("500")
    assert cash.projected_pct == pytest.approx(85.0)


def test_malformed_authoritative_notional_does_not_fall_back_to_qty_limit():
    snapshot = _snapshot(
        cash=10_000.0,
        open_orders=[{
            "ticker": "SH", "side": "buy", "notional": "broken",
            "qty": "10", "limit_price": "100",
        }],
    )
    report = _report(snapshot)
    assert _row(report, SLEEVE_HEDGE).status == STATUS_PENDING_UNKNOWN


def test_unknown_unassigned_pending_order_is_named_and_marks_cash_unknown():
    snapshot = _snapshot(
        cash=10_000.0,
        open_orders=[{"ticker": "AAPL", "side": "buy"}],
    )
    report = _report(snapshot)
    assert "AAPL" in report.unassigned_tickers
    assert "AAPL" in _row(report, SLEEVE_OTHER).tickers
    assert _row(report, SLEEVE_CASH).status == STATUS_PENDING_UNKNOWN


def test_unknown_pending_value_is_not_hidden_by_a_policy_conflict():
    snapshot = _snapshot(
        cash=10_000.0,
        open_orders=[{"ticker": "MSFT", "side": "buy"}],
    )
    report = _report(snapshot, policy=_policy(max_position_pct=0.05))
    assert _row(report, SLEEVE_GROWTH).status == STATUS_PENDING_UNKNOWN


@pytest.mark.parametrize("order", [None, {}, {"side": "buy", "notional": 100}])
def test_unidentifiable_open_order_refuses_the_whole_report(order):
    snapshot = _snapshot(cash=10_000.0, open_orders=[order])
    report = _report(snapshot)
    assert not report.usable
    assert any("order" in reason.lower() for reason in report.refusals)


def test_an_unknown_pending_value_marks_the_sleeve_rather_than_assuming_zero():
    """Zero is the one value a working order certainly is not."""
    snapshot = _snapshot(
        [_held("GLD", 100, 10.0)], cash=9_000.0,
        open_orders=[{"ticker": "SH", "side": "buy"}],  # plain market order
    )
    report = _report(snapshot)
    assert _row(report, SLEEVE_HEDGE).status == STATUS_PENDING_UNKNOWN


def test_unavailable_open_order_data_refuses_the_projection_entirely():
    snapshot = dataclasses.replace(
        _snapshot([_held("GLD", 100, 10.0)], cash=9_000.0),
        open_orders_available=False,
    )
    report = _report(snapshot)
    assert not report.usable
    assert any("Open-order data is unavailable" in r for r in report.refusals)


def test_a_pending_order_in_no_sleeve_lands_in_the_residual():
    snapshot = _snapshot(
        cash=10_000.0,
        open_orders=[{"ticker": "AAPL", "side": "buy", "notional": 500.0}],
    )
    report = _report(snapshot)
    assert "AAPL" in report.unassigned_tickers


# --- policy conflicts -------------------------------------------------------


def _policy(**overrides):
    fields = dict(
        version="test", name="test", execution_mode="paper",
        max_position_pct=1.0, max_total_exposure_pct=1.0, max_basket_pct=1.0,
        max_leveraged_etf_pct=0.20, min_cash_reserve_pct=0.10,
        max_order_value=50_000.0, allow_new_positions=True,
    )
    fields.update(overrides)
    return TradingPolicy(**fields)


def test_a_target_above_a_policy_cap_is_marked_not_silently_measured():
    """A cap is not a target, but a target above a cap is unreachable, which
    makes the band around it fiction."""
    profile = _profile(
        targets={SLEEVE_LEVERAGED: "30", SLEEVE_GROWTH: "25"}
    )
    report = _report(_snapshot(cash=10_000.0), profile=profile,
                     policy=_policy(max_leveraged_etf_pct=0.20))
    row = _row(report, SLEEVE_LEVERAGED)
    assert "leveraged-ETF cap" in row.policy_conflict_reason
    # REBAL1CR-001: the conflict must not swallow the drift state. Holding
    # nothing against a 30% target is underweight whether or not that target
    # is reachable, and the status column is what the owner reads per row.
    assert row.status == STATUS_UNDERWEIGHT
    assert any("leveraged" in d for d in report.disclosures)


def test_a_cash_target_below_the_reserve_floor_is_marked():
    profile = _profile(targets={SLEEVE_CASH: "5", SLEEVE_GROWTH: "45"})
    report = _report(_snapshot(cash=10_000.0), profile=profile,
                     policy=_policy(min_cash_reserve_pct=0.10))
    row = _row(report, SLEEVE_CASH)
    assert "minimum cash reserve" in row.policy_conflict_reason
    assert row.status == STATUS_OVERWEIGHT  # 100% cash against a 5% target


def test_total_invested_target_above_policy_cap_is_disclosed():
    report = _report(
        _snapshot(cash=10_000.0),
        policy=_policy(max_total_exposure_pct=0.50),
    )
    assert all(
        "total-exposure" in _row(report, sleeve).policy_conflict_reason
        for sleeve in SLEEVE_ORDER if sleeve != SLEEVE_CASH
    )
    # Every invested sleeve is empty here, so each must still read
    # underweight rather than having its drift hidden by the conflict.
    assert all(
        _row(report, sleeve).status == STATUS_UNDERWEIGHT
        for sleeve in SLEEVE_ORDER if sleeve != SLEEVE_CASH
    )
    assert any("total-exposure" in text for text in report.disclosures)


def test_sleeve_target_above_combined_position_capacity_is_disclosed():
    report = _report(
        _snapshot(cash=10_000.0),
        policy=_policy(max_position_pct=0.05),
    )
    growth = _row(report, SLEEVE_GROWTH)
    assert "position-cap capacity" in growth.policy_conflict_reason
    assert growth.status == STATUS_UNDERWEIGHT
    assert any("position-cap capacity" in text for text in report.disclosures)


def test_the_owner_approved_profile_conflicts_with_no_default_policy_cap():
    report = _report(_snapshot(cash=10_000.0), policy=_policy())
    assert not any(r.status == STATUS_POLICY_CONFLICT for r in report.rows)


def test_no_policy_means_no_conflict_check_rather_than_a_guessed_one():
    report = _report(_snapshot(cash=10_000.0), policy=None)
    assert not any(r.status == STATUS_POLICY_CONFLICT for r in report.rows)


def test_wrong_profile_type_returns_an_unusable_report_instead_of_crashing():
    report = evaluate_portfolio_rebalance(
        _snapshot(cash=10_000.0), object()  # type: ignore[arg-type]
    )
    assert not report.usable
    assert {row.status for row in report.rows} == {STATUS_DATA_UNAVAILABLE}


# --- headline figures -------------------------------------------------------


def test_invested_and_cash_percentages_describe_the_same_equity():
    snapshot = _snapshot([_held("JEPQ", 100, 50.0)], cash=5_000.0)
    report = _report(snapshot)
    assert report.invested_pct == pytest.approx(50.0)
    assert report.cash_pct == pytest.approx(50.0)
    assert report.invested_pct + report.cash_pct == pytest.approx(100.0)


def test_the_breach_count_matches_the_breached_sleeves():
    report = _report(_snapshot(cash=10_000.0))
    assert report.breached_count == len(report.breached)
    assert all(
        _row(report, s).status in (STATUS_UNDERWEIGHT, STATUS_OVERWEIGHT)
        for s in report.breached
    )


def test_the_report_carries_the_profile_identity_it_was_measured_against():
    report = _report(_snapshot(cash=10_000.0))
    assert report.profile_version == OWNER_APPROVED_PROFILE.version
    assert report.profile_fingerprint == compute_profile_fingerprint(
        OWNER_APPROVED_PROFILE
    )


def test_the_report_is_immutable():
    report = _report(_snapshot(cash=10_000.0))
    with pytest.raises(Exception):
        report.invested_pct = 1.0  # type: ignore[misc]
    with pytest.raises(Exception):
        report.rows[0].target_pct = 1.0  # type: ignore[misc]


# --- Stage 1 scope boundary -------------------------------------------------


def test_stage_one_emits_no_shares_sides_or_proposals():
    """Reports what the portfolio IS. Turning a dollar gap into an order is
    later-stage work carrying tax consequences and typed approval."""
    import ast

    source = (
        Path(__file__).resolve().parent.parent
        / "assistant" / "portfolio_rebalance.py"
    ).read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported.add(module)
            imported.update(f"{module}.{alias.name}" for alias in node.names)
    for forbidden in (
        "assistant.proposals",
        "assistant.allocation_proposals",
        "assistant.execution_service",
        "risk.execution_gate",
    ):
        assert not any(i.startswith(forbidden) for i in imported), imported

    fields = {
        f.name for f in dataclasses.fields(
            _row(_report(_snapshot(cash=10_000.0)), SLEEVE_CASH)
        )
    }
    for action_shaped in ("shares", "side", "quantity", "order", "proposal"):
        assert not any(action_shaped in f for f in fields), (action_shaped, fields)


# --- counter-review of the independent correction ---------------------------


def test_a_conflicted_sleeve_still_reports_its_band_state_and_breach():
    """REBAL1CR-001. Feasibility of a target and distance from it are
    independent facts. Letting a policy conflict occupy `status` hid the band
    state on every conflicted sleeve, and the headline breach count only
    counts band breaches -- so against the owner's approved profile and
    active policy the page reported ONE breached band while six sleeves were
    outside theirs. Understating drift on the page's most prominent number is
    worse than any wording problem it was solving.
    """
    report = _report(
        _snapshot(cash=10_000.0),
        policy=_policy(max_total_exposure_pct=0.50, max_position_pct=0.05),
    )
    invested = [s for s in SLEEVE_ORDER if s != SLEEVE_CASH]

    # every invested sleeve is empty against a positive target
    assert all(_row(report, s).status == STATUS_UNDERWEIGHT for s in invested)
    assert all(_row(report, s).policy_conflict_reason for s in invested)
    assert report.breached_count == len(invested) + 1, (
        "the headline must count every band breach, conflicted or not"
    )
    # and the conflict is still stated rather than lost
    assert any("total-exposure" in d for d in report.disclosures)


def test_the_owner_approved_profile_is_infeasible_under_the_active_policy():
    """Recorded as a fact the owner needs, not as a passing detail. The
    approved 90%-invested profile cannot be reached under a 50% total-exposure
    cap, and growth's 40% target exceeds the 30% capacity of six names each
    capped at 5%. The page must say so rather than presenting reachable-looking
    bands.
    """
    from assistant.policy import load_policy

    report = _report(_snapshot(cash=10_000.0), policy=load_policy())
    reasons = " ".join(r.policy_conflict_reason for r in report.rows)
    assert "total-exposure" in reasons
    assert "position-cap capacity" in reasons
    assert _row(report, SLEEVE_GROWTH).policy_conflict_reason


def test_every_row_carries_a_conflict_field_even_when_unusable():
    """The field must exist on the data-unavailable rows too, or a caller
    that reads it has to special-case the refusal path."""
    snapshot = dataclasses.replace(
        _snapshot(cash=10_000.0), total_equity=0.0, total_equity_exact=None
    )
    report = _report(snapshot)
    assert not report.usable
    assert all(r.policy_conflict_reason == "" for r in report.rows)
