from __future__ import annotations

import base64
import dataclasses
import hashlib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest

import research.target_price_revisions.trust_root as trust_root


ANCHOR = "a" * 40
PARENT = "b" * 40
OTHER = "c" * 40
HEAD = "d" * 40
PARENT_REGISTRY = b'{"entries":[],"generation":"parent"}\n'
ANCHOR_REGISTRY = b'{"entries":[],"generation":"anchor"}\n'

SHALLOW_ARGS = ("rev-parse", "--is-shallow-repository")
HEAD_ARGS = (
    "--no-replace-objects",
    "rev-parse",
    "--verify",
    "HEAD^{commit}",
)
ANCHOR_ARGS = (
    "--no-replace-objects",
    "log",
    "-1",
    "--format=%H",
    HEAD,
    "--",
    trust_root.REGISTRY_REPO_PATH,
)
PARENT_ARGS = (
    "--no-replace-objects",
    "rev-list",
    "--parents",
    "-n",
    "1",
    ANCHOR,
)
CHANGED_PATHS_ARGS = (
    "--no-replace-objects",
    "diff-tree",
    "--no-commit-id",
    "--name-only",
    "-r",
    f"{ANCHOR}^",
    ANCHOR,
)
PARENT_REGISTRY_ARGS = (
    "--no-replace-objects",
    "show",
    f"{ANCHOR}^:{trust_root.REGISTRY_REPO_PATH}",
)
ANCHOR_REGISTRY_ARGS = (
    "--no-replace-objects",
    "show",
    f"{ANCHOR}:{trust_root.REGISTRY_REPO_PATH}",
)
HEAD_REGISTRY_ARGS = (
    "--no-replace-objects",
    "show",
    f"{HEAD}:{trust_root.REGISTRY_REPO_PATH}",
)
ANCESTRY_ARGS = (
    "--no-replace-objects",
    "merge-base",
    "--is-ancestor",
    ANCHOR,
    HEAD,
)
SIGNATURE_PREFIX = (
    "--no-replace-objects",
    "-c",
    "gpg.format=ssh",
    "-c",
    f"gpg.ssh.allowedSignersFile={trust_root.ALLOWED_SIGNERS_GIT_PATH}",
    "-c",
    f"gpg.ssh.program={trust_root.SSH_KEYGEN_GIT_PATH}",
    "-c",
    "gpg.minTrustLevel=fully",
)
VERIFY_ARGS = (*SIGNATURE_PREFIX, "verify-commit", "--raw", ANCHOR)
STATUS_ARGS = (
    *SIGNATURE_PREFIX,
    "show",
    "-s",
    "--format=%G?%x00%GT%x00%GS%x00%GK%x00%GF",
    ANCHOR,
)
EXPECTED_CALLS = (
    SHALLOW_ARGS,
    HEAD_ARGS,
    ANCHOR_ARGS,
    PARENT_ARGS,
    CHANGED_PATHS_ARGS,
    PARENT_REGISTRY_ARGS,
    ANCHOR_REGISTRY_ARGS,
    HEAD_REGISTRY_ARGS,
    ANCESTRY_ARGS,
    VERIFY_ARGS,
    STATUS_ARGS,
    HEAD_ARGS,
)
COMMON_DIR_ARGS = (
    "--no-replace-objects",
    "rev-parse",
    "--path-format=absolute",
    "--git-common-dir",
)


@dataclasses.dataclass
class _FakeGitRunner:
    results: Mapping[tuple[str, ...], trust_root._GitResult]
    calls: list[tuple[str, ...]] = dataclasses.field(default_factory=list)

    def __call__(self, arguments: Sequence[str]) -> trust_root._GitResult:
        key = tuple(arguments)
        self.calls.append(key)
        if key not in self.results:
            raise AssertionError(f"unexpected Git invocation: {key!r}")
        return self.results[key]


