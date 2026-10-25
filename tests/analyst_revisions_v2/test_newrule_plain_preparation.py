"""Offline preparation fixtures; native network/artifact/Keychain denial required."""
import contextlib
import copy
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace as NS

import pytest

from scripts import prepare_arv2_newrule_plain_transport as m
from scripts import arv2_r298_recovery_evidence as evidence
from research.analyst_revisions_v2_qc import newrule_comparison_submission as original
from research.analyst_revisions_v2_qc import newrule_plain_transport as transport
from research.analyst_revisions_v2_qc import newrule_plain_projection as projection


def deny(*_args, **_kwargs):
    raise AssertionError('operational seam reached by synthetic fixture')


@pytest.fixture(autouse=True)
def no_private_inputs_or_contact(monkeypatch):
    monkeypatch.setattr(m.frozen.prepared_input.october, 'load_october_order_input_package', deny)
    monkeypatch.setattr(original, '_input', deny)
    monkeypatch.setattr(original, '_client', deny)
    monkeypatch.setattr(transport, 'build_plain_transport', deny)
    monkeypatch.setattr(transport, '_REQUIRE_SOURCE', deny)
    monkeypatch.setattr(transport, '_ITER_SOURCE', deny)
    monkeypatch.setattr(evidence, 'reconstruct_projection', deny)
    monkeypatch.setattr(projection, 'build_plain_projection', deny)


@pytest.fixture
def args():
    return NS(expected_head='a' * 40, caller_sha256='b' * 64)


@pytest.fixture
def operation(monkeypatch, args):
    state = NS(events=[], values={}, pins={}, fail=None, preflight_count=0)
    plain = NS(package_sha256='1' * 64, activation_manifest_sha256='2' * 64,
        parent_proof_sha256='3' * 64, upload_objects=(None,) * 6, total_upload_byte_count=1234,
        to_record=lambda: {'schema': 'synthetic-transport', 'content': 'metadata only'})
    projected = NS(projection_sha256='4' * 64, profile_bytes=m.canonical({'profile_sha256': '5' * 64}),
        to_record=lambda: {'schema': 'synthetic-projection', 'source_files': []})
    state.plain, state.projected = plain, projected
    def preflight(_args, _deadline):
        assert _args is args
        state.preflight_count += 1
        state.events.append('preflight')
        if state.fail == 'preflight' or (state.fail == 'late_preflight' and state.preflight_count == 2):
            raise m.Refused('source_pin')
    class FakeStore:
        def __init__(self):
            state.events.append('claim-leaf')
            if state.fail == 'claim': raise m.Refused('claim')
        def __enter__(self): state.events.append('enter'); return self
        def __exit__(self, *_): state.events.append('close')
        def write(self, name, value):
            state.events.append(name)
            assert name not in state.values
            if state.fail == name: raise m.Refused('control')
            state.values[name] = copy.deepcopy(value)
            raw = m.canonical(value)
            result = {'sha256': m.sha(raw), 'byte_count': len(raw)}
            state.pins[name] = result
            return result
        def verify(self):
            state.events.append('verify')
            if state.fail == 'verify': raise m.Refused('control_changed')
    def construct(_deadline):
        state.events.append('construct')
        assert state.values['claim.json']['attempt_consumed'] is True
        if state.fail == 'construct': raise transport.PlainTransportError('synthetic private reason')
        return plain, projected
    monkeypatch.setattr(m, 'preflight', preflight)
    monkeypatch.setattr(m, 'Store', FakeStore)
    monkeypatch.setattr(m, 'construct', construct)
    monkeypatch.setattr(m.frozen.helpers, '_alarm', lambda _deadline: contextlib.nullcontext())
    return state


def captured(capsys):
    value = capsys.readouterr()
    assert value.err == ''
    return value.out.encode('ascii')


def envelope(args):
    return {**m.binding(args), 'complete': True, 'failure_code': None,
        'attempt_consumed': True, 'report': {'sha256': 'c' * 64, 'byte_count': 1234},
        'summary': {**{key: 'd' * 64 for key in m.SUMMARY_HASHES}, 'object_count': 6, 'total_byte_count': 1234},
        **dict.fromkeys(m.FALSE_FLAGS, False)}


