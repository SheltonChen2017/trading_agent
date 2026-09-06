"""External trust-root verification for positive TPR review authority.

The checked-in registry is deliberately empty.  If a later, separately
authorized round adds an entry, this module authenticates the Git commit that
changed the registry before any entry is interpreted.  It never signs a
commit, creates a key, provisions the machine trust file, or grants outcome
access.
"""

from __future__ import annotations

import base64
import binascii
import dataclasses
import hashlib
import os
import re
import subprocess
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .import_firewall import ImportBoundaryError, validate_transitive_import_closure
from .windows_acl import WindowsAclError, validate_trust_path


class TrustRootError(ValueError):
    """The external signer, signed registry anchor, or Git lineage is invalid."""


SIGNATURE_FORMAT = "ssh"
SIGNATURE_NAMESPACE = "git"
SIGNER_PRINCIPAL = "shelton-tpr-reviewer"
SIGNING_KEY_TYPE = "ssh-ed25519"
ALLOWED_SIGNERS_PATH_ID = (
    "windows-programdata-customizedagent-trust-tpr-allowed-signers-v1"
)
ALLOWED_SIGNERS_PATH = Path(
    r"C:\ProgramData\CustomizedAgent\trust\tpr_allowed_signers"
)
ALLOWED_SIGNERS_GIT_PATH = (
    "C:/ProgramData/CustomizedAgent/trust/tpr_allowed_signers"
)
TRUST_DIRECTORY = ALLOWED_SIGNERS_PATH.parent
SSH_KEYGEN_PROGRAM = Path(r"C:\Windows\System32\OpenSSH\ssh-keygen.exe")
SSH_KEYGEN_GIT_PATH = "C:/Windows/System32/OpenSSH/ssh-keygen.exe"
GIT_PROGRAM = Path(r"C:\Program Files\Git\cmd\git.exe")
REGISTRY_REPO_PATH = (
    "research/target_price_revisions/specs/reviewed_spec_registry.json"
)
DECLARED_NON_MODULE_POLICY_PATHS = frozenset(
    {"research/target_price_revisions/specs/.gitattributes"}
)

SIGNATURE_POLICY = {
    "allowed_signers_path_id": ALLOWED_SIGNERS_PATH_ID,
    "format": SIGNATURE_FORMAT,
    "key_type": SIGNING_KEY_TYPE,
    "namespace": SIGNATURE_NAMESPACE,
    "principal": SIGNER_PRINCIPAL,
}

_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
_FINGERPRINT_RE = re.compile(r"SHA256:[A-Za-z0-9+/]{43}")
_PUBLIC_KEY_RE = re.compile(
    rb'shelton-tpr-reviewer namespaces="git" ssh-ed25519 '
    rb"([A-Za-z0-9+/]+={0,2})\n"
)
_FORBIDDEN_CALLER_GIT_ENVIRONMENT = frozenset(
    {
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_CEILING_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_DIR",
        "GIT_DISCOVERY_ACROSS_FILESYSTEM",
        "GIT_EXEC_PATH",
        "GIT_INDEX_FILE",
        "GIT_NAMESPACE",
        "GIT_NO_REPLACE_OBJECTS",
        "GIT_OBJECT_DIRECTORY",
        "GIT_PREFIX",
        "GIT_REPLACE_REF_BASE",
        "GIT_SHALLOW_FILE",
        "GIT_WORK_TREE",
    }
)
_SAFE_INHERITED_ENVIRONMENT = frozenset(
    {
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "WINDIR",
    }
)
_FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
_AUTHORITY_GIT_PREFIX = ("-c", "core.commitGraph=false")


@dataclasses.dataclass(frozen=True)
class TrustedSigner:
    principal: str
    namespace: str
    key_type: str
    public_key_base64: str
    fingerprint: str


@dataclasses.dataclass(frozen=True)
class TrustedRegistrySnapshot:
    anchor_commit: str
    parent_commit: str
    head_commit: str
    signing_key_fingerprint: str
    registry_payload: bytes


@dataclasses.dataclass(frozen=True)
class _GitResult:
    returncode: int
    stdout: bytes
    stderr: bytes


