"""GR-7b: idle-cash reporting against policy bounds and the mandate.

The dangerous directions for a REPORT are different from those for an
execution path: it cannot lose money directly, but a number a reader trusts
is acted on by a human. So these tests pin (a) that broken inputs refuse
rather than produce a confident figure, (b) that an unmeasured quantity is
reported absent rather than defaulted, and (c) that nothing in the payload
is action-shaped.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from assistant.cash_reporting import CashReportError, evaluate_idle_cash
from assistant.mandate import PortfolioMandate
from assistant.policy import load_policy, DEFAULT_POLICY_PATH
from assistant.schemas import PortfolioPosition, PortfolioSnapshot

_MANDATE = PortfolioMandate(
    version="test-1",
    name="test mandate",
    target_annualized_volatility_min_pct=12.0,
    target_annualized_volatility_max_pct=18.0,
)


def _policy(**overrides):
    import dataclasses

    return dataclasses.replace(load_policy(DEFAULT_POLICY_PATH), **overrides)


def _position(ticker: str, market_value: float, **overrides) -> PortfolioPosition:
    kwargs = dict(
        ticker=ticker,
        shares=10.0,
        entry_price=market_value / 10,
        current_price=market_value / 10,
        market_value=market_value,
        unrealized_pnl_pct=0.0,
        is_leveraged_etf=False,
    )
    kwargs.update(overrides)
    return PortfolioPosition(**kwargs)


def _snapshot(cash: float, positions, equity: float, **overrides) -> PortfolioSnapshot:
    kwargs = dict(
        positions=list(positions),
        cash=cash,
        total_equity=equity,
        as_of="2026-08-06",
        source="alpaca",
        account_mode="paper",
    )
    kwargs.update(overrides)
    return PortfolioSnapshot(**kwargs)


def test_reports_idle_cash_against_both_policy_bounds():
    """The owner's actual shape: mostly cash, well inside every limit, and
    therefore invisible to every existing check -- risk_copilot only reports
    the reserve floor being BREACHED, never cash sitting far above it."""
    report = evaluate_idle_cash(
        _snapshot(87_000.0, [_position("AAPL", 6_500.0), _position("MSFT", 6_500.0)], 100_000.0),
        _policy(),
        _MANDATE,
    )

    totals = report["totals"]
    assert totals["cash_pct"] == "87"
    assert totals["invested_pct"] == "13"

    bounds = report["policy_bounds"]
    assert bounds["reserve_floor"] == "10000"
    assert bounds["exposure_ceiling"] == "50000"
    assert bounds["cash_above_reserve"] == "77000"
    assert bounds["reserve_floor_breached"] is False
    # 50k ceiling - 13k invested. Less than the 77k of cash above the floor,
    # so exposure is what actually binds -- the distinction the report exists
    # to make.
    assert bounds["unused_exposure_capacity"] == "37000"
    assert bounds["policy_headroom"] == "37000"
    assert bounds["binding_constraint"] == "exposure_ceiling"


def test_reserve_floor_breach_is_reported_signed_not_clamped():
    """A breach is a different and more urgent condition than idle cash.
    Clamping cash_above_reserve at zero would erase it."""
    report = evaluate_idle_cash(
        _snapshot(5_000.0, [_position("AAPL", 95_000.0)], 100_000.0),
        _policy(),
        _MANDATE,
    )
    bounds = report["policy_bounds"]
    assert bounds["cash_above_reserve"] == "-5000"
    assert bounds["reserve_floor_breached"] is True
    # Over the exposure ceiling too, so there is no headroom -- but headroom
    # itself is floored, since negative headroom is not a meaningful amount.
    assert bounds["policy_headroom"] == "0"


def test_required_volatility_exposes_an_unreachable_mandate():
    """The bridge from cash to mandate. At 13% invested a 12% floor needs
    ~92% asset volatility, and even at the policy's own 50% ceiling it still
    needs 24% -- so the shortfall is structural, not just idle cash."""
    report = evaluate_idle_cash(
        _snapshot(87_000.0, [_position("AAPL", 13_000.0)], 100_000.0),
        _policy(),
        _MANDATE,
    )
    objective = report["mandate_objective"]
    assert objective["required_invested_volatility_pct"] == "92.31"
    assert objective["required_invested_volatility_at_policy_ceiling_pct"] == "24"
    assert "not a forecast" in objective["required_assumption"]


def test_unmeasured_volatility_is_absent_not_zero():
    """A defaulted 0.0 would read as 'far below mandate' and is
    indistinguishable from a genuinely flat portfolio."""
    report = evaluate_idle_cash(
        _snapshot(50_000.0, [_position("AAPL", 50_000.0)], 100_000.0),
        _policy(),
        _MANDATE,
    )
    measured = report["mandate_objective"]["measured"]
    assert measured["available"] is False
    assert measured["annualized_volatility_pct"] is None
    assert measured["within_mandate_band"] is None
    assert measured["unavailable_reason"]


@pytest.mark.parametrize(
    "observed,inside",
    [(11.9, False), (12.0, True), (15.0, True), (18.0, True), (18.1, False)],
)
def test_measured_volatility_band_boundaries_are_inclusive(observed, inside):
    report = evaluate_idle_cash(
        _snapshot(50_000.0, [_position("AAPL", 50_000.0)], 100_000.0),
        _policy(),
        _MANDATE,
        measured_annualized_volatility_pct=observed,
    )
    measured = report["mandate_objective"]["measured"]
    assert measured["available"] is True
    assert measured["within_mandate_band"] is inside


@pytest.mark.parametrize(
    "equity", [0.0, -1.0], ids=["zero_equity", "negative_equity"]
)
def test_non_positive_equity_refuses_instead_of_dividing(equity):
    """Percent-of-equity is undefined here. Returning 0% or infinity would
    be a confident wrong number in a report a human acts on."""
    with pytest.raises(CashReportError, match="positive"):
        evaluate_idle_cash(
            _snapshot(equity, [], equity), _policy(), _MANDATE
        )


@pytest.mark.parametrize(
    "bad", [float("nan"), float("inf")], ids=["nan", "inf"]
)
def test_non_finite_money_refuses(bad):
    with pytest.raises(CashReportError, match="not usable"):
        evaluate_idle_cash(
            _snapshot(bad, [_position("AAPL", 1_000.0)], 100_000.0),
            _policy(),
            _MANDATE,
        )


def test_fully_uninvested_portfolio_gives_no_required_figure():
    """Dividing by a near-zero invested fraction is arithmetically fine and
    rhetorically useless ('you need 4000% volatility'). Say it is
    unreachable and give no number."""
    report = evaluate_idle_cash(
        _snapshot(100_000.0, [], 100_000.0), _policy(), _MANDATE
    )
    objective = report["mandate_objective"]
    assert objective["required_invested_volatility_pct"] is None
    assert "too small" in objective["required_unavailable_reason"]
    assert report["totals"]["invested_pct"] == "0"


def test_exactness_of_the_underlying_numbers_is_disclosed():
    """A reader must be able to tell preserved broker decimals from
    display-rounded floats."""
    rounded = evaluate_idle_cash(
        _snapshot(50_000.0, [_position("AAPL", 50_000.0)], 100_000.0),
        _policy(),
        _MANDATE,
    )
    assert rounded["exact_numerics"] is False

    exact = evaluate_idle_cash(
        _snapshot(
            50_000.0,
            [
                _position(
                    "AAPL",
                    50_000.0,
                    shares_exact="10",
                    entry_price_exact="5000",
                    current_price_exact="5000",
                    market_value_exact="50000",
                )
            ],
            100_000.0,
            cash_exact="50000",
            total_equity_exact="100000",
        ),
        _policy(),
        _MANDATE,
    )
    assert exact["exact_numerics"] is True


def test_report_carries_no_action_shaped_field():
    """CLAUDE.md section 8 forbids action-shaped fields in presentation
    payloads. 'policy_headroom' describes room the policy leaves; a key
    named buy/sell/recommend/target_position would describe an instruction.
    """
    report = evaluate_idle_cash(
        _snapshot(87_000.0, [_position("AAPL", 13_000.0)], 100_000.0),
        _policy(),
        _MANDATE,
    )

    forbidden = ("buy", "sell", "order", "recommend", "suggest", "should", "trade")
    found: list[str] = []

    def walk(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                lowered = str(key).lower()
                if any(word in lowered for word in forbidden):
                    found.append(f"{path}.{key}")
                walk(value, f"{path}.{key}")
        elif isinstance(node, (list, tuple)):
            for index, item in enumerate(node):
                walk(item, f"{path}[{index}]")

    walk(report)
    assert not found, f"action-shaped keys in a reporting payload: {found}"
    assert any("does not create, size, rank, or approve" in d for d in report["disclaimers"])


def test_headroom_is_bounded_by_whichever_limit_binds_first():
    """When cash is the scarcer resource the report must say so, otherwise
    'headroom' would overstate what policy actually permits."""
    # Only 12k cash against a 10k floor => 2k above reserve, while the
    # exposure ceiling still leaves 38k of room.
    report = evaluate_idle_cash(
        _snapshot(12_000.0, [_position("AAPL", 12_000.0)], 100_000.0),
        _policy(),
        _MANDATE,
    )
    bounds = report["policy_bounds"]
    assert bounds["cash_above_reserve"] == "2000"
    assert bounds["unused_exposure_capacity"] == "38000"
    assert bounds["policy_headroom"] == "2000"
    assert bounds["binding_constraint"] == "cash_reserve_floor"


def test_idle_cash_cli_leaves_execution_and_evidence_tables_untouched(tmp_path, monkeypatch):
    """CLAUDE.md section 9 requires read-only commands to be proven read-only.

    `propose` deliberately saves a decision packet; this command deliberately
    does not, so a reporting run cannot pollute the evidence the epoch is
    accumulating.
    """
    from types import SimpleNamespace

    import scripts.run_personal_assistant as cli
    from assistant.storage import AssistantStore

    store = AssistantStore(tmp_path / "assistant.db")
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
    )

    def counts():
        with store._connect() as connection:
            return {
                name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                for name in tables
            }

    packet = SimpleNamespace(
        portfolio=_snapshot(
            87_000.0, [_position("AAPL", 13_000.0)], 100_000.0
        )
    )
    monkeypatch.setattr(cli, "_packet", lambda include_events=True, store=None: packet)

    before = counts()
    cli.command_idle_cash(
        SimpleNamespace(
            policy=None,
            mandate=str(DEFAULT_POLICY_PATH.parent / "default_mandate.json"),
            measured_volatility_pct=None,
            json=True,
        ),
        store=store,
    )
    assert counts() == before, "idle-cash must be strictly read-only"


def test_idle_cash_cli_refuses_a_broken_snapshot_instead_of_printing_zero(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import scripts.run_personal_assistant as cli
    from assistant.storage import AssistantStore

    store = AssistantStore(tmp_path / "assistant.db")
    packet = SimpleNamespace(portfolio=_snapshot(0.0, [], 0.0))
    monkeypatch.setattr(cli, "_packet", lambda include_events=True, store=None: packet)

    with pytest.raises(SystemExit, match="Cannot report idle cash"):
        cli.command_idle_cash(
            SimpleNamespace(
                policy=None,
                mandate=str(DEFAULT_POLICY_PATH.parent / "default_mandate.json"),
                measured_volatility_pct=None,
                json=True,
            ),
            store=store,
        )


def test_reports_page_renders_the_idle_cash_panel_without_exception():
    """UI surface: GR-7b must actually be visible to an owner who never
    opens a terminal. Rendering (not a button) is the point -- idle cash is
    a standing condition, so requiring a click would keep it invisible.
    """
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    app_path = Path(__file__).resolve().parents[1] / "scripts" / "personal_assistant_ui.py"
    app = AppTest.from_file(str(app_path), default_timeout=90)
    app.session_state["nav_page"] = "Reports"
    app.run()

    assert not app.exception
    # st.write text lands in the markdown collection; AppTest has no .write.
    rendered = " ".join(
        str(element.value)
        for element in list(app.markdown) + list(app.caption)
        if getattr(element, "value", None) is not None
    )
    # Assert on the panel's SUBSTANCE, not its expander label -- AppTest does
    # not surface expander titles in these collections.
    assert "room the policy leaves" in rendered, (
        "the headroom caption must render, and must keep its "
        "not-a-suggestion framing"
    )
    assert "Mandate volatility band" in rendered
    # The honesty caveat must travel with the number, not be dropped in the UI.
    assert "not a forecast" in rendered and "not a recommendation" in rendered
