"""GR-5: deliver operational alerts to a human, and prove it happened.

`operational_alerts` has always RECORDED alerts. Until this module nothing
ever DELIVERED one, so a critical broker-identity halt could sit in SQLite
while the operator watched a green screen. An alert nobody receives is a
log line.

Owner decision (2026-08-03): **Windows desktop notification is the
mandatory immediate channel for `critical`**; `warning` batches into the
daily briefing rather than interrupting; a webhook channel is deliberately
out of scope for this milestone.

Design rules this module holds to:

- **Delivery is recorded, not assumed.** Every attempt appends an immutable
  `alert_deliveries` row (channel, outcome, timestamps, occurrence count).
  A later success never erases an earlier failure.
- **Failure escalates, never swallows.** A channel exception is caught only
  to record it, then surfaced through the return value AND a durable
  `alert_delivery` failure alert, so a broken channel is itself an alert.
  It is never reported as delivered.
- **Re-delivery is occurrence-based.** A recurring alert re-notifies when
  its occurrence count grows past the last delivered attempt, so a
  persistent condition is not re-toasted on every 60-second sweep, while a
  genuinely NEW occurrence still reaches the operator.
- **The channel is dependency-free.** Windows toasts go through PowerShell's
  built-in WinRT notification API — no new pinned dependency, and it fails
  closed (recorded failure) on any non-Windows or restricted host.
- **Nothing here can trade.** This module reads alerts, writes delivery
  records, and calls a notifier. It never touches proposals, orders,
  reservations, the kill switch, or policy.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from assistant.storage import AssistantStore

CRITICAL = "critical"
WARNING = "warning"

#: Alerts at or above this severity interrupt the operator immediately.
IMMEDIATE_SEVERITIES = frozenset({CRITICAL})

#: Fingerprint used by the weekly channel self-test.
SELF_TEST_FINGERPRINT = "gr5_alert_delivery_self_test"

#: Fingerprint for "a delivery attempt itself failed".
DELIVERY_FAILURE_FINGERPRINT = "gr5_alert_delivery_failure"

_SELF_TEST_MAX_AGE_DAYS = 7.0


class AlertDeliveryError(RuntimeError):
    """Delivery could not be completed or verified."""


class AlertChannel(Protocol):
    """A real place a human actually looks."""

    name: str

    def send(self, *, title: str, body: str, severity: str) -> str:
        """Deliver one notification, or raise.

        Returns a short human-readable detail string recorded with the
        delivery. Raising means NOT delivered -- never return normally on a
        failure, because the caller records the return as proof.
        """


@dataclass(frozen=True)
class WindowsToastChannel:
    """Windows desktop notification via PowerShell's built-in WinRT API.

    Deliberately dependency-free: the repository pins no toast library, and
    adding one for a single notification would be a new supply-chain
    surface. Failure modes (non-Windows host, PowerShell unavailable,
    restricted execution policy, WinRT absent) all raise, so they are
    recorded as failures rather than silently "delivered".
    """

    name: str = "windows_toast"
    timeout_seconds: float = 20.0
    app_id: str = "Trading Assistant"

    def send(self, *, title: str, body: str, severity: str) -> str:
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if powershell is None:
            raise AlertDeliveryError(
                "no PowerShell executable found; cannot raise a Windows toast"
            )
        script = _TOAST_SCRIPT
        payload = json.dumps(
            {"title": title, "body": body, "severity": severity, "appId": self.app_id}
        )
        try:
            completed = subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    script,
                ],
                input=payload,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise AlertDeliveryError(
                f"toast notification timed out after {self.timeout_seconds}s"
            ) from exc
        except OSError as exc:
            raise AlertDeliveryError(f"could not run PowerShell: {exc}") from exc
        if completed.returncode != 0:
            raise AlertDeliveryError(
                "toast notification failed: "
                + (completed.stderr or completed.stdout or "no output").strip()[:300]
            )
        return "windows toast raised"


# Reads one JSON object from stdin so no alert text is ever interpolated
# into a command line (message text is operator-facing and may contain
# quotes, newlines, or characters PowerShell would otherwise parse).
_TOAST_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$raw = [Console]::In.ReadToEnd()
$payload = $raw | ConvertFrom-Json
[void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(
    [Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$texts = $template.GetElementsByTagName('text')
$texts.Item(0).AppendChild($template.CreateTextNode($payload.title)) | Out-Null
$texts.Item(1).AppendChild($template.CreateTextNode($payload.body)) | Out-Null
$toast = [Windows.UI.Notifications.ToastNotification]::new($template)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($payload.appId).Show($toast)
"""


