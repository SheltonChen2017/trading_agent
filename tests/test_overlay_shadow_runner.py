"""SHW-2 regressions: the overlay shadow runner.

Dangerous directions: backfilled history masquerading as prospective
observation, partial imputation at a cycle boundary, invisible gaps,
band math drifting from the stated mechanism, and failures that die
silently instead of leaving a durable alert.
"""
from __future__ import annotations

import json
import hashlib
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from assistant.overlay_shadow import (
    OverlayContractError,
    advance_overlay,
    completed_month_end_sessions,
    sleeve_return,
)
from assistant.runtime_identity import RuntimeIdentityError
from assistant.storage import AssistantStore
from scripts import run_overlay_shadow as runner

COMMIT = "c" * 40
UNIVERSE = ("AAA", "BBB")
CARRY = ("CCC", "DDD")


# ------------------------------------------------------------------ pure


def test_completed_month_ends_exclude_the_in_progress_month():
    sessions = [date(2026, 1, 30), date(2026, 1, 31), date(2026, 2, 27),
                date(2026, 3, 2), date(2026, 3, 31)]
    assert completed_month_end_sessions(sessions) == (
        date(2026, 1, 31), date(2026, 2, 27),
    )
    with pytest.raises(OverlayContractError, match="ascending"):
        completed_month_end_sessions([date(2026, 1, 31), date(2026, 1, 31)])


def test_sleeve_return_refuses_the_whole_sleeve_on_one_bad_member():
    previous = {"AAA": 100.0, "BBB": 100.0}
    value, missing = sleeve_return(previous, {"AAA": 110.0, "BBB": 90.0},
                                   ["AAA", "BBB"])
    assert value == pytest.approx(0.0)
    assert missing == ()
    value, missing = sleeve_return(previous, {"AAA": 110.0}, ["AAA", "BBB"])
    assert value is None and missing == ("BBB",)
    value, missing = sleeve_return(previous, {"AAA": 110.0, "BBB": float("nan")},
                                   ["AAA", "BBB"])
    assert value is None and missing == ("BBB",)


def test_advance_overlay_band_lets_small_drift_ride_and_snaps_large_drift():
    # Inside the band: ru=10%, rc=0 -> drift 0.2/1.08 = 0.185, within
    # [0.15, 0.25] -> ride.
    level, weight, rebalanced = advance_overlay(
        level=100.0, carry_weight=0.20, universe_return=0.10,
        carry_return=0.0, carry_target=0.20, band_fraction=0.25,
    )
    assert level == pytest.approx(108.0)
    assert weight == pytest.approx(0.2 / 1.08)
    assert rebalanced is False
    # Outside the band: ru=50% -> drift 0.2/1.4 = 0.1428 < 0.15 -> snap.
    level, weight, rebalanced = advance_overlay(
        level=100.0, carry_weight=0.20, universe_return=0.50,
        carry_return=0.0, carry_target=0.20, band_fraction=0.25,
    )
    assert level == pytest.approx(140.0)
    assert weight == pytest.approx(0.20)
    assert rebalanced is True
    with pytest.raises(OverlayContractError, match="wiped-out"):
        advance_overlay(level=100.0, carry_weight=0.5, universe_return=-1.0,
                        carry_return=-1.0, carry_target=0.5,
                        band_fraction=0.25)


# ---------------------------------------------------------------- harness


def _frame(closes: dict[date, float]) -> pd.DataFrame:
    index = pd.to_datetime(sorted(closes))
    return pd.DataFrame(
        {"close": [closes[stamp] for stamp in sorted(closes)]}, index=index
    )


class _StubFetch:
    def __init__(self):
        self.data: dict[str, dict[date, float]] = {}

    def __call__(self, tickers, lookback_days=252):
        return {ticker: _frame(self.data.get(ticker, {})) for ticker in tickers}


@pytest.fixture()
def harness(tmp_path: Path, monkeypatch):
    fetch = _StubFetch()
    monkeypatch.setattr(runner, "fetch_historical", fetch)
    monkeypatch.setattr(
        runner, "current_commit",
        lambda require_clean=True, repository=None: COMMIT,
    )
    config = {
        "stream_name": "defensive-carry-test",
        "evidence_epoch": "overlay-epoch-t1",
        "preregistration_path":
            "docs/research/DEFENSIVE_CARRY_2026-08-18_PREREGISTRATION.md",
        "schedule_key": "overlay-monthly",
        "schedule_version": "1",
        "universe_members": list(UNIVERSE),
        "carry_members": list(CARRY),
        "carry_weight": "0.20",
        "band_fraction": "0.25",
    }
    config_path = tmp_path / "stream.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    database = tmp_path / "shadow.db"
    argv = ["--database", str(database), "--config", str(config_path)]
    return fetch, argv, database, config


