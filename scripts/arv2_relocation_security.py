"""Read-only, fd-bound Darwin security observations for scoped fresh use.

This is not a source-loader replacement or a historical security assertion.
Only accessible xattrs are visible, even with SHOWCOMPRESSION. Provenance is
an opaque byte fingerprint, never a decoded security or process-identity claim.

ABI: Apple's installed SDK sys/acl.h, sys/xattr.h and acl_get(3),
acl_to_text(3), listxattr(2), getxattr(2). Empty text/entry behavior also follows
apple-oss-distributions/Libc/posix1e/{acl_translate,acl_entry}.c. Checking for
an entry before converting text prevents a malformed entry skipped by the
renderer from being mistaken for an empty ACL.
"""
from __future__ import annotations

import ctypes
import errno
import hashlib
import os
import stat
import sys


ACL_TYPE_EXTENDED = 0x100
ACL_FIRST_ENTRY = 0
XATTR_SHOWCOMPRESSION = 0x20
MAX_NAMES_BYTES = 8192
MAX_VALUE_BYTES = 64 * 1024
ALLOWED_XATTRS = frozenset({b"com.apple.provenance"})
EMPTY_ACL_TEXT = b"!#acl 1\n"


class Refusal(Exception):
    """A bounded security observation is unavailable, unsafe or unstable."""

    def __init__(self, message):
        codes = {
            "Darwin security API required": "darwin_api_required",
            "Darwin security API unavailable": "darwin_api_unavailable",
            "held security metadata unavailable": "held_metadata_unavailable",
            "held security metadata unsupported": "held_metadata_unsupported",
            "extended ACL unavailable": "acl_unavailable",
            "extended ACL entry present": "acl_entry_present",
            "extended ACL entry census unavailable": "acl_entry_census_unavailable",
            "extended ACL text unavailable": "acl_text_unavailable",
            "extended ACL is not exactly empty and unflagged": "acl_not_empty_unflagged",
            "extended ACL working-storage release failed": "acl_storage_release_failed",
            "accessible xattr name census unavailable or oversized": "xattr_census_unavailable_or_oversized",
            "accessible xattr names are malformed": "xattr_names_malformed",
            "unapproved accessible xattr present": "xattr_unapproved",
            "valid held descriptor required": "held_descriptor_invalid",
            "accessible xattr value unavailable or oversized": "xattr_value_unavailable_or_oversized",
            "accessible xattr names changed during observation": "xattr_names_changed",
            "held security metadata changed during observation": "held_metadata_changed",
        }
        self.code = codes.get(message, "security_observation_refused")
        super().__init__(message if message in codes else self.code)


def _native():
    if sys.platform != "darwin":
        raise Refusal("Darwin security API required")
    try:
        native = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
        signatures = {
            "acl_get_fd_np": ([ctypes.c_int, ctypes.c_int], ctypes.c_void_p),
            "acl_get_entry": ([ctypes.c_void_p, ctypes.c_int,
                               ctypes.POINTER(ctypes.c_void_p)], ctypes.c_int),
            "acl_to_text": ([ctypes.c_void_p, ctypes.POINTER(ctypes.c_ssize_t)],
                            ctypes.c_void_p),
            "acl_free": ([ctypes.c_void_p], ctypes.c_int),
            "flistxattr": ([ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t,
                            ctypes.c_int], ctypes.c_ssize_t),
            "fgetxattr": ([ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p,
                           ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int],
                          ctypes.c_ssize_t),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(native, name)
            function.argtypes, function.restype = arguments, result
        return native
    except (OSError, AttributeError):
        raise Refusal("Darwin security API unavailable") from None


def _metadata(fd):
    try:
        info = os.fstat(fd)
        fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid",
                  "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns", "st_flags")
        values = tuple(getattr(info, field) for field in fields)
    except (OSError, AttributeError):
        raise Refusal("held security metadata unavailable") from None
    if (any(type(value) is not int or value < 0 for value in values)
            or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode))):
        raise Refusal("held security metadata unsupported")
    return values


