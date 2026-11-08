"""Synthetic in-root files only; no retained controls or private data reads."""
import copy
import ctypes
import errno
import os
from pathlib import Path
import stat
import time
from types import SimpleNamespace

import pytest

from scripts import arv2_r298_fixed_data_guard as m


@pytest.fixture
def case(tmp_path, monkeypatch):
    root = tmp_path / 'synthetic-fixed-data-root'
    root.mkdir(mode=0o755); root.chmod(0o755)
    payloads = {'first': b'synthetic-first', 'second': b'synthetic-second'}
    plan, leaves = {}, {}
    for role, raw in payloads.items():
        relative = 'artifacts/analyst_revisions_v2/synthetic/' + role + '/data.bin'
        leaf = root / relative
        current = root
        for component in leaf.parent.relative_to(root).parts:
            current = current / component
            current.mkdir(mode=0o700, exist_ok=True); current.chmod(0o700)
        leaf.write_bytes(raw); leaf.chmod(0o600)
        leaves[role] = leaf
        plan[role] = {'relative_path': relative, 'byte_count': len(raw), 'sha256': m.sha(raw)}
    monkeypatch.setattr(m, 'ROOT', root)
    monkeypatch.chdir(root)
    return SimpleNamespace(root=root, payloads=payloads, plan=plan, leaves=leaves)


def guard(case):
    return m.FixedDataGuard(case.plan, deadline=time.monotonic() + 30)


def refused(code, callback):
    with pytest.raises(m.Refused) as error:
        callback()
    assert m.finite(error.value) == code


def test_active_plan_digest_cannot_be_changed_to_accept_other_same_size_bytes(case):
    original = case.payloads['first']
    changed = b'X' * len(original)
    case.leaves['first'].write_bytes(changed)
    with pytest.raises(m.Refused) as caught:
        with guard(case) as held:
            held.plan['first']['sha256'] = m.sha(changed)
            held.read_all_once()
    assert m.finite(caught.value) == 'plan'


@pytest.fixture
def native(case, monkeypatch):
    state = SimpleNamespace(attrs={b'com.apple.provenance': b'synthetic opaque attribute'},
        acl_errno=errno.ENOENT, acl_entry=False, seen=set(), calls=[])
    class Native:
        def acl_get_fd_np(self, fd, kind):
            state.seen.add((os.fstat(fd).st_dev, os.fstat(fd).st_ino))
            state.calls.append(('acl', fd))
            ctypes.set_errno(state.acl_errno)
            return 1 if state.acl_entry else None
        def acl_get_entry(self, acl, option, entry):
            return 0
        def acl_free(self, value): return 0
        def flistxattr(self, fd, buffer, maximum, options):
            raw = b'\0'.join(sorted(state.attrs)) + (b'\0' if state.attrs else b'')
            ctypes.memmove(buffer, raw, min(len(raw), maximum)); return len(raw)
        def fgetxattr(self, fd, name, buffer, maximum, position, options):
            state.calls.append(('xattr', fd, name))
            raw = state.attrs[name]
            ctypes.memmove(buffer, raw, min(len(raw), maximum)); return len(raw)
    monkeypatch.setattr(m.security, '_native', Native)
    return state


def test_real_native_security_and_private_file_modes_roundtrip(case):
    with guard(case) as held:
        assert held.read_all_once() == case.payloads
        receipt = held.receipt()
        assert receipt == m.validate_receipt(receipt, case.plan)
        assert all(row['metadata'] == m._metadata(row['fd']) for row in held.objects)
    assert held.active is False and held.spent is True and not held.objects
    assert receipt['requires_normal_return_before_use'] is True


