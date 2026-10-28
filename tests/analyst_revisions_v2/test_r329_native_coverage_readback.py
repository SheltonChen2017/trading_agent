"""Synthetic public-download readback; operational artifacts/contact denied."""
import copy
import ctypes
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time
from types import SimpleNamespace as NS

import pytest

from scripts import verify_arv2_r329_native_coverage_readback as m
from tests.analyst_revisions_v2 import test_r329_native_coverage_projection as fixtures

REAL_ROOT, REAL_SOURCE, REAL_STAGE = m.ROOT, m.SOURCE, m.stage.SOURCE


def deadline():
    return time.monotonic() + m.SECONDS - 1


def setxattr(path, name, value):
    """Fixture-only native writer, only synthetic in-root paths."""
    assert REAL_ROOT / '.pytest_cache' in path.parents
    native = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
    native.fsetxattr.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p,
        ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int)
    native.fsetxattr.restype = ctypes.c_int
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    try:
        name = name.encode('ascii') if type(name) is str else name
        result = native.fsetxattr(fd, name, value, len(value), 0, 0)
        if result != 0: raise OSError(ctypes.get_errno(), 'synthetic xattr fixture')
    finally:
        os.close(fd)


def paths():
    return {name: str(m.DOWNLOADS / name) for name in m.projection.CLOUD_NAMES}


def args():
    mapping = m.canonical(paths())
    return NS(expected_head='a' * 40, caller_sha256=m.sha(REAL_SOURCE.read_bytes()),
        profile_sha256=m.sha(m.canonical(m.profile_record(paths()))),
        download_map_json=mapping.decode('ascii'), download_map_sha256=m.sha(mapping))


def refused(code, call):
    with pytest.raises(m.Refused) as caught:
        call()
    assert m.finite(caught.value) == code


@pytest.fixture(scope='module')
def projected():
    return fixtures.generate(fixtures.inputs.__wrapped__())


def packet(projected):
    value = {'schema': m.SCHEMA, 'project_id': m.stage.PROJECT_ID,
        'download_map_sha256': args().download_map_sha256,
        'source_files': projected.to_record()['source_files'], 'projection_record': projected.to_record(),
        'projection_pin': m.pin(projected.record_bytes), 'profile_pin': m.pin(projected.profile_bytes),
        'selected_public_sources_sha256': m.sha(m.canonical({**m.selected_plan(),
            m.SOURCE.relative_to(m.ROOT).as_posix(): args().caller_sha256})),
        'source_endpoint_metadata_sha256': 'a' * 64, 'download_endpoint_metadata_sha256': 'b' * 64,
        'download_endpoint_security_sha256': 'c' * 64, 'file_count': 11, 'total_byte_count': 239149,
        'all_original_download_bytes_equal_expected': True, 'all_original_descriptors_postchecked': True,
        **m.FALSE_FLAGS}
    report = m.pin(m.canonical({'binding': m.binding(args()), 'result': value}))
    return m.canonical({'binding': m.binding(args()), 'outcome': {'result': value, 'report_pin': report}}) + b'\n'


def test_exact_public_dependencies_and_transport_scope_are_pinned():
    plan = m.selected_plan()
    assert len(plan) == 25
    assert all(m.sha((REAL_ROOT / name).read_bytes()) == expected for name, expected in plan.items())
    profile = m.profile_record(paths())
    assert profile['maximum_seconds'] == 60 and profile['maximum_download_bytes'] == 400 * 1024
    assert profile['download_map'] == paths()
    assert set(profile['download_xattr_names']) == {
        'com.apple.provenance', 'com.apple.quarantine', 'com.apple.metadata:kMDItemWhereFroms',
        'com.apple.lastuseddate#PS'}
    assert all(profile[key] is False for key in m.FALSE_FLAGS)
    assert m.STAGE_SHA256 == m.sha(REAL_STAGE.read_bytes())


@pytest.mark.parametrize('suffix', ('', ' 1', ' 999', ' (1)', ' (999)'))
def test_exact_map_allows_only_observed_safari_numeric_names(suffix):
    value = {name: str(m.DOWNLOADS / (name[:-3] + suffix + '.py')) for name in m.projection.CLOUD_NAMES}
    assert m.validate_map(value) == value


