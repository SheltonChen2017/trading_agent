"""Synthetic NEW R338-E orchestration; spent A/C/D remain unchanged."""
import ast
import copy
from contextlib import ExitStack
import io
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace as NS

import pytest
from scripts import prepare_arv2_r338_quarantine_v4 as m


def args(): return NS(expected_head='a' * 40, caller_sha256='b' * 64, profile_sha256='c' * 64)


def refuse(code, call):
    with pytest.raises(m.Refused) as error: call()
    assert m.finite(error.value) == code


class Security:
    @staticmethod
    def snapshot(fd): return {'acl_empty': True, 'xattrs': {}}


PRIVATE = {'synthetic_private_rows': ['PRIVATE-LICENSED-LIKE-CONTENT']}
INPUT = {'schema': 'synthetic_full_input', 'full_bindings': 6151, 'full_axis': 3466}
PINS = {name: {'byte_count': index + 10, 'sha256': str(index + 1) * 64}
    for index, name in enumerate(('quarantine_catalog_pin', 'vendor_archive_pin', 'vendor_catalog_pin', 'vendor_manifest_pin'))}
BUNDLE = b'PRIVATE-PREPARED-SOURCE-BUNDLE'


def receipt():
    return {'schema': 'synthetic_genuine_input', 'input_binding': copy.deepcopy(INPUT),
        'input_binding_sha256': m.sha(m.canonical(INPUT))}


def coverage():
    return {'schema': 'synthetic_coverage', 'input_binding_pin': m.pin(m.canonical(INPUT)),
        'private_evidence_pin': m.pin(m.canonical(PRIVATE)),
        'conservative_required_price_coverage_complete': False, **copy.deepcopy(PINS)}


def materialization():
    return {'schema': 'synthetic_materialization', 'input_binding_sha256': m.sha(m.canonical(INPUT)),
        'proposed_runtime_project_id': 38522505, **copy.deepcopy(PINS)}


def _pin(value):
    m.require(type(value) is dict and set(value) == {'byte_count', 'sha256'}
        and type(value['byte_count']) is int and value['byte_count'] > 0
        and type(value['sha256']) is str and len(value['sha256']) == 64, 'output')


class Input:
    @staticmethod
    def validate_receipt(value):
        m.require(type(value) is dict and set(value) == set(receipt())
            and value['schema'] == receipt()['schema'] and type(value['input_binding']) is dict
            and value['input_binding_sha256'] == m.sha(m.canonical(value['input_binding'])), 'output')
        return value


class Coverage:
    @staticmethod
    def validate_summary(value):
        m.require(type(value) is dict and set(value) == set(coverage())
            and value['schema'] == coverage()['schema']
            and type(value['conservative_required_price_coverage_complete']) is bool, 'output')
        for key in (*PINS, 'input_binding_pin', 'private_evidence_pin'): _pin(value[key])
        return value


class Materialization:
    @staticmethod
    def validate_summary(value):
        m.require(type(value) is dict and set(value) == set(materialization())
            and value['schema'] == materialization()['schema'] and value['proposed_runtime_project_id'] == 38522505
            and type(value['input_binding_sha256']) is str and len(value['input_binding_sha256']) == 64, 'output')
        for key in PINS: _pin(value[key])
        return value


@pytest.fixture(autouse=True)
def modules(monkeypatch):
    monkeypatch.setattr(m, 'MODULES', {'input': Input, 'coverage': Coverage, 'materialization': Materialization})
    monkeypatch.setattr(m, 'DEADLINE_FIRED', False)
    monkeypatch.setattr(m, 'CHILD_OBSERVATION', None)
    monkeypatch.setattr(m, 'ACTIVE_BINDING', None)
    monkeypatch.setattr(m, 'CLAIM_STATE', 'unallocated')
    monkeypatch.setattr(m, 'FAILURE_STAGE', 'preflight')
    monkeypatch.setattr(m, 'FAILURE_CASE', None)


def result():
    return {'schema': m.SCHEMA, 'diagnostic_complete': True, 'coverage': coverage(),
        'materialization': materialization(), 'input_receipt': receipt(),
        'source_bundle_pin': m.pin(BUNDLE), 'coverage_private_pin': m.pin(m.canonical(PRIVATE)),
        'both_DATA_authenticated': True, 'genuine_guard_normal_return': True, 'source_guard_normal_return': True,
        'worker_marker_pin': m.pin(m.canonical({'binding': m.binding(args()), 'phase': 'input_coverage_and_source_binding'})),
        'data_receipt_sha256': 'a' * 64, **m.FALSE_FLAGS}


def worker_packet():
    value = {'binding': m.binding(args()), 'result': result()}
    return {**value, 'report_pin': m.pin(m.canonical(value))}


def parent_packet():
    value = worker_packet()
    return {'binding': m.binding(args()), 'output_authenticated': True,
        'observation': {'actual_child_exit': 0, 'child_stdout_pin': m.pin(m.canonical(value) + b'\n'),
            'child_stderr_byte_count': 0, 'child_stderr_sha256': m.sha(b''), 'failure_code': None}, 'outcome': value}


def fixture_root(tmp_path, monkeypatch):
    root = tmp_path / 'root'; root.mkdir(mode=0o755); root.chmod(0o755)
    artifacts = root / 'artifacts'; artifacts.mkdir(mode=0o700)
    lane = artifacts / 'analyst_revisions_v2'; lane.mkdir(mode=0o700)
    monkeypatch.setattr(m, 'ROOT', root); monkeypatch.setattr(m, 'CONTROL', lane / 'quarantine/R338-E')


