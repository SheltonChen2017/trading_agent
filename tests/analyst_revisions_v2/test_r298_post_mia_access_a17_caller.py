"""Synthetic two-request reconciliation; native denial is supplied by runner."""
import ast
import copy
import re
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace as NS

import pytest

from scripts import observe_arv2_r298_post_mia_access_a17 as m
from scripts import observe_arv2_r298_post_mia_access as frozen
from scripts import arv2_r298_collaborator_access as access


@pytest.fixture(autouse=True)
def prevent_old_operational_fallback(monkeypatch):
    def fail(*_, **__): raise AssertionError('old operational fallback')
    for module, names in ((frozen, ('main', 'run', 'observe')),
        (m.a17, ('main', 'run', 'observe', 'worker', 'run_worker')),
        (m.prior, ('main', 'run', 'observe', 'worker', 'run_worker')),
        (m.prior.admitted, ('main', '_execute', '_recover', '_worker', 'authenticate_storage')),
        (m.prior.admission, ('admit',)), (m.prior.admitted.prep, ('main', 'construct'))):
        for name in names: monkeypatch.setattr(module, name, fail)


@pytest.fixture
def args():
    return NS(expected_head='a' * 40, caller_sha256='b' * 64, actual_exit=None)


@pytest.fixture
def control(tmp_path, monkeypatch):
    parent = tmp_path / 'parent'; parent.mkdir(mode=0o700)
    target = parent / 'new-control'
    monkeypatch.setattr(m, 'CONTROL', target)
    return target


@pytest.fixture
def seams(monkeypatch):
    order = []
    class API:
        def request(self, endpoint, payload):
            order.append((endpoint, payload))
            return {'success': True, 'synthetic_endpoint': endpoint}
    observation = {'access_failure_code': None, 'synthetic_observation': True}
    fake = NS(observe=lambda *args: copy.deepcopy(observation), validate_observation=lambda value: value,
              FINITE=frozenset())
    monkeypatch.setattr(m, 'helper', lambda: fake)
    monkeypatch.setattr(m, '_client', lambda: order.append('client') or API())
    monkeypatch.setattr(m, 'credential_shape', lambda: {'synthetic': True})
    monkeypatch.setattr(m, 'preflight', lambda *_: order.append('postflight'))
    monkeypatch.setattr(m.environment, 'require_safe_environment', lambda: None)
    monkeypatch.setattr(access, 'verify_access', lambda *args: {'matched': True})
    return NS(order=order, observation=observation, fake=fake)


def output(args, code=None):
    result = {'terminal': 'observed', 'application_dispatch_count': 2,
        'access_failure_code': code, 'observation': {'access_failure_code': code}, **m.FALSE_FLAGS}
    raw = m.canonical({**m.binding(args), 'result': result})
    return {'binding': m.binding(args), 'outcome': {'result': result,
        'report': {'byte_count': len(raw), 'sha256': m.sha(raw)}}}


def test_new_read_only_protocol_exact_endpoints_and_old_frozen_utility_reuse():
    assert m.ENDPOINTS == ('projects/read', 'projects/collaboration/read')
    assert m.CONTROL.name == 'R323-20261025-H' and m.CONTROL != m.prior.CONTROL
    assert m.capture is m.prior.capture and m.credential_shape is m.prior.credential_shape
    profile = m.profile_record()
    assert profile['max_application_dispatches'] == 2 and profile['deadline_seconds'] == 120
    assert all(profile[key] == 0 for key in ('lock_changes', 'uploads', 'capacity_calls', 'compiles', 'backtests'))
    assert profile['old_control_reads'] is False and 'assistant.dispatch_fence' not in sys.modules
    assert m.SCHEMA == 'arv2-r298-post-a17-mia-access-v1' and m.CONTROL != frozen.CONTROL
    assert profile['a17_spent'] is True and profile['a17_actual_exit'] == 2 and profile['a17_control_read'] is False
    assert profile['a17_parent_stdout_bytes'] == 755
    assert profile['a17_parent_stdout_sha256'] == 'fbcb3c200ee9acac2bd4549e714ab60b5c181f0750c0495a65231cb66ea7710c'
    assert profile['a17_failure_code'] == 'access_general_collaborators' and profile['a17_failure_stage'] == 'prepare'
    assert profile['a17_application_dispatch_count'] == profile['a17_returned_response_count'] == 2
    assert profile['a17_source_writes'] == profile['a17_compiles'] == profile['a17_jobs'] == 0
    assert profile['historical_a17_cause_authenticated'] is profile['access_policy_changed'] is False
    assert profile['ui_context_documentary_only'] is profile['ui_context_not_api_identity_or_access_authority'] is True
    assert profile['ui_remove_Mia_outcome'] == 'collaboration_not_found'
    assert profile['ui_request_edit_control_outcome'] == 'you_have_edit_permission'
    assert profile['ui_three_avatars_remained'] is True


