"""Current-state documents must not retain known contradictory status claims."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _text(name: str) -> str:
    return " ".join((ROOT / "docs" / name).read_text(encoding="utf-8").split())


def test_active_plan_agrees_on_epoch_and_completed_ui_milestones():
    plan = _text("ACTION_PLAN_2026-08-02.md")
    assert "`paper-epoch-002` has been active since 2026-08-06" in plan
    assert "19 statuses, no `dismissed`" not in plan
    assert "no Backtest tab" not in plan
    assert "GR-7a through GR-7c are also complete" in plan


def test_current_readiness_and_runbook_do_not_call_completed_work_unstarted():
    readiness = _text("GENERAL_READINESS_STATUS.md")
    runbook = _text("OPERATIONS_RUNBOOK.md")
    assert "GR-6 .. GR-9 — not started" not in readiness
    assert "GR-7a through GR-7c are complete" in readiness
    assert "alert_delivery` remains unproducible" not in runbook
    assert "`alert_delivery` is produced by GR-5" in runbook


def test_full_sweep_record_has_one_final_finding_count_and_status():
    review = _text("REVIEW_2026-08-07_FULL_CODEBASE_SWEEP.md")
    assert "ALL SEVENTEEN findings are FIXED" not in review
    assert "ALL EIGHTEEN findings were fixed" in review
    assert "Everything else remains open and" not in review
    assert "all twelve P3s are recorded but unfixed" not in review
