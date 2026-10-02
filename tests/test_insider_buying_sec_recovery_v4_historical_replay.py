"""Pinned blobs and invented worker results only; never an observed root replay."""
from __future__ import annotations

from dataclasses import replace
import importlib.util
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from data.hashing import hash_bytes
from research.insider_buying import sec_recovery_v4_plan as plan
from research import insider_buying_sec_recovery_v4_historical_replay as module


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def blobs():
    # Exact committed code bytes, not an execution of any retained source root.
    return tuple((name, (ROOT / name).read_bytes()) for name, _ in plan.HISTORICAL_FILES)


def test_historical_blob_inventory_accepts_the_exact_ordered_pins(blobs):
    module._validate_historical_blobs(blobs)
    assert tuple((name, hash_bytes(raw)) for name, raw in blobs) == plan.HISTORICAL_FILES


@pytest.mark.parametrize("case", (
    "reordered", "missing", "extra", "drift", "list", "wrong_path", "text_body", "wrong_item",
))
def test_historical_blob_inventory_refuses_every_source_shape_or_byte_drift(blobs, case):
    if case == "reordered":
        blobs = tuple(reversed(blobs))
    elif case == "missing":
        blobs = blobs[:-1]
    elif case == "extra":
        blobs = (*blobs, blobs[0])
    elif case == "drift":
        blobs = ((blobs[0][0], blobs[0][1] + b"\n"), *blobs[1:])
    elif case == "list":
        blobs = list(blobs)
    elif case == "wrong_path":
        blobs = (("research/invented.py", blobs[0][1]), *blobs[1:])
    elif case == "text_body":
        blobs = ((blobs[0][0], blobs[0][1].decode()), *blobs[1:])
    else:
        blobs = ([blobs[0][0], blobs[0][1]], *blobs[1:])
    with pytest.raises(module.HistoricalReplayError):
        module._validate_historical_blobs(blobs)


@pytest.mark.parametrize("event,args", (
    ("socket.__new__", ()), ("socket.connect", ()), ("socket.bind", ()),
    ("socket.getaddrinfo", ()), ("socket.sendto", ()),
    ("subprocess.Popen", ()), ("os.system", ()), ("os.fork", ()),
    ("os.exec", ()), ("os.posix_spawn", ()), ("ctypes.dlopen", ()),
    ("open", ("invented", "w", 0)), ("open", ("invented", "a", 0)),
    ("open", ("invented", "r+", 0)),
    ("open", ("invented", None, os.O_WRONLY)),
    ("open", ("invented", None, os.O_RDWR)),
    ("open", ("invented", None, os.O_CREAT)),
    ("open", ("invented", None, os.O_TRUNC)),
    ("os.remove", ()), ("os.rename", ()), ("os.mkdir", ()), ("os.rmdir", ()),
    ("os.link", ()), ("os.symlink", ()), ("os.chmod", ()),
    ("os.chown", ()), ("os.truncate", ()),
))
def test_worker_audit_refuses_transport_process_and_mutation_events(event, args):
    # Invoke the policy directly; no socket, process or filesystem action follows.
    with pytest.raises(module.HistoricalReplayError):
        module._audit_event(event, args)


@pytest.mark.parametrize("event,args", (
    ("open", ("invented", "r", os.O_RDONLY)),
    ("open", ("invented", "rb", os.O_RDONLY)),
    ("open", ("invented", None, os.O_RDONLY)),
    ("os.listdir", ("invented",)), ("os.scandir", ("invented",)),
))
def test_worker_audit_permits_read_only_custody_events(event, args):
    module._audit_event(event, args)


