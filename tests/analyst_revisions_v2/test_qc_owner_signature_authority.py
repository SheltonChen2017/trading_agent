from __future__ import annotations

import ast
import base64
import builtins
import dataclasses
import dis
import hashlib
import json
import os
import shutil
import signal
import stat
import subprocess
import tempfile
from pathlib import Path
from types import CodeType, FunctionType, MappingProxyType, SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import owner_signature_authority as authority


SSH_KEYGEN = Path("/usr/bin/ssh-keygen")
POSIX_RUNNER_AVAILABLE = all(
    hasattr(os, name)
    for name in (
        "getuid", "kill", "pipe", "posix_spawn", "waitpid",
        "waitstatus_to_exitcode", "POSIX_SPAWN_OPEN", "POSIX_SPAWN_DUP2",
        "WNOHANG",
    )
) and hasattr(signal, "SIGKILL")
POSIX_ONLY = pytest.mark.skipif(
    not POSIX_RUNNER_AVAILABLE,
    reason="owner-signature process boundary is POSIX-only",
)
OWNER_UID_FOR_TEST = getattr(os, "getuid", lambda: 501)() or 501


def _private_file(path: Path, payload: bytes) -> Path:
    path.write_bytes(payload)
    path.chmod(0o600)
    return path


def _public_key_parts(public_path: Path) -> tuple[str, str]:
    parts = public_path.read_text(encoding="ascii").strip().split()
    assert len(parts) >= 2
    assert parts[0] == "ssh-ed25519"
    return parts[0], parts[1]


def _pin(public_key_base64: str, *purposes: str) -> authority._ReviewedOwnerPublicKey:
    blob = base64.b64decode(public_key_base64, validate=True)
    return authority._ReviewedOwnerPublicKey(
        key_id="arv2-owner-ed25519-" + hashlib.sha256(blob).hexdigest()[:16],
        public_key_base64=public_key_base64,
        purposes=tuple(purposes),
    )


