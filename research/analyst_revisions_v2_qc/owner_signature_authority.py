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
import stat
import subprocess
import tempfile
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
# Owner-created 2026-09-12.  This is public verification material only; the
# private key and its passphrase are neither read nor stored by this lane.
_REVIEWED_OWNER_PUBLIC_KEYS: tuple[_ReviewedOwnerPublicKey, ...] = (
    _ReviewedOwnerPublicKey(
        key_id="arv2-owner-ed25519-21d1ae9d964ec350",
        public_key_base64=(
            "AAAAC3NzaC1lZDI1NTE5AAAAIA2kYwmz2Tc/F2tfAqo7xQlM/doV0nI1viXyOvUkcsQE"
        ),
        purposes=(
            FORMAL_EXECUTION_PURPOSE,
            FORMAL_RESULT_READ_PURPOSE,
            PREOPEN_EXECUTION_PURPOSE,
            PREOPEN_ACQUISITION_REVIEW_PURPOSE,
            PRODUCTION_EVIDENCE_REVIEW_PURPOSE,
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


@dataclasses.dataclass(frozen=True, slots=True)
class _VerifierSnapshot:
    path: Path
    device: int
    inode: int
    owner_uid: int
    mode: int
    byte_count: int
    link_count: int
    modified_ns: int
    changed_ns: int


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
    allowed_signers_path: Path
    allowed_signers_sha256: str
    allowed_signers_byte_count: int
    signature_path: Path
    signature_sha256: str
    signature_byte_count: int
    verifier_path: Path
    _authority_payload: bytes = dataclasses.field(repr=False)
    _allowed_signers_snapshot: _FileSnapshot = dataclasses.field(repr=False)
    _signature_snapshot: _FileSnapshot = dataclasses.field(repr=False)
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


def _snapshot_trusted_verifier(
    _sealed_path: Path = Path("/usr/bin/ssh-keygen"),
    _snapshot_type: type[_VerifierSnapshot] = _VerifierSnapshot,
) -> _VerifierSnapshot:
    # The default captures the reviewed executable identity when the function
    # is defined.  Rebinding the public informational constant therefore
    # cannot redirect production verification.
    path = _sealed_path
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
    return _snapshot_type(
        path=path,
        device=observed.st_dev,
        inode=observed.st_ino,
        owner_uid=observed.st_uid,
        mode=stat.S_IMODE(observed.st_mode),
        byte_count=observed.st_size,
        link_count=observed.st_nlink,
        modified_ns=observed.st_mtime_ns,
        changed_ns=observed.st_ctime_ns,
    )


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
    namespace: str, verifier: _VerifierSnapshot,
    _temporary_directory: object = tempfile.TemporaryDirectory,
    _write_file: object = _write_private_file,
    _run_process: object = subprocess.run,
    _principal: str = PRINCIPAL,
    _timeout_seconds: int = VERIFY_TIMEOUT_SECONDS,
    _completed_type: type[subprocess.CompletedProcess] = subprocess.CompletedProcess,
    _subprocess_error: type[subprocess.SubprocessError] = subprocess.SubprocessError,
) -> None:
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
                    str(verifier.path), "-Y", "verify", "-f", str(allowed_path),
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
    before: _VerifierSnapshot,
    *,
    _snapshot_verifier: object = _snapshot_trusted_verifier,
) -> None:
    after = _snapshot_verifier()
    if after != before:
        raise OwnerSignatureAuthorityError("trusted ssh-keygen verifier changed during use")


def _make_reviewed_pin_operations():
    """Seal every operation used by the production signature gate.

    The returned functions retain their dependencies lexically.  Rebinding a
    same-named module attribute can therefore revoke or break a test helper,
    but it cannot replace signature verification in a production loader or
    requirer that already captured these functions.
    """

    # Only exact immutable scalar tuples cross into the production closures.
    # ``MappingProxyType`` exposes its mutable backing mapping to a reflected
    # ``__eq__`` implementation, and frozen dataclass instances remain
    # writable through ``object.__setattr__``.  Neither is therefore suitable
    # authority state even when the public review-facing values are frozen.
    purpose_namespace_items = tuple(PURPOSE_NAMESPACES.items())
    purpose_names = tuple(item[0] for item in purpose_namespace_items)
    public_key_prefix = bytes(_SSH_ED25519_PREFIX)
    key_id_prefix = "arv2-owner-ed25519-"
    b64decode = base64.b64decode
    b64encode = base64.b64encode
    read_private_file = _read_private_stable_file
    validate_envelope = _validate_signature_envelope
    snapshot_verifier = _snapshot_trusted_verifier
    run_verify = _run_ssh_keygen_verify
    require_unchanged = _require_verifier_unchanged
    canonical_identity = _canonical_identity_bytes
    sha256 = hashlib.sha256
    authority_type = OwnerSignatureAuthority
    error_type = OwnerSignatureAuthorityError
    dataclass_fields = dataclasses.fields
    schema = SCHEMA
    principal = PRINCIPAL
    max_payload_bytes = MAX_AUTHORITY_PAYLOAD_BYTES
    max_allowed_bytes = MAX_ALLOWED_SIGNERS_BYTES
    max_signature_bytes = MAX_SIGNATURE_BYTES

    def namespace_for(purpose: str) -> str:
        if type(purpose) is not str:
            raise error_type("owner signature purpose changed")
        for candidate, namespace in purpose_namespace_items:
            if purpose == candidate:
                return namespace
        raise error_type("owner signature purpose changed")

    def select_scalar_pin(
        allowed_signers: bytes,
        purpose: str,
        reviewed_pin_records: tuple[tuple[str, str, tuple[str, ...]], ...],
    ) -> tuple[str, bytes]:
        if type(reviewed_pin_records) is not tuple:
            raise error_type("reviewed owner key registry is invalid")
        eligible: tuple[tuple[str, bytes, bytes], ...] = ()
        seen: tuple[str, ...] = ()
        for record in reviewed_pin_records:
            if type(record) is not tuple or len(record) != 3:
                raise error_type("reviewed owner key registry is invalid")
            key_id, public_key_base64, purposes = record
            if (
                type(key_id) is not str
                or len(key_id) != len(key_id_prefix) + 16
                or not key_id.startswith(key_id_prefix)
                or any(
                    character not in "0123456789abcdef"
                    for character in key_id[len(key_id_prefix):]
                )
                or type(public_key_base64) is not str
                or not public_key_base64
                or type(purposes) is not tuple
                or not purposes
                or any(type(item) is not str for item in purposes)
                or len(set(purposes)) != len(purposes)
                or any(item not in purpose_names for item in purposes)
                or key_id in seen
            ):
                raise error_type("reviewed owner key registry is invalid")
            try:
                blob = b64decode(public_key_base64.encode("ascii"), validate=True)
            except (UnicodeError, ValueError, binascii.Error) as exc:
                raise error_type("reviewed owner public key is invalid") from exc
            if (
                len(blob) != len(public_key_prefix) + 32
                or not blob.startswith(public_key_prefix)
                or b64encode(blob).decode("ascii") != public_key_base64
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
        if len(eligible) != 1 or allowed_signers != eligible[0][2]:
            raise error_type(
                "no unique independently reviewed owner Ed25519 key is installed for this gate"
            )
        return eligible[0][0], eligible[0][1]

    def load_with_reviewed_pins(
        *, purpose: str, authority_payload: bytes, allowed_signers_path: Path,
        signature_path: Path,
        reviewed_pin_records: tuple[tuple[str, str, tuple[str, ...]], ...],
    ) -> OwnerSignatureAuthority:
        namespace = namespace_for(purpose)
        if (
            type(authority_payload) is not bytes
            or not 0 < len(authority_payload) <= max_payload_bytes
        ):
            raise error_type("authority payload must be bounded exact bytes")
        allowed = read_private_file(
            allowed_signers_path,
            maximum_bytes=max_allowed_bytes,
            name="owner allowed-signers file",
        )
        signature = read_private_file(
            signature_path,
            maximum_bytes=max_signature_bytes,
            name="owner detached-signature file",
        )
        reviewed_key_id, public_blob = select_scalar_pin(
            allowed._content, purpose, reviewed_pin_records
        )
        validate_envelope(signature._content)
        verifier = snapshot_verifier()
        run_verify(
            authority_payload=authority_payload,
            allowed_signers=allowed._content,
            signature=signature._content,
            namespace=namespace,
            verifier=verifier,
        )
        # Reopen the controls after crypto verification so path replacement
        # cannot exchange either owner-controlled file during the check.
        allowed_after = read_private_file(
            allowed_signers_path,
            maximum_bytes=max_allowed_bytes,
            name="owner allowed-signers file",
        )
        signature_after = read_private_file(
            signature_path,
            maximum_bytes=max_signature_bytes,
            name="owner detached-signature file",
        )
        require_unchanged(verifier)
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
            "authority_payload_byte_count": len(authority_payload),
            "allowed_signers_path": str(allowed.path),
            "allowed_signers_sha256": allowed.content_sha256,
            "allowed_signers_byte_count": allowed.byte_count,
            "signature_path": str(signature.path),
            "signature_sha256": signature.content_sha256,
            "signature_byte_count": signature.byte_count,
            "verifier_path": str(verifier.path),
        }
        digest = sha256(canonical_identity(identity)).hexdigest()
        identity["authority_sha256"] = digest
        identity["authority_id"] = (
            "arv2-owner-signature-authority-" + digest[:24]
        )
        return authority_type(
            authority_id=str(identity["authority_id"]),
            authority_sha256=digest,
            schema=schema,
            purpose=purpose,
            namespace=namespace,
            principal=principal,
            reviewed_key_id=reviewed_key_id,
            public_key_blob_sha256=str(identity["public_key_blob_sha256"]),
            authority_payload_sha256=str(identity["authority_payload_sha256"]),
            authority_payload_byte_count=len(authority_payload),
            allowed_signers_path=allowed.path,
            allowed_signers_sha256=allowed.content_sha256,
            allowed_signers_byte_count=allowed.byte_count,
            signature_path=signature.path,
            signature_sha256=signature.content_sha256,
            signature_byte_count=signature.byte_count,
            verifier_path=verifier.path,
            _authority_payload=bytes(authority_payload),
            _allowed_signers_snapshot=allowed,
            _signature_snapshot=signature,
            _verifier_snapshot=verifier,
        )

    def require_with_reviewed_pins(
        value: OwnerSignatureAuthority,
        *, purpose: str,
        authority_payload: bytes,
        reviewed_pin_records: tuple[tuple[str, str, tuple[str, ...]], ...],
    ) -> OwnerSignatureAuthority:
        if type(value) is not authority_type:
            raise error_type("exact owner signature authority is required")
        rebuilt = load_with_reviewed_pins(
            purpose=purpose,
            authority_payload=authority_payload,
            allowed_signers_path=value.allowed_signers_path,
            signature_path=value.signature_path,
            reviewed_pin_records=reviewed_pin_records,
        )
        if any(
            getattr(value, field.name) != getattr(rebuilt, field.name)
            for field in dataclass_fields(authority_type)
        ):
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
    # gate captures only exact strings nested in tuples, never the mutable
    # review-facing dataclass instances.
    reviewed_pin_records = tuple(
        (pin.key_id, pin.public_key_base64, tuple(pin.purposes))
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
            purpose: sum(
                purpose in record[2] for record in reviewed_pin_records
            )
            for purpose, _namespace in purpose_namespace_items
        }
        return {
            "schema": schema,
            "reviewed_key_count": len(reviewed_pin_records),
            "gate_key_counts": enabled,
            "all_positive_paths_enabled": all(
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