@pytest.mark.parametrize('change', ('missing', 'extra', 'different_role', 'outside', 'relative', 'traversal',
    'double_slash', 'symlink_component', 'suffix_zero', 'suffix_fourdigits', 'unicode', 'wrong_type'))
def test_exact_map_refuses_unobserved_or_ambiguous_paths(change):
    value, name = paths(), 'main.py'
    if change == 'missing': value.pop(name)
    elif change == 'extra': value['other.py'] = str(m.DOWNLOADS / 'other.py')
    elif change == 'different_role': value[name] = value[m.projection.CLOUD_NAMES[0]]
    elif change == 'outside': value[name] = '/Users/sheltonchen/Documents/main.py'
    elif change == 'relative': value[name] = 'main.py'
    elif change == 'traversal': value[name] = str(m.DOWNLOADS) + '/../Downloads/main.py'
    elif change == 'double_slash': value[name] = str(m.DOWNLOADS) + '//main.py'
    elif change == 'symlink_component': value[name] = str(m.DOWNLOADS / 'nested/main.py')
    elif change == 'suffix_zero': value[name] = str(m.DOWNLOADS / 'main 0.py')
    elif change == 'suffix_fourdigits': value[name] = str(m.DOWNLOADS / 'main 1000.py')
    elif change == 'unicode': value[name] = str(m.DOWNLOADS / 'maïn.py')
    elif change == 'wrong_type': value[name] = False
    refused('map', lambda: m.validate_map(value))


@pytest.mark.parametrize('change', ('hash', 'spaces', 'duplicate', 'trailing', 'oversize'))
def test_canonical_map_external_binding_rejects_change(change):
    value = args()
    if change == 'hash': value.download_map_sha256 = '0' * 64
    elif change == 'spaces': value.download_map_json = json.dumps(paths())
    elif change == 'duplicate': value.download_map_json = value.download_map_json[:-1] + ',"main.py":"bad"}'
    elif change == 'trailing': value.download_map_json += '\n'
    elif change == 'oversize': value.download_map_json = 'x' * (m.MAX_MAP_BYTES + 1)
    if change != 'hash': value.download_map_sha256 = m.sha(value.download_map_json.encode('ascii'))
    refused('arguments' if change == 'oversize' else 'map', lambda: m.path_map(value))


@pytest.mark.parametrize('actual_exit', (None, False, True, -1, 1, 2, 99))
def test_success_requires_actual_integer_exit_zero(projected, actual_exit):
    refused('output', lambda: m.validate_output(packet(projected), actual_exit, args()))


@pytest.mark.parametrize('change', ('source_hash', 'coherent_wrong_size', 'projection_pin', 'profile_pin',
    'report_pin', 'map_pin', 'metadata', 'postcheck', 'grant', 'extra', 'binding', 'trailing', 'double_lf'))
def test_closed_output_and_external_report_pin_refuse_changes(projected, change):
    value = json.loads(packet(projected))
    result = value['outcome']['result']
    if change == 'source_hash': result['source_files'][0]['sha256'] = '0' * 64
    elif change == 'coherent_wrong_size':
        result['source_files'][0]['byte_count'] += 1
        result['projection_record']['source_files'][0]['byte_count'] += 1
        result['total_byte_count'] += 1
        value['outcome']['report_pin'] = m.pin(m.canonical({'binding': value['binding'], 'result': result}))
    elif change == 'projection_pin': result['projection_pin']['sha256'] = '0' * 64
    elif change == 'profile_pin': result['profile_pin']['sha256'] = '0' * 64
    elif change == 'report_pin': value['outcome']['report_pin']['sha256'] = '0' * 64
    elif change == 'map_pin': result['download_map_sha256'] = '0' * 64
    elif change == 'metadata': result['download_endpoint_metadata_sha256'] = 'unknown'
    elif change == 'postcheck': result['all_original_descriptors_postchecked'] = False
    elif change == 'grant': result['cloud_saved_source_currently_authenticated'] = True
    elif change == 'extra': result['download_bytes'] = 'not permitted'
    elif change == 'binding': value['binding']['expected_head'] = 'b' * 40
    raw = m.canonical(value) + b'\n'
    if change == 'trailing': raw += b'EXTRA'
    elif change == 'double_lf': raw += b'\n'
    refused('output', lambda: m.validate_output(raw, 0, args()))


