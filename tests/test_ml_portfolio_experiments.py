"""Tests for ml/portfolio_experiments.py (ML-LR-3 section 9.7).

The behavior that matters most here is UNDERFILL: plan 9.7 requires that
sparse real data be reported as unavailable rather than backfilled with
guessed holdings, and that refusals be visible rather than silently dropped.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from assistant.storage import AssistantStore
from ml.portfolio_experiments import (
    MIN_TARGETS_FOR_RESEARCH,
    PortfolioExperimentError,
    assess_portfolio_research_readiness,
    build_portfolio_target_series,
    build_realized_account_target_series,
    group_position_snapshots_by_session,
    summarize_portfolio_targets,
    targets_to_frame,
)

_START = "2026-01-01"


def _sessions(n: int) -> list[str]:
    return [str(d.date()) for d in pd.bdate_range(_START, periods=n)]


def _prices(n: int, *, seed: int = 0, daily_vol: float = 0.02) -> pd.Series:
    rng = np.random.default_rng(seed)
    index = pd.bdate_range(_START, periods=n)
    return pd.Series(100.0 * np.cumprod(1 + rng.normal(0, daily_vol, n)), index=index)


def _fixture(n_sessions: int = 120, *, horizon: int = 20):
    """Enough history that early sessions can produce targets and late ones
    legitimately cannot (no forward window)."""
    sessions = _sessions(n_sessions)
    close = {"AAA": _prices(n_sessions, seed=0), "BBB": _prices(n_sessions, seed=1)}
    positions = {
        session: [
            {"session_date": session, "ticker": "AAA", "market_value": "6000",
             "captured_at": f"{session}T21:00:00+00:00"},
            {"session_date": session, "ticker": "BBB", "market_value": "4000",
             "captured_at": f"{session}T21:00:00+00:00"},
        ]
        for session in sessions
    }
    cash = {session: "0" for session in sessions}
    cutoffs = {session: f"{session}T22:00:00+00:00" for session in sessions}
    return sessions, close, positions, cash, cutoffs


def _build(n_sessions: int = 120, horizon: int = 20):
    sessions, close, positions, cash, cutoffs = _fixture(n_sessions, horizon=horizon)
    return build_portfolio_target_series(
        "paper",
        positions_by_session=positions,
        cash_by_session=cash,
        close_by_ticker=close,
        forecast_cutoff_by_session=cutoffs,
        horizon_sessions=horizon,
    )


# --- grouping ---------------------------------------------------------------


def test_grouping_keeps_the_latest_capture_per_session_and_ticker():
    """The briefing can run more than once a day. Taking the earliest would
    silently use a stale intraday snapshot."""
    rows = [
        {"session_date": "2026-01-01", "ticker": "AAA", "market_value": "100",
         "captured_at": "2026-01-01T14:00:00+00:00"},
        {"session_date": "2026-01-01", "ticker": "AAA", "market_value": "200",
         "captured_at": "2026-01-01T21:00:00+00:00"},
    ]
    grouped = group_position_snapshots_by_session(rows)
    assert len(grouped["2026-01-01"]) == 1
    assert grouped["2026-01-01"][0]["market_value"] == "200"


def test_grouping_requires_its_fields():
    with pytest.raises(PortfolioExperimentError, match="missing 'captured_at'"):
        group_position_snapshots_by_session(
            [{"session_date": "2026-01-01", "ticker": "AAA", "market_value": "1"}]
        )


def test_grouping_reads_real_store_rows(tmp_path):
    """The runner consumes exactly what AssistantStore returns."""
    store = AssistantStore(tmp_path / "a.db")
    store.append_portfolio_position_snapshots([
        {"account_key": "paper", "session_date": "2026-01-01",
         "captured_at": "2026-01-01T21:00:00+00:00", "ticker": "NVDA",
         "shares": "10", "market_value": "2000", "price": "200", "source": "alpaca"},
    ])
    grouped = group_position_snapshots_by_session(
        store.list_portfolio_position_snapshots("paper")
    )
    assert grouped["2026-01-01"][0]["ticker"] == "NVDA"


# --- target series ----------------------------------------------------------


def test_sessions_without_a_forward_window_refuse_rather_than_shrink():
    result = _build(n_sessions=120, horizon=20)
    assert result.targets
    assert result.refusals
    # The last 20 sessions cannot have a full forward window.
    assert all("forward sessions available" in r["reason"] for r in result.refusals)
    assert result.attempted_session_count == 120


def test_refusals_are_returned_not_silently_dropped():
    """A run that produced 12 targets from 200 sessions looks identical to
    one that produced 12 from 12 unless refusals are visible."""
    result = _build()
    assert result.refusal_rate is not None and 0 < result.refusal_rate < 1
    counts = result.to_dict()["refusal_reason_counts"]
    assert counts and sum(counts.values()) == len(result.refusals)


def test_an_unrecorded_cash_balance_refuses_that_session():
    sessions, close, positions, cash, cutoffs = _fixture(60)
    del cash[sessions[0]]
    result = build_portfolio_target_series(
        "paper", positions_by_session=positions, cash_by_session=cash,
        close_by_ticker=close, forecast_cutoff_by_session=cutoffs, horizon_sessions=20,
    )
    assert any(
        r["as_of_session"] == sessions[0] and "cash balance unrecorded" in r["reason"]
        for r in result.refusals
    )


def test_an_unrecorded_forecast_cutoff_refuses_that_session():
    sessions, close, positions, cash, cutoffs = _fixture(60)
    del cutoffs[sessions[0]]
    result = build_portfolio_target_series(
        "paper", positions_by_session=positions, cash_by_session=cash,
        close_by_ticker=close, forecast_cutoff_by_session=cutoffs, horizon_sessions=20,
    )
    assert any(
        r["as_of_session"] == sessions[0] and "forecast cutoff unrecorded" in r["reason"]
        for r in result.refusals
    )


def test_a_snapshot_captured_after_its_cutoff_refuses_that_session():
    sessions, close, positions, cash, cutoffs = _fixture(60)
    late = sessions[0]
    positions[late] = [
        {**row, "captured_at": f"{late}T23:00:00+00:00"} for row in positions[late]
    ]
    result = build_portfolio_target_series(
        "paper", positions_by_session=positions, cash_by_session=cash,
        close_by_ticker=close, forecast_cutoff_by_session=cutoffs, horizon_sessions=20,
    )
    assert any(
        r["as_of_session"] == late and "after the forecast" in r["reason"]
        for r in result.refusals
    )


def test_every_built_target_is_a_frozen_weight_target():
    result = _build()
    assert all(t.target_kind == "frozen_weight" for t in result.targets)


# --- realized account series ------------------------------------------------


def _equity(n: int = 60):
    sessions = _sessions(n)
    rng = np.random.default_rng(0)
    values = 100_000 * np.cumprod(1 + rng.normal(0, 0.01, n))
    equity = {s: f"{v:.2f}" for s, v in zip(sessions, values)}
    flows = {s: "0" for s in sessions}
    return sessions, equity, flows


def test_realized_account_series_produces_its_own_kind():
    sessions, equity, flows = _equity(60)
    result = build_realized_account_target_series(
        "paper", equity_by_session=equity, net_external_flow_by_session=flows,
        horizon_sessions=20,
    )
    assert result.targets
    assert all(t.target_kind == "realized_account" for t in result.targets)


def test_the_two_target_kinds_cannot_be_pooled_into_one_frame():
    """They measure different quantities; pooling them would train a model on
    a mixture it can never predict."""
    frozen = _build(n_sessions=60).targets
    sessions, equity, flows = _equity(60)
    realized = build_realized_account_target_series(
        "paper", equity_by_session=equity, net_external_flow_by_session=flows,
        horizon_sessions=20,
    ).targets
    with pytest.raises(PortfolioExperimentError, match="different target kinds"):
        targets_to_frame(list(frozen) + list(realized))


# --- frame shape ------------------------------------------------------------


def test_targets_to_frame_uses_the_account_as_the_observation_unit():
    """The observation unit is an account-session, not a security. Naming it
    honestly keeps cross-sectional rank metrics from being applied to a panel
    with one name per date, where a rank correlation is undefined."""
    frame = targets_to_frame(_build(n_sessions=60).targets)
    assert set(frame["ticker"]) == {"paper"}
    assert frame.groupby("as_of_session").size().max() == 1


def test_targets_to_frame_carries_the_exit_session_for_purging():
    frame = targets_to_frame(_build(n_sessions=60).targets)
    assert "exit_session" in frame.columns
    assert (frame["exit_session"] > frame["as_of_session"]).all()


def test_targets_to_frame_is_sorted_and_carries_provenance():
    frame = targets_to_frame(_build(n_sessions=60).targets)
    assert frame["as_of_session"].is_monotonic_increasing
    assert frame["position_snapshot_hash"].str.len().eq(64).all()
    assert frame["price_input_hash"].str.len().eq(64).all()


def test_an_empty_target_list_yields_an_empty_typed_frame():
    frame = targets_to_frame([])
    assert frame.empty
    assert "label_value" in frame.columns


# --- readiness: the plan 9.7 behavior ---------------------------------------


def test_a_sparse_account_is_reported_underfilled_rather_than_researched():
    """Plan 9.7's core requirement."""
    result = _build(n_sessions=30)
    readiness = assess_portfolio_research_readiness(result)
    assert readiness["ready"] is False
    assert readiness["status"] == "underfilled"
    assert readiness["blockers"]
    assert "rather than run on an inadequate sample" in readiness["note"]


