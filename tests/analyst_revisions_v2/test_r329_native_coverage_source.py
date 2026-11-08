"""Synthetic source-only R329-A stage; production artifacts/contact denied."""
import copy
import json
import os
from pathlib import Path
import stat
import time
from types import SimpleNamespace as NS

import pytest

from scripts import prepare_arv2_r329_native_coverage_source as m
from tests.analyst_revisions_v2 import test_r329_native_coverage_projection as projection_fixtures

REAL_ROOT = m.ROOT
REAL_SOURCE = m.SOURCE


def deadline():
    return time.monotonic() + m.SECONDS - 1


def args():
    return NS(expected_head='a' * 40, caller_sha256=m.sha(REAL_SOURCE.read_bytes()),
        profile_sha256=m.sha(m.canonical(m.profile_record())))


def refused(code, call):
    with pytest.raises(m.Refused) as caught:
        call()
    assert m.finite(caught.value) == code


@pytest.fixture(scope='module')
def projected():
    return projection_fixtures.generate(projection_fixtures.inputs.__wrapped__())


def packet(projected):
    value = {'schema': m.SCHEMA, 'project_id': m.PROJECT_ID,
        'source_files': projected.to_record()['source_files'], 'projection_record': projected.to_record(),
        'projection_pin': m.pin(projected.record_bytes), 'profile_pin': m.pin(projected.profile_bytes),
        'selected_public_sources_sha256': m.sha(m.canonical({**m.public_plan(),
            m.SOURCE.relative_to(m.ROOT).as_posix(): args().caller_sha256})),
        'source_endpoint_metadata_sha256': 'a' * 64, 'output_endpoint_metadata_sha256': 'b' * 64,
        'source_and_output_original_FDs_postchecked': True, **m.FALSE_FLAGS}
    report = m.pin(m.canonical({'binding': m.binding(args()), 'result': value}))
    return m.canonical({'binding': m.binding(args()), 'outcome': {'result': value, 'report_pin': report}}) + b'\n'


def test_exact_public_plan_and_fixed_project_projection_profile_pins(projected):
    plan = m.public_plan()
    assert len(plan) == 24 and all(not name.startswith('artifacts/') for name in plan)
    assert all(m.sha((REAL_ROOT / name).read_bytes()) == expected for name, expected in plan.items())
    assert m.pin(projected.record_bytes) == m.EXPECTED_PROJECTION_PIN
    assert m.pin(projected.profile_bytes) == m.EXPECTED_PROFILE_PIN
    assert len(projected.source_pairs) == 11 and sum(len(raw) for _, raw in projected.source_pairs) == 239149
    assert projected.to_record()['project_id'] == m.PROJECT_ID == 38522505
    record = m.profile_record()
    assert all(record[name] is False for name in m.FALSE_FLAGS)
    assert 'not_whole_interpreter' in record['source_pin_scope']


def test_native_profile_blocks_all_contact_secrets_and_old_artifacts():
    policy = m.native_profile()
    assert '(deny network*)' in policy and '(deny process-exec (literal "/usr/bin/security"))' in policy
    assert '(deny file-read-data (regex "[.]pyc$"))' in policy
    assert '/Users/sheltonchen/Library/Keychains' in policy and '/Library/Keychains' in policy
    assert '(deny file-read* (require-all (subpath "' + str(m.ROOT / 'artifacts') + '")' in policy
    assert str(m.CONTROL) in policy and str(m.CONTROL.parent) in policy
    assert 'newrule_available_history_archive' not in policy and 'Downloads' not in policy
    assert 'allow network' not in policy and 'quantconnect.com' not in policy


@pytest.mark.parametrize('actual_exit', (None, False, True, -1, 1, 2, 77))
def test_success_is_inadmissible_without_observed_integer_actual_zero(projected, actual_exit):
    refused('output', lambda: m.validate_output(packet(projected), actual_exit, args()))


@pytest.mark.parametrize('change', ('source_pin', 'source_count', 'source_bytes', 'projection_pin', 'profile_pin',
    'report_pin', 'source_metadata', 'postcheck', 'grant', 'binding', 'extra', 'trailing', 'double_lf'))