def test_valid_success_and_finite_consumed_failure_distinct(projected):
    assert m.validate_output(packet(projected), 0, args())['outcome']['result']['file_count'] == 11
    failed = m.canonical(m.failure(args(), m.Refused('download_pin'), consumed=True)) + b'\n'
    assert m.validate_output(failed, 2, args())['claim_consumed'] is True
    refused('output', lambda: m.validate_output(failed, 0, args()))


@pytest.fixture
def downloads(monkeypatch, tmp_path):
    directory = tmp_path / 'Downloads'
    directory.mkdir(mode=0o700)
    expected = {name: ('# synthetic public source ' + name + '\n').encode('ascii') for name in m.projection.CLOUD_NAMES}
    for name, raw in expected.items():
        (directory / name).write_bytes(raw)
        (directory / name).chmod(0o600)
    monkeypatch.setattr(m, 'DOWNLOADS', directory)
    return NS(directory=directory, expected=expected)


def test_original11_download_descriptors_held_without_census_or_execution(downloads, monkeypatch):
    monkeypatch.setattr(os, 'listdir', lambda *_: pytest.fail('Downloads directory census'))
    with m.Downloads(paths(), downloads.expected, deadline()) as held:
        assert len(held.rows) == len(held.descriptors) == 11
        receipt = held.receipt()
        assert receipt['file_count'] == 11
        assert receipt['total_byte_count'] == sum(map(len, downloads.expected.values()))
        fds = list(held.descriptors)
        assert all(os.fstat(fd).st_nlink == 1 for fd in fds)
    for fd in fds:
        with pytest.raises(OSError): os.fstat(fd)


@pytest.mark.parametrize('change', ('bytes', 'size', 'symlink', 'hardlink', 'mode', 'unknown_xattr'))
def test_original_download_policy_refuses_before_acceptance(downloads, change):
    leaf = downloads.directory / 'main.py'
    if change == 'bytes': leaf.write_bytes(b'x' * len(downloads.expected['main.py']))
    elif change == 'size': leaf.write_bytes(b'x')
    elif change == 'symlink':
        leaf.unlink()
        leaf.symlink_to(downloads.directory / m.projection.CLOUD_NAMES[0])
    elif change == 'hardlink': os.link(leaf, downloads.directory / 'unobserved.py')
    elif change == 'mode': leaf.chmod(0o666)
    elif change == 'unknown_xattr': setxattr(leaf, 'org.arv2.unknown', b'opaque')
    with pytest.raises((m.Refused, m.security.Refusal)):
        m.Downloads(paths(), downloads.expected, deadline())


@pytest.mark.parametrize('name', sorted(m.ALLOWED_DOWNLOAD_XATTRS - {b'com.apple.provenance'}))
def test_allowed_transport_values_are_opaque_bounded_and_hashed(downloads, name):
    leaf = downloads.directory / 'main.py'
    raw = b'\x00\xffopaque transport metadata\x01'
    setxattr(leaf, name, raw)
    with m.Downloads(paths(), downloads.expected, deadline()) as held:
        security = held.rows['main.py']['security']
        assert security['bounded_visible_xattrs'][name.decode('ascii')] == m.pin(raw)
        assert raw not in m.canonical(security)


@pytest.mark.parametrize('change', ('same_bytes_replacement', 'ctime', 'added_known_xattr', 'changed_known_xattr', 'added_unknown_xattr'))
def test_original_descriptor_postcheck_refuses_metadata_or_transport_drift(downloads, change):
    leaf = downloads.directory / 'main.py'
    if change == 'changed_known_xattr': setxattr(leaf, 'com.apple.quarantine', b'first')
    held = m.Downloads(paths(), downloads.expected, deadline())
    try:
        if change == 'same_bytes_replacement':
            leaf.unlink()
            leaf.write_bytes(downloads.expected['main.py'])
        elif change == 'ctime': leaf.chmod(0o644)
        elif change == 'added_known_xattr': setxattr(leaf, 'com.apple.quarantine', b'new')
        elif change == 'changed_known_xattr': setxattr(leaf, 'com.apple.quarantine', b'second')
        elif change == 'added_unknown_xattr': setxattr(leaf, 'org.arv2.unknown', b'new')
        refused('download_changed', held.verify)
    finally:
        held.close()


