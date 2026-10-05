"""Exercise leak attribution only against redirected, disposable runtime state."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import assistant.dispatch_fence as dispatch_fence


def _stop_file(root: Path) -> Path:
    return (
        root / dispatch_fence._STATE_DIRECTORY_NAME
        / dispatch_fence._EMERGENCY_STOP_FILE_NAME
    )


def _write_stop(
    root: Path,
    origin_database: str,
    *,
    activated_at: object = "2000-01-01T00:00:00+00:00",
    incident_id: str = "crafted",
    reason: str = "test",
    generation: int = 1,
    incidents: list | None = None,
    last_clear: dict | None = None,
) -> None:
    """Activation time is semantic, not evidence of when these bytes appeared."""
    stop = _stop_file(root)
    stop.parent.mkdir(parents=True, exist_ok=True)
    if incidents is None:
        incidents = [{
            "incident_id": incident_id,
            "origin_database": origin_database,
            "reason": reason,
            "activated_at": activated_at,
        }]
    stop.write_text(
        json.dumps({
            "version": dispatch_fence._RUNTIME_STOP_STATE_VERSION,
            "active": bool(incidents),
            "scope": "execution_runtime",
            "generation": generation,
            "reason": reason,
            "changed_at": "2000-01-01T00:00:00+00:00",
            "open_incidents": incidents,
            "last_clear": last_clear,
        }),
        encoding="utf-8",
    )


@pytest.fixture
def runtime_guard(tmp_path, monkeypatch, request):
    # Use pytest's actual plugin, not a second import with an uncaptured baseline.
    source = Path(__file__).with_name("conftest.py").resolve()
    guard = next(plugin for plugin in request.config.pluginmanager.get_plugins()
                 if getattr(plugin, "__file__", None)
                 and Path(plugin.__file__).resolve() == source)
    root = tmp_path / "fake-localappdata"
    monkeypatch.setattr(dispatch_fence, "_canonical_runtime_root", lambda: root)
    monkeypatch.setattr(dispatch_fence, "_RUNTIME_FENCE_ROOT", root)
    for name in ("_RUNTIME_STOP_SESSION_FILE", "_RUNTIME_STOP_PREEXISTING",
                 "_RUNTIME_STOP_PREVIOUS_CLEAR"):
        monkeypatch.setattr(guard, name, getattr(guard, name))
    guard._capture_runtime_stop_session_baseline()
    yield guard, root
    # Only our crafted file is removed, never an operator runtime path.
    monkeypatch.setattr(dispatch_fence, "_canonical_runtime_root", lambda: root)
    _stop_file(root).unlink(missing_ok=True)


def test_guard_captures_once_before_collection_without_a_lazy_rebaseline(
    tmp_path, runtime_guard, monkeypatch, request,
):
    from _pytest.config import PytestPluginManager
    from types import SimpleNamespace
    guard, root = runtime_guard
    monkeypatch.setattr(guard, "_RUNTIME_STOP_SESSION_FILE", None)
    # Reproduce pytest's historic configure replay for a late-loaded conftest.
    manager = PytestPluginManager()
    manager.hook.pytest_configure.call_historic(kwargs={"config": request.config})
    class LateConftest:
        pytest_configure = staticmethod(guard.pytest_configure)
    manager.register(LateConftest(), name="late-runtime-guard")
    assert guard._RUNTIME_STOP_SESSION_FILE == _stop_file(root).resolve()
    _write_stop(root, str(tmp_path.parent / "collection_test0" / "assistant.db"))
    guard.pytest_sessionstart(SimpleNamespace(config=None))
    guard.pytest_configure(None)
    with pytest.raises(AssertionError, match="REAL runtime emergency stop"):
        guard._assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)


def test_guard_reports_an_unresolvable_root(runtime_guard, monkeypatch, tmp_path):
    """Resolution matters at baseline; afterwards the baselined file is read."""
    guard, root = runtime_guard
    def unresolved():
        raise RuntimeError("fixture root refusal")
    monkeypatch.setattr(dispatch_fence, "_canonical_runtime_root", unresolved)
    with pytest.raises(AssertionError, match="cannot resolve"):
        guard._capture_runtime_stop_session_baseline()
    # A root that cannot be resolved at teardown does not blind the guard:
    # the baselined real file is what it reads.
    guard._assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)
    _write_stop(root, str(tmp_path.parent / "late_test0" / "assistant.db"))
    with pytest.raises(AssertionError, match="REAL runtime emergency stop"):
        guard._assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)


def test_guard_fails_when_this_session_leaked_into_the_real_root(tmp_path, runtime_guard):
    guard, root = runtime_guard
    _write_stop(root, str(tmp_path.parent / "some_other_test0" / "assistant.db"))
    with pytest.raises(AssertionError, match="REAL runtime emergency stop"):
        guard._assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)


def test_guard_detects_a_new_incident_with_an_old_activation_time(tmp_path, runtime_guard):
    guard, root = runtime_guard
    # Exercise the real API: changed_at is caller-supplied semantic history.
    dispatch_fence.activate_runtime_emergency_stop(
        tmp_path.parent / "new_test0" / "assistant.db",
        incident_id="old-stamp", reason="legacy containment",
        changed_at="2000-01-01T00:00:00+00:00",
    )
    before = _stop_file(root).read_bytes()
    with pytest.raises(AssertionError, match="REAL runtime emergency stop"):
        guard._assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)
    assert _stop_file(root).read_bytes() == before


def test_guard_ignores_incidents_from_other_sessions(tmp_path, runtime_guard):
    guard, root = runtime_guard
    _write_stop(root, str(tmp_path.parent.parent / "another-session" / "assistant.db"))
    guard._assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)


def test_guard_ignores_a_prefix_colliding_sibling_base(tmp_path, runtime_guard):
    guard, root = runtime_guard
    sibling_base = tmp_path.parent.with_name(tmp_path.parent.name + "3")
    # Keep the obsolete time filter from masking the independent path defect.
    _write_stop(root, str(sibling_base / "other_test0" / "assistant.db"),
                activated_at="2999-01-01T00:00:00+00:00")
    guard._assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)


def test_guard_ignores_a_stale_incident_from_an_earlier_run_under_the_same_basetemp(
    tmp_path, runtime_guard,
):
    guard, root = runtime_guard
    _write_stop(root, str(tmp_path.parent / "earlier_run_test0" / "assistant.db"))
    # Actual pre-existence, not an old timestamp written after the snapshot.
    guard._capture_runtime_stop_session_baseline()
    before = _stop_file(root).read_bytes()
    guard._assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)
    assert _stop_file(root).read_bytes() == before


def test_guard_detects_content_change_reusing_a_baseline_identity(tmp_path, runtime_guard):
    guard, root = runtime_guard
    origin = str(tmp_path.parent / "earlier_run_test0" / "assistant.db")
    _write_stop(root, origin)
    guard._capture_runtime_stop_session_baseline()
    _write_stop(root, origin, reason="new containment", generation=2)
    with pytest.raises(AssertionError, match="REAL runtime emergency stop"):
        guard._assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)


def test_guard_detects_a_cleared_then_reintroduced_baseline_identity(tmp_path, runtime_guard):
    guard, root = runtime_guard
    origin = str(tmp_path.parent / "earlier_run_test0" / "assistant.db")
    _write_stop(root, origin)
    guard._capture_runtime_stop_session_baseline()
    _write_stop(root, origin, incidents=[], generation=2)
    guard._assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)
    _write_stop(root, origin, generation=3)
    with pytest.raises(AssertionError, match="REAL runtime emergency stop"):
        guard._assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)


def test_guard_detects_an_unobserved_identical_baseline_lifecycle(tmp_path, runtime_guard):
    guard, root = runtime_guard
    origin = str(tmp_path.parent / "earlier_run_test0" / "assistant.db")
    _write_stop(root, origin)
    guard._capture_runtime_stop_session_baseline()
    # A surviving per-incident clear receipt proves this identity was re-added.
    _write_stop(root, origin, generation=3, last_clear={
        "incident_id": "crafted", "origin_database": origin,
        "reason": "cleared", "cleared_at": "2000-01-01T00:00:00+00:00",
    })
    with pytest.raises(AssertionError, match="REAL runtime emergency stop"):
        guard._assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)


def test_guard_uses_a_production_clear_receipt_for_an_unobserved_reintroduction(
    tmp_path, runtime_guard,
):
    guard, root = runtime_guard
    database = tmp_path.parent / "earlier_run_test0" / "assistant.db"
    activation = dict(incident_id="baseline", reason="legacy containment",
                      changed_at="2000-01-01T00:00:00+00:00")
    initial = dispatch_fence.activate_runtime_emergency_stop(database, **activation)
    guard._capture_runtime_stop_session_baseline()
    cleared = dispatch_fence.clear_runtime_emergency_stop(
        database, incident_id="baseline", expected_generation=initial["generation"],
        reason="fixture recovery", changed_at="2000-01-01T00:00:00+00:00",
    )
    reintroduced = dispatch_fence.activate_runtime_emergency_stop(database, **activation)
    assert reintroduced["open_incidents"] == initial["open_incidents"]
    assert reintroduced["last_clear"] == cleared["last_clear"]
    assert reintroduced["last_clear"]["incident_id"] == "baseline"
    before = _stop_file(root).read_bytes()
    # The guard did not see the empty inventory, only this concrete clear receipt.
    with pytest.raises(AssertionError, match="REAL runtime emergency stop"):
        guard._assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)
    assert _stop_file(root).read_bytes() == before


def test_guard_does_not_guess_an_incident_lifecycle_from_global_generation(
    tmp_path, runtime_guard,
):
    guard, root = runtime_guard
    origin = str(tmp_path.parent / "earlier_run_test0" / "assistant.db")
    _write_stop(root, origin)
    guard._capture_runtime_stop_session_baseline()
    _write_stop(root, origin, generation=3)
    # No per-incident history survives; another session could cause this change.
    guard._assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)


def test_guard_keeps_baseline_exemption_when_a_sibling_adds_an_incident(tmp_path, runtime_guard):
    guard, root = runtime_guard
    origin = str(tmp_path.parent / "earlier_run_test0" / "assistant.db")
    _write_stop(root, origin)
    guard._capture_runtime_stop_session_baseline()
    incidents = json.loads(_stop_file(root).read_text())["open_incidents"]
    incidents.append({"incident_id": "sibling", "origin_database": str(tmp_path.parent.parent / "sibling" / "db"),
                      "reason": "test", "activated_at": "2000-01-01T00:00:00+00:00"})
    _write_stop(root, origin, incidents=incidents, generation=2)
    guard._assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)


def test_guard_does_not_attribute_a_siblings_unobserved_lifecycle_to_this_session(
    tmp_path, runtime_guard,
):
    guard, root = runtime_guard
    origin = str(tmp_path.parent / "earlier_run_test0" / "assistant.db")
    sibling = {"incident_id": "sibling", "origin_database": str(tmp_path.parent.parent / "sibling" / "db"),
               "reason": "test", "activated_at": "2000-01-01T00:00:00+00:00"}
    _write_stop(root, origin)
    incidents = json.loads(_stop_file(root).read_text())["open_incidents"] + [sibling]
    _write_stop(root, origin, incidents=incidents, generation=2)
    guard._capture_runtime_stop_session_baseline()
    # Another suite clears/re-adds its own incident; our stale incident never changed.
    _write_stop(root, origin, incidents=incidents, generation=4, last_clear={
        "incident_id": "sibling", "origin_database": sibling["origin_database"],
        "reason": "cleared", "cleared_at": "2000-01-01T00:00:00+00:00",
    })
    guard._assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)


@pytest.mark.parametrize("activated_at", ["not-a-timestamp", "2000-01-01T00:00:00", None],
                         ids=["unparseable", "naive", "missing"])
def test_guard_attributes_by_path_when_the_incident_stamp_is_unusable(
    tmp_path, runtime_guard, activated_at,
):
    guard, root = runtime_guard
    _write_stop(root, str(tmp_path.parent / "new_test0" / "assistant.db"), activated_at=activated_at)
    with pytest.raises(AssertionError, match="REAL runtime emergency stop"):
        guard._assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)


def test_guard_is_quiet_when_no_real_stop_file_exists(tmp_path, runtime_guard):
    guard, _ = runtime_guard
    guard._assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)


def test_guard_refuses_a_root_changed_without_a_new_baseline(tmp_path, runtime_guard, monkeypatch):
    guard, _ = runtime_guard
    monkeypatch.setattr(dispatch_fence, "_canonical_runtime_root", lambda: tmp_path / "unsnapshotted")
    with pytest.raises(AssertionError, match="no session baseline"):
        guard._assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)


@pytest.mark.parametrize("text", ["{", "[]", '{"generation":1,"open_incidents":null}',
                                  '{"generation":true,"open_incidents":[]}',
                                  '{"generation":1,"open_incidents":[null]}'])
def test_guard_reports_uninspectable_state_instead_of_claiming_no_leak(tmp_path, runtime_guard, text):
    guard, root = runtime_guard
    _stop_file(root).parent.mkdir(parents=True, exist_ok=True)
    _stop_file(root).write_text(text)
    with pytest.raises(AssertionError, match="cannot decode"):
        guard._assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)
    with pytest.raises(AssertionError, match="cannot decode"):
        guard._capture_runtime_stop_session_baseline()


def test_guard_reports_read_failure_and_does_not_overwrite_state(tmp_path, runtime_guard):
    guard, root = runtime_guard
    _write_stop(root, str(tmp_path.parent / "new_test0" / "assistant.db"))
    before = _stop_file(root).read_bytes()
    def unreadable(path):
        assert path == _stop_file(root).resolve()
        raise PermissionError("fixture read refusal")
    # The guard reads through its own import-bound descriptor reader, so the
    # refusal is injected at that seam rather than at a patchable Path method.
    with patch.object(guard, "_read_runtime_stop_bytes", unreadable):
        with pytest.raises(AssertionError, match="cannot read"):
            guard._assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)
        with pytest.raises(AssertionError, match="cannot read"):
            guard._capture_runtime_stop_session_baseline()
    assert _stop_file(root).read_bytes() == before


def test_guard_does_not_consult_monkeypatched_json_loads(tmp_path, runtime_guard, monkeypatch):
    guard, root = runtime_guard
    _write_stop(root, str(tmp_path.parent.parent / "sibling" / "assistant.db"))
    def forbidden(*args, **kwargs):
        raise AssertionError("json.loads must not run")
    monkeypatch.setattr(json, "loads", forbidden)
    guard._assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)


def test_guard_does_not_consult_monkeypatched_open(tmp_path, runtime_guard, monkeypatch):
    """A zero-I/O test's ``open`` sentinel must neither trip nor blind the guard."""
    import builtins
    guard, root = runtime_guard
    def forbidden(*args, **kwargs):
        raise AssertionError("open must not run")
    # Absent real state stays a quiet no-op under the sentinel ...
    with monkeypatch.context() as sentinel:
        sentinel.setattr(builtins, "open", forbidden)
        sentinel.setattr(Path, "open", forbidden)
        guard._assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)
    # ... and a real leak is still read and attributed under it.  The sentinel
    # stays installed through this test's own teardown, as it does in the
    # zero-I/O tests this protects.
    _write_stop(root, str(tmp_path.parent / "leaking_test0" / "assistant.db"))
    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    with pytest.raises(AssertionError, match="REAL runtime emergency stop"):
        guard._assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)


def test_guard_survives_windows_name_and_os_open_left_patched(tmp_path, runtime_guard, monkeypatch):
    """Windows-branch tests leave ``os.name == "nt"`` and an ``os.open`` sentinel.

    Under that state ``Path()`` cannot be instantiated on a POSIX host and the
    runtime root cannot be re-resolved.  The guard must stay quiet on absent
    state and still attribute a real leak.
    """
    import os as os_module
    guard, root = runtime_guard
    def forbidden(*args, **kwargs):
        raise AssertionError("os.open must not run")
    with monkeypatch.context() as patched:
        patched.setattr(os_module, "name", "nt")
        patched.setattr(os_module, "open", forbidden)
        guard._assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)
    _write_stop(root, str(tmp_path.parent / "windows_branch_test0" / "assistant.db"))
    monkeypatch.setattr(os_module, "name", "nt")
    monkeypatch.setattr(os_module, "open", forbidden)
    with pytest.raises(AssertionError, match="REAL runtime emergency stop"):
        guard._assert_test_left_no_incident_in_the_real_runtime_stop(tmp_path)
