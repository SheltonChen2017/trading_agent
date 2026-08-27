"""SYS-P2-011: one policy identity across every operational task."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from assistant import policy as policy_module
from assistant.operations import (
    OPERATIONAL_POLICY_HEARTBEAT_KEYS,
    OperationsError,
    REQUIRED_OPERATIONAL_POLICY_HEARTBEATS,
    operational_policy_identity,
    record_operational_policy_heartbeat,
    verify_operational_policy_heartbeats,
)
from assistant.policy import (
    DEFAULT_POLICY_PATH,
    POLICY_PATH_ENV_VAR,
    compute_policy_fingerprint,
    load_policy,
)
from assistant.storage import AssistantStore
from scripts import run_operations_watchdog as watchdog
from scripts import run_personal_assistant as personal_cli


def _write_policy(path: Path, *, name: str = "operational-test") -> Path:
    payload = json.loads(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))
    payload["name"] = name
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def test_watchdog_uses_lazy_canonical_precedence_and_refuses_broken_path(
    tmp_path, monkeypatch
):
    default = _write_policy(tmp_path / "default.json", name="default")
    personal = _write_policy(tmp_path / "personal.json", name="personal")
    environment = _write_policy(tmp_path / "environment.json", name="environment")
    explicit = _write_policy(tmp_path / "explicit.json", name="explicit")
    monkeypatch.setattr(policy_module, "DEFAULT_POLICY_PATH", default)
    monkeypatch.setattr(policy_module, "PERSONAL_POLICY_PATH", personal)
    monkeypatch.setenv(POLICY_PATH_ENV_VAR, str(environment))

    assert watchdog.build_parser().parse_args([]).policy is None
    env_path, env_policy = watchdog._resolve_runtime_policy(None)
    assert env_path == environment.resolve()
    assert env_policy.name == "environment"
    explicit_path, explicit_policy = watchdog._resolve_runtime_policy(explicit)
    assert explicit_path == explicit.resolve()
    assert explicit_policy.name == "explicit"

    with pytest.raises(SystemExit, match="Policy resolution failed"):
        watchdog._resolve_runtime_policy(tmp_path / "missing.json")


def test_all_four_operational_heartbeats_share_one_disk_verified_identity(tmp_path):
    policy_path = _write_policy(tmp_path / "policy.json")
    policy = load_policy(policy_path)
    store = AssistantStore(tmp_path / "assistant.db")

    for task in REQUIRED_OPERATIONAL_POLICY_HEARTBEATS:
        record_operational_policy_heartbeat(
            store,
            task,
            policy,
            policy_path,
            healthy=True,
            status="test",
        )

    report = verify_operational_policy_heartbeats(
        store, policy, policy_path, require_all=True
    )
    assert report["ok"] is True
    assert report["degraded"] is False
    expected_fingerprint = compute_policy_fingerprint(policy)
    for task in REQUIRED_OPERATIONAL_POLICY_HEARTBEATS:
        heartbeat = store.get_system_state(
            OPERATIONAL_POLICY_HEARTBEAT_KEYS[task]
        )
        assert heartbeat["policy_path"] == str(policy_path.resolve())
        assert heartbeat["policy_fingerprint"] == expected_fingerprint
        assert report["checks"][task]["status"] == "matched"

    # Compatibility consumers retain the historical watchdog key, but a
    # cycle no longer impersonates the watchdog.
    assert OPERATIONAL_POLICY_HEARTBEAT_KEYS["watchdog"] == "operations_heartbeat"
    assert store.get_system_state("operations_heartbeat")[
        "policy_fingerprint"
    ] == expected_fingerprint


def test_verifier_rejects_fingerprint_mismatch_and_unreadable_recorded_path(
    tmp_path,
):
    policy_path = _write_policy(tmp_path / "policy.json")
    policy = load_policy(policy_path)
    store = AssistantStore(tmp_path / "assistant.db")
    for task in REQUIRED_OPERATIONAL_POLICY_HEARTBEATS:
        record_operational_policy_heartbeat(
            store, task, policy, policy_path, healthy=True
        )

    cycle = store.get_system_state("operations_cycle_heartbeat")
    cycle["policy_fingerprint"] = "0" * 64
    store.set_system_state("operations_cycle_heartbeat", cycle)
    mismatch = verify_operational_policy_heartbeats(
        store, policy, policy_path, require_all=True
    )
    assert mismatch["ok"] is False
    assert mismatch["checks"]["cycle"]["status"] == "mismatched"

    observation = store.get_system_state("paper_observation_heartbeat")
    observation["policy_path"] = str(tmp_path / "deleted-policy.json")
    store.set_system_state("paper_observation_heartbeat", observation)
    unreadable = verify_operational_policy_heartbeats(
        store, policy, policy_path, require_all=True
    )
    assert unreadable["ok"] is False
    assert unreadable["checks"]["observation"]["status"] == "unreadable"


def test_missing_never_run_heartbeats_degrade_preview_but_fail_post_start(tmp_path):
    policy_path = _write_policy(tmp_path / "policy.json")
    policy = load_policy(policy_path)
    store = AssistantStore(tmp_path / "assistant.db")

    preview = verify_operational_policy_heartbeats(
        store, policy, policy_path, require_all=False
    )
    assert preview["ok"] is True
    assert preview["degraded"] is True
    required = verify_operational_policy_heartbeats(
        store, policy, policy_path, require_all=True
    )
    assert required["ok"] is False
    assert set(required["failed_tasks"]) == set(
        REQUIRED_OPERATIONAL_POLICY_HEARTBEATS
    )


def test_loaded_policy_cannot_certify_a_file_changed_after_load(tmp_path):
    policy_path = _write_policy(tmp_path / "policy.json", name="before")
    loaded = load_policy(policy_path)
    _write_policy(policy_path, name="after")

    with pytest.raises(OperationsError, match="no longer matches"):
        operational_policy_identity(loaded, policy_path)


def test_monitor_and_skipped_observation_record_policy_identity(
    tmp_path, monkeypatch
):
    policy_path = _write_policy(tmp_path / "policy.json")
    expected = compute_policy_fingerprint(load_policy(policy_path))
    store = AssistantStore(tmp_path / "assistant.db")

    monkeypatch.setattr(personal_cli, "acquire_process_singleton", lambda *a: None)
    monkeypatch.setattr(personal_cli, "monitor_orders", lambda *a, **k: None)
    personal_cli.command_monitor_orders(
        SimpleNamespace(
            database=tmp_path / "assistant.db",
            policy=str(policy_path),
            cancel_stale=False,
            poll_seconds=30,
        ),
        store,
    )
    monitor = store.get_system_state("order_monitor_heartbeat")
    assert monitor["policy_fingerprint"] == expected
    assert monitor["status"] == "running"

    monkeypatch.setattr(personal_cli.config, "PAPER_TRADING", True)
    monkeypatch.setattr(personal_cli, "is_configured", lambda: True)
    monkeypatch.setattr(personal_cli, "paper_session_schedule", lambda now: None)
    personal_cli.command_paper_observation(
        SimpleNamespace(
            policy=str(policy_path),
            benchmark="SPY",
            cancel_stale=False,
            alerts_jsonl=None,
        ),
        store,
    )
    observation = store.get_system_state("paper_observation_heartbeat")
    assert observation["policy_fingerprint"] == expected
    assert observation["status"] == "skipped"
    assert observation["captured"] is False


def test_installer_uses_one_command_plan_for_whatif_and_install_actions():
    root = Path(__file__).resolve().parent.parent
    source = (root / "scripts" / "install_windows_operational_tasks.ps1").read_text(
        encoding="utf-8"
    )
    command_block = source[
        source.index("$taskCommands =") : source.index(
            "# ScheduledTasks object construction"
        )
    ]
    assert command_block.count("--policy $policyArgument") == 4
    for name in (
        "OperationsCycle",
        "OrderMonitor",
        "Watchdog",
        "PaperObservation",
    ):
        assert f"Command = $taskCommands.{name}" in source
        assert f"-Argument $taskCommands.{name}" in source
    assert "policy-identity" in source
    assert "Operational policy validation failed" in source


def test_windows_verifier_checks_task_paths_and_runtime_fingerprints():
    source = (
        Path(__file__).resolve().parent.parent
        / "scripts"
        / "verify_windows_evidence_tasks.ps1"
    ).read_text(encoding="utf-8")
    assert 'Add-Check -Name "task_policy:$taskName"' in source
    assert '"verify-operational-policy-heartbeats"' in source
    assert '$heartbeatArguments += "--require-all"' in source
    assert 'Add-Check -Name "operational_policy_heartbeats"' in source