@dataclasses.dataclass
class _HeadFlipRunner:
    results: Mapping[tuple[str, ...], trust_root._GitResult]
    calls: list[tuple[str, ...]] = dataclasses.field(default_factory=list)
    head_reads: int = 0

    def __call__(self, arguments: Sequence[str]) -> trust_root._GitResult:
        key = tuple(arguments)
        self.calls.append(key)
        if key == HEAD_ARGS:
            self.head_reads += 1
            if self.head_reads == 2:
                return trust_root._GitResult(
                    0, f"{OTHER}\n".encode("ascii"), b""
                )
        return self.results[key]


def _wire_field(value: bytes) -> bytes:
    return len(value).to_bytes(4, "big") + value


def _ed25519_blob(key_material: bytes = bytes(range(32))) -> bytes:
    return _wire_field(b"ssh-ed25519") + _wire_field(key_material)


def _signer_payload_for_blob(blob: bytes) -> bytes:
    encoded = base64.b64encode(blob)
    return (
        b'shelton-tpr-reviewer namespaces="git" ssh-ed25519 '
        + encoded
        + b"\n"
    )


def _valid_signer() -> trust_root.TrustedSigner:
    return trust_root._parse_allowed_signer(_signer_payload_for_blob(_ed25519_blob()))


def _signature_status(
    signer: trust_root.TrustedSigner,
    *,
    status: str = "G",
    level: str = "fully",
    principal: str | None = None,
    key_identifier: str | None = None,
    fingerprint: str | None = None,
) -> bytes:
    fields = (
        status,
        level,
        signer.principal if principal is None else principal,
        signer.fingerprint if key_identifier is None else key_identifier,
        signer.fingerprint if fingerprint is None else fingerprint,
    )
    return "\0".join(fields).encode("ascii") + b"\n"


def _valid_results(
    signer: trust_root.TrustedSigner,
) -> dict[tuple[str, ...], trust_root._GitResult]:
    good_signature = (
        f'Good "git" signature for {signer.principal} with ED25519 key '
        f"{signer.fingerprint}\n"
    ).encode("ascii")
    return {
        SHALLOW_ARGS: trust_root._GitResult(0, b"false\n", b""),
        HEAD_ARGS: trust_root._GitResult(0, f"{HEAD}\n".encode("ascii"), b""),
        ANCHOR_ARGS: trust_root._GitResult(0, f"{ANCHOR}\n".encode("ascii"), b""),
        PARENT_ARGS: trust_root._GitResult(
            0, f"{ANCHOR} {PARENT}\n".encode("ascii"), b""
        ),
        CHANGED_PATHS_ARGS: trust_root._GitResult(
            0, f"{trust_root.REGISTRY_REPO_PATH}\n".encode("ascii"), b""
        ),
        PARENT_REGISTRY_ARGS: trust_root._GitResult(0, PARENT_REGISTRY, b""),
        ANCHOR_REGISTRY_ARGS: trust_root._GitResult(0, ANCHOR_REGISTRY, b""),
        HEAD_REGISTRY_ARGS: trust_root._GitResult(0, ANCHOR_REGISTRY, b""),
        ANCESTRY_ARGS: trust_root._GitResult(0, b"", b""),
        VERIFY_ARGS: trust_root._GitResult(0, b"", good_signature),
        STATUS_ARGS: trust_root._GitResult(
            0, _signature_status(signer), b""
        ),
    }


def _verify(
    *,
    changes: Mapping[tuple[str, ...], trust_root._GitResult] | None = None,
    working_registry_payload: bytes = ANCHOR_REGISTRY,
) -> tuple[trust_root.TrustedRegistrySnapshot, _FakeGitRunner]:
    signer = _valid_signer()
    results = _valid_results(signer)
    if changes:
        results.update(changes)
    runner = _FakeGitRunner(results)
    snapshot = trust_root._verify_with_runner(
        runner=runner,
        signer=signer,
        working_registry_payload=working_registry_payload,
    )
    return snapshot, runner