@pytest.fixture
def worker_setup(tmp_path, monkeypatch):
    fixture_root(tmp_path, monkeypatch)
    order = []; raw = {'quarantine': b'PRIVATE-QUARANTINE-DATA', 'archive': b'PRIVATE-ARCHIVE-DATA'}
    monkeypatch.setattr(m, 'DATA_PLAN', {name: {'relative_path': 'artifacts/analyst_revisions_v2/synthetic/' + name,
        **m.pin(value)} for name, value in raw.items()})
    state = NS(order=order, guard_fail=False, input_fail=False, source_fail=False,
        coverage_fail=False, materialization_fail=False, late_fail=False, random_calls=[], same_nonce=False)
    def random_bytes(count):
        assert count == 32
        assert (m.CONTROL / 'claim.json').exists() and (m.CONTROL / 'worker-started.json').exists()
        assert len(state.random_calls) < 2
        # Avoid accidental equality with the fixture's repeated-digit public
        # SHA placeholders; the values represent two separate random draws.
        value = bytes(range(32)) if not state.random_calls or state.same_nonce else bytes(range(32, 64))
        state.random_calls.append(value.hex()); order.append('nonce_' + str(len(state.random_calls)))
        return value
    monkeypatch.setattr(m.os, 'urandom', random_bytes)
    class SourceClose:
        def __enter__(self): return self
        def __exit__(self, *a):
            order.append('source_normal_return' if not state.source_fail else 'source_refusal')
            if state.source_fail: raise m.Refused('source_changed')
    class Guard:
        def __init__(self, plan, *, deadline): assert plan == m.DATA_PLAN
        def __enter__(self):
            assert (m.CONTROL / 'claim.json').exists() and (m.CONTROL / 'worker-started.json').exists()
            order.append('data_enter'); return self
        def read_all_once(self): order.append('data_read'); return raw
        def verify(self): order.append('data_verify')
        def receipt(self): return {'synthetic_data_receipt': True}
        def __exit__(self, *a):
            order.append('data_normal_return' if not state.guard_fail else 'data_refusal')
            if state.guard_fail: raise m.Refused('changed')
    class Genuine:
        def __init__(self, *, deadline):
            self.axis = ('synthetic-axis',); self.bindings = ('synthetic-bindings',)
            self.memberships = ('synthetic-memberships',); self.manifest = {'synthetic': 'manifest'}
            self.input_binding = copy.deepcopy(INPUT)
        def __enter__(self):
            assert (m.CONTROL / 'worker-started.json').exists(); order.append('input_enter'); return self
        def verify(self, *, deadline): order.append('input_verify')
        def receipt(self): return receipt()
        def __exit__(self, *a):
            order.append('input_normal_return' if not state.input_fail else 'input_refusal')
            if state.input_fail: raise m.Refused('input')
    class Observe(Coverage):
        @staticmethod
        def prepare(archive, catalog, **kwargs):
            assert archive == raw['archive'] and catalog == raw['quarantine']
            assert kwargs['input_binding'] == INPUT and kwargs['membership_rows'] == ('synthetic-memberships',)
            order.append('coverage')
            assert kwargs['transport_nonce'] == state.random_calls[0]
            if state.coverage_fail: raise m.Refused('input')
            private = {**copy.deepcopy(PRIVATE), 'transport_nonce': kwargs['transport_nonce']}
            observed = coverage(); observed['private_evidence_pin'] = m.pin(m.canonical(private))
            return observed, private
    class Materialize(Materialization):
        @staticmethod
        def prepare(sources, **kwargs):
            assert sources == (('PUBLIC.py', b'public'),) and kwargs['quarantine_catalog_raw'] == raw['quarantine']
            assert kwargs['archive_raw'] == raw['archive'] and kwargs['input_binding'] == INPUT
            order.append('materialization')
            if state.materialization_fail: raise m.Refused('input')
            return materialization(), {'synthetic_private': b'PRIVATE-SOURCE-ROWS'}
        @staticmethod
        def pack_outputs(outputs, *, transport_nonce):
            assert outputs == {'synthetic_private': b'PRIVATE-SOURCE-ROWS'}
            assert transport_nonce == state.random_calls[1]
            return BUNDLE + transport_nonce.encode('ascii')
        @staticmethod
        def validate_bundle(bundle, **kwargs):
            assert bundle == BUNDLE + state.random_calls[1].encode('ascii')
            assert kwargs['expected_pin'] == m.pin(bundle)
            assert kwargs['summary'] == materialization(); order.append('bundle_validate')
    def bootstrap(role, stack, deadline):
        stack.enter_context(SourceClose())
        return {'security': Security, 'guard': NS(FixedDataGuard=Guard),
            'input': NS(GenuineInput=Genuine), 'coverage': Observe, 'materialization': Materialize,
            'source_pairs': (('PUBLIC.py', b'public'),)}
    monkeypatch.setattr(m, 'bootstrap', bootstrap); monkeypatch.setattr(m, 'preflight', lambda *a: None)
    original = m.Store.write
    def write(store, name, value):
        if name in ('prepared-sources-private.bin', 'coverage-private.json', 'report.json'):
            assert all(item in order for item in ('input_normal_return', 'data_normal_return', 'source_normal_return'))
            assert order.index('input_normal_return') < order.index('data_normal_return') < order.index('source_normal_return')
        order.append('write_' + name)
        if state.late_fail and name == 'report.json': raise m.Refused('output')
        return original(store, name, value)
    monkeypatch.setattr(m.Store, 'write', write)
    def run():
        selected = args(); reader, writer = os.pipe()
        try: os.write(writer, m.canonical(m.binding(selected)))
        finally: os.close(writer)
        selected.intent_fd = reader; return m.worker(selected, time.monotonic() + 899)
    state.run = run; return state


