"""Synthetic AD source/transport protocol checks under native ALL-network denial."""
import copy
import inspect
import io
import json
import os
from pathlib import Path
import signal
import sys
import time
from types import SimpleNamespace as NS

import pytest
import requests

from scripts import inspect_arv2_r298_public_figi_lineage as m
from tests.analyst_revisions_v2 import test_r298_public_figi_corroboration as mapping_fixture

ARGS = NS(expected_head='a' * 40, caller_sha256='b' * 64)


def refused(code, function):
    with pytest.raises(m.Refused) as caught:
        function()
    assert m.finite(caught.value) == code


def synthetic_figi(index):
    stem = 'BBG' + ('%08d' % index)
    return next(stem + str(digit) for digit in range(10) if m.figi._figi(stem + str(digit)))


def inventory(candidates=1):
    stocks, retained = [], []
    for index in range(6151):
        binding = {'security_id': 'PRIVATE-ID-' + str(index), 'row_sha256': ('%064x' % index),
            'composite_figi': synthetic_figi(index % 5)}
        stocks.append({'binding_ordinal': index, 'binding': binding, 'disposition': 'routed', 'reason': None})
        retained.append({'binding_ordinal': index, 'binding': dict(binding),
            'current_candidate_rows': []})
    for index in range(5):
        stocks[index].update(disposition='refused', reason='identity_missing' if index < 4 else 'global_collision')
        retained[index]['current_candidate_rows'] = [{'figi': synthetic_figi(5 + index * candidates + item),
            'permaticker': 'PRIVATE-PERMA', 'ticker': 'PRIVATE-TICKER',
            'cusips': 'PRIVATE-CUSIP', 'name': 'PRIVATE-NAME'} for item in range(candidates)]
    funds = [{'fund_ordinal': index, 'ticker': 'PRIVATE-ETF-' + str(index)} for index in range(8)]
    return ({'binding_contract': {'synthetic': True}, 'stocks': stocks, 'funds': copy.deepcopy(funds)},
        {'binding_contract': {'synthetic': True}, 'stocks': retained, 'funds': copy.deepcopy(funds)})


def source_receipt():
    return {'schema': m.data_guard.SCHEMA + '-receipt',
        'profile_sha256': m.sha(m.data_guard.canonical(m.data_guard.profile_record(m.FILE_PLAN))),
        'files': {role: {**pin, 'current_metadata_sha256': 'd' * 64, 'current_security_sha256': 'e' * 64}
            for role, pin in m.FILE_PLAN.items()}, 'fresh_current_security_authenticated': True,
        'fixed_bytes_authenticated': True, 'requires_normal_return_before_use': True,
        'historical_continuity_proven': False, 'continuous_integrity_proven': False}


def actual(output=b'', *, exit=0, bound=None, errors=b''):
    return {'actual_exit': exit, 'bound': bound, 'spawn_observed': True,
        'dispatched_at': '2026-10-27T00:00:00Z', 'completion_observed_at': '2026-10-27T00:00:01Z',
        'stdout_bytes': len(output), 'stdout_sha256': m.sha(output),
        'stderr_bytes': len(errors), 'stderr_sha256': m.sha(errors)}


@pytest.fixture(autouse=True)
def no_old_operations(monkeypatch):
    def deny(*args, **kwargs): raise AssertionError('old operational function forbidden')
    monkeypatch.setattr(m.previous, 'run', deny)
    monkeypatch.setattr(m.previous, 'observe', deny)
    monkeypatch.setattr(m.previous, 'preflight', deny)
    monkeypatch.setattr(m.previous.routes, 'prepare', deny)