class FakeNative:
    def __init__(self, names, values=None, count=None):
        self.names, self.values, self.count = names, values or {}, count
    def flistxattr(self, fd, buffer, size, flags):
        raw = b'\0'.join(self.names) + (b'\0' if self.names else b'')
        ctypes.memmove(buffer, raw[:size], min(size, len(raw)))
        return len(raw) if self.count is None else self.count
    def fgetxattr(self, fd, name, buffer, size, position, flags):
        raw = self.values.get(name, b'opaque')
        ctypes.memmove(buffer, raw[:size], min(size, len(raw)))
        return len(raw)


@pytest.mark.parametrize('name', sorted(m.ALLOWED_DOWNLOAD_XATTRS))
def test_all_transport_value_classes_hash_opaque_native_bytes(monkeypatch, name):
    raw = b'\x00\xffopaque transport metadata\x01'
    monkeypatch.setattr(m.stage, 'metadata', lambda _: tuple(range(10)))
    monkeypatch.setattr(m.security, '_native', lambda: FakeNative([name], {name: raw}))
    monkeypatch.setattr(m.security, '_require_empty_acl', lambda *_: None)
    observed = m.download_security(999)
    assert observed['bounded_visible_xattrs'][name.decode('ascii')] == m.pin(raw)
    assert raw not in m.canonical(observed)


@pytest.mark.parametrize('native', (FakeNative([b'unknown']), FakeNative([b'com.apple.quarantine'] * 2),
    FakeNative([], count=-1), FakeNative([], count=1025)))
def test_native_xattr_inventory_fails_closed(native):
    refused('security', lambda: m._download_names(native, 999))


def test_aggregate_xattr_value_bound_refuses_oversize(monkeypatch):
    native = FakeNative([b'com.apple.quarantine'], {b'com.apple.quarantine': b'x' * (65536 + 1)})
    monkeypatch.setattr(m.stage, 'metadata', lambda _: tuple(range(10)))
    monkeypatch.setattr(m.security, '_native', lambda: native)
    monkeypatch.setattr(m.security, '_require_empty_acl', lambda *_: None)
    refused('security', lambda: m.download_security(999))


def test_empty_acl_is_required_for_download_not_assumed_for_ancestors(monkeypatch):
    monkeypatch.setattr(m.stage, 'metadata', lambda _: tuple(range(10)))
    monkeypatch.setattr(m.security, '_native', lambda: FakeNative([]))
    monkeypatch.setattr(m.security, '_require_empty_acl', lambda *_: (_ for _ in ()).throw(m.security.Refusal('acl')))
    with pytest.raises(m.security.Refusal): m.download_security(999)


@pytest.fixture
def local(monkeypatch, tmp_path, projected):
    root = tmp_path / 'repository'
    root.mkdir(mode=0o700)
    raw = {name: (REAL_ROOT / name).read_bytes() for name in m.selected_plan()}
    caller = REAL_SOURCE.relative_to(REAL_ROOT)
    raw[caller.as_posix()] = REAL_SOURCE.read_bytes()
    for relative, content in raw.items():
        target = root / relative
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        target.write_bytes(content)
        target.chmod(0o600)
    (root / 'artifacts').mkdir(mode=0o700)
    (root / 'artifacts/analyst_revisions_v2').mkdir(mode=0o700)
    control = root / 'artifacts/analyst_revisions_v2/newrule_available_history_native_coverage_source/R329-20261028-B'
    directory = root / 'Downloads'
    directory.mkdir(mode=0o700)
    for name, content in projected.source_pairs:
        (directory / name).write_bytes(content)
        (directory / name).chmod(0o600)
    monkeypatch.setattr(m, 'ROOT', root)
    monkeypatch.setattr(m.stage, 'ROOT', root)
    monkeypatch.setattr(m, 'SOURCE', root / caller)
    monkeypatch.setattr(m.stage, 'SOURCE', root / REAL_STAGE.relative_to(REAL_ROOT))
    monkeypatch.setattr(m, 'CONTROL', control)
    monkeypatch.setattr(m.stage, 'CONTROL', control)
    monkeypatch.setattr(m, 'DOWNLOADS', directory)
    fd = os.open(m.stage.SOURCE, os.O_RDONLY)
    try: monkeypatch.setattr(m, 'BOOTSTRAP_STAGE_METADATA', m.stage.metadata(fd))
    finally: os.close(fd)
    calls = []
    monkeypatch.setattr(m, 'preflight', lambda *_: calls.append('preflight'))
    return NS(root=root, control=control, directory=directory, calls=calls)


