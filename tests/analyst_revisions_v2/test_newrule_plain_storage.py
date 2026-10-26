"""Synthetic protocol only; run under native network/private-artifact denial."""
import copy
import json
import time
from types import SimpleNamespace as NS

import pytest

from scripts import arv2_newrule_plain_storage as m
from tests.analyst_revisions_v2 import test_newrule_plain_projection as fixtures


ORGANIZATION = '1' * 32


class Directory:
    def __init__(self):
        self.values = {}
        self.events = []
        self.fail_write = self.fail_read = None
        self.extra_names = []
        self.verify_failure = False

    def write(self, name, value):
        self.events.append(('write', name))
        if name == self.fail_write or name in self.values:
            raise RuntimeError('synthetic-only journal refusal')
        self.values[name] = json.loads(m.canonical(value))

    def read(self, name):
        self.events.append(('read', name))
        if name == self.fail_read:
            raise RuntimeError('synthetic-only journal refusal')
        return copy.deepcopy(self.values[name])

    def verify(self):
        self.events.append(('verify', None))
        if self.verify_failure:
            raise RuntimeError('synthetic-only journal refusal')

    def names(self):
        return list(self.values) + self.extra_names


@pytest.fixture(scope='module')
def package():
    # These fixture factories read public Python source only and mint synthetic
    # data capabilities; no source-authentication or real-publication claim.
    case = fixtures.case.__wrapped__(fixtures.public_parent.__wrapped__())
    projected = fixtures.build(case)
    record = {'schema': m.PREPARATION_SCHEMA, 'expected_head': 'a' * 40,
        'caller_sha256': 'b' * 64, 'profile_sha256': 'c' * 64,
        'complete': True, 'failure_code': None, 'transport': case.plain.to_record(),
        'projection': projected.to_record(), 'attempt_consumed': True,
        **{name: False for name in m.PREPARATION_FALSE}}
    return NS(plain=case.plain, record=record)


def observation(success=True, *, metadata=False, error=None, key='synthetic-key'):
    raw = {'success': success, 'errors': [] if error is None else [error]}
    if metadata:
        raw['metadata'] = {'synthetic': True}
    return m.wire.error_text._observation(m.canonical(raw),
        ('synthetic-user', 'synthetic-token', ORGANIZATION, key))


def packet(phase, row, *, absent=False, failure=None, attempted=True, choice=0):
    key = row[0]
    if failure is not None:
        return {'attempted': attempted, 'http_status': None, 'observation': None,
            'error_shape': None, 'object_state': None, 'absence_template_index': None,
            'failure_code': failure}
    error = m.wire.ABSENCE_TEMPLATES[choice].format(key=key) if absent else None
    return {'attempted': True, 'http_status': 200,
        'observation': observation(not absent, metadata=phase != 'put' and not absent, error=error, key=key),
        'error_shape': m.wire._error_shape({'errors': [error]}, key) if absent else None,
        'object_state': 'absent' if absent else 'published' if phase == 'put' else 'present',
        'absence_template_index': choice if absent else None, 'failure_code': None}


class Broker:
    def __init__(self, directory, *, present=()):
        self.directory = directory
        self.present = set(present)
        self.calls = []
        self.hook = None

    def __call__(self, phase, index, row, payload, request_sha256, deadline):
        assert type(row) is tuple and type(payload) is bytes
        assert m.CLAIM in self.directory.values
        ordinal = len(self.calls)
        assert m._stem(ordinal) + '-intent.json' in self.directory.values
        endpoint, body, _ = m.wire._body(phase, ORGANIZATION, row, payload)
        assert request_sha256 == m.sha(body)
        assert endpoint == ('object/set' if phase == 'put' else 'object/properties')
        assert row[1] == m.sha(payload) and row[2] == len(payload)
        self.calls.append((phase, index))
        if self.hook is not None:
            result = self.hook(phase, index, row)
            if result is not None:
                return result
        if phase == 'put':
            self.present.add(index)
        return packet(phase, row, absent=index not in self.present)


