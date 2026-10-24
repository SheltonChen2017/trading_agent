"""Read one explicitly named macOS Keychain credential without publishing it.

The owner supplied these four service/account pairs on 2026-10-13. Import is
inert: no Keychain, provider, file or environment discovery occurs. The caller
must separately enforce lane identity, preregistration and private acquisition
custody before reading a credential. Credential presence grants no entitlement,
rights, source/PIT evidence, outcome look, QuantConnect job or trading authority.

The real subprocess has fixed nonsecret arguments and a minimal environment.
Its stdout is bounded before accumulation, stderr is discarded, and timeout or
refusal cleanup kills its isolated process group. No secret is logged, hashed,
copied to a file or placed in arguments/environment. Python does not guarantee
erasure of immutable secret strings from memory; no such guarantee is claimed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import os
import re
import selectors
import signal
import subprocess
import sys
import time
from types import MappingProxyType
from typing import Callable


KEYCHAIN_ITEMS = MappingProxyType({
    "fmp": ("trading-agent-fmp", "fmp"),
    "sharadar": ("trading-agent-sharadar", "sharadar"),
    "massive": ("trading-agent-massive", "massive"),
    "eodhd": ("trading-agent-eodhd", "eodhd"),
})
MAX_CREDENTIAL_BYTES = 4096
TIMEOUT_SECONDS = 10
_MAX_OUTPUT_BYTES = MAX_CREDENTIAL_BYTES + 1  # security adds one terminal LF.
_SECRET = re.compile(rb"[!-~]+\Z")
_CHILD_ENV = MappingProxyType({"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"})
_READ_REFUSALS = frozenset({
    "keychain_process_refused", "keychain_read_timeout", "keychain_item_missing",
    "keychain_access_unavailable", "keychain_read_refused", "keychain_output_oversized",
    "keychain_credential_refused", "keychain_operation_refused",
})


class KeychainCredentialError(ValueError):
    """Only fixed refusal codes, never supplied names or upstream output."""


@dataclass(frozen=True, slots=True, repr=False)
class KeychainCredential:
    provider: str
    value: str = field(repr=False)
    fixture_only: bool = False

    def __repr__(self) -> str:
        return "KeychainCredential(<credential redacted>)"


def _stop_process(process: subprocess.Popen | None) -> None:
    """Reap the isolated child and descendants, without reading their output."""
    if not isinstance(process, subprocess.Popen):
        return
    try:
        try:
            # The leader may already have exited while a descendant retains
            # its stdout pipe. Its dedicated group still needs termination.
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError:
            # A failed group operation must still terminate the live child.
            if process.poll() is None:
                try:
                    process.kill()
                except OSError:
                    pass
        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass
        process.wait(timeout=1)
    finally:
        if process.stdout is not None:
            process.stdout.close()


def _bounded_stdout(process: subprocess.Popen, deadline: float) -> bytes:
    if not isinstance(process, subprocess.Popen) or process.stdout is None:
        raise KeychainCredentialError("keychain_process_refused")
    descriptor = process.stdout.fileno()
    os.set_blocking(descriptor, False)
    raw = bytearray()
    with selectors.DefaultSelector() as selector:
        selector.register(descriptor, selectors.EVENT_READ)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not selector.select(remaining):
                raise KeychainCredentialError("keychain_read_timeout")
            try:
                chunk = os.read(descriptor, _MAX_OUTPUT_BYTES + 1 - len(raw))
            except BlockingIOError:
                continue
            if not chunk:
                break
            raw.extend(chunk)
            if len(raw) > _MAX_OUTPUT_BYTES:
                raise KeychainCredentialError("keychain_output_oversized")
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise KeychainCredentialError("keychain_read_timeout")
    try:
        code = process.wait(timeout=remaining)
    except subprocess.TimeoutExpired:
        raise KeychainCredentialError("keychain_read_timeout") from None
    if code == 44:  # errSecItemNotFound, as security's process exit status.
        raise KeychainCredentialError("keychain_item_missing")
    if code in {36, 51, 128}:
        # Interaction-not-allowed, authentication failure or user cancellation;
        # these do not establish whether the item exists or a key is valid.
        raise KeychainCredentialError("keychain_access_unavailable")
    if code != 0:
        raise KeychainCredentialError("keychain_read_refused")
    return bytes(raw)


def read_keychain_credential(provider: str, *, _process_factory: Callable | None = None) -> KeychainCredential:
    """Read exactly the owner's pair; injected processes are fixture evidence.

    No arbitrary service/account, alternate keychain, shell or fallback source
    can be selected. This helper does not create/update Keychain items or accept
    access prompts; a denied/locked item is a sanitized external-state refusal.
    Callers must not serialize the returned value or its dataclass fields.
    """
    if type(provider) is not str or provider not in KEYCHAIN_ITEMS:
        raise KeychainCredentialError("keychain_provider_refused")
    fixture_only = _process_factory is not None
    if not fixture_only and sys.platform != "darwin":
        raise KeychainCredentialError("macos_keychain_required")
    if fixture_only and not callable(_process_factory):
        raise KeychainCredentialError("keychain_process_factory_refused")
    service, account = KEYCHAIN_ITEMS[provider]
    factory = subprocess.Popen if _process_factory is None else _process_factory
    process = None
    try:
        deadline = time.monotonic() + TIMEOUT_SECONDS
        process = factory(
            ("/usr/bin/security", "find-generic-password", "-s", service, "-a", account, "-w"),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            shell=False, env=dict(_CHILD_ENV), close_fds=True, bufsize=0,
            start_new_session=True,
        )
        raw = _bounded_stdout(process, deadline)
        if raw.endswith(b"\n"):
            raw = raw[:-1]
        if (not 1 <= len(raw) <= MAX_CREDENTIAL_BYTES or _SECRET.fullmatch(raw) is None
                or raw.lower() == b"test-api-key"):
            raise KeychainCredentialError("keychain_credential_refused")
        return KeychainCredential(provider, raw.decode("ascii"), fixture_only)
    except KeychainCredentialError as exc:
        if len(exc.args) == 1 and type(exc.args[0]) is str and exc.args[0] in _READ_REFUSALS:
            raise KeychainCredentialError(exc.args[0]) from None
        raise KeychainCredentialError("keychain_operation_refused") from None
    except Exception:
        # This is a secret-bearing operational boundary, not a permissive
        # fallback. Even an unexpected dependency failure must remain refused
        # without publishing its arguments or captured output.
        raise KeychainCredentialError("keychain_operation_refused") from None
    finally:
        try:
            _stop_process(process)
        except Exception:
            raise KeychainCredentialError("keychain_process_cleanup_refused") from None


__all__ = ["KEYCHAIN_ITEMS", "KeychainCredential", "KeychainCredentialError", "read_keychain_credential"]