@pytest.fixture
def state(monkeypatch):
    ac, aa = inventory()
    state = NS(ac=ac, aa=aa, events=[], files={}, stores=0, sends=[], body_reads=0,
        fail_stage=None, status=200, response_raw=None, headers={}, cookies=False, response_bytes=None,
        session_count=0, invalid_body=False, invalid_header=False)
    monkeypatch.setattr(m, 'binding', lambda args: {'schema': m.SCHEMA,
        'expected_head': args.expected_head, 'caller_sha256': args.caller_sha256, 'profile_sha256': 'c' * 64})
    class MemoryStore:
        def __init__(self):
            state.stores += 1; m.require(state.stores == 1, 'claim_spent')
        def __enter__(self): return self
        def __exit__(self, *_): state.events.append('store_close')
        def verify(self): state.events.append('store_verify')
        def write(self, name, value): return self.write_bytes(name, m.canonical(value), private=False)
        def write_bytes(self, name, raw, *, private):
            m.require(name not in state.files, 'control_name')
            state.events.append('write:' + name)
            if state.fail_stage == name: raise m.Refused('control_write')
            if private and name == m.PRIVATE_NAME: assert 'source_return' in state.events
            if private and name in m.RESPONSE_NAMES: assert 'source_enter' in state.events and 'source_return' not in state.events
            state.files[name] = bytes(raw)
            return {'byte_count': len(raw), 'sha256': m.sha(raw)}
    class MemoryGuard:
        def __init__(self, plan, *, deadline):
            assert plan == m.FILE_PLAN; state.events.append('guard_construct')
        def __enter__(self):
            assert 'claim.json' in state.files and 'source-start.json' in state.files
            state.events.append('source_enter'); return self
        def __exit__(self, kind, *_):
            state.events.append('source_exit')
            if state.fail_stage == 'guard_return' and kind is None: raise m.data_guard.Refused('named_changed')
            if kind is None: state.events.append('source_return')
        def verify(self): state.events.append('source_verify')
        def read_all_once(self): state.events.append('source_read'); return {'synthetic': b'not actual private data'}
        def receipt(self):
            if state.fail_stage == 'source_receipt': raise m.data_guard.Refused('named_changed')
            return source_receipt()
    class Response:
        def __init__(self, prepared, raw):
            self.request, self.url, self.history = prepared, m.ENDPOINT, []
            self.status_code = state.status
            self.headers = {'Content-Type': 'application/json', 'Content-Length': str(len(raw)), **state.headers}
            self.raw_bytes = raw
        def __enter__(self): return self
        def __exit__(self, *_): state.events.append('response_closed')
        def iter_content(self, *, chunk_size, decode_unicode=False):
            state.body_reads += 1
            assert self.status_code == 200 and chunk_size == 65536 and decode_unicode is False
            if state.fail_stage == 'body_transport': raise requests.ConnectionError('PRIVATE-RAW-ERROR')
            if state.fail_stage == 'body_after_partial':
                yield b'['
                raise requests.ConnectionError('PRIVATE-RAW-ERROR')
            yield self.raw_bytes
    original_session = m._session
    def session():
        state.session_count += 1
        return original_session()
    def send(session, prepared, **kwargs):
        state.events.append('send')
        index = len(state.sends)
        assert 'dispatch-%02d.json' % (index + 1) in state.files
        assert prepared.url == m.ENDPOINT and prepared.method == 'POST'
        assert b'PRIVATE-' not in prepared.body and b'CUSIP' not in prepared.body
        assert set(kwargs) == {'timeout', 'allow_redirects', 'stream', 'verify', 'proxies'}
        assert kwargs['allow_redirects'] is False and kwargs['stream'] is True and kwargs['verify'] is True
        assert kwargs['proxies'] == {} and 0 < kwargs['timeout'] <= m.REQUEST_SECONDS
        jobs = json.loads(prepared.body)
        assert all(set(job) == {'idType', 'idValue', 'includeUnlistedEquities'} for job in jobs)
        state.sends.append(prepared)
        if state.fail_stage == 'transport': raise requests.ConnectionError('PRIVATE-RAW-ERROR')
        if state.cookies: session.cookies['PRIVATE-COOKIE'] = 'PRIVATE-COOKIE-VALUE'
        raw = m.figi.canonical([{'data': [mapping_fixture.row(job['idValue'])]} for job in jobs])
        if state.response_raw is not None: raw = state.response_raw
        if state.response_bytes is not None: raw = state.response_bytes
        return Response(prepared, raw)
    real_analyze = m.figi.analyze_batch
    def analyze(*args, **kwargs):
        state.events.append('analyze')
        if kwargs['http_status'] == 200:
            expected_name = m.RESPONSE_NAMES[len([name for name in state.files if name in m.RESPONSE_NAMES]) - 1]
            assert state.files[expected_name] == kwargs['response_raw']
            assert state.events.index('write:' + expected_name) < len(state.events) - 1
        return real_analyze(*args, **kwargs)
    def preflight(*args):
        state.events.append('postflight')
        if state.fail_stage == 'postflight': raise m.Refused('source_pin')
    monkeypatch.setattr(m, 'Store', MemoryStore); monkeypatch.setattr(m.data_guard, 'FixedDataGuard', MemoryGuard)
    monkeypatch.setattr(m, '_frames', lambda buffers, deadline: (state.ac, state.aa))
    monkeypatch.setattr(m, '_session', session); monkeypatch.setattr(requests.Session, 'send', send)
    monkeypatch.setattr(m.figi, 'analyze_batch', analyze)
    monkeypatch.setattr(m, 'preflight', preflight)
    monkeypatch.setattr(m.environment, 'require_safe_environment', lambda: state.events.append('safe_environment'))
    return state