def test_readiness_reports_how_far_short_it_is():
    """'42 of the 60 sessions needed' is actionable; a silent absence is
    not."""
    result = _build(n_sessions=30)
    readiness = assess_portfolio_research_readiness(result)
    assert readiness["minimum_targets"] == MIN_TARGETS_FOR_RESEARCH
    assert readiness["target_count"] < readiness["minimum_targets"]
    assert any("required" in b for b in readiness["blockers"])


def test_readiness_accounts_for_purged_fold_arithmetic():
    """Target count alone is misleading: with a 20-session embargo a large
    fraction of every training fold is purged away."""
    result = _build(n_sessions=120)
    strict = assess_portfolio_research_readiness(
        result, n_splits=4, embargo_sessions=20
    )
    lenient = assess_portfolio_research_readiness(
        result, n_splits=2, embargo_sessions=5
    )
    assert strict["targets_needed_for_folds"] > lenient["targets_needed_for_folds"]


def test_an_adequately_filled_account_is_reported_ready():
    result = _build(n_sessions=200)
    readiness = assess_portfolio_research_readiness(
        result, n_splits=2, embargo_sessions=20
    )
    assert readiness["ready"] is True
    assert readiness["status"] == "ready"
    assert readiness["blockers"] == ()


def test_readiness_surfaces_the_refusal_rate():
    result = _build(n_sessions=120)
    readiness = assess_portfolio_research_readiness(result)
    assert readiness["refusal_count"] == len(result.refusals)
    assert readiness["refusal_reason_counts"]