def test_valid_signed_registry_anchor_returns_exact_immutable_snapshot() -> None:
    signer = _valid_signer()
    snapshot, runner = _verify()

    assert snapshot == trust_root.TrustedRegistrySnapshot(
        anchor_commit=ANCHOR,
        parent_commit=PARENT,
        head_commit=HEAD,
        signing_key_fingerprint=signer.fingerprint,
        registry_payload=ANCHOR_REGISTRY,
    )
    assert tuple(runner.calls) == EXPECTED_CALLS
    assert all(
        call == SHALLOW_ARGS or call[0] == "--no-replace-objects"
        for call in runner.calls
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        snapshot.anchor_commit = OTHER


def test_head_move_during_verification_refuses() -> None:
    signer = _valid_signer()
    runner = _HeadFlipRunner(_valid_results(signer))
    with pytest.raises(trust_root.TrustRootError, match="HEAD changed"):
        trust_root._verify_with_runner(
            runner=runner,
            signer=signer,
            working_registry_payload=ANCHOR_REGISTRY,
        )


@pytest.mark.parametrize(
    "result",
    [
        trust_root._GitResult(0, b"true\n", b""),
        trust_root._GitResult(0, b"false\r\n", b""),
        trust_root._GitResult(1, b"", b""),
        trust_root._GitResult(0, b"false\n", b"warning\n"),
    ],
)
def test_shallow_or_ambiguous_repository_probe_refuses(
    result: trust_root._GitResult,
) -> None:
    with pytest.raises(trust_root.TrustRootError):
        _verify(changes={SHALLOW_ARGS: result})


@pytest.mark.parametrize(
    "parent_record",
    [
        f"{ANCHOR}\n".encode("ascii"),
        f"{ANCHOR} {PARENT} {OTHER}\n".encode("ascii"),
        f"{OTHER} {PARENT}\n".encode("ascii"),
        f"{ANCHOR} {PARENT}\r\n".encode("ascii"),
        f"{ANCHOR} {PARENT.upper()}\n".encode("ascii"),
    ],
)
def test_root_merge_or_malformed_parent_record_refuses(parent_record: bytes) -> None:
    with pytest.raises(trust_root.TrustRootError, match="one non-merge commit"):
        _verify(
            changes={PARENT_ARGS: trust_root._GitResult(0, parent_record, b"")}
        )


@pytest.mark.parametrize(
    "changed_paths",
    [
        b"",
        b"README.md\n",
        (trust_root.REGISTRY_REPO_PATH + "\nREADME.md\n").encode("ascii"),
        (trust_root.REGISTRY_REPO_PATH + "\r\n").encode("ascii"),
    ],
)
def test_changed_path_inventory_must_be_exact(changed_paths: bytes) -> None:
    with pytest.raises(trust_root.TrustRootError, match="change only"):
        _verify(
            changes={
                CHANGED_PATHS_ARGS: trust_root._GitResult(0, changed_paths, b"")
            }
        )


def test_parent_and_anchor_registry_must_differ() -> None:
    with pytest.raises(trust_root.TrustRootError, match="does not change"):
        _verify(
            changes={
                PARENT_REGISTRY_ARGS: trust_root._GitResult(
                    0, ANCHOR_REGISTRY, b""
                )
            }
        )


@pytest.mark.parametrize(
    ("changes", "working_registry_payload"),
    [
        (
            {HEAD_REGISTRY_ARGS: trust_root._GitResult(0, b"different HEAD\n", b"")},
            ANCHOR_REGISTRY,
        ),
        ({}, b"different worktree\n"),
    ],
)
def test_anchor_head_and_worktree_registry_bytes_must_match(
    changes: Mapping[tuple[str, ...], trust_root._GitResult],
    working_registry_payload: bytes,
) -> None:
    with pytest.raises(trust_root.TrustRootError, match="anchor, HEAD, and working"):
        _verify(changes=changes, working_registry_payload=working_registry_payload)


@pytest.mark.parametrize(
    "arguments",
    [PARENT_REGISTRY_ARGS, ANCHOR_REGISTRY_ARGS, HEAD_REGISTRY_ARGS],
)
def test_any_registry_blob_read_failure_refuses(arguments: tuple[str, ...]) -> None:
    with pytest.raises(trust_root.TrustRootError, match="blob read failed closed"):
        _verify(
            changes={arguments: trust_root._GitResult(128, b"", b"fatal\n")}
        )


@pytest.mark.parametrize(
    "result",
    [
        trust_root._GitResult(1, b"", b""),
        trust_root._GitResult(0, b"unexpected\n", b""),
        trust_root._GitResult(0, b"", b"warning\n"),
        trust_root._GitResult(2, b"", b"fatal\n"),
    ],
)
def test_noncanonical_or_failed_ancestry_check_refuses(
    result: trust_root._GitResult,
) -> None:
    with pytest.raises(trust_root.TrustRootError, match="not an ancestor"):
        _verify(changes={ANCESTRY_ARGS: result})


@pytest.mark.parametrize(
    "result_factory",
    [
        lambda good: trust_root._GitResult(1, b"", good),
        lambda good: trust_root._GitResult(0, b"unexpected", good),
        lambda good: trust_root._GitResult(0, b"", b""),
        lambda good: trust_root._GitResult(0, b"", good + b"extra\n"),
        lambda good: trust_root._GitResult(
            0, b"", good.replace(b"ED25519", b"RSA", 1)
        ),
    ],
)
def test_bad_verify_commit_output_refuses(
    result_factory: Callable[[bytes], trust_root._GitResult],
) -> None:
    signer = _valid_signer()
    good = _valid_results(signer)[VERIFY_ARGS].stderr
    result = result_factory(good)
    with pytest.raises(trust_root.TrustRootError, match="signature verification"):
        _verify(changes={VERIFY_ARGS: result})


@pytest.mark.parametrize(
    "status_changes",
    [
        {"status": "N"},
        {"level": "marginal"},
        {"principal": "some-other-reviewer"},
        {"key_identifier": "SHA256:" + "A" * 43},
        {"fingerprint": "SHA256:" + "B" * 43},
    ],
)
def test_bad_status_trust_principal_key_or_fingerprint_refuses(
    status_changes: Mapping[str, str],
) -> None:
    signer = _valid_signer()
    payload = _signature_status(signer, **status_changes)
    with pytest.raises(trust_root.TrustRootError, match="does not match"):
        _verify(
            changes={STATUS_ARGS: trust_root._GitResult(0, payload, b"")}
        )


@pytest.mark.parametrize(
    "payload_factory",
    [
        lambda valid: valid.removesuffix(b"\n"),
        lambda valid: valid.replace(b"\n", b"\r\n"),
        lambda valid: valid.replace(b"\0fully\0", b"\0\0", 1),
        lambda valid: valid.removesuffix(b"\n") + b"\0extra\n",
        lambda valid: b"\xff" + valid[1:],
    ],
)
def test_malformed_signature_status_record_refuses(
    payload_factory: Callable[[bytes], bytes],
) -> None:
    signer = _valid_signer()
    payload = payload_factory(_signature_status(signer))
    with pytest.raises(trust_root.TrustRootError, match="status is malformed"):
        _verify(
            changes={STATUS_ARGS: trust_root._GitResult(0, payload, b"")}
        )


def test_valid_allowed_signer_is_parsed_and_fingerprinted_exactly() -> None:
    blob = _ed25519_blob()
    signer = trust_root._parse_allowed_signer(_signer_payload_for_blob(blob))

    expected_fingerprint = "SHA256:" + base64.b64encode(
        hashlib.sha256(blob).digest()
    ).decode("ascii").rstrip("=")
    assert signer == trust_root.TrustedSigner(
        principal=trust_root.SIGNER_PRINCIPAL,
        namespace=trust_root.SIGNATURE_NAMESPACE,
        key_type=trust_root.SIGNING_KEY_TYPE,
        public_key_base64=base64.b64encode(blob).decode("ascii"),
        fingerprint=expected_fingerprint,
    )


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        _signer_payload_for_blob(_ed25519_blob()).removesuffix(b"\n"),
        _signer_payload_for_blob(_ed25519_blob()) + b"\n",
        b"# comment\n" + _signer_payload_for_blob(_ed25519_blob()),
        _signer_payload_for_blob(_ed25519_blob()) * 2,
        _signer_payload_for_blob(_ed25519_blob()).replace(
            b"shelton-tpr-reviewer", b"other-reviewer", 1
        ),
        _signer_payload_for_blob(_ed25519_blob()).replace(
            b'namespaces="git"', b'namespaces="file"', 1
        ),
        b'shelton-tpr-reviewer namespaces="git" ssh-ed25519 !!!\n',
        _signer_payload_for_blob(_wire_field(b"ssh-rsa") + _wire_field(bytes(32))),
        _signer_payload_for_blob(_ed25519_blob(bytes(31))),
        _signer_payload_for_blob(_ed25519_blob() + b"trailing"),
        _signer_payload_for_blob(_ed25519_blob()).replace(
            base64.b64encode(_ed25519_blob()),
            base64.b64encode(_ed25519_blob()) + b"=",
            1,
        ),
    ],
)
def test_malformed_allowed_signers_content_refuses(payload: bytes) -> None:
    with pytest.raises(trust_root.TrustRootError):
        trust_root._parse_allowed_signer(payload)