def test_all_unique_components_held_once_and_security_is_root_scoped(case, native, monkeypatch):
    opens, original = [], os.open
    def observe(path, flags, *args, **kwargs):
        opens.append((path, flags))
        return original(path, flags, *args, **kwargs)
    monkeypatch.setattr(m.os, 'open', observe)
    with guard(case) as held:
        assert len(held.objects) == len({row['path'] for row in held.objects})
        assert len(held.objects) == len({row['fd'] for row in held.objects})
        scoped = {tuple(row['metadata'][:2]) for row in held.objects
            if row['path'] == case.root or case.root in row['path'].parents}
        assert native.seen == scoped
        assert all(row['security'] is None for row in held.objects
            if row['path'] != case.root and case.root not in row['path'].parents)
        assert all(len(row['metadata']) == 10 for row in held.objects)
        assert held.read_all_once() == case.payloads
    assert len(opens) == len({row[0] for row in opens}) + 1  # two distinct same-named data.bin leaves
    assert all(flags & os.O_NOFOLLOW for _, flags in opens)


@pytest.mark.parametrize('field', range(10))
def test_all_ten_held_metadata_fields_checked_on_normal_return(case, native, monkeypatch, field):
    with pytest.raises(m.Refused) as caught:
        with guard(case) as held:
            held.read_all_once()
            target, original = held.by_role['second']['fd'], m._metadata
            def changed(fd):
                values = original(fd)
                return tuple(value + 1 if fd == target and index == field else value
                    for index, value in enumerate(values))
            monkeypatch.setattr(m, '_metadata', changed)
    assert m.finite(caught.value) == 'named_changed'


@pytest.mark.parametrize('field', range(10))
def test_all_ten_named_metadata_fields_checked_independently(case, native, monkeypatch, field):
    with pytest.raises(m.Refused) as caught:
        with guard(case) as held:
            target, original = held.by_role['second'], m._named
            def changed(parent, name):
                values = original(parent, name)
                return tuple(value + 1 if parent == target['parent'] and name == target['name']
                    and index == field else value for index, value in enumerate(values))
            monkeypatch.setattr(m, '_named', changed)
            held.verify()
    assert m.finite(caught.value) == 'named_changed'


@pytest.mark.parametrize('target', ['root', 'directory', 'leaf'])
def test_symbolic_link_components_never_admit_target(case, native, target):
    path = case.root if target == 'root' else case.leaves['first'].parent if target == 'directory' else case.leaves['first']
    moved = path.with_name(path.name + '-moved')
    path.rename(moved); path.symlink_to(moved, target_is_directory=target != 'leaf')
    with pytest.raises(m.Refused):
        with guard(case): pass


@pytest.mark.parametrize('target,mode', [('root', 0o700), ('directory', 0o755), ('leaf', 0o644)])
def test_exact_scoped_modes_required(case, native, target, mode):
    path = case.root if target == 'root' else case.leaves['first'].parent if target == 'directory' else case.leaves['first']
    path.chmod(mode)
    with pytest.raises(m.Refused) as caught:
        with guard(case): pass
    assert m.finite(caught.value) == 'shape'


def test_hard_linked_leaf_refused(case, native):
    os.link(case.leaves['first'], case.leaves['first'].with_name('extra-link'))
    with pytest.raises(m.Refused) as caught:
        with guard(case): pass
    assert m.finite(caught.value) == 'shape'


def test_fifo_refused_before_nonblocking_open_or_any_byte_read(case, native, monkeypatch):
    case.leaves['first'].unlink(); os.mkfifo(case.leaves['first'], 0o600)
    def deny(*args): raise AssertionError('FIFO was read')
    monkeypatch.setattr(m.os, 'read', deny)
    with pytest.raises(m.Refused) as caught:
        with guard(case): pass
    assert m.finite(caught.value) == 'shape'


def test_named_inode_swap_detected_before_byte_consumption(case, native, monkeypatch):
    original, changed = os.open, False
    def swap(path, flags, *args, **kwargs):
        nonlocal changed
        if path == 'data.bin' and not changed:
            changed = True
            leaf = case.leaves['first']; leaf.rename(leaf.with_name('prior-data'))
            leaf.write_bytes(case.payloads['first']); leaf.chmod(0o600)
        return original(path, flags, *args, **kwargs)
    monkeypatch.setattr(m.os, 'open', swap)
    with pytest.raises(m.Refused) as caught:
        with guard(case): pass
    assert m.finite(caught.value) == 'named_changed'