def test_exclusive_claim_input_and_two_data_then_all_normal_returns_before_publication(worker_setup):
    packet = worker_setup.run(); value = packet['result']
    assert value['diagnostic_complete'] is True
    assert value['coverage']['conservative_required_price_coverage_complete'] is False
    order = worker_setup.order
    assert order.index('write_claim.json') < order.index('write_worker-started.json') < order.index('data_read')
    assert len(worker_setup.random_calls) == 2 and worker_setup.random_calls[0] != worker_setup.random_calls[1]
    assert order.index('write_worker-started.json') < order.index('nonce_1') < order.index('nonce_2') < order.index('coverage')
    assert order.index('input_enter') < order.index('coverage') < order.index('materialization') < order.index('bundle_validate')
    assert order.index('source_normal_return') < order.index('write_prepared-sources-private.bin') < order.index('write_report.json')
    raw = m.canonical(packet) + b'\n'; m.validate_envelope(raw, 0, args())
    assert b'PRIVATE-' not in raw and b'synthetic_private_rows' not in raw
    assert all(nonce.encode('ascii') not in raw for nonce in worker_setup.random_calls)
    refuse('claim_spent', worker_setup.run)


@pytest.mark.parametrize('failure', ['guard', 'input', 'source', 'coverage', 'materialization', 'late'])
def test_guard_and_late_failure_keep_claim_and_never_publish_success(worker_setup, monkeypatch, failure):
    setattr(worker_setup, failure + '_fail', True)
    monkeypatch.setattr(m, 'ACTIVE_BINDING', m.binding(args()))
    with pytest.raises(m.Refused) as error: worker_setup.run()
    packet = m.failure_packet(m.finite(error.value)); m.validate_failure(packet, args())
    assert packet['attempt_reusable'] is False and b'PRIVATE-' not in m.canonical(packet)
    assert (m.CONTROL / 'claim.json').exists() and (m.CONTROL / 'worker-started.json').exists()
    assert not (m.CONTROL / 'report.json').exists()
    assert (m.CONTROL / 'coverage-private.json').exists() is (failure == 'late')


def test_duplicate_private_payload_nonce_draws_refuse_without_data_or_retry(worker_setup):
    worker_setup.same_nonce = True
    refuse('input', worker_setup.run)
    assert len(worker_setup.random_calls) == 2
    assert 'data_read' not in worker_setup.order and 'coverage' not in worker_setup.order
    assert (m.CONTROL / 'claim.json').exists() and (m.CONTROL / 'worker-started.json').exists()
    assert not (m.CONTROL / 'report.json').exists()


def test_incomplete_coverage_is_an_accepted_observation_never_strategy_readiness():
    checked = m.validate_parent_output(m.canonical(parent_packet()) + b'\n', 0, args())
    assert checked['accepted'] is True
    assert checked['result']['coverage']['conservative_required_price_coverage_complete'] is False
    assert all(checked['result'][key] is False for key in m.FALSE_FLAGS)


@pytest.mark.parametrize('field,value', [('diagnostic_complete', 1), ('both_DATA_authenticated', 1),
    ('genuine_guard_normal_return', 1), ('source_guard_normal_return', 1), ('data_receipt_sha256', 'bad'),
    ('source_bundle_pin', {'byte_count': True, 'sha256': 'a' * 64}), ('current_cloud_project_verified', True),
    ('worker_marker_pin', {'byte_count': 0, 'sha256': 'a' * 64}), ('extra', False)])
def test_closed_result_exact_types_markers_and_false_flags(field, value):
    selected = result(); selected[field] = value
    refuse('output', lambda: m.validate_result(selected, args()))


@pytest.mark.parametrize('which', ['receipt_input', 'material_input', 'coverage_input', *PINS, 'private_bytes'])
def test_cross_component_input_archive_catalog_and_actual_private_pin_joins(which):
    value = result()
    if which == 'receipt_input':
        value['input_receipt']['input_binding']['full_bindings'] = 6000
        value['input_receipt']['input_binding_sha256'] = m.sha(m.canonical(value['input_receipt']['input_binding']))
        Input.validate_receipt(value['input_receipt'])
    elif which == 'material_input': value['materialization']['input_binding_sha256'] = 'f' * 64
    elif which == 'coverage_input': value['coverage']['input_binding_pin']['sha256'] = 'f' * 64
    elif which == 'private_bytes': value['coverage_private_pin']['sha256'] = 'f' * 64
    else: value['materialization'][which]['sha256'] = 'f' * 64
    Coverage.validate_summary(value['coverage']); Materialization.validate_summary(value['materialization'])
    refuse('output', lambda: m.validate_result(value, args()))


@pytest.mark.parametrize('which', ['actual2', 'actualbool', 'actualnone', 'workerexit', 'stderrbool', 'stderr',
    'stderrhash', 'stdoutpin', 'reportpin', 'markerpin', 'bind', 'flag', 'trailing', 'doubleLF'])