@dataclass(frozen=True)
class RecordingChannel:
    """In-memory channel for tests and dry runs. Never notifies a human."""

    name: str = "recording"
    sent: list[dict[str, str]] = None  # type: ignore[assignment]
    fail_with: Exception | None = None

    def __post_init__(self) -> None:
        if self.sent is None:
            object.__setattr__(self, "sent", [])

    def send(self, *, title: str, body: str, severity: str) -> str:
        if self.fail_with is not None:
            raise self.fail_with
        self.sent.append({"title": title, "body": body, "severity": severity})
        return f"recorded ({len(self.sent)})"


def _alert_title(alert: dict[str, Any]) -> str:
    return f"[{alert['severity'].upper()}] {alert['category']}"


def _alert_body(alert: dict[str, Any]) -> str:
    occurrences = alert.get("occurrences", 1)
    suffix = f" (x{occurrences})" if occurrences and occurrences > 1 else ""
    return f"{alert['message']}{suffix}"


def needs_delivery(store: AssistantStore, alert: dict[str, Any]) -> bool:
    """True when this alert has no successful delivery at its current count.

    Occurrence-based rather than time-based: a persistent condition is
    delivered once per NEW occurrence, so a 60-second health sweep does not
    re-toast the same unchanged problem, and a genuinely repeating fault
    still reaches the operator.
    """
    delivered = store.latest_successful_delivery(
        alert["fingerprint"], min_occurrences=alert.get("occurrences", 1)
    )
    return delivered is None