@pytest.mark.parametrize('fault', ['acl_unavailable', 'acl_entry', 'unapproved_xattr'])
def test_native_ACL_and_xattr_policy_cannot_be_bypassed(case, native, fault):
    if fault == 'acl_unavailable': native.acl_errno = errno.EPERM
    elif fault == 'acl_entry': native.acl_entry = True
    else: native.attrs[b'new.unapproved'] = b'synthetic'
    with pytest.raises(m.Refused) as caught:
        with guard(case): pass
    assert m.finite(caught.value) == 'security'


def test_opaque_xattr_value_drift_refuses_even_metadata_is_unchanged(case, native):
    with pytest.raises(m.Refused) as caught:
        with guard(case) as held:
            held.read_all_once()
            native.attrs[b'com.apple.provenance'] = b'new same-scope synthetic value'
    assert m.finite(caught.value) == 'security_changed'


def test_second_read_and_reenter_are_spent(case, native):
    held = guard(case)
    with held:
        assert held.read_all_once() == case.payloads
        refused('read_spent', held.read_all_once)
    refused('state', held.__enter__)
    refused('state', held.receipt)


def test_receipt_requires_every_planned_leaf_read(case, native):
    with guard(case) as held:
        refused('state', held.receipt)
        held.read_all_once()
        assert set(held.receipt()['files']) == set(case.plan)


def test_wrong_byte_pin_spends_read_and_does_not_repair_data(case, native):
    case.plan['second']['sha256'] = '0' * 64
    held = guard(case)
    with held:
        refused('byte_pin', held.read_all_once)
        refused('read_spent', held.read_all_once)
    assert case.leaves['second'].read_bytes() == case.payloads['second']


@pytest.mark.parametrize('key,value', [('relative_path', 'artifacts/analyst_revisions_v2/elsewhere/data.bin'),
    ('byte_count', 1), ('sha256', '0' * 64)])
def test_any_active_plan_field_mutation_refuses_before_further_read(case, native, key, value):
    with pytest.raises(m.Refused) as caught:
        with guard(case) as held:
            held.plan['first'][key] = value
            held.read_all_once()
    assert m.finite(caught.value) == 'plan'


def test_external_plan_is_copied_not_mutably_aliased(case, native):
    held = guard(case)
    original = copy.deepcopy(case.plan)
    case.plan['first']['sha256'] = '0' * 64
    with held:
        assert held.plan == original and held.read_all_once() == case.payloads


@pytest.mark.parametrize('value', [None, True, -1, float('nan'), float('inf')])
def test_deadline_rejects_invalid_values(case, value):
    refused('deadline', lambda: m.FixedDataGuard(case.plan, deadline=value))


def test_deadline_cannot_extend_beyond_fixed_maximum(case):
    refused('deadline', lambda: m.FixedDataGuard(case.plan, deadline=time.monotonic() + m.MAX_SECONDS + 1))


@pytest.mark.parametrize('kind', ['empty', 'role', 'unknown_field', 'duplicate_path', 'absolute', 'traversal',
    'backslash', 'wrong_prefix', 'dot', 'slash', 'bool_size', 'oversize', 'bad_hash', 'too_many', 'total'])
