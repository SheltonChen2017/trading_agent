"""Non-self-mintable owner signature trust roots for ARV2 QC actions.

The reviewed positive-path registry in this module pins the owner's dedicated
ARV2 Ed25519 public key.  Merely supplying another public key, an
``allowed_signers`` file, a signature, canonical JSON, or a content hash cannot
open a gate.

Production code in this module never reads or creates a private key and never
signs.  It verifies a detached OpenSSH signature over the exact caller-supplied
authority bytes with the root-owned ``/usr/bin/ssh-keygen`` executable.  Each
gate has a distinct fixed SSH signature namespace, so a valid signature for
one gate cannot authorize any other gate.
"""
from __future__ import annotations

import base64
import binascii
import dataclasses
import hashlib
import os
import re
import signal
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from types import MappingProxyType


class OwnerSignatureAuthorityError(ValueError):
    """A reviewed signer, detached signature, or authority binding is invalid."""


SCHEMA = "arv2-owner-signature-authority-v1"
PRINCIPAL = "arv2-owner"
FORMAL_EXECUTION_PURPOSE = "formal_qc_execution"
FORMAL_RESULT_READ_PURPOSE = "formal_qc_result_read"
PREOPEN_EXECUTION_PURPOSE = "preopen_qc_execution"
PREOPEN_ACQUISITION_REVIEW_PURPOSE = "preopen_control_acquisition_review"
PRODUCTION_EVIDENCE_REVIEW_PURPOSE = "production_evidence_review"
POWER_CALIBRATION_EXECUTION_PURPOSE = "power_calibration_qc_execution"
PURPOSE_NAMESPACES = MappingProxyType(
    {
        FORMAL_EXECUTION_PURPOSE: "arv2-formal-qc-execution-v1",
        FORMAL_RESULT_READ_PURPOSE: "arv2-formal-qc-result-read-v1",
        PREOPEN_EXECUTION_PURPOSE: "arv2-preopen-qc-execution-v1",
        PREOPEN_ACQUISITION_REVIEW_PURPOSE: (
            "arv2-preopen-control-acquisition-review-v1"
        ),
        PRODUCTION_EVIDENCE_REVIEW_PURPOSE: (
            "arv2-production-evidence-review-v1"
        ),
        POWER_CALIBRATION_EXECUTION_PURPOSE: (
            "arv2-power-calibration-qc-execution-v1"
        ),
    }
)
TRUSTED_SSH_KEYGEN_PATH = Path("/usr/bin/ssh-keygen")
MAX_AUTHORITY_PAYLOAD_BYTES = 1_048_576
MAX_ALLOWED_SIGNERS_BYTES = 8_192
MAX_SIGNATURE_BYTES = 16_384
VERIFY_TIMEOUT_SECONDS = 10

_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_KEY_ID = re.compile(r"arv2-owner-ed25519-[0-9a-f]{16}\Z")
_SSH_ED25519_PREFIX = b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20"
_SIGNATURE_BEGIN = b"-----BEGIN SSH SIGNATURE-----\n"
_SIGNATURE_END = b"-----END SSH SIGNATURE-----\n"


@dataclasses.dataclass(frozen=True, slots=True)
class _ReviewedOwnerPublicKey:
    """One public key installed by an independently reviewed code change.

    This type is private deliberately.  Public callers cannot supply a key pin
    to any production loader.  The private constructor is used only by the
    crypto fixture tests in this lane; production always reads the immutable
    registry immediately below.
    """

    key_id: str
    public_key_base64: str
    purposes: tuple[str, ...]


# Security boundary: installing a key requires editing and independently
# reviewing this exact source file.  Do not populate this registry from an
# environment variable, CLI flag, file, network response, or caller argument.
# Owner-rotated 2026-09-13 after the original key's passphrase was lost.  This
# is public verification material only; the
# private key and its passphrase are neither read nor stored by this lane.
_REVIEWED_OWNER_PUBLIC_KEYS: tuple[_ReviewedOwnerPublicKey, ...] = (
    _ReviewedOwnerPublicKey(
        key_id="arv2-owner-ed25519-4ba35c490d6bd18d",
        public_key_base64=(
            "AAAAC3NzaC1lZDI1NTE5AAAAIMscSpkCpc6Wb6zXpZjYm7CIXgtH7H0cq4Yryfcvacji"
        ),
        purposes=(
            FORMAL_EXECUTION_PURPOSE,
            FORMAL_RESULT_READ_PURPOSE,
            PREOPEN_EXECUTION_PURPOSE,
            PREOPEN_ACQUISITION_REVIEW_PURPOSE,
            PRODUCTION_EVIDENCE_REVIEW_PURPOSE,
            POWER_CALIBRATION_EXECUTION_PURPOSE,
        ),
    ),
)


@dataclasses.dataclass(frozen=True, slots=True)
class _FileSnapshot:
    path: Path
    content_sha256: str
    byte_count: int
    device: int
    inode: int
    owner_uid: int
    mode: int
    link_count: int
    modified_ns: int
    changed_ns: int
    _content: bytes = dataclasses.field(repr=False)


_VerifierPathSnapshot = tuple[str, int, int, int, int, int, int, int, int]
_VerifierSnapshot = tuple[
    tuple[tuple[object, ...], ...],
    _VerifierPathSnapshot,
]


@dataclasses.dataclass(frozen=True, slots=True)
class OwnerSignatureAuthority:
    authority_id: str
    authority_sha256: str
    schema: str
    purpose: str
    namespace: str
    principal: str
    reviewed_key_id: str
    public_key_blob_sha256: str
    authority_payload_sha256: str
    authority_payload_byte_count: int
    allowed_signers_path: str
    allowed_signers_sha256: str
    allowed_signers_byte_count: int
    signature_path: str
    signature_sha256: str
    signature_byte_count: int
    verifier_path: str
    _authority_payload: bytes = dataclasses.field(repr=False)
    _allowed_signers_snapshot: tuple[object, ...] = dataclasses.field(repr=False)
    _signature_snapshot: tuple[object, ...] = dataclasses.field(repr=False)
    _verifier_snapshot: _VerifierSnapshot = dataclasses.field(repr=False)


def _canonical_identity_bytes(value: dict[str, object]) -> bytes:
    """Encode the narrow scalar identity without importing a wider JSON helper."""

    import json

    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")


def _require_exact_path(path: Path, name: str) -> Path:
    if type(path) is not type(Path()) or not path.is_absolute() or ".." in path.parts:
        raise OwnerSignatureAuthorityError(f"{name} must be an absolute exact Path")
    current = Path(path.anchor)
    try:
        for part in path.parts[1:]:
            current = current / part
            if stat.S_ISLNK(os.lstat(current).st_mode):
                raise OwnerSignatureAuthorityError(
                    f"{name} and every parent must be nonsymlink"
                )
    except OwnerSignatureAuthorityError:
        raise
    except OSError as exc:
        raise OwnerSignatureAuthorityError(f"{name} is unavailable") from exc
    return path


