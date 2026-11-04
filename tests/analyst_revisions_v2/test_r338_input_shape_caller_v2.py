"""Only public code and in-root synthetic metadata/control fixtures."""
import ast
from contextlib import ExitStack
import copy
import errno
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
from types import SimpleNamespace as NS

import pytest
from scripts import inspect_arv2_r338_input_shape_v2 as m
from scripts import arv2_r338_input_shape as h


def deadline(): return time.monotonic() + 29
def args(): return NS(expected_head='a' * 40, caller_sha256='b' * 64,
    helper_sha256=m.HELPER_SHA256, profile_sha256='c' * 64)


def refuse(code, call):
    with pytest.raises(m.Refused) as error: call()
    assert m.finite(error.value) == code


@pytest.fixture(autouse=True)
def state(monkeypatch):
    monkeypatch.setattr(m, 'DEADLINE_FIRED', False)
    monkeypatch.setattr(m, 'CLAIM_STATE', 'unallocated')
    monkeypatch.setattr(m, 'ACTIVE_BINDING', None)


def synthetic_rows():
    rows = []
    for spec in h.scope():
        mode = stat.S_IFDIR if spec['kind'] == 'directory' else stat.S_IFREG
        permission = spec['required_mode'] if spec['required_mode'] is not None else 0o755
        info = (1, 100 + spec['path_index'], mode | permission, os.getuid(), 20, 1,
            spec['exact_bytes'] or 100, 100000, 200000, 0)
        rows.append({'path_index': spec['path_index'], 'path': spec['path'],
            'first_metadata': info, 'second_metadata': info, 'first_status': 'observed', 'second_status': 'observed'})
    return rows


def summary(): return h.inspect_metadata(synthetic_rows(), uid=os.getuid(), transport_nonce='37' * 32)[0]


def packet():
    value = {'schema': m.SCHEMA, 'diagnostic_complete': True, 'summary': summary(),
        'private_evidence_pin': summary()['private_evidence_pin'], 'source_code_guards_normal_return': True,
        'claim_pin': m.pin(m.canonical({'binding': m.binding(args()), 'profile_sha256': args().profile_sha256})), **m.FALSE_FLAGS}
    report = {'binding': m.binding(args()), 'result': value}
    return {**report, 'report_pin': m.pin(m.canonical(report))}


class Security:
    @staticmethod
    def snapshot(fd): return {'synthetic_empty_security': True}


def fixture_root(tmp_path, monkeypatch):
    root = tmp_path / 'root'; root.mkdir(mode=0o755); root.chmod(0o755)
    artifact = root / 'artifacts'; artifact.mkdir(mode=0o700)
    lane = artifact / 'analyst_revisions_v2'; lane.mkdir(mode=0o700)
    monkeypatch.setattr(m, 'ROOT', root); monkeypatch.setattr(m, 'CONTROL', lane / 'quarantine/R338-B2')


def test_real_pure_summary_strict_original_stdout_report_and_actual_exit():
    raw = m.canonical(packet()) + b'\n'
    assert m.validate_output(raw, 0, args(), h) == packet()
    assert b'source_activation' in raw
    assert b'37' * 32 not in raw
    assert all(packet()['result'][key] is False for key in m.FALSE_FLAGS)


@pytest.mark.parametrize('fault', ['actual2', 'actual3', 'bool_exit', 'bool_false_exit', 'none_exit', 'private_pin', 'report_pin', 'claim_pin',
    'binding', 'source_guard', 'flag', 'trailing', 'doubleLF', 'duplicate_json'])
def test_actual_exit_and_all_public_bindings_refuse_forgery(fault):
    value = packet(); actual = 0
    if fault == 'actual2': actual = 2
    elif fault == 'actual3': actual = 3
    elif fault == 'bool_exit': actual = True
    elif fault == 'bool_false_exit': actual = False
    elif fault == 'none_exit': actual = None
    elif fault == 'private_pin': value['result']['private_evidence_pin']['sha256'] = 'f' * 64
    elif fault == 'report_pin': value['report_pin']['sha256'] = 'f' * 64
    elif fault == 'claim_pin': value['result']['claim_pin']['sha256'] = 'f' * 64
    elif fault == 'binding': value['binding']['expected_head'] = 'f' * 40
    elif fault == 'source_guard': value['result']['source_code_guards_normal_return'] = 1
    elif fault == 'flag': value['result']['source_bytes_read'] = True
    raw = m.canonical(value) + b'\n'
    if fault == 'trailing': raw += b'noise'
    elif fault == 'doubleLF': raw += b'\n'
    elif fault == 'duplicate_json': raw = b'{"schema":1,"schema":2}\n'
    with pytest.raises(m.Refused): m.validate_output(raw, actual, args(), h)