def test_real_public_projection_then_exclusive_claim_before_any_download(local, monkeypatch):
    original = m.Downloads
    def observed(*parameters):
        assert (local.control / 'claim.json').read_bytes() == m.canonical(m.binding(args()))
        assert not (local.control / 'report.json').exists()
        local.calls.append('downloads')
        return original(*parameters)
    monkeypatch.setattr(m, 'Downloads', observed)
    value = m.produce(args(), deadline())
    assert m.validate_output(m.canonical(value) + b'\n', 0, args()) == value
    assert local.calls == ['preflight', 'downloads', 'preflight']
    assert {p.name for p in local.control.iterdir()} == {'claim.json', 'report.json'}
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in local.control.iterdir())
    with pytest.raises(m.stage.Refused): m.produce(args(), deadline())
    assert local.calls.count('downloads') == 1


def test_source_pin_failure_precedes_claim_and_download(local, monkeypatch):
    path = local.root / 'scripts/arv2_r329_native_coverage_projection.py'
    path.write_bytes(path.read_bytes() + b'\n')
    monkeypatch.setattr(m, 'Downloads', lambda *_: pytest.fail('unexpected Downloads access'))
    with pytest.raises(m.stage.Refused): m.produce(args(), deadline())
    assert not local.control.exists()


def test_readback_refusal_retains_consumed_claim_and_no_success(local):
    leaf = local.directory / 'main.py'
    leaf.write_bytes(b'x' * leaf.stat().st_size)
    value = m.produce(args(), deadline())
    failure = m.validate_output(m.canonical(value) + b'\n', 2, args())
    assert failure['claim_consumed'] is True and failure['failure_code'] == 'download_pin'
    assert {p.name for p in local.control.iterdir()} == {'claim.json', 'failure.json'}


def test_late_postcheck_failure_never_accepts_existing_report(local, monkeypatch):
    original = m.Store.write
    def changed(store, name, raw, end):
        result = original(store, name, raw, end)
        if name == 'report.json': setxattr(local.directory / 'main.py', 'com.apple.quarantine', b'changed')
        return result
    monkeypatch.setattr(m.Store, 'write', changed)
    value = m.produce(args(), deadline())
    assert m.validate_output(m.canonical(value) + b'\n', 2, args())['claim_consumed'] is True
    assert (local.control / 'report.json').exists() and (local.control / 'failure.json').exists()
    refused('output', lambda: m.validate_output(m.canonical(value) + b'\n', 0, args()))


def test_bootstrap_stage_endpoint_change_refuses_before_claim(local, monkeypatch):
    values = list(m.BOOTSTRAP_STAGE_METADATA)
    values[8] += 1
    monkeypatch.setattr(m, 'BOOTSTRAP_STAGE_METADATA', tuple(values))
    refused('source_changed', lambda: m.produce(args(), deadline()))
    assert not local.control.exists()


@pytest.mark.parametrize('value', (True, float('nan'), float('inf'), -1, 0))
def test_deadline_is_finite_bounded_and_never_extended(value):
    refused('deadline', lambda: m.remaining(value))


def test_alarm_restores_previous_state():
    old = signal.getsignal(signal.SIGALRM)
    with m.alarm(deadline()):
        assert 0 < signal.getitimer(signal.ITIMER_REAL)[0] <= 60
    assert signal.getsignal(signal.SIGALRM) == old and signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)


