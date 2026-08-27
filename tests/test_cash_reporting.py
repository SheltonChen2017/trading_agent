"""GR-7b: idle-cash reporting against policy bounds and the mandate.

The dangerous directions for a REPORT are different from those for an
execution path: it cannot lose money directly, but a number a reader trusts
is acted on by a human. So these tests pin (a) that broken inputs refuse
rather than produce a confident figure, (b) that an unmeasured quantity is
reported absent rather than defaulted, and (c) that nothing in the payload
is action-shaped.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime
from decimal import Decimal

import pytest

from assistant.cash_reporting import CashReportError, evaluate_idle_cash
from assistant.mandate import PortfolioMandate
from assistant.policy import load_policy, DEFAULT_POLICY_PATH
from assistant.schemas import PortfolioPosition, PortfolioSnapshot
from risk.execution_gate import TradeIntent, validate_trade_intent

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
    "bad", [float("nan"), float("inf"), -0.1], ids=["nan", "inf", "negative"]
)
def test_unusable_measured_volatility_refuses_as_cash_report_error(bad):
    """Callers only catch CashReportError. A raw ValueError from to_decimal
    on --measured-volatility-pct would traceback through the CLI/UI."""
    with pytest.raises(CashReportError):
        evaluate_idle_cash(
            _snapshot(50_000.0, [_position("AAPL", 50_000.0)], 100_000.0),
            _policy(),
            _MANDATE,
            measured_annualized_volatility_pct=bad,
        )


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
    # Only 12k cash against a 10k floor => 2k above reserve. Use a snapshot
    # whose cash plus positions equals equity; the execution gate derives
    # filled exposure as equity-cash and must not be tested against an
    # internally contradictory account shape.
    report = evaluate_idle_cash(
        _snapshot(12_000.0, [_position("AAPL", 88_000.0)], 100_000.0),
        _policy(max_total_exposure_pct=1.0),
        _MANDATE,
    )
    bounds = report["policy_bounds"]
    assert bounds["cash_above_reserve"] == "2000"
    assert bounds["unused_exposure_capacity"] == "12000"
    assert bounds["policy_headroom"] == "2000"
    assert bounds["binding_constraint"] == "cash_reserve_floor"


def test_idle_cash_cli_leaves_execution_and_evidence_tables_untouched(tmp_path, monkeypatch):
    """CLAUDE.md section 9 requires read-only commands to be proven read-only.

    Includes GR-4 provider-fetch evidence: the submitted implementation called
    `_packet(..., store=store)`, which records data_provider_fetches and would
    have passed a test that only mocked `_packet` away.
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
        "data_provider_fetches",
    )

    def counts():
        with store._connect() as connection:
            return {
                name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                for name in tables
            }

    portfolio = _snapshot(87_000.0, [_position("AAPL", 13_000.0)], 100_000.0)
    monkeypatch.setattr(cli, "is_configured", lambda: False)
    monkeypatch.setattr(
        cli,
        "build_portfolio_snapshot",
        lambda *args, **kwargs: portfolio,
    )

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
    monkeypatch.setattr(cli, "is_configured", lambda: False)
    monkeypatch.setattr(
        cli,
        "build_portfolio_snapshot",
        lambda *args, **kwargs: _snapshot(0.0, [], 0.0),
    )

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


