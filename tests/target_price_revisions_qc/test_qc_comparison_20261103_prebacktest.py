"""Synthetic pinned-file capsule checks; no USB, registry or native reads."""
from datetime import date, timedelta
import json
import os
from pathlib import Path
import stat

import pytest

from research.target_price_revisions_qc import comparison_20261103_prebacktest as p

HEAD = "a" * 40
OP = "TPR-PREBACKTEST-20261103-SYNTHETIC-001"


def _days(start, count):
    return [(start + timedelta(days=i)).isoformat() for i in range(count)]


def _synthetic_remx():
    targets = [day for day in _days(date(2026, 2, 23), 26)
        if date.fromisoformat(day).weekday() < 5]
    assert len(targets) == 20
    study_all = [day for day in _days(date(2021, 1, 4), 2105)
        if day <= "2026-10-09" and date.fromisoformat(day).weekday() < 5]
    study = sorted([day for day in study_all if day not in targets][:1429] + targets)
    assert len(study) == 1449
    identity = _days(date(2005, 1, 4), 323)
    post = _days(date(2010, 10, 27), 2567) + study
    normalized = set(post[:860])
    def line(day, volume):
        return (day + " 00:00:00,12345.6789,12346,12345,12345.6789," + volume + "\n").encode()
    original = b"".join(line(day, "100") for day in identity) + b"".join(
        line(day, "100.25" if day in targets else ("100.0" if day in normalized else "100"))
        for day in post)
    blobs = {"source_original.csv": original,
        "candidate_post_inception.csv": b"".join(line(day, "100") for day in post if day not in targets),
        "quarantine_pre_inception.csv": b"".join(line(day, "100") for day in identity),
        "quarantine_fractional_volume.csv": b"".join(line(day, "100.25") for day in targets)}
    manifest = {key: False for key in p.FALSE_REMX_FLAGS}
    manifest.update({"source_rows": 4339, "candidate_rows": 3996,
        "source_sha256": p._sha(original), "identity_boundary": "2010-10-27",
        "disposition_counts": {"post_inception_unchanged": 3136,
            "post_inception_integral_volume_normalized": 860,
            "pre_inception_identity_quarantine": 323, "fractional_volume_quarantine": 20},
        "full_source_preserved": True, "all_rows_accounted_for": True,
        "candidate_strict_parser_valid": True, "missing_post_inception_source_dates": targets,
        "outputs": {name: {"bytes": len(raw), "sha256": p._sha(raw)} for name, raw in blobs.items()}})
    blobs["manifest.json"] = p._wire(manifest)
    receipt = {"status": "prepared_partial_local_candidate", "git_head": p.REMX_CREATION_HEAD,
        "owner_instruction_sha256": p.REMX_CREATION_OWNER, "source_original_modified": False,
        "outputs": {name: {"name": name, "bytes": len(raw), "sha256": p._sha(raw)} for name, raw in blobs.items()}}
    blobs["receipt.json"] = p._wire(receipt)
    return blobs


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "lane"
    root.mkdir(mode=0o700)
    monkeypatch.chdir(root)
    monkeypatch.setattr(p, "ROOT", root)
    monkeypatch.setattr(p.io, "ROOT", root)
    monkeypatch.setattr(p, "HELPER_PINS", {})
    source_blobs = {}
    for name in p.REQUIRED_SOURCES:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = b"# public source fixture\n"
        path.write_bytes(raw)
        source_blobs[name] = raw
    record = root / p.RECORD
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_bytes(b"Synthetic retained history with no outcomes\n")
    def git(*args):
        if args == ("rev-parse", "--show-toplevel"):
            return str(root).encode()
        if args == ("branch", "--show-current"):
            return p.BRANCH.encode()
        if args == ("rev-parse", "HEAD"):
            return HEAD.encode()
        if args in (("diff", "--name-only", "-z"), ("diff", "--cached", "--name-only", "-z")):
            return b""
        if args[0] == "show":
            return source_blobs[args[1].split(":", 1)[1]]
        raise AssertionError("unexpected git operation")
    monkeypatch.setattr(p.io, "_git", git)
    blobs = _synthetic_remx()
    monkeypatch.setattr(p, "REMX_INPUTS",
        {name: (len(raw), p._sha(raw)) for name, raw in blobs.items()})
    registry_raw = b"synthetic registry only\n"
    monkeypatch.setattr(p.preflight, "REGISTRY_BYTES", len(registry_raw))
    monkeypatch.setattr(p.preflight, "REGISTRY_SHA256", p._sha(registry_raw))
    private = {p.REGISTRY: registry_raw, **{p.REMX_ROOT + "/" + name: raw for name, raw in blobs.items()}}
    for name, raw in private.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        target.chmod(0o600)
        for parent in target.parents:
            if parent == root:
                break
            if parent.is_relative_to(root / "artifacts"):
                parent.chmod(0o700)
    packets = {arm: {("unit" + str(i) + ".py"): b"pass\n"
        for i in range(p.EXPECTED_ARM_FILES[arm])} for arm in p.preflight.ARMS}
    calls = []
    def builder(epoch):
        def build(**kwargs):
            calls.append((epoch, kwargs))
            assert kwargs["owner_instruction_sha256"] == p.OWNER_SHA256
            assert kwargs["git_head"] == HEAD
            assert kwargs["project_bindings_raw"] == registry_raw
            for row in kwargs["requests"].values():
                assert "OFFLINE" in row["operation_id"] and row["attempt"] == 1
            manifest = {"source_epoch": epoch, "mode": "offline-preparation",
                "owner_instruction_sha256": p.OWNER_SHA256,
                "source_inputs_admitted": False, "backtesting_ready": False,
                "native_origin_authenticated": False, "accepted_performance": None,
                "local_syntax_units_checked": 71, "registry_creation_owner_instruction_sha256": "b" * 64,
                "registry_creation_git_head": "c" * 40,
                **{key: 0 for key in ("qc_requests", "qc_compiles", "backtests_launched",
                    "new_attempts", "new_observed_financial_looks")},
                "arms": {arm: {"project_id": p.preflight.REGISTERED_PROJECTS[p.preflight.bundle.ARM_KEYS[arm]],
                    "native_compilation": "NOT_RUN", "backtest": "NOT_RUN", "financial_metrics": None,
                    "native_accounting_accepted": False, "financial_function_bodies_unchanged": True,
                    "source_inventory": {name: {"bytes": len(raw), "sha256": p._sha(raw)}
                        for name, raw in files.items()}} for arm, files in packets.items()}}
            return packets, p._wire(manifest)
        return build
    monkeypatch.setattr(p.preflight, "prepare_offline", builder(p.preflight.FROZEN_EPOCH))
    monkeypatch.setattr(p.preflight, "prepare_recovery_candidate", builder(p.preflight.RECOVERY_EPOCH))
    def deny(*args, **kwargs):
        pytest.fail("native/provider/USB effect reached")
    monkeypatch.setattr(p.io, "_usb_stream", deny)
    monkeypatch.setattr(p.preflight.bundle.projects.ops, "credential", deny)
    monkeypatch.setattr(p.preflight.bundle.projects.ops, "read_private", deny)
    monkeypatch.setattr(p.preflight.bundle.projects.http.client, "HTTPSConnection", deny)
    return root, private, calls