def test_non_bytes_allowed_signers_and_working_registry_refuse() -> None:
    with pytest.raises(trust_root.TrustRootError, match="exact bytes"):
        trust_root._parse_allowed_signer("not bytes")

    signer = _valid_signer()
    with pytest.raises(trust_root.TrustRootError, match="working registry"):
        trust_root._verify_with_runner(
            runner=_FakeGitRunner(_valid_results(signer)),
            signer=signer,
            working_registry_payload="not bytes",
        )


@pytest.mark.parametrize(
    "name",
    [
        "GIT_CONFIG_COUNT",
        "git_config_key_0",
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_REPLACE_REF_BASE",
        "GIT_NO_REPLACE_OBJECTS",
        "GIT_SHALLOW_FILE",
    ],
)
def test_caller_git_configuration_object_and_replacement_overrides_refuse(
    name: str,
) -> None:
    with pytest.raises(trust_root.TrustRootError, match="forbidden"):
        trust_root._secure_git_environment({name: "attacker-controlled"})


def test_secure_git_environment_keeps_only_safe_inputs_and_fixed_controls() -> None:
    environment = trust_root._secure_git_environment(
        {
            "PATH": r"C:\trusted-bin",
            "SYSTEMROOT": r"C:\Windows",
            "UNRELATED_SECRET": "must-not-propagate",
            "LC_ALL": "caller-controlled",
        }
    )

    assert environment == {
        "SYSTEMROOT": r"C:\Windows",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C",
    }


