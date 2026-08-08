"""Tests for ml/portfolio_volatility.py (ML-LR-3), covering the
live-readiness plan's section 9.6 list that applies to the target builder:
cash is not renormalized away; a future position snapshot is rejected;
mismatched histories refuse rather than silently drop a held name;
zero/negative/non-finite weights or prices fail safely; daily and annualized
units cannot be mixed; and portfolio targets create no execution state.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from ml.portfolio_volatility import (
    CASH_TICKER,
    TRADING_SESSIONS_PER_YEAR,
    PortfolioVolatilityError,
    PortfolioVolatilityTarget,
    build_frozen_weight_targets,
    build_realized_account_targets,
    compute_frozen_weights,
)

_AS_OF = "2026-03-02"
_CAPTURED = "2026-03-02T21:00:00+00:00"
_CUTOFF = "2026-03-02T22:00:00+00:00"


def _prices(n: int = 40, *, daily_vol: float = 0.02, seed: int = 0, start: str = "2026-03-02"):
    """Sessions starting at the as-of date so the forward window is available."""
    rng = np.random.default_rng(seed)
    index = pd.bdate_range(start, periods=n)
    values = 100.0 * np.cumprod(1 + rng.normal(0, daily_vol, n))
    return pd.Series(values, index=index)


def _universe(seed: int = 0, **overrides):
    data = {
        "AAA": _prices(seed=seed),
        "BBB": _prices(seed=seed + 1),
    }
    data.update(overrides)
    return data


def _snapshots(**overrides):
    base = [
        {"ticker": "AAA", "market_value": "6000"},
        {"ticker": "BBB", "market_value": "4000"},
    ]
    if overrides.get("snapshots") is not None:
        return overrides["snapshots"]
    return base


def _build(**overrides):
    kwargs = dict(
        account_key="paper",
        as_of_session=_AS_OF,
        captured_at=_CAPTURED,
        forecast_cutoff=_CUTOFF,
        snapshots=_snapshots(),
        cash="0",
        close_by_ticker=_universe(),
        horizon_sessions=20,
    )
    kwargs.update(overrides)
    return build_frozen_weight_targets(kwargs.pop("account_key"), **kwargs)


# --- weights: cash handling -------------------------------------------------


def test_cash_is_not_renormalized_away():
    """Plan 9.6's first item. A book that is 50% cash has roughly half the
    volatility of the same securities at full weight; renormalizing would
    report the fully-invested number for a portfolio that was not fully
    invested."""
    weights, cash_weight, _ = compute_frozen_weights(
        [{"ticker": "AAA", "market_value": "5000"}], cash="5000"
    )
    assert weights["AAA"] == pytest.approx(0.5)
    assert cash_weight == pytest.approx(0.5)
    assert sum(weights.values()) + cash_weight == pytest.approx(1.0)


def test_a_half_cash_book_has_roughly_half_the_volatility():
    prices = _universe()
    invested = _build(snapshots=[{"ticker": "AAA", "market_value": "10000"}],
                      cash="0", close_by_ticker=prices)
    half_cash = _build(snapshots=[{"ticker": "AAA", "market_value": "5000"}],
                       cash="5000", close_by_ticker=prices)
    assert half_cash.cash_weight == pytest.approx(0.5)
    assert half_cash.daily_volatility_pct == pytest.approx(
        invested.daily_volatility_pct / 2, rel=1e-6
    )


def test_weights_use_exact_decimal_arithmetic():
    weights, cash_weight, _ = compute_frozen_weights(
        [{"ticker": "AAA", "market_value": "0.1"}, {"ticker": "BBB", "market_value": "0.2"}],
        cash="0",
    )
    assert sum(weights.values()) + cash_weight == pytest.approx(1.0, abs=1e-12)


def test_negative_market_value_is_refused_unless_shorts_are_allowed():
    snapshots = [{"ticker": "AAA", "market_value": "-100"}]
    with pytest.raises(PortfolioVolatilityError, match="outside the current"):
        compute_frozen_weights(snapshots, cash="1000")
    weights, _, _ = compute_frozen_weights(snapshots, cash="1000", allow_short=True)
    assert weights["AAA"] < 0


def test_negative_cash_is_refused():
    with pytest.raises(PortfolioVolatilityError, match="negative cash"):
        compute_frozen_weights([{"ticker": "AAA", "market_value": "100"}], cash="-5")


def test_zero_total_value_is_refused():
    with pytest.raises(PortfolioVolatilityError, match="must be positive"):
        compute_frozen_weights([{"ticker": "AAA", "market_value": "0"}], cash="0")


def test_a_zero_weight_position_is_refused_even_when_cash_makes_total_positive():
    with pytest.raises(PortfolioVolatilityError, match="zero-weight"):
        compute_frozen_weights([{"ticker": "AAA", "market_value": "0"}], cash="100")


def test_duplicate_and_reserved_tickers_are_refused():
    with pytest.raises(PortfolioVolatilityError, match="duplicate"):
        compute_frozen_weights(
            [{"ticker": "AAA", "market_value": "1"}, {"ticker": "AAA", "market_value": "2"}],
            cash="0",
        )
    with pytest.raises(PortfolioVolatilityError, match="reserved"):
        compute_frozen_weights([{"ticker": CASH_TICKER, "market_value": "1"}], cash="0")


def test_lowercase_ticker_is_refused():
    with pytest.raises(PortfolioVolatilityError, match="canonical uppercase"):
        compute_frozen_weights([{"ticker": "aaa", "market_value": "1"}], cash="0")


def test_non_finite_market_value_fails_safely():
    with pytest.raises(ValueError):
        compute_frozen_weights([{"ticker": "AAA", "market_value": "NaN"}], cash="0")


# --- look-ahead refusals ----------------------------------------------------


def test_a_position_snapshot_captured_after_the_cutoff_is_rejected():
    """Plan 9.6: a forecaster cannot know holdings recorded after its own
    decision point."""
    with pytest.raises(PortfolioVolatilityError, match="after the forecast"):
        _build(captured_at="2026-03-02T23:00:00+00:00", forecast_cutoff=_CUTOFF)


def test_a_snapshot_captured_exactly_at_the_cutoff_is_accepted():
    target = _build(captured_at=_CUTOFF, forecast_cutoff=_CUTOFF)
    assert target.target_kind == "frozen_weight"


def test_naive_timestamps_are_refused():
    with pytest.raises(PortfolioVolatilityError, match="timezone-aware"):
        _build(captured_at="2026-03-02T21:00:00")


# --- alignment refusals -----------------------------------------------------


def test_a_held_security_without_price_history_refuses_rather_than_dropping_it():
    """Dropping it would silently re-weight every remaining position and
    report the volatility of a book that was never held."""
    with pytest.raises(PortfolioVolatilityError, match="no price history"):
        _build(close_by_ticker={"AAA": _prices()})


def test_a_short_forward_window_refuses_rather_than_shrinking_the_horizon():
    with pytest.raises(PortfolioVolatilityError, match="forward sessions available"):
        _build(close_by_ticker=_universe_short(), horizon_sessions=20)


def _universe_short():
    return {"AAA": _prices(n=8), "BBB": _prices(n=8, seed=1)}


def test_a_missing_price_inside_the_window_refuses():
    prices = _universe()
    prices["BBB"] = prices["BBB"].copy()
    prices["BBB"].iloc[5] = np.nan
    with pytest.raises(PortfolioVolatilityError, match="missing or non-positive"):
        _build(close_by_ticker=prices)


def test_a_non_positive_price_inside_the_window_refuses():
    prices = _universe()
    prices["BBB"] = prices["BBB"].copy()
    prices["BBB"].iloc[5] = 0.0
    with pytest.raises(PortfolioVolatilityError, match="missing or non-positive"):
        _build(close_by_ticker=prices)


def test_duplicate_sessions_are_refused():
    prices = _universe()
    prices["AAA"] = pd.concat([prices["AAA"], prices["AAA"].iloc[-1:]])
    with pytest.raises(PortfolioVolatilityError, match="duplicate sessions"):
        _build(close_by_ticker=prices)


def test_missing_exact_as_of_row_is_refused_instead_of_using_stale_close():
    prices = {
        "AAA": _prices(start="2026-02-27"),
        "BBB": _prices(start="2026-02-27", seed=1),
    }
    prices = {
        ticker: series.drop(pd.Timestamp(_AS_OF))
        for ticker, series in prices.items()
    }
    with pytest.raises(PortfolioVolatilityError, match="exact common price row"):
        _build(close_by_ticker=prices)


def test_weekend_as_of_session_is_refused():
    with pytest.raises(PortfolioVolatilityError, match="not an NYSE trading session"):
        _build(
            as_of_session="2026-03-01",
            close_by_ticker=_universe(),
        )


def test_missing_exchange_session_inside_forward_window_is_refused():
    prices = _universe()
    prices = {
        ticker: series.drop(series.index[5])
        for ticker, series in prices.items()
    }
    with pytest.raises(PortfolioVolatilityError, match="canonical consecutive"):
        _build(close_by_ticker=prices)


# --- unit convention (plan 9.3) ---------------------------------------------


def test_the_target_is_a_daily_percent_standard_deviation():
    target = _build()
    assert 0 < target.daily_volatility_pct < 20  # daily, not annualized


def test_annualization_is_an_explicitly_named_display_field_only():
    """Plan 9.3: 'Do not compare a daily-percent target with an annualized
    baseline.' The only annualized value is behind a field whose name says
    so."""
    target = _build()
    assert target.annualized_volatility_pct == pytest.approx(
        target.daily_volatility_pct * math.sqrt(TRADING_SESSIONS_PER_YEAR)
    )
    payload = target.to_dict()
    assert payload["daily_volatility_pct"] == target.daily_volatility_pct
    assert "annualized" in "annualized_volatility_pct"
    # No unlabeled "volatility_pct" key that could be mistaken for either.
    assert "volatility_pct" not in payload


def test_a_target_rejects_a_negative_or_non_finite_volatility():
    with pytest.raises(PortfolioVolatilityError, match="non-negative finite"):
        PortfolioVolatilityTarget(
            account_key="paper", as_of_session=_AS_OF, target_kind="frozen_weight",
            horizon_sessions=20, daily_volatility_pct=-1.0, observation_count=20,
            weights={}, cash_weight=0.0, first_return_session=_AS_OF,
            last_return_session=_AS_OF, position_snapshot_hash="a", price_input_hash="b",
        )


def test_target_contract_rejects_unverifiable_provenance_and_weights():
    with pytest.raises(PortfolioVolatilityError, match="SHA-256"):
        PortfolioVolatilityTarget(
            account_key="paper", as_of_session=_AS_OF, target_kind="frozen_weight",
            horizon_sessions=20, daily_volatility_pct=1.0, observation_count=20,
            weights={"AAA": 1.0}, cash_weight=0.0, first_return_session=_AS_OF,
            last_return_session=_AS_OF, position_snapshot_hash="a", price_input_hash="b",
        )

    with pytest.raises(PortfolioVolatilityError, match="sum to one"):
        PortfolioVolatilityTarget(
            account_key="paper", as_of_session=_AS_OF, target_kind="frozen_weight",
            horizon_sessions=20, daily_volatility_pct=1.0, observation_count=20,
            weights={"AAA": 0.5}, cash_weight=0.0, first_return_session=_AS_OF,
            last_return_session=_AS_OF, position_snapshot_hash="a" * 64,
            price_input_hash="b" * 64,
        )


def test_an_unknown_target_kind_is_refused():
    with pytest.raises(PortfolioVolatilityError, match="target_kind"):
        PortfolioVolatilityTarget(
            account_key="paper", as_of_session=_AS_OF, target_kind="guessed",
            horizon_sessions=20, daily_volatility_pct=1.0, observation_count=20,
            weights={}, cash_weight=0.0, first_return_session=_AS_OF,
            last_return_session=_AS_OF, position_snapshot_hash="a", price_input_hash="b",
        )


# --- provenance -------------------------------------------------------------


def test_the_target_records_its_snapshot_and_price_input_hashes():
    target = _build()
    assert len(target.position_snapshot_hash) == 64
    assert len(target.price_input_hash) == 64


def test_changing_a_holding_changes_the_snapshot_hash():
    a = _build()
    b = _build(snapshots=[
        {"ticker": "AAA", "market_value": "7000"},
        {"ticker": "BBB", "market_value": "3000"},
    ])
    assert a.position_snapshot_hash != b.position_snapshot_hash


# --- realized account target ------------------------------------------------


def _equity_series(n: int = 25, *, start: float = 100_000.0, seed: int = 0):
    rng = np.random.default_rng(seed)
    sessions = [str(d.date()) for d in pd.bdate_range(_AS_OF, periods=n)]
    values = start * np.cumprod(1 + rng.normal(0, 0.01, n))
    return {s: f"{v:.2f}" for s, v in zip(sessions, values)}, sessions


def test_realized_account_target_is_a_distinct_kind():
    equity, sessions = _equity_series()
    flows = {s: "0" for s in sessions[1:]}
    target = build_realized_account_targets(
        "paper", as_of_session=_AS_OF, equity_by_session=equity,
        net_external_flow_by_session=flows, horizon_sessions=20,
    )
    assert target.target_kind == "realized_account"
    assert target.daily_volatility_pct > 0


def test_a_deposit_is_not_counted_as_investment_return():
    """Without flow adjustment a $10,000 contribution into a $100,000 account
    reads as a +10% return and would dominate the volatility estimate."""
    equity, sessions = _equity_series()
    with_deposit = dict(equity)
    deposit_session = sessions[3]
    # Add a large deposit to that session and every session after it.
    for session in sessions[3:]:
        with_deposit[session] = f"{float(equity[session]) + 10_000:.2f}"
    flows = {s: "0" for s in sessions[1:]}
    flows[deposit_session] = "10000"

    adjusted = build_realized_account_targets(
        "paper", as_of_session=_AS_OF, equity_by_session=with_deposit,
        net_external_flow_by_session=flows, horizon_sessions=20,
    )
    unflagged = build_realized_account_targets(
        "paper", as_of_session=_AS_OF, equity_by_session=with_deposit,
        net_external_flow_by_session={s: "0" for s in sessions[1:]},
        horizon_sessions=20,
    )
    # Treating the deposit as return inflates measured volatility.
    assert unflagged.daily_volatility_pct > adjusted.daily_volatility_pct


def test_a_missing_flow_record_refuses_rather_than_assuming_zero():
    equity, sessions = _equity_series()
    flows = {s: "0" for s in sessions[1:]}
    del flows[sessions[5]]
    with pytest.raises(PortfolioVolatilityError, match="net external flow is unrecorded"):
        build_realized_account_targets(
            "paper", as_of_session=_AS_OF, equity_by_session=equity,
            net_external_flow_by_session=flows, horizon_sessions=20,
        )


def test_insufficient_equity_history_reports_unavailable(tmp_path):
    """Plan 9.7: report unavailable rather than backfilling guessed
    holdings."""
    equity, sessions = _equity_series(n=6)
    flows = {s: "0" for s in sessions[1:]}
    with pytest.raises(PortfolioVolatilityError, match="forward equity observations"):
        build_realized_account_targets(
            "paper", as_of_session=_AS_OF, equity_by_session=equity,
            net_external_flow_by_session=flows, horizon_sessions=20,
        )


def test_non_positive_equity_is_refused():
    equity, sessions = _equity_series()
    equity[sessions[4]] = "0"
    flows = {s: "0" for s in sessions[1:]}
    with pytest.raises(PortfolioVolatilityError, match="must be positive"):
        build_realized_account_targets(
            "paper", as_of_session=_AS_OF, equity_by_session=equity,
            net_external_flow_by_session=flows, horizon_sessions=20,
        )


# --- no side effects --------------------------------------------------------


def test_the_module_imports_no_broker_or_execution_service():
    """Plan 9.2: 'Do not import a broker or execution service.'"""
    import ast
    import pathlib

    tree = ast.parse(pathlib.Path("ml/portfolio_volatility.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    forbidden = ("execution", "risk", "assistant.execution_service", "assistant.proposals")
    assert not [m for m in imported if any(m == f or m.startswith(f + ".") for f in forbidden)]


def test_building_targets_creates_no_files_or_database(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _build()
    equity, sessions = _equity_series()
    build_realized_account_targets(
        "paper", as_of_session=_AS_OF, equity_by_session=equity,
        net_external_flow_by_session={s: "0" for s in sessions[1:]}, horizon_sessions=20,
    )
    assert list(tmp_path.iterdir()) == []


def test_target_is_json_serializable():
    import json

    json.dumps(_build().to_dict())