@pytest.fixture
def case(package, monkeypatch):
    # Replace this module's imported namespace, never mutate the frozen access
    # module, and never inspect a real organization reference or credential.
    monkeypatch.setattr(m, 'access', NS(ORGANIZATION_SHA256=m.sha(ORGANIZATION.encode())))
    directory = Directory()
    broker = Broker(directory)
    raw = m.canonical(package.record)
    checks = []

    def source_recheck(plain):
        assert plain is package.plain
        assert m.CLAIM in directory.values
        checks.append(len(broker.calls))

    kwargs = {'deadline': time.monotonic() + 200,
        'expected_package_sha256': package.plain.package_sha256,
        'expected_activation_sha256': package.plain.activation_manifest_sha256,
        'expected_preparation_sha256': m.sha(raw), 'preparation_record': raw,
        'actual_preparation_exit': 0, 'source_recheck': source_recheck,
        'transport_request': broker}
    return NS(plain=package.plain, record=copy.deepcopy(package.record), directory=directory,
        broker=broker, checks=checks, kwargs=kwargs)


def run(case):
    return m.publish(case.directory, ORGANIZATION, case.plain, **case.kwargs)


def alter_preparation(case, change):
    change(case.record)
    raw = m.canonical(case.record)
    case.kwargs.update(preparation_record=raw, expected_preparation_sha256=m.sha(raw))


def report(case):
    return case.directory.values[m.REPORT]


def test_six_missing_objects_exact_24_dispatches_activation_last(case):
    result = run(case)
    assert result['complete'] is True and result['failure_code'] is None
    assert result['attempted_request_count'] == result['attempted_request_count_lower_bound'] == 24
    assert result['dispatch_count_known'] is True and case.checks == [0, 24]
    assert case.broker.calls[:6] == [('initial', i) for i in range(6)]
    assert case.broker.calls[6:] == [(phase, i) for i in range(6) for phase in ('recheck', 'put', 'verify')]
    assert report(case)['published_indices'] == report(case)['validated_indices'] == list(range(6))
    assert result['report_sha256'] == m.sha(m.canonical(report(case)))
    assert result['admission_sha256'] == m.sha(m.canonical(case.directory.values[m.ADMISSION]))
    assert all(result[name] is value for name, value in m.FLAGS.items())


def test_all_present_only_six_properties_no_set(case):
    case.broker.present = set(range(6))
    result = run(case)
    assert result['complete'] is True and result['attempted_request_count'] == 6
    assert case.broker.calls == [('initial', i) for i in range(6)]
    assert report(case)['published_indices'] == [] and case.checks == [0, 6]


@pytest.mark.parametrize('present', [(), (0,), (0, 2), (0, 1, 2, 3, 4)])
def test_partial_data_only_publishes_missing_with_activation_last(case, present):
    case.broker.present = set(present)
    result = run(case)
    missing = [i for i in range(6) if i not in present]
    assert result['complete'] is True and result['attempted_request_count'] == 6 + 3 * len(missing)
    assert report(case)['published_indices'] == missing
    assert case.broker.calls[-3:] == [('recheck', 5), ('put', 5), ('verify', 5)]


@pytest.mark.parametrize('present', [(5,), (0, 5), (0, 1, 2, 3, 5)])
def test_activation_present_with_missing_data_refuses_without_write(case, present):
    case.broker.present = set(present)
    result = run(case)
    assert result['complete'] is False and result['failure_code'] == 'activation_without_data'
    assert len(case.broker.calls) == 6 and m.ADMISSION not in case.directory.values


@pytest.mark.parametrize('field,bad', [('expected_package_sha256', 'f' * 64),
    ('expected_activation_sha256', 'f' * 64), ('expected_preparation_sha256', 'f' * 64),
    ('actual_preparation_exit', 2), ('actual_preparation_exit', True),
    ('actual_preparation_exit', None), ('source_recheck', None), ('transport_request', None),
    ('deadline', False), ('deadline', 0), ('deadline', float('inf'))])
