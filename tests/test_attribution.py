"""GR-7c: performance attribution against a single benchmark bucket.

The plan's stated test is "attribution components sum to total return
within a stated tolerance". That alone would be vacuous here, because
selection is DEFINED as the residual and would reconcile by construction.
So the real tests below build scenarios whose answer is known by hand --
fully invested, fully in cash, half invested, benchmark flat -- and assert
the components match, which is what makes the reconciliation meaningful.
"""
from __future__ import annotations

import json
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
    stay 0.

    Convention matches ``portfolio_equity_snapshots``: ``total_equity`` is
    POST-flow broker equity, and ``flow`` is the deposit that produced it.
    Passing that equity straight into ``Observation.value_before_flow``
    (the pre-fix wiring) reported about +33% on a three-point deposit-only
    series and dumped it into selection.
    """
    points = [
        AttributionPoint(
            at=_START, total_equity=100.0, invested_value=100.0,
            benchmark_close=400.0,
        ),
        AttributionPoint(
            at=_START + timedelta(days=1), total_equity=200.0,
            invested_value=200.0, benchmark_close=400.0, flow=100.0,
        ),
        AttributionPoint(
            at=_START + timedelta(days=2), total_equity=200.0,
            invested_value=200.0, benchmark_close=400.0,
        ),
    ]
    report = evaluate_attribution(points, minimum_observations=2)
    assert report["returns"]["portfolio_pct"] == "0"
    assert report["decomposition"]["selection_pct"] == "0"


def test_post_flow_equity_minus_flow_cannot_go_negative():
    with pytest.raises(AttributionError, match="total_equity - flow"):
        AttributionPoint(
            at=_START,
            total_equity=100.0,
            invested_value=0.0,
            benchmark_close=400.0,
            flow=150.0,
        )


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
    # The module's own `reconciles` flag is computed on UNROUNDED values and
    # is the real guarantee. This assertion sums the REPORTED values, which
    # are quantized to 4dp, so it must allow for that rounding: three
    # independently rounded figures can each be off by 5e-5, which exceeds
    # the module's 1e-4 tolerance in the worst case. Reusing that tolerance
    # here would be a test that passes on today's numbers and fails on some
    # future input for a reason unrelated to the invariant -- exactly the
    # kind of intermittent failure this project already has one of.
    rounding_slack = Decimal("0.0002")
    assert abs(total - Decimal(report["returns"]["active_pct"])) <= rounding_slack
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


def test_nan_realized_cost_refuses_as_attribution_error():
    """Callers catch AttributionError; a raw ValueError from to_decimal would
    traceback through the CLI the same way GR-7b's measured-vol path did."""
    with pytest.raises(AttributionError, match="realized_cost"):
        evaluate_attribution(
            _series([(100.0, 50.0, 400.0), (105.0, 55.0, 440.0)]),
            realized_cost=float("nan"),
            minimum_observations=2,
        )


def test_overinvested_weight_does_not_claim_cash_drag():
    """w > 1 is leverage / negative cash, not underinvestment. Labelling that
    allocation term 'cash drag' would invert the meaning."""
    report = evaluate_attribution(
        _series([(100.0, 150.0, 400.0), (110.0, 160.0, 440.0)]),
        minimum_observations=2,
    )
    meaning = report["decomposition"]["allocation_meaning"].lower()
    assert meaning.startswith("invested-weight effect")
    assert "so this is not cash drag" in meaning
    assert report["decomposition"]["average_invested_weight_pct"] == "150"


def test_attribution_cli_leaves_execution_and_evidence_tables_untouched(tmp_path):
    """CLAUDE.md section 9: read-only commands must be proven read-only."""
    from types import SimpleNamespace

    import scripts.run_personal_assistant as cli
    from assistant.storage import AssistantStore

    store = AssistantStore(tmp_path / "assistant.db")
    account_key = "paper:test"
    for index in range(3):
        store.append_portfolio_equity_snapshot(
            {
                "account_key": account_key,
                "session_date": f"2026-01-0{index + 2}",
                "captured_at": (
                    _START + timedelta(days=index)
                ).isoformat(),
                "total_equity": "100",
                "cash": "50",
                "net_external_flow": "0",
                "benchmarks": {"SPY": str(400 + index)},
            }
        )

    tables = (
        "trade_proposals",
        "broker_orders",
        "broker_order_events",
        "execution_reservations",
        "execution_telemetry_events",
        "decision_packets",
        "paper_account_observations",
        "paper_evidence_epochs",
        "journal_transactions",
        "data_provider_fetches",
    )

    def counts():
        with store._connect() as connection:
            return {
                name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                for name in tables
            }

    before = counts()
    cli.command_attribution(
        SimpleNamespace(
            account_key=account_key,
            benchmark="SPY",
            limit=500,
            minimum_observations=2,
            json=True,
        ),
        store=store,
    )
    assert counts() == before