def test_actual2_failure_cannot_be_accepted_as_observation(monkeypatch):
    monkeypatch.setattr(m, 'ACTIVE_BINDING', m.binding(args()))
    value = m.failure('metadata'); raw = m.canonical(value) + b'\n'
    assert m.validate_output(raw, 2, args(), h)['attempt_reusable'] is False
    refuse('output', lambda: m.validate_output(raw, 0, args(), h))


def test_rehashed_report_cannot_replace_the_summary_private_evidence_binding():
    value = packet(); value['result']['private_evidence_pin']['sha256'] = 'f' * 64
    value['report_pin'] = m.pin(m.canonical({'binding': value['binding'], 'result': value['result']}))
    refuse('output', lambda: m.validate_output(m.canonical(value) + b'\n', 0, args(), h))


def test_collect_only_lstat_twice_fixed_plan_and_block_bad_ancestor(monkeypatch):
    plan = h.scope(); data = synthetic_rows(); first = {row['path']: row['first_metadata'] for row in data}
    bad = next(spec for spec in plan if spec['kind'] == 'directory' and spec['scoped'] and spec['path'] != str(h.ROOT))
    values = list(first[bad['path']]); values[2] = stat.S_IFLNK | 0o777; first[bad['path']] = tuple(values)
    seen = []
    def lstat(path):
        path = str(path); seen.append(path); value = first[path]
        return NS(**dict(zip(m.FIELDS, value)))
    monkeypatch.setattr(m.os, 'lstat', lstat)
    monkeypatch.setattr(m.os, 'open', lambda *a, **k: pytest.fail('source descriptor opened'))
    monkeypatch.setattr(m.os, 'listdir', lambda *a, **k: pytest.fail('source directory listed'))
    rows = m.collect(h, deadline())
    assert seen.count(bad['path']) == 2
    for spec, row in zip(plan, rows):
        if Path(bad['path']) in Path(spec['path']).parents:
            assert spec['path'] not in seen
            assert row['first_status'] == row['second_status'] == 'blocked_ancestor'
    assert h.inspect_metadata(rows, uid=os.getuid(), transport_nonce='47' * 32)[0]['all_observed_policy_passed'] is False


@pytest.mark.parametrize('code,status', [(errno.ENOENT, 'not_found'), (errno.EACCES, 'permission_denied'),
    (errno.EPERM, 'permission_denied'), (errno.ENOTDIR, 'not_directory'), (errno.EIO, 'unavailable')])
def test_source_stat_errno_is_finite_observation_not_contents_or_raw_error(monkeypatch, code, status):
    root = h.scope()[0]['path']
    def lstat(path): assert str(path) == root; raise OSError(code, 'PRIVATE-RAW-ERROR')
    monkeypatch.setattr(m.os, 'lstat', lstat)
    rows = m.collect(h, deadline())
    assert rows[0]['first_status'] == rows[0]['second_status'] == status
    assert all(row['first_status'] == 'blocked_ancestor' for row in rows[1:])


def test_claim_fsync_nonce_metadata_then_source_return_before_private_publication(tmp_path, monkeypatch):
    fixture_root(tmp_path, monkeypatch); order = []
    class Codes:
        def close(self): order.append('source_normal_return')
    def collect(helper, stop):
        assert (m.CONTROL / 'claim.json').exists(); order.append('metadata'); return synthetic_rows()
    def nonce(count):
        assert count == 32 and (m.CONTROL / 'claim.json').exists(); order.append('nonce'); return bytes(range(32))
    monkeypatch.setattr(m, 'collect', collect); monkeypatch.setattr(m.os, 'urandom', nonce)
    monkeypatch.setattr(m, 'preflight', lambda *a: order.append('postflight'))
    original = m.Store.write
    def write(store, name, raw):
        if name != 'claim.json': assert 'source_normal_return' in order
        result = original(store, name, raw); order.append(name); return result
    monkeypatch.setattr(m.Store, 'write', write)
    result = m.observe(args(), h, Security, Codes(), deadline())
    assert order.index('claim.json') < order.index('nonce') < order.index('metadata') < order.index('source_normal_return')
    assert order.index('source_normal_return') < order.index('metadata-private.json') < order.index('report.json')
    assert bytes(range(32)).hex().encode() not in m.canonical(result)
    assert (m.CONTROL / 'metadata-private.json').stat().st_mode & 0o777 == 0o600
    m.validate_output(m.canonical(result) + b'\n', 0, args(), h)
    refuse('claim_spent', lambda: m.observe(args(), h, Security, Codes(), deadline()))


