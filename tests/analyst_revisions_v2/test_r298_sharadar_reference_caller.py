"""O synthetic caller: no private source, real Keychain or HTTP operation."""
import copy
import csv
import io
import json
import os
import re
import time
from types import SimpleNamespace as NS

import pytest

from scripts import run_arv2_r298_sharadar_reference as m


@pytest.fixture(autouse=True)
def deny_operations(monkeypatch):
    def denied(*args, **kwargs): raise AssertionError('unmocked source, credential or operational call')
    for module, names in ((m.previous, ('main', 'run', 'observe', 'consume')),
        (m.feed, ('main', 'run', 'observe', 'worker', 'run_worker')),
        (m.source_binding, ('prepare',)), (m.keychain, ('load_key',)),
        (m.observation, ('observe',))):
        for name in names: monkeypatch.setattr(module, name, denied)


@pytest.fixture
def args():
    return NS(expected_head='a' * 40, caller_sha256='b' * 64, control_fd=None,
        worker_index=None, actual_exit=None, operation='run')


@pytest.fixture
def control(tmp_path, monkeypatch):
    parent = tmp_path / 'parent'; parent.mkdir(mode=0o700)
    target = parent / 'o'
    monkeypatch.setattr(m, 'CONTROL', target)
    monkeypatch.setattr(m.security, 'snapshot', lambda fd: {'acl_empty': True, 'xattrs': {}})
    return target


def csv_bytes(fields, values):
    stream = io.StringIO(newline=''); writer = csv.writer(stream, lineterminator='\n')
    writer.writerow(fields)
    if values is not None: writer.writerow(values)
    return stream.getvalue().encode()


@pytest.fixture
def pair():
    packet = {'permaticker': '123456', 'expected_composite_figi': 'BBG000000001',
        'exchange_mic': 'XNYS', 'original_cusips': ('012345678', '123456789')}
    source = {**m.source_binding._fixed_receipt(), 'private_packet_sha256': m.source_binding.packet_digest(packet),
        'source_endpoint_sha256': 'c' * 64, 'fresh_input_snapshot_sha256': 'd' * 64, 'fresh_admission_sha256': 'e' * 64}
    metadata = csv_bytes(m.observation.META_FIELDS, ['SEP', 'SYNTHX', '123456', 'NYSE', 'N',
        'Domestic Common Stock', '012345678,123456789', 'BBG000000001', 'USD', '2000-01-01', '2026-10-20', '2026-10-25'])
    price = csv_bytes(m.observation.PRICE_FIELDS, ['SYNTHX', '2022-10-21', '12.50', '2026-10-25'])
    row = m.observation._metadata(metadata, packet)
    receipt = m.observation._receipt(packet, row, metadata, price)
    m.observation.validate_capture(packet, receipt, metadata, price)
    return NS(packet=packet, source=source, metadata=metadata, price=price, receipt=receipt)


def event(role, name, status=None):
    return {'schema': m.observation.EVENT_SCHEMA, 'event': name, 'role': role,
        'application_attempt': 1 if role == 'metadata' else 2, 'http_status': status,
        'http_status_state': 'not_observed' if name == 'intent' else 'validated' if status is not None else 'unavailable'}


@pytest.fixture
def workflow(control, args, pair, monkeypatch):
    state = NS(events=[], final_changed=False)
    def worker(args, store, deadline, index, expected=None):
        assert (control / 'claim.json').is_file()
        state.events.append('source-' + str(index))
        if index == 1:
            assert expected['captures'] == m.observation.capture_pins(pair.receipt)
            assert expected['private_packet_sha256'] == m.source_binding.packet_digest(pair.packet)
            m.observation.validate_capture(pair.packet, expected['receipt'],
                (control / 'metadata.csv').read_bytes(), (control / 'price.csv').read_bytes())
        value = {'source': copy.deepcopy(pair.source), 'private_packet': m.source_binding.private_record(pair.packet)}
        if index == 1 and state.final_changed: value['source']['source_endpoint_sha256'] = 'f' * 64
        return value
    def key(provider, *, timeout_seconds):
        assert provider == 'sharadar' and 0 < timeout_seconds <= 20
        assert state.events == ['source-0']
        state.events.append('keychain')
        return 'synthetic-secret-key'
    def observe(packet, *, session, api_key, journal, deadline):
        assert api_key == 'synthetic-secret-key' and packet == pair.packet
        state.events.append('provider')
        for role in ('metadata', 'price'):
            journal(role + '-intent', event(role, 'intent'))
            journal(role + '-status', event(role, 'status', 200))
        return copy.deepcopy(pair.receipt), m.observation.PrivateCapture(pair.metadata, pair.price)
    monkeypatch.setattr(m, 'run_worker', worker)
    monkeypatch.setattr(m.keychain, 'load_key', key)
    monkeypatch.setattr(m.observation, 'observe', observe)
    monkeypatch.setattr(m, 'preflight', lambda *args: None)
    monkeypatch.setattr(m.environment, 'require_safe_environment', lambda: None)
    return state