def test_attribution_cli_skips_cash_exceeding_equity_instead_of_clamping(tmp_path):
    """Silent clamp to invested=0 would report all-cash for a corrupt row."""
    from types import SimpleNamespace

    import scripts.run_personal_assistant as cli
    from assistant.storage import AssistantStore

    store = AssistantStore(tmp_path / "assistant.db")
    account_key = "paper:test"
    store.append_portfolio_equity_snapshot(
        {
            "account_key": account_key,
            "session_date": "2026-01-02",
            "captured_at": _START.isoformat(),
            "total_equity": "100",
            "cash": "50",
            "net_external_flow": "0",
            "benchmarks": {"SPY": "400"},
        }
    )
    store.append_portfolio_equity_snapshot(
        {
            "account_key": account_key,
            "session_date": "2026-01-03",
            "captured_at": (_START + timedelta(days=1)).isoformat(),
            "total_equity": "100",
            "cash": "150",
            "net_external_flow": "0",
            "benchmarks": {"SPY": "410"},
        }
    )
    store.append_portfolio_equity_snapshot(
        {
            "account_key": account_key,
            "session_date": "2026-01-04",
            "captured_at": (_START + timedelta(days=2)).isoformat(),
            "total_equity": "105",
            "cash": "50",
            "net_external_flow": "0",
            "benchmarks": {"SPY": "420"},
        }
    )

    # Only two usable points remain; with minimum_observations=2 the report
    # still builds, and the corrupt middle row must appear in skipped.
    import io
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cli.command_attribution(
            SimpleNamespace(
                account_key=account_key,
                benchmark="SPY",
                limit=500,
                minimum_observations=2,
                json=True,
            ),
            store=store,
        )
    import json

    payload = json.loads(buf.getvalue())
    assert any("cash exceeds equity" in item for item in payload["skipped_snapshots"])


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