def test_selected_public_dependency_pins_include_final_a17_and_pure_redactor():
    assert m.NEW_PINS['scripts/run_arv2_r298_raw_reference_diagnostic.py'] == '1f2f88de601312c1e5ee16381a64fdd091ada2ea7ab2a0709a991bbc6b6d71ff'
    values = m.pins()
    assert len(values) >= 117 and set(m.a17.pins()) <= set(values)
    for name, pin in values.items():
        assert type(pin) is str and re.fullmatch('[0-9a-f]{64}', pin) and pin != '0' * 64
        assert m.sha(m.ROOT.joinpath(name).read_bytes()) == pin
    assert m.sha(frozen.SOURCE.read_bytes()) == '11958e8387755871b78f7ee0f24d7f286811974a89350e19402e260debdf9b08'
    assert m.NEW_PINS['scripts/arv2_r298_post_mia_access.py'] == '09705275244935bce92c096e18d3beaaedd3eed13ab31deb8ef8788fb9df8672'


def test_entire_observation_lifecycle_matches_frozen_C_except_runtime_temp_identity():
    names = {'remaining', 'helper', 'finite', '_finite_code', 'binding', 'preflight', 'Store', '_client',
        'run', 'validate_result', 'validate_output', 'observe', 'main'}
    def selected(raw, newer=False):
        tree = ast.parse(raw)
        if newer:
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and node.value == 'r323-post-a17-mia-':
                    node.value = 'r323-post-mia-'
        return {node.name: ast.dump(node, include_attributes=False) for node in tree.body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names}
    before, after = selected(frozen.SOURCE.read_bytes()), selected(m.SOURCE.read_bytes(), True)
    assert set(before) == names and before == after


def test_store_exact_exclusive_claim_and_pin(control):
    with m.Store() as store:
        value = {'read_only': True}
        assert store.write('claim.json', value) == {'byte_count': len(m.canonical(value)), 'sha256': m.sha(m.canonical(value))}
        assert (control / 'claim.json').read_bytes() == m.canonical(value)
        assert (control / 'claim.json').stat().st_mode & 0o777 == 0o600
        with pytest.raises(m.Refused): store.write('claim.json', value)
    with pytest.raises(m.Refused): m.Store()


@pytest.mark.parametrize('name', ['../bad.json', '/tmp/a.json', 'bad_name.json', 'report.txt', 'a.json/x'])
def test_store_no_path_escape(control, name):
    with m.Store() as store:
        with pytest.raises(m.Refused): store.write(name, {})


@pytest.mark.parametrize('change', ['mode', 'new', 'replacement', 'inplace'])
def test_store_held_named_metadata_and_census(control, change):
    with m.Store() as store:
        store.write('claim.json', {'test': 1}); target = control / 'claim.json'
        if change == 'mode': target.chmod(0o640)
        elif change == 'new': (control / 'new.json').write_bytes(b'{}\n')
        elif change == 'replacement': target.unlink(); target.write_bytes(b'{}\n'); target.chmod(0o600)
        else: target.write_bytes(target.read_bytes())
        with pytest.raises(m.Refused): store.verify()