def run():
    return m.run(ARGS, time.monotonic() + 100)


def test_one_claim_all_five_cases_public_FIGIs_only_raw_capture_before_parse_and_final_after_guard(state):
    outcome = run()
    assert set(outcome) == {'result', 'report'} and state.session_count == 1 and len(state.sends) == 1
    result = outcome['result']
    assert result['selection_summary']['case_count'] == 5 and result['vendor_source_blockers_remaining'] == 5
    assert result['mapping_complete'] is True and result['provider_request_count'] is None
    assert result['corroboration_counts'] == {'unresolved_share_class_only': 5}
    order = ['write:claim.json', 'write:source-start.json', 'source_enter', 'source_read',
        'write:dispatch-01.json', 'send', 'write:response-01.json', 'analyze',
        'source_exit', 'source_return', 'write:' + m.PRIVATE_NAME, 'postflight', 'write:report.json']
    assert [state.events.index(item) for item in order] == sorted(state.events.index(item) for item in order)
    public = m.canonical(outcome)
    assert b'PRIVATE-' not in public
    assert all(job['idValue'].encode() not in public for prepared in state.sends for job in json.loads(prepared.body))
    package = json.loads(state.files[m.PRIVATE_NAME])
    assert len(package['selection']['cases']) == 5 and len(package['mapping_batches']) == 1
    assert package['no_original_identifier_or_vendor_collision_clearance'] is True
    value = {'binding': m.binding(ARGS), 'outcome': outcome}
    assert m.validate_output(m.canonical(value), 0, ARGS) == value
    assert all(result[flag] is False for flag in m.FALSE_FLAGS)


def test_exactly_thirty_unique_FIGIs_make_three_distinct_no_retry_batches(state):
    state.ac, state.aa = inventory(5)
    outcome = run()['result']
    assert len(state.sends) == 3 and [len(json.loads(request.body)) for request in state.sends] == [10, 10, 10]
    claims = [job['idValue'] for request in state.sends for job in json.loads(request.body)]
    assert len(claims) == len(set(claims)) == 30 and outcome['selection_summary']['planned_job_count'] == 30


@pytest.mark.parametrize('fault,code', [('missing','candidate_figi_missing'), ('invalid','candidate_figi_invalid'),
    ('no_rows','candidate_rows_missing'), ('malformed','candidate_row_shape'), ('original','original_figi_invalid'),
    ('too_many','figi_inventory_bound'), ('case_bound','case_bound')])
def test_entire_inventory_refuses_before_contact_and_retains_all_five_cases_after_normal_return(state, monkeypatch, fault, code):
    if fault == 'missing': state.aa['stocks'][0]['current_candidate_rows'][0]['figi'] = ''
    elif fault == 'invalid': state.aa['stocks'][0]['current_candidate_rows'][0]['figi'] = 'BBG000BLNNH7'
    elif fault == 'no_rows': state.aa['stocks'][0]['current_candidate_rows'] = []
    elif fault == 'malformed': state.aa['stocks'][0]['current_candidate_rows'][0] = ['PRIVATE-MALFORMED']
    elif fault == 'original': state.ac['stocks'][0]['binding']['composite_figi'] = 'PRIVATE-INVALID'
    elif fault == 'too_many':
        state.ac, state.aa = inventory(5)
        state.aa['stocks'][0]['current_candidate_rows'].append({'figi': synthetic_figi(100)})
    else: monkeypatch.setattr(m, 'MAX_CASES', 1)
    failed = run()['failure']
    assert failed['failure_code'] == code and failed['claim_consumed'] is True
    assert state.session_count == 0 and state.sends == [] and state.body_reads == 0
    assert failed['state']['selection_summary']['case_count'] == 5 and failed['state']['dispatch_intents'] == []
    assert failed['state']['source_guard_returned'] is True and m.PRIVATE_NAME in state.files
    assert len(json.loads(state.files[m.PRIVATE_NAME])['selection']['cases']) == 5
    value = {'binding': m.binding(ARGS), 'outcome': {'failure': failed}}
    assert m.validate_output(m.canonical(value), 2, ARGS) == value
    refused('claim_spent', run)


