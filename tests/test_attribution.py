"""GR-7c: performance attribution against a single benchmark bucket.

The plan's stated test is "attribution components sum to total return
within a stated tolerance". That alone would be vacuous here, because
selection is DEFINED as the residual and would reconcile by construction.
So the real tests below build scenarios whose answer is known by hand --
fully invested, fully in cash, half invested, benchmark flat -- and assert
the components match, which is what makes the reconciliation meaningful.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from assistant.attribution import (
    AttributionError,
    AttributionPoint,
    evaluate_attribution,
)

_START = datetime(2026, 1, 2, 21, 0, tzinfo=timezone.utc)


def _series(equity_and_invested_and_bench, *, days: int = 1):
    """Build points spaced `days` apart from (equity, invested, bench)."""
    return [
        AttributionPoint(
            at=_START + timedelta(days=index * days),
            total_equity=equity,
            invested_value=invested,
            benchmark_close=bench,
        )
        for index, (equity, invested, bench) in enumerate(
            equity_and_invested_and_bench
        )
    ]


def test_fully_invested_portfolio_matching_the_benchmark_has_no_attribution():
    """w = 1 and the portfolio tracks SPY exactly: cash drag is zero because
    there is no cash, and the residual is zero because nothing is left."""
    report = evaluate_attribution(
        _series([(100.0, 100.0, 400.0), (110.0, 110.0, 440.0)]),
        minimum_observations=2,
    )
    returns = report["returns"]
    decomposition = report["decomposition"]

    assert returns["portfolio_pct"] == "10"
    assert returns["benchmark_pct"] == "10"
    assert returns["active_pct"] == "0"
    assert decomposition["average_invested_weight_pct"] == "100"
    assert decomposition["allocation_pct"] == "0"
    assert decomposition["selection_pct"] == "0"


def test_all_cash_portfolio_attributes_the_entire_shortfall_to_cash_drag():
    """The owner's actual shape taken to its limit. Holding 100% cash while
    the benchmark gains 10% must show allocation = -10 and selection = 0 --
    the shortfall is entirely the decision not to be invested, and none of
    it is stock picking."""
    report = evaluate_attribution(
        _series([(100.0, 0.0, 400.0), (100.0, 0.0, 440.0)]),
        minimum_observations=2,
    )
    decomposition = report["decomposition"]

    assert report["returns"]["portfolio_pct"] == "0"
    assert report["returns"]["active_pct"] == "-10"
    assert decomposition["average_invested_weight_pct"] == "0"
    assert decomposition["allocation_pct"] == "-10"
    assert decomposition["selection_pct"] == "0"


def test_half_invested_tracking_the_benchmark_splits_exactly_in_half():
    """w = 0.5 against a +10% benchmark: cash drag is (0.5-1) x 10 = -5, and
    a portfolio that earns 5% (half of 10 on half the money) leaves nothing
    for the residual."""
    report = evaluate_attribution(
        _series([(100.0, 50.0, 400.0), (105.0, 55.0, 440.0)]),
        minimum_observations=2,
    )
    decomposition = report["decomposition"]

    assert report["returns"]["portfolio_pct"] == "5"
    assert decomposition["allocation_pct"] == "-5"
    assert decomposition["selection_pct"] == "0"


def test_outperformance_beyond_cash_drag_lands_in_selection():
    """Half invested but the portfolio gained 8% where cash drag alone
    predicts 5%. The extra 3 points are not explained by being underinvested
    and must fall to the residual."""
    report = evaluate_attribution(
        _series([(100.0, 50.0, 400.0), (108.0, 58.0, 440.0)]),
        minimum_observations=2,
    )
    decomposition = report["decomposition"]

    assert report["returns"]["active_pct"] == "-2"
    assert decomposition["allocation_pct"] == "-5"
    assert decomposition["selection_pct"] == "3"


def test_cash_drag_is_zero_when_the_benchmark_did_not_move():
    """Holding cash costs nothing when there was nothing to miss. A model
    that charged drag against a flat benchmark would blame the owner for a
    decision that had no consequence."""
    report = evaluate_attribution(
        _series([(100.0, 0.0, 400.0), (100.0, 0.0, 400.0)]),
        minimum_observations=2,
    )
    assert report["decomposition"]["allocation_pct"] == "0"
    assert report["decomposition"]["selection_pct"] == "0"


def test_a_deposit_is_not_counted_as_a_gain():
    """The single most common way a hand-rolled return calculation goes
    wrong. Equity doubles purely because money was added; the return must
    stay 0."""
    points = [
        AttributionPoint(
            at=_START, total_equity=100.0, invested_value=100.0,
            benchmark_close=400.0, flow=100.0,
        ),
        AttributionPoint(
            at=_START + timedelta(days=1), total_equity=200.0,
            invested_value=200.0, benchmark_close=400.0,
        ),
    ]
    report = evaluate_attribution(points, minimum_observations=2)
    assert report["returns"]["portfolio_pct"] == "0"


def test_components_reconcile_with_active_return_across_a_longer_series():
    """The plan's stated requirement, over a series with varying weight and
    a benchmark that moves both ways."""
    from decimal import Decimal

    report = evaluate_attribution(
        _series(
            [
                (100.0, 10.0, 400.0),
                (101.0, 20.0, 405.0),
                (99.0, 40.0, 395.0),
                (104.0, 60.0, 410.0),
                (103.0, 55.0, 402.0),
            ]
        ),
        minimum_observations=2,
    )
    decomposition = report["decomposition"]
    total = Decimal(decomposition["allocation_pct"]) + Decimal(
        decomposition["selection_pct"]
    )
    assert abs(total - Decimal(report["returns"]["active_pct"])) <= Decimal(
        decomposition["reconciliation_tolerance_pct"]
    )
    assert decomposition["reconciles"] is True


def test_thin_history_is_declared_insufficient_rather_than_reported_plainly():
    """The live situation: eight days of snapshots. The numbers still
    compute, but the report must say they are arithmetic on noise instead of
    presenting a confident decomposition."""
    report = evaluate_attribution(
        _series([(100.0, 50.0, 400.0), (101.0, 51.0, 402.0)]),
    )
    sufficiency = report["sample_sufficiency"]
    assert sufficiency["sufficient"] is False
    assert sufficiency["independent_count"] == 2
    assert sufficiency["required_count"] == 20
    assert sufficiency["independent_observation_unit"] == "market session"
    assert any("independent session" in r for r in sufficiency["insufficiency_reasons"])


def test_intraday_recaptures_are_not_counted_as_independent_observations():
    """Found by running this against the real database: the operator captures
    equity many times a day, so three days held 125 snapshots and the report
    happily declared a 125-observation sample "sufficient".

    Those are re-reads of the same account on the same day, not independent
    evidence. CLAUDE.md section 6: count independent dates, not correlated
    rows. The session is the unit; the raw point count is reported beside it
    so the ratio is visible rather than hidden.
    """
    points = [
        AttributionPoint(
            at=_START + timedelta(hours=index),
            total_equity=100.0 + index,
            invested_value=50.0,
            benchmark_close=400.0 + index,
            session_date="2026-01-02" if index < 12 else "2026-01-05",
        )
        for index in range(24)
    ]
    report = evaluate_attribution(points)
    sufficiency = report["sample_sufficiency"]

    assert sufficiency["valuation_point_count"] == 24
    assert sufficiency["independent_count"] == 2, (
        "24 intraday captures across two sessions are two independent "
        "observations, not 24"
    )
    assert sufficiency["sufficient"] is False


def test_sessions_are_taken_from_the_recorded_date_not_derived_from_utc():
    """`at` is UTC and sessions are Eastern, so deriving the date from `at`
    mis-buckets every capture after 8pm Eastern into the next session -- the
    defect already fixed once in storage.get_execution_budget_usage(). Two
    captures that straddle UTC midnight but share an Eastern session must
    count once."""
    points = [
        AttributionPoint(
            at=datetime(2026, 1, 3, 0, 30, tzinfo=timezone.utc),  # Jan 2, 7:30pm ET
            total_equity=100.0, invested_value=50.0, benchmark_close=400.0,
            session_date="2026-01-02",
        ),
        AttributionPoint(
            at=datetime(2026, 1, 3, 1, 30, tzinfo=timezone.utc),  # Jan 2, 8:30pm ET
            total_equity=101.0, invested_value=50.0, benchmark_close=402.0,
            session_date="2026-01-02",
        ),
    ]
    report = evaluate_attribution(points, minimum_observations=1)
    assert report["sample_sufficiency"]["independent_count"] == 1
    assert report["sample_sufficiency"]["valuation_point_count"] == 2


def test_costs_and_taxes_are_reported_as_already_inside_never_re_deducted():
    report = evaluate_attribution(
        _series([(100.0, 100.0, 400.0), (110.0, 110.0, 440.0)]),
        realized_cost=12.5,
        realized_tax=30.0,
        minimum_observations=2,
    )
    drags = report["realized_drags"]
    assert drags["already_inside_portfolio_return"] is True
    assert drags["cost"]["amount"] == "12.5"
    assert drags["tax"]["amount"] == "30"
    # They must NOT appear inside the identity.
    assert "cost" not in report["decomposition"]
    assert "tax" not in report["decomposition"]


def test_absent_cost_and_tax_are_unavailable_not_zero():
    """A zero would read as 'this cost you nothing', which is a different
    claim from 'nobody told me'."""
    report = evaluate_attribution(
        _series([(100.0, 100.0, 400.0), (110.0, 110.0, 440.0)]),
        minimum_observations=2,
    )
    for key in ("cost", "tax"):
        entry = report["realized_drags"][key]
        assert entry["available"] is False
        assert entry["amount"] is None
        assert entry["unavailable_reason"]


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"total_equity": 0.0}, "total_equity must be positive"),
        ({"total_equity": float("nan")}, "must be finite"),
        ({"benchmark_close": 0.0}, "benchmark_close must be positive"),
        ({"invested_value": -1.0}, "cannot be negative"),
        ({"at": datetime(2026, 1, 2)}, "timezone-aware"),
    ],
)
def test_unusable_points_refuse_at_construction(kwargs, match):
    base = dict(
        at=_START, total_equity=100.0, invested_value=50.0, benchmark_close=400.0
    )
    base.update(kwargs)
    with pytest.raises(AttributionError, match=match):
        AttributionPoint(**base)


def test_a_single_point_cannot_produce_a_return():
    with pytest.raises(AttributionError, match="at least two"):
        evaluate_attribution(_series([(100.0, 50.0, 400.0)]))


def test_duplicate_timestamps_refuse():
    """Two valuations at the same instant make the chain ambiguous."""
    point = AttributionPoint(
        at=_START, total_equity=100.0, invested_value=50.0, benchmark_close=400.0
    )
    with pytest.raises(AttributionError, match="distinct timestamps"):
        evaluate_attribution([point, point])


def test_report_carries_no_action_shaped_field():
    """Same discipline as GR-7b: a reporting payload must not read as an
    instruction."""
    report = evaluate_attribution(
        _series([(100.0, 50.0, 400.0), (108.0, 58.0, 440.0)]),
        minimum_observations=2,
    )
    forbidden = ("buy", "sell", "order", "recommend", "suggest", "should", "trade")
    found: list[str] = []

    def walk(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                if any(word in str(key).lower() for word in forbidden):
                    found.append(f"{path}.{key}")
                walk(value, f"{path}.{key}")
        elif isinstance(node, (list, tuple)):
            for index, item in enumerate(node):
                walk(item, f"{path}[{index}]")

    walk(report)
    assert not found, f"action-shaped keys in a reporting payload: {found}"


def test_selection_is_labelled_a_residual_not_a_skill_measurement():
    """The most likely misreading of this report, pinned in the payload so
    it travels with the number."""
    report = evaluate_attribution(
        _series([(100.0, 50.0, 400.0), (108.0, 58.0, 440.0)]),
        minimum_observations=2,
    )
    meaning = report["decomposition"]["selection_meaning"].lower()
    assert "residual" in meaning
    assert "not a skill measurement" in meaning
    assert "leverage" in meaning


def test_benchmark_defaults_to_the_ticker_the_epoch_already_binds():
    """paper_evidence writes benchmark_ticker=SPY into every observation.
    A different default here would put two benchmarks in one epoch."""
    report = evaluate_attribution(
        _series([(100.0, 50.0, 400.0), (108.0, 58.0, 440.0)]),
        minimum_observations=2,
    )
    assert report["benchmark_ticker"] == "SPY"


def test_weight_uses_beginning_of_period_not_an_average_including_the_end():
    """Pins the convention, because the plausible-looking alternative is
    wrong in a way that is easy to miss.

    Each point's weight is the allocation in force during the period that
    FOLLOWS it, so the final point is excluded. Averaging it in folds the
    period's own return back into the weight: a portfolio that rose because
    it was invested shows a higher end weight *because* it rose, and cash
    drag gets measured partly against its own consequence.

    Concretely, 50% invested into a +10% benchmark is exactly -5 of cash
    drag. Averaging the endpoint in silently produces -4.81 -- close enough
    to look right, wrong enough to misattribute every period.
    """
    from decimal import Decimal

    report = evaluate_attribution(
        _series([(100.0, 50.0, 400.0), (105.0, 55.0, 440.0)]),
        minimum_observations=2,
    )
    decomposition = report["decomposition"]

    assert decomposition["average_invested_weight_pct"] == "50", (
        "weight must be the 50% held going INTO the period, not the 52.38% "
        "held after it"
    )
    assert Decimal(decomposition["allocation_pct"]) == Decimal("-5")
    assert Decimal(decomposition["selection_pct"]) == Decimal("0")