@pytest.fixture
def aggregate():
    # This is a fabricated worker-contract example, not a custody receipt.
    return {
        "kind": module.VERSION, "scope": "observed_offline_custody_replay",
        "repository_head": "f" * 40, "historical_commit": plan.HISTORICAL_COMMIT,
        "historical_validator_sha256": plan.HISTORICAL_VALIDATOR_SHA256,
        "worker_bootstrap_sha256": hash_bytes(module._BOOTSTRAP.encode()),
        "worker_source_sha256": hash_bytes((ROOT / module._WORKER_PATH).read_bytes()),
        "current_source_inventory_sha256": "1" * 64,
        "historical_files": [{"path": p, "sha256": s} for p, s in plan.HISTORICAL_FILES],
        "executed_modules": [{"path": p, "sha256": s, "source_kind": "historical_git_blob"}
                             for p, s in plan.HISTORICAL_FILES] + [{
                                 "path": module._WORKER_PATH,
                                 "sha256": hash_bytes((ROOT / module._WORKER_PATH).read_bytes()),
                                 "source_kind": "current_source_snapshot",
                             }],
        "historical_function_paths": [p for p, _ in plan.HISTORICAL_FILES],
        "source_union_sha256": "a" * 64, "partial_descriptor_sha256": "b" * 64,
        "diagnostic_descriptor_sha256": "c" * 64, "v4_plan_sha256": "d" * 64,
        "partition_sha256": "e" * 64, "proposed_unattempted_inventory_sha256": "f" * 64,
        "counts": {"prior_completed": 9539, "offline_corrected_diagnostic": 1,
                   "remaining_selected_reuse": 8139, "v3_completed": 1846,
                   "accepted_ambiguous_diagnostic": 1, "originally_unattempted": 79868},
        "total_parents": 99394, "source_bound_count": 19526,
        "v3_attempt_count": 1847, "v3_completed_count": 1846,
        "stopped_v3_disposition": "preserved_unresolved_not_resumable",
        "diagnostic_report_sha256": plan.OBSERVED_DIAGNOSTIC_ANCHORS["report_sha256"],
        "diagnostic_body_sha256": plan.OBSERVED_DIAGNOSTIC_ANCHORS["body_sha256"],
        "diagnostic_body_size_bytes": 7373,
        "current_byte_binding_required": True, "historical_environment_recreated": False,
        "frozen_files_may_be_thawed": False,
        "isolation": {"os_network_denied": True, "os_file_writes_denied": True,
                      "os_process_fork_denied": True, "audit_additional_processes_denied": True,
                      "source_only_lane_imports": True},
        "authority": {
            "source_authenticated": False, "official_acceptance_verified": False,
            "publication_time_verified": False, "point_in_time_data": False,
            "rights_verified": False, "canonical_evidence": False, "complete_corpus": False,
            "qc_authorized": False, "backtest_authorized": False, "execution_authorized": False,
            "dispatch_enabled": False, "output_written": False, "sec_dispatches": 0,
            "outcome_looks": 0, "qc_jobs": 0, "backtests": 0,
        },
    }


def test_aggregate_is_exact_hash_only_and_does_not_claim_an_environment_or_thaw(aggregate):
    assert module._validate_aggregate(aggregate) == aggregate
    assert sum(aggregate["counts"].values()) == aggregate["total_parents"]
    assert aggregate["source_bound_count"] == 19526
    assert not aggregate["historical_environment_recreated"]
    assert not aggregate["frozen_files_may_be_thawed"]


@pytest.mark.parametrize("bucket", ("offline_corrected_diagnostic", "accepted_ambiguous_diagnostic"))
def test_aggregate_requires_integer_counts_not_boolean_one(aggregate, bucket):
    aggregate["counts"][bucket] = True
    with pytest.raises(module.HistoricalReplayError, match="aggregate"):
        module._validate_aggregate(aggregate)


@pytest.mark.parametrize("bucket", tuple(module._COUNTS))
def test_aggregate_requires_exact_integer_types_in_every_count_bucket(aggregate, bucket):
    aggregate["counts"][bucket] = float(aggregate["counts"][bucket])
    with pytest.raises(module.HistoricalReplayError, match="aggregate"):
        module._validate_aggregate(aggregate)


@pytest.mark.parametrize("flag", (
    "os_network_denied", "os_file_writes_denied", "os_process_fork_denied",
    "audit_additional_processes_denied", "source_only_lane_imports",
))
def test_aggregate_requires_boolean_isolation_flags_not_integer_one(aggregate, flag):
    aggregate["isolation"][flag] = 1
    with pytest.raises(module.HistoricalReplayError, match="aggregate"):
        module._validate_aggregate(aggregate)


@pytest.mark.parametrize("field,value", (
    ("total_parents", 99393), ("source_bound_count", 19527), ("v3_attempt_count", 1846),
    ("v3_completed_count", 1847), ("diagnostic_body_size_bytes", True),
    ("diagnostic_report_sha256", "0" * 64), ("diagnostic_body_sha256", "0" * 64),
    ("historical_validator_sha256", "0" * 64), ("historical_commit", "0" * 40),
    ("repository_head", "not-a-commit"), ("partition_sha256", "z" * 64),
    ("current_byte_binding_required", False), ("historical_environment_recreated", True),
    ("frozen_files_may_be_thawed", True), ("raw_parent_locator", "/invented/private/body.bin"),
))
def test_aggregate_refuses_schema_scalar_anchor_and_authority_drift(aggregate, field, value):
    aggregate[field] = value
    with pytest.raises(module.HistoricalReplayError):
        module._validate_aggregate(aggregate)