def test_actual_exit_stdout_report_binding_and_strict_framing(which):
    packet = parent_packet(); actual = 0
    if which == 'actual2': actual = 2
    elif which == 'actualbool': actual = True
    elif which == 'actualnone': actual = None
    elif which == 'workerexit': packet['observation']['actual_child_exit'] = 2
    elif which == 'stderrbool': packet['observation']['child_stderr_byte_count'] = False
    elif which == 'stderr': packet['observation']['child_stderr_byte_count'] = 1
    elif which == 'stderrhash': packet['observation']['child_stderr_sha256'] = 'f' * 64
    elif which == 'stdoutpin': packet['observation']['child_stdout_pin']['sha256'] = 'f' * 64
    elif which == 'reportpin': packet['outcome']['report_pin']['sha256'] = 'f' * 64
    elif which == 'markerpin': packet['outcome']['result']['worker_marker_pin']['sha256'] = 'f' * 64
    elif which == 'bind': packet['binding']['expected_head'] = 'f' * 40
    elif which == 'flag': packet['outcome']['result']['source_admission_granted'] = True
    raw = m.canonical(packet) + b'\n' + (b'noise' if which == 'trailing' else b'\n' if which == 'doubleLF' else b'')
    refuse('output', lambda: m.validate_parent_output(raw, actual, args()))


def test_rehashing_report_never_replaces_original_worker_stdout_binding():
    packet = parent_packet(); value = packet['outcome']
    value['result']['source_bundle_pin']['sha256'] = 'f' * 64
    value['report_pin'] = m.pin(m.canonical({'binding': value['binding'], 'result': value['result']}))
    m.validate_envelope(m.canonical(value) + b'\n', 0, args())
    refuse('output', lambda: m.validate_parent_output(m.canonical(packet) + b'\n', 0, args()))


@pytest.mark.parametrize('actual', [0, 2, True, None])
def test_worker_success_envelope_requires_exact_observed_zero_exit(actual):
    raw = m.canonical(worker_packet()) + b'\n'
    if type(actual) is int and actual == 0: m.validate_envelope(raw, actual, args())
    else: refuse('child_failure', lambda: m.validate_envelope(raw, actual, args()))


@pytest.mark.parametrize('code', ['input', 'changed', 'source_pin', 'deadline', 'output'])
def test_child2_finite_failure_is_authenticated_only_as_failure(code, monkeypatch):
    monkeypatch.setattr(m, 'ACTIVE_BINDING', m.binding(args()))
    failed = m.failure_packet(code)
    packet = {'binding': m.binding(args()), 'output_authenticated': True, 'failure': failed,
        'observation': {'actual_child_exit': 2, 'child_stdout_pin': m.pin(m.canonical(failed) + b'\n'),
            'child_stderr_byte_count': 0, 'child_stderr_sha256': m.sha(b''), 'failure_code': None}}
    checked = m.validate_parent_output(m.canonical(packet) + b'\n', 2, args())
    assert checked['accepted'] is False and checked['failure']['failure_code'] == code
    refuse('output', lambda: m.validate_parent_output(m.canonical(packet) + b'\n', 0, args()))


@pytest.mark.parametrize('mode', ['success', 'failure', 'stderr', 'timeout', 'bound'])
def test_real_tiny_child_capture_noise_deadline_and_own_kill_reap(monkeypatch, mode):
    actual = subprocess.Popen; children = []
    monkeypatch.setattr(m, 'safe_env', lambda: {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin',
        'LC_ALL': 'C', 'PYTHONDONTWRITEBYTECODE': '1'})
    def tracked(*a, **k): child = actual(*a, **k); children.append(child); return child
    monkeypatch.setattr(m.subprocess, 'Popen', tracked)
    code = 'import os,time\n'
    if mode == 'timeout': code += 'time.sleep(5)\n'
    if mode == 'stderr': code += 'os.write(2,b"synthetic error")\n'
    if mode == 'bound': monkeypatch.setattr(m, 'MAX_OUTPUT', 32); code += 'os.write(1,b"x"*33)\n'
    else: code += 'os.write(1,b"finite synthetic output\\n")\n'
    code += 'raise SystemExit(' + ('2' if mode == 'failure' else '0') + ')'
    exitcode, raw, count, digest, problem = m.run_child([sys.executable, '-I', '-B', '-c', code], (),
        time.monotonic() + (.2 if mode == 'timeout' else 10))
    assert children[0].poll() is not None and children[0].stdout.closed and children[0].stderr.closed
    if mode == 'timeout': assert exitcode < 0 and problem == 'deadline'
    elif mode == 'bound': assert problem == 'bound' and raw == b''
    else: assert exitcode == (2 if mode == 'failure' else 0) and problem is None and count == (15 if mode == 'stderr' else 0)


@pytest.mark.parametrize('mode', ['launch', 'worker', 'validate'])
def test_each_cli_role_arms_actual_alarm_before_preflight_or_dispatch(monkeypatch, mode):
    selected = args(); argv = [str(m.SOURCE), mode, '--expected-head', selected.expected_head,
        '--caller-sha256', selected.caller_sha256, '--profile-sha256', selected.profile_sha256]
    if mode == 'worker': argv += ['--intent-fd', '3', '--outer-deadline', repr(time.monotonic() + 839)]
    if mode == 'validate': argv += ['--actual-parent-exit', '2']
    order = []; monkeypatch.setattr(m.sys, 'argv', argv)
    monkeypatch.setattr(m, 'ENTRY_DEADLINE', time.monotonic() + 899)
    monkeypatch.setattr(m.signal, 'signal', lambda *a: None)
    monkeypatch.setattr(m.signal, 'setitimer', lambda *a: order.append(('alarm', a[1])))
    monkeypatch.setattr(m, 'parent', lambda *a: {'mode': 'launch'})
    monkeypatch.setattr(m, 'worker', lambda *a: {'mode': 'worker'})
    monkeypatch.setattr(m, 'preflight', lambda *a: order.append(('preflight', None)))
    monkeypatch.setattr(m, 'bootstrap', lambda *a: (order.append(('bootstrap', None)) or {}))
    monkeypatch.setattr(m.sys, 'stdin', NS(buffer=io.BytesIO(b'synthetic')))
    monkeypatch.setattr(m, 'validate_parent_output', lambda *a: {'mode': 'validate'})
    assert m.main() == {'mode': mode}
    assert order[0][0] == 'alarm' and 0 < order[0][1] <= (30 if mode == 'validate' else 840 if mode == 'worker' else 900)
    if mode == 'validate': assert [item[0] for item in order] == ['alarm', 'preflight', 'bootstrap']