def _set_all(fetch: _StubFetch, closes_by_session: dict[date, float],
             tickers=UNIVERSE + CARRY):
    for ticker in tickers:
        fetch.data.setdefault(ticker, {}).update(closes_by_session)


JAN31 = date(2026, 1, 30)
FEB27 = date(2026, 2, 27)
MAR31 = date(2026, 3, 31)
APR30 = date(2026, 4, 30)
MAY29 = date(2026, 5, 29)
JUN01 = date(2026, 6, 1)
MAR02 = date(2026, 3, 2)
APR01 = date(2026, 4, 1)


def test_register_binds_the_preregistration_hash(harness):
    fetch, argv, database, config = harness
    assert runner.main([*argv, "register"]) == 0
    store = AssistantStore(database)
    row = store.get_overlay_stream_registration(
        config["stream_name"], config["evidence_epoch"]
    )
    payload = json.loads(row["registration_json"])
    expected = hashlib.sha256(
        (runner.ROOT / config["preregistration_path"]).read_bytes()
    ).hexdigest()
    assert payload["preregistration_sha256"] == expected
    assert payload["code_commit"] == COMMIT


def test_register_refuses_a_dirty_tree_with_a_durable_alert(
    harness, monkeypatch
):
    fetch, argv, database, config = harness
    monkeypatch.setattr(
        runner, "current_commit",
        lambda require_clean=True, repository=None: (_ for _ in ()).throw(
            RuntimeIdentityError("worktree is dirty")
        ),
    )
    assert runner.main([*argv, "register"]) == 1
    store = AssistantStore(database)
    with store._connect() as connection:
        alerts = connection.execute(
            "SELECT fingerprint, category FROM operational_alerts"
        ).fetchall()
    assert any(a["category"] == "shadow_overlay" for a in alerts)


def test_first_observe_is_a_prospective_baseline_not_a_backfill(harness):
    fetch, argv, database, config = harness
    runner.main([*argv, "register"])
    _set_all(fetch, {JAN31: 90.0, FEB27: 100.0, MAR02: 101.0})
    assert runner.main([*argv, "observe"]) == 0
    store = AssistantStore(database)
    rows = store.get_overlay_observations(
        config["stream_name"], config["evidence_epoch"]
    )
    # ONE row, at the LATEST completed month-end, at 100.0 — January is
    # never backfilled even though its data exists.
    assert len(rows) == 1
    payload = json.loads(rows[0]["observation_json"])
    assert payload["cycle_session"] == FEB27.isoformat()
    assert payload["index_levels"] == {
        "carry": 100.0, "combined": 100.0, "universe": 100.0
    }
    assert payload["combined_carry_weight"] == pytest.approx(0.20)


def test_observe_advances_with_hand_computed_band_math(harness):
    fetch, argv, database, config = harness
    runner.main([*argv, "register"])
    _set_all(fetch, {FEB27: 100.0, MAR02: 100.0})
    runner.main([*argv, "observe"])                       # baseline at FEB27
    # Universe +10%, carry flat at MAR31.
    _set_all(fetch, {MAR31: 110.0, APR01: 111.0}, tickers=UNIVERSE)
    _set_all(fetch, {MAR31: 100.0, APR01: 100.0}, tickers=CARRY)
    assert runner.main([*argv, "observe"]) == 0
    store = AssistantStore(database)
    rows = store.get_overlay_observations(
        config["stream_name"], config["evidence_epoch"]
    )
    assert len(rows) == 2
    payload = json.loads(rows[-1]["observation_json"])
    assert payload["cycle_session"] == MAR31.isoformat()
    assert payload["index_levels"]["universe"] == pytest.approx(110.0)
    assert payload["index_levels"]["carry"] == pytest.approx(100.0)
    assert payload["index_levels"]["combined"] == pytest.approx(108.0)
    assert payload["combined_carry_weight"] == pytest.approx(0.2 / 1.08)
    # Idempotent rerun records nothing new.
    assert runner.main([*argv, "observe"]) == 0
    assert len(store.get_overlay_observations(
        config["stream_name"], config["evidence_epoch"]
    )) == 2


