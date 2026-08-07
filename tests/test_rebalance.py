"""GR-7d (report-only slice): drift measurement against an owner-chosen target.

The dangerous directions for a REPORT are not financial loss but a confident
wrong number a human acts on. So these tests pin, in order of severity:

(a) a holding with NO target is never silently dropped -- that row implies
    exiting the whole position and is the largest statement the report can
    make;
(b) broken or impossible inputs refuse rather than produce a figure;
(c) band boundaries are inclusive and decided on unrounded values;
(d) an undefined relative drift is reported absent, never as a number that
    could compare as "inside band"; and
(e) nothing in the payload is action-shaped (no shares, no side, no verb).
"""
from __future__ import annotations

from decimal import Decimal

import pytest

import config
from assistant.rebalance import (
    ROW_STATUSES,
    STATUS_HELD_NOT_IN_TARGET,
    STATUS_INSIDE_BAND,
    STATUS_OVERWEIGHT,
    STATUS_UNDERWEIGHT,
    RebalanceReportError,
    evaluate_rebalance_drift,
    target_weights_equal,
)
from assistant.schemas import PortfolioPosition, PortfolioSnapshot


def _position(ticker: str, market_value: float, **overrides) -> PortfolioPosition:
    kwargs = dict(
        ticker=ticker,
        shares=10.0,
        entry_price=market_value / 10 if market_value else 1.0,
        current_price=market_value / 10 if market_value else 1.0,
        market_value=market_value,
        unrealized_pnl_pct=0.0,
        is_leveraged_etf=False,
    )
    kwargs.update(overrides)
    return PortfolioPosition(**kwargs)


def _snapshot(positions, *, cash=0.0, equity=1000.0, **overrides) -> PortfolioSnapshot:
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


def _row(report, ticker):
    for row in report["rows"]:
        if row["ticker"] == ticker:
            return row
    raise AssertionError(f"{ticker} missing from report rows: {[r['ticker'] for r in report['rows']]}")


# --- (a) the held-but-untargeted row, the one that must never vanish ------


def test_holding_absent_from_target_still_produces_a_row():
    """The whole point of GR-7d honesty: an untargeted holding implies exit."""
    report = evaluate_rebalance_drift(
        _snapshot([_position("NVDL", 250.0)], equity=1000.0),
        {"AAPL": Decimal("50")},
        band_pct=25,
    )
    row = _row(report, "NVDL")
    assert row["status"] == STATUS_HELD_NOT_IN_TARGET
    assert row["in_target"] is False
    assert row["target_pct"] == "0"
    # The gap is the negative of the whole position: exiting it entirely.
    assert row["gap_value"] == "-250"
    assert report["counts"][STATUS_HELD_NOT_IN_TARGET] == 1


def test_untargeted_holding_is_never_classified_inside_band():
    """Fail-open check: a 0% target must not compare as compliant."""
    for market_value in (0.01, 1.0, 999.0):
        report = evaluate_rebalance_drift(
            _snapshot([_position("BBB", market_value)], equity=1000.0),
            {"AAPL": Decimal("50")},
            band_pct=1000,  # absurdly wide; still must not absorb this row
        )
        assert _row(report, "BBB")["status"] == STATUS_HELD_NOT_IN_TARGET


def test_explicit_zero_target_weight_while_held_is_not_inside_band():
    """A caller may legitimately target 0% for a name it wants out of.

    That row's relative drift is undefined exactly like an untargeted
    holding's, so it must not fall through to "inside band" -- the
    fail-open direction. Distinct from the untargeted case above because
    this ticker IS in the target mapping, so it takes a different branch.
    """
    report = evaluate_rebalance_drift(
        _snapshot([_position("AAPL", 100.0)], equity=1000.0),
        {"AAPL": Decimal("0"), "MSFT": Decimal("10")},
        band_pct=25,
    )
    row = _row(report, "AAPL")
    assert row["in_target"] is True
    assert row["drift_ratio_pct"] is None
    assert row["status"] == STATUS_OVERWEIGHT