def test_protocol_has_no_qc_or_strategy_authority():
    record = m.profile_record()
    assert m.CONTROL.name == 'R323-20261025-O' and m.DEADLINE_SECONDS == 600
    assert record['maximum_provider_attempts'] == 2 and record['keychain_lookups'] == 1
    assert record['keychain_provider'] == record['keychain_account'] == 'sharadar'
    assert record['credential_fallback'] is False and record['qc_jobs'] == record['new_strategy_looks'] == 0
    assert record['source_guard_across_provider_contact'] is False


def test_selected_source_pins_and_compile():
    for name, pin in m.pins().items():
        assert re.fullmatch('[0-9a-f]{64}', pin) and pin != '0' * 64
        assert m.sha((m.ROOT / name).read_bytes()) == pin
    for name in ('scripts/run_arv2_r298_sharadar_reference.py',
        'tests/analyst_revisions_v2/test_r298_sharadar_reference_caller.py'):
        compile((m.ROOT / name).read_bytes(), name, 'exec')


def test_claim_before_auth_before_key_and_two_requests(control, args, pair, workflow):
    outcome = m.run(args, time.monotonic() + 500)
    assert workflow.events == ['source-0', 'keychain', 'provider', 'source-1']
    assert outcome['result']['receipt']['price_row_count'] == 1
    assert outcome['result']['result_cell'] == 0
    assert m.validate_output(m.canonical({'binding': m.binding(args), 'outcome': outcome}), 0, args)
    with pytest.raises(ValueError):
        m.validate_output(m.canonical({'binding': m.binding(args), 'outcome': outcome}), 2, args)
    public = json.dumps(outcome)
    for private in ('synthetic-secret-key', 'SYNTHX', 'BBG000000001', '012345678', '12.50'):
        assert private not in public
    assert (control / 'metadata.csv').read_bytes() == pair.metadata
    assert (control / 'metadata.csv').stat().st_mode & 0o777 == 0o600
    with pytest.raises(m.Refused): m.run(args, time.monotonic() + 500)


def test_initial_source_failure_never_reads_key_or_contacts(control, args, workflow, monkeypatch):
    def fail(*args, **kwargs): raise m.Refused('source_changed')
    monkeypatch.setattr(m, 'run_worker', fail)
    result = m.run(args, time.monotonic() + 500)
    assert result['failure']['failure_code'] == 'source_changed' and workflow.events == []


def test_keychain_failure_has_no_contact_or_fallback(control, args, workflow, monkeypatch):
    def fail(*args, **kwargs): raise m.keychain.KeychainUnavailable('credentials_unavailable')
    monkeypatch.setattr(m.keychain, 'load_key', fail)
    result = m.run(args, time.monotonic() + 500)
    assert result['failure']['failure_code'] == 'credentials_unavailable'
    assert workflow.events == ['source-0']


@pytest.mark.parametrize('status', [401, 403, 429, 500])
def test_http_refusal_preserves_exact_status_no_failed_body(control, args, workflow, monkeypatch, status):
    def fail(packet, *, journal, **kwargs):
        journal('metadata-intent', event('metadata', 'intent'))
        journal('metadata-status', event('metadata', 'status', status))
        raise m.observation.Refused('http_status')
    monkeypatch.setattr(m.observation, 'observe', fail)
    outcome = m.run(args, time.monotonic() + 500)
    failed = outcome['failure']
    assert failed['failure_code'] == 'provider_http_status'
    assert failed['state']['http_events'][-1]['http_status'] == status
    assert not (control / 'metadata.csv').exists() and 'source-1' not in workflow.events
    assert m.validate_output(m.canonical({'binding': m.binding(args), 'outcome': outcome}), 2, args)