def test_claim_precedes_all_seven_reads_and_exports_remain_local(workspace, monkeypatch):
    root, originals, calls = workspace
    reader = p._private_read
    seen = []
    def read(path, pin):
        claim = json.loads((root / p.DESTINATION / OP / "claim.json").read_bytes())
        assert claim["git_head"] == HEAD
        assert claim["latest_owner_instruction_sha256"] == p.OWNER_SHA256
        assert claim["private_reads_max"] == 7
        assert claim["private_bytes_max"] == sum(len(raw) for raw in originals.values())
        assert claim["reserved_attempt"] is None and claim["financial_outcome_look"] is None
        assert claim["signal_packet_open_authorized"] is False
        assert OP in (root / p.RECORD).read_text()
        assert claim["qc_requests"] == claim["safari_requests"] == claim["backtests"] == 0
        seen.append(path)
        return reader(path, pin)
    monkeypatch.setattr(p, "_private_read", read)
    result = p.prepare_workspace(OP)
    operation = root / p.DESTINATION / OP
    readiness = json.loads((operation / "readiness.json").read_bytes())
    receipt = json.loads((operation / "receipt.json").read_bytes())
    assert set(seen) == set(originals) and len(seen) == 7
    assert result["status"] == "prepared_prebacktest_local"
    assert result["local_preparation_complete"] is True and result["backtesting_ready"] is False
    assert readiness["local_syntax_units_checked"] == 142
    assert len(calls) == 2
    assert readiness["remx"]["fractional_volume_quarantine_rows"] == 20
    assert readiness["remx"]["diagnostic_gap_blocks_frozen_source_assembly"] is False
    assert readiness["remx"]["raw_rows_copied_into_source_exports"] is False
    assert readiness["remx"]["historical_creation_owner_sha256"] == p.REMX_CREATION_OWNER
    assert readiness["latest_owner_instruction_sha256"] != p.REMX_CREATION_OWNER
    assert receipt["quarantine_hashes_verified"] is True
    for key in ("backtesting_ready", "source_inputs_admitted", "native_origin_authenticated",
                "financial_acceptance", "point_in_time_data", "source_rights_admitted",
                "canonical_admission", "trading_authority"):
        assert readiness[key] is False
    assert readiness["next_step"] == "STOP_BEFORE_QC_SAFARI_NATIVE_COMPILE_OR_BACKTEST"
    for arm in readiness["arms"].values():
        assert arm["native_upload"] == arm["native_compilation"] == arm["backtest"] == "NOT_RUN"
        assert arm["financial_metrics"] is None
    for name, raw in originals.items():
        assert (root / name).read_bytes() == raw
    source_paths = list(operation.glob("*/*/*.py"))
    assert len(source_paths) == 142
    assert all(b",12345.6789," not in path.read_bytes() for path in source_paths)
    assert b",12345.6789," not in (operation / "readiness.json").read_bytes()
    for path in operation.rglob("*"):
        if path.is_file():
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
        else:
            assert stat.S_IMODE(path.stat().st_mode) == 0o700


