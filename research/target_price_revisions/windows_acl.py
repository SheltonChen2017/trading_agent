"""Fail-closed Windows ACL inspection for the external TPR trust root.

The caller owns the exact path policy.  This module only proves that the
supplied directory or file has the one approved Windows custody shape and
that no component of its existing path is a reparse point.  It never creates,
repairs, or otherwise mutates filesystem state.
"""

from __future__ import annotations

import ctypes
import dataclasses
import os
from pathlib import Path
from typing import Protocol

from ctypes import wintypes


# ``ctypes.wintypes`` mirrors the host C ABI and is therefore not fixed-width
# when this source is merely imported off Windows.  Keep all structures whose
# layout we inspect pinned to the Win32 ABI even though native construction
# still refuses on non-Windows hosts.
_WIN_BOOL = ctypes.c_int32
_WIN_DWORD = ctypes.c_uint32
_WIN_WORD = ctypes.c_uint16


class WindowsAclError(ValueError):
    """The requested trust path does not have the required custody shape."""


SYSTEM_SID = "S-1-5-18"
ADMINISTRATORS_SID = "S-1-5-32-544"
USERS_SID = "S-1-5-32-545"

_FILE_ATTRIBUTE_DIRECTORY = 0x00000010
_FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
_INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF

_ACCESS_ALLOWED_ACE_TYPE = 0x00
_OBJECT_INHERIT_ACE = 0x01
_CONTAINER_INHERIT_ACE = 0x02
_DIRECTORY_ACE_FLAGS = _OBJECT_INHERIT_ACE | _CONTAINER_INHERIT_ACE
_FILE_ACE_FLAGS = 0x00

# Canonical masks produced by an explicit Windows Full Control / Read & Execute
# DACL.  Requiring the masks exactly also rejects write, delete, ownership, and
# ACL-control rights for BUILTIN\Users.
_FULL_CONTROL_MASK = 0x001F01FF
_READ_AND_EXECUTE_MASK = 0x001200A9

_SE_FILE_OBJECT = 1
_OWNER_SECURITY_INFORMATION = 0x00000001
_DACL_SECURITY_INFORMATION = 0x00000004
_SE_DACL_PROTECTED = 0x1000
_ACL_SIZE_INFORMATION_CLASS = 2
_ACL_HEADER_SIZE = 8
_SID_HEADER_SIZE = 8


@dataclasses.dataclass(frozen=True, order=True)
class WindowsAce:
    """One normalized direct allow ACE in a validated trust-path DACL."""

    sid: str
    access_mask: int
    inheritance_flags: int


@dataclasses.dataclass(frozen=True)
class WindowsAclSnapshot:
    """Immutable, non-secret evidence returned for a validated path."""

    canonical_path: str
    is_directory: bool
    owner_sid: str
    dacl_protected: bool
    aces: tuple[WindowsAce, ...]


@dataclasses.dataclass(frozen=True)
class _RawAce:
    ace_type: int
    ace_flags: int
    access_mask: int
    sid: str


@dataclasses.dataclass(frozen=True)
class _RawSecurityDescriptor:
    owner_sid: str
    dacl_present: bool
    dacl_defaulted: bool
    dacl_is_null: bool
    control: int
    aces: tuple[_RawAce, ...]


class _WindowsApi(Protocol):
    def resolve(self, path: Path) -> Path: ...

    def file_attributes(self, path: Path) -> int: ...

    def security_descriptor(self, path: Path) -> _RawSecurityDescriptor: ...


class _AceHeader(ctypes.Structure):
    _fields_ = [
        ("ace_type", ctypes.c_ubyte),
        ("ace_flags", ctypes.c_ubyte),
        ("ace_size", _WIN_WORD),
    ]


class _AccessAllowedAce(ctypes.Structure):
    _fields_ = [
        ("header", _AceHeader),
        ("access_mask", _WIN_DWORD),
        ("sid_start", _WIN_DWORD),
    ]


class _AclSizeInformation(ctypes.Structure):
    _fields_ = [
        ("ace_count", _WIN_DWORD),
        ("acl_bytes_in_use", _WIN_DWORD),
        ("acl_bytes_free", _WIN_DWORD),
    ]