def test_native_policy_allows_exact_genuine_inputs_and_two_data_not_old_controls():
    native = m.native_profile()
    assert '(deny network*)' in native and '/Volumes' in native
    assert '/Library/Keychains' in native and '/usr/bin/security' in native
    assert '(deny file-read-data (regex "[.]pyc$"))' in native
    assert set(m.DATA_PLAN) == {'quarantine', 'archive'}
    for item in m.DATA_PLAN.values(): assert str(m.ROOT / item['relative_path']) in native
    assert '(require-not (subpath "' + str(m.INPUT_PACKAGE) + '"))' in native
    assert '(require-not (literal "' + str(m.INPUT_LINEAGE) + '"))' in native
    assert 'R337-20261103-A/report.json' not in native and 'R327-20261028-K/report.json' not in native


@pytest.mark.parametrize('change', ['profile', 'head', 'source', 'platform', 'isolated', 'dirty'])
def test_preflight_exact_clean_host_head_self_source_and_profile(tmp_path, monkeypatch, change):
    source = tmp_path / 'scripts/caller.py'; source.parent.mkdir(); source.write_bytes(b'synthetic public source')
    monkeypatch.setattr(m, 'ROOT', tmp_path); monkeypatch.setattr(m, 'SOURCE', source); monkeypatch.setattr(m, '__file__', str(source))
    selected = args(); selected.caller_sha256 = m.sha(source.read_bytes()); selected.profile_sha256 = m.sha(m.canonical(m.profile_record()))
    monkeypatch.setattr(m, 'sys', NS(platform='darwin', version_info=(3, 13), executable=m.PYTHON,
        flags=NS(isolated=1), dont_write_bytecode=True))
    monkeypatch.setattr(m.Path, 'cwd', classmethod(lambda cls: tmp_path)); monkeypatch.setattr(m, 'safe_env', lambda: {})
    def run(command, **kwargs):
        if command[1] == 'cat-file': out = source.read_bytes() if change != 'source' else b'changed'
        elif command[1] == 'status': out = b'untracked' if change == 'dirty' else b''
        elif command[1] == 'branch': out = m.BRANCH.encode()
        elif command[-1] == 'HEAD': out = ('d' * 40 if change == 'head' else selected.expected_head).encode()
        else: out = str(tmp_path).encode()
        return NS(returncode=0, stderr=b'', stdout=out)
    monkeypatch.setattr(m.subprocess, 'run', run)
    if change == 'profile': selected.profile_sha256 = 'd' * 64
    if change == 'platform': m.sys.platform = 'other'
    if change == 'isolated': m.sys.flags.isolated = 0
    refuse('host' if change in ('platform', 'isolated') else 'git_state' if change in ('head', 'dirty') else 'source_pin',
        lambda: m.preflight(selected, time.monotonic() + 899))


def test_parent_held_public_source_guards_return_before_final_metadata(monkeypatch):
    order = []
    class Public:
        def __enter__(self): return self
        def __exit__(self, *a): order.append('source_normal_return')
    def boot(role, stack, deadline): stack.enter_context(Public()); return {}
    monkeypatch.setattr(m, 'preflight', lambda *a: None); monkeypatch.setattr(m, 'bootstrap', boot)
    monkeypatch.setattr(m, '_parent_bound', lambda *a: (order.append('child_return') or {'synthetic': 'public'}))
    assert m.parent(args()) == {'synthetic': 'public'} and order == ['child_return', 'source_normal_return']


@pytest.mark.parametrize('role', ['worker', 'validate'])
def test_fresh_compile_held_source_finder_and_component_profiles_no_pyc(role):
    code = """from scripts import prepare_arv2_r338_quarantine_v4 as m
from contextlib import ExitStack
import sys,time
assert sys.flags.isolated==1 and sys.dont_write_bytecode
with ExitStack() as stack:
 modules=m.bootstrap(ROLE,stack,time.monotonic()+899)
 assert set(modules)=={'security','guard','input','coverage','materialization','source_pairs'}
 assert len(modules['source_pairs'])==21
 for name in ('guard','input','coverage','materialization'):
  record=modules[name].profile_record(m.DATA_PLAN) if name=='guard' else modules[name].profile_record()
  assert m.pin(m.canonical(record))==m.COMPONENT_PROFILE_PINS[name]
  assert modules[name].FINITE==m.MODULE_CODES[name]
 assert modules['input'].__name__=='scripts.arv2_r338_quarantine_input_v2'
 assert modules['materialization'].__name__=='scripts.arv2_r338_quarantine_materialization_v2'
 assert 'scripts.arv2_r338_quarantine_materialization' not in sys.modules
 assert 'scripts.arv2_r338_quarantine_input' not in sys.modules
 assert 'scripts.prepare_arv2_r338_quarantine' not in sys.modules
 for name in ('arv2_relocation_security','arv2_r338_quarantine_data_guard','arv2_r338_quarantine_input_v2','arv2_r338_quarantine_coverage','arv2_r338_quarantine_materialization_v2'):
  module=sys.modules['scripts.'+name]
  assert type(module.__spec__.loader).__name__=='SourceLoader'
  assert getattr(module,'__cached__',None) is None
 assert 'assistant.dispatch_fence' not in sys.modules
 assert not any(name.startswith(('scripts.run_arv2','scripts.observe_arv2','scripts.inspect_arv2','QuantConnect')) for name in sys.modules)
 assert 'scripts.arv2_keychain_connections' not in sys.modules
""".replace('ROLE', repr(role))
    child = subprocess.run([sys.executable, '-I', '-B', '-c', 'import sys;sys.path.insert(0,' + repr(str(m.ROOT)) + ');' + code],
        cwd=m.ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20,
        env={'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LC_ALL': 'C', 'PYTHONDONTWRITEBYTECODE': '1'})
    assert child.returncode == 0 and not child.stdout and not child.stderr