@pytest.mark.parametrize("case", (
    "missing_field", "wrong_count", "reordered_files", "missing_trace", "trace_hash",
    "current_fallback", "repeated_trace", "extra_trace_field", "unknown_lane_path", "authority",
))
def test_aggregate_refuses_non_executed_or_changed_source_inventory(aggregate, case):
    if case == "missing_field":
        del aggregate["source_union_sha256"]
    elif case == "wrong_count":
        aggregate["counts"]["originally_unattempted"] += 1
    elif case == "reordered_files":
        aggregate["historical_files"].reverse()
    elif case == "missing_trace":
        aggregate["executed_modules"].pop()
    elif case == "trace_hash":
        aggregate["executed_modules"][0]["sha256"] = "0" * 64
    elif case == "current_fallback":
        aggregate["executed_modules"][0]["source_kind"] = "current_source_snapshot"
    elif case == "repeated_trace":
        aggregate["executed_modules"].append(dict(aggregate["executed_modules"][0]))
    elif case == "extra_trace_field":
        aggregate["executed_modules"][0]["locator"] = "/invented/private/body.bin"
    elif case == "unknown_lane_path":
        aggregate["executed_modules"][0]["path"] = "elsewhere/module.py"
    else:
        aggregate["authority"]["dispatch_enabled"] = True
    with pytest.raises(module.HistoricalReplayError):
        module._validate_aggregate(aggregate)


def test_sealed_receipt_is_copy_safe_and_reconstruction_cannot_grant_authority(aggregate):
    original = copy.deepcopy(aggregate)
    receipt = module._seal(aggregate)
    aggregate["counts"]["v3_completed"] = 0
    payload = receipt.to_payload()
    assert payload == original
    assert receipt.sha256 == hash_bytes(module._canonical(original))
    payload["authority"]["dispatch_enabled"] = True
    assert receipt.to_payload() == original
    raw = module._canonical(payload)
    forged = replace(receipt, _raw=raw, _sha256=hash_bytes(raw))
    with pytest.raises(module.HistoricalReplayError, match="receipt"):
        forged.to_payload()
    rebuilt = replace(receipt)
    with pytest.raises(module.HistoricalReplayError, match="receipt"):
        rebuilt.to_payload()


def test_loader_executes_the_supplied_historical_image_not_current_fallback(monkeypatch):
    # Invented tiny modules exercise loader mechanics only. Test-local pins never
    # flow into the observed entrypoint or prove real historical root custody.
    fake_blobs = tuple((path, ("MARKER = 'historical-%d'\ndef custody_call():\n"
                              "    return MARKER\n" % index).encode())
                       for index, (path, _) in enumerate(plan.HISTORICAL_FILES))
    monkeypatch.setattr(module, "HISTORICAL_FILES", tuple((p, hash_bytes(b)) for p, b in fake_blobs))
    current = tuple((path, b"MARKER = 'current'\n") for path, _ in fake_blobs)
    finder = module._HistoricalBlobFinder(fake_blobs, current)
    for index, (path, raw) in enumerate(fake_blobs):
        name, _ = module._module_name(path)
        spec = finder.find_spec(name)
        loaded = importlib.util.module_from_spec(spec)
        previous_profile = sys.getprofile()
        try:
            sys.setprofile(finder.profile)
            spec.loader.exec_module(loaded)
            assert loaded.custody_call() == f"historical-{index}"
        finally:
            sys.setprofile(previous_profile)
        assert loaded.__file__ == str(module.LANE_ROOT / path)
        assert loaded.__cached__ is None
        assert spec.origin == f"git:{plan.HISTORICAL_COMMIT}:{path}"
    assert finder.executed == [
        {"path": p, "sha256": hash_bytes(b), "source_kind": "historical_git_blob"}
        for p, b in fake_blobs
    ]
    assert finder.called == {p for p, _ in fake_blobs}
    with pytest.raises(module.HistoricalReplayError, match="inventory"):
        finder.find_spec("research.uninventoried_lane_module")
    assert finder.find_spec("invented_external_module") is None