class _SidHeader(ctypes.Structure):
    _fields_ = [
        ("revision", ctypes.c_ubyte),
        ("sub_authority_count", ctypes.c_ubyte),
        ("identifier_authority", ctypes.c_ubyte * 6),
    ]


class _CtypesWindowsApi:
    """Narrow native adapter; construction itself refuses off Windows."""

    def __init__(self) -> None:
        if os.name != "nt" or not hasattr(ctypes, "WinDLL"):
            raise WindowsAclError("Windows ACL validation requires Windows")
        try:
            self._advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
            self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        except (OSError, AttributeError) as exc:
            raise WindowsAclError("Windows security APIs are unavailable") from exc
        self._configure_signatures()

    def _configure_signatures(self) -> None:
        self._kernel32.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
        self._kernel32.GetFileAttributesW.restype = _WIN_DWORD
        self._kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
        self._kernel32.LocalFree.restype = wintypes.HLOCAL

        self._advapi32.GetNamedSecurityInfoW.argtypes = [
            wintypes.LPWSTR,
            _WIN_DWORD,
            _WIN_DWORD,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self._advapi32.GetNamedSecurityInfoW.restype = _WIN_DWORD
        self._advapi32.GetSecurityDescriptorControl.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_WIN_WORD),
            ctypes.POINTER(_WIN_DWORD),
        ]
        self._advapi32.GetSecurityDescriptorControl.restype = _WIN_BOOL
        self._advapi32.GetSecurityDescriptorDacl.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_WIN_BOOL),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(_WIN_BOOL),
        ]
        self._advapi32.GetSecurityDescriptorDacl.restype = _WIN_BOOL
        self._advapi32.GetAclInformation.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            _WIN_DWORD,
            _WIN_DWORD,
        ]
        self._advapi32.GetAclInformation.restype = _WIN_BOOL
        self._advapi32.GetAce.argtypes = [
            ctypes.c_void_p,
            _WIN_DWORD,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self._advapi32.GetAce.restype = _WIN_BOOL
        self._advapi32.IsValidSid.argtypes = [ctypes.c_void_p]
        self._advapi32.IsValidSid.restype = _WIN_BOOL
        self._advapi32.GetLengthSid.argtypes = [ctypes.c_void_p]
        self._advapi32.GetLengthSid.restype = _WIN_DWORD
        self._advapi32.ConvertSidToStringSidW.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(wintypes.LPWSTR),
        ]
        self._advapi32.ConvertSidToStringSidW.restype = _WIN_BOOL

    def resolve(self, path: Path) -> Path:
        try:
            return path.resolve(strict=True)
        except OSError as exc:
            raise WindowsAclError("trust path is absent or cannot be resolved") from exc

    def file_attributes(self, path: Path) -> int:
        ctypes.set_last_error(0)
        attributes = int(self._kernel32.GetFileAttributesW(str(path)))
        if attributes == _INVALID_FILE_ATTRIBUTES:
            error = ctypes.get_last_error()
            raise WindowsAclError(
                f"trust path attributes are unavailable (Win32 error {error})"
            )
        return attributes

    def _sid_text(
        self,
        sid: ctypes.c_void_p,
        *,
        expected_size: int | None = None,
    ) -> str:
        if not sid or not self._advapi32.IsValidSid(sid):
            raise WindowsAclError("trust path ACL contains an invalid SID")
        sid_size = int(self._advapi32.GetLengthSid(sid))
        if sid_size <= 0 or (
            expected_size is not None and sid_size != expected_size
        ):
            raise WindowsAclError("trust path ACL contains a malformed SID boundary")
        rendered = wintypes.LPWSTR()
        if not self._advapi32.ConvertSidToStringSidW(sid, ctypes.byref(rendered)):
            raise WindowsAclError("trust path SID cannot be normalized")
        try:
            if not rendered.value:
                raise WindowsAclError("trust path SID normalized to empty text")
            return rendered.value
        finally:
            self._kernel32.LocalFree(
                wintypes.HLOCAL(ctypes.cast(rendered, ctypes.c_void_p).value)
            )

    def _aces(self, dacl: ctypes.c_void_p) -> tuple[_RawAce, ...]:
        if not dacl.value:
            raise WindowsAclError("trust path DACL pointer is null")
        information = _AclSizeInformation()
        if not self._advapi32.GetAclInformation(
            dacl,
            ctypes.byref(information),
            ctypes.sizeof(information),
            _ACL_SIZE_INFORMATION_CLASS,
        ):
            raise WindowsAclError("trust path DACL metadata is unavailable")
        ace_count = int(information.ace_count)
        bytes_in_use = int(information.acl_bytes_in_use)
        if bytes_in_use < _ACL_HEADER_SIZE or ace_count > (
            bytes_in_use - _ACL_HEADER_SIZE
        ) // ctypes.sizeof(_AceHeader):
            raise WindowsAclError("trust path DACL size metadata is malformed")

        acl_start = int(dacl.value)
        acl_end = acl_start + bytes_in_use
        expected_ace_start = acl_start + _ACL_HEADER_SIZE
        result: list[_RawAce] = []
        for index in range(ace_count):
            ace_pointer = ctypes.c_void_p()
            if not self._advapi32.GetAce(dacl, index, ctypes.byref(ace_pointer)):
                raise WindowsAclError("trust path ACE is unavailable")
            ace_start = int(ace_pointer.value or 0)
            if (
                ace_start != expected_ace_start
                or acl_end - ace_start < ctypes.sizeof(_AceHeader)
            ):
                raise WindowsAclError("trust path DACL contains an out-of-bounds ACE")
            header = _AceHeader.from_address(ace_start)
            ace_size = int(header.ace_size)
            if (
                ace_size < ctypes.sizeof(_AceHeader)
                or ace_size % 4 != 0
                or ace_size > acl_end - ace_start
            ):
                raise WindowsAclError("trust path DACL contains a truncated ACE")
            expected_ace_start = ace_start + ace_size
            if header.ace_type != _ACCESS_ALLOWED_ACE_TYPE:
                result.append(
                    _RawAce(
                        ace_type=int(header.ace_type),
                        ace_flags=int(header.ace_flags),
                        access_mask=0,
                        sid="",
                    )
                )
                continue
            sid_offset = _AccessAllowedAce.sid_start.offset
            if ace_size < sid_offset + _SID_HEADER_SIZE:
                raise WindowsAclError("trust path DACL contains a truncated allow ACE")
            allow = _AccessAllowedAce.from_address(ace_start)
            sid_address = ace_start + sid_offset
            sid_header = _SidHeader.from_address(sid_address)
            sid_size = _SID_HEADER_SIZE + 4 * int(sid_header.sub_authority_count)
            if sid_size != ace_size - sid_offset:
                raise WindowsAclError(
                    "trust path ACL contains a malformed SID boundary"
                )
            result.append(
                _RawAce(
                    ace_type=int(header.ace_type),
                    ace_flags=int(header.ace_flags),
                    access_mask=int(allow.access_mask),
                    sid=self._sid_text(
                        ctypes.c_void_p(sid_address),
                        expected_size=sid_size,
                    ),
                )
            )
        if expected_ace_start != acl_end:
            raise WindowsAclError("trust path DACL contains unaccounted bytes")
        return tuple(result)

    def security_descriptor(self, path: Path) -> _RawSecurityDescriptor:
        owner = ctypes.c_void_p()
        returned_dacl = ctypes.c_void_p()
        descriptor = ctypes.c_void_p()
        result = self._advapi32.GetNamedSecurityInfoW(
            str(path),
            _SE_FILE_OBJECT,
            _OWNER_SECURITY_INFORMATION | _DACL_SECURITY_INFORMATION,
            ctypes.byref(owner),
            None,
            ctypes.byref(returned_dacl),
            None,
            ctypes.byref(descriptor),
        )
        if result != 0 or not descriptor.value:
            raise WindowsAclError(
                f"trust path security descriptor is unavailable (Win32 error {result})"
            )
        try:
            control = _WIN_WORD()
            revision = _WIN_DWORD()
            if not self._advapi32.GetSecurityDescriptorControl(
                descriptor, ctypes.byref(control), ctypes.byref(revision)
            ):
                raise WindowsAclError("trust path security controls are unavailable")

            dacl_present = _WIN_BOOL()
            dacl = ctypes.c_void_p()
            dacl_defaulted = _WIN_BOOL()
            if not self._advapi32.GetSecurityDescriptorDacl(
                descriptor,
                ctypes.byref(dacl_present),
                ctypes.byref(dacl),
                ctypes.byref(dacl_defaulted),
            ):
                raise WindowsAclError("trust path DACL is unavailable")
            if returned_dacl.value != dacl.value:
                raise WindowsAclError("trust path DACL pointers disagree")
            return _RawSecurityDescriptor(
                owner_sid=self._sid_text(owner),
                dacl_present=bool(dacl_present.value),
                dacl_defaulted=bool(dacl_defaulted.value),
                dacl_is_null=not bool(dacl.value),
                control=int(control.value),
                aces=() if not dacl.value else self._aces(dacl),
            )
        finally:
            self._kernel32.LocalFree(wintypes.HLOCAL(descriptor.value))


