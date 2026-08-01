"""Tests for ml/shadow.py and the ML-LR-6 storage schema.

Covers plan 12.6's applicable items: concurrent claims create one run; exact
retry is idempotent and conflict is loud; a model/config/provider change
requires a new epoch; predictions from different epochs are never pooled;
exchange holidays mature on the correct session; unavailable attempts cannot
mature; clock skew and naive timestamps fail closed; and the shadow cycle
leaves every execution table unchanged.
"""
from __future__ import annotations

import pytest

from assistant.storage import AssistantStore
from ml.shadow import (
    MaturityDecision,
    ShadowScheduleError,
    build_lineage,
    configuration_hash,
    decide_maturity,
    epoch_key,
    is_trading_session,
    plan_scheduled_sessions,
    resolve_decision_cutoff,
    resolve_target_availability,
    resolve_target_session,
    session_close_instant,
    trading_sessions,
)


def _lineage(**overrides) -> dict[str, str]:
    payload = dict(
        model_artifact_hash="a" * 64,
        evaluation_report_hash="b" * 64,
        feature_set_version="fs-v1",
        label_version="forward_realized_vol_20d_v1",
        data_provider_id="yfinance_retroactively_adjusted",
        configuration_hash="c" * 64,
        code_commit="d" * 40,
        schedule_version="daily-close-v1",
    )
    payload.update(overrides)
    return build_lineage(**payload)


def _open_epoch(store: AssistantStore, **overrides):
    lineage = overrides.pop("lineage", _lineage())
    kwargs = dict(
        evidence_epoch=epoch_key("vol:0.1.0", "volatility_forecast", lineage),
        model_key="vol:0.1.0",
        task="volatility_forecast",
        lineage=lineage,
        created_by="test",
        started_at="2026-02-01T00:00:00+00:00",
    )
    kwargs.update(overrides)
    return store.open_ml_evidence_epoch(**kwargs)


# --- exchange calendar ------------------------------------------------------


def test_a_horizon_skips_thanksgiving_rather_than_counting_calendar_days():
    """2026-11-26 is Thanksgiving. Calendar-day arithmetic would land on a
    day that never traded."""
    assert resolve_target_session("2026-11-25", 1) == "2026-11-27"
    assert not is_trading_session("2026-11-26")


def test_a_horizon_skips_weekends():
    # 2026-11-27 is a Friday; +1 session is the following Monday.
    assert resolve_target_session("2026-11-27", 1) == "2026-11-30"


def test_an_early_close_session_uses_its_real_close_not_1600_et():
    """Black Friday closes at 13:00 ET. Assuming 16:00 would make a job wait
    three hours for data that already exists."""
    black_friday = session_close_instant("2026-11-27")
    normal = session_close_instant("2026-11-25")
    assert black_friday.hour == 18  # 13:00 ET
    assert normal.hour == 21        # 16:00 ET


def test_a_non_session_has_no_close_instant():
    with pytest.raises(ShadowScheduleError, match="not an NYSE trading session"):
        session_close_instant("2026-11-26")


def test_the_decision_cutoff_derives_from_the_session_not_from_now():
    """A job that fires late must produce the prediction it would have
    produced on time; deriving from `now` would make a delayed scheduler a
    different experiment."""
    first = resolve_decision_cutoff("2026-02-25")
    second = resolve_decision_cutoff("2026-02-25")
    assert first == second == "2026-02-25T21:00:00+00:00"


def test_a_non_canonical_session_is_refused():
    with pytest.raises(ShadowScheduleError, match="YYYY-MM-DD"):
        resolve_target_session("2026-2-25", 5)


def test_a_non_positive_horizon_is_refused():
    with pytest.raises(ShadowScheduleError, match="positive integer"):
        resolve_target_session("2026-02-25", 0)


def test_a_long_horizon_resolves_rather_than_silently_truncating():
    """The over-fetch must scale with the horizon. If it did not, a long
    horizon would quietly return the last session in a too-short window --
    a target years earlier than requested, with nothing to indicate it.
    pandas_market_calendars generates rules-based schedules far into the
    future, so this resolves rather than refusing."""
    assert resolve_target_session("2026-02-25", 2000) == "2034-02-10"
    # And a horizon genuinely beyond the calendar still refuses rather than
    # truncating.
    with pytest.raises(ShadowScheduleError):
        resolve_target_session("2026-02-25", 10_000_000)


