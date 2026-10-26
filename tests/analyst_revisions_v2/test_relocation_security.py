"""Synthetic-only native security-observer contracts; no private source access."""
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from types import SimpleNamespace

import pytest

from scripts import arv2_relocation_security as security


class Native:
    def __init__(self, *, names=b"", value=b"", acl_text=security.EMPTY_ACL_TEXT):
        self.names, self.value, self.acl_text = names, value, acl_text
        self.buffers, self.freed, self.calls = [], [], []
        self.entry_result, self.entry_errno = -1, errno.EINVAL
        self.acl_pointer = 1234
        self.acl_errno = 0
        self.text_null = False
        self.text_length = None
        self.free_result = 0
        self.list_results = []
        self.get_result = None
        self.after_get = lambda: None

    def acl_get_fd_np(self, fd, kind):
        self.calls.append(("acl", fd, kind))
        ctypes.set_errno(self.acl_errno)
        return self.acl_pointer

    def acl_get_entry(self, acl, first, entry):
        assert first == security.ACL_FIRST_ENTRY
        ctypes.set_errno(self.entry_errno)
        return self.entry_result

    def acl_to_text(self, acl, length):
        self.calls.append(("text",))
        if self.text_null:
            return None
        text = ctypes.create_string_buffer(self.acl_text)
        self.buffers.append(text)
        ctypes.cast(length, ctypes.POINTER(ctypes.c_ssize_t))[0] = (
            len(self.acl_text) if self.text_length is None else self.text_length)
        return ctypes.addressof(text)

    def acl_free(self, pointer):
        self.freed.append(pointer)
        return self.free_result

    def flistxattr(self, fd, buffer, size, options):
        self.calls.append(("list", fd, size, options))
        raw = self.list_results.pop(0) if self.list_results else self.names
        if isinstance(raw, int):
            return raw
        ctypes.memmove(buffer, raw, min(len(raw), size))
        return len(raw)

    def fgetxattr(self, fd, name, buffer, size, position, options):
        self.calls.append(("get", fd, name, size, position, options))
        ctypes.memmove(buffer, self.value, min(len(self.value), size))
        self.after_get()
        return len(self.value) if self.get_result is None else self.get_result


@pytest.fixture
def held(tmp_path):
    path = tmp_path / "synthetic-security"
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        yield fd
    finally:
        os.close(fd)


@pytest.fixture
def native(monkeypatch):
    fake = Native()
    monkeypatch.setattr(security, "_native", lambda: fake)
    original_fstat = os.fstat

    def synthetic_stat(fd):
        # These are fake-ABI tests, not native filesystem observations. Supply
        # the synthetic flags field on Linux while preserving all actual
        # test-owned descriptor fields and the production metadata checks.
        info = original_fstat(fd)
        values = {name: getattr(info, name) for name in (
            "st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
            "st_size", "st_mtime_ns", "st_ctime_ns")}
        return SimpleNamespace(**values, st_flags=getattr(info, "st_flags", 0))

    monkeypatch.setattr(security.os, "fstat", synthetic_stat)
    return fake


def test_empty_acl_and_no_accessible_xattrs(held, native):
    assert security.snapshot(held) == {"acl_empty": True, "xattrs": {}}
    assert len(native.freed) == 4
    assert all(call[-1] == security.XATTR_SHOWCOMPRESSION
               for call in native.calls if call[0] == "list")


def test_only_opaque_provenance_hash_and_size_returned(held, native):
    native.names, native.value = b"com.apple.provenance\0", b"synthetic-private-value"
    result = security.snapshot(held)
    assert result == {"acl_empty": True, "xattrs": {"com.apple.provenance": {
        "size": len(native.value), "sha256": hashlib.sha256(native.value).hexdigest()}}}
    assert native.value.decode() not in json.dumps(result)
    get = next(call for call in native.calls if call[0] == "get")
    assert get[-2:] == (0, security.XATTR_SHOWCOMPRESSION)
    assert len([call for call in native.calls if call[0] == "get"]) == 1


@pytest.mark.parametrize("value", [b"", b"v" * security.MAX_VALUE_BYTES])
def test_value_bounds_include_zero_and_exact_maximum(held, native, value):
    native.names, native.value = b"com.apple.provenance\0", value
    assert security.snapshot(held)["xattrs"]["com.apple.provenance"]["size"] == len(value)


@pytest.mark.parametrize("raw", [b"com.apple.macl\0", b"com.apple.decmpfs\0", b"unknown\0"])
def test_unknown_names_refuse_without_reading_values(held, native, raw):
    native.names = raw
    with pytest.raises(security.Refusal, match="unapproved"):
        security.snapshot(held)
    assert not any(call[0] == "get" for call in native.calls)


@pytest.mark.parametrize("raw", [b"missing-terminator", b"\0", b"com.apple.provenance\0\0",
                               b"com.apple.provenance\0com.apple.provenance\0", b"x" * 128 + b"\0"])
def test_malformed_names_refuse(held, native, raw):
    native.names = raw
    with pytest.raises(security.Refusal, match="malformed"):
        security.snapshot(held)


@pytest.mark.parametrize("count", [-1, security.MAX_NAMES_BYTES + 1])
def test_unavailable_or_oversized_name_census_refuses_without_retry(held, native, count):
    native.list_results = [count]
    with pytest.raises(security.Refusal, match="name census"):
        security.snapshot(held)
    assert len([call for call in native.calls if call[0] == "list"]) == 1


@pytest.mark.parametrize("count", [-1, security.MAX_VALUE_BYTES + 1])
def test_unavailable_or_oversized_value_refuses_without_retry(held, native, count):
    native.names, native.get_result = b"com.apple.provenance\0", count
    with pytest.raises(security.Refusal, match="value unavailable"):
        security.snapshot(held)
    assert len([call for call in native.calls if call[0] == "get"]) == 1


