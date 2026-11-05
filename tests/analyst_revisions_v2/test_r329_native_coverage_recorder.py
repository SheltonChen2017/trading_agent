"""Synthetic C result recording only; real artifacts and all network denied."""
import copy
import io
import json
import os
from pathlib import Path
import signal
import sys
import time
from types import SimpleNamespace as NS

import pytest

from scripts import record_arv2_r329_native_coverage_result as m
from tests.analyst_revisions_v2 import test_r329_native_coverage_result as fixture_source

REAL_ROOT = m.ROOT


def example(*, trailing=False, failed=False):
    case = fixture_source.fixture(refused=failed)
    expected = case['expected_run']; expected['compile_id'] = 'abcdef-123456'
    raw = case['statistic_bytes'] + (b' ' if trailing else b'')
    run = {'schema': m.RUN_SCHEMA, 'expected_run': expected, 'UI_build_kind': m.BUILD_KIND,
        'source_readback_method': 'Safari_download11',
        'engine_version': m.ENGINE_VERSION, 'raw_terminal': 'Runtime Error' if failed else 'Completed',
        'statistic_name': m.STATISTIC, 'framing': 'exactly_one_trailing_space' if trailing else 'canonical',
        'raw_statistic_pin': m.pin(raw)}
    return raw, run


def args(run=None):
    if run is None: _, run = example()
    raw = m.canonical(run)
    return NS(expected_head='a' * 40, caller_sha256=m.sha(m.SOURCE.read_bytes()),
        profile_sha256=m.sha(m.canonical(m.profile_record(run))), run_json=raw.decode('ascii'),
        run_sha256=m.sha(raw), worker=False)


def deadline(): return time.monotonic() + m.SECONDS - .01


def refuse(code, action):
    with pytest.raises(m.Refused) as caught: action()
    assert m.finite(caught.value) == code


def test_literal_public_import_closure_matches_selected_source_pins():
    m._dependencies()
    assert len(m.selected_plan()) == 26
    assert all(m.sha((REAL_ROOT / path).read_bytes()) == expected for path, expected in m.selected_plan().items())
    assert len(m.BOOTSTRAP_METADATA) == 26
    assert m.STAGE_SHA256 == '652a46b6b0db83f50cf042e1b374b9beed3192d897e5886557e48cf25a75193e'
    assert m.PARSER_SHA256 == 'daaac5778c4f6c2a98996c6a061c5051b07207939f83df110a3fe74898c923ea'


@pytest.mark.parametrize('trailing', (False, True))
def test_explicit_framing_preserves_raw_and_body_pins_with_UI_translation(trailing):
    raw, run = example(trailing=trailing)
    value = m.interpret(raw, run)
    assert value['raw_statistic_pin'] == m.pin(raw)
    assert value['body_pin'] == m.pin(raw[:-1] if trailing else raw)
    assert value['raw_UI_terminal'] == 'Completed' and value['normalized_terminal'] == 'Completed.'
    assert value['UI_build_kind'] == m.BUILD_KIND
    assert value['literal_UI_status_translation_not_API_observation'] is True
    assert value['selected']['classification'] == 'diagnostic_complete_with_gaps'
    assert value['selected']['strategy_result_accepted'] is False


def test_genuine_finite_failed_terminal_is_retained_as_failed_diagnostic():
    raw, run = example(failed=True)
    value = m.interpret(raw, run)
    assert value['normalized_terminal'] == 'Runtime Error.'
    assert value['selected']['diagnostic_complete'] is False


def test_API_readback_method_remains_external_metadata_not_Safari_claim():
    raw, run = example(); run['source_readback_method'] = 'named_API_read11'
    assert m.interpret(raw, run)['source_readback_method'] == 'named_API_read11'
    run['source_readback_method'] = 'arbitrary_unrecorded_read'
    refuse('run', lambda: m.validate_run(run))


