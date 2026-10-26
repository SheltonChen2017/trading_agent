"""Synthetic A11 process/envelope tests; native denial is required externally.

The real operational worker is never launched. A tiny public-source process
inherits the test invocation's native network/artifact/Keychain denial instead.
Deep admission/access behavior belongs to the separate caller/helper tests.
"""
import copy
from contextlib import nullcontext
import json
import os
import subprocess
import time
from types import SimpleNamespace as NS

import pytest

from scripts import run_arv2_r298_plain_readiness as m
from scripts import arv2_newrule_execution_environment as environment
from tests.analyst_revisions_v2 import test_r298_plain_readiness_remote as public_fixture


ARGS = NS(operation='recover', expected_head='a' * 40, caller_sha256='b' * 64,
    control_fd=None, deadline=None)
OPERATION = 'admission-initial-worker'


@pytest.fixture(autouse=True)
def forbid_operational_boundaries(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError('operational boundary forbidden in channel-only tests')
    monkeypatch.setattr(m.prep, 'construct', forbidden)
    monkeypatch.setattr(m, 'authenticate_storage', forbidden)
    monkeypatch.setattr(m, '_preflight', forbidden)
    monkeypatch.setattr(m, '_worker', forbidden)
    monkeypatch.setattr(m, '_recover', forbidden)
    monkeypatch.setattr(m, 'Store', forbidden)


def worker_result():
    return {'storage_receipt': {'synthetic_public_metadata': True}, 'public_source': 'public-only'}


def worker_envelope(result=None):
    return {'schema': m.SCHEMA, 'operation': OPERATION, 'binding': m.binding(ARGS),
        'result': worker_result() if result is None else result, 'operation_completed': True, **m.FALSE_FLAGS}


def encode(value):
    return m.canonical(value) + b'\n'


@pytest.fixture
def child(tmp_path, monkeypatch):
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    journal, seen, processes = [], [], []
    env = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'TMPDIR': str(tmp_path),
        'PYTHONPYCACHEPREFIX': str(tmp_path / 'cache'), 'PYTHONDONTWRITEBYTECODE': '1'}
    store = NS(fd=fd, write=lambda name, value: journal.append((name, copy.deepcopy(value))))
    original_popen = subprocess.Popen
    case = NS(source='', envelope=worker_envelope(), stderr='', code=0, sleep=False,
        raw=None, public_size=None, journal=journal, seen=seen, processes=processes, store=store)

    class Process:
        def __init__(self, value):
            self.value, self.kills, self.waits = value, 0, []
            self.stdout, self.stderr = value.stdout, value.stderr
        def poll(self): return self.value.poll()
        def kill(self): self.kills += 1; return self.value.kill()
        def wait(self, timeout=None):
            self.waits.append(timeout)
            return self.value.wait(timeout=timeout)

    def popen(command, **kwargs):
        seen.append((command, kwargs))
        assert command[:3] == ['/usr/bin/sandbox-exec', '-p', m.SANDBOX]
        assert command[3:6] == [str(m.frozen.PYTHON), '-B', str(m.SOURCE)]
        assert command[6] == OPERATION
        assert kwargs['cwd'] == m.ROOT and kwargs['env'] == env
        assert kwargs['pass_fds'] == (fd,) and kwargs['stdin'] == subprocess.DEVNULL
        assert not {'QC_USER_ID', 'QC_API_TOKEN'} & set(kwargs['env'])
        source = 'import json,os,sys,time\nos.fstat(int(sys.argv[1]))\n'
        if case.sleep:
            source += 'time.sleep(10)\n'
        elif case.raw is not None:
            source += 'sys.stdout.buffer.write(' + repr(case.raw) + ')\n'
        else:
            value = copy.deepcopy(case.envelope)
            source += 'value=' + repr(value) + '\n'
            if case.public_size is not None:
                source += "value['result']['public_source']='x'*" + str(case.public_size) + '\n'
            source += "sys.stdout.write(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\\n\\n')\n"
        source += 'sys.stderr.write(' + repr(case.stderr) + ')\nraise SystemExit(' + str(case.code) + ')\n'
        process = Process(original_popen([str(m.frozen.PYTHON), '-B', '-c', source, str(fd)],
            cwd=m.ROOT, env=env, pass_fds=(fd,), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE))
        processes.append(process)
        return process

    def public_packet(value):
        # Only this channel fixture substitutes the deep public-source parser.
        assert type(value) is dict and set(value) == {'storage_receipt', 'public_source'}
        assert value['storage_receipt'] == {'synthetic_public_metadata': True}
        assert type(value['public_source']) is str and value['public_source'].isascii()

    monkeypatch.setattr(m, '_worker_environment', lambda: dict(env))
    monkeypatch.setattr(m, '_validate_worker_result', public_packet)
    monkeypatch.setattr(m.subprocess, 'Popen', popen)
    try:
        yield case
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)
        os.close(fd)