def test_final_source_drift_preserves_receipt_but_not_success(control, args, workflow):
    workflow.final_changed = True
    outcome = m.run(args, time.monotonic() + 500)
    assert outcome['failure']['failure_code'] == 'source_changed'
    assert outcome['failure']['state']['receipt']['price_row_count'] == 1
    assert not (control / 'report.json').exists()
    raw = m.canonical({'binding': m.binding(args), 'outcome': outcome})
    assert m.validate_output(raw, 2, args)
    with pytest.raises(ValueError): m.validate_output(raw, 0, args)


@pytest.mark.parametrize('actual', [2, None, False])
def test_success_requires_exact_actual_zero(control, args, workflow, actual):
    outcome = m.run(args, time.monotonic() + 500)
    assert 'result' in outcome
    raw = m.canonical({'binding': m.binding(args), 'outcome': outcome})
    with pytest.raises(ValueError): m.validate_output(raw, actual, args)


@pytest.mark.parametrize('change', ['status', 'capture', 'source', 'flag', 'report'])
def test_output_cannot_upgrade_or_break_source_capture_binding(control, args, workflow, change):
    outcome = m.run(args, time.monotonic() + 500)
    value = {'binding': m.binding(args), 'outcome': outcome}
    result = value['outcome']['result']
    if change == 'status': result['http_events'][-1]['http_status'] = 403
    elif change == 'capture': result['captures']['metadata.csv']['sha256'] = '0' * 64
    elif change == 'source': result['source']['private_packet_sha256'] = '0' * 64
    elif change == 'flag': result['price_used'] = True
    else: value['outcome']['report']['sha256'] = '0' * 64
    with pytest.raises(ValueError): m.validate_output(m.canonical(value), 0, args)


@pytest.mark.parametrize('name', ['../outside.json', '/tmp/out.json', 'key.txt', 'unexpected.csv'])
def test_store_rejects_other_names(control, name):
    with m.Store() as store:
        with pytest.raises(ValueError): store.write(name, {})


def test_private_output_held_named_metadata_drift_detected(control):
    with m.Store() as store:
        store.write('claim.json', {})
        store.write_bytes('metadata.csv', b'synthetic\n', private=True)
        (control / 'metadata.csv').chmod(0o640)
        with pytest.raises(ValueError): store.verify()


def test_unsafe_empty_private_leaf_refuses_before_licensed_bytes(control, monkeypatch):
    with m.Store() as store:
        store.write('claim.json', {})
        writes = []
        original = os.write
        def write(fd, value): writes.append(bytes(value)); return original(fd, value)
        def unsafe(fd): raise m.security.Refusal('synthetic inherited unsafe ACL')
        monkeypatch.setattr(m.os, 'write', write)
        monkeypatch.setattr(m.security, 'snapshot', unsafe)
        with pytest.raises(m.Refused, match='capture_security'):
            store.write_bytes('metadata.csv', b'synthetic licensed bytes\n', private=True)
        assert writes == [] and (control / 'metadata.csv').stat().st_size == 0


def test_native_profile_denies_spent_controls_and_credentials():
    profile = m.native_profile()
    assert str(m.previous.CONTROL) in profile and str(m.feed.CONTROL) in profile
    assert '(deny network*)' in profile and 'Library/Keychains' in profile
    assert '(require-not (subpath "' + str(m.CONTROL) + '"))' in profile


