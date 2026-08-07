"""GR-0 readiness taxonomy.

Every status is proven from fixtures. "All five dimensions are currently
blocked" is an OBSERVED result of this machine's state, not an expectation
baked into the tests -- pinning it would make the suite pass forever
without proving the ready/degraded paths ever work.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from assistant.platform_readiness import (
    BLOCKED,
    DEGRADED,
    DIMENSIONS,
    EVIDENCE_READINESS,
    EXECUTION_INTEGRITY,
    OPERATIONAL_READINESS,
    READY,
    STRATEGY_READINESS,
    PlatformReadinessError,
    build_data_integrity,
    build_evidence_readiness,
    build_execution_integrity,
    build_operational_readiness,
    build_platform_readiness,
    build_strategy_readiness,
)
from assistant.mandate import load_mandate
from assistant.policy import load_policy
from assistant.storage import AssistantStore

NOW = datetime(2026, 8, 2, 12, tzinfo=timezone.utc)


def _health(checks):
    return {"checked_at": NOW.isoformat(), "checks": list(checks), "healthy": False}


def _check(name, ok, *, severity="warning", category="transaction_readiness"):
    return {
        "name": name,
        "ok": ok,
        "detail": f"{name} detail",
        "severity": severity,
        "category": category,
    }


_TRANSACTION_CHECKS = (
    "policy",
    "policy_execution_mode",
    "database_integrity",
    "environment_kill_switch",
    "persistent_kill_switch",
    "ambiguous_broker_outcomes",
    "active_order_budget",
    "stranded_pre_broker_claims",
    "reconciliation_freshness",
    "daily_submission_budget",
    "broker_account",
    "broker_open_order_budget",
)


def _execution_health(*overrides):
    by_name = {name: _check(name, True) for name in _TRANSACTION_CHECKS}
    by_name["portfolio_ledger_reconciliation"] = _check(
        "portfolio_ledger_reconciliation",
        True,
        severity="critical",
        category="portfolio_accounting",
    )
    for override in overrides:
        by_name[override["name"]] = override
    return _health(by_name.values())


# --- status derivation, each proven independently ------------------------


def test_execution_integrity_is_ready_when_every_check_passes():
    assert build_execution_integrity(_execution_health()).status == READY


def test_every_execution_failure_is_blocking_even_with_a_warning_label():
    dimension = build_execution_integrity(
        _execution_health(_check("daily_submission_budget", False))
    )
    assert dimension.status == BLOCKED
    assert any("daily_submission_budget" in item for item in dimension.blockers)


def test_an_engaged_kill_switch_blocks_despite_its_warning_label():
    """The specific bug a blanket severity mapping would have shipped.

    operational_health() labels both kill-switch checks "warning". If this
    report inherited that, an engaged emergency stop would be reported as
    degraded -- platform impaired but operable -- which is the opposite of
    what an engaged kill switch means.
    """
    for name in ("environment_kill_switch", "persistent_kill_switch"):
        health = _execution_health(_check(name, False, severity="warning"))
        dimension = build_execution_integrity(health)
        assert dimension.status == BLOCKED, name
        assert any(name in blocker for blocker in dimension.blockers)


def test_a_failing_dimension_cannot_be_masked_by_passing_ones():
    broken = _check("ambiguous_broker_outcomes", False, severity="critical")
    dimension = build_execution_integrity(_execution_health(broken, *[
        _check(f"fine_{i}", True) for i in range(20)
    ]))
    assert dimension.status == BLOCKED


def test_ledger_reconciliation_belongs_to_execution_integrity():
    broken = _check(
        "portfolio_ledger_reconciliation",
        False,
        severity="critical",
        category="portfolio_accounting",
    )
    health = _execution_health(broken)
    execution = build_execution_integrity(health)
    operations = build_operational_readiness(health)
    assert execution.status == BLOCKED
    assert any("portfolio_ledger_reconciliation" in item for item in execution.blockers)
    assert all(
        check.name != "portfolio_ledger_reconciliation" for check in operations.checks
    )


def test_missing_offline_broker_checks_remain_blocked():
    health = _execution_health()
    health["checks"] = [
        check
        for check in health["checks"]
        if check["name"] not in {"broker_account", "broker_open_order_budget"}
    ]
    dimension = build_execution_integrity(health)
    assert dimension.status == BLOCKED
    assert any("broker_account" in item for item in dimension.blockers)


def test_empty_delegated_output_is_blocked_not_ready():
    """No checks means nothing was verified, which is not the same as fine."""
    assert build_execution_integrity(_health([])).status == BLOCKED


def test_malformed_delegated_output_is_refused():
    with pytest.raises(PlatformReadinessError):
        build_execution_integrity({"checked_at": NOW.isoformat()})
    with pytest.raises(PlatformReadinessError):
        build_execution_integrity(_health([{"detail": "no name or ok"}]))
    with pytest.raises(PlatformReadinessError):
        build_execution_integrity(
            _health([_check("database_integrity", "false", severity="critical")])
        )


def test_operational_readiness_honours_the_producers_severity_split():
    """Outside execution safety, the source's critical/warning split is right."""
    stale_backup = _check("backup", False, severity="warning", category="recovery")
    assert build_operational_readiness(_health([stale_backup])).status == DEGRADED

    corrupt = _check(
        "portfolio_ledger_reconciliation", False,
        severity="critical", category="portfolio_accounting",
    )
    assert build_operational_readiness(_health([corrupt])).status == BLOCKED