def run_child(case, *, seconds=5):
    return m._child(ARGS, case.store, time.monotonic() + seconds, OPERATION)


def test_native_inherited_child_exact_envelope_and_private_free_result(child):
    assert run_child(child) == worker_result()
    assert len(child.journal) == len(child.seen) == len(child.processes) == 1
    name, record = child.journal[0]
    assert name == OPERATION + '-completed.json'
    assert record == {**m.binding(ARGS), 'storage_receipt': worker_result()['storage_receipt'],
        'public_packet_sha256': m.sha(m.canonical(worker_result())),
        'public_packet_byte_count': len(m.canonical(worker_result())), 'actual_worker_exit': 0}
    process = child.processes[0]
    assert process.kills == 0 and process.waits and process.stdout.closed and process.stderr.closed


@pytest.mark.parametrize('field,value', [('schema', 'wrong'), ('operation', 'recover'), ('binding', {}),
    ('operation_completed', False), ('operation_completed', 1), ('backtest_created', True),
    ('capacity_observed', True), ('launch_authorized', True), ('extra', False)])
def test_child_envelope_strict_fields(child, field, value):
    child.envelope[field] = value
    with pytest.raises(m.Refused): run_child(child)
    assert child.journal == [] and child.processes[0].poll() is not None


@pytest.mark.parametrize('code', [1, 2, 3, 17])
def test_actual_nonzero_child_exit_never_publishes_completion(child, code):
    child.code = code
    with pytest.raises(m.Refused, match='^child_failed$'): run_child(child)
    assert child.journal == [] and child.processes[0].poll() == code


@pytest.mark.parametrize('stderr', ['synthetic-noise', '\n', 'x' * 1000])
def test_any_child_stderr_refuses_without_echo(child, stderr, capsys):
    child.stderr = stderr
    with pytest.raises(m.Refused, match='^child_failed$'): run_child(child)
    assert child.journal == [] and capsys.readouterr() == ('', '')


@pytest.mark.parametrize('change', ['single_lf', 'no_lf', 'trailing', 'noise', 'duplicate', 'noncanonical'])
def test_child_stdout_exact_framing(child, change):
    raw = encode(child.envelope)
    if change == 'single_lf': raw = raw[:-1]
    if change == 'no_lf': raw = raw[:-2]
    if change == 'trailing': raw += b'trailing'
    if change == 'noise': raw = b'noise' + raw
    if change == 'duplicate': raw = raw.replace(b'"operation_completed":true', b'"operation_completed":true,"operation_completed":true')
    if change == 'noncanonical': raw = raw.replace(b'"schema":', b'"schema" :', 1)
    child.raw = raw
    with pytest.raises((m.Refused, m.previous.Refused, ValueError)): run_child(child)
    assert child.journal == []


def test_child_exact_640k_stream_bound_accepts(child):
    child.envelope['result']['public_source'] = ''
    child.public_size = m.WORKER_MAX_OUTPUT - len(encode(child.envelope))
    assert child.public_size > 500 * 1024
    result = run_child(child)
    assert len(result['public_source']) == child.public_size and len(child.journal) == 1


@pytest.mark.parametrize('excess', [1, 4096, 65536])
def test_child_640k_plus_any_excess_refuses_and_reaps(child, excess):
    child.envelope['result']['public_source'] = ''
    child.public_size = m.WORKER_MAX_OUTPUT - len(encode(child.envelope)) + excess
    with pytest.raises(m.Refused, match='^child_output$'): run_child(child)
    assert child.journal == [] and child.processes[0].poll() is not None
    assert child.processes[0].stdout.closed and child.processes[0].stderr.closed


def test_child_timeout_kills_only_owned_child_and_reaps(child):
    child.sleep = True
    with pytest.raises(m.Refused, match='^deadline$'): run_child(child, seconds=0.2)
    process = child.processes[0]
    assert process.kills == 1 and process.poll() is not None and 5 in process.waits
    assert child.journal == []