def test_accessible_names_change_refuses(held, native):
    native.list_results = [b"com.apple.provenance\0", b""]
    with pytest.raises(security.Refusal, match="names changed"):
        security.snapshot(held)


def test_nonempty_acl_refuses_before_text_name_resolution(held, native):
    native.entry_result = 0
    with pytest.raises(security.Refusal, match="entry present"):
        security.snapshot(held)
    assert native.freed == [native.acl_pointer]
    assert not any(call[0] == "text" for call in native.calls)


@pytest.mark.parametrize("result,error", [(-1, errno.EACCES), (1, 0), (-1, 0)])
def test_unknown_acl_entry_status_refuses(held, native, result, error):
    native.entry_result, native.entry_errno = result, error
    with pytest.raises(security.Refusal, match="census unavailable"):
        security.snapshot(held)


@pytest.mark.parametrize("text", [b"", b"!#acl 1", b"!#acl 1 no_inherit\n",
                                b"!#acl 1\nuser:synthetic:::allow:read\n", b"!#acl 1\0"])
def test_unknown_or_flagged_acl_text_refuses_and_releases(held, native, text):
    native.acl_text = text
    with pytest.raises(security.Refusal, match="not exactly empty"):
        security.snapshot(held)
    assert len(native.freed) == 2


@pytest.mark.parametrize("error", [0, errno.EACCES, errno.EBADF, errno.ENOTSUP, errno.EINVAL])
def test_unknown_acl_refuses(held, native, error):
    native.acl_pointer = None
    native.acl_errno = error
    with pytest.raises(security.Refusal, match="ACL unavailable"):
        security.snapshot(held)
    assert native.freed == []


def test_documented_native_absent_acl_is_not_an_unknown_error(held, native):
    native.acl_pointer, native.acl_errno = None, errno.ENOENT
    assert security.snapshot(held) == {"acl_empty": True, "xattrs": {}}
    assert native.freed == []


def test_stale_errno_cannot_disguise_unknown_acl(held, native):
    native.acl_pointer, native.acl_errno = None, 0
    ctypes.set_errno(errno.ENOENT)
    with pytest.raises(security.Refusal, match="ACL unavailable"):
        security.snapshot(held)


def test_missing_acl_text_refuses_and_releases_acl(held, native):
    native.text_null = True
    with pytest.raises(security.Refusal, match="text unavailable"):
        security.snapshot(held)
    assert native.freed == [native.acl_pointer]


def test_acl_free_failure_refuses(held, native):
    native.free_result = -1
    with pytest.raises(security.Refusal, match="release failed"):
        security.snapshot(held)
    assert len(native.freed) == 2


@pytest.mark.parametrize("field", ["st_dev", "st_ino", "st_mode", "st_uid", "st_gid",
                                 "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns", "st_flags"])
def test_each_held_metadata_drift_refuses(held, native, monkeypatch, field):
    info = os.fstat(held)
    values = {name: getattr(info, name) for name in (
        "st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size",
        "st_mtime_ns", "st_ctime_ns", "st_flags")}
    changed = {**values, field: values[field] + (1 if field != "st_mode" else 0o20)}
    iterator = iter([SimpleNamespace(**values), SimpleNamespace(**changed)])
    monkeypatch.setattr(security.os, "fstat", lambda _fd: next(iterator))
    with pytest.raises(security.Refusal, match="metadata changed"):
        security.snapshot(held)


def test_missing_flags_refuses(held, monkeypatch):
    monkeypatch.setattr(security.os, "fstat", lambda _fd: SimpleNamespace())
    with pytest.raises(security.Refusal, match="metadata unavailable"):
        security.snapshot(held)


@pytest.mark.parametrize("fd", [True, -1, "3", None])
def test_invalid_descriptors_refuse(fd):
    with pytest.raises(security.Refusal, match="valid held descriptor"):
        security.snapshot(fd)


def test_non_darwin_refuses(monkeypatch):
    monkeypatch.setattr(security.sys, "platform", "other")
    with pytest.raises(security.Refusal, match="Darwin security API required"):
        security._native()


@pytest.mark.parametrize("missing", [False, True])
def test_missing_native_library_or_symbol_refuses(monkeypatch, missing):
    monkeypatch.setattr(security.sys, "platform", "darwin")
    def library(*args, **kwargs):
        if not missing:
            raise OSError("synthetic API unavailable")
        return SimpleNamespace()
    monkeypatch.setattr(security.ctypes, "CDLL", library)
    with pytest.raises(security.Refusal, match="API unavailable"):
        security._native()


def test_native_empty_synthetic_file_only(held):
    # This is a fresh test-owned inode, never a retained source or real probe.
    if sys.platform != "darwin" or not hasattr(os.stat_result, "st_flags"):
        pytest.skip("native Darwin ABI test")
    result = security.snapshot(held)
    assert result["acl_empty"] is True
    assert set(result["xattrs"]) <= {"com.apple.provenance"}


def test_observer_has_no_mutation_or_network_calls():
    import ast
    tree = ast.parse(Path(security.__file__).read_text())
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not attributes & {"setxattr", "fsetxattr", "removexattr", "fremovexattr",
                             "chmod", "chown", "chflags", "acl_set_fd_np", "acl_set_file",
                             "connect", "socket", "requests", "urlopen", "unlink", "write"}


def test_refusal_codes_cannot_leak_unrecognized_messages():
    refusal = security.Refusal("unrecognized private value")
    assert refusal.code == str(refusal) == "security_observation_refused"
    assert security.Refusal("extended ACL unavailable").code == "acl_unavailable"