def test_replay_is_refused_before_any_second_private_read(workspace, monkeypatch):
    root, _, _ = workspace
    assert p.prepare_workspace(OP)["local_preparation_complete"]
    monkeypatch.setattr(p, "_private_read", lambda *args: pytest.fail("spent operation reused"))
    with pytest.raises(FileExistsError):
        p.prepare_workspace(OP)


@pytest.mark.parametrize("operation", ["", "../escape", "TPR-PREBACKTEST-20261103-", "bad", 1])
def test_operation_refuses_before_any_context_or_io(operation, monkeypatch):
    monkeypatch.setattr(p, "_context", lambda: pytest.fail("context reached"))
    with pytest.raises(p.PreparationRefusal):
        p.prepare_workspace(operation)


def test_uncommitted_source_and_empty_history_refuse_before_claim(workspace, monkeypatch):
    root, _, _ = workspace
    original = (root / p.MODULE).read_bytes()
    (root / p.MODULE).write_bytes(b"changed public source\n")
    monkeypatch.setattr(p, "_private_read", lambda *args: pytest.fail("private read"))
    with pytest.raises(p.PreparationRefusal):
        p.prepare_workspace(OP)
    assert not (root / p.DESTINATION).exists()
    (root / p.MODULE).write_bytes(original)
    (root / p.RECORD).write_bytes(b"")
    with pytest.raises(p.PreparationRefusal):
        p.prepare_workspace(OP)
    assert not (root / p.DESTINATION).exists()