def test_idle_cash_cli_refuses_nan_measured_volatility_without_traceback(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    import scripts.run_personal_assistant as cli
    from assistant.storage import AssistantStore

    store = AssistantStore(tmp_path / "assistant.db")
    monkeypatch.setattr(cli, "is_configured", lambda: False)
    monkeypatch.setattr(
        cli,
        "build_portfolio_snapshot",
        lambda *args, **kwargs: _snapshot(
            50_000.0, [_position("AAPL", 50_000.0)], 100_000.0
        ),
    )

    with pytest.raises(SystemExit, match="Cannot report idle cash"):
        cli.command_idle_cash(
            SimpleNamespace(
                policy=None,
                mandate=str(DEFAULT_POLICY_PATH.parent / "default_mandate.json"),
                measured_volatility_pct=float("nan"),
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


def test_reports_idle_cash_panel_does_not_write_provider_fetch_rows(tmp_path, monkeypatch):
    """Reports claims read-only; using _load_packet would record GR-4 fetches."""
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    import scripts.personal_assistant_ui as ui
    from assistant.storage import AssistantStore

    store = AssistantStore(tmp_path / "assistant.db")
    monkeypatch.setattr(ui, "_store", lambda: store)
    monkeypatch.setattr(ui, "is_configured", lambda: False)

    def counts():
        with store._connect() as connection:
            return connection.execute(
                "SELECT COUNT(*) FROM data_provider_fetches"
            ).fetchone()[0]

    before = counts()
    app_path = Path(__file__).resolve().parents[1] / "scripts" / "personal_assistant_ui.py"
    app = AppTest.from_file(str(app_path), default_timeout=90)
    app.session_state["nav_page"] = "Reports"
    app.run()
    assert not app.exception
    assert counts() == before

def test_idle_cash_cli_degrades_when_the_broker_snapshot_fails(monkeypatch):
    """Counter-review of GR7BREV-001's fix. Closing the provider-fetch write
    left `build_portfolio_snapshot_from_alpaca()` outside every guard, so a
    broker outage on a CONFIGURED account ended in a traceback rather than a
    refusal -- while the UI sibling of this panel was given exactly that
    guard. GR-7a already set the rule: an outage must degrade the report,
    not break it.
    """
    from types import SimpleNamespace

    import scripts.run_personal_assistant as cli

    def _outage():
        raise RuntimeError("alpaca: 503 service unavailable")

    monkeypatch.setattr(cli, "is_configured", lambda: True)
    monkeypatch.setattr(cli, "build_portfolio_snapshot_from_alpaca", _outage)

    with pytest.raises(SystemExit, match="portfolio snapshot unavailable"):
        cli.command_idle_cash(
            SimpleNamespace(
                policy=None,
                mandate=str(DEFAULT_POLICY_PATH.parent / "default_mandate.json"),
                measured_volatility_pct=None,
                json=True,
            ),
            store=None,
        )


def test_readonly_portfolio_loader_is_cached_and_takes_no_store():
    """Counter-review of GR7BREV-002's fix. Dropping `_load_packet` removed
    the write (correct) but also removed the shared cache, reintroducing a
    live broker call on every rerun of the Reports page and allowing that
    page to disagree with Briefing about the same account in the same
    session -- the invariant `_load_base_packet` exists to protect.

    Source-level: 'is decorated with st.cache_data' and 'never passes a
    store' are structural properties no single call can observe.
    """
    import ast
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1] / "scripts" / "personal_assistant_ui.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    loader = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "_load_readonly_portfolio"
        ),
        None,
    )
    assert loader is not None, "the read-only portfolio loader must exist"

    decorators = [ast.unparse(d) for d in loader.decorator_list]
    assert any("cache_data" in d for d in decorators), (
        f"read-only portfolio loader must be cached, got {decorators}"
    )
    # A store anywhere in the EXECUTABLE body would put the provider-fetch
    # write back. The docstring is excluded deliberately: it explains the
    # `store=_store()` call this loader exists to avoid, and matching on it
    # would make the test fail for describing the bug it guards.
    statements = [
        node
        for node in loader.body
        if not (
            isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
        )
    ]
    body = "\n".join(ast.unparse(node) for node in statements)
    assert "_store()" not in body and "store=" not in body, (
        f"the read-only loader must never reach a store; body was:\n{body}"
    )


