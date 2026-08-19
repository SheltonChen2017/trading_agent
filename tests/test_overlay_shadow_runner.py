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
        "required_observation_count": 24,
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


def test_observe_refuses_an_unregistered_stream(harness):
    """SHW2-007: the closed-epoch half lives in its own test below."""
    fetch, argv, database, config = harness
    _set_all(fetch, {FEB27: 100.0, MAR02: 100.0})
    assert runner.main([*argv, "observe"]) == 1   # not registered


def test_baseline_refuses_when_any_member_is_unpriced(harness):
    """SHW2-001: an available t0 with an unpriced member would poison
    every later cycle boundary; the baseline must refuse and retry at
    the next month-end instead."""
    fetch, argv, database, config = harness
    runner.main([*argv, "register"])
    _set_all(fetch, {FEB27: 100.0, MAR02: 100.0},
             tickers=("AAA", "BBB", "CCC"))
    fetch.data["DDD"] = {MAR02: 100.0}          # no FEB27 close
    assert runner.main([*argv, "observe"]) == 0
    store = AssistantStore(database)
    rows = store.get_overlay_observations(
        config["stream_name"], config["evidence_epoch"]
    )
    assert len(rows) == 1 and rows[0]["available"] == 0
    refusal = json.loads(rows[0]["observation_json"])
    assert any("DDD" in reason for reason in refusal["refusal_reasons"])
    # The stream HEALS: DDD priced at the next month-end -> baseline there.
    _set_all(fetch, {MAR31: 100.0, APR01: 100.0})
    assert runner.main([*argv, "observe"]) == 0
    rows = store.get_overlay_observations(
        config["stream_name"], config["evidence_epoch"]
    )
    assert rows[-1]["cycle_session"] == MAR31.isoformat()
    assert rows[-1]["available"] == 1


def test_mature_never_settles_a_multi_month_span_as_monthly(harness):
    """SHW2-002: a pair of available observations separated by gap or
    refusal cycles spans several months; `monthly_returns` must not
    settle it. Only calendar-adjacent available pairs mature."""
    fetch, argv, database, config = harness
    runner.main([*argv, "register"])
    _set_all(fetch, {FEB27: 100.0, MAR02: 100.0})
    runner.main([*argv, "observe"])                       # baseline FEB27
    _set_all(fetch, {MAR31: 150.0, APR30: 180.0, MAY29: 200.0, JUN01: 201.0},
             tickers=UNIVERSE)
    _set_all(fetch, {MAR31: 100.0, APR30: 100.0, MAY29: 100.0, JUN01: 100.0},
             tickers=CARRY)
    runner.main([*argv, "observe"])       # gaps at MAR31/APR30, obs at MAY29
    assert runner.main([*argv, "mature"]) == 0
    store = AssistantStore(database)
    assert store.get_overlay_outcomes(
        config["stream_name"], config["evidence_epoch"]
    ) == []


def test_observe_refuses_a_closed_epoch_with_an_alert(harness):
    """SHW2-003: the closed-stream gate, actually exercised."""
    fetch, argv, database, config = harness
    store = AssistantStore(database)
    from assistant.overlay_shadow import OverlayStreamRegistration
    registration = OverlayStreamRegistration(
        stream_name=config["stream_name"],
        evidence_epoch=config["evidence_epoch"],
        preregistration_path=config["preregistration_path"],
        preregistration_sha256="a" * 64,
        code_commit=COMMIT,
        schedule_key=config["schedule_key"],
        schedule_version=config["schedule_version"],
        universe_members=config["universe_members"],
        carry_members=config["carry_members"],
        carry_weight=config["carry_weight"],
        band_fraction=config["band_fraction"],
        required_observation_count=config["required_observation_count"],
        status="closed",
    )
    store.register_overlay_stream(registration.to_payload())
    _set_all(fetch, {FEB27: 100.0, MAR02: 100.0})
    assert runner.main([*argv, "observe"]) == 1
    with store._connect() as connection:
        alerts = connection.execute(
            "SELECT message FROM operational_alerts "
            "WHERE category = 'shadow_overlay'"
        ).fetchall()
    assert any("closed" in a["message"] for a in alerts)


def test_observation_cannot_assert_point_in_time_data(harness):
    """SHW2-005: adjusted provider history stays explicitly non-PIT and
    no caller can claim otherwise; every payload carries the flag."""
    from assistant.overlay_shadow import (
        OverlayContractError, OverlayObservation,
    )
    with pytest.raises(OverlayContractError, match="point_in_time"):
        OverlayObservation(
            stream_name="s", evidence_epoch="e", cycle_session="2026-02-27",
            generated_at="2026-02-27T21:00:00+00:00", provider="p",
            inputs_sha256="a" * 64, available=False,
            refusal_reasons=("x",), point_in_time_data=True,
        )
    fetch, argv, database, config = harness
    runner.main([*argv, "register"])
    _set_all(fetch, {FEB27: 100.0, MAR02: 100.0})
    runner.main([*argv, "observe"])
    store = AssistantStore(database)
    rows = store.get_overlay_observations(
        config["stream_name"], config["evidence_epoch"]
    )
    assert json.loads(rows[0]["observation_json"])["point_in_time_data"] is False