def test_trading_sessions_rejects_an_inverted_range():
    with pytest.raises(ShadowScheduleError, match="must not precede"):
        trading_sessions.__wrapped__ if False else trading_sessions(
            __import__("datetime").date(2026, 3, 1),
            __import__("datetime").date(2026, 2, 1),
        )


def test_planning_excludes_sessions_whose_target_exceeds_coverage():
    plan = plan_scheduled_sessions(start="2026-11-20", end="2026-12-04", horizon_sessions=5)
    assert plan
    for slot in plan:
        assert slot["target_session"] > slot["as_of_session"]
        assert slot["target_available_at"] > slot["decision_cutoff"]


# --- maturity ---------------------------------------------------------------


def _prediction(**overrides):
    payload = dict(
        prediction_id="p1",
        available=True,
        as_of_session="2026-02-25",
        horizon_sessions=20,
        target_available_at=resolve_target_availability("2026-02-25", 20),
    )
    payload.update(overrides)
    return payload


def test_a_target_that_has_not_arrived_is_pending_not_zero():
    """Recording a missing target as zero is indistinguishable from a model
    that predicted the outcome exactly."""
    decision = decide_maturity(_prediction(), now="2026-03-01T00:00:00+00:00")
    assert not decision.ready
    assert "Pending, not zero" in decision.reason
    assert decision.target_session == "2026-03-25"


def test_a_matured_target_is_ready():
    decision = decide_maturity(_prediction(), now="2026-04-01T00:00:00+00:00")
    assert decision.ready
    assert decision.reason is None


def test_maturity_is_exact_at_the_availability_instant():
    from datetime import datetime, timedelta

    available_at = resolve_target_availability("2026-02-25", 20)
    assert decide_maturity(_prediction(), now=available_at).ready
    one_second_early = (
        datetime.fromisoformat(available_at) - timedelta(seconds=1)
    ).isoformat()
    assert not decide_maturity(_prediction(), now=one_second_early).ready


def test_the_calendar_tracks_the_dst_change_between_cutoff_and_target():
    """16:00 ET is 21:00 UTC in February and 20:00 UTC in late March. A
    fixed UTC offset would make every post-DST target appear to mature an
    hour late -- or, worse, an hour early on the other side of the year."""
    cutoff = resolve_decision_cutoff("2026-02-25")          # EST
    target = resolve_target_availability("2026-02-25", 20)  # EDT
    assert cutoff.endswith("T21:00:00+00:00")
    assert target.endswith("T20:00:00+00:00")


def test_an_unavailable_prediction_never_matures():
    """It made no claim, so there is nothing to score; attaching an outcome
    would quietly convert a refusal into a data point."""
    decision = decide_maturity(_prediction(available=False), now="2026-06-01T00:00:00+00:00")
    assert not decision.ready
    assert "make no claim" in decision.reason


def test_a_prediction_without_recorded_target_availability_cannot_mature():
    decision = decide_maturity(
        _prediction(target_available_at=None), now="2026-06-01T00:00:00+00:00"
    )
    assert not decision.ready
    assert "cannot be reconstructed" in decision.reason


def test_a_naive_now_fails_closed():
    with pytest.raises(ShadowScheduleError, match="timezone-aware"):
        decide_maturity(_prediction(), now="2026-04-01T00:00:00")


def test_timezone_equivalent_now_values_agree():
    utc = decide_maturity(_prediction(), now="2026-03-25T21:00:00+00:00")
    eastern = decide_maturity(_prediction(), now="2026-03-25T17:00:00-04:00")
    assert utc.ready == eastern.ready is True


def test_maturity_decision_is_json_serializable():
    import json

    json.dumps(decide_maturity(_prediction(), now="2026-04-01T00:00:00+00:00").to_dict())


# --- lineage and epochs -----------------------------------------------------


def test_every_lineage_field_is_required():
    for field in (
        "model_artifact_hash", "evaluation_report_hash", "feature_set_version",
        "label_version", "data_provider_id", "configuration_hash",
        "code_commit", "schedule_version",
    ):
        with pytest.raises(ShadowScheduleError, match=field):
            _lineage(**{field: ""})