def _require_empty_acl(native, fd):
    ctypes.set_errno(0)
    acl = native.acl_get_fd_np(fd, ACL_TYPE_EXTENDED)
    if not acl:
        # Apple's acl_file.c -> statx_np.c -> filesec.c reports the absent
        # FILESEC_ACL property as NULL/ENOENT for this held-fd operation.
        # It is not the pathname ENOENT case. No other error means absence.
        if ctypes.get_errno() == errno.ENOENT:
            return
        raise Refusal("extended ACL unavailable")
    text_pointer = None
    try:
        entry = ctypes.c_void_p()
        ctypes.set_errno(0)
        result = native.acl_get_entry(acl, ACL_FIRST_ENTRY, ctypes.byref(entry))
        if result == 0:
            raise Refusal("extended ACL entry present")
        # Darwin returns -1/EINVAL at the end, unlike POSIX's zero convention.
        if result != -1 or ctypes.get_errno() != errno.EINVAL:
            raise Refusal("extended ACL entry census unavailable")
        length = ctypes.c_ssize_t()
        text_pointer = native.acl_to_text(acl, ctypes.byref(length))
        if not text_pointer:
            raise Refusal("extended ACL text unavailable")
        if (length.value != len(EMPTY_ACL_TEXT)
                or ctypes.string_at(text_pointer, len(EMPTY_ACL_TEXT) + 1)
                != EMPTY_ACL_TEXT + b"\0"):
            raise Refusal("extended ACL is not exactly empty and unflagged")
    finally:
        free_failed = False
        if text_pointer:
            free_failed = native.acl_free(text_pointer) != 0
        if native.acl_free(acl) != 0:
            free_failed = True
        if free_failed:
            raise Refusal("extended ACL working-storage release failed")


def _names(native, fd):
    buffer = ctypes.create_string_buffer(MAX_NAMES_BYTES)
    count = native.flistxattr(fd, buffer, MAX_NAMES_BYTES, XATTR_SHOWCOMPRESSION)
    if type(count) is not int or not 0 <= count <= MAX_NAMES_BYTES:
        raise Refusal("accessible xattr name census unavailable or oversized")
    if count == 0:
        return ()
    raw = buffer.raw[:count]
    if not raw.endswith(b"\0"):
        raise Refusal("accessible xattr names are malformed")
    names = raw[:-1].split(b"\0")
    if any(not name or len(name) > 127 for name in names) or len(set(names)) != len(names):
        raise Refusal("accessible xattr names are malformed")
    if any(name not in ALLOWED_XATTRS for name in names):
        raise Refusal("unapproved accessible xattr present")
    return tuple(sorted(names))


def snapshot(fd):
    """Return only empty-ACL status and opaque accessible-xattr fingerprints.

    Reads each value once into a bounded memory buffer; no values are returned,
    logged or written. No retry, pathname lookup, attribute mutation or network
    API is present. Caller must pin the named leaf/ancestors and compare these
    snapshots around its own exact fresh-buffer consumption. This function's
    endpoint checks do not claim continuous stability or hidden-xattr coverage.
    """
    if type(fd) is not int or fd < 0:
        raise Refusal("valid held descriptor required")
    before = _metadata(fd)
    native = _native()
    _require_empty_acl(native, fd)
    names = _names(native, fd)
    values = {}
    remaining = MAX_VALUE_BYTES
    for name in names:
        buffer = ctypes.create_string_buffer(max(1, remaining))
        count = native.fgetxattr(fd, name, buffer, remaining, 0, XATTR_SHOWCOMPRESSION)
        if type(count) is not int or not 0 <= count <= remaining:
            raise Refusal("accessible xattr value unavailable or oversized")
        values[name.decode("ascii")] = {
            "size": count, "sha256": hashlib.sha256(buffer.raw[:count]).hexdigest()}
        remaining -= count
    if _names(native, fd) != names:
        raise Refusal("accessible xattr names changed during observation")
    _require_empty_acl(native, fd)
    if _metadata(fd) != before:
        raise Refusal("held security metadata changed during observation")
    return {"acl_empty": True, "xattrs": values}