@pytest.mark.parametrize('change', ('leading', 'two_trailing', 'newline', 'tabs', 'wrong_mode', 'empty', 'overbound', 'pin'))
def test_no_generic_strip_repair_or_second_framing_trial(change):
    raw, run = example(trailing=True)
    if change == 'leading': raw = b' ' + raw
    elif change == 'two_trailing': raw += b' '
    elif change == 'newline': raw = raw[:-1] + b'\n'
    elif change == 'tabs': raw = raw[:-1] + b'\t'
    elif change == 'wrong_mode': run['framing'] = 'canonical'
    elif change == 'empty': raw = b''
    elif change == 'overbound': raw = b' ' * 8004
    elif change == 'pin': run['raw_statistic_pin']['sha256'] = 'f' * 64
    if change not in ('pin', 'empty', 'overbound'): run['raw_statistic_pin'] = m.pin(raw)
    with pytest.raises((m.Refused, m.result_parser.Refused)):
        m.interpret(raw, run)


@pytest.mark.parametrize('change', ('extra', 'missing', 'name', 'version', 'kind', 'terminal', 'framing', 'statistic',
    'project_bool', 'compile_shape', 'job', 'readback_size', 'raw_pin_bool'))
def test_run_binding_is_closed_and_externally_exact(change):
    _, run = example()
    if change == 'extra': run['grant'] = True
    elif change == 'missing': del run['engine_version']
    elif change == 'name': run['expected_run']['name'] = 'secret\n'
    elif change == 'version': run['engine_version'] = 'changed'
    elif change == 'kind': run['UI_build_kind'] = 'REST_compileId'
    elif change == 'terminal': run['raw_terminal'] = 'Completed.'
    elif change == 'framing': run['framing'] = 'strip'
    elif change == 'statistic': run['statistic_name'] = 'wrong'
    elif change == 'project_bool': run['expected_run']['project_id'] = True
    elif change == 'compile_shape': run['expected_run']['compile_id'] = 'unknown'
    elif change == 'job': run['expected_run']['backtest_id'] = 'A' * 32
    elif change == 'readback_size': run['expected_run']['source_readback_pin']['byte_count'] = False
    elif change == 'raw_pin_bool': run['raw_statistic_pin']['byte_count'] = True
    refuse('run', lambda: m.validate_run(run))


def test_profile_preserves_scope_and_explicit_deadline_exclusions():
    _, run = example(); value = m.profile_record(run)
    assert all(value[key] is False for key in m.FALSE_FLAGS)
    assert 'bootstrap_import_preflight' in value['parent_deadline_scope']
    assert 'parent_argument_source_validation' in value['parent_exclusions']
    policy = m.native_profile()
    assert policy.startswith('(version 1)(allow default)(deny network*)')
    assert '(deny process-exec (literal "/usr/bin/security"))' in policy and '[.]pyc$' in policy
    assert str(m.CONTROL) in policy and '/Downloads' not in policy
    assert 'R329-20261028-A' not in policy and 'R329-20261028-B' not in policy


def test_bounded_input_rejects_invalid_types_empty_and_overflow():
    for raw in (b'', b'x' * 8004): refuse('raw_bound', lambda: m._read_input(io.BytesIO(raw)))
    assert m._read_input(io.BytesIO(b'abc')) == b'abc'


def test_wrong_fixed_source_binding_fails_profile_before_claim():
    _, run = example(); run['expected_run']['source_projection_pin']['sha256'] = 'f' * 64
    with pytest.raises(m.result_parser.Refused): m.profile_record(run)


def test_fresh_worker_rejects_preloaded_repository_module_before_read(monkeypatch):
    monkeypatch.setattr(m, 'stage', None)
    monkeypatch.setattr(m, '__name__', '__main__')
    monkeypatch.setattr(m, '_public_source', lambda *_: (_ for _ in ()).throw(AssertionError('read before preloaded check')))
    refuse('source_pin', m._dependencies)


def test_child_alarm_expires_and_restores_prior_handler():
    old = signal.getsignal(signal.SIGALRM)
    with pytest.raises(m.Refused) as caught:
        with m.alarm(time.monotonic() + .01):
            time.sleep(.1)
    assert m.finite(caught.value) == 'deadline'
    assert signal.getsignal(signal.SIGALRM) == old and signal.getitimer(signal.ITIMER_REAL) == (0., 0.)