@pytest.mark.parametrize('status', [301,401,403,429,500])
def test_non200_records_numeric_status_never_reads_body_and_never_retries(state, status):
    state.status = status
    failed = run()['failure']
    assert failed['failure_code'] == 'http_status' and failed['state']['http_statuses'] == [status]
    assert len(state.sends) == 1 and state.body_reads == 0 and not set(m.RESPONSE_NAMES) & set(state.files)
    assert failed['state']['dispatch_intents'][0]['dispatch_intent_count'] == 1
    assert failed['provider_request_count'] is None and m.PRIVATE_NAME in state.files
    assert m.validate_output(m.canonical({'binding':m.binding(ARGS),'outcome':{'failure':failed}}),2,ARGS)


@pytest.mark.parametrize('failure', ['transport','body_transport','guard_return','postflight','report.json',
    'response-01.json','public-figi-private.json'])
def test_transport_or_owned_output_failure_is_finite_consumed_and_preserves_provisional_evidence(state, failure):
    state.fail_stage = failure
    failed = run()['failure']
    assert failed['claim_consumed'] is True and len(state.sends) <= 1
    assert b'PRIVATE-RAW-ERROR' not in m.canonical(failed)
    assert failed['provider_request_count'] is None
    if failure == 'guard_return':
        assert 'response-01.json' in state.files and m.PRIVATE_NAME not in state.files
    assert m.validate_output(m.canonical({'binding':m.binding(ARGS),'outcome':{'failure':failed}}),2,ARGS)


def test_malformed_success_body_is_retained_before_semantic_refusal_and_not_accepted(state):
    state.response_raw = b'not JSON but retained diagnostic evidence'
    failed = run()['failure']
    assert state.files['response-01.json'] == state.response_raw
    assert failed['failure_code'].startswith('figi_') and failed['state']['mapping_complete'] is False
    assert failed['state']['source_guard_returned'] is True and m.PRIVATE_NAME in state.files


@pytest.mark.parametrize('fault,code', [('encoding','response_headers'), ('content_type','response_headers'),
    ('length','response_bound'), ('oversize','response_bound'), ('set_cookie','response_headers'), ('cookie','cookie')])
def test_response_shape_bounds_and_cookie_refusals_are_terminal_without_body_fallback(state, fault, code):
    if fault == 'encoding': state.headers['Content-Encoding'] = 'gzip'
    elif fault == 'content_type': state.headers['Content-Type'] = 'text/html'
    elif fault == 'length': state.headers['Content-Length'] = '9' * 20
    elif fault == 'oversize': state.response_bytes = b'x' * (m.MAX_BODY + 1)
    elif fault == 'set_cookie': state.headers['Set-Cookie'] = 'PRIVATE-COOKIE'
    else: state.cookies = True
    failed = run()['failure']
    assert failed['failure_code'] == code and len(state.sends) == 1
    assert failed['state']['mapping_complete'] is False


def test_two_source_pins_are_both_checked_before_any_JSON_interpretation(monkeypatch):
    monkeypatch.setattr(m,'_decode_private',lambda raw: (_ for _ in ()).throw(AssertionError('not reached')))
    refused('frame',lambda:m._frames({'ac_plan':b'wrong','aa_frame':b'wrong'},time.monotonic()+10))


@pytest.mark.parametrize('fault', ['last_binding','first_ordinal','last_fund','count'])
def test_all_6151_bindings_and_eight_funds_align_not_only_selected_five(fault):
    ac,aa=inventory()
    if fault=='last_binding': aa['stocks'][-1]['binding']['row_sha256']='f'*64
    elif fault=='first_ordinal': ac['stocks'][1]['binding_ordinal']=True
    elif fault=='last_fund': aa['funds'][-1]['ticker']='PRIVATE-DIFFERENT'
    else: aa['stocks'].pop()
    refused('inventory',lambda:m._aligned_inventory(ac,aa,ac['binding_contract'],time.monotonic()+30))


def test_exact_alarm_exception_maps_deadline_but_foreign_subclass_is_unknown():
    assert m.finite(m.admitted.helpers.Deadline())=='deadline'
    class Foreign(m.admitted.helpers.Deadline): pass
    assert m.finite(Foreign())=='unknown_exception'


def test_request_alarm_restores_remaining_parent_timer_and_handler(monkeypatch):
    clock=NS(now=100.0);calls=[];prior=object()
    fake=NS(SIGALRM=1,ITIMER_REAL=2,getsignal=lambda _:prior,getitimer=lambda _:(60.0,0.0),
        signal=lambda sig,handler:calls.append(('handler',handler)),
        setitimer=lambda timer,value,interval=0:calls.append(('timer',value,interval)))
    monkeypatch.setattr(m,'signal',fake)
    monkeypatch.setattr(m.time,'monotonic',lambda:clock.now)
    with m._request_alarm(130.0):
        clock.now=110.0
    timers=[item for item in calls if item[0]=='timer']
    assert timers==[('timer',30.0,0),('timer',0,0),('timer',50.0,0.0)]
    assert calls[-2]==('handler',prior)