def test_unpriceable_member_refuses_the_cycle_and_names_the_ticker(harness):
    fetch, argv, database, config = harness
    runner.main([*argv, "register"])
    _set_all(fetch, {FEB27: 100.0, MAR02: 100.0})
    runner.main([*argv, "observe"])
    _set_all(fetch, {MAR31: 110.0, APR01: 111.0}, tickers=("AAA", "BBB", "CCC"))
    fetch.data["DDD"][APR01] = 100.0        # DDD has no MAR31 close
    assert runner.main([*argv, "observe"]) == 0
    store = AssistantStore(database)
    rows = store.get_overlay_observations(
        config["stream_name"], config["evidence_epoch"]
    )
    refusal = json.loads(rows[-1]["observation_json"])
    assert refusal["available"] is False
    assert refusal["index_levels"] is None
    assert any("DDD" in reason for reason in refusal["refusal_reasons"])


def test_gap_cycles_get_refusal_rows_and_the_next_cycle_spans_them(harness):
    fetch, argv, database, config = harness
    runner.main([*argv, "register"])
    _set_all(fetch, {FEB27: 100.0, MAR02: 100.0})
    runner.main([*argv, "observe"])                       # baseline FEB27
    # The runner was off for March and April; universe doubled over the
    # span, carry flat. Completed month-ends now: FEB27, MAR31, APR30, MAY29.
    _set_all(fetch, {MAR31: 150.0, APR30: 180.0, MAY29: 200.0, JUN01: 201.0},
             tickers=UNIVERSE)
    _set_all(fetch, {MAR31: 100.0, APR30: 100.0, MAY29: 100.0, JUN01: 100.0},
             tickers=CARRY)
    assert runner.main([*argv, "observe"]) == 0
    store = AssistantStore(database)
    rows = store.get_overlay_observations(
        config["stream_name"], config["evidence_epoch"]
    )
    by_cycle = {row["cycle_session"]: row for row in rows}
    assert set(by_cycle) == {
        FEB27.isoformat(), MAR31.isoformat(), APR30.isoformat(),
        MAY29.isoformat(),
    }
    assert by_cycle[MAR31.isoformat()]["available"] == 0
    assert by_cycle[APR30.isoformat()]["available"] == 0
    target = json.loads(by_cycle[MAY29.isoformat()]["observation_json"])
    assert target["available"] is True
    # Spanning return FEB27 -> MAY29: universe +100%, carry flat; drift
    # 0.2/1.8 = 0.111 < 0.15 -> band snaps back to target.
    assert target["index_levels"]["universe"] == pytest.approx(200.0)
    assert target["index_levels"]["combined"] == pytest.approx(180.0)
    assert target["combined_carry_weight"] == pytest.approx(0.20)


def test_mature_settles_only_consecutive_available_cycles(harness):
    fetch, argv, database, config = harness
    runner.main([*argv, "register"])
    _set_all(fetch, {FEB27: 100.0, MAR02: 100.0})
    runner.main([*argv, "observe"])
    _set_all(fetch, {MAR31: 110.0, APR01: 111.0}, tickers=UNIVERSE)
    _set_all(fetch, {MAR31: 100.0, APR01: 100.0}, tickers=CARRY)
    runner.main([*argv, "observe"])
    assert runner.main([*argv, "mature"]) == 0
    store = AssistantStore(database)
    outcomes = store.get_overlay_outcomes(
        config["stream_name"], config["evidence_epoch"]
    )
    assert len(outcomes) == 1
    payload = json.loads(outcomes[0]["outcome_json"])
    assert payload["cycle_session"] == FEB27.isoformat()
    assert payload["monthly_returns"]["universe"] == pytest.approx(0.10)
    assert payload["monthly_returns"]["combined"] == pytest.approx(0.08)
    # Idempotent: nothing new on rerun.
    assert runner.main([*argv, "mature"]) == 0
    assert len(store.get_overlay_outcomes(
        config["stream_name"], config["evidence_epoch"]
    )) == 1


def test_observe_failure_records_a_durable_alert(harness, monkeypatch):
    fetch, argv, database, config = harness
    runner.main([*argv, "register"])
    def _boom(tickers, lookback_days=252):
        raise RuntimeError("provider exploded")
    monkeypatch.setattr(runner, "fetch_historical", _boom)
    assert runner.main([*argv, "observe"]) == 1
    store = AssistantStore(database)
    with store._connect() as connection:
        alerts = connection.execute(
            "SELECT fingerprint, message FROM operational_alerts "
            "WHERE category = 'shadow_overlay'"
        ).fetchall()
    assert any("observe" in a["fingerprint"] for a in alerts)
    assert any("provider exploded" in a["message"] for a in alerts)


def test_observe_refuses_an_unregistered_or_closed_stream(harness):
    fetch, argv, database, config = harness
    _set_all(fetch, {FEB27: 100.0, MAR02: 100.0})
    assert runner.main([*argv, "observe"]) == 1   # not registered
