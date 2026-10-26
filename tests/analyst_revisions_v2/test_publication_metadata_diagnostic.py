"""Synthetic temp fixtures only; never execute the frozen production path."""
import json
import os
import shutil
import stat
import subprocess
from types import SimpleNamespace

import pytest

from scripts import diagnose_arv2_publication_metadata as subject
from research.analyst_revisions_v2.canonical import canonical_json_bytes, sha256_bytes


class Clock:
    value = 0.0

    def __init__(self):
        self.sleeps = []

    def __call__(self):
        return self.value

    def sleep(self, delay):
        self.sleeps.append(delay)
        self.value += delay


def run(tmp_path, monkeypatch, *, clock=None, probe=None):
    clock = clock or Clock()
    monkeypatch.setattr(subject, "_provenance", probe or (lambda *_args: None))
    path = tmp_path / "private" / "synthetic-test-only"
    report, digest = subject._run(path, clock, clock.sleep)
    return path, report, digest, clock


def test_fast_synthetic_path_retains_nine_exclusive_private_fixtures_and_bounded_report(tmp_path, monkeypatch):
    path, report, digest, clock = run(tmp_path, monkeypatch)
    assert report["complete"] and report["case_count"] == 9 and report["observation_count"] == 54
    assert report["final_verification_count"] == 9
    assert clock.value == pytest.approx(18) and all(0 < value <= 1 for value in clock.sleeps)
    assert report["synthetic_only"] is True and report["production_integrity_waiver"] is False
    assert report["proves_perpetual_stability"] is False and report["provider_or_qc_contact"] is False
    raw = (path / "report.json").read_bytes()
    assert len(raw) <= subject.MAX_REPORT_BYTES and sha256_bytes(raw) == digest
    assert raw == canonical_json_bytes(json.loads(raw))
    assert stat.S_IMODE(path.stat().st_mode) == 0o700
    assert set(leaf.name for leaf in path.iterdir()) == {"report.json"} | {
        f"{variant}-{index}" for variant in subject.VARIANTS for index in (1, 2, 3)}
    for case in report["cases"]:
        fixture = path / f"{case['variant']}-{case['repetition']}"
        assert stat.S_IMODE(fixture.stat().st_mode) == 0o700
        assert set(leaf.name for leaf in fixture.iterdir()) == {"final.json"}
        leaf = fixture / "final.json"
        assert leaf.read_bytes() == subject.PAYLOAD
        assert stat.S_IMODE(leaf.stat().st_mode) == 0o600 and leaf.stat().st_nlink == 1
        assert [row["offset_seconds"] for row in case["observations"]] == list(subject.OFFSETS)
        assert all(row["readback_sha256"] == sha256_bytes(subject.PAYLOAD)
                   and row["readback_matches"] for row in case["observations"])
    before = raw
    with pytest.raises(FileExistsError):
        subject._run(path, clock, clock.sleep)
    assert (path / "report.json").read_bytes() == before


def test_original_writer_close_readonly_reopen_and_exact_extra_fsync_variant(tmp_path, monkeypatch):
    original_new = subject.private._new_private_file
    original_link = subject.os.link
    original_open = subject.private._open_private_regular
    original_sync = subject.private._fsync
    pending = []
    opened_labels = []
    sync_labels = []

    def new_file(directory, leaf, label):
        descriptor = original_new(directory, leaf, label)
        if leaf == "pending.json":
            pending.append(descriptor)
        return descriptor

    def link(*args, **kwargs):
        with pytest.raises(OSError):
            os.fstat(pending[-1])  # Original pending writer is already closed.
        return original_link(*args, **kwargs)

    def opened(*args, **kwargs):
        opened_labels.append(kwargs["label"])
        return original_open(*args, **kwargs)

    def sync(descriptor, label):
        sync_labels.append(label)
        return original_sync(descriptor, label)

    monkeypatch.setattr(subject.private, "_new_private_file", new_file)
    monkeypatch.setattr(subject.os, "link", link)
    monkeypatch.setattr(subject.private, "_open_private_regular", opened)
    monkeypatch.setattr(subject.private, "_fsync", sync)
    _path, report, _digest, _clock = run(tmp_path, monkeypatch)
    assert len(pending) == 6
    assert opened_labels.count("synthetic read-only visitor") == 9
    assert opened_labels.count("synthetic final sync") == 3
    assert sync_labels.count("synthetic final") == 3
    for case in report["cases"]:
        steps = [row["step"] for row in case["steps"]]
        assert steps[0] == "writer_closed_after_file_fsync"
        if case["variant"] == "direct_final":
            assert steps == ["writer_closed_after_file_fsync", "directories_fsynced"]
        else:
            assert steps[1:4] == ["final_linked", "pending_unlinked", "directories_fsynced"]
            assert case["steps"][1]["named"]["nlink"] == 2
            assert case["steps"][2]["named"]["nlink"] == 1
            assert ("extra_final_fsync_closed" in steps) == (case["variant"] == "pending_link_final_fsync")