def test_real_inner_request_alarm_expires_without_network_or_artifact_access():
    old_handler=signal.getsignal(signal.SIGALRM);old_timer=signal.getitimer(signal.ITIMER_REAL)
    assert old_timer[0]==0
    with pytest.raises(m.admitted.helpers.Deadline):
        with m._request_alarm(time.monotonic()+0.02):
            time.sleep(0.1)
    assert signal.getsignal(signal.SIGALRM)==old_handler and signal.getitimer(signal.ITIMER_REAL)[0]==0


def test_current_public_identity_positive_never_clears_five_vendor_source_blockers(state):
    for index in range(5):
        state.aa['stocks'][index]['current_candidate_rows'][0]['figi'] = state.ac['stocks'][index]['binding']['composite_figi']
    result = run()['result']
    assert result['corroboration_counts'] == {'same_current_us_composite_observed': 5}
    assert result['vendor_source_blockers_remaining'] == 5 and result['vendor_global_collision_cleared'] is False
    assert result['original_FIGI_replaced'] is False and result['strategy_price_admitted'] is False


def test_partial_received_bytes_are_not_reported_as_completed_body_bytes_or_no_contact(state):
    state.fail_stage = 'body_after_partial'
    failed = run()['failure']
    assert failed['failure_code'] == 'transport_unknown' and failed['state']['http_statuses'] == [200]
    assert state.body_reads == 1 and failed['state']['response_bytes'] == 0
    assert failed['state']['response_pins'] == {} and failed['provider_request_count'] is None


def test_owned_preparation_ignores_proxy_netrc_cookie_and_API_key_environment(monkeypatch):
    monkeypatch.setenv('HTTPS_PROXY', 'http://PRIVATE-PROXY')
    monkeypatch.setenv('OPENFIGI_API_KEY', 'PRIVATE-TOKEN')
    monkeypatch.setenv('REQUESTS_CA_BUNDLE', '/PRIVATE-CERT')
    raw = m._jobs([synthetic_figi(0)])
    with m._session() as session:
        prepared = m._prepared(session, raw)
        assert session.trust_env is False and session.auth is None and not session.cookies and not session.proxies
        assert prepared.hooks == {'response': []} and b'PRIVATE-' not in prepared.body
        assert all('PRIVATE-' not in value for value in prepared.headers.values())


def test_real_owned_Session_send_302_location_never_consumes_failed_body_or_loses_numeric_status(monkeypatch):
    calls = NS(body_reads=0, sends=0, writes=[])
    class Raw:
        def stream(self, *args, **kwargs):
            calls.body_reads += 1
            yield b'FAILED-REDIRECT-BODY-MUST-NOT-BE-READ'
        def close(self): pass
        def release_conn(self): pass
    class Adapter(requests.adapters.BaseAdapter):
        max_retries = NS(total=0)
        def send(self, request, **kwargs):
            calls.sends += 1
            response = requests.Response()
            response.status_code, response.url, response.request = 302, m.ENDPOINT, request
            response.headers['Location'] = 'https://example.invalid/never-follow'
            response.raw = Raw()
            return response
        def close(self): pass
    class Directory:
        def write(self, name, value):
            calls.writes.append(name)
            return {'byte_count': len(m.canonical(value)), 'sha256': m.sha(m.canonical(value))}
        def write_bytes(self, *args, **kwargs): raise AssertionError('no non200 body capture')
    state = {'dispatch_intents': [], 'http_statuses': [], 'response_pins': {}, 'response_bytes': 0}
    monkeypatch.setattr(m, 'binding', lambda args: {'synthetic': True})
    monkeypatch.setattr(m.environment, 'require_safe_environment', lambda: None)
    with m._session() as session:
        assert type(session) is m.OwnedSession
        session.mount('https://', Adapter())
        status, raw = m._fetch(session, [synthetic_figi(0)], m._jobs([synthetic_figi(0)]), 0,
            Directory(), NS(verify=lambda: None), state, ARGS, time.monotonic() + 30)
    assert status == 302 and raw is None and state['http_statuses'] == [302]
    assert calls.sends == 1 and calls.body_reads == 0 and calls.writes == ['dispatch-01.json']


def test_foreign_session_or_subclass_cannot_change_owned_redirect_policy():
    with requests.Session() as session:
        refused('request', lambda: m._session_check(session))
    class Foreign(m.OwnedSession): pass
    with Foreign() as session:
        refused('request', lambda: m._session_check(session))