def test_explicit_zero_target_weight_while_unheld_is_inside_band():
    """The mirror case: targeting 0% and holding nothing is compliant."""
    report = evaluate_rebalance_drift(
        _snapshot([], equity=1000.0),
        {"AAPL": Decimal("0"), "MSFT": Decimal("10")},
        band_pct=25,
    )
    row = _row(report, "AAPL")
    assert row["drift_ratio_pct"] is None
    assert row["status"] == STATUS_INSIDE_BAND


def test_untargeted_holding_reports_no_relative_drift_number():
    """Undefined ratio is reported absent, not as a sentinel that sorts wrong."""
    report = evaluate_rebalance_drift(
        _snapshot([_position("NVDL", 250.0)], equity=1000.0),
        {"AAPL": Decimal("50")},
        band_pct=25,
    )
    assert _row(report, "NVDL")["drift_ratio_pct"] is None


def test_real_configured_holdings_land_outside_a_universe_target():
    """Pins the documented conflict rather than letting it surprise someone.

    SOXL is deliberately traded by CONFIGURED_LEVERAGED_PAIRS, and NVDL/BBB
    were real holdings on 2026-08-06 -- none are in UNIVERSE, so a
    UNIVERSE-derived target implies exiting all of them.
    """
    targets = target_weights_equal(config.REBALANCE_TARGET_TICKERS, 50)
    for ticker in ("SOXL", "SOXX", "NVDL", "BBB"):
        assert ticker not in targets


# --- (b) refusals on impossible input -------------------------------------


@pytest.mark.parametrize("equity", [0.0, -1.0, -1000.0])
def test_non_positive_equity_refuses(equity):
    with pytest.raises(RebalanceReportError, match="non-positive equity|Total equity"):
        evaluate_rebalance_drift(
            _snapshot([], equity=equity), {"AAPL": Decimal("50")}, band_pct=25
        )


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_equity_refuses(bad):
    """NaN defeats ordinary comparisons, so it must be rejected explicitly."""
    with pytest.raises(RebalanceReportError):
        evaluate_rebalance_drift(
            _snapshot([], equity=bad), {"AAPL": Decimal("50")}, band_pct=25
        )


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_non_finite_position_value_refuses(bad):
    with pytest.raises(RebalanceReportError, match="unusable market value"):
        evaluate_rebalance_drift(
            _snapshot([_position("AAPL", bad)], equity=1000.0),
            {"AAPL": Decimal("50")},
            band_pct=25,
        )


def test_empty_target_refuses():
    with pytest.raises(RebalanceReportError, match="nothing to measure drift against"):
        evaluate_rebalance_drift(_snapshot([]), {}, band_pct=25)


def test_negative_target_weight_refuses():
    with pytest.raises(RebalanceReportError, match="negative"):
        evaluate_rebalance_drift(
            _snapshot([]), {"AAPL": Decimal("-5")}, band_pct=25
        )


def test_negative_band_refuses():
    with pytest.raises(RebalanceReportError, match="must not be negative"):
        evaluate_rebalance_drift(_snapshot([]), {"AAPL": Decimal("50")}, band_pct=-1)


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_non_finite_band_refuses(bad):
    with pytest.raises(RebalanceReportError, match="Invalid band_pct"):
        evaluate_rebalance_drift(_snapshot([]), {"AAPL": Decimal("50")}, band_pct=bad)


def test_blank_position_ticker_refuses():
    with pytest.raises(RebalanceReportError, match="blank ticker"):
        evaluate_rebalance_drift(
            _snapshot([_position("   ", 100.0)]), {"AAPL": Decimal("50")}, band_pct=25
        )


def test_duplicate_target_ticker_after_normalisation_refuses():
    """'aapl' and 'AAPL' would otherwise silently pick one weight."""
    with pytest.raises(RebalanceReportError, match="more than once"):
        evaluate_rebalance_drift(
            _snapshot([]),
            {"AAPL": Decimal("25"), "aapl": Decimal("50")},
            band_pct=25,
        )


