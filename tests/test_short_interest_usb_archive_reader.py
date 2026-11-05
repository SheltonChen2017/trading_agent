"""Fabricated local read failures do not become USB/source admission."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts import inspect_short_interest_usb_archive as driver

# Only protected-I/O cases require POSIX; pure parsing, transport and early
# refusal checks must remain active on the supported Windows host.
_POSIX_CAPTURE_ONLY = pytest.mark.skipif(
    not hasattr(os, "getuid"),
    reason=(
        "the protected-capture runtime requires POSIX ownership and mode "
        "semantics (os.getuid, O_NOFOLLOW, 0o600/0o700, symlinks); it cannot "
        "execute on this host, see the lane record SI-CR17-002"
    ),
)


class Clock:
    def check(self):
        pass


@pytest.fixture(autouse=True)
def isolated_comparison_evidence(monkeypatch):
    # The production registry is finite, process-local provenance, never a
    # persistent report. Every fixture uses only its own ordinary temp inode.
    monkeypatch.setattr(driver, "_STAMP_FAILURES", {})
    monkeypatch.setattr(driver, "_READ_ORIGINS", {})


def changed_info(info, field):
    values = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
    name = "st_" + field
    values[name] = values.get(name, 0) + 1
    return SimpleNamespace(**values)


@pytest.mark.parametrize("field", driver._STAMP_FIELDS)
@_POSIX_CAPTURE_ONLY
def test_exact_failed_original_stamp_projects_all_ten_field_names_without_new_stat(tmp_path, monkeypatch, field):
    target = tmp_path / "private-source-name"
    target.write_bytes(b"private fabricated bytes")
    item = driver._Read(target, 64, Clock(), component=("full", None))
    original = driver.os.fstat
    def fstat(fd):
        result = original(fd)
        return changed_info(result, field) if fd == item.fd else result
    monkeypatch.setattr(driver.os, "fstat", fstat)
    try:
        with pytest.raises(driver.UsbInspectionRefusal) as caught:
            item.audit()
        # A restored current observation is never substituted for the actual
        # failed original comparison, and role labels are captured at failure.
        monkeypatch.setattr(driver.os, "fstat", original)
        item.component = ("readme", None)
        detail = driver.comparison_diagnostic(caught.value)
        assert detail == {"schema": "si-usb-original-comparison-diagnostic-v1",
            "entered_phase": "held_audit", "role": "full", "code_ordinal": None,
            "chain_ordinal": len(item.directories) + 1,
            "relation": "file_descriptor_before_bytes_vs_original", "mismatching_fields": [field]}
        serialized = json.dumps(detail)
        assert str(target) not in serialized and "private-source-name" not in serialized
        assert "private fabricated bytes" not in serialized
    finally: item.close()


@pytest.mark.parametrize("comparison", ["root_descriptor", "root_name", "directory_descriptor", "directory_name"])
@_POSIX_CAPTURE_ONLY
def test_root_zero_and_directory_ordinal_and_first_failed_relation_preserve_short_circuit(tmp_path, monkeypatch, comparison):
    target = tmp_path / "literal"; target.write_bytes(b"fabricated")
    item = driver._Read(target, 64, Clock(), component=("code", 4))
    fstat, stat_call = driver.os.fstat, driver.os.stat
    ordinal = 0 if comparison.startswith("root") else 2
    selected_fd = item.fds[0] if ordinal == 0 else item.directories[ordinal - 1][2]
    parent, name = (None, "/") if ordinal == 0 else item.directories[ordinal - 1][:2]
    named_calls = []
    def named(path, *args, **kwargs):
        selected = (path == "/" if ordinal == 0 else path == name and kwargs.get("dir_fd") == parent)
        if selected:
            named_calls.append(True)
            if comparison.endswith("descriptor"):
                pytest.fail("name comparison ran after the first descriptor mismatch")
            return changed_info(stat_call(path, *args, **kwargs), "ctime_ns")
        return stat_call(path, *args, **kwargs)
    def descriptor(fd):
        result = fstat(fd)
        return changed_info(result, "ctime_ns") if fd == selected_fd and comparison.endswith("descriptor") else result
    monkeypatch.setattr(driver.os, "fstat", descriptor); monkeypatch.setattr(driver.os, "stat", named)
    try:
        with pytest.raises(driver.UsbInspectionRefusal) as caught: item.audit()
        detail = driver.comparison_diagnostic(caught.value)
        assert detail["role"] == "code" and detail["code_ordinal"] == 4
        assert detail["chain_ordinal"] == ordinal and detail["relation"] == comparison + "_vs_original"
        assert detail["mismatching_fields"] == ["ctime_ns"]
        assert len(named_calls) == (0 if comparison.endswith("descriptor") else 1)
    finally: item.close()


@_POSIX_CAPTURE_ONLY
def test_constructor_failure_reports_actual_entered_initial_phase(tmp_path, monkeypatch):
    target = tmp_path / "literal"; target.write_bytes(b"fabricated")
    read = driver._Read._read; first = True
    def read_then_change(self):
        nonlocal first
        raw = read(self)
        if first:
            first = False; info = target.stat()
            os.utime(target, ns=(info.st_atime_ns, info.st_mtime_ns + 1000000))
        return raw
    monkeypatch.setattr(driver._Read, "_read", read_then_change)
    with pytest.raises(driver.UsbInspectionRefusal) as caught:
        driver._Read(target, 64, Clock(), component=("manifest", None))
    detail = driver.comparison_diagnostic(caught.value)
    assert detail["entered_phase"] == "initial_audit" and detail["role"] == "manifest"
    assert "mtime_ns" in detail["mismatching_fields"]


@_POSIX_CAPTURE_ONLY
def test_close_failure_preserves_exact_phase_and_terminal_negative_only_fixed_fields(tmp_path, monkeypatch, capsys):
    target = tmp_path / "literal"; target.write_bytes(b"fabricated")
    item = driver._Read(target, 64, Clock(), component=("year", None))
    info = target.stat(); os.utime(target, ns=(info.st_atime_ns, info.st_mtime_ns + 1000000))
    def inspect(*unused): item.close()
    monkeypatch.setattr(driver, "inspect_registered", inspect)
    assert driver.main(["a" * 40, "b" * 40]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["code"] == "original_file_stamp_changed"
    assert result["original_comparison"]["entered_phase"] == "close_audit"
    assert result["original_comparison"]["role"] == "year"
    assert result["custody_qualified"] is result["source_admitted"] is False and not item.fds


@pytest.mark.parametrize("late", [False, True])
@_POSIX_CAPTURE_ONLY
def test_post_close_original_comparison_and_after_last_close_are_diagnosed(tmp_path, monkeypatch, late):
    target = tmp_path / "literal"; target.write_bytes(b"fabricated")
    item = driver._Read(target, 64, Clock(), component=("readme", None)); item.close()
    def mutate():
        info = target.stat(); os.utime(target, ns=(info.st_atime_ns, info.st_mtime_ns + 1000000))
    if late:
        close = driver.os.close; changed = False
        def close_then_change(fd):
            nonlocal changed
            selected = os.fstat(fd).st_ino == target.stat().st_ino
            close(fd)
            if selected and not changed: changed = True; mutate()
        monkeypatch.setattr(driver.os, "close", close_then_change)
    else: mutate()
    with pytest.raises(driver.UsbInspectionRefusal) as caught: item.after_close()
    detail = driver.comparison_diagnostic(caught.value)
    assert detail["entered_phase"] == ("post_close_named_audit" if late else "post_close_compare")
    assert detail["relation"] == ("post_close_file_name_vs_original" if late else "reopened_file_descriptor_vs_original")
    assert "mtime_ns" in detail["mismatching_fields"] and item.failed


@_POSIX_CAPTURE_ONLY
def test_forged_or_unrelated_failures_do_not_adopt_another_comparison_diagnostic(tmp_path, monkeypatch):
    target = tmp_path / "literal"; target.write_bytes(b"fabricated")
    item = driver._Read(target, 64, Clock(), component=("full", None))
    info = target.stat(); os.utime(target, ns=(info.st_atime_ns, info.st_mtime_ns + 1000000))
    try:
        with pytest.raises(driver.UsbInspectionRefusal) as caught: item.audit()
        genuine = caught.value; row = driver._STAMP_FAILURES[id(genuine)]
        forged = driver.UsbInspectionRefusal("original_directory_changed")
        assert driver.comparison_diagnostic(forged) is None
        driver._STAMP_FAILURES[id(forged)] = (forged, *row[1:])
        assert driver.comparison_diagnostic(forged) is None
        driver._STAMP_FAILURES[id(genuine)] = tuple(list(row))
        assert driver.comparison_diagnostic(genuine) is None
        assert driver.comparison_diagnostic(OSError("PRIVATE exception /path")) is None
    finally: item.close()


@_POSIX_CAPTURE_ONLY
def test_helper_called_outside_original_method_is_unknown_even_with_matching_literal_labels(tmp_path):
    target = tmp_path / "literal"; target.write_bytes(b"fabricated")
    item = driver._Read(target, 64, Clock(), component=("full", None))
    try:
        changed = (*item.original[:8], item.original[8] + 1, item.original[9])
        with pytest.raises(driver.UsbInspectionRefusal) as caught:
            driver._compare_stamp(item, changed, item.original, "original_directory_changed",
                "held_audit", 0, "root_descriptor_vs_original")
        assert driver.comparison_diagnostic(caught.value) is None
    finally: item.close()


@_POSIX_CAPTURE_ONLY
def test_actual_after_bytes_comparison_is_not_misattributed_to_earlier_check(tmp_path, monkeypatch):
    target = tmp_path / "literal"; target.write_bytes(b"fabricated")
    item = driver._Read(target, 64, Clock(), component=("full", None)); read = item._read
    def read_then_change():
        raw = read(); info = target.stat()
        os.utime(target, ns=(info.st_atime_ns, info.st_mtime_ns + 1000000)); return raw
    monkeypatch.setattr(item, "_read", read_then_change)
    try:
        with pytest.raises(driver.UsbInspectionRefusal) as caught: item.audit()
        detail = driver.comparison_diagnostic(caught.value)
        assert detail["relation"] == "file_descriptor_after_bytes_vs_original"
        assert detail["entered_phase"] == "held_audit" and "mtime_ns" in detail["mismatching_fields"]
    finally: item.close()


def test_fixed_role_and_exact_four_code_ordinals_are_supplied_by_registered_composition(monkeypatch):
    components = []; raw = b"FABRICATED_SOURCE_FREE_BYTES"
    class Read:
        def __init__(self, path, maximum, clock, *, minimum=1, component=None):
            components.append(component); self.raw = raw; self.digest = hashlib.sha256(raw).hexdigest()
            self.original = tuple(range(10))
        def audit(self): pass
        def close(self): pass
        def after_close(self): pass
    monkeypatch.setattr(driver, "_guard", lambda *args: None)
    monkeypatch.setattr(driver, "_Read", Read); monkeypatch.setattr(driver, "_git", lambda *args: raw)
    monkeypatch.setattr(driver, "INPUTS", tuple((role, "toy-fixed", len(raw), hashlib.sha256(raw).hexdigest())
        for role in ("full", "year", "manifest", "readme")))
    monkeypatch.setattr(driver, "_inspect_pair", lambda *args, **kwargs: ({"source_admitted": False}, "a" * 64))
    result = driver.inspect_registered("a" * 40, "b" * 40)
    assert components == [("code", n) for n in range(1, 5)] + [(role, None) for role in ("full", "year", "manifest", "readme")]
    assert result["protected_source_custody_verified"] is False and result["new_STARTs"] == 0


def test_literal_custody_error_without_original_frame_has_no_inferred_component(monkeypatch, capsys):
    def fail(*args): raise driver.UsbInspectionRefusal("original_directory_changed")
    monkeypatch.setattr(driver, "inspect_registered", fail)
    assert driver.main(["a" * 40, "b" * 40]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["code"] == "original_directory_changed" and "original_comparison" not in output


@pytest.mark.parametrize("drift", ["component", "reopen"])
@_POSIX_CAPTURE_ONLY
def test_constructor_role_and_phase_cannot_be_relabelled_before_genuine_failure(tmp_path, drift):
    target = tmp_path / "literal"; target.write_bytes(b"fabricated")
    item = driver._Read(target, 64, Clock(), component=("full", None))
    if drift == "component": item.component = ("code", 1)
    else: item._reopen = True
    info = target.stat(); os.utime(target, ns=(info.st_atime_ns, info.st_mtime_ns + 1000000))
    with pytest.raises(driver.UsbInspectionRefusal) as caught:
        item.close()  # The ordinary close remains strict and closes every FD.
    assert item.failed and not item.fds
    assert driver.comparison_diagnostic(caught.value) is None


@_POSIX_CAPTURE_ONLY
def test_original_read_is_readonly_and_exact_and_closes_all_handles(tmp_path):
    import fcntl
    target = tmp_path / "literal"
    target.write_bytes(b"fabricated source-free literal")
    item = driver._Read(target, 128, Clock())
    assert item.raw == target.read_bytes()
    assert item.digest == hashlib.sha256(item.raw).hexdigest()
    assert all(fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY
               for fd in item.fds)
    handles = tuple(item.fds)
    item.close()
    item.after_close()
    for fd in handles:
        with pytest.raises(OSError):
            os.fstat(fd)


@_POSIX_CAPTURE_ONLY
def test_empty_code_is_explicit_and_source_default_still_refuses(tmp_path):
    target = tmp_path / "empty_code.py"
    target.write_bytes(b"")
    with pytest.raises(driver.UsbInspectionRefusal, match="regular_bounded_single_link"):
        driver._Read(target, 64, Clock())
    item = driver._Read(target, 64, Clock(), minimum=0)
    assert item.raw == b"" and item.original[6] == 0
    item.close()
    item.after_close()


@pytest.mark.parametrize("change", ["bytes", "timestamps", "replacement"])
@_POSIX_CAPTURE_ONLY
def test_any_original_file_change_refuses_and_latches(tmp_path, change):
    target = tmp_path / "literal"
    target.write_bytes(b"fabricated")
    item = driver._Read(target, 64, Clock())
    original = target.stat()
    if change == "bytes":
        target.write_bytes(b"FABRICATED")
    elif change == "timestamps":
        os.utime(target, ns=(original.st_atime_ns, original.st_mtime_ns + 1000000))
    else:
        new = tmp_path / "replacement"
        new.write_bytes(b"fabricated")
        os.replace(new, target)
    with pytest.raises(driver.UsbInspectionRefusal):
        item.audit()
    assert item.failed
    with pytest.raises(driver.UsbInspectionRefusal, match="read_failure_latched"):
        item.audit()
    item.close()
    assert not item.fds


@_POSIX_CAPTURE_ONLY
def test_post_close_same_bytes_new_metadata_never_rebaseline(tmp_path):
    target = tmp_path / "literal"
    target.write_bytes(b"same bytes")
    item = driver._Read(target, 64, Clock())
    item.close()
    original = item.original
    current = target.stat()
    os.utime(target, ns=(current.st_atime_ns, current.st_mtime_ns + 1000000))
    with pytest.raises(driver.UsbInspectionRefusal, match="post_close_original_changed"):
        item.after_close()
    assert item.original is original
    assert item.failed
    os.utime(target, ns=(current.st_atime_ns, current.st_mtime_ns))
    with pytest.raises(driver.UsbInspectionRefusal, match="closed_original_required"):
        item.after_close()


@_POSIX_CAPTURE_ONLY
def test_post_close_parent_metadata_change_also_refuses(tmp_path):
    target = tmp_path / "literal"
    target.write_bytes(b"same bytes")
    item = driver._Read(target, 64, Clock())
    item.close()
    original = tmp_path.stat()
    os.utime(tmp_path, ns=(original.st_atime_ns, original.st_mtime_ns + 1000000))
    with pytest.raises(driver.UsbInspectionRefusal, match="post_close_original_changed"):
        item.after_close()


@_POSIX_CAPTURE_ONLY
def test_metadata_change_at_last_fresh_descriptor_close_is_detected(tmp_path, monkeypatch):
    target = tmp_path / "literal"
    target.write_bytes(b"same bytes")
    item = driver._Read(target, 64, Clock())
    item.close()
    original_close = driver.os.close
    changed = False
    def close_then_change(fd):
        nonlocal changed
        data_fd = os.fstat(fd).st_ino == target.stat().st_ino
        original_close(fd)
        if data_fd and not changed:
            changed = True
            current = target.stat()
            os.utime(target, ns=(current.st_atime_ns, current.st_mtime_ns + 1000000))
    monkeypatch.setattr(driver.os, "close", close_then_change)
    with pytest.raises(driver.UsbInspectionRefusal, match="post_close_original_changed"):
        item.after_close()
    assert changed and item.failed


@pytest.mark.parametrize("kind", ["file_symlink", "parent_symlink", "hardlink", "oversize", "empty"])
@_POSIX_CAPTURE_ONLY
def test_untrusted_path_or_file_shape_fails_closed(tmp_path, kind):
    target = tmp_path / "literal"
    target.write_bytes(b"fabricated")
    if kind == "file_symlink":
        link = tmp_path / "link"
        link.symlink_to(target)
        target = link
    elif kind == "parent_symlink":
        link = tmp_path / "link"
        link.symlink_to(tmp_path, target_is_directory=True)
        target = link / target.name
    elif kind == "hardlink":
        os.link(target, tmp_path / "alias")
    elif kind == "empty":
        target.write_bytes(b"")
    with pytest.raises((OSError, driver.UsbInspectionRefusal)):
        driver._Read(target, 2 if kind == "oversize" else 64, Clock())


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, 181])
def test_clock_refuses_nonfinite_backwards_and_expired(monkeypatch, value):
    observations = iter([0, value])
    monkeypatch.setattr(driver.time, "monotonic", lambda: next(observations))
    clock = driver._Clock()
    with pytest.raises(driver.UsbInspectionRefusal, match="clock_or_deadline"):
        clock.check()


def test_guard_accepts_git_sha1_and_only_matching_lane_remote(monkeypatch):
    head, remote = "a" * 40, "b" * 40
    replies = {
        ("rev-parse", "--show-toplevel"): str(driver.ROOT).encode(),
        ("branch", "--show-current"): b"codex/strategy-short-interest",
        ("rev-parse", "HEAD"): head.encode(),
        ("status", "--porcelain=v1", "--untracked-files=normal"): b"",
        ("rev-parse", "refs/remotes/origin/codex/strategy-short-interest"): remote.encode(),
        ("ls-remote", "--exit-code", "--refs", "origin", "refs/heads/codex/strategy-short-interest"):
            (remote + "\trefs/heads/codex/strategy-short-interest").encode(),
    }
    monkeypatch.setattr(driver.Path, "cwd", lambda: driver.ROOT)
    monkeypatch.setattr(driver.Path, "resolve", lambda self: self)
    monkeypatch.setattr(driver, "_git", lambda *args: replies[args])
    driver._guard(head, remote)
    replies[("status", "--porcelain=v1", "--untracked-files=normal")] = b"?? unrelated"
    with pytest.raises(driver.UsbInspectionRefusal, match="lane_snapshot_changed"):
        driver._guard(head, remote)
    with pytest.raises(driver.UsbInspectionRefusal, match="exact_git_hashes_required"):
        driver._guard("a" * 64, remote)


@pytest.mark.parametrize("error", [OSError("PRIVATE source values"),
    driver.UsbInspectionRefusal("PRIVATE path"), driver.UsbInspectionRefusal()])
def test_refusal_does_not_disclose_external_exception_text(monkeypatch, capsys, error):
    def bad(*unused):
        raise error
    monkeypatch.setattr(driver, "inspect_registered", bad)
    assert driver.main(["a" * 40, "b" * 40]) == 2
    output = capsys.readouterr().out
    assert "PRIVATE" not in output
    assert json.loads(output) == {"status": "refused_external_byte_inspection",
                                 "code": "unexpected_local_refusal",
                                 "custody_qualified": False, "source_admitted": False}


def test_registered_read_rejects_pin_mismatch_before_parser(monkeypatch, tmp_path):
    def forbidden(**unused):
        pytest.fail("changed source reached parser")
    class FakeRead:
        def __init__(self, path, maximum, clock, **unused):
            self.raw = b"changed"
            self.digest = hashlib.sha256(self.raw).hexdigest()
        def close(self):
            pass
    monkeypatch.setattr(driver, "_guard", lambda *unused: None)
    monkeypatch.setattr(driver, "CODE_FILES", ())
    monkeypatch.setattr(driver, "_Read", FakeRead)
    monkeypatch.setattr(driver, "_inspect_pair", forbidden)
    with pytest.raises(driver.UsbInspectionRefusal, match="fixed_usb_input_changed"):
        driver.inspect_registered("a" * 40, "b" * 40)


@pytest.mark.parametrize("terminal_failure", ["close", "guard", "code", "source", "final_guard"])
def test_no_result_escapes_failed_terminal_boundary(monkeypatch, terminal_failure):
    events = []
    class Report:
        def to_payload(self):
            return {"authority": {"source_admitted": False}}
    class FakeRead:
        def __init__(self, path, maximum, clock, **unused):
            self.path = str(path)
            self.raw = b"fabricated"
            self.digest = hashlib.sha256(self.raw).hexdigest()
            self.original = tuple(range(10))
        def close(self):
            events.append("close")
            if terminal_failure == "close":
                raise driver.UsbInspectionRefusal("test_close_failure")
        def audit(self):
            events.append("audit")
        def after_close(self):
            events.append("after_close")
            if terminal_failure in ("code", "source") and (
                (terminal_failure == "code") == self.path.startswith(str(driver.ROOT))
            ):
                raise driver.UsbInspectionRefusal("test_terminal_failure")
    def guard(*unused):
        events.append("guard")
        if ((terminal_failure == "guard" and events.count("guard") == 2)
                or (terminal_failure == "final_guard" and events.count("guard") == 3)):
            raise driver.UsbInspectionRefusal("test_guard_failure")
    monkeypatch.setattr(driver, "_guard", guard)
    monkeypatch.setattr(driver, "CODE_FILES", (driver.MODEL,))
    digest = hashlib.sha256(b"fabricated").hexdigest()
    monkeypatch.setattr(driver, "INPUTS", (("full", "toy.zip", 10, digest),))
    monkeypatch.setattr(driver, "_Read", FakeRead)
    monkeypatch.setattr(driver, "_git", lambda *unused: b"fabricated")
    monkeypatch.setattr(driver, "_inspect_pair", lambda *args, **unused: (Report().to_payload(), "c" * 64))
    with pytest.raises(driver.UsbInspectionRefusal):
        driver.inspect_registered("a" * 40, "b" * 40)
    assert "close" in events


def test_isolated_reader_never_initializes_research_package_or_third_party_calendar():
    # Only reviewed Python source is compiled; the model is given fabricated
    # invalid archive bytes and must refuse without importing package siblings.
    root = Path(__file__).resolve().parents[1]
    program = r'''
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
namespace = {"__name__": "_fixture_reader", "__file__": sys.argv[2]}
with open(sys.argv[2], "rb") as f: source = f.read()
exec(compile(source, sys.argv[2], "exec"), namespace)
with open(sys.argv[3], "rb") as f: model = f.read()
try:
    namespace["_inspect_pair"](model, full=b"fabricated", year=b"fabricated",
                             manifest=b"{}", readme=b"fabricated")
except ValueError:
    pass
else:
    raise AssertionError("wrong pins admitted")
assert "research" not in sys.modules
assert "pandas" not in sys.modules
assert "pandas_market_calendars" not in sys.modules
assert "_si_usb_registered_byte_inspector" not in sys.modules
print("isolated_four_file_inspector_only")
'''
    result = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", program,
        str(root), str(root / driver.DRIVER), str(root / driver.MODEL)],
        cwd=root, env={"PATH": "/usr/bin:/bin"}, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "isolated_four_file_inspector_only"


@_POSIX_CAPTURE_ONLY
def test_git_metadata_reads_work_under_unchanged_all_write_open_denial():
    root = Path(__file__).resolve().parents[1]
    program = r'''
import sys, os
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
namespace = {"__name__": "_fixture_reader", "__file__": sys.argv[2]}
with open(sys.argv[2], "rb") as f: source = f.read()
exec(compile(source, sys.argv[2], "exec"), namespace)
attempts = []
def deny(event, args):
    if event == "open" and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
        attempts.append("write_open_denied")
        raise RuntimeError("write_open_denied")
sys.addaudithook(deny)
assert namespace["_git"]("rev-parse", "--show-toplevel").decode().strip() == sys.argv[1]
assert attempts == []
print("lane_Git_read_no_Python_write_open")
'''
    result = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", program,
        str(root), str(root / driver.DRIVER)], cwd=root,
        env={"PATH": "/usr/bin:/bin", "GIT_OPTIONAL_LOCKS": "0"}, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "lane_Git_read_no_Python_write_open"