def test_pinned_helper_refuses_before_any_private_claim(workspace, monkeypatch):
    root, _, _ = workspace
    monkeypatch.setattr(p, "HELPER_PINS", {p.preflight.MODULE: "0" * 64})
    with pytest.raises(p.PreparationRefusal):
        p.prepare_workspace(OP)
    assert not (root / p.DESTINATION).exists()


def test_head_or_source_change_after_claim_refuses_before_private_read(workspace, monkeypatch):
    root, _, _ = workspace
    note = p.io._note
    def change(message):
        note(message)
        if message.startswith("Fresh local prebacktest"):
            (root / p.MODULE).write_bytes(b"changed after claim\n")
    monkeypatch.setattr(p.io, "_note", change)
    monkeypatch.setattr(p, "_private_read", lambda *args: pytest.fail("private read"))
    result = p.prepare_workspace(OP)
    receipt = json.loads((root / p.DESTINATION / OP / "receipt.json").read_bytes())
    assert result["status"] == "refused"
    assert receipt["quarantine_hashes_verified"] is False
    assert receipt["local_preparation_complete"] is False


@pytest.mark.parametrize("damage", ["hash", "leaf_symlink", "ancestor_symlink", "fifo", "permissions"])
def test_invalid_private_input_retains_body_free_refusal(workspace, damage):
    root, _, _ = workspace
    path = root / p.REMX_ROOT / "quarantine_fractional_volume.csv"
    if damage == "hash":
        path.write_bytes(b"x" * p.REMX_INPUTS[path.name][0])
    elif damage == "leaf_symlink":
        actual = path.with_name("unread-target")
        path.rename(actual)
        path.symlink_to(actual)
    elif damage == "ancestor_symlink":
        parent = path.parent
        actual = parent.with_name("private-original")
        parent.rename(actual)
        parent.symlink_to(actual, target_is_directory=True)
    elif damage == "fifo":
        path.unlink()
        os.mkfifo(path, 0o600)
    else:
        path.chmod(0o644)
    result = p.prepare_workspace(OP)
    receipt = json.loads((root / p.DESTINATION / OP / "receipt.json").read_bytes())
    assert result["status"] == "refused" and receipt["readiness"] is None
    assert receipt["source_inputs_admitted"] is False and receipt["financial_acceptance"] is False
    assert receipt["quarantine_hashes_verified"] is False


def test_deadline_after_one_read_refuses_remaining_reads_and_processing(workspace, monkeypatch):
    root, _, calls = workspace
    clock = [10]
    monkeypatch.setattr(p.time, "monotonic", lambda: clock[0])
    reader = p._private_read
    count = []
    def read(*args):
        count.append(1)
        raw = reader(*args)
        clock[0] += p.MAX_LIFETIME_SECONDS
        return raw
    monkeypatch.setattr(p, "_private_read", read)
    result = p.prepare_workspace(OP)
    assert result["status"] == "refused" and len(count) == 1 and calls == []
    assert not (root / p.DESTINATION / OP / "readiness.json").exists()


@pytest.mark.parametrize("promotion", ["financial_acceptance", "source_inputs_admitted",
    "permanent_sid_bound", "full_coverage_verified", "fractional_volumes_rounded_or_truncated"])
def test_coherently_rehashed_remx_metadata_cannot_admit_or_round(workspace, monkeypatch, promotion):
    root, _, calls = workspace
    path = root / p.REMX_ROOT / "manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest[promotion] = True
    raw = p._wire(manifest)
    path.write_bytes(raw)
    pins = dict(p.REMX_INPUTS)
    pins[path.name] = (len(raw), p._sha(raw))
    monkeypatch.setattr(p, "REMX_INPUTS", pins)
    result = p.prepare_workspace(OP)
    assert result["status"] == "refused" and calls == []


