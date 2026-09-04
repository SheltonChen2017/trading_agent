import ctypes
import dataclasses
import inspect
from collections.abc import Callable
from pathlib import Path

import pytest

import research.target_price_revisions.windows_acl as windows_acl


def _aces(*, directory: bool) -> tuple[windows_acl._RawAce, ...]:
    flags = windows_acl._DIRECTORY_ACE_FLAGS if directory else 0
    # Deliberately unsorted: the public evidence must normalize the order.
    return (
        windows_acl._RawAce(
            ace_type=windows_acl._ACCESS_ALLOWED_ACE_TYPE,
            ace_flags=flags,
            access_mask=windows_acl._READ_AND_EXECUTE_MASK,
            sid=windows_acl.USERS_SID,
        ),
        windows_acl._RawAce(
            ace_type=windows_acl._ACCESS_ALLOWED_ACE_TYPE,
            ace_flags=flags,
            access_mask=windows_acl._FULL_CONTROL_MASK,
            sid=windows_acl.SYSTEM_SID,
        ),
        windows_acl._RawAce(
            ace_type=windows_acl._ACCESS_ALLOWED_ACE_TYPE,
            ace_flags=flags,
            access_mask=windows_acl._FULL_CONTROL_MASK,
            sid=windows_acl.ADMINISTRATORS_SID,
        ),
    )


def _security(*, directory: bool) -> windows_acl._RawSecurityDescriptor:
    return windows_acl._RawSecurityDescriptor(
        owner_sid=windows_acl.ADMINISTRATORS_SID,
        dacl_present=True,
        dacl_defaulted=False,
        dacl_is_null=False,
        control=windows_acl._SE_DACL_PROTECTED,
        aces=_aces(directory=directory),
    )


@dataclasses.dataclass
class _FakeWindowsApi:
    target: Path
    directory: bool
    security: windows_acl._RawSecurityDescriptor
    resolved: Path | None = None
    reparse_paths: frozenset[Path] = frozenset()
    missing_paths: frozenset[Path] = frozenset()

    def resolve(self, path: Path) -> Path:
        return self.resolved if self.resolved is not None else path

    def file_attributes(self, path: Path) -> int:
        if path in self.missing_paths:
            raise windows_acl.WindowsAclError("synthetic missing path")
        attributes = 0
        if path != self.target or self.directory:
            attributes |= windows_acl._FILE_ATTRIBUTE_DIRECTORY
        if path in self.reparse_paths:
            attributes |= windows_acl._FILE_ATTRIBUTE_REPARSE_POINT
        return attributes

    def security_descriptor(
        self, path: Path
    ) -> windows_acl._RawSecurityDescriptor:
        assert path == (self.resolved if self.resolved is not None else self.target)
        return self.security


def _api(
    target: Path,
    *,
    directory: bool,
    security: windows_acl._RawSecurityDescriptor | None = None,
    **changes: object,
) -> _FakeWindowsApi:
    return _FakeWindowsApi(
        target=target,
        directory=directory,
        security=security or _security(directory=directory),
        **changes,
    )