@pytest.fixture
def mock_replay(monkeypatch, aggregate, blobs):
    """Mock every root replay/child; only parent contract checks run."""
    head = aggregate["repository_head"]
    executor = b"invented capture blob; never executed"
    diagnostic = b"invented capture diagnostic; never executed"
    sources = (*blobs, (module.DIAGNOSTIC_CAPTURE_PATH, diagnostic),
               (module._WORKER_PATH, (ROOT / module._WORKER_PATH).read_bytes()))
    aggregate["current_source_inventory_sha256"] = module._digest([
        {"path": path, "sha256": hash_bytes(raw)} for path, raw in sources])
    monkeypatch.setattr(module, "EXECUTOR_SHA256", hash_bytes(executor))

    def fake_git(*args):
        assert args[:2] == ("cat-file", "blob")
        commit, path = args[2].split(":", 1)
        if path == module.EXECUTOR_PATH:
            assert commit == plan.HISTORICAL_COMMIT
            return executor
        if path == module.DIAGNOSTIC_CAPTURE_PATH:
            assert commit == module.DIAGNOSTIC_CAPTURE_COMMIT
            return diagnostic
        assert commit == plan.HISTORICAL_COMMIT
        return dict(blobs)[path]

    calls = []

    def fake_worker(raw, timeout_seconds):
        assert type(timeout_seconds) is int and 1 <= timeout_seconds <= 600
        bundle = json.loads(raw)
        assert bundle["repository_head"] == head
        assert module._decode_sources(bundle["historical_sources"]) == blobs
        calls.append((raw, timeout_seconds))
        return SimpleNamespace(returncode=0, stdout=module._canonical(aggregate))

    monkeypatch.setattr(module, "_git", fake_git)
    monkeypatch.setattr(module, "_repository_snapshot", lambda: (head, ""))
    monkeypatch.setattr(module, "_source_snapshot", lambda: sources)
    monkeypatch.setattr(module, "_assert_sources_unchanged", lambda rows: None)
    monkeypatch.setattr(module, "_run_isolated_worker", fake_worker, raising=False)
    return SimpleNamespace(head=head, sources=sources, calls=calls, aggregate=aggregate)


def test_parent_seals_only_the_validated_mocked_worker_result(mock_replay):
    receipt = module.run_observed_historical_v3_custody_replay(expected_head=mock_replay.head)
    assert receipt.to_payload() == mock_replay.aggregate
    assert len(mock_replay.calls) == 1


def test_child_profile_denies_network_writes_and_additional_processes():
    policy = module._worker_policy()
    assert "(deny network*)" in policy and "(deny file-write*)" in policy
    assert "(deny process-fork)" in policy and "(deny process-exec)" in policy


@pytest.mark.parametrize("timeout", (True, 0, -1, 601, 1.0, "1"))
def test_parent_timeout_contract_refuses_before_a_mocked_worker(mock_replay, timeout):
    with pytest.raises(module.HistoricalReplayError, match="timeout"):
        module.run_observed_historical_v3_custody_replay(
            expected_head=mock_replay.head, timeout_seconds=timeout)
    assert not mock_replay.calls


def test_missing_os_sandbox_fails_closed_without_an_unsandboxed_fallback(mock_replay, monkeypatch):
    original = Path.is_file
    monkeypatch.setattr(Path, "is_file", lambda path: False if path == Path("/usr/bin/sandbox-exec") else original(path))
    with pytest.raises(module.HistoricalReplayError, match="sandbox"):
        module.run_observed_historical_v3_custody_replay(expected_head=mock_replay.head)
    assert not mock_replay.calls


@pytest.mark.parametrize("phase,field", ((2, "head"), (2, "status"), (3, "head"), (3, "status")))
def test_repository_head_and_status_must_remain_exact_across_mocked_replay(mock_replay, monkeypatch, phase, field):
    seen = 0

    def snapshot():
        nonlocal seen
        seen += 1
        if seen == phase:
            return ("0" * 40, "") if field == "head" else (mock_replay.head, " M unrelated.py\n")
        return mock_replay.head, ""

    monkeypatch.setattr(module, "_repository_snapshot", snapshot)
    with pytest.raises(module.HistoricalReplayError, match="context|HEAD|status|dirty"):
        module.run_observed_historical_v3_custody_replay(expected_head=mock_replay.head)
    assert len(mock_replay.calls) == int(phase == 3)