def test_partial_export_failure_preserves_sources_and_refusal(workspace, monkeypatch):
    root, originals, _ = workspace
    original_retain = p.io._retain
    def fail(path, raw):
        if path.name == "unit2.py":
            raise OSError("SENSITIVE_SENTINEL")
        return original_retain(path, raw)
    monkeypatch.setattr(p.io, "_retain", fail)
    result = p.prepare_workspace(OP)
    receipt = json.loads((root / p.DESTINATION / OP / "receipt.json").read_bytes())
    assert result["status"] == "refused"
    assert receipt["exports"] and receipt["readiness"] is None
    assert receipt["local_preparation_complete"] is False
    assert "SENSITIVE_SENTINEL" not in (root / p.DESTINATION / OP / "receipt.json").read_text()
    assert all((root / name).read_bytes() == raw for name, raw in originals.items())


def test_export_budget_refuses_without_overwriting_existing_source(workspace, monkeypatch):
    root, originals, _ = workspace
    monkeypatch.setattr(p, "MAX_OUTPUT_BYTES", 1)
    result = p.prepare_workspace(OP)
    receipt = json.loads((root / p.DESTINATION / OP / "receipt.json").read_bytes())
    assert result["status"] == "refused" and receipt["export_bytes"] == 0
    assert all((root / name).read_bytes() == raw for name, raw in originals.items())


def test_cli_and_argument_errors_never_echo_sensitive_values(capsys, monkeypatch):
    def fail(*args):
        raise RuntimeError("SENSITIVE_SENTINEL")
    monkeypatch.setattr(p, "prepare_workspace", fail)
    assert p.main(["TPR-PREBACKTEST-20261103-SYNTHETIC-ERROR"]) == 1
    assert "SENSITIVE_SENTINEL" not in capsys.readouterr().out
    assert p.main(["--SENSITIVE_SENTINEL"]) == 1
    output = capsys.readouterr()
    assert "SENSITIVE_SENTINEL" not in output.out + output.err


def test_nonflat_generated_source_is_refused_before_source_file_write(workspace, monkeypatch):
    root, _, _ = workspace
    builder = p.preflight.prepare_offline
    def bad(**kwargs):
        packets, raw = builder(**kwargs)
        first = next(iter(packets))
        files = dict(packets[first])
        files["../escape.py"] = files.pop(next(iter(files)))
        return {**packets, first: files}, raw
    monkeypatch.setattr(p.preflight, "prepare_offline", bad)
    result = p.prepare_workspace(OP)
    assert result["status"] == "refused"
    assert not (root / "escape.py").exists()
    assert not (root / p.DESTINATION / OP / "frozen").exists()


def test_native_performance_or_inventory_promotion_is_refused(workspace, monkeypatch):
    root, _, _ = workspace
    builder = p.preflight.prepare_offline
    def bad(**kwargs):
        packets, raw = builder(**kwargs)
        manifest = json.loads(raw)
        manifest["arms"]["cap_off"]["financial_metrics"] = {"fake_return": "1"}
        return packets, p._wire(manifest)
    monkeypatch.setattr(p.preflight, "prepare_offline", bad)
    result = p.prepare_workspace(OP)
    assert result["status"] == "refused"
    assert not (root / p.DESTINATION / OP / "frozen").exists()


def test_output_parent_symlink_refuses_without_escape(workspace):
    root, _, _ = workspace
    parent = root / p.DESTINATION
    outside = root / "outside"
    outside.mkdir()
    parent.symlink_to(outside, target_is_directory=True)
    with pytest.raises(OSError):
        p.prepare_workspace(OP)
    assert list(outside.iterdir()) == []


def test_duplicate_json_keys_are_refused_before_interpretation():
    with pytest.raises(p.PreparationRefusal):
        p._parse(b'{"financial_acceptance":false,"financial_acceptance":true}')