def test_external_pin_exit_callback_deadline_fail_before_claim(case, field, bad):
    case.kwargs[field] = bad
    with pytest.raises((m.PlainStorageError, m.transport.PlainTransportError)):
        run(case)
    assert case.directory.values == {} and case.broker.calls == []


@pytest.mark.parametrize('bad', ['', '2' * 32, '1' * 31, b'1' * 32, True])
def test_organization_binding_before_claim(case, bad):
    with pytest.raises(m.PlainStorageError, match='organization'):
        m.publish(case.directory, bad, case.plain, **case.kwargs)
    assert case.directory.values == {} and case.broker.calls == []


@pytest.mark.parametrize('field,bad', [('schema', 'old'), ('complete', False), ('complete', 1),
    ('failure_code', 'failure'), ('attempt_consumed', False), ('expected_head', 'a' * 39),
    ('caller_sha256', 'bad'), ('profile_sha256', 'bad'),
    *[(name, True) for name in m.PREPARATION_FALSE]])
def test_preparation_shape_and_false_flags_required(case, field, bad):
    alter_preparation(case, lambda value: value.__setitem__(field, bad))
    with pytest.raises(m.PlainStorageError):
        run(case)
    assert case.directory.values == {} and case.broker.calls == []


@pytest.mark.parametrize('mutation', [
    lambda v: v['transport'].__setitem__('package_sha256', 'f' * 64),
    lambda v: v['projection'].__setitem__('package_sha256', 'f' * 64),
    lambda v: v['projection'].__setitem__('lineage_sha256', 'f' * 64),
    lambda v: v['projection'].__setitem__('activation_manifest_key', 'old/key'),
    lambda v: v['projection'].__setitem__('activation_manifest_sha256', 'f' * 64),
    lambda v: v['projection'].__setitem__('activation_manifest_byte_count', True),
    lambda v: v['projection'].__setitem__('upload_inventory_sha256', 'f' * 64),
    lambda v: v['projection']['upload_inventory'][0].__setitem__('content_sha256', 'f' * 64),
    lambda v: v['projection'].__setitem__('total_upload_byte_count', 1),
    lambda v: v['projection']['bridge'].__setitem__('parent_projection_sha256', 'f' * 64),
    lambda v: v['projection']['bridge'].__setitem__('historical_d15_admission_sha256', 'f' * 64),
    lambda v: v['projection']['bridge'].__setitem__('source_mapping', {}),
    lambda v: v['projection'].__setitem__('bridge_sha256', 'f' * 64),
    lambda v: v['projection']['source_files'][0].__setitem__('byte_count', True),
    lambda v: v['projection']['source_files'][0].__setitem__('content_sha256', 'f' * 63),
    lambda v: v['projection']['source_files'].pop(),
])
def test_preparation_actual_transport_and_projection_bridge_bound(case, mutation):
    alter_preparation(case, mutation)
    with pytest.raises(m.PlainStorageError):
        run(case)
    assert case.directory.values == {} and case.broker.calls == []


@pytest.mark.parametrize('raw', [b'{}', b'{bad}\n', b'[]\n', b'\xff', b'{}\n\n', b'x' * (128 * 1024 + 1)])
def test_preparation_finite_canonical_bytes_required(case, raw):
    case.kwargs.update(preparation_record=raw, expected_preparation_sha256=m.sha(raw))
    with pytest.raises(m.PlainStorageError): run(case)
    assert case.directory.values == {} and case.broker.calls == []


@pytest.mark.parametrize('point', ['initial', 'final'])
@pytest.mark.parametrize('behavior', ['raise', 'bool'])
def test_required_source_recheck_failure_never_admits(case, point, behavior):
    calls = []
    def recheck(plain):
        calls.append(plain)
        if len(calls) == (1 if point == 'initial' else 2):
            if behavior == 'raise': raise RuntimeError('private exception must not escape')
            return True
    case.kwargs['source_recheck'] = recheck
    result = run(case)
    assert result['complete'] is False and m.ADMISSION not in case.directory.values
    assert len(case.broker.calls) == (0 if point == 'initial' else 24)
    assert 'private exception' not in m.canonical(report(case)).decode()