def test_claim_and_fsync_precede_client_and_exact_two_calls(control, seams, args, monkeypatch):
    original = m.Store.write
    def write(self, name, value):
        pin = original(self, name, value); seams.order.append(name); return pin
    monkeypatch.setattr(m.Store, 'write', write)
    outcome = m.run(args, time.monotonic() + 30)
    assert seams.order.index('claim.json') < seams.order.index('client')
    assert [item for item in seams.order if type(item) is tuple] == [
        ('projects/read', {'projectId': 38364439}), ('projects/collaboration/read', {'projectId': 38364439})]
    assert outcome['result']['access_failure_code'] is None
    assert all(outcome['result'][key] is False for key in m.FALSE_FLAGS)
    assert len(list(control.iterdir())) == 6
    assert b'synthetic_endpoint' not in b''.join(path.read_bytes() for path in control.iterdir())
    assert m.validate_output(m.canonical({'binding': m.binding(args), 'outcome': outcome}), 0, args)


@pytest.mark.parametrize('code', sorted(access.FINITE_CODES))
def test_all_exact_foreign_access_predicates_retained_after_two_successful_rpcs(control, seams, args, monkeypatch, code):
    seams.observation['access_failure_code'] = code
    def refuse(*_): raise access.AccessRefused(code)
    monkeypatch.setattr(access, 'verify_access', refuse)
    outcome = m.run(args, time.monotonic() + 30)
    assert outcome['result']['access_failure_code'] == code
    assert outcome['result']['application_dispatch_count'] == 2
    assert all(outcome['result'][key] is False for key in m.FALSE_FLAGS)
    assert m.validate_output(m.canonical({'binding': m.binding(args), 'outcome': outcome}), 0, args)


@pytest.mark.parametrize('which', [0, 1])
def test_rpc_exception_distinguishes_intent_from_successful_response(control, seams, args, monkeypatch, which):
    calls = []
    class API:
        def request(self, endpoint, payload):
            calls.append(endpoint)
            if len(calls) == which + 1: raise RuntimeError('PRIVATE RAW MESSAGE MUST NOT LEAK')
            return {'success': True}
    monkeypatch.setattr(m, '_client', API)
    outcome = m.run(args, time.monotonic() + 30)
    failed = outcome['failure']; state = failed['state']
    assert state['application_dispatch_count'] == which + 1 and state['response_count'] == which
    assert state['last_endpoint'] == m.ENDPOINTS[which] and state['last_response_received'] is False
    assert failed['failure_code'] == 'unknown_exception'
    assert b'PRIVATE' not in m.canonical(outcome)
    assert m.validate_output(m.canonical({'binding': m.binding(args), 'outcome': outcome}), 2, args)


def test_foreign_scope_refusal_is_safe_failed_observation(control, seams, args, monkeypatch):
    def refuse(*_): raise m.Refused('request_scope')
    seams.fake.observe = refuse
    outcome = m.run(args, time.monotonic() + 30)
    assert outcome['failure']['failure_code'] == 'request_scope'
    assert outcome['failure']['state']['stage'] == 'projection'
    assert outcome['failure']['state']['response_count'] == 2


def test_report_publication_failure_is_exit2_not_observation_success(control, seams, args, monkeypatch):
    write = m.Store.write
    def refuse_report(self, name, value):
        if name == 'report.json': raise OSError('PRIVATE DISK MESSAGE')
        return write(self, name, value)
    monkeypatch.setattr(m.Store, 'write', refuse_report)
    outcome = m.run(args, time.monotonic() + 30)
    assert set(outcome) == {'failure'} and outcome['failure']['failure_code'] == 'os_error'
    assert outcome['failure']['state']['stage'] == 'report'
    raw = m.canonical({'binding': m.binding(args), 'outcome': outcome})
    assert m.validate_output(raw, 2, args)
    with pytest.raises(m.Refused): m.validate_output(raw, 0, args)


@pytest.mark.parametrize('bad', ['stage', 'countbool', 'responses', 'endpoint', 'received', 'extra', 'raw-code'])
def test_failure_state_closed_and_request_response_accounting(args, seams, bad):
    state = {'stage': 'collaboration', 'application_dispatch_count': 2,
        'response_count': 1, 'last_endpoint': m.ENDPOINTS[1], 'last_response_received': False}
    failed = {'failure_code': 'unknown_exception', 'state': state,
        'attempt_consumption': 'consumed_or_ambiguous_no_retry', **m.FALSE_FLAGS}
    if bad == 'stage': state['stage'] = 'compile'
    elif bad == 'countbool': state['application_dispatch_count'] = True
    elif bad == 'responses': state['response_count'] = 2
    elif bad == 'endpoint': state['last_endpoint'] = 'files/update'
    elif bad == 'received': state['last_response_received'] = 1
    elif bad == 'extra': state['raw_response'] = {}
    else: failed['failure_code'] = 'private_message'
    value = {'binding': m.binding(args), 'outcome': {'failure': failed}}
    with pytest.raises(m.Refused): m.validate_output(m.canonical(value), 2, args)


