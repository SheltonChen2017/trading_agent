"""Injected operation ordering and finite failure evidence; no QC or DATA reads."""
from contextlib import contextmanager
import copy
import os
from pathlib import Path
import time
from types import SimpleNamespace as NS

import pytest

from scripts import run_arv2_r345_legacy_six_v2 as m
from scripts import arv2_r345_legacy_six_qc_v2 as actual_engine


def refused(code, operation):
    with pytest.raises(m.Refused) as caught:
        operation()
    assert caught.value.args == (code,)


def uploads():
    return tuple(NS(object_store_key=f'synthetic/key-{index}.json', payload=f'opaque-{index}'.encode())
        for index in range(6))


def metadata_packet(payload, objects):
    item = next(item for item in objects if item.object_store_key == payload['key'])
    return {'success': True, 'metadata': {'key': item.object_store_key, 'size': len(item.payload),
        'md5': m.hashlib.md5(item.payload, usedforsecurity=False).hexdigest(), 'preview': 'MUST-NEVER-BE-RETAINED'}}


def test_exact_six_metadata_rows_bind_opaque_payloads_without_preview_or_download():
    objects, calls, events, state = uploads(), [], [], {}
    def request(endpoint, payload):
        calls.append((endpoint, payload))
        return metadata_packet(payload, objects)
    result = m.object_admission(request, objects, 'a' * 32,
        lambda marker, value: events.append((marker, value)), state)
    assert len(calls) == 6 and all(endpoint == 'object/properties' for endpoint, _ in calls)
    assert len(result['objects']) == 6 and len(events) == 12
    assert 'MUST-NEVER-BE-RETAINED' not in m.canonical(result).decode()
    assert 'not_remote_SHA256' in result['qualification']
    assert state['last_object_observation']['md5_matches'] is True


@pytest.mark.parametrize('fault', ['missing', 'key', 'size', 'size_bool', 'md5', 'md5_malformed', 'success'])
def test_metadata_refusal_preserves_finite_observation_and_stops_without_retry(fault):
    objects, calls, state = uploads(), [], {}
    def request(endpoint, payload):
        calls.append(endpoint)
        packet = metadata_packet(payload, objects)
        if fault == 'missing': packet['metadata'] = None
        elif fault == 'key': packet['metadata']['key'] = 'unexpected-private-string'
        elif fault == 'size': packet['metadata']['size'] += 1
        elif fault == 'size_bool': packet['metadata']['size'] = True
        elif fault == 'md5': packet['metadata']['md5'] = '0' * 32
        elif fault == 'md5_malformed': packet['metadata']['md5'] = 'G' * 32
        else: packet['success'] = False
        return packet
    refused('object_admission', lambda: m.object_admission(request, objects, 'a' * 32, lambda *args: None, state))
    assert calls == ['object/properties']
    assert 'unexpected-private-string' not in m.canonical(state).decode()
    if fault != 'success':
        assert state['last_object_observation']['ordinal'] == 0


def test_metadata_MD5_case_is_insensitive_as_in_existing_QC_transport():
    objects, state = uploads(), {}
    def request(endpoint, payload):
        packet = metadata_packet(payload, objects)
        packet['metadata']['md5'] = packet['metadata']['md5'].upper()
        return packet
    result = m.object_admission(request, objects, 'a' * 32, lambda *args: None, state)
    assert len(result['objects']) == 6
    assert state['last_object_observation']['md5_hex'] is True
    assert state['last_object_observation']['md5_matches'] is True


class FakeStore:
    def __init__(self):
        self.events, self.application_dispatch_count = [], 0
    def journal(self, marker, value): self.events.append((marker, copy.deepcopy(value)))


