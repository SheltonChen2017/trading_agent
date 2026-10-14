"""Synthetic runner composition; no private input, credential or remote use."""
from contextlib import contextmanager
import json
import sys
from types import SimpleNamespace as NS

import pytest

import scripts
from scripts import arv2_newrule_storage_recovery_v2 as real_recovery
from scripts import run_arv2_newrule_storage_recovery_v2 as m
REAL_DIRECTORY = real_recovery.old._Directory


class SyntheticRecoveryError(ValueError):
    pass


@pytest.fixture(autouse=True)
def operational_guards(monkeypatch):
    violations = []
    def forbidden(*args, **kwargs):
        violations.append('operational')
        pytest.fail('operational seam forbidden in caller tests')
    for obj, names in (
        (real_recovery, ('claim', 'recover')),
        (real_recovery.old, ('_Directory', '_client', '_session', 'load_family', 'prepare_family')),
        (m.frozen.prepared_input.october, ('load_october_order_input_package',)),
    ):
        for name in names:
            monkeypatch.setattr(obj, name, forbidden)
    for name in ('__init__', 'verify', 'names', 'read', 'write'):
        monkeypatch.setattr(REAL_DIRECTORY, name, forbidden)
    yield violations
    assert not violations, 'caught operational seam must not masquerade as expected exit 2'


@pytest.fixture
def setup(monkeypatch):
    assert 'assistant.dispatch_fence' not in sys.modules
    calls = []
    args = NS(expected_head='a' * 40, caller_sha256='b' * 64)
    module = NS(claim=lambda *a: calls.append('claim'),
        recover=lambda *a: calls.append('recover') or
            {'complete': True, 'receipt_sha256': 'c' * 64, 'receipt_bytes': 100,
             'report_sha256': 'd' * 64, 'report_bytes': 200, 'failure_code': None,
             'attempted_request_count': 0, 'requests': []},
        FINITE_FAILURE_CODES=frozenset({'service_refused'}),
        StorageRecoveryError=SyntheticRecoveryError,
        finite_failure=lambda error: 'helper_git_binding')
    monkeypatch.setitem(sys.modules, 'scripts.arv2_newrule_storage_recovery_v2', module)
    monkeypatch.setattr(scripts, 'arv2_newrule_storage_recovery_v2', module)
    monkeypatch.setattr(m, '_preflight', lambda *a: calls.append('preflight'))
    monkeypatch.setattr(m, '_load_plan', lambda: calls.append('load') or object())
    return args, module, calls


def test_success_order_and_external_pin_output(setup, capsys):
    args, _, calls = setup
    assert m.run(args) == 0
    value = json.loads(capsys.readouterr().out)
    assert calls == ['preflight', 'claim', 'load', 'recover']
    assert value['operation_completed'] is True
    assert value['result']['receipt_sha256'] == 'c' * 64
    assert value['original_upload_accepted'] is False
    assert value['formal_forward_ready'] is value['point_in_time_proven'] is value['paper_or_live_ready'] is False


def test_missing_import_mock_hits_guard_before_real_directory(setup, monkeypatch, capsys, operational_guards):
    args, _, calls = setup
    monkeypatch.setattr(scripts, 'arv2_newrule_storage_recovery_v2', real_recovery)
    assert m.run(args) == 2
    assert calls == ['preflight']
    assert json.loads(capsys.readouterr().out)['failure_code'] == 'unknown_exception'
    assert operational_guards == ['operational']
    operational_guards.clear()  # this test explicitly expects and checks that guard


def test_negative_recovery_has_actual_exit_two(setup, capsys):
    args, module, _ = setup
    module.recover = lambda *a: {'complete': False, 'report_sha256': 'd' * 64, 'report_bytes': 200,
        'failure_code': 'service_refused', 'attempted_request_count': 0, 'requests': []}
    assert m.run(args) == 2
    assert json.loads(capsys.readouterr().out)['operation_completed'] is False


def test_verified_helper_preclaim_refusal_retains_finite_reason(setup, capsys):
    args, module, calls = setup
    def refuse(*a):
        raise SyntheticRecoveryError('NEVER-PRINT')
    module.claim = refuse
    assert m.run(args) == 2
    raw = capsys.readouterr().out
    assert 'NEVER-PRINT' not in raw
    assert json.loads(raw)['failure_code'] == 'helper_git_binding'
    assert calls == ['preflight']


@pytest.mark.parametrize('stage', ['preflight', 'claim', 'load', 'recover'])
def test_failures_never_continue_or_expose_error(setup, monkeypatch, capsys, stage):
    args, module, calls = setup
    def fail(*_):
        calls.append(stage)
        raise ValueError('SECRET-NOT-TO-PRINT')
    if stage == 'preflight':
        monkeypatch.setattr(m, '_preflight', fail)
    elif stage == 'load':
        monkeypatch.setattr(m, '_load_plan', fail)
    else:
        setattr(module, stage, fail)
    assert m.run(args) == 2
    raw = capsys.readouterr().out
    assert 'SECRET' not in raw
    assert calls == ['preflight', 'claim', 'load', 'recover'][:['preflight', 'claim', 'load', 'recover'].index(stage) + 1]


def test_claim_collision_stops_before_private_load(setup, capsys):
    args, module, calls = setup
    def collision(*_):
        raise FileExistsError('secret-path')
    module.claim = collision
    assert m.run(args) == 2
    value = json.loads(capsys.readouterr().out)
    assert calls == ['preflight']
    assert value['failure_code'] == 'claim_collision'
    assert value['attempt_consumption'] == 'consumed_or_ambiguous'