_GitRunner = Callable[[Sequence[str]], _GitResult]


def _decode_ssh_ed25519_blob(encoded: bytes) -> bytes:
    try:
        blob = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise TrustRootError("allowed signer public key is not canonical base64") from exc
    if base64.b64encode(blob) != encoded:
        raise TrustRootError("allowed signer public key is not canonical base64")

    def take_field(offset: int) -> tuple[bytes, int]:
        if len(blob) - offset < 4:
            raise TrustRootError("allowed signer public key blob is truncated")
        length = int.from_bytes(blob[offset : offset + 4], "big")
        start = offset + 4
        end = start + length
        if end > len(blob):
            raise TrustRootError("allowed signer public key blob is truncated")
        return blob[start:end], end

    algorithm, offset = take_field(0)
    key_material, offset = take_field(offset)
    if (
        algorithm != SIGNING_KEY_TYPE.encode("ascii")
        or len(key_material) != 32
        or offset != len(blob)
    ):
        raise TrustRootError("allowed signer must contain one Ed25519 public key")
    return blob


def _parse_allowed_signer(payload: bytes) -> TrustedSigner:
    if type(payload) is not bytes:
        raise TrustRootError("allowed-signers content must be exact bytes")
    match = _PUBLIC_KEY_RE.fullmatch(payload)
    if match is None:
        raise TrustRootError(
            "allowed-signers file must contain exactly one frozen LF-terminated line"
        )
    encoded = match.group(1)
    blob = _decode_ssh_ed25519_blob(encoded)
    fingerprint = "SHA256:" + base64.b64encode(
        hashlib.sha256(blob).digest()
    ).decode("ascii").rstrip("=")
    if _FINGERPRINT_RE.fullmatch(fingerprint) is None:  # pragma: no cover
        raise TrustRootError("allowed signer fingerprint is malformed")
    return TrustedSigner(
        principal=SIGNER_PRINCIPAL,
        namespace=SIGNATURE_NAMESPACE,
        key_type=SIGNING_KEY_TYPE,
        public_key_base64=encoded.decode("ascii"),
        fingerprint=fingerprint,
    )


def _load_allowed_signer(path: Path) -> TrustedSigner:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise TrustRootError("external allowed-signers file is unavailable") from exc
    return _parse_allowed_signer(payload)


def _secure_git_environment(
    source: Mapping[str, str] | None = None,
) -> dict[str, str]:
    inherited = os.environ if source is None else source
    for name in inherited:
        upper = name.upper()
        if upper.startswith("GIT_CONFIG") or upper in _FORBIDDEN_CALLER_GIT_ENVIRONMENT:
            raise TrustRootError(
                f"caller-controlled Git environment is forbidden: {upper}"
            )
    result = {
        name: value
        for name, value in inherited.items()
        if name.upper() in _SAFE_INHERITED_ENVIRONMENT
    }
    result.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
        }
    )
    return result


def _canonical_repository_root(path: Path) -> Path:
    if not isinstance(path, Path):
        raise TrustRootError("repository root must be a pathlib path")
    original = path.absolute()
    try:
        resolved = original.resolve(strict=True)
    except OSError as exc:
        raise TrustRootError("repository root is unavailable") from exc
    if resolved != original or not resolved.is_dir() or not (resolved / ".git").exists():
        raise TrustRootError("repository root must be canonical, unredirected, and Git-backed")
    return resolved


def _canonical_frozen_git_program() -> Path:
    original = GIT_PROGRAM.absolute()
    try:
        for component in (original, *original.parents):
            attributes = int(getattr(component.lstat(), "st_file_attributes", 0))
            if attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
                raise TrustRootError(
                    "the frozen Git executable path must not contain a reparse point"
                )
        resolved = original.resolve(strict=True)
    except OSError as exc:
        raise TrustRootError("the frozen Git executable is unavailable") from exc
    if resolved != original or not resolved.is_file():
        raise TrustRootError(
            "the frozen Git executable must be canonical and unredirected"
        )
    return resolved