def _read_fd_twice(descriptor: int, maximum_bytes: int) -> tuple[bytes, os.stat_result]:
    def read_once() -> bytes:
        chunks: list[bytes] = []
        remaining = maximum_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    before = os.fstat(descriptor)
    first = read_once()
    middle = os.fstat(descriptor)
    os.lseek(descriptor, 0, os.SEEK_SET)
    second = read_once()
    after = os.fstat(descriptor)
    stable_fields = (
        "st_dev", "st_ino", "st_uid", "st_mode", "st_nlink", "st_size",
        "st_mtime_ns", "st_ctime_ns",
    )
    if first != second or any(
        getattr(before, field) != getattr(middle, field)
        or getattr(before, field) != getattr(after, field)
        for field in stable_fields
    ):
        raise OwnerSignatureAuthorityError("private signature control changed while read")
    return first, before


def _read_private_stable_file(
    path: Path,
    *,
    maximum_bytes: int,
    name: str,
    _require_path: object = _require_exact_path,
    _read_twice: object = _read_fd_twice,
    _sha256: object = hashlib.sha256,
    _snapshot_type: type[_FileSnapshot] = _FileSnapshot,
) -> _FileSnapshot:
    exact = _require_path(path, name)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(exact, flags)
    except OSError as exc:
        raise OwnerSignatureAuthorityError(f"{name} is unavailable") from exc
    try:
        payload, observed = _read_twice(descriptor, maximum_bytes)
    finally:
        os.close(descriptor)
    if (
        not stat.S_ISREG(observed.st_mode)
        or stat.S_IMODE(observed.st_mode) != 0o600
        or observed.st_uid != os.getuid()
        or observed.st_nlink != 1
        or observed.st_size != len(payload)
        or not 0 < len(payload) <= maximum_bytes
    ):
        raise OwnerSignatureAuthorityError(
            f"{name} must be a bounded, owner-owned, mode-0600, single-link regular file"
        )
    return _snapshot_type(
        path=exact,
        content_sha256=_sha256(payload).hexdigest(),
        byte_count=len(payload),
        device=observed.st_dev,
        inode=observed.st_ino,
        owner_uid=observed.st_uid,
        mode=stat.S_IMODE(observed.st_mode),
        link_count=observed.st_nlink,
        modified_ns=observed.st_mtime_ns,
        changed_ns=observed.st_ctime_ns,
        _content=payload,
    )


def _snapshot_verifier_path(
    path: str,
) -> _VerifierPathSnapshot:
    """Snapshot one explicit path; production never exposes this choice."""

    if type(path) is not str or not path.startswith("/"):
        raise OwnerSignatureAuthorityError(
            "trusted ssh-keygen verifier path is invalid"
        )
    try:
        observed = os.lstat(path)
    except OSError as exc:
        raise OwnerSignatureAuthorityError("trusted ssh-keygen verifier is unavailable") from exc
    if (
        not stat.S_ISREG(observed.st_mode)
        or observed.st_uid != 0
        or observed.st_nlink < 1
        or stat.S_IMODE(observed.st_mode) & 0o022
        or not stat.S_IMODE(observed.st_mode) & 0o111
        or observed.st_size <= 0
    ):
        raise OwnerSignatureAuthorityError(
            "trusted ssh-keygen verifier is not a root-owned nonwritable executable"
        )
    return (
        path,
        observed.st_dev,
        observed.st_ino,
        observed.st_uid,
        stat.S_IMODE(observed.st_mode),
        observed.st_size,
        observed.st_nlink,
        observed.st_mtime_ns,
        observed.st_ctime_ns,
    )


def _snapshot_trusted_verifier() -> _VerifierPathSnapshot:
    """Snapshot the reviewed path for direct diagnostics and fixture tests."""

    return _snapshot_verifier_path("/usr/bin/ssh-keygen")


def _parse_ed25519_blob(public_key_base64: str) -> bytes:
    if type(public_key_base64) is not str or not public_key_base64:
        raise OwnerSignatureAuthorityError("reviewed owner public key is invalid")
    try:
        blob = base64.b64decode(public_key_base64.encode("ascii"), validate=True)
    except (UnicodeError, ValueError, binascii.Error) as exc:
        raise OwnerSignatureAuthorityError("reviewed owner public key is invalid") from exc
    if len(blob) != len(_SSH_ED25519_PREFIX) + 32 or not blob.startswith(
        _SSH_ED25519_PREFIX
    ) or base64.b64encode(blob).decode("ascii") != public_key_base64:
        raise OwnerSignatureAuthorityError("reviewed owner key is not exact Ed25519")
    return blob


def _validate_reviewed_pin(
    pin: _ReviewedOwnerPublicKey,
    *,
    _key_id_pattern: re.Pattern[str] = _KEY_ID,
    _parse_public_blob: object = _parse_ed25519_blob,
    _purpose_namespaces: object = PURPOSE_NAMESPACES,
    _sha256: object = hashlib.sha256,
    _principal: str = PRINCIPAL,
) -> tuple[bytes, bytes]:
    if (
        type(pin) is not _ReviewedOwnerPublicKey
        or _key_id_pattern.fullmatch(pin.key_id) is None
        or type(pin.purposes) is not tuple
        or not pin.purposes
        or tuple(dict.fromkeys(pin.purposes)) != pin.purposes
        or any(purpose not in _purpose_namespaces for purpose in pin.purposes)
    ):
        raise OwnerSignatureAuthorityError("reviewed owner key registry is invalid")
    blob = _parse_public_blob(pin.public_key_base64)
    expected_id = "arv2-owner-ed25519-" + _sha256(blob).hexdigest()[:16]
    if pin.key_id != expected_id:
        raise OwnerSignatureAuthorityError("reviewed owner key identity changed")
    allowed = f"{_principal} ssh-ed25519 {pin.public_key_base64}\n".encode("ascii")
    return blob, allowed


def _select_reviewed_pin(
    allowed_signers: bytes,
    purpose: str,
    reviewed_pins: tuple[_ReviewedOwnerPublicKey, ...],
    *,
    _validate_pin: object = _validate_reviewed_pin,
) -> tuple[_ReviewedOwnerPublicKey, bytes]:
    if type(reviewed_pins) is not tuple:
        raise OwnerSignatureAuthorityError("reviewed owner key registry is invalid")
    eligible: list[tuple[_ReviewedOwnerPublicKey, bytes, bytes]] = []
    seen: set[str] = set()
    for pin in reviewed_pins:
        blob, exact_allowed = _validate_pin(pin)
        if pin.key_id in seen:
            raise OwnerSignatureAuthorityError("reviewed owner key registry has duplicates")
        seen.add(pin.key_id)
        if purpose in pin.purposes:
            eligible.append((pin, blob, exact_allowed))
    if len(eligible) != 1 or allowed_signers != eligible[0][2]:
        raise OwnerSignatureAuthorityError(
            "no unique independently reviewed owner Ed25519 key is installed for this gate"
        )
    return eligible[0][0], eligible[0][1]


def _validate_signature_envelope(
    payload: bytes,
    *,
    _begin: bytes = _SIGNATURE_BEGIN,
    _end: bytes = _SIGNATURE_END,
) -> None:
    if (
        b"\r" in payload
        or b"\x00" in payload
        or not payload.startswith(_begin)
        or not payload.endswith(_end)
        or payload.count(_begin) != 1
        or payload.count(_end) != 1
    ):
        raise OwnerSignatureAuthorityError("detached signature is not one SSH signature")
    try:
        payload.decode("ascii")
    except UnicodeError as exc:
        raise OwnerSignatureAuthorityError("detached signature is not ASCII") from exc


