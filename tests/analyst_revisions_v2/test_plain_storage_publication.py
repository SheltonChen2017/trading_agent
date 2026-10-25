"""Synthetic caller/broker boundaries; native denial required by lane policy."""
import copy
import hashlib
import os
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace as NS

import pytest

from scripts import run_arv2_plain_storage_publication as m
from scripts import arv2_newrule_plain_storage as helper
from scripts import arv2_plain_storage_rpc as rpc
from tests.analyst_revisions_v2 import test_newrule_plain_storage as fixture


ORG = '1' * 32
ARGS = NS(operation='publish', expected_head='a' * 40, caller_sha256='b' * 64,
          control_fd=None, request_fd=None, reply_fd=None, deadline=None)


@pytest.fixture(autouse=True)
def forbid_operations(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError('operational boundary is forbidden in synthetic tests')
    monkeypatch.setattr(m.prep, 'construct', forbidden)
    monkeypatch.setattr(m, 'read_preparation', forbidden)
    monkeypatch.setattr(helper.wire, '_transport', forbidden)
    monkeypatch.setattr(helper.wire.old, '_client', forbidden)
    monkeypatch.setattr(m, 'modules', lambda: (helper, rpc, NS(require_safe_environment=lambda: None)))


@pytest.fixture
def ready(monkeypatch):
    payloads = tuple(('synthetic-%d\n' % i).encode() for i in range(6))
    expected = {**m.EXPECTED, 'total_byte_count': sum(map(len, payloads)),
        'activation_sha256': m.sha(payloads[-1])}
    monkeypatch.setattr(m, 'EXPECTED', expected)
    prefix = 'arv2/newrule-plain-v1/' + expected['parent_proof_sha256'][:24] + '/'
    inventory = []
    for i, role in enumerate(m.ROLES):
        name = 'evaluator-manifest.json' if i == 0 else 'transport-manifest.json' if i == 5 else role + '-0000.jsonl'
        inventory.append({'schema': 'arv2-newrule-plain-upload-object-v1', 'role': role,
            'ordinal': 0, 'object_store_key': prefix + name, 'relative_path': name,
            'byte_count': len(payloads[i]), 'content_sha256': m.sha(payloads[i]),
            'record_count': 1, 'compression': 'identity', 'activation_manifest': i == 5})
    derived = {'project_source_manifest_sha256': 'c' * 64,
        'activation_manifest_key': inventory[-1]['object_store_key'],
        'activation_manifest_byte_count': inventory[-1]['byte_count']}
    header = {'kind': 'ready', 'binding_sha256': m.sha(m.canonical(m.binding(ARGS))),
        'preparation_sha256': m.PREPARATION_SHA256, 'summary': expected,
        'inventory': inventory, 'inventory_sha256': m.sha(m.canonical(inventory)),
        'projection_binding': derived}
    return NS(header=header, payloads=payloads, summary={**expected, **derived})


def rehash_ready(value):
    value['inventory_sha256'] = m.sha(m.canonical(value['inventory']))


def test_ready_has_exact_selected_source_and_new_control(ready):
    rows = m.validate_ready(ready.header, ARGS)
    assert len(rows) == 6 and rows[-1][3] is True
    assert all(row[1] == m.sha(payload) for row, payload in zip(rows, ready.payloads))
    assert m.PREPARATION_HEAD == 'd95198e014926ba1a578db61a5c21c4887293a26'
    assert str(m.CONTROL).endswith('/newrule_plain_storage/R322-20261025-B')
    assert m.HELPER_SHA256 == m.sha(Path(helper.__file__).read_bytes())
    assert m.RPC_SHA256 == m.sha(Path(rpc.__file__).read_bytes())
    assert m.profile()['storage_dispatch_limit'] == 24
    assert m.profile()['organization_projects'] == [37165262, 38364439]
    assert m.profile()['storage_endpoints'] == ['object/properties', 'object/set']


@pytest.mark.parametrize('field,value', [('kind', 'other'), ('binding_sha256', '0' * 64),
    ('preparation_sha256', '0' * 64), ('inventory_sha256', '0' * 64), ('summary', {}), ('inventory', [])])
def test_ready_header_refusals(ready, field, value):
    ready.header[field] = value
    with pytest.raises(m.Refused):
        m.validate_ready(ready.header, ARGS)


@pytest.mark.parametrize('field,value', [('schema', 'old'), ('role', 'other'), ('ordinal', True),
    ('relative_path', '../old.json'), ('object_store_key', 'old/object'), ('compression', 'gzip'),
    ('activation_manifest', True), ('byte_count', True), ('byte_count', 0),
    ('byte_count', 32 * 1024 * 1024 + 1), ('content_sha256', 'x'), ('record_count', True),
    ('record_count', 0), ('extra', 0)])
def test_ready_descriptor_refusals_even_with_updated_inventory_hash(ready, field, value):
    ready.header['inventory'][0][field] = value
    rehash_ready(ready.header)
    with pytest.raises(m.Refused):
        m.validate_ready(ready.header, ARGS)


@pytest.mark.parametrize('change', ['order', 'activation', 'total', 'row_bound', 'derived_key',
    'derived_size', 'derived_hash', 'derived_extra'])
def test_ready_cross_field_refusals(ready, change):
    rows = ready.header['inventory']
    if change == 'order': rows[0], rows[1] = rows[1], rows[0]
    if change == 'activation': rows[-1]['content_sha256'] = '0' * 64
    if change == 'total': rows[0]['byte_count'] += 1
    if change == 'row_bound': rows[1]['byte_count'] = 16 * 1024 * 1024 + 1
    if change == 'derived_key': ready.header['projection_binding']['activation_manifest_key'] = 'old'
    if change == 'derived_size': ready.header['projection_binding']['activation_manifest_byte_count'] = True
    if change == 'derived_hash': ready.header['projection_binding']['project_source_manifest_sha256'] = 'bad'
    if change == 'derived_extra': ready.header['projection_binding']['extra'] = True
    rehash_ready(ready.header)
    with pytest.raises(m.Refused):
        m.validate_ready(ready.header, ARGS)


@pytest.mark.parametrize('kind', ['request', 'done'])
def test_exact_flow_union_roundtrip(kind):
    value = ({'kind': 'done', 'binding_sha256': 'a' * 64, 'result_sha256': 'b' * 64}
        if kind == 'done' else {'kind': 'storage_request', 'ordinal': 0, 'phase': 'initial',
            'index': 0, 'endpoint': 'object/properties', 'key': 'synthetic', 'request_sha256': 'c' * 64})
    encoded = rpc.encode_frame(m.flow_frame(value), b'', header_fields=m.FLOW_FIELDS)
    header, payload = rpc.decode_frame(encoded, header_fields=m.FLOW_FIELDS)
    assert m.flow_header(header) == value and payload == b''
    inactive = next(iter(m.FLOW_FIELDS - set(value)))
    header[inactive] = False
    with pytest.raises(m.Refused): m.flow_header(header)


@pytest.mark.parametrize('header', [{}, {'kind': 'other'}, [], None])
def test_flow_noninventory_refuses(header):
    with pytest.raises(m.Refused): m.flow_header(header)


@pytest.fixture
def broker(ready, monkeypatch):
    rows = m.validate_ready(ready.header, ARGS)
    directory = fixture.Directory()
    case = NS(ready=ready, rows=rows, directory=directory, present=set(), calls=[], hook=None)

    def transport(_api, endpoint, body, _content_type, organization, key, entry, state, _deadline):
        assert organization == ORG and endpoint in ('object/properties', 'object/set')
        assert key == rows[entry['index']][0]
        state['attempted_request_count'] += 1
        entry['attempted'], entry['http_status'] = True, 200
        case.calls.append((entry['phase'], entry['index']))
        if case.hook: case.hook(entry)
        if entry['phase'] == 'put': case.present.add(entry['index'])
        packet = fixture.packet(entry['phase'], rows[entry['index']], absent=entry['index'] not in case.present)
        entry.update(packet)
        return {'success': entry['index'] in case.present, 'errors': []}

    def properties(_response, row, _payload):
        index = rows.index(row)
        return ('present', None) if index in case.present else ('absent', 0)

    monkeypatch.setattr(helper.wire, '_transport', transport)
    monkeypatch.setattr(helper.wire, '_properties_state', properties)
    case.value = m.Broker(rows, ORG, object(), directory, time.monotonic() + 100)
    return case


def request(case, *, phase=None, index=None):
    phase, index = case.value.pending if phase is None else (phase, index)
    row, payload = case.rows[index], case.ready.payloads[index]
    endpoint, body, _ = helper.wire._body(phase, ORG, row, payload)
    return {'kind': 'storage_request', 'ordinal': case.value.ordinal, 'phase': phase,
        'index': index, 'endpoint': endpoint, 'key': row[0], 'request_sha256': m.sha(body)}, payload


@pytest.mark.parametrize('present,count', [((), 24), (tuple(range(6)), 6), ((0, 2, 4), 15)])
def test_complete_broker_exact_sequence(broker, present, count):
    broker.present.update(present)
    while broker.value.pending is not None:
        response = broker.value.request(*request(broker))
        assert response['packet']['failure_code'] is None
    assert not broker.value.failed and broker.value.dispatches == broker.value.ordinal == count
    assert broker.calls[:6] == [('initial', i) for i in range(6)]
    assert broker.calls[6:] == [(phase, i) for i in range(6) if i not in present
        for phase in ('recheck', 'put', 'verify')]
    assert len(broker.directory.values) == 2 * count
    with pytest.raises(m.Refused): broker.value.request(*request(broker, phase='initial', index=0))


@pytest.mark.parametrize('field,value', [('ordinal', True), ('ordinal', 1), ('index', True),
    ('index', 6), ('phase', 'put'), ('endpoint', 'backtests/create'), ('endpoint', 'object/get'),
    ('key', 'old/object'), ('request_sha256', '0' * 64), ('extra', False)])
def test_broker_refuses_before_dispatch(broker, field, value):
    header, payload = request(broker)
    header[field] = value
    with pytest.raises(m.Refused): broker.value.request(header, payload)
    assert not broker.calls and not broker.directory.values


@pytest.mark.parametrize('payload', [b'wrong', bytearray(b'wrong'), b''])
def test_broker_opaque_payload_pin_binds_all_phases(broker, payload):
    header, _ = request(broker)
    with pytest.raises(m.Refused): broker.value.request(header, payload)
    assert not broker.calls


def test_activation_present_with_missing_data_stops(broker):
    broker.present = {5}
    for _ in range(6): broker.value.request(*request(broker))
    assert broker.value.failed and broker.value.dispatches == 6
    with pytest.raises(m.Refused): broker.value.request(*request(broker))


def test_absence_recheck_drift_never_puts(broker):
    for _ in range(6): broker.value.request(*request(broker))
    broker.present.add(0)
    broker.value.request(*request(broker))
    assert broker.value.failed and broker.value.dispatches == 7
    with pytest.raises(m.Refused): broker.value.request(*request(broker))


def test_failed_transport_retains_count_and_finite_failure(broker):
    def fail(_entry): raise RuntimeError('SECRET must never be retained')
    broker.hook = fail
    response = broker.value.request(*request(broker))
    assert response['packet']['failure_code'] == 'unknown_exception'
    assert broker.value.dispatches == 1 and broker.value.failed
    assert b'SECRET' not in m.canonical(broker.directory.values)
    with pytest.raises(m.Refused): broker.value.request(*request(broker))


def success_result(count=6):
    return {'complete': True, 'failure_code': None, 'report_sha256': 'd' * 64,
        'report_byte_count': 100, 'attempted_request_count': count,
        'attempted_request_count_lower_bound': count, 'dispatch_count_known': True,
        'admission_sha256': 'e' * 64, 'admission_byte_count': 100, **helper.FLAGS}


def census(count=6):
    return NS(failed=False, pending=None, initial=['present'] * 6, dispatches=count, ordinal=count)


def test_valid_worker_result_requires_actual_exit_and_census():
    value = success_result()
    assert m.validate_result(value, actual_worker_exit=0, broker=census()) == value


@pytest.mark.parametrize('exit_value', [None, 2, 1, True, False, '0'])
def test_worker_actual_exit_not_report_boolean(exit_value):
    with pytest.raises(m.Refused): m.validate_result(success_result(), actual_worker_exit=exit_value, broker=census())


@pytest.mark.parametrize('field,value', [('attempted_request_count', True), ('attempted_request_count', 7),
    ('attempted_request_count_lower_bound', True), ('dispatch_count_known', False),
    ('report_sha256', 'bad'), ('report_byte_count', 0), ('admission_byte_count', True),
    ('admission_sha256', None), ('extra', None), ('complete', 1), ('backtest_created', True)])
def test_worker_receipt_refusals(field, value):
    result = success_result(); result[field] = value
    with pytest.raises(m.Refused): m.validate_result(result, actual_worker_exit=0, broker=census())


def test_unknown_dispatch_failure_keeps_lower_bound():
    value = {**success_result(), 'complete': False, 'failure_code': 'dispatch_packet',
        'dispatch_count_known': False, 'attempted_request_count': None,
        'attempted_request_count_lower_bound': 5, 'admission_sha256': None, 'admission_byte_count': None}
    assert m.validate_result(value, actual_worker_exit=2, broker=census()) == value


def output(ready):
    result = {'complete': True, 'failure_code': None, 'report': {'sha256': 'f' * 64, 'byte_count': 500},
        'organization_binding': {'sha256': '9' * 64, 'byte_count': 300},
        'worker_result_file': m.worker_result_pin(m.binding(ARGS), success_result()),
        'worker_failure_code': None,
        'worker_result': success_result(), 'summary': ready.summary, 'attempt_consumed': True,
        'organization_dispatches': 2, 'storage_dispatches': 6, 'worker_exit': 0}
    return {'schema': m.SCHEMA, 'operation': 'publish', 'binding': m.binding(ARGS),
        'complete': True, 'failure_code': None, 'result': result, **m.FALSE_FLAGS}


def check_output(value, exit_value=0):
    return m.validate_output(m.canonical(value) + b'\n', actual_exit=exit_value, expected_binding=m.binding(ARGS))


def test_success_output_validates_both_exits_and_authentication(ready):
    value = output(ready)
    assert check_output(value) == value
    for exit_value in (None, False, 2):
        with pytest.raises(m.Refused): check_output(value, exit_value)


@pytest.mark.parametrize('field,value', [('worker_exit', False), ('worker_exit', 2),
    ('organization_dispatches', True), ('organization_dispatches', 1), ('storage_dispatches', True),
    ('storage_dispatches', 25), ('attempt_consumed', False), ('report', None),
    ('worker_result', None), ('worker_result_file', None), ('worker_failure_code', 'source'),
    ('summary', None), ('organization_binding', None), ('extra', False)])
def test_success_output_nested_refusals(ready, field, value):
    envelope = output(ready); envelope['result'][field] = value
    with pytest.raises(m.Refused): check_output(envelope)


def test_success_output_does_not_accept_nested_failed_receipt(ready):
    value = output(ready)
    value['result']['worker_result']['complete'] = False
    with pytest.raises(m.Refused): check_output(value)


@pytest.mark.parametrize('raw', [b'{}', b'{}\n', b'{}\n\ntrailing', b'{}\n\n\n', b'', b'x' * (m.MAX_OUTPUT + 1)])
def test_output_framing_refuses(raw):
    with pytest.raises(m.Refused): m.validate_output(raw, actual_exit=0, expected_binding=m.binding(ARGS))


def test_missing_credentials_refuse_before_claim(monkeypatch):
    monkeypatch.delenv('QC_USER_ID', raising=False)
    monkeypatch.delenv('QC_API_TOKEN', raising=False)
    claims = []
    monkeypatch.setattr(m, 'Store', lambda **kw: claims.append(kw))
    with pytest.raises(m.Refused, match='^credentials$'): m.publish(ARGS, time.monotonic() + 100)
    assert claims == []


def test_store_exclusive_bound_retained_metadata(tmp_path, monkeypatch):
    root = tmp_path / 'artifacts'; root.mkdir()
    monkeypatch.setattr(m, 'CONTROL', root / 'new' / 'one')
    with m.Store(create=True) as store:
        pin = store.write('claim.json', {'synthetic': True})
        assert pin == {'sha256': m.sha(m.canonical({'synthetic': True})), 'byte_count': 19}
        assert store.read('claim.json') == {'synthetic': True}
        with pytest.raises(FileExistsError): store.write('claim.json', {'synthetic': True})
        os.chmod(m.CONTROL / 'claim.json', 0o644)
        with pytest.raises(m.Refused): store.verify()
    with pytest.raises(FileExistsError): m.Store(create=True)


@pytest.mark.parametrize('name', ['../old.json', 'bad.txt', 'X.json', '', 'old/claim.json'])
def test_store_leaf_names_refused(tmp_path, monkeypatch, name):
    root = tmp_path / 'artifacts'; root.mkdir()
    monkeypatch.setattr(m, 'CONTROL', root / 'new' / 'one')
    with m.Store(create=True) as store:
        with pytest.raises(m.Refused): store.write(name, {})


def test_store_broker_and_worker_maximum_journals_fit(tmp_path, monkeypatch):
    root = tmp_path / 'artifacts'; root.mkdir()
    monkeypatch.setattr(m, 'CONTROL', root / 'new' / 'one')
    with m.Store(create=True) as store:
        for i in range(110): store.write(f'synthetic-{i:03d}.json', {'i': i})
        assert len(store.names()) == 110


def test_native_worker_policy_does_not_permit_network_or_keychain():
    policy = m.sandbox()
    assert '(deny network*)' in policy and '/usr/bin/security' in policy
    assert '/Users/sheltonchen/Library/Keychains' in policy
    assert str(m.CONTROL) in policy and str(m.ROOT / '.pytest_cache') in policy


class HostileError(Exception):
    def __str__(self): raise AssertionError('must not stringify')
    def __repr__(self): raise AssertionError('must not repr')


def test_finite_failure_does_not_render_unknown_exception():
    assert m.finite(HostileError('secret')) == 'unknown_exception'
    assert m.finite(m.Refused('payload')) == 'payload'
    assert m.finite(m.Refused('secret')) == 'unknown_exception'


def test_bounded_canonical_parse_and_deadline():
    assert m.parse(b'{"x":1}\n') == {'x': 1}
    for raw in (b'{"x":1,"x":1}\n', b'{ "x":1}\n', b'[]\n', b'{"x":NaN}\n'):
        with pytest.raises((m.Refused, m.prep.Refused)): m.parse(raw)
    for deadline in (None, True, float('nan'), float('inf'), time.monotonic() - 1, time.monotonic() + 700):
        with pytest.raises(m.Refused): m.remaining(deadline)


@pytest.mark.parametrize('bad', ['owner', 'public', 'language', 'project', 'organization', 'rows', 'errors'])
def test_organization_scope_is_exact_and_finite(monkeypatch, bad):
    directory, state = fixture.Directory(), {'organization_dispatches': 0}
    seen = []
    def validate_org(value): m.require(value == ORG, 'organization')
    monkeypatch.setattr(helper, 'access', NS(_organization=validate_org, ORGANIZATION_SHA256=m.sha(ORG.encode())))
    def ask(endpoint, body):
        seen.append((endpoint, body))
        row = {'projectId': body['projectId'], 'owner': True, 'language': 'Py', 'organizationId': ORG}
        packet = {'success': True, 'projects': [row]}
        if bad == 'owner': row['owner'] = False
        if bad == 'public': row['public'] = True
        if bad == 'language': row['language'] = 'C#'
        if bad == 'project': row['projectId'] = 1
        if bad == 'organization': row['organizationId'] = '2' * 32
        if bad == 'rows': packet['projects'].append(dict(row))
        if bad == 'errors': packet['errors'] = ['synthetic-only']
        return packet
    with pytest.raises(m.Refused): m.organization(NS(request=ask), directory, state)
    assert state['organization_dispatches'] == 1 and seen == [('projects/read', {'projectId': m.REFERENCE})]
    assert b'synthetic-only' not in m.canonical(directory.values)


def test_organization_exact_two_reference_reads(monkeypatch):
    directory, state, calls = fixture.Directory(), {'organization_dispatches': 0}, []
    monkeypatch.setattr(helper, 'access', NS(_organization=lambda value: m.require(value == ORG, 'organization'),
        ORGANIZATION_SHA256=m.sha(ORG.encode())))
    def ask(endpoint, body):
        calls.append((endpoint, body))
        return {'success': True, 'projects': [{'projectId': body['projectId'], 'owner': True,
            'language': 'Py', 'organizationId': ORG}]}
    assert m.organization(NS(request=ask), directory, state) == ORG
    assert calls == [('projects/read', {'projectId': project}) for project in (m.REFERENCE, m.PROJECT)]
    assert state['organization_dispatches'] == 2
    assert ORG.encode() not in m.canonical(directory.values)


def test_publish_mocked_child_scope_and_success(broker, monkeypatch):
    """Complete parent orchestration with no OS child or operational boundary."""
    directory = broker.directory
    class Context:
        fd = 87
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def write(self, *args): return {'sha256': 'f' * 64, 'byte_count': 100} if directory.write(*args) is None else None
        def verify(self): directory.verify()
    captured, sent = [], []
    class Process:
        stdout = NS(close=lambda: None)
        stderr = NS(close=lambda: None)
        def poll(self): return 0
    def spawn(command, **kwargs):
        captured.append((command, kwargs))
        return Process()
    frames = [(broker.ready.header, b'')]
    for i in range(6):
        header, payload = request(broker, phase='initial', index=i)
        header['ordinal'] = i
        frames.append((m.flow_frame(header), payload))
    result = success_result()
    frames.append((m.flow_frame({'kind': 'done', 'binding_sha256': broker.ready.header['binding_sha256'],
        'result_sha256': m.sha(m.canonical(result))}), b''))
    fake_rpc = NS(receive_frame=lambda *_a, **_k: frames.pop(0),
        send_frame=lambda *_a, **_k: sent.append((_a, _k)), reject_pending=lambda *_a: None)
    monkeypatch.setattr(m, 'modules', lambda: (helper, fake_rpc, NS(require_safe_environment=lambda: None)))
    monkeypatch.setattr(m, 'Store', lambda **_kw: Context())
    monkeypatch.setattr(m.subprocess, 'Popen', spawn)
    monkeypatch.setattr(helper.wire.old, '_client', lambda: object())
    monkeypatch.setattr(m, 'organization', lambda _a, _b, state: state.update(organization_dispatches=2) or ORG)
    monkeypatch.setattr(m, 'preflight', lambda *_a: None)
    monkeypatch.setattr(m, 'validate_ready_preparation', lambda *_a: None)
    monkeypatch.setattr(m, 'complete_census', lambda *_a, **_kw: None)
    monkeypatch.setattr(helper, 'access', NS(_organization=lambda value: m.require(value == ORG, 'organization'),
        ORGANIZATION_SHA256=m.sha(ORG.encode())))
    monkeypatch.setattr(m, '_channels', lambda *_a: (0, {'schema': m.SCHEMA, 'operation': 'worker',
        'binding': m.binding(ARGS), 'result': result, **m.FALSE_FLAGS}))
    monkeypatch.setenv('QC_USER_ID', 'synthetic-user')
    monkeypatch.setenv('QC_API_TOKEN', 'synthetic-token')
    broker.present.update(range(6))
    value = m.publish(ARGS, time.monotonic() + 100)
    assert value['complete'] is True and value['worker_exit'] == 0 and value['storage_dispatches'] == 6
    assert value['summary'] == broker.ready.summary and value['attempt_consumed'] is True
    assert len(sent) == 7 and len(captured) == 1 and not frames
    command, kwargs = captured[0]
    assert command[:3] == ['/usr/bin/sandbox-exec', '-p', m.sandbox()]
    assert 'QC_USER_ID' not in kwargs['env'] and 'QC_API_TOKEN' not in kwargs['env']
    assert kwargs['pass_fds'][0] == 87 and len(kwargs['pass_fds']) == 3
    assert kwargs['cwd'] == m.ROOT and kwargs['stdin'] == subprocess.DEVNULL


@pytest.mark.parametrize('failure_at', ['receive', 'organization', 'dispatch', 'late_output'])
def test_parent_failure_preserves_counts_and_no_retry(broker, monkeypatch, failure_at):
    directory = broker.directory
    class Context:
        fd = 87
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def write(self, *args): directory.write(*args); return {'sha256': 'f' * 64, 'byte_count': 100}
        def verify(self): directory.verify()
    class Process:
        stdout = NS(close=lambda: None)
        stderr = NS(close=lambda: None)
        killed = 0
        def poll(self): return -9 if self.killed else None
        def kill(self): self.killed += 1
        def wait(self, timeout): return -9
    process = Process()
    frames = [(broker.ready.header, b'')]
    for i in range(6):
        header, payload = request(broker, phase='initial', index=i)
        header['ordinal'] = i
        frames.append((m.flow_frame(header), payload))
    frames.append((m.flow_frame({'kind': 'done', 'binding_sha256': broker.ready.header['binding_sha256'],
        'result_sha256': m.sha(m.canonical(success_result()))}), b''))
    def receive(*_a, **_kw):
        if failure_at == 'receive': raise RuntimeError('SECRET')
        return frames.pop(0)
    def organization(_api, _store, state):
        state['organization_dispatches'] = 1 if failure_at == 'organization' else 2
        if failure_at == 'organization': raise RuntimeError('SECRET')
        return ORG
    def channels(*_args): raise RuntimeError('SECRET')
    fake_rpc = NS(receive_frame=receive, send_frame=lambda *_a, **_kw: None, reject_pending=lambda *_a: None)
    monkeypatch.setattr(m, 'modules', lambda: (helper, fake_rpc, NS(require_safe_environment=lambda: None)))
    monkeypatch.setattr(m, 'Store', lambda **_kw: Context())
    monkeypatch.setattr(m.subprocess, 'Popen', lambda *_a, **_kw: process)
    monkeypatch.setattr(helper.wire.old, '_client', lambda: object())
    monkeypatch.setattr(m, 'organization', organization)
    monkeypatch.setattr(m, '_channels', channels)
    monkeypatch.setattr(m, 'validate_ready_preparation', lambda *_a: None)
    monkeypatch.setattr(helper, 'access', NS(_organization=lambda value: m.require(value == ORG, 'organization'),
        ORGANIZATION_SHA256=m.sha(ORG.encode())))
    monkeypatch.setenv('QC_USER_ID', 'synthetic-user'); monkeypatch.setenv('QC_API_TOKEN', 'synthetic-token')
    broker.present.update(range(6))
    if failure_at == 'dispatch':
        def fail(_entry): raise RuntimeError('SECRET')
        broker.hook = fail
    value = m.publish(ARGS, time.monotonic() + 100)
    assert value['complete'] is False and value['attempt_consumed'] is True
    assert value['storage_dispatches'] == {'receive': 0, 'organization': 0, 'dispatch': 1, 'late_output': 6}[failure_at]
    assert value['organization_dispatches'] == {'receive': 0, 'organization': 1, 'dispatch': 2, 'late_output': 2}[failure_at]
    assert value['worker_exit'] == -9 and process.killed == 1
    assert b'SECRET' not in m.canonical(value) and 'broker-failure.json' in directory.values


def test_native_tiny_child_framing_and_bounded_channels(tmp_path):
    """Real synthetic Python subprocess; not the operational worker/caller."""
    request_read, request_write = os.pipe()
    reply_read, reply_write = os.pipe()
    source = (
        "import os,sys,time\n"
        "from scripts import arv2_plain_storage_rpc as r\n"
        "a,b=map(int,sys.argv[1:]); d=time.monotonic()+5\n"
        "r.send_frame(a,{'kind':'synthetic'},b'opaque\\x00bytes',d,header_fields={'kind'})\n"
        "h,p=r.receive_frame(b,d,header_fields={'kind'}); assert h=={'kind':'reply'} and p==b''\n"
        "os.close(a);os.close(b);sys.stdout.write('{\\\"synthetic\\\":true}\\n\\n')\n"
    )
    child_env = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C',
        'TMPDIR': str(tmp_path), 'PYTHONPYCACHEPREFIX': str(tmp_path), 'PYTHONDONTWRITEBYTECODE': '1'}
    # The outer test invocation's native sandbox is inherited; this test does
    # not need or claim a second sandbox installation inside that process.
    process = subprocess.Popen([str(m.prep.frozen.PYTHON), '-B',
        '-c', source, str(request_write), str(reply_read)], cwd=m.ROOT, env=child_env,
        pass_fds=(request_write, reply_read), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    os.close(request_write); os.close(reply_read)
    try:
        deadline = time.monotonic() + 5
        header, payload = rpc.receive_frame(request_read, deadline, header_fields={'kind'})
        assert header == {'kind': 'synthetic'} and payload == b'opaque\x00bytes'
        rpc.send_frame(reply_write, {'kind': 'reply'}, b'', deadline, header_fields={'kind'})
        assert m._channels(process, deadline) == (0, {'synthetic': True})
        rpc.reject_pending(request_read, deadline)
    finally:
        if process.poll() is None: process.kill(); process.wait(timeout=5)
        process.stdout.close(); process.stderr.close()
        os.close(request_read); os.close(reply_write)


@pytest.mark.parametrize('count', [6, 9, 12, 15, 18, 21, 24])
def test_exact_whole_control_census(count):
    names = m.complete_names(count)
    assert len(names) == 11 + 4 * count
    assert len(m.complete_names(count, final=True)) <= 128
    m.complete_census(NS(names=lambda: names), count)
    for extra in ('rogue.json', 'broker-99-observed.json', 'broker-report.json'):
        with pytest.raises(m.Refused): m.complete_census(NS(names=lambda: names | {extra}), count)
    with pytest.raises(m.Refused): m.complete_census(NS(names=lambda: names - {'worker-result.json'}), count)


@pytest.mark.parametrize('count', [True, None, 0, 5, 7, 25])
def test_impossible_success_dispatch_count_refused(count):
    with pytest.raises(m.Refused): m.complete_names(count)


def test_exact_private_organization_binding(monkeypatch):
    monkeypatch.setattr(helper, 'access', NS(_organization=lambda value: m.require(value == ORG, 'organization'),
        ORGANIZATION_SHA256=m.sha(ORG.encode())))
    value = {**m.binding(ARGS), 'organization_id': ORG, 'organization_sha256': helper.access.ORGANIZATION_SHA256}
    assert m.validate_organization_binding(value, m.binding(ARGS)) == ORG
    for field, changed in [('organization_id', '2' * 32), ('organization_sha256', 'bad'),
            ('expected_head', 'f' * 40), ('extra', False)]:
        with pytest.raises(m.Refused): m.validate_organization_binding({**value, field: changed}, m.binding(ARGS))


@pytest.fixture
def metadata_ready(monkeypatch):
    package = fixture.package.__wrapped__()
    plain, record = package.plain, copy.deepcopy(package.record)
    record.update(expected_head=m.PREPARATION_HEAD, caller_sha256=m.PREPARATION_CALLER)
    projected = NS(projection_sha256=m.sha(m.canonical(record['projection'])[:-1]),
        to_record=lambda: record['projection'])
    expected = {'package_sha256': plain.package_sha256, 'projection_sha256': projected.projection_sha256,
        'profile_sha256': record['projection']['profile_sha256'], 'activation_sha256': plain.activation_manifest_sha256,
        'parent_proof_sha256': plain.parent_proof_sha256, 'object_count': 6,
        'total_byte_count': plain.total_upload_byte_count}
    raw = m.canonical(record)
    monkeypatch.setattr(m, 'EXPECTED', expected)
    monkeypatch.setattr(m, 'PREPARATION_SHA256', m.sha(raw))
    monkeypatch.setattr(m, 'PREPARATION_BYTES', len(raw))
    monkeypatch.setattr(m.prep, 'summary', lambda *_args: dict(expected))
    return NS(raw=raw, header=m.ready_header(ARGS, plain, projected), record=record,
        plain=plain, projected=projected)


def test_ready_inventory_and_source_manifest_mechanically_bind_pinned_metadata(metadata_ready):
    m.validate_ready(metadata_ready.header, ARGS)
    m.validate_ready_preparation(metadata_ready.raw, metadata_ready.header)


@pytest.mark.parametrize('change', ['descriptor', 'manifest', 'activation_size', 'raw_hash', 'raw_size'])
def test_bound_looking_forged_handshake_cannot_override_pinned_preparation(metadata_ready, change):
    header, raw = metadata_ready.header, metadata_ready.raw
    if change == 'descriptor':
        header['inventory'][0]['content_sha256'] = '0' * 64
        rehash_ready(header)
    if change == 'manifest': header['projection_binding']['project_source_manifest_sha256'] = '0' * 64
    if change == 'activation_size': header['projection_binding']['activation_manifest_byte_count'] += 1
    if change == 'raw_hash': raw = raw.replace(b'"complete":true', b'"complete":null')
    if change == 'raw_size': raw += b'\n'
    with pytest.raises(m.Refused): m.validate_ready_preparation(raw, header)


@pytest.mark.parametrize('worker', ['SECRET', {'unknown': 'SECRET'}, {'complete': True}])
def test_failed_outer_output_never_accepts_unbounded_worker_result(ready, worker):
    value = output(ready)
    value.update(complete=False, failure_code='result')
    value['result'].update(complete=False, failure_code='result', worker_exit=2, worker_result=worker)
    with pytest.raises(m.Refused): check_output(value, 2)


def test_worker_real_helper_synthetic_capability_and_only_finite_ipc(metadata_ready, monkeypatch):
    directory, sent, constructs = fixture.Directory(), [], []
    args = NS(**{**ARGS.__dict__, 'operation': 'worker', 'control_fd': 91, 'request_fd': 92,
        'reply_fd': 93, 'deadline': time.monotonic() + 200})
    directory.values['parent-claim.json'] = {**m.binding(args), 'attempt_consumed': True, 'parent_pid': os.getppid()}
    class Context:
        def __enter__(self): return directory
        def __exit__(self, *_): pass
    def constructor(**kwargs):
        assert kwargs == {'inherited': 91}
        return Context()
    def construct(_deadline):
        constructs.append(None)
        return metadata_ready.plain, metadata_ready.projected
    organization_returned = False
    def send(fd, header, payload, deadline, *, header_fields):
        assert fd == 92 and type(payload) is bytes
        # Exercise actual binary canonical frame schema in both directions.
        decoded, actual = rpc.decode_frame(rpc.encode_frame(header, payload, header_fields=header_fields),
            header_fields=header_fields)
        assert decoded == header and actual == payload
        sent.append((header, payload))
    def receive(fd, deadline, *, header_fields):
        nonlocal organization_returned
        assert fd == 93
        if not organization_returned:
            organization_returned = True
            assert header_fields == m.ORG_FIELDS
            return {'kind': 'organization', 'binding_sha256': metadata_ready.header['binding_sha256'],
                'organization_id': ORG}, b''
        frame = m.flow_header(sent[-1][0])
        assert header_fields == m.RESPONSE_FIELDS
        row = m.validate_ready(metadata_ready.header, args)[frame['index']]
        return {'kind': 'storage_response', **{key: frame[key] for key in
            ('ordinal', 'phase', 'index', 'request_sha256')}, 'packet': fixture.packet(frame['phase'], row)}, b''
    monkeypatch.setattr(m, 'modules', lambda: (helper, NS(send_frame=send, receive_frame=receive),
        NS(require_safe_environment=lambda: None)))
    monkeypatch.setattr(m, 'Store', constructor)
    monkeypatch.setattr(m.prep, 'construct', construct)
    monkeypatch.setattr(m, 'read_preparation', lambda: metadata_ready.raw)
    monkeypatch.setattr(m, 'preflight', lambda *_args: None)
    monkeypatch.setattr(helper, 'access', NS(_organization=lambda value: m.require(value == ORG, 'organization'),
        ORGANIZATION_SHA256=m.sha(ORG.encode())))
    original_write = directory.write
    def write(name, value):
        original_write(name, value)
        raw = m.canonical(value)
        return {'sha256': m.sha(raw), 'byte_count': len(raw)}
    directory.write = write
    value = m.worker(args, args.deadline)
    assert value['complete'] is True and value['attempted_request_count'] == 6
    assert len(constructs) == 3 and len(sent) == 8
    assert sent[0] == (metadata_ready.header, metadata_ready.raw)
    assert m.flow_header(sent[-1][0])['kind'] == 'done' and sent[-1][1] == b''
    assert directory.values['worker-result.json']['result'] == value
    assert all(m.flow_header(header)['phase'] == 'initial' for header, _raw in sent[1:-1])


@pytest.mark.parametrize('mode', ['stderr', 'noise', 'oversize'])
def test_real_child_noise_cannot_be_success(tmp_path, mode):
    code = {'stderr': "import sys;sys.stderr.write('synthetic-only');sys.stdout.write('{}\\n\\n')",
        'noise': "import sys;sys.stdout.write('noise{}\\n\\n')",
        'oversize': "import sys;sys.stdout.write('x'*70000)"}[mode]
    child_env = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'TMPDIR': str(tmp_path),
        'PYTHONPYCACHEPREFIX': str(tmp_path), 'PYTHONDONTWRITEBYTECODE': '1'}
    process = subprocess.Popen([str(m.prep.frozen.PYTHON), '-B', '-c', code], cwd=m.ROOT,
        env=child_env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        with pytest.raises((m.Refused, m.prep.Refused)):
            m._channels(process, time.monotonic() + 5)
    finally:
        if process.poll() is None: process.kill(); process.wait(timeout=5)
        process.stdout.close(); process.stderr.close()


def fallback():
    return {'schema': m.SCHEMA, 'operation': 'worker', 'binding': m.binding(ARGS),
        'complete': False, 'failure_code': 'source', 'result': None, **m.FALSE_FLAGS}


@pytest.mark.parametrize('field,value', [('operation', 'publish'), ('schema', 'other'),
    ('binding', {}), ('complete', True), ('failure_code', 'SECRET'), ('failure_code', object()),
    ('result', {'raw': 'SECRET'}), ('capacity_access', True), ('extra', 0)])
def test_child_finite_fallback_strictness(field, value):
    packet = fallback(); packet[field] = value
    with pytest.raises(m.Refused): m.worker_failure(packet, ARGS, 2)


@pytest.mark.parametrize('actual_exit', [None, True, False, 0, -9, '2'])
def test_child_fallback_requires_actual_failure_exit(actual_exit):
    with pytest.raises(m.Refused): m.worker_failure(fallback(), ARGS, actual_exit)


def test_parent_retains_completed_early_child_finite_failure(ready, monkeypatch):
    directory = fixture.Directory()
    class Context:
        fd = 88
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def write(self, name, value):
            directory.write(name, value)
            return {'sha256': m.sha(m.canonical(value)), 'byte_count': len(m.canonical(value))}
    process = NS(stdout=NS(close=lambda: None), stderr=NS(close=lambda: None), poll=lambda: 2)
    def eof(*_args, **_kw): raise rpc.PlainStorageRPCError('eof')
    monkeypatch.setattr(m, 'modules', lambda: (helper, NS(receive_frame=eof), NS(require_safe_environment=lambda: None)))
    monkeypatch.setattr(m, 'Store', lambda **_kw: Context())
    monkeypatch.setattr(m.subprocess, 'Popen', lambda *_a, **_kw: process)
    monkeypatch.setattr(m, '_channels', lambda *_args: (2, fallback()))
    monkeypatch.setenv('QC_USER_ID', 'synthetic-user'); monkeypatch.setenv('QC_API_TOKEN', 'synthetic-token')
    value = m.publish(ARGS, time.monotonic() + 100)
    assert value['complete'] is False and value['worker_failure_code'] == 'source'
    assert value['worker_exit'] == 2 and value['storage_dispatches'] == value['organization_dispatches'] == 0
    envelope = {'schema': m.SCHEMA, 'operation': 'publish', 'binding': m.binding(ARGS),
        'complete': False, 'failure_code': value['failure_code'], 'result': value, **m.FALSE_FLAGS}
    assert check_output(envelope, 2) == envelope
