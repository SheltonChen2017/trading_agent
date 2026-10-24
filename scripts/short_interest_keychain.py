"""Read only owner-named macOS login-Keychain items for this research lane.

Never open the encrypted database, search other items, change ACLs or serialize
credential values. A named item is access evidence, not dataset entitlement.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from urllib.parse import unquote_to_bytes

KEYCHAIN = Path('/Users/sheltonchen/Library/Keychains/login.keychain-db')
ITEMS = {
    'fmp': ('trading-agent-fmp', 'fmp'),
    'sharadar': ('trading-agent-sharadar', 'sharadar'),
    'massive': ('trading-agent-massive', 'massive'),
    'eodhd': ('trading-agent-eodhd', 'eodhd'),
}


class ShortInterestKeychainError(ValueError):
    """Fixed diagnostics never include security stderr or credential values."""


class KeychainSecret:
    __slots__ = ('__value',)

    def __init__(self, value: str):
        if (type(value) is not str or not 1 <= len(value) <= 4096
                or any(not 33 <= ord(c) <= 126 for c in value)):
            raise ShortInterestKeychainError('keychain_credential_format_refused')
        self.__value = value

    def __repr__(self):
        return 'KeychainSecret(<redacted>)'

    def __str__(self):
        return '<redacted>'

    def __reduce__(self):
        raise ShortInterestKeychainError('keychain_credential_serialization_refused')

    def for_authorization_header(self) -> str:
        """Release only to the fixed HTTPS runtime's in-memory header builder."""
        return self.__value

    def echoed_in(self, raw: bytes) -> bool:
        if type(raw) is not bytes:
            raise ShortInterestKeychainError('keychain_response_type_refused')
        needle, candidate = self.__value.encode('ascii'), raw

        def ascii_escape(match):
            value = int(match.group(1), 16)
            return bytes((value,)) if value < 128 else match.group(0)

        # Check before response hashes/publication, including malformed JSON
        # and duplicate keys. Decoding is bounded, in memory and not logged.
        for _ in range(3):
            if needle in candidate:
                return True
            previous = candidate
            if b'%' in candidate:
                candidate = unquote_to_bytes(candidate)
            if b'\\' in candidate:
                candidate = re.sub(rb'\\u([0-9a-fA-F]{4})', ascii_escape, candidate)
                candidate = candidate.replace(b'\\/', b'/').replace(b'\\"', b'"').replace(b'\\\\', b'\\')
            if candidate == previous:
                break
        return needle in candidate


def _validate_keychain():
    if sys.platform != 'darwin' or os.name != 'posix' or not callable(getattr(os, 'getuid', None)):
        raise ShortInterestKeychainError('macos_login_keychain_required')
    uid = os.getuid()
    try:
        metadata = KEYCHAIN.lstat()
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != uid
                or metadata.st_mode & 0o022):
            raise ShortInterestKeychainError('owner_keychain_path_refused')
        for parent in KEYCHAIN.parents:
            item = parent.lstat()
            if (not stat.S_ISDIR(item.st_mode) or item.st_uid not in {0, uid}
                    or item.st_mode & 0o022):
                raise ShortInterestKeychainError('owner_keychain_parent_refused')
    except OSError:
        raise ShortInterestKeychainError('owner_keychain_path_unavailable') from None


def read_named_keychain(provider: str) -> KeychainSecret:
    """Existing exact item only; UI lock/access failure is never bypassed."""
    _validate_keychain()
    if type(provider) is not str or provider not in ITEMS:
        raise ShortInterestKeychainError('unknown_owner_keychain_item')
    service, account = ITEMS[provider]
    try:
        result = subprocess.run(
            ['/usr/bin/security', 'find-generic-password', '-s', service,
             '-a', account, '-w', str(KEYCHAIN)],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=10, check=False, env={'PATH': '/usr/bin:/bin'},
        )
    except (OSError, subprocess.SubprocessError):
        raise ShortInterestKeychainError('owner_keychain_access_unavailable') from None
    if type(result.returncode) is not int or result.returncode != 0:
        raise ShortInterestKeychainError('owner_keychain_item_unavailable')
    if type(result.stdout) is not bytes or not 1 <= len(result.stdout) <= 4098:
        raise ShortInterestKeychainError('keychain_credential_format_refused')
    raw = result.stdout[:-1] if result.stdout.endswith(b'\n') else result.stdout
    try:
        value = raw.decode('ascii')
    except UnicodeError:
        raise ShortInterestKeychainError('keychain_credential_format_refused') from None
    return KeychainSecret(value)
