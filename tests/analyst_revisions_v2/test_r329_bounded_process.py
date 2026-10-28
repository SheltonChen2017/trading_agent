import json
import sys

import pytest

from scripts import arv2_r329_bounded_process as process


def execute(source, *, seconds=5, maximum=65536):
    return process.collect([sys.executable, '-B', '-c', source],
        {'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1'},
        seconds=seconds, maximum=maximum)


def test_child_failure_exit_is_retained_not_success():
    value = execute('import sys; print(\'{"failure_code":"source_pin"}\'); sys.exit(2)')
    assert value['collector_status'] == 'returned'
    assert value['actual_child_exit'] == 2
    assert value['child_envelope'] == {'failure_code': 'source_pin'}
    assert value['child_output_accepted'] is False
    assert value['attempt_reusable'] is False


def test_normal_zero_still_requires_separate_validator():
    value = execute('print(\'{"binding":{},"outcome":{}}\')')
    assert value['collector_status'] == 'returned'
    assert value['actual_child_exit'] == 0
    assert value['child_envelope'] == {'binding': {}, 'outcome': {}}
    assert value['child_output_accepted'] is False


def test_oversized_stdout_is_bounded_and_child_reaped():
    value = execute('import sys,time; sys.stdout.write("X"*100000); sys.stdout.flush(); time.sleep(30)', maximum=1024)
    assert value['collector_status'] == 'stdout_bound'
    assert value['stdout_byte_count'] <= 1024
    assert type(value['actual_child_exit']) is int
    assert value['child_envelope'] is None


def test_stderr_is_never_forwarded():
    value = execute('import sys,time; sys.stderr.write("SECRET");sys.stderr.flush();time.sleep(30)')
    assert value['collector_status'] == 'stderr'
    assert value['stderr_seen'] is True
    assert value['child_envelope'] is None
    assert b'SECRET' not in process.canonical(value)


def test_deadline_kills_and_reaps_only_own_child():
    value = execute('import time;time.sleep(30)', seconds=0.1)
    assert value['collector_status'] == 'deadline'
    assert type(value['actual_child_exit']) is int
    assert value['child_envelope'] is None


@pytest.mark.parametrize('text', ['{"failure_code":"x"}\nextra',
    '{"failure_code":"x","failure_code":"y"}', '{"failure_code":NaN}',
    '{"opaque":"SECRET"}', '{ "failure_code": "x" }'])
def test_malformed_or_unexpected_output_is_not_forwarded(text):
    value = execute('print(' + repr(text) + ')')
    assert value['collector_status'] == 'malformed_output'
    assert value['child_envelope'] is None


def test_arbitrary_program_is_rejected():
    spec = {'schema': process.SCHEMA, 'operation': 'arbitrary', 'expected_head': 'a'*40,
        'caller_sha256': 'a'*64, 'profile_sha256': 'b'*64,
        'native_policy': 'x', 'native_policy_sha256': 'c'*64, 'extra_args': []}
    with pytest.raises(process.Refused):
        process.command(spec)


def test_exact_child_command_and_no_extra_stage_flags():
    policy = '(version 1)(allow default)(deny network*)(deny process-exec (literal "/usr/bin/security"))'
    spec = {'schema': process.SCHEMA, 'operation': 'stage', 'expected_head': 'a'*40,
        'caller_sha256': 'a'*64, 'profile_sha256': 'b'*64, 'native_policy': policy,
        'native_policy_sha256': process.sha(policy.encode()), 'extra_args': []}
    command = process.command(spec)
    assert command[:5] == ['/usr/bin/sandbox-exec', '-p', policy, process.PYTHON, '-B']
    assert command[5] == str(process.ROOT / 'scripts' / process.CALLERS['stage'])
    spec['extra_args'] = ['--retry']
    with pytest.raises(process.Refused):
        process.command(spec)


def test_spec_parser_rejects_duplicates_and_trailing():
    for raw in (b'{"a":1,"a":2}', b'{"a":1}\n', b'{"a":NaN}', b'{}extra'):
        with pytest.raises(process.Refused):
            process.parse(raw)


def test_external_spec_hash_checked_before_dispatch(monkeypatch):
    monkeypatch.setattr(process, 'collect', lambda *a, **kw: pytest.fail('dispatch'))
    with pytest.raises(process.Refused):
        process.run({}, '0'*64)


def test_cli_unknown_argument_is_finite_without_echo(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['collector', '--spec-json', '{}', '--spec-sha256',
        '0'*64, '--SECRET'])
    assert process.main() == 2
    captured = capsys.readouterr()
    assert captured.err == ''
    assert captured.out == '{"failure_code":"outer_binding","attempt_reusable":false}\n'


@pytest.mark.parametrize('flags', [process.STAGE_FALSE, process.READBACK_FALSE])
def test_exact_finite_preflight_failure_preserved_with_false_flags(flags):
    value = {'binding': {}, 'failure_code': 'git_state', 'claim_consumed': False,
        'allocation_unknown': True, **{key: False for key in flags}}
    text = process.canonical(value).decode()
    result = execute('import sys; print(' + repr(text) + '); sys.exit(2)')
    assert result['collector_status'] == 'returned'
    assert result['actual_child_exit'] == 2
    assert result['child_envelope'] == value