def test_public_verifier_uses_only_fixed_custody_and_trust_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path.absolute()
    (root / ".git").mkdir()
    registry_path = root / trust_root.REGISTRY_REPO_PATH
    registry_path.parent.mkdir(parents=True)
    registry_path.write_bytes(ANCHOR_REGISTRY)
    synthetic_tool = root / "ssh-keygen.exe"
    synthetic_tool.write_bytes(b"synthetic executable marker")
    signer = _valid_signer()
    runner = _FakeGitRunner(_valid_results(signer))
    custody_calls: list[tuple[Path, bool]] = []
    signer_calls: list[Path] = []

    def validate(path: Path, *, expect_directory: bool) -> None:
        custody_calls.append((path, expect_directory))

    def load(path: Path) -> trust_root.TrustedSigner:
        signer_calls.append(path)
        return signer

    monkeypatch.setattr(trust_root, "validate_trust_path", validate)
    monkeypatch.setattr(trust_root, "_load_allowed_signer", load)
    monkeypatch.setattr(trust_root, "SSH_KEYGEN_PROGRAM", synthetic_tool)
    monkeypatch.setattr(trust_root, "_production_runner", lambda path: runner)

    snapshot = trust_root.verify_signed_registry_anchor(root, ANCHOR_REGISTRY)

    assert snapshot.anchor_commit == ANCHOR
    assert custody_calls == [
        (trust_root.TRUST_DIRECTORY, True),
        (trust_root.ALLOWED_SIGNERS_PATH, False),
    ]
    assert signer_calls == [trust_root.ALLOWED_SIGNERS_PATH]
    assert tuple(runner.calls) == EXPECTED_CALLS
    assert trust_root.ALLOWED_SIGNERS_PATH == Path(
        r"C:\ProgramData\CustomizedAgent\trust\tpr_allowed_signers"
    )
    assert trust_root.SSH_KEYGEN_GIT_PATH == (
        "C:/Windows/System32/OpenSSH/ssh-keygen.exe"
    )
    assert trust_root.GIT_PROGRAM == Path(r"C:\Program Files\Git\cmd\git.exe")