def _load_native_api() -> _WindowsApi:
    return _CtypesWindowsApi()


def _same_canonical_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left)) == os.path.normcase(str(right))


def _validate_trust_path(
    path: Path,
    *,
    expect_directory: bool,
    api: _WindowsApi,
) -> WindowsAclSnapshot:
    if not isinstance(path, Path) or type(expect_directory) is not bool:
        raise WindowsAclError("trust path and expected type are invalid")
    if not path.is_absolute():
        raise WindowsAclError("trust path must be absolute")

    absolute = Path(os.path.abspath(path))
    for component in (absolute, *absolute.parents):
        attributes = api.file_attributes(component)
        if attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
            raise WindowsAclError("trust path and ancestors must not be reparse points")

    resolved = api.resolve(absolute)
    if not _same_canonical_path(absolute, resolved):
        raise WindowsAclError("trust path must use one canonical unredirected spelling")
    attributes = api.file_attributes(resolved)
    is_directory = bool(attributes & _FILE_ATTRIBUTE_DIRECTORY)
    if is_directory != expect_directory:
        raise WindowsAclError("trust path type does not match its custody contract")

    security = api.security_descriptor(resolved)
    if security.owner_sid != ADMINISTRATORS_SID:
        raise WindowsAclError("trust path owner must be BUILTIN\\Administrators")
    if not security.dacl_present or security.dacl_is_null:
        raise WindowsAclError("trust path must have a present non-null DACL")
    if security.dacl_defaulted:
        raise WindowsAclError("trust path DACL must not be defaulted")
    if not security.control & _SE_DACL_PROTECTED:
        raise WindowsAclError("trust path DACL must be protected from inheritance")

    expected_flags = _DIRECTORY_ACE_FLAGS if is_directory else _FILE_ACE_FLAGS
    expected = {
        SYSTEM_SID: _FULL_CONTROL_MASK,
        ADMINISTRATORS_SID: _FULL_CONTROL_MASK,
        USERS_SID: _READ_AND_EXECUTE_MASK,
    }
    normalized: list[WindowsAce] = []
    seen: set[str] = set()
    for ace in security.aces:
        if ace.ace_type != _ACCESS_ALLOWED_ACE_TYPE:
            raise WindowsAclError("trust path DACL contains a non-allow ACE")
        if ace.sid not in expected or ace.sid in seen:
            raise WindowsAclError("trust path DACL contains an extra or duplicate ACE")
        if ace.ace_flags != expected_flags:
            raise WindowsAclError("trust path ACE inheritance flags are not exact")
        if ace.access_mask != expected[ace.sid]:
            raise WindowsAclError("trust path ACE rights are not exact")
        seen.add(ace.sid)
        normalized.append(
            WindowsAce(
                sid=ace.sid,
                access_mask=ace.access_mask,
                inheritance_flags=ace.ace_flags,
            )
        )
    if seen != set(expected):
        raise WindowsAclError("trust path DACL is missing a required ACE")

    return WindowsAclSnapshot(
        canonical_path=str(resolved),
        is_directory=is_directory,
        owner_sid=security.owner_sid,
        dacl_protected=True,
        aces=tuple(sorted(normalized)),
    )


def validate_trust_path(
    path: Path,
    *,
    expect_directory: bool,
) -> WindowsAclSnapshot:
    """Return immutable ACL evidence or refuse without changing the path."""

    return _validate_trust_path(
        path,
        expect_directory=expect_directory,
        api=_load_native_api(),
    )
