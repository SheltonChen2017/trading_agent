"""Fast synthetic temp fixtures only; never invoke the frozen B artifact path."""
import fcntl
import json
import os
import shutil
import stat

import pytest

from scripts import diagnose_arv2_publication_writer_lifecycle as subject


class Clock:
    def __init__(self):
        self.value = 0.0
        self.sleeps = []

    def __call__(self):
        return self.value

    def sleep(self, delay):
        self.sleeps.append(delay)
        self.value += delay


def run(tmp_path, monkeypatch, *, clock=None, provenance=None):
    clock = clock or Clock()
    monkeypatch.setattr(subject.probe, "_provenance", provenance or (lambda *_args: None))
    path = tmp_path / "private" / "synthetic-test-only"
    report, digest = subject._run(path, clock, clock.sleep)
    return path, report, digest, clock


def test_eight_private_factorial_cases_two_windows_and_retained_report(tmp_path, monkeypatch):
    path, report, digest, clock = run(tmp_path, monkeypatch)
    assert report["complete"] and report["case_count"] == 8 and report["observation_count"] == 96
    assert report["final_verification_count"] == report["consumer_verification_count"] == 8
    assert clock.value == pytest.approx(32) and all(0 < delay <= 1 for delay in clock.sleeps)
    assert report["synthetic_only"] and not report["production_integrity_waiver"]
    assert not report["proves_perpetual_stability"] and not report["provider_or_qc_contact"]
    raw = (path / "report.json").read_bytes()
    assert subject.probe.sha256_bytes(raw) == digest and len(raw) <= subject.MAX_REPORT_BYTES
    assert raw == subject.probe.canonical_json_bytes(json.loads(raw))
    assert stat.S_IMODE(path.stat().st_mode) == 0o700
    assert stat.S_IMODE((path / "report.json").stat().st_mode) == 0o600
    factors = [(False, True), (False, False), (True, True), (True, False)]
    assert [(row["writer_retained"], row["provenance_enabled"], row["repetition"])
            for row in report["cases"]] == [(a, b, rep) for a, b in factors for rep in (1, 2)]
    for case in report["cases"]:
        name = f"writer_{'retained' if case['writer_retained'] else 'early'}-provenance_{'on' if case['provenance_enabled'] else 'off'}-{case['repetition']}"
        fixture = path / name
        assert stat.S_IMODE(fixture.stat().st_mode) == 0o700
        assert {leaf.name for leaf in fixture.iterdir()} == {"final.json"}
        leaf = fixture / "final.json"
        assert leaf.read_bytes() == subject.probe.PAYLOAD
        assert stat.S_IMODE(leaf.stat().st_mode) == 0o600 and leaf.stat().st_nlink == 1
        assert case["writer_allocation"] == {"dev": leaf.stat().st_dev, "ino": leaf.stat().st_ino}
        assert case["baseline_reset"] is False and case["diagnostic_only"] is True
        for stage in ("before_writer_close", "after_writer_close"):
            assert [row["offset_seconds"] for row in case[stage]] == list(subject.probe.OFFSETS)
            assert [row["stage_elapsed_seconds"] for row in case[stage]] == pytest.approx(subject.probe.OFFSETS)
            assert all(row["readback_matches"] for row in case[stage])
        assert case["writer_close_performed"] is case["writer_retained"]
    with pytest.raises(FileExistsError):
        subject._run(path, clock, clock.sleep)
    assert (path / "report.json").read_bytes() == raw


def test_original_odrw_writer_and_same_readonly_visitor_through_both_windows(tmp_path, monkeypatch):
    private = subject.probe.private
    original_new, original_open, original_close = private._new_private_file, private._open_private_regular, os.close
    original_link, original_sample = os.link, subject.probe._sample
    cases = []

    def new_file(directory, leaf, label):
        fd = original_new(directory, leaf, label)
        if leaf == "pending.json":
            cases.append({"writer": fd, "writer_open": True, "visitor_open": False,
                          "calls": 0, "retained": len(cases) >= 4, "events": ["allocated"]})
            assert fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDWR
        return fd

    def close(fd):
        if cases:
            case = cases[-1]
            if case["writer_open"] and fd == case["writer"]:
                case["writer_open"] = False
                case["events"].append("writer_closed")
            elif case["visitor_open"] and fd == case["visitor"]:
                case["visitor_open"] = False
                case["events"].append("visitor_closed")
        return original_close(fd)

    def link(*args, **kwargs):
        case = cases[-1]
        assert case["writer_open"] is case["retained"]
        case["events"].append("linked")
        return original_link(*args, **kwargs)

    def opened(*args, **kwargs):
        case = cases[-1]
        if kwargs["label"] == "synthetic B final consumer":
            assert not case["writer_open"] and not case["visitor_open"]
            case["events"].append("consumer_opened")
        fd = original_open(*args, **kwargs)
        assert fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY
        if kwargs["label"] == "synthetic B read-only visitor":
            case["visitor"], case["visitor_open"] = fd, True
            case["events"].append("visitor_opened")
        return fd

    def sample(directory, fd):
        case = cases[-1]
        case["calls"] += 1
        if case["calls"] <= 14:
            assert fd == case["visitor"] and case["visitor_open"]
            assert case["writer_open"] is (case["retained"] and case["calls"] <= 7)
        else:
            assert case["calls"] == 15 and not case["visitor_open"] and not case["writer_open"]
        return original_sample(directory, fd)

    monkeypatch.setattr(private, "_new_private_file", new_file)
    monkeypatch.setattr(private, "_open_private_regular", opened)
    monkeypatch.setattr(subject.os, "close", close)
    monkeypatch.setattr(subject.os, "link", link)
    monkeypatch.setattr(subject.probe, "_sample", sample)
    run(tmp_path, monkeypatch)
    assert len(cases) == 8 and all(case["calls"] == 15 for case in cases)
    for case in cases:
        events = case["events"]
        assert (events.index("writer_closed") < events.index("linked")) is (not case["retained"])
        assert events.index("writer_closed") < events.index("visitor_closed") < events.index("consumer_opened")