def test_closed_public_report_refuses_corruption(projected, change):
    raw = packet(projected)
    value = json.loads(raw)
    result = value['outcome']['result']
    if change == 'source_pin': result['source_files'][0]['sha256'] = '0' * 64
    elif change == 'source_count': result['source_files'].pop()
    elif change == 'source_bytes': result['source_files'][0]['byte_count'] = True
    elif change == 'projection_pin': result['projection_pin']['sha256'] = '0' * 64
    elif change == 'profile_pin': result['profile_pin']['sha256'] = '0' * 64
    elif change == 'report_pin': value['outcome']['report_pin']['sha256'] = '0' * 64
    elif change == 'source_metadata': result['source_endpoint_metadata_sha256'] = 'unknown'
    elif change == 'postcheck': result['source_and_output_original_FDs_postchecked'] = False
    elif change == 'grant': result['QC_transfer_granted'] = True
    elif change == 'binding': value['binding']['expected_head'] = 'b' * 40
    elif change == 'extra': result['raw_exception'] = 'never'
    raw = m.canonical(value) + b'\n'
    if change == 'trailing': raw += b'EXTRA'
    elif change == 'double_lf': raw += b'\n'
    refused('output', lambda: m.validate_output(raw, 0, args()))


def test_matching_success_report_and_failure_are_distinct(projected):
    checked = m.validate_output(packet(projected), 0, args())
    assert checked['outcome']['result']['project_id'] == m.PROJECT_ID
    failed = m.canonical(m.failure(args(), m.Refused('source_pin'), consumed=True)) + b'\n'
    assert m.validate_output(failed, 2, args())['claim_consumed'] is True
    refused('output', lambda: m.validate_output(failed, 0, args()))


@pytest.fixture
def local(monkeypatch, tmp_path):
    root = tmp_path / 'repository'
    root.mkdir(mode=0o700)
    plan = m.public_plan()
    raw = {name: (REAL_ROOT / name).read_bytes() for name in plan}
    relative_caller = REAL_SOURCE.relative_to(REAL_ROOT)
    raw[relative_caller.as_posix()] = REAL_SOURCE.read_bytes()
    for relative, content in raw.items():
        target = root / relative
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        target.write_bytes(content)
        target.chmod(0o600)
    artifacts = root / 'artifacts'
    artifacts.mkdir(mode=0o700)
    (artifacts / 'analyst_revisions_v2').mkdir(mode=0o700)
    control = artifacts / 'analyst_revisions_v2/newrule_available_history_native_coverage_source/R329-20261028-A'
    monkeypatch.setattr(m, 'ROOT', root)
    monkeypatch.setattr(m, 'SOURCE', root / relative_caller)
    monkeypatch.setattr(m, 'CONTROL', control)
    monkeypatch.setattr(m, 'BOOTSTRAP_METADATA', {name: tuple(getattr((root / name).stat(), field) for field in m.FIELDS)
        for name in plan})
    calls = []
    def synthetic_preflight(*_):
        calls.append('preflight')
    monkeypatch.setattr(m, 'preflight', synthetic_preflight)
    return NS(root=root, control=control, raw=raw, calls=calls)


def test_actual_generator_stages_all11_exact_source_files_after_exclusive_claim(local, monkeypatch, projected):
    generate = m.projection.generate
    calls = []
    def observe(**kwargs):
        assert (local.control / 'claim.json').read_bytes() == m.canonical(m.binding(args()))
        calls.append('generate')
        return generate(**kwargs)
    monkeypatch.setattr(m.projection, 'generate', observe)
    value = m.produce(args(), deadline())
    raw = m.canonical(value) + b'\n'
    assert m.validate_output(raw, 0, args()) == value
    assert calls == ['generate'] and local.calls == ['preflight', 'preflight']
    expected = dict(projected.source_pairs)
    expected.update({'profile.json': projected.profile_bytes, 'projection.json': projected.record_bytes,
        'claim.json': m.canonical(m.binding(args())),
        'report.json': m.canonical({'binding': m.binding(args()), 'result': value['outcome']['result']})})
    assert set(path.name for path in local.control.iterdir()) == set(expected)
    for name, content in expected.items():
        path = local.control / name
        assert path.read_bytes() == content and stat.S_IMODE(path.stat().st_mode) == 0o600
    refused('claim_spent', lambda: m.produce(args(), deadline()))
    assert calls == ['generate']


def test_wrong_source_pin_refuses_before_any_control_allocation(local):
    path = local.root / next(iter(m.public_plan()))
    path.write_bytes(path.read_bytes() + b'\n')
    refused('source_pin', lambda: m.produce(args(), deadline()))
    assert not local.control.exists()