@pytest.mark.parametrize('complete', [0, 1, None, 'true', [], {}])
def test_boolean_alias_result_refuses(setup, capsys, complete):
    args, module, _ = setup
    module.recover = lambda *a: {'complete': complete}
    assert m.run(args) == 2
    assert json.loads(capsys.readouterr().out)['failure_code'] == 'operation_refused'


def test_output_bound_refuses(setup, monkeypatch, capsys):
    args, _, _ = setup
    monkeypatch.setattr(m, 'MAX_OUTPUT_BYTES', 1)
    assert m.run(args) == 2
    assert 'receipt_sha256' not in capsys.readouterr().out


def test_alarm_bounds_entire_operation(setup, monkeypatch, capsys):
    args, _, calls = setup
    @contextmanager
    def alarm(deadline):
        assert deadline > m.time.monotonic()
        calls.append('alarm_enter')
        try:
            yield
        finally:
            calls.append('alarm_exit')
    monkeypatch.setattr(m.helpers, '_alarm', alarm)
    assert m.run(args) == 0
    assert calls == ['alarm_enter', 'preflight', 'claim', 'load', 'recover', 'alarm_exit']
    capsys.readouterr()


def test_preflight_checks_new_source_before_import(monkeypatch):
    calls = []
    monkeypatch.setattr(m.frozen, '_preflight', lambda args, deadline: calls.append(args))
    monkeypatch.setattr(m, 'RECOVERY_SHA256', 'c' * 64)
    monkeypatch.setattr(m.helpers, '_source_digest', lambda path: 'b' * 64 if path == m.SOURCE
        else 'c' * 64 if path == m.RECOVERY_SOURCE else m.DIAGNOSTIC_PINS[str(path.relative_to(m.ROOT))])
    m._preflight(NS(expected_head='a' * 40, caller_sha256='b' * 64), m.time.monotonic() + 5)
    assert calls[0].operation == 'summarize'
    assert calls[0].caller_sha256 == m.FROZEN_CALLER_SHA256
    monkeypatch.setattr(m.helpers, '_source_digest', lambda path: 'b' * 64)
    with pytest.raises(m.RecoveryOperationRefusal):
        m._preflight(NS(expected_head='a' * 40, caller_sha256='b' * 64), m.time.monotonic() + 5)


def test_public_profile_retains_pins_and_no_launch():
    value = m.profile_record()
    assert value['source_pins'] == dict(m.frozen.SOURCE_PINS)
    assert value['strategy_launch'] is value['original_upload_accepted'] is False
    assert value['deadline_seconds'] == 500


@pytest.mark.parametrize('relative', list(m.DIAGNOSTIC_PINS))
def test_diagnostic_pin_mismatch_prevents_import_claim_and_private_load(monkeypatch, capsys, relative):
    import builtins
    original_import = builtins.__import__
    imports = []
    def guarded_import(name, *args, **kwargs):
        if name == 'scripts' and 'arv2_newrule_storage_recovery_v2' in (args[2] if len(args) > 2 else kwargs.get('fromlist', ())):
            imports.append(name)
            raise AssertionError('recovery must not import')
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded_import)
    monkeypatch.setattr(m.frozen, '_preflight', lambda *a: None)
    monkeypatch.setattr(m, 'RECOVERY_SHA256', 'c' * 64)
    def digest(path):
        if path == m.ROOT / relative:
            return 'e' * 64
        if path == m.SOURCE:
            return 'b' * 64
        if path == m.RECOVERY_SOURCE:
            return 'c' * 64
        return m.DIAGNOSTIC_PINS[str(path.relative_to(m.ROOT))]
    monkeypatch.setattr(m.helpers, '_source_digest', digest)
    monkeypatch.setattr(m, '_load_plan', lambda: pytest.fail('private input must not load'))
    assert m.run(NS(expected_head='a' * 40, caller_sha256='b' * 64)) == 2
    value = json.loads(capsys.readouterr().out)
    assert value['stage'] == 'preflight' and imports == []


@pytest.mark.parametrize('digest', ['e' * 64, True, 'SECRET', None])
def test_trace_request_digest_is_strict_and_safe(setup, capsys, digest):
    args, module, _ = setup
    value = module.recover()
    value['attempted_request_count'] = 1
    value['requests'] = [{'ordinal': 0, 'endpoint': 'object/list', 'index': None,
        'request_sha256': digest, 'attempted': True, 'http_status': 200,
        'response_schema_valid': True, 'api_success': True, 'error_category': 'unknown'}]
    module.recover = lambda *a: value
    assert m.run(args) == (0 if digest == 'e' * 64 else 2)
    assert 'SECRET' not in capsys.readouterr().out


def test_failure_does_not_render_hostile_exception():
    class Hostile(Exception):
        def __str__(self):
            raise AssertionError('must not render')
    assert m._failure(Hostile()) == 'unknown_exception'


@pytest.mark.parametrize('change', [
    {'raw_error': 'NEVER-PRINT'}, {'failure_code': 'NEVER-PRINT'},
    {'report_bytes': True}, {'receipt_sha256': 'NEVER-PRINT'},
    {'attempted_request_count': True}, {'attempted_request_count': 1},
    {'requests': [{'opaque': 'NEVER-PRINT'}]},
])
def test_result_unknown_fields_and_shapes_refuse(setup, capsys, change):
    args, module, _ = setup
    result = module.recover()
    module.recover = lambda *a: dict(result, **change)
    assert m.run(args) == 2
    assert 'NEVER-PRINT' not in capsys.readouterr().out
