import dataclasses
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.mandate import (
    compute_mandate_fingerprint,
    evaluate_live_promotion,
    evaluate_mandate_metrics,
    load_mandate,
)


def test_default_mandate_is_valid_but_deliberately_not_approved():
    mandate = load_mandate()
    assert mandate.status == "proposed"
    assert mandate.allow_autonomous_execution is False
    assert len(compute_mandate_fingerprint(mandate)) == 64


def test_approved_mandate_is_bound_to_its_behavior_fields(tmp_path):
    proposed = load_mandate()
    approved = dataclasses.replace(
        proposed,
        status="approved",
        approved_at="2026-07-29T12:00:00+00:00",
        approved_by="owner",
    )
    approved = dataclasses.replace(
        approved,
        approved_fingerprint=compute_mandate_fingerprint(approved),
    )
    path = tmp_path / "mandate.json"
    path.write_text(json.dumps(approved.to_dict()), encoding="utf-8")
    assert load_mandate(path).status == "approved"

    changed = approved.to_dict()
    changed["max_drawdown_pct"] = changed["max_drawdown_pct"] + 1
    path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="approved_fingerprint"):
        load_mandate(path)


def test_mandate_metric_scorecard_fails_closed_on_missing_metric():
    mandate = load_mandate()
    result = evaluate_mandate_metrics(
        mandate,
        {
            "annualized_volatility_pct": 15,
            "max_drawdown_pct": -20,
            "max_time_under_water_sessions": 100,
            "downside_capture_pct": 60,
        },
    )
    assert result["passed"] is False
    upside = next(
        check
        for check in result["checks"]
        if check["name"] == "upside_capture_pct"
    )
    assert upside["available"] is False


def test_proposed_mandate_can_never_pass_live_promotion():
    result = evaluate_live_promotion(
        load_mandate(),
        metric_report={
            "annualized_volatility_pct": 15,
            "max_drawdown_pct": -20,
            "max_time_under_water_sessions": 100,
            "downside_capture_pct": 60,
            "upside_capture_pct": 80,
        },
        paper_sessions=100,
        paper_orders=100,
        unreconciled_items=0,
        critical_alerts=0,
        research_reproduced=True,
        point_in_time_data=True,
        backup_restore_drill_passed=True,
        operational_health_passed=True,
        paper_evidence_integrity_passed=True,
        operational_drills_passed=True,
    )
    assert result["ready_for_live_canary_review"] is False
    assert result["does_not_enable_live_trading"] is True
