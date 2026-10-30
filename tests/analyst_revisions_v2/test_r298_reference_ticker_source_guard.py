"""In-root synthetic FDs/native ABI doubles; never inspect retained sources."""
import ctypes
import errno
import hashlib
import os
from pathlib import Path
import time
from types import SimpleNamespace

import pytest

from scripts import arv2_r298_reference_ticker_source_guard as m


@pytest.fixture
def case(tmp_path, monkeypatch):
    # Only this explicit test seam changes the fixed module constants. There
    # is no root, path, expected-pin or policy parameter in the public guard.
    root = tmp_path / 'synthetic-source-root'
    root.mkdir(mode=0o755); root.chmod(0o755)
    capture = root / 'artifacts/analyst_revisions_v2/sharadar_capture/arv2-sharadar-source-20260914T003329843989Z'
    current = root
    for component in capture.relative_to(root).parts:
        current = current / component
        current.mkdir(mode=0o700); current.chmod(0o700)
    manifest, archive = b'{"synthetic":true}\n', b'synthetic ZIP payload only'
    manifest_pin = hashlib.sha256(manifest).hexdigest()
    payloads = dict(zip(m.LEAVES, (manifest, (manifest_pin + '\n').encode('ascii'), archive)))
    for name, payload in payloads.items():
        leaf = capture / name
        leaf.write_bytes(payload); leaf.chmod(0o600)
    values = {name: bytes([65 + i]) * size
              for i, (name, size, _pin) in enumerate(m.VINTAGE_XATTR_PINS)}
    pins = tuple((name, len(value), hashlib.sha256(value).hexdigest())
                 for name, value in values.items())
    capture_ino = capture.stat().st_ino
    state = SimpleNamespace(root=root, capture=capture, payloads=payloads,
        values=values, names=None, acl_error=None, after_get=lambda: None,
        calls=[], pins=pins, ordinary={})

    class Native:
        def attrs(self, fd):
            return state.values if os.fstat(fd).st_ino == capture_ino else state.ordinary

        def acl_get_fd_np(self, fd, kind):
            state.calls.append(('acl', fd))
            ctypes.set_errno(state.acl_error if state.acl_error is not None else errno.ENOENT)
            return None

        def flistxattr(self, fd, buffer, maximum, options):
            attrs = self.attrs(fd)
            names = state.names if attrs and state.names is not None else tuple(sorted(attrs))
            raw = b'\0'.join(names) + (b'\0' if names else b'')
            ctypes.memmove(buffer, raw, min(len(raw), maximum))
            return len(raw)

        def fgetxattr(self, fd, name, buffer, maximum, position, options):
            state.calls.append(('xattr', fd, name))
            value = self.attrs(fd)[name]
            ctypes.memmove(buffer, value, min(len(value), maximum))
            state.after_get()
            return len(value)

    monkeypatch.setattr(m, 'ROOT', root)
    monkeypatch.setattr(m, 'CAPTURE', capture)
    monkeypatch.setattr(m, 'MANIFEST_SHA256', manifest_pin)
    monkeypatch.setattr(m, 'ARCHIVE_SHA256', hashlib.sha256(archive).hexdigest())
    monkeypatch.setattr(m, 'ARCHIVE_BYTES', len(archive))
    monkeypatch.setattr(m, 'VINTAGE_XATTR_PINS', pins)
    monkeypatch.setattr(m.security, '_native', Native)
    # Any accidental replay of the old assessed/relocated source is fatal.
    monkeypatch.setattr(m.historical, 'snapshot', lambda *a: pytest.fail('spent v4 snapshot'))
    monkeypatch.chdir(root)
    return state


def guard():
    return m.SourceGuard(deadline=time.monotonic() + 30)


def test_fixed_production_profile_and_no_operational_policy_parameter():
    value = m.profile_record()
    assert value['root'] == '/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2'
    assert value['leaves'] == ['manifest.json', 'manifest.sha256', '01-tickers-years-full.zip']
    assert value['manifest_sha256'] == '94251ffdf0529b118ff331b98c4a144d97bc734380d7e7333f94045e4aa6f09b'
    assert value['archive_byte_count'] == 4937076
    assert value['marker_byte_count'] == 65
    assert len(value['metadata_fields']) == 10
    assert value['vintage_xattrs'] == [
        {'name': name.decode('ascii'), 'size': size, 'sha256': pin}
        for name, size, pin in m.historical.XATTR_PINS]
    for key in ('historical_metadata_refreshed', 'old_v4_replayed', 'continuous_integrity_proven',
                'historical_continuity_proven', 'source_admission_granted', 'operational_authority_granted',
                'point_in_time_proven', 'formal_identity_admitted', 'formal_forward_ready', 'paper_or_live_ready'):
        assert value[key] is False
    with pytest.raises(TypeError): m.SourceGuard(root=Path('/tmp'), deadline=1)