@pytest.mark.parametrize("path", [p for p, _ in plan.HISTORICAL_FILES])
def test_each_frozen_disk_image_drift_refuses_before_mocked_worker(mock_replay, monkeypatch, path):
    changed = tuple((p, raw + b"\n" if p == path else raw) for p, raw in mock_replay.sources)
    monkeypatch.setattr(module, "_source_snapshot", lambda: changed)
    with pytest.raises(module.HistoricalReplayError, match="frozen current validator"):
        module.run_observed_historical_v3_custody_replay(expected_head=mock_replay.head)
    assert not mock_replay.calls


def test_parent_rechecks_sources_after_mocked_worker(mock_replay, monkeypatch):
    calls = 0

    def unchanged(_sources):
        nonlocal calls
        calls += 1
        if calls == 2:
            module._refuse("captured current code changed during replay")

    monkeypatch.setattr(module, "_assert_sources_unchanged", unchanged)
    with pytest.raises(module.HistoricalReplayError, match="changed during replay"):
        module.run_observed_historical_v3_custody_replay(expected_head=mock_replay.head)
    assert len(mock_replay.calls) == 1


@pytest.mark.parametrize("case", ("wrong_head", "unknown_source", "wrong_current_hash", "wrong_inventory", "wrong_wrapper", "wrong_bootstrap", "failed", "oversized", "invalid_json"))
def test_parent_refuses_bad_mocked_worker_envelopes(mock_replay, monkeypatch, case):
    payload = copy.deepcopy(mock_replay.aggregate)
    if case == "wrong_head":
        payload["repository_head"] = "0" * 40
    elif case in ("unknown_source", "wrong_current_hash"):
        payload["executed_modules"].append({
            "path": "research/invented.py" if case == "unknown_source" else module._WORKER_PATH,
            "sha256": "0" * 64, "source_kind": "current_source_snapshot",
        })
        if case == "wrong_current_hash":
            payload["executed_modules"][-1]["path"] = module.DIAGNOSTIC_CAPTURE_PATH
    elif case == "wrong_inventory":
        payload["current_source_inventory_sha256"] = "0" * 64
    elif case == "wrong_wrapper":
        payload["worker_source_sha256"] = "0" * 64
        payload["executed_modules"][-1]["sha256"] = "0" * 64
    elif case == "wrong_bootstrap":
        payload["worker_bootstrap_sha256"] = "0" * 64
    raw = (b"x" * (module._MAX_OUTPUT_BYTES + 1) if case == "oversized"
           else b"not json" if case == "invalid_json" else module._canonical(payload))
    monkeypatch.setattr(module, "_run_isolated_worker", lambda *_, **__: SimpleNamespace(
        returncode=1 if case == "failed" else 0, stdout=raw))
    with pytest.raises(module.HistoricalReplayError):
        module.run_observed_historical_v3_custody_replay(expected_head=mock_replay.head)


def test_audit_hook_blocks_real_child_operations_but_preserves_reading(tmp_path):
    # This child installs only the audit policy, not the observed replay worker.
    # Every attempted operation is refused before any network/process/mutation.
    sentinel = tmp_path / "invented-read-only.txt"
    sentinel.write_text("invented custody")
    script = r"""
import json, os, pathlib, socket, subprocess, sys
sys.path.insert(0, sys.argv[1])
from research import insider_buying_sec_recovery_v4_historical_replay as m
path = pathlib.Path(sys.argv[2])
sys.addaudithook(m._audit_event)
assert path.read_text() == 'invented custody'
actions = (
    lambda: socket.socket(),
    lambda: socket.getaddrinfo('blocked.invalid', 443),
    lambda: subprocess.Popen([sys.executable, '-c', 'raise SystemExit(99)']),
    lambda: path.write_text('must never replace custody'),
    lambda: path.unlink(),
)
denied = 0
for action in actions:
    try:
        action()
    except m.HistoricalReplayError:
        denied += 1
    else:
        raise AssertionError('audit failed to refuse')
assert path.read_text() == 'invented custody'
print(json.dumps({'denied': denied, 'read_preserved': True}))
"""
    result = subprocess.run(
        (str(Path(sys.executable).resolve()), "-I", "-S", "-B", "-c", script, str(ROOT), str(sentinel)),
        cwd=ROOT, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
        capture_output=True, text=True, check=True, timeout=30,
    )
    assert json.loads(result.stdout) == {"denied": 5, "read_preserved": True}
    assert sentinel.read_text() == "invented custody"