# --- target_weights_equal ------------------------------------------------


def test_equal_weights_split_exposure_evenly():
    weights = target_weights_equal(["AAPL", "MSFT", "NVDA", "AMD"], 50)
    assert set(weights) == {"AAPL", "MSFT", "NVDA", "AMD"}
    assert all(w == Decimal("12.5") for w in weights.values())
    assert sum(weights.values()) == Decimal("50")


def test_equal_weights_deduplicate_rather_than_double_weighting():
    """A name listed twice must not receive twice the intended share."""
    weights = target_weights_equal(["AAPL", "aapl", " AAPL ", "MSFT"], 50)
    assert set(weights) == {"AAPL", "MSFT"}
    assert weights["AAPL"] == Decimal("25")


def test_equal_weights_over_the_full_target_list_sum_to_the_exposure():
    """50% across 104 names is a repeating decimal; pin the residual's size.

    Equal weights CANNOT sum exactly here (see target_weights_equal's
    docstring). What matters is that the residual stays financially
    meaningless rather than drifting into something a reader would notice.
    """
    weights = target_weights_equal(config.REBALANCE_TARGET_TICKERS, 50)
    assert len(weights) == len(set(config.REBALANCE_TARGET_TICKERS))
    residual = abs(sum(weights.values()) - Decimal("50"))
    assert residual < Decimal("1e-20"), f"residual grew to {residual}"


def test_equal_weights_are_genuinely_equal_not_remainder_adjusted():
    """The residual must not be papered over by making one name heavier."""
    weights = target_weights_equal(config.REBALANCE_TARGET_TICKERS, 50)
    assert len(set(weights.values())) == 1


@pytest.mark.parametrize("bad", [0, -1, 101, float("nan")])
def test_equal_weights_rejects_impossible_exposure(bad):
    with pytest.raises(RebalanceReportError):
        target_weights_equal(["AAPL"], bad)


def test_equal_weights_rejects_empty_list():
    with pytest.raises(RebalanceReportError, match="target portfolio of nothing"):
        target_weights_equal([], 50)


def test_equal_weights_rejects_blank_ticker():
    with pytest.raises(RebalanceReportError, match="blank ticker"):
        target_weights_equal(["AAPL", "  "], 50)


# --- (c) band boundaries, inclusive, decided on unrounded values ----------


def test_exactly_at_the_band_edge_is_inside_the_band():
    """Inclusive boundary, matching the project's cap convention."""
    # target 10% of 1000 = 100; +25% drift = 125 exactly.
    report = evaluate_rebalance_drift(
        _snapshot([_position("AAPL", 125.0)], equity=1000.0),
        {"AAPL": Decimal("10")},
        band_pct=25,
    )
    row = _row(report, "AAPL")
    assert row["drift_ratio_pct"] == "25"
    assert row["status"] == STATUS_INSIDE_BAND


def test_just_beyond_the_band_edge_is_outside():
    report = evaluate_rebalance_drift(
        _snapshot([_position("AAPL", 125.01)], equity=1000.0),
        {"AAPL": Decimal("10")},
        band_pct=25,
    )
    assert _row(report, "AAPL")["status"] == STATUS_OVERWEIGHT


def test_lower_band_edge_is_inclusive_too():
    report = evaluate_rebalance_drift(
        _snapshot([_position("AAPL", 75.0)], equity=1000.0),
        {"AAPL": Decimal("10")},
        band_pct=25,
    )
    assert _row(report, "AAPL")["drift_ratio_pct"] == "-25"
    assert _row(report, "AAPL")["status"] == STATUS_INSIDE_BAND


def test_status_is_decided_before_presentation_rounding():
    """A drift that rounds to the edge but exceeds it must read as drifted.

    target 10% of 1000 = 100. A value of 125.000001 gives 25.0000001% drift,
    which quantises to '25' for display but is genuinely outside a 25% band.
    Classifying on the rounded string would fail open.
    """
    report = evaluate_rebalance_drift(
        _snapshot([_position("AAPL", 125.000001)], equity=1000.0),
        {"AAPL": Decimal("10")},
        band_pct=25,
    )
    row = _row(report, "AAPL")
    assert row["drift_ratio_pct"] == "25"  # display-rounded
    assert row["status"] == STATUS_OVERWEIGHT  # but classified on the real value