def test_invalid_worker_operation_never_spawns(child):
    with pytest.raises(m.Refused, match='^arguments$'):
        m._child(ARGS, child.store, time.monotonic() + 5, 'recover')
    assert child.seen == []


@pytest.fixture
def public_packet(monkeypatch):
    cloud = public_fixture.cloud.__wrapped__(monkeypatch)
    return {'admission_authenticated': True, 'storage_receipt': m._storage_receipt(),
        'projection_record': cloud.record_bytes.decode('ascii'),
        'source_pairs': [[name, raw.decode('ascii')] for name, raw in cloud.pairs]}


def test_worker_public_packet_real_validation(public_packet):
    record, pairs = m._validate_worker_result(public_packet)
    assert record == public_packet['projection_record'].encode('ascii') and len(pairs) == 11


@pytest.mark.parametrize('change', ['unknown', 'false', 'receipt', 'record_type', 'record_unicode',
    'pairs_tuple', 'missing', 'duplicate', 'pair_tuple', 'source_unicode', 'source_bytes', 'mismatched_source'])
def test_worker_public_packet_rejects_scope_and_code_mismatch(public_packet, change):
    if change == 'unknown': public_packet['private_rows'] = []
    if change == 'false': public_packet['admission_authenticated'] = False
    if change == 'receipt': public_packet['storage_receipt']['actual_storage_exit'] = 2
    if change == 'record_type': public_packet['projection_record'] = b'{}'
    if change == 'record_unicode': public_packet['projection_record'] += '\u2603'
    if change == 'pairs_tuple': public_packet['source_pairs'] = tuple(public_packet['source_pairs'])
    if change == 'missing': public_packet['source_pairs'].pop()
    if change == 'duplicate': public_packet['source_pairs'][-1] = public_packet['source_pairs'][0]
    if change == 'pair_tuple': public_packet['source_pairs'][0] = tuple(public_packet['source_pairs'][0])
    if change == 'source_unicode': public_packet['source_pairs'][0][1] += '\u2603'
    if change == 'source_bytes': public_packet['source_pairs'][0][1] = b'public source'
    if change == 'mismatched_source': public_packet['source_pairs'][0][1] += '# changed\n'
    with pytest.raises((m.Refused, m.remote.Refused, TypeError)):
        m._validate_worker_result(public_packet)


@pytest.fixture
def envelope(monkeypatch):
    # Deep validators are covered by the admission/workflow suite; this fixture
    # isolates exact report pin, false flags, outer actual exit and framing.
    value = {'synthetic_public_result': True, 'response_observation': None, 'access_observation': None}
    monkeypatch.setattr(m, '_validate_result', lambda item: m.require(item == value, 'bound'))
    monkeypatch.setattr(m, '_validate_response', lambda item, **_kw: m.require(item is None, 'bound'))
    monkeypatch.setattr(m, '_validate_access', lambda item, **_kw: m.require(item is None, 'bound'))
    report = m.canonical({**m.binding(ARGS), 'result': value, 'operation_completed': True, **m.FALSE_FLAGS})
    return {'schema': m.SCHEMA, 'operation': 'recover', 'binding': m.binding(ARGS),
        'result': {'report': {'sha256': m.sha(report), 'byte_count': len(report)}, 'result': value},
        'operation_completed': True, **m.FALSE_FLAGS}


def test_parent_exact_exit_and_report_pin(envelope):
    assert m.validate_output(encode(envelope), 0, ARGS) == envelope


@pytest.mark.parametrize('actual', [None, True, False, '0', 1, 2, -9])
def test_parent_success_requires_actual_zero(envelope, actual):
    with pytest.raises(m.Refused): m.validate_output(encode(envelope), actual, ARGS)


@pytest.mark.parametrize('change', ['binding', 'schema', 'operation', 'extra', 'completed', 'flag',
    'hash', 'size', 'bool_size', 'report_extra', 'result_extra'])