def test_the_epoch_name_derives_from_its_lineage():
    """A different lineage produces a different epoch name, so an epoch
    cannot be reused for a changed system even by accident."""
    base = epoch_key("vol:0.1.0", "volatility_forecast", _lineage())
    changed = epoch_key(
        "vol:0.1.0", "volatility_forecast", _lineage(model_artifact_hash="e" * 64)
    )
    assert base != changed
    assert base == epoch_key("vol:0.1.0", "volatility_forecast", _lineage())


def test_opening_the_same_epoch_twice_is_idempotent(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    first = _open_epoch(store)
    second = _open_epoch(store)
    assert first == second
    assert len(store.list_ml_evidence_epochs()) == 1


def test_a_second_active_epoch_for_one_model_task_is_refused(tmp_path):
    """Two active epochs would let predictions from different systems
    accumulate under one banner."""
    store = AssistantStore(tmp_path / "a.db")
    _open_epoch(store)
    with pytest.raises(ValueError, match="already has active epoch"):
        _open_epoch(store, evidence_epoch="a-different-name")


def test_reusing_an_epoch_name_with_different_lineage_is_refused(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    epoch = _open_epoch(store)
    with pytest.raises(ValueError, match="requires a NEW epoch"):
        store.open_ml_evidence_epoch(
            evidence_epoch=epoch["evidence_epoch"],
            model_key="vol:0.1.0", task="volatility_forecast",
            lineage=_lineage(data_provider_id="other-vendor"),
            created_by="test",
        )


def test_incomplete_lineage_is_refused(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    with pytest.raises(ValueError, match="missing required key"):
        store.open_ml_evidence_epoch(
            evidence_epoch="e1", model_key="m", task="t",
            lineage={"code_commit": "x"}, created_by="test",
        )


def test_a_closed_epoch_allows_a_new_one(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    first = _open_epoch(store)
    store.close_ml_evidence_epoch(first["evidence_epoch"], closed_at="2026-03-01T00:00:00+00:00")
    changed = _lineage(model_artifact_hash="f" * 64)
    second = _open_epoch(store, lineage=changed,
                         evidence_epoch=epoch_key("vol:0.1.0", "volatility_forecast", changed))
    assert second["status"] == "active"
    assert store.get_active_ml_evidence_epoch("vol:0.1.0", "volatility_forecast")[
        "evidence_epoch"
    ] == second["evidence_epoch"]


def test_closing_an_epoch_is_idempotent(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    epoch = _open_epoch(store)
    first = store.close_ml_evidence_epoch(epoch["evidence_epoch"], closed_at="2026-03-01T00:00:00+00:00")
    second = store.close_ml_evidence_epoch(epoch["evidence_epoch"], closed_at="2026-04-01T00:00:00+00:00")
    assert first == second


# --- shadow runs ------------------------------------------------------------


def _claim(store: AssistantStore, epoch: str, **overrides):
    kwargs = dict(
        schedule_key="volatility-daily",
        scheduled_for="2026-02-25T21:00:00+00:00",
        evidence_epoch=epoch,
        code_commit="d" * 40,
        configuration_hash="c" * 64,
        started_at="2026-02-25T21:05:00+00:00",
    )
    kwargs.update(overrides)
    return store.claim_ml_shadow_run(**kwargs)


def test_two_claims_on_one_slot_produce_one_run(tmp_path):
    """Plan 12.6: concurrent claims create one run."""
    store = AssistantStore(tmp_path / "a.db")
    epoch = _open_epoch(store)["evidence_epoch"]
    first = _claim(store, epoch)
    second = _claim(store, epoch)
    assert first["run_id"] == second["run_id"]
    assert len(store.list_ml_shadow_runs()) == 1


def test_a_conflicting_configuration_on_the_same_slot_is_loud(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    epoch = _open_epoch(store)["evidence_epoch"]
    _claim(store, epoch)
    with pytest.raises(ValueError, match="different configuration_hash"):
        _claim(store, epoch, configuration_hash="9" * 64)


def test_a_run_cannot_be_claimed_outside_a_registered_epoch(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    with pytest.raises(ValueError, match="does not exist"):
        _claim(store, "no-such-epoch")


def test_a_closed_epoch_cannot_accept_new_runs(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    epoch = _open_epoch(store)["evidence_epoch"]
    store.close_ml_evidence_epoch(epoch, closed_at="2026-03-01T00:00:00+00:00")
    with pytest.raises(ValueError, match="cannot accept new predictions"):
        _claim(store, epoch)


def test_completing_a_run_records_counts_and_is_idempotent(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    epoch = _open_epoch(store)["evidence_epoch"]
    run = _claim(store, epoch)
    first = store.complete_ml_shadow_run(
        run["run_id"], status="completed", prediction_count=8, unavailable_count=2,
        completed_at="2026-02-25T21:10:00+00:00",
    )
    second = store.complete_ml_shadow_run(
        run["run_id"], status="completed", prediction_count=8, unavailable_count=2,
        completed_at="2026-02-25T21:10:00+00:00",
    )
    assert first == second
    assert first["prediction_count"] == 8
    assert first["unavailable_count"] == 2


def test_rewriting_a_closed_run_with_different_counts_is_refused(tmp_path):
    """A crash-resume must not silently rewrite a completed run's counts."""
    store = AssistantStore(tmp_path / "a.db")
    epoch = _open_epoch(store)["evidence_epoch"]
    run = _claim(store, epoch)
    store.complete_ml_shadow_run(
        run["run_id"], status="completed", prediction_count=8, unavailable_count=0
    )
    with pytest.raises(ValueError, match="refusing to rewrite"):
        store.complete_ml_shadow_run(
            run["run_id"], status="completed", prediction_count=99, unavailable_count=0
        )


def test_a_failed_run_records_its_durable_error(tmp_path):
    """Plan 12.5: operational errors are durable."""
    store = AssistantStore(tmp_path / "a.db")
    epoch = _open_epoch(store)["evidence_epoch"]
    run = _claim(store, epoch)
    completed = store.complete_ml_shadow_run(
        run["run_id"], status="failed", prediction_count=0, unavailable_count=0,
        error={"kind": "artifact_hash_mismatch", "detail": "expected abc, got def"},
    )
    assert completed["status"] == "failed"
    assert completed["error"]["kind"] == "artifact_hash_mismatch"


def test_an_unknown_run_status_is_refused(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    epoch = _open_epoch(store)["evidence_epoch"]
    run = _claim(store, epoch)
    with pytest.raises(ValueError, match="'completed' or 'failed'"):
        store.complete_ml_shadow_run(
            run["run_id"], status="promoted", prediction_count=0, unavailable_count=0
        )


# --- predictions are bound to their epoch -----------------------------------


def _shadow_prediction(epoch: str, run_id: str, **overrides):
    payload = {
        "model_key": "vol:0.1.0",
        "task": "volatility_forecast",
        "subject_key": "NVDA",
        "as_of_session": "2026-02-25",
        "generated_at": "2026-02-25T21:05:00+00:00",
        "horizon_sessions": 20,
        "target_available_at": resolve_target_availability("2026-02-25", 20),
        "data_available_at": "2026-02-25T21:00:00+00:00",
        "feature_freshness": {"maximum_age_sessions": 0, "missing_count": 0, "stale_count": 0},
        "feature_snapshot_hash": "a" * 64,
        "evidence_status": "exploratory",
        "production_authoritative": False,
        "available": True,
        "values": {"annualized_volatility_pct": 30.0},
        "evidence_epoch": epoch,
        "shadow_run_id": run_id,
    }
    payload.update(overrides)
    return payload


def test_a_prediction_records_and_returns_its_epoch_and_run(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    store.register_ml_model("vol:0.1.0", {"model_id": "vol"})
    epoch = _open_epoch(store)["evidence_epoch"]
    run = _claim(store, epoch)
    stored = store.record_ml_prediction(_shadow_prediction(epoch, run["run_id"]))
    assert stored["evidence_epoch"] == epoch
    assert stored["shadow_run_id"] == run["run_id"]


def test_an_epoch_without_a_run_is_refused(tmp_path):
    """A prediction inside an epoch must be traceable to the run that made
    it, or the lineage the epoch provides is incomplete."""
    store = AssistantStore(tmp_path / "a.db")
    store.register_ml_model("vol:0.1.0", {"model_id": "vol"})
    epoch = _open_epoch(store)["evidence_epoch"]
    with pytest.raises(ValueError, match="must be supplied together"):
        store.record_ml_prediction(
            _shadow_prediction(epoch, "x", shadow_run_id=None)
        )


def test_predictions_from_different_epochs_are_never_pooled(tmp_path):
    """Plan 12.2: 'Do not pool across epochs.' A track record spanning a
    model change describes neither system."""
    store = AssistantStore(tmp_path / "a.db")
    store.register_ml_model("vol:0.1.0", {"model_id": "vol"})

    first_epoch = _open_epoch(store)["evidence_epoch"]
    first_run = _claim(store, first_epoch)
    store.record_ml_prediction(_shadow_prediction(first_epoch, first_run["run_id"]))
    store.close_ml_evidence_epoch(first_epoch, closed_at="2026-03-01T00:00:00+00:00")

    changed = _lineage(model_artifact_hash="f" * 64)
    second_epoch = _open_epoch(
        store, lineage=changed,
        evidence_epoch=epoch_key("vol:0.1.0", "volatility_forecast", changed),
    )["evidence_epoch"]
    second_run = _claim(
        store, second_epoch,
        scheduled_for="2026-02-26T21:00:00+00:00",
        started_at="2026-02-26T21:05:00+00:00",
    )
    store.record_ml_prediction(
        _shadow_prediction(
            second_epoch, second_run["run_id"], as_of_session="2026-02-26",
            generated_at="2026-02-26T21:05:00+00:00",
            data_available_at="2026-02-26T21:00:00+00:00",
            target_available_at=resolve_target_availability("2026-02-26", 20),
        )
    )

    assert len(store.list_ml_predictions()) == 2
    assert len(store.list_ml_predictions(evidence_epoch=first_epoch)) == 1
    assert len(store.list_ml_predictions(evidence_epoch=second_epoch)) == 1


def test_legacy_predictions_carry_a_null_epoch_rather_than_a_guessed_one(tmp_path):
    """Pre-shadow rows keep NULL, which is the honest answer: their lineage
    was never recorded and cannot be reconstructed."""
    store = AssistantStore(tmp_path / "a.db")
    store.register_ml_model("vol:0.1.0", {"model_id": "vol"})
    payload = _shadow_prediction("x", "y")
    payload.pop("evidence_epoch")
    payload.pop("shadow_run_id")
    stored = store.record_ml_prediction(payload)
    assert stored["evidence_epoch"] is None
    assert stored["shadow_run_id"] is None


# --- no execution state -----------------------------------------------------


def test_a_full_shadow_cycle_leaves_every_execution_table_unchanged(tmp_path):
    """Plan 12.6's final item."""
    store = AssistantStore(tmp_path / "a.db")
    store.register_ml_model("vol:0.1.0", {"model_id": "vol"})
    epoch = _open_epoch(store)["evidence_epoch"]
    run = _claim(store, epoch)
    prediction = store.record_ml_prediction(_shadow_prediction(epoch, run["run_id"]))
    store.record_ml_prediction_outcome(
        prediction["prediction_id"], {"realized_vol_pct": 27.5},
        matured_at=resolve_target_availability("2026-02-25", 20),
    )
    store.complete_ml_shadow_run(
        run["run_id"], status="completed", prediction_count=1, unavailable_count=0
    )

    assert store.list_proposals() == []
    with store._connect() as connection:
        for table in (
            "trade_proposals", "broker_orders", "broker_order_events",
            "execution_reservations", "allocation_batches",
        ):
            count = connection.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            assert count == 0, table


def test_the_shadow_module_imports_nothing_execution_capable():
    import ast
    import pathlib

    tree = ast.parse(pathlib.Path("ml/shadow.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    forbidden = ("execution", "risk", "assistant.execution_service",
                 "assistant.proposals", "assistant.storage")
    assert not [m for m in imported if any(m == f or m.startswith(f + ".") for f in forbidden)]