def _invoke_git(
    program: Path,
    root: Path,
    arguments: Sequence[str],
    environment: Mapping[str, str],
) -> _GitResult:
    command = [str(program), "-C", str(root), *arguments]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=False,
            shell=False,
            env=dict(environment),
        )
    except OSError as exc:
        raise TrustRootError("signed-registry Git verification is unavailable") from exc
    return _GitResult(completed.returncode, completed.stdout, completed.stderr)


def _reject_legacy_grafts(runner: _GitRunner) -> None:
    payload = _checked(
        runner,
        (
            "--no-replace-objects",
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        ),
        "Git common-directory verification",
    )
    try:
        rendered = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise TrustRootError("Git common directory is malformed") from exc
    if not rendered.endswith("\n") or rendered.count("\n") != 1 or "\r" in rendered:
        raise TrustRootError("Git common directory is malformed")
    original = Path(rendered[:-1])
    if not original.is_absolute():
        raise TrustRootError("Git common directory must be absolute")
    absolute = original.absolute()
    try:
        resolved = original.resolve(strict=True)
    except OSError as exc:
        raise TrustRootError("Git common directory is unavailable") from exc
    if resolved != absolute or not resolved.is_dir():
        raise TrustRootError("Git common directory must be canonical and unredirected")
    grafts = resolved / "info" / "grafts"
    try:
        grafts.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise TrustRootError("legacy Git graft state cannot be inspected") from exc
    raise TrustRootError("legacy Git grafts are forbidden for authority verification")


def _production_runner(root: Path) -> _GitRunner:
    environment = _secure_git_environment()
    program = _canonical_frozen_git_program()
    runner = lambda arguments: _invoke_git(
        program,
        root,
        (*_AUTHORITY_GIT_PREFIX, *arguments),
        environment,
    )
    _reject_legacy_grafts(runner)
    return runner


def _checked(
    runner: _GitRunner,
    arguments: Sequence[str],
    name: str,
    *,
    stderr_must_be_empty: bool = True,
) -> bytes:
    result = runner(arguments)
    if (
        result.returncode != 0
        or (stderr_must_be_empty and result.stderr != b"")
    ):
        raise TrustRootError(f"{name} failed closed")
    return result.stdout


def _one_commit(payload: bytes, name: str) -> str:
    try:
        text = payload.decode("ascii")
    except UnicodeDecodeError as exc:
        raise TrustRootError(f"{name} is malformed") from exc
    if not text.endswith("\n") or text.count("\n") != 1:
        raise TrustRootError(f"{name} is malformed")
    value = text[:-1]
    if _COMMIT_RE.fullmatch(value) is None:
        raise TrustRootError(f"{name} is malformed")
    return value


def _parse_signature_status(payload: bytes, signer: TrustedSigner) -> None:
    if not payload.endswith(b"\n") or payload.count(b"\n") != 1 or b"\r" in payload:
        raise TrustRootError("Git signature status is malformed")
    fields = payload[:-1].split(b"\0")
    if len(fields) != 5 or any(not field for field in fields):
        raise TrustRootError("Git signature status is malformed")
    try:
        status, trust, principal, key_identifier, fingerprint = (
            field.decode("ascii") for field in fields
        )
    except UnicodeDecodeError as exc:
        raise TrustRootError("Git signature status is malformed") from exc
    if (
        status != "G"
        or trust != "fully"
        or principal != signer.principal
        or key_identifier != signer.fingerprint
        or fingerprint != signer.fingerprint
    ):
        raise TrustRootError("Git signature status does not match external trust")


def _validate_verify_output(result: _GitResult, signer: TrustedSigner) -> None:
    expected = (
        f'Good "{SIGNATURE_NAMESPACE}" signature for {signer.principal} '
        f"with ED25519 key {signer.fingerprint}\n"
    ).encode("ascii")
    if result.returncode != 0 or result.stdout != b"" or result.stderr != expected:
        raise TrustRootError("registry-anchor signature verification failed closed")