# --- summary ----------------------------------------------------------------


def test_the_summary_is_descriptive_and_carries_no_verdict():
    summary = summarize_portfolio_targets(_build(n_sessions=120))
    assert summary["available"] is True
    assert summary["target_kind"] == "frozen_weight"
    for forbidden in ("verdict", "passes", "promising", "production_authoritative"):
        assert forbidden not in summary


def test_the_summary_states_its_units():
    summary = summarize_portfolio_targets(_build(n_sessions=60))
    assert "daily-return standard deviation in percent" in summary["units"]


def test_the_summary_reports_cash_drag():
    sessions, close, positions, cash, cutoffs = _fixture(60)
    half_cash = {s: "10000" for s in sessions}  # equal to the invested value
    result = build_portfolio_target_series(
        "paper", positions_by_session=positions, cash_by_session=half_cash,
        close_by_ticker=close, forecast_cutoff_by_session=cutoffs, horizon_sessions=20,
    )
    summary = summarize_portfolio_targets(result)
    assert summary["cash_weight"]["mean"] == pytest.approx(0.5, abs=1e-9)


def test_an_empty_result_summarizes_as_unavailable():
    summary = summarize_portfolio_targets(_build(n_sessions=10))
    assert summary["available"] is False
    assert "no portfolio targets" in summary["reason"]
    assert summary["refusal_reason_counts"]


def test_summary_and_readiness_are_json_serializable():
    import json

    result = _build(n_sessions=60)
    json.dumps(summarize_portfolio_targets(result))
    json.dumps(assess_portfolio_research_readiness(result))
    json.dumps(result.to_dict())


# --- no side effects --------------------------------------------------------


def test_the_module_imports_no_broker_execution_service_or_storage():
    import ast
    import pathlib

    tree = ast.parse(pathlib.Path("ml/portfolio_experiments.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    forbidden = ("execution", "risk", "assistant.execution_service",
                 "assistant.proposals", "assistant.storage")
    assert not [m for m in imported if any(m == f or m.startswith(f + ".") for f in forbidden)]


def test_building_targets_creates_no_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _build(n_sessions=60)
    assert list(tmp_path.iterdir()) == []