def operation_fixture(*, compile_states=('Building', 'BuildSuccess'), launch_states=('launched',)):
    events, objects, store = [], uploads(), FakeStore()
    candidate = NS(candidate_id='R343-AR100', cell_record=lambda: {'synthetic-source': True})
    submission = NS(candidates=(candidate,), uploads=objects)
    class EngineRefused(ValueError): pass
    class Engine:
        REFERENCE_PROJECT = 37165262
        PAYLOAD_KEYS = {'authenticate': set()}
        COMPILE_POLLS, COMPILE_INTERVAL, CAPACITY_POLLS, CAPACITY_INTERVAL = 3, 2, 3, 60
        Refused, FINITE = EngineRefused, frozenset(('source_changed',))
        @staticmethod
        def access_capacity(request, *, user_id, journal):
            events.append('access')
            request('authenticate', {})
            return {'organization_id': 'a' * 32, 'public': {'capacity': {'available_count': 1}}}
        class LegacySixQc:
            def __init__(self, cell, **kwargs):
                assert cell == {'synthetic-source': True}
                assert kwargs['attempt'] == 2 and kwargs['a1_failure_fact'] == {'synthetic_fact': True}
                self.request = kwargs['request']
                self.project_id, self.compile_id, self.launch_receipt = 123, 'compile-id', None
                self.last_request = self.last_failure = None
                events.append('constructed')
            def begin_once(self):
                events.append('begin')
                return {'state': 'compiling'}
            def poll_compile(self, index):
                events.append('compile-' + str(index))
                return {'state': compile_states[min(index, len(compile_states)-1)]}
            def launch_once(self):
                index = sum(item.startswith('launch-') for item in events)
                events.append('launch-' + str(index))
                return {'state': launch_states[min(index, len(launch_states)-1)],
                    'launch_receipt': {'project_id': 123, 'backtest_id': 'job-id'}, 'terminal_receipt': None}
    class API:
        deadline = None
        last_http_status, statuses, responses = 200, [], []
        def _exchange(self, endpoint, payload):
            events.append(endpoint)
            return {'success': True} if endpoint == 'authenticate' else metadata_packet(payload, objects)
    return submission, Engine, API(), store, events


def test_metadata_both_before_mutation_and_before_single_launch_no_result_read():
    submission, engine, api, store, events = operation_fixture()
    state = {}
    result = m.operate(submission, 'R343-AR100', engine=engine, api=api,
        secret={'QC_USER_ID': '1'}, store=store, deadline=time.monotonic()+3599,
        state=state, a1_failure_fact={'synthetic_fact': True}, sleep=lambda seconds: events.append('sleep-' + str(seconds)))
    assert events.count('object/properties') == 12
    assert events.index('begin') > max(index for index, item in enumerate(events[:events.index('begin')]) if item == 'object/properties')
    assert events[-1] == 'launch-0'
    assert events.count('begin') == 1 and events.count('launch-0') == 1
    assert state['operation'].project_id == 123
    assert result['result_read'] is False and result['launch_receipt']['backtest_id'] == 'job-id'
    assert 'backtests/read' not in events


def test_build_error_keeps_registered_project_and_does_not_launch():
    submission, engine, api, store, events = operation_fixture(compile_states=('BuildError',))
    state = {}
    refused('compile', lambda: m.operate(submission, 'R343-AR100', engine=engine, api=api,
        secret={'QC_USER_ID': '1'}, store=store, deadline=time.monotonic()+3599, state=state, a1_failure_fact={'synthetic_fact': True}))
    assert state['operation'].project_id == 123 and not any(item.startswith('launch-') for item in events)


def test_post_compile_object_refusal_updates_shared_failure_state_before_launch():
    submission, engine, api, store, events = operation_fixture(compile_states=('BuildSuccess',))
    real_exchange, object_calls = api._exchange, 0
    def exchange(endpoint, payload):
        nonlocal object_calls
        response = real_exchange(endpoint, payload)
        if endpoint == 'object/properties':
            object_calls += 1
            if object_calls == 7:
                response['metadata']['size'] += 1
        return response
    api._exchange = exchange
    state = {'api': api}
    refused('object_admission', lambda: m.operate(submission, 'R343-AR100', engine=engine, api=api,
        secret={'QC_USER_ID': '1'}, store=store, deadline=time.monotonic()+3599, state=state, a1_failure_fact={'synthetic_fact': True}))
    assert state['operation'].compile_id == 'compile-id'
    assert state['last_request']['endpoint'] == 'object/properties'
    assert state['last_object_observation']['ordinal'] == 0
    assert state['last_object_observation']['observed_size'] == len(submission.uploads[0].payload) + 1
    sources = NS(engine=engine, consumer=NS(Refused=type('ConsumerRefused', (ValueError,), {}), FINITE=()),
        transport=NS(Refused=type('TransportRefused', (ValueError,), {}), FINITE=()))
    evidence = m.failure_evidence(state, sources, m.Refused('object_admission'))
    assert evidence['last_request']['endpoint'] == 'object/properties'
    assert evidence['object_observation']['observed_size'] == len(submission.uploads[0].payload) + 1
    assert evidence['allocated_identities']['project_id'] == 123
    assert not any(item.startswith('launch-') for item in events)


