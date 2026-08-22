import dataclasses
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.mandate import (
    PortfolioMandate as AssistantPortfolioMandate,
    compute_mandate_fingerprint,
    evaluate_live_promotion,
    evaluate_mandate_metrics,
    load_mandate,
)
from data.portfolio_mandate import PortfolioMandate, load_portfolio_mandate


def test_assistant_mandate_facade_preserves_contract_identity_and_load_behavior():
    assert AssistantPortfolioMandate is PortfolioMandate
    assert load_mandate().to_dict() == load_portfolio_mandate(
        Path(__file__).resolve().parent.parent / "assistant" / "default_mandate.json"
    ).to_dict()


def test_default_mandate_is_owner_approved_with_bound_fingerprint():
    """Contract change 2026-08-04: the owner explicitly approved the
    mandate (Phase 5 decision) with targets unchanged from the proposed
    defaults. The old expectation ("deliberately not approved") described
    the pre-decision state; what must now hold is that the approval is
    complete, fingerprint-bound to the behavior fields, and still grants
    no autonomy."""
    mandate = load_mandate()
    assert mandate.status == "approved"
    assert mandate.approved_by == "sheltonchen"
    assert mandate.approved_at
    assert mandate.approved_fingerprint == compute_mandate_fingerprint(mandate)
    # Approval must never flip the permanent human-approval boundary.
    assert mandate.allow_autonomous_execution is False


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


def test_mandate_metric_scorecard_rejects_a_stray_boolean_metric():
    # Independent review, 2026-07-31 (P2 #5): float(actual) alone doesn't
    # exclude bool before casting -- isinstance(True, int) is True, so
    # float(True) == 1.0 would silently coerce instead of being rejected.
    mandate = load_mandate()
    result = evaluate_mandate_metrics(
        mandate,
        {
            "annualized_volatility_pct": 15,
            "max_drawdown_pct": True,  # stray boolean, not a real metric
            "max_time_under_water_sessions": 100,
            "downside_capture_pct": 60,
            "upside_capture_pct": 90,
        },
    )
    drawdown = next(
        check for check in result["checks"] if check["name"] == "max_drawdown_pct"
    )
    assert drawdown["available"] is False
    assert drawdown["actual"] is None
    assert drawdown["passed"] is False


def test_proposed_mandate_can_never_pass_live_promotion():
    """The default mandate is now approved, so this safety invariant is
    exercised on an explicitly-constructed proposed variant: an unapproved
    mandate must fail the gate even when every other input is perfect."""
    proposed = dataclasses.replace(
        load_mandate(),
        status="proposed",
        approved_at=None,
        approved_by=None,
        approved_fingerprint=None,
    )
    result = evaluate_live_promotion(
        proposed,
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