def test_idle_cash_panel_uses_the_cached_readonly_loader():
    """Pins the wiring, not just the helper: a future edit that inlines a
    bare build_portfolio_snapshot_from_alpaca() call back into the panel
    would restore the per-rerun fetch without failing anything else."""
    import re
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1] / "scripts" / "personal_assistant_ui.py"
    ).read_text(encoding="utf-8")
    panel = re.search(
        r"# GR-7b\. Renders on load.*?(?=^# -{20,})", source, re.DOTALL | re.MULTILINE
    )
    assert panel is not None, "could not locate the GR-7b panel"
    body = panel.group(0)
    assert "_load_readonly_portfolio()" in body
    assert "build_portfolio_snapshot_from_alpaca(" not in body, (
        "the panel must go through the cached read-only loader"
    )
    assert "_load_packet(" not in body, "the panel must not use the writing loader"


# --------------------------------------------------------------------------
# FCS-004: headroom must net out capital already committed to working orders.
#
# risk/execution_gate.py folds pending buys into BOTH bounds -- the cash check
# via min(cash, buying_power), the exposure check via total_pending_buy_value.
# This report used raw cash and raw market value, so it advertised room the
# gate would refuse. Third recurrence of the class already fixed in
# allocation_proposals.build_allocation_plan and
# portfolio_analytics.preview_trade_impact.
# --------------------------------------------------------------------------

def _snapshot_with_open_orders(cash, positions, equity, open_orders):
    snapshot = _snapshot(cash, positions, equity)
    return dataclasses.replace(snapshot, open_orders=list(open_orders))


def test_headroom_nets_out_capital_already_committed_to_working_orders():
    working = [
        {"ticker": "MSFT", "side": "buy", "shares": 10, "limit_price": 400.0},
    ]  # $4,000 already spoken for
    without = evaluate_idle_cash(
        _snapshot(87_000.0, [_position("AAPL", 13_000.0)], 100_000.0),
        _policy(), _MANDATE,
    )["policy_bounds"]
    with_orders = evaluate_idle_cash(
        _snapshot_with_open_orders(
            87_000.0, [_position("AAPL", 13_000.0)], 100_000.0, working
        ),
        _policy(), _MANDATE,
    )["policy_bounds"]

    assert with_orders["capital_already_committed"] == "4000"
    assert Decimal(with_orders["policy_headroom"]) == (
        Decimal(without["policy_headroom"]) - Decimal("4000")
    )
    assert with_orders["policy_headroom_basis"] == "execution_gate_equivalent"
    assert with_orders["committed_capital_complete"] is True


def test_buying_power_is_the_cash_bound_used_by_the_execution_gate():
    snapshot = dataclasses.replace(
        _snapshot(9_000.0, [_position("AAPL", 1_000.0)], 10_000.0),
        buying_power=1_000.0,
    )

    bounds = evaluate_idle_cash(snapshot, _policy(), _MANDATE)["policy_bounds"]

    assert bounds["available_capital_at_gate"] == "1000"
    assert bounds["cash_above_reserve_at_gate"] == "0"
    assert bounds["policy_headroom"] == "0"
    assert bounds["binding_constraint"] == "cash_reserve_floor"


def test_unavailable_open_orders_make_exact_policy_headroom_unavailable():
    snapshot = dataclasses.replace(
        _snapshot(9_000.0, [_position("AAPL", 1_000.0)], 10_000.0),
        open_orders=[],
        open_orders_available=False,
    )

    bounds = evaluate_idle_cash(snapshot, _policy(), _MANDATE)["policy_bounds"]

    assert bounds["committed_capital_complete"] is False
    assert bounds["policy_headroom"] is None
    assert bounds["binding_constraint"] is None
    assert "unavailable" in bounds["policy_headroom_unavailable_reason"]