def test_capacity_waits_are_bounded_without_second_create_or_attempt():
    submission, engine, api, store, events = operation_fixture(launch_states=('wait', 'wait', 'wait'))
    refused('capacity', lambda: m.operate(submission, 'R343-AR100', engine=engine, api=api,
        secret={'QC_USER_ID': '1'}, store=store, deadline=time.monotonic()+3599,
        state={}, a1_failure_fact={'synthetic_fact': True}, sleep=lambda seconds: events.append('sleep-' + str(seconds))))
    assert events.count('begin') == 1 and events.count('sleep-60') == 2
    assert events.count('object/properties') == 24


@pytest.mark.parametrize('endpoint,payload', [('projects/create', {'name': 'forbidden-new-project'}),
    ('projects/read', {}), ('projects/read', {'projectId': 777})])
def test_request_wrapper_refuses_new_project_global_listing_or_another_project(endpoint, payload):
    submission, engine, api, store, events = operation_fixture()
    engine.PAYLOAD_KEYS[endpoint] = set(payload)
    original = engine.LegacySixQc
    class InvalidEngine(original):
        def begin_once(self):
            return self.request(endpoint, payload)
    engine.LegacySixQc = InvalidEngine
    refused('request', lambda: m.operate(submission, 'R343-AR100', engine=engine, api=api,
        secret={'QC_USER_ID': '1'}, store=store, deadline=time.monotonic()+3599,
        state={}, a1_failure_fact={'synthetic_fact': True}))
    assert endpoint not in events


def test_profile_and_control_are_exact_AR100_attempt2_same_A1_project():
    record = m.profile_record('R343-AR100')
    assert record['attempt'] == 2 and record['recovery_project_id'] == 39054561
    assert record['a1_failure_fact_pin'] == {'byte_count': 3418,
        'sha256': '20d65921c14bf10577f01f87dde381cbec829cd5ba8c79b3ceb9562c97126823'}
    assert m.control('R343-AR100').name == 'R345-20261107-AR100-A2'
    assert m.PLAN.name == 'arv2_r345_legacy_six_plan_v2.json'
    assert m.SOURCE.name == 'run_arv2_r345_legacy_six_v2.py'


@pytest.mark.parametrize('fail_before_validation', [False, True])
def test_latest_closed_missing_isLibrary_observation_survives_success_or_access_failure(fail_before_validation):
    submission, engine, api, store, events = operation_fixture(compile_states=('BuildSuccess',))
    engine.validate_metadata_observation = actual_engine.validate_metadata_observation
    original = engine.LegacySixQc
    class ObservingEngine(original):
        def begin_once(self):
            # Same actual field-presence shape that caused the A1 guard to
            # stop; no remote identifiers or values are retained by observer.
            self.last_access_observation = actual_engine.owned_access_observation({'projects': [{
                'libraries': [], 'language': 'SENSITIVE-PROJECT-VALUE'}]})
            if fail_before_validation:
                raise engine.Refused('source_changed')
            return super().begin_once()
    engine.LegacySixQc = ObservingEngine
    state = {'api': api}
    call = lambda: m.operate(submission, 'R343-AR100', engine=engine, api=api,
        secret={'QC_USER_ID': '1'}, store=store, deadline=time.monotonic()+3599,
        state=state, a1_failure_fact={'synthetic_fact': True})
    if fail_before_validation:
        with pytest.raises(engine.Refused) as caught:
            call()
        sources = NS(engine=engine, consumer=NS(Refused=type('ConsumerRefused', (ValueError,), {}), FINITE=()),
            transport=NS(Refused=type('TransportRefused', (ValueError,), {}), FINITE=()))
        observation = m.failure_evidence(state, sources, caught.value)['last_access_observation']
    else:
        observation = call()['last_access_observation']
    assert observation['field_types']['isLibrary'] == observation['flags']['isLibrary'] == 'absent'
    assert observation['field_types']['libraries'] == 'list' and observation['library_count'] == 0
    assert 'SENSITIVE-PROJECT-VALUE' not in m.canonical(observation).decode()
    actual_engine.validate_metadata_observation(observation)


@pytest.mark.parametrize('value', [None, {'raw': 'SENSITIVE'}, {'schema': 'SENSITIVE'}])
def test_missing_or_invalid_access_metadata_is_null_in_failure_output(value):
    sources, state = evidence_fixture()
    sources.engine.validate_metadata_observation = actual_engine.validate_metadata_observation
    state['operation'].last_access_observation = value
    evidence = m.failure_evidence(state, sources, RuntimeError('SENSITIVE'))
    assert evidence['last_access_observation'] is None
    assert 'SENSITIVE' not in m.canonical(evidence).decode()