def test_code_guard_exit_refusal_never_publishes_private_or_report(tmp_path, monkeypatch):
    fixture_root(tmp_path, monkeypatch)
    class Codes:
        def close(self): raise m.Refused('source_changed')
    monkeypatch.setattr(m, 'collect', lambda *a: synthetic_rows())
    refuse('source_changed', lambda: m.observe(args(), h, Security, Codes(), deadline()))
    assert (m.CONTROL / 'claim.json').exists()
    assert not (m.CONTROL / 'metadata-private.json').exists() and not (m.CONTROL / 'report.json').exists()


def test_native_policy_metadata_scope_and_own_output_only():
    policy = m.native_profile(h)
    assert '(deny network*)' in policy and '(deny file-read-data' in policy
    assert '(deny file-read-xattr' in policy and '/usr/bin/security' in policy
    for spec in h.scope():
        if str(m.ROOT / 'artifacts') in spec['path']: assert '(literal "' + spec['path'] + '")' in policy
    assert '(require-not (subpath "' + str(m.CONTROL) + '"))' in policy
    strict = m.native_profile(h, validator=True)
    assert '(deny file-read* (subpath "' + str(m.ROOT / 'artifacts') + '"))' in strict
    assert 'old_A_report' not in policy


def test_selected_public_code_compiles_without_old_input_or_operational_imports():
    with ExitStack() as stack:
        helper, security = m.load_modules(stack, m.HELPER_SHA256)
        assert helper.scope() == h.scope()
        assert callable(security.snapshot)
    tree = ast.parse(m.SOURCE.read_bytes())
    assert not any(isinstance(node, ast.ImportFrom) and (node.module or '').startswith(('scripts.', 'research.')) for node in ast.walk(tree))
    calls = {node.func.attr for node in ast.walk(next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'collect'))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert not calls.intersection({'open', 'read', 'pread', 'listdir', 'resolve', 'stat', 'snapshot', 'getxattr'})


def test_real_alarm_inside_json_keeps_deadline_over_secondary_failure():
    code = """import os,sys,signal,time
sys.path.insert(0,ROOT)
from scripts import inspect_arv2_r338_input_shape_v2 as m
original=m.json.dumps
def slow(*a,**k):time.sleep(1);return original(*a,**k)
m.json.dumps=slow
signal.signal(signal.SIGALRM,m.expire);signal.setitimer(signal.ITIMER_REAL,.02)
try:m.canonical({'synthetic':1})
except m.RunDeadline:
 assert m.DEADLINE_FIRED and m.finite(ValueError('PRIVATE-CLEANUP'))=='deadline'
 os.write(1,b'deadline\\n')
else:raise SystemExit(2)
finally:signal.setitimer(signal.ITIMER_REAL,0)
""".replace('ROOT', repr(str(m.ROOT)))
    result = subprocess.run([sys.executable, '-I', '-B', '-c', code], cwd=m.ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5, env=m.safe_env())
    assert result.returncode == 0 and result.stdout == b'deadline\n' and not result.stderr


