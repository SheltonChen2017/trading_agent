"""Wide-band drift measurement (REBAL-1 core).

The behaviour under test is the one the confirmed finding actually turns on:
a breach is corrected to the nearest band EDGE, never to the target. Trading
back to target is precisely what "wide rebalance band vs. tight/continuous
vol-targeting" measured against, so a module that silently corrected to the
centre would implement the arm that LOST while citing the arm that won.

The other half is the failure direction, which differs from the hedge
sleeve's in an important way. A weight is a ratio, so one unreadable holding
corrupts the denominator shared by every other holding -- a single bad row
can manufacture a phantom breach on a ticker whose own value is perfectly
readable. Dropping the bad row is therefore not a conservative choice here;
it is the dangerous one.
"""
from __future__ import annotations

import dataclasses
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.context_builder import build_portfolio_snapshot
from assistant.rebalance_bands import (
    ABOVE,
    BELOW,
    INSIDE,
    DriftReport,
    evaluate_drift,
)


def _held(ticker, shares, price):
    return {
        "ticker": ticker, "shares": shares,
        "entry_price": price, "current_price": price,
    }


def _snapshot(positions=None, cash=0.0):
    return build_portfolio_snapshot(positions or [], cash=cash)


# --- the band, and where a correction stops ---------------------------------


def test_a_holding_inside_its_band_produces_no_trade():
    """The entire point. A 50% target with a 20% relative band tolerates
    anything from 40% to 60% without trading."""
    snapshot = _snapshot([_held("AAA", 45, 100.0), _held("BBB", 55, 100.0)])
    report = evaluate_drift(
        snapshot, targets={"AAA": 50, "BBB": 50}, band_fraction=0.2
    )
    assert report.usable, report.refusals
    assert not report.has_breach
    for row in report.rows:
        assert row.state == INSIDE
        assert Decimal(row.correction_dollars_exact) == 0


def test_a_breach_is_corrected_to_the_band_edge_not_to_the_target():
    """THE case. AAA is 70% of a $10,000 book against a 50% target with a 20%
    relative band, so its band ends at 60%. The correction is $7,000 -> $6,000
    (sell $1,000), NOT $7,000 -> $5,000 (sell $2,000). Correcting to target
    would trade twice as much and realize twice the gain.
    """
    snapshot = _snapshot([_held("AAA", 70, 100.0), _held("BBB", 30, 100.0)])
    report = evaluate_drift(
        snapshot, targets={"AAA": 50, "BBB": 50}, band_fraction=0.2
    )
    aaa = next(r for r in report.rows if r.ticker == "AAA")
    assert aaa.state == ABOVE
    assert aaa.current_pct == pytest.approx(70.0)
    assert aaa.upper_edge_pct == pytest.approx(60.0)
    assert Decimal(aaa.correction_dollars_exact) == Decimal("-1000"), (
        "a sell to the 60% edge is $1,000; to the 50% target it would be $2,000"
    )


def test_an_underweight_breach_corrects_upward_to_its_lower_edge():
    snapshot = _snapshot([_held("AAA", 30, 100.0), _held("BBB", 70, 100.0)])
    report = evaluate_drift(
        snapshot, targets={"AAA": 50, "BBB": 50}, band_fraction=0.2
    )
    aaa = next(r for r in report.rows if r.ticker == "AAA")
    assert aaa.state == BELOW
    assert aaa.lower_edge_pct == pytest.approx(40.0)
    assert Decimal(aaa.correction_dollars_exact) == Decimal("1000")


def test_the_band_is_relative_to_each_target_not_absolute_points():
    """A 20% relative band is +/-10 points on a 50% target and +/-0.4 points
    on a 2% one. Absolute points would make 'wide' mean something different
    at every target size."""
    snapshot = _snapshot([_held("BIG", 50, 100.0), _held("SMALL", 2, 100.0)],
                         cash=4_800.0)
    report = evaluate_drift(
        snapshot, targets={"BIG": 50, "SMALL": 2}, band_fraction=0.2
    )
    big = next(r for r in report.rows if r.ticker == "BIG")
    small = next(r for r in report.rows if r.ticker == "SMALL")
    assert (big.upper_edge_pct - big.target_pct) == pytest.approx(10.0)
    assert (small.upper_edge_pct - small.target_pct) == pytest.approx(0.4)