def output(value):
    return m.canonical(value) + b'\n'


def test_claim_precedes_private_construction_and_success_binds_real_exit(operation, args, capsys):
    actual = m.run(args)
    raw = captured(capsys)
    assert actual == 0
    value = m.validate_output(raw, actual_exit=actual, expected_binding=m.binding(args))
    assert value['complete'] is True and value['summary']['package_sha256'] == operation.plain.package_sha256
    assert value['report'] == operation.pins['report.json']
    assert operation.events == ['preflight', 'claim-leaf', 'enter', 'claim.json', 'construct',
        'report.json', 'preflight', 'verify', 'close']
    assert all(operation.values['report.json'][key] is False for key in m.FALSE_FLAGS)
    assert b'synthetic-transport' not in raw and b'source_files' not in raw


def test_construction_failure_retains_safe_authenticated_report(operation, args, capsys):
    operation.fail = 'construct'
    actual = m.run(args)
    raw = captured(capsys)
    value = m.validate_output(raw, actual_exit=actual, expected_binding=m.binding(args))
    assert actual == 2 and value['complete'] is False and value['summary'] is None
    assert value['failure_code'] == 'plain_refused' and value['attempt_consumed'] is True
    assert b'synthetic private reason' not in raw
    assert set(operation.values['report.json']) == set(m.binding(args)) | {
        'complete', 'failure_code', 'attempt_consumed', *m.FALSE_FLAGS}


@pytest.mark.parametrize('failure', ['preflight', 'claim', 'claim.json', 'report.json', 'late_preflight', 'verify'])
def test_preclaim_and_late_failures_never_become_success(operation, args, capsys, failure):
    operation.fail = failure
    actual = m.run(args)
    raw = captured(capsys)
    assert actual == 2
    value = m.parse(raw[:-1])
    assert value['complete'] is False and value['failure_code'] in m.FAILURES
    assert value['attempt_consumed'] is None and value['stage'] in m.STAGES
    with pytest.raises(m.Refused): m.validate_output(raw, actual_exit=actual, expected_binding=m.binding(args))
    if failure in ('preflight', 'claim', 'claim.json'): assert 'construct' not in operation.events
    if failure in ('late_preflight', 'verify'): assert operation.values['report.json']['complete'] is True


@pytest.mark.parametrize('actual', [None, True, False, -1, 1, 3, '0', 0.0])
def test_actual_exit_requires_exact_supported_integer(args, actual):
    with pytest.raises(m.Refused): m.validate_output(output(envelope(args)), actual_exit=actual, expected_binding=m.binding(args))


def test_success_report_cannot_override_nonzero_actual_exit(args):
    with pytest.raises(m.Refused): m.validate_output(output(envelope(args)), actual_exit=2, expected_binding=m.binding(args))


def test_failure_cannot_claim_zero_actual_exit(args):
    value = envelope(args); value.update(complete=False, failure_code='plain_refused', summary=None)
    with pytest.raises(m.Refused): m.validate_output(output(value), actual_exit=0, expected_binding=m.binding(args))


@pytest.mark.parametrize('change', ['single_lf', 'extra_lf', 'noise', 'noncanonical', 'duplicate', 'huge', 'not_bytes'])
def test_output_framing_and_bound_are_exact(args, change):
    value = envelope(args); raw = output(value)
    if change == 'single_lf': raw = raw[:-1]
    elif change == 'extra_lf': raw += b'\n'
    elif change == 'noise': raw += b'extra'
    elif change == 'noncanonical': raw = b' ' + raw
    elif change == 'duplicate': raw = raw.replace(b'{', b'{"complete":true,', 1)
    elif change == 'huge': raw = b' ' * 4097 + b'\n\n'
    else: raw = raw.decode('ascii')
    with pytest.raises(m.Refused): m.validate_output(raw, actual_exit=0, expected_binding=m.binding(args))


@pytest.mark.parametrize('field', ['schema', 'expected_head', 'caller_sha256', 'profile_sha256'])
def test_output_exact_binding_required(args, field):
    value = envelope(args); value[field] = 'unexpected'
    with pytest.raises(m.Refused): m.validate_output(output(value), actual_exit=0, expected_binding=m.binding(args))


