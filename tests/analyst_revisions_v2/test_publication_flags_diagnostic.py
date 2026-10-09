"""Synthetic temp-path tests only; no actual fixed R266 diagnostic invocation."""
import copy
import fcntl
import json
import os
import shutil
import stat
from types import SimpleNamespace

import pytest

from scripts import diagnose_arv2_publication_flags as subject


class Clock:
    def __init__(self):
        self.value = 0.0
        self.sleeps = []

    def __call__(self):
        return self.value

    def sleep(self, delay):
        self.sleeps.append(delay)
        self.value += delay


def run(tmp_path, *, clock=None):
    clock = clock or Clock()
    path = tmp_path / "private" / "synthetic-test-flags"
    report, digest = subject._diagnose_publication_flags_for_test(path, clock, clock.sleep)
    return path, report, digest, clock


def test_initial_inherited_group_different_from_process_is_pinned(tmp_path, monkeypatch):
    original = subject._metadata
    inherited_group = os.getgid() + 1

    def metadata(info):
        # Model filesystem inheritance without chown, an outside-root probe,
        # or assuming this account can allocate a second real group.
        return {**original(info), "gid": inherited_group}

    monkeypatch.setattr(subject, "_metadata", metadata)
    _path, report, _digest, _clock = run(tmp_path)
    assert report["refused_initial_integrity_count"] == 0
    assert report["refused_integrity_observation_count"] == 0
    for case in report["cases"]:
        assert case["allocation"]["gid"] == inherited_group
        assert case["baseline"]["held"]["gid"] == inherited_group
        assert case["baseline"]["named"]["gid"] == inherited_group
        assert case["baseline_reset"] is False


def test_allocated_group_change_before_baseline_is_refused(tmp_path, monkeypatch):
    original_metadata = subject._metadata
    original_write = subject.probe.private._write_all
    inherited_group = os.getgid() + 1
    changed = False

    def metadata(info):
        return {**original_metadata(info), "gid": inherited_group + int(changed)}

    def write(*args, **kwargs):
        nonlocal changed
        original_write(*args, **kwargs)
        changed = True

    monkeypatch.setattr(subject, "_metadata", metadata)
    monkeypatch.setattr(subject.probe.private, "_write_all", write)
    with pytest.raises(subject.probe.private.SharadarCaptureError, match="allocation changed"):
        run(tmp_path)
    path = tmp_path / "private" / "synthetic-test-flags"
    assert (path / "direct_final" / "final.json").exists()
    assert not (path / "report.json").exists()


@pytest.mark.parametrize("dimension,value", [("uid", os.getuid() + 1), ("mode", 0o640)])
def test_allocated_owner_and_private_mode_still_required(tmp_path, monkeypatch, dimension, value):
    original = subject._metadata
    monkeypatch.setattr(subject, "_metadata", lambda info: {**original(info), dimension: value})
    with pytest.raises(subject.probe.private.SharadarCaptureError, match="allocation changed"):
        run(tmp_path)
    assert not (tmp_path / "private" / "synthetic-test-flags" / "report.json").exists()