@pytest.mark.parametrize('fault', ['url','method','body','cookie','auth','hook'])
def test_changed_prepared_request_refuses_before_dispatch(fault, monkeypatch):
    with m._session() as session:
        prepare = session.prepare_request
        def altered(request):
            prepared = prepare(request)
            if fault == 'url': prepared.url += '?PRIVATE-TOKEN'
            elif fault == 'method': prepared.method = 'GET'
            elif fault == 'body': prepared.body = b'PRIVATE-ROW'
            elif fault == 'cookie': prepared.headers['Cookie'] = 'PRIVATE-COOKIE'
            elif fault == 'auth': prepared.headers['Authorization'] = 'PRIVATE-AUTH'
            else: prepared.hooks['response'].append(lambda response: response)
            return prepared
        monkeypatch.setattr(session, 'prepare_request', altered)
        refused('request', lambda: m._prepared(session, m._jobs([synthetic_figi(0)])))


@pytest.mark.parametrize('exit', [2,False,None])
def test_successful_report_never_substitutes_for_observed_actual_zero(state, exit):
    raw = m.canonical({'binding':m.binding(ARGS),'outcome':run()})
    refused('output', lambda:m.validate_output(raw,exit,ARGS))


def test_exact_public_source_closure_and_anonymous_profile_do_not_refresh_pins():
    assert len(m.pins()) == 178
    for name,pin in m.pins().items(): assert m.sha((m.ROOT/name).read_bytes()) == pin
    profile=m.profile_record()
    assert profile['source_data_leaf_count']==2 and profile['maximum_source_bytes']==64*1024*1024
    assert profile['maximum_aggregate_response_bytes']==6*1024*1024
    assert 'not_partial_wire_bytes' in profile['response_bytes_measure']
    assert profile['exchange_or_market_filters'] is False
    assert profile['job_identifier_type']=='ID_BB_GLOBAL'
    assert profile['candidate_scope'].endswith('not_vendor_global_CUSIP_or_poison_census')
    assert profile['API_key_auth_cookie_proxy_or_env_credentials'] is False
    assert all(profile[key] is False for key in m.FALSE_FLAGS)
    producer,validator=m.native_profile(mode='producer'),m.native_profile(mode='validator')
    assert 'remote tcp "*:443"' in producer and 'remote udp "*:53"' in producer
    assert '(deny network*)' in validator and 'Library/Keychains' in producer and '/usr/bin/security' in producer
    assert '01-tickers-years-full.zip' not in producer and 'membership-demand-private.json' not in producer


def test_changed_prior_report_observation_refuses_before_private_open(monkeypatch):
    fact = m.anchor.observed_fact()
    fact['report']['sha256'] = 'f' * 64
    monkeypatch.setattr(m.anchor, 'observed_fact', lambda: fact)
    refused('source_binding', m.source_binding)

@pytest.mark.parametrize('fault', ['producer_nonzero', 'producer_bool', 'producer_timeout',
    'producer_noise', 'producer_binding', 'validator_nonzero', 'validator_bool', 'validator_noise', 'validator_binding'])
def test_no_data_observer_requires_exact_native_producer_and_separate_validator_actuals(state, monkeypatch, fault):
    value = {'binding': m.binding(ARGS), 'outcome': run()}
    raw = m.canonical(value)
    calls = []
    def capture(command, safe, timeout, **kwargs):
        calls.append((command, safe, timeout, kwargs))
        assert command[:2] == ['/usr/bin/sandbox-exec', '-p']
        assert ('network-outbound' in command[2] if len(calls) == 1 else '(deny network*)' in command[2]) and '/usr/bin/security' in command[2]
        producer = len(calls) == 1
        errors = b'noise' if fault == ('producer_noise' if producer else 'validator_noise') else b''
        exit = (2 if fault == ('producer_nonzero' if producer else 'validator_nonzero') else
            False if fault == ('producer_bool' if producer else 'validator_bool') else 0)
        if fault == 'producer_nonzero' and not producer:
            # A real external validator refuses a success envelope paired
            # with observed producer exit2, rather than fabricating exit0.
            refused('output', lambda: m.validate_output(raw, 2, ARGS))
            exit = 2
        output = raw if not (fault == 'validator_binding' and not producer) else m.canonical({'wrong': 'metadata'})
        checked = actual(output, exit=exit, errors=errors,
            bound='deadline' if fault == 'producer_timeout' and producer else None)
        if fault == 'producer_binding' and producer: checked['stdout_sha256'] = 'f' * 64
        if not producer:
            assert kwargs['input_bytes'] == raw and timeout == m.VALIDATOR_SECONDS
        return output, errors, checked
    monkeypatch.setattr(m, 'capture', capture)
    outer, code = m.observe(ARGS)
    assert code == 2 and outer['output_authenticated'] is False
    assert len(calls) == (1 if fault.startswith('producer_') and fault != 'producer_nonzero' else 2)
    assert outer['failure_code'] in ('parent_failed', 'validator_failed')


