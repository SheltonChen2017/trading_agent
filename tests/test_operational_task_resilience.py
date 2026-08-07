"""Scheduled-task resilience invariants (incident 2026-08-05).

Source-level checks, for the same reason as
`tests/test_setup_operational_host.py`: the script's effects are Windows
machine mutations that no test should perform.

The incident: OrderMonitor and Watchdog both exited 0xC000013A
(STATUS_CONTROL_C_EXIT) when their console windows were closed. Their only
trigger was AtLogOn, which never fires again, and RestartCount did not
cover that exit because Task Scheduler treats a console close as the task
being stopped rather than failing. Order-stream tracking and the health
heartbeat stayed dead and silent — silent specifically because the
Watchdog is the component that would have raised the alarm about itself.

Separately, `New-ScheduledTaskSettingsSet` defaults both battery guards to
on. On a laptop that makes an unplugged machine skip the post-close
observation entirely, so a session silently fails to count toward the
evidence epoch — indistinguishable afterwards from a defect-caused gap.

Run with: python -m pytest tests/test_operational_task_resilience.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "install_windows_operational_tasks.ps1"
)
_SCRIPT = _PATH.read_text(encoding="utf-8")


def _settings_block(name: str) -> str:
    """Return one `$<name> = New-ScheduledTaskSettingsSet ...` assignment."""
    match = re.search(
        rf"\${name}\s*=\s*New-ScheduledTaskSettingsSet(.*?)(?=\n\$\w+\s*=)",
        _SCRIPT,
        re.DOTALL,
    )
    assert match is not None, f"could not locate the ${name} settings block"
    return match.group(1)


def test_long_running_tasks_carry_a_repeating_recovery_trigger():
    """A logon-only trigger cannot recover from any death. The repeating
    companion is what makes a closed console window self-healing."""
    assert "$selfHealTrigger" in _SCRIPT
    assert "-RepetitionInterval (New-TimeSpan -Minutes $LongRunningHealMinutes)" in _SCRIPT

    # Must span BOTH branches, so the pattern runs through the `else` block
    # rather than stopping at the first closing brace.
    match = re.search(
        r"\$longRunningTrigger\s*=\s*if.*?\nelse\s*\{.*?\n\}\n", _SCRIPT, re.DOTALL
    )
    assert match is not None, "could not locate the $longRunningTrigger assignment"
    branch = match.group(0)
    # BOTH logon-type branches need the recovery trigger: S4U hosts fail the
    # same way, they just start at boot instead of at logon.
    assert branch.count("$selfHealTrigger") == 2, (
        "each $longRunningTrigger branch must include the self-heal trigger"
    )
    assert "-AtStartup" in branch and "-AtLogOn" in branch


def test_recovery_trigger_cannot_stack_duplicate_instances():
    """The recovery trigger must not spawn a second monitor every interval.
    IgnoreNew blocks a second process; scheduler metadata may still update."""
    assert "-MultipleInstances IgnoreNew" in _settings_block("longSettings")
    assert "-At ((Get-Date).AddMinutes(1))" in _SCRIPT
    assert ".Date.AddMinutes(1)" not in _SCRIPT


def test_paper_observation_uses_battery_cleared_short_settings():
    """PaperObservation must use $shortSettings so an unplugged laptop still
    captures the session that makes a day count."""
    assert "Settings = $shortSettings" in _SCRIPT
    # The observation task registration block names PaperObservation and
    # shortSettings in the same task object.
    match = re.search(
        r'Name\s*=\s*"\$TaskPrefix-PaperObservation".*?Settings\s*=\s*\$(\w+)',
        _SCRIPT,
        re.DOTALL,
    )
    assert match is not None
    assert match.group(1) == "shortSettings"

def test_no_task_is_blocked_or_stopped_by_running_on_battery():
    """Both guards default to ON, so this must be explicit for every task
    group. For PaperObservation it is an evidence property: unplugged at
    16:30 would mean the session never counts."""
    for name in ("shortSettings", "longSettings"):
        block = _settings_block(name)
        assert "-AllowStartIfOnBatteries" in block, f"${name} still blocks on battery"
        assert "-DontStopIfGoingOnBatteries" in block, f"${name} still stops on battery"
        assert "-StartWhenAvailable" in block


def test_the_heal_interval_stays_within_a_sane_range():
    """A zero or absurd interval would either hammer the scheduler or
    leave a long blind window."""
    match = re.search(
        r"\[ValidateRange\((\d+),\s*(\d+)\)\]\s*\n\s*\[int\]\$LongRunningHealMinutes\s*=\s*(\d+)",
        _SCRIPT,
    )
    assert match is not None, "$LongRunningHealMinutes must carry a ValidateRange"
    low, high, default = (int(group) for group in match.groups())
    assert low >= 1 and high <= 60
    assert low <= default <= high
    assert default <= 15, "a blind window longer than 15 minutes defeats the purpose"


def test_incident_rationale_is_recorded_beside_the_code():
    """The next reader must be able to see why these settings exist before
    deciding they look redundant and removing them."""
    assert "0xC000013A" in _SCRIPT
    assert "RestartCount does not cover" in _SCRIPT