def test_mature_calendar_guard_holds_even_without_intervening_rows(harness):
    """SHW2-006: two available rows in non-adjacent months with NO gap
    row between them (inserted directly, bypassing observe) must still
    not settle — the calendar guard is load-bearing on its own, not just
    a shadow of row adjacency."""
    fetch, argv, database, config = harness
    runner.main([*argv, "register"])
    store = AssistantStore(database)
    from assistant.overlay_shadow import OverlayObservation
    for cycle, level in ((FEB27, 100.0), (MAY29, 180.0)):
        store.record_overlay_observation(OverlayObservation(
            stream_name=config["stream_name"],
            evidence_epoch=config["evidence_epoch"],
            cycle_session=cycle.isoformat(),
            generated_at="2026-06-01T21:00:00+00:00",
            provider="test", inputs_sha256="a" * 64, available=True,
            index_levels={"universe": level, "carry": 100.0,
                          "combined": level},
            combined_carry_weight=0.20,
        ).to_payload())
    assert runner.main([*argv, "mature"]) == 0
    assert store.get_overlay_outcomes(
        config["stream_name"], config["evidence_epoch"]
    ) == []


def test_registration_requires_a_positive_preregistered_count():
    """SHW-3: no universal default sample threshold; every stream must
    preregister its own positive requirement."""
    from assistant.overlay_shadow import (
        OverlayContractError,
    )
    from tests.test_overlay_shadow import _registration
    for bad in (0, -1, True, "24", None):
        with pytest.raises((OverlayContractError, TypeError)):
            _registration(required_observation_count=bad)


_FORBIDDEN_REPORT_TERMS = ("sharpe", "cagr", "mean_return", "p_value",
                           "index_levels", "monthly_returns")


def test_sufficiency_reports_counts_and_reasons_without_statistics(harness):
    """SHW-3: the section-6 fields, and NOT ONE statistic — the report
    must be safe to read without spending a look."""
    fetch, argv, database, config = harness
    runner.main([*argv, "register"])
    _set_all(fetch, {FEB27: 100.0, MAR02: 100.0})
    runner.main([*argv, "observe"])                       # baseline only
    out = Path(argv[1]).parent / "sufficiency.json"
    assert runner.main([*argv, "sufficiency", "--output", str(out)]) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["sufficiency"] == "NOT_MET"
    assert report["preregistered_required_count"] == 24
    assert report["independent_observation_count"] == 0
    assert any("0 matured" in reason
               for reason in report["insufficiency_reasons"])
    assert report["counts"]["available_observations"] == 1
    assert report["point_in_time_data"] is False
    assert "separate, owner-authorized" in report["gate_evaluation"]
    text = out.read_text(encoding="utf-8").lower()
    for term in _FORBIDDEN_REPORT_TERMS:
        assert term not in text, term


def test_sufficiency_met_exactly_at_the_preregistered_boundary(
    harness, tmp_path
):
    fetch, argv, database, config = harness
    config["required_observation_count"] = 1
    config_path = tmp_path / "boundary.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    argv = ["--database", argv[1], "--config", str(config_path)]
    runner.main([*argv, "register"])
    _set_all(fetch, {FEB27: 100.0, MAR02: 100.0})
    runner.main([*argv, "observe"])
    _set_all(fetch, {MAR31: 110.0, APR01: 111.0}, tickers=UNIVERSE)
    _set_all(fetch, {MAR31: 100.0, APR01: 100.0}, tickers=CARRY)
    runner.main([*argv, "observe"])
    runner.main([*argv, "mature"])
    out = tmp_path / "boundary_report.json"
    assert runner.main([*argv, "sufficiency", "--output", str(out)]) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["sufficiency"] == "MET"
    assert report["independent_observation_count"] == 1
    assert report["insufficiency_reasons"] == []
    # MET still evaluates no gate and prints no statistic.
    assert "separate, owner-authorized" in report["gate_evaluation"]


def test_sufficiency_refuses_a_drifted_config_count(harness, tmp_path):
    """The registration is the authority; a config with a different
    requirement must refuse loudly, not silently re-anchor the report."""
    fetch, argv, database, config = harness
    runner.main([*argv, "register"])
    drifted = dict(config, required_observation_count=6)
    drifted_path = tmp_path / "drifted.json"
    drifted_path.write_text(json.dumps(drifted), encoding="utf-8")
    assert runner.main(
        ["--database", argv[1], "--config", str(drifted_path), "sufficiency"]
    ) == 1
    store = AssistantStore(database)
    with store._connect() as connection:
        alerts = connection.execute(
            "SELECT message FROM operational_alerts "
            "WHERE category = 'shadow_overlay'"
        ).fetchall()
    assert any("config drift" in a["message"] for a in alerts)


def test_sufficiency_is_read_only_against_the_database(harness, tmp_path):
    import sqlite3 as _sqlite3
    fetch, argv, database, config = harness
    runner.main([*argv, "register"])
    _set_all(fetch, {FEB27: 100.0, MAR02: 100.0})
    runner.main([*argv, "observe"])

    def snapshot():
        with _sqlite3.connect(database) as connection:
            connection.row_factory = _sqlite3.Row
            tables = [r["name"] for r in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")
                if not r["name"].startswith("sqlite_")]
            return {t: [tuple(row) for row in connection.execute(
                f"SELECT * FROM {t}")] for t in tables}

    before = snapshot()
    out = tmp_path / "ro_report.json"
    assert runner.main([*argv, "sufficiency", "--output", str(out)]) == 0
    assert snapshot() == before