def test_failed_projection_retains_claim_and_failure_with_no_retry(local, monkeypatch):
    monkeypatch.setattr(m.projection, 'generate', lambda **_: (_ for _ in ()).throw(m.projection.Refused('source_pin')))
    value = m.produce(args(), deadline())
    raw = m.canonical(value) + b'\n'
    assert m.validate_output(raw, 2, args())['claim_consumed'] is True
    assert set(path.name for path in local.control.iterdir()) == {'claim.json', 'failure.json'}
    refused('claim_spent', lambda: m.produce(args(), deadline()))


@pytest.mark.parametrize('change', ('bytes', 'rename', 'ancestor', 'flags'))
def test_original_public_source_FDs_detect_drift(local, change):
    relative = next(iter(m.public_plan()))
    plan = {relative: m.public_plan()[relative]}
    with pytest.raises(m.Refused):
        with m.PublicSources(plan, deadline()) as held:
            target = local.root / relative
            if change == 'bytes': target.write_bytes(target.read_bytes() + b'\n')
            elif change == 'rename':
                replacement = target.with_name('replacement.py')
                replacement.write_bytes(target.read_bytes())
                replacement.chmod(0o600)
                os.replace(replacement, target)
            elif change == 'ancestor':
                original = target.parent.stat()
                os.utime(target.parent, ns=(original.st_atime_ns, original.st_mtime_ns + 1))
            else: os.chflags(target, stat.UF_HIDDEN)
            held.verify()


@pytest.mark.parametrize('change', ('contents', 'unknown_leaf', 'replacement'))
def test_original_output_FDs_and_inventory_detect_mutation(local, change):
    with pytest.raises(m.Refused):
        with m.Store() as store:
            store.write('claim.json', b'{}', deadline())
            path = local.control / 'claim.json'
            if change == 'contents': path.write_bytes(b'[]')
            elif change == 'unknown_leaf': (local.control / 'unexpected').write_bytes(b'x')
            else:
                alternate = local.control / 'alternate'
                alternate.write_bytes(b'{}')
                alternate.chmod(0o600)
                os.replace(alternate, path)
            store.verify()
    assert (local.control / 'claim.json').exists()


@pytest.mark.parametrize('link_delta', (-1, 0, 2))
def test_own_file_refresh_refuses_unexpected_APFS_link_deltas(monkeypatch, link_delta):
    parent_old = (1, 2, stat.S_IFDIR | 0o700, os.getuid(), 20, 4, 64, 1000, 1000, 0)
    parent_new = (*parent_old[:5], parent_old[5] + link_delta, 96, 2000, 2000, 0)
    child_info = (1, 3, stat.S_IFREG | 0o600, os.getuid(), 20, 1, 0, 1000, 1000, 0)
    guard = object.__new__(m.DirectoryGuard)
    guard._policy = lambda _: None
    monkeypatch.setattr(m, 'metadata', lambda fd: parent_new if fd == 90 else child_info)
    monkeypatch.setattr(m, 'named', lambda *_: child_info)
    refused('output_changed', lambda: guard.own_created({'fd': 90, 'metadata': parent_old},
        {'fd': 91, 'parent': 90, 'name': 'own', 'metadata': child_info}, directory=False))


def test_late_guard_failure_cannot_make_retained_success_report_admissible(local, monkeypatch, capfd):
    original = m.Store.__exit__
    def late(self, kind, *args):
        original(self, kind, *args)
        raise m.Refused('output_changed')
    monkeypatch.setattr(m.Store, '__exit__', late)
    supplied = args()
    code = m.main(['--expected-head', supplied.expected_head, '--caller-sha256', supplied.caller_sha256,
        '--profile-sha256', supplied.profile_sha256])
    output = capfd.readouterr().out.encode('ascii')
    assert code == 2 and (local.control / 'report.json').is_file()
    assert m.validate_output(output, code, supplied)['allocation_unknown'] is True
    refused('output', lambda: m.validate_output(output, 0, supplied))


def test_finite_failure_never_formats_arbitrary_objects():
    class Secret:
        def __str__(self): pytest.fail('secret formatting')
        def __repr__(self): pytest.fail('secret formatting')
        def __eq__(self, _): pytest.fail('secret comparison')
    assert m.finite(m.Refused(Secret())) == 'unknown'
    assert m.finite(RuntimeError(Secret())) == 'unknown'


def test_deadline_and_alarm_enforce_bound_and_restore_signal():
    refused('deadline', lambda: m.remaining(float('nan')))
    refused('deadline', lambda: m.remaining(time.monotonic() - 1))
    refused('deadline', lambda: m.remaining(time.monotonic() + m.SECONDS + 5))
    handler = m.signal.getsignal(m.signal.SIGALRM)
    with m.alarm(deadline()):
        assert 0 < m.signal.getitimer(m.signal.ITIMER_REAL)[0] <= m.SECONDS
    assert m.signal.getitimer(m.signal.ITIMER_REAL) == (0.0, 0.0)
    assert m.signal.getsignal(m.signal.SIGALRM) is handler