def _cli_args(**overrides):
    from types import SimpleNamespace

    base = dict(
        benchmark="SPY",
        account_key=None,
        limit=500,
        minimum_observations=2,
        json=True,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class _SnapshotStore:
    """Only what command_attribution reads."""

    def __init__(self, rows):
        self._rows = rows

    def list_portfolio_equity_account_keys(self):
        return sorted({row["account_key"] for row in self._rows})

    def list_portfolio_equity_snapshots(self, account_key, *, limit=10_000):
        return [r for r in self._rows if r["account_key"] == account_key][:limit]


def _snapshot_row(session, equity, cash, close, flow="0", key="alpaca:paper:x"):
    return {
        "account_key": key,
        "session_date": session,
        "captured_at": f"{session}T21:00:00+00:00",
        "total_equity": str(equity),
        "cash": str(cash),
        "net_external_flow": flow,
        "benchmarks": {"SPY": str(close)} if close is not None else {},
    }


def test_cli_refuses_when_a_skipped_snapshot_carried_an_external_flow():
    """Counter-review of GR7CREV-002's fix, and of my own earlier skip path.

    Skipping a valuation point silently reintroduces the deposit-as-gain
    error: the chain links across the gap, so the equity jump the deposit
    caused is read as return. Verified -- dropping a point whose $100
    deposit doubled equity reports +100%.

    Refusing is the only honest option. Publishing a performance number that
    is mostly a bank transfer would be worse than publishing nothing.
    """
    import scripts.run_personal_assistant as cli

    rows = [
        _snapshot_row("2026-01-02", 100, 50, 400),
        # Middle point is skipped (no benchmark close) AND carried a deposit.
        _snapshot_row("2026-01-03", 200, 150, None, flow="100"),
        _snapshot_row("2026-01-04", 200, 100, 400),
    ]
    with pytest.raises(SystemExit, match="carried external cash"):
        cli.command_attribution(_cli_args(), store=_SnapshotStore(rows))


def test_cli_still_reports_when_the_skipped_snapshot_had_no_flow():
    """Guards against 'fixing' the above by refusing on every skip. A
    snapshot missing only its benchmark close is droppable -- the chain
    stays honest because no money moved."""
    import scripts.run_personal_assistant as cli

    rows = [
        _snapshot_row("2026-01-02", 100, 50, 400),
        _snapshot_row("2026-01-03", 105, 50, None),
        _snapshot_row("2026-01-05", 110, 55, 440),
    ]
    cli.command_attribution(_cli_args(), store=_SnapshotStore(rows))


def test_cli_never_pools_two_accounts_into_one_return_series():
    """The operator database holds both the live paper account and
    `manual:manual` sample rows. Blending them would attribute one
    portfolio's return to another's allocation."""
    import scripts.run_personal_assistant as cli

    rows = [
        _snapshot_row("2026-01-02", 100, 50, 400),
        _snapshot_row("2026-01-03", 110, 55, 440),
        _snapshot_row("2026-01-02", 999, 999, 400, key="manual:manual"),
    ]
    store = _SnapshotStore(rows)
    # Both keys exist, but only one is a broker account, so it is chosen
    # without needing --account-key.
    cli.command_attribution(_cli_args(), store=store)
    with pytest.raises(SystemExit, match="no snapshots for"):
        cli.command_attribution(_cli_args(account_key="nope"), store=store)


def test_cli_deposit_on_kept_snapshot_is_not_counted_as_return():
    """GR7CFOLLOW-001: the kept path must match portfolio_performance_report.

    Snapshots store post-flow equity. A $100 deposit that doubles the account
    must report 0% portfolio return, not ~+33% dumped into selection.
    """
    import io
    from contextlib import redirect_stdout

    import scripts.run_personal_assistant as cli

    rows = [
        _snapshot_row("2026-01-02", 100, 0, 400),
        _snapshot_row("2026-01-03", 200, 100, 400, flow="100"),
        _snapshot_row("2026-01-04", 200, 100, 400),
    ]
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        cli.command_attribution(_cli_args(json=True), store=_SnapshotStore(rows))
    report = json.loads(buffer.getvalue())
    assert report["returns"]["portfolio_pct"] == "0"
    assert report["decomposition"]["selection_pct"] == "0"
    assert (
        report["decomposition"]["average_invested_weight_method"]
        == "session_equalized_beginning_of_period"
    )


def test_human_cli_does_not_call_leverage_cash_drag(capsys):
    """GR7CFOLLOW-003: non-JSON output must follow allocation_meaning."""
    import scripts.run_personal_assistant as cli

    rows = [
        _snapshot_row("2026-01-02", 100, -20, 400),  # invested 120 > equity
        _snapshot_row("2026-01-03", 110, -20, 440),
    ]
    cli.command_attribution(_cli_args(json=False), store=_SnapshotStore(rows))
    text = capsys.readouterr().out
    assert "cash drag" not in text
    assert "invested-weight effect" in text
    assert "session_equalized_beginning_of_period" in text


def test_weight_is_equalized_by_session_not_biased_by_capture_frequency():
    """Found on the live account during a fresh-eyes pass.

    The operator captures equity an arbitrary number of times per day, so a
    flat mean over valuation points weights each day by how often the app
    happened to be running. On the real data 2026-08-03 supplied 27 of 49
    captures at 0.88% invested, pulling the reported average weight to 5.71%
    where the session-equalized figure is 8.00% -- a 2.3-point error that
    flows straight into cash drag, since allocation = (w-1)*R_benchmark.

    Here: session A is captured nine times at 0% invested, session B once at
    100%. Two sessions, so the honest average is 50%. A flat point mean gives
    10% -- reporting a portfolio as nearly all cash when it spent half its
    sessions fully invested.
    """
    points = [
        AttributionPoint(
            at=_START + timedelta(hours=index),
            total_equity=100.0,
            invested_value=0.0,
            benchmark_close=400.0,
            session_date="2026-01-02",
        )
        for index in range(9)
    ]
    points.append(
        AttributionPoint(
            at=_START + timedelta(hours=9),
            total_equity=100.0,
            invested_value=100.0,
            benchmark_close=400.0,
            session_date="2026-01-05",
        )
    )
    # A trailing point so the two weighted sessions are both begin-of-period.
    points.append(
        AttributionPoint(
            at=_START + timedelta(hours=10),
            total_equity=110.0,
            invested_value=110.0,
            benchmark_close=440.0,
            session_date="2026-01-06",
        )
    )

    report = evaluate_attribution(points, minimum_observations=1)
    assert report["decomposition"]["average_invested_weight_pct"] == "50", (
        "nine captures of one session must not outvote one capture of another"
    )
    assert (
        report["decomposition"]["average_invested_weight_method"]
        == "session_equalized_beginning_of_period"
    )
    assert report["decomposition"]["average_invested_weight_unit"] == "market session"


def test_single_capture_per_session_is_unchanged_by_equalization():
    """Guards against 'fixing' the above in a way that distorts the ordinary
    case: with one capture per session, equalizing is a no-op."""
    report = evaluate_attribution(
        [
            AttributionPoint(
                at=_START + timedelta(days=index),
                total_equity=100.0,
                invested_value=invested,
                benchmark_close=400.0,
                session_date=f"2026-01-{2 + index:02d}",
            )
            for index, invested in enumerate([20.0, 40.0, 60.0, 99.0])
        ],
        minimum_observations=1,
    )
    # Begin-of-period weights are 20/40/60 (the last point starts no period).
    assert report["decomposition"]["average_invested_weight_pct"] == "40"
