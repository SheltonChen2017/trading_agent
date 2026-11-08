"""V protocol fixtures are synthetic: no private input, Keychain or HTTP."""
import copy
import json
import os
import re
import time
from types import SimpleNamespace as NS

import pytest

from scripts import run_arv2_r298_sharadar_eligibility_v2 as m
from tests.analyst_revisions_v2 import test_r298_sharadar_eligibility_v2_observation as provider_tests
from tests.analyst_revisions_v2._post_merge_pins import current_pin

REAL_PROVIDER_OBSERVE = m.observation.observe


@pytest.fixture(autouse=True)
def deny_operations(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('unmocked historical operation, credential or provider')
    for module, names in ((m.previous, ('main', 'run', 'observe', 'worker', 'run_worker')),
        (m.previous.source_binding, ('prepare',)), (m.keychain, ('load_key',)),
        (m.observation, ('observe',))):
        for name in names:
            monkeypatch.setattr(module, name, denied)


@pytest.fixture
def args():
    return NS(expected_head='a' * 40, caller_sha256='b' * 64, actual_exit=None, operation='run')


@pytest.fixture
def control(tmp_path, monkeypatch):
    parent = tmp_path / 'parent'
    parent.mkdir(mode=0o700)
    target = parent / 'synthetic-v'
    monkeypatch.setattr(m, 'CONTROL', target)
    monkeypatch.setattr(m.security, 'snapshot', lambda fd: {'acl_empty': True, 'xattrs': {}})
    return target


def event(index, kind, status=None):
    return {'schema': m.observation.EVENT_SCHEMA, 'event': kind, 'role': m.ROLES[index],
        'application_attempt': index + 1, 'http_status': status,
        'http_status_state': 'not_observed' if kind == 'intent' else
            'validated' if status is not None else 'unavailable'}


@pytest.fixture
def workflow(control, monkeypatch):
    buffers = {name: ('synthetic-private-' + str(index) + '\n').encode()
        for index, name in enumerate(m.CAPTURE_NAMES)}
    captures = {name: {'byte_count': len(raw), 'sha256': m.sha(raw)} for name, raw in buffers.items()}
    fixture = provider_tests.payloads()
    catalog = m.observation.current_routes.catalog(
        provider_tests.rows(fixture[m.CAPTURE_NAMES[0]]), provider_tests.rows(fixture[m.CAPTURE_NAMES[1]]))
    receipt = {'schema': 'synthetic-closed-eligibility', 'captures': captures,
        'current_route_catalog': catalog}
    state = NS(events=[], receipt=receipt, buffers=buffers, captures=captures,
        capture_checks=0, fail_postflight=False)

    def validate_receipt(value):
        assert value == receipt
        return copy.deepcopy(value)

    def validate_capture(value, payloads):
        validate_receipt(value)
        assert payloads == buffers
        state.capture_checks += 1
        return copy.deepcopy(value)

    def validate_events(value, values):
        validate_receipt(value)
        assert values == [event(index, kind, None if kind == 'intent' else 200)
            for index in range(6) for kind in ('intent', 'status')]
        return copy.deepcopy(values)

    def key(provider, *, timeout_seconds):
        assert provider == 'sharadar' and 0 < timeout_seconds <= 20
        claim = m.parse((control / 'claim.json').read_bytes())
        assert claim['local_only'] is True and claim['old_controls_spent'] is True
        assert sorted(path.name for path in control.iterdir()) == ['claim.json']
        state.events.append('keychain')
        return 'synthetic-key-not-a-real-credential'

    def observe(*, session, api_key, journal, catalog_observer, deadline):
        assert api_key == 'synthetic-key-not-a-real-credential'
        assert state.events == ['keychain']
        state.events.append('provider')
        for index in range(6):
            for kind in ('intent', 'status'):
                row = event(index, kind, None if kind == 'intent' else 200)
                marker = row['role'].replace('_', '-') + '-' + kind
                journal(marker, row)
                retained = m.parse((control / (marker + '.json')).read_bytes())
                assert retained['observation'] == row
            if index == 1:
                assert catalog_observer(copy.deepcopy(catalog)) is None
                assert m.parse((control / 'metadata-catalog.json').read_bytes())['catalog'] == catalog
        return copy.deepcopy(receipt), m.observation.PrivateCapture(dict(buffers))

    def preflight(*unused):
        state.events.append('postflight')
        if state.fail_postflight:
            raise m.Refused('source_pin')

    monkeypatch.setattr(m.keychain, 'load_key', key)
    monkeypatch.setattr(m.observation, 'observe', observe)
    monkeypatch.setattr(m.observation, 'validate_receipt', validate_receipt)
    monkeypatch.setattr(m.observation, 'validate_capture', validate_capture)
    monkeypatch.setattr(m.observation, 'validate_events', validate_events)
    monkeypatch.setattr(m.observation, 'capture_pins', lambda value: (validate_receipt(value), copy.deepcopy(captures))[1])
    monkeypatch.setattr(m, 'preflight', preflight)
    monkeypatch.setattr(m.environment, 'require_safe_environment', lambda: None)
    return state


def envelope(args, outcome):
    return m.canonical({'binding': m.binding(args), 'outcome': outcome})


def test_public_scope_and_fixed_local_only_protocol():
    record = m.profile_record()
    assert m.CONTROL.name == 'R323-20261025-V'
    assert m.DEADLINE_SECONDS == record['deadline_seconds'] == 600
    assert record['outer_seconds'] == 630 and record['validator_seconds'] == 20
    assert record['maximum_application_dispatches'] == 6 and record['provider_request_count'] is None
    assert record['keychain_lookups'] == 1 and record['keychain_account'] == 'sharadar'
    assert m.CAPTURE_NAMES == ('stocks-metadata.csv', 'funds-metadata.csv', 'stocks-status.json',
        'funds-status.json', 'stocks-prior.csv', 'funds-prior.csv')
    assert len(m.CAPTURE_BOUNDS) == 6 and record['max_control_files'] == 24
    assert record['qc_jobs'] == record['new_strategy_looks'] == record['result_cell'] == 0
    assert all(record[key] is False for key in m.FALSE_FLAGS)
    assert 'worker' not in m.main.__code__.co_consts


def test_selected_pins_and_in_memory_compilation():
    assert {'scripts/capture_arv2_sharadar_identities.py',
        'research/analyst_revisions_v2_qc/newrule_comparison_targets.py'} <= set(m.NEW_PINS)
    for name, pin in m.pins().items():
        assert re.fullmatch('[0-9a-f]{64}', pin) and pin != '0' * 64
        assert m.sha((m.ROOT / name).read_bytes()) == current_pin(name, pin)
    for name in ('scripts/run_arv2_r298_sharadar_eligibility_v2.py',
        'tests/analyst_revisions_v2/test_r298_sharadar_eligibility_v2_caller.py'):
        compile((m.ROOT / name).read_bytes(), name, 'exec')


def test_claim_before_one_key_six_requests_and_private_validation(control, args, workflow):
    outcome = m.run(args, time.monotonic() + 500)
    assert workflow.events == ['keychain', 'provider', 'postflight']
    assert workflow.capture_checks == 2
    assert outcome['result']['post_checks_complete'] is True
    assert len(outcome['result']['http_events']) == 12
    assert m.validate_output(envelope(args, outcome), 0, args)
    assert len(list(control.iterdir())) == 21
    for name, raw in workflow.buffers.items():
        assert (control / name).read_bytes() == raw
        assert (control / name).stat().st_mode & 0o777 == 0o600
    assert control.stat().st_mode & 0o777 == 0o700
    public = json.dumps(outcome)
    assert 'synthetic-key-not-a-real-credential' not in public
    assert 'synthetic-private-' not in public
    with pytest.raises(m.Refused, match='claim_spent'):
        m.run(args, time.monotonic() + 500)


def test_keychain_failure_consumes_claim_without_provider(control, args, workflow, monkeypatch):
    def refused(*args, **kwargs):
        assert (control / 'claim.json').is_file()
        raise m.keychain.KeychainUnavailable('unretained private message')
    monkeypatch.setattr(m.keychain, 'load_key', refused)
    outcome = m.run(args, time.monotonic() + 500)
    assert outcome['failure']['failure_code'] == 'credentials_unavailable'
    assert workflow.events == []
    assert m.validate_output(envelope(args, outcome), 2, args)


@pytest.mark.parametrize('status', [401, 403, 429, 500, None])
def test_non200_or_unknown_status_is_finite_failure_without_payload(control, args, workflow, monkeypatch, status):
    def refused(*, journal, **kwargs):
        journal('stocks-metadata-intent', event(0, 'intent'))
        journal('stocks-metadata-status', event(0, 'status', status))
        raise m.observation.Refused('http_status' if status is not None else 'http_status_unavailable')
    monkeypatch.setattr(m.observation, 'observe', refused)
    outcome = m.run(args, time.monotonic() + 500)
    failed = outcome['failure']
    assert failed['state']['http_events'][-1]['http_status'] is status
    assert failed['state']['receipt'] is None and failed['state']['captures'] == {}
    assert not any((control / name).exists() for name in m.CAPTURE_NAMES)
    assert m.validate_output(envelope(args, outcome), 2, args)


@pytest.mark.parametrize('actual', [2, None, False, True, -1])
def test_success_requires_exact_actual_zero(control, args, workflow, actual):
    outcome = m.run(args, time.monotonic() + 500)
    with pytest.raises(ValueError):
        m.validate_output(envelope(args, outcome), actual, args)


@pytest.mark.parametrize('field', ['post_checks_complete', 'private_capture_authenticated', 'qc_transfer_authorized',
    'strategy_price_admitted', 'strategy_nav_admitted', 'formal_forward_ready', 'result_cell'])
def test_output_cannot_upgrade_evidence_or_break_completion(control, args, workflow, field):
    outcome = m.run(args, time.monotonic() + 500)
    outcome['result'][field] = False if field in ('post_checks_complete', 'private_capture_authenticated') else True
    with pytest.raises(ValueError):
        m.validate_output(envelope(args, outcome), 0, args)


@pytest.mark.parametrize('mutation', ['pin', 'size', 'report', 'event', 'binding', 'extra'])
def test_external_output_authenticates_report_capture_events_and_binding(control, args, workflow, mutation):
    outcome = m.run(args, time.monotonic() + 500)
    value = {'binding': m.binding(args), 'outcome': outcome}
    if mutation == 'pin': outcome['result']['captures'][m.CAPTURE_NAMES[0]]['sha256'] = 'f' * 64
    elif mutation == 'size': outcome['result']['captures'][m.CAPTURE_NAMES[0]]['byte_count'] = True
    elif mutation == 'report': outcome['report']['sha256'] = 'f' * 64
    elif mutation == 'event': outcome['result']['http_events'][-1]['http_status'] = 403
    elif mutation == 'binding': value['binding']['expected_head'] = 'f' * 40
    else: outcome['result']['extra'] = 'untrusted'
    with pytest.raises((ValueError, AssertionError)):
        m.validate_output(m.canonical(value), 0, args)


def test_postflight_failure_retains_only_nonadmissible_finite_receipt(control, args, workflow):
    workflow.fail_postflight = True
    outcome = m.run(args, time.monotonic() + 500)
    assert outcome['failure']['state']['stage'] == 'postflight'
    assert outcome['failure']['state']['receipt'] == workflow.receipt
    assert set(outcome['failure']['state']['captures']) == set(m.CAPTURE_NAMES)
    assert not (control / 'report.json').exists()
    assert m.validate_output(envelope(args, outcome), 2, args)
    with pytest.raises(ValueError):
        m.validate_output(envelope(args, outcome), 0, args)


def test_capture_buffer_binding_precedes_any_publication(control, args, workflow, monkeypatch):
    original = m.observation.PrivateCapture.bytes_by_name
    def changed(self):
        values = original(self)
        values[m.CAPTURE_NAMES[0]] = b'different private body'
        return values
    monkeypatch.setattr(m.observation.PrivateCapture, 'bytes_by_name', changed)
    outcome = m.run(args, time.monotonic() + 500)
    assert 'failure' in outcome and outcome['failure']['state']['stage'] == 'provider'
    assert not any((control / name).exists() for name in m.CAPTURE_NAMES)


def test_retained_private_descriptors_are_revalidated_after_read(control, monkeypatch):
    with m.Store() as store:
        store.write('claim.json', {'synthetic': True})
        for name in m.CAPTURE_NAMES:
            store.write_bytes(name, b'synthetic', private=True)
        original = store._read
        def changed(fd, size):
            value = original(fd, size)
            info = os.fstat(fd)
            os.utime(fd, ns=(info.st_atime_ns, info.st_mtime_ns + 1))
            return value
        monkeypatch.setattr(store, '_read', changed)
        with pytest.raises(m.Refused, match='capture_changed'):
            store.capture_bytes()


def test_full_metadata_and_security_drift_refuse(control, monkeypatch):
    with m.Store() as store:
        store.write_bytes(m.CAPTURE_NAMES[0], b'synthetic', private=True)
        fd, _ = store.held[m.CAPTURE_NAMES[0]]
        info = os.fstat(fd)
        os.utime(fd, ns=(info.st_atime_ns, info.st_mtime_ns + 1))
        with pytest.raises(m.Refused, match='capture_changed'):
            store.verify()


def test_security_policy_is_observed_before_any_private_write(control, monkeypatch):
    with m.Store() as store:
        def refused(fd):
            if os.fstat(fd).st_mode & 0o170000 == 0o040000:
                return {'acl_empty': True, 'xattrs': {}}
            assert os.fstat(fd).st_size == 0
            raise m.security.Refusal('extended ACL entry present')
        monkeypatch.setattr(m.security, 'snapshot', refused)
        with pytest.raises(m.Refused, match='capture_security'):
            store.write_bytes(m.CAPTURE_NAMES[0], b'private', private=True)
        assert (control / m.CAPTURE_NAMES[0]).stat().st_size == 0


def test_late_report_failure_may_leave_report_but_cannot_be_accepted(control, args, workflow, monkeypatch):
    original = m.Store.write
    def late(self, name, value):
        result = original(self, name, value)
        if name == 'report.json':
            raise m.Refused('control_write')
        return result
    monkeypatch.setattr(m.Store, 'write', late)
    outcome = m.run(args, time.monotonic() + 500)
    assert (control / 'report.json').is_file()
    assert outcome['failure']['failure_code'] == 'control_write'
    assert outcome['failure']['state']['stage'] == 'report'
    assert m.validate_output(envelope(args, outcome), 2, args)
    with pytest.raises(ValueError):
        m.validate_output(envelope(args, outcome), 0, args)


@pytest.mark.parametrize('name', ['../outside.json', '/tmp/out.json', 'key.txt', 'unexpected.csv'])
def test_store_rejects_other_names(control, name):
    with m.Store() as store:
        with pytest.raises(m.Refused, match='control_name'):
            store.write_bytes(name, b'private', private=True)


def test_journal_cannot_continue_after_refused_status():
    values = [event(0, 'intent'), event(0, 'status', 403)]
    assert m._events(values) == values
    with pytest.raises(m.Refused, match='journal'):
        m._events([*values, event(1, 'intent')])


@pytest.mark.parametrize('value', [None, False, float('nan'), float('inf'), -1, time.monotonic() - 1,
    time.monotonic() + 1000])
def test_deadline_is_finite_exact_and_parent_bounded(value):
    with pytest.raises(m.Refused, match='deadline'):
        m.remaining(value)


def test_unknown_hostile_exception_is_not_stringified():
    class Hostile(ValueError):
        def __str__(self):
            raise AssertionError('must not render')
    assert m.finite(Hostile('private')) == 'unknown_exception'
    class Derived(m.observation.Refused):
        pass
    assert m.finite(Derived('http_status')) == 'unknown_exception'


def test_native_validator_policy_denies_all_production_artifacts_and_keys():
    policy = m.native_profile()
    assert '(deny network*)' in policy
    assert str(m.ROOT / 'artifacts') in policy
    assert 'Keychains' in policy and '/usr/bin/security' in policy


def test_observer_preserves_parent_exit_and_has_no_credential_handoff(control, args, workflow, monkeypatch):
    outcome = m.run(args, time.monotonic() + 500)
    raw = envelope(args, outcome)
    calls = []
    def capture(command, env, seconds, **kwargs):
        calls.append((command, env, seconds, kwargs))
        assert not any(key in env for key in ('QC_USER_ID', 'QC_API_TOKEN', 'SHARADAR_API_KEY', 'MASSIVE_API_KEY'))
        if len(calls) == 1:
            assert seconds == 630 and kwargs['stdout_limit'] == m.MAX_OUTPUT
            return raw, b'', {'actual_exit': 0, 'bound': None}
        assert seconds == 20 and command[:2] == ['/usr/bin/sandbox-exec', '-p']
        assert kwargs['input_bytes'] == raw
        return raw, b'', {'actual_exit': 0, 'bound': None}
    monkeypatch.setattr(m, 'capture', capture)
    result, code = m.observe(args)
    assert code == 0 and result['output_authenticated'] is True and len(calls) == 2


@pytest.mark.parametrize('actual, bound, stderr', [(None, None, b''), (False, None, b''),
    (0, 'stdout', b''), (0, None, b'private raw error')])
def test_observer_does_not_validate_ambiguous_parent(control, args, monkeypatch, actual, bound, stderr):
    calls = []
    def capture(*unused, **kwargs):
        calls.append(1)
        return b'never parse', stderr, {'actual_exit': actual, 'bound': bound}
    monkeypatch.setattr(m, 'capture', capture)
    result, code = m.observe(args)
    assert code == 2 and result['output_authenticated'] is False and len(calls) == 1
    assert result['failure_code'] == 'parent_failed'


def test_failure_state_cannot_claim_unpublished_or_postchecked_success(control, args, workflow):
    workflow.fail_postflight = True
    outcome = m.run(args, time.monotonic() + 500)
    state = outcome['failure']['state']
    state['stage'] = 'credentials'
    with pytest.raises(ValueError):
        m.validate_output(envelope(args, outcome), 2, args)


def test_preflight_failure_requires_actual_nonzero(args):
    raw = m.canonical({'binding': m.binding(args), 'preflight_failure': 'source_pin'})
    assert m.validate_output(raw, 2, args)
    with pytest.raises(ValueError):
        m.validate_output(raw, 0, args)


def test_real_native_held_file_security_and_metadata_shape(tmp_path, monkeypatch):
    parent = tmp_path / 'native-parent'
    parent.mkdir(mode=0o700)
    monkeypatch.setattr(m, 'CONTROL', parent / 'native-v')
    with m.Store() as store:
        store.write_bytes(m.CAPTURE_NAMES[0], b'inert-synthetic-private-buffer', private=True)
        fd, snapshot = store.held[m.CAPTURE_NAMES[0]]
        assert snapshot['acl_empty'] is True and set(snapshot) == {'acl_empty', 'xattrs'}
        assert type(snapshot['xattrs']) is dict
        assert len(m.metadata(os.fstat(fd))) == 10
        assert m.metadata(os.fstat(fd)) == store.files[m.CAPTURE_NAMES[0]]
        store.verify()


@pytest.mark.parametrize('empty', [False, True])
def test_genuine_new_provider_to_caller_receipt_interoperability(control, args, monkeypatch, empty):
    transport = provider_tests.transport.__wrapped__(monkeypatch)
    if empty:
        transport.captures[m.CAPTURE_NAMES[4]] = provider_tests.csv_bytes(m.observation.PRICE_FIELDS, [])
        transport.captures[m.CAPTURE_NAMES[5]] = provider_tests.csv_bytes(m.observation.PRICE_FIELDS, [])
    def key(provider, *, timeout_seconds):
        assert (control / 'claim.json').is_file() and transport.calls == []
        return provider_tests.KEY
    monkeypatch.setattr(m.observation, 'observe', REAL_PROVIDER_OBSERVE)
    monkeypatch.setattr(m.keychain, 'load_key', key)
    monkeypatch.setattr(m, 'preflight', lambda *unused: None)
    monkeypatch.setattr(m.environment, 'require_safe_environment', lambda: None)
    outcome = m.run(args, time.monotonic() + 500)
    assert 'result' in outcome, outcome.get('failure', {}).get('failure_code')
    assert len(transport.calls) == 6 and len(outcome['result']['http_events']) == 12
    receipt = outcome['result']['receipt']
    assert receipt['early_prices']['stocks']['observed_row_count'] == (0 if empty else 1)
    assert receipt['early_prices']['funds']['observed_row_count'] == (0 if empty else 8)
    assert receipt['paid_tier_proven'] is receipt['common_price_package_admitted'] is False
    assert m.validate_output(envelope(args, outcome), 0, args)
    assert all((control / name).read_bytes() == raw for name, raw in transport.captures.items())


def test_genuine_route_collision_retains_closed_catalog_before_refusal(control, args, monkeypatch):
    transport = provider_tests.transport.__wrapped__(monkeypatch)
    funds = provider_tests.rows(transport.captures[m.CAPTURE_NAMES[1]])
    funds[1]['cusips'] += ' 000000001'
    transport.captures[m.CAPTURE_NAMES[1]] = provider_tests.csv_bytes(m.observation.META_FIELDS, funds)
    monkeypatch.setattr(m.observation, 'observe', REAL_PROVIDER_OBSERVE)
    monkeypatch.setattr(m.keychain, 'load_key', lambda *args, **kwargs: provider_tests.KEY)
    monkeypatch.setattr(m, 'preflight', lambda *unused: None)
    monkeypatch.setattr(m.environment, 'require_safe_environment', lambda: None)
    outcome = m.run(args, time.monotonic() + 500)
    failed = outcome['failure']
    assert failed['failure_code'] == 'provider_routing_route_collision'
    assert len(transport.calls) == 2 and len(failed['state']['http_events']) == 4
    catalog = failed['state']['current_route_catalog']
    assert catalog['probes'][0]['cross_table_complete_token_overlap_rows'] == 1
    assert m.parse((control / 'metadata-catalog.json').read_bytes())['catalog'] == catalog
    assert not any((control / name).exists() for name in m.CAPTURE_NAMES)
    assert m.validate_output(envelope(args, outcome), 2, args)
    public = m.canonical(outcome)
    assert b'000000001' not in public and provider_tests.KEY.encode() not in public


@pytest.mark.parametrize('fault', ['missing', 'duplicate'])
def test_catalog_callback_must_be_once_after_four_events_before_third_dispatch(control, args, workflow, monkeypatch, fault):
    def provider(*, journal, catalog_observer, **unused):
        for index in range(2):
            journal(m.ROLES[index].replace('_', '-') + '-intent', event(index, 'intent'))
            journal(m.ROLES[index].replace('_', '-') + '-status', event(index, 'status', 200))
        if fault == 'duplicate':
            catalog_observer(copy.deepcopy(workflow.receipt['current_route_catalog']))
            catalog_observer(copy.deepcopy(workflow.receipt['current_route_catalog']))
        else:
            journal('stocks-status-intent', event(2, 'intent'))
        raise AssertionError('invalid protocol continued')
    monkeypatch.setattr(m.observation, 'observe', provider)
    outcome = m.run(args, time.monotonic() + 500)
    failed = outcome['failure']
    assert failed['failure_code'] == 'journal' and len(failed['state']['http_events']) == 4
    assert (control / 'metadata-catalog.json').exists() is (fault == 'duplicate')
    assert m.validate_output(envelope(args, outcome), 2, args)


def test_failure_receiver_rejects_missing_or_upgraded_catalog(control, args, workflow):
    workflow.fail_postflight = True
    outcome = m.run(args, time.monotonic() + 500)
    assert m.validate_output(envelope(args, outcome), 2, args)
    changed = copy.deepcopy(outcome)
    changed['failure']['state']['current_route_catalog'] = None
    with pytest.raises(m.Refused):
        m.validate_output(envelope(args, changed), 2, args)
    changed = copy.deepcopy(outcome)
    changed['failure']['state']['current_route_catalog']['current_identity_admitted'] = True
    with pytest.raises(m.Refused):
        m.validate_output(envelope(args, changed), 2, args)


def test_normal_capture_must_match_earlier_retained_catalog(control, args, workflow, monkeypatch):
    def altered(*, catalog_observer, journal, **unused):
        assert workflow.events == ['keychain']
        workflow.events.append('provider')
        for index in range(6):
            for kind in ('intent', 'status'):
                journal(m.ROLES[index].replace('_', '-') + '-' + kind,
                    event(index, kind, None if kind == 'intent' else 200))
            if index == 1:
                value = copy.deepcopy(workflow.receipt['current_route_catalog'])
                value['metadata_rows_sha256']['stocks'] = 'f' * 64
                catalog_observer(value)
        return copy.deepcopy(workflow.receipt), m.observation.PrivateCapture(workflow.buffers)
    monkeypatch.setattr(m.observation, 'observe', altered)
    outcome = m.run(args, time.monotonic() + 500)
    assert outcome['failure']['failure_code'] == 'capture_changed'
    assert outcome['failure']['state']['stage'] == 'provider'
    assert outcome['failure']['state']['receipt'] is None
    assert not any((control / name).exists() for name in m.CAPTURE_NAMES)
    assert m.validate_output(envelope(args, outcome), 2, args)


@pytest.fixture
def preflight_environment(args, monkeypatch):
    actual_source = m.SOURCE.read_bytes()
    args.caller_sha256 = m.sha(actual_source)
    selected = {str(m.SOURCE.relative_to(m.ROOT)): args.caller_sha256}
    monkeypatch.setattr(m, 'pins', lambda: dict(selected))
    monkeypatch.setattr(m.admitted.v5, '_under_test', lambda: False)
    monkeypatch.setattr(m.environment, '_require_environment', lambda: None)
    outputs = {('rev-parse', '--show-toplevel'): str(m.ROOT).encode(),
        ('branch', '--show-current'): m.admitted.frozen.BRANCH.encode(),
        ('rev-parse', 'HEAD'): args.expected_head.encode(), ('status', '--porcelain'): b''}
    state = NS(outputs=outputs, source=actual_source, calls=[])
    def git(command, deadline, maximum=None):
        state.calls.append(tuple(command))
        return state.source if command[0] == 'cat-file' else outputs[tuple(command)]
    monkeypatch.setattr(m.admitted.v5, '_git', git)
    return state


def test_preflight_binds_clean_exact_host_head_selected_bytes_and_committed_caller(args, preflight_environment):
    m.preflight(args, time.monotonic() + 30)
    assert preflight_environment.calls[-1][0] == 'cat-file'


@pytest.mark.parametrize('which', ['root', 'branch', 'head', 'dirty', 'committed'])
def test_preflight_rejects_scope_or_committed_source_drift(args, preflight_environment, which):
    keys = {'root': ('rev-parse', '--show-toplevel'), 'branch': ('branch', '--show-current'),
        'head': ('rev-parse', 'HEAD'), 'dirty': ('status', '--porcelain')}
    if which == 'committed':
        preflight_environment.source = b'uncommitted-code'
    else:
        preflight_environment.outputs[keys[which]] = b'changed'
    with pytest.raises(m.Refused, match='source_pin' if which == 'committed' else 'git_state'):
        m.preflight(args, time.monotonic() + 30)


def test_preflight_rejects_source_pin_change(args, preflight_environment, monkeypatch):
    monkeypatch.setattr(m, 'pins', lambda: {str(m.SOURCE.relative_to(m.ROOT)): '0' * 64})
    with pytest.raises(m.Refused, match='source_pin'):
        m.preflight(args, time.monotonic() + 30)


@pytest.mark.parametrize('field', ['expected_head', 'caller_sha256'])
def test_preflight_rejects_malformed_cli_source_bindings(args, preflight_environment, field):
    setattr(args, field, 'unbound')
    with pytest.raises(m.Refused, match='arguments'):
        m.preflight(args, time.monotonic() + 30)


def test_security_snapshot_drift_refuses_even_if_inode_metadata_matches(control, monkeypatch):
    with m.Store() as store:
        store.write_bytes(m.CAPTURE_NAMES[0], b'synthetic', private=True)
        fd, _ = store.held[m.CAPTURE_NAMES[0]]
        baseline = m.metadata(os.fstat(fd))
        def snapshot(other):
            return {'acl_empty': True, 'xattrs': {} if other != fd else
                {'com.apple.provenance': {'size': 1, 'sha256': 'f' * 64}}}
        monkeypatch.setattr(m.security, 'snapshot', snapshot)
        with pytest.raises(m.Refused, match='capture_changed'):
            store.verify()
        assert m.metadata(os.fstat(fd)) == baseline


@pytest.mark.parametrize('code', sorted(m.observation.FINITE))
def test_all_selected_provider_finite_codes_remain_closed_without_rendering(code):
    assert m.finite(m.observation.Refused(code)) == 'provider_' + code
    assert m._finite_code('provider_' + code)


def test_selected_dependency_pin_conflicts_are_not_silently_refreshed(monkeypatch):
    name = 'scripts/run_arv2_r298_sharadar_reference.py'
    monkeypatch.setattr(m.previous, 'pins', lambda: {name: 'f' * 64})
    with pytest.raises(m.Refused, match='source_pin'):
        m.pins()


def test_unchanged_protocol_primitives_match_S_while_catalog_contract_is_new():
    import ast
    import inspect
    from scripts import run_arv2_r298_sharadar_eligibility as old

    def normalized(raw):
        tree = ast.parse(raw)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "Store":
                node.body.pop(0)
            if isinstance(node, ast.keyword) and node.arg == "prefix":
                node.value = ast.Constant(None)
        return ast.dump(tree, include_attributes=False)

    # Run/result validation intentionally add a durable catalog callback; they
    # have behavioral tests instead of falsely promising whole-protocol parity.
    for name in ('Store', 'preflight', '_events', 'security_snapshot',
            '_capture_pins', 'remaining', 'native_profile', 'observe', 'main'):
        assert normalized(inspect.getsource(getattr(m, name))) == normalized(inspect.getsource(getattr(old, name)))
    assert m.SCHEMA != old.SCHEMA and m.SOURCE != old.SOURCE and m.CONTROL != old.CONTROL
    assert m.ROLES == old.ROLES and m.CAPTURE_NAMES == old.CAPTURE_NAMES
    assert m.CAPTURE_BOUNDS == old.CAPTURE_BOUNDS


def test_new_parser_router_and_spent_predecessor_are_external_source_bindings():
    required = {
        "scripts/arv2_r298_sharadar_eligibility_observation.py",
        "scripts/run_arv2_r298_sharadar_eligibility.py",
        "scripts/arv2_r298_sharadar_cusip_syntax.py",
        "scripts/arv2_r298_sharadar_probe_metadata.py",
        "scripts/arv2_r298_sharadar_current_routes.py",
        "scripts/arv2_r298_sharadar_eligibility_v2_observation.py",
    }
    assert required <= set(m.NEW_PINS)
    record = m.profile_record()
    assert record["complete_coverage_proven"] is False
    assert record["cloud_processing_rights_proven"] is False
    assert record["qc_transfer_authorized"] is False
    assert record["old_operational_entrypoints_invoked"] is False
