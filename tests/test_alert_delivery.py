"""GR-5 alert delivery: the plan's section 10.3 contract, behaviorally.

Owner channel decision (2026-08-03): Windows desktop notification is the
mandatory immediate channel for `critical`; `warning` batches into the daily
briefing; webhook is out of scope.

Every test here uses a real `AssistantStore` and the real delivery
functions; only the notification channel is substituted, because a test
must never actually toast the operator. The Windows channel itself is
covered by its failure directions (no PowerShell / nonzero exit), never by
raising a real notification.

Run with: python -m pytest tests/test_alert_delivery.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.alert_delivery import (
    DELIVERY_FAILURE_FINGERPRINT,
    SELF_TEST_FINGERPRINT,
    RecordingChannel,
    WindowsToastChannel,
    deliver_alert,
    deliver_pending_alerts,
    needs_delivery,
    pending_briefing_alerts,
    run_channel_self_test,
    self_test_freshness,
    undelivered_critical_alerts,
)
from assistant.operations import run_operational_check
from assistant.platform_readiness import build_alert_delivery_checks
from assistant.policy import load_policy
from assistant.storage import AssistantStore

NOW = datetime(2026, 8, 3, 18, 0, tzinfo=timezone.utc)


@pytest.fixture()
def store(tmp_path):
    return AssistantStore(tmp_path / "alerts.db")


def _critical(store, fingerprint="fp-critical", message="mismatched broker order"):
    return store.upsert_operational_alert(
        fingerprint=fingerprint,
        severity="critical",
        category="broker_reconciliation",
        message=message,
        details={"proposal_id": "p-1"},
        seen_at=NOW.isoformat(),
    )


def _warning(store, fingerprint="fp-warning"):
    return store.upsert_operational_alert(
        fingerprint=fingerprint,
        severity="warning",
        category="recovery",
        message="backup is stale",
        details={},
        seen_at=NOW.isoformat(),
    )


# --- a critical alert delivers and records its delivery --------------------


def test_critical_alert_delivers_and_records_the_delivery(store):
    alert = _critical(store)
    channel = RecordingChannel()

    report = deliver_pending_alerts(store, channel, now=NOW)

    assert report["healthy"] is True
    assert [r["fingerprint"] for r in report["delivered"]] == ["fp-critical"]
    assert channel.sent == [
        {
            "title": "[CRITICAL] broker_reconciliation",
            "body": "mismatched broker order",
            "severity": "critical",
        }
    ]
    records = store.list_alert_deliveries(fingerprint="fp-critical")
    assert len(records) == 1
    assert records[0]["outcome"] == "delivered"
    assert records[0]["delivered_at"] == NOW.isoformat()
    assert records[0]["channel"] == "recording"
    assert records[0]["alert_id"] == alert["alert_id"]
    assert records[0]["occurrences_at_attempt"] == 1


def test_delivered_critical_no_longer_counts_as_undelivered(store):
    _critical(store)
    assert [a["fingerprint"] for a in undelivered_critical_alerts(store)] == [
        "fp-critical"
    ]
    deliver_pending_alerts(store, RecordingChannel(), now=NOW)
    assert undelivered_critical_alerts(store) == []


# --- severity routing: warnings batch, never interrupt ---------------------


def test_warnings_are_not_delivered_immediately_but_are_batched(store):
    _warning(store)
    channel = RecordingChannel()

    report = deliver_pending_alerts(store, channel, now=NOW)

    assert report["delivered"] == []
    assert channel.sent == []
    assert store.list_alert_deliveries(fingerprint="fp-warning") == []
    assert [a["fingerprint"] for a in pending_briefing_alerts(store)] == ["fp-warning"]


# --- delivery failure escalates rather than being swallowed ----------------


def test_delivery_failure_is_recorded_escalated_and_never_marked_delivered(store):
    _critical(store)
    channel = RecordingChannel(name="broken", fail_with=RuntimeError("channel offline"))

    report = deliver_pending_alerts(store, channel, now=NOW)

    assert report["healthy"] is False
    assert report["delivered"] == []
    record = store.list_alert_deliveries(fingerprint="fp-critical")[0]
    assert record["outcome"] == "failed"
    assert record["delivered_at"] is None
    assert "channel offline" in record["detail"]
    # Escalation: a durable critical alert about the broken channel itself.
    escalations = [
        a
        for a in store.list_operational_alerts(status="open")
        if a["fingerprint"] == DELIVERY_FAILURE_FINGERPRINT
    ]
    assert len(escalations) == 1
    assert escalations[0]["severity"] == "critical"
    # Both the original condition and the broken-channel escalation remain
    # mandatory until a successful self-test proves the channel recovered.
    assert sorted(
        a["fingerprint"] for a in undelivered_critical_alerts(store)
    ) == sorted(["fp-critical", DELIVERY_FAILURE_FINGERPRINT])


def test_a_later_success_never_erases_an_earlier_failure(store):
    _critical(store)
    deliver_pending_alerts(
        store, RecordingChannel(fail_with=RuntimeError("offline")), now=NOW
    )
    deliver_pending_alerts(store, RecordingChannel(), now=NOW + timedelta(minutes=1))

    outcomes = [r["outcome"] for r in store.list_alert_deliveries(fingerprint="fp-critical")]
    assert sorted(outcomes) == ["delivered", "failed"]


def test_the_delivery_failure_alert_is_not_pushed_through_the_broken_channel(store):
    _critical(store)
    channel = RecordingChannel(fail_with=RuntimeError("offline"))
    deliver_pending_alerts(store, channel, now=NOW)

    second = RecordingChannel()
    report = deliver_pending_alerts(store, second, now=NOW + timedelta(minutes=1))

    delivered = [r["fingerprint"] for r in report["delivered"]]
    assert DELIVERY_FAILURE_FINGERPRINT not in delivered


# --- deduplication / re-delivery by occurrence ----------------------------


def test_an_unchanged_alert_is_not_redelivered_on_every_sweep(store):
    _critical(store)
    channel = RecordingChannel()
    deliver_pending_alerts(store, channel, now=NOW)
    deliver_pending_alerts(store, channel, now=NOW + timedelta(minutes=1))
    deliver_pending_alerts(store, channel, now=NOW + timedelta(minutes=2))

    assert len(channel.sent) == 1
    assert len(store.list_alert_deliveries(fingerprint="fp-critical")) == 1


def test_a_new_occurrence_of_the_same_alert_is_delivered_again(store):
    _critical(store)
    channel = RecordingChannel()
    deliver_pending_alerts(store, channel, now=NOW)

    # The same fingerprint recurs: dedup keeps one alert row but increments
    # occurrences, and the operator must hear about the NEW occurrence.
    recurred = _critical(store)
    assert recurred["occurrences"] == 2
    assert needs_delivery(store, recurred) is True

    deliver_pending_alerts(store, channel, now=NOW + timedelta(minutes=5))
    assert len(channel.sent) == 2
    assert channel.sent[-1]["body"].endswith("(x2)")


# --- the self-test detects a broken channel -------------------------------


def test_self_test_passes_and_verifies_from_storage(store):
    channel = RecordingChannel()

    result = run_channel_self_test(store, channel, now=NOW)

    assert result["passed"] is True
    assert result["verified_from_storage"] is True
    assert len(channel.sent) == 1
    assert store.latest_successful_delivery(SELF_TEST_FINGERPRINT) is not None
    # The synthetic alert must not pollute the operator's open alert list.
    open_fingerprints = {a["fingerprint"] for a in store.list_operational_alerts()}
    assert SELF_TEST_FINGERPRINT not in open_fingerprints


def test_self_test_detects_a_silently_broken_channel(store):
    channel = RecordingChannel(name="broken", fail_with=RuntimeError("WinRT missing"))

    result = run_channel_self_test(store, channel, now=NOW)

    assert result["passed"] is False
    assert result["verified_from_storage"] is False
    record = store.list_alert_deliveries(fingerprint=SELF_TEST_FINGERPRINT)[0]
    assert record["outcome"] == "failed"
    escalations = [
        a
        for a in store.list_operational_alerts(status="open")
        if a["fingerprint"] == DELIVERY_FAILURE_FINGERPRINT
    ]
    assert len(escalations) == 1
    assert "did not deliver" in escalations[0]["message"]


def test_self_test_freshness_is_fail_closed_without_a_recorded_pass(store):
    assert self_test_freshness(store, now=NOW)["ok"] is False

    run_channel_self_test(store, RecordingChannel(), now=NOW)
    assert self_test_freshness(store, now=NOW + timedelta(days=1))["ok"] is True
    # Older than the weekly window: the channel is no longer proven.
    assert self_test_freshness(store, now=NOW + timedelta(days=8))["ok"] is False


# --- readiness integration: undelivered criticals are detectable ----------


def test_readiness_flags_an_undelivered_critical_alert(store):
    _critical(store)

    checks = {c.name: c for c in build_alert_delivery_checks(store)}
    assert checks["critical_alert_delivery"].ok is False
    assert checks["critical_alert_delivery"].mandatory is True
    assert "fp-critical" in checks["critical_alert_delivery"].detail

    deliver_pending_alerts(store, RecordingChannel(), now=NOW)
    after = {c.name: c for c in build_alert_delivery_checks(store)}
    assert after["critical_alert_delivery"].ok is True


def test_readiness_flags_a_stale_channel_self_test_without_blocking(store):
    checks = {c.name: c for c in build_alert_delivery_checks(store)}
    assert checks["alert_channel_self_test"].ok is False
    # Degrades rather than blocks: an unproven channel is not a halt.
    assert checks["alert_channel_self_test"].mandatory is False


def test_delivery_failure_remains_mandatory_until_a_successful_self_test(store):
    """A broken channel cannot make the readiness surface claim green.

    The failure alert is deliberately not sent through the known-broken
    channel, so a later successful self-test is the recovery proof that can
    safely acknowledge it.
    """
    _critical(store)
    deliver_pending_alerts(
        store, RecordingChannel(fail_with=RuntimeError("offline")), now=NOW
    )
    # The original alert later reaches the operator, but the separate
    # channel-failure alert must still keep readiness failed.
    deliver_pending_alerts(store, RecordingChannel(), now=NOW + timedelta(minutes=1))
    assert [a["fingerprint"] for a in undelivered_critical_alerts(store)] == [
        DELIVERY_FAILURE_FINGERPRINT
    ]
    assert {c.name: c for c in build_alert_delivery_checks(store)}[
        "critical_alert_delivery"
    ].ok is False

    run_channel_self_test(store, RecordingChannel(), now=NOW + timedelta(minutes=2))
    assert undelivered_critical_alerts(store) == []


def test_delivery_health_never_manufactures_its_own_alert(store):
    """The check must not live where failing checks persist alerts: an
    'undelivered critical' alert would itself be an undelivered critical,
    and every cycle would create another."""
    policy = load_policy()
    _critical(store)

    first = run_operational_check(store, policy, check_broker=False, now=NOW)
    second = run_operational_check(
        store, policy, check_broker=False, now=NOW + timedelta(minutes=1)
    )

    assert len(second["alerts"]) == len(first["alerts"])
    delivery_alerts = [
        a
        for a in store.list_operational_alerts(status=None, limit=500)
        if a["category"] == "observability"
    ]
    assert delivery_alerts == []


# --- the Windows channel's failure directions -----------------------------


def test_windows_channel_reports_a_missing_powershell_as_a_failure(store, monkeypatch):
    monkeypatch.setattr("assistant.alert_delivery.shutil.which", lambda name: None)
    alert = _critical(store)

    record = deliver_alert(store, alert, WindowsToastChannel(), now=NOW)

    assert record["outcome"] == "failed"
    assert record["channel"] == "windows_toast"
    assert "PowerShell" in record["detail"]


def test_windows_channel_reports_a_nonzero_exit_as_a_failure(store, monkeypatch):
    class _Completed:
        returncode = 1
        stdout = ""
        stderr = "WinRT type not found"

    monkeypatch.setattr(
        "assistant.alert_delivery.shutil.which", lambda name: "powershell"
    )
    monkeypatch.setattr(
        "assistant.alert_delivery.subprocess.run", lambda *a, **k: _Completed()
    )
    alert = _critical(store)

    record = deliver_alert(store, alert, WindowsToastChannel(), now=NOW)

    assert record["outcome"] == "failed"
    assert "WinRT type not found" in record["detail"]


def test_windows_channel_passes_alert_text_through_stdin_not_the_command_line(
    store, monkeypatch
):
    """Alert text is operator-facing and may contain quotes or newlines;
    interpolating it into a command line would be both fragile and an
    injection surface."""
    captured = {}

    class _Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["input"] = kwargs.get("input")
        return _Completed()

    monkeypatch.setattr(
        "assistant.alert_delivery.shutil.which", lambda name: "powershell"
    )
    monkeypatch.setattr("assistant.alert_delivery.subprocess.run", fake_run)
    alert = _critical(store, message='weird "quoted" \n message')

    record = deliver_alert(store, alert, WindowsToastChannel(), now=NOW)

    assert record["outcome"] == "delivered"
    assert 'weird "quoted"' not in " ".join(captured["command"])
    assert 'weird \\"quoted\\"' in captured["input"]


# --- nothing here can trade ------------------------------------------------


def test_delivery_never_touches_execution_state(store):
    _critical(store)
    before = (
        store.list_operational_alerts(status=None, limit=500),
        store.get_kill_switch(),
    )
    deliver_pending_alerts(store, RecordingChannel(), now=NOW)
    with store._connect() as connection:
        proposals = connection.execute("SELECT COUNT(*) FROM trade_proposals").fetchone()[0]
        orders = connection.execute("SELECT COUNT(*) FROM broker_orders").fetchone()[0]
        reservations = connection.execute(
            "SELECT COUNT(*) FROM execution_reservations"
        ).fetchone()[0]
    assert (proposals, orders, reservations) == (0, 0, 0)
    assert store.get_kill_switch() == before[1]


# --- the briefing is the warnings' delivery surface (routing completeness) --


def test_cli_briefing_prints_batched_warnings(store, capsys):
    """Owner routing (2026-08-03): warnings batch into the daily briefing.
    Without this surface they would be delivered NOWHERE -- not toasted
    (deliberately) and not briefed (this regression)."""
    import scripts.run_personal_assistant as cli

    _warning(store)
    _critical(store)  # criticals belong to the toast path, not the briefing

    cli._print_batched_warnings(store)
    out = capsys.readouterr().out

    assert "Open operational warnings (1, batched here by policy)" in out
    assert "[recovery] backup is stale" in out
    assert "mismatched broker order" not in out


def test_cli_briefing_prints_nothing_when_no_warnings_are_open(store, capsys):
    import scripts.run_personal_assistant as cli

    cli._print_batched_warnings(store)
    assert capsys.readouterr().out == ""


def test_cli_briefing_surfaces_warnings_before_packet_failure(
    store, capsys, monkeypatch
):
    """The briefing is warnings' only routed surface, so an upstream
    portfolio/data failure must not hide warnings that are already durable."""
    import scripts.run_personal_assistant as cli

    _warning(store)

    def _packet_failure(*, include_events):
        raise RuntimeError("portfolio feed unavailable")

    monkeypatch.setattr(cli, "_packet", _packet_failure)
    args = type("Args", (), {"no_events": False})()

    with pytest.raises(RuntimeError, match="portfolio feed unavailable"):
        cli.command_briefing(args, store)

    assert "[recovery] backup is stale" in capsys.readouterr().out


def test_ui_briefing_tab_surfaces_batched_warnings(tmp_path, monkeypatch):
    """The Streamlit briefing must show the same batch. Uses the real app
    via AppTest with the session-isolated database seeded with one open
    warning."""
    import os

    from streamlit.testing.v1 import AppTest

    seeded = AssistantStore(Path(os.environ["TRADING_ASSISTANT_DB"]))
    seeded.upsert_operational_alert(
        fingerprint="fp-ui-warning",
        severity="warning",
        category="recovery",
        message="ui-visible stale backup warning",
        details={},
        seen_at=NOW.isoformat(),
    )
    try:
        at = AppTest.from_file(
            str(Path(__file__).resolve().parent.parent / "scripts" / "personal_assistant_ui.py"),
            default_timeout=120,
        )
        at.run()
        assert not at.exception
        rendered = [w.value for w in at.warning]
        assert any("ui-visible stale backup warning" in str(v) for v in rendered)
    finally:
        # The session database is shared by every UI render test: leaving
        # the seeded alert open would leak into their assertions.
        for alert in seeded.list_operational_alerts(status="open", limit=50):
            if alert["fingerprint"] == "fp-ui-warning":
                seeded.acknowledge_operational_alert(alert["alert_id"])


# --- end-to-end: the cycle's marquee seam, halt -> alert -> operator -------


def test_reconciliation_halt_reaches_the_operator_end_to_end(store):
    """GR-3 gave broker anomalies an atomic kill-switch + critical alert;
    GR-5 gave critical alerts a delivery path. This pins the JOINED
    contract: a mismatched-order halt produced by the real storage
    primitive is picked up by the real delivery sweep and reaches the
    channel, with the delivery recorded against the same alert row."""
    store.activate_reconciliation_halt(
        proposal_id="p-integration",
        reason="Order under this idempotency key does NOT match the intent",
        details={"mismatch": "side", "path": "manual_lookup"},
    )
    assert store.get_kill_switch()["active"] is True

    channel = RecordingChannel()
    report = deliver_pending_alerts(store, channel, now=NOW)

    assert report["healthy"] is True
    assert len(channel.sent) == 1
    assert channel.sent[0]["severity"] == "critical"
    assert "does NOT match" in channel.sent[0]["body"]
    fingerprint = "broker_reconciliation:p-integration"
    record = store.list_alert_deliveries(fingerprint=fingerprint)[0]
    assert record["outcome"] == "delivered"
    assert undelivered_critical_alerts(store) == []
    store.set_kill_switch(False, reason="test cleanup")