@pytest.mark.parametrize('change', ('none', 'root', 'branch', 'head', 'dirty', 'caller', 'profile'))
def test_preflight_requires_exact_clean_git_caller_and_profile_before_claim(monkeypatch, change):
    supplied = args()
    answers = {
        ('rev-parse', '--show-toplevel'): str(m.ROOT).encode(),
        ('branch', '--show-current'): m.BRANCH.encode(),
        ('rev-parse', 'HEAD'): supplied.expected_head.encode(),
        ('status', '--porcelain'): b'',
    }
    if change == 'root': answers[('rev-parse', '--show-toplevel')] = b'/different'
    elif change == 'branch': answers[('branch', '--show-current')] = b'other-lane'
    elif change == 'head': answers[('rev-parse', 'HEAD')] = b'b' * 40
    elif change == 'dirty': answers[('status', '--porcelain')] = b' M tracked.py'
    elif change == 'profile': supplied.profile_sha256 = '0' * 64
    monkeypatch.setattr(m, '_environment', lambda: None)
    def git(arguments, _deadline):
        if arguments[:2] == ['cat-file', 'blob']:
            return REAL_SOURCE.read_bytes() + (b'\n' if change == 'caller' else b'')
        return answers[tuple(arguments)]
    monkeypatch.setattr(m, '_git', git)
    monkeypatch.setattr(m, 'Store', lambda: pytest.fail('preflight allocated control'))
    if change == 'none':
        m.preflight(supplied, deadline())
    else:
        refused('git_state' if change in ('root', 'branch', 'head', 'dirty') else 'source_pin',
            lambda: m.preflight(supplied, deadline()))


@pytest.mark.parametrize('change', ('none', 'credential', 'pythonpath', 'external_tmp', 'bytecode', 'plugins'))
def test_environment_is_credential_free_and_support_paths_are_inroot(monkeypatch, change):
    clean = {'PATH': '/usr/bin:/bin', 'TMPDIR': str(REAL_ROOT / '.pytest_cache/r329-native-stage/tmp'),
        'PYTHONPYCACHEPREFIX': str(REAL_ROOT / '.pytest_cache/r329-native-stage/pycache'),
        'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'}
    if change == 'credential': clean['QC_API_TOKEN'] = 'synthetic-never-output'
    elif change == 'pythonpath': clean['PYTHONPATH'] = '/unexpected'
    elif change == 'external_tmp': clean['TMPDIR'] = '/tmp'
    elif change == 'bytecode': clean['PYTHONDONTWRITEBYTECODE'] = '0'
    elif change == 'plugins': clean['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '0'
    monkeypatch.setattr(m, 'os', NS(environ=clean))
    if change == 'none': m._environment()
    else: refused('environment', m._environment)


def test_bootstrap_checks_all_byte_pins_before_any_import_resolution(monkeypatch):
    name = next(iter(m.BOOTSTRAP_PINS))
    with monkeypatch.context() as patch:
        patch.setattr(m, 'BOOTSTRAP_PINS', {name: '0' * 64})
        patch.setattr(m.PathFinder, 'find_spec', lambda *_: pytest.fail('import resolution before pin refusal'))
        with pytest.raises(RuntimeError, match='^public_bootstrap$'):
            m._bootstrap()


def test_bootstrap_rejects_preloaded_flat_module_alias(monkeypatch):
    with monkeypatch.context() as patch:
        patch.setitem(m.sys.modules, 'newrule_native_price_book_runtime', NS(__file__='/unexpected'))
        with pytest.raises(RuntimeError, match='^public_bootstrap$'):
            m._bootstrap()


def test_same_bytes_rewritten_since_bootstrap_refuse_before_claim(local):
    target = local.root / next(iter(m.public_plan()))
    before = target.stat()
    target.write_bytes(target.read_bytes())
    assert target.stat().st_ctime_ns != before.st_ctime_ns
    refused('source_changed', lambda: m.produce(args(), deadline()))
    assert not local.control.exists()


def test_invalid_CLI_does_not_echo_unknown_argument_or_raw_parser_error(capfd):
    assert m.main(['--unexpected', 'synthetic-secret-never-output']) == 2
    captured = capfd.readouterr()
    assert captured.out == '{"failure_code":"arguments"}\n' and captured.err == ''