def test_underweight_and_overweight_directions():
    report = evaluate_rebalance_drift(
        _snapshot(
            [_position("AAPL", 200.0), _position("MSFT", 50.0)], equity=1000.0
        ),
        {"AAPL": Decimal("10"), "MSFT": Decimal("10")},
        band_pct=25,
    )
    assert _row(report, "AAPL")["status"] == STATUS_OVERWEIGHT
    assert _row(report, "MSFT")["status"] == STATUS_UNDERWEIGHT


def test_targeted_but_unheld_ticker_is_fully_underweight():
    report = evaluate_rebalance_drift(
        _snapshot([], equity=1000.0), {"AAPL": Decimal("10")}, band_pct=25
    )
    row = _row(report, "AAPL")
    assert row["status"] == STATUS_UNDERWEIGHT
    assert row["held"] is False
    assert row["current_value"] == "0"
    assert row["drift_ratio_pct"] == "-100"


# --- correctness of the arithmetic ---------------------------------------


def test_duplicate_position_rows_for_one_ticker_are_summed():
    """Taking only one row would make an overweight holding look compliant."""
    report = evaluate_rebalance_drift(
        _snapshot(
            [_position("AAPL", 100.0), _position("AAPL", 100.0)], equity=1000.0
        ),
        {"AAPL": Decimal("10")},
        band_pct=25,
    )
    row = _row(report, "AAPL")
    assert row["current_value"] == "200"
    assert row["status"] == STATUS_OVERWEIGHT


def test_position_ticker_case_is_normalised_against_the_target():
    report = evaluate_rebalance_drift(
        _snapshot([_position("aapl", 100.0)], equity=1000.0),
        {"AAPL": Decimal("10")},
        band_pct=25,
    )
    row = _row(report, "AAPL")
    assert row["in_target"] is True
    assert row["status"] == STATUS_INSIDE_BAND
    assert report["counts"][STATUS_HELD_NOT_IN_TARGET] == 0


def test_exact_broker_decimals_are_preferred_over_rounded_floats():
    """Money must come from the preserved decimal text when present."""
    position = _position("AAPL", 100.0, market_value_exact="100.004999")
    report = evaluate_rebalance_drift(
        _snapshot([position], equity=1000.0), {"AAPL": Decimal("10")}, band_pct=25
    )
    # 100.004999 quantises to 100.00, proving the exact text drove the math
    # rather than the rounded float being re-derived.
    assert _row(report, "AAPL")["current_value"] == "100"
    assert _row(report, "AAPL")["drift_ratio_pct"] == "0.005"


def test_exact_numerics_flag_reports_provenance():
    report = evaluate_rebalance_drift(
        _snapshot([_position("AAPL", 100.0)], equity=1000.0),
        {"AAPL": Decimal("10")},
        band_pct=25,
    )
    assert report["exact_numerics"] is False


def test_totals_and_counts_are_consistent_with_rows():
    report = evaluate_rebalance_drift(
        _snapshot(
            [_position("AAPL", 100.0), _position("NVDL", 300.0)],
            cash=600.0,
            equity=1000.0,
        ),
        {"AAPL": Decimal("10"), "MSFT": Decimal("10")},
        band_pct=25,
    )
    assert report["totals"]["invested"] == "400"
    assert report["totals"]["invested_pct"] == "40"
    assert report["totals"]["cash"] == "600"
    assert report["totals"]["target_invested_pct"] == "20"
    assert report["totals"]["target_ticker_count"] == 2
    assert sum(report["counts"].values()) == len(report["rows"])
    assert set(report["counts"]) == set(ROW_STATUSES)


