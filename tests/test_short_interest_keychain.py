"""Fabricated credential results only; never call the actual OS Keychain."""
from __future__ import annotations

import json
import pickle
from types import SimpleNamespace

import pytest

import scripts.short_interest_keychain as keys
import os

# Only protected-I/O cases require POSIX; pure parsing, transport and early
# refusal checks must remain active on the supported Windows host.
_POSIX_CAPTURE_ONLY = pytest.mark.skipif(
    not hasattr(os, "getuid"),
    reason=(
        "the protected-capture runtime requires POSIX ownership and mode "
        "semantics (os.getuid, O_NOFOLLOW, 0o600/0o700, symlinks); it cannot "
        "execute on this host, see the lane record SI-CR17-002"
    ),
)


@pytest.fixture
def reader(monkeypatch):
    calls = []
    monkeypatch.setattr(keys, '_validate_keychain', lambda: None)

    def fake(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout=b'fabricated-key-only\n', stderr=b'')

    monkeypatch.setattr(keys.subprocess, 'run', fake)
    return calls


@pytest.mark.parametrize('provider', tuple(keys.ITEMS))
def test_exact_owner_item_no_search_or_inherited_credentials(reader, provider):
    secret = keys.read_named_keychain(provider)
    service, account = keys.ITEMS[provider]
    assert reader[0][0][0] == ['/usr/bin/security', 'find-generic-password', '-s',
                              service, '-a', account, '-w', str(keys.KEYCHAIN)]
    assert reader[0][1]['env'] == {'PATH': '/usr/bin:/bin'}
    assert reader[0][1]['timeout'] == 10
    assert secret.for_authorization_header() == 'fabricated-key-only'
    assert 'fabricated-key-only' not in str(secret) + repr(secret)
    assert secret.echoed_in(b'body fabricated-key-only')


@pytest.mark.parametrize('provider', ('unknown', '', 3, True, ['eodhd']))
def test_no_guessed_item_or_command_injection(reader, provider):
    with pytest.raises(keys.ShortInterestKeychainError, match='unknown_owner_keychain_item'):
        keys.read_named_keychain(provider)
    assert not reader


@pytest.mark.parametrize('stdout', (b'bad\r\n', b'bad\nvalue\n', b'bad value\n', b'\n', b'\xff', b'a' * 4099))
def test_malformed_secret_never_reaches_header_or_error(reader, monkeypatch, stdout):
    monkeypatch.setattr(keys.subprocess, 'run', lambda *a, **k:
                        SimpleNamespace(returncode=0, stdout=stdout, stderr=b'private-diagnostic'))
    with pytest.raises(keys.ShortInterestKeychainError) as error:
        keys.read_named_keychain('eodhd')
    assert str(error.value) == 'keychain_credential_format_refused'


def test_refusal_redacts_system_output(reader, monkeypatch):
    monkeypatch.setattr(keys.subprocess, 'run', lambda *a, **k:
                        SimpleNamespace(returncode=44, stdout=b'private-value', stderr=b'private-value'))
    with pytest.raises(keys.ShortInterestKeychainError) as error:
        keys.read_named_keychain('eodhd')
    assert str(error.value) == 'owner_keychain_item_unavailable'


def test_secret_not_json_pickle_or_plain_text(reader):
    secret = keys.read_named_keychain('eodhd')
    with pytest.raises(TypeError):
        json.dumps(secret)
    with pytest.raises(keys.ShortInterestKeychainError, match='serialization_refused'):
        pickle.dumps(secret)
    assert str(secret) == '<redacted>'


def test_platform_first_no_item_read(monkeypatch):
    monkeypatch.setattr(keys.sys, 'platform', 'win32')
    monkeypatch.setattr(keys.subprocess, 'run', lambda *a, **k: pytest.fail('must not call security'))
    with pytest.raises(keys.ShortInterestKeychainError, match='macos_login_keychain_required'):
        keys.read_named_keychain('eodhd')


@pytest.mark.parametrize('filemode,owner', ((0o120600, 123), (0o100620, 123), (0o100600, 124)))
@_POSIX_CAPTURE_ONLY
def test_path_owner_symlink_and_writable_storage_refuse_before_security(monkeypatch, filemode, owner):
    monkeypatch.setattr(keys.sys, 'platform', 'darwin')
    monkeypatch.setattr(keys.os, 'getuid', lambda: 123)
    monkeypatch.setattr(keys.Path, 'lstat', lambda path:
                        SimpleNamespace(st_mode=filemode, st_uid=owner))
    monkeypatch.setattr(keys.subprocess, 'run', lambda *a, **k: pytest.fail('must not call security'))
    with pytest.raises(keys.ShortInterestKeychainError, match='owner_keychain_path_refused'):
        keys.read_named_keychain('eodhd')


@_POSIX_CAPTURE_ONLY
def test_parent_symlink_refuses_before_security(monkeypatch):
    monkeypatch.setattr(keys.sys, 'platform', 'darwin')
    monkeypatch.setattr(keys.os, 'getuid', lambda: 123)
    monkeypatch.setattr(keys.Path, 'lstat', lambda path:
                        SimpleNamespace(st_mode=0o100600 if path==keys.KEYCHAIN else 0o120700,
                                        st_uid=123))
    monkeypatch.setattr(keys.subprocess, 'run', lambda *a, **k: pytest.fail('must not call security'))
    with pytest.raises(keys.ShortInterestKeychainError, match='owner_keychain_parent_refused'):
        keys.read_named_keychain('eodhd')