def deliver_alert(
    store: AssistantStore,
    alert: dict[str, Any],
    channel: AlertChannel,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Attempt one delivery and record the outcome immutably.

    Returns the delivery record. A failure is recorded and RETURNED (with
    ``outcome='failed'``) rather than raised, so a sweep can continue
    through the remaining alerts; the caller escalates.
    """
    attempted_at = (now or datetime.now(timezone.utc)).isoformat()
    try:
        detail = channel.send(
            title=_alert_title(alert),
            body=_alert_body(alert),
            severity=alert["severity"],
        )
    except Exception as exc:  # channel failures must never look delivered
        return store.record_alert_delivery(
            fingerprint=alert["fingerprint"],
            alert_id=alert.get("alert_id"),
            channel=getattr(channel, "name", "unknown"),
            severity=alert["severity"],
            outcome="failed",
            occurrences_at_attempt=alert.get("occurrences", 1),
            detail=str(exc)[:500],
            attempted_at=attempted_at,
        )
    return store.record_alert_delivery(
        fingerprint=alert["fingerprint"],
        alert_id=alert.get("alert_id"),
        channel=getattr(channel, "name", "unknown"),
        severity=alert["severity"],
        outcome="delivered",
        occurrences_at_attempt=alert.get("occurrences", 1),
        detail=str(detail)[:500],
        attempted_at=attempted_at,
        delivered_at=attempted_at,
    )


def deliver_pending_alerts(
    store: AssistantStore,
    channel: AlertChannel,
    *,
    now: datetime | None = None,
    severities: frozenset[str] = IMMEDIATE_SEVERITIES,
) -> dict[str, Any]:
    """Deliver every open alert of the given severities that still needs it.

    Severity routing (owner decision 2026-08-03): only `critical` is
    immediate. `warning` is deliberately excluded here and surfaces in the
    daily briefing batch instead -- see ``pending_briefing_alerts``.

    A channel failure is escalated two ways: it appears in the returned
    ``failed`` list (so a CLI can exit nonzero) and it raises a durable
    ``alert_delivery`` critical alert, which makes a broken channel visible
    even to an operator who never runs the CLI again.
    """
    moment = now or datetime.now(timezone.utc)
    delivered: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for alert in store.list_operational_alerts(status="open", limit=500):
        if alert["severity"] not in severities:
            continue
        if alert["fingerprint"] == DELIVERY_FAILURE_FINGERPRINT:
            # Never try to deliver the "delivery is broken" alert through
            # the broken channel: that is an infinite failure loop, and the
            # operator surface/health check already exposes it.
            continue
        if not needs_delivery(store, alert):
            continue
        record = deliver_alert(store, alert, channel, now=moment)
        (delivered if record["outcome"] == "delivered" else failed).append(record)
    if failed:
        store.upsert_operational_alert(
            fingerprint=DELIVERY_FAILURE_FINGERPRINT,
            severity=CRITICAL,
            category="alert_delivery",
            message=(
                f"{len(failed)} critical alert(s) could not be delivered through "
                f"channel {getattr(channel, 'name', 'unknown')!r}: "
                + failed[0]["detail"][:200]
            ),
            details={
                "channel": getattr(channel, "name", "unknown"),
                "failed_fingerprints": [record["fingerprint"] for record in failed],
            },
            seen_at=moment.isoformat(),
        )
    return {
        "checked_at": moment.isoformat(),
        "channel": getattr(channel, "name", "unknown"),
        "delivered": delivered,
        "failed": failed,
        "healthy": not failed,
    }


def pending_briefing_alerts(
    store: AssistantStore, *, severities: frozenset[str] = frozenset({WARNING})
) -> list[dict[str, Any]]:
    """Open non-immediate alerts, for the daily briefing batch.

    Read-only: the briefing surfaces these, and doing so is not a
    'delivery' in the recorded sense -- the operator has to be looking.
    """
    return [
        alert
        for alert in store.list_operational_alerts(status="open", limit=500)
        if alert["severity"] in severities
    ]


def undelivered_critical_alerts(store: AssistantStore) -> list[dict[str, Any]]:
    """Open critical alerts with no successful delivery at their current
    occurrence count -- the condition GR-5 exists to make detectable.

    A delivery-failure alert is the one exception to the ordinary delivery
    attempt rule: it is deliberately not re-sent through a channel already
    known to be broken.  It is nevertheless an open, mandatory condition
    until a successful channel self-test proves recovery and acknowledges it.
    Excluding it here would make readiness claim every critical alert was
    delivered immediately after the original alert eventually succeeded.
    """
    return [
        alert
        for alert in store.list_operational_alerts(status="open", limit=500)
        if alert["severity"] == CRITICAL
        and (
            alert["fingerprint"] == DELIVERY_FAILURE_FINGERPRINT
            or needs_delivery(store, alert)
        )
    ]


def run_channel_self_test(
    store: AssistantStore,
    channel: AlertChannel,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Emit a synthetic alert, deliver it, and verify the recorded receipt.

    A channel that silently broke is worse than no channel, so this proves
    the path end to end rather than checking configuration. Verification
    reads the delivery back from storage instead of trusting the in-memory
    return value.
    """
    moment = now or datetime.now(timezone.utc)
    synthetic = store.upsert_operational_alert(
        fingerprint=SELF_TEST_FINGERPRINT,
        severity=CRITICAL,
        category="alert_delivery",
        message=(
            "Synthetic alert-delivery self-test. If you can read this, the "
            "critical alert channel works."
        ),
        details={"self_test": True, "at": moment.isoformat()},
        seen_at=moment.isoformat(),
    )
    record = deliver_alert(store, synthetic, channel, now=moment)
    verified = store.latest_successful_delivery(
        SELF_TEST_FINGERPRINT, min_occurrences=synthetic["occurrences"]
    )
    passed = record["outcome"] == "delivered" and verified is not None
    if passed:
        # The self-test alert has served its purpose; leaving it open would
        # pollute the operator's real alert list.
        store.acknowledge_operational_alert(synthetic["alert_id"])
        # A previous delivery-failure alert intentionally could not be
        # delivered through its known-broken channel.  This successful test
        # is the recovery proof: preserve its immutable delivery evidence,
        # but close the now-resolved open alert so readiness can recover.
        for alert in store.list_operational_alerts(status="open", limit=500):
            if alert["fingerprint"] == DELIVERY_FAILURE_FINGERPRINT:
                store.acknowledge_operational_alert(alert["alert_id"])
    else:
        store.upsert_operational_alert(
            fingerprint=DELIVERY_FAILURE_FINGERPRINT,
            severity=CRITICAL,
            category="alert_delivery",
            message=(
                "Alert-delivery self-test FAILED: the critical channel "
                f"{getattr(channel, 'name', 'unknown')!r} did not deliver a "
                "synthetic alert. Critical alerts may not be reaching you."
            ),
            details={"channel": getattr(channel, "name", "unknown"), "detail": record["detail"]},
            seen_at=moment.isoformat(),
        )
    return {
        "passed": passed,
        "performed_at": moment.isoformat(),
        "channel": getattr(channel, "name", "unknown"),
        "delivery": record,
        "verified_from_storage": verified is not None,
    }


def self_test_freshness(
    store: AssistantStore,
    *,
    now: datetime | None = None,
    max_age_days: float = _SELF_TEST_MAX_AGE_DAYS,
) -> dict[str, Any]:
    """Is the weekly channel self-test recent enough to trust the channel?"""
    moment = now or datetime.now(timezone.utc)
    latest = store.latest_successful_delivery(SELF_TEST_FINGERPRINT)
    if latest is None:
        return {
            "ok": False,
            "detail": "No successful alert-delivery self-test has ever been recorded.",
            "last_passed_at": None,
        }
    last = datetime.fromisoformat(latest["delivered_at"])
    age = moment - last
    ok = timedelta(0) <= age <= timedelta(days=max_age_days)
    return {
        "ok": ok,
        "detail": (
            f"Last successful self-test {last.isoformat()} "
            f"({age.total_seconds() / 86400:.1f} days ago; limit {max_age_days})."
        ),
        "last_passed_at": latest["delivered_at"],
    }
