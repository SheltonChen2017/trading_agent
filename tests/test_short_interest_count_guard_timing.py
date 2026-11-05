"""Cold-child offline timing guards; never install an audit hook in pytest.

All source archives, current-code/Git bindings and baseline constants in the
composition test are the explicitly fabricated original loader test domain.
No actual source, key, provider, native operation, ticket or claim is opened.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

from data.hashing import canonical_json

# The runtime under test imports POSIX-only stdlib modules at import time, so
# this module cannot even be collected on the supported Windows host; see the
# lane record SI-CR18-001. Portable contract logic stays covered on POSIX.
pytest.importorskip(
    "resource",
    reason=(
        "the protected-capture runtime imports the POSIX-only module "
        "resource at import time; it cannot execute on this host, see the "
        "lane record SI-CR18-001"
    ),
)

from scripts import diagnose_short_interest_count_guard_timing as timing


def child(script, *, timeout=40):
    result = subprocess.run([sys.executable, "-B", "-c", textwrap.dedent(script)],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": ".:tests", "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}, timeout=timeout)
    assert result.returncode == 0, (result.returncode, result.stdout[-4000:], result.stderr[-4000:])
    return [json.loads(line) for line in result.stdout.splitlines() if line]


def test_original_readonly_OwnedOutput_inventory_ABI_survives_real_hook(tmp_path):
    directory = tmp_path / "existing"; directory.mkdir(mode=0o700)
    (directory / "synthetic.private.json").write_bytes(b'{"synthetic":true}')
    result = child(f'''
        from pathlib import Path
        from data.hashing import canonical_json
        from scripts import diagnose_short_interest_count_guard_timing as d
        seams = d.OfflineSeams("c" * 40); seams.install()
        with d.loader.prior._OwnedOutput(Path({str(directory)!r}), lambda: None) as owned:
            names = d.loader.count.old.cache._inventory_names(owned._anchor[2], boundary=lambda: None)
            assert names == ("synthetic.private.json",)
            owned.check()
        assert not any(seams.denied.values())
        print(canonical_json({{"status":"readonly_original_constructor_inventory_closed","denied":seams.denied}}))
    ''')
    assert result[0]["status"] == "readonly_original_constructor_inventory_closed"
    assert not any(result[0]["denied"].values())
    assert sorted(path.name for path in directory.iterdir()) == ["synthetic.private.json"]


@pytest.mark.parametrize("kind", ["publish", "write", "socket", "credentials", "source", "native", "mutation", "subprocess",
    "future_credentials", "future_source"])
def test_actual_cold_handler_refuses_external_seams_before_the_operation(tmp_path, kind):
    result = child(f'''
        import ctypes, os, socket, subprocess
        from pathlib import Path
        from data.hashing import canonical_json
        from scripts import diagnose_short_interest_count_guard_timing as d
        directory = Path({str(tmp_path)!r})
        seams = d.OfflineSeams("c" * 40); seams.install()
        try:
            kind = {kind!r}
            if kind == "publish": d.loader.prior._OwnedOutput.publish(None, "new", {{}})
            elif kind == "write": os.open(directory / "new", os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
            elif kind == "socket": socket.socket()
            elif kind == "credentials": d.loader.count.read_named_keychain("massive")
            elif kind == "source": d.loader.count.run_registered(None)
            elif kind == "future_credentials": d.future_transport.read_named_keychain("massive")
            elif kind == "future_source": d.future_transport.CountCaptureOperation.dispatch(None, None, None, None)
            elif kind == "native": ctypes.CDLL("/usr/lib/libSystem.B.dylib")
            elif kind == "mutation": os.mkdir(directory / "new", 0o700)
            else: subprocess.run(["/bin/true"], cwd=directory, check=True)
        except d.CountGuardTimingRefusal:
            assert sum(seams.denied.values()) == 1
        else: raise AssertionError("forbidden seam passed")
        print(canonical_json({{"status":"external_operation_refused","denied":seams.denied}}))
    ''')
    assert result[0]["status"] == "external_operation_refused"
    assert sum(result[0]["denied"].values()) == 1
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("argv", [
    ["git", "show", "--output=/tmp/FABRICATED_ONLY", "c" * 40 + ":" + timing.DRIVER],
    ["git", "show", "c" * 40 + ":private/unregistered.json"],
    ["git", "cat-file", "--batch-all-objects", "--batch"],
    ["git", "status", "--ignored", "--untracked-files=all"],
    ["git", "ls-remote", "--exit-code", "origin", "refs/heads/other"],
    ["git", "ls-remote", "origin", "refs/heads/other"],
    ["git", "push", "origin", "HEAD"],
])
def test_nonmatching_or_mutating_Git_arguments_are_rejected_without_running(argv):
    seams = timing.OfflineSeams("c" * 40)
    with pytest.raises(timing.CountGuardTimingRefusal):
        seams.audit("subprocess.Popen", ("git", argv, str(timing.ROOT), {}))
    assert seams.git == 0 and seams.denied["subprocess"] == 1


def test_original_loader_ancestry_command_is_permitted_readonly_not_run():
    seams = timing.OfflineSeams("c" * 40)
    seams.audit("subprocess.Popen", ("git", ["git", "merge-base", "--is-ancestor",
        timing.loader.prior.V3_HEAD, "c" * 40], str(timing.ROOT), {}))
    assert seams.git == 1 and not any(seams.denied.values())


@pytest.mark.parametrize("argv", [
    ["git", "rev-parse", "--show-toplevel"], ["git", "rev-parse", "HEAD"],
    ["git", "branch", "--show-current"], ["git", "status", "--porcelain"],
    ["git", "status", "--porcelain=v2", "--branch", "--no-ahead-behind", "--untracked-files=all"],
    ["git", "ls-remote", "--exit-code", "origin", timing.loader.lane.REF],
    ["git", "show", "c" * 40 + ":" + timing.DRIVER],
])
def test_exact_original_Git_metadata_shapes_remain_permitted_without_execution(argv):
    seams = timing.OfflineSeams("c" * 40)
    seams.audit("subprocess.Popen", ("git", argv, str(timing.ROOT), {}))
    assert seams.git == 1 and not any(seams.denied.values())


def test_original_saved_cache_remote_producer_survives_fixed_readonly_hook(monkeypatch):
    from scripts import qualify_sharadar_companion as producer
    seams = timing.OfflineSeams("c" * 40)
    called = []
    def fake_git(argv, **kwargs):
        seams.audit("subprocess.Popen", ("git", argv, kwargs["cwd"], None))
        called.append(tuple(argv))
        return subprocess.CompletedProcess(argv, 0, "b" * 40 + "\t" + timing.loader.lane.REF + "\n", "")
    monkeypatch.setattr(subprocess, "run", fake_git)
    producer._guard_remote(timing.ROOT, "b" * 40)
    assert called == [("git", "ls-remote", "origin", timing.loader.lane.REF)]
    assert seams.git == 1 and not any(seams.denied.values())


def test_negative_snapshot_preserves_original_denial_role_without_command_values(monkeypatch):
    seams = timing.OfflineSeams("c" * 40)
    monkeypatch.setattr(timing, "_DIAGNOSTIC_SEAM", seams)
    monkeypatch.setattr(timing, "_DIAGNOSTIC_ORIGIN", (seams, timing._SEAMS[seams], object()))
    with pytest.raises(timing.CountGuardTimingRefusal):
        seams.audit("subprocess.Popen", ("git", ["git", "show", "--output=SECRET"], str(timing.ROOT), None))
    seams.audit("subprocess.Popen", ("git", ["git", "rev-parse", "HEAD"], str(timing.ROOT), None))
    summary = timing.negative_seam_summary()
    assert summary["state"] == "original_counter_snapshot" and summary["denied"]["subprocess"] == 1
    assert summary["first_denial_kind"] == "subprocess"
    assert summary["first_denial_command_role"] == "other_subprocess"
    assert summary["last_command_role"] == "local_head" and "SECRET" not in canonical_json(summary)
    seams.denied["subprocess"] = 0
    failed = timing.negative_seam_summary()
    assert failed["state"] == "integrity_refused" and failed["denied"] is None


def test_negative_snapshot_does_not_adopt_a_copied_origin(monkeypatch):
    seams = timing.OfflineSeams("c" * 40)
    monkeypatch.setattr(timing, "_DIAGNOSTIC_SEAM", seams)
    monkeypatch.setattr(timing, "_DIAGNOSTIC_ORIGIN", (seams, tuple([*timing._SEAMS[seams]]), object()))
    assert timing.negative_seam_summary()["state"] == "integrity_refused"


def test_no_callable_counter_rebase_can_clear_a_denial():
    seams = timing.OfflineSeams("c" * 40)
    with pytest.raises(timing.CountGuardTimingRefusal): seams.deny("write")
    seams.denied["write"] = 0
    seams.first_denial_kind = "none"; seams.first_denial_command_role = None
    rebase = getattr(seams, "_record", None)
    if callable(rebase): rebase()
    with pytest.raises(timing.CountGuardTimingRefusal, match="counter_changed"): seams.check()


def test_foreign_counter_key_never_executes_equality_during_projection(monkeypatch):
    calls = []
    class Foreign:
        __hash__ = object.__hash__
        def __eq__(self, unused): calls.append("eq"); return False
    seams = timing.OfflineSeams("c" * 40)
    monkeypatch.setattr(timing, "_DIAGNOSTIC_SEAM", seams)
    monkeypatch.setattr(timing, "_DIAGNOSTIC_ORIGIN", (seams, timing._SEAMS[seams], object()))
    keys = tuple(seams.denied); seams.denied.clear()
    seams.denied.update({Foreign(): 0, **{key: 0 for key in keys[1:]}})
    assert timing.negative_seam_summary()["state"] == "integrity_refused"
    assert calls == []


@pytest.mark.parametrize("slot", ["__hash__", "__eq__"])
def test_projection_refuses_changed_registry_identity_methods_before_lookup(monkeypatch, slot):
    calls = []
    seams = timing.OfflineSeams("c" * 40)
    monkeypatch.setattr(timing, "_DIAGNOSTIC_SEAM", seams)
    monkeypatch.setattr(timing, "_DIAGNOSTIC_ORIGIN", (seams, timing._SEAMS[seams], object()))
    def foreign(*unused): calls.append("called"); raise AssertionError("foreign identity method")
    monkeypatch.setattr(timing.OfflineSeams, slot, foreign)
    assert timing.negative_seam_summary()["state"] == "integrity_refused" and calls == []


@pytest.mark.parametrize("kind", ["counter_reset", "counter_bool", "counter_map_replaced", "head_replaced"])
def test_original_counter_and_argument_catalogue_pins_cannot_be_reset(kind):
    seams = timing.OfflineSeams("c" * 40)
    if kind == "counter_reset":
        with pytest.raises(timing.CountGuardTimingRefusal): seams.deny("write")
        seams.denied["write"] = 0
    elif kind == "counter_bool": seams.git = True
    elif kind == "counter_map_replaced": seams.denied = dict(seams.denied)
    else: seams.head = (" " + seams.head)[1:]
    with pytest.raises(timing.CountGuardTimingRefusal, match="counter_changed"): seams.check()


def test_finite_Git_quota_is_checked_against_original_counter_without_execution(monkeypatch):
    monkeypatch.setattr(timing, "MAXIMUM_GIT_COMMANDS", 1)
    seams = timing.OfflineSeams("c" * 40)
    args = ("git", ["git", "rev-parse", "HEAD"], str(timing.ROOT), {})
    seams.audit("subprocess.Popen", args)
    with pytest.raises(timing.CountGuardTimingRefusal): seams.audit("subprocess.Popen", args)
    assert seams.git == 1 and seams.denied["subprocess"] == 1


def test_exact_code_manifest_includes_dormant_settlement_imports_without_calling_them():
    expected = tuple(sorted(set((*timing.loader.code_paths(), timing.DRIVER,
        "research/short_interest_etf/native_count_recovery_budget.py",
        "scripts/short_interest_count_durable_budget.py",
        "scripts/short_interest_closed_count_chunk.py",
        "scripts/short_interest_count_durable_transport.py"))))
    assert timing.code_paths() == expected and len(expected) == 63
    policy = timing.protocol()
    assert policy["runtime_code_paths"] == list(expected)
    assert all(policy[name] == 0 for name in ("ticket_reservations", "new_claims", "new_HTTP",
        "new_STARTs", "new_charged_bytes", "new_files"))


def test_hostile_argument_methods_are_not_called_by_fixed_projection_or_audit():
    calls = []
    class Hostile:
        def __eq__(self, unused): calls.append("eq"); raise AssertionError("caller equality executed")
        def __str__(self): calls.append("str"); raise AssertionError("caller string executed")
    error = timing.CountGuardTimingRefusal(Hostile())
    projected = timing.failure_summary(error)
    assert projected["contract_code"] is None and "Hostile" not in canonical_json(projected)
    for args in (("git", [Hostile(), "status"], str(timing.ROOT), {}),
            ("git", ["git", "status"], Hostile(), {})):
        with pytest.raises(timing.CountGuardTimingRefusal): timing.OfflineSeams("c" * 40).audit("subprocess.Popen", args)
    assert calls == []


def test_changed_historical_catalogue_cannot_turn_show_into_output_option(monkeypatch):
    seams = timing.OfflineSeams("c" * 40)
    monkeypatch.setattr(timing, "HISTORICAL_HEADS", ("--output=/tmp/fabricated",))
    with pytest.raises(timing.CountGuardTimingRefusal, match="counter_changed"):
        seams.audit("subprocess.Popen", ("git", ["git", "show", "--output=/tmp/fabricated:" + timing.DRIVER],
            str(timing.ROOT), None))


@pytest.mark.parametrize("now,code", [(99.0, "clock_refused"), (1900.0, "window_exhausted"),
    (float("inf"), "clock_refused"), (True, "clock_refused")])
def test_whole_initialization_and_closure_clock_bound_is_strict(monkeypatch, now, code):
    monkeypatch.setattr(timing.time, "monotonic", lambda: now)
    previous = [100.0]
    with pytest.raises(timing.CountGuardTimingRefusal, match=code): timing._window(100.0, previous)
    assert previous == [100.0]


def test_default_unregistered_protocol_refuses_before_hook_or_source(monkeypatch):
    calls = []
    monkeypatch.setattr(timing, "PROTOCOL_SHA256", "PENDING")
    monkeypatch.setattr(timing.OfflineSeams, "install", lambda self: calls.append("hook"))
    monkeypatch.setattr(timing.loader, "load_registered_count_epoch_ledger", lambda *a, **k: calls.append("loader"))
    with pytest.raises(timing.CountGuardTimingRefusal, match="registration_pending"):
        timing.run_registered("c" * 40, "b" * 40)
    assert calls == []


def test_genuine_toy_loader_closes_before_empty_budget_sampling_with_real_cold_hook(tmp_path):
    result = child(f'''
        import os
        from pathlib import Path
        from pytest import MonkeyPatch
        from data.hashing import canonical_json, hash_bytes, hash_payload
        from scripts import diagnose_short_interest_count_guard_timing as d
        from test_short_interest_count_epoch_ledger_loader import Harness
        mp = MonkeyPatch(); root = Path({str(tmp_path)!r})
        h = Harness(mp, root)
        # Original four-epoch loader and closure witness determine the toy
        # baseline. The existing named cumulative-linkage seam is explicit.
        with h.load() as observed: model = observed._anchor[0]
        observed.closed_summary(); old = model.public_summary()
        p = d.plan_model
        for name, value in {{"BASELINE_LEDGER_SHA256":model.sha256,
            "PRIOR_STARTS":old["START_debits"], "PRIOR_CHARGED_BYTES":old["charged_response_bytes"],
            "HISTORICAL_START_CEILING":old["maximum_historical_STARTs"],
            "MAXIMUM_CUMULATIVE_STARTS":53, "MAXIMUM_CUMULATIVE_BYTES":old["maximum_historical_bytes"],
            "MISSING_POSITIONS":old["missing_transport_observation_positions"],
            "POSITIONS_PER_CHUNK":1, "MAXIMUM_CHUNKS":1, "EXTRA_ATTEMPTS_PER_CHUNK":2,
            "_PLAN_MINTS":{{}}, "_BUDGET_MINTS":{{}}, "_PLAN_KEYS":set()}}.items(): mp.setattr(p,name,value)
        for name, value in (("_BUDGETS",{{}}),("_TICKETS",{{}}),("_LOCKS",{{}}),("_FAILED",set()),("_CONSUMED",set())):
            mp.setattr(d.accounting,name,value)
        mp.setattr(d.accounting,"_EXPECTED_SOURCE_PROFILE",d.accounting._source_profile())
        mp.setattr(d,"ROOT",root); mp.setattr(d,"_INVOKED",False)
        for name in d.code_paths():
            path=root/name
            if not path.exists():
                path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(name.encode())
        mp.setattr(d,"PROTOCOL_SHA256",hash_payload(d.protocol()))
        os.chdir(root); before=set(root.rglob("*"))
        closed=d.run_registered("c"*40,"b"*40)
        assert closed["status"]=="closed_readonly_guard_timing_only"
        assert closed["new_ticket_reservations"]==0 and len(closed["samples_seconds"])==3
        assert not d.accounting._TICKETS and not any(closed["denied_seams"].values())
        assert set(root.rglob("*"))==before
        assert "EXPLICIT_toy_prior_cumulative_linkage_seam" in h.events
        assert h.events.count("saved_context_exited")>=2
        print(canonical_json({{"status":"genuine_toy_original_loader_and_empty_budget_closed",
            "sample_count":len(closed["samples_seconds"]),"new_tickets":len(d.accounting._TICKETS)}}))
    ''', timeout=60)
    assert result[-1] == {"status": "genuine_toy_original_loader_and_empty_budget_closed", "sample_count": 3, "new_tickets": 0}
