"""Machine-local Keychain credential lookup; no provider or file fallback.

This module never retrieves a credential on import. Callers must establish
their own narrowly bounded provider authority before requesting a secret.
Returned values are secrets and must never be printed, serialized, or logged.
"""
from __future__ import annotations

import subprocess
from types import MappingProxyType

KEYCHAIN = "/Users/sheltonchen/Library/Keychains/login.keychain-db"
SERVICES = MappingProxyType({
    "fmp": ("trading-agent-fmp", "fmp"),
    "massive": ("trading-agent-massive", "massive"),
    "eodhd": ("trading-agent-eodhd", "eodhd"),
    "sharadar": ("trading-agent-sharadar", "sharadar"),
})
MAX_KEY_BYTES = 4096


class KeychainUnavailable(ValueError):
    """Finite refusal, never a macOS or credential-bearing error string."""


def load_key(provider: str, *, timeout_seconds: float) -> str:
    """Read exactly one named generic password from the login keychain.

macOS may ask the user for approval. No access-control settings are changed.
Only the command's single final LF is removed; other whitespace is refused.
"""
    if (type(provider) is not str or provider not in SERVICES
            or type(timeout_seconds) not in (int, float)
            or not 0 < timeout_seconds <= 20):
        raise KeychainUnavailable("credentials_unavailable")
    service, account = SERVICES[provider]
    try:
        completed = subprocess.run(
            ["/usr/bin/security", "find-generic-password", "-s", service,
             "-a", account, "-w", KEYCHAIN],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=timeout_seconds, check=False,
        )
        payload = completed.stdout
        if (type(completed.returncode) is not int or completed.returncode != 0
                or type(payload) is not bytes or not payload.endswith(b"\n")):
            raise KeychainUnavailable("credentials_unavailable")
        payload = payload[:-1]
        if (not 8 <= len(payload) <= MAX_KEY_BYTES
                or any(value < 33 or value > 126 for value in payload)):
            raise KeychainUnavailable("credentials_unavailable")
        return payload.decode("ascii")
    except Exception:
        # Never stringify subprocess exceptions: their stdout can be a secret.
        raise KeychainUnavailable("credentials_unavailable") from None