@pytest.mark.parametrize('index', [0, 1])
def test_native_worker_consumes_within_guard_and_start_marker_once(control, args, pair, monkeypatch, index):
    held, calls = [], []
    def prepare(deadline, *, phase, consumer):
        assert phase == ('initial' if index == 0 else 'final')
        held.append(True)
        try:
            result = consumer(pair.source, pair.packet)
            calls.append('consumer-returned')
            return result
        finally: held.pop()
    def check(*args): assert held == [True]; calls.append('postflight')
    monkeypatch.setattr(m.source_binding, 'prepare', prepare)
    monkeypatch.setattr(m, 'preflight', check)
    monkeypatch.setattr(m.environment, 'require_safe_environment', lambda: None)
    with m.Store() as store:
        store.write('claim.json', {**m.binding(args), 'old_controls_spent': True})
        captures = {name: store.write_bytes(name, raw, private=True) for name, raw in
            zip(m.CAPTURE_NAMES, (pair.metadata, pair.price), strict=True)} if index else None
        expected = {'source': pair.source, 'private_packet_sha256': m.source_binding.packet_digest(pair.packet),
            'receipt': pair.receipt, 'captures': captures} if index else None
        store.write('worker-' + str(index) + '-intent.json',
            {'binding': m.binding(args), 'worker_index': index, 'expected': expected})
        args.control_fd, args.worker_index = store.fd, index
        output = m.worker(args, time.monotonic() + 100)
        assert output['source'] == pair.source and output['private_packet'] == m.source_binding.private_record(pair.packet)
        store.adopt_started(index, args); store.verify()
        with pytest.raises(FileExistsError): m.worker(args, time.monotonic() + 100)
    assert calls == ['postflight', 'consumer-returned'] and held == []


@pytest.mark.parametrize('change', ['fd', 'index', 'index-bool', 'binding', 'expected'])
def test_worker_scope_refuses_before_source_prepare(control, args, monkeypatch, change):
    with m.Store() as store:
        store.write('claim.json', {**m.binding(args), 'old_controls_spent': True})
        args.control_fd, args.worker_index = store.fd, 0
        intent = {'binding': m.binding(args), 'worker_index': 0, 'expected': None}
        if change == 'fd': args.control_fd = -1
        elif change == 'index': args.worker_index = False
        elif change == 'index-bool': intent['worker_index'] = False
        elif change == 'binding': intent['binding']['expected_head'] = 'f' * 40
        else: intent['extra'] = True
        store.write('worker-0-intent.json', intent)
        with pytest.raises(ValueError): m.worker(args, time.monotonic() + 100)


def test_final_worker_rejects_private_csv_pin_drift(control, args, pair, monkeypatch):
    monkeypatch.setattr(m.source_binding, 'prepare', lambda deadline, *, phase, consumer:
        consumer(pair.source, pair.packet))
    monkeypatch.setattr(m, 'preflight', lambda *args: None)
    monkeypatch.setattr(m.environment, 'require_safe_environment', lambda: None)
    with m.Store() as store:
        store.write('claim.json', {**m.binding(args), 'old_controls_spent': True})
        captures = {name: store.write_bytes(name, raw, private=True) for name, raw in
            zip(m.CAPTURE_NAMES, (pair.metadata, pair.price), strict=True)}
        captures['metadata.csv']['sha256'] = '0' * 64
        expected = {'source': pair.source, 'private_packet_sha256': m.source_binding.packet_digest(pair.packet),
            'receipt': pair.receipt, 'captures': captures}
        store.write('worker-1-intent.json', {'binding': m.binding(args), 'worker_index': 1, 'expected': expected})
        args.control_fd, args.worker_index = store.fd, 1
        with pytest.raises(ValueError): m.worker(args, time.monotonic() + 100)
        store.adopt_started(1, args); store.verify()


def test_final_worker_rejects_metadata_only_drift_during_consumer(control, args, pair, monkeypatch):
    monkeypatch.setattr(m.source_binding, 'prepare', lambda deadline, *, phase, consumer:
        consumer(pair.source, pair.packet))
    monkeypatch.setattr(m, 'preflight', lambda *args: None)
    monkeypatch.setattr(m.environment, 'require_safe_environment', lambda: None)
    original = m.observation.validate_capture
    def change(*values):
        result = original(*values)
        path = control / 'metadata.csv'; info = path.stat()
        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 1000000000))
        return result
    monkeypatch.setattr(m.observation, 'validate_capture', change)
    with m.Store() as store:
        store.write('claim.json', {**m.binding(args), 'old_controls_spent': True})
        captures = {name: store.write_bytes(name, raw, private=True) for name, raw in
            zip(m.CAPTURE_NAMES, (pair.metadata, pair.price), strict=True)}
        expected = {'source': pair.source, 'private_packet_sha256': m.source_binding.packet_digest(pair.packet),
            'receipt': pair.receipt, 'captures': captures}
        store.write('worker-1-intent.json', {'binding': m.binding(args), 'worker_index': 1, 'expected': expected})
        args.control_fd, args.worker_index = store.fd, 1
        with pytest.raises(m.Refused, match='capture_changed'): m.worker(args, time.monotonic() + 100)