def test_frozen_used_v1_caller_is_preserved_byte_for_byte():
    root = Path(__file__).resolve().parents[2]
    raw = (root / 'scripts/run_arv2_r345_legacy_six.py').read_bytes()
    assert m.pin(raw) == {'byte_count': 38408,
        'sha256': '0e2c2444a064a8d1c67b4b0b66e3d8abfd28c7fb49abab7508e9f613498bfc9d'}


def evidence_fixture():
    class ConsumerRefused(ValueError): pass
    class EngineRefused(ValueError): pass
    class TransportRefused(ValueError): pass
    sources = NS(consumer=NS(Refused=ConsumerRefused, FINITE={'pin'}),
        engine=NS(Refused=EngineRefused, FINITE={'source_changed'}, PAYLOAD_KEYS={'files/create': set(), 'compile/create': set()}),
        transport=NS(Refused=TransportRefused, FINITE={'http_status'}))
    state = {'api': NS(last_http_status=403, statuses=[{'endpoint': 'files/create', 'http_status': 403}],
        responses=[{'endpoint': 'compile/create', 'byte_count': 100, 'sha256': 'a' * 64}]),
        'operation': NS(project_id=123, compile_id='compile-id', launch_receipt={'backtest_id': 'job-id', 'raw_secret': 'SENSITIVE'},
            last_request={'endpoint': 'files/create', 'marker': 'write-00-source', 'payload_sha256': 'b' * 64, 'content': 'SENSITIVE'},
            last_failure={'endpoint': 'files/create', 'marker': 'write-00-source', 'payload_sha256': 'b' * 64,
                'stage': 'response_unaccepted', 'response_sha256': 'c' * 64, 'response_bytes': 321, 'content': 'SENSITIVE'}),
        'last_request': {'endpoint': 'files/create', 'payload_sha256': 'b' * 64, 'content': 'SENSITIVE'},
        'last_object_observation': None}
    return sources, state


def test_failure_retains_numeric_status_module_code_allocation_and_response_pins_only():
    sources, state = evidence_fixture()
    result = m.failure_evidence(state, sources, sources.engine.Refused('source_changed'))
    assert result['last_http_status'] == 403
    assert result['module_error'] == {'module': 'engine', 'code': 'source_changed'}
    assert result['engine_last_failure']['response_sha256'] == 'c' * 64
    assert result['allocated_identities'] == {'project_id': 123, 'compile_id': 'compile-id', 'backtest_id': 'job-id'}
    assert result['response_pin_count'] == result['http_status_count'] == 1
    assert 'SENSITIVE' not in m.canonical(result).decode()


@pytest.mark.parametrize('field,value', [('last_http_status', True), ('last_http_status', 'SENSITIVE'), ('last_http_status', 999)])
def test_unvalidated_status_never_becomes_numeric_failure_evidence(field, value):
    sources, state = evidence_fixture(); setattr(state['api'], field, value)
    result = m.failure_evidence(state, sources, RuntimeError('SENSITIVE'))
    assert result['last_http_status'] is None and 'SENSITIVE' not in m.canonical(result).decode()


def test_unknown_exception_and_malformed_object_observation_cannot_leak_raw_strings():
    sources, state = evidence_fixture()
    state['last_object_observation'] = dict.fromkeys(('ordinal', 'key_sha256', 'metadata_present', 'key_exact',
        'size_type', 'observed_size', 'expected_size', 'md5_lower_hex', 'md5_hex', 'md5_matches'), 'SENSITIVE')
    result = m.failure_evidence(state, sources, RuntimeError('SENSITIVE'))
    assert result['object_observation'] is None and result['module_error']['code'] == 'unknown'
    assert 'SENSITIVE' not in m.canonical(result).decode()