def test_selected_source_inventory_contains_all_components_and_exact_current_pins():
    assert len(m.SOURCE_PINS) == 132
    for path, expected in m.SOURCE_PINS.items(): assert m.sha((m.ROOT / path).read_bytes()) == expected
    assert all('scripts/arv2_r338_quarantine_' + name + '.py' in m.SOURCE_PINS
        for name in ('data_guard', 'input', 'input_v2', 'coverage', 'materialization', 'materialization_v2'))
    assert set(m.COMPONENT_PROFILE_PINS) == set(m.MODULE_CODES) == {'guard', 'input', 'coverage', 'materialization'}
    assert m.profile_record()['native_worker_policy_sha256'] == m.sha(m.native_profile().encode())
    tree = ast.parse(m.SOURCE.read_bytes())
    assert not any(isinstance(node, ast.ImportFrom) and (node.module or '').startswith(('scripts.', 'research.')) for node in ast.walk(tree))


def test_E_exact_caller_profile_inventory_and_new_materializer_pins():
    source=m.SOURCE.read_bytes()
    assert m.pin(source)=={'byte_count':58660,
        'sha256':'7efee1808ee62c9044a96d676b276660b2b9ac67f39c06f4609d435d51ee2618'}
    assert m.pin(m.canonical(m.profile_record()))=={'byte_count':21215,
        'sha256':'366e1813cb32c20c2690f45d7b1335a2bf2f0e93a2a5f15352b814ee5165ab03'}
    assert m.pin(m.canonical(m.SOURCE_PINS))=={'byte_count':16803,
        'sha256':'0bced17b9358ebe9473a92ae4d8a5c3986941fc71f0c90cb34cf73f86a2fc4f3'}
    assert m.SOURCE_PINS['scripts/arv2_r338_quarantine_materialization.py']==(
        'b9c5c84bee710f2e4c1b2ce062d8ec56d7293193c7b00fcc8113d3d94ca2016f')
    assert m.SOURCE_PINS['scripts/arv2_r338_quarantine_materialization_v2.py']==(
        '0dd3e11b339438c36702b3ddb446fb6cf870a42aefbf91269df104a17838ba58')
    assert m.COMPONENT_PROFILE_PINS['materialization']=={'byte_count':10168,
        'sha256':'aa2b326c2c27a06d0da3d65c38315c07b9e063fc5225b3429dd5931a8ba6e08c'}