def _write_private_file(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(payload)
        while view:
            count = os.write(descriptor, view)
            if count <= 0:
                raise OwnerSignatureAuthorityError("temporary verifier input write failed")
            view = view[count:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _run_ssh_keygen_verify(
    *, authority_payload: bytes, allowed_signers: bytes, signature: bytes,
    namespace: str, verifier_path: str,
    _temporary_directory: object = tempfile.TemporaryDirectory,
    _write_file: object = _write_private_file,
    _run_process: object = subprocess.run,
    _principal: str = PRINCIPAL,
    _timeout_seconds: int = VERIFY_TIMEOUT_SECONDS,
    _completed_type: type[subprocess.CompletedProcess] = subprocess.CompletedProcess,
    _subprocess_error: type[subprocess.SubprocessError] = subprocess.SubprocessError,
) -> None:
    if type(verifier_path) is not str or verifier_path != "/usr/bin/ssh-keygen":
        raise OwnerSignatureAuthorityError(
            "trusted ssh-keygen verifier path changed"
        )
    try:
        with _temporary_directory(prefix="arv2-owner-signature-") as directory:
            root = Path(directory)
            if stat.S_IMODE(root.stat().st_mode) != 0o700:
                raise OwnerSignatureAuthorityError("temporary verifier directory is not private")
            allowed_path = root / "allowed_signers"
            signature_path = root / "authority.sig"
            _write_file(allowed_path, allowed_signers)
            _write_file(signature_path, signature)
            completed = _run_process(
                (
                    verifier_path, "-Y", "verify", "-f", str(allowed_path),
                    "-I", _principal, "-n", namespace, "-s", str(signature_path),
                ),
                input=authority_payload,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=root,
                env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
                timeout=_timeout_seconds,
                check=False,
                shell=False,
            )
    except OwnerSignatureAuthorityError:
        raise
    except (OSError, _subprocess_error) as exc:
        raise OwnerSignatureAuthorityError(
            "detached owner signature verifier was unavailable"
        ) from exc
    if type(completed) is not _completed_type or completed.returncode != 0:
        raise OwnerSignatureAuthorityError("detached owner signature verification failed")


def _require_verifier_unchanged(
    before: _VerifierPathSnapshot,
    *,
    _snapshot_verifier: object = _snapshot_trusted_verifier,
) -> None:
    after = _snapshot_verifier()
    if after != before:
        raise OwnerSignatureAuthorityError("trusted ssh-keygen verifier changed during use")


def _make_reviewed_pin_operations():
    """Seal every operation used by the production signature gate.

    The returned functions retain their dependencies lexically and supply
    every dependency-bearing helper argument explicitly.  Rebinding a
    same-named module attribute can therefore revoke or break a test helper,
    but neither rebinding nor mutating published helper defaults can replace
    signature verification in a production loader or requirer that already
    captured these functions.
    """

    # Capture every builtin used by the gate while this reviewed module is
    # initialized.  Runtime rebinding of ``builtins`` must not alter exact-type
    # checks, byte streams, descriptor scheduling, or identity construction.
    exact_type = type
    exact_tuple = tuple
    dict_type = dict
    bytes_type = bytes
    string_type = str
    integer_type = int
    length = len
    any_true = any
    all_true = all
    set_type = set
    minimum = min
    get_attribute = getattr
    codepoint = ord
    unicode_error_type = UnicodeError

    # Mutable authority data does not cross into the production closures.
    # Reviewed pin state and authenticated path identities are retained only
    # as scalar strings/bytes nested in tuples.  Public constructors and slot
    # attributes are not trusted after module initialization; mutation of
    # executable code or closure cells, and a concurrent type mutation after
    # the final topology check returns, remain the documented interpreter
    # boundary.
    # ``MappingProxyType`` exposes its mutable backing mapping to a reflected
    # ``__eq__`` implementation, and frozen dataclass instances remain
    # writable through ``object.__setattr__``.  Neither is therefore suitable
    # authority state even when the public review-facing values are frozen.
    purpose_namespace_items = exact_tuple(PURPOSE_NAMESPACES.items())
    purpose_names = exact_tuple(item[0] for item in purpose_namespace_items)
    public_key_prefix = bytes_type(_SSH_ED25519_PREFIX)
    key_id_prefix = "arv2-owner-ed25519-"
    signature_begin = bytes_type(_SIGNATURE_BEGIN)
    signature_end = bytes_type(_SIGNATURE_END)
    # Retain the executable authority as an immutable scalar.  A Path carries
    # mutable internal lists on Python 3.13 and is not closure-safe state.
    trusted_verifier_path = "/usr/bin/ssh-keygen"
    trusted_verifier_parents = ("/", "/usr", "/usr/bin")
    path_type = exact_type(Path())
    fspath = os.fspath
    lstat = os.lstat
    open_file = os.open
    read_file = os.read
    write_file = os.write
    seek_file = os.lseek
    stat_file = os.fstat
    close_file = os.close
    pipe_file = os.pipe
    set_blocking = os.set_blocking
    getuid = getattr(os, "getuid", None)
    read_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        read_flags |= os.O_NOFOLLOW
    seek_set = os.SEEK_SET
    file_type_mask = 0o170000
    regular_file_type = 0o100000
    directory_file_type = 0o040000
    symlink_file_type = 0o120000
    posix_spawn = getattr(os, "posix_spawn", None)
    waitpid = getattr(os, "waitpid", None)
    kill = getattr(os, "kill", None)
    waitstatus_to_exitcode = getattr(os, "waitstatus_to_exitcode", None)
    monotonic = time.monotonic
    sleep = time.sleep
    spawn_open = getattr(os, "POSIX_SPAWN_OPEN", -1)
    spawn_dup2 = getattr(os, "POSIX_SPAWN_DUP2", -1)
    wnohang = getattr(os, "WNOHANG", -1)
    raw_sigkill = getattr(signal, "SIGKILL", None)
    sigkill = (
        integer_type(raw_sigkill)
        if raw_sigkill is not None
        else None
    )
    o_wronly = os.O_WRONLY
    devnull = string_type(os.devnull)
    timeout_seconds = VERIFY_TIMEOUT_SECONDS
    memoryview_type = memoryview
    os_error = OSError
    blocking_io_error = BlockingIOError
    broken_pipe_error = BrokenPipeError
    child_process_error = ChildProcessError
    attribute_error_type = AttributeError
    key_error_type = KeyError
    type_error_type = TypeError
    sha256 = hashlib.sha256
    authority_type = OwnerSignatureAuthority
    error_type = OwnerSignatureAuthorityError
    object_new = object.__new__
    type_getattribute = type.__getattribute__
    authority_namespace = type_getattribute(authority_type, "__dict__")
    authority_slots = exact_tuple(
        (field.name, authority_namespace[field.name])
        for field in dataclasses.fields(authority_type)
    )
    authority_type_protocol = exact_tuple(
        (
            name,
            name in authority_namespace,
            authority_namespace[name] if name in authority_namespace else None,
        )
        for name in ("__new__", "__init__", "__getattribute__", "__setattr__")
    )
    authority_allowed_path_slot = authority_namespace["allowed_signers_path"]
    authority_signature_path_slot = authority_namespace["signature_path"]
    schema = SCHEMA
    principal = PRINCIPAL
    max_payload_bytes = MAX_AUTHORITY_PAYLOAD_BYTES
    max_allowed_bytes = MAX_ALLOWED_SIGNERS_BYTES
    max_signature_bytes = MAX_SIGNATURE_BYTES

    identity_keys = (
        "allowed_signers_byte_count",
        "allowed_signers_path",
        "allowed_signers_sha256",
        "authority_id",
        "authority_payload_byte_count",
        "authority_payload_sha256",
        "authority_sha256",
        "namespace",
        "principal",
        "public_key_blob_sha256",
        "purpose",
        "reviewed_key_id",
        "schema",
        "signature_byte_count",
        "signature_path",
        "signature_sha256",
        "verifier_path",
    )
    identity_string_keys = (
        "allowed_signers_path",
        "allowed_signers_sha256",
        "authority_payload_sha256",
        "namespace",
        "principal",
        "public_key_blob_sha256",
        "purpose",
        "reviewed_key_id",
        "schema",
        "signature_path",
        "signature_sha256",
        "verifier_path",
    )
    identity_integer_keys = (
        "allowed_signers_byte_count",
        "authority_payload_byte_count",
        "signature_byte_count",
    )

    def authority_type_is_current() -> bool:
        try:
            current_namespace = type_getattribute(authority_type, "__dict__")
            return (
                all_true(
                    (name in current_namespace) is was_present
                    and (
                        not was_present
                        or current_namespace[name] is original
                    )
                    for name, was_present, original in authority_type_protocol
                )
                and all_true(
                    name in current_namespace
                    and current_namespace[name] is slot
                    for name, slot in authority_slots
                )
            )
        except (attribute_error_type, key_error_type, type_error_type):
            return False

    def canonical_json_string(value: str) -> str:
        if exact_type(value) is not string_type:
            raise error_type("owner signature identity string changed")
        encoded = '"'
        for character in value:
            point = codepoint(character)
            if character == '"':
                encoded += '\\"'
            elif character == "\\":
                encoded += "\\\\"
            elif character == "\b":
                encoded += "\\b"
            elif character == "\t":
                encoded += "\\t"
            elif character == "\n":
                encoded += "\\n"
            elif character == "\f":
                encoded += "\\f"
            elif character == "\r":
                encoded += "\\r"
            elif point < 0x20 or point >= 0x7F:
                if point <= 0xFFFF:
                    encoded += f"\\u{point:04x}"
                else:
                    adjusted = point - 0x10000
                    high = 0xD800 + (adjusted >> 10)
                    low = 0xDC00 + (adjusted & 0x3FF)
                    encoded += f"\\u{high:04x}\\u{low:04x}"
            else:
                encoded += character
        return encoded + '"'

    def canonical_nonnegative_integer(value: int) -> str:
        if exact_type(value) is not integer_type or value < 0:
            raise error_type("owner signature identity integer changed")
        return f"{value:d}"

    def canonical_identity(value: dict[str, object]) -> bytes:
        if (
            exact_type(value) is not dict_type
            or length(value) != length(identity_keys)
            or any_true(key not in value for key in identity_keys)
            or value["authority_id"] is not None
            or value["authority_sha256"] is not None
            or any_true(
                exact_type(value[key]) is not string_type
                for key in identity_string_keys
            )
            or any_true(
                exact_type(value[key]) is not integer_type
                or value[key] < 0
                for key in identity_integer_keys
            )
        ):
            raise error_type("owner signature identity changed")
        document = (
            '{"allowed_signers_byte_count":'
            + canonical_nonnegative_integer(value["allowed_signers_byte_count"])
            + ',"allowed_signers_path":'
            + canonical_json_string(value["allowed_signers_path"])
            + ',"allowed_signers_sha256":'
            + canonical_json_string(value["allowed_signers_sha256"])
            + ',"authority_id":null,"authority_payload_byte_count":'
            + canonical_nonnegative_integer(value["authority_payload_byte_count"])
            + ',"authority_payload_sha256":'
            + canonical_json_string(value["authority_payload_sha256"])
            + ',"authority_sha256":null,"namespace":'
            + canonical_json_string(value["namespace"])
            + ',"principal":'
            + canonical_json_string(value["principal"])
            + ',"public_key_blob_sha256":'
            + canonical_json_string(value["public_key_blob_sha256"])
            + ',"purpose":'
            + canonical_json_string(value["purpose"])
            + ',"reviewed_key_id":'
            + canonical_json_string(value["reviewed_key_id"])
            + ',"schema":'
            + canonical_json_string(value["schema"])
            + ',"signature_byte_count":'
            + canonical_nonnegative_integer(value["signature_byte_count"])
            + ',"signature_path":'
            + canonical_json_string(value["signature_path"])
            + ',"signature_sha256":'
            + canonical_json_string(value["signature_sha256"])
            + ',"verifier_path":'
            + canonical_json_string(value["verifier_path"])
            + "}\n"
        )
        return document.encode("ascii")

    def exact_public_control_path_text(path: Path, name: str) -> str:
        if exact_type(path) is not path_type:
            raise error_type(f"{name} must be an absolute exact Path")
        path_text = fspath(path)
        if exact_type(path_text) is not string_type:
            raise error_type(f"{name} must be an absolute exact Path")
        return path_text

    def read_private_control(
        path_text: str,
        maximum_bytes: int,
        name: str,
    ) -> tuple[object, ...]:
        if getuid is None:
            raise error_type(
                "trusted POSIX verifier process boundary is unavailable"
            )
        parts = (
            path_text.split("/")
            if exact_type(path_text) is string_type
            else ()
        )
        if (
            exact_type(path_text) is not string_type
            or not path_text.startswith("/")
            or length(parts) < 2
            or any_true(part in ("", ".", "..") for part in parts[1:])
        ):
            raise error_type(f"{name} must be an absolute exact Path")
        current = ""
        try:
            for part in parts[1:]:
                current += "/" + part
                if lstat(current).st_mode & file_type_mask == symlink_file_type:
                    raise error_type(f"{name} and every parent must be nonsymlink")
            descriptor = open_file(path_text, read_flags)
        except error_type:
            raise
        except os_error as exc:
            raise error_type(f"{name} is unavailable") from exc

        def read_once() -> bytes:
            chunks: list[bytes] = []
            remaining = maximum_bytes + 1
            while remaining:
                chunk = read_file(descriptor, minimum(65_536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= length(chunk)
            return b"".join(chunks)

        try:
            before = stat_file(descriptor)
            first = read_once()
            middle = stat_file(descriptor)
            seek_file(descriptor, 0, seek_set)
            second = read_once()
            after = stat_file(descriptor)
        finally:
            close_file(descriptor)
        observed_fields = (
            "st_dev",
            "st_ino",
            "st_uid",
            "st_mode",
            "st_nlink",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if first != second or any_true(
            get_attribute(before, field) != get_attribute(middle, field)
            or get_attribute(before, field) != get_attribute(after, field)
            for field in observed_fields
        ):
            raise error_type("private signature control changed while read")
        if (
            before.st_mode & file_type_mask != regular_file_type
            or before.st_mode & 0o7777 != 0o600
            or before.st_uid != getuid()
            or before.st_nlink != 1
            or before.st_size != length(first)
            or not 0 < length(first) <= maximum_bytes
        ):
            raise error_type(
                f"{name} must be a bounded, owner-owned, mode-0600, "
                "single-link regular file"
            )
        return (
            path_text,
            sha256(first).hexdigest(),
            length(first),
            before.st_dev,
            before.st_ino,
            before.st_uid,
            before.st_mode & 0o7777,
            before.st_nlink,
            before.st_mtime_ns,
            before.st_ctime_ns,
            first,
        )

    def validate_signature_envelope(payload: bytes) -> None:
        if (
            b"\r" in payload
            or b"\x00" in payload
            or not payload.startswith(signature_begin)
            or not payload.endswith(signature_end)
            or payload.count(signature_begin) != 1
            or payload.count(signature_end) != 1
        ):
            raise error_type("detached signature is not one SSH signature")
        try:
            payload.decode("ascii")
        except unicode_error_type as exc:
            raise error_type("detached signature is not ASCII") from exc

    def snapshot_trusted_verifier() -> _VerifierSnapshot:
        parent_snapshots: tuple[tuple[object, ...], ...] = ()
        try:
            for parent in trusted_verifier_parents:
                observed_parent = lstat(parent)
                if (
                    observed_parent.st_mode & file_type_mask
                    != directory_file_type
                    or observed_parent.st_uid != 0
                    or observed_parent.st_mode & 0o022
                ):
                    raise error_type(
                        "trusted ssh-keygen verifier parent is not root-controlled"
                    )
                parent_snapshots = (
                    *parent_snapshots,
                    (
                        parent,
                        observed_parent.st_dev,
                        observed_parent.st_ino,
                        observed_parent.st_uid,
                        observed_parent.st_mode & 0o7777,
                        observed_parent.st_nlink,
                        observed_parent.st_mtime_ns,
                        observed_parent.st_ctime_ns,
                    ),
                )
            observed = lstat(trusted_verifier_path)
        except error_type:
            raise
        except os_error as exc:
            raise error_type(
                "trusted ssh-keygen verifier is unavailable"
            ) from exc
        if (
            observed.st_mode & file_type_mask != regular_file_type
            or observed.st_uid != 0
            or observed.st_nlink < 1
            or observed.st_mode & 0o022
            or not observed.st_mode & 0o111
            or observed.st_size <= 0
        ):
            raise error_type(
                "trusted ssh-keygen verifier is not a root-owned "
                "nonwritable executable"
            )
        return (
            parent_snapshots,
            (
                trusted_verifier_path,
                observed.st_dev,
                observed.st_ino,
                observed.st_uid,
                observed.st_mode & 0o7777,
                observed.st_size,
                observed.st_nlink,
                observed.st_mtime_ns,
                observed.st_ctime_ns,
            ),
        )

    def run_signature_verifier_once(
        authority_payload: bytes,
        allowed_signers: bytes,
        signature: bytes,
        namespace: str,
    ) -> None:
        if (
            posix_spawn is None
            or waitpid is None
            or kill is None
            or waitstatus_to_exitcode is None
            or exact_type(spawn_open) is not integer_type
            or spawn_open < 0
            or exact_type(spawn_dup2) is not integer_type
            or spawn_dup2 < 0
            or exact_type(wnohang) is not integer_type
            or wnohang < 0
            or exact_type(sigkill) is not integer_type
            or sigkill <= 0
        ):
            raise error_type(
                "trusted POSIX verifier process boundary is unavailable"
            )

        # This closed operation exclusively owns reaping its child.  A
        # process-wide competing reaper is unsupported and causes a typed
        # refusal; an observed ECHILD is never followed by signalling that PID.
        pid = None
        reaped = False
        returncode = None
        input_stream_broken = False
        verifier_descriptors: tuple[int, ...] = ()
        try:
            streams: tuple[tuple[int, int, bytes], ...] = ()
            for payload in (authority_payload, allowed_signers, signature):
                read_descriptor, write_descriptor = pipe_file()
                verifier_descriptors = (
                    *verifier_descriptors,
                    read_descriptor,
                    write_descriptor,
                )
                set_blocking(write_descriptor, False)
                streams = (
                    *streams,
                    (read_descriptor, write_descriptor, payload),
                )
            if any_true(
                exact_type(descriptor) is not integer_type or descriptor < 3
                for descriptor in verifier_descriptors
            ) or length(set_type(verifier_descriptors)) != 6:
                raise error_type("anonymous verifier descriptors are invalid")

            payload_stream, allowed_stream, signature_stream = streams
            payload_descriptor = payload_stream[0]
            allowed_descriptor = allowed_stream[0]
            signature_descriptor = signature_stream[0]
            read_descriptors = (
                payload_descriptor,
                allowed_descriptor,
                signature_descriptor,
            )
            descriptor_targets: tuple[int, ...] = ()
            candidate = 3
            while length(descriptor_targets) < 2:
                if candidate not in read_descriptors:
                    descriptor_targets = (*descriptor_targets, candidate)
                candidate += 1
            allowed_target, signature_target = descriptor_targets
            allowed_descriptor_path = f"/dev/fd/{allowed_target}"
            signature_descriptor_path = f"/dev/fd/{signature_target}"
            arguments = (
                trusted_verifier_path,
                "-Y",
                "verify",
                "-f",
                allowed_descriptor_path,
                "-I",
                principal,
                "-n",
                namespace,
                "-s",
                signature_descriptor_path,
            )
            file_actions = (
                (spawn_dup2, payload_descriptor, 0),
                (spawn_dup2, allowed_descriptor, allowed_target),
                (spawn_dup2, signature_descriptor, signature_target),
                (spawn_open, 1, devnull, o_wronly, 0),
                (spawn_open, 2, devnull, o_wronly, 0),
            )
            pid = posix_spawn(
                trusted_verifier_path,
                arguments,
                {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
                file_actions=file_actions,
            )
            for descriptor in read_descriptors:
                close_file(descriptor)
                verifier_descriptors = exact_tuple(
                    item for item in verifier_descriptors if item != descriptor
                )

            pending = exact_tuple(
                (write_descriptor, memoryview_type(payload))
                for _read_descriptor, write_descriptor, payload in streams
            )
            deadline = monotonic() + timeout_seconds
            while pending and not reaped:
                if monotonic() >= deadline:
                    raise error_type(
                        "detached owner signature verifier timed out"
                    )
                next_pending: tuple[tuple[int, object], ...] = ()
                made_progress = False
                for descriptor, view in pending:
                    try:
                        count = write_file(descriptor, view)
                    except blocking_io_error:
                        next_pending = (*next_pending, (descriptor, view))
                        continue
                    except broken_pipe_error:
                        input_stream_broken = True
                        close_file(descriptor)
                        verifier_descriptors = exact_tuple(
                            item
                            for item in verifier_descriptors
                            if item != descriptor
                        )
                        continue
                    if count <= 0:
                        raise error_type("anonymous verifier input write failed")
                    made_progress = True
                    remaining = view[count:]
                    if remaining:
                        next_pending = (*next_pending, (descriptor, remaining))
                    else:
                        close_file(descriptor)
                        verifier_descriptors = exact_tuple(
                            item
                            for item in verifier_descriptors
                            if item != descriptor
                        )
                pending = next_pending
                if pending and not made_progress:
                    observed_pid, status = waitpid(pid, wnohang)
                    if observed_pid == pid:
                        reaped = True
                        returncode = waitstatus_to_exitcode(status)
                        if monotonic() >= deadline:
                            raise error_type(
                                "detached owner signature verifier timed out"
                            )
                        break
                    if observed_pid != 0:
                        raise error_type(
                            "detached owner signature verifier returned "
                            "an invalid pid"
                        )
                    if monotonic() >= deadline:
                        raise error_type(
                            "detached owner signature verifier timed out"
                        )
                    sleep(0.01)

            while not reaped:
                if monotonic() >= deadline:
                    raise error_type(
                        "detached owner signature verifier timed out"
                    )
                observed_pid, status = waitpid(pid, wnohang)
                if observed_pid == pid:
                    reaped = True
                    returncode = waitstatus_to_exitcode(status)
                    if monotonic() >= deadline:
                        raise error_type(
                            "detached owner signature verifier timed out"
                        )
                    break
                if observed_pid != 0:
                    raise error_type(
                        "detached owner signature verifier returned an invalid pid"
                    )
                if monotonic() >= deadline:
                    raise error_type(
                        "detached owner signature verifier timed out"
                    )
                sleep(0.01)
        except error_type:
            raise
        except child_process_error as exc:
            # Another process-wide SIGCHLD policy or waiter may already have
            # reaped this child.  The numeric PID is no longer ours to signal;
            # it can be reused immediately by an unrelated process.  Let the
            # bounded wrapper distinguish this exact transient from every
            # cryptographic or verifier-integrity refusal.
            pid = None
            reaped = True
            raise
        except os_error as exc:
            raise error_type(
                "detached owner signature verifier was unavailable"
            ) from exc
        finally:
            for descriptor in verifier_descriptors:
                try:
                    close_file(descriptor)
                except os_error:
                    pass
            if pid is not None and not reaped:
                try:
                    kill(pid, sigkill)
                except os_error:
                    pass
                try:
                    waitpid(pid, 0)
                except (os_error, child_process_error):
                    pass
        if (
            input_stream_broken
            or exact_type(returncode) is not integer_type
            or returncode != 0
        ):
            raise error_type("detached owner signature verification failed")

    def run_signature_verifier(
        authority_payload: bytes,
        allowed_signers: bytes,
        signature: bytes,
        namespace: str,
    ) -> None:
        # Verification is a local, read-only operation.  A process-wide
        # SIGCHLD waiter can race this module and reap an otherwise valid
        # verifier child.  Retry that exact ECHILD-shaped condition once with
        # the same authenticated bytes and a fresh child.  Timeouts, spawn
        # errors, malformed input, nonzero verification, and all typed
        # integrity refusals remain single-attempt failures.
        attempts_remaining = 2
        while attempts_remaining:
            attempts_remaining -= 1
            try:
                run_signature_verifier_once(
                    authority_payload,
                    allowed_signers,
                    signature,
                    namespace,
                )
                return
            except child_process_error as exc:
                if attempts_remaining:
                    continue
                raise error_type(
                    "detached owner signature verifier was unavailable"
                ) from exc

    def require_trusted_verifier_unchanged(before: _VerifierSnapshot) -> None:
        if snapshot_trusted_verifier() != before:
            raise error_type("trusted ssh-keygen verifier changed during use")

    def namespace_for(purpose: str) -> str:
        if exact_type(purpose) is not string_type:
            raise error_type("owner signature purpose changed")
        for candidate, namespace in purpose_namespace_items:
            if purpose == candidate:
                return namespace
        raise error_type("owner signature purpose changed")

    def select_scalar_pin(
        allowed_signers: bytes,
        purpose: str,
        reviewed_pin_records: tuple[
            tuple[str, str, tuple[str, ...], bytes], ...
        ],
    ) -> tuple[str, bytes]:
        if exact_type(reviewed_pin_records) is not exact_tuple:
            raise error_type("reviewed owner key registry is invalid")
        eligible: tuple[tuple[str, bytes, bytes], ...] = ()
        seen: tuple[str, ...] = ()
        for record in reviewed_pin_records:
            if exact_type(record) is not exact_tuple or length(record) != 4:
                raise error_type("reviewed owner key registry is invalid")
            key_id, public_key_base64, purposes, blob = record
            if (
                exact_type(key_id) is not string_type
                or length(key_id) != length(key_id_prefix) + 16
                or not key_id.startswith(key_id_prefix)
                or any_true(
                    character not in "0123456789abcdef"
                    for character in key_id[length(key_id_prefix):]
                )
                or exact_type(public_key_base64) is not string_type
                or not public_key_base64
                or exact_type(purposes) is not exact_tuple
                or not purposes
                or exact_type(blob) is not bytes_type
                or any_true(
                    exact_type(item) is not string_type for item in purposes
                )
                or length(set_type(purposes)) != length(purposes)
                or any_true(item not in purpose_names for item in purposes)
                or key_id in seen
            ):
                raise error_type("reviewed owner key registry is invalid")
            if (
                length(blob) != length(public_key_prefix) + 32
                or not blob.startswith(public_key_prefix)
            ):
                raise error_type("reviewed owner key is not exact Ed25519")
            if key_id != key_id_prefix + sha256(blob).hexdigest()[:16]:
                raise error_type("reviewed owner key identity changed")
            exact_allowed = (
                f"{principal} ssh-ed25519 {public_key_base64}\n".encode("ascii")
            )
            seen = (*seen, key_id)
            if purpose in purposes:
                eligible = (*eligible, (key_id, blob, exact_allowed))
        if length(eligible) != 1 or allowed_signers != eligible[0][2]:
            raise error_type(
                "no unique independently reviewed owner Ed25519 key is installed for this gate"
            )
        return eligible[0][0], eligible[0][1]

    def load_with_reviewed_path_texts(
        *, purpose: str, authority_payload: bytes, allowed_signers_path: str,
        signature_path: str,
        reviewed_pin_records: tuple[
            tuple[str, str, tuple[str, ...], bytes], ...
        ],
    ) -> OwnerSignatureAuthority:
        if not authority_type_is_current():
            raise error_type("owner signature authority type changed")
        namespace = namespace_for(purpose)
        if (
            exact_type(authority_payload) is not bytes_type
            or not 0 < length(authority_payload) <= max_payload_bytes
        ):
            raise error_type("authority payload must be bounded exact bytes")
        allowed = read_private_control(
            allowed_signers_path,
            max_allowed_bytes,
            "owner allowed-signers file",
        )
        signature = read_private_control(
            signature_path,
            max_signature_bytes,
            "owner detached-signature file",
        )
        allowed_path_text, allowed_sha256, allowed_byte_count = allowed[:3]
        signature_path_text, signature_sha256, signature_byte_count = signature[:3]
        allowed_content = allowed[10]
        signature_content = signature[10]
        reviewed_key_id, public_blob = select_scalar_pin(
            allowed_content, purpose, reviewed_pin_records
        )
        validate_signature_envelope(signature_content)
        verifier = snapshot_trusted_verifier()
        run_signature_verifier(
            authority_payload,
            allowed_content,
            signature_content,
            namespace,
        )
        # Reopen the controls after crypto verification so path replacement
        # cannot exchange either owner-controlled file during the check.
        allowed_after = read_private_control(
            allowed_signers_path,
            max_allowed_bytes,
            "owner allowed-signers file",
        )
        signature_after = read_private_control(
            signature_path,
            max_signature_bytes,
            "owner detached-signature file",
        )
        require_trusted_verifier_unchanged(verifier)
        if allowed_after != allowed or signature_after != signature:
            raise error_type(
                "owner signature controls changed during verification"
            )
        identity = {
            "schema": schema,
            "authority_id": None,
            "authority_sha256": None,
            "purpose": purpose,
            "namespace": namespace,
            "principal": principal,
            "reviewed_key_id": reviewed_key_id,
            "public_key_blob_sha256": sha256(public_blob).hexdigest(),
            "authority_payload_sha256": sha256(authority_payload).hexdigest(),
            "authority_payload_byte_count": length(authority_payload),
            "allowed_signers_path": allowed_path_text,
            "allowed_signers_sha256": allowed_sha256,
            "allowed_signers_byte_count": allowed_byte_count,
            "signature_path": signature_path_text,
            "signature_sha256": signature_sha256,
            "signature_byte_count": signature_byte_count,
            "verifier_path": trusted_verifier_path,
        }
        digest = sha256(canonical_identity(identity)).hexdigest()
        identity["authority_sha256"] = digest
        identity["authority_id"] = (
            "arv2-owner-signature-authority-" + digest[:24]
        )
        authority_values = {
            "authority_id": string_type(identity["authority_id"]),
            "authority_sha256": digest,
            "schema": schema,
            "purpose": purpose,
            "namespace": namespace,
            "principal": principal,
            "reviewed_key_id": reviewed_key_id,
            "public_key_blob_sha256": string_type(
                identity["public_key_blob_sha256"]
            ),
            "authority_payload_sha256": string_type(
                identity["authority_payload_sha256"]
            ),
            "authority_payload_byte_count": length(authority_payload),
            "allowed_signers_path": allowed_path_text,
            "allowed_signers_sha256": allowed_sha256,
            "allowed_signers_byte_count": allowed_byte_count,
            "signature_path": signature_path_text,
            "signature_sha256": signature_sha256,
            "signature_byte_count": signature_byte_count,
            "verifier_path": trusted_verifier_path,
            "_authority_payload": bytes_type(authority_payload),
            "_allowed_signers_snapshot": allowed,
            "_signature_snapshot": signature,
            "_verifier_snapshot": verifier,
        }
        if (
            length(authority_values) != length(authority_slots)
            or any_true(name not in authority_values for name, _slot in authority_slots)
        ):
            raise error_type("owner signature authority schema changed")
        if not authority_type_is_current():
            raise error_type("owner signature authority type changed")
        result = object_new(authority_type)
        for name, slot in authority_slots:
            slot.__set__(result, authority_values[name])
        if not authority_type_is_current():
            raise error_type("owner signature authority type changed")
        return result

    def load_with_reviewed_pins(
        *, purpose: str, authority_payload: bytes, allowed_signers_path: Path,
        signature_path: Path,
        reviewed_pin_records: tuple[
            tuple[str, str, tuple[str, ...], bytes], ...
        ],
    ) -> OwnerSignatureAuthority:
        return load_with_reviewed_path_texts(
            purpose=purpose,
            authority_payload=authority_payload,
            allowed_signers_path=exact_public_control_path_text(
                allowed_signers_path, "owner allowed-signers file"
            ),
            signature_path=exact_public_control_path_text(
                signature_path, "owner detached-signature file"
            ),
            reviewed_pin_records=reviewed_pin_records,
        )

    def require_with_reviewed_pins(
        value: OwnerSignatureAuthority,
        *, purpose: str,
        authority_payload: bytes,
        reviewed_pin_records: tuple[
            tuple[str, str, tuple[str, ...], bytes], ...
        ],
    ) -> OwnerSignatureAuthority:
        if (
            exact_type(value) is not authority_type
            or not authority_type_is_current()
        ):
            raise error_type("exact owner signature authority is required")
        try:
            allowed_path_text = authority_allowed_path_slot.__get__(
                value, authority_type
            )
            signature_path_text = authority_signature_path_slot.__get__(
                value, authority_type
            )
            rebuilt = load_with_reviewed_path_texts(
                purpose=purpose,
                authority_payload=authority_payload,
                allowed_signers_path=allowed_path_text,
                signature_path=signature_path_text,
                reviewed_pin_records=reviewed_pin_records,
            )
            changed = any_true(
                slot.__get__(value, authority_type)
                != slot.__get__(rebuilt, authority_type)
                for _name, slot in authority_slots
            )
        except attribute_error_type as exc:
            raise error_type("owner signature authority changed") from exc
        if changed or not authority_type_is_current():
            raise error_type("owner signature authority changed")
        return value

    return load_with_reviewed_pins, require_with_reviewed_pins


(
    _load_with_reviewed_pins,
    _require_with_reviewed_pins,
) = _make_reviewed_pin_operations()
del _make_reviewed_pin_operations


def _seal_public_api(
    reviewed_pins: tuple[_ReviewedOwnerPublicKey, ...],
):
    """Capture reviewed keys away from a mutable module-global lookup.

    Normal Python callers can rebind ``_REVIEWED_OWNER_PUBLIC_KEYS`` but that
    cannot affect these closures.  Mutating function code or closure cells via
    a debugger remains equivalent to replacing reviewed running code and is
    outside this pure-Python data-boundary threat model.
    """

    # The registry remains published for transparent review.  The production
    # gate captures only exact strings and bytes nested in tuples, never the
    # mutable review-facing dataclass instances.
    sum_values = sum
    length = len
    all_true = all
    reviewed_pin_records = tuple(
        (
            pin.key_id,
            pin.public_key_base64,
            tuple(pin.purposes),
            _parse_ed25519_blob(pin.public_key_base64),
        )
        for pin in reviewed_pins
    )
    loader = _load_with_reviewed_pins
    requirer = _require_with_reviewed_pins
    formal_execution_purpose = FORMAL_EXECUTION_PURPOSE
    formal_result_read_purpose = FORMAL_RESULT_READ_PURPOSE
    preopen_execution_purpose = PREOPEN_EXECUTION_PURPOSE
    preopen_acquisition_review_purpose = PREOPEN_ACQUISITION_REVIEW_PURPOSE
    production_evidence_review_purpose = PRODUCTION_EVIDENCE_REVIEW_PURPOSE
    power_calibration_execution_purpose = POWER_CALIBRATION_EXECUTION_PURPOSE
    purpose_namespace_items = tuple(PURPOSE_NAMESPACES.items())
    schema = SCHEMA

    def load_formal_execution_owner_signature(
        *, authority_payload: bytes, allowed_signers_path: Path,
        signature_path: Path,
    ) -> OwnerSignatureAuthority:
        return loader(
            purpose=formal_execution_purpose,
            authority_payload=authority_payload,
            allowed_signers_path=allowed_signers_path,
            signature_path=signature_path,
            reviewed_pin_records=reviewed_pin_records,
        )

    def require_formal_execution_owner_signature(
        value: OwnerSignatureAuthority, *, authority_payload: bytes,
    ) -> OwnerSignatureAuthority:
        return requirer(
            value,
            purpose=formal_execution_purpose,
            authority_payload=authority_payload,
            reviewed_pin_records=reviewed_pin_records,
        )

    def load_formal_result_read_owner_signature(
        *, authority_payload: bytes, allowed_signers_path: Path,
        signature_path: Path,
    ) -> OwnerSignatureAuthority:
        return loader(
            purpose=formal_result_read_purpose,
            authority_payload=authority_payload,
            allowed_signers_path=allowed_signers_path,
            signature_path=signature_path,
            reviewed_pin_records=reviewed_pin_records,
        )

    def require_formal_result_read_owner_signature(
        value: OwnerSignatureAuthority, *, authority_payload: bytes,
    ) -> OwnerSignatureAuthority:
        return requirer(
            value,
            purpose=formal_result_read_purpose,
            authority_payload=authority_payload,
            reviewed_pin_records=reviewed_pin_records,
        )

    def load_preopen_execution_owner_signature(
        *, authority_payload: bytes, allowed_signers_path: Path,
        signature_path: Path,
    ) -> OwnerSignatureAuthority:
        return loader(
            purpose=preopen_execution_purpose,
            authority_payload=authority_payload,
            allowed_signers_path=allowed_signers_path,
            signature_path=signature_path,
            reviewed_pin_records=reviewed_pin_records,
        )

    def require_preopen_execution_owner_signature(
        value: OwnerSignatureAuthority, *, authority_payload: bytes,
    ) -> OwnerSignatureAuthority:
        return requirer(
            value,
            purpose=preopen_execution_purpose,
            authority_payload=authority_payload,
            reviewed_pin_records=reviewed_pin_records,
        )

    def load_preopen_acquisition_review_owner_signature(
        *, authority_payload: bytes, allowed_signers_path: Path,
        signature_path: Path,
    ) -> OwnerSignatureAuthority:
        return loader(
            purpose=preopen_acquisition_review_purpose,
            authority_payload=authority_payload,
            allowed_signers_path=allowed_signers_path,
            signature_path=signature_path,
            reviewed_pin_records=reviewed_pin_records,
        )

    def require_preopen_acquisition_review_owner_signature(
        value: OwnerSignatureAuthority, *, authority_payload: bytes,
    ) -> OwnerSignatureAuthority:
        return requirer(
            value,
            purpose=preopen_acquisition_review_purpose,
            authority_payload=authority_payload,
            reviewed_pin_records=reviewed_pin_records,
        )

    def load_production_evidence_review_owner_signature(
        *, authority_payload: bytes, allowed_signers_path: Path,
        signature_path: Path,
    ) -> OwnerSignatureAuthority:
        return loader(
            purpose=production_evidence_review_purpose,
            authority_payload=authority_payload,
            allowed_signers_path=allowed_signers_path,
            signature_path=signature_path,
            reviewed_pin_records=reviewed_pin_records,
        )

    def require_production_evidence_review_owner_signature(
        value: OwnerSignatureAuthority, *, authority_payload: bytes,
    ) -> OwnerSignatureAuthority:
        return requirer(
            value,
            purpose=production_evidence_review_purpose,
            authority_payload=authority_payload,
            reviewed_pin_records=reviewed_pin_records,
        )

    def load_power_calibration_execution_owner_signature(
        *, authority_payload: bytes, allowed_signers_path: Path,
        signature_path: Path,
    ) -> OwnerSignatureAuthority:
        return loader(
            purpose=power_calibration_execution_purpose,
            authority_payload=authority_payload,
            allowed_signers_path=allowed_signers_path,
            signature_path=signature_path,
            reviewed_pin_records=reviewed_pin_records,
        )

    def require_power_calibration_execution_owner_signature(
        value: OwnerSignatureAuthority, *, authority_payload: bytes,
    ) -> OwnerSignatureAuthority:
        return requirer(
            value,
            purpose=power_calibration_execution_purpose,
            authority_payload=authority_payload,
            reviewed_pin_records=reviewed_pin_records,
        )

    def reviewed_owner_signature_registry_status() -> dict[str, object]:
        """Return non-sensitive closed/open state; never key material."""

        enabled = {
            purpose: sum_values(
                purpose in record[2] for record in reviewed_pin_records
            )
            for purpose, _namespace in purpose_namespace_items
        }
        return {
            "schema": schema,
            "reviewed_key_count": length(reviewed_pin_records),
            "gate_key_counts": enabled,
            "all_positive_paths_enabled": all_true(
                count == 1 for count in enabled.values()
            ),
            "production_signing_implemented": False,
            "private_key_access_implemented": False,
        }

    return (
        load_formal_execution_owner_signature,
        require_formal_execution_owner_signature,
        load_formal_result_read_owner_signature,
        require_formal_result_read_owner_signature,
        load_preopen_execution_owner_signature,
        require_preopen_execution_owner_signature,
        load_preopen_acquisition_review_owner_signature,
        require_preopen_acquisition_review_owner_signature,
        load_production_evidence_review_owner_signature,
        require_production_evidence_review_owner_signature,
        load_power_calibration_execution_owner_signature,
        require_power_calibration_execution_owner_signature,
        reviewed_owner_signature_registry_status,
    )


(
    load_formal_execution_owner_signature,
    require_formal_execution_owner_signature,
    load_formal_result_read_owner_signature,
    require_formal_result_read_owner_signature,
    load_preopen_execution_owner_signature,
    require_preopen_execution_owner_signature,
    load_preopen_acquisition_review_owner_signature,
    require_preopen_acquisition_review_owner_signature,
    load_production_evidence_review_owner_signature,
    require_production_evidence_review_owner_signature,
    load_power_calibration_execution_owner_signature,
    require_power_calibration_execution_owner_signature,
    reviewed_owner_signature_registry_status,
) = _seal_public_api(_REVIEWED_OWNER_PUBLIC_KEYS)
del _seal_public_api
del _load_with_reviewed_pins
del _require_with_reviewed_pins


__all__ = [
    "FORMAL_EXECUTION_PURPOSE",
    "FORMAL_RESULT_READ_PURPOSE",
    "OwnerSignatureAuthority",
    "OwnerSignatureAuthorityError",
    "PREOPEN_ACQUISITION_REVIEW_PURPOSE",
    "PREOPEN_EXECUTION_PURPOSE",
    "POWER_CALIBRATION_EXECUTION_PURPOSE",
    "PRINCIPAL",
    "PURPOSE_NAMESPACES",
    "PRODUCTION_EVIDENCE_REVIEW_PURPOSE",
    "SCHEMA",
    "TRUSTED_SSH_KEYGEN_PATH",
    "load_formal_execution_owner_signature",
    "load_formal_result_read_owner_signature",
    "load_preopen_execution_owner_signature",
    "load_preopen_acquisition_review_owner_signature",
    "load_production_evidence_review_owner_signature",
    "load_power_calibration_execution_owner_signature",
    "require_formal_execution_owner_signature",
    "require_formal_result_read_owner_signature",
    "require_preopen_execution_owner_signature",
    "require_preopen_acquisition_review_owner_signature",
    "require_production_evidence_review_owner_signature",
    "require_power_calibration_execution_owner_signature",
    "reviewed_owner_signature_registry_status",
]