def test_rows_are_deterministically_ordered():
    report = evaluate_rebalance_drift(
        _snapshot([_position("ZZZ", 10.0), _position("AAA", 10.0)], equity=1000.0),
        {"MMM": Decimal("10")},
        band_pct=25,
    )
    tickers = [row["ticker"] for row in report["rows"]]
    assert tickers == sorted(tickers)


# --- (e) nothing action-shaped -------------------------------------------


def test_payload_contains_no_action_shaped_field():
    """A report must not look like an order. No side, no shares, no verb."""
    report = evaluate_rebalance_drift(
        _snapshot([_position("AAPL", 200.0), _position("NVDL", 50.0)], equity=1000.0),
        {"AAPL": Decimal("10")},
        band_pct=25,
    )
    forbidden = {
        "side", "shares", "qty", "quantity", "order_type", "limit_price",
        "action", "buy", "sell", "trade", "proposal_id", "intent",
        "shares_to_buy", "shares_to_sell", "recommended",
    }
    for row in report["rows"]:
        assert not (forbidden & set(row)), f"action-shaped field in row: {row}"
    assert not (forbidden & set(report))
    assert not (forbidden & set(report["totals"]))


def test_report_is_pure_and_does_not_mutate_the_snapshot():
    positions = [_position("AAPL", 200.0)]
    snapshot = _snapshot(positions, cash=800.0, equity=1000.0)
    before = (
        [(p.ticker, p.market_value) for p in snapshot.positions],
        snapshot.cash,
        snapshot.total_equity,
    )
    evaluate_rebalance_drift(snapshot, {"AAPL": Decimal("10")}, band_pct=25)
    after = (
        [(p.ticker, p.market_value) for p in snapshot.positions],
        snapshot.cash,
        snapshot.total_equity,
    )
    assert before == after


def test_report_is_json_serialisable():
    import json

    report = evaluate_rebalance_drift(
        _snapshot([_position("AAPL", 200.0), _position("NVDL", 50.0)], equity=1000.0),
        {"AAPL": Decimal("10")},
        band_pct=25,
    )
    # Decimal is not JSON-serialisable; every emitted number must already be
    # a string, so this round-trip is a real guard rather than a formality.
    assert json.loads(json.dumps(report, sort_keys=True))["rows"]


# --- the pinning test the config comment promises -------------------------


def test_rebalance_target_set_is_pinned_against_silent_universe_growth():
    """A research edit to UNIVERSE must not quietly enlarge the target set.

    If this fails, UNIVERSE changed. That is not automatically wrong -- but
    it means the owner's target PORTFOLIO changed as a side effect of a
    research decision. Update the expected count deliberately, having
    decided that the new ticker belongs in the target allocation.
    """
    assert len(config.REBALANCE_TARGET_TICKERS) == 104
    assert len(set(config.REBALANCE_TARGET_TICKERS)) == 104
    assert list(config.REBALANCE_TARGET_TICKERS) == list(config.UNIVERSE)


def test_rebalance_band_is_the_wide_owner_chosen_band():
    assert config.REBALANCE_BAND_PCT == 25.0


# --- CLI surface ----------------------------------------------------------


def _cli_args(**overrides):
    from types import SimpleNamespace

    kwargs = dict(
        policy=None,
        band_pct=25.0,
        target_exposure_pct=None,
        limit=20,
        json=True,
    )
    kwargs.update(overrides)
    return SimpleNamespace(**kwargs)


def test_rebalance_report_cli_is_strictly_read_only(tmp_path, monkeypatch, capsys):
    """The defect this guards has now appeared twice on reporting surfaces.

    GR-7a's tax Build and GR-7b's cash panel both wrote GR-4 provider-fetch
    evidence from a page that claimed to be read-only. A reporting command
    must leave every table untouched, evidence tables included.
    """
    import scripts.run_personal_assistant as cli
    from assistant.storage import AssistantStore

    store = AssistantStore(tmp_path / "assistant.db")
    tables = (
        "trade_proposals",
        "decision_packets",
        "data_provider_fetches",
        "paper_account_observations",
        "paper_evidence_epochs",
        "journal_transactions",
        "execution_reservations",
    )

    def counts():
        with store._connect() as connection:
            return {
                name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                for name in tables
            }

    monkeypatch.setattr(cli, "is_configured", lambda: False)
    monkeypatch.setattr(
        cli,
        "build_portfolio_snapshot",
        lambda *a, **k: _snapshot([_position("AAPL", 13_000.0)], cash=87_000.0, equity=100_000.0),
    )

    before = counts()
    cli.command_rebalance_report(_cli_args(), store=store)
    capsys.readouterr()
    assert counts() == before, "rebalance-report must be strictly read-only"