# --- data integrity and the import boundary ------------------------------


def test_absent_adjustment_evidence_is_blocked_never_assumed():
    dimension = build_data_integrity()
    assert dimension.status == BLOCKED
    assert {check.name for check in dimension.checks} == {
        "price_freshness",
        "provider_health",
        "adjustment_honesty",
    }
    assert all(not check.ok and check.mandatory for check in dimension.checks)


def test_data_integrity_cannot_be_turned_ready_by_a_caller_assertion():
    with pytest.raises(TypeError):
        build_data_integrity(True)


def test_platform_readiness_does_not_import_ml():
    """assistant/ may not reach into ml/ for adjustment evidence."""
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent
              / "assistant" / "platform_readiness.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        for name in names:
            assert name != "ml" and not name.startswith("ml."), name


# --- evidence: absent and invalid are distinct ---------------------------


def test_absent_evidence_and_invalid_evidence_are_both_blocked_but_distinct(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    absent = build_evidence_readiness(store, load_mandate())
    assert absent.status == BLOCKED
    assert "absent" in absent.blockers[0]

    class _CorruptStore:
        def get_active_paper_evidence_epoch(self):
            raise sqlite_error()

    def sqlite_error():
        import sqlite3

        return sqlite3.DatabaseError("file is not a database")

    unreadable = build_evidence_readiness(_CorruptStore(), load_mandate())
    assert unreadable.status == BLOCKED
    assert "unreadable" in unreadable.blockers[0]
    # The two situations demand different responses, so they must not share
    # an explanation.
    assert absent.blockers[0] != unreadable.blockers[0]


def test_one_paper_session_does_not_satisfy_the_mandate(monkeypatch):
    class _Store:
        def get_active_paper_evidence_epoch(self):
            return {"evidence_epoch": "paper-one"}

    monkeypatch.setattr(
        "assistant.platform_readiness.paper_evidence_summary",
        lambda *_: {
            "evidence_epoch": "paper-one",
            "paper_sessions": 1,
            "paper_orders": {"count": 1},
            "coverage_complete": True,
            "lineage_consistent": True,
        },
    )
    dimension = build_evidence_readiness(_Store(), load_mandate())
    assert dimension.status == BLOCKED
    assert any("1/60" in item for item in dimension.blockers)
    assert any("1/30" in item for item in dimension.blockers)


def test_malformed_evidence_counts_are_blocked_not_coerced(monkeypatch):
    class _Store:
        def get_active_paper_evidence_epoch(self):
            return {"evidence_epoch": "paper-malformed"}

    monkeypatch.setattr(
        "assistant.platform_readiness.paper_evidence_summary",
        lambda *_: {
            "evidence_epoch": "paper-malformed",
            "paper_sessions": "60",
            "paper_orders": {"count": 30},
            "coverage_complete": "true",
            "lineage_consistent": True,
        },
    )
    dimension = build_evidence_readiness(_Store(), load_mandate())
    assert dimension.status == BLOCKED
    assert "malformed" in dimension.blockers[0]


# --- strategy readiness ---------------------------------------------------


class _Finding:
    def __init__(self, verdict, authoritative):
        self.status = type("S", (), {"value": verdict})()
        self.production_authoritative = authoritative


def test_strategy_readiness_requires_confirmed_and_authoritative():
    # A production-authoritative REJECTION is real evidence, and says
    # nothing about a strategy being ready. Thirteen currently exist.
    assert build_strategy_readiness(
        [_Finding("rejected", True) for _ in range(13)]
    ).status == BLOCKED

    # A confirmed finding that has not been re-verified is not enough.
    assert build_strategy_readiness([_Finding("confirmed", False)]).status == BLOCKED

    # Both together are.
    assert build_strategy_readiness([_Finding("confirmed", True)]).status == READY

    # One valid finding must not hide corruption elsewhere in the registry.
    assert build_strategy_readiness([
        _Finding("confirmed", True), _Finding("invented_status", True)
    ]).status == BLOCKED


def test_strategy_readiness_is_blocked_against_the_real_registry():
    """Observed, not assumed: recorded so a future change is visible."""
    assert build_strategy_readiness().status == BLOCKED


# --- whole report ---------------------------------------------------------


def test_report_covers_every_dimension_and_is_json_serializable(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    report = build_platform_readiness(
        store, load_policy(), load_mandate(), now=NOW, check_broker=False
    )
    assert tuple(d.dimension for d in report.dimensions) == DIMENSIONS
    payload = report.to_dict()
    assert json.loads(json.dumps(payload)) == payload


def test_whole_report_turns_operational_failure_into_blocked_dimensions(
    tmp_path, monkeypatch
):
    store = AssistantStore(tmp_path / "a.db")

    def _broken_health(*args, **kwargs):
        raise RuntimeError("health delegate failed")

    monkeypatch.setattr(
        "assistant.platform_readiness.operational_health", _broken_health
    )
    report = build_platform_readiness(
        store, load_policy(), load_mandate(), now=NOW, check_broker=False
    )
    assert report.dimension(EXECUTION_INTEGRITY).status == BLOCKED
    assert report.dimension(OPERATIONAL_READINESS).status == BLOCKED
    assert "health delegate failed" in report.dimension(
        EXECUTION_INTEGRITY
    ).blockers[0]


def test_required_alert_delivery_drill_is_part_of_operational_readiness(
    tmp_path, monkeypatch
):
    store = AssistantStore(tmp_path / "a.db")
    summary = {
        "evidence_epoch": "paper-drills",
        "paper_sessions": 60,
        "paper_orders": {"count": 30},
        "coverage_complete": True,
        "lineage_consistent": True,
        "required_drills": {
            name: {"passed": name != "alert_delivery"}
            for name in (
                "kill_switch",
                "ambiguous_submission",
                "restart_recovery",
                "backup_restore",
                "alert_delivery",
            )
        },
    }
    monkeypatch.setattr(
        "assistant.platform_readiness._load_paper_summary",
        lambda *_: (summary, None),
    )
    report = build_platform_readiness(
        store, load_policy(), load_mandate(), now=NOW, check_broker=False
    )
    operations = report.dimension(OPERATIONAL_READINESS)
    assert operations.status == BLOCKED
    assert any("drill_alert_delivery" in item for item in operations.blockers)


def test_report_carries_no_aggregate_score(tmp_path):
    """An average lets a strong dimension hide a fatal one."""
    store = AssistantStore(tmp_path / "a.db")
    payload = build_platform_readiness(
        store, load_policy(), load_mandate(), now=NOW, check_broker=False
    ).to_dict()
    assert set(payload) == {"checked_at", "dimensions"}
    for forbidden in ("score", "ready", "healthy", "overall", "percent", "passed"):
        assert forbidden not in payload


def test_report_is_hash_stable_for_fixed_inputs(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    first = build_platform_readiness(
        store, load_policy(), load_mandate(), now=NOW, check_broker=False
    )
    second = build_platform_readiness(
        store, load_policy(), load_mandate(), now=NOW, check_broker=False
    )
    assert json.dumps(first.to_dict(), sort_keys=True) == json.dumps(
        second.to_dict(), sort_keys=True
    )


def test_report_creates_no_proposal_order_or_execution_state(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    tables = (
        "trade_proposals",
        "broker_orders",
        "broker_order_events",
        "execution_reservations",
        "allocation_batches",
        "operational_alerts",
    )

    def counts():
        with store._connect() as connection:
            return {
                t: connection.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in tables
            }

    before = counts()
    build_platform_readiness(
        store, load_policy(), load_mandate(), now=NOW, check_broker=False
    )
    assert counts() == before, "platform-readiness must be strictly read-only"


def test_now_must_be_timezone_aware(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    with pytest.raises(PlatformReadinessError):
        build_platform_readiness(
            store,
            load_policy(),
            load_mandate(),
            now=datetime(2026, 8, 2, 12),
            check_broker=False,
        )