def test_source_only_inventory_includes_required_empty_packages_and_ml_helpers(blobs):
    current = (("data/__init__.py", b""), ("research/__init__.py", b""),
               ("ml/__init__.py", b""), ("ml/immutable_io.py", b"MARKER = 'invented'\n"))
    assert module._decode_sources(module._encode_sources(current)) == current
    finder = module._HistoricalBlobFinder(blobs, current)
    for path, _ in current:
        name, _ = module._module_name(path)
        spec = finder.find_spec(name)
        loaded = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loaded)
        assert loaded.__cached__ is None
        assert spec.origin == "snapshot:" + path
    with pytest.raises(module.HistoricalReplayError, match="inventory"):
        finder.find_spec("ml.uninventoried_module")
    with pytest.raises(module.HistoricalReplayError, match="inventory"):
        finder.find_spec("assistant.invented")


def test_current_source_inventory_captures_only_the_two_needed_ml_modules():
    inventory = dict(module._source_snapshot())
    assert {p for p in inventory if p.startswith("ml/")} == {
        "ml/__init__.py", "ml/immutable_io.py",
    }
    for path in ("data/__init__.py", "research/__init__.py", "ml/__init__.py"):
        assert path in inventory


@pytest.mark.parametrize("case", ("empty_module", "drift", "duplicate", "extra", "raw_locator", "unknown_namespace"))
def test_source_only_decoding_refuses_drift_repetition_and_uninventoried_shapes(case):
    rows = module._encode_sources((("research/invented.py", b"MARKER = 1\n"),))
    if case == "empty_module":
        rows = module._encode_sources((("research/invented.py", b""),))
    elif case == "drift":
        rows[0]["sha256"] = "0" * 64
    elif case == "duplicate":
        rows *= 2
    elif case == "extra":
        rows[0]["unexpected"] = True
    elif case == "raw_locator":
        rows[0]["path"] = "/invented/private/body.bin"
    else:
        rows[0]["path"] = "execution/invented.py"
    with pytest.raises(module.HistoricalReplayError):
        module._decode_sources(rows)


def test_bounded_child_runner_uses_isolated_python_and_only_minimal_environment(monkeypatch):
    # An invented bootstrap reports flags/environment only, and never imports
    # historical modules, supplied artifacts, transports, or the replay worker.
    script = ("import json,os,sys\n"
              "sys.stdin.buffer.read()\n"
              "print(json.dumps({'environment': sorted(os.environ),"
              " 'isolated':sys.flags.isolated,'no_bytecode':sys.flags.dont_write_bytecode}))\n")
    monkeypatch.setattr(module, "_BOOTSTRAP", script)
    monkeypatch.setenv("INVENTED_SEC_TOKEN", "must-not-reach-child")
    monkeypatch.setenv("PYTHONPATH", "/invented/untrusted/site")
    real_popen = subprocess.Popen
    captured = []

    def capture(command, **kwargs):
        captured.append((command, kwargs))
        # macOS refuses applying another sandbox inside the network-denied
        # pytest parent. The invented flags-only child inherits that parent;
        # the actual worker OS profile is verified separately outside pytest.
        assert command[:2] == ("/usr/bin/sandbox-exec", "-p")
        return real_popen(command[3:], **kwargs)

    monkeypatch.setattr(module.subprocess, "Popen", capture)
    result = module._run_isolated_worker(b"invented", 30)
    assert result.returncode == 0
    flags = json.loads(result.stdout)
    assert flags["isolated"] == flags["no_bytecode"] == 1
    assert "INVENTED_SEC_TOKEN" not in flags["environment"]
    assert "PYTHONPATH" not in flags["environment"]
    command, kwargs = captured[0]
    assert command[0] == "/usr/bin/sandbox-exec" and "-I" in command and "-S" in command and "-B" in command
    assert kwargs["cwd"] == module.LANE_ROOT
    assert kwargs["env"] == {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}


def test_bounded_child_runner_refuses_streaming_output_overflow(monkeypatch):
    monkeypatch.setattr(module, "_BOOTSTRAP", (
        "import sys\nsys.stdin.buffer.read()\n"
        f"sys.stdout.buffer.write(b'x' * {module._MAX_OUTPUT_BYTES + 1})\n"
        "sys.stdout.buffer.flush()\n"
    ))
    real_popen = subprocess.Popen
    monkeypatch.setattr(module.subprocess, "Popen", lambda command, **kwargs:
                        real_popen(command[3:], **kwargs))
    with pytest.raises(module.HistoricalReplayError, match="output cap"):
        module._run_isolated_worker(b"invented", 30)