@pytest.fixture
def store_root(tmp_path, monkeypatch):
    m._dependencies()
    root = tmp_path / 'root'; (root / 'artifacts' / 'analyst_revisions_v2').mkdir(parents=True)
    control = root / 'artifacts' / 'analyst_revisions_v2' / 'result' / 'R329-C'
    monkeypatch.setattr(m.stage, 'ROOT', root)
    monkeypatch.setattr(m, 'CONTROL', control)
    return control


def test_original_FDs_exact_bytes_security_and_no_reuse(store_root):
    raw, run = example()
    with m.Store() as store:
        store.write('claim.json', b'{}', deadline())
        store.write('selected.raw', raw, deadline())
        assert os.pread(store.files['selected.raw']['fd'], len(raw) + 1, 0) == raw
        assert store.files['selected.raw']['metadata'] == m.stage.named(store.fd, 'selected.raw')
        store.verify()
        refuse('output_bound', lambda: store.write('selected.raw', raw, deadline()))
    assert sorted(path.name for path in store_root.iterdir()) == ['claim.json', 'selected.raw']
    with pytest.raises(m.stage.Refused) as caught: m.Store()
    assert m.stage.finite(caught.value) == 'claim_spent'


@pytest.mark.parametrize('change', ('chmod', 'replace', 'append', 'extra', 'hardlink'))
def test_own_output_metadata_and_name_drift_refuse(store_root, change):
    with pytest.raises((m.Refused, m.stage.Refused)):
        with m.Store() as store:
            store.write('claim.json', b'{}', deadline())
            target = store_root / 'claim.json'
            if change == 'chmod': target.chmod(0o644)
            elif change == 'replace': target.rename(store_root / 'renamed'); target.write_bytes(b'{}')
            elif change == 'append':
                with target.open('ab') as output: output.write(b' ')
            elif change == 'extra': (store_root / 'extra').write_bytes(b'x')
            else: os.link(target, store_root / 'link')
            store.verify()


class FakeSources:
    def __init__(self, plan, deadline):
        self.files = {name: {'metadata': m.BOOTSTRAP_METADATA.get(name, (1,) * 10)} for name in plan}
        self.verifies = 0
    def verify(self): self.verifies += 1
    def __enter__(self): return self
    def __exit__(self, *_): return None


@pytest.fixture
def produced(store_root, monkeypatch):
    raw, run = example(trailing=True); arguments = args(run)
    monkeypatch.setattr(m, 'preflight', lambda *args: None)
    monkeypatch.setattr(m.stage, 'PublicSources', FakeSources)
    value = m.produce(arguments, raw, deadline())
    return NS(raw=raw, run=run, args=arguments, value=value, control=store_root)


def test_record_success_preserves_original_transport_and_report_with_strict_pins(produced):
    value = produced.value
    assert sorted(path.name for path in produced.control.iterdir()) == ['claim.json', 'report.json', 'selected.raw']
    assert (produced.control / 'selected.raw').read_bytes() == produced.raw
    assert value['outcome']['report_pin'] == m.pin((produced.control / 'report.json').read_bytes())
    assert m.validate_child(m.canonical(value) + b'\n', 0, produced.args) == value
    assert all(value['outcome']['result'][key] is False for key in m.FALSE_FLAGS)


@pytest.mark.parametrize('actual_exit', (None, False, True, -1, 1, 2, 77))
def test_late_child_failure_cannot_accept_report_alone(produced, actual_exit):
    refuse('output', lambda: m.validate_child(m.canonical(produced.value) + b'\n', actual_exit, produced.args))