def test_reads_only_fixed_three_byte_pins_holds_all_fds_through_consumer(case, monkeypatch):
    opened = []
    original = m.os.open
    def opening(name, *args, **kwargs):
        opened.append(name)
        return original(name, *args, **kwargs)
    monkeypatch.setattr(m.os, 'open', opening)
    value = guard()
    with value as held:
        descriptors = [row['fd'] for row in held._objects]
        assert len(descriptors) == len(case.capture.parts) + 3
        for name in m.LEAVES:
            assert held.read(name, held.deadline) == case.payloads[name]
        # The whole source guard outlives arbitrary memory-only consumers.
        assert all(os.fstat(fd) for fd in descriptors)
        assert [name for name in opened if name in m.LEAVES] == list(m.LEAVES)
        assert not any('actions' in str(name).lower() or 'fundamentals' in str(name).lower() for name in opened)
    for fd in descriptors:
        with pytest.raises(OSError): os.fstat(fd)
    with pytest.raises(m.Refused, match='state'): value.__enter__()


@pytest.mark.parametrize('name', m.LEAVES)
def test_each_leaf_is_one_read_only_no_retry(case, name):
    with guard() as held:
        held.read(name, held.deadline)
        with pytest.raises(m.Refused, match='read_spent'): held.read(name, held.deadline)


@pytest.mark.parametrize('name', ['02-actions.zip', '03-fundamentals.zip', '../manifest.json', '', None, True])
def test_other_names_never_open_or_read(case, name):
    with guard() as held:
        with pytest.raises(m.Refused, match='leaf'): held.read(name, held.deadline)


@pytest.mark.parametrize('index', range(10))
def test_all_ten_held_metadata_fields_preserved_through_consumer(case, monkeypatch, index):
    with pytest.raises(m.Refused, match='metadata_changed'):
        with guard() as held:
            original = m._metadata
            target = held._by_path[case.capture / m.LEAVES[2]]['fd']
            def changed(fd):
                values = original(fd)
                return tuple(value + 1 if offset == index and fd == target else value
                             for offset, value in enumerate(values))
            monkeypatch.setattr(m, '_metadata', changed)


def test_named_leaf_replacement_detected_even_original_fd_unchanged(case):
    with pytest.raises(m.Refused):
        with guard() as held:
            leaf = case.capture / m.LEAVES[0]
            leaf.rename(case.capture / 'displaced-synthetic-manifest')
            leaf.write_bytes(case.payloads[m.LEAVES[0]]); leaf.chmod(0o600)
            held.verify()


@pytest.mark.parametrize('target', ['system_ancestor', 'root', 'vintage', 'leaf'])
def test_named_full_chain_is_checked_independently_of_held_fd_metadata(case, monkeypatch, target):
    with pytest.raises(m.Refused, match='named_changed'):
        with guard() as held:
            path = {'system_ancestor': Path('/'), 'root': case.root,
                    'vintage': case.capture, 'leaf': case.capture / m.LEAVES[0]}[target]
            original = m.SourceGuard._named
            def changed(self, row):
                values = original(self, row)
                return tuple(value + 1 if i == 1 and row['path'] == path else value
                             for i, value in enumerate(values))
            monkeypatch.setattr(m.SourceGuard, '_named', changed)
            held.verify()


@pytest.mark.parametrize('position', ['root', 'capture', 'leaf'])
def test_nofollow_scope_components_and_leaves(case, position):
    selected = {'root': case.root, 'capture': case.capture,
                'leaf': case.capture / m.LEAVES[0]}[position]
    moved = selected.with_name(selected.name + '-original')
    selected.rename(moved)
    selected.symlink_to(moved, target_is_directory=position != 'leaf')
    with pytest.raises(m.Refused):
        with guard(): pass


@pytest.mark.parametrize('target,mode', [('root', 0o700), ('capture', 0o755), ('leaf', 0o644)])
def test_preserves_exact_original_scoped_modes(case, target, mode):
    path = {'root': case.root, 'capture': case.capture, 'leaf': case.capture / m.LEAVES[0]}[target]
    path.chmod(mode)
    with pytest.raises(m.Refused, match='directory_policy|file_policy'):
        with guard(): pass