def test_parent_exact_envelope_report_and_false_flags(envelope, change):
    if change == 'binding': envelope['binding']['expected_head'] = 'f' * 40
    if change == 'schema': envelope['schema'] = 'old'
    if change == 'operation': envelope['operation'] = OPERATION
    if change == 'extra': envelope['private'] = []
    if change == 'completed': envelope['operation_completed'] = 1
    if change == 'flag': envelope['backtest_created'] = True
    if change == 'hash': envelope['result']['report']['sha256'] = '0' * 64
    if change == 'size': envelope['result']['report']['byte_count'] += 1
    if change == 'bool_size': envelope['result']['report']['byte_count'] = True
    if change == 'report_extra': envelope['result']['report']['extra'] = 0
    if change == 'result_extra': envelope['result']['extra'] = 0
    with pytest.raises(m.Refused): m.validate_output(encode(envelope), 0, ARGS)


@pytest.mark.parametrize('raw', [b'', b'{}', b'{}\n', b'{}\n\nnoise', b'{}\n\n\n', b'x' * (m.MAX_OUTPUT + 1)])
def test_parent_output_framing_and_bound(raw):
    with pytest.raises((m.Refused, m.previous.Refused, ValueError)):
        m.validate_output(raw, 0, ARGS)


def failure():
    return {'schema': m.SCHEMA, 'operation': 'recover', 'binding': m.binding(ARGS),
        'operation_completed': False, 'failure_code': 'source', 'failure_observation': None,
        'attempt_consumption': 'consumed_or_ambiguous_no_retry', **m.FALSE_FLAGS}


def test_finite_failure_output_never_claims_unspent():
    value = failure()
    assert m.validate_output(encode(value), 2, ARGS) == value


@pytest.mark.parametrize('field,value', [('operation_completed', True), ('failure_code', 'raw SECRET'),
    ('failure_observation', 'raw SECRET'), ('attempt_consumption', 'unspent'), ('backtest_created', True),
    ('extra', None)])
def test_failed_envelope_is_finite_and_exact(field, value):
    packet = failure(); packet[field] = value
    with pytest.raises((m.Refused, m.previous.Refused, ValueError, TypeError)):
        m.validate_output(encode(packet), 2, ARGS)


@pytest.fixture
def main_hooks(monkeypatch):
    monkeypatch.setattr(m, '_preflight', lambda *_args: None)
    monkeypatch.setattr(environment, '_bootstrap_cli_logging', lambda: None)
    monkeypatch.setattr(m.helpers, '_alarm', lambda *_args: nullcontext())


def argv(operation='recover'):
    return [operation, '--expected-head', ARGS.expected_head, '--caller-sha256', ARGS.caller_sha256]


def test_main_double_lf_success(envelope, main_hooks, monkeypatch, capsys):
    monkeypatch.setattr(m, '_execute', lambda *_args: envelope['result'])
    assert m.main(argv()) == 0
    out, err = capsys.readouterr()
    assert err == '' and m.validate_output(out.encode('ascii'), 0, ARGS) == envelope


def test_main_unknown_exception_is_not_rendered(main_hooks, monkeypatch, capsys):
    class SecretError(Exception):
        def __str__(self): raise AssertionError('never render secret')
        def __repr__(self): raise AssertionError('never repr secret')
    def fail(*_args): raise SecretError('SECRET')
    monkeypatch.setattr(m, '_execute', fail)
    assert m.main(argv()) == 2
    out, err = capsys.readouterr()
    assert err == '' and 'SECRET' not in out and out.endswith('\n\n')
    assert m.validate_output(out.encode('ascii'), 2, ARGS)['failure_code'] == 'unknown_exception'


@pytest.mark.parametrize('operation,limit', [('recover', m.MAX_OUTPUT), (OPERATION, m.WORKER_MAX_OUTPUT)])
def test_main_stream_budget_counts_final_print_lf(main_hooks, monkeypatch, capsys, operation, limit):
    # Canonical payload exactly at the limit would produce limit+1 stdout bytes.
    args = NS(**{**ARGS.__dict__, 'operation': operation})
    tiny = {'public': ''}
    overhead = len(m.canonical({'schema': m.SCHEMA, 'operation': operation, 'binding': m.binding(args),
        'result': tiny, 'operation_completed': True, **m.FALSE_FLAGS}))
    result = {'public': 'x' * (limit - overhead)}
    monkeypatch.setattr(m, '_execute', lambda *_args: result)
    code = m.main(argv(operation))
    out, err = capsys.readouterr()
    assert code == 2
    assert err == '' and len(out.encode('ascii')) <= limit
    assert m.parse(out.encode('ascii')[:-1])['operation_completed'] is False