def test_rebalance_report_cli_never_calls_the_evidence_writing_packet_path():
    """Source-level guard: _packet(store=...) records provider-fetch rows."""
    import inspect

    import scripts.run_personal_assistant as cli

    source = inspect.getsource(cli.command_rebalance_report)
    body = source.split('"""', 2)[-1]  # drop the docstring, which names it
    assert "_packet(" not in body
    assert "store=store" not in body


def test_rebalance_report_cli_refuses_a_broken_snapshot(tmp_path, monkeypatch):
    import scripts.run_personal_assistant as cli
    from assistant.storage import AssistantStore

    store = AssistantStore(tmp_path / "assistant.db")
    monkeypatch.setattr(cli, "is_configured", lambda: False)
    monkeypatch.setattr(
        cli, "build_portfolio_snapshot", lambda *a, **k: _snapshot([], equity=0.0)
    )
    with pytest.raises(SystemExit, match="Cannot report rebalance drift"):
        cli.command_rebalance_report(_cli_args(), store=store)


def test_rebalance_report_cli_degrades_on_broker_outage(tmp_path, monkeypatch):
    """A scheduled run during an Alpaca incident must not dump a traceback."""
    import scripts.run_personal_assistant as cli
    from assistant.storage import AssistantStore

    store = AssistantStore(tmp_path / "assistant.db")
    monkeypatch.setattr(cli, "is_configured", lambda: True)

    def boom():
        raise RuntimeError("alpaca is down")

    monkeypatch.setattr(cli, "build_portfolio_snapshot_from_alpaca", boom)
    with pytest.raises(SystemExit, match="portfolio snapshot unavailable"):
        cli.command_rebalance_report(_cli_args(), store=store)


def test_rebalance_report_cli_surfaces_untargeted_holdings_prominently(
    tmp_path, monkeypatch, capsys
):
    """The largest statement the report makes must not be buried."""
    import scripts.run_personal_assistant as cli
    from assistant.storage import AssistantStore

    store = AssistantStore(tmp_path / "assistant.db")
    monkeypatch.setattr(cli, "is_configured", lambda: False)
    monkeypatch.setattr(
        cli,
        "build_portfolio_snapshot",
        lambda *a, **k: _snapshot(
            [_position("SOXL", 5_000.0), _position("AAPL", 500.0)],
            cash=94_500.0,
            equity=100_000.0,
        ),
    )
    cli.command_rebalance_report(_cli_args(json=False), store=store)
    out = capsys.readouterr().out
    assert "HELD BUT NOT IN THE TARGET SET" in out
    assert "SOXL" in out
    assert "no order was created, sized, or approved" in out


def test_rebalance_report_cli_emits_serialisable_json(tmp_path, monkeypatch, capsys):
    import json as json_module

    import scripts.run_personal_assistant as cli
    from assistant.storage import AssistantStore

    store = AssistantStore(tmp_path / "assistant.db")
    monkeypatch.setattr(cli, "is_configured", lambda: False)
    monkeypatch.setattr(
        cli,
        "build_portfolio_snapshot",
        lambda *a, **k: _snapshot([_position("AAPL", 500.0)], cash=99_500.0, equity=100_000.0),
    )
    cli.command_rebalance_report(_cli_args(json=True), store=store)
    payload = json_module.loads(capsys.readouterr().out)
    assert payload["totals"]["target_ticker_count"] == len(config.REBALANCE_TARGET_TICKERS)
    assert payload["band_pct"] == "25"