def test_git_invocation_uses_the_frozen_absolute_program_not_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frozen_program = Path(r"C:\Program Files\Git\cmd\git.exe")
    calls: list[tuple[list[str], dict[str, object]]] = []

    def run(command: list[str], **keywords: object) -> trust_root._GitResult:
        calls.append((command, keywords))
        return trust_root._GitResult(0, b"expected\n", b"")

    monkeypatch.setattr(trust_root.subprocess, "run", run)
    result = trust_root._invoke_git(
        frozen_program,
        tmp_path,
        ("rev-parse", "--is-shallow-repository"),
        {"PATH": r"C:\attacker-controlled"},
    )

    assert result == trust_root._GitResult(0, b"expected\n", b"")
    command, keywords = calls[0]
    assert command[0] == str(frozen_program)
    assert command[0] != "git"
    assert keywords["shell"] is False
    assert keywords["env"] == {"PATH": r"C:\attacker-controlled"}


def test_frozen_git_program_must_exist_as_an_unredirected_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "missing-git.exe"
    monkeypatch.setattr(trust_root, "GIT_PROGRAM", missing)
    with pytest.raises(trust_root.TrustRootError, match="unavailable"):
        trust_root._canonical_frozen_git_program()

    directory = tmp_path / "git.exe"
    directory.mkdir()
    monkeypatch.setattr(trust_root, "GIT_PROGRAM", directory)
    with pytest.raises(trust_root.TrustRootError, match="canonical"):
        trust_root._canonical_frozen_git_program()


def test_production_runner_disables_commit_graph_for_every_git_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path.absolute()
    common = root / ".git"
    (common / "info").mkdir(parents=True)
    program = Path(r"C:\Program Files\Git\cmd\git.exe")
    captured: list[tuple[str, ...]] = []

    def invoke(
        supplied_program: Path,
        supplied_root: Path,
        arguments: Sequence[str],
        environment: Mapping[str, str],
    ) -> trust_root._GitResult:
        assert supplied_program == program
        assert supplied_root == root
        captured.append(tuple(arguments))
        if tuple(arguments[2:]) == COMMON_DIR_ARGS:
            return trust_root._GitResult(
                0, (str(common) + "\n").encode("utf-8"), b""
            )
        return trust_root._GitResult(0, b"false\n", b"")

    monkeypatch.setattr(trust_root, "_secure_git_environment", lambda: {})
    monkeypatch.setattr(trust_root, "_canonical_frozen_git_program", lambda: program)
    monkeypatch.setattr(trust_root, "_invoke_git", invoke)

    runner = trust_root._production_runner(root)
    assert runner(SHALLOW_ARGS).stdout == b"false\n"
    assert captured == [
        (*trust_root._AUTHORITY_GIT_PREFIX, *COMMON_DIR_ARGS),
        (*trust_root._AUTHORITY_GIT_PREFIX, *SHALLOW_ARGS),
    ]

def test_legacy_git_grafts_are_absent_before_authority_reads(tmp_path: Path) -> None:
    common = (tmp_path / ".git").absolute()
    (common / "info").mkdir(parents=True)
    runner = _FakeGitRunner(
        {
            COMMON_DIR_ARGS: trust_root._GitResult(
                0, (str(common) + "\n").encode("utf-8"), b""
            )
        }
    )

    trust_root._reject_legacy_grafts(runner)
    assert runner.calls == [COMMON_DIR_ARGS]

    (common / "info" / "grafts").write_text("synthetic graft\n", encoding="utf-8")
    with pytest.raises(trust_root.TrustRootError, match="grafts are forbidden"):
        trust_root._reject_legacy_grafts(runner)


