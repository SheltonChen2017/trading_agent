"""Fabricated local read failures do not become USB/source admission."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import inspect_short_interest_usb_archive as driver


class Clock:
    def check(self):
        pass


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


def test_post_close_parent_metadata_change_also_refuses(tmp_path):
    target = tmp_path / "literal"
    target.write_bytes(b"same bytes")
    item = driver._Read(target, 64, Clock())
    item.close()
    original = tmp_path.stat()
    os.utime(tmp_path, ns=(original.st_atime_ns, original.st_mtime_ns + 1000000))
    with pytest.raises(driver.UsbInspectionRefusal, match="post_close_original_changed"):
        item.after_close()


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
