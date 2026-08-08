import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from assistant.operations import (
    ensure_recent_database_backup,
    run_backup_restore_drill,
    run_operational_check,
)
from assistant.paper_evidence import (
    build_paper_lineage,
    start_paper_evidence_epoch,
)
from assistant.policy import load_policy
from assistant.storage import AssistantStore


def test_operational_failures_are_durable_and_deduplicated(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    policy = load_policy()
    now = datetime(2026, 7, 29, tzinfo=timezone.utc)
    first = run_operational_check(
        store, policy, now=now, check_broker=False
    )
    assert first["healthy"] is False
    assert first["alerts"]
    second = run_operational_check(
        store, policy, now=now, check_broker=False
    )
    open_alerts = store.list_operational_alerts()
    assert len(open_alerts) == len(first["alerts"])
    assert all(alert["occurrences"] == 2 for alert in open_alerts)
    assert second["heartbeat"]["emitted_alert_count"] == len(open_alerts)

    alert_id = open_alerts[0]["alert_id"]
    assert store.acknowledge_operational_alert(alert_id) is True
    assert store.acknowledge_operational_alert(alert_id) is False


def test_backup_restore_drill_verifies_integrity_and_counts(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    store.set_system_state("example", {"ok": True})
    report = run_backup_restore_drill(
        store, tmp_path / "backups" / "drill.db"
    )
    assert report["passed"] is True
    assert report["source_integrity"] == ["ok"]
    assert report["restored_integrity"] == ["ok"]
    assert report["table_counts_match"] is True
    assert store.get_system_state("last_backup_restore_drill")["passed"] is True


def test_backup_cadence_is_idempotent_and_drill_is_epoch_evidence(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    start_paper_evidence_epoch(
        store,
        "paper-v1",
        build_paper_lineage(
            code_commit="a" * 40,
            mandate_fingerprint="b" * 64,
            policy_fingerprint="c" * 64,
            strategy_id="scanner",
            strategy_version="1.0.0",
            model_id="deterministic-no-model",
            broker_account_id="paper-account-1",
        ),
        started_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
    )
    first = ensure_recent_database_backup(
        store, tmp_path / "backups"
    )
    second = ensure_recent_database_backup(
        store, tmp_path / "backups"
    )
    assert first["created"] is True
    assert second["created"] is False

    run_backup_restore_drill(
        store, tmp_path / "backups" / "restore-drill.db"
    )
    drills = store.list_operational_drills(evidence_epoch="paper-v1")
    assert drills[0]["drill_type"] == "backup_restore"
    assert drills[0]["passed"] is True


# --------------------------------------------------------------------------
# FCS-017: a future-dated timestamp must never read as fresh.
#
# `now - at <= limit` is True for any `at` in the future, so clock skew, a
# timezone misconfiguration, or a hand-inserted row made a stale operational
# control look current. `ml/evidence_operations.py` guards the SAME backup and
# restore-drill facts with `timedelta(0) <= ...`; `assistant/operations.py`
# did not, so the platform could report the backup fresh and stale at once
# depending which report you read.
# --------------------------------------------------------------------------

def test_a_future_dated_control_is_not_fresh():
    from datetime import timedelta

    now = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
    future = now + timedelta(days=5)
    limit = timedelta(days=30)

    # The corrected form, as written at every site now.
    assert not (timedelta(0) <= now - future <= limit)
    # The form that shipped, for contrast -- this is what read as fresh.
    assert now - future <= limit


@pytest.mark.parametrize(
    "expression",
    [
        "now - reconciliation_at",
        "now - backup_at",
        "now - drill_at",
    ],
)
def test_every_operational_freshness_check_is_bounded_below(expression):
    """Source-level: the invariant is 'no site may omit the lower bound'.

    A behavioural test can only cover the sites it happens to name; this
    fails when a NEW freshness check is added without the guard, which is how
    the four fixed here diverged from their five guarded siblings.
    """
    source = (
        Path(__file__).resolve().parent.parent / "assistant" / "operations.py"
    ).read_text(encoding="utf-8")
    assert expression in source, f"{expression} no longer exists; update this test"
    for line_number, line in enumerate(source.splitlines(), 1):
        if expression in line and "timedelta" in line:
            assert "timedelta(0)" in line, (
                f"assistant/operations.py:{line_number} compares {expression} "
                "against an upper bound only; a future-dated timestamp reads "
                "as fresh (FCS-017)"
            )


def test_readiness_reconciliation_freshness_is_bounded_below():
    source = (
        Path(__file__).resolve().parent.parent / "assistant" / "readiness.py"
    ).read_text(encoding="utf-8")
    assert "timedelta(0)\n        <= now - reconciled_at" in source, (
        "readiness.py's reconciliation freshness must reject a future "
        "timestamp (FCS-017)"
    )