def test_ctime_only_drift_is_refused_against_original_baseline_without_rebase(tmp_path, monkeypatch):
    original = subject._sample
    calls = 0

    def drift(*args):
        nonlocal calls
        value = original(*args)
        calls += 1
        if 3 <= calls <= 7:
            for key in ("held", "named", "held_after_read", "named_after_read"):
                value[key]["ctime_ns"] += 1
        return value

    monkeypatch.setattr(subject, "_sample", drift)
    _path, report, _digest, _clock = run(tmp_path, monkeypatch)
    observations = report["cases"][0]["observations"]
    assert observations[0]["integrity_unchanged"]
    assert all(row["held_changed"] == ["ctime_ns"] and row["named_changed"] == ["ctime_ns"]
               and not row["integrity_unchanged"] for row in observations[1:])
    assert all(row["readback_matches"] for row in observations)
    assert report["refused_integrity_observation_count"] >= 5


def test_initial_baseline_read_drift_is_refused_not_absorbed(tmp_path, monkeypatch):
    original = subject._sample
    calls = 0

    def drift(*args):
        nonlocal calls
        value = original(*args)
        calls += 1
        if calls == 1:
            value["held_after_read"]["ctime_ns"] += 1
            value["named_after_read"]["ctime_ns"] += 1
            value["during_read_held_changed"] = ["ctime_ns"]
            value["during_read_named_changed"] = ["ctime_ns"]
        return value

    monkeypatch.setattr(subject, "_sample", drift)
    _path, report, _digest, _clock = run(tmp_path, monkeypatch)
    case = report["cases"][0]
    assert case["baseline"]["during_read_held_changed"] == ["ctime_ns"]
    assert not case["baseline_integrity_unchanged"]
    assert all(not row["integrity_unchanged"] for row in case["observations"])
    assert not case["final_integrity_unchanged"]


def test_during_read_drift_refuses_even_when_after_metadata_returns_to_baseline(tmp_path, monkeypatch):
    original = subject._sample
    calls = 0

    def drift(*args):
        nonlocal calls
        value = original(*args)
        calls += 1
        if calls == 2:
            value["held"]["ctime_ns"] += 1
            value["named"]["ctime_ns"] += 1
            value["during_read_held_changed"] = ["ctime_ns"]
            value["during_read_named_changed"] = ["ctime_ns"]
        return value

    monkeypatch.setattr(subject, "_sample", drift)
    _path, report, _digest, _clock = run(tmp_path, monkeypatch)
    first = report["cases"][0]["observations"][0]
    assert first["held_changed"] == [] and first["named_changed"] == []
    assert not first["integrity_unchanged"]


@pytest.mark.parametrize("phase", ["initial", "final"])
def test_provenance_caused_ctime_drift_is_not_hidden_or_rebased(tmp_path, monkeypatch, phase):
    original = subject._sample
    active = False
    probes = 0

    def probe(*_args):
        nonlocal active, probes
        probes += 1
        if probes == (1 if phase == "initial" else 2):
            active = True
        return None

    def sample(*args):
        value = original(*args)
        if active:
            for key in ("held", "named", "held_after_read", "named_after_read"):
                value[key]["ctime_ns"] += 1
        return value

    monkeypatch.setattr(subject, "_sample", sample)
    _path, report, _digest, _clock = run(tmp_path, monkeypatch, probe=probe)
    first = report["cases"][0]
    assert all(row["integrity_unchanged"] is (phase == "final") for row in first["observations"])
    assert first["final_verification"]["held_changed"] == ["ctime_ns"]
    assert not first["final_integrity_unchanged"] and report["refused_final_integrity_count"] >= 1