@pytest.mark.parametrize('field', m.FALSE_FLAGS)
@pytest.mark.parametrize('bad', [True, None, 0])
def test_false_authority_flags_are_exact(args, field, bad):
    value = envelope(args); value[field] = bad
    with pytest.raises(m.Refused): m.validate_output(output(value), actual_exit=0, expected_binding=m.binding(args))


@pytest.mark.parametrize('field', m.SUMMARY_HASHES)
def test_summary_hashes_are_validated(args, field):
    value = envelope(args); value['summary'][field] = 'bad'
    with pytest.raises(m.Refused): m.validate_output(output(value), actual_exit=0, expected_binding=m.binding(args))


@pytest.mark.parametrize('field,bad', [('object_count', 5), ('object_count', 97), ('object_count', True),
    ('total_byte_count', 0), ('total_byte_count', 44 * 1024 * 1024 + 1), ('total_byte_count', True)])
def test_summary_aggregate_and_object_bounds(args, field, bad):
    value = envelope(args); value['summary'][field] = bad
    with pytest.raises(m.Refused): m.validate_output(output(value), actual_exit=0, expected_binding=m.binding(args))


@pytest.mark.parametrize('field,bad', [('sha256', None), ('byte_count', 0), ('byte_count', m.MAX_FILE + 1), ('byte_count', True)])
def test_report_pin_is_bounded(args, field, bad):
    value = envelope(args); value['report'][field] = bad
    with pytest.raises(m.Refused): m.validate_output(output(value), actual_exit=0, expected_binding=m.binding(args))


def test_output_rejects_unknown_fields(args):
    for location in ('outer', 'summary', 'report'):
        value = envelope(args); target = value if location == 'outer' else value[location]
        target['secret'] = 'must not be accepted'
        with pytest.raises(m.Refused): m.validate_output(output(value), actual_exit=0, expected_binding=m.binding(args))


@pytest.mark.parametrize('failure', m.FAILURES)
def test_each_finite_failure_validates_with_exit_two(args, failure):
    value = envelope(args); value.update(complete=False, failure_code=failure, summary=None)
    assert m.validate_output(output(value), actual_exit=2, expected_binding=m.binding(args))['failure_code'] == failure


def test_unknown_exception_is_not_stringified():
    class Hostile(Exception):
        def __str__(self): raise AssertionError('stringification')
        def __repr__(self): raise AssertionError('repr')
    assert m.finite(Hostile('private')) == 'unknown_exception'
    assert m.finite(m.Refused('private')) == 'unknown_exception'
    assert m.finite(transport.PlainTransportError('private')) == 'plain_refused'
    assert m.finite(projection.PlainProjectionError('private')) == 'projection_refused'
    assert m.finite(OSError('private')) == 'os_error'


@pytest.fixture
def public_preflight(monkeypatch, args):
    events = []
    pins = {'scripts/synthetic-public-source.py': 'c' * 64}
    monkeypatch.setattr(m, 'selected_pins', lambda: pins)
    monkeypatch.setattr(m.frozen.helpers, '_remaining', lambda _deadline: 10)
    def source(path):
        events.append(('source', path))
        return args.caller_sha256 if path == m.SOURCE else pins[str(path.relative_to(m.ROOT))]
    monkeypatch.setattr(m.frozen.helpers, '_source_digest', source)
    expected = {('rev-parse', '--show-toplevel'): str(m.ROOT), ('branch', '--show-current'): m.frozen.BRANCH,
        ('rev-parse', 'HEAD'): args.expected_head, ('status', '--porcelain'): ''}
    def git(command, **kwargs):
        events.append(('git', command))
        assert kwargs['cwd'] == m.ROOT and kwargs['stdin'] is subprocess.DEVNULL and kwargs['capture_output'] is True
        assert 0 < kwargs['timeout'] <= 3
        return NS(returncode=0, stderr=b'', stdout=(expected[tuple(command[1:])] + '\n').encode('ascii'))
    monkeypatch.setattr(m.subprocess, 'run', git)
    return NS(events=events, pins=pins)