@pytest.mark.parametrize('change', ['missing', 'head', 'spent', 'spent-int'])
def test_worker_missing_or_mismatched_claim_precedes_private_source(control, args, change):
    with m.Store() as store:
        claim = {**m.binding(args), 'old_controls_spent': True}
        if change == 'head': claim['expected_head'] = 'f' * 40
        elif change == 'spent': claim['old_controls_spent'] = False
        elif change == 'spent-int': claim['old_controls_spent'] = 1
        if change != 'missing': store.write('claim.json', claim)
        store.write('worker-0-intent.json', {'binding': m.binding(args), 'worker_index': 0, 'expected': None})
        args.control_fd, args.worker_index = store.fd, 0
        with pytest.raises((ValueError, FileNotFoundError)): m.worker(args, time.monotonic() + 100)
        assert not (control / 'worker-0-started.json').exists()


@pytest.mark.parametrize('index,bad', [(0, False), (1, True)])
def test_started_marker_bool_index_is_not_an_integer(control, args, index, bad):
    with m.Store() as store:
        name = 'worker-' + str(index) + '-started.json'
        path = control / name
        path.write_bytes(m.canonical({'binding': m.binding(args), 'worker_index': bad}))
        path.chmod(0o600)
        with pytest.raises(ValueError): store.adopt_started(index, args)


def test_known_native_foreign_refusals_remain_finite():
    for module, prefix in m._foreign():
        code = sorted(module.FINITE)[0]
        mapped = m.finite(module.Refused(code))
        assert mapped == prefix + code and m._finite_code(mapped)


@pytest.mark.parametrize('change', ['none', 'binding', 'code', 'extra'])
def test_bound_child_refusal_retained_without_private_packet(control, args, monkeypatch, change):
    code = 'native_security_metadata_changed'
    def capture(*values, **kwargs):
        failed = {'binding': m.binding(args), 'preflight_failure': code}
        if change == 'binding': failed['binding']['expected_head'] = 'f' * 40
        elif change == 'code': failed['preflight_failure'] = 'raw secret exception'
        elif change == 'extra': failed['private_packet'] = {'not': 'allowed'}
        return m.canonical(failed), b'', {'actual_exit': 2, 'bound': None}
    monkeypatch.setattr(m, 'capture', capture)
    with m.Store() as store:
        store.write('claim.json', {**m.binding(args), 'old_controls_spent': True})
        if change == 'none':
            with pytest.raises(m.WorkerRefused) as error: m.run_worker(args, store, time.monotonic() + 100, 0)
            assert m.finite(error.value) == code
        else:
            with pytest.raises(m.Refused, match='worker_failed'): m.run_worker(args, store, time.monotonic() + 100, 0)
        with pytest.raises(ValueError): m.run_worker(args, store, time.monotonic() + 100, 0)


def test_event_budget_order_and_no_unknown_fields():
    values = [event('metadata', 'intent'), event('metadata', 'status', 200),
        event('price', 'intent'), event('price', 'status', 200)]
    assert m._events(values) == values
    with pytest.raises(ValueError): m._events([values[2]])
    with pytest.raises(ValueError): m._events(values + [values[0]])
    values[0]['raw_url'] = 'never retain'
    with pytest.raises(ValueError): m._events(values)


@pytest.mark.parametrize('actual', [False, None, 0])
def test_failure_requires_actual_nonzero(args, actual):
    value = {'binding': m.binding(args), 'preflight_failure': 'source_pin'}
    with pytest.raises(ValueError): m.validate_output(m.canonical(value), actual, args)