def test_classification_never_stringifies_foreign_or_hostile_errors():
    class Hostile(access.AccessRefused):
        def __str__(self): raise AssertionError('stringified')
    class Value:
        def __str__(self): raise AssertionError('stringified')
    assert m.finite(Hostile('owner')) == 'unknown_exception'
    assert m.finite(access.AccessRefused(Value())) == 'access_unknown'
    assert m.finite(access.AccessRefused('owner', 'private')) == 'access_unknown'
    assert m.finite(access.AccessRefused('PRIVATE RAW')) == 'access_unknown'
    assert m.finite(access.AccessRefused('owner')) == 'access_owner'


def test_qc_client_exception_is_exact_class_category_not_message():
    from research import quantconnect as qc
    class Child(qc.QuantConnectError): pass
    assert m.finite(qc.QuantConnectError('PRIVATE HTTP ERROR')) == 'qc_client_refused'
    assert m.finite(qc.QuantConnectNotConfigured('PRIVATE TOKEN')) == 'qc_not_configured'
    assert m.finite(Child('PRIVATE HTTP ERROR')) == 'unknown_exception'


@pytest.mark.parametrize('mia', [False, True])
def test_real_helper_projection_report_and_two_fixed_api_calls(control, args, monkeypatch, mia):
    from tests.analyst_revisions_v2 import test_post_mia_access as fixtures
    supplied = fixtures.supplied.__wrapped__(monkeypatch)
    if mia:
        supplied.project['projects'][0]['collaborators'].append(
            {'name': 'Mia', 'owner': False, 'uid': None, 'private': 'PRIVATE ROW'})
    class API:
        def request(self, endpoint, payload):
            assert payload == {'projectId': 38364439}
            return copy.deepcopy(supplied.project if endpoint == m.ENDPOINTS[0] else supplied.dedicated)
    monkeypatch.setattr(m, '_client', API)
    monkeypatch.setattr(m, 'credential_shape', lambda: {})
    monkeypatch.setattr(m.environment, 'require_safe_environment', lambda: None)
    monkeypatch.setattr(m, 'preflight', lambda *_: None)
    outcome = m.run(args, time.monotonic() + 30)
    assert outcome['result']['access_failure_code'] == ('general_collaborators' if mia else None)
    value = m.validate_output(m.canonical({'binding': m.binding(args), 'outcome': outcome}), 0, args)
    observation = value['outcome']['result']['observation']
    assert observation['general']['count'] == (3 if mia else 2)
    assert observation['dedicated']['count'] == 1
    assert b'PRIVATE' not in m.canonical(outcome) and b'SYNTHETIC' not in m.canonical(outcome)
    if mia: assert observation['general']['rows'][-1]['identifier_matches']['name']['is_mia'] is True


def test_owner_A5_Mia_shaped_third_row_is_redacted_and_never_policy_accepted(control, args, monkeypatch):
    from tests.analyst_revisions_v2 import test_post_mia_access as fixtures
    supplied = fixtures.supplied.__wrapped__(monkeypatch)
    supplied.project['projects'][0]['collaborators'].append(
        {'name': 'Mia', 'owner': False, 'uid': None, 'publicId': 'mia-ai', 'private': 'PRIVATE METADATA'})
    class API:
        def request(self, endpoint, payload):
            assert payload == {'projectId': 38364439}
            return copy.deepcopy(supplied.project if endpoint == m.ENDPOINTS[0] else supplied.dedicated)
    monkeypatch.setattr(m, '_client', API)
    monkeypatch.setattr(m, 'credential_shape', lambda: {})
    monkeypatch.setattr(m.environment, 'require_safe_environment', lambda: None)
    monkeypatch.setattr(m, 'preflight', lambda *_: None)
    outcome = m.run(args, time.monotonic() + 30)
    result = outcome['result']
    assert result['access_failure_code'] == 'general_collaborators'
    assert result['observation']['general']['count'] == 3 and result['observation']['dedicated']['count'] == 1
    extra = result['observation']['general']['rows'][-1]
    assert extra['field_types']['uid'] == 'null' and extra['uid_matches_project_owner'] is False
    assert extra['identifier_matches']['publicId']['is_mia_ai'] is True
    assert all(result[key] is False for key in m.FALSE_FLAGS)
    assert b'PRIVATE METADATA' not in m.canonical(result) and b'mia-ai' not in m.canonical(result)
    assert m.validate_output(m.canonical({'binding': m.binding(args), 'outcome': outcome}), 0, args)