def test_partial_fill_counts_only_the_unfilled_limit_order_remainder():
    working = [{
        "ticker": "MSFT",
        "side": "buy",
        "shares": 10,
        "filled_qty": 4,
        "limit_price": 400.0,
    }]

    bounds = evaluate_idle_cash(
        _snapshot_with_open_orders(
            87_000.0, [_position("AAPL", 13_000.0)], 100_000.0, working
        ),
        _policy(),
        _MANDATE,
    )["policy_bounds"]

    assert bounds["capital_already_committed"] == "2400"
    assert bounds["committed_capital_complete"] is True


def test_negative_pending_notional_cannot_increase_reported_headroom():
    malformed = [{
        "ticker": "MSFT",
        "side": "buy",
        "notional": -4_000.0,
    }]

    bounds = evaluate_idle_cash(
        _snapshot_with_open_orders(
            87_000.0, [_position("AAPL", 13_000.0)], 100_000.0, malformed
        ),
        _policy(),
        _MANDATE,
    )["policy_bounds"]

    assert bounds["capital_already_committed"] == "0"
    assert bounds["committed_capital_complete"] is False
    assert bounds["capital_already_committed_unknown_tickers"] == ("MSFT",)
    assert bounds["policy_headroom"] is None


def test_reported_headroom_matches_execution_gate_boundary():
    working = [{"ticker": "MSFT", "side": "buy", "notional": 1_000.0}]
    snapshot = dataclasses.replace(
        _snapshot_with_open_orders(
            7_000.0, [_position("AAPL", 3_000.0)], 10_000.0, working
        ),
        buying_power=6_000.0,
    )
    policy = _policy(max_position_pct=0.50)
    bounds = evaluate_idle_cash(snapshot, policy, _MANDATE)["policy_bounds"]
    assert bounds["policy_headroom"] == "1000"

    at_limit = validate_trade_intent(
        TradeIntent(ticker="KO", side="buy", shares=1_000),
        snapshot,
        reference_price=1.0,
        now=datetime(2026, 8, 3, 10, 0),  # Monday during market hours
        max_position_pct=policy.max_position_pct,
        max_total_exposure_pct=policy.max_total_exposure_pct,
        min_cash_reserve_pct=policy.min_cash_reserve_pct,
        pending_buy_value_by_ticker={"MSFT": 1_000.0},
    )
    over_limit = validate_trade_intent(
        TradeIntent(ticker="KO", side="buy", shares=1_001),
        snapshot,
        reference_price=1.0,
        now=datetime(2026, 8, 3, 10, 0),
        max_position_pct=policy.max_position_pct,
        max_total_exposure_pct=policy.max_total_exposure_pct,
        min_cash_reserve_pct=policy.min_cash_reserve_pct,
        pending_buy_value_by_ticker={"MSFT": 1_000.0},
    )

    assert at_limit.approved is True
    assert over_limit.approved is False
    assert any("total-exposure limit" in text for text in over_limit.violations)


def test_a_commitment_of_unknowable_value_is_disclosed_not_counted_as_zero():
    """A bare market order carries no notional and no limit price.

    Counting it as zero would silently overstate headroom -- the same
    fail-open the estimator was written to avoid for the UI preview.
    """
    working = [{"ticker": "MSFT", "side": "buy", "shares": 10}]
    bounds = evaluate_idle_cash(
        _snapshot_with_open_orders(
            87_000.0, [_position("AAPL", 13_000.0)], 100_000.0, working
        ),
        _policy(), _MANDATE,
    )["policy_bounds"]
    assert bounds["committed_capital_complete"] is False
    assert bounds["capital_already_committed_unknown_tickers"] == ("MSFT",)


def test_sell_orders_do_not_reduce_headroom():
    """Only BUYs consume deployable room; a pending sell releases it."""
    working = [{"ticker": "AAPL", "side": "sell", "shares": 10, "limit_price": 400.0}]
    bounds = evaluate_idle_cash(
        _snapshot_with_open_orders(
            87_000.0, [_position("AAPL", 13_000.0)], 100_000.0, working
        ),
        _policy(), _MANDATE,
    )["policy_bounds"]
    assert bounds["capital_already_committed"] == "0"