def test_observer_authenticates_failure_without_reclassifying_it_success(state, monkeypatch):
    state.status = 403
    raw = m.canonical({'binding': m.binding(ARGS), 'outcome': run()})
    calls = []
    def capture(command, safe, timeout, **kwargs):
        calls.append(command)
        return raw, b'', actual(raw, exit=2 if len(calls) == 1 else 0)
    monkeypatch.setattr(m, 'capture', capture)
    outer, code = m.observe(ARGS)
    assert code == 2 and outer['output_authenticated'] is True and outer['failure_code'] is None
    assert outer['output']['outcome']['failure']['claim_consumed'] is True and len(calls) == 2


def test_observer_public_only_success_broker_never_opens_private_output(state, monkeypatch):
    value = {'binding': m.binding(ARGS), 'outcome': run()}; raw = m.canonical(value)
    calls = []
    def capture(command, safe, timeout, **kwargs):
        calls.append(command)
        return raw, b'', actual(raw)
    monkeypatch.setattr(m, 'capture', capture)
    outer, code = m.observe(ARGS)
    assert code == 0 and outer['output_authenticated'] is True and outer['output'] == value
    assert b'PRIVATE-' not in m.canonical(outer)
    assert len(calls) == 2


@pytest.mark.parametrize('fault', ['zero', 'placeholder', 'conflict', 'baseline_count'])
def test_unfrozen_or_conflicting_source_pin_map_refuses(fault, monkeypatch):
    baseline = {'scripts/existing-' + str(i) + '.py': 'd' * 64 for i in range(175)}
    monkeypatch.setattr(m.previous, 'pins', lambda: baseline)
    additions = {'scripts/new.py': 'e' * 64}
    if fault == 'zero': additions['scripts/new.py'] = '0' * 64
    elif fault == 'placeholder': additions['scripts/new.py'] = 'UNFROZEN'
    elif fault == 'conflict': additions['scripts/existing-1.py'] = 'f' * 64
    else: baseline.pop('scripts/existing-1.py')
    monkeypatch.setattr(m, 'NEW_PINS', additions)
    refused('source_pin', m.pins)


def test_real_new_control_store_is_exclusive_bounded_held_and_preserves_failure_leaf(tmp_path, monkeypatch):
    control = tmp_path / 'synthetic-AA-parent/synthetic-AA'
    monkeypatch.setattr(m, 'CONTROL', control)
    with m.Store() as store:
        pin = store.write('claim.json', {'synthetic': True})
        assert pin == {'byte_count': len(m.canonical({'synthetic': True})),
            'sha256': m.sha(m.canonical({'synthetic': True}))}
        private = b'synthetic-private-in-cache-only'
        private_pin = store.write_bytes(m.PRIVATE_NAME, private, private=True)
        assert private_pin == {'byte_count': len(private), 'sha256': m.sha(private)}
        held = store.held[m.PRIVATE_NAME][0]
        assert store._read(held, len(private)) == private
        refused('control_name', lambda: store.write('claim.json', {}))
        refused('control_name', lambda: store.write_bytes('stocks-metadata.csv', b'denied', private=True))
        refused('control_name', lambda: store.write('../elsewhere.json', {}))
        refused('control_bound', lambda: store.write_bytes('empty.json', b'', private=False))
        refused('claim_spent', m.Store)
        store.verify()
    assert control.is_dir() and {path.name for path in control.iterdir()} == {'claim.json', m.PRIVATE_NAME}
    with pytest.raises(OSError): os.fstat(held)


@pytest.mark.parametrize('change', ['content', 'mode', 'name', 'extra_name'])
def test_real_owned_control_detects_external_drift_without_cleanup(tmp_path, monkeypatch, change):
    control = tmp_path / 'synthetic-AA-parent/synthetic-AA'
    monkeypatch.setattr(m, 'CONTROL', control)
    with m.Store() as store:
        store.write('claim.json', {'synthetic': True})
        path = control / 'claim.json'
        if change == 'content': path.write_bytes(b'changed')
        elif change == 'mode': path.chmod(0o644)
        elif change == 'extra_name': (control / 'synthetic-unexpected').write_bytes(b'extra')
        else:
            path.rename(control / 'synthetic-retained-old')
            path.write_bytes(b'changed'); path.chmod(0o600)
        refused('control_changed' if change in ('extra_name', 'name') else 'capture_changed', store.verify)
    assert control.is_dir()