def test_E_contract_uses_new_control_and_input_role_without_expanding_data_scope():
    assert m.SOURCE.name == 'prepare_arv2_r338_quarantine_v4.py'
    assert m.CONTROL.name == 'R338-20261104-E'
    assert m.SCHEMA.endswith('-v4')
    assert set(m.DATA_PLAN) == {'quarantine', 'archive'}
    assert all('R338-20261104-A' not in row['relative_path'] for row in m.DATA_PLAN.values())
    tree = ast.parse(m.SOURCE.read_bytes())
    bootstrap = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'bootstrap')
    literals = {node.value for node in ast.walk(bootstrap) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert 'scripts.arv2_r338_quarantine_input_v2' in literals
    assert 'scripts.arv2_r338_quarantine_materialization_v2' in literals
    assert 'scripts.arv2_r338_quarantine_materialization' not in literals
    assert 'scripts.prepare_arv2_r338_quarantine' not in literals


def test_native_package_scope_matches_independent_frozen_input_derivation():
    from scripts import arv2_r338_quarantine_input_v2 as actual_input
    expected = actual_input.INPUT_ROOT / ('arv2-preliminary-qc-package-' + actual_input.PACKAGE_SHA256[:24])
    assert m.INPUT_PACKAGE == expected and len(m.INPUT_PACKAGE.name.rsplit('-', 1)[1]) == 24
    assert actual_input.input_paths()['package_directory'] == str(m.INPUT_PACKAGE)
    assert actual_input.input_paths()['source_activation'] == str(m.INPUT_PACKAGE / 'transport-manifest.json')
    assert actual_input.input_paths()['lineage_file'] == str(m.INPUT_LINEAGE)
    policy = m.native_profile()
    assert '(require-not (subpath "' + str(expected) + '"))' in policy
    old_wrong = expected.parent / ('arv2-preliminary-qc-package-' + actual_input.PACKAGE_SHA256[:25])
    assert str(old_wrong) not in policy


@pytest.mark.parametrize('fault', ['package', 'lineage'])
def test_fresh_bootstrap_refuses_helper_scope_mismatch_before_claim(fault):
    code = """import os,sys,time
from pathlib import Path
from contextlib import ExitStack
from scripts import prepare_arv2_r338_quarantine_v4 as m
if FAULT=='package':m.INPUT_PACKAGE=Path(str(m.INPUT_PACKAGE)+'d')
else:m.INPUT_LINEAGE=m.INPUT_LINEAGE.parent/'wrong-lineage.json'
try:
 with ExitStack() as sources:m.bootstrap('worker',sources,time.monotonic()+899)
except m.Refused as error:
 assert m.finite(error)=='source_pin' and m.CLAIM_STATE=='unallocated'
 os.write(1,b'preclaim-path-refusal\\n')
else:raise SystemExit(2)
""".replace('FAULT', repr(fault))
    child = subprocess.run([sys.executable, '-I', '-B', '-c', 'import sys;sys.path.insert(0,' + repr(str(m.ROOT)) + ');' + code],
        cwd=m.ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20,
        env={'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LC_ALL': 'C', 'PYTHONDONTWRITEBYTECODE': '1'})
    assert child.returncode == 0 and child.stdout == b'preclaim-path-refusal\n' and not child.stderr


def test_real_nonisolated_validator_preflight_refuses_before_git_or_claim():
    code = """import os,sys,time
from types import SimpleNamespace as NS
from scripts import prepare_arv2_r338_quarantine_v4 as m
assert sys.flags.isolated==0
def forbidden(*a,**k):raise AssertionError('git-before-host-refusal')
m.subprocess.run=forbidden
args=NS(expected_head='a'*40,caller_sha256='b'*64,profile_sha256='c'*64)
try:m.preflight(args,time.monotonic()+899)
except m.Refused as error:
 assert m.finite(error)=='host' and m.CLAIM_STATE=='unallocated'
 os.write(1,b'isolated-required\\n')
else:raise SystemExit(2)
"""
    child = subprocess.run([sys.executable, '-s', '-B', '-c', 'import sys;sys.path.insert(0,' + repr(str(m.ROOT)) + ');' + code],
        cwd=m.ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, env=m.safe_env())
    assert child.returncode == 0 and child.stdout == b'isolated-required\n' and not child.stderr


def _native_scope_rehearsal(base):
    """Run separately at top level: macOS cannot apply a new nested sandbox.

    Only in-root synthetic files are created/opened. Production artifacts are
    explicitly denied in addition to the real caller's remapped policy. This
    utility is not an operational caller or a pytest skip/fallback.
    """
    from scripts import arv2_r338_quarantine_input_v2 as actual_input
    real_root = m.ROOT
    base.mkdir(parents=True, exist_ok=True)
    fake = base / 'native-root'; fake.mkdir(mode=0o755); fake.chmod(0o755)
    input_root = fake / 'artifacts/input'
    for relative in ('artifacts', 'artifacts/input', 'artifacts/retained'):
        (fake / relative).mkdir(mode=0o700)
    expected = input_root / actual_input.PACKAGE.name
    declared = input_root / m.INPUT_PACKAGE.name
    wrong = input_root / ('arv2-preliminary-qc-package-' + actual_input.PACKAGE_SHA256[:25])
    sibling = input_root / 'unrelated-sibling'
    for directory in {expected, wrong, sibling}:
        directory.mkdir(mode=0o700)
        (directory / 'transport-manifest.json').write_bytes(b'public-synthetic-activation')
    lineage = input_root / 'synthetic-lineage.json'; lineage.write_bytes(b'public-synthetic-lineage')
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(m, 'ROOT', fake)
        patch.setattr(m, 'CONTROL', fake / 'artifacts/retained/synthetic-control')
        patch.setattr(m, 'INPUT_PACKAGE', declared); patch.setattr(m, 'INPUT_LINEAGE', lineage)
        patch.setattr(m, 'DATA_PLAN', {name: {'relative_path': 'artifacts/retained/' + name + '.json'}
            for name in ('quarantine', 'archive')})
        policy = m.native_profile() + '(deny file-read* file-write* (subpath "' + str(real_root / 'artifacts') + '"))'
        environment = m.safe_env()
    code = """import os,socket
expected=EXPECTED;forbidden=FORBIDDEN
fd=os.open(expected,os.O_RDONLY|os.O_NOFOLLOW)
try:assert os.read(fd,100)==b'public-synthetic-activation'
finally:os.close(fd)
for path in forbidden:
 try:fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
 except PermissionError:pass
 else:
  os.close(fd);raise AssertionError('wrong-scope-opened')
connection=None
try:
 connection=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
 connection.connect(('127.0.0.1',9))
except PermissionError:pass
else:raise AssertionError('network-denial-missing')
finally:
 if connection is not None:connection.close()
os.write(1,b'exact24-open-wrong25-sibling-network-denied\\n')
""".replace('EXPECTED', repr(str(expected / 'transport-manifest.json'))).replace('FORBIDDEN',
        repr([str(path / 'transport-manifest.json') for path in (wrong, sibling)]))
    child = subprocess.run(['/usr/bin/sandbox-exec', '-p', policy, m.PYTHON, '-I', '-B', '-c', code],
        cwd=real_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, env=environment)
    assert child.returncode == 0 and child.stdout == b'exact24-open-wrong25-sibling-network-denied\n' and not child.stderr
    return {'native_exit': 0, 'correct_24_opened': True, 'wrong_25_denied': True,
        'sibling_denied': True, 'network_denied': True, 'production_artifacts_denied': True}


@pytest.mark.parametrize('name', ['guard', 'input', 'coverage', 'materialization'])
def test_dependency_deadline_is_never_relabelled_as_private_data(name, monkeypatch):
    class Budget(ValueError): pass
    monkeypatch.setitem(m.MODULES, name, NS(Refused=Budget, finite=lambda _: 'deadline'))
    assert m.finite(Budget('deadline')) == 'deadline'


@pytest.mark.parametrize('code', ['guard_deadline', 'input_deadline', 'coverage_deadline', 'materialization_deadline'])
def test_prefixed_deadline_not_an_admissible_failure_category(code):
    refuse('output', lambda: m.failure_packet(code))


@pytest.mark.parametrize('error', [TimeoutError(), subprocess.TimeoutExpired('synthetic git', 1), m.RunDeadline()])
def test_control_builtin_and_git_timeouts_have_canonical_deadline(error):
    assert m.finite(error) == 'deadline'


def test_real_timer_inside_private_json_handler_preserves_deadline_not_secondary_error():
    code = """import os,signal,time
from scripts import prepare_arv2_r338_quarantine_v4 as m
from research.analyst_revisions_v2_qc import newrule_five_case_quarantine_policy as policy
original=policy.json.dumps
def slow(*a,**k):
 time.sleep(1)
 return original(*a,**k)
policy.json.dumps=slow
signal.signal(signal.SIGALRM,m.deadline_expired)
signal.setitimer(signal.ITIMER_REAL,.02)
try:policy.canonical({'synthetic':1})
except m.RunDeadline:
 assert m.DEADLINE_FIRED and m.finite(ValueError('PRIVATE-CLEANUP'))=='deadline'
 os.write(1,b'deadline\\n')
else:raise SystemExit(2)
finally:signal.setitimer(signal.ITIMER_REAL,0)
"""
    child = subprocess.run([sys.executable, '-I', '-B', '-c', 'import sys;sys.path.insert(0,' + repr(str(m.ROOT)) + ');' + code],
        cwd=m.ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5, env=m.safe_env())
    assert child.returncode == 0 and child.stdout == b'deadline\n' and not child.stderr


def test_real_tiny_child_inherits_only_explicit_intent_descriptor(monkeypatch):
    monkeypatch.setattr(m, 'safe_env', lambda: {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin',
        'LC_ALL': 'C', 'PYTHONDONTWRITEBYTECODE': '1'})
    reader, writer = os.pipe()
    try:
        os.write(writer, b'synthetic-one-use-intent'); os.close(writer); writer = None
        code = 'import os,sys;raw=os.read(int(sys.argv[1]),100);assert raw==b"synthetic-one-use-intent";os.write(1,b"bound-intent\\n")'
        observed = m.run_child([sys.executable, '-I', '-B', '-c', code, str(reader)], (reader,), time.monotonic() + 10)
        assert observed == (0, b'bound-intent\n', 0, m.sha(b''), None)
    finally:
        os.close(reader)
        if writer is not None: os.close(writer)


@pytest.mark.parametrize('kind', ['symlink', 'unknown', 'bytes', 'mode', 'security'])
def test_original_held_control_and_output_metadata_security_unchanged(tmp_path, monkeypatch, kind):
    fixture_root(tmp_path, monkeypatch)
    if kind == 'symlink':
        other = tmp_path / 'other'; other.mkdir()
        m.CONTROL.parent.symlink_to(other, target_is_directory=True)
        with pytest.raises((OSError, m.Refused)): m.Store(Security).__enter__()
        assert not (other / m.CONTROL.name).exists(); return
    class Current(Security):
        changed = False
        @staticmethod
        def snapshot(fd): return {'synthetic_current_security': Current.changed}
    with pytest.raises(m.Refused):
        with m.Store(Current) as store:
            store.write('claim.json', b'{}')
            if kind == 'unknown': (m.CONTROL / 'unknown').write_bytes(b'PRIVATE')
            elif kind == 'bytes': (m.CONTROL / 'claim.json').write_bytes(b'PRIVATE')
            elif kind == 'mode': (m.CONTROL / 'claim.json').chmod(0o644)
            else: Current.changed = True
            store.verify()


def test_low_descriptor_budget_refuses_before_git_or_claim(monkeypatch):
    monkeypatch.setattr(m.resource, 'getrlimit', lambda _: (16, 16))
    monkeypatch.setattr(m.subprocess, 'run', lambda *a, **k: pytest.fail('git reached before descriptor refusal'))
    refuse('descriptor_budget', lambda: m.preflight(args(), time.monotonic() + 899))
    assert m.CLAIM_STATE == 'unallocated'


def test_git_timeout_preserved_as_deadline_before_claim(monkeypatch):
    selected = args(); selected.profile_sha256 = m.sha(m.canonical(m.profile_record()))
    monkeypatch.setattr(m, 'sys', NS(platform='darwin', version_info=(3, 13), executable=m.PYTHON,
        flags=NS(isolated=1), dont_write_bytecode=True))
    def timeout(*a, **k): raise subprocess.TimeoutExpired('synthetic git', 1)
    monkeypatch.setattr(m.subprocess, 'run', timeout)
    with pytest.raises(subprocess.TimeoutExpired) as error: m.preflight(selected, time.monotonic() + 899)
    assert m.finite(error.value) == 'deadline' and m.CLAIM_STATE == 'unallocated'


def test_insufficient_inroot_free_space_refuses_before_git_or_claim(monkeypatch):
    monkeypatch.setattr(m.os, 'statvfs', lambda root: NS(f_bavail=0, f_frsize=4096))
    monkeypatch.setattr(m.subprocess, 'run', lambda *a, **k: pytest.fail('git reached before disk refusal'))
    refuse('disk_budget', lambda: m.preflight(args(), time.monotonic() + 899))
    assert m.CLAIM_STATE == 'unallocated'