def _verify_with_runner(
    *,
    runner: _GitRunner,
    signer: TrustedSigner,
    working_registry_payload: bytes,
) -> TrustedRegistrySnapshot:
    if type(working_registry_payload) is not bytes:
        raise TrustRootError("working registry must be exact bytes")
    shallow = _checked(
        runner,
        ("rev-parse", "--is-shallow-repository"),
        "shallow-repository probe",
    )
    if shallow != b"false\n":
        raise TrustRootError("signed registry requires complete non-shallow history")

    head = _one_commit(
        _checked(
            runner,
            (
                "--no-replace-objects",
                "rev-parse",
                "--verify",
                "HEAD^{commit}",
            ),
            "HEAD snapshot derivation",
        ),
        "HEAD snapshot commit",
    )
    anchor = _one_commit(
        _checked(
            runner,
            (
                "--no-replace-objects",
                "log",
                "-1",
                "--format=%H",
                head,
                "--",
                REGISTRY_REPO_PATH,
            ),
            "registry-anchor derivation",
        ),
        "registry-anchor commit",
    )
    parent_line = _checked(
        runner,
        ("--no-replace-objects", "rev-list", "--parents", "-n", "1", anchor),
        "registry-anchor parent verification",
    )
    try:
        parent_text = parent_line.decode("ascii")
    except UnicodeDecodeError as exc:
        raise TrustRootError("registry-anchor parent record is malformed") from exc
    if not parent_text.endswith("\n") or parent_text.count("\n") != 1:
        raise TrustRootError("registry-anchor parent record is malformed")
    parts = parent_text[:-1].split(" ")
    if (
        len(parts) != 2
        or parts[0] != anchor
        or _COMMIT_RE.fullmatch(parts[1]) is None
    ):
        raise TrustRootError("registry anchor must be one non-merge commit")
    parent = parts[1]

    changed = _checked(
        runner,
        (
            "--no-replace-objects",
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            f"{anchor}^",
            anchor,
        ),
        "registry-anchor path verification",
    )
    if changed != (REGISTRY_REPO_PATH + "\n").encode("ascii"):
        raise TrustRootError("registry anchor must change only the reviewed registry")

    parent_registry = _checked(
        runner,
        (
            "--no-replace-objects",
            "show",
            f"{anchor}^:{REGISTRY_REPO_PATH}",
        ),
        "parent registry blob read",
    )
    anchor_registry = _checked(
        runner,
        (
            "--no-replace-objects",
            "show",
            f"{anchor}:{REGISTRY_REPO_PATH}",
        ),
        "anchor registry blob read",
    )
    if parent_registry == anchor_registry:
        raise TrustRootError("registry anchor does not change the registry bytes")
    head_registry = _checked(
        runner,
        ("--no-replace-objects", "show", f"{head}:{REGISTRY_REPO_PATH}"),
        "HEAD registry blob read",
    )
    if anchor_registry != head_registry or anchor_registry != working_registry_payload:
        raise TrustRootError("registry bytes differ among anchor, HEAD, and working tree")

    ancestry = runner(
        (
            "--no-replace-objects",
            "merge-base",
            "--is-ancestor",
            anchor,
            head,
        )
    )
    if ancestry.returncode != 0 or ancestry.stdout != b"" or ancestry.stderr != b"":
        raise TrustRootError("registry anchor is not an ancestor of HEAD")

    signature_arguments = (
        "--no-replace-objects",
        "-c",
        "gpg.format=ssh",
        "-c",
        f"gpg.ssh.allowedSignersFile={ALLOWED_SIGNERS_GIT_PATH}",
        "-c",
        f"gpg.ssh.program={SSH_KEYGEN_GIT_PATH}",
        "-c",
        "gpg.minTrustLevel=fully",
    )
    verification = runner((*signature_arguments, "verify-commit", "--raw", anchor))
    _validate_verify_output(verification, signer)
    status = _checked(
        runner,
        (
            *signature_arguments,
            "show",
            "-s",
            "--format=%G?%x00%GT%x00%GS%x00%GK%x00%GF",
            anchor,
        ),
        "registry-anchor signature status",
    )
    _parse_signature_status(status, signer)
    final_head = _one_commit(
        _checked(
            runner,
            (
                "--no-replace-objects",
                "rev-parse",
                "--verify",
                "HEAD^{commit}",
            ),
            "terminal HEAD snapshot verification",
        ),
        "terminal HEAD snapshot commit",
    )
    if final_head != head:
        raise TrustRootError("HEAD changed during signed-registry verification")
    return TrustedRegistrySnapshot(
        anchor_commit=anchor,
        parent_commit=parent,
        head_commit=head,
        signing_key_fingerprint=signer.fingerprint,
        registry_payload=anchor_registry,
    )


