"""Synthetic V5 caller tests: no operational source/path/credential access."""
import hashlib
import json
import sys
import time
from contextlib import contextmanager
from types import ModuleType, SimpleNamespace

import pytest

from scripts import run_arv2_newrule_recovery_continuation_v5 as d
from scripts import arv2_newrule_execution_environment as environment
from scripts import arv2_newrule_recovery_continuation_v5 as continuation
from scripts import arv2_newrule_recovery_continuation_v4 as legacy
from research.analyst_revisions_v2_qc import newrule_comparison_submission as submission

BODY = b'synthetic-caller-source'
SHA, HEAD = hashlib.sha256(BODY).hexdigest(), 'a' * 40
REAL_OPERATION = d._operation
REAL_GIT = d._git


def args(operation='capacity', **changes):
    values = dict(operation=operation, expected_head=HEAD, caller_sha256=SHA,
        receipt_sha256=d.ADMISSION_SHA256, candidate=None, attempt=None,
        prior_failure_sha256=None, justification_sha256=None)
    if type(operation) is str and operation in ('begin','compile','launch','status','read'):
        values.update(candidate='R298', attempt=1)
    values.update(changes)
    return SimpleNamespace(**values)


@pytest.fixture(autouse=True)
def no_operations(monkeypatch):
    hits = []
    def forbidden(label):
        def stop(*_a, **_k):
            hits.append(label)
            pytest.fail('forbidden production seam: ' + label)
        return stop
    for obj, names in ((d.helpers, ('_source_digest',)),
        (d.frozen.prepared_input.october, ('load_october_order_input_package',)),
        (submission, ('load_family','_Directory','_client','capacity_once','begin_attempt',
            'poll_compile_once','launch_compiled','poll_status_once','read_result_once','summarize_family')),
        (legacy, ('dispatch','capacity_once','begin_attempt')),
        (continuation, ('dispatch',)), (d.frozen, ('_operation',)),
        (d, ('_operation','_git')),
        (environment, ('guarded_client','_bootstrap_cli_logging'))):
        for name in names:
            monkeypatch.setattr(obj, name, forbidden(name))
    yield
    assert hits == [], 'a product BaseException handler swallowed a test tripwire'


def fixtures(monkeypatch, *, bad_source=None, bad_git=None):
    reads, git, events = [], [], []
    monkeypatch.setattr(d, '_under_test', lambda: False)
    pins = {name: d.frozen.SOURCE_PINS.get(name, 'd' * 64) for name in d.NEW_PINS}
    monkeypatch.setattr(d, 'NEW_PINS', pins)
    monkeypatch.setattr(environment, '_require_environment', lambda: events.append('environment'))
    monkeypatch.setattr(environment, 'require_safe_environment', lambda: events.append('safe'))
    answers = {('rev-parse','--show-toplevel'): str(d.ROOT),
        ('branch','--show-current'): d.frozen.BRANCH, ('rev-parse','HEAD'): HEAD,
        ('status','--porcelain'): ''}
    def fake_git(command, _deadline, limit=65536):
        git.append(command)
        events.append('git')
        if tuple(command[:2]) == ('cat-file','-s'):
            return str(len(BODY)).encode() + b'\n'
        if tuple(command[:2]) == ('cat-file','blob'):
            return b'bad' if bad_git == 'blob' else BODY
        value = answers[tuple(command)]
        if tuple(command) == bad_git:
            value = 'mismatch'
        return value.encode() + (b'\n' if value else b'')
    monkeypatch.setattr(d, '_git', fake_git)
    def digest(path):
        name = path.relative_to(d.ROOT).as_posix()
        reads.append(name)
        events.append('source')
        if name == bad_source: return 'e' * 64
        if path == d.SOURCE: return SHA
        if path == d.frozen.SOURCE: return d.FROZEN_CALLER_SHA256
        if name in pins: return pins[name]
        return d.frozen.SOURCE_PINS[name]
    monkeypatch.setattr(d.helpers, '_source_digest', digest)
    return reads, git, events


def test_profile_is_separate_fixed_admission_and_false_readiness():
    profile = d.profile_record()
    assert profile['schema'].endswith('-v5')
    assert profile['admission_sha256'] == '1a6850a8fbefeeab8dea2fead19b3b5f656ca29987da9ef180be1e7cc59322a3'
    assert profile['executable_attempts'] == [1]
    assert profile['actual_recovery_exit_zero_required_externally'] is True
    assert profile['no_legacy_public_lifecycle_dispatch'] is True
    assert profile['occupied_capacity_state'] == 'wait_no_automatic_advance'
    assert profile['new_pins']['data/exchange_calendar.py'] == '174a032efce4082b8661eabe84b0cf6094048e937722bdf1659c8cb6c7decb89'
    assert profile['new_pins']['research/analyst_revisions_v2_qc/accepted_risk_preliminary_rating_evaluator.py'] == '2fb9bc8a8f74e37b57acb97f4d20b5820be04b9ee470fc2f34b3a8ea2c804910'
    assert all(profile[key] is False for key in ('point_in_time_proven','formal_forward_ready','paper_or_live_ready'))