def _keypair(root: Path, name: str = "owner") -> tuple[Path, str]:
    private = root / name
    completed = subprocess.run(
        (
            str(SSH_KEYGEN), "-q", "-t", "ed25519", "-N", "",
            "-C", "ARV2 fixture only", "-f", str(private),
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    _, public_key_base64 = _public_key_parts(private.with_suffix(".pub"))
    return private, public_key_base64


def _signed_controls(
    root: Path,
    *,
    private_key: Path,
    public_key_base64: str,
    payload: bytes,
    namespace: str,
    stem: str = "authority",
) -> tuple[Path, Path]:
    message = _private_file(root / f"{stem}.json", payload)
    completed = subprocess.run(
        (
            str(SSH_KEYGEN), "-Y", "sign", "-f", str(private_key),
            "-n", namespace, str(message),
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    signature = message.with_name(message.name + ".sig")
    signature.chmod(0o600)
    allowed = _private_file(
        root / f"{stem}.allowed_signers",
        f"{authority.PRINCIPAL} ssh-ed25519 {public_key_base64}\n".encode("ascii"),
    )
    return allowed, signature


def _verify_fixture_signature(
    *,
    purpose: str,
    authority_payload: bytes,
    allowed_signers_path: Path,
    signature_path: Path,
    reviewed_pins: tuple[authority._ReviewedOwnerPublicKey, ...],
    _purpose_namespaces=authority.PURPOSE_NAMESPACES,
    _read_private_file=authority._read_private_stable_file,
    _select_pin=authority._select_reviewed_pin,
    _validate_envelope=authority._validate_signature_envelope,
    _snapshot_verifier=authority._snapshot_trusted_verifier,
    _run_verify=authority._run_ssh_keygen_verify,
    _require_verifier_unchanged=authority._require_verifier_unchanged,
) -> dict[str, object]:
    """Exercise fixture-key crypto without publishing an authority minter."""

    allowed = _read_private_file(
        allowed_signers_path,
        maximum_bytes=authority.MAX_ALLOWED_SIGNERS_BYTES,
        name="owner allowed-signers file",
    )
    signature = _read_private_file(
        signature_path,
        maximum_bytes=authority.MAX_SIGNATURE_BYTES,
        name="owner detached-signature file",
    )
    pin, public_blob = _select_pin(allowed._content, purpose, reviewed_pins)
    _validate_envelope(signature._content)
    verifier = _snapshot_verifier()
    namespace = _purpose_namespaces[purpose]
    _run_verify(
        authority_payload=authority_payload,
        allowed_signers=allowed._content,
        signature=signature._content,
        namespace=namespace,
        verifier_path=verifier[0],
    )
    allowed_after = _read_private_file(
        allowed_signers_path,
        maximum_bytes=authority.MAX_ALLOWED_SIGNERS_BYTES,
        name="owner allowed-signers file",
    )
    signature_after = _read_private_file(
        signature_path,
        maximum_bytes=authority.MAX_SIGNATURE_BYTES,
        name="owner detached-signature file",
    )
    _require_verifier_unchanged(verifier)
    if allowed_after != allowed or signature_after != signature:
        raise authority.OwnerSignatureAuthorityError(
            "owner signature controls changed during verification"
        )
    return {
        "purpose": purpose,
        "namespace": namespace,
        "principal": authority.PRINCIPAL,
        "reviewed_key_id": pin.key_id,
        "public_key_blob_sha256": hashlib.sha256(public_blob).hexdigest(),
        "authority_payload_sha256": hashlib.sha256(authority_payload).hexdigest(),
        "allowed_signers_path": allowed.path,
        "signature_path": signature.path,
        "verifier_path": verifier[0],
    }


def test_production_registry_keeps_power_calibration_purpose_unpinned():
    assert len(authority._REVIEWED_OWNER_PUBLIC_KEYS) == 1
    pin = authority._REVIEWED_OWNER_PUBLIC_KEYS[0]
    blob, allowed = authority._validate_reviewed_pin(pin)

    assert pin.key_id == "arv2-owner-ed25519-21d1ae9d964ec350"
    assert hashlib.sha256(blob).hexdigest() == (
        "21d1ae9d964ec3503e483135254bfff4e25781de75fbad4413f0d0b71211f77e"
    )
    assert pin.purposes == (
        authority.FORMAL_EXECUTION_PURPOSE,
        authority.FORMAL_RESULT_READ_PURPOSE,
        authority.PREOPEN_EXECUTION_PURPOSE,
        authority.PREOPEN_ACQUISITION_REVIEW_PURPOSE,
        authority.PRODUCTION_EVIDENCE_REVIEW_PURPOSE,
    )
    assert authority.POWER_CALIBRATION_EXECUTION_PURPOSE not in pin.purposes
    assert allowed == (
        b"arv2-owner ssh-ed25519 "
        b"AAAAC3NzaC1lZDI1NTE5AAAAIA2kYwmz2Tc/F2tfAqo7xQlM/doV0nI1viXyOvUkcsQE\n"
    )


@pytest.fixture
def signer(tmp_path):
    if not SSH_KEYGEN.is_file():
        pytest.skip("fixed OpenSSH verifier is unavailable")
    private, public_key_base64 = _keypair(tmp_path)
    return private, public_key_base64


@pytest.mark.parametrize(
    ("purpose", "namespace"), tuple(authority.PURPOSE_NAMESPACES.items())
)
def test_fixture_signature_verifies_twice_for_one_exact_gate(
    tmp_path, signer, purpose, namespace,
):
    private, public_key_base64 = signer
    payload = (
        b'{"authority":"exact-reviewed-bytes","purpose":"'
        + purpose.encode("ascii")
        + b'"}\n'
    )
    allowed, signature = _signed_controls(
        tmp_path,
        private_key=private,
        public_key_base64=public_key_base64,
        payload=payload,
        namespace=namespace,
        stem=purpose,
    )
    pin = _pin(public_key_base64, purpose)

    loaded = _verify_fixture_signature(
        purpose=purpose,
        authority_payload=payload,
        allowed_signers_path=allowed,
        signature_path=signature,
        reviewed_pins=(pin,),
    )

    assert loaded["purpose"] == purpose
    assert loaded["namespace"] == namespace
    assert loaded["principal"] == "arv2-owner"
    assert loaded["reviewed_key_id"] == pin.key_id
    assert loaded["authority_payload_sha256"] == hashlib.sha256(payload).hexdigest()
    assert loaded["allowed_signers_path"] == allowed
    assert loaded["signature_path"] == signature
    assert _verify_fixture_signature(
        purpose=purpose,
        authority_payload=payload,
        allowed_signers_path=allowed,
        signature_path=signature,
        reviewed_pins=(pin,),
    ) == loaded


def test_production_registry_rejects_an_unreviewed_key_supplied_by_caller(
    tmp_path, signer, monkeypatch,
):
    private, public_key_base64 = signer
    purpose = authority.FORMAL_EXECUTION_PURPOSE
    payload = b'{"formal_execution":"reviewed-candidate"}\n'
    allowed, signature = _signed_controls(
        tmp_path,
        private_key=private,
        public_key_base64=public_key_base64,
        payload=payload,
        namespace=authority.PURPOSE_NAMESPACES[purpose],
    )
    calls = []
    monkeypatch.setattr(authority, "_run_ssh_keygen_verify", lambda **kwargs: calls.append(kwargs))

    with pytest.raises(authority.OwnerSignatureAuthorityError, match="no unique independently"):
        authority.load_formal_execution_owner_signature(
            authority_payload=payload,
            allowed_signers_path=allowed,
            signature_path=signature,
        )

    assert calls == []
    assert authority.reviewed_owner_signature_registry_status() == {
        "schema": "arv2-owner-signature-authority-v1",
        "reviewed_key_count": 1,
        "gate_key_counts": {
            "formal_qc_execution": 1,
            "formal_qc_result_read": 1,
            "preopen_qc_execution": 1,
            "preopen_control_acquisition_review": 1,
            "production_evidence_review": 1,
            "power_calibration_qc_execution": 0,
        },
        "all_positive_paths_enabled": False,
        "production_signing_implemented": False,
        "private_key_access_implemented": False,
    }
    assert "reviewed_pins" not in authority.load_formal_execution_owner_signature.__annotations__


def test_rebinding_pin_selector_and_crypto_runner_cannot_admit_attacker_key(
    tmp_path, signer, monkeypatch,
):
    private, public_key_base64 = signer
    purpose = authority.FORMAL_EXECUTION_PURPOSE
    payload = b'{"formal_execution":"attacker-key"}\n'
    allowed, signature = _signed_controls(
        tmp_path,
        private_key=private,
        public_key_base64=public_key_base64,
        payload=payload,
        namespace=authority.PURPOSE_NAMESPACES[purpose],
    )
    pin = _pin(public_key_base64, purpose)
    selector_calls = []
    verifier_calls = []

    def forged_selector(*args, **kwargs):
        selector_calls.append((args, kwargs))
        return pin, base64.b64decode(public_key_base64, validate=True)

    monkeypatch.setattr(authority, "_select_reviewed_pin", forged_selector)
    monkeypatch.setattr(
        authority,
        "_run_ssh_keygen_verify",
        lambda **kwargs: verifier_calls.append(kwargs),
    )

    with pytest.raises(authority.OwnerSignatureAuthorityError, match="no unique independently"):
        authority.load_formal_execution_owner_signature(
            authority_payload=payload,
            allowed_signers_path=allowed,
            signature_path=signature,
        )
    assert selector_calls == []
    assert verifier_calls == []


def test_production_power_calibration_gate_refuses_before_crypto_verifier(
    tmp_path, signer, monkeypatch,
):
    private, public_key_base64 = signer
    payload = b'{"power_calibration":"exact-candidate"}\n'
    allowed, signature = _signed_controls(
        tmp_path,
        private_key=private,
        public_key_base64=public_key_base64,
        payload=payload,
        namespace=authority.PURPOSE_NAMESPACES[
            authority.POWER_CALIBRATION_EXECUTION_PURPOSE
        ],
        stem="power-calibration",
    )
    calls = []
    monkeypatch.setattr(
        authority,
        "_run_ssh_keygen_verify",
        lambda **kwargs: calls.append(kwargs),
    )

    with pytest.raises(
        authority.OwnerSignatureAuthorityError,
        match="no unique independently",
    ):
        authority.load_power_calibration_execution_owner_signature(
            authority_payload=payload,
            allowed_signers_path=allowed,
            signature_path=signature,
        )

    assert calls == []
    assert authority.reviewed_owner_signature_registry_status()[
        "gate_key_counts"
    ][authority.POWER_CALIBRATION_EXECUTION_PURPOSE] == 0


def test_rebinding_registry_and_public_verifier_path_cannot_replace_or_redirect_gate(
    tmp_path, signer, monkeypatch,
):
    private, public_key_base64 = signer
    purpose = authority.FORMAL_EXECUTION_PURPOSE
    payload = b'{"formal_execution":"sealed-registry"}\n'
    allowed, signature = _signed_controls(
        tmp_path,
        private_key=private,
        public_key_base64=public_key_base64,
        payload=payload,
        namespace=authority.PURPOSE_NAMESPACES[purpose],
    )
    pin = _pin(public_key_base64, purpose)
    monkeypatch.setattr(authority, "_REVIEWED_OWNER_PUBLIC_KEYS", (pin,))
    monkeypatch.setattr(authority, "TRUSTED_SSH_KEYGEN_PATH", Path("/bin/false"))

    with pytest.raises(authority.OwnerSignatureAuthorityError, match="no unique independently"):
        authority.load_formal_execution_owner_signature(
            authority_payload=payload,
            allowed_signers_path=allowed,
            signature_path=signature,
        )

    fixture_authority = _verify_fixture_signature(
        purpose=purpose,
        authority_payload=payload,
        allowed_signers_path=allowed,
        signature_path=signature,
        reviewed_pins=(pin,),
    )
    assert fixture_authority["verifier_path"] == "/usr/bin/ssh-keygen"


def test_wrong_payload_namespace_or_key_never_authenticates(tmp_path, signer):
    private, public_key_base64 = signer
    purpose = authority.FORMAL_EXECUTION_PURPOSE
    payload = b'{"formal_execution":"one"}\n'
    allowed, signature = _signed_controls(
        tmp_path,
        private_key=private,
        public_key_base64=public_key_base64,
        payload=payload,
        namespace=authority.PURPOSE_NAMESPACES[purpose],
    )
    pin = _pin(public_key_base64, *authority.PURPOSE_NAMESPACES)

    with pytest.raises(authority.OwnerSignatureAuthorityError, match="verification failed"):
        _verify_fixture_signature(
            purpose=purpose,
            authority_payload=payload + b"changed",
            allowed_signers_path=allowed,
            signature_path=signature,
            reviewed_pins=(pin,),
        )
    with pytest.raises(authority.OwnerSignatureAuthorityError, match="verification failed"):
        _verify_fixture_signature(
            purpose=authority.FORMAL_RESULT_READ_PURPOSE,
            authority_payload=payload,
            allowed_signers_path=allowed,
            signature_path=signature,
            reviewed_pins=(pin,),
        )

    other_private, other_public = _keypair(tmp_path, "other")
    del other_private
    wrong_pin = _pin(other_public, purpose)
    with pytest.raises(authority.OwnerSignatureAuthorityError, match="no unique independently"):
        _verify_fixture_signature(
            purpose=purpose,
            authority_payload=payload,
            allowed_signers_path=allowed,
            signature_path=signature,
            reviewed_pins=(wrong_pin,),
        )


def test_acquisition_review_signatures_are_not_cross_usable(tmp_path, signer):
    private, public_key_base64 = signer
    payload = b'{"review":"same-exact-payload"}\n'
    preopen_purpose = authority.PREOPEN_ACQUISITION_REVIEW_PURPOSE
    production_purpose = authority.PRODUCTION_EVIDENCE_REVIEW_PURPOSE
    allowed, signature = _signed_controls(
        tmp_path,
        private_key=private,
        public_key_base64=public_key_base64,
        payload=payload,
        namespace=authority.PURPOSE_NAMESPACES[preopen_purpose],
        stem="preopen-acquisition-review",
    )
    pin = _pin(public_key_base64, preopen_purpose, production_purpose)
    assert _verify_fixture_signature(
        purpose=preopen_purpose,
        authority_payload=payload,
        allowed_signers_path=allowed,
        signature_path=signature,
        reviewed_pins=(pin,),
    )["purpose"] == preopen_purpose
    with pytest.raises(
        authority.OwnerSignatureAuthorityError,
        match="verification failed",
    ):
        _verify_fixture_signature(
            purpose=production_purpose,
            authority_payload=payload,
            allowed_signers_path=allowed,
            signature_path=signature,
            reviewed_pins=(pin,),
        )


@pytest.mark.parametrize("target_name", ("allowed", "signature"))
def test_private_controls_reject_mode_symlink_and_hardlink(
    tmp_path, signer, target_name,
):
    private, public_key_base64 = signer
    purpose = authority.PREOPEN_EXECUTION_PURPOSE
    payload = b'{"preopen":"exact-plan-authority"}\n'
    allowed, signature = _signed_controls(
        tmp_path,
        private_key=private,
        public_key_base64=public_key_base64,
        payload=payload,
        namespace=authority.PURPOSE_NAMESPACES[purpose],
    )
    pin = _pin(public_key_base64, purpose)
    target = allowed if target_name == "allowed" else signature
    kwargs = {
        "purpose": purpose,
        "authority_payload": payload,
        "allowed_signers_path": allowed,
        "signature_path": signature,
        "reviewed_pins": (pin,),
    }

    target.chmod(0o640)
    with pytest.raises(authority.OwnerSignatureAuthorityError, match="mode-0600"):
        _verify_fixture_signature(**kwargs)
    target.chmod(0o600)

    link = tmp_path / f"{target.name}.hardlink"
    os.link(target, link)
    with pytest.raises(authority.OwnerSignatureAuthorityError, match="single-link"):
        _verify_fixture_signature(**kwargs)
    link.unlink()

    link.symlink_to(target)
    if target_name == "allowed":
        kwargs["allowed_signers_path"] = link
    else:
        kwargs["signature_path"] = link
    with pytest.raises(authority.OwnerSignatureAuthorityError, match="nonsymlink"):
        _verify_fixture_signature(**kwargs)


@pytest.mark.parametrize(
    "replacement",
    (
        b"arv2-owner,another ssh-ed25519 KEY\n",
        b"arv2-owner namespaces=\"x\" ssh-ed25519 KEY\n",
        b"someone-else ssh-ed25519 KEY\n",
        b"arv2-owner ssh-rsa KEY\n",
        b"arv2-owner ssh-ed25519 KEY comment\n",
        b"arv2-owner ssh-ed25519 KEY\narv2-owner ssh-ed25519 KEY\n",
    ),
)
def test_allowed_signers_must_be_one_exact_reviewed_line(
    tmp_path, signer, replacement,
):
    private, public_key_base64 = signer
    purpose = authority.FORMAL_RESULT_READ_PURPOSE
    payload = b'{"result_read":"exact"}\n'
    allowed, signature = _signed_controls(
        tmp_path,
        private_key=private,
        public_key_base64=public_key_base64,
        payload=payload,
        namespace=authority.PURPOSE_NAMESPACES[purpose],
    )
    pin = _pin(public_key_base64, purpose)
    _private_file(allowed, replacement.replace(b"KEY", public_key_base64.encode("ascii")))

    with pytest.raises(authority.OwnerSignatureAuthorityError, match="no unique independently"):
        _verify_fixture_signature(
            purpose=purpose,
            authority_payload=payload,
            allowed_signers_path=allowed,
            signature_path=signature,
            reviewed_pins=(pin,),
        )


def test_crypto_helper_rebinding_is_inert_and_path_replacement_changes_snapshot(
    tmp_path, signer, monkeypatch,
):
    private, public_key_base64 = signer
    purpose = authority.FORMAL_EXECUTION_PURPOSE
    payload = b'{"formal_execution":"exact"}\n'
    allowed, signature = _signed_controls(
        tmp_path,
        private_key=private,
        public_key_base64=public_key_base64,
        payload=payload,
        namespace=authority.PURPOSE_NAMESPACES[purpose],
    )
    pin = _pin(public_key_base64, purpose)
    real_verify = authority._run_ssh_keygen_verify
    calls = []

    def verify_then_replace(**kwargs):
        calls.append(kwargs)
        real_verify(**kwargs)
        original = signature.read_bytes()
        replacement = tmp_path / "replacement.sig"
        _private_file(replacement, original)
        os.replace(replacement, signature)

    monkeypatch.setattr(authority, "_run_ssh_keygen_verify", verify_then_replace)
    loaded = _verify_fixture_signature(
        purpose=purpose,
        authority_payload=payload,
        allowed_signers_path=allowed,
        signature_path=signature,
        reviewed_pins=(pin,),
    )

    # The production verifier captured its operation before module publication;
    # rebinding the old name cannot insert a path replacement between reads.
    assert loaded["signature_path"] == signature
    assert calls == []

    before = authority._read_private_stable_file(
        signature,
        maximum_bytes=authority.MAX_SIGNATURE_BYTES,
        name="owner detached-signature file",
    )
    replacement = tmp_path / "replacement-after.sig"
    _private_file(replacement, signature.read_bytes())
    os.replace(replacement, signature)
    after = authority._read_private_stable_file(
        signature,
        maximum_bytes=authority.MAX_SIGNATURE_BYTES,
        name="owner detached-signature file",
    )
    assert after != before


def test_verifier_command_is_fixed_clean_and_output_is_never_disclosed(
    tmp_path, signer, monkeypatch,
):
    private, public_key_base64 = signer
    purpose = authority.PREOPEN_EXECUTION_PURPOSE
    payload = b'{"preopen":"exact"}\n'
    allowed, signature = _signed_controls(
        tmp_path,
        private_key=private,
        public_key_base64=public_key_base64,
        payload=payload,
        namespace=authority.PURPOSE_NAMESPACES[purpose],
    )
    pin = _pin(public_key_base64, purpose)
    observed = {}

    def fake_run(args, **kwargs):
        observed["args"] = args
        observed.update(kwargs)
        return subprocess.CompletedProcess(
            args=args,
            returncode=7,
            stdout=b"DO-NOT-DISCLOSE-STDOUT",
            stderr=b"DO-NOT-DISCLOSE-STDERR",
        )

    verifier = authority._snapshot_trusted_verifier()
    with pytest.raises(authority.OwnerSignatureAuthorityError) as failure:
        authority._run_ssh_keygen_verify(
            authority_payload=payload,
            allowed_signers=allowed.read_bytes(),
            signature=signature.read_bytes(),
            namespace=authority.PURPOSE_NAMESPACES[purpose],
            verifier_path=verifier[0],
            _run_process=fake_run,
        )
    message = str(failure.value)
    assert "DO-NOT-DISCLOSE" not in message
    assert observed["args"][0:3] == ("/usr/bin/ssh-keygen", "-Y", "verify")
    assert observed["args"][6:10] == (
        "arv2-owner", "-n", "arv2-preopen-qc-execution-v1", "-s",
    )
    assert observed["input"] == payload
    assert observed["env"] == {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"}
    assert observed["shell"] is False
    assert observed["check"] is False
    assert observed["timeout"] == 10


def _forged_authority(tmp_path: Path, purpose: str, payload: bytes):
    value = object.__new__(authority.OwnerSignatureAuthority)
    fields = {
        "authority_id": "arv2-owner-signature-authority-" + "0" * 24,
        "authority_sha256": "0" * 64,
        "schema": authority.SCHEMA,
        "purpose": purpose,
        "namespace": authority.PURPOSE_NAMESPACES[purpose],
        "principal": authority.PRINCIPAL,
        "reviewed_key_id": "arv2-owner-ed25519-" + "0" * 16,
        "public_key_blob_sha256": "0" * 64,
        "authority_payload_sha256": hashlib.sha256(payload).hexdigest(),
        "authority_payload_byte_count": len(payload),
        "allowed_signers_path": str(tmp_path / "missing.allowed_signers"),
        "allowed_signers_sha256": "0" * 64,
        "allowed_signers_byte_count": 1,
        "signature_path": str(tmp_path / "missing.sig"),
        "signature_sha256": "0" * 64,
        "signature_byte_count": 1,
        "verifier_path": str(SSH_KEYGEN),
        "_authority_payload": payload,
        "_allowed_signers_snapshot": None,
        "_signature_snapshot": None,
        "_verifier_snapshot": None,
    }
    for name, item in fields.items():
        object.__setattr__(value, name, item)
    return value


@pytest.mark.parametrize(
    ("purpose", "requirer_name"),
    (
        (authority.FORMAL_EXECUTION_PURPOSE, "require_formal_execution_owner_signature"),
        (authority.FORMAL_RESULT_READ_PURPOSE, "require_formal_result_read_owner_signature"),
        (authority.PREOPEN_EXECUTION_PURPOSE, "require_preopen_execution_owner_signature"),
        (
            authority.PREOPEN_ACQUISITION_REVIEW_PURPOSE,
            "require_preopen_acquisition_review_owner_signature",
        ),
        (
            authority.PRODUCTION_EVIDENCE_REVIEW_PURPOSE,
            "require_production_evidence_review_owner_signature",
        ),
        (
            authority.POWER_CALIBRATION_EXECUTION_PURPOSE,
            "require_power_calibration_execution_owner_signature",
        ),
    ),
)
def test_rebinding_raw_loader_cannot_self_mint_any_production_gate(
    tmp_path, monkeypatch, purpose, requirer_name,
):
    payload = b'{"forged":"owner-authority"}\n'
    forged = _forged_authority(tmp_path, purpose, payload)
    calls = []

    def forged_loader(**kwargs):
        calls.append(kwargs)
        return forged

    assert not hasattr(authority, "_load_with_reviewed_pins")
    monkeypatch.setattr(
        authority,
        "_load_with_reviewed_pins",
        forged_loader,
        raising=False,
    )
    with pytest.raises(authority.OwnerSignatureAuthorityError):
        getattr(authority, requirer_name)(forged, authority_payload=payload)
    assert calls == []


def test_authority_factories_and_raw_operation_handles_are_not_published():
    for name in (
        "_make_reviewed_pin_operations",
        "_seal_public_api",
        "_load_with_reviewed_pins",
        "_require_with_reviewed_pins",
    ):
        assert not hasattr(authority, name)


def test_mutating_review_facing_pin_object_cannot_reseal_production_gate(
    tmp_path, signer,
):
    private, public_key_base64 = signer
    purpose = authority.FORMAL_EXECUTION_PURPOSE
    payload = b'{"formal_execution":"mutated-published-pin"}\n'
    allowed, signature = _signed_controls(
        tmp_path,
        private_key=private,
        public_key_base64=public_key_base64,
        payload=payload,
        namespace=authority.PURPOSE_NAMESPACES[purpose],
    )
    published_pin = authority._REVIEWED_OWNER_PUBLIC_KEYS[0]
    original = (
        published_pin.key_id,
        published_pin.public_key_base64,
        published_pin.purposes,
    )
    attacker_pin = _pin(public_key_base64, purpose)
    try:
        object.__setattr__(published_pin, "key_id", attacker_pin.key_id)
        object.__setattr__(
            published_pin,
            "public_key_base64",
            attacker_pin.public_key_base64,
        )
        object.__setattr__(published_pin, "purposes", attacker_pin.purposes)
        with pytest.raises(
            authority.OwnerSignatureAuthorityError,
            match="no unique independently",
        ):
            authority.load_formal_execution_owner_signature(
                authority_payload=payload,
                allowed_signers_path=allowed,
                signature_path=signature,
            )
        assert authority.reviewed_owner_signature_registry_status()[
            "gate_key_counts"
        ] == {
            "formal_qc_execution": 1,
            "formal_qc_result_read": 1,
            "preopen_qc_execution": 1,
            "preopen_control_acquisition_review": 1,
            "production_evidence_review": 1,
            "power_calibration_qc_execution": 0,
        }
    finally:
        object.__setattr__(published_pin, "key_id", original[0])
        object.__setattr__(published_pin, "public_key_base64", original[1])
        object.__setattr__(published_pin, "purposes", original[2])


def _reachable_closure_values(function):
    observed = []
    pending = [function]
    seen = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        defaults = current.__defaults__ or ()
        kwdefaults = current.__kwdefaults__ or {}
        for value in (*defaults, *kwdefaults.keys(), *kwdefaults.values()):
            observed.append(value)
            if type(value) is FunctionType:
                pending.append(value)
        closure = current.__closure__ or ()
        for cell in closure:
            try:
                value = cell.cell_contents
            except ValueError:
                continue
            observed.append(value)
            if type(value) is FunctionType:
                pending.append(value)
    return tuple(observed)


def _closure_cell(value):
    return (lambda: value).__closure__[0]


def _with_closure_values(function, **replacements):
    names = function.__code__.co_freevars
    unknown = set(replacements) - set(names)
    assert unknown == set()
    cells = tuple(
        _closure_cell(replacements.get(name, cell.cell_contents))
        for name, cell in zip(names, function.__closure__, strict=True)
    )
    clone = FunctionType(
        function.__code__,
        function.__globals__,
        name=function.__name__,
        argdefs=function.__defaults__,
        closure=cells,
    )
    clone.__kwdefaults__ = function.__kwdefaults__
    return clone


def _production_signature_runner():
    runners = tuple(
        value
        for value in _reachable_closure_values(
            authority.load_formal_execution_owner_signature
        )
        if type(value) is FunctionType
        and value.__name__ == "run_signature_verifier"
    )
    assert len(runners) == 1
    return runners[0]


def _nested_code_objects(code):
    yield code
    for value in code.co_consts:
        if type(value) is CodeType:
            yield from _nested_code_objects(value)


def test_production_signature_closures_capture_only_immutable_scalar_pin_state():
    public_operations = (
        authority.load_formal_execution_owner_signature,
        authority.require_formal_execution_owner_signature,
        authority.load_formal_result_read_owner_signature,
        authority.require_formal_result_read_owner_signature,
        authority.load_preopen_execution_owner_signature,
        authority.require_preopen_execution_owner_signature,
        authority.load_preopen_acquisition_review_owner_signature,
        authority.require_preopen_acquisition_review_owner_signature,
        authority.load_production_evidence_review_owner_signature,
        authority.require_production_evidence_review_owner_signature,
        authority.load_power_calibration_execution_owner_signature,
        authority.require_power_calibration_execution_owner_signature,
        authority.reviewed_owner_signature_registry_status,
    )
    for operation in public_operations:
        reachable = _reachable_closure_values(operation)
        assert not any(
            type(value) is authority._ReviewedOwnerPublicKey
            or isinstance(value, MappingProxyType)
            or isinstance(value, Path)
            or type(value) in (dict, list, set)
            for value in reachable
        )


def test_production_gate_code_has_no_runtime_global_or_builtin_lookup():
    public_gates = (
        authority.load_formal_execution_owner_signature,
        authority.require_formal_execution_owner_signature,
        authority.load_formal_result_read_owner_signature,
        authority.require_formal_result_read_owner_signature,
        authority.load_preopen_execution_owner_signature,
        authority.require_preopen_execution_owner_signature,
        authority.load_preopen_acquisition_review_owner_signature,
        authority.require_preopen_acquisition_review_owner_signature,
        authority.load_production_evidence_review_owner_signature,
        authority.require_production_evidence_review_owner_signature,
        authority.load_power_calibration_execution_owner_signature,
        authority.require_power_calibration_execution_owner_signature,
        authority.reviewed_owner_signature_registry_status,
    )
    inspected = set()
    for operation in public_gates:
        reachable = (operation, *_reachable_closure_values(operation))
        for candidate in reachable:
            if (
                type(candidate) is not FunctionType
                or candidate.__module__ != authority.__name__
                or id(candidate) in inspected
            ):
                continue
            inspected.add(id(candidate))
            for code in _nested_code_objects(candidate.__code__):
                assert not any(
                    instruction.opname
                    in {"IMPORT_NAME", "LOAD_GLOBAL", "LOAD_NAME"}
                    for instruction in dis.get_instructions(code)
                ), (candidate.__qualname__, code.co_name)


@POSIX_ONLY
def test_production_verifier_captures_anonymous_pipe_process_boundary():
    reachable = _reachable_closure_values(
        authority.load_formal_execution_owner_signature
    )

    assert os.pipe in reachable
    assert os.posix_spawn in reachable
    assert tempfile.TemporaryDirectory not in reachable
    assert dataclasses.fields not in reachable


def test_sealed_json_string_encoder_matches_canonical_json_boundaries():
    encoders = tuple(
        value
        for value in _reachable_closure_values(
            authority.load_formal_execution_owner_signature
        )
        if type(value) is FunctionType
        and value.__name__ == "canonical_json_string"
    )
    assert len(encoders) == 1
    samples = (
        "",
        'plain / quote " slash \\',
        "\x00\b\t\n\f\r\x1f",
        "~\x7f\x80\u2028\ud800\U0001f600",
    )

    for sample in samples:
        assert encoders[0](sample) == json.dumps(sample, ensure_ascii=True)


def test_production_fixture_loader_seals_identity_from_json_and_import_rebinding(
    tmp_path,
    signer,
):
    private, public_key_base64 = signer
    purpose = authority.FORMAL_EXECUTION_PURPOSE
    namespace = authority.PURPOSE_NAMESPACES[purpose]
    payload = b'{"formal_execution":"sealed-identity"}\n'
    allowed, signature = _signed_controls(
        tmp_path,
        private_key=private,
        public_key_base64=public_key_base64,
        payload=payload,
        namespace=namespace,
        stem="sealed-identity",
    )
    pin = _pin(public_key_base64, purpose)
    reviewed_pin_records = (
        (
            pin.key_id,
            pin.public_key_base64,
            pin.purposes,
            base64.b64decode(pin.public_key_base64, validate=True),
        ),
    )
    loaders = tuple(
        value
        for value in _reachable_closure_values(
            authority.load_formal_execution_owner_signature
        )
        if type(value) is FunctionType
        and value.__name__ == "load_with_reviewed_pins"
    )
    assert len(loaders) == 1
    calls = []
    original_dumps = json.dumps
    original_import = builtins.__import__

    def refuse_dependency(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("production identity resolved an external encoder")

    try:
        json.dumps = refuse_dependency
        builtins.__import__ = refuse_dependency
        loaded = loaders[0](
            purpose=purpose,
            authority_payload=payload,
            allowed_signers_path=allowed,
            signature_path=signature,
            reviewed_pin_records=reviewed_pin_records,
        )
    finally:
        json.dumps = original_dumps
        builtins.__import__ = original_import

    identity = {
        "schema": loaded.schema,
        "authority_id": None,
        "authority_sha256": None,
        "purpose": loaded.purpose,
        "namespace": loaded.namespace,
        "principal": loaded.principal,
        "reviewed_key_id": loaded.reviewed_key_id,
        "public_key_blob_sha256": loaded.public_key_blob_sha256,
        "authority_payload_sha256": loaded.authority_payload_sha256,
        "authority_payload_byte_count": loaded.authority_payload_byte_count,
        "allowed_signers_path": str(loaded.allowed_signers_path),
        "allowed_signers_sha256": loaded.allowed_signers_sha256,
        "allowed_signers_byte_count": loaded.allowed_signers_byte_count,
        "signature_path": str(loaded.signature_path),
        "signature_sha256": loaded.signature_sha256,
        "signature_byte_count": loaded.signature_byte_count,
        "verifier_path": str(loaded.verifier_path),
    }
    expected_digest = hashlib.sha256(
        authority._canonical_identity_bytes(identity)
    ).hexdigest()
    assert calls == []
    assert loaded.authority_sha256 == expected_digest
    assert loaded.authority_id == (
        "arv2-owner-signature-authority-" + expected_digest[:24]
    )


def test_production_authority_construction_and_reauthentication_seal_type_state(
    tmp_path,
    signer,
):
    private, public_key_base64 = signer
    purpose = authority.FORMAL_EXECUTION_PURPOSE
    payload = b'{"formal_execution":"sealed-authority-type"}\n'
    allowed, signature = _signed_controls(
        tmp_path,
        private_key=private,
        public_key_base64=public_key_base64,
        payload=payload,
        namespace=authority.PURPOSE_NAMESPACES[purpose],
        stem="sealed-authority-type",
    )
    pin = _pin(public_key_base64, purpose)
    reviewed_pin_records = (
        (
            pin.key_id,
            pin.public_key_base64,
            pin.purposes,
            base64.b64decode(pin.public_key_base64, validate=True),
        ),
    )
    loaders = tuple(
        value
        for value in _reachable_closure_values(
            authority.load_formal_execution_owner_signature
        )
        if type(value) is FunctionType
        and value.__name__ == "load_with_reviewed_pins"
    )
    requirers = tuple(
        value
        for value in _reachable_closure_values(
            authority.require_formal_execution_owner_signature
        )
        if type(value) is FunctionType
        and value.__name__ == "require_with_reviewed_pins"
    )
    assert len(loaders) == len(requirers) == 1
    loader = loaders[0]
    requirer = requirers[0]

    path_type = type(Path())
    path_new_was_local = "__new__" in path_type.__dict__
    original_path_new = path_type.__dict__.get("__new__")
    path_constructor_calls = []

    def poisoned_path_new(*args, **kwargs):
        path_constructor_calls.append((args, kwargs))
        raise AssertionError("authenticated authority paths must remain scalars")

    setattr(path_type, "__new__", poisoned_path_new)
    try:
        loaded = loader(
            purpose=purpose,
            authority_payload=payload,
            allowed_signers_path=allowed,
            signature_path=signature,
            reviewed_pin_records=reviewed_pin_records,
        )
        assert type(loaded.allowed_signers_path) is str
        assert loaded.allowed_signers_path == str(allowed)
        assert type(loaded.signature_path) is str
        assert loaded.signature_path == str(signature)
        assert type(loaded.verifier_path) is str
        assert loaded.verifier_path == "/usr/bin/ssh-keygen"
        assert requirer(
            loaded,
            purpose=purpose,
            authority_payload=payload,
            reviewed_pin_records=reviewed_pin_records,
        ) is loaded
        assert path_constructor_calls == []
    finally:
        if path_new_was_local:
            setattr(path_type, "__new__", original_path_new)
        else:
            delattr(path_type, "__new__")

    authority_type = authority.OwnerSignatureAuthority
    original_init = authority_type.__dict__["__init__"]
    constructor_calls = []

    def poisoned_authority_init(*args, **kwargs):
        constructor_calls.append((args, kwargs))

    setattr(authority_type, "__init__", poisoned_authority_init)
    try:
        with pytest.raises(
            authority.OwnerSignatureAuthorityError,
            match="owner signature authority type changed",
        ):
            loader(
                purpose=purpose,
                authority_payload=payload,
                allowed_signers_path=allowed,
                signature_path=signature,
                reviewed_pin_records=reviewed_pin_records,
            )
        assert constructor_calls == []
    finally:
        setattr(authority_type, "__init__", original_init)

    loaded = loader(
        purpose=purpose,
        authority_payload=payload,
        allowed_signers_path=allowed,
        signature_path=signature,
        reviewed_pin_records=reviewed_pin_records,
    )
    authority_id_slot = authority_type.__dict__["authority_id"]
    setattr(authority_type, "authority_id", "attacker-presentation")
    try:
        assert loaded.authority_id == "attacker-presentation"
        with pytest.raises(
            authority.OwnerSignatureAuthorityError,
            match="exact owner signature authority is required",
        ):
            requirer(
                loaded,
                purpose=purpose,
                authority_payload=payload,
                reviewed_pin_records=reviewed_pin_records,
            )
    finally:
        setattr(authority_type, "authority_id", authority_id_slot)

    class SplitViewAuthorityId:
        def __get__(self, instance, _owner):
            if instance is None:
                return authority_id_slot
            return "attacker-split-presentation"

    setattr(authority_type, "authority_id", SplitViewAuthorityId())
    try:
        assert authority_type.authority_id is authority_id_slot
        assert loaded.authority_id == "attacker-split-presentation"
        with pytest.raises(
            authority.OwnerSignatureAuthorityError,
            match="exact owner signature authority is required",
        ):
            requirer(
                loaded,
                purpose=purpose,
                authority_payload=payload,
                reviewed_pin_records=reviewed_pin_records,
            )
    finally:
        setattr(authority_type, "authority_id", authority_id_slot)

    authority_id_slot.__set__(loaded, "forged-underlying-identity")
    with pytest.raises(
        authority.OwnerSignatureAuthorityError,
        match="owner signature authority changed",
    ):
        requirer(
            loaded,
            purpose=purpose,
            authority_payload=payload,
            reviewed_pin_records=reviewed_pin_records,
        )


def test_reflected_namespace_and_captured_pin_mutation_cannot_reseal_any_gate(
    tmp_path, signer,
):
    private, public_key_base64 = signer
    formal_purpose = authority.FORMAL_EXECUTION_PURPOSE
    formal_namespace = authority.PURPOSE_NAMESPACES[formal_purpose]
    payload = b'{"formal_execution":"reflected-mutation"}\n'
    allowed, signature = _signed_controls(
        tmp_path,
        private_key=private,
        public_key_base64=public_key_base64,
        payload=payload,
        namespace=formal_namespace,
        stem="reflected-mutation",
    )

    class ReflectedMappingCapture:
        value = None

        def __eq__(self, other):
            self.value = other
            return False

    capture = ReflectedMappingCapture()
    assert (authority.PURPOSE_NAMESPACES == capture) is False
    backing = capture.value
    assert type(backing) is dict
    original_namespaces = dict(backing)
    published_pin = authority._REVIEWED_OWNER_PUBLIC_KEYS[0]
    original_pin = (
        published_pin.key_id,
        published_pin.public_key_base64,
        published_pin.purposes,
    )
    attacker_pin = _pin(public_key_base64, *original_namespaces)
    operations = (
        (
            authority.load_formal_execution_owner_signature,
            authority.require_formal_execution_owner_signature,
            authority.FORMAL_EXECUTION_PURPOSE,
        ),
        (
            authority.load_formal_result_read_owner_signature,
            authority.require_formal_result_read_owner_signature,
            authority.FORMAL_RESULT_READ_PURPOSE,
        ),
        (
            authority.load_preopen_execution_owner_signature,
            authority.require_preopen_execution_owner_signature,
            authority.PREOPEN_EXECUTION_PURPOSE,
        ),
        (
            authority.load_preopen_acquisition_review_owner_signature,
            authority.require_preopen_acquisition_review_owner_signature,
            authority.PREOPEN_ACQUISITION_REVIEW_PURPOSE,
        ),
        (
            authority.load_production_evidence_review_owner_signature,
            authority.require_production_evidence_review_owner_signature,
            authority.PRODUCTION_EVIDENCE_REVIEW_PURPOSE,
        ),
        (
            authority.load_power_calibration_execution_owner_signature,
            authority.require_power_calibration_execution_owner_signature,
            authority.POWER_CALIBRATION_EXECUTION_PURPOSE,
        ),
    )
    try:
        backing.clear()
        backing.update(
            (purpose, "arv2-attacker-reflected-namespace-v1")
            for purpose in original_namespaces
        )
        object.__setattr__(published_pin, "key_id", attacker_pin.key_id)
        object.__setattr__(
            published_pin, "public_key_base64", attacker_pin.public_key_base64
        )
        object.__setattr__(published_pin, "purposes", attacker_pin.purposes)

        for loader, requirer, purpose in operations:
            with pytest.raises(
                authority.OwnerSignatureAuthorityError,
                match="no unique independently",
            ):
                loader(
                    authority_payload=payload,
                    allowed_signers_path=allowed,
                    signature_path=signature,
                )
            forged = _forged_authority(tmp_path, purpose, payload)
            object.__setattr__(forged, "allowed_signers_path", str(allowed))
            object.__setattr__(forged, "signature_path", str(signature))
            with pytest.raises(
                authority.OwnerSignatureAuthorityError,
                match="no unique independently",
            ):
                requirer(forged, authority_payload=payload)

        assert authority.reviewed_owner_signature_registry_status()[
            "gate_key_counts"
        ] == {
            "formal_qc_execution": 1,
            "formal_qc_result_read": 1,
            "preopen_qc_execution": 1,
            "preopen_control_acquisition_review": 1,
            "production_evidence_review": 1,
            "power_calibration_qc_execution": 0,
        }

        if hasattr(os, "fork"):
            read_descriptor, write_descriptor = os.pipe()
            child = os.fork()
            if child == 0:
                os.close(read_descriptor)
                try:
                    authority.load_formal_execution_owner_signature(
                        authority_payload=payload,
                        allowed_signers_path=allowed,
                        signature_path=signature,
                    )
                except authority.OwnerSignatureAuthorityError:
                    result = b"refused"
                else:
                    result = b"accepted"
                os.write(write_descriptor, result)
                os.close(write_descriptor)
                os._exit(0)
            os.close(write_descriptor)
            result = os.read(read_descriptor, 32)
            os.close(read_descriptor)
            _, status = os.waitpid(child, 0)
            assert os.waitstatus_to_exitcode(status) == 0
            assert result == b"refused"
    finally:
        backing.clear()
        backing.update(original_namespaces)
        object.__setattr__(published_pin, "key_id", original_pin[0])
        object.__setattr__(published_pin, "public_key_base64", original_pin[1])
        object.__setattr__(published_pin, "purposes", original_pin[2])


def test_signature_namespaces_are_immutable_and_production_closure_pinned(
    tmp_path, signer, monkeypatch,
):
    private, public_key_base64 = signer
    purpose = authority.FORMAL_EXECUTION_PURPOSE
    namespace = authority.PURPOSE_NAMESPACES[purpose]
    payload = b'{"formal_execution":"namespace-pin"}\n'
    allowed, signature = _signed_controls(
        tmp_path,
        private_key=private,
        public_key_base64=public_key_base64,
        payload=payload,
        namespace=namespace,
    )
    pin = _pin(public_key_base64, purpose)
    with pytest.raises(TypeError):
        authority.PURPOSE_NAMESPACES[authority.FORMAL_EXECUTION_PURPOSE] = "forged"

    monkeypatch.setattr(
        authority,
        "PURPOSE_NAMESPACES",
        {authority.FORMAL_EXECUTION_PURPOSE: "forged"},
    )
    assert authority.reviewed_owner_signature_registry_status()["gate_key_counts"] == {
        "formal_qc_execution": 1,
        "formal_qc_result_read": 1,
        "preopen_qc_execution": 1,
        "preopen_control_acquisition_review": 1,
        "production_evidence_review": 1,
        "power_calibration_qc_execution": 0,
    }
    loaded = _verify_fixture_signature(
        purpose=purpose,
        authority_payload=payload,
        allowed_signers_path=allowed,
        signature_path=signature,
        reviewed_pins=(pin,),
    )
    assert loaded["namespace"] == namespace


def test_production_module_has_no_signing_or_private_key_surface():
    source_path = Path(authority.__file__)
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    public = set(authority.__all__)

    assert not any("private_key" in name or "sign_payload" in name for name in public)
    assert not any(
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value in {"sign", "-t", "ed25519", "-N"}
        for node in ast.walk(tree)
    )
    assert "arv2-owner-ed25519-21d1ae9d964ec350" in source
    assert "AAAAC3NzaC1lZDI1NTE5AAAAIA2kYwmz2Tc/F2tfAqo7xQlM/doV0nI1viXyOvUkcsQE" in source
    assert shutil.which("ssh-keygen") is not None


def test_trusted_verifier_snapshot_refuses_a_user_owned_world_writable_executable(
    tmp_path,
):
    """Exercise the combined invalid-ownership and writable-mode case."""

    fake = tmp_path / "ssh-keygen"
    fake.write_bytes(b"#!/bin/sh\nexit 0\n")
    fake.chmod(0o777)

    with pytest.raises(authority.OwnerSignatureAuthorityError) as excinfo:
        authority._snapshot_verifier_path(str(fake))

    assert "root-owned nonwritable executable" in str(excinfo.value)


def test_trusted_verifier_snapshot_refuses_user_owned_nonwritable_executable(
    tmp_path,
):
    fake = tmp_path / "ssh-keygen"
    fake.write_bytes(b"#!/bin/sh\nexit 0\n")
    fake.chmod(0o555)

    with pytest.raises(authority.OwnerSignatureAuthorityError) as excinfo:
        authority._snapshot_verifier_path(str(fake))

    assert "root-owned nonwritable executable" in str(excinfo.value)


def test_trusted_verifier_snapshot_refuses_root_owned_writable_metadata(
    monkeypatch,
):
    observed = SimpleNamespace(
        st_mode=stat.S_IFREG | 0o777,
        st_uid=0,
        st_nlink=1,
        st_size=1,
        st_dev=1,
        st_ino=1,
        st_mtime_ns=1,
        st_ctime_ns=1,
    )
    monkeypatch.setattr(
        authority,
        "os",
        SimpleNamespace(lstat=lambda _path: observed),
    )

    with pytest.raises(authority.OwnerSignatureAuthorityError) as excinfo:
        authority._snapshot_verifier_path("/usr/bin/ssh-keygen")

    assert "root-owned nonwritable executable" in str(excinfo.value)


def test_trusted_verifier_snapshot_is_primitive_and_exact_path():
    snapshot = authority._snapshot_trusted_verifier()

    assert type(snapshot) is tuple
    assert snapshot[0] == "/usr/bin/ssh-keygen"
    assert all(type(value) in (str, int) for value in snapshot)


def _unsigned_controls_for_reviewed_owner(root: Path) -> tuple[Path, Path]:
    allowed = _private_file(
        root / "unsigned.allowed_signers",
        (
            f"{authority.PRINCIPAL} ssh-ed25519 "
            f"{authority._REVIEWED_OWNER_PUBLIC_KEYS[0].public_key_base64}\n"
        ).encode("ascii"),
    )
    signature = _private_file(
        root / "unsigned.sig",
        (
            b"-----BEGIN SSH SIGNATURE-----\n"
            b"AAAA\n"
            b"-----END SSH SIGNATURE-----\n"
        ),
    )
    return allowed, signature


def test_production_loader_ignores_mutated_verifier_path_defaults(tmp_path):
    payload = b'{"formal_execution":"mutated-verifier-default"}\n'
    allowed, signature = _unsigned_controls_for_reviewed_owner(tmp_path)
    original_defaults = authority._snapshot_trusted_verifier.__defaults__
    assert original_defaults is None

    try:
        authority._snapshot_trusted_verifier.__defaults__ = (
            Path("/usr/bin/true"),
            object(),
        )
        assert authority._snapshot_trusted_verifier()[0] == "/usr/bin/ssh-keygen"
        with pytest.raises(
            authority.OwnerSignatureAuthorityError,
            match="detached owner signature verification failed",
        ):
            authority.load_formal_execution_owner_signature(
                authority_payload=payload,
                allowed_signers_path=allowed,
                signature_path=signature,
            )
    finally:
        authority._snapshot_trusted_verifier.__defaults__ = original_defaults


def test_production_loader_ignores_mutated_public_verifier_path_storage(tmp_path):
    payload = b'{"formal_execution":"mutated-public-path-storage"}\n'
    allowed, signature = _unsigned_controls_for_reviewed_owner(tmp_path)
    published_path = authority.TRUSTED_SSH_KEYGEN_PATH
    original_raw_paths = list(published_path._raw_paths)

    try:
        published_path._raw_paths[:] = ["/usr/bin/true"]
        assert published_path._raw_paths == ["/usr/bin/true"]
        with pytest.raises(
            authority.OwnerSignatureAuthorityError,
            match="detached owner signature verification failed",
        ):
            authority.load_formal_execution_owner_signature(
                authority_payload=payload,
                allowed_signers_path=allowed,
                signature_path=signature,
            )
    finally:
        published_path._raw_paths[:] = original_raw_paths


def test_production_loader_ignores_mutated_crypto_runner_defaults(tmp_path):
    payload = b'{"formal_execution":"mutated-runner-default"}\n'
    allowed, signature = _unsigned_controls_for_reviewed_owner(tmp_path)
    original_kwdefaults = dict(authority._run_ssh_keygen_verify.__kwdefaults__)
    calls = []

    def false_success(*args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args=args, returncode=0)

    try:
        authority._run_ssh_keygen_verify.__kwdefaults__["_run_process"] = (
            false_success
        )
        with pytest.raises(
            authority.OwnerSignatureAuthorityError,
            match="detached owner signature verification failed",
        ):
            authority.load_formal_execution_owner_signature(
                authority_payload=payload,
                allowed_signers_path=allowed,
                signature_path=signature,
            )
        assert calls == []
    finally:
        authority._run_ssh_keygen_verify.__kwdefaults__.clear()
        authority._run_ssh_keygen_verify.__kwdefaults__.update(original_kwdefaults)


def test_production_loader_does_not_use_rebound_subprocess_popen(
    tmp_path,
    monkeypatch,
):
    payload = b'{"formal_execution":"rebound-popen"}\n'
    allowed, signature = _unsigned_controls_for_reviewed_owner(tmp_path)
    calls = []

    def false_success(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("production must not reach subprocess.Popen")

    monkeypatch.setattr(subprocess, "Popen", false_success)
    with pytest.raises(
        authority.OwnerSignatureAuthorityError,
        match="detached owner signature verification failed",
    ):
        authority.load_formal_execution_owner_signature(
            authority_payload=payload,
            allowed_signers_path=allowed,
            signature_path=signature,
        )
    assert calls == []


def test_production_loader_does_not_use_rebound_builtin_memoryview(
    tmp_path,
    monkeypatch,
):
    payload = b'{"formal_execution":"rebound-memoryview"}\n'
    allowed, signature = _unsigned_controls_for_reviewed_owner(tmp_path)
    calls = []

    def substitute_payload(value):
        calls.append(value)
        raise AssertionError("production must retain the captured memoryview type")

    monkeypatch.setattr(builtins, "memoryview", substitute_payload)
    with pytest.raises(
        authority.OwnerSignatureAuthorityError,
        match="detached owner signature verification failed",
    ):
        authority.load_formal_execution_owner_signature(
            authority_payload=payload,
            allowed_signers_path=allowed,
            signature_path=signature,
        )
    assert calls == []


def test_production_loader_does_not_resolve_critical_builtins_at_runtime(
    tmp_path,
):
    payload = b'{"formal_execution":"rebound-critical-builtins"}\n'
    allowed, signature = _unsigned_controls_for_reviewed_owner(tmp_path)
    names = (
        "type",
        "tuple",
        "bytes",
        "int",
        "len",
        "any",
        "all",
        "set",
        "min",
        "getattr",
        "object",
        "memoryview",
        "AttributeError",
        "UnicodeError",
        "ValueError",
    )
    originals = {name: getattr(builtins, name) for name in names}
    calls = []

    def substitute_builtin(name):
        def substitute(*args, **kwargs):
            calls.append((name, args, kwargs))
            raise AssertionError(
                f"production resolved mutable builtin {name}"
            )

        return substitute

    failure = None
    try:
        for name in names:
            setattr(builtins, name, substitute_builtin(name))
        try:
            authority.load_formal_execution_owner_signature(
                authority_payload=payload,
                allowed_signers_path=allowed,
                signature_path=signature,
            )
        except BaseException as exc:
            failure = exc
    finally:
        for name, original in originals.items():
            setattr(builtins, name, original)

    assert type(failure) is authority.OwnerSignatureAuthorityError
    assert "detached owner signature verification failed" in str(failure)
    assert calls == []


@POSIX_ONLY
def test_production_loader_does_not_use_rebound_pipe_or_spawn(
    tmp_path,
    monkeypatch,
):
    payload = b'{"formal_execution":"rebound-pipe-spawn"}\n'
    allowed, signature = _unsigned_controls_for_reviewed_owner(tmp_path)
    calls = []

    def substitute_boundary(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("production must retain captured POSIX primitives")

    monkeypatch.setattr(os, "pipe", substitute_boundary)
    monkeypatch.setattr(os, "posix_spawn", substitute_boundary)
    with pytest.raises(
        authority.OwnerSignatureAuthorityError,
        match="detached owner signature verification failed",
    ):
        authority.load_formal_execution_owner_signature(
            authority_payload=payload,
            allowed_signers_path=allowed,
            signature_path=signature,
        )
    assert calls == []


def test_raw_verifier_runner_refuses_an_alternate_root_executable(tmp_path):
    payload = b'{"formal_execution":"alternate-root-executable"}\n'
    allowed, signature = _unsigned_controls_for_reviewed_owner(tmp_path)
    calls = []

    def false_success(*args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args=args, returncode=0)

    with pytest.raises(
        authority.OwnerSignatureAuthorityError,
        match="trusted ssh-keygen verifier path changed",
    ):
        authority._run_ssh_keygen_verify(
            authority_payload=payload,
            allowed_signers=allowed.read_bytes(),
            signature=signature.read_bytes(),
            namespace=authority.PURPOSE_NAMESPACES[
                authority.FORMAL_EXECUTION_PURPOSE
            ],
            verifier_path="/usr/bin/true",
            _run_process=false_success,
        )
    assert calls == []


@POSIX_ONLY
def test_production_posix_runner_pins_spawn_contract_and_never_kills_after_echild():
    pipe_pairs = iter(((10, 11), (12, 13), (14, 15)))
    spawn_calls = []
    wait_calls = []
    kill_calls = []

    def fake_spawn(path, arguments, environment, **kwargs):
        spawn_calls.append((path, arguments, environment, kwargs))
        return 424242

    def already_reaped(pid, options):
        wait_calls.append((pid, options))
        raise ChildProcessError("already reaped")

    runner = _with_closure_values(
        _production_signature_runner(),
        pipe_file=lambda: next(pipe_pairs),
        set_blocking=lambda *_args: None,
        posix_spawn=fake_spawn,
        write_file=lambda _descriptor, view: len(view),
        close_file=lambda _descriptor: None,
        waitpid=already_reaped,
        kill=lambda *args: kill_calls.append(args),
    )
    with pytest.raises(
        authority.OwnerSignatureAuthorityError,
        match="detached owner signature verifier was unavailable",
    ):
        runner(b"payload", b"allowed", b"signature", "namespace")

    assert spawn_calls == [
        (
            "/usr/bin/ssh-keygen",
            (
                "/usr/bin/ssh-keygen",
                "-Y",
                "verify",
                "-f",
                "/dev/fd/3",
                "-I",
                "arv2-owner",
                "-n",
                "namespace",
                "-s",
                "/dev/fd/4",
            ),
            {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
            {
                "file_actions": (
                    (os.POSIX_SPAWN_DUP2, 10, 0),
                    (os.POSIX_SPAWN_DUP2, 12, 3),
                    (os.POSIX_SPAWN_DUP2, 14, 4),
                    (os.POSIX_SPAWN_OPEN, 1, "/dev/null", os.O_WRONLY, 0),
                    (os.POSIX_SPAWN_OPEN, 2, "/dev/null", os.O_WRONLY, 0),
                )
            },
        )
    ]
    assert wait_calls == [(424242, os.WNOHANG)]
    assert kill_calls == []


@POSIX_ONLY
def test_production_posix_runner_refuses_any_broken_input_stream():
    pipe_pairs = iter(((10, 11), (12, 13), (14, 15)))
    kill_calls = []

    def write_with_broken_allowed(descriptor, view):
        if descriptor == 13:
            raise BrokenPipeError("closed")
        return len(view)

    runner = _with_closure_values(
        _production_signature_runner(),
        pipe_file=lambda: next(pipe_pairs),
        set_blocking=lambda *_args: None,
        posix_spawn=lambda *_args, **_kwargs: 424242,
        write_file=write_with_broken_allowed,
        close_file=lambda _descriptor: None,
        waitpid=lambda _pid, _options: (424242, 0),
        waitstatus_to_exitcode=lambda _status: 0,
        kill=lambda *args: kill_calls.append(args),
    )
    with pytest.raises(
        authority.OwnerSignatureAuthorityError,
        match="detached owner signature verification failed",
    ):
        runner(b"payload", b"allowed", b"signature", "namespace")

    assert kill_calls == []


@POSIX_ONLY
def test_production_posix_runner_timeout_is_wall_clock_not_idle_only():
    pipe_pairs = iter(((10, 11), (12, 13), (14, 15)))
    clock = iter((0.0, 1.0, 11.0))
    kill_calls = []
    wait_calls = []

    def fake_wait(pid, options):
        wait_calls.append((pid, options))
        return (pid, 0) if options == 0 else (0, 0)

    runner = _with_closure_values(
        _production_signature_runner(),
        pipe_file=lambda: next(pipe_pairs),
        set_blocking=lambda *_args: None,
        posix_spawn=lambda *_args, **_kwargs: 424242,
        write_file=lambda _descriptor, _view: 1,
        close_file=lambda _descriptor: None,
        monotonic=lambda: next(clock),
        sleep=lambda _seconds: None,
        waitpid=fake_wait,
        kill=lambda *args: kill_calls.append(args),
    )
    with pytest.raises(
        authority.OwnerSignatureAuthorityError,
        match="detached owner signature verifier timed out",
    ):
        runner(b"payload", b"allowed", b"signature", "namespace")

    assert kill_calls == [(424242, int(signal.SIGKILL))]
    assert wait_calls == [(424242, 0)]


@POSIX_ONLY
def test_production_posix_runner_accepts_a_valid_fixture_signature(
    tmp_path,
    signer,
):
    private, public_key_base64 = signer
    purpose = authority.FORMAL_EXECUTION_PURPOSE
    payload = b'{"formal_execution":"posix-runner-fixture"}\n'
    allowed, signature = _signed_controls(
        tmp_path,
        private_key=private,
        public_key_base64=public_key_base64,
        payload=payload,
        namespace=authority.PURPOSE_NAMESPACES[purpose],
        stem="posix-runner",
    )
    runners = tuple(
        value
        for value in _reachable_closure_values(
            authority.load_formal_execution_owner_signature
        )
        if type(value) is FunctionType
        and value.__name__ == "run_signature_verifier"
    )
    assert len(runners) == 1

    runners[0](
        payload,
        allowed.read_bytes(),
        signature.read_bytes(),
        authority.PURPOSE_NAMESPACES[purpose],
    )


@POSIX_ONLY
def test_production_posix_runner_streams_the_maximum_payload(
    tmp_path,
    signer,
):
    private, public_key_base64 = signer
    purpose = authority.FORMAL_EXECUTION_PURPOSE
    payload = b"x" * authority.MAX_AUTHORITY_PAYLOAD_BYTES
    allowed, signature = _signed_controls(
        tmp_path,
        private_key=private,
        public_key_base64=public_key_base64,
        payload=payload,
        namespace=authority.PURPOSE_NAMESPACES[purpose],
        stem="maximum-payload",
    )
    runners = tuple(
        value
        for value in _reachable_closure_values(
            authority.load_formal_execution_owner_signature
        )
        if type(value) is FunctionType
        and value.__name__ == "run_signature_verifier"
    )
    assert len(runners) == 1

    runners[0](
        payload,
        allowed.read_bytes(),
        signature.read_bytes(),
        authority.PURPOSE_NAMESPACES[purpose],
    )


def _production_closure(name):
    functions = {
        id(value): value
        for value in _reachable_closure_values(
            authority.load_formal_execution_owner_signature
        )
        if type(value) is FunctionType and value.__name__ == name
    }
    assert len(functions) == 1
    return next(iter(functions.values()))


def test_module_initialization_does_not_require_unix_only_attributes():
    tree = ast.parse(Path(authority.__file__).read_text(encoding="utf-8"))
    factory = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_make_reviewed_pin_operations"
    )
    direct_unix_lookups = {
        (node.value.id, node.attr)
        for node in ast.walk(factory)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and (node.value.id, node.attr)
        in {("os", "getuid"), ("os", "kill"), ("signal", "SIGKILL")}
    }
    assert direct_unix_lookups == set()


def test_sealed_operations_refuse_missing_posix_primitives_at_call_time():
    read_control = _with_closure_values(
        _production_closure("read_private_control"), getuid=None
    )
    with pytest.raises(
        authority.OwnerSignatureAuthorityError,
        match="trusted POSIX verifier process boundary is unavailable",
    ):
        read_control("/not-opened", 1, "fixture control")

    runner = _with_closure_values(
        _production_closure("run_signature_verifier"), sigkill=None
    )
    with pytest.raises(
        authority.OwnerSignatureAuthorityError,
        match="trusted POSIX verifier process boundary is unavailable",
    ):
        runner(b"payload", b"allowed", b"signature", "namespace")


def _fake_verifier_lstat(
    *,
    verifier_uid=0,
    verifier_mode=stat.S_IFREG | 0o755,
    parent_uid=0,
    parent_mode=stat.S_IFDIR | 0o755,
):
    def fake_lstat(path):
        if path == "/usr/bin/ssh-keygen":
            return SimpleNamespace(
                st_mode=verifier_mode, st_uid=verifier_uid, st_nlink=1,
                st_size=1, st_dev=1, st_ino=2, st_mtime_ns=3, st_ctime_ns=4,
            )
        return SimpleNamespace(
            st_mode=parent_mode, st_uid=parent_uid, st_nlink=1, st_dev=1,
            st_ino=5, st_mtime_ns=6, st_ctime_ns=7,
        )

    return fake_lstat


def test_sealed_verifier_snapshot_refuses_untrusted_verifier_or_parent():
    """The sealed snapshot, not the public helper, ties verification to a root binary."""

    snapshot = _production_closure("snapshot_trusted_verifier")
    accepted = _with_closure_values(snapshot, lstat=_fake_verifier_lstat())()
    assert accepted[1][0] == "/usr/bin/ssh-keygen"

    user_uid = OWNER_UID_FOR_TEST
    for lstat in (
        _fake_verifier_lstat(verifier_uid=user_uid),
        _fake_verifier_lstat(verifier_mode=stat.S_IFREG | 0o777),
        _fake_verifier_lstat(verifier_mode=stat.S_IFREG | 0o644),
    ):
        with pytest.raises(
            authority.OwnerSignatureAuthorityError,
            match="root-owned nonwritable executable",
        ):
            _with_closure_values(snapshot, lstat=lstat)()

    for lstat in (
        _fake_verifier_lstat(parent_mode=stat.S_IFDIR | 0o777),
        _fake_verifier_lstat(parent_uid=user_uid),
    ):
        with pytest.raises(
            authority.OwnerSignatureAuthorityError,
            match="verifier parent is not root-controlled",
        ):
            _with_closure_values(snapshot, lstat=lstat)()


def test_sealed_loader_refuses_untrusted_verifier_before_spawning(tmp_path, signer):
    private, public_key_base64 = signer
    purpose = authority.FORMAL_EXECUTION_PURPOSE
    payload = b'{"formal_execution":"untrusted-verifier"}\n'
    allowed, signature = _signed_controls(
        tmp_path,
        private_key=private,
        public_key_base64=public_key_base64,
        payload=payload,
        namespace=authority.PURPOSE_NAMESPACES[purpose],
        stem="untrusted-verifier",
    )
    pin = _pin(public_key_base64, purpose)
    reviewed_pin_records = (
        (
            pin.key_id,
            pin.public_key_base64,
            pin.purposes,
            base64.b64decode(pin.public_key_base64, validate=True),
        ),
    )
    spawned = []

    def refuse_spawn(*args, **kwargs):
        spawned.append((args, kwargs))
        raise AssertionError("an untrusted verifier must never be spawned")

    untrusted_snapshot = _with_closure_values(
        _production_closure("snapshot_trusted_verifier"),
        lstat=_fake_verifier_lstat(verifier_uid=OWNER_UID_FOR_TEST),
    )
    loader = _with_closure_values(
        _production_closure("load_with_reviewed_path_texts"),
        snapshot_trusted_verifier=untrusted_snapshot,
        run_signature_verifier=refuse_spawn,
    )
    with pytest.raises(
        authority.OwnerSignatureAuthorityError,
        match="root-owned nonwritable executable",
    ):
        loader(
            purpose=purpose,
            authority_payload=payload,
            allowed_signers_path=str(allowed),
            signature_path=str(signature),
            reviewed_pin_records=reviewed_pin_records,
        )
    assert spawned == []


def test_sealed_loader_refuses_a_verifier_that_changes_during_use(tmp_path, signer):
    private, public_key_base64 = signer
    purpose = authority.FORMAL_EXECUTION_PURPOSE
    payload = b'{"formal_execution":"verifier-changed-during-use"}\n'
    allowed, signature = _signed_controls(
        tmp_path,
        private_key=private,
        public_key_base64=public_key_base64,
        payload=payload,
        namespace=authority.PURPOSE_NAMESPACES[purpose],
        stem="verifier-changed",
    )
    pin = _pin(public_key_base64, purpose)
    reviewed_pin_records = (
        (
            pin.key_id,
            pin.public_key_base64,
            pin.purposes,
            base64.b64decode(pin.public_key_base64, validate=True),
        ),
    )
    snapshots = iter((
        _fake_verifier_lstat(),
        _fake_verifier_lstat(verifier_mode=stat.S_IFREG | 0o555),
    ))
    sealed_snapshot = _production_closure("snapshot_trusted_verifier")

    def changing_snapshot():
        return _with_closure_values(sealed_snapshot, lstat=next(snapshots))()

    verified = []
    loader = _with_closure_values(
        _production_closure("load_with_reviewed_path_texts"),
        snapshot_trusted_verifier=changing_snapshot,
        run_signature_verifier=lambda *args: verified.append(args),
        require_trusted_verifier_unchanged=_with_closure_values(
            _production_closure("require_trusted_verifier_unchanged"),
            snapshot_trusted_verifier=changing_snapshot,
        ),
    )
    with pytest.raises(
        authority.OwnerSignatureAuthorityError,
        match="trusted ssh-keygen verifier changed during use",
    ):
        loader(
            purpose=purpose,
            authority_payload=payload,
            allowed_signers_path=str(allowed),
            signature_path=str(signature),
            reviewed_pin_records=reviewed_pin_records,
        )
    assert len(verified) == 1