@pytest.mark.parametrize('operation', ['observe', 'validate'])
def test_cli_arms_actual_timer_before_code_load_or_metadata(monkeypatch, operation):
    selected = args(); events = []
    argv = [operation, '--expected-head', selected.expected_head, '--caller-sha256', selected.caller_sha256,
        '--helper-sha256', selected.helper_sha256, '--profile-sha256', selected.profile_sha256]
    if operation == 'validate': argv += ['--actual-exit', '0']
    monkeypatch.setattr(m.signal, 'signal', lambda *a: None)
    monkeypatch.setattr(m.signal, 'setitimer', lambda *a: events.append('alarm'))
    monkeypatch.setattr(m, 'load_modules', lambda *a: (events.append('code') or (h, Security)))
    class Held:
        def __init__(self, *a): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
    monkeypatch.setattr(m, 'HeldCode', Held); monkeypatch.setattr(m, 'preflight', lambda *a: events.append('preflight'))
    monkeypatch.setattr(m, 'observe', lambda *a: {'synthetic': True})
    monkeypatch.setattr(m.sys, 'stdin', NS(buffer=io.BytesIO(m.canonical(packet()) + b'\n')))
    assert m.main(argv)
    assert events[0:2] == ['alarm', 'code']


def test_actual_synthetic_observe_and_stdin_validator_subprocess(tmp_path):
    root = tmp_path / 'root'; root.mkdir(mode=0o755); root.chmod(0o755)
    (root / 'artifacts').mkdir(mode=0o700); (root / 'artifacts/analyst_revisions_v2').mkdir(mode=0o700)
    code = """import os,sys,json,time
from contextlib import ExitStack
from types import SimpleNamespace as NS
from pathlib import Path
sys.path.insert(0,__REPO__)
from scripts import inspect_arv2_r338_input_shape_v2 as m
from scripts import arv2_r338_input_shape as h
m.ROOT=Path(__FIXTURE_ROOT__);m.CONTROL=m.ROOT/'artifacts/analyst_revisions_v2/quarantine/R338-B2'
class Security:
 @staticmethod
 def snapshot(fd):return {'synthetic_empty':True}
class Codes:
 def close(self):pass
args=NS(expected_head='a'*40,caller_sha256='b'*64,helper_sha256=m.HELPER_SHA256,profile_sha256='c'*64)
if OP=='observe':
 rows=[]
 for spec in h.scope():
  mode=(0o040000 if spec['kind']=='directory' else 0o100000)|(spec['required_mode'] or 0o755)
  info=(1,100+spec['path_index'],mode,os.getuid(),20,1,spec['exact_bytes'] or 100,1,1,0)
  rows.append({'path_index':spec['path_index'],'path':spec['path'],'first_metadata':info,'second_metadata':info,'first_status':'observed','second_status':'observed'})
 m.collect=lambda *a:rows;m.preflight=lambda *a:None
 value=m.observe(args,h,Security,Codes(),time.monotonic()+29)
 os.write(1,m.canonical(value)+b'\\n')
else:
 raw=sys.stdin.buffer.read(m.MAX_OUTPUT+1);m.validate_output(raw,0,args,h);os.write(1,raw)
""".replace('__REPO__', repr(str(m.ROOT))).replace('__FIXTURE_ROOT__', repr(str(root)))
    environment = m.safe_env()
    first = subprocess.run([sys.executable, '-I', '-B', '-c', code.replace('OP', repr('observe'))], cwd=m.ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, env=environment)
    assert first.returncode == 0 and not first.stderr
    second = subprocess.run([sys.executable, '-I', '-B', '-c', code.replace('OP', repr('validate'))], cwd=m.ROOT,
        input=first.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, env=environment)
    assert second.returncode == 0 and second.stdout == first.stdout and not second.stderr
    assert b'expected_uid' not in first.stdout and b'transport_nonce' not in first.stdout