def test_native_policy_has_exact_leaf_exceptions_and_qualified_directory_literal(downloads):
    policy = m.native_profile(paths())
    assert '(deny network*)' in policy and '(deny process-exec (literal "/usr/bin/security"))' in policy
    assert '(require-not (literal "' + str(downloads.directory) + '"))' in policy
    assert m.profile_record(paths())['directory_handle_census_prohibition_is_program_level_not_native'] is True
    for leaf in paths().values():
        assert '(require-not (literal "' + leaf + '"))' in policy
    assert str(downloads.directory / 'unlisted.py') not in policy
    assert 'Keychains' in policy and str(m.CONTROL) in policy


def test_cli_parser_errors_are_finite_without_argument_echo(capsys):
    assert m.main(['--unknown', 'SECRET_MUST_NOT_APPEAR']) == 2
    output = capsys.readouterr()
    assert output.out == '{"failure_code":"arguments"}\n' and output.err == ''


@pytest.fixture
def preflight(monkeypatch):
    value = args()
    observed = []
    def git(command, end):
        observed.append(command)
        return {('rev-parse', '--show-toplevel'): str(m.ROOT).encode('ascii'),
            ('branch', '--show-current'): m.stage.BRANCH.encode('ascii'),
            ('rev-parse', 'HEAD'): value.expected_head.encode('ascii'),
            ('status', '--porcelain'): b''}.get(tuple(command), REAL_SOURCE.read_bytes())
    monkeypatch.setattr(m.stage, '_environment', lambda: observed.append('environment'))
    monkeypatch.setattr(m.stage, '_git', git)
    return NS(args=value, observed=observed, git=git)


def test_clean_host_head_caller_and_map_profile_are_preflighted(preflight):
    m.preflight(preflight.args, deadline())
    assert preflight.observed[0] == 'environment'
    assert ['status', '--porcelain'] in preflight.observed
    assert preflight.observed[-1] == ['cat-file', 'blob', 'a' * 40 + ':' + REAL_SOURCE.relative_to(REAL_ROOT).as_posix()]


@pytest.mark.parametrize('change', ('root', 'branch', 'head', 'dirty', 'caller', 'profile'))
def test_preflight_refuses_source_or_git_drift(preflight, monkeypatch, change):
    original = preflight.git
    target = {'root': ('rev-parse', '--show-toplevel'), 'branch': ('branch', '--show-current'),
        'head': ('rev-parse', 'HEAD'), 'dirty': ('status', '--porcelain')}.get(change)
    def wrong(command, end):
        if tuple(command) == target or change == 'caller' and command[0] == 'cat-file': return b'wrong'
        return original(command, end)
    monkeypatch.setattr(m.stage, '_git', wrong)
    if change == 'profile': preflight.args.profile_sha256 = '0' * 64
    refused('source_pin' if change in ('caller', 'profile') else 'git_state',
        lambda: m.preflight(preflight.args, deadline()))


def test_failure_categorization_never_formats_opaque_exception():
    class Hostile(Exception):
        def __str__(self): raise AssertionError('opaque formatted')
        def __repr__(self): raise AssertionError('opaque represented')
    assert m.finite(Hostile('not for output')) == 'unknown'
    assert m.finite(m.Refused('unregistered')) == 'unknown'
    assert 'not for output' not in m.canonical(m.failure(args(), Hostile())).decode('ascii')


def test_download_bytes_are_never_imported_or_executed(downloads):
    expected = {name: b"raise RuntimeError('download must stay inert')\n" for name in m.projection.CLOUD_NAMES}
    for name, raw in expected.items(): (downloads.directory / name).write_bytes(raw)
    with m.Downloads(paths(), expected, deadline()) as held:
        assert held.receipt()['file_count'] == 11


def test_new_native_profile_refuses_stale_bytecode_reads():
    assert '(deny file-read-data (regex "[.]pyc$"))' in m.native_profile(paths())
    assert m.profile_record(paths())['native_bytecode_reads_denied'] is True