@pytest.mark.parametrize('closing_failure', [False, True])
def test_run_claims_before_DATA_and_preserves_identity_through_final_close(monkeypatch, closing_failure):
    events, saved = [], {}
    args = NS(candidate='R343-AR100')
    class Store:
        application_dispatch_count = 0
        def __init__(self, *args): pass
        def __enter__(self): events.append('exclusive-store'); return self
        def __exit__(self, *args): events.append('store-closed')
        def write(self, name, value):
            events.append(name); saved[name] = value; return m.pin(b'fixture')
        def verify(self): events.append('store-verify')
    class Consumer:
        def __init__(self, **kwargs): pass
        def __enter__(self): events.append('DATA-enter'); return NS(value='immutable-fixture')
        def __exit__(self, *args): events.append('DATA-normal-return')
    class Transport:
        @staticmethod
        def credentials(value): events.append('credentials'); return value
        class API:
            def __init__(self, *args): events.append('API')
            def close(self): events.append('API-close')
    class Sources:
        def __init__(self, *args):
            self.plan = {'private_pin': {}, 'source_summary': {}, 'preparation_binding': {}}
            self.consumer, self.transport, self.security = NS(FreshSubmission=Consumer), Transport, None
            self.engine = NS(PAYLOAD_KEYS={})
            self.a1_failure_fact = {'synthetic_fact': True}
        def __enter__(self): return self
        def __exit__(self, *args):
            events.append('sources-normal-return')
            if closing_failure: raise m.Refused('source_changed')
        def verify(self): events.append('sources-verify')
    monkeypatch.setattr(m, 'preflight', lambda *args: {'synthetic': True})
    monkeypatch.setattr(m, 'Sources', Sources); monkeypatch.setattr(m, 'Store', Store)
    def operate(*args, **kwargs):
        events.append('operate')
        kwargs['state']['operation'] = NS(project_id=123, compile_id='compile-id',
            launch_receipt={'backtest_id': 'job-id'})
        return {'synthetic': True}
    monkeypatch.setattr(m, 'operate', operate)
    if closing_failure:
        refused('source_changed', lambda: m.run(args))
        assert m.LAST_FAILURE['allocated_identities']['backtest_id'] == 'job-id'
        assert m.LAST_FAILURE['allocated_identities']['project_id'] == 123
    else:
        result = m.run(args)
        assert result['attempt_consumed'] is True and m.LAST_FAILURE is None
    assert events.index('claim.json') < events.index('DATA-enter') < events.index('DATA-normal-return')
    assert events.index('DATA-normal-return') < events.index('credentials') < events.index('API') < events.index('operate')
    assert events.count('claim.json') == 1


def test_directory_identity_failure_retains_new_fd_for_finally_close(tmp_path, monkeypatch):
    path = tmp_path / 'synthetic.py'; path.write_bytes(b'pass\n')
    sources = m.Sources(NS(), time.monotonic()+3599)
    opened, real_open, real_metadata, count = [], os.open, m.metadata, 0
    def observed_open(*args, **kwargs):
        fd = real_open(*args, **kwargs); opened.append(fd); return fd
    def changing(info):
        nonlocal count
        count += 1; value = real_metadata(info)
        return (*value[:7], value[7]+1, *value[8:]) if count == 3 else value
    monkeypatch.setattr(m.os, 'open', observed_open); monkeypatch.setattr(m, 'metadata', changing)
    try:
        refused('source_changed', lambda: sources.hold(path, m.pin(b'pass\n')))
    finally:
        sources.close()
    assert len(opened) == 2
    for fd in opened:
        with pytest.raises(OSError): os.fstat(fd)


def test_real_exclusive_store_keeps_claim_and_append_only_journal_fsynced(tmp_path, monkeypatch):
    root = tmp_path / 'synthetic-repository'; root.mkdir(mode=0o755)
    (root / 'artifacts').mkdir(mode=0o700)
    monkeypatch.setattr(m, 'ROOT', root)
    security = NS(snapshot=lambda fd: ('synthetic-empty-security', os.fstat(fd).st_uid))
    path = root / 'artifacts' / 'runs' / 'A'
    with m.Store(path, security) as store:
        store.write('claim.json', {'synthetic': True}); store.write('events.jsonl', b'')
        store.journal('project-created', {'project_id': 123})
        store.intent('files/create', 123); store.attempt('files/create', 123)
        assert store.application_dispatch_count == store.intents == 1
        raw = bytes(store.events)
        assert os.pread(store.journal_fd, len(raw)+1, 0) == raw
        store.write('report.json', {'synthetic': True}); store.verify()
    refused('claim_spent', lambda: m.Store(path, security).__enter__())
    assert (path/'events.jsonl').read_bytes() == raw


def test_native_policy_limits_read_to_exact_B_data_and_own_control():
    value = m.native_profile('R343-AR100')
    assert str(m.DATA) in value and 'R343-20261105-A' not in value
    assert '(deny process-exec (literal "/usr/bin/security"))' in value
    assert '/Library/Keychains' in value and '/Volumes' in value
    assert 'remote tcp "*:443"' in value and 'remote tcp "*:53"' in value
    assert str(m.control('R343-AR100')) in value


@pytest.mark.parametrize('value', ['R343-AR050', 'R343-AR080', 'R343-AR200', 'R343-AR100-A3', None])
def test_only_frozen_AR100_A2_recovery_is_exposed(value):
    refused('arguments', lambda: m.control(value))