def test_two_fixed_private_cases_roundrobin_thirty_second_window(tmp_path, monkeypatch):
    monkeypatch.setattr(subject.probe, "_provenance", lambda *_args: pytest.fail("no attribute/protection calls"))
    monkeypatch.setattr(subject.os, "listxattr", lambda *_args: pytest.fail("no attribute calls"), raising=False)
    monkeypatch.setattr(subject.probe.subprocess, "run", lambda *_args, **_kw: pytest.fail("no subprocess calls"))
    path, report, digest, clock = run(tmp_path)
    assert report["complete"] and report["case_count"] == 2 and report["observation_count"] == 22
    assert report["initial_verification_count"] == 2 and clock.value == pytest.approx(30)
    assert report["maximum_seconds"] == 45 and all(0 < value <= 10 for value in clock.sleeps)
    assert report["source_profile_sha256"] == subject.PROFILE_SHA256
    assert report["source_profile"] == subject.PROFILE
    assert report["schema"] == "arv2-synthetic-publication-flags-v2"
    assert report["source_profile"]["allocation_policy"] == "exclusive_created_file_dev_ino_gid_pinned_before_write"
    assert report["synthetic_only"] and not report["production_integrity_waiver"]
    assert not report["security_attributes_queried"] and not report["provider_or_qc_contact"]
    assert not report["proves_perpetual_stability"] and report["fixture_mode"] == "offline_test_double"
    assert [case["case"] for case in report["cases"]] == list(subject.CASES)
    raw = (path / "report.json").read_bytes()
    assert subject.probe.sha256_bytes(raw) == digest and len(raw) <= subject.MAX_REPORT_BYTES
    assert raw == subject.probe.canonical_json_bytes(json.loads(raw))
    assert stat.S_IMODE(path.stat().st_mode) == 0o700
    assert stat.S_IMODE((path / "report.json").stat().st_mode) == 0o600
    for case in report["cases"]:
        fixture = path / case["case"]
        assert stat.S_IMODE(fixture.stat().st_mode) == 0o700
        assert {leaf.name for leaf in fixture.iterdir()} == {"final.json"}
        leaf = fixture / "final.json"
        assert leaf.read_bytes() == subject.probe.PAYLOAD
        assert stat.S_IMODE(leaf.stat().st_mode) == 0o600 and leaf.stat().st_nlink == 1
        assert case["allocation"] == {"dev": leaf.stat().st_dev, "ino": leaf.stat().st_ino, "gid": leaf.stat().st_gid}
        assert case["baseline_reset"] is False
        assert set(case["baseline"]["held"]) == set(subject.STAT_FIELDS)
        assert [row["offset_seconds"] for row in case["observations"]] == list(subject.OFFSETS)
        assert [row["elapsed_seconds"] for row in case["observations"]] == pytest.approx(subject.OFFSETS)
        assert all(row["readback_matches"] and row["within_deadline"] for row in case["observations"])
    with pytest.raises(FileExistsError):
        subject._diagnose_publication_flags_for_test(path, clock, clock.sleep)
    assert (path / "report.json").read_bytes() == raw


def test_both_cases_established_before_roundrobin_and_writers_closed_before_visitors(tmp_path, monkeypatch):
    private = subject.probe.private
    original_new, original_close, original_open = private._new_private_file, os.close, private._open_private_regular
    original_sample = subject._sample
    writers = {}
    events = []
    visitors = []

    def new_file(directory, leaf, label):
        fd = original_new(directory, leaf, label)
        if label == "synthetic flags writer":
            writers[fd] = True
            events.append("writer")
            assert fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDWR
        return fd

    def close(fd):
        if writers.get(fd):
            writers[fd] = False
            events.append("writer_closed")
        return original_close(fd)

    def opened(*args, **kwargs):
        assert not any(writers.values())
        fd = original_open(*args, **kwargs)
        assert fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY
        visitors.append(fd)
        events.append("visitor")
        return fd

    def sample(*args, **kwargs):
        if "baseline_ok" in kwargs:
            assert len(visitors) == 2
            events.append(f"poll-{visitors.index(args[1])}")
        return original_sample(*args, **kwargs)

    monkeypatch.setattr(private, "_new_private_file", new_file)
    monkeypatch.setattr(subject.os, "close", close)
    monkeypatch.setattr(private, "_open_private_regular", opened)
    monkeypatch.setattr(subject, "_sample", sample)
    run(tmp_path)
    assert events[:6] == ["writer", "writer_closed", "visitor", "writer", "writer_closed", "visitor"]
    assert events[6:] == [name for _offset in subject.OFFSETS for name in ("poll-0", "poll-1")]


@pytest.mark.parametrize("dimension", ["flags", "ctime_ns", "gid", "uid", "mode", "birthtime_ns", "birthtime_seconds"])
def test_stat_drift_refused_named_and_held_without_reset(tmp_path, monkeypatch, dimension):
    original = subject._metadata
    active = False
    clock = Clock()
    original_sleep = clock.sleep

    def metadata(info):
        result = original(info)
        if active:
            result[dimension] = (result[dimension] or 0) + 1
        return result

    def sleep(delay):
        nonlocal active
        original_sleep(delay)
        active = True

    clock.sleep = sleep
    monkeypatch.setattr(subject, "_metadata", metadata)
    _path, report, _digest, _clock = run(tmp_path, clock=clock)
    for case in report["cases"]:
        assert case["observations"][0]["integrity_unchanged"]
        assert all(not row["integrity_unchanged"] and row["held_changed"] == [dimension]
                   and row["named_changed"] == [dimension] and row["readback_matches"]
                   for row in case["observations"][1:])
        assert case["baseline_reset"] is False
    assert report["refused_integrity_observation_count"] == 20