@pytest.mark.parametrize("directory", [False, True])
def test_valid_acl_returns_sorted_immutable_evidence(
    tmp_path: Path, directory: bool
) -> None:
    target = (tmp_path / ("trust" if directory else "tpr_allowed_signers")).absolute()
    snapshot = windows_acl._validate_trust_path(
        target,
        expect_directory=directory,
        api=_api(target, directory=directory),
    )

    expected_flags = windows_acl._DIRECTORY_ACE_FLAGS if directory else 0
    assert snapshot == windows_acl.WindowsAclSnapshot(
        canonical_path=str(target),
        is_directory=directory,
        owner_sid=windows_acl.ADMINISTRATORS_SID,
        dacl_protected=True,
        aces=tuple(
            sorted(
                (
                    windows_acl.WindowsAce(
                        windows_acl.SYSTEM_SID,
                        windows_acl._FULL_CONTROL_MASK,
                        expected_flags,
                    ),
                    windows_acl.WindowsAce(
                        windows_acl.ADMINISTRATORS_SID,
                        windows_acl._FULL_CONTROL_MASK,
                        expected_flags,
                    ),
                    windows_acl.WindowsAce(
                        windows_acl.USERS_SID,
                        windows_acl._READ_AND_EXECUTE_MASK,
                        expected_flags,
                    ),
                )
            )
        ),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        snapshot.owner_sid = windows_acl.SYSTEM_SID


def test_public_api_is_narrow_and_uses_only_the_private_native_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    signature = inspect.signature(windows_acl.validate_trust_path)
    assert tuple(signature.parameters) == ("path", "expect_directory")
    assert (
        signature.parameters["expect_directory"].kind
        is inspect.Parameter.KEYWORD_ONLY
    )

    target = (tmp_path / "trust").absolute()
    fake = _api(target, directory=True)
    monkeypatch.setattr(windows_acl, "_load_native_api", lambda: fake)

    assert windows_acl.validate_trust_path(
        target, expect_directory=True
    ).canonical_path == str(target)


def test_native_adapter_refuses_non_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(windows_acl.os, "name", "posix")

    with pytest.raises(windows_acl.WindowsAclError, match="requires Windows"):
        windows_acl._CtypesWindowsApi()


@pytest.mark.parametrize(
    ("path_factory", "expected_directory"),
    [
        (lambda target: Path("relative-trust-path"), True),
        (lambda target: str(target), True),
    ],
)
def test_invalid_path_inputs_refuse(
    tmp_path: Path,
    path_factory: Callable[[Path], object],
    expected_directory: bool,
) -> None:
    target = (tmp_path / "trust").absolute()
    supplied = path_factory(target)
    with pytest.raises(windows_acl.WindowsAclError):
        windows_acl._validate_trust_path(
            supplied,
            expect_directory=expected_directory,
            api=_api(target, directory=True),
        )


def test_non_boolean_expected_type_refuses(tmp_path: Path) -> None:
    target = (tmp_path / "trust").absolute()
    with pytest.raises(windows_acl.WindowsAclError):
        windows_acl._validate_trust_path(
            target,
            expect_directory=1,
            api=_api(target, directory=True),
        )


@pytest.mark.parametrize("at_parent", [False, True])
def test_reparse_target_or_parent_refuses(tmp_path: Path, at_parent: bool) -> None:
    target = (tmp_path / "trust" / "tpr_allowed_signers").absolute()
    redirected = target.parent if at_parent else target
    with pytest.raises(windows_acl.WindowsAclError, match="reparse"):
        windows_acl._validate_trust_path(
            target,
            expect_directory=False,
            api=_api(
                target,
                directory=False,
                reparse_paths=frozenset({redirected}),
            ),
        )


@pytest.mark.parametrize("at_parent", [False, True])
def test_missing_target_or_parent_refuses(tmp_path: Path, at_parent: bool) -> None:
    target = (tmp_path / "trust" / "tpr_allowed_signers").absolute()
    missing = target.parent if at_parent else target
    with pytest.raises(windows_acl.WindowsAclError, match="missing"):
        windows_acl._validate_trust_path(
            target,
            expect_directory=False,
            api=_api(
                target,
                directory=False,
                missing_paths=frozenset({missing}),
            ),
        )


def test_noncanonical_resolved_path_refuses(tmp_path: Path) -> None:
    target = (tmp_path / "trust" / "tpr_allowed_signers").absolute()
    alternate = target.with_name("other_signers")
    with pytest.raises(windows_acl.WindowsAclError, match="canonical"):
        windows_acl._validate_trust_path(
            target,
            expect_directory=False,
            api=_api(
                target,
                directory=False,
                resolved=alternate,
            ),
        )


@pytest.mark.parametrize(
    ("directory", "expected_directory"),
    [(True, False), (False, True)],
)
def test_wrong_file_type_refuses(
    tmp_path: Path, directory: bool, expected_directory: bool
) -> None:
    target = (tmp_path / "trust-target").absolute()
    with pytest.raises(windows_acl.WindowsAclError, match="type"):
        windows_acl._validate_trust_path(
            target,
            expect_directory=expected_directory,
            api=_api(target, directory=directory),
        )


@pytest.mark.parametrize(
    "change",
    [
        {"owner_sid": windows_acl.USERS_SID},
        {"dacl_present": False},
        {"dacl_is_null": True},
        {"dacl_defaulted": True},
        {"control": 0},
    ],
)
def test_wrong_owner_or_dacl_state_refuses(
    tmp_path: Path, change: dict[str, object]
) -> None:
    target = (tmp_path / "trust").absolute()
    security = dataclasses.replace(_security(directory=True), **change)
    with pytest.raises(windows_acl.WindowsAclError):
        windows_acl._validate_trust_path(
            target,
            expect_directory=True,
            api=_api(target, directory=True, security=security),
        )


def _changed_aces(
    *,
    directory: bool,
    index: int | None = None,
    replacement: windows_acl._RawAce | None = None,
    append: windows_acl._RawAce | None = None,
    drop: int | None = None,
) -> tuple[windows_acl._RawAce, ...]:
    aces = list(_aces(directory=directory))
    if index is not None and replacement is not None:
        aces[index] = replacement
    if append is not None:
        aces.append(append)
    if drop is not None:
        aces.pop(drop)
    return tuple(aces)


def _ace_variants() -> tuple[tuple[windows_acl._RawAce, ...], ...]:
    valid = _aces(directory=True)
    users = valid[0]
    system = valid[1]
    return (
        _changed_aces(directory=True, drop=0),
        _changed_aces(directory=True, append=users),
        _changed_aces(
            directory=True,
            append=dataclasses.replace(users, sid="S-1-5-11"),
        ),
        _changed_aces(
            directory=True,
            index=0,
            replacement=dataclasses.replace(users, ace_type=1),
        ),
        _changed_aces(
            directory=True,
            index=0,
            replacement=dataclasses.replace(
                users,
                access_mask=windows_acl._READ_AND_EXECUTE_MASK | 0x00000002,
            ),
        ),
        _changed_aces(
            directory=True,
            index=1,
            replacement=dataclasses.replace(system, access_mask=0x001200A9),
        ),
        _changed_aces(
            directory=True,
            index=0,
            replacement=dataclasses.replace(users, ace_flags=0),
        ),
        _changed_aces(
            directory=True,
            index=0,
            replacement=dataclasses.replace(users, ace_flags=0x13),
        ),
    )


@pytest.mark.parametrize("aces", _ace_variants())
def test_missing_extra_duplicate_nonallow_or_unsafe_ace_refuses(
    tmp_path: Path, aces: tuple[windows_acl._RawAce, ...]
) -> None:
    target = (tmp_path / "trust").absolute()
    security = dataclasses.replace(_security(directory=True), aces=aces)
    with pytest.raises(windows_acl.WindowsAclError):
        windows_acl._validate_trust_path(
            target,
            expect_directory=True,
            api=_api(target, directory=True, security=security),
        )


def test_native_structure_offsets_match_access_allowed_ace_layout() -> None:
    assert ctypes.sizeof(windows_acl._AceHeader) == 4
    assert windows_acl._AccessAllowedAce.access_mask.offset == 4
    assert windows_acl._AccessAllowedAce.sid_start.offset == 8
    assert ctypes.sizeof(windows_acl._AccessAllowedAce) == 12
    assert ctypes.sizeof(windows_acl._SidHeader) == 8


@dataclasses.dataclass
class _NativeKernelFunctions:
    freed: list[int] = dataclasses.field(default_factory=list)

    def LocalFree(self, handle: ctypes.c_void_p) -> int:
        self.freed.append(int(handle.value or 0))
        return 0


@dataclasses.dataclass
class _NativeAclFunctions:
    buffer: ctypes.Array[ctypes.c_char]
    ace_offsets: tuple[int, ...]
    bytes_in_use: int
    sid_text_by_address: dict[int, str] = dataclasses.field(default_factory=dict)
    sid_size_by_address: dict[int, int] = dataclasses.field(default_factory=dict)
    sid_api_calls: int = 0
    convert_calls: int = 0

    @property
    def base(self) -> int:
        return ctypes.addressof(self.buffer)

    def GetAclInformation(
        self,
        dacl: ctypes.c_void_p,
        output: object,
        output_size: int,
        information_class: int,
    ) -> int:
        assert dacl.value == self.base
        assert output_size == ctypes.sizeof(windows_acl._AclSizeInformation)
        assert information_class == windows_acl._ACL_SIZE_INFORMATION_CLASS
        information = output._obj
        information.ace_count = len(self.ace_offsets)
        information.acl_bytes_in_use = self.bytes_in_use
        information.acl_bytes_free = 0
        return 1

    def GetAce(
        self,
        dacl: ctypes.c_void_p,
        index: int,
        output: object,
    ) -> int:
        assert dacl.value == self.base
        output._obj.value = self.base + self.ace_offsets[index]
        return 1

    def IsValidSid(self, sid: ctypes.c_void_p) -> int:
        self.sid_api_calls += 1
        return int(int(sid.value or 0) in self.sid_size_by_address)

    def GetLengthSid(self, sid: ctypes.c_void_p) -> int:
        self.sid_api_calls += 1
        return self.sid_size_by_address[int(sid.value or 0)]

    def ConvertSidToStringSidW(
        self,
        sid: ctypes.c_void_p,
        output: object,
    ) -> int:
        self.sid_api_calls += 1
        self.convert_calls += 1
        output._obj.value = self.sid_text_by_address[int(sid.value or 0)]
        return 1


def _unconfigured_native_api(
    *,
    advapi32: object,
    kernel32: object,
) -> windows_acl._CtypesWindowsApi:
    api = object.__new__(windows_acl._CtypesWindowsApi)
    api._advapi32 = advapi32
    api._kernel32 = kernel32
    return api


def _synthetic_allow_acl(
    *,
    ace_size: int,
    sub_authority_count: int,
    allocation_size: int | None = None,
) -> ctypes.Array[ctypes.c_char]:
    size = allocation_size or windows_acl._ACL_HEADER_SIZE + ace_size
    raw = bytearray(size)
    ace_start = windows_acl._ACL_HEADER_SIZE
    raw[ace_start] = windows_acl._ACCESS_ALLOWED_ACE_TYPE
    raw[ace_start + 1] = 0
    raw[ace_start + 2 : ace_start + 4] = ace_size.to_bytes(2, "little")
    if size >= ace_start + windows_acl._AccessAllowedAce.sid_start.offset:
        raw[ace_start + 4 : ace_start + 8] = (
            windows_acl._FULL_CONTROL_MASK.to_bytes(4, "little")
        )
    sid_start = ace_start + windows_acl._AccessAllowedAce.sid_start.offset
    if size > sid_start:
        raw[sid_start] = 1
    if size > sid_start + 1:
        raw[sid_start + 1] = sub_authority_count
    if size >= sid_start + windows_acl._SID_HEADER_SIZE:
        raw[sid_start + 7] = 5
    if size >= sid_start + windows_acl._SID_HEADER_SIZE + 4:
        raw[
            sid_start
            + windows_acl._SID_HEADER_SIZE : sid_start
            + windows_acl._SID_HEADER_SIZE
            + 4
        ] = (18).to_bytes(4, "little")
    return ctypes.create_string_buffer(bytes(raw), size)


def test_native_ace_parser_bounds_sid_before_native_sid_calls() -> None:
    cases = (
        # GetAce must return the next exact in-ACL address.
        (20, 1, 28, 32),
        # A declared ACE may not cross AclBytesInUse.
        (24, 1, 20, 8),
        # ACCESS_ALLOWED_ACE's four-byte SidStart placeholder is not a SID.
        (12, 0, 20, 8),
        # The SID header fits, but its declared subauthority does not.
        (16, 1, 24, 8),
    )
    for ace_size, sub_authorities, bytes_in_use, ace_offset in cases:
        buffer = _synthetic_allow_acl(
            ace_size=ace_size,
            sub_authority_count=sub_authorities,
            allocation_size=max(40, windows_acl._ACL_HEADER_SIZE + ace_size),
        )
        advapi32 = _NativeAclFunctions(
            buffer=buffer,
            ace_offsets=(ace_offset,),
            bytes_in_use=bytes_in_use,
        )
        api = _unconfigured_native_api(
            advapi32=advapi32,
            kernel32=_NativeKernelFunctions(),
        )

        with pytest.raises(windows_acl.WindowsAclError):
            api._aces(ctypes.c_void_p(advapi32.base))

        assert advapi32.sid_api_calls == 0


def test_native_ace_parser_normalizes_only_an_exact_bounded_sid() -> None:
    buffer = _synthetic_allow_acl(ace_size=20, sub_authority_count=1)
    sid_address = (
        ctypes.addressof(buffer)
        + windows_acl._ACL_HEADER_SIZE
        + windows_acl._AccessAllowedAce.sid_start.offset
    )
    advapi32 = _NativeAclFunctions(
        buffer=buffer,
        ace_offsets=(windows_acl._ACL_HEADER_SIZE,),
        bytes_in_use=ctypes.sizeof(buffer),
        sid_text_by_address={sid_address: windows_acl.SYSTEM_SID},
        sid_size_by_address={sid_address: 12},
    )
    kernel32 = _NativeKernelFunctions()
    api = _unconfigured_native_api(advapi32=advapi32, kernel32=kernel32)

    assert api._aces(ctypes.c_void_p(advapi32.base)) == (
        windows_acl._RawAce(
            ace_type=windows_acl._ACCESS_ALLOWED_ACE_TYPE,
            ace_flags=0,
            access_mask=windows_acl._FULL_CONTROL_MASK,
            sid=windows_acl.SYSTEM_SID,
        ),
    )
    assert advapi32.sid_api_calls == 3
    assert advapi32.convert_calls == 1
    assert len(kernel32.freed) == 1


def test_native_sid_length_mismatch_refuses_before_conversion() -> None:
    buffer = _synthetic_allow_acl(ace_size=20, sub_authority_count=1)
    sid_address = (
        ctypes.addressof(buffer)
        + windows_acl._ACL_HEADER_SIZE
        + windows_acl._AccessAllowedAce.sid_start.offset
    )
    advapi32 = _NativeAclFunctions(
        buffer=buffer,
        ace_offsets=(windows_acl._ACL_HEADER_SIZE,),
        bytes_in_use=ctypes.sizeof(buffer),
        sid_text_by_address={sid_address: windows_acl.SYSTEM_SID},
        sid_size_by_address={sid_address: 16},
    )
    kernel32 = _NativeKernelFunctions()
    api = _unconfigured_native_api(advapi32=advapi32, kernel32=kernel32)

    with pytest.raises(windows_acl.WindowsAclError, match="SID boundary"):
        api._aces(ctypes.c_void_p(advapi32.base))

    assert advapi32.sid_api_calls == 2
    assert advapi32.convert_calls == 0
    assert kernel32.freed == []


@dataclasses.dataclass
class _NativeDescriptorFunctions:
    dacl_address: int
    descriptor_address: int
    fail_control: bool = False

    def GetNamedSecurityInfoW(self, *arguments: object) -> int:
        arguments[3]._obj.value = 0x1000
        arguments[5]._obj.value = self.dacl_address
        arguments[7]._obj.value = self.descriptor_address
        return 0

    def GetSecurityDescriptorControl(
        self,
        descriptor: ctypes.c_void_p,
        control: object,
        revision: object,
    ) -> int:
        assert descriptor.value == self.descriptor_address
        if self.fail_control:
            return 0
        control._obj.value = windows_acl._SE_DACL_PROTECTED
        revision._obj.value = 1
        return 1

    def GetSecurityDescriptorDacl(
        self,
        descriptor: ctypes.c_void_p,
        present: object,
        dacl: object,
        defaulted: object,
    ) -> int:
        assert descriptor.value == self.descriptor_address
        present._obj.value = 1
        dacl._obj.value = self.dacl_address
        defaulted._obj.value = 0
        return 1


@pytest.mark.parametrize("fail_control", [False, True])
def test_native_security_descriptor_is_freed_on_success_and_failure(
    fail_control: bool,
) -> None:
    advapi32 = _NativeDescriptorFunctions(
        dacl_address=0x2000,
        descriptor_address=0x3000,
        fail_control=fail_control,
    )
    kernel32 = _NativeKernelFunctions()
    api = _unconfigured_native_api(advapi32=advapi32, kernel32=kernel32)
    api._sid_text = lambda sid: windows_acl.ADMINISTRATORS_SID
    api._aces = lambda dacl: ()

    if fail_control:
        with pytest.raises(windows_acl.WindowsAclError, match="controls"):
            api.security_descriptor(Path(r"C:\synthetic"))
    else:
        assert api.security_descriptor(Path(r"C:\synthetic")) == (
            windows_acl._RawSecurityDescriptor(
                owner_sid=windows_acl.ADMINISTRATORS_SID,
                dacl_present=True,
                dacl_defaulted=False,
                dacl_is_null=False,
                control=windows_acl._SE_DACL_PROTECTED,
                aces=(),
            )
        )
    assert kernel32.freed == [0x3000]