def test_bad_or_ambiguous_plans_refuse(case, kind, monkeypatch):
    plan = copy.deepcopy(case.plan)
    if kind == 'empty': plan = {}
    elif kind == 'role': plan['BAD-ROLE'] = plan.pop('first')
    elif kind == 'unknown_field': plan['first']['extra'] = True
    elif kind == 'duplicate_path': plan['second'] = dict(plan['first'])
    elif kind == 'absolute': plan['first']['relative_path'] = '/' + plan['first']['relative_path']
    elif kind == 'traversal': plan['first']['relative_path'] = 'artifacts/analyst_revisions_v2/../data.bin'
    elif kind == 'backslash': plan['first']['relative_path'] += '\\unsafe'
    elif kind == 'wrong_prefix': plan['first']['relative_path'] = 'artifacts/other/data/file'
    elif kind == 'dot': plan['first']['relative_path'] += '/.'
    elif kind == 'slash': plan['first']['relative_path'] = plan['first']['relative_path'].replace('/synthetic/', '//synthetic/')
    elif kind == 'bool_size': plan['first']['byte_count'] = True
    elif kind == 'oversize': plan['first']['byte_count'] = m.MAX_FILE_BYTES + 1
    elif kind == 'bad_hash': plan['first']['sha256'] = 'RAW-private-value'
    elif kind == 'too_many':
        plan = {'role' + str(i): {**plan['first'], 'relative_path': f'artifacts/analyst_revisions_v2/test/data{i}'}
            for i in range(m.MAX_FILES + 1)}
    else: monkeypatch.setattr(m, 'MAX_TOTAL_BYTES', 1)
    refused('plan', lambda: m.checked_plan(plan))


@pytest.mark.parametrize('fault', ['schema', 'profile', 'file_hash', 'metadata_hash', 'extra', 'flag'])
def test_receipt_closed_plan_and_false_continuity_flags(case, native, fault):
    with guard(case) as held:
        held.read_all_once(); receipt = held.receipt()
    if fault == 'schema': receipt['schema'] = 'other'
    elif fault == 'profile': receipt['profile_sha256'] = '0' * 64
    elif fault == 'file_hash': receipt['files']['second']['sha256'] = '0' * 64
    elif fault == 'metadata_hash': receipt['files']['second']['current_metadata_sha256'] = 'RAW-private-value'
    elif fault == 'extra': receipt['files']['second']['private-row'] = 'must-not-escape'
    else: receipt['historical_continuity_proven'] = True
    refused('receipt', lambda: m.validate_receipt(receipt, case.plan))


def test_profile_does_not_grant_source_or_publication_authority(case):
    profile = m.profile_record(case.plan)
    assert profile['metadata_fields'] == list(m.FIELDS) and len(m.FIELDS) == 10
    for key in ('operational_authority_granted', 'source_admission_granted', 'price_admission_granted',
        'historical_continuity_proven', 'continuous_integrity_proven', 'paper_or_live_ready'):
        assert profile[key] is False
    assert profile['generic_technical_guard_not_protocol_or_attempt_authority'] is True


def test_body_exception_does_not_convert_to_success_or_reuse(case, native):
    held = guard(case)
    with pytest.raises(RuntimeError):
        with held:
            held.read_all_once()
            raise RuntimeError('synthetic consumer failure')
    assert held.active is False and held.spent is True and not held.objects
    refused('state', held.__enter__)


def test_close_failure_is_explicit_and_all_other_descriptors_still_close(case, native, monkeypatch):
    held, closed = guard(case), []
    with pytest.raises(m.Refused) as caught:
        with held:
            held.read_all_once()
            target, original = held.by_role['second']['fd'], os.close
            def close(fd):
                original(fd); closed.append(fd)
                if fd == target: raise OSError('synthetic close failure after release')
            monkeypatch.setattr(m.os, 'close', close)
    assert m.finite(caught.value) == 'close'
    assert not held.objects and held.active is False
    assert len(closed) == len(set(closed)) and len(closed) > len(case.plan)


def test_deadline_expiration_at_normal_return_closes_without_receipt_acceptance(case, native):
    held = guard(case)
    with pytest.raises(m.Refused) as caught:
        with held:
            held.read_all_once(); held.deadline = time.monotonic() - 1
    assert m.finite(caught.value) == 'deadline'
    assert not held.objects and held.active is False and held.spent is True


def test_nonserializable_active_plan_mutation_has_only_finite_refusal(case, native):
    class Hostile:
        def __str__(self): raise AssertionError('raw plan value formatted')
    with pytest.raises(m.Refused) as caught:
        with guard(case) as held:
            held.plan['first']['sha256'] = Hostile()
            held.read_all_once()
    assert m.finite(caught.value) == 'plan'