def test_initial_baseline_is_before_read_and_readtime_drift_poisons_following_checks(tmp_path, monkeypatch):
    original_metadata, original_read = subject._metadata, os.read
    read_seen = False

    def metadata(info):
        result = original_metadata(info)
        if read_seen:
            result["ctime_ns"] += 1
        return result

    def read(fd, size):
        nonlocal read_seen
        result = original_read(fd, size)
        read_seen = True
        return result

    monkeypatch.setattr(subject, "_metadata", metadata)
    monkeypatch.setattr(subject.os, "read", read)
    _path, report, _digest, _clock = run(tmp_path)
    first = report["cases"][0]
    assert first["initial_verification"]["during_read_held_changed"] == ["ctime_ns"]
    assert not first["baseline_integrity_unchanged"]
    assert all(not row["integrity_unchanged"] for row in first["observations"])
    assert report["refused_initial_integrity_count"] == 1


@pytest.mark.parametrize("dimension", ["ctime_ns", "gid", "uid", "mode"])
def test_during_read_temporary_drift_is_not_hidden_by_restored_after_metadata(tmp_path, monkeypatch, dimension):
    original_sample, original_metadata = subject._sample, subject._metadata
    polling, position = False, 0

    def metadata(info):
        nonlocal position
        result = original_metadata(info)
        if polling:
            position += 1
            # _sample observes held, named, held-after, then named-after.
            # Only the pre-read named observation drifts; afterwards every
            # value equals the original baseline again. No result is forged.
            if position == 2:
                result[dimension] += 1
        return result

    def sample(*args, **kwargs):
        nonlocal polling, position
        polling, position = "baseline_ok" in kwargs, 0
        try:
            return original_sample(*args, **kwargs)
        finally:
            if polling:
                assert position == 4
            polling = False

    monkeypatch.setattr(subject, "_metadata", metadata)
    monkeypatch.setattr(subject, "_sample", sample)
    _path, report, _digest, _clock = run(tmp_path)
    assert report["refused_initial_integrity_count"] == 0
    for case in report["cases"]:
        for row in case["observations"]:
            assert row["held_changed"] == row["named_changed"] == row["held_named_mismatch"] == []
            assert row["during_read_held_changed"] == []
            assert row["during_read_named_changed"] == [dimension]
            assert row["readback_matches"] and not row["integrity_unchanged"]
    assert report["refused_integrity_observation_count"] == 22


def test_named_group_differs_from_held_without_rebaseline(tmp_path, monkeypatch):
    original_sample, original_metadata = subject._sample, subject._metadata
    polling, position = False, 0

    def metadata(info):
        nonlocal position
        result = original_metadata(info)
        if polling:
            position += 1
            if position in (2, 4):  # Named stat before and after the read.
                result["gid"] += 1
        return result

    def sample(*args, **kwargs):
        nonlocal polling, position
        polling, position = "baseline_ok" in kwargs, 0
        try:
            return original_sample(*args, **kwargs)
        finally:
            polling = False

    monkeypatch.setattr(subject, "_metadata", metadata)
    monkeypatch.setattr(subject, "_sample", sample)
    _path, report, _digest, _clock = run(tmp_path)
    assert report["refused_initial_integrity_count"] == 0
    for case in report["cases"]:
        assert case["baseline_reset"] is False
        for row in case["observations"]:
            assert row["held_changed"] == row["during_read_held_changed"] == []
            assert row["during_read_named_changed"] == []
            assert row["named_changed"] == row["held_named_mismatch"] == ["gid"]
            assert row["readback_matches"] and not row["integrity_unchanged"]
    assert report["refused_integrity_observation_count"] == 22


def test_full_payload_rehash_refuses_changed_bytes_even_with_same_metadata(tmp_path, monkeypatch):
    original = os.read
    calls = 0

    def read(fd, size):
        nonlocal calls
        value = original(fd, size)
        calls += 1
        if calls == 3:
            return b"x" + value[1:]
        return value

    monkeypatch.setattr(subject.os, "read", read)
    _path, report, _digest, _clock = run(tmp_path)
    row = report["cases"][0]["observations"][0]
    assert row["held_changed"] == row["named_changed"] == []
    assert not row["readback_matches"] and not row["integrity_unchanged"]