@pytest.mark.parametrize('operation', d.OPERATIONS)
def test_source_environment_and_clean_blob_gates(monkeypatch, capsys, operation):
    reads, git, events = fixtures(monkeypatch)
    def operation_stub(value, _deadline):
        assert value.operation == operation and len(git) == 8
        assert set(reads) == set(d.NEW_PINS) | set(d.frozen.SOURCE_PINS) | {
            d.SOURCE.relative_to(d.ROOT).as_posix(), d.frozen.SOURCE.relative_to(d.ROOT).as_posix()}
        assert events.index('environment') < events.index('git')
        assert events[-1] == 'safe'
        return {'state': 'wait', 'synthetic': True}
    monkeypatch.setattr(d, '_operation', operation_stub)
    assert d.run(args(operation)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['result']['state'] == 'wait' and result['operation_completed'] is True


@pytest.mark.parametrize('bad', [('rev-parse','--show-toplevel'), ('branch','--show-current'),
    ('rev-parse','HEAD'), ('status','--porcelain'), 'blob'])
def test_host_git_or_own_blob_refusal(monkeypatch, capsys, bad):
    fixtures(monkeypatch, bad_git=bad)
    assert d.run(args()) == 2
    assert json.loads(capsys.readouterr().out)['stage'] == 'preflight'


@pytest.mark.parametrize('name', list(d.NEW_PINS) + list(d.frozen.SOURCE_PINS))
def test_every_selected_source_pin_refuses(monkeypatch, capsys, name):
    fixtures(monkeypatch, bad_source=name)
    assert d.run(args()) == 2
    assert json.loads(capsys.readouterr().out)['operation_completed'] is False


def test_early_environment_refusal_precedes_git(monkeypatch, capsys):
    reads, git, _ = fixtures(monkeypatch)
    monkeypatch.setattr(d, '_operation', lambda *_: {'synthetic': True})
    def stop(): raise environment.EnvironmentRefused('opaque-secret')
    monkeypatch.setattr(environment, '_require_environment', stop)
    assert d.run(args()) == 2
    text = capsys.readouterr().out
    assert 'opaque' not in text and git == []
    assert reads == ['scripts/arv2_newrule_execution_environment.py']
    assert json.loads(text)['failure_code'] == 'execution_environment_refused'


@pytest.mark.parametrize('changes', [dict(receipt_sha256='f'*64), dict(attempt=2),
    dict(attempt=True), dict(candidate='other'), dict(prior_failure_sha256='f'*64),
    dict(justification_sha256='f'*64), dict(expected_head='bad'), dict(caller_sha256='bad')])
def test_admission_attempt_and_arguments_refuse(monkeypatch, capsys, changes):
    fixtures(monkeypatch)
    assert d.run(args('begin', **changes)) == 2
    assert json.loads(capsys.readouterr().out)['operation_completed'] is False


@pytest.mark.parametrize('operation', [None, [], {}, 1, False, 'unknown'])
def test_malformed_operation_finite(monkeypatch, capsys, operation):
    fixtures(monkeypatch)
    assert d.run(args(operation)) == 2
    assert json.loads(capsys.readouterr().out)['operation'] == 'unknown'


def test_pytest_operational_refusal_precedes_any_source(monkeypatch, capsys):
    assert d.run(args()) == 2
    assert json.loads(capsys.readouterr().out)['stage'] == 'preflight'


def test_git_children_never_receive_qc_credentials(monkeypatch, tmp_path):
    monkeypatch.setattr(d, 'os', SimpleNamespace(environ={'PATH': environment.PATH,
        'LANG':'C', 'TMPDIR':str(tmp_path), 'PYTHONPYCACHEPREFIX':str(tmp_path),
        'QC_USER_ID':'synthetic-user','QC_API_TOKEN':'synthetic-token'}))
    def child(command, **kwargs):
        assert command == ['git','rev-parse','HEAD']
        assert kwargs['cwd'] == d.ROOT and kwargs['timeout'] <= 3
        assert not {'QC_USER_ID','QC_API_TOKEN'} & kwargs['env'].keys()
        assert kwargs['env']['PATH'] == environment.PATH
        return SimpleNamespace(returncode=0, stdout=b'answer', stderr=b'')
    monkeypatch.setattr(d.frozen.subprocess, 'run', child)
    assert REAL_GIT(['rev-parse','HEAD'],time.monotonic()+3) == b'answer'


@pytest.mark.parametrize('operation', ['capacity','begin','compile','launch','status','summarize'])
def test_actual_operation_composes_new_dispatch_only(monkeypatch, operation):
    events = []
    monkeypatch.setattr(d,'_preflight',lambda *_: events.append('preflight'))
    monkeypatch.setattr(environment,'require_safe_environment',lambda: events.append('safe'))
    def load(*_a, **_k):
        assert events[-1] == 'safe'
        events.append('input')
        return 'synthetic-input'
    monkeypatch.setattr(d.frozen.prepared_input.october,'load_october_order_input_package',load)
    def family(value, **kwargs):
        assert value == 'synthetic-input' and events[-1] == 'safe'
        assert kwargs['expected_family_sha256'] == d.FAMILY_SHA256
        events.append('family')
        return 'synthetic-plan'
    monkeypatch.setattr(submission,'load_family',family)
    def dispatch(op, plan, candidate, attempt, **kwargs):
        assert op == operation and plan == 'synthetic-plan' and events[-1] == 'safe'
        assert set(kwargs) == {'expected_family_sha256','expected_receipt_sha256'}
        assert kwargs['expected_receipt_sha256'] == d.ADMISSION_SHA256
        events.append('dispatch')
        return {'state':'wait'}
    monkeypatch.setattr(continuation,'dispatch',dispatch)
    assert REAL_OPERATION(args(operation),time.monotonic()+10) == {'state':'wait'}
    assert events == ['preflight','safe','input','safe','family','safe','dispatch']


def test_read_returns_only_bounded_public_result_summary(monkeypatch):
    monkeypatch.setattr(d,'_preflight',lambda *_: None)
    monkeypatch.setattr(environment,'require_safe_environment',lambda: None)
    monkeypatch.setattr(d.frozen.prepared_input.october,'load_october_order_input_package',lambda *_a, **_k: object())
    monkeypatch.setattr(submission,'load_family',lambda *_a, **_k: object())
    result = {key: 'synthetic' for key in ('family_sha256','candidate_id','attempt_id',
        'project_id','backtest_id','status','cell_completed','family_comparable','result_cell')}
    meta = {key: 0 for key in ('account_aggregates','common_source_path_sha256','decision_count',
        'evaluation_session_count','order_count','fill_count','coverage_fallback_counts')}
    result['statistics'] = {'meta': meta, 'excluded_synthetic_payload': 'not-printed'}
    monkeypatch.setattr(continuation,'dispatch',lambda *_a, **_k: result)
    output = REAL_OPERATION(args('read'),time.monotonic()+10)
    assert 'statistics' not in output and 'excluded_synthetic_payload' not in output
    assert output['statistics_sha256'] == hashlib.sha256(d.helpers.canonical_json_bytes(result['statistics'])).hexdigest()
    assert output['order_count'] == 0


def test_cli_bootstrap_and_run_share_deadline(monkeypatch):
    values = []
    monkeypatch.setattr(d,'_source_preflight',lambda _,deadline: values.append(('preflight',deadline)))
    monkeypatch.setattr(environment,'_bootstrap_cli_logging',lambda: values.append(('bootstrap',None)))
    def execute(value, deadline, started):
        assert deadline == values[0][1] and type(started) is str
        values.append(('run',deadline))
        return 0
    monkeypatch.setattr(d,'_run',execute)
    assert d.main(['capacity','--expected-head',HEAD,'--caller-sha256',SHA,
        '--receipt-sha256',d.ADMISSION_SHA256]) == 0
    assert [item[0] for item in values] == ['preflight','bootstrap','run']


def test_cli_source_refusal_never_bootstraps(monkeypatch, capsys):
    def stop(*_a): raise d.frozen.OperationRefusal('opaque')
    monkeypatch.setattr(d,'_source_preflight',stop)
    assert d.main(['capacity','--expected-head',HEAD,'--caller-sha256',SHA,
        '--receipt-sha256',d.ADMISSION_SHA256]) == 2
    assert 'opaque' not in capsys.readouterr().out


def test_library_run_never_bootstraps(monkeypatch, capsys):
    fixtures(monkeypatch)
    monkeypatch.setattr(d,'_operation',lambda *_: {'synthetic': True})
    assert d.run(args()) == 0
    assert json.loads(capsys.readouterr().out)['operation_completed'] is True


def test_partial_module_cannot_break_finite_failure(monkeypatch):
    monkeypatch.setitem(sys.modules,'scripts.arv2_newrule_recovery_continuation_v5',
        ModuleType('scripts.arv2_newrule_recovery_continuation_v5'))
    assert d._failure(ValueError('opaque'),None,None) == 'value_error'


def test_oversize_operation_output_is_finite_failure(monkeypatch, capsys):
    fixtures(monkeypatch)
    monkeypatch.setattr(d,'_operation',lambda *_: {'opaque': 'x'*d.MAX_OUTPUT_BYTES})
    assert d.run(args()) == 2
    text = capsys.readouterr().out
    assert len(text) < 2048 and 'xxxxx' not in text


def test_deadline_is_not_swallowed_as_success(monkeypatch, capsys):
    fixtures(monkeypatch)
    def stop(*_a): raise d.helpers.Deadline()
    monkeypatch.setattr(d,'_operation',stop)
    assert d.run(args()) == 2
    assert json.loads(capsys.readouterr().out)['failure_code'] == 'deadline'