@pytest.mark.parametrize("dependency", sorted(p.preflight.bundle.projects.REQUIRED_SOURCES -
    p.preflight.RECOVERY_REQUIRED_SOURCES - p.io.REQUIRED_SOURCES))
def test_changed_transitive_validator_dependency_refuses_before_private_claim(workspace, monkeypatch, dependency):
    root, _, _ = workspace
    assert dependency in p.REQUIRED_SOURCES
    (root / dependency).write_bytes(b"# changed transitive public dependency\n")
    monkeypatch.setattr(p, "_private_read", lambda *args: pytest.fail("private read"))
    with pytest.raises(p.PreparationRefusal):
        p.prepare_workspace(OP)
    assert not (root / p.DESTINATION).exists()



def test_private_custody_is_not_dropped_between_stat_and_read(workspace, monkeypatch):
    root, originals, calls = workspace
    original_stat, original_close = p.io.os.stat, p.io.os.close
    approved_parent = [None]
    changed = [False]
    def observed_stat(path, *args, **kwargs):
        result = original_stat(path, *args, **kwargs)
        if path == "manifest.json" and kwargs.get("dir_fd") is not None and approved_parent[0] is None:
            approved_parent[0] = kwargs["dir_fd"]
        return result
    def close_after_permission_change(fd):
        if fd == approved_parent[0] and not changed[0]:
            p.io.os.chmod("manifest.json", 0o644, dir_fd=fd, follow_symlinks=False)
            changed[0] = True
        return original_close(fd)
    monkeypatch.setattr(p.io.os, "stat", observed_stat)
    monkeypatch.setattr(p.io.os, "close", close_after_permission_change)
    result = p.prepare_workspace(OP)
    assert changed[0]
    assert result["status"] == "refused"
    receipt = json.loads((root / p.DESTINATION / OP / "receipt.json").read_bytes())
    assert receipt["quarantine_hashes_verified"] is False and calls == []
    assert receipt["readiness"] is None
    assert (root / p.REMX_ROOT / "manifest.json").read_bytes() == originals[p.REMX_ROOT + "/manifest.json"]


@pytest.mark.parametrize("change", ["chmod", "replacement"])
def test_private_leaf_swap_or_mode_change_at_open_refuses(workspace, monkeypatch, change):
    root, originals, calls = workspace
    actual_open = p.io.os.open
    changed = [False]
    target = root / p.REMX_ROOT / "manifest.json"
    def open_after_leaf_change(path, *args, **kwargs):
        if path == "manifest.json" and kwargs.get("dir_fd") is not None and not changed[0]:
            if change == "chmod":
                target.chmod(0o644)
            else:
                replacement = target.with_name("same-content-replacement")
                replacement.write_bytes(target.read_bytes())
                replacement.chmod(0o600)
                os.replace(replacement, target)
            changed[0] = True
        return actual_open(path, *args, **kwargs)
    monkeypatch.setattr(p.io.os, "open", open_after_leaf_change)
    result = p.prepare_workspace(OP)
    assert changed[0] and result["status"] == "refused" and calls == []
    receipt = json.loads((root / p.DESTINATION / OP / "receipt.json").read_bytes())
    assert receipt["quarantine_hashes_verified"] is False
    assert target.read_bytes() == originals[p.REMX_ROOT + "/manifest.json"]

def test_private_reads_stay_within_exact_claimed_byte_budget(workspace, monkeypatch):
    root, originals, _ = workspace
    real_read = p.io.os.read
    requested = []
    def bounded(fd, maximum):
        # The claim authorizes the exact pinned bytes. Before/after fstat
        # detects growth without opening an additional unclaimed guard byte.
        assert maximum <= p.io.os.fstat(fd).st_size
        requested.append(maximum)
        return real_read(fd, maximum)
    monkeypatch.setattr(p.io.os, "read", bounded)
    result = p.prepare_workspace(OP)
    assert result["status"] == "prepared_prebacktest_local"
    assert len(requested) == 7
    assert sum(requested) == sum(len(raw) for raw in originals.values())
