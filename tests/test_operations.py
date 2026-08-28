import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import assistant.operations as operations_module
import assistant.readiness as readiness_module
from assistant.operations import (
    ensure_recent_database_backup,
    operational_health,
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


def test_operational_timestamp_parser_refuses_naive_or_non_temporal_values():
    class EqualityTrap:
        def __eq__(self, _other):
            raise AssertionError("non-temporal values must be rejected by type")

    assert operations_module._parse_timestamp("2026-08-27T12:00:00") is None
    assert operations_module._parse_timestamp(12345) is None
    assert operations_module._parse_timestamp(EqualityTrap()) is None
    assert readiness_module._parse_timestamp(EqualityTrap()) is None
    parsed = operations_module._parse_timestamp("2026-08-27T12:00:00-07:00")
    assert parsed == datetime(2026, 8, 27, 19, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "value",
    (
        "0001-01-01T00:00:00+14:00",
        "9999-12-31T23:59:59.999999-14:00",
    ),
)
def test_operational_timestamp_parsers_refuse_utc_normalization_overflow(value):
    assert operations_module._parse_timestamp(value) is None
    assert readiness_module._parse_timestamp(value) is None


def test_operational_numeric_limits_normalize_huge_integers_to_operations_error():
    policy = load_policy()
    with pytest.raises(operations_module.OperationsError, match="positive and finite"):
        operational_health(
            object(),
            policy,
            check_broker=False,
            max_backup_age_hours=10**10000,
        )
    with pytest.raises(operations_module.OperationsError, match="positive and finite"):
        ensure_recent_database_backup(
            object(),
            Path("unused"),
            max_age_hours=10**10000,
        )


@pytest.mark.parametrize(
    "age_name",
    [
        "reconciliation_age",
        "backup_age",
        "drill_age",
    ],
)
def test_every_operational_freshness_check_is_bounded_below(age_name):
    """Source-level: the invariant is 'no site may omit the lower bound'.

    A behavioural test can only cover the sites it happens to name; this
    fails when a NEW freshness check is added without the guard, which is how
    the four fixed here diverged from their five guarded siblings.
    """
    source = (
        Path(__file__).resolve().parent.parent / "assistant" / "operations.py"
    ).read_text(encoding="utf-8")
    assert f"timedelta(0) <= {age_name}" in source, (
        f"{age_name} lacks the lower-bound freshness guard; a future-dated "
        "timestamp would read as fresh (FCS-017)"
    )


def test_readiness_reconciliation_freshness_is_bounded_below():
    source = (
        Path(__file__).resolve().parent.parent / "assistant" / "readiness.py"
    ).read_text(encoding="utf-8")
    assert "timedelta(0)\n        <= reconciliation_age" in source, (
        "readiness.py's reconciliation freshness must reject a future "
        "timestamp (FCS-017)"
    )


def test_health_freshness_uses_a_clock_captured_after_each_state_read(
    tmp_path, monkeypatch
):
    """AP-7: a concurrent valid write must not look future-dated.

    The production check used one ``now`` captured before readiness/broker
    work. A concurrent process could then commit a reconciliation, backup, or
    drill a second later; the correct lower-bound guard treated that newly
    read row as future-dated and raised a false critical/warning alert. Keep
    rejecting genuine clock-skewed future rows, but compare each stored fact
    with a clock captured immediately after reading that fact.
    """
    store = AssistantStore(tmp_path / "assistant.db")
    policy = load_policy()
    started_at = datetime(2026, 8, 10, 21, 52, 21, tzinfo=timezone.utc)
    committed_at = started_at + timedelta(seconds=1)

    store.record_ledger_reconciliation(
        "concurrent-reconciliation",
        "alpaca",
        {
            "reconciliation_id": "concurrent-reconciliation",
            "reconciled_at": committed_at.isoformat(),
            "matched": True,
            "mismatch_count": 0,
        },
    )
    backup_path = store.backup_to(tmp_path / "backup.db")
    store.set_system_state(
        "last_database_backup",
        {"completed_at": committed_at.isoformat(), "path": str(backup_path)},
    )
    store.set_system_state(
        "last_backup_restore_drill",
        {"completed_at": committed_at.isoformat(), "passed": True},
    )

    class AdvancingDateTime(datetime):
        calls = 0

        @classmethod
        def now(cls, tz=None):
            cls.calls += 1
            value = started_at if cls.calls == 1 else started_at + timedelta(seconds=2)
            return value if tz is None else value.astimezone(tz)

    monkeypatch.setattr(operations_module, "datetime", AdvancingDateTime)
    report = operational_health(store, policy, check_broker=False)
    by_name = {check["name"]: check for check in report["checks"]}

    for name in (
        "portfolio_ledger_reconciliation",
        "database_backup",
        "backup_restore_drill",
    ):
        assert by_name[name]["ok"] is True, by_name[name]
        assert "age_seconds=" in by_name[name]["detail"]

    # An explicit historical/as-of clock is intentionally frozen. The same
    # rows are genuinely future-dated relative to it and must still refuse.
    future_report = operational_health(
        store, policy, check_broker=False, now=started_at
    )
    future_by_name = {
        check["name"]: check for check in future_report["checks"]
    }
    for name in (
        "portfolio_ledger_reconciliation",
        "database_backup",
        "backup_restore_drill",
    ):
        assert future_by_name[name]["ok"] is False
        assert "age_seconds=-1.000000" in future_by_name[name]["detail"]


def test_readiness_freshness_uses_a_clock_captured_after_the_state_read(
    tmp_path, monkeypatch
):
    """AP-7, second instance (counter-review): same race, wider window.

    `assistant/operations.py` was corrected to compare each stored fact
    against a clock captured after reading it, but `transaction_readiness`
    kept its entry clock -- and it is the MORE exposed site: the deployed
    `monitor-orders` task rewrites `last_order_reconciliation` every 30
    seconds, while the window between this function's entry clock and that
    read contains a full SQLite integrity check and several proposal
    queries. A valid concurrent write therefore looked future-dated and
    failed the `timedelta(0) <=` guard, and because `operational_health`
    reports `healthy = all(check["ok"])`, a *warning*-severity readiness
    check still made the scheduled operations cycle exit nonzero.
    """
    import assistant.readiness as readiness_module
    from assistant.readiness import transaction_readiness

    store = AssistantStore(tmp_path / "assistant.db")
    policy = load_policy()
    started_at = datetime(2026, 8, 10, 21, 52, 21, tzinfo=timezone.utc)
    committed_at = started_at + timedelta(seconds=1)

    store.set_system_state(
        "last_order_reconciliation",
        {"at": committed_at.isoformat(), "checked": 0, "updated": 0, "error_count": 0},
    )

    class AdvancingDateTime(datetime):
        calls = 0

        @classmethod
        def now(cls, tz=None):
            cls.calls += 1
            value = started_at if cls.calls == 1 else started_at + timedelta(seconds=2)
            return value if tz is None else value.astimezone(tz)

    monkeypatch.setattr(readiness_module, "datetime", AdvancingDateTime)
    report = transaction_readiness(store, policy, check_broker=False)
    freshness = {c["name"]: c for c in report["checks"]}["reconciliation_freshness"]
    assert freshness["ok"] is True, freshness
    assert "age_seconds=" in freshness["detail"]

    # An explicit as-of clock stays frozen: the row is genuinely future-dated
    # relative to it and must still refuse (FCS-017 unchanged).
    frozen = transaction_readiness(
        store, policy, check_broker=False, now=started_at
    )
    frozen_freshness = {
        c["name"]: c for c in frozen["checks"]
    }["reconciliation_freshness"]
    assert frozen_freshness["ok"] is False
    assert "age_seconds=-1.000000" in frozen_freshness["detail"]


def test_the_production_call_path_does_not_freeze_the_readiness_clock(
    tmp_path, monkeypatch
):
    """AP-11 (observed in production 2026-08-13T05:40Z on epoch-004).

    Both AP-7 fixes above are correct at their own sites, but the two tests
    above call each function DIRECTLY with ``now=None`` -- and production
    never does. The deployed watchdog and operations cycle reach
    ``transaction_readiness`` only through ``operational_health``, which did
    ``now = now or datetime.now(...)`` at entry and then passed that
    manufactured clock DOWN as an explicit ``now``. The inner function
    cannot distinguish it from a genuine caller-frozen as-of clock, so
    every production run took the frozen branch, re-arming the exact race:
    monitor-orders committed ``last_order_reconciliation`` 0.117 s after
    the entry clock, the read happened ~5 s later behind the integrity and
    broker checks, and a healthy reconciliation was alerted as future-dated
    (age_seconds=-0.117315) with ``healthy=False`` failing the cycle.

    The distinction that matters: ``explicit_now`` means THE CALLER of the
    outermost entry point supplied a clock, so it must be forwarded, not
    manufactured mid-chain. This test drives the production shape end to
    end; the direct-call tests above cannot detect the regression.
    """
    import assistant.readiness as readiness_module

    store = AssistantStore(tmp_path / "assistant.db")
    policy = load_policy()
    started_at = datetime(2026, 8, 13, 5, 40, 44, 639241, tzinfo=timezone.utc)
    committed_at = started_at + timedelta(seconds=1)

    store.set_system_state(
        "last_order_reconciliation",
        {"at": committed_at.isoformat(), "checked": 0, "updated": 0, "error_count": 0},
    )

    class AdvancingDateTime(datetime):
        # Shared across BOTH modules deliberately: the first now() anywhere in
        # the chain is the entry clock, every later one is post-read.
        calls = 0

        @classmethod
        def now(cls, tz=None):
            cls.calls += 1
            value = started_at if cls.calls == 1 else started_at + timedelta(seconds=5)
            return value if tz is None else value.astimezone(tz)

    monkeypatch.setattr(operations_module, "datetime", AdvancingDateTime)
    monkeypatch.setattr(readiness_module, "datetime", AdvancingDateTime)

    report = operational_health(store, policy, check_broker=False)
    freshness = {c["name"]: c for c in report["checks"]}["reconciliation_freshness"]
    assert freshness["ok"] is True, (
        "a reconciliation committed 1 s after operational_health's entry "
        f"clock is CONCURRENT, not future-dated: {freshness}"
    )

    # A genuinely caller-supplied as-of clock must stay frozen through the
    # whole chain: the same row is future-dated relative to it and must
    # refuse at the nested readiness check too (FCS-017 unchanged).
    frozen = operational_health(
        store, policy, check_broker=False, now=started_at
    )
    frozen_freshness = {
        c["name"]: c for c in frozen["checks"]
    }["reconciliation_freshness"]
    assert frozen_freshness["ok"] is False
    assert "age_seconds=-1.000000" in frozen_freshness["detail"]