def verify_signed_registry_anchor(
    repository_root: Path,
    working_registry_payload: bytes,
) -> TrustedRegistrySnapshot:
    """Authenticate the positive registry's externally trusted signed anchor.

    No caller can override the principal, trust path, SSH program, namespace,
    key type, Git configuration, or policy inventory through this interface.
    """
    root = _canonical_repository_root(repository_root)
    try:
        validate_trust_path(TRUST_DIRECTORY, expect_directory=True)
        validate_trust_path(ALLOWED_SIGNERS_PATH, expect_directory=False)
    except WindowsAclError as exc:
        raise TrustRootError("external trust-root custody is invalid") from exc
    if not SSH_KEYGEN_PROGRAM.is_file():
        raise TrustRootError("the frozen OpenSSH verifier is unavailable")
    signer = _load_allowed_signer(ALLOWED_SIGNERS_PATH)
    snapshot = _verify_with_runner(
        runner=_production_runner(root),
        signer=signer,
        working_registry_payload=working_registry_payload,
    )
    registry_path = (root / REGISTRY_REPO_PATH).absolute()
    try:
        resolved_registry_path = registry_path.resolve(strict=True)
        terminal_payload = resolved_registry_path.read_bytes()
    except OSError as exc:
        raise TrustRootError("working registry is unavailable after verification") from exc
    if resolved_registry_path != registry_path or terminal_payload != snapshot.registry_payload:
        raise TrustRootError("working registry changed during signed-registry verification")
    return snapshot


def authority_git(
    repository_root: Path,
    *arguments: str,
    binary: bool = False,
) -> str | bytes:
    """Run an internal authority read with a scrubbed environment.

    Every call ignores replacement objects.  The function is intentionally
    narrow and offers no environment, configuration, executable, or path
    override.
    """
    root = _canonical_repository_root(repository_root)
    payload = _checked(
        _production_runner(root),
        ("--no-replace-objects", *arguments),
        "authority Git read",
    )
    if binary:
        return payload
    try:
        return payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise TrustRootError("authority Git output is not strict UTF-8") from exc


def authority_is_ancestor(
    repository_root: Path,
    ancestor: str,
    descendant: str,
) -> bool:
    root = _canonical_repository_root(repository_root)
    if _COMMIT_RE.fullmatch(ancestor) is None or (
        descendant != "HEAD" and _COMMIT_RE.fullmatch(descendant) is None
    ):
        raise TrustRootError("authority ancestry requires canonical commit names")
    result = _production_runner(root)(
        (
            "--no-replace-objects",
            "merge-base",
            "--is-ancestor",
            ancestor,
            descendant,
        )
    )
    if result.stdout != b"" or result.stderr != b"" or result.returncode not in (0, 1):
        raise TrustRootError("authority ancestry verification failed")
    return result.returncode == 0


def computed_policy_repo_paths(repository_root: Path) -> tuple[str, ...]:
    """Compute the TPR verifier's import-closed signed policy inventory."""
    root = _canonical_repository_root(repository_root)
    result = set(DECLARED_NON_MODULE_POLICY_PATHS)
    try:
        closure = validate_transitive_import_closure(root)
    except ImportBoundaryError as exc:
        raise TrustRootError("signed policy import closure is invalid") from exc
    for module in closure:
        relative = Path(*module.split("."))
        for candidate in (relative.with_suffix(".py"), relative / "__init__.py"):
            if (root / candidate).is_file():
                result.add(candidate.as_posix())
                break
        else:  # pragma: no cover - the closure validates every local source
            raise TrustRootError(f"policy module has no source file: {module}")
    return tuple(sorted(result))