def test_metadata_missing_optional_flags_or_birthtime_remains_unknown_not_zero():
    info = SimpleNamespace(st_dev=1, st_ino=2, st_size=3, st_mtime_ns=4, st_ctime_ns=5,
                           st_mode=stat.S_IFREG | 0o600, st_uid=os.getuid(), st_gid=os.getgid(), st_nlink=1)
    result = subject._metadata(info)
    assert result["flags"] is result["birthtime_ns"] is result["birthtime_seconds"] is None


def _replace(directory, leaf):
    os.rename(leaf, leaf + ".retained", src_dir_fd=directory, dst_dir_fd=directory)
    fd = os.open(leaf, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        os.write(fd, subject.probe.PAYLOAD)
    finally:
        os.close(fd)


def test_prebaseline_same_bytes_pending_replacement_refuses_factor_identity(tmp_path, monkeypatch):
    original = os.link

    def link(*args, **kwargs):
        _replace(kwargs["src_dir_fd"], "pending.json")
        return original(*args, **kwargs)

    monkeypatch.setattr(subject.os, "link", link)
    with pytest.raises(subject.probe.private.SharadarCaptureError, match="allocation changed"):
        run(tmp_path)
    path = tmp_path / "private" / "synthetic-test-flags"
    assert not (path / "report.json").exists() and list(path.rglob("*.retained"))


@pytest.mark.parametrize("replacement", ["same_bytes", "symlink"])
def test_named_leaf_replacement_refuses_and_never_reads_replacement(tmp_path, monkeypatch, replacement):
    clock = Clock()
    original_sleep = clock.sleep
    path = tmp_path / "private" / "synthetic-test-flags"
    changed = False

    def sleep(delay):
        nonlocal changed
        original_sleep(delay)
        if not changed:
            directory = os.open(path / "direct_final", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                if replacement == "same_bytes":
                    _replace(directory, "final.json")
                else:
                    os.rename("final.json", "final.json.retained", src_dir_fd=directory, dst_dir_fd=directory)
                    os.symlink("/UNREAD_TARGET", "final.json", dir_fd=directory)
            finally:
                os.close(directory)
            changed = True

    clock.sleep = sleep
    _path, report, _digest, _clock = run(tmp_path, clock=clock)
    first = report["cases"][0]
    assert first["observations"][0]["integrity_unchanged"]
    assert all(not row["integrity_unchanged"] and "ino" in row["named_changed"]
               and row["readback_matches"] for row in first["observations"][1:])


@pytest.mark.parametrize("scope", ["root", "ancestor"])
def test_named_root_or_ancestor_replacement_refuses_without_new_report(tmp_path, monkeypatch, scope):
    clock = Clock()
    original_sleep = clock.sleep
    path = tmp_path / "private" / "synthetic-test-flags"
    changed = False

    def sleep(delay):
        nonlocal changed
        original_sleep(delay)
        if not changed:
            target = path if scope == "root" else path.parent
            retained = target.with_name(target.name + "-retained")
            target.rename(retained)
            shutil.copytree(retained, target)
            changed = True

    clock.sleep = sleep
    with pytest.raises(subject.probe.private.SharadarCaptureError, match="pathname changed"):
        run(tmp_path, clock=clock)
    assert not (path / "report.json").exists() and list(tmp_path.rglob("final.json"))


def test_deadline_incomplete_does_not_sleep_past_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(subject, "MAX_SECONDS", 0.025)
    _path, report, _digest, clock = run(tmp_path)
    assert report["observation_count"] == 4 and not report["complete"]
    assert clock.value == pytest.approx(0.01)


def test_overdue_read_sample_retained_but_no_completion_claim(tmp_path, monkeypatch):
    clock = Clock()
    original = subject._sample
    changed = False

    def sample(*args, **kwargs):
        nonlocal changed
        result = original(*args, **kwargs)
        if not changed and "baseline_ok" in kwargs:
            clock.value += subject.MAX_SECONDS + 1
            changed = True
        return result

    monkeypatch.setattr(subject, "_sample", sample)
    _path, report, _digest, _clock = run(tmp_path, clock=clock)
    assert not report["complete"] and report["observation_count"] == 1
    assert not report["cases"][0]["observations"][0]["within_deadline"]


def test_report_byte_bound_refuses_without_cleanup_or_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(subject, "MAX_REPORT_BYTES", 8)
    with pytest.raises(subject.probe.private.SharadarCaptureError, match="byte limit"):
        run(tmp_path)
    path = tmp_path / "private" / "synthetic-test-flags"
    assert len(list(path.glob("*/final.json"))) == 2 and not (path / "report.json").exists()


def test_fixed_production_path_and_explicit_test_seam_refuse_wrong_scope(tmp_path):
    clock = Clock()
    with pytest.raises(subject.probe.private.SharadarCaptureError, match="production path is fixed"):
        subject._run(tmp_path / "wrong", clock, clock.sleep, synthetic_test=False)
    with pytest.raises(subject.probe.private.SharadarCaptureError, match="test path is not explicit"):
        subject._diagnose_publication_flags_for_test(tmp_path / "wrong", clock, clock.sleep)
    assert not list(tmp_path.iterdir())


def test_cli_count_hash_only_and_redacted_error(monkeypatch, capsys):
    report = {"case_count": 2, "observation_count": 22, "initial_verification_count": 2,
              "refused_initial_integrity_count": 1, "refused_integrity_observation_count": 20,
              "complete": True, "cases": ["UNEXPORTED_PRIVATE_METADATA"]}
    monkeypatch.setattr(subject, "_run", lambda *_args, **_kw: (copy.deepcopy(report), "a" * 64))
    assert subject.main([]) == 0
    output = capsys.readouterr().out
    assert "cases=2 observations=22 initial_checks=2 refused_initial=1 refused_integrity=20 complete=true" in output
    assert "UNEXPORTED" not in output and subject.probe.PAYLOAD.decode().strip() not in output
    monkeypatch.setattr(subject, "_run", lambda *_args, **_kw: (_ for _ in ()).throw(RuntimeError("PRIVATE_ERROR")))
    assert subject.main([]) == 1
    assert capsys.readouterr().err == "synthetic flags diagnostic refused; all allocated fixtures retained\n"


@pytest.mark.parametrize("kind", ["wrong_path", "test_seam", "wrong_cwd", "wrong_source_root"])
def test_relocation_requires_exact_root_path_and_non_test_mode(tmp_path, monkeypatch, kind):
    root = tmp_path / "authorized"
    root.mkdir()
    path = root / "R272"
    monkeypatch.setattr(subject, "RELOCATION_ROOT", root)
    monkeypatch.setattr(subject, "RELOCATION_ARTIFACT_PATH", path)
    monkeypatch.setattr(subject, "__file__", str(root / "scripts" / "diagnostic.py"))
    monkeypatch.chdir(root)
    if kind == "wrong_path":
        path = root / "other"
    elif kind == "wrong_cwd":
        monkeypatch.chdir(tmp_path)
    elif kind == "wrong_source_root":
        monkeypatch.setattr(subject, "__file__", str(tmp_path / "scripts" / "diagnostic.py"))
    clock = Clock()
    with pytest.raises(subject.probe.private.SharadarCaptureError, match="authorized relocation root/path"):
        subject._run(path, clock, clock.sleep, synthetic_test=(kind == "test_seam"), relocation_trial=True)
    assert not list(root.iterdir())


def test_relocation_exact_scope_uses_new_schema_and_is_exclusive(tmp_path, monkeypatch):
    root = tmp_path / "authorized"
    root.mkdir(mode=0o700)
    path = root / "R272"
    monkeypatch.setattr(subject, "RELOCATION_ROOT", root)
    monkeypatch.setattr(subject, "RELOCATION_ARTIFACT_PATH", path)
    monkeypatch.setattr(subject, "__file__", str(root / "scripts" / "diagnostic.py"))
    monkeypatch.chdir(root)
    clock = Clock()
    report, digest = subject._run(path, clock, clock.sleep, synthetic_test=False, relocation_trial=True)
    assert report["complete"] and report["refused_integrity_observation_count"] == 0
    assert report["refused_initial_integrity_count"] == 0
    assert report["schema"] == "arv2-authorized-relocation-flags-v1"
    assert report["source_profile"] == subject.RELOCATION_PROFILE
    assert report["source_profile_sha256"] == subject.RELOCATION_PROFILE_SHA256
    assert report["fixture_mode"] == "authorized_relocation_synthetic_diagnostic"
    assert subject.probe.sha256_bytes((path / "report.json").read_bytes()) == digest
    with pytest.raises(FileExistsError):
        subject._run(path, clock, clock.sleep, synthetic_test=False, relocation_trial=True)