@pytest.mark.parametrize('phase,index,expected', [('recheck', 0, 'recheck_changed'),
    ('verify', 0, 'verification_failed')])
def test_race_or_missing_after_set_refuses_no_retry(case, phase, index, expected):
    case.broker.hook = lambda p, i, row: packet(p, row, absent=p == 'verify') if (p, i) == (phase, index) else None
    result = run(case)
    assert result['complete'] is False and result['failure_code'] == expected
    assert case.broker.calls[-1] == (phase, index)
    assert m.ADMISSION not in case.directory.values


@pytest.mark.parametrize('attempted', [False, True])
def test_finite_refusal_records_confirmed_dispatch_count(case, attempted):
    case.broker.hook = lambda p, i, row: packet(p, row, failure='response_transport', attempted=attempted) if i == 2 else None
    result = run(case)
    assert result['complete'] is False and result['failure_code'] == 'response_transport'
    assert result['dispatch_count_known'] is True
    assert result['attempted_request_count'] == result['attempted_request_count_lower_bound'] == 2 + int(attempted)
    assert len(case.broker.calls) == 3 and m.ADMISSION not in case.directory.values


@pytest.mark.parametrize('kind', ['lost', 'malformed'])
def test_lost_or_malformed_reply_never_reports_zero_or_known_count(case, kind):
    def hook(phase, index, row):
        if index != 2: return None
        if kind == 'lost': raise TimeoutError('SECRET token provider text')
        return {'unexpected': 'SECRET token provider text'}
    case.broker.hook = hook
    result = run(case)
    assert result['complete'] is False and result['attempted_request_count'] is None
    assert result['dispatch_count_known'] is False and result['attempted_request_count_lower_bound'] == 2
    assert report(case)['requests'][-1]['attempted'] is None
    assert 'SECRET' not in m.canonical(report(case)).decode() and len(case.broker.calls) == 3


@pytest.mark.parametrize('field,bad', [('attempted', 1), ('attempted', False), ('http_status', True),
    ('http_status', 201), ('object_state', 'published'), ('absence_template_index', True),
    ('failure_code', 'raw provider text'), ('observation', None), ('error_shape', {'raw': 'x'})])
def test_packet_field_forgery_refuses(case, field, bad):
    row = m._inventory(case.plain, case.plain.package_sha256, case.plain.activation_manifest_sha256)[0][0]
    value = packet('initial', row, absent=True)
    value[field] = bad
    with pytest.raises((m.PlainStorageError, m.wire.StorageRecoveryError)):
        m.validate_dispatch_packet(value, 'initial', row)


@pytest.mark.parametrize('field,bad', [('api_success', True), ('error_count', 0),
    ('metadata_present', True), ('errors_present', False), ('success_with_errors', True)])
def test_absence_packet_coherence_required(case, field, bad):
    row = m._inventory(case.plain, case.plain.package_sha256, case.plain.activation_manifest_sha256)[0][0]
    value = packet('initial', row, absent=True)
    value['observation'][field] = bad
    with pytest.raises((m.PlainStorageError, m.wire.StorageRecoveryError)):
        m.validate_dispatch_packet(value, 'initial', row)


@pytest.mark.parametrize('choice', range(len(m.wire.ABSENCE_TEMPLATES)))
def test_exact_frozen_absence_variants_supported(case, choice):
    row = m._inventory(case.plain, case.plain.package_sha256, case.plain.activation_manifest_sha256)[0][0]
    value = packet('initial', row, absent=True, choice=choice)
    assert m.validate_dispatch_packet(value, 'initial', row) == value
    value['error_shape']['suffix_characters'] += 1
    with pytest.raises(m.PlainStorageError): m.validate_dispatch_packet(value, 'initial', row)