def test_provenance_off_never_queries_and_enabled_unknown_remains_distinct(tmp_path, monkeypatch):
    calls = []

    def query(_fd, path, *_args):
        assert "provenance_on" in str(path)
        calls.append(path)
        return None

    _path, report, _digest, _clock = run(tmp_path, monkeypatch, provenance=query)
    assert len(calls) == 8
    for case in report["cases"]:
        assert case["provenance_requested"] is case["provenance_enabled"]
        assert case["provenance_before"] is case["provenance_after"] is None
        assert "provenance_performed" not in case


@pytest.mark.parametrize("phase", ["baseline", "postclose", "final", "consumer", "duringread"])
def test_drift_refuses_against_original_baseline_without_reset(tmp_path, monkeypatch, phase):
    original = subject.probe._sample
    calls = 0

    def sample(*args):
        nonlocal calls
        value = original(*args)
        calls += 1
        index = (calls - 1) % 15 + 1
        changed = ((phase == "postclose" and index >= 8) or
                   (phase == "final" and index >= 14) or (phase == "consumer" and index == 15))
        if changed:
            for key in ("held", "named", "held_after_read", "named_after_read"):
                value[key]["ctime_ns"] += 1
        if (phase == "baseline" and index == 1) or (phase == "duringread" and index == 3):
            value["during_read_held_changed"] = value["during_read_named_changed"] = ["ctime_ns"]
        return value

    monkeypatch.setattr(subject.probe, "_sample", sample)
    _path, report, _digest, _clock = run(tmp_path, monkeypatch)
    case = report["cases"][0]
    assert case["baseline_reset"] is False
    if phase == "baseline":
        assert not case["baseline_integrity_unchanged"]
        assert all(not row["integrity_unchanged"] for row in case["before_writer_close"] + case["after_writer_close"])
        assert not case["consumer_integrity_unchanged"]
    elif phase == "postclose":
        assert all(row["integrity_unchanged"] for row in case["before_writer_close"])
        assert all(not row["integrity_unchanged"] and row["held_changed"] == ["ctime_ns"]
                   for row in case["after_writer_close"])
        assert not case["final_integrity_unchanged"] and not case["consumer_integrity_unchanged"]
    elif phase == "duringread":
        row = case["before_writer_close"][1]
        assert not row["integrity_unchanged"] and row["held_changed"] == []
    else:
        assert all(row["integrity_unchanged"] for row in case["after_writer_close"])
        assert case["final_integrity_unchanged"] is (phase == "consumer")
        assert not case["consumer_integrity_unchanged"]