@pytest.mark.parametrize(
    "payload",
    [b"relative/.git\n", b"C:/one/.git\nC:/two/.git\n", b"C:/bad/.git\r\n"],
)
def test_malformed_git_common_directory_refuses(
    tmp_path: Path, payload: bytes
) -> None:
    runner = _FakeGitRunner(
        {COMMON_DIR_ARGS: trust_root._GitResult(0, payload, b"")}
    )
    with pytest.raises(trust_root.TrustRootError, match="common directory"):
        trust_root._reject_legacy_grafts(runner)


def test_public_verifier_translates_invalid_acl_and_missing_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path.absolute()
    (root / ".git").mkdir()

    def invalid_acl(path: Path, *, expect_directory: bool) -> None:
        raise trust_root.WindowsAclError("synthetic unsafe ACL")

    monkeypatch.setattr(trust_root, "validate_trust_path", invalid_acl)
    with pytest.raises(trust_root.TrustRootError, match="custody"):
        trust_root.verify_signed_registry_anchor(root, ANCHOR_REGISTRY)

    monkeypatch.setattr(
        trust_root,
        "validate_trust_path",
        lambda path, *, expect_directory: None,
    )
    monkeypatch.setattr(trust_root, "SSH_KEYGEN_PROGRAM", root / "missing.exe")
    with pytest.raises(trust_root.TrustRootError, match="verifier is unavailable"):
        trust_root.verify_signed_registry_anchor(root, ANCHOR_REGISTRY)


def test_missing_external_signer_refuses_like_an_unprovisioned_host(
    tmp_path: Path,
) -> None:
    with pytest.raises(trust_root.TrustRootError, match="unavailable"):
        trust_root._load_allowed_signer(tmp_path / "missing_allowed_signers")


@pytest.mark.parametrize("root", ["not-a-path", Path("missing-repository")])
def test_repository_root_requires_a_canonical_existing_git_path(root: object) -> None:
    with pytest.raises(trust_root.TrustRootError, match="repository root"):
        trust_root._canonical_repository_root(root)


def _write_module(root: Path, module: str, *, package: bool = False) -> None:
    relative = Path(*module.split("."))
    path = (
        root / relative / "__init__.py"
        if package
        else root / relative.with_suffix(".py")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# synthetic policy module\n", encoding="utf-8")


def test_computed_policy_paths_use_import_closure_and_declared_nonmodules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path.absolute()
    (root / ".git").mkdir()
    _write_module(root, "research", package=True)
    _write_module(root, "research.target_price_revisions", package=True)
    _write_module(root, "research.target_price_revisions.trust_root")
    _write_module(root, "research.target_price_revisions.windows_acl")
    closure = (
        "research.target_price_revisions.windows_acl",
        "research",
        "research.target_price_revisions.trust_root",
        "research.target_price_revisions",
    )
    monkeypatch.setattr(
        trust_root,
        "validate_transitive_import_closure",
        lambda repository_root: closure,
    )

    assert trust_root.computed_policy_repo_paths(root) == tuple(
        sorted(
            {
                "research/__init__.py",
                "research/target_price_revisions/__init__.py",
                "research/target_price_revisions/trust_root.py",
                "research/target_price_revisions/windows_acl.py",
                "research/target_price_revisions/specs/.gitattributes",
            }
        )
    )


def test_computed_policy_paths_refuse_closure_member_without_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path.absolute()
    (root / ".git").mkdir()
    monkeypatch.setattr(
        trust_root,
        "validate_transitive_import_closure",
        lambda repository_root: ("research.target_price_revisions.missing",),
    )

    with pytest.raises(trust_root.TrustRootError, match="has no source file"):
        trust_root.computed_policy_repo_paths(root)


def test_computed_policy_paths_translate_an_invalid_import_closure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path.absolute()
    (root / ".git").mkdir()

    def invalid_closure(repository_root: Path) -> tuple[str, ...]:
        raise trust_root.ImportBoundaryError("synthetic forbidden import")

    monkeypatch.setattr(
        trust_root, "validate_transitive_import_closure", invalid_closure
    )
    with pytest.raises(trust_root.TrustRootError, match="import closure"):
        trust_root.computed_policy_repo_paths(root)