@pytest.mark.parametrize('change', ['source', 'blob', 'git', 'argument'])
def test_preflight_exact_current_public_source_head_and_clean_host(args, monkeypatch, change):
    monkeypatch.setattr(m.prior.admitted.v5, '_under_test', lambda: False)
    monkeypatch.setattr(m.environment, '_require_environment', lambda: None)
    raw = m.SOURCE.read_bytes()
    args.caller_sha256 = m.sha(raw)
    monkeypatch.setattr(m, 'pins', lambda: {str(m.SOURCE.relative_to(m.ROOT)): 'f' * 64 if change == 'source' else m.sha(raw)})
    def git(command, deadline, *unused):
        if command[:2] == ['cat-file', 'blob']: return b'wrong' if change == 'blob' else raw
        result = {('rev-parse', '--show-toplevel'): str(m.ROOT),
            ('branch', '--show-current'): m.prior.admitted.frozen.BRANCH,
            ('rev-parse', 'HEAD'): args.expected_head, ('status', '--porcelain'): ''}[tuple(command)]
        if change == 'git' and command == ['status', '--porcelain']: result = ' M foreign'
        return (result + '\n').encode('ascii')
    monkeypatch.setattr(m.prior.admitted.v5, '_git', git)
    if change == 'argument': args.expected_head = 'not-a-head'
    with pytest.raises(m.Refused): m.preflight(args, time.monotonic() + 30)


def test_source_only_preflight_accepts_exact_pinned_head_blob(args, monkeypatch):
    monkeypatch.setattr(m.prior.admitted.v5, '_under_test', lambda: False)
    monkeypatch.setattr(m.environment, '_require_environment', lambda: None)
    raw = m.SOURCE.read_bytes(); args.caller_sha256 = m.sha(raw)
    monkeypatch.setattr(m, 'pins', lambda: {str(m.SOURCE.relative_to(m.ROOT)): m.sha(raw)})
    def git(command, deadline, *unused):
        if command[:2] == ['cat-file', 'blob']: return raw
        return ({('rev-parse', '--show-toplevel'): str(m.ROOT),
            ('branch', '--show-current'): m.prior.admitted.frozen.BRANCH,
            ('rev-parse', 'HEAD'): args.expected_head, ('status', '--porcelain'): ''}[tuple(command)] + '\n').encode()
    monkeypatch.setattr(m.prior.admitted.v5, '_git', git)
    m.preflight(args, time.monotonic() + 30)


@pytest.mark.parametrize('bad', ['extra', 'exit2', 'exitbool', 'pin', 'countbool', 'code', 'flag', 'code-mismatch'])
def test_output_actual_exit_report_and_closed_projection_binding(args, seams, bad):
    value, code = output(args), 0
    if bad == 'extra': value['raw_response'] = {}
    elif bad == 'exit2': code = 2
    elif bad == 'exitbool': code = False
    elif bad == 'pin': value['outcome']['report']['sha256'] = 'f' * 64
    elif bad == 'countbool': value['outcome']['result']['application_dispatch_count'] = True
    elif bad == 'code': value['outcome']['result']['access_failure_code'] = 'PRIVATE'
    elif bad == 'code-mismatch': value['outcome']['result']['observation']['access_failure_code'] = 'owner'
    else: value['outcome']['result']['project_ready'] = True
    with pytest.raises(m.Refused): m.validate_output(m.canonical(value), code, args)