def test_cli_parent_and_validator_use_alarm_and_preflight_before_any_operation(monkeypatch):
    events, stdout = [], io.BytesIO()
    class Alarm:
        def __init__(self, deadline):
            assert 0 < deadline - time.monotonic() <= m.DEADLINE_SECONDS
            events.append('alarm_construct')
        def __enter__(self): events.append('alarm_enter')
        def __exit__(self, *_): events.append('alarm_exit')
    monkeypatch.setattr(m.admitted.helpers, '_alarm', Alarm)
    monkeypatch.setattr(m, 'preflight', lambda *args: events.append('preflight'))
    monkeypatch.setattr(m.environment, '_bootstrap_cli_logging', lambda: events.append('logging'))
    monkeypatch.setattr(m, 'binding', lambda args: {'synthetic': True})
    def run(args, deadline):
        events.append('run'); return {'failure': {'synthetic': True}}
    monkeypatch.setattr(m, 'run', run)
    monkeypatch.setattr(m.sys, 'stdout', NS(buffer=stdout))
    assert m.main(['run', '--expected-head', ARGS.expected_head, '--caller-sha256', ARGS.caller_sha256]) == 2
    assert events == ['alarm_construct', 'alarm_enter', 'preflight', 'logging', 'run', 'alarm_exit']
    assert json.loads(stdout.getvalue()) == {'binding': {'synthetic': True},
        'outcome': {'failure': {'synthetic': True}}}


@pytest.fixture
def public_preflight(monkeypatch):
    raw = m.SOURCE.read_bytes()
    args = NS(expected_head='a' * 40, caller_sha256=m.sha(raw))
    state = NS(raw=raw, args=args, calls=[], change=None)
    monkeypatch.setattr(m.admitted.v5, '_under_test', lambda: False)
    monkeypatch.setattr(m.environment, '_require_environment', lambda: None)
    monkeypatch.setattr(m, 'pins', lambda: {m.SOURCE.relative_to(m.ROOT).as_posix():
        'f' * 64 if state.change == 'selected_pin' else m.sha(raw)})
    values = {('rev-parse', '--show-toplevel'): str(m.ROOT),
        ('branch', '--show-current'): m.admitted.frozen.BRANCH,
        ('rev-parse', 'HEAD'): args.expected_head, ('status', '--porcelain'): ''}
    def git(command, deadline, *args):
        state.calls.append(command)
        if command[0] == 'cat-file':
            return b'wrong committed source bytes' if state.change == 'committed_blob' else raw
        value = values[tuple(command)]
        if state.change == tuple(command): value = 'concurrent or mismatched synthetic state'
        return value.encode('ascii')
    monkeypatch.setattr(m.admitted.v5, '_git', git)
    return state


def test_preflight_binds_exact_host_clean_root_branch_head_source_and_committed_blob(public_preflight):
    fixture = public_preflight
    m.preflight(fixture.args, time.monotonic() + 30)
    assert fixture.calls[:4] == [['rev-parse', '--show-toplevel'], ['branch', '--show-current'],
        ['rev-parse', 'HEAD'], ['status', '--porcelain']]
    assert fixture.calls[-1] == ['cat-file', 'blob', fixture.args.expected_head + ':'
        + m.SOURCE.relative_to(m.ROOT).as_posix()]


@pytest.mark.parametrize('change', [('rev-parse', '--show-toplevel'), ('branch', '--show-current'),
    ('rev-parse', 'HEAD'), ('status', '--porcelain'), 'selected_pin', 'caller_pin', 'committed_blob'])
def test_preflight_concurrent_git_or_source_mismatch_refuses_without_refresh(public_preflight, change):
    fixture = public_preflight; fixture.change = change
    if change == 'caller_pin': fixture.args.caller_sha256 = 'f' * 64
    refused('git_state' if type(change) is tuple else 'source_pin',
        lambda: m.preflight(fixture.args, time.monotonic() + 30))


def test_preflight_test_host_and_invalid_args_refuse_before_git(public_preflight, monkeypatch):
    fixture = public_preflight
    monkeypatch.setattr(m.admitted.v5, '_under_test', lambda: True)
    refused('host', lambda: m.preflight(fixture.args, time.monotonic() + 30))
    assert fixture.calls == []
    monkeypatch.setattr(m.admitted.v5, '_under_test', lambda: False)
    fixture.args.expected_head = 'not a frozen commit'
    refused('arguments', lambda: m.preflight(fixture.args, time.monotonic() + 30))
    assert fixture.calls == []