def call_preflight(args, monkeypatch):
    with monkeypatch.context() as scope:
        scope.delitem(sys.modules, 'pytest', raising=False)
        scope.delenv('PYTEST_CURRENT_TEST', raising=False)
        return m.preflight(args, 999999999)


def test_preflight_checks_clean_exact_lane_and_current_sources(public_preflight, args, monkeypatch):
    call_preflight(args, monkeypatch)
    assert [entry[0] for entry in public_preflight.events] == ['git'] * 4 + ['source'] * 2


def test_preflight_refuses_pytest_context(public_preflight, args):
    with pytest.raises(m.Refused, match='preflight'): m.preflight(args, 999999999)
    assert public_preflight.events == []


@pytest.mark.parametrize('bad', ['bad', '', 'A' * 40, None, 7])
def test_preflight_head_format(public_preflight, args, monkeypatch, bad):
    args.expected_head = bad
    with pytest.raises(m.Refused): call_preflight(args, monkeypatch)
    assert public_preflight.events == []


def test_preflight_selected_source_drift(public_preflight, args, monkeypatch):
    monkeypatch.setattr(m.frozen.helpers, '_source_digest', lambda _path: 'd' * 64)
    with pytest.raises(m.Refused, match='source_pin'): call_preflight(args, monkeypatch)


@pytest.mark.parametrize('result', [NS(returncode=1, stderr=b'', stdout=b''),
    NS(returncode=0, stderr=b'warning', stdout=b''), NS(returncode=0, stderr=b'', stdout=b'wrong')])
def test_preflight_git_errors_refuse(public_preflight, args, monkeypatch, result):
    monkeypatch.setattr(m.subprocess, 'run', lambda *_args, **_kwargs: result)
    with pytest.raises(m.Refused, match='git_state'): call_preflight(args, monkeypatch)


def test_preflight_pending_pin_never_authenticates(public_preflight, args, monkeypatch):
    public_preflight.pins['scripts/synthetic-public-source.py'] = 'PENDING'
    with pytest.raises(m.Refused, match='source_pin'): call_preflight(args, monkeypatch)


def test_real_store_claim_is_exclusive_and_holds_named_files(tmp_path, monkeypatch):
    monkeypatch.setattr(m, 'CONTROL', tmp_path / 'controls' / 'one')
    with m.Store() as store:
        first = store.write('claim.json', {'attempt_consumed': True})
        second = store.write('report.json', {'complete': False})
        assert first == {'sha256': m.sha(m.canonical({'attempt_consumed': True})), 'byte_count': 26}
        assert second['byte_count'] > 0
        store.verify()
        with pytest.raises(m.Refused): store.write('claim.json', {'attempt_consumed': True})
    assert set(path.name for path in m.CONTROL.iterdir()) == {'claim.json', 'report.json'}
    with pytest.raises(m.Refused, match='claim'): m.Store()


def test_real_store_retains_failed_claim_without_reallocation(tmp_path, monkeypatch):
    monkeypatch.setattr(m, 'CONTROL', tmp_path / 'controls' / 'one')
    with m.Store() as store:
        with pytest.raises(m.Refused): store.write('unknown.json', {})
    assert m.CONTROL.is_dir()
    with pytest.raises(m.Refused, match='claim'): m.Store()


def test_real_store_rejects_symlink_parent(tmp_path, monkeypatch):
    real = tmp_path / 'real'; real.mkdir()
    link = tmp_path / 'linked'; link.symlink_to(real, target_is_directory=True)
    monkeypatch.setattr(m, 'CONTROL', link / 'controls' / 'one')
    with pytest.raises(OSError): m.Store()