@pytest.mark.parametrize("field,value", [("mode", 0o640), ("regular", False), ("nlink", 2), ("uid", -1)])
def test_unsafe_baseline_metadata_is_not_claimed_unchanged(tmp_path, monkeypatch, field, value):
    original = subject._sample
    calls = 0

    def invalid(*args):
        nonlocal calls
        result = original(*args)
        calls += 1
        if calls == 1:
            for key in ("held", "named", "held_after_read", "named_after_read"):
                result[key][field] = value
        return result

    monkeypatch.setattr(subject, "_sample", invalid)
    _path, report, _digest, _clock = run(tmp_path, monkeypatch)
    first = report["cases"][0]
    assert not first["baseline_integrity_unchanged"] and not first["final_integrity_unchanged"]
    assert all(not row["integrity_unchanged"] for row in first["observations"])


def test_same_bytes_path_replacement_refuses_named_identity_without_reading_replacement(tmp_path, monkeypatch):
    clock = Clock()
    replaced = False
    path = tmp_path / "private" / "synthetic-test-only"
    original_sleep = clock.sleep

    def replace(delay):
        nonlocal replaced
        original_sleep(delay)
        if not replaced:
            fixture = path / "direct_final-1"
            retained = fixture / "retained-original.json"
            (fixture / "final.json").rename(retained)
            fd = os.open(fixture / "final.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                os.write(fd, subject.PAYLOAD)
            finally:
                os.close(fd)
            replaced = True

    clock.sleep = replace
    _path, report, _digest, _clock = run(tmp_path, monkeypatch, clock=clock)
    later = report["cases"][0]["observations"][1:]
    assert all("ino" in row["named_changed"] and "ino" in row["held_named_mismatch"]
               and not row["integrity_unchanged"] for row in later)
    assert all(row["readback_matches"] for row in later)
    assert (path / "direct_final-1" / "retained-original.json").read_bytes() == subject.PAYLOAD


def test_deadline_marks_incomplete_does_not_allocate_more_cases(tmp_path, monkeypatch):
    monkeypatch.setattr(subject, "MAX_SECONDS", 0.025)
    _path, report, _digest, clock = run(tmp_path, monkeypatch)
    assert not report["complete"] and report["case_count"] == 1 and report["observation_count"] == 2
    assert not report["cases"][0]["complete"] and clock.value < 0.025


def test_overdue_native_observation_does_not_claim_full_completion(tmp_path, monkeypatch):
    clock = Clock()
    original = subject._sample
    calls = 0

    def overdue(*args):
        nonlocal calls
        result = original(*args)
        calls += 1
        if calls == 2:
            clock.value += subject.MAX_SECONDS + 1
        return result

    monkeypatch.setattr(subject, "_sample", overdue)
    _path, report, _digest, _clock = run(tmp_path, monkeypatch, clock=clock)
    assert not report["complete"] and report["observation_count"] == 0
    assert report["case_count"] == 1 and not report["cases"][0]["complete"]


def test_overdue_final_probe_marks_case_incomplete_despite_six_observations(tmp_path, monkeypatch):
    clock = Clock()
    calls = 0

    def probe(*_args):
        nonlocal calls
        calls += 1
        if calls == 2:
            clock.value += subject.MAX_SECONDS
        return None

    _path, report, _digest, _clock = run(tmp_path, monkeypatch, clock=clock, probe=probe)
    assert report["observation_count"] == 6 and report["case_count"] == 1
    assert not report["complete"] and not report["cases"][0]["complete"]


@pytest.mark.parametrize("scope", ["root", "ancestor"])
def test_same_bytes_directory_replacement_refuses_named_path_without_new_report(tmp_path, monkeypatch, scope):
    clock = Clock()
    path = tmp_path / "private" / "synthetic-test-only"
    original_sleep = clock.sleep
    replaced = False

    def replace(delay):
        nonlocal replaced
        original_sleep(delay)
        if not replaced:
            target = path if scope == "root" else path.parent
            retained = target.with_name(target.name + "-retained")
            target.rename(retained)
            shutil.copytree(retained, target)
            replaced = True

    clock.sleep = replace
    with pytest.raises(subject.private.SharadarCaptureError, match="pathname changed"):
        run(tmp_path, monkeypatch, clock=clock)
    assert replaced and not (path / "report.json").exists()
    assert list(tmp_path.rglob("final.json"))  # Both retained and replacement fixtures survive.


def test_report_overflow_refuses_without_overwrite_or_cleanup(tmp_path, monkeypatch):
    monkeypatch.setattr(subject, "MAX_REPORT_BYTES", 8)
    with pytest.raises(subject.private.SharadarCaptureError, match="byte limit"):
        run(tmp_path, monkeypatch)
    path = tmp_path / "private" / "synthetic-test-only"
    assert len(list(path.glob("*/final.json"))) == 9 and not (path / "report.json").exists()


@pytest.mark.parametrize("present", [False, True])
def test_descriptor_listxattr_exposes_only_fixed_presence(tmp_path, monkeypatch, present):
    path = tmp_path / "fixture.json"
    path.write_bytes(subject.PAYLOAD)
    fd = os.open(path, os.O_RDONLY)
    calls = []
    monkeypatch.setattr(subject.os, "listxattr", lambda descriptor: calls.append(descriptor) or
                        (["com.apple.provenance", "UNEXPORTED_OTHER_NAME"] if present else ["UNEXPORTED_OTHER_NAME"]),
                        raising=False)
    monkeypatch.setattr(subject.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("no fallback when available"))
    try:
        assert subject._provenance(fd, path, 1, Clock()) is present
        assert calls == [fd]
    finally:
        os.close(fd)


def test_names_only_cli_fallback_bounded_by_remaining_budget_and_no_raw_output(tmp_path, monkeypatch):
    path = tmp_path / "fixture.json"
    path.write_bytes(subject.PAYLOAD)
    fd = os.open(path, os.O_RDONLY)
    monkeypatch.delattr(subject.os, "listxattr", raising=False)
    calls = []

    def cli(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout=b"UNEXPORTED_OTHER_NAME\ncom.apple.provenance\n")

    monkeypatch.setattr(subject.subprocess, "run", cli)
    try:
        assert subject._provenance(fd, path, 0.1, Clock()) is True
        args, options = calls[0]
        assert args == ["/usr/bin/xattr", "-s", str(path)]
        assert options["timeout"] == 0.1 and options["stdout"] == subprocess.PIPE
        assert options["stderr"] == subprocess.DEVNULL and options["check"] is False
        assert subject._provenance(fd, path, 0, Clock()) is None and len(calls) == 1
    finally:
        os.close(fd)


@pytest.mark.parametrize("kind", ["timeout", "failed", "oversized", "identity_changed", "unsupported_present"])
def test_provenance_uncertainty_never_claims_absence_or_exports_detail(tmp_path, monkeypatch, kind):
    path = tmp_path / "fixture.json"
    path.write_bytes(subject.PAYLOAD)
    fd = os.open(path, os.O_RDONLY)
    monkeypatch.delattr(subject.os, "listxattr", raising=False)

    def cli(*_args, **_kwargs):
        if kind == "timeout":
            raise subprocess.TimeoutExpired("UNEXPORTED_DETAIL", 0.5)
        if kind == "identity_changed":
            path.chmod(0o640)
        return SimpleNamespace(returncode=1 if kind == "failed" else 0,
                               stdout=b"x" * 8193 if kind == "oversized" else b"com.apple.provenance\n")

    if kind == "unsupported_present":
        monkeypatch.setattr(subject.os, "listxattr", lambda *_args: (_ for _ in ()).throw(TypeError("UNEXPORTED_DETAIL")), raising=False)
        monkeypatch.setattr(subject.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("present unsupported is unknown, not fallback"))
    else:
        monkeypatch.setattr(subject.subprocess, "run", cli)
    try:
        assert subject._provenance(fd, path, 1, Clock()) is None
    finally:
        os.close(fd)


def test_cli_summary_never_prints_payload_or_metadata_and_redacts_errors(monkeypatch, capsys):
    report = {"case_count": 9, "observation_count": 54, "refused_integrity_observation_count": 1,
              "final_verification_count": 9, "refused_final_integrity_count": 2,
              "complete": True, "cases": ["UNPRINTED_METADATA"]}
    monkeypatch.setattr(subject, "_run", lambda *_args: (report, "a" * 64))
    assert subject.main([]) == 0
    output = capsys.readouterr()
    assert "cases=9 observations=54 refused_integrity=1 final_checks=9 refused_final=2 complete=true report_sha256=" in output.out
    assert "UNPRINTED_METADATA" not in output.out and subject.PAYLOAD.decode().strip() not in output.out
    monkeypatch.setattr(subject, "_run", lambda *_args: (_ for _ in ()).throw(RuntimeError("UNEXPORTED_DETAIL")))
    assert subject.main([]) == 1
    assert capsys.readouterr().err == "synthetic metadata diagnostic refused; all allocated fixtures retained\n"