@pytest.mark.parametrize('bad', ['trailing', 'malformed', 'large', 'list'])
def test_malformed_finite_output_refuses(args, seams, bad):
    raw = m.canonical(output(args))
    if bad == 'trailing': raw += b'{}\n'
    elif bad == 'malformed': raw = b'{'
    elif bad == 'large': raw = b' ' * (m.MAX_OUTPUT + 1)
    else: raw = b'[]\n'
    with pytest.raises((ValueError, TypeError)): m.validate_output(raw, 0, args)


def test_finite_preflight_failure_requires_actual_exit2(args):
    value = {'binding': m.binding(args), 'preflight_failure': 'source_pin'}
    assert m.validate_output(m.canonical(value), 2, args) == value
    with pytest.raises(m.Refused): m.validate_output(m.canonical(value), 0, args)


def test_invalid_binding_arguments_not_echoed(args):
    args.expected_head, args.caller_sha256 = 'PRIVATE ACCOUNT', 'PRIVATE TOKEN'
    value = m.binding(args)
    assert value['expected_head'] is value['caller_sha256'] is None and b'PRIVATE' not in m.canonical(value)


def test_deadline_refuses_before_any_dispatch(control, seams, args):
    outcome = m.run(args, time.monotonic() - 1)
    assert outcome['failure']['failure_code'] == 'deadline'
    assert outcome['failure']['state']['application_dispatch_count'] == 0
    assert not [item for item in seams.order if type(item) is tuple]


def test_observer_credential_failure_never_spawns(args, monkeypatch):
    monkeypatch.setattr(m, 'credential_shape', lambda: (_ for _ in ()).throw(ValueError('PRIVATE TOKEN')))
    monkeypatch.setattr(m, 'capture', lambda *_args, **_kwargs: pytest.fail('must not spawn'))
    result, code = m.observe(args)
    assert code == 2 and result['parent'] is None and result['output_authenticated'] is False
    assert b'PRIVATE' not in m.canonical(result)


def test_observer_native_validator_receives_actual_exit_without_credentials(args, seams, tmp_path, monkeypatch):
    value, calls = output(args), []
    def capture(command, env, timeout, **kwargs):
        calls.append((command, dict(env), timeout, kwargs))
        return m.canonical(value), b'', {'actual_exit': 0, 'bound': None}
    monkeypatch.setattr(m, 'capture', capture)
    monkeypatch.setattr(m.tempfile, 'mkdtemp', lambda **_: str(tmp_path))
    monkeypatch.setattr(m.prior.capture_support, '_environment', lambda path, credentials=None: dict(credentials or {}))
    monkeypatch.setattr(m, 'credential_shape', lambda: {'QC_USER_ID': 'synthetic', 'QC_API_TOKEN': 'synthetic-token'})
    result, code = m.observe(args)
    assert code == 0 and result['output_authenticated'] is True
    assert calls[0][0][3] == 'run' and calls[0][1]['QC_API_TOKEN'] == 'synthetic-token'
    assert calls[1][0][0] == '/usr/bin/sandbox-exec' and calls[1][0][-2:] == ['--actual-exit', '0']
    assert not {'QC_USER_ID', 'QC_API_TOKEN'} & calls[1][1].keys()
    assert calls[1][3]['input_bytes'] == m.canonical(value)
    assert str(m.ROOT / 'artifacts') in calls[1][0][2] and '(deny network*)' in calls[1][0][2]


@pytest.mark.parametrize('bad', ['parentnoise', 'parenttimeout', 'validatornoise', 'validatorexit'])
def test_observer_refuses_noisy_unknown_or_failed_actual_outcomes(args, seams, tmp_path, monkeypatch, bad):
    calls = []
    def capture(*_, **__):
        calls.append(1); parent = len(calls) == 1
        stderr = b'PRIVATE RAW' if bad == ('parentnoise' if parent else 'validatornoise') else b''
        observed = {'actual_exit': 2 if not parent and bad == 'validatorexit' else 0,
                    'bound': 'deadline' if parent and bad == 'parenttimeout' else None}
        return m.canonical(output(args)), stderr, observed
    monkeypatch.setattr(m, 'capture', capture)
    monkeypatch.setattr(m.tempfile, 'mkdtemp', lambda **_: str(tmp_path))
    monkeypatch.setattr(m.prior.capture_support, '_environment', lambda *_args: {})
    result, code = m.observe(args)
    assert code == 2 and result['output_authenticated'] is False and b'PRIVATE' not in m.canonical(result)