def test_the_edge_is_inclusive_so_sitting_exactly_on_it_does_not_trade():
    """Exactly at the edge is inside. A boundary that trades on equality
    churns every time a price rounds onto it."""
    snapshot = _snapshot([_held("AAA", 60, 100.0), _held("BBB", 40, 100.0)])
    report = evaluate_drift(
        snapshot, targets={"AAA": 50, "BBB": 50}, band_fraction=0.2
    )
    assert not report.has_breach
    assert all(r.state == INSIDE for r in report.rows)


def test_a_target_with_no_holding_at_all_reads_as_a_full_underweight():
    snapshot = _snapshot([_held("AAA", 100, 100.0)])
    report = evaluate_drift(
        snapshot, targets={"AAA": 50, "BBB": 50}, band_fraction=0.2
    )
    bbb = next(r for r in report.rows if r.ticker == "BBB")
    assert not bbb.held
    assert bbb.state == BELOW
    assert Decimal(bbb.correction_dollars_exact) == Decimal("4000")  # to 40%


# --- the failure direction --------------------------------------------------


def test_one_unreadable_holding_refuses_the_whole_portfolio():
    """Unlike a per-instrument sleeve, a weight shares its denominator with
    every other holding, so dropping the bad row would silently move every
    other row's percentage and could manufacture a breach anywhere."""
    snapshot = _snapshot([_held("AAA", 50, 100.0), _held("BBB", 50, 100.0)])
    positions = [
        dataclasses.replace(
            p, market_value=float("nan"), market_value_exact=None
        ) if p.ticker == "AAA" else p
        for p in snapshot.positions
    ]
    snapshot = dataclasses.replace(snapshot, positions=positions)

    report = evaluate_drift(
        snapshot, targets={"AAA": 50, "BBB": 50}, band_fraction=0.2
    )
    assert not report.usable
    assert not report.has_breach
    assert any("AAA" in r for r in report.refusals)
    # and BBB, whose own value is fine, must not be reported as drifted
    bbb = next(r for r in report.rows if r.ticker == "BBB")
    assert bbb.state == INSIDE
    assert Decimal(bbb.correction_dollars_exact) == 0


def test_a_malformed_exact_value_does_not_fall_back_to_the_float():
    snapshot = _snapshot([_held("AAA", 50, 100.0), _held("BBB", 50, 100.0)])
    positions = [
        dataclasses.replace(
            p, market_value=5_000.0, market_value_exact="not-a-number"
        ) if p.ticker == "AAA" else p
        for p in snapshot.positions
    ]
    snapshot = dataclasses.replace(snapshot, positions=positions)
    report = evaluate_drift(
        snapshot, targets={"AAA": 50, "BBB": 50}, band_fraction=0.2
    )
    assert not report.usable


def test_a_zero_share_row_reads_as_not_held_rather_than_refusing():
    snapshot = _snapshot([_held("AAA", 0, 100.0), _held("BBB", 100, 100.0)])
    report = evaluate_drift(
        snapshot, targets={"AAA": 50, "BBB": 50}, band_fraction=0.2
    )
    assert report.usable, report.refusals
    aaa = next(r for r in report.rows if r.ticker == "AAA")
    assert aaa.state == BELOW


@pytest.mark.parametrize("equity", [0.0, -1.0, float("nan"), float("inf")])
def test_unusable_equity_refuses(equity):
    snapshot = dataclasses.replace(
        _snapshot([_held("AAA", 50, 100.0)]),
        total_equity=equity, total_equity_exact=None,
    )
    report = evaluate_drift(
        snapshot, targets={"AAA": 100}, band_fraction=0.2
    )
    assert not report.usable


@pytest.mark.parametrize(
    "band", [0, -0.1, 0.009, 1.5, float("nan"), float("inf"), "", "abc", None]
)
def test_an_unusable_band_refuses(band):
    report = evaluate_drift(
        _snapshot([_held("AAA", 50, 100.0)]),
        targets={"AAA": 100}, band_fraction=band,
    )
    assert not report.usable


