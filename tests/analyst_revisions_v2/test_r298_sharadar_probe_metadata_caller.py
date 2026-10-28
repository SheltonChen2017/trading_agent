"""T protocol fixtures are synthetic: no private input, Keychain or HTTP."""
import copy
import json
import os
import re
import time
from types import SimpleNamespace as NS

import pytest

from scripts import run_arv2_r298_sharadar_probe_metadata as m
from tests.analyst_revisions_v2 import test_r298_sharadar_probe_metadata as synthetic_catalog
from tests.analyst_revisions_v2._post_merge_pins import current_pin

REAL_PROVIDER_OBSERVE = m.observation.observe


@pytest.fixture(autouse=True)
def deny_operations(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('unmocked historical operation, credential or provider')
    for module, names in ((m.previous, ('main', 'run', 'observe')),
        (m.previous.previous.source_binding, ('prepare',)), (m.keychain, ('load_key',)),
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
    target = parent / 'synthetic-t'
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
    receipt = {'schema': 'synthetic-closed-probe', 'captures': captures}
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
            for index in range(2) for kind in ('intent', 'status')]
        return copy.deepcopy(values)

    def key(provider, *, timeout_seconds):
        assert provider == 'sharadar' and 0 < timeout_seconds <= 20
        claim = m.parse((control / 'claim.json').read_bytes())
        assert claim['local_only'] is True and claim['old_controls_spent'] is True
        assert sorted(path.name for path in control.iterdir()) == ['claim.json']
        state.events.append('keychain')
        return 'synthetic-key-not-a-real-credential'

    def observe(*, session, api_key, journal, deadline):
        assert api_key == 'synthetic-key-not-a-real-credential'
        assert state.events == ['keychain']
        state.events.append('provider')
        for index in range(2):
            for kind in ('intent', 'status'):
                row = event(index, kind, None if kind == 'intent' else 200)
                marker = row['role'].replace('_', '-') + '-' + kind
                journal(marker, row)
                retained = m.parse((control / (marker + '.json')).read_bytes())
                assert retained['observation'] == row
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
    assert m.CONTROL.name == 'R323-20261025-T'
    assert m.DEADLINE_SECONDS == record['deadline_seconds'] == 300
    assert record['outer_seconds'] == 330 and record['validator_seconds'] == 20
    assert record['maximum_application_dispatches'] == 2 and record['provider_request_count'] is None
    assert record['keychain_lookups'] == 1 and record['keychain_account'] == 'sharadar'
    assert m.CAPTURE_NAMES == ('stocks-probe.csv', 'funds-probe.csv')
    assert len(m.CAPTURE_BOUNDS) == 2 and record['max_control_files'] == 12
    assert record['qc_jobs'] == record['new_strategy_looks'] == record['result_cell'] == 0
    assert all(record[key] is False for key in m.FALSE_FLAGS)
    assert 'worker' not in m.main.__code__.co_consts


def test_selected_pins_and_in_memory_compilation():
    assert {'scripts/capture_arv2_sharadar_identities.py',
        'research/analyst_revisions_v2_qc/newrule_comparison_targets.py'} <= set(m.NEW_PINS)
    for name, pin in m.pins().items():
        assert re.fullmatch('[0-9a-f]{64}', pin) and pin != '0' * 64
        assert m.sha((m.ROOT / name).read_bytes()) == current_pin(name, pin)
    for name in ('scripts/run_arv2_r298_sharadar_probe_metadata.py',
        'tests/analyst_revisions_v2/test_r298_sharadar_probe_metadata_caller.py'):
        compile((m.ROOT / name).read_bytes(), name, 'exec')


def test_claim_before_one_key_two_requests_and_private_validation(control, args, workflow):
    outcome = m.run(args, time.monotonic() + 200)
    assert workflow.events == ['keychain', 'provider', 'postflight']
    assert workflow.capture_checks == 2
    assert outcome['result']['post_checks_complete'] is True
    assert len(outcome['result']['http_events']) == 4
    assert m.validate_output(envelope(args, outcome), 0, args)
    assert len(list(control.iterdir())) == 8
    for name, raw in workflow.buffers.items():
        assert (control / name).read_bytes() == raw
        assert (control / name).stat().st_mode & 0o777 == 0o600
    assert control.stat().st_mode & 0o777 == 0o700
    public = json.dumps(outcome)
    assert 'synthetic-key-not-a-real-credential' not in public
    assert 'synthetic-private-' not in public
    with pytest.raises(m.Refused, match='claim_spent'):
        m.run(args, time.monotonic() + 200)


def test_keychain_failure_consumes_claim_without_provider(control, args, workflow, monkeypatch):
    def refused(*args, **kwargs):
        assert (control / 'claim.json').is_file()
        raise m.keychain.KeychainUnavailable('unretained private message')
    monkeypatch.setattr(m.keychain, 'load_key', refused)
    outcome = m.run(args, time.monotonic() + 200)
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
    outcome = m.run(args, time.monotonic() + 200)
    failed = outcome['failure']
    assert failed['state']['http_events'][-1]['http_status'] is status
    assert failed['state']['receipt'] is None and failed['state']['captures'] == {}
    assert not any((control / name).exists() for name in m.CAPTURE_NAMES)
    assert m.validate_output(envelope(args, outcome), 2, args)


@pytest.mark.parametrize('actual', [2, None, False, True, -1])
def test_success_requires_exact_actual_zero(control, args, workflow, actual):
    outcome = m.run(args, time.monotonic() + 200)
    with pytest.raises(ValueError):
        m.validate_output(envelope(args, outcome), actual, args)


@pytest.mark.parametrize('field', ['post_checks_complete', 'private_capture_authenticated', 'qc_transfer_authorized',
    'strategy_price_admitted', 'strategy_nav_admitted', 'formal_forward_ready', 'result_cell'])
def test_output_cannot_upgrade_evidence_or_break_completion(control, args, workflow, field):
    outcome = m.run(args, time.monotonic() + 200)
    outcome['result'][field] = False if field in ('post_checks_complete', 'private_capture_authenticated') else True
    with pytest.raises(ValueError):
        m.validate_output(envelope(args, outcome), 0, args)


@pytest.mark.parametrize('mutation', ['pin', 'size', 'report', 'event', 'binding', 'extra'])
def test_external_output_authenticates_report_capture_events_and_binding(control, args, workflow, mutation):
    outcome = m.run(args, time.monotonic() + 200)
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
    outcome = m.run(args, time.monotonic() + 200)
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
    outcome = m.run(args, time.monotonic() + 200)
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
    outcome = m.run(args, time.monotonic() + 200)
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
    outcome = m.run(args, time.monotonic() + 200)
    raw = envelope(args, outcome)
    calls = []
    def capture(command, env, seconds, **kwargs):
        calls.append((command, env, seconds, kwargs))
        assert not any(key in env for key in ('QC_USER_ID', 'QC_API_TOKEN', 'SHARADAR_API_KEY', 'MASSIVE_API_KEY'))
        if len(calls) == 1:
            assert seconds == 330 and kwargs['stdout_limit'] == m.MAX_OUTPUT
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
    outcome = m.run(args, time.monotonic() + 200)
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
    monkeypatch.setattr(m, 'CONTROL', parent / 'native-t')
    with m.Store() as store:
        store.write_bytes(m.CAPTURE_NAMES[0], b'inert-synthetic-private-buffer', private=True)
        fd, snapshot = store.held[m.CAPTURE_NAMES[0]]
        assert snapshot['acl_empty'] is True and set(snapshot) == {'acl_empty', 'xattrs'}
        assert type(snapshot['xattrs']) is dict
        assert len(m.metadata(os.fstat(fd))) == 10
        assert m.metadata(os.fstat(fd)) == store.files[m.CAPTURE_NAMES[0]]
        store.verify()


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
    name = 'scripts/run_arv2_r298_sharadar_eligibility.py'
    monkeypatch.setattr(m.previous, 'pins', lambda: {name: 'f' * 64})
    with pytest.raises(m.Refused, match='source_pin'):
        m.pins()


@pytest.mark.parametrize('quality', ['normal', 'missing_cusip', 'unknown_interval',
    'missing_candidate', 'ambiguous_candidate', 'collision'])
def test_genuine_current_predicate_observation_can_contain_refusals_without_admission(
        control, args, monkeypatch, quality):
    # Reuse only public, synthetic CSV construction/transport fixtures. The
    # spent S transport/observer entry points remain forbidden below.
    transport = synthetic_catalog.transport.__wrapped__(monkeypatch)
    stocks = synthetic_catalog.rows(transport.captures[synthetic_catalog.m.CAPTURE_NAMES[0]])
    funds = synthetic_catalog.rows(transport.captures[synthetic_catalog.m.CAPTURE_NAMES[1]])
    if quality == 'missing_cusip':
        stocks[0]['cusips'] = ''
    elif quality == 'unknown_interval':
        stocks[0]['firstpricedate'] = ''
    elif quality == 'missing_candidate':
        stocks[0]['ticker'] = 'SYNTHETIC_OTHER'
    elif quality == 'ambiguous_candidate':
        stocks.append(dict(stocks[0]))
    elif quality == 'collision':
        funds[0]['permaticker'] = stocks[0]['permaticker']
    transport.captures[synthetic_catalog.m.CAPTURE_NAMES[0]] = synthetic_catalog.csv_bytes(m.observation.META_FIELDS, stocks)
    transport.captures[synthetic_catalog.m.CAPTURE_NAMES[1]] = synthetic_catalog.csv_bytes(m.observation.META_FIELDS, funds)
    def key(provider, *, timeout_seconds):
        assert (control / 'claim.json').is_file() and transport.calls == []
        return synthetic_catalog.KEY
    def denied(*unused, **kwargs):
        raise AssertionError('spent S provider invocation')
    monkeypatch.setattr(m.observation.previous, 'observe', denied)
    monkeypatch.setattr(m.observation.previous, '_fetch', denied)
    monkeypatch.setattr(m.observation, 'observe', REAL_PROVIDER_OBSERVE)
    monkeypatch.setattr(m.keychain, 'load_key', key)
    monkeypatch.setattr(m, 'preflight', lambda *unused: None)
    monkeypatch.setattr(m.environment, 'require_safe_environment', lambda: None)
    outcome = m.run(args, time.monotonic() + 200)
    assert 'result' in outcome, outcome.get('failure', {}).get('failure_code')
    assert len(transport.calls) == 2 and len(outcome['result']['http_events']) == 4
    receipt = outcome['result']['receipt']
    probe = receipt['probes'][0]
    if quality == 'missing_cusip':
        assert probe['predicates']['cusip_field_nonempty'] is False
        assert probe['failed_identity_predicate_count'] > 0
    elif quality == 'unknown_interval':
        assert probe['predicates']['reference_interval_contains'] is None
        assert probe['unknown_predicate_count'] > 0
    elif quality in ('missing_candidate', 'ambiguous_candidate'):
        assert probe['candidate_count'] == (0 if quality == 'missing_candidate' else 2)
        assert probe['predicates'] is probe['fields'] is None
    elif quality == 'collision':
        assert probe['predicates']['cross_table_permaticker_collision'] is True
    assert receipt['probe_metadata_admitted'] is receipt['s_failure_cause_authenticated'] is False
    assert all(receipt[key] is False for key in m.observation.FALSE_FLAGS)
    assert m.validate_output(envelope(args, outcome), 0, args)
    public = json.dumps(outcome)
    assert synthetic_catalog.KEY not in public and 'QCOM' not in public and 'BBG000000001' not in public