def test_system_ancestors_do_not_receive_private_scope_acl_or_owner_policy(case, monkeypatch):
    seen = []
    original = m.SourceGuard._security
    def observe(self, row):
        if row['path'] != case.root and case.root not in row['path'].parents:
            seen.append(row['path'])
            assert row.get('security') is None
        return original(self, row)
    monkeypatch.setattr(m.SourceGuard, '_security', observe)
    with guard(): pass
    assert Path('/') in seen and case.root.parent in seen


@pytest.mark.parametrize('which', ['extra', 'missing', 'value', 'acl'])
def test_native_vintage_exact_names_values_and_empty_acl_required(case, which):
    if which == 'extra': case.names = tuple(sorted((*case.values, b'new.unapproved')))
    elif which == 'missing': case.names = tuple(sorted(case.values))[1:]
    elif which == 'value':
        first = next(iter(case.values)); case.values[first] = b'Z' * len(case.values[first])
    else: case.acl_error = errno.EACCES
    with pytest.raises(m.Refused, match='xattr_names|xattr_values|security_observation'):
        with guard(): pass


def test_native_security_drift_after_consumer_cannot_be_accepted(case):
    with pytest.raises(m.Refused, match='xattr_values'):
        with guard():
            first = next(iter(case.values)); case.values[first] = b'Z' * len(case.values[first])


def test_native_acl_entry_refuses_and_partial_enter_closes_every_fd(case, monkeypatch):
    descriptors = []
    original_open = m.os.open
    def opening(*args, **kwargs):
        fd = original_open(*args, **kwargs); descriptors.append(fd); return fd
    monkeypatch.setattr(m.os, 'open', opening)
    def acl(*args): raise m.security.Refusal('extended ACL entry present')
    monkeypatch.setattr(m.security, '_require_empty_acl', acl)
    with pytest.raises(m.Refused, match='security_observation'):
        with guard(): pass
    assert descriptors
    for fd in descriptors:
        with pytest.raises(OSError): os.fstat(fd)


def test_vintage_native_duplicate_name_census_refuses(case):
    first = next(iter(case.values))
    case.names = (first, first)
    with pytest.raises(m.Refused, match='security_observation'):
        with guard(): pass


def test_ordinary_objects_remain_provenance_only_and_opaque_pin_stable(case):
    case.ordinary = {b'com.apple.provenance': b'opaque synthetic provenance'}
    with guard(): pass
    with pytest.raises(m.Refused, match='security_changed'):
        with guard():
            case.ordinary[b'com.apple.provenance'] = b'changed opaque provenance'
    case.ordinary = {b'com.apple.macl': b'no general exception'}
    with pytest.raises(m.Refused, match='security_observation'):
        with guard(): pass


@pytest.mark.parametrize('name', m.LEAVES)
def test_unchanged_size_wrong_bytes_refuse_not_source_admitted(case, name):
    path = case.capture / name
    payload = case.payloads[name]
    path.write_bytes(bytes([payload[0] ^ 1]) + payload[1:])
    with pytest.raises(m.Refused, match='byte_pin'):
        with guard() as held: held.read(name, held.deadline)


def test_primary_exception_preserved_all_fds_closed(case):
    with pytest.raises(ValueError, match='synthetic primary'):
        with guard() as held:
            descriptors = [row['fd'] for row in held._objects]
            raise ValueError('synthetic primary')
    for fd in descriptors:
        with pytest.raises(OSError): os.fstat(fd)


def test_deadline_no_extension_or_partial_enter_leak(case):
    with pytest.raises(m.Refused, match='deadline'):
        with m.SourceGuard(deadline=time.monotonic() - 1): pass
    with guard() as held:
        with pytest.raises(AttributeError): held.deadline += 1
        with pytest.raises(m.Refused, match='deadline'): held.read(m.LEAVES[0], held.deadline + 1)
        assert m.LEAVES[0] in held._reads


@pytest.mark.parametrize('value', [None, True, float('inf'), float('nan'), '100'])
def test_invalid_deadline_before_any_open(value):
    with pytest.raises(m.Refused, match='deadline'): m.SourceGuard(deadline=value)


def test_finite_error_never_stringifies_unknown_objects():
    class Hostile:
        def __str__(self): raise AssertionError('must not render')
    assert m.finite(ValueError(Hostile())) == 'state'
    for code in m.FINITE: assert m.finite(m.Refused(code)) == code
    assert m.finite(m.Refused(Hostile())) == 'state'