@pytest.mark.parametrize(
    "targets",
    [
        {},
        None,
        ["AAA"],
        {"AAA": -5},
        {"AAA": 101},
        {"AAA": "abc"},
        {"AAA": float("nan")},
        {"": 50},
        {5: 50},
    ],
)
def test_unusable_targets_refuse(targets):
    report = evaluate_drift(
        _snapshot([_held("AAA", 50, 100.0)]),
        targets=targets, band_fraction=0.2,
    )
    assert not report.usable


def test_targets_summing_above_one_hundred_percent_refuse():
    """Unreachable without leverage this app does not use, so every band
    derived from those targets would be fiction."""
    report = evaluate_drift(
        _snapshot([_held("AAA", 50, 100.0)]),
        targets={"AAA": 60, "BBB": 60}, band_fraction=0.2,
    )
    assert not report.usable
    assert any("exceeds 100" in r for r in report.refusals)


def test_targets_summing_below_one_hundred_are_allowed_as_a_cash_allocation():
    report = evaluate_drift(
        _snapshot([_held("AAA", 40, 100.0)], cash=6_000.0),
        targets={"AAA": 40}, band_fraction=0.2,
    )
    assert report.usable, report.refusals


def test_a_duplicated_target_refuses_rather_than_depending_on_dict_order():
    report = evaluate_drift(
        _snapshot([_held("AAA", 50, 100.0)]),
        targets={"AAA": 50, "aaa": 30}, band_fraction=0.2,
    )
    assert not report.usable
    assert any("more than one target weight" in r for r in report.refusals)


# --- what the report is allowed to claim ------------------------------------


def test_holdings_without_a_target_are_named_not_silently_ignored():
    """They still occupy the shared denominator, so a reader who assumes the
    targets describe the whole portfolio is misreading every weight."""
    snapshot = _snapshot([_held("AAA", 50, 100.0), _held("ZZZ", 50, 100.0)])
    report = evaluate_drift(
        snapshot, targets={"AAA": 50}, band_fraction=0.2
    )
    assert any("ZZZ" in note for note in report.notes)


def test_the_report_never_promises_the_confirmed_number_transfers():
    report = evaluate_drift(
        _snapshot([_held("AAA", 50, 100.0)]),
        targets={"AAA": 50}, band_fraction=0.2,
    )
    joined = " ".join(report.notes)
    assert "not a prediction about this portfolio" in joined
    assert "nearest band EDGE, never to the target" in joined


def test_the_report_is_immutable():
    report = evaluate_drift(
        _snapshot([_held("AAA", 50, 100.0)]),
        targets={"AAA": 50}, band_fraction=0.2,
    )
    with pytest.raises(Exception):
        report.band_fraction = 0.5  # type: ignore[misc]
    with pytest.raises(Exception):
        report.rows[0].ticker = "X"  # type: ignore[misc]


# --- boundaries this milestone must not cross -------------------------------


def test_the_module_proposes_nothing_and_touches_no_policy():
    """REBAL-1's core measures only. Rebalancing SELLS on the app's own
    initiative, unlike every other sell path here, and that surface belongs
    to the reviewed milestone plan rather than to a default chosen in the
    module that happened to be written first.

    The invariant is what the module IMPORTS, not what its prose mentions.
    The first version of this guard searched the source text and failed on
    the docstring sentence explaining that no proposal is created -- it would
    have banned the explanation rather than the dependency, the same mistake
    `test_the_reader_opens_the_database_read_only` already corrected once.
    """
    import ast

    source = (
        Path(__file__).resolve().parent.parent
        / "assistant" / "rebalance_bands.py"
    ).read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported.add(module)
            imported.update(f"{module}.{alias.name}" for alias in node.names)

    forbidden = (
        "assistant.proposals",
        "assistant.policy",
        "risk.execution_gate",
        "assistant.execution_service",
        "assistant.allocation_proposals",
    )
    for name in forbidden:
        assert not any(i.startswith(name) for i in imported), (name, imported)

    called = {
        node.func.id
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not {"TradeProposal", "TradeIntent"} & called, called