@pytest.mark.parametrize('change', ['bytes', 'mode', 'replacement', 'extra_name'])
def test_real_store_detects_retained_or_named_file_change(tmp_path, monkeypatch, change):
    monkeypatch.setattr(m, 'CONTROL', tmp_path / 'controls' / 'one')
    with m.Store() as store:
        store.write('claim.json', {'attempt_consumed': True})
        target = m.CONTROL / 'claim.json'
        if change == 'bytes':
            with target.open('r+b') as handle: handle.write(b'!')
        elif change == 'mode': target.chmod(0o640)
        elif change == 'replacement':
            target.rename(m.CONTROL / 'retained-original.json')
            target.write_bytes(b'{"attempt_consumed":true}\n')
        else: (m.CONTROL / 'extra').write_bytes(b'synthetic')
        with pytest.raises(m.Refused): store.verify()


def test_real_store_report_bound_refuses_before_file_creation(tmp_path, monkeypatch):
    monkeypatch.setattr(m, 'CONTROL', tmp_path / 'controls' / 'one')
    with m.Store() as store:
        store.write('claim.json', {'attempt_consumed': True})
        monkeypatch.setattr(m, 'MAX_FILE', 8)
        with pytest.raises(m.Refused, match='bound'): store.write('report.json', {'too_large': 'synthetic'})
        assert not (m.CONTROL / 'report.json').exists()


def test_output_validator_has_no_filesystem_consumer(args, monkeypatch):
    raw, expected = output(envelope(args)), m.binding(args)
    with monkeypatch.context() as scope:
        scope.setattr(Path, 'open', deny)
        scope.setattr(m.os, 'open', deny)
        scope.setattr(m.os, 'read', deny)
        assert m.validate_output(raw, actual_exit=0, expected_binding=expected)['complete'] is True


def test_profile_has_no_contact_or_launch_authority():
    value = m.profile()
    assert value['control'] == str(m.CONTROL)
    assert value['max_plain_bytes'] == 44 * 1024 * 1024 and value['attempt_consumed_at_exclusive_claim'] is True
    assert all(value[field] is False for field in m.FALSE_FLAGS)
    assert 'assistant.dispatch_fence' not in sys.modules


def test_construct_calls_exact_old_admission_then_new_conversion(monkeypatch):
    events = []
    authenticated, package, plain, parent, projected = object(), object(), object(), object(), object()
    def load(path, **kwargs):
        events.append('load')
        assert path == m.frozen.PACKAGE and kwargs == {'expected_package_sha256': m.frozen.PACKAGE_SHA256,
            'lineage_path': m.frozen.LINEAGE, 'expected_lineage_sha256': m.frozen.LINEAGE_SHA256}
        return authenticated
    def require(value):
        assert value is authenticated; events.append('input'); return package
    def convert(value, **kwargs):
        assert value is package and kwargs == {'expected_package_sha256': m.frozen.PACKAGE_SHA256,
            'expected_lineage_sha256': m.frozen.LINEAGE_SHA256}
        events.append('convert'); return plain
    def reconstruct(): events.append('parent'); return parent
    def project(old, value, **kwargs):
        assert old is parent and value is plain
        assert set(kwargs['sources']) == {*m.NEW_PINS, 'accepted_risk_six_universe_order_qc_projection.py'}
        assert kwargs['expected_new_source_pins'] == m.NEW_PINS
        assert all(type(raw) is bytes for raw in kwargs['sources'].values())
        events.append('projection'); return projected
    monkeypatch.setattr(m.frozen.prepared_input.october, 'load_october_order_input_package', load)
    monkeypatch.setattr(original, '_input', require)
    monkeypatch.setattr(transport, 'build_plain_transport', convert)
    monkeypatch.setattr(evidence, 'reconstruct_projection', reconstruct)
    monkeypatch.setattr(projection, 'build_plain_projection', project)
    monkeypatch.setattr(m.frozen.helpers, '_remaining', lambda _deadline: events.append('deadline'))
    assert m.construct(123) == (plain, projected)
    assert events == ['load', 'input', 'deadline', 'convert', 'parent', 'projection', 'deadline']


def test_main_parses_only_source_binding_arguments(monkeypatch):
    seen = []
    monkeypatch.setattr(m, 'run', lambda args: seen.append(args) or 2)
    assert m.main(['--expected-head', 'a' * 40, '--caller-sha256', 'b' * 64]) == 2
    assert vars(seen[0]) == {'expected_head': 'a' * 40, 'caller_sha256': 'b' * 64}