def _replacement(directory, leaf):
    os.rename(leaf, leaf + ".retained", src_dir_fd=directory, dst_dir_fd=directory)
    fd = os.open(leaf, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        os.write(fd, subject.probe.PAYLOAD)
    finally:
        os.close(fd)


@pytest.mark.parametrize("point", ["write", "link", "baseline"])
def test_same_bytes_prebaseline_replacement_cannot_change_lifecycle_factor(tmp_path, monkeypatch, point):
    private = subject.probe.private
    original_write, original_link, original_open = private._write_all, os.link, private._open_private_regular

    def written(fd, payload, label):
        original_write(fd, payload, label)
        if label == "synthetic B bytes" and point == "write":
            # Resolve only the already-known synthetic temp child, never provider paths.
            child = next((tmp_path / "private" / "synthetic-test-only").iterdir())
            directory = os.open(child, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                _replacement(directory, "pending.json")
            finally:
                os.close(directory)

    def linked(*args, **kwargs):
        if point == "link":
            _replacement(kwargs["src_dir_fd"], "pending.json")
        return original_link(*args, **kwargs)

    def opened(*args, **kwargs):
        if point == "baseline" and kwargs["label"] == "synthetic B read-only visitor":
            _replacement(args[0], "final.json")
        return original_open(*args, **kwargs)

    monkeypatch.setattr(private, "_write_all", written)
    monkeypatch.setattr(subject.os, "link", linked)
    monkeypatch.setattr(private, "_open_private_regular", opened)
    with pytest.raises(private.SharadarCaptureError, match="allocation changed"):
        run(tmp_path, monkeypatch)
    path = tmp_path / "private" / "synthetic-test-only"
    assert not (path / "report.json").exists() and list(path.rglob("*.retained"))


def test_consumer_same_bytes_replacement_is_refused_against_original_baseline(tmp_path, monkeypatch):
    original = subject.probe.private._open_private_regular
    replaced = False

    def opened(*args, **kwargs):
        nonlocal replaced
        if not replaced and kwargs["label"] == "synthetic B final consumer":
            _replacement(args[0], "final.json")
            replaced = True
        return original(*args, **kwargs)

    monkeypatch.setattr(subject.probe.private, "_open_private_regular", opened)
    path, report, _digest, _clock = run(tmp_path, monkeypatch)
    first = report["cases"][0]
    assert first["final_integrity_unchanged"] and not first["consumer_integrity_unchanged"]
    assert "ino" in first["consumer_verification"]["held_changed"]
    assert first["consumer_verification"]["readback_matches"] and first["baseline_reset"] is False
    assert len(list(path.rglob("*.retained"))) == 1


@pytest.mark.parametrize("phase", ["preclose", "postclose", "provenance", "consumer"])
def test_cooperative_deadline_marks_missing_or_overdue_completion(tmp_path, monkeypatch, phase):
    clock = Clock()
    original = subject.probe._sample
    calls = 0
    probes = 0
    if phase in ("preclose", "postclose"):
        monkeypatch.setattr(subject, "MAX_SECONDS", 0.025 if phase == "preclose" else 2.025)

    def sample(*args):
        nonlocal calls
        result = original(*args)
        calls += 1
        if phase == "consumer" and calls == 15:
            clock.value += subject.MAX_SECONDS
        return result

    def query(*_args):
        nonlocal probes
        probes += 1
        if phase == "provenance" and probes == 2:
            clock.value += subject.MAX_SECONDS
        return None

    monkeypatch.setattr(subject.probe, "_sample", sample)
    _path, report, _digest, _clock = run(tmp_path, monkeypatch, clock=clock, provenance=query)
    assert report["case_count"] == 1 and not report["complete"] and not report["cases"][0]["complete"]
    assert report["observation_count"] == {"preclose": 4, "postclose": 8, "provenance": 12, "consumer": 12}[phase]


def test_actual_offsets_include_optional_query_delay(tmp_path, monkeypatch):
    clock = Clock()

    def query(*_args):
        clock.value += 0.03
        return None

    _path, report, _digest, _clock = run(tmp_path, monkeypatch, clock=clock, provenance=query)
    first = report["cases"][0]["before_writer_close"][0]
    assert first["offset_seconds"] == 0 and first["stage_elapsed_seconds"] == pytest.approx(0.03)


@pytest.mark.parametrize("scope", ["root", "ancestor"])
def test_replaced_named_root_or_ancestor_refuses_without_report(tmp_path, monkeypatch, scope):
    clock = Clock()
    original_sleep = clock.sleep
    path = tmp_path / "private" / "synthetic-test-only"
    replaced = False

    def sleep(delay):
        nonlocal replaced
        original_sleep(delay)
        if not replaced:
            target = path if scope == "root" else path.parent
            retained = target.with_name(target.name + "-retained")
            target.rename(retained)
            shutil.copytree(retained, target)
            replaced = True

    clock.sleep = sleep
    with pytest.raises(subject.probe.private.SharadarCaptureError, match="pathname changed"):
        run(tmp_path, monkeypatch, clock=clock)
    assert replaced and not (path / "report.json").exists()
    assert list(tmp_path.rglob("final.json"))


def test_report_overflow_keeps_fixtures_without_report(tmp_path, monkeypatch):
    monkeypatch.setattr(subject, "MAX_REPORT_BYTES", 8)
    with pytest.raises(subject.probe.private.SharadarCaptureError, match="byte limit"):
        run(tmp_path, monkeypatch)
    path = tmp_path / "private" / "synthetic-test-only"
    assert len(list(path.glob("*/final.json"))) == 8 and not (path / "report.json").exists()


def test_cli_only_count_hash_completion_and_redacted_errors(monkeypatch, capsys):
    report = {"case_count": 8, "observation_count": 96, "refused_integrity_observation_count": 1,
              "final_verification_count": 8, "refused_final_integrity_count": 2,
              "consumer_verification_count": 8, "refused_consumer_integrity_count": 3,
              "complete": True, "cases": ["UNEXPORTED_METADATA"]}
    monkeypatch.setattr(subject, "_run", lambda *_args: (report, "a" * 64))
    assert subject.main([]) == 0
    output = capsys.readouterr().out
    assert "cases=8 observations=96" in output and "consumer_checks=8 refused_consumer=3 complete=true" in output
    assert "UNEXPORTED_METADATA" not in output and subject.probe.PAYLOAD.decode().strip() not in output
    monkeypatch.setattr(subject, "_run", lambda *_args: (_ for _ in ()).throw(RuntimeError("UNEXPORTED_ERROR")))
    assert subject.main([]) == 1
    assert capsys.readouterr().err == "synthetic writer diagnostic refused; all allocated fixtures retained\n"