@pytest.mark.parametrize('name', [m.CLAIM, m.REPORT, m.ADMISSION, m._stem(0) + '-intent.json', m._stem(0) + '-observed.json'])
def test_durable_write_failures_cannot_return_admission(case, name):
    case.directory.fail_write = name
    if name in (m.CLAIM, m.REPORT, m.ADMISSION):
        with pytest.raises(m.PlainStorageError): run(case)
    else:
        result = run(case)
        assert result['complete'] is False and result['admission_sha256'] is None
    assert m.ADMISSION not in case.directory.values
    if name == m.CLAIM or name.endswith('-intent.json'): assert not case.broker.calls


@pytest.mark.parametrize('name', [m.CLAIM, m.REPORT, m.ADMISSION])
def test_exact_readbacks_required_and_late_failure_is_not_success(case, name):
    case.directory.fail_read = name
    if name == m.CLAIM:
        result = run(case)
        assert result['complete'] is False
    else:
        with pytest.raises(m.PlainStorageError): run(case)
    if name == m.ADMISSION:
        assert report(case)['complete'] is True  # Actual exit remains decisive.
    else:
        assert m.ADMISSION not in case.directory.values


def test_duplicate_claim_cannot_repeat_network(case):
    run(case)
    before = list(case.broker.calls)
    with pytest.raises(m.PlainStorageError, match='journal'): run(case)
    assert case.broker.calls == before


def test_own_control_census_rejects_unknown_control_before_admission(case):
    case.directory.extra_names = [m.STEM + 'unexpected.json']
    with pytest.raises(m.PlainStorageError, match='request_census'): run(case)
    assert m.ADMISSION not in case.directory.values


def test_helper_never_calls_old_transport_entrypoints_or_reads_credentials(case, monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('forbidden frozen operational path')
    monkeypatch.setattr(m, 'wire', NS(**{**vars(m.wire), '_transport': forbidden,
        'recover': forbidden, 'require_admission': forbidden}))
    assert run(case)['complete'] is True


def test_packet_return_is_detached(case):
    row = m._inventory(case.plain, case.plain.package_sha256, case.plain.activation_manifest_sha256)[0][0]
    value = packet('initial', row, absent=True)
    accepted = m.validate_dispatch_packet(value, 'initial', row)
    value['observation']['redacted_provider_reasons'].clear()
    assert accepted['observation']['error_count'] == len(accepted['observation']['redacted_provider_reasons']) == 1


@pytest.mark.parametrize('phase', [None, True, 'get', 'delete', 'list'])
def test_packet_unsupported_phase_refuses(case, phase):
    row = m._inventory(case.plain, case.plain.package_sha256, case.plain.activation_manifest_sha256)[0][0]
    with pytest.raises(m.PlainStorageError, match='dispatch_packet'):
        m.validate_dispatch_packet(packet('initial', row), phase, row)


@pytest.mark.parametrize('kind', ['copied', 'mutated'])
def test_genuine_unchanged_capability_required_before_claim(case, kind):
    if kind == 'copied':
        case.plain = copy.copy(case.plain)
        with pytest.raises(m.transport.PlainTransportError): run(case)
    else:
        old = case.plain.record_bytes
        try:
            object.__setattr__(case.plain, 'record_bytes', bytearray(old))
            with pytest.raises(m.transport.PlainTransportError): run(case)
        finally:
            object.__setattr__(case.plain, 'record_bytes', old)
    assert not case.directory.values and not case.broker.calls


def test_final_source_check_restored_after_callback_cannot_make_boolean_authority(case):
    original = case.kwargs['source_recheck']
    calls = []
    def recheck(plain):
        original(plain)
        calls.append(plain)
        return None if len(calls) == 1 else False
    case.kwargs['source_recheck'] = recheck
    result = run(case)
    assert result['complete'] is False and result['failure_code'] == 'source_check_result'
    assert m.ADMISSION not in case.directory.values
