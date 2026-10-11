"""Synthetic-only v4 wrapper coverage; never the real preflight or assessment."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import sys
from types import MappingProxyType, SimpleNamespace

import pytest

from scripts import assess_arv2_relocated_sources_v4 as tool

REAL_ROOT = tool.ROOT
REAL_OUTPUT = tool.OUTPUT


@pytest.fixture(autouse=True)
def real_artifact_tripwire(monkeypatch):
    original = tool.audit._open_absolute_directory

    def guarded(path):
        assert path != REAL_ROOT
        assert not path.is_relative_to(REAL_ROOT / "artifacts"), "real artifact access attempted"
        return original(path)

    monkeypatch.setattr(tool.audit, "_open_absolute_directory", guarded)


@pytest.fixture
def scope(tmp_path, monkeypatch):
    if (sys.platform != "darwin" or not hasattr(stat, "UF_TRACKED")
            or not hasattr(os.stat_result, "st_flags")):
        pytest.skip("Darwin/APFS synthetic filesystem integration")
    anchor = tmp_path / "Code"
    anchor.mkdir(mode=0o700)
    root = anchor / "lane"
    root.mkdir(mode=0o755)
    root.chmod(0o755)
    expected, sources = {}, []
    for package, leaves in tool.v1.PACKAGES.items():
        directory = root
        for component in Path(package).parts:
            directory = directory / component
            if not directory.exists():
                directory.mkdir(mode=0o700)
        for leaf in leaves:
            path = directory / leaf
            raw = ("synthetic-only-" + leaf).encode()
            path.write_bytes(raw)
            path.chmod(0o600)
            sources.append(path)
            expected[str(path.relative_to(root))] = {
                "kind": "file", "metadata": tool.audit._metadata(path.stat()),
                "sha256": hashlib.sha256(raw).hexdigest(), "contains_old_root_literal": False}
    output = root / "artifacts/analyst_revisions_v2/relocation_trial" / REAL_OUTPUT.name
    output.parent.mkdir(mode=0o700)
    vintage = root / tool.v1.VINTAGE
    # Synthetic fixture device only; production pins are never learned or changed.
    monkeypatch.setattr(tool.policy, "PROSPECTIVE_DEVICE", root.stat().st_dev)
    # Synthetic-only contract: no native timestamp setter, no production refresh.
    pairs = {path: (expected[path]["metadata"]["ctime_ns"] - 1,
                    expected[path]["metadata"]["ctime_ns"])
             for path in tool.CTIME_PROJECTION}
    monkeypatch.setattr(tool, "CTIME_PROJECTION", MappingProxyType(pairs))
    monkeypatch.setattr(tool, "CTIME_PROJECTION_SHA256",
                        hashlib.sha256(tool.audit._json_bytes(pairs)).hexdigest())
    monkeypatch.setattr(tool, "ROOT", root)
    monkeypatch.setattr(tool, "OUTPUT", output)
    monkeypatch.setattr(tool, "__file__", str(root / "scripts" / "synthetic_v4.py"))
    monkeypatch.setattr(tool.v1, "ROOT", root)
    monkeypatch.setattr(tool.policy, "VINTAGE_PATH", vintage)
    monkeypatch.setattr(tool.policy, "VINTAGE_METADATA", MappingProxyType(tool.audit._metadata(vintage.stat())))
    monkeypatch.chdir(root)
    events, observations = [], []
    vintage_inode = vintage.stat().st_ino

    def names(_native, fd):
        inode = os.fstat(fd).st_ino
        observations.append(inode)
        events.append("names")
        return tuple(name for name, _size, _digest in tool.policy.XATTR_PINS) if inode == vintage_inode else (b"com.apple.provenance",)

    def snapshot(fd):
        events.append("snapshot")
        return {"acl_empty": True, "xattrs": {"synthetic": {"size": 1, "sha256": "1" * 64}}}

    def reports(_root):
        events.append("reports")
        assert output.is_dir()
        assert list(output.iterdir()) == []
        historical = deepcopy(expected)
        for path, row in historical.items():
            row["metadata"]["dev"] = tool.policy.HISTORICAL_DEVICE
            if path in tool.CTIME_PROJECTION:
                row["metadata"]["ctime_ns"] = tool.CTIME_PROJECTION[path][0]
        return ({"census": {"entries": deepcopy(historical)}}, {"census": {"entries": historical}})

    def consume():
        events.append("consume")
        assert output.is_dir()
        assert len([path.read_bytes() for path in sources]) == 15
        return {"synthetic_rows": 15}

    monkeypatch.setattr(tool.policy.legacy, "_native", lambda: object())
    monkeypatch.setattr(tool.policy, "_names", names)
    monkeypatch.setattr(tool.policy, "snapshot", snapshot)
    monkeypatch.setattr(tool.v1, "_read_pinned_reports", reports)
    monkeypatch.setattr(tool.v1, "_load_sources", consume)
    return SimpleNamespace(root=root, output=output, vintage=vintage, sources=sources,
                           expected=expected, events=events, observations=observations)


def invoke(mode="--assess", pin=None):
    return tool.main([mode, "--expected-profile-sha256", pin or tool.profile_sha256()])


def test_profile_is_fresh_and_has_no_implicit_authority():
    first = tool.profile()
    digest = tool.profile_sha256()
    first["policy"]["vintage_metadata"]["ino"] = 0
    first["source_packages"].clear()
    assert tool.profile_sha256() == digest
    assert first != tool.profile()
    assert tool.profile()["independent_review_required_before_assessment"] is True
    assert tool.profile()["separately_recorded_run_authority_required"] is True
    for flag in ("historical_audit_accepted", "historical_security_equivalence", "continuous_stability_proven",
                 "all_worktree_artifacts_executable", "formal_admission", "production_publication_authorized",
                 "provider_or_qc_contact"):
        assert tool.profile()[flag] is False


@pytest.mark.parametrize("arguments", [[], ["--assess"], ["--preflight-only"],
                                      ["--assess", "--preflight-only", "--expected-profile-sha256", "0" * 64]])
def test_cli_requires_exact_mode_and_pin(arguments):
    with pytest.raises(SystemExit) as error:
        tool.main(arguments)
    assert error.value.code == 2


def test_metadata_preflight_checks_all_names_before_values_without_allocating(scope, capsys):
    assert invoke("--preflight-only") == 0
    result = json.loads(capsys.readouterr().out)
    assert result["directory_count"] == 12
    assert result["file_count"] == 15
    assert len(result["inventory"]) == 27
    assert scope.events.index("snapshot") == 27
    assert len(scope.observations) == 54
    assert "consume" not in scope.events and "reports" not in scope.events
    assert not scope.output.exists()
    assert result["source_contents_read"] is result["source_reauthenticated"] is False
    assert result["output_allocated_by_preflight"] is False


@pytest.mark.parametrize("vintage", [False, True])
def test_wrong_names_refuse_before_any_value_read(scope, monkeypatch, vintage):
    original = tool.policy._names
    target = scope.vintage if vintage else scope.sources[-1]
    inode = target.stat().st_ino

    def names(native, fd):
        return (b"unknown-private-name",) if os.fstat(fd).st_ino == inode else original(native, fd)

    monkeypatch.setattr(tool.policy, "_names", names)
    with pytest.raises(tool.audit.Refusal, match="preflight_.*_names"):
        invoke("--preflight-only")
    assert "snapshot" not in scope.events
    assert not scope.output.exists()


def test_vintage_metadata_drift_refuses_before_value_observation(scope, monkeypatch):
    pinned = dict(tool.policy.VINTAGE_METADATA)
    pinned["ctime_ns"] += 1
    monkeypatch.setattr(tool.policy, "VINTAGE_METADATA", MappingProxyType(pinned))
    with pytest.raises(tool.audit.Refusal, match="preflight_vintage_metadata"):
        invoke("--preflight-only")
    assert "snapshot" not in scope.events
    assert not scope.output.exists()


def test_preflight_endpoint_name_drift_refuses(scope, monkeypatch):
    original = tool.policy._names
    calls = 0

    def names(native, fd):
        nonlocal calls
        calls += 1
        return () if calls == 28 else original(native, fd)

    monkeypatch.setattr(tool.policy, "_names", names)
    with pytest.raises(tool.audit.Refusal, match="preflight_names_changed"):
        invoke("--preflight-only")
    assert scope.events.count("snapshot") == 1
    assert not scope.output.exists()


@pytest.mark.parametrize("kind", ["fifo", "symlink", "public_mode"])
def test_preflight_refuses_wrong_type_or_mode_before_leaf_open(scope, monkeypatch, kind):
    source = scope.sources[0]
    if kind == "public_mode":
        source.chmod(0o644)
    else:
        source.unlink()
        if kind == "fifo":
            os.mkfifo(source, 0o600)
        else:
            source.symlink_to(scope.sources[1])
    original = os.open
    attempted = []

    def opened(path, *args, **kwargs):
        if path == source.name and kwargs.get("dir_fd") is not None:
            attempted.append(path)
            raise AssertionError("wrong-type source was opened")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(tool.os, "open", opened)
    with pytest.raises(tool.audit.Refusal, match="preflight_private_regular_required"):
        invoke("--preflight-only")
    assert attempted == []


@pytest.mark.parametrize("mismatch", ["cwd", "module", "legacy_root", "policy_path", "profile", "platform"])
def test_preallocation_guards_touch_no_output_or_source(scope, monkeypatch, mismatch):
    pin = tool.profile_sha256()
    if mismatch == "cwd":
        monkeypatch.chdir(scope.root.parent)
    elif mismatch == "module":
        monkeypatch.setattr(tool, "__file__", str(scope.root.parent / "scripts" / "wrong.py"))
    elif mismatch == "legacy_root":
        monkeypatch.setattr(tool.v1, "ROOT", scope.root.parent)
    elif mismatch == "policy_path":
        monkeypatch.setattr(tool.policy, "VINTAGE_PATH", scope.root / "different")
    elif mismatch == "profile":
        pin = "0" * 64
    else:
        def unsupported():
            raise tool.audit.Refusal("synthetic_platform_refusal")
        monkeypatch.setattr(tool.v1, "_require_supported_platform", unsupported)
    with pytest.raises(tool.audit.Refusal):
        invoke(pin=pin)
    assert scope.events == []
    assert not scope.output.exists()


def test_success_spends_directory_before_reads_and_keeps_false_gates(scope, monkeypatch, capsys):
    syncs = []
    original = os.fsync

    def sync(fd):
        syncs.append(os.fstat(fd).st_ino)
        original(fd)

    original_preflight = tool.preflight_scope

    def preflight():
        assert scope.output.stat().st_ino in syncs
        assert scope.output.parent.stat().st_ino in syncs
        return original_preflight()

    monkeypatch.setattr(tool.os, "fsync", sync)
    monkeypatch.setattr(tool, "preflight_scope", preflight)
    assert invoke() == 0
    raw = (scope.output / "report.json").read_bytes()
    report = json.loads(raw)
    assert report["complete"] is report["source_reauthenticated"] is True
    assert report["file_count"] == 15 and report["directory_count"] == 12
    assert scope.events.count("consume") == 1
    assert report["profile_sha256"] == tool.profile_sha256()
    assert hashlib.sha256(raw).hexdigest() in capsys.readouterr().out
    for flag in ("historical_audit_accepted", "historical_security_equivalence", "continuous_stability_proven",
                 "all_worktree_artifacts_executable", "formal_admission", "production_publication_authorized",
                 "provider_or_qc_contact", "output_acl_xattr_envelope_proven"):
        assert report[flag] is False
    with pytest.raises(FileExistsError):
        invoke()
    assert (scope.output / "report.json").read_bytes() == raw


@pytest.mark.parametrize("stage", ["preflight", "reports", "consumer"])
def test_interrupt_leaves_spent_directory_without_retry(scope, monkeypatch, stage):
    def interrupted(*_args):
        assert scope.output.is_dir()
        raise KeyboardInterrupt()
    owner, name = {"preflight": (tool, "preflight_scope"), "reports": (tool.v1, "_read_pinned_reports"),
                   "consumer": (tool.v1, "_load_sources")}[stage]
    monkeypatch.setattr(owner, name, interrupted)
    with pytest.raises(KeyboardInterrupt):
        invoke()
    assert scope.output.is_dir()
    assert list(scope.output.iterdir()) == []
    with pytest.raises(FileExistsError):
        invoke()


@pytest.mark.parametrize("stage", ["preflight", "reports", "consumer"])
def test_refusal_report_redacts_private_error_and_remains_spent(scope, monkeypatch, stage, capsys):
    def failed(*_args):
        raise ValueError("PRIVATE-SYNTHETIC-SOURCE-OR-ATTRIBUTE")
    owner, name = {"preflight": (tool, "preflight_scope"), "reports": (tool.v1, "_read_pinned_reports"),
                   "consumer": (tool.v1, "_load_sources")}[stage]
    monkeypatch.setattr(owner, name, failed)
    assert invoke() == 1
    raw = (scope.output / "report.json").read_bytes()
    report = json.loads(raw)
    assert report["complete"] is report["source_reauthenticated"] is False
    assert report["refusal_code"] == "current_security_or_source_refused"
    assert b"PRIVATE-SYNTHETIC" not in raw
    assert "PRIVATE-SYNTHETIC" not in capsys.readouterr().out
    with pytest.raises(FileExistsError):
        invoke()


@pytest.mark.parametrize("kind", ["extra", "pending", "ctime", "rename"])
def test_claim_directory_change_blocks_publication_and_is_retained(scope, monkeypatch, kind):
    original = tool.v1._load_sources
    retained = scope.output.with_name("retained-synthetic-original")

    def consume():
        result = original()
        if kind in ("extra", "pending"):
            (scope.output / ("foreign" if kind == "extra" else "report.json.pending")).write_bytes(b"retain")
        elif kind == "ctime":
            scope.output.chmod(0o750)
            scope.output.chmod(0o700)
        else:
            scope.output.rename(retained)
            scope.output.mkdir(mode=0o700)
        return result

    monkeypatch.setattr(tool.v1, "_load_sources", consume)
    with pytest.raises(tool.audit.Refusal, match="assessment_directory_changed"):
        invoke()
    assert not (scope.output / "report.json").exists()
    assert scope.output.exists()
    if kind == "rename":
        assert retained.exists()


@pytest.mark.parametrize("failure", ["before", "after"])
def test_publication_failure_never_prints_success_even_if_complete_report_exists(scope, monkeypatch, capsys, failure):
    original = tool.audit._publish_report

    def publish(fd, name, raw):
        if failure == "after":
            original(fd, name, raw)
        raise tool.audit.Refusal("synthetic_publish_failure")

    monkeypatch.setattr(tool.audit, "_publish_report", publish)
    with pytest.raises(tool.audit.Refusal, match="synthetic_publish_failure"):
        invoke()
    assert scope.output.is_dir()
    assert capsys.readouterr().out == ""
    if failure == "after":
        assert json.loads((scope.output / "report.json").read_bytes())["complete"] is True
    with pytest.raises(FileExistsError):
        invoke()


def test_postpublication_extra_leaf_refuses_and_retains_report(scope, monkeypatch, capsys):
    original = tool.audit._publish_report

    def publish(fd, name, raw):
        digest = original(fd, name, raw)
        (scope.output / "foreign-after").write_bytes(b"retain")
        return digest

    monkeypatch.setattr(tool.audit, "_publish_report", publish)
    with pytest.raises(tool.audit.Refusal):
        invoke()
    assert (scope.output / "report.json").exists()
    assert (scope.output / "foreign-after").exists()
    assert capsys.readouterr().out == ""


def test_guarded_preopen_check_blocks_wrong_object_before_open(scope, monkeypatch):
    source = scope.sources[0]
    source.unlink()
    os.mkfifo(source, 0o600)
    original = os.open

    def opened(path, *args, **kwargs):
        if path == source.name and kwargs.get("dir_fd") is not None:
            raise AssertionError("guarded consumer opened wrong-type source")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(tool.os, "open", opened)
    with pytest.raises(tool.audit.Refusal, match="source_preopen_identity"):
        tool._guarded_consume(scope.root, scope.expected, lambda: pytest.fail("consumer reached"), tool.policy.snapshot)


@pytest.mark.parametrize("field", ["ctime_ns", "mtime_ns", "mode", "uid", "gid", "flags", "nlink", "size", "dev", "ino"])
def test_guarded_consumer_retains_each_v1_postconsume_metadata_guard(scope, monkeypatch, field):
    target = scope.sources[0].stat().st_ino
    original = tool.audit._metadata
    consumed = False

    def metadata(info):
        result = original(info)
        if consumed and info.st_ino == target:
            result[field] += 1
        return result

    def consume():
        nonlocal consumed
        consumed = True
        return {}

    monkeypatch.setattr(tool.audit, "_metadata", metadata)
    with pytest.raises(tool.audit.Refusal, match="source_changed_across_consumer"):
        tool._guarded_consume(scope.root, scope.expected, consume, tool.policy.snapshot)
    assert consumed is True


def test_guarded_consumer_rechecks_bytes_independently_of_metadata(scope, monkeypatch):
    original = tool.v1._digest_held
    consumed = False

    def digest(fd, size):
        return "0" * 64 if consumed else original(fd, size)

    def consume():
        nonlocal consumed
        consumed = True
        return {}

    monkeypatch.setattr(tool.v1, "_digest_held", digest)
    with pytest.raises(tool.audit.Refusal, match="source_hash_after_consumer"):
        tool._guarded_consume(scope.root, scope.expected, consume, tool.policy.snapshot)


def test_cooperative_budget_checks_return_and_restores_timer(monkeypatch):
    clock = iter([0.0, 2.0])
    timers, handlers = [], []
    sentinel = object()
    monkeypatch.setattr(tool.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(tool.signal, "getitimer", lambda _kind: (0, 0))
    monkeypatch.setattr(tool.signal, "getsignal", lambda _kind: sentinel)
    monkeypatch.setattr(tool.signal, "signal", lambda _kind, handler: handlers.append(handler))
    monkeypatch.setattr(tool.signal, "setitimer", lambda _kind, delay: timers.append(delay))
    with pytest.raises(tool.audit.Refusal, match="cooperative_budget_exceeded"):
        with tool._budget(1):
            pass
    assert timers == [1, 0]
    assert handlers[-1] is sentinel


@pytest.mark.parametrize("event", ["fsync_failure", "metadata_drift"])
def test_claim_sync_failure_or_drift_is_spent_before_source_reads(scope, monkeypatch, event):
    original = os.fsync

    def sync(fd):
        if os.fstat(fd).st_ino == scope.output.stat().st_ino:
            if event == "fsync_failure":
                raise OSError("synthetic fsync refusal")
            scope.output.chmod(0o750)
            scope.output.chmod(0o700)
        original(fd)

    monkeypatch.setattr(tool.os, "fsync", sync)
    with pytest.raises((OSError, tool.audit.Refusal)):
        invoke()
    assert scope.output.is_dir()
    assert list(scope.output.iterdir()) == []
    assert scope.events == []
    with pytest.raises(FileExistsError):
        invoke()


@pytest.mark.parametrize("target_kind", ["source", "directory"])
def test_guarded_security_snapshot_drift_is_independent_of_unchanged_metadata(scope, target_kind):
    target = scope.sources[0] if target_kind == "source" else scope.sources[0].parent
    inode = target.stat().st_ino
    consumed = False

    def snapshot(fd):
        return {"synthetic-security": 1 if consumed and os.fstat(fd).st_ino == inode else 0}

    def consume():
        nonlocal consumed
        consumed = True
        return {}

    code = "source_security_changed_across_consumer" if target_kind == "source" else "directory_security_changed_across_consumer"
    with pytest.raises(tool.audit.Refusal, match=code):
        tool._guarded_consume(scope.root, scope.expected, consume, snapshot)
    assert consumed


@pytest.mark.parametrize("kind", ["source", "directory"])
def test_guarded_initial_security_read_metadata_drift_precedes_consumer(scope, monkeypatch, kind):
    target = scope.sources[0] if kind == "source" else scope.sources[0].parent
    inode = target.stat().st_ino
    original = tool.audit._metadata
    changed = False

    def metadata(info):
        result = original(info)
        if changed and info.st_ino == inode:
            result["ctime_ns"] += 1
        return result

    def snapshot(fd):
        nonlocal changed
        if os.fstat(fd).st_ino == inode:
            changed = True
        return {}

    monkeypatch.setattr(tool.audit, "_metadata", metadata)
    code = "source_changed_during_initial_read" if kind == "source" else "directory_changed_during_security_read"
    with pytest.raises(tool.audit.Refusal, match=code):
        tool._guarded_consume(scope.root, scope.expected, lambda: pytest.fail("consumer reached"), snapshot)


def test_guarded_initial_hash_refuses_before_consumer(scope, monkeypatch):
    monkeypatch.setattr(tool.v1, "_digest_held", lambda _fd, _size: "0" * 64)
    with pytest.raises(tool.audit.Refusal, match="current_source_hash"):
        tool._guarded_consume(scope.root, scope.expected, lambda: pytest.fail("consumer reached"), tool.policy.snapshot)


@pytest.mark.parametrize("phase", ["initial", "after_consumer", "after_final_hash"])
def test_guarded_named_identity_rechecked_at_each_boundary(scope, monkeypatch, phase):
    source = sorted(scope.sources)[0]
    original = os.stat
    matching_calls = 0
    consumed = False
    # Pre-open, post-open, post-consumer, after-final-hash named samples.
    changed_call = {"initial": 2, "after_consumer": 3, "after_final_hash": 4}[phase]

    def named(path, *args, **kwargs):
        nonlocal matching_calls
        info = original(path, *args, **kwargs)
        if path == source.name and kwargs.get("dir_fd") is not None:
            # Different packages may share a basename; bind the test-owned inode.
            if info.st_ino == source.stat().st_ino:
                matching_calls += 1
                if matching_calls == changed_call:
                    fields = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
                    fields["st_ino"] += 1
                    return SimpleNamespace(**fields)
        return info

    def consume():
        nonlocal consumed
        consumed = True
        return {}

    monkeypatch.setattr(tool.os, "stat", named)
    code = {"initial": "current_source_named_identity", "after_consumer": "source_changed_across_consumer",
            "after_final_hash": "source_changed_during_final_read"}[phase]
    with pytest.raises(tool.audit.Refusal, match=code):
        tool._guarded_consume(scope.root, scope.expected, consume, tool.policy.snapshot)
    assert consumed is (phase != "initial")


def test_guarded_directory_metadata_drift_is_not_hidden_by_security_snapshot(scope, monkeypatch):
    inode = scope.sources[0].parent.stat().st_ino
    original = tool.audit._metadata
    consumed = False

    def metadata(info):
        result = original(info)
        if consumed and info.st_ino == inode:
            result["ctime_ns"] += 1
        return result

    def consume():
        nonlocal consumed
        consumed = True
        return {}

    monkeypatch.setattr(tool.audit, "_metadata", metadata)
    with pytest.raises(tool.audit.Refusal, match="directory_changed_across_consumer"):
        tool._guarded_consume(scope.root, scope.expected, consume, tool.policy.snapshot)


def test_guarded_directory_security_refuses_disallowed_flags(scope, monkeypatch):
    inode = scope.sources[0].parent.stat().st_ino
    original = tool.audit._metadata

    def metadata(info):
        result = original(info)
        if info.st_ino == inode:
            result["flags"] = stat.UF_IMMUTABLE
        return result

    monkeypatch.setattr(tool.audit, "_metadata", metadata)
    with pytest.raises(tool.audit.Refusal, match="current_directory_security"):
        tool._guarded_consume(scope.root, scope.expected, lambda: pytest.fail("consumer reached"), tool.policy.snapshot)


def historical_rows(scope):
    rows = deepcopy(scope.expected)
    for path, row in rows.items():
        row["metadata"]["dev"] = tool.policy.HISTORICAL_DEVICE
        if path in tool.CTIME_PROJECTION:
            row["metadata"]["ctime_ns"] = tool.CTIME_PROJECTION[path][0]
    return rows


def test_frozen_metadata_projection_contract_is_exact_and_not_historical_acceptance():
    contract = tool.profile()["source_metadata_projection"]
    assert contract["historical_device"] == 16777232
    assert contract["prospective_device"] == 16777231
    assert contract["changed_metadata_fields"] == ["dev", "ctime_ns"]
    assert contract["source_paths"] == sorted(tool._source_keys())
    assert contract["source_count"] == 15
    assert contract["historical_device_continuity_proven"] is False
    assert contract["historical_evidence_modified"] is False
    assert contract["other_metadata_waived"] is False
    assert tool.OUTPUT == tool.ROOT / "artifacts/analyst_revisions_v2/relocation_trial/R282-20261011-A"
    assert tool.SCHEMA == "arv2-relocated-source-fresh-use-v4"


def test_projection_changes_only_accepted_metadata_and_never_mutates_or_aliases_history(scope):
    rows = historical_rows(scope)
    original = deepcopy(rows)
    projected, receipt = tool._project_sources(rows)
    assert rows == original
    assert projected == scope.expected
    assert receipt["historical_rows_sha256"] == hashlib.sha256(tool.audit._json_bytes(original)).hexdigest()
    assert receipt["prospective_rows_sha256"] == hashlib.sha256(tool.audit._json_bytes(projected)).hexdigest()
    key = sorted(rows)[0]
    projected[key]["metadata"]["gid"] += 1
    projected[key]["sha256"] = "0" * 64
    assert rows == original
    rows[key]["metadata"]["uid"] += 1
    assert projected[key]["metadata"]["uid"] == original[key]["metadata"]["uid"]


@pytest.mark.parametrize("device", [16777231, 16777233, 0, -1, True, False, 16777232.0, "16777232", None])
def test_historical_projection_refuses_any_other_or_noninteger_device(scope, device):
    rows = historical_rows(scope)
    rows[sorted(rows)[0]]["metadata"]["dev"] = device
    with pytest.raises(tool.audit.Refusal, match="historical_projection_(device|metadata)"):
        tool._project_sources(rows)
    assert scope.events == []


@pytest.mark.parametrize("change", ["missing", "extra", "absolute", "traversal", "noncanonical", "not_dict"])
def test_projection_scope_is_exact_before_any_object_observation(scope, change):
    rows = historical_rows(scope)
    key = sorted(rows)[0]
    if change == "missing":
        rows.pop(key)
    elif change == "extra":
        rows["another-source"] = deepcopy(rows[key])
    elif change in ("absolute", "traversal", "noncanonical"):
        replacement = {"absolute": "/" + key, "traversal": "../" + key,
                       "noncanonical": "./" + key}[change]
        rows[replacement] = rows.pop(key)
    else:
        rows = list(rows.items())
    with pytest.raises(tool.audit.Refusal, match="historical_projection_paths"):
        tool._project_sources(rows)
    assert scope.events == []


@pytest.mark.parametrize("change", ["missing_metadata", "extra_metadata", "float_field", "row_kind", "hash"])
def test_projection_refuses_malformed_historical_rows(scope, change):
    rows = historical_rows(scope)
    row = rows[sorted(rows)[0]]
    if change == "missing_metadata":
        row["metadata"].pop("ctime_ns")
    elif change == "extra_metadata":
        row["metadata"]["unknown"] = 1
    elif change == "float_field":
        row["metadata"]["gid"] = float(row["metadata"]["gid"])
    elif change == "row_kind":
        row["kind"] = "symlink"
    else:
        row["sha256"] = "G" * 64
    with pytest.raises(tool.audit.Refusal, match="historical_projection_(metadata|row|hash)"):
        tool._project_sources(rows)


@pytest.mark.parametrize("field", sorted(tool.METADATA_FIELDS - {"dev", "ctime_ns"}))
def test_projection_does_not_refresh_any_other_historical_metadata(scope, field):
    rows = historical_rows(scope)
    key = sorted(rows)[0]
    rows[key]["metadata"][field] += 1
    projected, _receipt = tool._project_sources(rows)
    assert projected[key]["metadata"][field] == rows[key]["metadata"][field]
    with pytest.raises(tool.audit.Refusal, match="source_preopen_identity"):
        tool._guarded_consume(scope.root, projected, lambda: pytest.fail("consumer reached"), tool.policy.snapshot)


@pytest.mark.parametrize("device", [16777232, 16777233, 0, -1, True, 16777231.0, "16777231", None])
def test_guarded_scope_rejects_nonprospective_device_before_observations(scope, device):
    rows = deepcopy(scope.expected)
    rows[sorted(rows)[0]]["metadata"]["dev"] = device
    with pytest.raises(tool.audit.Refusal, match="guarded_projection_(device|metadata)"):
        tool._guarded_consume(scope.root, rows, lambda: pytest.fail("consumer reached"), tool.policy.snapshot)
    assert scope.events == []


@pytest.mark.parametrize("kind", ["source", "directory"])
@pytest.mark.parametrize("device", [16777232, 16777233, 16777231.0, True])
def test_preflight_requires_exact_current_device_before_names_or_values(scope, monkeypatch, kind, device):
    inode = (scope.sources[0] if kind == "source" else scope.sources[0].parent).stat().st_ino
    original = tool.audit._metadata

    def metadata(info):
        result = original(info)
        if info.st_ino == inode:
            result["dev"] = device
        return result

    monkeypatch.setattr(tool.audit, "_metadata", metadata)
    with pytest.raises(tool.audit.Refusal, match="preflight_(source|directory)_device"):
        invoke("--preflight-only")
    assert scope.events == []
    assert not scope.output.exists()


@pytest.mark.parametrize("field", sorted(tool.METADATA_FIELDS))
def test_guarded_preopen_metadata_preserves_every_projected_field(scope, monkeypatch, field):
    inode = scope.sources[0].stat().st_ino
    original = tool.audit._metadata

    def metadata(info):
        result = original(info)
        if info.st_ino == inode:
            result[field] += 1
        return result

    monkeypatch.setattr(tool.audit, "_metadata", metadata)
    with pytest.raises(tool.audit.Refusal, match="source_preopen_identity"):
        tool._guarded_consume(scope.root, scope.expected, lambda: pytest.fail("consumer reached"), tool.policy.snapshot)


def test_v2_still_refuses_new_device_against_unmodified_historical_rows(scope):
    from scripts import assess_arv2_relocated_sources_v2 as old

    with pytest.raises(tool.audit.Refusal, match="source_preopen_identity"):
        old._guarded_consume(scope.root, historical_rows(scope),
                             lambda: pytest.fail("old consumer reached"), lambda _fd: {})


@pytest.mark.parametrize("kind", ["parent", "output"])
def test_output_allocation_requires_new_device_and_preserves_spent_failures(scope, monkeypatch, kind):
    original = tool.audit._metadata
    parent_inode = scope.output.parent.stat().st_ino

    def metadata(info):
        result = original(info)
        target = (info.st_ino == parent_inode if kind == "parent" else
                  scope.output.exists() and info.st_ino == scope.output.stat().st_ino)
        if target:
            result["dev"] = tool.policy.HISTORICAL_DEVICE
        return result

    monkeypatch.setattr(tool.audit, "_metadata", metadata)
    code = "assessment_parent_device" if kind == "parent" else "assessment_directory_device"
    with pytest.raises(tool.audit.Refusal, match=code):
        invoke()
    assert scope.events == []
    assert scope.output.exists() is (kind == "output")
    if kind == "output":
        assert list(scope.output.iterdir()) == []
        with pytest.raises(FileExistsError):
            invoke()


def test_success_report_binds_actual_historical_and_projected_rows(scope, monkeypatch):
    rows = historical_rows(scope)
    original_reports = tool.v1._read_pinned_reports
    seen = []

    def reports(root):
        before, after = original_reports(root)
        seen.extend((before, after, deepcopy(before), deepcopy(after)))
        return before, after

    monkeypatch.setattr(tool.v1, "_read_pinned_reports", reports)
    assert invoke() == 0
    report = json.loads((scope.output / "report.json").read_bytes())
    receipt = report["source_metadata_projection"]
    assert report["source_metadata_projection_contract"] == tool.profile()["source_metadata_projection"]
    assert receipt["historical_rows_sha256"] == hashlib.sha256(tool.audit._json_bytes(rows)).hexdigest()
    assert receipt["prospective_rows_sha256"] == hashlib.sha256(tool.audit._json_bytes(scope.expected)).hexdigest()
    assert receipt["changed_metadata_fields"] == ["dev", "ctime_ns"]
    assert receipt["historical_device_continuity_proven"] is False
    assert seen[0] == seen[2] and seen[1] == seen[3]


@pytest.mark.parametrize("failure", ["device", "source_hash", "historical_bytes", "loader_manifest"])
def test_assessment_integration_never_clears_source_or_manifest_refusal(scope, monkeypatch, failure):
    reports = tool.v1._read_pinned_reports

    def changed(root):
        before, after = reports(root)
        key = sorted(scope.expected)[0]
        if failure == "device":
            for report in (before, after):
                report["census"]["entries"][key]["metadata"]["dev"] = tool.policy.PROSPECTIVE_DEVICE
        elif failure == "source_hash":
            for report in (before, after):
                report["census"]["entries"][key]["sha256"] = "0" * 64
        elif failure == "historical_bytes":
            after["census"]["entries"][key]["sha256"] = "0" * 64
        return before, after

    def refused_loader():
        raise tool.audit.Refusal("synthetic_manifest_digest_refused")

    monkeypatch.setattr(tool.v1, "_read_pinned_reports", changed)
    if failure == "loader_manifest":
        monkeypatch.setattr(tool.v1, "_load_sources", refused_loader)
    assert invoke() == 1
    raw = (scope.output / "report.json").read_bytes()
    report = json.loads(raw)
    assert report["complete"] is report["source_reauthenticated"] is False
    assert "loader_results" not in report
    assert report["refusal_code"] == {
        "device": "historical_projection_device", "source_hash": "current_source_hash",
        "historical_bytes": "historical_source_bytes", "loader_manifest": "synthetic_manifest_digest_refused"}[failure]
    with pytest.raises(FileExistsError):
        invoke()
    assert (scope.output / "report.json").read_bytes() == raw


def test_production_ctime_contract_has_only_twelve_immutable_exact_pairs():
    pairs = tool._validated_ctime_projection()
    assert type(pairs) is MappingProxyType
    assert len(pairs) == 12
    assert hashlib.sha256(tool.audit._json_bytes(dict(pairs))).hexdigest() == (
        "4291685e8a45ab5b4a04a9d33022be0aeffffaa2a32ad1d94bad9326ecb52d5b")
    with pytest.raises(TypeError):
        pairs[sorted(pairs)[0]] = (1, 2)
    contract = tool.profile()["source_metadata_projection"]
    assert contract["ctime_reference_report_sha256"] == (
        "1631babf154ed52a3f2df338f6c4fd4b37cb1071f732ff7fdfce7613b7b0dc3c")
    assert contract["baseline_values_record"] == "280.5"
    assert contract["owner_authority_record"] == "282"
    contract["ctime_pairs"].clear()
    assert len(tool.profile()["source_metadata_projection"]["ctime_pairs"]) == 12


@pytest.mark.parametrize("change", ["mutable", "missing", "extra", "vintage", "absolute", "traversal"])
def test_ctime_map_refuses_wrong_paths_or_mutability_before_observation(scope, monkeypatch, change):
    pairs = dict(tool.CTIME_PROJECTION)
    key = sorted(pairs)[0]
    if change == "missing":
        pairs.pop(key)
    elif change == "extra":
        pairs["another-source"] = (1, 2)
    elif change in ("vintage", "absolute", "traversal"):
        replacement = {"vintage": tool.v1.VINTAGE + "/manifest.json",
                       "absolute": "/" + key, "traversal": "../" + key}[change]
        pairs[replacement] = pairs.pop(key)
    monkeypatch.setattr(tool, "CTIME_PROJECTION", pairs if change == "mutable" else MappingProxyType(pairs))
    with pytest.raises(tool.audit.Refusal, match="ctime_projection_paths"):
        tool._project_sources(historical_rows(scope))
    assert scope.events == []


@pytest.mark.parametrize("pair", [(True, 2), (1, False), (1.0, 2), (1, 2.0), ("1", 2),
                                 (1, "2"), (0, 2), (-1, 2), (2, 2), (3, 2), (1,),
                                 (1, 2, 3), [1, 2], None])
def test_ctime_map_refuses_malformed_or_noninteger_pairs(scope, monkeypatch, pair):
    pairs = dict(tool.CTIME_PROJECTION)
    pairs[sorted(pairs)[0]] = pair
    monkeypatch.setattr(tool, "CTIME_PROJECTION", MappingProxyType(pairs))
    with pytest.raises(tool.audit.Refusal, match="ctime_projection_values"):
        tool._validated_ctime_projection()
    assert scope.events == []


@pytest.mark.parametrize("side", [0, 1])
def test_ctime_map_cannot_silently_refresh_one_positive_value(scope, monkeypatch, side):
    pairs = dict(tool.CTIME_PROJECTION)
    key = sorted(pairs)[0]
    values = list(pairs[key])
    values[side] += -1 if side == 0 else 1
    pairs[key] = tuple(values)
    monkeypatch.setattr(tool, "CTIME_PROJECTION", MappingProxyType(pairs))
    with pytest.raises(tool.audit.Refusal, match="ctime_projection_pin"):
        tool._validated_ctime_projection()


@pytest.mark.parametrize("path", sorted(tool.CTIME_PROJECTION))
def test_each_historical_ctime_must_equal_accepted_old_endpoint(scope, path):
    rows = historical_rows(scope)
    rows[path]["metadata"]["ctime_ns"] -= 1
    with pytest.raises(tool.audit.Refusal, match="historical_projection_ctime"):
        tool._project_sources(rows)
    assert scope.events == []


@pytest.mark.parametrize("path", sorted(tool.CTIME_PROJECTION))
def test_each_prospective_ctime_must_equal_accepted_new_endpoint(scope, path):
    rows = deepcopy(scope.expected)
    rows[path]["metadata"]["ctime_ns"] += 1
    with pytest.raises(tool.audit.Refusal, match="guarded_projection_ctime"):
        tool._guarded_consume(scope.root, rows, lambda: pytest.fail("consumer reached"),
                              lambda _fd: pytest.fail("snapshot reached"))
    assert scope.events == []


@pytest.mark.parametrize("value", [True, False, 1.0, "1", None])
@pytest.mark.parametrize("prospective", [False, True])
def test_ctime_fields_refuse_nonintegers_before_projection_or_observation(scope, value, prospective):
    rows = deepcopy(scope.expected) if prospective else historical_rows(scope)
    rows[sorted(tool.CTIME_PROJECTION)[0]]["metadata"]["ctime_ns"] = value
    with pytest.raises(tool.audit.Refusal, match="(guarded|historical)_projection_metadata"):
        if prospective:
            tool._guarded_consume(scope.root, rows, lambda: {}, lambda _fd: {})
        else:
            tool._project_sources(rows)
    assert scope.events == []


@pytest.mark.parametrize("path", [tool.v1.VINTAGE + "/" + leaf
                                 for leaf in tool.v1.PACKAGES[tool.v1.VINTAGE]])
def test_vintage_ctime_is_never_projected_or_refreshed(scope, path):
    rows = historical_rows(scope)
    rows[path]["metadata"]["ctime_ns"] += 1
    projected, _receipt = tool._project_sources(rows)
    assert projected[path]["metadata"]["ctime_ns"] == rows[path]["metadata"]["ctime_ns"]
    with pytest.raises(tool.audit.Refusal, match="source_preopen_identity"):
        tool._guarded_consume(scope.root, projected, lambda: pytest.fail("consumer reached"), lambda _fd: {})


def test_historical_digest_guard_isolates_mutation_even_when_copy_agrees(scope, monkeypatch):
    rows = historical_rows(scope)
    key = sorted(rows)[0]

    def mutating_copy(value):
        copied = deepcopy(value)
        value[key]["contains_old_root_literal"] = True
        copied[key]["contains_old_root_literal"] = True
        return copied

    monkeypatch.setattr(tool, "deepcopy", mutating_copy)
    with pytest.raises(tool.audit.Refusal, match="historical_projection_input_changed"):
        tool._project_sources(rows)
    assert scope.events == []


@pytest.mark.parametrize("field", ["gid", "mtime_ns", "sha256", "contains_old_root_literal"])
def test_projection_rejects_copy_changes_outside_exact_allowlist(scope, monkeypatch, field):
    rows = historical_rows(scope)
    original = deepcopy(rows)
    key = sorted(rows)[0]

    def changed_copy(value):
        copied = deepcopy(value)
        if field in tool.METADATA_FIELDS:
            copied[key]["metadata"][field] += 1
        else:
            copied[key][field] = "0" * 64 if field == "sha256" else True
        return copied

    monkeypatch.setattr(tool, "deepcopy", changed_copy)
    with pytest.raises(tool.audit.Refusal, match="projection_unauthorized_change"):
        tool._project_sources(rows)
    assert rows == original


def test_postcopy_prospective_ctime_check_is_not_shadowed_by_delta_check(scope, monkeypatch):
    original = tool._validate_source_scope
    key = sorted(tool.CTIME_PROJECTION)[0]

    def validate(rows, device, code):
        original(rows, device, code)
        if code == "prospective_projection":
            rows[key]["metadata"]["ctime_ns"] += 1

    monkeypatch.setattr(tool, "_validate_source_scope", validate)
    with pytest.raises(tool.audit.Refusal, match="prospective_projection_ctime"):
        tool._project_sources(historical_rows(scope))


@pytest.mark.parametrize("device", [16777232, 16777233, True, 16777231.0])
def test_consumer_directory_device_guard_precedes_permissive_security(scope, monkeypatch, device):
    inode = scope.root.parent.stat().st_ino
    original = tool.audit._metadata
    observed = []

    def metadata(info):
        result = original(info)
        if info.st_ino == inode:
            result["dev"] = device
        return result

    def permissive_snapshot(fd):
        observed.append(fd)
        return {}

    monkeypatch.setattr(tool.audit, "_metadata", metadata)
    with pytest.raises(tool.audit.Refusal, match="current_directory_device"):
        tool._guarded_consume(scope.root, scope.expected, lambda: {}, permissive_snapshot)
    assert observed == []


def test_preflight_directory_security_guard_precedes_names(scope, monkeypatch):
    monkeypatch.setattr(tool, "_directory_secure", lambda *_args: False)
    with pytest.raises(tool.audit.Refusal, match="preflight_directory_security"):
        invoke("--preflight-only")
    assert scope.events == []


def test_preflight_initial_named_directory_guard_isolated(scope, monkeypatch):
    original = tool._named_metadata
    calls = 0

    def metadata(path, directories):
        nonlocal calls
        result = original(path, directories)
        calls += 1
        if calls == 1:
            result["ino"] += 1
        return result

    monkeypatch.setattr(tool, "_named_metadata", metadata)
    with pytest.raises(tool.audit.Refusal, match="preflight_named_directory"):
        invoke("--preflight-only")
    assert calls == 1 and scope.events == []


def test_preflight_leaf_open_identity_guard_isolated(scope, monkeypatch):
    original = os.fstat
    inode = sorted(scope.sources)[0].stat().st_ino
    calls = 0

    def held(fd):
        nonlocal calls
        info = original(fd)
        if info.st_ino == inode:
            calls += 1
            if calls == 1:
                fields = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
                fields["st_ino"] += 1
                return SimpleNamespace(**fields)
        return info

    monkeypatch.setattr(tool.os, "fstat", held)
    with pytest.raises(tool.audit.Refusal, match="preflight_open_identity"):
        invoke("--preflight-only")
    assert calls == 1 and scope.events == []


def test_preflight_after_names_metadata_guard_isolated(scope, monkeypatch):
    inode = scope.root.parent.stat().st_ino
    original_names, original_meta = tool.policy._names, tool.audit._metadata
    calls = 0
    changed = False

    def names(native, fd):
        nonlocal calls, changed
        result = original_names(native, fd)
        calls += 1
        if calls == 28:
            changed = True
        return result

    def metadata(info):
        result = original_meta(info)
        if changed and info.st_ino == inode:
            result["ctime_ns"] += 1
        return result

    monkeypatch.setattr(tool.policy, "_names", names)
    monkeypatch.setattr(tool.audit, "_metadata", metadata)
    with pytest.raises(tool.audit.Refusal, match="preflight_metadata_changed_after_names"):
        invoke("--preflight-only")
    assert calls == 28


def test_consumer_final_security_metadata_guard_isolated(scope, monkeypatch):
    inode = scope.sources[0].parent.stat().st_ino
    original = tool.audit._metadata
    consumed = changed = False

    def metadata(info):
        result = original(info)
        if changed and info.st_ino == inode:
            result["ctime_ns"] += 1
        return result

    def snapshot(fd):
        nonlocal changed
        if consumed and os.fstat(fd).st_ino == inode:
            changed = True
        return {}

    def consume():
        nonlocal consumed
        consumed = True
        return {}

    monkeypatch.setattr(tool.audit, "_metadata", metadata)
    with pytest.raises(tool.audit.Refusal, match="directory_changed_during_final_security"):
        tool._guarded_consume(scope.root, scope.expected, consume, snapshot)


def test_assessment_report_size_guard_precedes_publication(scope, monkeypatch, capsys):
    monkeypatch.setattr(tool, "MAX_REPORT_BYTES", 1)
    monkeypatch.setattr(tool.audit, "_publish_report", lambda *_args: pytest.fail("publication reached"))
    with pytest.raises(tool.audit.Refusal, match="assessment_report_size"):
        invoke()
    assert scope.output.is_dir() and list(scope.output.iterdir()) == []
    assert capsys.readouterr().out == ""


def test_preflight_profile_recheck_rejects_late_profile_change(scope, monkeypatch, capsys):
    original = tool.preflight_scope

    def preflight():
        result = original()
        result["profile_sha256"] = "0" * 64
        return result

    monkeypatch.setattr(tool, "preflight_scope", preflight)
    with pytest.raises(tool.audit.Refusal, match="profile_changed_during_preflight"):
        invoke("--preflight-only")
    assert not scope.output.exists() and capsys.readouterr().out == ""


def test_assessment_profile_recheck_publishes_refusal_not_success(scope, monkeypatch, capsys):
    original = tool.v1._load_sources

    def consume():
        result = original()
        monkeypatch.setattr(tool, "profile_sha256", lambda: "0" * 64)
        return result

    monkeypatch.setattr(tool.v1, "_load_sources", consume)
    assert invoke() == 1
    report = json.loads((scope.output / "report.json").read_bytes())
    assert report["refusal_code"] == "profile_changed_across_assessment"
    assert report["complete"] is report["source_reauthenticated"] is False
    assert "complete=false" in capsys.readouterr().out


@pytest.mark.parametrize("elapsed,remaining", [(2.0, 3.0), (5.0, None), (6.0, None)])
def test_nested_budget_restores_only_unexpired_outer_alarm(monkeypatch, elapsed, remaining):
    clock = iter([0.0, elapsed, elapsed])
    timers, handlers = [], []
    sentinel = object()
    monkeypatch.setattr(tool.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(tool.signal, "getitimer", lambda _kind: (5.0, 0))
    monkeypatch.setattr(tool.signal, "getsignal", lambda _kind: sentinel)
    monkeypatch.setattr(tool.signal, "signal", lambda _kind, handler: handlers.append(handler))
    monkeypatch.setattr(tool.signal, "setitimer", lambda _kind, delay: timers.append(delay))
    if elapsed > 5:
        with pytest.raises(tool.audit.Refusal, match="cooperative_budget_exceeded"):
            with tool._budget(15):
                pass
    else:
        with tool._budget(15):
            pass
    assert timers == [5.0, 0] + ([] if remaining is None else [remaining])
    assert handlers[-1] is sentinel