@pytest.mark.parametrize('change', ('reportpin', 'bodypin', 'rawpin', 'rawterminal', 'sourcepin', 'readbackpin', 'grant', 'metadata', 'binding', 'extra', 'trailing'))
def test_closed_output_revalidates_source_framing_semantics_and_false_flags(produced, change):
    value = copy.deepcopy(produced.value); result = value['outcome']['result']
    if change == 'reportpin': value['outcome']['report_pin']['sha256'] = 'f' * 64
    elif change == 'bodypin': result['interpretation']['body_pin']['sha256'] = 'f' * 64
    elif change == 'rawpin': result['interpretation']['raw_statistic_pin']['byte_count'] += 1
    elif change == 'rawterminal': result['interpretation']['raw_UI_terminal'] = 'Completed.'
    elif change == 'sourcepin': result['selected_public_sources_sha256'] = 'f' * 64
    elif change == 'readbackpin': result['run_binding']['expected_run']['source_readback_pin']['sha256'] = 'f' * 64
    elif change == 'grant': result['strategy_result_accepted'] = True
    elif change == 'metadata': result['input_endpoint_metadata_sha256'] = 'unknown'
    elif change == 'binding': value['binding']['expected_head'] = 'b' * 40
    elif change == 'extra': result['raw_error'] = 'secret'
    raw = m.canonical(value) + b'\n'
    if change == 'trailing': raw += b' '
    refuse('output', lambda: m.validate_child(raw, 0, produced.args))


def test_bad_raw_is_retained_as_consumed_finite_failure(store_root, monkeypatch):
    _, run = example(); arguments = args(run); raw = b'{"wrong":1}'
    monkeypatch.setattr(m, 'preflight', lambda *args: None)
    monkeypatch.setattr(m.stage, 'PublicSources', FakeSources)
    value = m.produce(arguments, raw, deadline())
    assert value['outcome']['failure']['failure_code'] == 'raw_pin'
    assert value['outcome']['failure']['claim_consumed'] is True
    assert (store_root / 'selected.raw').read_bytes() == raw
    assert (store_root / 'failure.json').is_file() and not (store_root / 'report.json').exists()
    m.validate_child(m.canonical(value) + b'\n', 2, arguments)


def test_preflight_failure_precedes_any_control_allocation(monkeypatch):
    raw, run = example(); arguments = args(run)
    monkeypatch.setattr(m, 'preflight', lambda *_: (_ for _ in ()).throw(m.Refused('profile')))
    monkeypatch.setattr(m, 'Store', lambda: (_ for _ in ()).throw(AssertionError('claim allocated')))
    refuse('profile', lambda: m.produce(arguments, raw, deadline()))


@pytest.mark.parametrize('change', ('valid', 'root', 'branch', 'head', 'dirty', 'blob', 'profile', 'environment', 'host'))
def test_preflight_binds_clean_host_public_source_and_profile_before_claim(monkeypatch, change):
    arguments = args(); raw_source = m.SOURCE.read_bytes()
    monkeypatch.setattr(m.os, 'environ', synthetic_env(REAL_ROOT / '.pytest_cache' / 'r329-native-recorder' / 'tmp'))
    def git(command, limit):
        if command[:2] == ['cat-file', 'blob']: return b'changed' if change == 'blob' else raw_source
        if command == ['rev-parse', '--show-toplevel']: return (str(REAL_ROOT) if change != 'root' else '/wrong').encode()
        if command == ['branch', '--show-current']: return (m.BRANCH if change != 'branch' else 'main').encode()
        if command == ['rev-parse', 'HEAD']: return (arguments.expected_head if change != 'head' else 'b' * 40).encode()
        assert command == ['status', '--porcelain']
        return b'M scripts/changed.py' if change == 'dirty' else b''
    monkeypatch.setattr(m.stage, '_git', git)
    if change == 'profile': arguments.profile_sha256 = 'b' * 64
    if change == 'environment': monkeypatch.setenv('UNEXPECTED_CREDENTIAL', 'synthetic-only')
    if change == 'host': monkeypatch.setattr(m.sys, 'executable', '/wrong/python')
    if change == 'valid': m.preflight(arguments, deadline())
    else:
        expected = 'git_state' if change in ('root', 'branch', 'head', 'dirty') else 'profile' if change in ('blob', 'profile') else change
        refuse(expected, lambda: m.preflight(arguments, deadline()))