@pytest.mark.parametrize('fault', ['none', 'profile', 'head', 'source', 'environment', 'host'])
def test_preflight_current_root_head_code_profile_and_credential_free_environment(tmp_path, monkeypatch, fault):
    root = tmp_path / 'root'; root.mkdir(); sources = root / 'scripts'; sources.mkdir()
    caller = sources / 'caller.py'; caller.write_bytes(b'synthetic-public-caller')
    helper = sources / 'helper.py'; helper.write_bytes(m.HELPER.read_bytes())
    security = sources / 'security.py'; security.write_bytes(m.SECURITY.read_bytes())
    monkeypatch.setattr(m, 'ROOT', root); monkeypatch.setattr(m, 'SOURCE', caller)
    monkeypatch.setattr(m, 'HELPER', helper); monkeypatch.setattr(m, 'SECURITY', security)
    monkeypatch.setattr(m, '__file__', str(caller)); monkeypatch.setattr(m.Path, 'cwd', classmethod(lambda _: root))
    monkeypatch.setattr(m, 'safe_env', lambda: {})
    monkeypatch.setattr(m.os, 'environ', {'UNEXPECTED': 'PRIVATE'} if fault == 'environment' else {})
    monkeypatch.setattr(m, 'sys', NS(platform='darwin', version_info=(3, 13), executable=m.PYTHON,
        flags=NS(isolated=0 if fault == 'host' else 1), dont_write_bytecode=True))
    selected = args(); selected.caller_sha256 = m.sha(caller.read_bytes())
    selected.profile_sha256 = m.sha(m.canonical(m.profile_record(h)))
    if fault == 'profile': selected.profile_sha256 = 'f' * 64
    def git(command, **kwargs):
        if command[1] == 'cat-file':
            output = (root / command[-1].split(':', 1)[1]).read_bytes()
            if fault == 'source' and command[-1].endswith('caller.py'): output += b'drift'
        elif command[1] == 'status': output = b''
        elif command[1] == 'branch': output = m.BRANCH.encode()
        elif command[-1] == 'HEAD': output = ('f' * 40 if fault == 'head' else selected.expected_head).encode()
        else: output = str(root).encode()
        return NS(returncode=0, stderr=b'', stdout=output)
    monkeypatch.setattr(m.subprocess, 'run', git)
    if fault == 'none': m.preflight(selected, h, deadline())
    else: refuse({'profile': 'source_pin', 'head': 'git_state', 'source': 'source_pin',
        'environment': 'environment', 'host': 'host'}[fault], lambda: m.preflight(selected, h, deadline()))


@pytest.mark.parametrize('include', [False, True])
def test_only_exact_observed_OS_current_uid_uppercase_encoding_is_allowed(include, monkeypatch):
    monkeypatch.setattr(m.os, 'getuid', lambda: 0x1AB)
    value = m.safe_env()
    if include: value['__CF_USER_TEXT_ENCODING'] = '0x1AB:0x0:0x0'
    m.validate_environment(value)


@pytest.mark.parametrize('bad', [None, True, b'0x1AB:0x0:0x0', '0x1ab:0x0:0x0',
    '0X1AB:0x0:0x0', '0x01AB:0x0:0x0', '0x1AC:0x0:0x0', '0x1AB:0x1:0x0',
    '0x1AB:0x0:0x1', '0x1AB:0x0:0x0\n', '0x1AB:0x0:0x0:0x0', '0' * 65])
def test_CF_entry_does_not_become_generic_environment_or_identity_waiver(monkeypatch, bad):
    monkeypatch.setattr(m.os, 'getuid', lambda: 0x1AB)
    value = m.safe_env(); value['__CF_USER_TEXT_ENCODING'] = bad
    refuse('environment', lambda: m.validate_environment(value))


@pytest.mark.parametrize('fault', ['new_key', 'other_CF_key', 'configured_drift', 'configured_nonstr'])
def test_all_other_environment_extras_and_configured_drift_still_refuse(fault):
    value = m.safe_env()
    if fault == 'new_key': value['UNEXPECTED'] = 'PRIVATE'
    elif fault == 'other_CF_key': value['__CF_ARBITRARY'] = 'PRIVATE'
    elif fault == 'configured_drift': value['PATH'] = '/unexpected'
    else: value['PATH'] = True
    refuse('environment', lambda: m.validate_environment(value))


def test_real_native_code_only_environment_contract_does_not_inspect_source():
    # The process is a code-only proof: no observe(), collect(), lstat of
    # source scope, claim, report or artifact read is invoked.
    code = """import os,sys
sys.path.insert(0,REPO)
from scripts import inspect_arv2_r338_input_shape_v2 as m
m.validate_environment(dict(os.environ))
present='__CF_USER_TEXT_ENCODING' in os.environ
os.write(1,b'CF-present\\n' if present else b'CF-absent\\n')
""".replace('REPO', repr(str(m.ROOT)))
    result = subprocess.run([sys.executable, '-I', '-B', '-c', code], cwd=m.ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5, env=m.safe_env())
    assert result.returncode == 0 and result.stdout in (b'CF-present\n', b'CF-absent\n') and not result.stderr