def synthetic_env(tmp_path):
    return {'PATH': '/usr/bin:/bin', 'TMPDIR': str(tmp_path), 'PYTHONPYCACHEPREFIX': str(tmp_path / 'pycache'),
        'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'LC_ALL': 'C'}


def test_real_synthetic_child_bounded_stdin_and_output(tmp_path):
    code = 'import sys; r=sys.stdin.buffer.read(); assert r==b"abc"; sys.stdout.write(\'{"binding":{},"outcome":{}}\\n\')'
    value = m.collect([m.PYTHON, '-B', '-c', code], synthetic_env(tmp_path), b'abc')
    assert value['collector_status'] == 'returned' and value['actual_child_exit'] == 0
    assert value['stdin_byte_count'] == 3 and value['child_output_accepted'] is False


def test_finite_startup_failure_is_retained_but_never_success_or_retry(tmp_path):
    code = 'import sys; sys.stdin.buffer.read(); sys.stdout.write(\'{"attempt_reusable":false,"failure_code":"source_pin"}\\n\'); sys.exit(2)'
    value = m.collect([m.PYTHON, '-B', '-c', code], synthetic_env(tmp_path), b'abc')
    assert value['collector_status'] == 'returned' and value['actual_child_exit'] == 2
    arguments = args()
    child = m.canonical(value['child_envelope']) + b'\n'
    assert m.validate_child(child, 2, arguments) == {'failure_code': 'source_pin', 'attempt_reusable': False}
    refuse('output', lambda: m.validate_child(child, 0, arguments))


@pytest.mark.parametrize('kind', ('noise', 'bound', 'deadline', 'malformed'))
def test_real_synthetic_child_noise_bound_deadline_and_malformed_are_terminal(tmp_path, kind):
    body = {'noise': 'sys.stderr.write("private text must not escape")',
        'bound': 'sys.stdout.write("x"*33000)', 'deadline': 'import time; time.sleep(5)',
        'malformed': 'sys.stdout.write("not-json")'}[kind]
    code = 'import sys; sys.stdin.buffer.read(); ' + body
    value = m.collect([m.PYTHON, '-B', '-c', code], synthetic_env(tmp_path), b'abc', seconds=.1 if kind == 'deadline' else 5)
    assert value['collector_status'] == {'noise': 'stderr', 'bound': 'stdout_bound', 'deadline': 'deadline', 'malformed': 'malformed_output'}[kind]
    assert value['child_envelope'] is None and value['attempt_reusable'] is False
    assert 'private text' not in m.canonical(value).decode()


def test_parent_exit_and_child_bytes_are_both_mandatory(produced):
    child = m.canonical(produced.value) + b'\n'
    outer = {'schema': m.OUTER_SCHEMA, 'collector_status': 'returned', 'actual_child_exit': 0,
        'stdin_byte_count': len(produced.raw), 'stdout_pin': m.pin(child), 'stderr_seen': False,
        'child_envelope': produced.value, 'child_output_accepted': False, 'attempt_reusable': False}
    raw = m.canonical(outer) + b'\n'
    assert m.validate_output(raw, 0, produced.args) == produced.value
    for code in (None, False, True, 2): refuse('output', lambda: m.validate_output(raw, code, produced.args))
    outer['stdout_pin']['sha256'] = 'f' * 64
    refuse('output', lambda: m.validate_output(m.canonical(outer) + b'\n', 0, produced.args))


def test_finite_arguments_do_not_echo_raw_cli_content(capsys):
    assert m.main(['--unknown', 'private-value']) == 2
    output = capsys.readouterr()
    assert 'private-value' not in output.out + output.err
    assert not output.err and json.loads(output.out)['failure_code'] == 'arguments'


def validation_argv(arguments, *extra):
    values = []
    for key in ('expected_head', 'caller_sha256', 'profile_sha256', 'run_json', 'run_sha256'):
        values.extend(('--' + key.replace('_', '-'), getattr(arguments, key)))
    return values + list(extra)


def parent_envelope(produced):
    child = m.canonical(produced.value) + b'\n'
    return {'schema': m.OUTER_SCHEMA, 'collector_status': 'returned', 'actual_child_exit': 0,
        'stdin_byte_count': len(produced.raw), 'stdout_pin': m.pin(child), 'stderr_seen': False,
        'child_envelope': produced.value, 'child_output_accepted': False, 'attempt_reusable': False}


@pytest.mark.parametrize('change', ('valid', 'actual_exit', 'raw_pin', 'overflow'))
def test_offline_validation_CLI_binds_observed_exit_and_bytes_without_claim_or_child(produced, monkeypatch, capsys, change):
    envelope = parent_envelope(produced)
    if change == 'raw_pin': envelope['stdout_pin']['sha256'] = 'f' * 64
    raw = m.canonical(envelope) + b'\n'
    if change == 'overflow': raw = b'x' * (m.MAX_OUTPUT_BYTES + 2049)
    monkeypatch.setattr(m.os, 'environ', synthetic_env(REAL_ROOT / '.pytest_cache' / 'r329-native-recorder' / 'tmp'))
    monkeypatch.setattr(m.sys, 'stdin', NS(buffer=io.BytesIO(raw)))
    def forbidden(*_args, **_kwargs): raise AssertionError('operational allocation or child')
    monkeypatch.setattr(m, 'Store', forbidden)
    monkeypatch.setattr(m, 'produce', forbidden)
    monkeypatch.setattr(m, 'collect', forbidden)
    original = m.validate_output; calls = []
    def once(*values):
        calls.append(values)
        return original(*values)
    monkeypatch.setattr(m, 'validate_output', once)
    code = m.main(validation_argv(produced.args, '--validate-output', '--actual-parent-exit', '2' if change == 'actual_exit' else '0'))
    output = capsys.readouterr(); value = json.loads(output.out)
    assert not output.err
    assert len(calls) == (0 if change == 'overflow' else 1)
    if change == 'valid':
        assert code == 0 and value['schema'] == m.VALIDATION_SCHEMA
        assert value['output_authenticated'] is True and value['recording_success'] is True
        assert value['diagnostic_status'] == 'diagnostic_complete_with_gaps'
        assert value['diagnostic_complete'] is True
        assert value['report_pin'] == produced.value['outcome']['report_pin']
        assert value['raw_statistic_pin'] == m.pin(produced.raw)
        assert value['persisted_output_reopened'] is False and value['control_claimed'] is False
        assert all(value[key] is False for key in m.FALSE_FLAGS)
        assert 'summary' not in value and 'raw_statistic' not in value
    else:
        assert code == 2 and value['attempt_reusable'] is False
        assert value['failure_code'] == ('raw_bound' if change == 'overflow' else 'output')


@pytest.mark.parametrize('flags', (
    ('--validate-output',), ('--actual-parent-exit', '0'),
    ('--worker', '--validate-output', '--actual-parent-exit', '0'),
    ('--worker', '--actual-parent-exit', '0'), ('--validate-output', '--actual-parent-exit', 'private-value'),
))
def test_validation_CLI_mode_and_external_exit_are_explicit_without_error_echo(capsys, flags):
    code = m.main(validation_argv(args(), *flags))
    output = capsys.readouterr()
    assert code == 2 and not output.err and 'private-value' not in output.out
    assert json.loads(output.out) == {'failure_code': 'arguments', 'attempt_reusable': False}


def test_validated_unbound_startup_failure_never_claims_run_output_authentication(produced):
    value = parent_envelope(produced)
    value['actual_child_exit'] = 2
    value['child_envelope'] = {'failure_code': 'source_pin', 'attempt_reusable': False}
    value['stdout_pin'] = m.pin(m.canonical(value['child_envelope']) + b'\n')
    produced.args.actual_parent_exit = 0
    checked = m.validate_supplied_output(produced.args, m.canonical(value) + b'\n', deadline())
    assert checked['supplied_envelope_validated'] is True
    assert checked['output_authenticated'] is False and checked['recording_success'] is False
    assert checked['diagnostic_status'] == 'recorder_failed' and checked['diagnostic_complete'] is False
    assert checked['failure_code'] == 'source_pin' and checked['report_pin'] is None
